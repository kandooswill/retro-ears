# retro-ears Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local ytmp3-style web page that searches YouTube Music songs and playlists, reads pasted YouTube / Spotify / Apple Music links, and downloads iPod-ready M4A, Opus or MP3 files with tags and cover art.

**Architecture:** A small FastAPI app bound to `127.0.0.1:8787` serves one vanilla `index.html`. Search and playlists come from `ytmusicapi` (no login); Spotify and Apple pages are parsed for track names and matched on YouTube Music. Downloads run through `yt-dlp` (as a library) with the bundled ffmpeg and deno, get tagged with `mutagen`, and are handed to the browser as a file or a ZIP from an in-memory job queue.

**Tech Stack:** Python ≥ 3.10, FastAPI, uvicorn, yt-dlp[default], ytmusicapi, mutagen, Pillow, imageio-ffmpeg, deno (PyPI), httpx + certifi, pytest. Frontend: plain HTML/CSS/JS.

**Spec:** `docs/superpowers/specs/2026-09-14-retro-ears-design.md`

## Global Constraints

- Working directory for every command: `/Users/kushalsharma/Desktop/retro-ears`. Use `.venv/bin/python` and `.venv/bin/pytest` (the venv already exists with all packages installed).
- Python ≥ 3.10 must keep working (yt-dlp has deprecated 3.10; README recommends 3.11+). Every module starts with `from __future__ import annotations`.
- Server binds `127.0.0.1:8787` only. Requests whose `Host` header is not `127.0.0.1:8787` or `localhost:8787` get 403.
- All HTTP fetches in our code use `httpx` with `verify=certifi.where()` — never `urllib` (python.org macOS Python has no CA certificates).
- Formats are exactly `m4a`, `opus`, `mp3`. yt-dlp format strings, verbatim from spec §5.5:
  - M4A: `141/140/bestaudio[ext=m4a]` with Premium, `140/bestaudio[ext=m4a]` without
  - Opus: `774/251/bestaudio[acodec=opus]` with Premium, `251/bestaudio[acodec=opus]` without
  - MP3 320: `774/141/251/140/bestaudio` with Premium, `251/140/bestaudio` without
- Premium ids (141, 774) are used only when a cookie source is set. If a download with a cookie source fails for any reason, retry once without cookies.
- Cookie values are never stored, logged or returned. Settings store only the source: `off` | `firefox` | `safari` | `chrome` | `file:<path>`.
- Downloaded file names: `Artist - Title.ext`, sanitized, max 150 chars. ZIP layout: `<name>/Artist - Title.ext`, `ZIP_STORED`.
- Cover art: YouTube Music thumbnail URL rewritten to `=w600-h600`; saved as baseline JPEG ≤ 600 px.
- Job worker pool: 3. Finished jobs older than 1 hour are deleted when a new job starts; all job folders are deleted on app start.
- Frontend is one `static/index.html` with inline CSS/JS, no build step, no external scripts or fonts. User data goes into the DOM via `textContent` only.
- User-facing error copy is taken verbatim from spec §6.
- Offline tests run by default (`.venv/bin/pytest`); network tests are marked `live` and run with `.venv/bin/pytest -m live`.
- Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01MQz45mnyMgWrdhLLmWDvqD
  ```

## File Map

| File | Responsibility |
|---|---|
| `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `.gitignore` | Dependencies and test config |
| `models.py` | `Track`, `PlaylistInfo`, user-facing error classes |
| `tags.py` | Fetch cover art → baseline JPEG; write tags for m4a/opus/mp3 |
| `download.py` | yt-dlp options, format strings, Premium fallback, quality label, safe file names, `fetch()` |
| `settings.py` | Premium cookie source: validate, load, save |
| `ytmusic.py` | Song search, playlist search, playlist tracks, single song, Spotify/Apple track matching |
| `links.py` | Classify pasted text; parse Spotify embed and Apple pages; `resolve()` used by the search route |
| `jobs.py` | In-memory jobs on a thread pool, ZIP building, cleanup |
| `app.py` | FastAPI routes, Host check, error mapping, `main()` |
| `static/index.html` | The whole UI |
| `run.sh`, `run.ps1`, `README.md` | Launchers and docs |
| `tests/` | `conftest.py`, one test file per module, `test_live.py` |

---

### Task 1: Project scaffold, models and tag writing

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `.gitignore`, `models.py`, `tags.py`
- Test: `tests/conftest.py`, `tests/test_tags.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `models.Track(title: str, artist: str, album: str | None = None, duration_s: int | None = None, art_url: str | None = None, video_id: str | None = None)` (dataclass)
  - `models.PlaylistInfo(id: str | None, name: str, art_url: str | None = None, count: int | None = None, tracks: list[Track] = [], note: str | None = None)` (dataclass)
  - `models.RetroError`, and subclasses `NotSupported`, `NotFound`, `ParseChanged`, `Offline`
  - `tags.to_baseline_jpeg(data: bytes, size: int = 600) -> bytes`
  - `tags.fetch_art(url: str | None) -> bytes | None`
  - `tags.write_tags(path: Path, track: Track, art: bytes | None) -> None` (raises `ValueError` for other extensions)
  - Fixtures `silent_file(ext, name="silent") -> Path` and `jpeg_bytes(size=(800, 800), progressive=True) -> bytes`

- [ ] **Step 1: Write config files**

`requirements.txt`:
```
fastapi>=0.115
uvicorn[standard]>=0.30
yt-dlp[default]>=2026.8.19
ytmusicapi>=1.12
mutagen>=1.48
pillow>=11.0
imageio-ffmpeg>=0.6
deno>=2.9
httpx>=0.28
certifi>=2024.2.2
```

`requirements-dev.txt`:
```
-r requirements.txt
pytest>=8.0
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests
pythonpath = .
addopts = -m "not live"
markers =
    live: needs the internet; run with -m live
