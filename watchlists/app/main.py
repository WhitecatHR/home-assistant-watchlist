import asyncio
import json
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .store import Store, PROVIDERS, now
from .catalog import Catalog
from .browser import Browsers, BrowserBusy, BrowserProblem

ROOT=Path(__file__).parent


class Rename(BaseModel):
    name:str=Field(min_length=1,max_length=40,pattern=r"\S")

class Add(BaseModel):
    show_id:int=Field(gt=0)
    provider:Literal["netflix","prime","disney","crunchyroll"]

class Mark(BaseModel):
    episode_id:int=Field(gt=0)
    watched:bool=True
    through:bool=False

class State(BaseModel):
    status:Literal["watching","paused","finished"]

class Resolve(BaseModel):
    show_id:int=Field(gt=0)

class Binding(BaseModel):
    source_profile:str=Field(min_length=1,max_length=80,pattern=r"\S")
    enabled:bool=False

class Action(BaseModel):
    kind:Literal["click","type","key","scroll","section"]
    x:int=Field(default=0,ge=0,lt=1280)
    y:int=Field(default=0,ge=0,lt=900)
    text:str=Field(default="",max_length=1500)
    key:Literal["Tab","Enter","Backspace","Escape","ArrowDown","ArrowUp","ControlOrMeta+A"]="Tab"
    dy:int=Field(default=0,ge=-1800,le=1800)
    section:Literal["watchlist","history"]="watchlist"


def read_options():
    try:
        return json.loads(Path(os.environ.get("WATCHLIST_OPTIONS","/data/options.json")).read_text())
    except FileNotFoundError:
        return {}


