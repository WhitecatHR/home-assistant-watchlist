import asyncio
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock,MagicMock
import httpx

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'watchlists'))
from app.providers import series_title,title_key,search_title,netflix_history_rows,enrich_netflix,page_is_section,image_allowed
from app.store import Store
from app.catalog import Catalog
from app.main import create_app
from app.browser import BrowserBlocked,BrowserProblem,Browsers,merge_collected_rows


def item(title='Reacher - Staffel 1',ident='ONE',**extra):
    return {'provider_id':'/detail/'+ident,'title':title,'url':'https://www.primevideo.com/detail/'+ident,
        'parser_version':2,'media_type':'series','series_title':series_title(title),'image':'https://m.media-amazon.com/images/test.jpg',**extra}

SHOW={'id':118,'name':'Reacher','summary':'Test','url':'https://www.tvmaze.com/shows/118/test','image':None,'status':'Running'}


class NativeImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'data.sqlite')
    def tearDown(self):self.tmp.cleanup()

    def test_watchlist_is_visible_before_any_catalog_assignment(self):
        self.store.observe(1,'prime','watchlist',[item()])
        library=self.store.library(1)
        self.assertEqual(len(library),1)
        self.assertEqual(library[0]['name'],'Reacher')
        self.assertTrue(library[0]['native'])
        self.assertEqual(library[0]['providers'][0]['on_watchlist'],1)
        self.assertTrue(library[0]['image'].startswith('https://m.media-amazon.com'))
        self.assertEqual(self.store.library(2),[])

    def test_prime_seasons_share_one_title_and_one_assignment(self):
        self.store.observe(1,'prime','watchlist',[item(),item('Reacher - Staffel 2','TWO')])
        self.assertEqual(len(self.store.library(1)),1)
        pending=self.store.pending(1)
        self.assertEqual(len(pending),1)
        self.assertEqual(pending[0]['count'],2)
        self.assertEqual(pending[0]['search_query'],'Reacher')
        self.store.cache_show(SHOW,[])
        self.store.resolve(1,pending[0]['id'],118)
        self.assertEqual(self.store.pending(1),[])
        self.assertEqual([s['id'] for s in self.store.library(1)],[118])
        self.store.observe(1,'prime','watchlist',[item('Reacher - Staffel 3','THREE')])
        self.assertEqual(self.store.pending(1),[])
        self.assertEqual(len(self.store.library(1)),1)

    def test_history_never_claims_watchlist_membership(self):
        self.store.observe(1,'prime','history',[item(season=1,episode=2,completion=35)])
        show=self.store.library(1)[0]
        self.assertEqual(show['providers'][0]['on_watchlist'],0)
        self.assertEqual(show['source_position']['episode'],2)
        self.assertEqual(show['source_position']['completion'],35)

    def test_identically_named_movie_and_series_are_not_merged(self):
        self.store.observe(1,'prime','watchlist',[item('Fargo','MOVIE',media_type='movie'),item('Fargo - Staffel 1','SERIES',media_type='series')])
        library=self.store.library(1)
        self.assertEqual(len(library),2)
        self.assertEqual(len(self.store.pending(1)),2)
        self.store.cache_show(SHOW,[])
        self.store.resolve(1,self.store.pending(1)[0]['id'],118)
        self.assertEqual(len(self.store.pending(1)),1)

    def test_old_movie_to_series_mismatch_is_not_reapplied_to_fresh_import(self):
        self.store.cache_show(SHOW,[])
        old=item('Interstellar','MOVIE',parser_version=0,media_type='unknown')
        self.store.observe(1,'prime','watchlist',[old]);self.store.resolve(1,self.store.pending(1)[0]['id'],118)
        self.store.observe(1,'prime','watchlist',[item('Interstellar','MOVIE',media_type='movie')])
        library=self.store.library(1)
        self.assertTrue(next(s for s in library if s['id']==118)['legacy_only'])
        native=next(s for s in library if s['native'])
        self.assertEqual(native['name'],'Interstellar');self.assertEqual(native['media_type'],'movie')
        self.assertEqual(len(self.store.pending(1)),1)

    def test_newest_episode_is_kept_independently_of_import_order(self):
        rows=[item(ident='NEW',season=2,episode=8,activity_at=900),item(ident='OLD',season=1,episode=1,activity_at=100)]
        for ordered in [rows,list(reversed(rows))]:
            self.store.observe(1,'prime','history',ordered)
            self.assertEqual(self.store.library(1)[0]['source_position']['episode'],8)

    def test_native_personal_correction_survives_new_imports(self):
        self.store.observe(1,'prime','watchlist',[item()]);show=self.store.library(1)[0]
        self.store.native_position(1,show['id'],{'season':2,'episode':5,'completion':100})
        self.store.observe(1,'prime','history',[item(season=1,episode=1,completion=100)])
        self.assertEqual(self.store.library(1)[0]['source_position']['episode'],5)
        self.store.native_position(1,show['id'],None)
        self.assertEqual(self.store.library(1)[0]['source_position']['episode'],1)
        with self.assertRaises(ValueError):self.store.native_position(2,show['id'],{})

    def test_native_movie_needs_no_series_catalog_and_has_personal_seen_status(self):
        movie=item('Interstellar','MOVIE',media_type='movie')
        self.store.observe(1,'prime','watchlist',[movie]);self.store.observe(2,'prime','watchlist',[movie])
        a=self.store.library(1)[0];b=self.store.library(2)[0]
        self.store.mark_title(1,a['id'],True)
        self.assertTrue(self.store.library(1)[0]['movie_watched'])
        self.assertFalse(self.store.library(2)[0]['movie_watched'])
        self.assertNotEqual(a['id'],b['id'])
        self.assertTrue(Store(self.store.path).library(1)[0]['movie_watched'])

    def test_later_movie_metadata_does_not_lose_seen_status_or_duplicate_title(self):
        self.store.observe(1,'prime','watchlist',[item('Interstellar','MOVIE',media_type='movie')])
        self.store.mark_title(1,self.store.library(1)[0]['id'],True)
        movie={**SHOW,'id':-1000816692,'name':'Interstellar','media_type':'movie','catalog':'cinemeta'}
        self.store.cache_show(movie,[]);self.store.resolve(1,self.store.pending(1)[0]['id'],movie['id'])
        library=self.store.library(1)
        self.assertEqual(len(library),1);self.assertTrue(library[0]['movie_watched'])
        self.assertEqual(library[0]['media_type'],'movie')

    def test_empty_import_never_erases_native_titles_or_progress(self):
        self.store.observe(1,'prime','watchlist',[item()]);show=self.store.library(1)[0]
        self.store.native_position(1,show['id'],{'season':2,'episode':5})
        self.store.observe(1,'prime','watchlist',[])
        self.assertEqual(self.store.library(1)[0]['source_position']['episode'],5)

    def test_upgrade_retains_old_data_and_does_not_present_it_as_fresh_watchlist(self):
        self.store.cache_show(SHOW,[]);self.store.add(1,118,'netflix',source='import')
        self.store.rename(1,'Originalname')
        with self.store.db() as db:db.execute('PRAGMA user_version=1')
        old=self.store.export()
        migrated=Store(self.store.path)
        self.assertTrue(migrated.library(1)[0]['legacy_only'])
        self.assertEqual(migrated.profiles()[0]['name'],'Originalname')
        self.assertEqual(migrated.export()['tables']['shows'],old['tables']['shows'])

    def test_real_v1_columns_migrate_without_losing_existing_rows_or_sessions(self):
        self.store.cache_show(SHOW,[]);self.store.add(1,118,'netflix',source='import')
        session=Path(self.tmp.name)/'.sessions/1-netflix/Preferences';session.parent.mkdir(parents=True);session.write_text('session-preserved')
        with self.store.db() as db:
            for column in ['native_id','parser_version','dismissed']:db.execute('ALTER TABLE observations DROP COLUMN '+column)
            for column in ['media_type','catalog']:db.execute('ALTER TABLE shows DROP COLUMN '+column)
            db.execute('ALTER TABLE connections DROP COLUMN last_report')
            db.execute('DROP TABLE native_items');db.execute('DROP TABLE title_progress');db.execute('PRAGMA user_version=1')
        upgraded=Store(self.store.path)
        self.assertTrue(upgraded.library(1)[0]['legacy_only'])
        upgraded.observe(1,'prime','watchlist',[item()])
        self.assertTrue(any(s['native'] for s in upgraded.library(1)))
        self.assertEqual(session.read_text(),'session-preserved')