```

`.gitignore`:
```
.venv/
__pycache__/
.pytest_cache/
.DS_Store
cookies*.txt
*.cookies.txt
```

- [ ] **Step 2: Write `models.py`**

```python
"""Shared data shapes and user-facing errors."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Track:
    title: str
    artist: str
    album: str | None = None
    duration_s: int | None = None
    art_url: str | None = None
    video_id: str | None = None  # None for Spotify/Apple tracks until matched


@dataclass
class PlaylistInfo:
    id: str | None
    name: str
    art_url: str | None = None
    count: int | None = None
    tracks: list[Track] = field(default_factory=list)
    note: str | None = None


class RetroError(Exception):
    """An error whose message is safe to show to the user."""


class NotSupported(RetroError):
    pass


class NotFound(RetroError):
    pass


class ParseChanged(RetroError):
    pass


class Offline(RetroError):
    pass
```

- [ ] **Step 3: Write `tests/conftest.py`**

```python
import io
import subprocess

import imageio_ffmpeg
import pytest
from PIL import Image

CODEC_ARGS = {
    "m4a": ["-c:a", "aac", "-b:a", "128k"],
    "opus": ["-c:a", "libopus", "-b:a", "96k"],
    "mp3": ["-c:a", "libmp3lame", "-b:a", "128k"],
}


@pytest.fixture
def silent_file(tmp_path):
    """Make a 1-second silent audio file with the bundled ffmpeg."""

    def make(ext, name="silent"):
        path = tmp_path / f"{name}.{ext}"
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "1",
                *CODEC_ARGS[ext], str(path),
            ],
            check=True,
        )
        return path

    return make


@pytest.fixture
def jpeg_bytes():
    def make(size=(800, 800), progressive=True):
        buffer = io.BytesIO()
        Image.new("RGB", size, (200, 60, 40)).save(buffer, "JPEG", progressive=progressive)
        return buffer.getvalue()

    return make
```

- [ ] **Step 4: Write the failing tests `tests/test_tags.py`**

```python
import base64
import io

import httpx
import pytest
from mutagen.flac import Picture
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from PIL import Image

import tags
from models import Track

TRACK = Track(title="Café Song", artist="Some Artist", album="Some Album", duration_s=1, video_id="abc123def45")


def is_baseline(data: bytes) -> bool:
    return b"\xff\xc0" in data and b"\xff\xc2" not in data


def test_to_baseline_jpeg_converts_progressive_and_resizes(jpeg_bytes):
    out = tags.to_baseline_jpeg(jpeg_bytes(size=(1200, 1200), progressive=True))
    image = Image.open(io.BytesIO(out))
    assert image.format == "JPEG"
    assert image.size == (600, 600)
    assert is_baseline(out)


def test_to_baseline_jpeg_accepts_png_with_alpha():
    buffer = io.BytesIO()
    Image.new("RGBA", (100, 100), (0, 0, 0, 0)).save(buffer, "PNG")
    out = tags.to_baseline_jpeg(buffer.getvalue())
    image = Image.open(io.BytesIO(out))
    assert image.mode == "RGB"
    assert image.size == (100, 100)


def test_fetch_art_without_url_returns_none():
    assert tags.fetch_art(None) is None


def test_fetch_art_network_error_returns_none(monkeypatch):
    def boom(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(tags.httpx, "get", boom)
    assert tags.fetch_art("https://example.com/cover.jpg") is None


def test_fetch_art_non_image_returns_none(monkeypatch):
    response = httpx.Response(200, content=b"not an image", request=httpx.Request("GET", "https://x"))
    monkeypatch.setattr(tags.httpx, "get", lambda *args, **kwargs: response)
    assert tags.fetch_art("https://x") is None


def test_fetch_art_returns_baseline_jpeg(monkeypatch, jpeg_bytes):
    response = httpx.Response(200, content=jpeg_bytes(), request=httpx.Request("GET", "https://x"))
    monkeypatch.setattr(tags.httpx, "get", lambda *args, **kwargs: response)
    assert is_baseline(tags.fetch_art("https://x"))


def test_m4a_tags_round_trip(silent_file, jpeg_bytes):
    path = silent_file("m4a")
    art = tags.to_baseline_jpeg(jpeg_bytes())
    tags.write_tags(path, TRACK, art)
    audio = MP4(path)
    assert audio["\xa9nam"] == ["Café Song"]
    assert audio["\xa9ART"] == ["Some Artist"]
    assert audio["\xa9alb"] == ["Some Album"]
    assert bytes(audio["covr"][0]) == art


def test_opus_tags_round_trip(silent_file, jpeg_bytes):
    path = silent_file("opus")
    art = tags.to_baseline_jpeg(jpeg_bytes())
    tags.write_tags(path, TRACK, art)
    audio = OggOpus(path)
    assert audio["title"] == ["Café Song"]
    assert audio["artist"] == ["Some Artist"]
    assert audio["album"] == ["Some Album"]
    picture = Picture(base64.b64decode(audio["metadata_block_picture"][0]))
    assert picture.data == art
    assert picture.type == 3
    assert picture.mime == "image/jpeg"


def test_mp3_tags_round_trip_as_id3v23(silent_file, jpeg_bytes):
    path = silent_file("mp3")
    art = tags.to_baseline_jpeg(jpeg_bytes())
    tags.write_tags(path, TRACK, art)
    audio = ID3(path)
    assert audio.version == (2, 3, 0)
    assert audio["TIT2"].text == ["Café Song"]
    assert audio["TPE1"].text == ["Some Artist"]
    assert audio["TALB"].text == ["Some Album"]
    assert audio.getall("APIC")[0].data == art


def test_write_tags_skips_missing_album_and_art(silent_file):
    path = silent_file("m4a")
    tags.write_tags(path, Track(title="T", artist="A"), None)
    audio = MP4(path)
    assert audio["\xa9nam"] == ["T"]
    assert "\xa9alb" not in audio.tags
    assert "covr" not in audio.tags


def test_write_tags_rejects_unknown_extension(tmp_path):
    path = tmp_path / "song.wav"
    path.write_bytes(b"")
    with pytest.raises(ValueError):
        tags.write_tags(path, TRACK, None)
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_tags.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'tags'`

- [ ] **Step 6: Write `tags.py`**

```python
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
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_tags.py -v`
Expected: 11 passed

- [ ] **Step 8: Commit**

```bash
git add requirements.txt requirements-dev.txt pytest.ini .gitignore models.py tags.py tests/conftest.py tests/test_tags.py
git commit -m "feat: add models and cover art + tag writing for m4a, opus, mp3"
```

---

### Task 2: Downloading with yt-dlp

**Files:**
- Create: `download.py`
- Test: `tests/test_download.py`, `tests/test_live.py`

**Interfaces:**
- Consumes: `models.Track`, `models.RetroError`, `tags.fetch_art`, `tags.write_tags`
- Produces:
  - `download.FORMATS = ("m4a", "opus", "mp3")`
  - `download.Result(path: Path, quality: str)` (dataclass)
  - `download.format_string(fmt: str, premium: bool) -> str`
  - `download.postprocessor(fmt: str) -> dict`
  - `download.cookie_opts(cookie_source: str) -> dict`
  - `download.deno_path() -> str | None`
  - `download.build_opts(fmt: str, outdir: Path, cookie_source: str) -> dict`
  - `download.quality_label(fmt: str, acodec: str | None, abr: float | None) -> str`
  - `download.safe_filename(name: str, max_len: int = 150) -> str`
  - `download.unique_path(directory: Path, stem: str, ext: str) -> Path`
  - `download.friendly_error(message: str) -> str`
  - `download.fetch(track: Track, fmt: str, workdir: Path, cookie_source: str = "off") -> Result` (raises `RetroError`)

- [ ] **Step 1: Write the failing tests `tests/test_download.py`**

```python
import shutil
from pathlib import Path

import pytest
import yt_dlp
from mutagen.mp4 import MP4

import download
import tags
from models import RetroError, Track

TRACK = Track(title="Song", artist="Artist", album="Album", duration_s=1, art_url="https://art.example/cover", video_id="abc123def45")


@pytest.mark.parametrize(
    "fmt,premium,expected",
    [
        ("m4a", False, "140/bestaudio[ext=m4a]"),
        ("m4a", True, "141/140/bestaudio[ext=m4a]"),
        ("opus", False, "251/bestaudio[acodec=opus]"),
        ("opus", True, "774/251/bestaudio[acodec=opus]"),
        ("mp3", False, "251/140/bestaudio"),
        ("mp3", True, "774/141/251/140/bestaudio"),
    ],
)
def test_format_string(fmt, premium, expected):
    assert download.format_string(fmt, premium) == expected


def test_postprocessor_copies_m4a_and_opus_streams():
    assert download.postprocessor("m4a") == {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}
    assert download.postprocessor("opus") == {"key": "FFmpegExtractAudio", "preferredcodec": "opus"}


def test_postprocessor_mp3_is_320():
    assert download.postprocessor("mp3") == {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"}


def test_cookie_opts():
    assert download.cookie_opts("off") == {}
    assert download.cookie_opts("") == {}
    assert download.cookie_opts("chrome") == {"cookiesfrombrowser": ("chrome", None, None, None)}
    assert download.cookie_opts("file:/tmp/cookies.txt") == {"cookiefile": "/tmp/cookies.txt"}


def test_build_opts_without_premium(tmp_path):
    opts = download.build_opts("opus", tmp_path, "off")
    assert opts["format"] == "251/bestaudio[acodec=opus]"
    assert opts["outtmpl"] == str(tmp_path / "%(id)s.%(ext)s")
    assert opts["postprocessors"] == [download.postprocessor("opus")]
    assert opts["noplaylist"] is True
    assert Path(opts["ffmpeg_location"]).exists()
    assert "cookiesfrombrowser" not in opts and "cookiefile" not in opts


def test_build_opts_with_premium(tmp_path):
    opts = download.build_opts("m4a", tmp_path, "firefox")
    assert opts["format"] == "141/140/bestaudio[ext=m4a]"
    assert opts["cookiesfrombrowser"] == ("firefox", None, None, None)


def test_deno_is_found_in_the_virtualenv(tmp_path):
    assert download.deno_path() is not None
    assert download.build_opts("m4a", tmp_path, "off")["js_runtimes"] == {"deno": {"path": download.deno_path()}}


@pytest.mark.parametrize(
    "fmt,acodec,abr,label",
    [
        ("m4a", "mp4a.40.2", 129.548, "AAC 130"),
        ("m4a", "mp4a.40.2", 255.9, "AAC 256"),
        ("opus", "opus", 132.978, "Opus 133"),
        ("mp3", "opus", 132.978, "MP3 320 (from Opus 133)"),
        ("opus", None, None, "Audio ?"),
    ],
)
def test_quality_label(fmt, acodec, abr, label):
    assert download.quality_label(fmt, acodec, abr) == label


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('AC/DC - Back: In "Black"?', "ACDC - Back In Black"),
        ("  spaced   out.. ", "spaced out"),
        ("CON", "_CON"),
        ("nul.txt", "_nul.txt"),
        ("", "track"),
        ("\x00\x1f", "track"),
    ],
)
def test_safe_filename(raw, expected):
    assert download.safe_filename(raw) == expected


def test_safe_filename_caps_length():
    assert len(download.safe_filename("a" * 300)) == 150


def test_unique_path_adds_counter(tmp_path):
    (tmp_path / "Artist - Song.m4a").write_bytes(b"")
    (tmp_path / "Artist - Song (2).m4a").write_bytes(b"")
    assert download.unique_path(tmp_path, "Artist - Song", "m4a") == tmp_path / "Artist - Song (3).m4a"


@pytest.mark.parametrize(
    "message,expected",
    [
        ("ERROR: [youtube] abc: Sign in to confirm your age. This video may be inappropriate for some users.", "Age-restricted — needs a Premium login"),
        ("ERROR: [youtube] abc: Video unavailable", "Unavailable on YouTube"),
        ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access to this video", "Unavailable on YouTube"),
        ("ERROR: [youtube] abc: Requested format is not available. Use --list-formats", "No audio stream in this format"),
        ("ERROR: [youtube] abc: Unable to download API page: timed out", "Network error — check your connection"),
        ("ERROR: [youtube] abc: Something new broke", "Something new broke"),
    ],
)
def test_friendly_error(message, expected):
    assert download.friendly_error(message) == expected


def make_fake_extract(source: Path, ext: str, calls: list, fail_with_cookies: bool = False):
    def fake_extract(opts, url):
        calls.append((opts, url))
        if fail_with_cookies and ("cookiesfrombrowser" in opts or "cookiefile" in opts):
            raise RuntimeError("could not read cookies")
        out = Path(opts["outtmpl"]).parent / f"abc123def45.{ext}"
        shutil.copy(source, out)
        return {"acodec": "mp4a.40.2", "abr": 129.548, "requested_downloads": [{"filepath": str(out)}]}

    return fake_extract


def test_fetch_tags_renames_and_labels(tmp_path, monkeypatch, silent_file, jpeg_bytes):
    calls = []
    monkeypatch.setattr(download, "_extract", make_fake_extract(silent_file("m4a"), "m4a", calls))
    monkeypatch.setattr(tags, "fetch_art", lambda url: tags.to_baseline_jpeg(jpeg_bytes()))
    workdir = tmp_path / "job"

    result = download.fetch(TRACK, "m4a", workdir)

    assert result.path == workdir / "Artist - Song.m4a"
    assert result.quality == "AAC 130"
    assert calls[0][1] == "https://music.youtube.com/watch?v=abc123def45"
    audio = MP4(result.path)
    assert audio["\xa9nam"] == ["Song"]
    assert "covr" in audio.tags
    assert [p.name for p in workdir.iterdir()] == ["Artist - Song.m4a"]  # temp folder removed


def test_fetch_same_song_twice_gets_unique_names(tmp_path, monkeypatch, silent_file):
    monkeypatch.setattr(download, "_extract", make_fake_extract(silent_file("m4a"), "m4a", []))
    monkeypatch.setattr(tags, "fetch_art", lambda url: None)
    workdir = tmp_path / "job"
    first = download.fetch(TRACK, "m4a", workdir)
    second = download.fetch(TRACK, "m4a", workdir)
    assert first.path.name == "Artist - Song.m4a"
    assert second.path.name == "Artist - Song (2).m4a"


def test_fetch_falls_back_to_free_quality_when_login_fails(tmp_path, monkeypatch, silent_file):
    calls = []
    monkeypatch.setattr(download, "_extract", make_fake_extract(silent_file("m4a"), "m4a", calls, fail_with_cookies=True))
    monkeypatch.setattr(tags, "fetch_art", lambda url: None)

    result = download.fetch(TRACK, "m4a", tmp_path / "job", cookie_source="firefox")

    assert [opts["format"] for opts, _ in calls] == ["141/140/bestaudio[ext=m4a]", "140/bestaudio[ext=m4a]"]
    assert "cookiesfrombrowser" not in calls[1][0]
    assert result.path.exists()


def test_fetch_error_is_friendly_and_cleans_up(tmp_path, monkeypatch):
    def fake_extract(opts, url):
        raise yt_dlp.utils.DownloadError("ERROR: [youtube] abc123def45: Video unavailable")

    monkeypatch.setattr(download, "_extract", fake_extract)
    workdir = tmp_path / "job"
    with pytest.raises(RetroError, match="Unavailable on YouTube"):
        download.fetch(TRACK, "m4a", workdir)
    assert list(workdir.iterdir()) == []


def test_fetch_requires_video_id(tmp_path):
    with pytest.raises(RetroError):
        download.fetch(Track(title="Song", artist="Artist"), "m4a", tmp_path)


def test_fetch_rejects_unknown_format(tmp_path):
    with pytest.raises(ValueError):
        download.fetch(TRACK, "wav", tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_download.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'download'`

- [ ] **Step 3: Write `download.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_download.py -v`
Expected: 37 passed

- [ ] **Step 5: Write the live download test `tests/test_live.py`**

```python
"""Network tests. Run with: .venv/bin/pytest -m live -s
Set RETRO_COOKIES=<firefox|safari|chrome|file:/path> to test with a Premium login."""
import os

import mutagen
import pytest

import download
from models import Track

pytestmark = pytest.mark.live

COOKIES = os.environ.get("RETRO_COOKIES", "off")
SONG = Track(
    title="Blinding Lights",
    artist="The Weeknd",
    album="Blinding Lights",
    duration_s=202,
    art_url="https://i.ytimg.com/vi/J7p4bzqLvCw/hqdefault.jpg",
    video_id="J7p4bzqLvCw",
)
LABEL_PREFIX = {"m4a": "AAC", "opus": "Opus", "mp3": "MP3 320"}


@pytest.mark.parametrize("fmt", download.FORMATS)
def test_download_real_song(tmp_path, fmt):
    result = download.fetch(SONG, fmt, tmp_path, cookie_source=COOKIES)
    print(f"\n{fmt} (cookies={COOKIES}): {result.quality}")
    assert result.path.suffix == f".{fmt}"
    assert result.path.stat().st_size > 1_000_000
    assert result.quality.startswith(LABEL_PREFIX[fmt])
    audio = mutagen.File(result.path, easy=True)
    assert audio["title"] == ["Blinding Lights"]
    assert audio["artist"] == ["The Weeknd"]
```

- [ ] **Step 6: Run the live test without Premium**

Run: `.venv/bin/pytest -m live tests/test_live.py -s -v`
Expected: 3 passed; printed labels `AAC 130`, `Opus 1xx`, `MP3 320 (from Opus 1xx)`

- [ ] **Step 7: Premium check with Kushal's account**

Ask Kushal which browser he is signed in to YouTube Premium with (on macOS, Chrome triggers a Keychain prompt he must allow; Safari needs Full Disk Access for the terminal). Then run:

Run: `RETRO_COOKIES=<browser> .venv/bin/pytest -m live tests/test_live.py -s -v`
Expected: 3 passed. Record the printed labels. `AAC 256` / `Opus 256` means Premium formats work; `AAC 130` / `Opus 1xx` means YouTube did not serve them and the fallback worked. Write the outcome into the spec §3 table row for Premium audio (replace "not yet verified with a real account" with the result and date).

- [ ] **Step 8: Commit**

```bash
git add download.py tests/test_download.py tests/test_live.py docs/superpowers/specs/2026-09-14-retro-ears-design.md
git commit -m "feat: download songs with yt-dlp in m4a, opus or mp3 with Premium fallback"
```

---

### Task 3: Premium settings

**Files:**
- Create: `settings.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `settings.DEFAULTS = {"cookie_source": "off"}`
  - `settings.settings_path() -> Path`
  - `settings.validate_cookie_source(value: str, platform: str | None = None) -> str` (raises `ValueError`)
  - `settings.load(path: Path | None = None) -> dict`
  - `settings.save(values: dict, path: Path | None = None) -> dict`

- [ ] **Step 1: Write the failing tests `tests/test_settings.py`**

```python
import json
from pathlib import Path

import pytest

import settings


def test_load_returns_defaults_when_file_missing(tmp_path):
    assert settings.load(tmp_path / "settings.json") == {"cookie_source": "off"}


def test_load_ignores_corrupt_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", "utf-8")
    assert settings.load(path) == {"cookie_source": "off"}


def test_load_ignores_unknown_keys(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"cookie_source": "firefox", "other": 1}), "utf-8")
    assert settings.load(path) == {"cookie_source": "firefox"}


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "nested" / "settings.json"
    assert settings.save({"cookie_source": "firefox"}, path) == {"cookie_source": "firefox"}
    assert settings.load(path) == {"cookie_source": "firefox"}
    assert json.loads(path.read_text("utf-8")) == {"cookie_source": "firefox"}


def test_save_rejects_unknown_source(tmp_path):
    with pytest.raises(ValueError, match="Unknown login source"):
        settings.save({"cookie_source": "netscape"}, tmp_path / "settings.json")


@pytest.mark.parametrize(
    "platform,source,allowed",
    [
        ("darwin", "safari", True),
        ("darwin", "chrome", True),
        ("darwin", "firefox", True),
        ("win32", "firefox", True),
        ("win32", "chrome", False),
        ("win32", "safari", False),
        ("linux", "safari", False),
    ],
)
def test_browser_sources_per_platform(platform, source, allowed):
    if allowed:
        assert settings.validate_cookie_source(source, platform) == source
    else:
        with pytest.raises(ValueError):
            settings.validate_cookie_source(source, platform)


def test_cookie_file_must_exist(tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    with pytest.raises(ValueError, match="cookies.txt file not found"):
        settings.validate_cookie_source(f"file:{cookie_file}")
    with pytest.raises(ValueError, match="cookies.txt file not found"):
        settings.validate_cookie_source("file:")
    cookie_file.write_text("# Netscape HTTP Cookie File\n", "utf-8")
    assert settings.validate_cookie_source(f"file:{cookie_file}") == f"file:{cookie_file}"


def test_settings_path_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(settings.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert settings.settings_path() == tmp_path / "retro-ears" / "settings.json"


def test_settings_path_on_macos(monkeypatch):
    monkeypatch.setattr(settings.sys, "platform", "darwin")
    assert settings.settings_path() == Path.home() / "Library" / "Application Support" / "retro-ears" / "settings.json"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_settings.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'settings'`

- [ ] **Step 3: Write `settings.py`**

```python
"""The one setting retro-ears keeps: where to read a YouTube Premium login from."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEFAULTS = {"cookie_source": "off"}
BROWSERS = ("firefox", "safari", "chrome")


