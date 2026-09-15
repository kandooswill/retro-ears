"""Copy finished songs onto a Rockbox iPod."""
from __future__ import annotations

import shutil
from pathlib import Path

import download
from models import RetroError, Track

HEADROOM_BYTES = 1024 * 1024


def destination_path(mount: Path, track: Track, ext: str) -> Path:
    artist = download.safe_filename(track.artist)
    album = download.safe_filename(track.album) if track.album else "Singles"
    name = download.safe_filename(f"{track.artist} - {track.title}")
    return mount / "Music" / artist / album / f"{name}.{ext}"


def copy_to_ipod(file: Path, track: Track, art: bytes | None, mount: Path) -> str:
    if not (mount / ".rockbox").is_dir():
        raise RetroError("iPod disconnected")
    ext = file.suffix.lstrip(".")
    target = destination_path(mount, track, ext)
    size = file.stat().st_size
    if target.exists() and target.stat().st_size == size:
        return "Already on iPod"
    if shutil.disk_usage(mount).free < size + HEADROOM_BYTES:
        raise RetroError("iPod is full")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target = download.unique_path(target.parent, target.stem, ext)
    partial = target.with_name(target.name + ".part")
    try:
        shutil.copyfile(file, partial)
        partial.replace(target)
    except OSError as exc:
        try:
            partial.unlink(missing_ok=True)
        except OSError:
            pass
        raise RetroError("iPod disconnected") from exc
    cover = target.parent / "cover.jpg"
    if art and not cover.exists():
        try:
            cover.write_bytes(art)  # Rockbox shows cover.jpg for every song in the folder
        except OSError:
            pass
    return "Saved to iPod"
