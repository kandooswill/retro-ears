"""App version, the GitHub release check, and updating yt-dlp in place."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import certifi
import httpx
import yt_dlp.version

APP_DIR = Path(__file__).parent
RELEASES_API = "https://api.github.com/repos/kandooswill/retro-ears/releases/latest"
CHECK_EVERY_S = 6 * 3600
RESTART_EXIT_CODE = 42
STARTED = time.time()  # new value after every restart, so the page can tell the app came back


def app_version() -> str:
    try:
        return (APP_DIR / "VERSION").read_text("utf-8").strip()
    except OSError:
        return "0.0.0"


def ytdlp_version() -> str:
    return yt_dlp.version.__version__


def uv_path() -> Path | None:
    value = os.environ.get("RETRO_UV")
    return Path(value) if value and Path(value).is_file() else None


def parse_version(text: str) -> tuple[int, int, int] | None:
    found = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text.strip())
    return tuple(int(part) for part in found.groups()) if found else None


def is_newer(candidate: str, current: str) -> bool:
    new, old = parse_version(candidate), parse_version(current)
    return bool(new and old and new > old)


def fetch_latest() -> dict | None:
    response = httpx.get(RELEASES_API, timeout=5, verify=certifi.where(), headers={"Accept": "application/vnd.github+json"})
    if response.status_code != 200:
        return None
    data = response.json()
    return {"tag": data.get("tag_name", ""), "url": data.get("html_url")}


class ReleaseChecker:
    """Asks GitHub for the latest release at most once every six hours."""

    def __init__(self, fetch: Callable[[], dict | None] = fetch_latest, clock: Callable[[], float] = time.monotonic):
        self._fetch = fetch
        self._clock = clock
        self._checked_at: float | None = None
        self._latest: dict | None = None
        self._lock = threading.Lock()

    def latest(self) -> dict | None:
        with self._lock:
            now = self._clock()
            if self._checked_at is None or now - self._checked_at >= CHECK_EVERY_S:
                self._checked_at = now
                try:
                    self._latest = self._fetch()
                except Exception:  # offline, rate-limited, or GitHub changed: just show no banner
                    self._latest = None
            return self._latest


def version_info(checker) -> dict:
    current = app_version()
    latest = checker.latest()
    newer = latest if latest and is_newer(latest.get("tag", ""), current) else None
    return {
        "app": current,
        "ytdlp": ytdlp_version(),
        "can_update": uv_path() is not None,
        "latest_app": newer["tag"].lstrip("v") if newer else None,
        "release_url": newer["url"] if newer else None,
        "started": STARTED,
    }


def update_command(uv: Path) -> list[str]:
    return [str(uv), "pip", "install", "--python", sys.executable, "--upgrade", "yt-dlp[default]"]


def update_ytdlp(run: Callable = subprocess.run) -> bool:
    uv = uv_path()
    if uv is None:
        return False
    try:
        result = run(update_command(uv), capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def schedule_restart(delay_s: float = 1.0, exit: Callable[[int], object] = os._exit) -> threading.Timer:
    """Exit with 42 shortly after the HTTP reply is sent; the launcher starts the app again."""
    timer = threading.Timer(delay_s, exit, args=[RESTART_EXIT_CODE])
    timer.daemon = True
    timer.start()
    return timer