def settings_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "retro-ears" / "settings.json"


def validate_cookie_source(value: str, platform: str | None = None) -> str:
    platform = platform or sys.platform
    if value == "off":
        return value
    if value in BROWSERS:
        if value == "safari" and platform != "darwin":
            raise ValueError("Safari is only available on macOS")
        if value == "chrome" and platform == "win32":
            raise ValueError("Chrome logins can't be read on Windows — use Firefox or a cookies.txt file")
        return value
    if value.startswith("file:"):
        cookie_file = value[len("file:"):].strip()
        if not cookie_file or not Path(cookie_file).is_file():
            raise ValueError("cookies.txt file not found")
        return f"file:{cookie_file}"
    raise ValueError("Unknown login source")


def load(path: Path | None = None) -> dict:
    path = path or settings_path()
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULTS)
    if not isinstance(data, dict):
        return dict(DEFAULTS)
    return {**DEFAULTS, **{key: value for key, value in data.items() if key in DEFAULTS}}


def save(values: dict, path: Path | None = None) -> dict:
    path = path or settings_path()
    merged = {**load(path), "cookie_source": validate_cookie_source(values.get("cookie_source", "off"))}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2), "utf-8")
    return merged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_settings.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add settings.py tests/test_settings.py
git commit -m "feat: store the optional Premium login source"
```

---

### Task 4: YouTube Music search, playlists and matching

**Files:**
- Create: `ytmusic.py`
- Test: `tests/test_ytmusic.py`; Modify: `tests/test_live.py` (append)

**Interfaces:**
- Consumes: `models.Track`, `models.PlaylistInfo`, `models.NotFound`, `models.Offline`
- Produces:
  - `ytmusic.client() -> YTMusic` (cached)
  - `ytmusic.big_art(url: str | None, size: int = 600) -> str | None`
  - `ytmusic.song_to_track(item: dict) -> Track`
  - `ytmusic.search_songs(query: str, limit: int = 20) -> list[Track]`
  - `ytmusic.search_playlists(query: str, limit: int = 20) -> list[PlaylistInfo]`
  - `ytmusic.get_playlist(playlist_id: str) -> PlaylistInfo` (raises `NotFound`)
  - `ytmusic.get_song(video_id: str) -> Track` (raises `NotFound`)
  - `ytmusic.pick_match(results: list[dict], duration_s: int | None) -> dict`
  - `ytmusic.match(track: Track) -> Track` (raises `NotFound`)
  - All network failures raise `Offline("Couldn't reach YouTube Music. Check your connection.")`

- [ ] **Step 1: Write the failing tests `tests/test_ytmusic.py`**

```python
import pytest
import requests
from ytmusicapi.exceptions import YTMusicServerError

import ytmusic
from models import NotFound, Offline, Track


def song_item(title="Neon Night", artists=("Glass Arcade",), album="Midnight Drive", seconds=200, video_id="vid00000001"):
    return {
        "title": title,
        "artists": [{"name": name, "id": "x"} for name in artists],
        "album": {"name": album, "id": "y"} if album else None,
        "duration_seconds": seconds,
        "videoId": video_id,
        "thumbnails": [
            {"url": "https://yt3.googleusercontent.com/abc=w60-h60-l90-rj", "width": 60},
            {"url": "https://yt3.googleusercontent.com/abc=w120-h120-l90-rj", "width": 120},
        ],
    }


def playlist_item(title, browse_id, count):
    return {
        "title": title,
        "browseId": browse_id,
        "itemCount": count,
        "author": "Someone",
        "thumbnails": [{"url": "https://yt3.googleusercontent.com/pl=w544-h544-l90-rj", "width": 544}],
    }


class FakeYT:
    def __init__(self, search=None, playlist=None, song=None, error=None):
        self.search_results = search or {}
        self.playlist = playlist
        self.song = song
        self.error = error
        self.searches = []

    def search(self, query, filter=None, limit=20):
        self.searches.append((query, filter))
        if self.error:
            raise self.error
        return self.search_results.get(filter, [])

    def get_playlist(self, playlist_id, limit=100):
        if isinstance(self.playlist, Exception):
            raise self.playlist
        return self.playlist

    def get_song(self, video_id):
        if isinstance(self.song, Exception):
            raise self.song
        return self.song


@pytest.fixture
def use_fake(monkeypatch):
    def install(fake):
        monkeypatch.setattr(ytmusic, "client", lambda: fake)
        return fake

    return install


def test_big_art_rewrites_size():
    assert ytmusic.big_art("https://yt3.googleusercontent.com/abc=w120-h120-l90-rj") == "https://yt3.googleusercontent.com/abc=w600-h600-l90-rj"
    assert ytmusic.big_art("https://i.ytimg.com/vi/x/hqdefault.jpg") == "https://i.ytimg.com/vi/x/hqdefault.jpg"
    assert ytmusic.big_art(None) is None


def test_search_songs_maps_results(use_fake):
    fake = use_fake(FakeYT(search={"songs": [song_item(artists=("Glass Arcade", "Low Tide")), {**song_item(), "videoId": None}]}))
    songs = ytmusic.search_songs("neon night")
    assert songs == [
        Track(
            title="Neon Night",
            artist="Glass Arcade, Low Tide",
            album="Midnight Drive",
            duration_s=200,
            art_url="https://yt3.googleusercontent.com/abc=w600-h600-l90-rj",
            video_id="vid00000001",
        )
    ]
    assert fake.searches == [("neon night", "songs")]


def test_search_playlists_puts_featured_first_and_dedupes(use_fake):
    use_fake(FakeYT(search={
        "featured_playlists": [playlist_item("Official Mix", "VLRDCLAK5uy_a", 100)],
        "community_playlists": [playlist_item("Official Mix", "VLRDCLAK5uy_a", None), playlist_item("Fan Mix", "VLPLfan", None)],
    }))
    playlists = ytmusic.search_playlists("mix")
    assert [(p.id, p.name, p.count) for p in playlists] == [("VLRDCLAK5uy_a", "Official Mix", 100), ("VLPLfan", "Fan Mix", None)]
    assert playlists[0].art_url == "https://yt3.googleusercontent.com/pl=w600-h600-l90-rj"


def test_get_playlist_maps_tracks_and_skips_unavailable(use_fake):
    use_fake(FakeYT(playlist={
        "id": "RDCLAK5uy_a",
        "title": "Official Mix",
        "thumbnails": [{"url": "https://yt3.googleusercontent.com/pl=w544-h544-l90-rj"}],
        "tracks": [song_item(album=None), {**song_item(title="Gone"), "videoId": None}],
    }))
    playlist = ytmusic.get_playlist("VLRDCLAK5uy_a")
    assert playlist.id == "RDCLAK5uy_a"
    assert playlist.name == "Official Mix"
    assert playlist.count == 1
    assert [t.title for t in playlist.tracks] == ["Neon Night"]
    assert playlist.tracks[0].album is None


@pytest.mark.parametrize("error", [KeyError("contents"), YTMusicServerError("404")])
def test_get_playlist_missing_raises_not_found(use_fake, error):
    use_fake(FakeYT(playlist=error))
    with pytest.raises(NotFound, match="This playlist is private or doesn't exist"):
        ytmusic.get_playlist("PLmissing")


def test_get_song_maps_video_details(use_fake):
    use_fake(FakeYT(song={"videoDetails": {
        "title": "Neon Night",
        "author": "Glass Arcade - Topic",
        "lengthSeconds": "200",
        "thumbnail": {"thumbnails": [{"url": "https://yt3.googleusercontent.com/s=w544-h544-l90-rj"}]},
    }}))
    assert ytmusic.get_song("vid00000001") == Track(
        title="Neon Night",
        artist="Glass Arcade",
        album=None,
        duration_s=200,
        art_url="https://yt3.googleusercontent.com/s=w600-h600-l90-rj",
        video_id="vid00000001",
    )


def test_get_song_missing_raises_not_found(use_fake):
    use_fake(FakeYT(song={"playabilityStatus": {"status": "ERROR"}}))
    with pytest.raises(NotFound):
        ytmusic.get_song("nope")


def test_pick_match_prefers_close_duration():
    results = [song_item(video_id="far", seconds=400), song_item(video_id="close", seconds=207)]
    assert ytmusic.pick_match(results, 200)["videoId"] == "close"


def test_pick_match_falls_back_to_first():
    results = [song_item(video_id="first", seconds=400), song_item(video_id="second", seconds=500)]
    assert ytmusic.pick_match(results, 200)["videoId"] == "first"
    assert ytmusic.pick_match(results, None)["videoId"] == "first"


def test_match_keeps_tracks_that_already_have_a_video(use_fake):
    fake = use_fake(FakeYT())
    track = Track(title="A", artist="B", video_id="already")
    assert ytmusic.match(track) is track
    assert fake.searches == []


def test_match_fills_video_album_and_art(use_fake):
    fake = use_fake(FakeYT(search={"songs": [song_item(video_id="matched", seconds=198)]}))
    matched = ytmusic.match(Track(title="Neon Night", artist="Glass Arcade", duration_s=200))
    assert matched.video_id == "matched"
    assert matched.title == "Neon Night" and matched.artist == "Glass Arcade"
    assert matched.album == "Midnight Drive"
    assert matched.art_url == "https://yt3.googleusercontent.com/abc=w600-h600-l90-rj"
    assert fake.searches == [("Neon Night Glass Arcade", "songs")]


def test_match_without_results_raises_not_found(use_fake):
    use_fake(FakeYT(search={"songs": []}))
    with pytest.raises(NotFound, match="Not found on YouTube Music"):
        ytmusic.match(Track(title="Nothing", artist="Nobody"))


def test_network_errors_raise_offline(use_fake):
    use_fake(FakeYT(error=requests.ConnectionError("down")))
    with pytest.raises(Offline, match="Couldn't reach YouTube Music. Check your connection."):
        ytmusic.search_songs("anything")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_ytmusic.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'ytmusic'`

- [ ] **Step 3: Write `ytmusic.py`**

```python
"""YouTube Music search, playlists and song matching. No login needed."""
from __future__ import annotations

import re
from dataclasses import replace
from functools import lru_cache

import requests
from ytmusicapi import YTMusic
from ytmusicapi.exceptions import YTMusicServerError

from models import NotFound, Offline, PlaylistInfo, Track

MATCH_TOLERANCE_S = 10
OFFLINE_MESSAGE = "Couldn't reach YouTube Music. Check your connection."
PLAYLIST_MISSING = "This playlist is private or doesn't exist"


@lru_cache(maxsize=1)
def client() -> YTMusic:
    return YTMusic()


def _call(fn):
    try:
        return fn()
    except requests.RequestException as exc:
        raise Offline(OFFLINE_MESSAGE) from exc


def big_art(url: str | None, size: int = 600) -> str | None:
    if not url:
        return None
    return re.sub(r"=w\d+-h\d+", f"=w{size}-h{size}", url)


def _art(item: dict) -> str | None:
    thumbnails = item.get("thumbnails") or []
    return big_art(thumbnails[-1].get("url")) if thumbnails else None


def _artist(item: dict) -> str:
    names = [artist["name"] for artist in item.get("artists") or [] if artist.get("name")]
    return ", ".join(names) or "Unknown Artist"


def song_to_track(item: dict) -> Track:
    album = item.get("album") or {}
    return Track(
        title=item.get("title") or "Unknown Title",
        artist=_artist(item),
        album=album.get("name"),
        duration_s=item.get("duration_seconds"),
        art_url=_art(item),
        video_id=item.get("videoId"),
    )


def search_songs(query: str, limit: int = 20) -> list[Track]:
    items = _call(lambda: client().search(query, filter="songs", limit=limit))
    return [song_to_track(item) for item in items if item.get("videoId")][:limit]