class ProviderFixTests(unittest.TestCase):
    def test_reported_title_formats(self):
        for raw,expected in [('Dr. House: Staffel 2: Ein konkreter Folgentitel','Dr. House'),('Reacher - Staffel 1','Reacher'),
            ('Reacher Staffel 2','Reacher'),('Reacher - Staffel 1 [dt./OV]','Reacher'),('Star Trek: Discovery: Staffel 2: Folge','Star Trek: Discovery'),
            ('Mission: Impossible','Mission: Impossible')]:
            self.assertEqual(series_title(raw),expected)
        self.assertEqual(search_title('Dr. House: Staffel 1: Pilot'),'House')

    def test_netflix_history_extracts_series_separately_from_episode_and_unknown_progress(self):
        payload={'jsonGraph':{'aui':{'viewingActivity':{'value':{'viewedItems':[
            {'movieID':1234,'series':99,'seriesTitle':'Dr. House','episodeTitle':'Folgentitel','title':'Dr. House: Staffel 2: Folgentitel','bookmark':1800,'duration':2400,'date':1000},
            {'movieID':2000,'title':'Ein Film','date':900}]}}}}}
        rows=netflix_history_rows(payload)
        self.assertEqual(rows[0]['series_title'],'Dr. House');self.assertEqual(rows[0]['completion'],75)
        self.assertIsNone(rows[1]['completion']);self.assertEqual(rows[1]['media_type'],'movie')
        self.assertEqual(netflix_history_rows({'recommendations':[{'title':'Fremd'}]}),[])
        enrich_netflix(rows,{'id':99,'type':'show','title':'Dr. House','seasons':[{'seq':2,'episodes':[{'id':1234,'seq':7,'title':'Folgentitel'}]}]})
        self.assertEqual((rows[0]['season'],rows[0]['episode']),(2,7))

    def test_netflix_hidden_numbering_is_not_assumed_to_match_catalog(self):
        rows=netflix_history_rows({'viewedItems':[{'movieID':1234,'series':99,'seriesTitle':'Sammlung'}]})
        enrich_netflix(rows,{'id':99,'type':'show','hiddenEpisodeNumbers':True,'seasons':[{'seq':1,'episodes':[{'id':1234,'seq':8}]}]})
        self.assertIsNone(rows[0]['episode'])

    def test_netflix_current_metadata_position_and_unknowns_are_handled_explicitly(self):
        rows=netflix_history_rows({'viewedItems':[{'movieID':1234,'series':99,'seriesTitle':'House','bookmark':0,'duration':1000}]})
        enrich_netflix(rows,{'id':99,'type':'show','seasons':[{'seq':2,'episodes':[{'id':1234,'seq':7,'bookmark':{'offset':899999},'runtime':1000000}]}]})
        self.assertEqual(rows[0]['completion'],89.99)
        self.assertEqual((rows[0]['season'],rows[0]['episode']),(2,7))
        unknown=netflix_history_rows({'viewedItems':[{'movieID':1234,'title':'Film'}]})
        self.assertIsNone(unknown[0]['completion'])

    def test_redirected_homepage_is_never_a_watchlist(self):
        self.assertFalse(page_is_section('netflix','watchlist','https://www.netflix.com/browse'))
        self.assertTrue(page_is_section('netflix','watchlist','https://www.netflix.com/browse/my-list'))
        self.assertTrue(page_is_section('netflix','history','https://www.netflix.com/settings/viewed/profile'))
        self.assertFalse(page_is_section('prime','watchlist','https://www.primevideo.com/'))
        self.assertTrue(image_allowed('https://occ-0-1.1.nflxso.net/dnm/test.jpg'))
        self.assertFalse(image_allowed('https://localhost/private'))


