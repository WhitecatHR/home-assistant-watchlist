"""Local household data. Manual decisions have priority over imported observations."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .providers import series_title,title_key,search_title,image_allowed

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
            """)
            self._migrate(db)
            db.executemany("INSERT OR IGNORE INTO profiles VALUES(?,?,?)", [(1,"Person 1","#d5a377"),(2,"Person 2","#a5b9a8")])
            db.executemany("INSERT OR IGNORE INTO connections(profile_id,provider) VALUES(?,?)", [(p,k) for p in (1,2) for k in PROVIDERS])

    def _migrate(self,db):
        version=db.execute('PRAGMA user_version').fetchone()[0]
        db.executescript("""
            CREATE TABLE IF NOT EXISTS native_items(id INTEGER PRIMARY KEY AUTOINCREMENT,profile_id INTEGER REFERENCES profiles(id),
                provider TEXT NOT NULL,group_key TEXT NOT NULL,name TEXT NOT NULL,image TEXT,url TEXT,media_type TEXT NOT NULL DEFAULT 'unknown',
                on_watchlist INTEGER NOT NULL DEFAULT 0,history_seen INTEGER NOT NULL DEFAULT 0,activity TEXT,manual_activity TEXT,
                catalog_show_id INTEGER REFERENCES shows(id),hidden INTEGER NOT NULL DEFAULT 0,UNIQUE(profile_id,provider,group_key));
            CREATE TABLE IF NOT EXISTS title_progress(profile_id INTEGER REFERENCES profiles(id),show_id INTEGER,
                watched INTEGER NOT NULL,source TEXT NOT NULL,PRIMARY KEY(profile_id,show_id));
        """)
        for table,columns in {
            'shows':{'media_type':"TEXT NOT NULL DEFAULT 'series'",'catalog':"TEXT NOT NULL DEFAULT 'tvmaze'"},
            'observations':{'parser_version':'INTEGER NOT NULL DEFAULT 0','native_id':'INTEGER REFERENCES native_items(id)','dismissed':'INTEGER NOT NULL DEFAULT 0'},
            'connections':{'last_report':"TEXT NOT NULL DEFAULT '{}'"},
        }.items():
            existing={r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
            for name,definition in columns.items():
                if name not in existing:db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
        if version<2:
            db.execute("UPDATE lists SET source='legacy' WHERE source='import'")
            db.execute('PRAGMA user_version=2')

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
            db.execute("UPDATE shows SET media_type=?,catalog=? WHERE id=?",(show.get('media_type','series'),show.get('catalog','tvmaze'),show['id']))

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
            native=db.execute('SELECT id FROM native_items WHERE id=? AND profile_id=?',(-show_id,profile_id)).fetchone() if -1_000_000_000<show_id<0 else None
            if native:
                db.execute('UPDATE native_items SET hidden=1 WHERE id=?',(native['id'],));return
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
                show['native']=False
                show['legacy_only']=all(p['source']=='legacy' for p in entries)
                movie=db.execute('SELECT watched FROM title_progress WHERE profile_id=? AND show_id=?',(profile_id,show['id'])).fetchone()
                show['movie_watched']=bool(movie['watched']) if movie else False
                show['movie_progress_set']=bool(movie)
                show['metadata_needed']=False
                native_sources=[dict(n) for n in db.execute('SELECT * FROM native_items WHERE profile_id=? AND catalog_show_id=?',(profile_id,show['id']))]
                native_sources.sort(key=lambda n:(bool(n['manual_activity']),(json.loads(n['activity'] or '{}').get('activity_at') or 0)),reverse=True)
                source=next((n for n in native_sources if n['manual_activity'] or n['activity']),None)
                show['source_position']=json.loads((source['manual_activity'] or source['activity']) if source else '{}')
                show['manual_episode_progress']=bool(db.execute("SELECT 1 FROM progress p JOIN episodes e ON e.id=p.episode_id WHERE p.profile_id=? AND e.show_id=? AND p.source='manual' LIMIT 1",(profile_id,show['id'])).fetchone())
                if source:
                    show['activity']=[{'provider':source['provider'],'payload':show['source_position']}]
            for row in db.execute('SELECT * FROM native_items WHERE profile_id=? AND catalog_show_id IS NULL AND hidden=0',(profile_id,)):
                activity=json.loads(row['manual_activity'] or row['activity'] or '{}')
                watched=db.execute('SELECT watched FROM title_progress WHERE profile_id=? AND show_id=?',(profile_id,-row['id'])).fetchone()
                shows.append({'id':-row['id'],'name':row['name'],'summary':'Direkt aus dem Streamingdienst. Eine Katalogzuordnung ist für die Anzeige nicht erforderlich.',
                    'image':row['image'],'url':row['url'],'media_type':row['media_type'],'catalog':'native','native':True,'metadata_needed':True,
                    'providers':[{'provider':row['provider'],'on_watchlist':row['on_watchlist'],'source':'import'}],
                    'total':0,'watched':0,'next_episode':None,'upcoming':None,'user_status':'watching','movie_watched':bool(watched['watched']) if watched else False,'movie_progress_set':bool(watched),
                    'source_position':activity,'position_manual':bool(row['manual_activity']),'legacy_only':False,'activity':[]})
            shows.sort(key=lambda s:s['name'].casefold())
            return shows

    def native_position(self,profile_id,show_id,position):
        self.profile(profile_id)
        with self.db() as db:
            if not db.execute('SELECT id FROM native_items WHERE id=? AND profile_id=?',(-show_id,profile_id)).fetchone():raise ValueError('Anbietertitel nicht gefunden')
            db.execute('UPDATE native_items SET manual_activity=? WHERE id=?',(json.dumps(position) if position else None,-show_id))

    def mark_title(self,profile_id,show_id,watched):
        self.profile(profile_id)
        if not any(s['id']==show_id for s in self.library(profile_id)):raise ValueError('Titel nicht in deiner Liste')
        with self.db() as db:
            db.execute("INSERT INTO title_progress VALUES(?,?,?,'manual') ON CONFLICT(profile_id,show_id) DO UPDATE SET watched=excluded.watched,source='manual'",(profile_id,show_id,int(watched)))

    def classify(self,profile_id,show_id,media_type):
        self.profile(profile_id)
        if media_type not in {'movie','series'}:raise ValueError('Ungültiger Typ')
        with self.db() as db:
            if not db.execute('SELECT id FROM native_items WHERE id=? AND profile_id=?',(-show_id,profile_id)).fetchone():raise ValueError('Anbietertitel nicht gefunden')
            db.execute('UPDATE native_items SET media_type=? WHERE id=?',(media_type,-show_id))

    def connections(self, profile_id):
        self.profile(profile_id)
        with self.db() as db:
            return [dict(x) for x in db.execute("SELECT * FROM connections WHERE profile_id=? ORDER BY provider",(profile_id,))]

    def connection_update(self, profile_id, provider, **values):
        self.profile(profile_id)
        if provider not in PROVIDERS or not set(values)<= {"source_profile","enabled","last_sync","last_attempt","message","last_report"}:
            raise ValueError("Ungültige Verbindung")
        with self.db() as db:
            fields=','.join(f"{key}=?" for key in values)
            db.execute(f"UPDATE connections SET {fields} WHERE profile_id=? AND provider=?",(*values.values(),profile_id,provider))

    def pending(self, profile_id):
        self.profile(profile_id)
        with self.db() as db:
            groups={}
            for row in db.execute("SELECT * FROM observations WHERE profile_id=? AND show_id IS NULL AND dismissed=0 ORDER BY id DESC",(profile_id,)):
                key=(row['provider'],row['native_id'] or title_key(row['title']),row['parser_version']<2)
                if key not in groups:groups[key]={'id':row['id'],'provider':row['provider'],'title':series_title(row['title']),
                    'search_query':search_title(row['title']),'section':row['section'],'sections':[],'count':0,'examples':[],
                    'legacy':row['parser_version']<2,'native_show_id':-row['native_id'] if row['native_id'] else None,'captured_at':row['captured_at']}
                group=groups[key];group['count']+=1
                if row['section'] not in group['sections']:group['sections'].append(row['section'])
                if len(group['examples'])<3 and row['title'] not in group['examples']:group['examples'].append(row['title'])
            return list(groups.values())

    def dismiss(self,profile_id,observation_id):
        self.profile(profile_id)
        with self.db() as db:
            row=db.execute('SELECT * FROM observations WHERE id=? AND profile_id=?',(observation_id,profile_id)).fetchone()
            if not row:raise ValueError('Import nicht gefunden')
            ids=[r['id'] for r in db.execute('SELECT * FROM observations WHERE profile_id=? AND provider=?',(profile_id,row['provider'])) if title_key(r['title'])==title_key(row['title']) and r['parser_version']<2]
            db.executemany('UPDATE observations SET dismissed=1 WHERE id=?',[(i,) for i in ids])

    def _native_upsert(self,db,profile_id,provider,section,row,seen_history):
        name=row.get('series_title') or series_title(row['title'])
        image=row.get('image') if image_allowed(row.get('image')) else None
        media=row.get('media_type','unknown')
        if media not in {'movie','series','unknown'}:media='unknown'
        by_id=db.execute('SELECT n.* FROM native_items n JOIN observations o ON o.native_id=n.id WHERE o.profile_id=? AND o.provider=? AND o.provider_id=? LIMIT 1',(profile_id,provider,row['provider_id'])).fetchone()
        if by_id:key=by_id['group_key']
        elif provider=='netflix' and (row.get('series_id') or row['provider_id'].rsplit('/',1)[-1].isdigit()):
            key='netflix:'+str(row.get('series_id') or row['provider_id'].rsplit('/',1)[-1])
        elif media=='series':key='series:'+title_key(name)
        else:key='item:'+row['provider_id']
        db.execute("""INSERT INTO native_items(profile_id,provider,group_key,name,image,url,media_type,on_watchlist,history_seen)
            VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(profile_id,provider,group_key) DO UPDATE SET image=COALESCE(excluded.image,native_items.image),
            url=excluded.url,on_watchlist=MAX(native_items.on_watchlist,excluded.on_watchlist),history_seen=MAX(native_items.history_seen,excluded.history_seen),
            media_type=CASE WHEN native_items.media_type='unknown' THEN excluded.media_type ELSE native_items.media_type END""",
            (profile_id,provider,key,name,image,row.get('url'),media,int(section=='watchlist'),int(section=='history')))
        native=db.execute('SELECT * FROM native_items WHERE profile_id=? AND provider=? AND group_key=?',(profile_id,provider,key)).fetchone()
        if section=='history' and (key not in seen_history or row.get('activity_at')):
            previous=json.loads(native['activity'] or '{}');old_date=previous.get('activity_at') or 0;new_date=row.get('activity_at') or 0
            if not old_date or new_date>=old_date:
                db.execute('UPDATE native_items SET activity=? WHERE id=?',(json.dumps(row),native['id']))
            seen_history.add(key)
            if media=='movie' and isinstance(row.get('completion'),(int,float)) and row['completion']>=90:
                db.execute("INSERT INTO title_progress VALUES(?,?,1,?) ON CONFLICT(profile_id,show_id) DO UPDATE SET watched=1 WHERE title_progress.source!='manual'",(profile_id,-native['id'],provider))
        return native

    def observe(self, profile_id, provider, section, rows):
        """Additive import: missing/partial pages never remove a watchlist or erase progress."""
        self.profile(profile_id)
        if provider not in PROVIDERS or section not in {"watchlist","history"}:
            raise ValueError("Ungültiger Import")
        if len(rows)>2000:
            raise ValueError("Zu viele Einträge")
        with self.db() as db:
            seen_history=set()
            for row in rows:
                identity=str(row["provider_id"])[:300]
                native=self._native_upsert(db,profile_id,provider,section,row,seen_history) if row.get('parser_version',0)>=2 else None
                mapped=db.execute("SELECT show_id FROM mappings WHERE profile_id=? AND provider=? AND provider_id=?",(profile_id,provider,identity)).fetchone()
                show_id=mapped[0] if mapped else native['catalog_show_id'] if native else None
                type_conflict=False
                if show_id and native:
                    target=db.execute('SELECT media_type FROM shows WHERE id=?',(show_id,)).fetchone()
                    source_type=row.get('media_type') if row.get('media_type') in {'movie','series'} else native['media_type']
                    type_conflict=bool(target and source_type in {'movie','series'} and target['media_type']!=source_type)
                    if type_conflict:
                        db.execute("UPDATE lists SET source='legacy' WHERE profile_id=? AND show_id=? AND provider=? AND source!='manual'",(profile_id,show_id,provider))
                        db.execute('UPDATE native_items SET catalog_show_id=NULL WHERE id=?',(native['id'],))
                        show_id=None
                db.execute("""INSERT INTO observations(profile_id,provider,provider_id,section,title,payload,show_id,captured_at)
                    VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(profile_id,provider,provider_id,section)
                    DO UPDATE SET title=excluded.title,payload=excluded.payload,captured_at=excluded.captured_at,show_id=COALESCE(excluded.show_id,observations.show_id)""",
                    (profile_id,provider,identity,section,row["title"][:300],json.dumps(row),show_id,now()))
                db.execute('UPDATE observations SET parser_version=?,native_id=COALESCE(?,native_id) WHERE profile_id=? AND provider=? AND provider_id=? AND section=?',
                    (row.get('parser_version',0),native['id'] if native else None,profile_id,provider,identity,section))
                if type_conflict:
                    db.execute('UPDATE observations SET show_id=NULL WHERE profile_id=? AND provider=? AND provider_id=? AND section=?',(profile_id,provider,identity,section))
                if show_id:
                    if native:db.execute('UPDATE native_items SET catalog_show_id=? WHERE id=?',(show_id,native['id']))
                    self._apply(db,profile_id,provider,show_id,section,row)

    def _apply(self, db, profile_id, provider, show_id, section, row):
        db.execute("""INSERT INTO lists(profile_id,show_id,provider,on_watchlist,source) VALUES(?,?,?,?,?)
            ON CONFLICT(profile_id,show_id,provider) DO UPDATE SET on_watchlist=CASE
            WHEN lists.source='manual' THEN lists.on_watchlist ELSE MAX(lists.on_watchlist,excluded.on_watchlist) END,
            source=CASE WHEN lists.source='manual' THEN lists.source ELSE excluded.source END""",
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
            observations=[o for o in db.execute('SELECT * FROM observations WHERE profile_id=? AND provider=? AND dismissed=0',(profile_id,row['provider']))
                if (row['native_id'] and o['native_id']==row['native_id']) or (not row['native_id'] and not o['native_id'] and title_key(o['title'])==title_key(row['title']) and not o['show_id']) or o['id']==row['id']]
            for obs in observations:
                self._apply(db,profile_id,row["provider"],show_id,obs["section"],json.loads(obs["payload"]))
                db.execute('UPDATE observations SET show_id=? WHERE id=?',(show_id,obs['id']))
                db.execute('INSERT OR REPLACE INTO mappings VALUES(?,?,?,?)',(profile_id,row['provider'],obs['provider_id'],show_id))
                if obs['native_id']:
                    db.execute('UPDATE native_items SET catalog_show_id=? WHERE id=?',(show_id,obs['native_id']))
                    db.execute("INSERT OR IGNORE INTO title_progress SELECT profile_id,?,watched,source FROM title_progress WHERE profile_id=? AND show_id=?",(show_id,profile_id,-obs['native_id']))

    def export(self):
        # Export contains household data, never browser cookies, tokens, or raw credentials.
        tables=["profiles","shows","episodes","lists","progress","show_state","hidden","mappings","observations","native_items","title_progress"]
        with self.db() as db:
            return {"format":"watchlists-household-v1","created_at":now(),"tables":{t:[dict(x) for x in db.execute(f"SELECT * FROM {t}")] for t in tables}}