def search_playlists(query: str, limit: int = 20) -> list[PlaylistInfo]:
    featured = _call(lambda: client().search(query, filter="featured_playlists", limit=limit))
    community = _call(lambda: client().search(query, filter="community_playlists", limit=limit))
    seen: set[str] = set()
    playlists: list[PlaylistInfo] = []
    for item in [*featured, *community]:
        playlist_id = item.get("browseId")
        if not playlist_id or playlist_id in seen:
            continue
        seen.add(playlist_id)
        playlists.append(PlaylistInfo(id=playlist_id, name=item.get("title") or "Playlist", art_url=_art(item), count=item.get("itemCount")))
    return playlists[:limit]


def get_playlist(playlist_id: str) -> PlaylistInfo:
    try:
        data = _call(lambda: client().get_playlist(playlist_id, limit=None))
    except (KeyError, YTMusicServerError) as exc:  # ytmusicapi raises KeyError when the page has no playlist
        raise NotFound(PLAYLIST_MISSING) from exc
    tracks = [song_to_track(item) for item in data.get("tracks") or [] if item.get("videoId")]
    return PlaylistInfo(
        id=data.get("id") or playlist_id,
        name=data.get("title") or "Playlist",
        art_url=_art(data),
        count=len(tracks),
        tracks=tracks,
    )


def get_song(video_id: str) -> Track:
    try:
        details = _call(lambda: client().get_song(video_id)).get("videoDetails") or {}
    except (KeyError, YTMusicServerError) as exc:
        raise NotFound("This video is unavailable") from exc
    if not details.get("title"):
        raise NotFound("This video is unavailable")
    thumbnails = (details.get("thumbnail") or {}).get("thumbnails") or []
    artist = re.sub(r"\s+-\s+Topic$", "", details.get("author") or "") or "Unknown Artist"
    length = details.get("lengthSeconds")
    return Track(
        title=details["title"],
        artist=artist,
        duration_s=int(length) if length else None,
        art_url=big_art(thumbnails[-1].get("url")) if thumbnails else None,
        video_id=video_id,
    )


def pick_match(results: list[dict], duration_s: int | None) -> dict:
    if duration_s is not None:
        for item in results:
            seconds = item.get("duration_seconds")
            if seconds is not None and abs(seconds - duration_s) <= MATCH_TOLERANCE_S:
                return item
    return results[0]


