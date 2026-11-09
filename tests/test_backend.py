import asyncio
import copy
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import httpx

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"watchlists"))
from app.store import Store
from app.providers import allowed_url,episode_numbers,normalize_row
from app.main import create_app,read_options
from app.browser import BrowserProblem

SHOW={"id":100,"name":"Testserie","summary":"Beschreibung","image":None,"url":"https://www.tvmaze.com/shows/100/test","premiered":"2020-01-01","status":"Running"}
EPISODES=[{"id":1001,"season":1,"number":1,"name":"Start","airdate":"2020-01-01"},
          {"id":1002,"season":1,"number":2,"name":"Weiter","airdate":"2020-01-02"},
          {"id":1003,"season":2,"number":1,"name":"Später","airdate":"2021-01-01"},
          {"id":1004,"season":2,"number":2,"name":"Zukunft","airdate":"2099-01-01"},
          {"id":1005,"season":0,"number":1,"name":"Special","airdate":"2020-01-01"}]


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.temp.name)/"test.sqlite")
        self.store.cache_show(SHOW,EPISODES)
        self.store.add(1,100,"netflix")
        self.store.add(2,100,"netflix")

    def tearDown(self):
        self.temp.cleanup()

    def observation(self,pct=95):
        return {"provider_id":"/title/12","title":"Testserie","season":1,"episode":1,"completion":pct,"url":"https://www.netflix.com/title/12"}

    def test_separate_profiles_and_persistence(self):
        self.store.mark(1,100,1001,True)
        self.assertEqual(self.store.library(1)[0]["watched"],1)
        self.assertEqual(self.store.library(2)[0]["watched"],0)
        reopened=Store(self.store.path)
        self.assertEqual(reopened.library(1)[0]["next_episode"]["id"],1002)
        self.assertEqual(len(reopened.profiles()),2)

    def test_next_unseen_handles_gaps_specials_and_future(self):
        self.store.mark(1,100,1002,True)
        item=self.store.library(1)[0]
        self.assertEqual(item["next_episode"]["id"],1001)
        self.assertEqual(item["total"],3)
        self.assertEqual(item["upcoming"]["id"],1004)
        self.store.mark(1,100,1003,True,through=True)
        item=self.store.library(1)[0]
        self.assertEqual(item["watched"],3)
        self.assertIsNone(item["next_episode"])
        self.assertFalse(next(e for e in self.store.episodes(1,100) if e["id"]==1005)["watched"])

    def test_import_requires_explicit_mapping(self):
        self.store.observe(1,"netflix","history",[self.observation()])
        self.assertEqual(self.store.library(1)[0]["watched"],0)
        self.assertEqual(len(self.store.pending(1)),1)
        obs=self.store.pending(1)[0]
        self.store.resolve(1,obs["id"],100)
        self.assertEqual(self.store.library(1)[0]["watched"],1)
        self.assertEqual(self.store.pending(1),[])

    def test_unknown_or_low_completion_never_marks_seen(self):
        for pct in [None,0,15,89,101]:
            with self.subTest(pct=pct):
                self.store.observe(1,"netflix","history",[self.observation(pct)])
                rows=self.store.pending(1)
                if rows:self.store.resolve(1,rows[0]["id"],100)
                self.assertEqual(self.store.library(1)[0]["watched"],0)

    def test_manual_unwatch_has_priority_over_auto_import(self):
        self.store.observe(1,"netflix","history",[self.observation()])
        self.store.resolve(1,self.store.pending(1)[0]["id"],100)
        self.store.mark(1,100,1001,False)
        self.store.observe(1,"netflix","history",[self.observation(100)])
        self.assertEqual(self.store.library(1)[0]["watched"],0)
        self.assertEqual(self.store.episodes(1,100)[1]["source"],"manual")

    def test_empty_import_never_erases_existing_data(self):
        self.store.mark(1,100,1001,True)
        self.store.observe(1,"netflix","watchlist",[])
        self.assertEqual(self.store.library(1)[0]["watched"],1)
        self.assertEqual(len(self.store.library(1)),1)

    def test_remove_preserves_progress_and_hides_future_imports(self):
        self.store.mark(1,100,1001,True)
        self.store.observe(1,"netflix","watchlist",[self.observation()])
        self.store.resolve(1,self.store.pending(1)[0]["id"],100)
        self.store.remove(1,100)
        self.store.observe(1,"netflix","watchlist",[self.observation()])
        self.assertEqual(self.store.library(1),[])
        self.store.add(1,100,"netflix")
        self.assertEqual(self.store.library(1)[0]["watched"],1)

    def test_profile_cannot_resolve_another_persons_observation(self):
        self.store.observe(1,"netflix","history",[self.observation()])
        with self.assertRaises(ValueError):
            self.store.resolve(2,self.store.pending(1)[0]["id"],100)
        self.assertEqual(self.store.library(2)[0]["watched"],0)

    def test_history_alone_does_not_claim_provider_watchlist(self):
        self.store.remove(1,100)
        self.store.observe(1,"prime","history",[self.observation()])
        self.store.resolve(1,self.store.pending(1)[0]["id"],100)
        with self.store.db() as db:
            row=db.execute("SELECT * FROM lists WHERE profile_id=1 AND provider='prime'").fetchone()
        self.assertEqual(row["on_watchlist"],0)

    def test_export_excludes_sessions_and_connections(self):
        self.store.connection_update(1,"netflix",source_profile="Privates Profil",enabled=1)
        data=self.store.export()
        self.assertNotIn("connections",data["tables"])
        self.assertNotIn("sessions",json.dumps(data))
        self.assertEqual(data["format"],"watchlists-household-v1")