class CatalogFixTests(unittest.IsolatedAsyncioTestCase):
    async def test_doctor_house_query_and_real_movie_catalog_route(self):
        seen=[]
        async def respond(request):
            seen.append(str(request.url))
            if request.url.host=='api.tvmaze.com':return httpx.Response(200,json=[{'show':SHOW}])
            movie={'id':'tt0816692','name':'Interstellar','type':'movie','releaseInfo':'2014','poster':'https://m.media-amazon.com/x.jpg'}
            return httpx.Response(200,json={'meta':movie} if '/meta/' in request.url.path else {'metas':[movie]})
        catalog=Catalog();await catalog.client.aclose()
        catalog.client=httpx.AsyncClient(base_url='https://api.tvmaze.com',transport=httpx.MockTransport(respond))
        await catalog.search('Dr. House: Staffel 2: Ein Folgentitel')
        self.assertTrue(seen[0].endswith('q=House'))
        results=await catalog.search('Interstellar','movie')
        self.assertEqual(results[0]['media_type'],'movie')
        movie,episodes=await catalog.show(results[0]['id'])
        self.assertEqual(movie['name'],'Interstellar');self.assertEqual(episodes,[])
        self.assertIn('/meta/movie/tt0816692.json',seen[-1])
        await catalog.close()