def match(track: Track) -> Track:
    """Find a YouTube Music song for a Spotify/Apple track (title + artist + duration)."""
    if track.video_id:
        return track
    results = _call(lambda: client().search(f"{track.title} {track.artist}", filter="songs", limit=5))
    results = [item for item in results if item.get("videoId")]
    if not results:
        raise NotFound("Not found on YouTube Music")
    best = pick_match(results, track.duration_s)
    return replace(
        track,
        video_id=best["videoId"],
        album=track.album or (best.get("album") or {}).get("name"),
        art_url=track.art_url or _art(best),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_ytmusic.py -v`
Expected: 14 passed

- [ ] **Step 5: Append live YouTube Music tests to `tests/test_live.py`**

```python
import ytmusic


def test_search_songs_live():
    songs = ytmusic.search_songs("the weeknd blinding lights", limit=5)
    assert songs and all(song.video_id for song in songs)


def test_search_and_open_playlist_live():
    playlists = ytmusic.search_playlists("80s hits", limit=5)
    assert playlists
    playlist = ytmusic.get_playlist(playlists[0].id)
    assert playlist.tracks and all(track.video_id for track in playlist.tracks)


def test_match_live():
    matched = ytmusic.match(Track(title="Blinding Lights", artist="The Weeknd", duration_s=200))
    assert matched.video_id
```

(Put the `import ytmusic` line with the other imports at the top of the file.)

- [ ] **Step 6: Run live tests**

Run: `.venv/bin/pytest -m live tests/test_live.py -v -k "search_songs_live or open_playlist_live or match_live"`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add ytmusic.py tests/test_ytmusic.py tests/test_live.py
git commit -m "feat: search songs and playlists on YouTube Music and match tracks"
```

---

### Task 5: Pasted links (YouTube, Spotify, Apple Music)

**Files:**
- Create: `links.py`
- Test: `tests/test_links.py`; Modify: `tests/test_live.py` (append)

**Interfaces:**
- Consumes: `models.*`, `ytmusic.search_songs`, `ytmusic.search_playlists`, `ytmusic.get_playlist`, `ytmusic.get_song`
- Produces:
  - `links.Route(kind: str, value: str)` (dataclass; kind is `search` | `song` | `youtube_playlist` | `spotify` | `apple`)
  - `links.classify(text: str) -> Route` (raises `NotSupported`)
  - `links.fetch_page(url: str) -> str` (raises `Offline`, `NotFound`)
  - `links.spotify_embed_url(url: str) -> str`
  - `links.parse_spotify(html: str) -> PlaylistInfo` (raises `ParseChanged`)
  - `links.parse_apple(html: str) -> PlaylistInfo` (raises `ParseChanged`)
  - `links.resolve(text: str, tab: str) -> dict` returning one of `{"type": "songs", "songs": list[Track]}`, `{"type": "playlists", "playlists": list[PlaylistInfo]}`, `{"type": "playlist", "playlist": PlaylistInfo}`

- [ ] **Step 1: Write the failing tests `tests/test_links.py`**

```python
import json

import httpx
import pytest

import links
from models import NotFound, NotSupported, Offline, ParseChanged, PlaylistInfo, Track

SPOTIFY_URL = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc"
APPLE_URL = "https://music.apple.com/us/playlist/todays-hits/pl.f4d106fed2bd41149aaacabb233eb5eb"


@pytest.mark.parametrize(
    "text,kind,value",
    [
        ("neon night", "search", "neon night"),
        ("  glass arcade  ", "search", "glass arcade"),
        ("https://www.youtube.com/watch?v=J7p4bzqLvCw", "song", "J7p4bzqLvCw"),
        ("https://youtu.be/J7p4bzqLvCw?si=abc", "song", "J7p4bzqLvCw"),
        ("https://music.youtube.com/watch?v=J7p4bzqLvCw&feature=share", "song", "J7p4bzqLvCw"),
        ("https://m.youtube.com/watch?v=J7p4bzqLvCw", "song", "J7p4bzqLvCw"),
        ("https://www.youtube.com/watch?v=J7p4bzqLvCw&list=RDJ7p4bzqLvCw", "song", "J7p4bzqLvCw"),
        ("https://www.youtube.com/playlist?list=PLabc123", "youtube_playlist", "PLabc123"),
        ("https://music.youtube.com/playlist?list=RDCLAK5uy_abc", "youtube_playlist", "RDCLAK5uy_abc"),
        ("https://www.youtube.com/watch?v=J7p4bzqLvCw&list=PLabc123", "youtube_playlist", "PLabc123"),
        (SPOTIFY_URL, "spotify", SPOTIFY_URL),
        ("https://open.spotify.com/intl-de/album/4yP0hdKOZPNshxUOjY0cZj", "spotify", "https://open.spotify.com/intl-de/album/4yP0hdKOZPNshxUOjY0cZj"),
        (APPLE_URL, "apple", APPLE_URL),
        ("https://music.apple.com/us/album/after-hours/1499378108", "apple", "https://music.apple.com/us/album/after-hours/1499378108"),
    ],
)
def test_classify(text, kind, value):
    assert links.classify(text) == links.Route(kind, value)


@pytest.mark.parametrize(
    "text",
    [
        "https://soundcloud.com/artist/song",
        "https://open.spotify.com/track/7bxaFZ1O3cHkgLKMsdC3xR",
        "https://www.youtube.com/@somechannel",
        "https://example.com",
    ],
)
def test_classify_rejects_unsupported_links(text):
    with pytest.raises(NotSupported, match="Link not supported"):
        links.classify(text)


def test_spotify_embed_url():
    assert links.spotify_embed_url(SPOTIFY_URL) == "https://open.spotify.com/embed/playlist/37i9dQZF1DXcBWIGoYBM5M"
    assert links.spotify_embed_url("https://open.spotify.com/intl-de/album/4yP0hdKOZPNshxUOjY0cZj") == "https://open.spotify.com/embed/album/4yP0hdKOZPNshxUOjY0cZj"


def spotify_html(entity):
    data = {"props": {"pageProps": {"state": {"data": {"entity": entity}}}}}
    return f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></body></html>'


def spotify_row(i):
    return {"title": f"Song {i}", "subtitle": "Glass Arcade, Low Tide", "duration": 201400, "uri": f"spotify:track:{i}"}


def test_parse_spotify_playlist():
    html = spotify_html({
        "type": "playlist",
        "name": "Road Trip",
        "coverArt": {"sources": [{"url": "https://i.scdn.co/image/cover"}]},
        "trackList": [spotify_row(1), spotify_row(2)],
    })
    playlist = links.parse_spotify(html)
    assert playlist.name == "Road Trip"
    assert playlist.art_url == "https://i.scdn.co/image/cover"
    assert playlist.count == 2
    assert playlist.note is None
    assert playlist.tracks[0] == Track(title="Song 1", artist="Glass Arcade, Low Tide", album=None, duration_s=201, art_url=None, video_id=None)


def test_parse_spotify_warns_at_100_tracks():
    html = spotify_html({"type": "playlist", "name": "Big", "trackList": [spotify_row(i) for i in range(100)]})
    assert links.parse_spotify(html).note == "Spotify only shares the first 100 songs — this playlist may have more"


def test_parse_spotify_album_sets_album_name():
    html = spotify_html({"type": "album", "name": "Midnight Drive", "subtitle": "Glass Arcade", "trackList": [{"title": "Intro", "subtitle": "Glass Arcade", "duration": 60000}]})
    playlist = links.parse_spotify(html)
    assert playlist.tracks[0].album == "Midnight Drive"
    assert playlist.tracks[0].artist == "Glass Arcade"


def test_parse_spotify_changed_page():
    with pytest.raises(ParseChanged, match="Couldn't read this playlist — the site may have changed"):
        links.parse_spotify("<html>nothing here</html>")


def apple_html(header, tracks, og_image="https://is1-ssl.mzstatic.com/image/thumb/x/1200x630wp.png?a=1&amp;b=2"):
    data = {"data": [{"data": {"sections": [
        {"itemKind": "containerDetailHeaderLockup", "items": [header]},
        {"itemKind": "trackLockup", "items": tracks},
    ]}}]}
    return (
        f'<html><head><meta property="og:image" content="{og_image}"></head><body>'
        f'<script type="application/json" id="serialized-server-data">{json.dumps(data)}</script></body></html>'
    )


def test_parse_apple_playlist():
    html = apple_html(
        {"id": "playlist-detail-header - pl.abc", "title": "Hits", "subtitleLinks": [{"title": "Apple Music"}]},
        [{"title": "Song A", "artistName": "Artist A", "duration": 213806}, {"title": "Song B", "artistName": "Artist B", "duration": 180000}],
    )
    playlist = links.parse_apple(html)
    assert playlist.name == "Hits"
    assert playlist.art_url == "https://is1-ssl.mzstatic.com/image/thumb/x/1200x630wp.png?a=1&b=2"
    assert playlist.tracks == [
        Track(title="Song A", artist="Artist A", album=None, duration_s=214),
        Track(title="Song B", artist="Artist B", album=None, duration_s=180),
    ]


def test_parse_apple_album_uses_header_artist_and_album():
    html = apple_html(
        {"id": "album-detail-header - 123", "title": "Midnight Drive", "subtitleLinks": [{"title": "Glass Arcade"}]},
        [{"title": "Intro", "duration": 60000}],
    )
    playlist = links.parse_apple(html)
    assert playlist.tracks == [Track(title="Intro", artist="Glass Arcade", album="Midnight Drive", duration_s=60)]


@pytest.mark.parametrize("html", ["<html></html>", apple_html({"id": "playlist-detail-header - x", "title": "Empty"}, [])])
def test_parse_apple_changed_page(html):
    with pytest.raises(ParseChanged):
        links.parse_apple(html)


def test_fetch_page_offline(monkeypatch):
    def boom(*args, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(links.httpx, "get", boom)
    with pytest.raises(Offline):
        links.fetch_page("https://open.spotify.com/embed/playlist/x")


def test_fetch_page_missing(monkeypatch):
    monkeypatch.setattr(links.httpx, "get", lambda *a, **k: httpx.Response(404, request=httpx.Request("GET", "https://x")))
    with pytest.raises(NotFound, match="This playlist is private or doesn't exist"):
        links.fetch_page("https://x")


def test_fetch_page_ok(monkeypatch):
    monkeypatch.setattr(links.httpx, "get", lambda *a, **k: httpx.Response(200, text="<html>ok</html>", request=httpx.Request("GET", "https://x")))
    assert links.fetch_page("https://x") == "<html>ok</html>"


def test_resolve_dispatch(monkeypatch):
    song = Track(title="S", artist="A", video_id="v")
    playlist = PlaylistInfo(id="p", name="P")
    fetched = []
    monkeypatch.setattr(links.ytmusic, "search_songs", lambda q: [song])
    monkeypatch.setattr(links.ytmusic, "search_playlists", lambda q: [playlist])
    monkeypatch.setattr(links.ytmusic, "get_song", lambda video_id: song)
    monkeypatch.setattr(links.ytmusic, "get_playlist", lambda playlist_id: playlist)
    monkeypatch.setattr(links, "fetch_page", lambda url: fetched.append(url) or "html")
    monkeypatch.setattr(links, "parse_spotify", lambda html: playlist)
    monkeypatch.setattr(links, "parse_apple", lambda html: playlist)

    assert links.resolve("neon", "songs") == {"type": "songs", "songs": [song]}
    assert links.resolve("neon", "playlists") == {"type": "playlists", "playlists": [playlist]}
    assert links.resolve("https://youtu.be/J7p4bzqLvCw", "playlists") == {"type": "songs", "songs": [song]}
    assert links.resolve("https://www.youtube.com/playlist?list=PLx", "songs") == {"type": "playlist", "playlist": playlist}
    assert links.resolve(SPOTIFY_URL, "songs") == {"type": "playlist", "playlist": playlist}
    assert links.resolve(APPLE_URL, "songs") == {"type": "playlist", "playlist": playlist}
    assert fetched == ["https://open.spotify.com/embed/playlist/37i9dQZF1DXcBWIGoYBM5M", APPLE_URL]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_links.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'links'`

- [ ] **Step 3: Write `links.py`**

```python
"""Turn whatever the user typed or pasted into search results or a playlist."""
from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import certifi
import httpx

import ytmusic
from models import NotFound, NotSupported, Offline, ParseChanged, PlaylistInfo, Track

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
SPOTIFY_CAP = 100
NOT_SUPPORTED = "Link not supported — paste a YouTube, YouTube Music, Spotify or Apple Music link"
PARSE_CHANGED = "Couldn't read this playlist — the site may have changed"
YOUTUBE_HOSTS = {"youtube.com", "music.youtube.com", "youtu.be"}


@dataclass
class Route:
    kind: str  # search | song | youtube_playlist | spotify | apple
    value: str  # query text, video id, playlist id, or URL


def classify(text: str) -> Route:
    text = text.strip()
    if not re.match(r"^https?://", text, re.IGNORECASE):
        return Route("search", text)
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    for prefix in ("www.", "m."):
        host = host.removeprefix(prefix)
    query = parse_qs(parsed.query)

    if host in YOUTUBE_HOSTS:
        video_id = parsed.path.strip("/").split("/")[0] if host == "youtu.be" else (query.get("v") or [""])[0]
        list_id = (query.get("list") or [""])[0]
        # "RD…" lists next to a video are auto-generated radio mixes: the user meant the song.
        if list_id and not (video_id and list_id.startswith("RD")):
            return Route("youtube_playlist", list_id)
        if video_id:
            return Route("song", video_id)
    if host == "open.spotify.com" and re.search(r"/(playlist|album)/[A-Za-z0-9]+", parsed.path):
        return Route("spotify", text)
    if host == "music.apple.com" and re.search(r"/(playlist|album)/", parsed.path):
        return Route("apple", text)
    raise NotSupported(NOT_SUPPORTED)


def fetch_page(url: str) -> str:
    try:
        response = httpx.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=20, verify=certifi.where())
    except httpx.HTTPError as exc:
        raise Offline("Couldn't reach that site. Check your connection.") from exc
    if response.status_code >= 400:
        raise NotFound("This playlist is private or doesn't exist")
    return response.text


def spotify_embed_url(url: str) -> str:
    found = re.search(r"/(playlist|album)/([A-Za-z0-9]+)", urlparse(url).path)
    return f"https://open.spotify.com/embed/{found.group(1)}/{found.group(2)}"


def _script_json(html: str, script_id: str):
    found = re.search(rf'<script[^>]*id="{script_id}"[^>]*>(.*?)</script>', html, re.DOTALL)
    return json.loads(found.group(1))


def _seconds(milliseconds) -> int | None:
    return round(milliseconds / 1000) if milliseconds else None


def parse_spotify(html: str) -> PlaylistInfo:
    try:
        entity = _script_json(html, "__NEXT_DATA__")["props"]["pageProps"]["state"]["data"]["entity"]
        rows = entity["trackList"]
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ParseChanged(PARSE_CHANGED) from exc
    name = entity.get("name") or entity.get("title") or "Spotify playlist"
    is_album = entity.get("type") == "album"
    tracks = [
        Track(
            title=row["title"],
            artist=re.sub(r"\s*,\s*", ", ", (row.get("subtitle") or "").replace("\xa0", " ")).strip() or "Unknown Artist",
            album=name if is_album else None,
            duration_s=_seconds(row.get("duration")),
        )
        for row in rows
        if row.get("title")
    ]
    sources = (entity.get("coverArt") or {}).get("sources") or []
    note = None
    if not is_album and len(tracks) >= SPOTIFY_CAP:
        note = "Spotify only shares the first 100 songs — this playlist may have more"
    return PlaylistInfo(id=None, name=name, art_url=sources[0].get("url") if sources else None, count=len(tracks), tracks=tracks, note=note)


def parse_apple(html: str) -> PlaylistInfo:
    try:
        sections = _script_json(html, "serialized-server-data")["data"][0]["data"]["sections"]
    except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
        raise ParseChanged(PARSE_CHANGED) from exc
    header = next((s["items"][0] for s in sections if s.get("itemKind") == "containerDetailHeaderLockup" and s.get("items")), {})
    rows = [item for s in sections if s.get("itemKind") == "trackLockup" for item in s.get("items") or []]
    if not rows:
        raise ParseChanged(PARSE_CHANGED)
    name = header.get("title") or "Apple Music playlist"
    is_album = str(header.get("id", "")).startswith("album-")
    header_artist = ((header.get("subtitleLinks") or [{}])[0] or {}).get("title")
    tracks = [
        Track(
            title=row["title"],
            artist=row.get("artistName") or header_artist or "Unknown Artist",
            album=name if is_album else None,
            duration_s=_seconds(row.get("duration")),
        )
        for row in rows
        if row.get("title")
    ]
    og_image = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
    return PlaylistInfo(id=None, name=name, art_url=html_lib.unescape(og_image.group(1)) if og_image else None, count=len(tracks), tracks=tracks)


def resolve(text: str, tab: str) -> dict:
    route = classify(text)
    if route.kind == "search":
        if tab == "playlists":
            return {"type": "playlists", "playlists": ytmusic.search_playlists(route.value)}
        return {"type": "songs", "songs": ytmusic.search_songs(route.value)}
    if route.kind == "song":
        return {"type": "songs", "songs": [ytmusic.get_song(route.value)]}
    if route.kind == "youtube_playlist":
        return {"type": "playlist", "playlist": ytmusic.get_playlist(route.value)}
    if route.kind == "spotify":
        return {"type": "playlist", "playlist": parse_spotify(fetch_page(spotify_embed_url(route.value)))}
    return {"type": "playlist", "playlist": parse_apple(fetch_page(route.value))}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_links.py -v`
Expected: 31 passed

- [ ] **Step 5: Append live link tests to `tests/test_live.py`**

```python
import links


def test_spotify_playlist_live():
    result = links.resolve("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M", "songs")
    playlist = result["playlist"]
    assert playlist.tracks and all(track.title and track.artist for track in playlist.tracks)


def test_apple_playlist_live():
    result = links.resolve("https://music.apple.com/us/playlist/todays-hits/pl.f4d106fed2bd41149aaacabb233eb5eb", "songs")
    playlist = result["playlist"]
    assert playlist.tracks and all(track.artist != "Unknown Artist" for track in playlist.tracks)
```

(Put `import links` with the other imports at the top of the file.)

- [ ] **Step 6: Run live link tests**

Run: `.venv/bin/pytest -m live tests/test_live.py -v -k "spotify or apple"`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add links.py tests/test_links.py tests/test_live.py
git commit -m "feat: read pasted YouTube, Spotify and Apple Music links"
```

---

### Task 6: Download jobs

**Files:**
- Create: `jobs.py`
- Modify: `tests/conftest.py` (append fixtures)
- Test: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `download.fetch`, `download.FORMATS`, `download.Result`, `download.safe_filename`, `download.unique_path`, `ytmusic.match`, `models.Track`, `models.RetroError`, `models.NotFound`
- Produces:
  - `jobs.ROOT: Path`, `jobs.KEEP_SECONDS = 3600`
  - `jobs.Job` with `.id`, `.dir`, `.finished_at`, `.public() -> dict` (`id, name, status, done, failed, total, current, cancelled, results`)
  - `jobs.clear_root(root: Path = ROOT) -> None`
  - `jobs.build_zip(files: list[Path], zip_path: Path, folder: str) -> None`
  - `jobs.JobManager(root=ROOT, fetch=download.fetch, match=ytmusic.match, cookie_source=lambda: "off", workers=3)` with `.start(tracks, fmt, name) -> Job` (raises `ValueError`), `.get(job_id) -> Job` (raises `NotFound`), `.cancel(job_id)`, `.file(job_id) -> tuple[Path, str]` (raises `RetroError`), `.cleanup(now=None)`
  - Fixtures `fake_fetch(fail_titles=(), calls=None)` and `wait_job(manager, job_id, timeout=10) -> dict`

- [ ] **Step 1: Append fixtures to `tests/conftest.py`**

Add these imports at the top of the file:
```python
import time

import download
from models import RetroError
```

Append at the end of the file:
```python
@pytest.fixture
def fake_fetch():
    """Stand-in for download.fetch that writes a tiny file instead of downloading."""

    def make(fail_titles=(), calls=None):
        def fetch(track, fmt, workdir, cookie_source="off"):
            if calls is not None:
                calls.append((track, fmt, cookie_source))
            if track.title in fail_titles:
                raise RetroError("Unavailable on YouTube")
            path = download.unique_path(workdir, download.safe_filename(f"{track.artist} - {track.title}"), fmt)
            path.write_bytes(b"audio")
            return download.Result(path=path, quality="AAC 130")

        return fetch

    return make


@pytest.fixture
def wait_job():
    def wait(manager, job_id, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = manager.get(job_id).public()
            if status["status"] != "running":
                return status
            time.sleep(0.02)
        raise AssertionError("job did not finish in time")

    return wait
```

- [ ] **Step 2: Write the failing tests `tests/test_jobs.py`**

```python
import threading
import time
import zipfile

import pytest

import jobs
from models import NotFound, RetroError, Track

TRACKS = [Track(title=f"Song {i}", artist="Artist", video_id=f"vid{i}") for i in range(3)]


def manager_for(tmp_path, fetch, **kwargs):
    return jobs.JobManager(root=tmp_path / "jobs", fetch=fetch, match=lambda track: track, **kwargs)


def test_playlist_job_builds_zip(tmp_path, fake_fetch, wait_job):
    manager = manager_for(tmp_path, fake_fetch())
    job = manager.start(TRACKS, "m4a", "My Mix")
    status = wait_job(manager, job.id)

    assert status["status"] == "done"
    assert (status["done"], status["failed"], status["total"]) == (3, 0, 3)
    assert status["current"] is None
    assert sorted(r["title"] for r in status["results"]) == ["Song 0", "Song 1", "Song 2"]
    assert all(r["quality"] == "AAC 130" for r in status["results"])

    path, filename = manager.file(job.id)
    assert filename == "My Mix.zip"
    with zipfile.ZipFile(path) as archive:
        assert sorted(archive.namelist()) == ["My Mix/Artist - Song 0.m4a", "My Mix/Artist - Song 1.m4a", "My Mix/Artist - Song 2.m4a"]
        assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())


def test_single_song_job_returns_the_file(tmp_path, fake_fetch, wait_job):
    manager = manager_for(tmp_path, fake_fetch())
    job = manager.start(TRACKS[:1], "opus", "Artist - Song 0")
    wait_job(manager, job.id)
    path, filename = manager.file(job.id)
    assert filename == "Artist - Song 0.opus"
    assert path.read_bytes() == b"audio"


def test_partial_failure_keeps_going(tmp_path, fake_fetch, wait_job):
    manager = manager_for(tmp_path, fake_fetch(fail_titles={"Song 1"}))
    job = manager.start(TRACKS, "m4a", "Mix")
    status = wait_job(manager, job.id)
    assert (status["status"], status["done"], status["failed"]) == ("done", 2, 1)
    assert {"title": "Song 1", "artist": "Artist", "error": "Unavailable on YouTube"} in status["results"]
    path, _ = manager.file(job.id)
    with zipfile.ZipFile(path) as archive:
        assert len(archive.namelist()) == 2


def test_all_failed_job_has_no_file(tmp_path, fake_fetch, wait_job):
    manager = manager_for(tmp_path, fake_fetch(fail_titles={"Song 0", "Song 1", "Song 2"}))
    job = manager.start(TRACKS, "m4a", "Mix")
    assert wait_job(manager, job.id)["status"] == "failed"
    with pytest.raises(RetroError, match="Nothing was downloaded"):
        manager.file(job.id)


def test_unexpected_errors_are_recorded(tmp_path, wait_job):
    def broken_fetch(track, fmt, workdir, cookie_source="off"):
        raise ValueError("boom")

    manager = manager_for(tmp_path, broken_fetch)
    job = manager.start(TRACKS[:1], "m4a", "Mix")
    status = wait_job(manager, job.id)
    assert status["results"] == [{"title": "Song 0", "artist": "Artist", "error": "boom"}]


def test_match_failures_are_recorded(tmp_path, fake_fetch, wait_job):
    def no_match(track):
        raise RetroError("Not found on YouTube Music")

    manager = jobs.JobManager(root=tmp_path / "jobs", fetch=fake_fetch(), match=no_match)
    job = manager.start([Track(title="Lost", artist="Nobody")], "m4a", "Mix")
    assert wait_job(manager, job.id)["results"] == [{"title": "Lost", "artist": "Nobody", "error": "Not found on YouTube Music"}]


def test_cancel_skips_queued_songs(tmp_path, fake_fetch, wait_job):
    started, release = threading.Event(), threading.Event()
    base = fake_fetch()

    def slow_fetch(track, fmt, workdir, cookie_source="off"):
        started.set()
        release.wait(5)
        return base(track, fmt, workdir, cookie_source)

    manager = manager_for(tmp_path, slow_fetch, workers=1)
    job = manager.start(TRACKS, "m4a", "Mix")
    assert started.wait(5)
    manager.cancel(job.id)
    release.set()
    status = wait_job(manager, job.id)
    assert (status["status"], status["done"], status["cancelled"]) == ("done", 1, True)


def test_file_while_running_raises(tmp_path, fake_fetch, wait_job):
    release = threading.Event()
    base = fake_fetch()

    def slow_fetch(track, fmt, workdir, cookie_source="off"):
        release.wait(5)
        return base(track, fmt, workdir, cookie_source)

    manager = manager_for(tmp_path, slow_fetch)
    job = manager.start(TRACKS[:1], "m4a", "Mix")
    with pytest.raises(RetroError, match="Still downloading"):
        manager.file(job.id)
    release.set()
    wait_job(manager, job.id)


def test_cookie_source_is_passed_to_fetch(tmp_path, fake_fetch, wait_job):
    calls = []
    manager = manager_for(tmp_path, fake_fetch(calls=calls), cookie_source=lambda: "firefox")
    job = manager.start(TRACKS[:1], "mp3", "Mix")
    wait_job(manager, job.id)
    assert calls[0][1:] == ("mp3", "firefox")


def test_unknown_job_raises_not_found(tmp_path, fake_fetch):
    with pytest.raises(NotFound, match="Download not found"):
        manager_for(tmp_path, fake_fetch()).get("nope")


def test_start_validates_input(tmp_path, fake_fetch):
    manager = manager_for(tmp_path, fake_fetch())
    with pytest.raises(ValueError):
        manager.start([], "m4a", "Mix")
    with pytest.raises(ValueError):
        manager.start(TRACKS, "wav", "Mix")


def test_cleanup_removes_jobs_older_than_an_hour(tmp_path, fake_fetch, wait_job):
    manager = manager_for(tmp_path, fake_fetch())
    job = manager.start(TRACKS[:1], "m4a", "Mix")
    wait_job(manager, job.id)
    manager.cleanup(now=job.finished_at + jobs.KEEP_SECONDS - 1)
    assert job.id in manager.jobs
    manager.cleanup(now=job.finished_at + jobs.KEEP_SECONDS + 1)
    assert job.id not in manager.jobs
    assert not job.dir.exists()


def test_clear_root_empties_the_folder(tmp_path):
    (tmp_path / "old-job").mkdir()
    (tmp_path / "old-job" / "song.m4a").write_bytes(b"x")
    jobs.clear_root(tmp_path)
    assert tmp_path.exists()
    assert list(tmp_path.iterdir()) == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_jobs.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'jobs'`

- [ ] **Step 4: Write `jobs.py`**

```python
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
        cookie_source: Callable[[], str] = lambda: "off",
        workers: int = WORKERS,
    ):
        self.root = root
        self.jobs: dict[str, Job] = {}
        self._fetch = fetch
        self._match = match
        self._cookie_source = cookie_source
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
        cookie_source = self._cookie_source()
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            list(pool.map(lambda track: self._one(job, track, cookie_source), job.tracks))
        with job.lock:
            job.current = None
            job.status = "done" if job.files else "failed"
            job.finished_at = time.time()

    def _one(self, job: Job, track: Track, cookie_source: str) -> None:
        with job.lock:
            if job.cancelled:
                return
            job.current = f"{track.title} — {track.artist}"
        try:
            result = self._fetch(self._match(track), job.fmt, job.dir, cookie_source)
        except Exception as exc:  # one bad song must not stop the rest of the playlist
            with job.lock:
                job.failed += 1
                job.results.append({"title": track.title, "artist": track.artist, "error": (str(exc) or type(exc).__name__)[:200]})
            return
        with job.lock:
            job.done += 1
            job.files.append(result.path)
            job.results.append({"title": track.title, "artist": track.artist, "quality": result.quality})
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_jobs.py -v`
Expected: 13 passed

- [ ] **Step 6: Commit**

```bash
git add jobs.py tests/conftest.py tests/test_jobs.py
git commit -m "feat: run downloads as jobs and package playlists as ZIP files"
```

---

### Task 7: FastAPI app

**Files:**
- Create: `app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `jobs.JobManager`, `jobs.clear_root`, `links.resolve`, `ytmusic.get_playlist`, `settings.load`, `settings.save`, `models.*`
- Produces:
  - `app.create_app(manager: JobManager | None = None, settings_file: Path | None = None) -> FastAPI`
  - `app.main()` (clears job folders, opens the browser unless `--no-browser`, runs uvicorn on `127.0.0.1:8787`)
  - Routes: `GET /`, `GET /api/search?q=&type=songs|playlists`, `GET /api/playlist?id=`, `POST /api/jobs`, `GET /api/jobs/{id}`, `GET /api/jobs/{id}/file`, `POST /api/jobs/{id}/cancel`, `GET /api/settings`, `PUT /api/settings`
  - Errors are JSON `{"error": "<message>"}`: `NotFound` → 404, `Offline`/`ParseChanged` → 502, other `RetroError` → 400, foreign `Host` → 403