class ProviderTests(unittest.TestCase):
    def test_options_can_be_read_from_unprivileged_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/"options.json"
            file.write_text('{"browser_enabled": false, "sync_interval_minutes": 240}')
            with patch.dict('os.environ',{"WATCHLIST_OPTIONS":str(file)}):
                self.assertFalse(read_options()["browser_enabled"])
                self.assertEqual(read_options()["sync_interval_minutes"],240)

    def test_navigation_and_resource_limits(self):
        for url in ["https://www.netflix.com/login","https://netflix.com/title/123"]:
            self.assertTrue(allowed_url("netflix",url,True))
        for url in ["http://netflix.com","https://netflix.com.evil.test/","https://127.0.0.1/","https://user@netflix.com/","https://netflix.com:8123/","file:///data/test","https://netflix.com:invalid/"]:
            self.assertFalse(allowed_url("netflix",url,True),url)
        self.assertFalse(allowed_url("netflix","https://img.nflximg.net/test",True))
        self.assertTrue(allowed_url("netflix","https://img.nflximg.net/test"))

    def test_episode_formats_and_no_number_guess(self):
        for text in ["S1E2","S1 · E2".replace(' · ',': '),"Staffel 1, Folge 2","Season 1 Episode 2"]:
            self.assertEqual(episode_numbers(text),(1,2),text)
        self.assertEqual(episode_numbers("Folge 19 · 2024"),(None,None))

    def test_normalization_rejects_external_and_impossible_progress(self):
        row=normalize_row("crunchyroll",{"url":"https://www.crunchyroll.com/series/ABC?from=test","title":" Test  Serie ","text":"S2E3","completion":150})
        self.assertEqual(row["title"],"Test Serie")
        self.assertEqual(row["season"],2)
        self.assertIsNone(row["completion"])
        self.assertEqual(row["url"],"https://www.crunchyroll.com/series/ABC")
        self.assertIsNone(normalize_row("netflix",{"url":"https://evil.test","title":"Test"}))


class FakeCatalog:
    async def search(self,q):return [copy.deepcopy(SHOW)]
    async def show(self,id):
        if id!=100:raise ValueError("Serie nicht gefunden")
        return copy.deepcopy(SHOW),copy.deepcopy(EPISODES)
    async def close(self):pass


class APITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=create_app(self.temp.name,standalone=True,catalog=FakeCatalog())
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url="http://test")
        self.headers={"X-Watchlists-Request":"1"}

    async def asyncTearDown(self):
        await self.client.aclose()
        self.temp.cleanup()

    async def add(self,profile=1):
        return await self.client.post(f"/api/profiles/{profile}/library",json={"show_id":100,"provider":"netflix"},headers=self.headers)

    async def test_full_profile_workflow(self):
        self.assertEqual((await self.add()).status_code,200)
        self.assertEqual((await self.add(2)).status_code,200)
        r=await self.client.patch("/api/profiles/1/library/100/episodes",json={"episode_id":1001,"watched":True},headers=self.headers)
        self.assertEqual(r.status_code,200)
        self.assertEqual((await self.client.get("/api/profiles/1/library")).json()[0]["watched"],1)
        self.assertEqual((await self.client.get("/api/profiles/2/library")).json()[0]["watched"],0)
        self.assertEqual((await self.client.patch("/api/profiles/1",json={"name":"Anna"},headers=self.headers)).status_code,200)
        self.assertEqual((await self.client.get("/api/profiles")).json()[0]["name"],"Anna")

    async def test_write_requires_application_header(self):
        r=await self.client.post("/api/profiles/1/library",json={"show_id":100,"provider":"netflix"})
        self.assertEqual(r.status_code,403)

    async def test_invalid_profiles_and_providers_fail(self):
        self.assertEqual((await self.client.get("/api/profiles/999/library")).status_code,404)
        self.assertEqual((await self.client.post("/api/profiles/1/library",headers=self.headers,json={"show_id":100,"provider":"fake"})).status_code,422)
        self.assertEqual((await self.client.get("/api/profiles/1/connections/fake/browser")).status_code,404)

    async def test_production_checks_actual_tcp_peer(self):
        production=create_app(self.temp.name,catalog=FakeCatalog())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=production,client=("192.168.1.8",123)),base_url="http://test") as client:
            r=await client.get("/api/profiles",headers={"X-Forwarded-For":"172.30.32.2"})
            self.assertEqual(r.status_code,403)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=production,client=("172.30.32.2",123)),base_url="http://test") as client:
            self.assertEqual((await client.get("/api/profiles")).status_code,200)

    async def test_relative_assets_and_security_headers(self):
        page=await self.client.get("/")
        self.assertEqual(page.status_code,200)
        self.assertIn('src="static/app.js"',page.text)
        self.assertEqual(page.headers["cache-control"],"no-store")
        self.assertIn("object-src 'none'",page.headers["content-security-policy"])
        self.assertEqual((await self.client.get("/static/app.css")).status_code,200)

    async def test_sync_failure_retains_library(self):
        await self.add()
        await self.client.patch("/api/profiles/1/connections/netflix",headers=self.headers,json={"source_profile":"Anna","enabled":False})
        async def fail(*args):raise BrowserProblem("Anmeldung erforderlich")
        self.app.state.browsers.collect=fail
        r=await self.client.post("/api/profiles/1/connections/netflix/sync",headers=self.headers)
        self.assertEqual(r.status_code,503)
        self.assertEqual(len((await self.client.get("/api/profiles/1/library")).json()),1)
        c=(await self.client.get("/api/profiles/1/connections")).json()
        netflix=next(x for x in c if x["provider"]=="netflix")
        self.assertIsNone(netflix["last_sync"])
        self.assertEqual(netflix["message"],"Anmeldung erforderlich")

    async def test_successful_observations_wait_for_user_mapping(self):
        await self.client.patch("/api/profiles/1/connections/netflix",headers=self.headers,json={"source_profile":"Anna","enabled":False})
        async def collect(*args):return {"watchlist":[{"provider_id":"/title/123","title":"Testserie","url":"https://www.netflix.com/title/123","season":None,"episode":None,"completion":None}]}
        self.app.state.browsers.collect=collect
        r=await self.client.post("/api/profiles/1/connections/netflix/sync",headers=self.headers)
        self.assertEqual(r.status_code,200)
        pending=(await self.client.get("/api/profiles/1/pending")).json()
        self.assertEqual(len(pending),1)
        self.assertEqual((await self.client.get("/api/profiles/1/library")).json(),[])
        r=await self.client.post(f'/api/profiles/1/pending/{pending[0]["id"]}',headers=self.headers,json={"show_id":100})
        self.assertEqual(r.status_code,200)
        self.assertEqual((await self.client.get("/api/profiles/1/library")).json()[0]["providers"][0]["source"],"import")

    async def test_browser_input_size_and_action_constraints(self):
        r=await self.client.post("/api/profiles/1/connections/netflix/browser/action",headers=self.headers,json={"kind":"key","key":"F12"})
        self.assertEqual(r.status_code,422)
        r=await self.client.post("/api/profiles/1/connections/netflix/browser/action",headers=self.headers,json={"kind":"click","x":2000})
        self.assertEqual(r.status_code,422)


if __name__=="__main__":unittest.main(verbosity=2)