class FakeCatalog:
    async def show(self,id):return SHOW,[]
    async def close(self):pass

class APIImportFixTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=create_app(self.tmp.name,True,FakeCatalog())
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://test')
        self.headers={'X-Watchlists-Request':'1'}
        self.app.state.store.connection_update(1,'prime',source_profile='Person 1')
    async def asyncTearDown(self):await self.client.aclose();self.tmp.cleanup()

    async def test_sync_shows_source_titles_immediately_and_reports_history_separately(self):
        async def collect(*args):return {'watchlist':[item()], '_report':{'watchlist':{'status':'ok','count':1},'history':{'status':'failed','message':'Verlauf nicht erkannt'}}}
        self.app.state.browsers.collect=collect
        response=await self.client.post('/api/profiles/1/connections/prime/sync',headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertIn('Verlauf: nicht eingelesen',response.json()['message'])
        library=(await self.client.get('/api/profiles/1/library')).json()
        self.assertEqual(library[0]['name'],'Reacher');self.assertTrue(library[0]['native'])
        r=await self.client.patch(f"/api/profiles/1/library/{library[0]['id']}/position",headers=self.headers,json={'season':2,'episode':5,'completion':100})
        self.assertEqual(r.status_code,200)
        self.assertEqual((await self.client.get('/api/profiles/1/library')).json()[0]['source_position']['episode'],5)

    async def test_security_block_disables_scheduled_import_without_deleting_connection(self):
        self.app.state.store.connection_update(1,'crunchyroll',source_profile='Person 1',enabled=1)
        async def blocked(*args):raise BrowserBlocked('Sicherheitsprüfung blockiert')
        self.app.state.browsers.collect=blocked
        r=await self.client.post('/api/profiles/1/connections/crunchyroll/sync',headers=self.headers)
        self.assertEqual(r.status_code,503)
        connection=next(c for c in (await self.client.get('/api/profiles/1/connections')).json() if c['provider']=='crunchyroll')
        self.assertEqual(connection['enabled'],0);self.assertEqual(connection['source_profile'],'Person 1')

    async def test_history_success_never_claims_watchlist_success(self):
        self.app.state.store.connection_update(1,'netflix',source_profile='Person 1')
        report={'watchlist':{'status':'failed','diagnostics':{'title_links':66,'galleries':0,'history_rows':0,'containers':[]},'message':'Listenbereich nicht erkannt.'},
                'history':{'status':'ok','count':1,'scope':'viewing-activity JSON','profile_checked':True}}
        history=netflix_history_rows({'viewedItems':[{'movieID':101,'series':100,'seriesTitle':'Nur im Verlauf','date':1000}]})
        async def collect(*args):return {'history':history,'_report':report}
        self.app.state.browsers.collect=collect
        response=await self.client.post('/api/profiles/1/connections/netflix/sync',headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()['message'].startswith('Watchlist konnte nicht eingelesen werden.'))
        self.assertIn('Verlauf: 1 Einträge',response.json()['message'])
        library=(await self.client.get('/api/profiles/1/library')).json()
        self.assertEqual(len(library),1);self.assertFalse(library[0]['providers'][0]['on_watchlist'])
        connections=(await self.client.get('/api/profiles/1/connections')).json()
        self.assertEqual(json.loads(next(c for c in connections if c['provider']=='netflix')['last_report']),report)


class CollectionSourceTests(unittest.TestCase):
    def test_netflix_json_replaces_dom_history_instead_of_duplicating_episodes(self):
        dom=[{'url':'https://www.netflix.com/title/101','title':'Serie: Staffel 1: Folge A'}]
        found={}
        self.assertFalse(merge_collected_rows(found,'netflix','history',dom,[]))
        self.assertEqual(list(found),['/title/101'])
        captured=netflix_history_rows({'viewedItems':[{'movieID':101,'series':100,'seriesTitle':'Serie'},
            {'movieID':102,'series':100,'seriesTitle':'Serie'}]})
        self.assertTrue(merge_collected_rows(found,'netflix','history',dom,captured))
        self.assertEqual(set(found),{'/watch/101','/watch/102'})
        # Repeated responses and further DOM scrolling must not add the episode again.
        self.assertTrue(merge_collected_rows(found,'netflix','history',dom,captured+captured))
        self.assertEqual(len(found),2)

    def test_structured_history_does_not_replace_the_watchlist_or_other_providers(self):
        captured=netflix_history_rows({'viewedItems':[{'movieID':101,'title':'Verlauf'}]})
        found={}
        self.assertFalse(merge_collected_rows(found,'netflix','watchlist',[{'url':'https://www.netflix.com/title/200','title':'Merkliste'}],captured))
        self.assertEqual(list(found),['/title/200'])
        prime={}
        self.assertFalse(merge_collected_rows(prime,'prime','history',[{'url':'https://www.primevideo.com/detail/ABC','title':'Prime'}],captured))
        self.assertEqual(list(prime),['/detail/ABC'])


class BrowserGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_collector_stops_on_security_page_without_extracting_titles(self):
        with tempfile.TemporaryDirectory() as folder:
            browser=Browsers(folder)
            browser._open=AsyncMock();browser.close=AsyncMock()
            page=MagicMock();page.goto=AsyncMock();page.wait_for_timeout=AsyncMock()
            page.evaluate=AsyncMock(return_value={'blocked':True,'profile':None})
            browser.page=page
            with self.assertRaises(BrowserBlocked):await browser.collect(1,'crunchyroll','Person 1')
            self.assertEqual(page.evaluate.await_count,1)
            self.assertEqual(browser.last_report['watchlist']['status'],'blocked')
            browser.close.assert_awaited_once()

    async def test_redirect_to_catalog_home_is_rejected_before_dom_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            browser=Browsers(folder);browser._open=AsyncMock();browser.close=AsyncMock()
            page=MagicMock();page.url='https://www.netflix.com/browse'
            page.goto=AsyncMock();page.wait_for_timeout=AsyncMock();page.evaluate=AsyncMock(return_value={'blocked':False,'profile':None})
            page.locator.return_value.count=AsyncMock(return_value=0)
            browser.page=page
            with self.assertRaises(BrowserProblem):await browser.collect(1,'netflix')
            self.assertTrue(all('umgeleitet' in r['message'] for r in browser.last_report.values()))
            self.assertEqual(page.evaluate.await_count,2)

    async def test_wrong_provider_profile_is_rejected_without_import(self):
        with tempfile.TemporaryDirectory() as folder:
            browser=Browsers(folder);browser._open=AsyncMock();browser.close=AsyncMock()
            page=MagicMock();page.goto=AsyncMock();page.wait_for_timeout=AsyncMock()
            page.evaluate=AsyncMock(return_value={'blocked':False,'profile':'Andere Person'})
            browser.page=page
            with self.assertRaises(BrowserProblem):await browser.collect(1,'netflix','Person 1')
            self.assertTrue(all('Streamingprofil' in r['message'] for r in browser.last_report.values()))


if __name__=='__main__':unittest.main()