- [ ] **Step 1: Write the failing tests `tests/test_app.py`**

```python
import time

import pytest
from fastapi.testclient import TestClient

import app as app_module
import jobs
from models import NotFound, NotSupported, Offline, PlaylistInfo, Track


def build_app(tmp_path, fake_fetch):
    manager = jobs.JobManager(root=tmp_path / "jobs", fetch=fake_fetch(), match=lambda track: track)
    return app_module.create_app(manager=manager, settings_file=tmp_path / "settings.json")


@pytest.fixture
def client(tmp_path, fake_fetch):
    return TestClient(build_app(tmp_path, fake_fetch), base_url="http://127.0.0.1:8787")


def wait_for(client, job_id):
    for _ in range(500):
        status = client.get(f"/api/jobs/{job_id}").json()
        if status["status"] != "running":
            return status
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_rejects_other_host_names(client):
    response = client.get("/api/settings", headers={"host": "evil.example:8787"})
    assert response.status_code == 403


def test_allows_localhost_name(tmp_path, fake_fetch):
    local = TestClient(build_app(tmp_path, fake_fetch), base_url="http://localhost:8787")
    assert local.get("/api/settings").status_code == 200


def test_search_returns_songs(client, monkeypatch):
    calls = []

    def fake_resolve(text, tab):
        calls.append((text, tab))
        return {"type": "songs", "songs": [Track(title="Song", artist="Artist", video_id="abc")]}

    monkeypatch.setattr(app_module.links, "resolve", fake_resolve)
    response = client.get("/api/search", params={"q": "song", "type": "songs"})
    assert response.status_code == 200
    assert response.json() == {
        "type": "songs",
        "songs": [{"title": "Song", "artist": "Artist", "album": None, "duration_s": None, "art_url": None, "video_id": "abc"}],
    }
    assert calls == [("song", "songs")]


def test_search_defaults_to_songs_tab(client, monkeypatch):
    calls = []
    monkeypatch.setattr(app_module.links, "resolve", lambda text, tab: calls.append(tab) or {"type": "songs", "songs": []})
    client.get("/api/search", params={"q": "x"})
    assert calls == ["songs"]


def test_search_requires_text(client):
    response = client.get("/api/search", params={"q": "   "})
    assert response.status_code == 400
    assert response.json() == {"error": "Type something to search"}


@pytest.mark.parametrize(
    "error,status",
    [
        (NotSupported("Link not supported — paste a YouTube, YouTube Music, Spotify or Apple Music link"), 400),
        (NotFound("This playlist is private or doesn't exist"), 404),
        (Offline("Couldn't reach YouTube Music. Check your connection."), 502),
    ],
)
def test_search_errors_become_json(client, monkeypatch, error, status):
    def boom(text, tab):
        raise error

    monkeypatch.setattr(app_module.links, "resolve", boom)
    response = client.get("/api/search", params={"q": "x"})
    assert response.status_code == status
    assert response.json() == {"error": str(error)}


def test_playlist_route(client, monkeypatch):
    monkeypatch.setattr(app_module.ytmusic, "get_playlist", lambda playlist_id: PlaylistInfo(id=playlist_id, name="Mix", count=0))
    response = client.get("/api/playlist", params={"id": "VLabc"})
    assert response.status_code == 200
    assert response.json()["id"] == "VLabc"
    assert response.json()["name"] == "Mix"


def test_job_lifecycle_returns_zip(client):
    body = {
        "tracks": [{"title": "One", "artist": "A", "video_id": "v1"}, {"title": "Two", "artist": "A", "video_id": "v2"}],
        "format": "m4a",
        "name": "Mix",
    }
    job_id = client.post("/api/jobs", json=body).json()["id"]
    status = wait_for(client, job_id)
    assert (status["status"], status["done"], status["total"]) == ("done", 2, 2)
    response = client.get(f"/api/jobs/{job_id}/file")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="Mix.zip"'


def test_job_rejects_bad_format(client):
    response = client.post("/api/jobs", json={"tracks": [{"title": "a", "artist": "b"}], "format": "wav"})
    assert response.status_code == 422


def test_job_rejects_empty_track_list(client):
    response = client.post("/api/jobs", json={"tracks": [], "format": "m4a"})
    assert response.status_code == 422


def test_unknown_job(client):
    response = client.get("/api/jobs/nope")
    assert response.status_code == 404
    assert response.json() == {"error": "Download not found"}


def test_cancel_job(client):
    job_id = client.post("/api/jobs", json={"tracks": [{"title": "a", "artist": "b", "video_id": "v"}]}).json()["id"]
    assert client.post(f"/api/jobs/{job_id}/cancel").json() == {"ok": True}


def test_settings_round_trip(client):
    initial = client.get("/api/settings").json()
    assert initial["cookie_source"] == "off"
    assert "platform" in initial
    saved = client.put("/api/settings", json={"cookie_source": "firefox"})
    assert saved.status_code == 200
    assert saved.json()["cookie_source"] == "firefox"
    assert client.get("/api/settings").json()["cookie_source"] == "firefox"


def test_settings_rejects_unknown_source(client):
    response = client.put("/api/settings", json={"cookie_source": "netscape"})
    assert response.status_code == 400
    assert response.json() == {"error": "Unknown login source"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_app.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Write `app.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_app.py -v`
Expected: 17 passed

- [ ] **Step 5: Run the whole offline suite**

Run: `.venv/bin/pytest`
Expected: all passed, 0 failed

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: add local FastAPI app with search, jobs and settings routes"
```

---

### Task 8: The page

**Files:**
- Create: `static/index.html`
- Modify: `tests/test_app.py` (append one test)

**Interfaces:**
- Consumes: every route from Task 7 and their JSON shapes: search → `{type, songs|playlists|playlist}`; job status → `{id, name, status, done, failed, total, current, cancelled, results[{title, artist, quality|error}]}`; settings → `{cookie_source, platform}`; errors → `{error}`.
- Produces: the UI at `GET /`.

- [ ] **Step 1: Append the failing test to `tests/test_app.py`**

```python
def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<title>retro-ears</title>" in response.text
    assert 'id="searchForm"' in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_app.py::test_index_page -v`
Expected: FAIL (FileResponse raises because `static/index.html` does not exist)

