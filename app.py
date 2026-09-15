"""retro-ears: a local page for downloading iPod-ready music."""
from __future__ import annotations

import socket
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException

import jobs
import links
import updates
import ytmusic
from models import NotFound, Offline, ParseChanged, RetroError, Track

HOST = "127.0.0.1"
PORT = 8787
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
STATIC_DIR = Path(__file__).parent / "static"


class TrackIn(BaseModel):
    title: str
    artist: str
    album: str | None = None
    duration_s: int | None = None
    art_url: str | None = None
    video_id: str | None = None


class JobIn(BaseModel):
    tracks: list[TrackIn] = Field(min_length=1, max_length=1000)
    format: Literal["m4a", "opus", "mp3"] = "m4a"
    name: str = Field(default="retro-ears", max_length=200)


def _status_for(error: RetroError) -> int:
    if isinstance(error, NotFound):
        return 404
    if isinstance(error, (Offline, ParseChanged)):
        return 502
    return 400


def create_app(manager: jobs.JobManager | None = None, checker=None, restart=None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    manager = manager or jobs.JobManager()
    checker = checker or updates.ReleaseChecker()
    restart = restart or updates.schedule_restart

    @app.middleware("http")
    async def only_local_host(request: Request, call_next):
        # Stops DNS-rebinding: other web pages can't reach this app through a different host name.
        if request.headers.get("host") not in ALLOWED_HOSTS:
            return JSONResponse({"error": "Forbidden"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(RetroError)
    async def retro_error(request: Request, error: RetroError):
        return JSONResponse({"error": str(error)}, status_code=_status_for(error))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        return JSONResponse({"error": error.detail}, status_code=error.status_code)

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/search")
    def search(q: str = "", tab: Literal["songs", "playlists"] = Query("songs", alias="type")):
        if not q.strip():
            raise HTTPException(400, "Type something to search")
        return links.resolve(q, tab)

    @app.get("/api/playlist")
    def playlist(playlist_id: str = Query(alias="id")):
        return ytmusic.get_playlist(playlist_id)

    @app.post("/api/jobs")
    def start_job(body: JobIn):
        try:
            job = manager.start([Track(**track.model_dump()) for track in body.tracks], body.format, body.name)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        return {"id": job.id}

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str):
        return manager.get(job_id).public()

    @app.get("/api/jobs/{job_id}/file")
    def job_file(job_id: str):
        path, filename = manager.file(job_id)
        return FileResponse(path, filename=filename)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        manager.cancel(job_id)
        return {"ok": True}

    @app.get("/api/version")
    def version():
        return updates.version_info(checker)

    @app.post("/api/update")
    def update():
        if manager.busy():
            raise HTTPException(409, "Wait for the current download to finish")
        if updates.uv_path() is None:
            raise HTTPException(400, "Updating only works when retro-ears is started with its launcher")
        if not updates.update_ytdlp():
            raise HTTPException(502, "Update failed — check your internet connection")
        restart()
        return {"ok": True, "restarting": True}

    return app


def port_status(host: str = HOST, port: int = PORT, timeout: float = 2.0) -> str:
    """'free', 'retro-ears' (a copy is already running), or 'other' (another program has the port)."""
    with socket.socket() as probe:
        if sys.platform != "win32":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # mirror uvicorn so a quick restart isn't blocked
        try:
            probe.bind((host, port))
            return "free"
        except OSError:
            pass
    try:
        response = httpx.get(f"http://{host}:{port}/api/version", timeout=timeout)
        if response.status_code == 200 and "app" in response.json():
            return "retro-ears"
    except (httpx.HTTPError, ValueError):
        pass
    return "other"


def main() -> None:
    import uvicorn

    url = f"http://{HOST}:{PORT}"
    status = port_status()
    if status == "retro-ears":
        print("retro-ears is already running", flush=True)
        if "--no-browser" not in sys.argv:
            webbrowser.open(url)
        sys.exit(0)
    if status == "other":
        print(f"Port {PORT} is in use by another program", flush=True)
        sys.exit(1)

    jobs.clear_root()
    if "--no-browser" not in sys.argv:
        threading.Timer(1.5, webbrowser.open, args=[url]).start()
    print(f"retro-ears is running at {url} — keep this window open; close it to stop.", flush=True)
    uvicorn.run(create_app(), host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
