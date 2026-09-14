"""retro-ears: a local page for downloading iPod-ready music."""
from __future__ import annotations

import sys
import threading
import webbrowser
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException

import jobs
import links
import settings
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


class SettingsIn(BaseModel):
    cookie_source: str


def _status_for(error: RetroError) -> int:
    if isinstance(error, NotFound):
        return 404
    if isinstance(error, (Offline, ParseChanged)):
        return 502
    return 400


def create_app(manager: jobs.JobManager | None = None, settings_file: Path | None = None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    manager = manager or jobs.JobManager(cookie_source=lambda: settings.load(settings_file)["cookie_source"])

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

    @app.get("/api/settings")
    def get_settings():
        return {**settings.load(settings_file), "platform": sys.platform}

    @app.put("/api/settings")
    def put_settings(body: SettingsIn):
        try:
            saved = settings.save({"cookie_source": body.cookie_source}, settings_file)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        return {**saved, "platform": sys.platform}

    return app


def main() -> None:
    import uvicorn

    jobs.clear_root()
    url = f"http://{HOST}:{PORT}"
    if "--no-browser" not in sys.argv:
        threading.Timer(1.5, webbrowser.open, args=[url]).start()
    print(f"retro-ears is running at {url} — press Ctrl+C to stop")
    uvicorn.run(create_app(), host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