- [ ] **Step 3: Write `static/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>retro-ears</title>
<style>
  :root {
    color-scheme: dark;
    --bg: #0c0c0d;
    --surface: #151517;
    --surface-2: #1d1d20;
    --line: #27272b;
    --line-strong: #3a3a40;
    --text: #ededee;
    --muted: #8d8d94;
    --accent: #e6ff5c;
    --accent-ink: #0c0c0d;
    --danger: #ff7a7a;
    --warn: #f4c261;
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  * { box-sizing: border-box; }
  [hidden] { display: none !important; }
  body { margin: 0; background: var(--bg); color: var(--text); font-size: 15px; line-height: 1.45; -webkit-font-smoothing: antialiased; }
  button, input, select { font: inherit; color: inherit; }
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .wrap { max-width: 760px; margin: 0 auto; padding: 48px 20px 160px; }
  header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 28px; }
  .brand { font-size: 20px; font-weight: 650; letter-spacing: -0.02em; }
  .brand b { color: var(--accent); font-weight: inherit; }
  .btn { height: 36px; padding: 0 14px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface-2); cursor: pointer; white-space: nowrap; transition: border-color .15s, background-color .15s; }
  .btn:hover { border-color: var(--line-strong); }
  .btn:disabled { opacity: .5; cursor: default; }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); font-weight: 600; }
  .btn.icon { width: 36px; padding: 0; font-size: 17px; }
  .search { display: flex; gap: 8px; }
  .search input { flex: 1; min-width: 0; height: 50px; padding: 0 16px; background: var(--surface); border: 1px solid var(--line); border-radius: 12px; }
  .search input::placeholder { color: var(--muted); }
  .search input:focus-visible { outline: none; border-color: var(--accent); }
  .search .btn { height: 50px; padding: 0 22px; border-radius: 12px; }
  .toolbar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin: 16px 0 12px; }
  .tabs { display: inline-flex; padding: 3px; background: var(--surface); border: 1px solid var(--line); border-radius: 999px; }
  .tab { padding: 6px 16px; border: 0; border-radius: 999px; background: transparent; color: var(--muted); cursor: pointer; }
  .tab[aria-selected="true"] { background: var(--surface-2); color: var(--text); }
  .format { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 14px; }
  select { height: 34px; padding: 0 8px; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; }
  .list { margin: 0; padding: 0; list-style: none; }
  .row { display: grid; grid-template-columns: 48px minmax(0, 1fr) auto auto; align-items: center; gap: 14px; padding: 8px; border-radius: 10px; }
  .row:hover { background: var(--surface); }
  .art { width: 48px; height: 48px; border-radius: 6px; object-fit: cover; background: var(--surface-2); }
  .title, .sub { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .sub { color: var(--muted); font-size: 13px; }
  .time { color: var(--muted); font-size: 13px; font-variant-numeric: tabular-nums; }
  .actions { display: flex; gap: 6px; }
  .state { margin: 0; padding: 56px 8px; color: var(--muted); text-align: center; }
  .state.error { color: var(--danger); }
  .back { margin: 4px 0 12px; padding: 0; border: 0; background: none; color: var(--muted); cursor: pointer; }
  .back:hover { color: var(--text); }
  .pl-head { display: flex; align-items: center; gap: 18px; margin-bottom: 18px; }
  .cover { flex: none; width: 104px; height: 104px; border-radius: 10px; object-fit: cover; background: var(--surface-2); }
  .pl-head h2 { margin: 0 0 2px; font-size: 22px; letter-spacing: -0.01em; }
  .pl-head .btn { margin-top: 12px; }
  .note { margin-top: 4px; color: var(--warn); font-size: 13px; }
  .dock { position: fixed; right: 0; bottom: 0; left: 0; background: rgba(12, 12, 13, .92); border-top: 1px solid var(--line); backdrop-filter: blur(14px); }
  .dock-inner { max-width: 760px; margin: 0 auto; padding: 14px 20px 16px; }
  .dock-line { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .dock-line > div { min-width: 0; }
  .bar { height: 3px; margin-top: 12px; overflow: hidden; background: var(--surface-2); border-radius: 3px; }
  .bar i { display: block; width: 0; height: 100%; background: var(--accent); transition: width .3s ease; }
  details { margin-top: 10px; color: var(--muted); font-size: 13px; }
  details ul { max-height: 180px; margin: 8px 0 0; padding-left: 18px; overflow: auto; }
  .bad { color: var(--danger); }
  dialog { width: min(420px, calc(100vw - 32px)); padding: 22px; background: var(--surface); color: var(--text); border: 1px solid var(--line); border-radius: 14px; }
  dialog::backdrop { background: rgba(0, 0, 0, .6); }
  dialog h2 { margin: 0 0 6px; font-size: 18px; }
  .field { display: grid; gap: 6px; margin-top: 16px; color: var(--muted); font-size: 14px; }
  .field input { height: 38px; padding: 0 10px; background: var(--bg); border: 1px solid var(--line); border-radius: 8px; }
  .help { margin: 8px 0 0; color: var(--muted); font-size: 13px; }
  .help.bad { color: var(--danger); }
  .dialog-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }
  @media (max-width: 560px) {
    .wrap { padding-top: 28px; }
    .row { grid-template-columns: 40px minmax(0, 1fr) auto; }
    .art { width: 40px; height: 40px; }
    .time { display: none; }
  }
  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">retro<b>·</b>ears</div>
    <button class="btn" id="premiumBtn" type="button">Premium: Off</button>
  </header>

  <form class="search" id="searchForm" role="search">
    <input id="q" type="search" autocomplete="off" spellcheck="false" autofocus
      placeholder="Search songs or playlists, or paste a link…"
      aria-label="Search songs or playlists, or paste a link">
    <button class="btn primary" type="submit">Search</button>
  </form>

  <div class="toolbar">
    <div class="tabs" role="tablist" aria-label="Search for">
      <button class="tab" role="tab" type="button" data-tab="songs" aria-selected="true">Songs</button>
      <button class="tab" role="tab" type="button" data-tab="playlists" aria-selected="false">Playlists</button>
    </div>
    <label class="format">Format
      <select id="format">
        <option value="m4a">M4A · iPod</option>
        <option value="opus">Opus · Rockbox</option>
        <option value="mp3">MP3 320</option>
      </select>
    </label>
  </div>

  <main id="results" aria-live="polite">
    <p class="state">Search for a song or playlist, or paste a YouTube, Spotify or Apple Music link.</p>
  </main>
</div>

<div class="dock" id="dock" hidden>
  <div class="dock-inner">
    <div class="dock-line">
      <div>
        <div class="title" id="dockTitle"></div>
        <div class="sub" id="dockSub"></div>
      </div>
      <button class="btn" id="dockAction" type="button"></button>
    </div>
    <div class="bar" id="dockBar"><i id="dockFill"></i></div>
    <details id="dockDetails" hidden>
      <summary>Details</summary>
      <ul id="dockList"></ul>
    </details>
  </div>
</div>

<dialog id="premiumDialog" aria-labelledby="premiumTitle">
  <form method="dialog">
    <h2 id="premiumTitle">YouTube Premium</h2>
    <p class="help">Optional. Uses your own Premium login from a browser to get 256 kbps audio. Without it you still get the best free quality.</p>
    <label class="field">Login from
      <select id="cookieSource">
        <option value="off">Off</option>
        <option value="firefox">Firefox</option>
        <option value="safari">Safari</option>
        <option value="chrome">Chrome</option>
        <option value="file">cookies.txt file</option>
      </select>
    </label>
    <label class="field" id="cookieFileField" hidden>Path to cookies.txt
      <input id="cookieFile" type="text" spellcheck="false">
    </label>
    <p class="help" id="cookieHint"></p>
    <p class="help bad" id="premiumError" role="alert" hidden></p>
    <div class="dialog-actions">
      <button class="btn" value="cancel">Cancel</button>
      <button class="btn primary" id="premiumSave" type="button">Save</button>
    </div>
  </form>
</dialog>

<script>
  const $ = (selector) => document.querySelector(selector);
  const els = {
    q: $("#q"), results: $("#results"), format: $("#format"),
    dock: $("#dock"), dockTitle: $("#dockTitle"), dockSub: $("#dockSub"), dockAction: $("#dockAction"),
    dockBar: $("#dockBar"), dockFill: $("#dockFill"), dockDetails: $("#dockDetails"), dockList: $("#dockList"),
    premiumBtn: $("#premiumBtn"), premiumDialog: $("#premiumDialog"), cookieSource: $("#cookieSource"),
    cookieFileField: $("#cookieFileField"), cookieFile: $("#cookieFile"), cookieHint: $("#cookieHint"),
    premiumError: $("#premiumError"),
  };
  const state = { tab: "songs", jobId: null, back: null, platform: null, seq: 0 };
  const encode = encodeURIComponent;
  const isLink = (text) => /^https?:\/\//i.test(text.trim());

  function h(tag, props = {}, ...children) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") el.className = value;
      else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
      else el.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      el.append(child instanceof Node ? child : String(child));
    }
    return el;
  }

  async function api(path, options = {}) {
    let response;
    try {
      response = await fetch(path, { ...options, headers: { "Content-Type": "application/json" } });
    } catch {
      throw new Error("retro-ears isn't running. Start it again with run.sh or run.ps1.");
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : "Something went wrong.");
    return data;
  }

  function readStored(key, fallback) {
    try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
  }
  function writeStored(key, value) {
    try { localStorage.setItem(key, value); } catch { /* storage unavailable */ }
  }

  /* ---------- results ---------- */

  function show(...nodes) { els.results.replaceChildren(...nodes.filter(Boolean)); }
  function showMessage(text, isError = false) { show(h("p", { class: isError ? "state error" : "state" }, text)); }

  function duration(seconds) {
    if (seconds === null || seconds === undefined) return "";
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  }

  function image(url, className) {
    return url
      ? h("img", { class: className, src: url, alt: "", loading: "lazy", referrerpolicy: "no-referrer" })
      : h("div", { class: className });
  }

  function songRow(track) {
    return h("li", { class: "row" },
      image(track.art_url, "art"),
      h("div", {},
        h("div", { class: "title" }, track.title),
        h("div", { class: "sub" }, [track.artist, track.album].filter(Boolean).join(" · "))),
      h("span", { class: "time" }, duration(track.duration_s)),
      h("div", { class: "actions" },
        h("button", {
          class: "btn icon", type: "button", title: "Download", "aria-label": `Download ${track.title}`,
          onclick: () => startJob([track], `${track.artist} - ${track.title}`),
        }, "↓")));
  }

  function renderSongs(songs) {
    if (!songs.length) return showMessage("No songs found");
    state.back = () => renderSongs(songs);
    show(h("ul", { class: "list" }, songs.map(songRow)));
  }

  function renderPlaylists(playlists) {
    if (!playlists.length) return showMessage("No playlists found");
    state.back = () => renderPlaylists(playlists);
    show(h("ul", { class: "list" }, playlists.map((playlist) => h("li", { class: "row" },
      image(playlist.art_url, "art"),
      h("div", {},
        h("div", { class: "title" }, playlist.name),
        h("div", { class: "sub" }, playlist.count ? `${playlist.count} songs` : "Playlist")),
      h("span", { class: "time" }),
      h("div", { class: "actions" },
        h("button", { class: "btn", type: "button", onclick: () => openPlaylist(playlist.id) }, "View"),
        h("button", {
          class: "btn icon", type: "button", title: "Download all", "aria-label": `Download all of ${playlist.name}`,
          onclick: () => downloadPlaylist(playlist.id),
        }, "↓"))))));
  }

  function renderPlaylist(playlist, back) {
    const tracks = playlist.tracks || [];
    show(
      back && h("button", { class: "back", type: "button", onclick: back }, "← Back"),
      h("div", { class: "pl-head" },
        image(playlist.art_url, "cover"),
        h("div", {},
          h("h2", {}, playlist.name),
          h("div", { class: "sub" }, `${tracks.length} songs`),
          playlist.note && h("div", { class: "note" }, playlist.note),
          h("button", {
            class: "btn primary", type: "button", disabled: !tracks.length,
            onclick: () => startJob(tracks, playlist.name),
          }, "Download all"))),
      tracks.length
        ? h("ul", { class: "list" }, tracks.map(songRow))
        : h("p", { class: "state" }, "This playlist has no downloadable songs."));
  }

  async function runSearch() {
    const text = els.q.value.trim();
    if (!text) return;
    const seq = ++state.seq;
    showMessage(isLink(text) ? "Reading link…" : "Searching…");
    try {
      const data = await api(`/api/search?q=${encode(text)}&type=${state.tab}`);
      if (seq !== state.seq) return;
      if (data.type === "songs") renderSongs(data.songs);
      else if (data.type === "playlists") renderPlaylists(data.playlists);
      else { state.back = null; renderPlaylist(data.playlist, null); }
    } catch (error) {
      if (seq === state.seq) showMessage(error.message, true);
    }
  }

  async function openPlaylist(id) {
    const back = state.back;
    const seq = ++state.seq;
    showMessage("Loading playlist…");
    try {
      const playlist = await api(`/api/playlist?id=${encode(id)}`);
      if (seq === state.seq) renderPlaylist(playlist, back);
    } catch (error) {
      if (seq === state.seq) showMessage(error.message, true);
    }
  }

  /* ---------- downloads ---------- */

  function setDock({ title, sub = "", progress = null, action = null, results = null, error = false }) {
    els.dock.hidden = false;
    els.dockTitle.textContent = title;
    els.dockTitle.classList.toggle("bad", error);
    els.dockSub.textContent = sub;
    els.dockAction.hidden = !action;
    if (action) {
      els.dockAction.textContent = action.label;
      els.dockAction.onclick = action.run;
    }
    els.dockBar.hidden = progress === null;
    if (progress !== null) els.dockFill.style.width = `${Math.round(progress * 100)}%`;
    els.dockDetails.hidden = !(results && results.length);
    if (results) {
      els.dockList.replaceChildren(...results.map((result) => h("li", {},
        `${result.artist} — ${result.title}: `,
        result.error ? h("span", { class: "bad" }, result.error) : result.quality)));
    }
  }

  const hideDock = () => { els.dock.hidden = true; };
  const closeAction = { label: "Close", run: hideDock };
  const nudgeBusy = () => { els.dockSub.textContent = "Finish or cancel the current download first."; };

  async function startJob(tracks, name) {
    if (state.jobId) return nudgeBusy();
    if (!tracks.length) return setDock({ title: "Nothing to download", error: true, action: closeAction });
    state.jobId = "starting";
    setDock({ title: tracks.length === 1 ? `Starting ${tracks[0].title}…` : `Starting ${name}…`, progress: 0 });
    try {
      const { id } = await api("/api/jobs", { method: "POST", body: JSON.stringify({ tracks, format: els.format.value, name }) });
      state.jobId = id;
      pollJob(id);
    } catch (error) {
      state.jobId = null;
      setDock({ title: error.message, error: true, action: closeAction });
    }
  }

  async function downloadPlaylist(id) {
    if (state.jobId) return nudgeBusy();
    setDock({ title: "Loading playlist…", progress: 0 });
    try {
      const playlist = await api(`/api/playlist?id=${encode(id)}`);
      await startJob(playlist.tracks, playlist.name);
    } catch (error) {
      setDock({ title: error.message, error: true, action: closeAction });
    }
  }

  async function pollJob(id) {
    let job;
    try {
      job = await api(`/api/jobs/${encode(id)}`);
    } catch (error) {
      state.jobId = null;
      return setDock({ title: error.message, error: true, action: closeAction });
    }
    const single = job.total === 1;
    const finished = job.done + job.failed;
    if (job.status === "running") {
      setDock({
        title: single ? `Downloading ${job.current || job.name}` : `Downloading ${finished} / ${job.total}`,
        sub: single ? "" : job.current || "",
        progress: single ? null : finished / job.total,
        action: {
          label: job.cancelled ? "Cancelling…" : "Cancel",
          run: () => api(`/api/jobs/${encode(id)}/cancel`, { method: "POST" }).catch(() => {}),
        },
      });
      setTimeout(() => pollJob(id), 1000);
      return;
    }
    state.jobId = null;
    if (job.status === "done") saveFile(id);
    const first = job.results[0] || {};
    setDock({
      title: job.name,
      sub: single
        ? (job.done ? `Downloaded · ${first.quality}` : `Failed · ${first.error || "Cancelled"}`)
        : `${job.done} done · ${job.failed} failed${job.cancelled ? " · cancelled" : ""}`,
      error: job.status === "failed",
      results: single ? null : job.results,
      action: closeAction,
    });
  }

  function saveFile(id) {
    const link = h("a", { href: `/api/jobs/${encode(id)}/file`, download: "" });
    document.body.append(link);
    link.click();
    link.remove();
  }

  /* ---------- Premium ---------- */

  const SOURCE_NAMES = { off: "Off", firefox: "Firefox", safari: "Safari", chrome: "Chrome", file: "cookies.txt" };

  function applySettings(saved) {
    state.platform = saved.platform;
    const source = saved.cookie_source.startsWith("file:") ? "file" : saved.cookie_source;
    els.cookieSource.value = source;
    els.cookieFile.value = source === "file" ? saved.cookie_source.slice(5) : "";
    els.cookieSource.querySelector('[value="safari"]').disabled = saved.platform !== "darwin";
    els.cookieSource.querySelector('[value="chrome"]').disabled = saved.platform === "win32";
    els.premiumBtn.textContent = `Premium: ${SOURCE_NAMES[source] || "Off"}`;
    updatePremiumFields();
  }

  function updatePremiumFields() {
    const source = els.cookieSource.value;
    els.cookieFileField.hidden = source !== "file";
    els.premiumError.hidden = true;
    const hints = [];
    if (state.platform === "win32") hints.push("Chrome and Edge logins can't be read on Windows — use Firefox or a cookies.txt file.");
    if (source === "chrome") hints.push("macOS may ask for Keychain access the first time.");
    if (source === "safari") hints.push("Safari needs Full Disk Access for the terminal running retro-ears.");
    if (source === "file") hints.push("Export it from a browser where you're signed in to YouTube.");
    els.cookieHint.textContent = hints.join(" ");
  }

  async function loadSettings() {
    try { applySettings(await api("/api/settings")); } catch { /* keep defaults */ }
  }

  /* ---------- wiring ---------- */

  $("#searchForm").addEventListener("submit", (event) => { event.preventDefault(); runSearch(); });

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.tab = tab.dataset.tab;
      document.querySelectorAll(".tab").forEach((other) => other.setAttribute("aria-selected", String(other === tab)));
      const text = els.q.value.trim();
      if (text && !isLink(text)) runSearch();
    });
  });

  document.addEventListener("keydown", (event) => {
    const typing = ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName);
    if (event.key === "/" && !typing) { event.preventDefault(); els.q.focus(); }
  });

  els.format.value = readStored("format", "m4a");
  if (!els.format.value) els.format.value = "m4a";
  els.format.addEventListener("change", () => writeStored("format", els.format.value));

  els.cookieSource.addEventListener("change", updatePremiumFields);
  els.premiumBtn.addEventListener("click", () => els.premiumDialog.showModal());
  els.premiumDialog.addEventListener("close", loadSettings);
  $("#premiumSave").addEventListener("click", async () => {
    const source = els.cookieSource.value;
    const value = source === "file" ? `file:${els.cookieFile.value.trim()}` : source;
    try {
      applySettings(await api("/api/settings", { method: "PUT", body: JSON.stringify({ cookie_source: value }) }));
      els.premiumDialog.close();
    } catch (error) {
      els.premiumError.textContent = error.message;
      els.premiumError.hidden = false;
    }
  });

  loadSettings();
</script>
</body>
</html>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_app.py -v`
Expected: 18 passed

