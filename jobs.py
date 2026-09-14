"""In-memory download jobs: run songs on a small thread pool and package the result."""
from __future__ import annotations

import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import download
import ytmusic
from models import NotFound, RetroError, Track

ROOT = Path(tempfile.gettempdir()) / "retro-ears-jobs"
WORKERS = 3
KEEP_SECONDS = 3600


@dataclass
class Job:
    id: str
    name: str
    fmt: str
    tracks: list[Track]
    dir: Path
    status: str = "running"  # running | done | failed
    done: int = 0
    failed: int = 0
    current: str | None = None
    cancelled: bool = False
    results: list[dict] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)
    finished_at: float | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def public(self) -> dict:
        with self.lock:
            return {
                "id": self.id,
                "name": self.name,
                "status": self.status,
                "done": self.done,
                "failed": self.failed,
                "total": len(self.tracks),
                "current": self.current,
                "cancelled": self.cancelled,
                "results": list(self.results),
            }


def clear_root(root: Path = ROOT) -> None:
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)


def build_zip(files: list[Path], zip_path: Path, folder: str) -> None:
    partial = zip_path.with_name(zip_path.name + ".part")
    with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_STORED) as archive:  # audio is already compressed
        for file in files:
            archive.write(file, arcname=f"{folder}/{file.name}")
    partial.replace(zip_path)


class JobManager:
    def __init__(
        self,
        root: Path = ROOT,
        fetch: Callable = download.fetch,
        match: Callable = ytmusic.match,
        workers: int = WORKERS,
    ):
        self.root = root
        self.jobs: dict[str, Job] = {}
        self._fetch = fetch
        self._match = match
        self._workers = workers
        root.mkdir(parents=True, exist_ok=True)

    def start(self, tracks: list[Track], fmt: str, name: str) -> Job:
        if not tracks:
            raise ValueError("No songs to download")
        if fmt not in download.FORMATS:
            raise ValueError(f"Unknown format: {fmt}")
        self.cleanup()
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id, name=name.strip() or "retro-ears", fmt=fmt, tracks=list(tracks), dir=self.root / job_id)
        job.dir.mkdir(parents=True)
        self.jobs[job_id] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def get(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise NotFound("Download not found")
        return job

    def cancel(self, job_id: str) -> None:
        job = self.get(job_id)
        with job.lock:
            job.cancelled = True

    def file(self, job_id: str) -> tuple[Path, str]:
        job = self.get(job_id)
        with job.lock:
            if job.status == "running":
                raise RetroError("Still downloading")
            if not job.files:
                raise RetroError("Nothing was downloaded")
            if len(job.tracks) == 1:
                return job.files[0], job.files[0].name
            folder = download.safe_filename(job.name)
            zip_path = job.dir / f"{folder}.zip"
            if not zip_path.exists():
                build_zip(job.files, zip_path, folder)
            return zip_path, zip_path.name

    def cleanup(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        for job_id, job in list(self.jobs.items()):
            if job.finished_at is not None and now - job.finished_at > KEEP_SECONDS:
                shutil.rmtree(job.dir, ignore_errors=True)
                del self.jobs[job_id]

    def _run(self, job: Job) -> None:
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            list(pool.map(lambda track: self._one(job, track), job.tracks))
        with job.lock:
            job.current = None
            job.status = "done" if job.files else "failed"
            job.finished_at = time.time()

    def _one(self, job: Job, track: Track) -> None:
        with job.lock:
            if job.cancelled:
                return
            job.current = f"{track.title} — {track.artist}"
        try:
            result = self._fetch(self._match(track), job.fmt, job.dir)
        except Exception as exc:  # one bad song must not stop the rest of the playlist
            with job.lock:
                job.failed += 1
                job.results.append({"title": track.title, "artist": track.artist, "error": (str(exc) or type(exc).__name__)[:200]})
            return
        with job.lock:
            job.done += 1
            job.files.append(result.path)
            job.results.append({"title": track.title, "artist": track.artist, "quality": result.quality})
