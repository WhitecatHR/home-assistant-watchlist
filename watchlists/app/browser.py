"""A single local browser, remotely operated through the HA-authenticated UI."""
import asyncio
import os
import shutil
import time
from pathlib import Path
from .providers import SPECS, EXTRACT_JS, allowed_url, normalize_row


class BrowserBusy(Exception):
    pass


class BrowserProblem(Exception):
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

    async def collect(self, profile_id, provider):
        if self.lock.locked() or (self.interactive and time.monotonic()-self.last_used<300):
            raise BrowserBusy("Anmeldefenster ist geöffnet. Erst schließen, dann importieren.")
        async with self.lock:
            await self._open(profile_id,provider)
            results={}
            try:
                for section in ("watchlist","history"):
                    target=SPECS[provider][section]
                    if not target:
                        continue
                    await self.page.goto(target,wait_until="domcontentloaded",timeout=45000)
                    await self.page.wait_for_timeout(1500)
                    # Fail closed on a visible password input or an explicit authentication URL.
                    if reauth_url(self.page.url) or await self.page.locator('input[type="password"]:visible').count():
                        raise BrowserProblem("Anmeldung erforderlich. Bitte das richtige Streamingprofil erneut verbinden.")
                    found={}
                    stable=0
                    for _ in range(10):
                        rows=await self.page.evaluate(EXTRACT_JS,{"provider":provider,"section":section})
                        before=len(found)
                        for row in rows:
                            item=normalize_row(provider,row)
                            if item:
                                found[item["provider_id"]]=item
                        stable=stable+1 if before==len(found) else 0
                        if stable>=3:
                            break
                        await self.page.mouse.wheel(0,900)
                        await self.page.wait_for_timeout(650)
                    results[section]=list(found.values())
                if not any(results.values()):
                    raise BrowserProblem("Keine Einträge erkannt. Die Liste kann leer sein, die Anmeldung fehlen oder der Seitenadapter muss angepasst werden. Vorhandene Daten bleiben erhalten.")
                return results
            except (BrowserProblem,BrowserBusy):
                raise
            except Exception:
                raise BrowserProblem("Import nicht abgeschlossen. Die Website hat anders geantwortet oder den Zugriff unterbrochen. Vorhandene Daten bleiben erhalten.") from None
            finally:
                await self.close()


def reauth_url(url):
    from urllib.parse import urlparse
    path=urlparse(url).path.lower()
    return any(part in path for part in ["/login","/signin","/sign-in","/auth/login","/ap/signin"])