- [ ] **Step 5: Manual check in a real browser**

Start: `.venv/bin/python app.py --no-browser` (background), then open `http://127.0.0.1:8787` and check each item:
1. Songs tab: search `blinding lights` → rows show art, title, artist · album, duration.
2. Click ↓ on one row with Format M4A → dock shows progress, then the browser saves `The Weeknd - Blinding Lights.m4a` and the dock shows `Downloaded · AAC 130` (or `AAC 256` with Premium).
3. Playlists tab: search `80s hits` → rows with song counts; **View** opens the track list with **← Back**; **Back** returns to the list.
4. Download a small playlist (or a pasted YouTube playlist link with ≤ 5 songs) → `n / total` progress, **Cancel** works, a ZIP is saved, dock shows `x done · y failed` with **Details**.
5. Paste `https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M` → playlist view; paste an Apple Music playlist link → playlist view.
6. Paste `https://soundcloud.com/a/b` → red message "Link not supported — …".
7. Premium dialog: pick Firefox → button reads `Premium: Firefox`; pick cookies.txt with a wrong path → red "cookies.txt file not found".
8. Narrow the window to ~400 px → rows stay readable, durations hide.
Stop the server afterwards.

- [ ] **Step 6: Commit**

```bash
git add static/index.html tests/test_app.py
git commit -m "feat: add the retro-ears page"
```

---

### Task 9: Launchers, README and final verification

**Files:**
- Create: `run.sh`, `run.ps1`, `README.md`

**Interfaces:**
- Consumes: `app.py` (`python app.py [--no-browser]`), `requirements.txt`
- Produces: `./run.sh [--update] [--no-browser]`, `run.ps1 [-Update] [-NoBrowser]`

- [ ] **Step 1: Write `run.sh`**

```bash
#!/usr/bin/env bash
# Start retro-ears on macOS. Usage: ./run.sh [--update] [--no-browser]
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "retro-ears needs Python 3.10 or newer: https://www.python.org/downloads/"
  exit 1
fi
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "retro-ears needs Python 3.10 or newer (found $("$PYTHON" --version 2>&1))."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "First run: setting up (this takes a minute)…"
  "$PYTHON" -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
fi

APP_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --update) .venv/bin/python -m pip install --upgrade "yt-dlp[default]" ytmusicapi ;;
    *) APP_ARGS+=("$arg") ;;
  esac
done

.venv/bin/python -m pip install --quiet -r requirements.txt
exec .venv/bin/python app.py "${APP_ARGS[@]+"${APP_ARGS[@]}"}"
```

- [ ] **Step 2: Write `run.ps1`**

```powershell
# Start retro-ears on Windows. Usage: powershell -ExecutionPolicy Bypass -File run.ps1 [-Update] [-NoBrowser]
param([switch]$Update, [switch]$NoBrowser)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (Get-Command py -ErrorAction SilentlyContinue) { $Py = "py"; $PyArgs = @("-3") }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $Py = "python"; $PyArgs = @() }
else { Write-Host "retro-ears needs Python 3.10 or newer: https://www.python.org/downloads/"; exit 1 }

& $Py @PyArgs -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) { Write-Host "retro-ears needs Python 3.10 or newer."; exit 1 }

$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "First run: setting up (this takes a minute)..."
    & $Py @PyArgs -m venv .venv
    & $VenvPython -m pip install --quiet --upgrade pip
}
if ($Update) { & $VenvPython -m pip install --upgrade "yt-dlp[default]" ytmusicapi }

& $VenvPython -m pip install --quiet -r requirements.txt
$AppArgs = @()
if ($NoBrowser) { $AppArgs += "--no-browser" }
& $VenvPython app.py @AppArgs
```

- [ ] **Step 3: Write `README.md`**

````markdown
# retro-ears

Search songs and playlists, or paste a YouTube, YouTube Music, Spotify or Apple Music link, and download music ready for an iPod — with title, artist, album and cover art built in.

retro-ears runs on your own computer at http://127.0.0.1:8787. It's for personal use: you're responsible for what you download and for following copyright law and YouTube's terms.

## Run it

You need Python 3.10 or newer (3.11+ recommended — yt-dlp has deprecated 3.10). Nothing else: ffmpeg and the JavaScript runtime yt-dlp needs are installed automatically.

**macOS**

```bash
./run.sh
```

**Windows (PowerShell)**

```powershell
powershell -ExecutionPolicy Bypass -File run.ps1
```

The first run sets everything up, then your browser opens. Add `--no-browser` (`-NoBrowser` on Windows) to skip opening it.

If downloads start failing, YouTube probably changed something. Update and restart:

```bash
./run.sh --update          # Windows: run.ps1 -Update
```

## Formats

| Format | What you get | Best for |
|---|---|---|
| **M4A** | YouTube's own AAC audio, not converted (about 130 kbps, 256 with Premium) | Stock iPod |
| **Opus** | YouTube's own Opus audio, not converted (about 130 kbps, 256 with Premium) | Rockbox |
| **MP3 320** | Converted from the best stream — plays anywhere, but isn't better than the source | Everything else |

Each finished song shows the quality it actually got. Spotify playlists only share their first 100 songs.

## Getting songs onto the iPod

- **Stock iPod:** drag the files into the Music app (macOS) or iTunes / Apple Music (Windows), then sync.
- **Rockbox:** copy the files into the iPod's `Music` folder.

## YouTube Premium (optional)

A Premium login can unlock 256 kbps audio. Click **Premium** and choose the browser you're signed in to YouTube with:

- **macOS:** Firefox, Safari (the terminal needs Full Disk Access) or Chrome (allow the Keychain prompt).
- **Windows:** Firefox, or a `cookies.txt` file exported with a browser extension. Chrome and Edge logins can't be read on Windows.

retro-ears only remembers which browser or file to use — never your login itself. If the login doesn't work, downloads carry on at free quality.

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest              # offline tests
.venv/bin/pytest -m live -s   # real downloads; RETRO_COOKIES=firefox to test Premium
```
````

- [ ] **Step 4: Check the launchers**

Run: `chmod +x run.sh && bash -n run.sh && echo "syntax ok"`
Expected: `syntax ok`

Run: `./run.sh --no-browser` (background), wait 5 seconds, then `curl -s -H "Host: 127.0.0.1:8787" http://127.0.0.1:8787/api/settings` and `curl -s -o /dev/null -w "%{http_code}\n" -H "Host: evil.example" http://127.0.0.1:8787/api/settings`; stop the server.
Expected: `{"cookie_source":"off","platform":"darwin"}` (or the saved source) and `403`

`run.ps1` cannot be executed on macOS; it needs one real run on Windows before Windows support is called done (spec §9).

- [ ] **Step 5: Run every test**

Run: `.venv/bin/pytest -v`
Expected: all offline tests pass

Run: `.venv/bin/pytest -m live -s -v`
Expected: all live tests pass

- [ ] **Step 6: Commit**

```bash
git add run.sh run.ps1 README.md
git commit -m "feat: add launchers and README"
```
