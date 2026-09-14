"""Cover art download and tag writing for m4a, opus and mp3 files."""
from __future__ import annotations

import base64
import io
from pathlib import Path

import certifi
import httpx
from mutagen.flac import Picture
from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus
from PIL import Image

from models import Track

ART_SIZE = 600


def to_baseline_jpeg(data: bytes, size: int = ART_SIZE) -> bytes:
    """Fit inside `size` and re-save as baseline JPEG (Rockbox can't decode progressive JPEG)."""
    image = Image.open(io.BytesIO(data)).convert("RGB")
    image.thumbnail((size, size))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=90, progressive=False)
    return out.getvalue()


def fetch_art(url: str | None) -> bytes | None:
    if not url:
        return None
    try:
        response = httpx.get(url, timeout=15, follow_redirects=True, verify=certifi.where())
        response.raise_for_status()
        return to_baseline_jpeg(response.content)
    except (httpx.HTTPError, OSError):  # PIL's UnidentifiedImageError is an OSError
        return None


def write_tags(path: Path, track: Track, art: bytes | None) -> None:
    writers = {".m4a": _tag_m4a, ".opus": _tag_opus, ".mp3": _tag_mp3}
    writer = writers.get(path.suffix.lower())
    if writer is None:
        raise ValueError(f"Unsupported file type: {path.suffix}")
    writer(path, track, art)


def _tag_m4a(path: Path, track: Track, art: bytes | None) -> None:
    audio = MP4(path)
    audio["\xa9nam"] = [track.title]
    audio["\xa9ART"] = [track.artist]
    if track.album:
        audio["\xa9alb"] = [track.album]
    if art:
        audio["covr"] = [MP4Cover(art, imageformat=MP4Cover.FORMAT_JPEG)]
    audio.save()


def _tag_opus(path: Path, track: Track, art: bytes | None) -> None:
    audio = OggOpus(path)
    audio["title"] = [track.title]
    audio["artist"] = [track.artist]
    if track.album:
        audio["album"] = [track.album]
    if art:
        picture = Picture()
        picture.type = 3  # front cover
        picture.mime = "image/jpeg"
        picture.desc = "Cover"
        picture.width, picture.height = Image.open(io.BytesIO(art)).size
        picture.depth = 24
        picture.data = art
        audio["metadata_block_picture"] = [base64.b64encode(picture.write()).decode("ascii")]
    audio.save()


def _tag_mp3(path: Path, track: Track, art: bytes | None) -> None:
    try:
        id3 = ID3(path)
    except ID3NoHeaderError:
        id3 = ID3()
    id3.setall("TIT2", [TIT2(encoding=3, text=[track.title])])
    id3.setall("TPE1", [TPE1(encoding=3, text=[track.artist])])
    if track.album:
        id3.setall("TALB", [TALB(encoding=3, text=[track.album])])
    if art:
        id3.setall("APIC", [APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=art)])
    id3.save(path, v2_version=3)  # stock iPods read ID3v2.3 most reliably
