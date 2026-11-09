"""Local household data. Manual decisions have priority over imported observations."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

PROVIDERS = {"netflix": "Netflix", "prime": "Prime Video", "disney": "Disney+", "crunchyroll": "Crunchyroll"}


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS profiles(id INTEGER PRIMARY KEY, name TEXT NOT NULL, color TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS shows(id INTEGER PRIMARY KEY, name TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
                    image TEXT, url TEXT NOT NULL, premiered TEXT, status TEXT);
                CREATE TABLE IF NOT EXISTS episodes(id INTEGER PRIMARY KEY, show_id INTEGER NOT NULL REFERENCES shows(id),
                    season INTEGER NOT NULL, number INTEGER, name TEXT NOT NULL, airdate TEXT,
                    UNIQUE(show_id,season,number));
                CREATE TABLE IF NOT EXISTS lists(profile_id INTEGER REFERENCES profiles(id), show_id INTEGER REFERENCES shows(id),
                    provider TEXT NOT NULL, on_watchlist INTEGER NOT NULL DEFAULT 1, source TEXT NOT NULL DEFAULT 'manual',
                    PRIMARY KEY(profile_id,show_id,provider));
                CREATE TABLE IF NOT EXISTS progress(profile_id INTEGER REFERENCES profiles(id), episode_id INTEGER REFERENCES episodes(id),
                    watched INTEGER NOT NULL, source TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(profile_id,episode_id));
                CREATE TABLE IF NOT EXISTS show_state(profile_id INTEGER REFERENCES profiles(id), show_id INTEGER REFERENCES shows(id),
                    status TEXT NOT NULL DEFAULT 'watching', PRIMARY KEY(profile_id,show_id));
                CREATE TABLE IF NOT EXISTS hidden(profile_id INTEGER REFERENCES profiles(id), show_id INTEGER REFERENCES shows(id),
                    PRIMARY KEY(profile_id,show_id));
                CREATE TABLE IF NOT EXISTS connections(profile_id INTEGER REFERENCES profiles(id), provider TEXT NOT NULL,
                    source_profile TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 0,
                    last_sync TEXT, last_attempt TEXT, message TEXT NOT NULL DEFAULT 'Noch nicht verbunden',
                    PRIMARY KEY(profile_id,provider));
                CREATE TABLE IF NOT EXISTS mappings(profile_id INTEGER, provider TEXT, provider_id TEXT,
                    show_id INTEGER REFERENCES shows(id), PRIMARY KEY(profile_id,provider,provider_id));
                CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id INTEGER REFERENCES profiles(id),
                    provider TEXT NOT NULL, provider_id TEXT NOT NULL, section TEXT NOT NULL, title TEXT NOT NULL,
                    payload TEXT NOT NULL, show_id INTEGER REFERENCES shows(id), captured_at TEXT NOT NULL,
                    UNIQUE(profile_id,provider,provider_id,section));
                PRAGMA user_version=1;
            """)
            db.executemany("INSERT OR IGNORE INTO profiles VALUES(?,?,?)", [(1,"Person 1","#d5a377"),(2,"Person 2","#a5b9a8")])
            db.executemany("INSERT OR IGNORE INTO connections(profile_id,provider) VALUES(?,?)", [(p,k) for p in (1,2) for k in PROVIDERS])

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def profile(self, profile_id):
        with self.db() as db:
            if not db.execute("SELECT 1 FROM profiles WHERE id=?", (profile_id,)).fetchone():
                raise ValueError("Profil nicht gefunden")

    def profiles(self):
        with self.db() as db:
            return [dict(x) for x in db.execute("SELECT * FROM profiles ORDER BY id")]

    def rename(self, profile_id, name):
        self.profile(profile_id)
        with self.db() as db:
            db.execute("UPDATE profiles SET name=? WHERE id=?", (name,profile_id))

    def cache_show(self, show, episodes):
        with self.db() as db:
            db.execute("""INSERT INTO shows(id,name,summary,image,url,premiered,status) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,summary=excluded.summary,image=excluded.image,
                premiered=excluded.premiered,status=excluded.status""",
                (show["id"],show["name"],show.get("summary") or "",(show.get("image") or {}).get("medium"),
                 show["url"],show.get("premiered"),show.get("status")))
            db.executemany("""INSERT INTO episodes(id,show_id,season,number,name,airdate) VALUES(?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET season=excluded.season,number=excluded.number,name=excluded.name,airdate=excluded.airdate""",
                [(e["id"],show["id"],e["season"],e.get("number"),e["name"],e.get("airdate")) for e in episodes])

    def add(self, profile_id, show_id, provider, source="manual", on_watchlist=True):
        self.profile(profile_id)
        if provider not in PROVIDERS:
            raise ValueError("Unbekannter Dienst")
        with self.db() as db:
            if not db.execute("SELECT 1 FROM shows WHERE id=?", (show_id,)).fetchone():
                raise ValueError("Serie nicht gefunden")
            db.execute("""INSERT INTO lists(profile_id,show_id,provider,source,on_watchlist) VALUES(?,?,?,?,?)
                ON CONFLICT(profile_id,show_id,provider) DO UPDATE SET
                on_watchlist=CASE WHEN lists.source='manual' AND excluded.source!='manual' THEN lists.on_watchlist ELSE excluded.on_watchlist END,
                source=CASE WHEN excluded.source='manual' THEN 'manual' ELSE lists.source END""",
                (profile_id,show_id,provider,source,int(on_watchlist)))
            if source=="manual":
                db.execute("DELETE FROM hidden WHERE profile_id=? AND show_id=?",(profile_id,show_id))

    def remove(self, profile_id, show_id):
        self.profile(profile_id)
        with self.db() as db:
            # Progress is retained when a title is removed from the household list.
            db.execute("DELETE FROM lists WHERE profile_id=? AND show_id=?", (profile_id,show_id))
            if db.execute("SELECT 1 FROM shows WHERE id=?",(show_id,)).fetchone():
                db.execute("INSERT OR IGNORE INTO hidden VALUES(?,?)",(profile_id,show_id))

    def set_status(self, profile_id, show_id, status):
        if status not in {"watching","paused","finished"}:
            raise ValueError("Ungültiger Status")
        with self.db() as db:
            if not db.execute("SELECT 1 FROM lists WHERE profile_id=? AND show_id=?",(profile_id,show_id)).fetchone():
                raise ValueError("Serie nicht auf deiner Liste")
            db.execute("INSERT INTO show_state VALUES(?,?,?) ON CONFLICT(profile_id,show_id) DO UPDATE SET status=excluded.status",(profile_id,show_id,status))

    def mark(self, profile_id, show_id, episode_id, watched, through=False):
        self.profile(profile_id)
        with self.db() as db:
            e = db.execute("SELECT * FROM episodes WHERE id=? AND show_id=?",(episode_id,show_id)).fetchone()
            if not e or not db.execute("SELECT 1 FROM lists WHERE profile_id=? AND show_id=?",(profile_id,show_id)).fetchone():
                raise ValueError("Folge nicht auf deiner Liste")
            if through:
                rows = db.execute("SELECT id FROM episodes WHERE show_id=? AND season>0 AND (season<? OR (season=? AND number<=?))",(show_id,e["season"],e["season"],e["number"]))
                ids = [r[0] for r in rows]
            else:
                ids = [episode_id]
            db.executemany("""INSERT INTO progress VALUES(?,?,?,?,?) ON CONFLICT(profile_id,episode_id)
                DO UPDATE SET watched=excluded.watched,source='manual',updated_at=excluded.updated_at""",
                [(profile_id,i,int(watched),"manual",now()) for i in ids])

    def episodes(self, profile_id, show_id):
        self.profile(profile_id)
        with self.db() as db:
            return [dict(x) for x in db.execute("""SELECT e.*, COALESCE(p.watched,0) AS watched,p.source FROM episodes e
                LEFT JOIN progress p ON p.episode_id=e.id AND p.profile_id=? WHERE e.show_id=? ORDER BY season,number,id""",(profile_id,show_id))]

    def library(self, profile_id):
        self.profile(profile_id)
        today = now()[:10]
        with self.db() as db:
            shows = [dict(x) for x in db.execute("""SELECT DISTINCT s.*,COALESCE(ss.status,'watching') AS user_status FROM shows s JOIN lists l ON l.show_id=s.id
                LEFT JOIN show_state ss ON ss.show_id=s.id AND ss.profile_id=l.profile_id WHERE l.profile_id=?
                AND NOT EXISTS(SELECT 1 FROM hidden h WHERE h.profile_id=l.profile_id AND h.show_id=s.id)
                ORDER BY s.name COLLATE NOCASE""",(profile_id,))]
            for show in shows:
                entries = [dict(x) for x in db.execute("SELECT provider,on_watchlist,source FROM lists WHERE profile_id=? AND show_id=?",(profile_id,show["id"]))]
                episodes = [dict(x) for x in db.execute("""SELECT e.*,COALESCE(p.watched,0) AS watched FROM episodes e LEFT JOIN progress p
                    ON p.episode_id=e.id AND p.profile_id=? WHERE e.show_id=? AND e.season>0 AND e.number IS NOT NULL ORDER BY e.season,e.number""",(profile_id,show["id"]))]
                aired = [e for e in episodes if e["airdate"] and e["airdate"]<=today]
                show.update(providers=entries, total=len(aired), watched=sum(e["watched"] for e in aired),
                            next_episode=next((e for e in aired if not e["watched"]),None),
                            upcoming=next((e for e in episodes if e["airdate"] and e["airdate"]>today),None))
                show["activity"] = [dict(x) for x in db.execute("SELECT provider,title,payload,captured_at FROM observations WHERE profile_id=? AND show_id=? AND section='history' ORDER BY captured_at DESC LIMIT 2",(profile_id,show["id"]))]
                for a in show["activity"]:
                    a["payload"]=json.loads(a["payload"])
            return shows

    def connections(self, profile_id):
        self.profile(profile_id)
        with self.db() as db:
            return [dict(x) for x in db.execute("SELECT * FROM connections WHERE profile_id=? ORDER BY provider",(profile_id,))]

    def connection_update(self, profile_id, provider, **values):
        self.profile(profile_id)
        if provider not in PROVIDERS or not set(values)<= {"source_profile","enabled","last_sync","last_attempt","message"}:
            raise ValueError("Ungültige Verbindung")
        with self.db() as db:
            fields=','.join(f"{key}=?" for key in values)
            db.execute(f"UPDATE connections SET {fields} WHERE profile_id=? AND provider=?",(*values.values(),profile_id,provider))

    def pending(self, profile_id):
        self.profile(profile_id)
        with self.db() as db:
            return [dict(x) for x in db.execute("SELECT id,provider,title,section,captured_at FROM observations WHERE profile_id=? AND show_id IS NULL ORDER BY id DESC LIMIT 250",(profile_id,))]

    def observe(self, profile_id, provider, section, rows):
        """Additive import: missing/partial pages never remove a watchlist or erase progress."""
        self.profile(profile_id)
        if provider not in PROVIDERS or section not in {"watchlist","history"}:
            raise ValueError("Ungültiger Import")
        if len(rows)>2000:
            raise ValueError("Zu viele Einträge")
        with self.db() as db:
            for row in rows:
                identity=str(row["provider_id"])[:300]
                mapped=db.execute("SELECT show_id FROM mappings WHERE profile_id=? AND provider=? AND provider_id=?",(profile_id,provider,identity)).fetchone()
                db.execute("""INSERT INTO observations(profile_id,provider,provider_id,section,title,payload,show_id,captured_at)
                    VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(profile_id,provider,provider_id,section)
                    DO UPDATE SET title=excluded.title,payload=excluded.payload,captured_at=excluded.captured_at""",
                    (profile_id,provider,identity,section,row["title"][:300],json.dumps(row),mapped[0] if mapped else None,now()))
                if mapped:
                    self._apply(db,profile_id,provider,mapped[0],section,row)

    def _apply(self, db, profile_id, provider, show_id, section, row):
        db.execute("""INSERT INTO lists(profile_id,show_id,provider,on_watchlist,source) VALUES(?,?,?,?,?)
            ON CONFLICT(profile_id,show_id,provider) DO UPDATE SET on_watchlist=CASE
            WHEN lists.source='manual' THEN lists.on_watchlist ELSE MAX(lists.on_watchlist,excluded.on_watchlist) END""",
            (profile_id,show_id,provider,int(section=="watchlist"),"import"))
        # A history entry alone does not prove that a complete episode was watched.
        pct=row.get("completion")
        if section!="history" or pct is None or not 90<=pct<=100 or row.get("season") is None or row.get("episode") is None:
            return
        ep=db.execute("SELECT id FROM episodes WHERE show_id=? AND season=? AND number=?",(show_id,row["season"],row["episode"])).fetchone()
        if ep:
            db.execute("""INSERT INTO progress VALUES(?,?,?,?,?) ON CONFLICT(profile_id,episode_id) DO UPDATE
                SET watched=1,source=excluded.source,updated_at=excluded.updated_at WHERE progress.source!='manual'""",(profile_id,ep[0],1,provider,now()))

    def resolve(self, profile_id, observation_id, show_id):
        self.profile(profile_id)
        with self.db() as db:
            row=db.execute("SELECT * FROM observations WHERE id=? AND profile_id=?",(observation_id,profile_id)).fetchone()
            if not row or not db.execute("SELECT 1 FROM shows WHERE id=?",(show_id,)).fetchone():
                raise ValueError("Eintrag nicht gefunden")
            db.execute("INSERT OR REPLACE INTO mappings VALUES(?,?,?,?)",(profile_id,row["provider"],row["provider_id"],show_id))
            observations=list(db.execute("SELECT * FROM observations WHERE profile_id=? AND provider=? AND provider_id=?",(profile_id,row["provider"],row["provider_id"])))
            for obs in observations:
                self._apply(db,profile_id,row["provider"],show_id,obs["section"],json.loads(obs["payload"]))
            db.execute("UPDATE observations SET show_id=? WHERE profile_id=? AND provider=? AND provider_id=?",(show_id,profile_id,row["provider"],row["provider_id"]))

    def export(self):
        # Export contains household data, never browser cookies, tokens, or raw credentials.
        tables=["profiles","shows","episodes","lists","progress","show_state","hidden","mappings","observations"]
        with self.db() as db:
            return {"format":"watchlists-household-v1","created_at":now(),"tables":{t:[dict(x) for x in db.execute(f"SELECT * FROM {t}")] for t in tables}}
