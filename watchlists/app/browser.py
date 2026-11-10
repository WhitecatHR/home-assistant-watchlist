"""A single local browser, remotely operated through the HA-authenticated UI."""
import asyncio
import os
import re
import shutil
import time
from pathlib import Path
from .providers import SPECS, EXTRACT_JS, PAGE_STATUS_JS, allowed_url, normalize_row,page_is_section,netflix_history_rows,enrich_netflix


class BrowserBusy(Exception):
    pass


class BrowserProblem(Exception):
    pass

class BrowserBlocked(BrowserProblem):
    pass


class Browsers:
    def __init__(self, data, enabled=True):
        self.root=Path(data)/".sessions"
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.enabled=enabled
        self.lock=asyncio.Lock()
        self.context=None
        self.page=None
        self.key=None
        self.engine=None
        self.last_used=0
        self.interactive=False
        self.last_report={}

    async def close(self):
        if self.context:
            try:
                await self.context.close()
            finally:
                self.context=self.page=self.key=None
        if self.engine:
            await self.engine.stop()
            self.engine=None
        self.interactive=False

    async def _open(self, profile_id, provider, interactive=False):
        if not self.enabled:
            raise BrowserProblem("Browser in der Add-on-Konfiguration deaktiviert")
        executable=os.environ.get("CHROMIUM_PATH") or shutil.which("chromium")
        if not executable:
            raise BrowserProblem("Chromium nicht vorhanden. Der Browser wird im Add-on-Container mitgeliefert.")
        key=(profile_id,provider)
        if self.key!=key:
            await self.close()
            from playwright.async_api import async_playwright
            self.engine=await async_playwright().start()
            path=self.root/f"{profile_id}-{provider}"
            path.mkdir(mode=0o700,exist_ok=True)
            try:
                self.context=await self.engine.chromium.launch_persistent_context(str(path),executable_path=executable,
                    headless=not bool(os.environ.get("DISPLAY")),viewport={"width":1280,"height":900},locale="de-DE",
                    accept_downloads=False,args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"],
                    permissions=[], service_workers="block")
                async def route(req):
                    request=req.request
                    main=request.is_navigation_request() and request.frame==self.page.main_frame
                    if allowed_url(provider,request.url,navigation=main):
                        await req.continue_()
                    else:
                        await req.abort()
                await self.context.route("**/*",route)
                self.page=self.context.pages[0] if self.context.pages else await self.context.new_page()
                self.page.on("popup",lambda p:asyncio.create_task(p.close()))
                self.key=key
            except Exception:
                await self.close()
                raise BrowserProblem("Browser konnte nicht gestartet werden. Bitte Add-on-Protokoll und Arbeitsspeicher prüfen.") from None
        self.interactive=interactive
        self.last_used=time.monotonic()

    async def open_login(self, profile_id, provider):
        if self.lock.locked():
            raise BrowserBusy("Ein Import läuft. Bitte kurz warten.")
        async with self.lock:
            await self._open(profile_id,provider,True)
            try:
                await self.page.goto(SPECS[provider]["login"],wait_until="domcontentloaded",timeout=45000)
            except Exception:
                raise BrowserProblem("Die Anmeldeseite wurde nicht vollständig geladen. Erneut öffnen oder Bild aktualisieren.") from None

    def _require(self, profile_id, provider):
        if self.key!=(profile_id,provider) or not self.page or not self.interactive:
            raise BrowserProblem("Anmeldefenster ist geschlossen. Bitte neu öffnen.")
        self.last_used=time.monotonic()

    async def screenshot(self, profile_id, provider):
        if self.lock.locked():
            raise BrowserBusy("Browser beschäftigt")
        async with self.lock:
            self._require(profile_id,provider)
            return await self.page.screenshot(type="jpeg",quality=72,timeout=10000)

    async def status(self,profile_id,provider):
        if self.lock.locked():raise BrowserBusy('Browser beschäftigt')
        async with self.lock:
            self._require(profile_id,provider)
            data=await self.page.evaluate(PAGE_STATUS_JS)
            data['message']='Der Anbieter zeigt eine Sicherheitsprüfung. Solange sie blockiert, ist kein automatischer Import möglich. Die Prüfung wird nicht umgangen; Titel lassen sich lokal verwalten.' if data.get('blocked') else ''
            return data

    async def action(self, profile_id, provider, action):
        if self.lock.locked():
            raise BrowserBusy("Browser beschäftigt")
        async with self.lock:
            self._require(profile_id,provider)
            kind=action["kind"]
            if kind=="click":
                await self.page.mouse.click(action["x"],action["y"])
            elif kind=="type":
                await self.page.keyboard.insert_text(action["text"])
            elif kind=="key":
                await self.page.keyboard.press(action["key"])
            elif kind=="scroll":
                await self.page.mouse.wheel(0,action["dy"])
            elif kind=="section":
                target=SPECS[provider][action["section"]]
                if not target:
                    raise BrowserProblem("Für diesen Bereich gibt es noch keinen Adapter.")
                await self.page.goto(target,wait_until="domcontentloaded",timeout=45000)

    async def stop(self, profile_id, provider):
        if self.lock.locked():
            raise BrowserBusy("Browser beschäftigt")
        async with self.lock:
            if self.key==(profile_id,provider):
                await self.close()

    async def forget(self, profile_id, provider):
        await self.stop(profile_id,provider)
        shutil.rmtree(self.root/f"{profile_id}-{provider}",ignore_errors=True)

    async def idle_cleanup(self):
        if not self.lock.locked() and self.context and time.monotonic()-self.last_used>300:
            async with self.lock:
                await self.close()

    async def collect(self, profile_id, provider,expected_profile=None):
        if self.lock.locked() or (self.interactive and time.monotonic()-self.last_used<300):
            raise BrowserBusy("Anmeldefenster ist geöffnet. Erst schließen, dann importieren.")
        async with self.lock:
            await self._open(profile_id,provider)
            results={}
            self.last_report={}
            captured=[];tasks=set()
            def response_handler(response):
                # Only the site's own viewing-activity responses. No cookies, auth URLs or session JSON are retained.
                if provider!='netflix' or not allowed_url(provider,response.url,True) or not any(s in response.url.lower() for s in ['viewingactivity','viewing-activity','pathevaluator']):return
                async def capture():
                    try:
                        if 'json' not in response.headers.get('content-type',''):return
                        body=await response.body()
                        if len(body)>4_000_000:return
                        import json
                        captured.extend(netflix_history_rows(json.loads(body)))
                    except Exception:pass
                task=asyncio.create_task(capture());tasks.add(task);task.add_done_callback(tasks.discard)
            self.page.on('response',response_handler)
            try:
                for section in ("watchlist","history"):
                    target=SPECS[provider][section]
                    if not target:
                        continue
                    try:
                        await self.page.goto(target,wait_until="domcontentloaded",timeout=45000)
                        await self.page.wait_for_timeout(1800)
                        status=await self.page.evaluate(PAGE_STATUS_JS)
                        if status.get('blocked'):raise BrowserBlocked('Sicherheitsprüfung des Anbieters blockiert den Import. Regelmäßiger Import wird angehalten; keine Umgehung.')
                        if expected_profile and status.get('profile') and status['profile'].casefold().strip()!=expected_profile.casefold().strip():
                            raise BrowserProblem('Das angemeldete Streamingprofil stimmt nicht mit dem bestätigten Profil überein. Bitte Anmeldung und Profilnamen prüfen.')
                        if reauth_url(self.page.url) or await self.page.locator('input[type="password"]:visible').count():
                            raise BrowserProblem('Anmeldung erforderlich. Bitte das richtige Streamingprofil erneut verbinden.')
                        if not page_is_section(provider,section,self.page.url):
                            raise BrowserProblem('Die Website hat auf einen anderen Bereich umgeleitet. Empfehlungen werden nicht importiert.')
                        found={};stable=0;recognized=False;selector=''
                        for _ in range(10):
                            if tasks:await asyncio.wait(tuple(tasks),timeout=3)
                            extraction=await self.page.evaluate(EXTRACT_JS,{"provider":provider,"section":section})
                            self.last_report[section]={'diagnostics':extraction.get('diagnostics',{})}
                            recognized=recognized or extraction.get('recognized',False);selector=extraction.get('selector',selector)
                            rows=extraction.get('rows',[]) if extraction.get('recognized') else []
                            before=len(found)
                            for row in rows:
                                item=normalize_row(provider,row)
                                if item:found[item['provider_id']]=item
                            if provider=='netflix' and section=='history' and captured:
                                for item in captured:found[item['provider_id']]=item
                                recognized=True;selector='viewing-activity JSON'
                            stable=stable+1 if before==len(found) else 0
                            if stable>=3:break
                            if provider=='netflix' and section=='history':
                                more=self.page.get_by_role('button',name=re.compile(r'^(Mehr anzeigen|Show more)$',re.I))
                                if await more.count() and await more.first.is_visible():await more.first.click()
                            await self.page.mouse.wheel(0,900)
                            await self.page.wait_for_timeout(650)
                        if not recognized:raise BrowserProblem('Listenbereich nicht erkannt. Es wird nicht die ganze Seite als Watchlist übernommen.')
                        rows=list(found.values())
                        if provider=='netflix' and section=='history':
                            failures=0
                            for ident in list(dict.fromkeys(r.get('series_id') or int(r['provider_id'].rsplit('/',1)[-1]) for r in rows))[:12]:
                                metadata=await self.page.evaluate(r'''async id => {
                                  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),6000);
                                  try {const r=await fetch('/nq/website/memberapi/release/metadata?languages=de-DE&movieid='+encodeURIComponent(id),{credentials:'same-origin',signal:controller.signal});
                                    if(!r.ok)return null;const data=await r.json();return data.video || null;
                                  } catch {return null;} finally {clearTimeout(timer);}
                                }''',ident)
                                if not metadata:
                                    failures+=1
                                    if failures>=2:break
                                else:enrich_netflix(rows,metadata)
                        results[section]=rows
                        self.last_report[section].update({'status':'ok','count':len(rows),'scope':selector,'profile_checked':bool(status.get('profile'))})
                    except (BrowserProblem,BrowserBlocked) as exc:
                        self.last_report.setdefault(section,{}).update({'status':'blocked' if isinstance(exc,BrowserBlocked) else 'failed','message':str(exc)})
                        if isinstance(exc,BrowserBlocked):
                            if not results:raise
                            break
                    except Exception:
                        self.last_report[section]={'status':'failed','message':'Bereich konnte nicht eingelesen werden. Bestehende Daten bleiben erhalten.'}
                if not any(results.values()):
                    if results:return {**results,'_report':self.last_report}
                    detail=next((r.get('message') for r in self.last_report.values() if r.get('message')),None)
                    raise BrowserProblem(detail or 'Keine bestätigten Listenbereiche erkannt. Bestehende Daten bleiben erhalten.')
                results['_report']=self.last_report
                return results
            except (BrowserProblem,BrowserBusy):
                raise
            except Exception:
                raise BrowserProblem("Import nicht abgeschlossen. Die Website hat anders geantwortet oder den Zugriff unterbrochen. Vorhandene Daten bleiben erhalten.") from None
            finally:
                for task in tuple(tasks):task.cancel()
                if tasks:await asyncio.gather(*tasks,return_exceptions=True)
                await self.close()


def reauth_url(url):
    from urllib.parse import urlparse
    path=urlparse(url).path.lower()
    return any(part in path for part in ["/login","/signin","/sign-in","/auth/login","/ap/signin"])
