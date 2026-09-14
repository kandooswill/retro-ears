"""Download one song from YouTube Music with yt-dlp in the chosen format."""
from __future__ import annotations

import re
import shutil
import sys
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
import yt_dlp

import tags
from models import RetroError, Track

FORMATS = ("m4a", "opus", "mp3")

# (format, premium) -> yt-dlp format selector. 141 and 774 only exist with a Premium login.
FORMAT_STRINGS = {
    ("m4a", True): "141/140/bestaudio[ext=m4a]",
    ("m4a", False): "140/bestaudio[ext=m4a]",
    ("opus", True): "774/251/bestaudio[acodec=opus]",
    ("opus", False): "251/bestaudio[acodec=opus]",
    ("mp3", True): "774/141/251/140/bestaudio",
    ("mp3", False): "251/140/bestaudio",
}

CODEC_NAMES = {"mp4a": "AAC", "opus": "Opus"}
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}

_name_lock = threading.Lock()


@dataclass
class Result:
    path: Path
    quality: str


class _QuietLogger:
    """Keeps yt-dlp from printing progress and warnings into the server log."""

    def debug(self, message: str) -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


def format_string(fmt: str, premium: bool) -> str:
    return FORMAT_STRINGS[(fmt, premium)]


def postprocessor(fmt: str) -> dict:
    # FFmpegExtractAudio copies AAC→m4a and Opus→opus without re-encoding; mp3 is encoded at 320k.
    pp = {"key": "FFmpegExtractAudio", "preferredcodec": fmt}
    if fmt == "mp3":
        pp["preferredquality"] = "320"
    return pp


def cookie_opts(cookie_source: str) -> dict:
    if not cookie_source or cookie_source == "off":
        return {}
    if cookie_source.startswith("file:"):
        return {"cookiefile": cookie_source[len("file:"):]}
    return {"cookiesfrombrowser": (cookie_source, None, None, None)}


def deno_path() -> str | None:
    name = "deno.exe" if sys.platform == "win32" else "deno"
    beside_python = Path(sys.executable).parent / name
    return str(beside_python) if beside_python.exists() else shutil.which("deno")


def build_opts(fmt: str, outdir: Path, cookie_source: str) -> dict:
    cookies = cookie_opts(cookie_source)
    opts = {
        "format": format_string(fmt, premium=bool(cookies)),
        "outtmpl": str(outdir / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _QuietLogger(),
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
        "postprocessors": [postprocessor(fmt)],
        **cookies,
    }
    deno = deno_path()
    if deno:
        opts["js_runtimes"] = {"deno": {"path": deno}}
    return opts


def quality_label(fmt: str, acodec: str | None, abr: float | None) -> str:
    base = (acodec or "").split(".")[0]
    name = CODEC_NAMES.get(base, base.upper() or "Audio")
    source = f"{name} {round(abr) if abr else '?'}"
    return f"MP3 320 (from {source})" if fmt == "mp3" else source


def safe_filename(name: str, max_len: int = 150) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    if not name:
        return "track"
    if name.split(".")[0].upper() in WINDOWS_RESERVED:
        name = f"_{name}"
    return name[:max_len].rstrip(". ") or "track"


def unique_path(directory: Path, stem: str, ext: str) -> Path:
    candidate = directory / f"{stem}.{ext}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem} ({counter}).{ext}"
        counter += 1
    return candidate


def friendly_error(message: str) -> str:
    lowered = message.lower()
    if "confirm your age" in lowered or "age-restricted" in lowered:
        return "Age-restricted — needs a Premium login"
    if "video unavailable" in lowered or "private video" in lowered:
        return "Unavailable on YouTube"
    if "requested format is not available" in lowered:
        return "No audio stream in this format"
    if "unable to download" in lowered or "timed out" in lowered or "getaddrinfo" in lowered:
        return "Network error — check your connection"
    return re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*[\w-]+:\s*)?", "", message).strip()[:200]


def _extract(opts: dict, url: str) -> dict:
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=True)


def _download(fmt: str, outdir: Path, url: str, cookie_source: str) -> dict:
    try:
        return _extract(build_opts(fmt, outdir, cookie_source), url)
    except Exception as first:
        if not cookie_opts(cookie_source):
            raise RetroError(friendly_error(str(first))) from first
    # The Premium login couldn't be used; the app must still work without it.
    try:
        return _extract(build_opts(fmt, outdir, "off"), url)
    except Exception as second:
        raise RetroError(friendly_error(str(second))) from second


def fetch(track: Track, fmt: str, workdir: Path, cookie_source: str = "off") -> Result:
    if fmt not in FORMATS:
        raise ValueError(f"Unknown format: {fmt}")
    if not track.video_id:
        raise RetroError("This song has no YouTube source")
    workdir.mkdir(parents=True, exist_ok=True)
    tmp = workdir / f".tmp-{uuid.uuid4().hex}"
    tmp.mkdir()
    try:
        info = _download(fmt, tmp, f"https://music.youtube.com/watch?v={track.video_id}", cookie_source)
        source = Path(info["requested_downloads"][0]["filepath"])
        tags.write_tags(source, track, tags.fetch_art(track.art_url))
        with _name_lock:
            final = unique_path(workdir, safe_filename(f"{track.artist} - {track.title}"), fmt)
            source.replace(final)
        return Result(path=final, quality=quality_label(fmt, info.get("acodec"), info.get("abr")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