def create_app(data=None, standalone=False, catalog=None):
    data=Path(data or os.environ.get("WATCHLIST_DATA","/data/watchlists"))
    store=Store(data/"watchlists.sqlite")
    options=read_options()
    browser=Browsers(data,options.get("browser_enabled",True))
    catalog=catalog or Catalog()
    sync_lock=asyncio.Lock()

    async def sync(profile_id,provider):
        store.profile(profile_id)
        if provider not in PROVIDERS:
            raise HTTPException(404,"Dienst nicht gefunden")
        connection=next(x for x in store.connections(profile_id) if x["provider"]==provider)
        if not connection["source_profile"]:
            raise HTTPException(409,"Zuerst anmelden und das Streamingprofil bestätigen")
        if sync_lock.locked():
            raise BrowserBusy("Ein Import läuft bereits")
        async with sync_lock:
            store.connection_update(profile_id,provider,last_attempt=now(),message="Import läuft")
            try:
                results=await browser.collect(profile_id,provider)
                for section,rows in results.items():
                    store.observe(profile_id,provider,section,rows)
                count=sum(len(x) for x in results.values())
                message=f"{count} Beobachtungen eingelesen. Zuordnungen und unklare Folgen bitte prüfen."
                if provider=="disney":
                    message+=" Disney+-Folgenstand wird noch nicht automatisch eingelesen."
                store.connection_update(profile_id,provider,last_sync=now(),message=message)
                return {"message":message,"count":count}
            except BrowserBusy as exc:
                store.connection_update(profile_id,provider,last_attempt=connection["last_attempt"],message=str(exc))
                raise
            except BrowserProblem as exc:
                store.connection_update(profile_id,provider,message=str(exc))
                raise

    async def scheduler():
        await asyncio.sleep(30)
        while True:
            await browser.idle_cleanup()
            for p in store.profiles():
                for c in store.connections(p["id"]):
                    if not c["enabled"]:
                        continue
                    from datetime import datetime,timezone
                    last=c["last_attempt"]
                    due=not last or (datetime.now(timezone.utc)-datetime.fromisoformat(last)).total_seconds()>=max(60,min(1440,int(options.get("sync_interval_minutes",360))))*60
                    if due:
                        with suppress(BrowserBusy,BrowserProblem,HTTPException):
                            await sync(p["id"],c["provider"])
            await asyncio.sleep(60)

    @asynccontextmanager
    async def lifespan(app):
        task=asyncio.create_task(scheduler())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await browser.close()
        await catalog.close()

    app=FastAPI(title="Watchlists",docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.store=store
    app.state.browsers=browser

    @app.middleware("http")
    async def protect(request:Request, call_next):
        # Uvicorn must run with proxy_headers=False: the TCP peer, never a forwarded IP, authorizes ingress.
        if not standalone and (not request.client or request.client.host!="172.30.32.2"):
            return JSONResponse({"detail":"Zugriff nur über Home Assistant Ingress"},403)
        if request.method not in ("GET","HEAD","OPTIONS") and request.headers.get("x-watchlists-request")!="1":
            return JSONResponse({"detail":"Anfrage nicht aus der Watchlists-Oberfläche"},403)
        try:
            length=int(request.headers.get("content-length","0"))
        except ValueError:
            return JSONResponse({"detail":"Ungültige Anfragegröße"},400)
        if length>262144:
            return JSONResponse({"detail":"Anfrage zu groß"},413)
        response=await call_next(request)
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Referrer-Policy"]="no-referrer"
        response.headers["Cache-Control"]="no-store"
        response.headers["Content-Security-Policy"]="default-src 'self'; img-src 'self' blob: https://static.tvmaze.com; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'"
        return response

    @app.exception_handler(ValueError)
    async def value_error(request,exc):
        return JSONResponse({"detail":str(exc)},404)

    @app.exception_handler(BrowserProblem)
    async def browser_error(request,exc):
        return JSONResponse({"detail":str(exc)},503)

    @app.exception_handler(BrowserBusy)
    async def busy_error(request,exc):
        return JSONResponse({"detail":str(exc)},409)

    @app.exception_handler(httpx.HTTPError)
    async def catalog_error(request,exc):
        return JSONResponse({"detail":"Serienkatalog derzeit nicht erreichbar. Bitte später erneut versuchen."},502)

    @app.get("/")
    async def index():
        return FileResponse(ROOT/"static/index.html")

    @app.get("/api/profiles")
    async def profiles():
        return store.profiles()

    @app.patch("/api/profiles/{profile_id}")
    async def rename(profile_id:int,body:Rename):
        store.rename(profile_id,body.name.strip())
        return {"ok":True}

    @app.get("/api/catalog")
    async def search(q:str=""):
        if not 2<=len(q.strip())<=100:
            raise HTTPException(422,"Bitte mindestens zwei Zeichen eingeben")
        return await catalog.search(q.strip())

    @app.get("/api/profiles/{profile_id}/library")
    async def library(profile_id:int):
        return store.library(profile_id)

    @app.post("/api/profiles/{profile_id}/library")
    async def add(profile_id:int,body:Add):
        store.profile(profile_id)
        show,episodes=await catalog.show(body.show_id)
        store.cache_show(show,episodes)
        store.add(profile_id,body.show_id,body.provider)
        return {"ok":True}

    @app.delete("/api/profiles/{profile_id}/library/{show_id}")
    async def remove(profile_id:int,show_id:int):
        store.remove(profile_id,show_id)
        return {"ok":True}

    @app.patch("/api/profiles/{profile_id}/library/{show_id}")
    async def state(profile_id:int,show_id:int,body:State):
        store.set_status(profile_id,show_id,body.status)
        return {"ok":True}

    @app.post("/api/profiles/{profile_id}/library/{show_id}/refresh")
    async def refresh(profile_id:int,show_id:int):
        if not any(x["id"]==show_id for x in store.library(profile_id)):
            raise HTTPException(404,"Serie nicht auf deiner Liste")
        show,episodes=await catalog.show(show_id)
        store.cache_show(show,episodes)
        return {"ok":True}

    @app.get("/api/profiles/{profile_id}/library/{show_id}/episodes")
    async def episodes(profile_id:int,show_id:int):
        return store.episodes(profile_id,show_id)

    @app.patch("/api/profiles/{profile_id}/library/{show_id}/episodes")
    async def mark(profile_id:int,show_id:int,body:Mark):
        store.mark(profile_id,show_id,body.episode_id,body.watched,body.through)
        return {"ok":True}

    @app.get("/api/profiles/{profile_id}/connections")
    async def connections(profile_id:int):
        return store.connections(profile_id)

    def validate(profile_id,provider):
        store.profile(profile_id)
        if provider not in PROVIDERS:
            raise HTTPException(404,"Dienst nicht gefunden")

    @app.patch("/api/profiles/{profile_id}/connections/{provider}")
    async def binding(profile_id:int,provider:str,body:Binding):
        validate(profile_id,provider)
        store.connection_update(profile_id,provider,source_profile=body.source_profile.strip(),enabled=int(body.enabled),message="Profil bestätigt; Import noch nicht geprüft")
        return {"ok":True}

    @app.post("/api/profiles/{profile_id}/connections/{provider}/sync")
    async def run_sync(profile_id:int,provider:str):
        validate(profile_id,provider)
        return await sync(profile_id,provider)

    @app.delete("/api/profiles/{profile_id}/connections/{provider}")
    async def disconnect(profile_id:int,provider:str):
        validate(profile_id,provider)
        await browser.forget(profile_id,provider)
        store.connection_update(profile_id,provider,source_profile="",enabled=0,message="Getrennt; lokale Watchlists bleiben erhalten")
        return {"ok":True}

    @app.post("/api/profiles/{profile_id}/connections/{provider}/browser")
    async def open_browser(profile_id:int,provider:str):
        validate(profile_id,provider)
        await browser.open_login(profile_id,provider)
        return {"width":1280,"height":900}

    @app.get("/api/profiles/{profile_id}/connections/{provider}/browser")
    async def browser_image(profile_id:int,provider:str):
        validate(profile_id,provider)
        return Response(await browser.screenshot(profile_id,provider),media_type="image/jpeg")

    @app.post("/api/profiles/{profile_id}/connections/{provider}/browser/action")
    async def browser_action(profile_id:int,provider:str,body:Action):
        validate(profile_id,provider)
        try:
            await browser.action(profile_id,provider,body.model_dump())
        except (BrowserBusy,BrowserProblem):
            raise
        except Exception:
            raise BrowserProblem("Browseraktion nicht abgeschlossen. Bitte Bild aktualisieren.") from None
        return {"ok":True}

    @app.delete("/api/profiles/{profile_id}/connections/{provider}/browser")
    async def close_browser(profile_id:int,provider:str):
        validate(profile_id,provider)
        await browser.stop(profile_id,provider)
        return {"ok":True}

    @app.get("/api/profiles/{profile_id}/pending")
    async def pending(profile_id:int):
        return store.pending(profile_id)

    @app.post("/api/profiles/{profile_id}/pending/{observation_id}")
    async def resolve(profile_id:int,observation_id:int,body:Resolve):
        store.profile(profile_id)
        show,episodes=await catalog.show(body.show_id)
        store.cache_show(show,episodes)
        store.resolve(profile_id,observation_id,body.show_id)
        return {"ok":True}

    @app.get("/api/export")
    async def export():
        return JSONResponse(store.export(),headers={"Content-Disposition":'attachment; filename="watchlists-export.json"'})

    app.mount("/static",StaticFiles(directory=ROOT/"static"),name="static")
    return app


if __name__=="__main__":
    import uvicorn
    uvicorn.run(create_app(),host="0.0.0.0",port=8099,proxy_headers=False,access_log=False)
