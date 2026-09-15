# retro-ears Easy Install Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let non-technical Mac and Windows users download retro-ears from GitHub Releases, double-click to run, update yt-dlp with one button, and save songs straight to a Rockbox iPod.

**Architecture:** The repo becomes a `uv` project (`pyproject.toml` + `uv.lock`, Python 3.12). Double-click launchers use a bundled `uv` binary to install Python and packages into `.runtime/` inside the app folder, then run `app.py` in a restart loop (exit code 42 = restart after update). New modules: `updates.py` (version, GitHub release check, yt-dlp update), `devices.py` (Rockbox detection), `ipod.py` (copy to iPod). `scripts/build_release.py` builds the release zips; GitHub Actions runs tests and publishes releases.

**Tech Stack:** Python ≥ 3.10 (runs on uv-managed 3.12), FastAPI, yt-dlp, uv 0.12.15, bash (`.command`), cmd (`.bat`), GitHub Actions (`actions/checkout@v7.0.1`, `astral-sh/setup-uv@v10.1.0`), vanilla JS.

**Spec:** `docs/superpowers/specs/2026-09-16-retro-ears-easy-install-design.md`

## Global Constraints

- Work on branch `feature/easy-install` in `/Users/kushalsharma/Desktop/retro-ears`.
- Until Task 1 step 7, run tests with `.venv/bin/pytest`; from then on use `uv run pytest` (offline) and `uv run pytest -m live -s` (network).
- Every Python module starts with `from __future__ import annotations` and must run on Python 3.10+.
- Launcher, update and iPod user-facing text is copied verbatim from spec §4.3, §5, §6 and §9.
- `.bat` files contain ASCII only (no em dashes or ellipses); `.command` files use LF line endings; `.bat` files use CRLF.
- Restart exit code is **42**. Runtime folder is `.runtime/` (`python/`, `cache/`, `venv/`, `installed-version`).
- `RETRO_NO_PAUSE=1` makes launchers skip every "press a key" wait (used by tests and CI).
- No real major-label songs, artists or IDs anywhere in the repo. Examples use Kevin MacLeod (CC BY 4.0): YouTube `5viHgHli590` "Kool Kats"; Spotify album `https://open.spotify.com/album/5G34ftqKz03s5y2No2eRu3` ("Groovy"); Apple album `https://music.apple.com/us/album/light-electronic/1887659157`. `tests/test_repo_hygiene.py` enforces this; its denylist is ROT13-encoded.
- Offline tests never touch the network: inject fakes (`checker`, `find_devices`, `restart`, `copy`, `get`).
- Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01MQz45mnyMgWrdhLLmWDvqD
  ```

## File Map

| File | Change |
|---|---|
| `pyproject.toml`, `uv.lock`, `.python-version`, `VERSION`, `LICENSE`, `.gitattributes` | Create (Task 1) |
| `requirements.txt`, `requirements-dev.txt`, `run.sh`, `run.ps1` | Delete (Task 1) |
| `tests/test_repo_hygiene.py` | Create (Task 1), extend (Task 2) |
| `tests/test_live.py`, `tests/test_links.py`, old spec/plan docs | Scrub to CC examples (Task 1) |
| `Start retro-ears.command`, `Start retro-ears.bat`, `tests/test_launchers.py` | Create (Task 2) |
| `app.py` | Second-launch handling (Task 2), version/update routes (Task 3), devices + destination (Task 4) |
| `updates.py`, `tests/test_updates.py` | Create (Task 3) |
| `jobs.py` | `busy()` (Task 3), iPod destination (Task 4) |
| `devices.py`, `ipod.py`, `tests/test_devices.py`, `tests/test_ipod.py` | Create (Task 4) |
| `download.py` | `Result.art` (Task 4) |
| `static/index.html` | Footer, banner, update button (Task 3); Save-to menu (Task 4) |
| `scripts/build_release.py`, `tests/test_build_release.py`, `.github/workflows/ci.yml`, `.github/workflows/release.yml` | Create (Task 5) |
| `README.md`, `docs/images/*.png` | Rewrite / create (Task 6) |

---

### Task 1: uv project, license and Creative Commons examples

**Files:**
- Create: `pyproject.toml`, `.python-version`, `VERSION`, `LICENSE`, `.gitattributes`, `uv.lock` (generated), `tests/test_repo_hygiene.py`
- Modify: `.gitignore`, `tests/test_live.py` (rewrite), `tests/test_links.py`, `docs/superpowers/specs/2026-09-14-retro-ears-design.md`, `docs/superpowers/plans/2026-09-14-retro-ears.md`
- Delete: `requirements.txt`, `requirements-dev.txt`, `run.sh`, `run.ps1`

**Interfaces:**
- Consumes: existing modules unchanged.
- Produces: `VERSION` file containing `1.0.0` (no trailing newline); `uv sync` / `uv run` work from the repo root.

- [ ] **Step 1: Write the failing test `tests/test_repo_hygiene.py`**

```python
import codecs
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Major-label names and IDs that must never appear in the repo. ROT13-encoded so this file doesn't contain them.
BANNED = [
    codecs.decode(term, "rot13")
    for term in (
        "jrrxaq", "oyvaqvat yvtugf", "fgneobl", "qnsg chax", "zvpunry wnpxfba", "zbetna jnyyra", "gnzr vzcnyn",
        "37v9qDMS1Q", "cy.s4q106srq", "W7c4omdYiPj", "3_t2ha5Z350", "4AEKk6H8NOD",
        "4lC0uqXBMCAfukHBwL0pMw", "7oknSM1B3pUxtYXZfqP3kE", "nsgre-ubhef/1499378108",
    )
]
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".zip"}


def tracked_files():
    output = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    for name in output.splitlines():
        path = ROOT / name
        if path.name in {"test_repo_hygiene.py", "uv.lock"} or path.suffix.lower() in SKIP_SUFFIXES or not path.is_file():
            continue
        yield path


def test_no_major_label_music_references():
    offenders = []
    for path in tracked_files():
        text = path.read_text("utf-8", errors="ignore").lower()
        offenders += [f"{path.relative_to(ROOT)}: {term}" for term in BANNED if term.lower() in text]
    assert offenders == []


def test_version_file_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", (ROOT / "VERSION").read_text("utf-8").strip())


def test_pyproject_version_matches_version_file():
    pyproject = (ROOT / "pyproject.toml").read_text("utf-8")
    version = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE).group(1)
    assert version == (ROOT / "VERSION").read_text("utf-8").strip()


def test_old_install_files_are_gone():
    for name in ("requirements.txt", "requirements-dev.txt", "run.sh", "run.ps1"):
        assert not (ROOT / name).exists(), name


def test_license_is_gpl3():
    text = (ROOT / "LICENSE").read_text("utf-8")
    assert "GNU GENERAL PUBLIC LICENSE" in text
    assert "Version 3, 29 June 2007" in text
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_repo_hygiene.py -v`
Expected: FAIL — music references found in tests and old docs; `VERSION`, `pyproject.toml`, `LICENSE` missing; old install files present.

- [ ] **Step 3: Create project metadata**

`pyproject.toml`:
```toml
[project]
name = "retro-ears"
version = "1.0.0"
description = "Search songs and playlists and download iPod-ready music."
readme = "README.md"
license = "GPL-3.0-or-later"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "yt-dlp[default]>=2026.8.19",
    "ytmusicapi>=1.12",
    "mutagen>=1.48",
    "pillow>=11.0",
    "imageio-ffmpeg>=0.6",
    "deno>=2.9",
    "httpx>=0.28",
    "certifi>=2024.2.2",
]

[dependency-groups]
dev = ["pytest>=8.0"]

[tool.uv]
package = false
```

`.python-version` (one line): `3.12`

`VERSION` — write exactly `1.0.0` with **no trailing newline**:
```bash
printf '1.0.0' > VERSION
```

`.gitattributes`:
```
*.command text eol=lf
*.sh text eol=lf
*.bat text eol=crlf
```

Append to `.gitignore`:
```
.runtime/
dist/
```

- [ ] **Step 4: Add the GPL-3.0 license and remove old install files**

```bash
curl -fsSL https://www.gnu.org/licenses/gpl-3.0.txt -o LICENSE
git rm -q requirements.txt requirements-dev.txt run.sh run.ps1
```

- [ ] **Step 5: Scrub music references from tests and old docs**

```bash
python3 - <<'SCRUB'
import codecs
from pathlib import Path

# (ROT13 of the text to remove, replacement)
REPLACEMENTS = [
    ("gur jrrxaq oyvaqvat yvtugf", "kevin macleod kool kats"),
    ("Oyvaqvat Yvtugf", "Kool Kats"),
    ("oyvaqvat yvtugf", "kool kats"),
    ("Gur Jrrxaq", "Kevin MacLeod"),
    ("Orng Vg — Zvpunry Wnpxfba", "Carefree — Kevin MacLeod"),
    ("Fgneobl", "The Descent"),
    ("gbqnlf-uvgf/cy.s4q106srq2oq41149nnnpnoo233ro5ro", "calm-mix/pl.u-0000000000000"),
    ("37v9qDMS1QKpOJVTbLOZ5Z", "1a2B3c4D5e6F7g8H9i0JkL"),
    ("W7c4omdYiPj", "5viHgHli590"),
    ("4lC0uqXBMCAfukHBwL0pMw", "5G34ftqKz03s5y2No2eRu3"),
    ("nsgre-ubhef/1499378108", "light-electronic/1887659157"),
    ("7oknSM1B3pUxtYXZfqP3kE", "9zY8xW7vU6tS5rQ4pO3nMl"),
]
FILES = [
    "tests/test_links.py",
    "docs/superpowers/specs/2026-09-14-retro-ears-design.md",
    "docs/superpowers/plans/2026-09-14-retro-ears.md",
]
for name in FILES:
    path = Path(name)
    text = path.read_text("utf-8")
    for encoded, replacement in REPLACEMENTS:
        text = text.replace(codecs.decode(encoded, "rot13"), replacement)
    path.write_text(text, "utf-8")
    print("scrubbed", name)
SCRUB
```

Then replace `tests/test_live.py` entirely:

```python
"""Network tests. Run with: uv run pytest -m live -s
All media is Kevin MacLeod (incompetech.com), licensed CC BY 4.0."""
import mutagen
import pytest

import download
import links
import ytmusic
from models import Track

pytestmark = pytest.mark.live

SONG = Track(
    title="Kool Kats",
    artist="Kevin MacLeod",
    duration_s=202,
    art_url="https://i.ytimg.com/vi/5viHgHli590/hqdefault.jpg",
    video_id="5viHgHli590",
)
LABEL_PREFIX = {"m4a": "AAC", "opus": "Opus", "mp3": "MP3 320"}
SPOTIFY_ALBUM = "https://open.spotify.com/album/5G34ftqKz03s5y2No2eRu3"
APPLE_ALBUM = "https://music.apple.com/us/album/light-electronic/1887659157"


@pytest.mark.parametrize("fmt", download.FORMATS)
def test_download_real_song(tmp_path, fmt):
    result = download.fetch(SONG, fmt, tmp_path)
    print(f"\n{fmt}: {result.quality}")
    assert result.path.suffix == f".{fmt}"
    assert result.path.stat().st_size > 1_000_000
    assert result.quality.startswith(LABEL_PREFIX[fmt])
    audio = mutagen.File(result.path, easy=True)
    assert audio["title"] == ["Kool Kats"]
    assert audio["artist"] == ["Kevin MacLeod"]


def test_search_songs_live():
    songs = ytmusic.search_songs("kevin macleod", limit=5)
    assert songs and all(song.video_id for song in songs)


def test_search_and_open_playlist_live():
    playlists = ytmusic.search_playlists("royalty free music", limit=5)
    assert playlists
    playlist = ytmusic.get_playlist(playlists[0].id)
    assert playlist.tracks and all(track.video_id for track in playlist.tracks)


def test_match_live():
    matched = ytmusic.match(Track(title="Kool Kats", artist="Kevin MacLeod", duration_s=202))
    assert matched.video_id


def test_spotify_album_live():
    playlist = links.resolve(SPOTIFY_ALBUM, "songs")["playlist"]
    assert playlist.tracks and all(track.artist == "Kevin MacLeod" for track in playlist.tracks)


def test_apple_album_live():
    playlist = links.resolve(APPLE_ALBUM, "songs")["playlist"]
    assert playlist.tracks and all(track.artist == "Kevin MacLeod" for track in playlist.tracks)
```

- [ ] **Step 6: Lock and install with uv**

```bash
uv lock
uv sync
```
Expected: `uv.lock` created; `.venv` recreated on Python 3.12.

- [ ] **Step 7: Run all tests**

Run: `uv run pytest -v`
Expected: all passed, 0 failed (including `tests/test_repo_hygiene.py`).

Run: `uv run pytest -m live -s -v`
Expected: all passed. If `test_match_live` or a playlist test fails because YouTube Music results changed, pick another Kevin MacLeod title/query that returns results and keep the test otherwise identical.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "build: switch to a uv project, add GPL-3.0 license, use CC test media"
```

---

### Task 2: Double-click launchers and second-launch handling

**Files:**
- Create: `Start retro-ears.command`, `Start retro-ears.bat`, `tests/test_launchers.py`
- Modify: `app.py` (imports, new `port_status`, `main`), `tests/test_app.py` (append), `tests/test_repo_hygiene.py` (append)

**Interfaces:**
- Consumes: `VERSION` (Task 1), `app.create_app`, `jobs.clear_root`.
- Produces:
  - `app.port_status(host: str = HOST, port: int = PORT, timeout: float = 2.0) -> str` returning `"free"`, `"retro-ears"` or `"other"` (checks `GET /api/version`, which Task 3 adds).
  - Launchers set `RETRO_UV`, `UV_PYTHON_INSTALL_DIR`, `UV_CACHE_DIR`, `UV_PROJECT_ENVIRONMENT`, `UV_PYTHON_PREFERENCE` and restart on exit code 42.

- [ ] **Step 1: Write the failing launcher tests `tests/test_launchers.py`**

```python
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MAC = "Start retro-ears.command"
WIN = "Start retro-ears.bat"

FAKE_UV_SH = """#!/bin/bash
echo "$(basename "$0") $*" >> "$FAKE_LOG"
echo "env RETRO_UV=$RETRO_UV UV_PROJECT_ENVIRONMENT=$UV_PROJECT_ENVIRONMENT UV_PYTHON_PREFERENCE=$UV_PYTHON_PREFERENCE" >> "$FAKE_LOG"
if [ "$1" = "sync" ]; then exit "${FAKE_SYNC_EXIT:-0}"; fi
count=$(cat "$FAKE_COUNT" 2>/dev/null || echo 0)
count=$((count + 1))
echo "$count" > "$FAKE_COUNT"
codes=(${FAKE_RUN_CODES:-0})
exit "${codes[$((count - 1))]:-0}"
"""

FAKE_UV_CMD = "\r\n".join([
    "@echo off",
    'echo uv %*>>"%FAKE_LOG%"',
    'echo env RETRO_UV=%RETRO_UV% UV_PROJECT_ENVIRONMENT=%UV_PROJECT_ENVIRONMENT%>>"%FAKE_LOG%"',
    'if "%1"=="sync" exit /b %FAKE_SYNC_EXIT%',
    'set /p N=<"%FAKE_COUNT%"',
    "set /a N=N+1",
    '>"%FAKE_COUNT%" echo %N%',
    'if "%N%"=="1" exit /b %FAKE_FIRST_RUN_EXIT%',
    "exit /b 0",
]) + "\r\n"


def make_app(tmp_path, launcher):
    app = tmp_path / "retro-ears"
    app.mkdir()
    shutil.copy(ROOT / launcher, app / launcher)
    (app / "VERSION").write_text("9.9.9", "utf-8")
    return app


def commands(log):
    return [line for line in log.splitlines() if not line.startswith("env ")]


@pytest.mark.skipif(sys.platform == "win32", reason="macOS launcher")
class TestMacLauncher:
    def launch(self, app, tmp_path, *, bundled=True, sync_exit="0", run_codes="0", path="/usr/bin:/bin"):
        log, count = tmp_path / "uv.log", tmp_path / "count"
        if bundled:
            (app / "bin").mkdir(exist_ok=True)
            for name in ("uv-arm64", "uv-x86_64"):
                fake = app / "bin" / name
                fake.write_text(FAKE_UV_SH, "utf-8")
                fake.chmod(0o755)
        env = {
            "PATH": path, "HOME": str(tmp_path), "RETRO_NO_PAUSE": "1", "FAKE_LOG": str(log),
            "FAKE_COUNT": str(count), "FAKE_SYNC_EXIT": sync_exit, "FAKE_RUN_CODES": run_codes,
        }
        result = subprocess.run(["bash", str(app / MAC), "--no-browser"], env=env, capture_output=True, text=True, timeout=30)
        return result, log.read_text("utf-8") if log.exists() else ""

    def test_first_run_sets_up_then_restarts_on_42(self, tmp_path):
        app = make_app(tmp_path, MAC)
        result, log = self.launch(app, tmp_path, run_codes="42 0")
        uv = "uv-arm64" if platform.machine() == "arm64" else "uv-x86_64"
        run = f"{uv} run --no-sync python app.py --no-browser"
        assert commands(log) == [f"{uv} sync --frozen --no-dev", run, run]
        assert "Setting up retro-ears — the first run takes 1–2 minutes…" in result.stdout
        assert "Restarting…" in result.stdout
        assert "retro-ears stopped. You can close this window." in result.stdout
        assert result.returncode == 0
        assert (app / ".runtime" / "installed-version").read_text("utf-8") == "9.9.9"
        env_line = next(line for line in log.splitlines() if line.startswith("env "))
        assert f"RETRO_UV={app / 'bin' / uv}" in env_line
        assert f"UV_PROJECT_ENVIRONMENT={app / '.runtime' / 'venv'}" in env_line
        assert "UV_PYTHON_PREFERENCE=only-managed" in env_line

    def test_same_version_skips_setup(self, tmp_path):
        app = make_app(tmp_path, MAC)
        (app / ".runtime").mkdir()
        (app / ".runtime" / "installed-version").write_text("9.9.9", "utf-8")
        result, log = self.launch(app, tmp_path)
        assert not any(" sync " in line for line in commands(log))
        assert "Setting up" not in result.stdout

    def test_new_version_sets_up_again(self, tmp_path):
        app = make_app(tmp_path, MAC)
        (app / ".runtime").mkdir()
        (app / ".runtime" / "installed-version").write_text("1.0.0", "utf-8")
        _, log = self.launch(app, tmp_path)
        assert " sync --frozen --no-dev" in commands(log)[0]

    def test_setup_failure_stops(self, tmp_path):
        app = make_app(tmp_path, MAC)
        result, log = self.launch(app, tmp_path, sync_exit="1")
        assert result.returncode == 1
        assert "Setup failed — check your internet connection and try again" in result.stdout
        assert not any(" run " in line for line in commands(log))
        assert not (app / ".runtime" / "installed-version").exists()

    def test_other_exit_codes_end_the_loop(self, tmp_path):
        app = make_app(tmp_path, MAC)
        result, log = self.launch(app, tmp_path, run_codes="1")
        assert result.returncode == 1
        assert len([line for line in commands(log) if " run " in line]) == 1

    def test_uses_uv_from_path_when_not_bundled(self, tmp_path):
        tools = tmp_path / "tools"
        tools.mkdir()
        fake = tools / "uv"
        fake.write_text(FAKE_UV_SH, "utf-8")
        fake.chmod(0o755)
        app = make_app(tmp_path, MAC)
        _, log = self.launch(app, tmp_path, bundled=False, path=f"{tools}:/usr/bin:/bin")
        assert commands(log)[0] == "uv sync --frozen --no-dev"

    def test_without_uv_points_to_releases(self, tmp_path):
        app = make_app(tmp_path, MAC)
        result, _ = self.launch(app, tmp_path, bundled=False)
        assert result.returncode == 1
        assert "Download retro-ears from https://github.com/kandooswill/retro-ears/releases" in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher")
class TestWindowsLauncher:
    def launch(self, app, tmp_path, *, sync_exit="0", first_run_exit="0", with_uv=True):
        tools = tmp_path / "tools"
        tools.mkdir(exist_ok=True)
        if with_uv:
            (tools / "uv.cmd").write_bytes(FAKE_UV_CMD.encode("ascii"))
        log, count = tmp_path / "uv.log", tmp_path / "count"
        count.write_text("0")
        env = {
            **os.environ, "PATH": f"{tools};{os.environ['SystemRoot']}\\System32", "RETRO_NO_PAUSE": "1",
            "FAKE_LOG": str(log), "FAKE_COUNT": str(count), "FAKE_SYNC_EXIT": sync_exit, "FAKE_FIRST_RUN_EXIT": first_run_exit,
        }
        result = subprocess.run(f'"{app / WIN}" --no-browser', shell=True, env=env, capture_output=True, text=True, timeout=60)
        return result, log.read_text() if log.exists() else ""

    def test_first_run_sets_up_then_restarts_on_42(self, tmp_path):
        app = make_app(tmp_path, WIN)
        result, log = self.launch(app, tmp_path, first_run_exit="42")
        run = "uv run --no-sync python app.py --no-browser"
        assert commands(log) == ["uv sync --frozen --no-dev", run, run]
        assert "Restarting..." in result.stdout
        assert (app / ".runtime" / "installed-version").read_text() == "9.9.9"
        assert f"UV_PROJECT_ENVIRONMENT={app}\\.runtime\\venv" in log

    def test_setup_failure_stops(self, tmp_path):
        app = make_app(tmp_path, WIN)
        result, log = self.launch(app, tmp_path, sync_exit="1")
        assert result.returncode == 1
        assert "Setup failed - check your internet connection and try again" in result.stdout
        assert not any(" run " in line for line in commands(log))

    def test_without_uv_points_to_releases(self, tmp_path):
        app = make_app(tmp_path, WIN)
        result, _ = self.launch(app, tmp_path, with_uv=False)
        assert result.returncode == 1
        assert "Download retro-ears from https://github.com/kandooswill/retro-ears/releases" in result.stdout
```

- [ ] **Step 2: Append second-launch tests to `tests/test_app.py`**

Add these imports at the top of the file:
```python
import http.server
import json
import socket
import threading
```

Append:
```python
def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_port_status_free():
    assert app_module.port_status(port=free_port()) == "free"


def test_port_status_other_program():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        assert app_module.port_status(port=listener.getsockname()[1], timeout=0.5) == "other"


def test_port_status_retro_ears_already_running():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"app": "1.0.0"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert app_module.port_status(port=server.server_address[1]) == "retro-ears"
    finally:
        server.shutdown()
        server.server_close()


def test_main_opens_the_running_copy(monkeypatch, capsys):
    opened = []
    monkeypatch.setattr(app_module, "port_status", lambda **kwargs: "retro-ears")
    monkeypatch.setattr(app_module.webbrowser, "open", opened.append)
    monkeypatch.setattr(app_module.sys, "argv", ["app.py"])
    with pytest.raises(SystemExit) as exit_info:
        app_module.main()
    assert exit_info.value.code == 0
    assert "retro-ears is already running" in capsys.readouterr().out
    assert opened == ["http://127.0.0.1:8787"]


def test_main_port_taken_by_another_program(monkeypatch, capsys):
    monkeypatch.setattr(app_module, "port_status", lambda **kwargs: "other")
    monkeypatch.setattr(app_module.sys, "argv", ["app.py", "--no-browser"])
    with pytest.raises(SystemExit) as exit_info:
        app_module.main()
    assert exit_info.value.code == 1
    assert "Port 8787 is in use by another program" in capsys.readouterr().out
```

- [ ] **Step 3: Append launcher checks to `tests/test_repo_hygiene.py`**

```python
def test_mac_launcher_is_executable_in_git():
    output = subprocess.run(["git", "ls-files", "-s", "Start retro-ears.command"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert output.split()[0] == "100755"


def test_line_endings_are_pinned():
    text = (ROOT / ".gitattributes").read_text("utf-8")
    assert "*.command text eol=lf" in text
    assert "*.bat text eol=crlf" in text


def test_windows_launcher_is_ascii():
    (ROOT / "Start retro-ears.bat").read_bytes().decode("ascii")
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest tests/test_launchers.py tests/test_app.py tests/test_repo_hygiene.py -v`
Expected: FAIL — launcher files missing; `app.port_status` not defined.

- [ ] **Step 5: Write `Start retro-ears.command`**

```bash
#!/bin/bash
# Double-click to start retro-ears on macOS.
cd "$(dirname "$0")" || exit 1
APP_DIR="$(pwd)"

wait_for_key() {
  [ -n "$RETRO_NO_PAUSE" ] && return
  read -r -p "Press Return to close this window…" _
}

case "$(uname -m)" in
  arm64) BUNDLED_UV="$APP_DIR/bin/uv-arm64" ;;
  *) BUNDLED_UV="$APP_DIR/bin/uv-x86_64" ;;
esac

if [ -x "$BUNDLED_UV" ]; then
  UV="$BUNDLED_UV"
elif command -v uv >/dev/null 2>&1; then
  UV="$(command -v uv)"
else
  echo "Download retro-ears from https://github.com/kandooswill/retro-ears/releases"
  wait_for_key
  exit 1
fi

export UV_PYTHON_INSTALL_DIR="$APP_DIR/.runtime/python"
export UV_CACHE_DIR="$APP_DIR/.runtime/cache"
export UV_PROJECT_ENVIRONMENT="$APP_DIR/.runtime/venv"
export UV_PYTHON_PREFERENCE=only-managed
export RETRO_UV="$UV"

VERSION="$(tr -d '[:space:]' < VERSION)"
if [ "$(cat .runtime/installed-version 2>/dev/null)" != "$VERSION" ]; then
  echo "Setting up retro-ears — the first run takes 1–2 minutes…"
  if ! "$UV" sync --frozen --no-dev; then
    echo "Setup failed — check your internet connection and try again"
    wait_for_key
    exit 1
  fi
  mkdir -p .runtime
  printf '%s' "$VERSION" > .runtime/installed-version
fi

while true; do
  "$UV" run --no-sync python app.py "$@"
  code=$?
  if [ "$code" -eq 42 ]; then
    echo "Restarting…"
    continue
  fi
  break
done

echo "retro-ears stopped. You can close this window."
wait_for_key
exit "$code"
```

Then: `chmod +x "Start retro-ears.command" && git add "Start retro-ears.command"`

- [ ] **Step 6: Write `Start retro-ears.bat`** (ASCII only)

```bat
@echo off
setlocal
rem Double-click to start retro-ears on Windows.
cd /d "%~dp0"
set "APP_DIR=%CD%"

set "UV=%APP_DIR%\bin\uv.exe"
if exist "%UV%" goto have_uv
set "UV="
for /f "delims=" %%U in ('where uv 2^>nul') do if not defined UV set "UV=%%U"
if defined UV goto have_uv
echo Download retro-ears from https://github.com/kandooswill/retro-ears/releases
call :wait_for_key
exit /b 1

:have_uv
set "UV_PYTHON_INSTALL_DIR=%APP_DIR%\.runtime\python"
set "UV_CACHE_DIR=%APP_DIR%\.runtime\cache"
set "UV_PROJECT_ENVIRONMENT=%APP_DIR%\.runtime\venv"
set "UV_PYTHON_PREFERENCE=only-managed"
set "RETRO_UV=%UV%"

set /p VERSION=<VERSION
set "INSTALLED="
if exist ".runtime\installed-version" set /p INSTALLED=<".runtime\installed-version"
if "%INSTALLED%"=="%VERSION%" goto run

echo Setting up retro-ears - the first run takes 1-2 minutes...
"%UV%" sync --frozen --no-dev
if errorlevel 1 (
  echo Setup failed - check your internet connection and try again
  call :wait_for_key
  exit /b 1
)
if not exist ".runtime" mkdir ".runtime"
>".runtime\installed-version" <nul set /p "=%VERSION%"

:run
"%UV%" run --no-sync python app.py %*
set "CODE=%ERRORLEVEL%"
if "%CODE%"=="42" (
  echo Restarting...
  goto run
)
echo retro-ears stopped. You can close this window.
call :wait_for_key
exit /b %CODE%

:wait_for_key
if defined RETRO_NO_PAUSE exit /b 0
pause
exit /b 0
```

Then: `git add "Start retro-ears.bat" .gitattributes`

- [ ] **Step 7: Add `port_status` and the new `main()` to `app.py`**

Add to the imports at the top of `app.py`:
```python
import socket

import httpx
```

Add above `def main()`:
```python
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
```

Replace the whole `main()` function with:
```python
def main() -> None:
    import uvicorn

    url = f"http://{HOST}:{PORT}"
    status = port_status()
    if status == "retro-ears":
        print("retro-ears is already running")
        if "--no-browser" not in sys.argv:
            webbrowser.open(url)
        sys.exit(0)
    if status == "other":
        print(f"Port {PORT} is in use by another program")
        sys.exit(1)

    jobs.clear_root()
    if "--no-browser" not in sys.argv:
        threading.Timer(1.5, webbrowser.open, args=[url]).start()
    print(f"retro-ears is running at {url} — keep this window open; close it to stop.")
    uvicorn.run(create_app(), host=HOST, port=PORT, log_level="warning")
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `uv run pytest -v`
Expected: all passed, 0 failed (Windows launcher tests skipped on macOS).

- [ ] **Step 9: Smoke-test the real launcher**

Run in the background: `RETRO_NO_PAUSE=1 bash "Start retro-ears.command" --no-browser`
Then: `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8787/`
Expected: first run prints the setup message, creates `.runtime/` (Python 3.12 + packages), then `200`. Stop the launcher afterwards (`kill` the process on port 8787).

- [ ] **Step 10: Commit**

```bash
git add "Start retro-ears.command" "Start retro-ears.bat" .gitattributes app.py tests/test_launchers.py tests/test_app.py tests/test_repo_hygiene.py
git commit -m "feat: add double-click launchers for macOS and Windows"
```

---

### Task 3: Version check and one-click yt-dlp update

**Files:**
- Create: `updates.py`, `tests/test_updates.py`
- Modify: `jobs.py` (add `busy`), `tests/test_jobs.py` (append), `app.py` (`create_app` parameters, two routes), `tests/test_app.py` (`build_app` fakes + tests), `static/index.html` (banner, footer, update flow)

**Interfaces:**
- Consumes: `VERSION`, `RETRO_UV` env var set by the launchers (Task 2), `jobs.JobManager`.
- Produces:
  - `updates.RESTART_EXIT_CODE = 42`, `updates.STARTED: float`, `updates.CHECK_EVERY_S = 21600`
  - `updates.app_version() -> str`, `updates.ytdlp_version() -> str`, `updates.uv_path() -> Path | None`
  - `updates.parse_version(text: str) -> tuple[int, int, int] | None`, `updates.is_newer(candidate: str, current: str) -> bool`
  - `updates.fetch_latest() -> dict | None` (`{"tag", "url"}`), `updates.ReleaseChecker(fetch=fetch_latest, clock=time.monotonic)` with `.latest() -> dict | None`
  - `updates.version_info(checker) -> dict` (`app, ytdlp, can_update, latest_app, release_url, started`)
  - `updates.update_command(uv: Path) -> list[str]`, `updates.update_ytdlp(run=subprocess.run) -> bool`, `updates.schedule_restart(delay_s=1.0, exit=os._exit) -> threading.Timer`
  - `jobs.JobManager.busy() -> bool`
  - `app.create_app(manager=None, checker=None, restart=None)`; routes `GET /api/version`, `POST /api/update`

- [ ] **Step 1: Write the failing tests `tests/test_updates.py`**

```python
import subprocess
import sys

import httpx
import pytest

import updates


class FakeChecker:
    def __init__(self, latest=None):
        self._latest = latest

    def latest(self):
        return self._latest


@pytest.mark.parametrize(
    "candidate,current,newer",
    [("v1.1.0", "1.0.0", True), ("1.0.0", "1.0.0", False), ("v0.9.9", "1.0.0", False), ("v1.10.0", "1.9.0", True), ("latest", "1.0.0", False)],
)
def test_is_newer(candidate, current, newer):
    assert updates.is_newer(candidate, current) is newer


def test_app_version_reads_version_file():
    assert updates.app_version() == (updates.APP_DIR / "VERSION").read_text("utf-8").strip()


def test_release_checker_caches_for_six_hours():
    calls, now = [], [0.0]
    checker = updates.ReleaseChecker(fetch=lambda: calls.append(1) or {"tag": "v2.0.0", "url": "u"}, clock=lambda: now[0])
    assert checker.latest() == {"tag": "v2.0.0", "url": "u"}
    now[0] = updates.CHECK_EVERY_S - 1
    checker.latest()
    assert len(calls) == 1
    now[0] = updates.CHECK_EVERY_S
    checker.latest()
    assert len(calls) == 2


def test_release_checker_failure_gives_none():
    def boom():
        raise httpx.ConnectError("offline")

    assert updates.ReleaseChecker(fetch=boom).latest() is None


def test_fetch_latest_parses_github(monkeypatch):
    response = httpx.Response(
        200,
        json={"tag_name": "v1.2.0", "html_url": "https://github.com/kandooswill/retro-ears/releases/tag/v1.2.0"},
        request=httpx.Request("GET", updates.RELEASES_API),
    )
    monkeypatch.setattr(updates.httpx, "get", lambda *args, **kwargs: response)
    assert updates.fetch_latest() == {"tag": "v1.2.0", "url": "https://github.com/kandooswill/retro-ears/releases/tag/v1.2.0"}


def test_fetch_latest_without_releases(monkeypatch):
    response = httpx.Response(404, request=httpx.Request("GET", updates.RELEASES_API))
    monkeypatch.setattr(updates.httpx, "get", lambda *args, **kwargs: response)
    assert updates.fetch_latest() is None


def test_version_info_with_newer_release(monkeypatch, tmp_path):
    uv = tmp_path / "uv"
    uv.write_text("")
    monkeypatch.setenv("RETRO_UV", str(uv))
    monkeypatch.setattr(updates, "app_version", lambda: "1.0.0")
    info = updates.version_info(FakeChecker({"tag": "v1.1.0", "url": "https://example.com/release"}))
    assert info == {
        "app": "1.0.0", "ytdlp": updates.ytdlp_version(), "can_update": True,
        "latest_app": "1.1.0", "release_url": "https://example.com/release", "started": updates.STARTED,
    }


def test_version_info_hides_older_release(monkeypatch):
    monkeypatch.delenv("RETRO_UV", raising=False)
    monkeypatch.setattr(updates, "app_version", lambda: "1.0.0")
    info = updates.version_info(FakeChecker({"tag": "v0.1.0", "url": "https://example.com/old"}))
    assert (info["latest_app"], info["release_url"], info["can_update"]) == (None, None, False)


def test_uv_path_needs_an_existing_file(monkeypatch, tmp_path):
    monkeypatch.delenv("RETRO_UV", raising=False)
    assert updates.uv_path() is None
    monkeypatch.setenv("RETRO_UV", str(tmp_path / "missing"))
    assert updates.uv_path() is None


def test_update_command(tmp_path):
    assert updates.update_command(tmp_path / "uv") == [str(tmp_path / "uv"), "pip", "install", "--python", sys.executable, "--upgrade", "yt-dlp[default]"]


@pytest.mark.parametrize("outcome,expected", [(0, True), (1, False), ("timeout", False)])
def test_update_ytdlp(monkeypatch, tmp_path, outcome, expected):
    uv = tmp_path / "uv"
    uv.write_text("")
    monkeypatch.setenv("RETRO_UV", str(uv))

    def fake_run(command, **kwargs):
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(command, 300)
        return subprocess.CompletedProcess(command, outcome, "", "")

    assert updates.update_ytdlp(run=fake_run) is expected


def test_update_ytdlp_without_uv(monkeypatch):
    monkeypatch.delenv("RETRO_UV", raising=False)
    assert updates.update_ytdlp(run=lambda *args, **kwargs: pytest.fail("must not run")) is False


def test_schedule_restart_exits_with_42():
    codes = []
    timer = updates.schedule_restart(delay_s=0, exit=codes.append)
    timer.join(2)
    assert codes == [42]
```

- [ ] **Step 2: Append the busy test to `tests/test_jobs.py`**

```python
def test_busy_while_a_job_runs(tmp_path, fake_fetch, wait_job):
    release = threading.Event()
    base = fake_fetch()

    def slow_fetch(track, fmt, workdir):
        release.wait(5)
        return base(track, fmt, workdir)

    manager = manager_for(tmp_path, slow_fetch)
    assert manager.busy() is False
    job = manager.start(TRACKS[:1], "m4a", "Mix")
    assert manager.busy() is True
    release.set()
    wait_job(manager, job.id)
    assert manager.busy() is False
```

- [ ] **Step 3: Update `tests/test_app.py`**

Add `from pathlib import Path` to the imports and `ROOT = Path(__file__).resolve().parent.parent` below them. Replace the existing `build_app` function with:

```python
class FakeChecker:
    def __init__(self, latest=None):
        self._latest = latest

    def latest(self):
        return self._latest


def build_app(tmp_path, fake_fetch, manager=None, **overrides):
    manager = manager or jobs.JobManager(root=tmp_path / "jobs", fetch=fake_fetch(), match=lambda track: track)
    options = {"checker": FakeChecker(), "restart": lambda: None, **overrides}
    return app_module.create_app(manager=manager, **options)


def local_client(application):
    return TestClient(application, base_url="http://127.0.0.1:8787")
```

In `test_index_page`, add `assert 'id="updateBtn"' in response.text`. Append:

```python
def test_version_route(tmp_path, fake_fetch, monkeypatch):
    monkeypatch.delenv("RETRO_UV", raising=False)
    release = {"tag": "v99.0.0", "url": "https://github.com/kandooswill/retro-ears/releases/tag/v99.0.0"}
    info = local_client(build_app(tmp_path, fake_fetch, checker=FakeChecker(release))).get("/api/version").json()
    assert info["app"] == (ROOT / "VERSION").read_text("utf-8").strip()
    assert (info["latest_app"], info["release_url"], info["can_update"]) == ("99.0.0", release["url"], False)
    assert info["ytdlp"]
    assert isinstance(info["started"], float)


def test_update_needs_the_launcher(client, monkeypatch):
    monkeypatch.delenv("RETRO_UV", raising=False)
    response = client.post("/api/update")
    assert response.status_code == 400
    assert response.json() == {"error": "Updating only works when retro-ears is started with its launcher"}


def test_update_refused_while_downloading(tmp_path, fake_fetch, monkeypatch):
    uv = tmp_path / "uv"
    uv.write_text("")
    monkeypatch.setenv("RETRO_UV", str(uv))
    release = threading.Event()
    base = fake_fetch()

    def slow_fetch(track, fmt, workdir):
        release.wait(5)
        return base(track, fmt, workdir)

    manager = jobs.JobManager(root=tmp_path / "jobs", fetch=slow_fetch, match=lambda track: track)
    client = local_client(build_app(tmp_path, fake_fetch, manager=manager))
    client.post("/api/jobs", json={"tracks": [{"title": "a", "artist": "b", "video_id": "v"}]})
    response = client.post("/api/update")
    release.set()
    assert response.status_code == 409
    assert response.json() == {"error": "Wait for the current download to finish"}


def test_update_success_restarts(tmp_path, fake_fetch, monkeypatch):
    uv = tmp_path / "uv"
    uv.write_text("")
    monkeypatch.setenv("RETRO_UV", str(uv))
    monkeypatch.setattr(app_module.updates, "update_ytdlp", lambda: True)
    restarts = []
    client = local_client(build_app(tmp_path, fake_fetch, restart=lambda: restarts.append(True)))
    response = client.post("/api/update")
    assert response.json() == {"ok": True, "restarting": True}
    assert restarts == [True]


def test_update_failure_keeps_running(tmp_path, fake_fetch, monkeypatch):
    uv = tmp_path / "uv"
    uv.write_text("")
    monkeypatch.setenv("RETRO_UV", str(uv))
    monkeypatch.setattr(app_module.updates, "update_ytdlp", lambda: False)
    restarts = []
    client = local_client(build_app(tmp_path, fake_fetch, restart=lambda: restarts.append(True)))
    response = client.post("/api/update")
    assert response.status_code == 502
    assert response.json() == {"error": "Update failed — check your internet connection"}
    assert restarts == []
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest tests/test_updates.py tests/test_jobs.py tests/test_app.py -v`
Expected: FAIL — `No module named 'updates'`, `JobManager` has no `busy`, `create_app` rejects `checker`.

- [ ] **Step 5: Write `updates.py`**

```python
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
```

- [ ] **Step 6: Add `busy` to `jobs.JobManager`** (below `get`)

```python
    def busy(self) -> bool:
        return any(job.public()["status"] == "running" for job in list(self.jobs.values()))
```

- [ ] **Step 7: Add the routes to `app.py`**

Add `import updates` to the imports. Change the `create_app` signature and its first lines to:

```python
def create_app(manager: jobs.JobManager | None = None, checker=None, restart=None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    manager = manager or jobs.JobManager()
    checker = checker or updates.ReleaseChecker()
    restart = restart or updates.schedule_restart
```

Add these routes just before `return app`:

```python
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
```

- [ ] **Step 8: Add the banner, footer and update flow to `static/index.html`**

1. In the `<style>` block, insert before `  @media (max-width: 560px) {`:
```css
  .banner { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 20px; padding: 10px 14px; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; font-size: 14px; }
  .banner a { color: var(--accent); }
  .link-btn { padding: 0; border: 0; background: none; color: var(--muted); cursor: pointer; text-decoration: underline; }
  .link-btn:hover { color: var(--text); }
  .link-btn:disabled { cursor: default; text-decoration: none; }
  footer { margin-top: 40px; color: var(--muted); font-size: 13px; }
```

2. Replace `<div class="wrap">` + newline + `  <header>` with:
```html
<div class="wrap">
  <div class="banner" id="banner" hidden>
    <span id="bannerText"></span>
    <span><a id="bannerLink" href="#" target="_blank" rel="noopener">Download</a> · <button class="link-btn" id="bannerClose" type="button">Dismiss</button></span>
  </div>
  <header>
```

3. Replace `  </main>` + newline + `</div>` with:
```html
  </main>

  <footer id="footer" hidden>
    <span id="versions"></span>
    <button class="link-btn" id="updateBtn" type="button" hidden>Update yt-dlp</button>
  </footer>
</div>
```

4. Insert before `  /* ---------- wiring ---------- */`:
```js
  /* ---------- version & updates ---------- */

  const updateEls = {
    banner: $("#banner"), bannerText: $("#bannerText"), bannerLink: $("#bannerLink"), bannerClose: $("#bannerClose"),
    footer: $("#footer"), versions: $("#versions"), updateBtn: $("#updateBtn"),
  };
  let canUpdate = false;
  let startedAt = null;

  async function loadVersion() {
    try {
      const info = await api("/api/version");
      canUpdate = info.can_update;
      startedAt = info.started;
      updateEls.versions.textContent = `retro-ears ${info.app} · yt-dlp ${info.ytdlp}${info.can_update ? " · " : ""}`;
      updateEls.updateBtn.hidden = !info.can_update;
      updateEls.footer.hidden = false;
      if (info.latest_app && info.latest_app !== readStored("dismissedRelease", "")) {
        updateEls.bannerText.textContent = `retro-ears ${info.latest_app} is out`;
        updateEls.bannerLink.href = info.release_url;
        updateEls.bannerClose.onclick = () => {
          writeStored("dismissedRelease", info.latest_app);
          updateEls.banner.hidden = true;
        };
        updateEls.banner.hidden = false;
      }
    } catch { /* footer stays hidden */ }
  }

  async function updateYtdlp() {
    if (state.jobId) return nudgeBusy();
    const before = startedAt;
    updateEls.updateBtn.disabled = true;
    updateEls.updateBtn.textContent = "Updating…";
    setDock({ title: "Updating yt-dlp…" });
    try {
      await api("/api/update", { method: "POST" });
    } catch (error) {
      updateEls.updateBtn.disabled = false;
      updateEls.updateBtn.textContent = "Update yt-dlp";
      return setDock({ title: error.message, error: true, action: closeAction });
    }
    setDock({ title: "Restarting retro-ears…" });
    for (let attempt = 0; attempt < 60; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      try {
        const info = await api("/api/version");
        if (info.started !== before) return location.reload();
      } catch { /* still restarting */ }
    }
    setDock({ title: "retro-ears didn't restart — start it again with the launcher", error: true, action: closeAction });
  }
```

5. In `pollJob`, replace
```js
      results: single ? null : job.results,
      action: closeAction,
```
with
```js
      results: single ? null : job.results,
      action: job.failed > 0 && canUpdate ? { label: "Update yt-dlp", run: updateYtdlp } : closeAction,
```

6. At the end of the script, after `  els.format.addEventListener("change", () => writeStored("format", els.format.value));`, add:
```js

  updateEls.updateBtn.addEventListener("click", updateYtdlp);
  loadVersion();
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `uv run pytest -v`
Expected: all passed, 0 failed.

- [ ] **Step 10: Manual check through the launcher**

1. Start: `RETRO_NO_PAUSE=1 bash "Start retro-ears.command" --no-browser` (background).
2. `curl -s http://127.0.0.1:8787/api/version` → `can_update: true`, `app: "1.0.0"`.
3. Run the launcher a second time in the foreground → prints `retro-ears is already running` and exits 0.
4. Open `http://127.0.0.1:8787` in the headless browser (`browse` skill): the footer shows versions and **Update yt-dlp**. Click it → dock shows "Restarting retro-ears…" → page reloads with a new `started` value; launcher output shows `Restarting…`.
5. Stop the launcher.

- [ ] **Step 11: Commit**

```bash
git add updates.py jobs.py app.py static/index.html tests/test_updates.py tests/test_jobs.py tests/test_app.py
git commit -m "feat: show versions, flag new releases and update yt-dlp in one click"
```

---

### Task 4: Save straight to a Rockbox iPod

**Files:**
- Create: `devices.py`, `ipod.py`, `tests/test_devices.py`, `tests/test_ipod.py`
- Modify: `download.py` (`Result.art`), `jobs.py` (destination + copy), `app.py` (`find_devices`, `/api/devices`, job destination), `static/index.html` (Save-to menu), `tests/test_download.py`, `tests/test_jobs.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: `download.safe_filename`, `download.unique_path`, `download.Result`, `models.RetroError`, `models.Track`, `jobs.JobManager`, `app.create_app` (Task 3 signature).
- Produces:
  - `devices.Device(id: str, name: str, mount: Path, free_bytes: int)` with `.public() -> dict` (`id, name, free_bytes`)
  - `devices.candidate_mounts(platform: str | None = None, volumes: Path = Path("/Volumes")) -> list[Path]`
  - `devices.volume_name(mount: Path, platform: str | None = None) -> str`, `devices.find_rockbox(platform=None, volumes=Path("/Volumes")) -> list[Device]`
  - `ipod.destination_path(mount: Path, track: Track, ext: str) -> Path`
  - `ipod.copy_to_ipod(file: Path, track: Track, art: bytes | None, mount: Path) -> str` (`"Saved to iPod"` / `"Already on iPod"`; raises `RetroError("iPod disconnected")`, `RetroError("iPod is full")`)
  - `download.Result(path, quality, art: bytes | None = None)`
  - `jobs.JobManager(..., copy=ipod.copy_to_ipod)`, `.start(tracks, fmt, name, destination: Device | None = None)`; job status gains `destination_name`
  - `app.create_app(manager=None, checker=None, restart=None, find_devices=None)`; `GET /api/devices`; `POST /api/jobs` accepts `destination`

- [ ] **Step 1: Write the failing tests `tests/test_devices.py`**

```python
from pathlib import Path

import devices


def test_finds_rockbox_volumes_on_macos(tmp_path):
    (tmp_path / "IPOD" / ".rockbox").mkdir(parents=True)
    (tmp_path / "Backup").mkdir()
    (tmp_path / "notes.txt").write_text("x")
    found = devices.find_rockbox(platform="darwin", volumes=tmp_path)
    assert [(d.id, d.name, d.mount) for d in found] == [(str(tmp_path / "IPOD"), "IPOD", tmp_path / "IPOD")]
    assert found[0].free_bytes > 0


def test_missing_volumes_folder_finds_nothing(tmp_path):
    assert devices.find_rockbox(platform="darwin", volumes=tmp_path / "missing") == []


def test_windows_candidates_are_drives_d_to_z():
    assert [str(mount)[:2] for mount in devices.candidate_mounts("win32")] == [f"{letter}:" for letter in "DEFGHIJKLMNOPQRSTUVWXYZ"]


def test_other_platforms_have_no_candidates():
    assert devices.candidate_mounts("linux") == []


def test_windows_name_uses_label_or_drive_letter(monkeypatch):
    monkeypatch.setattr(devices, "_windows_label", lambda mount: "")
    assert devices.volume_name(Path("E:\\"), platform="win32") == "iPod (E:)"
    monkeypatch.setattr(devices, "_windows_label", lambda mount: "MY IPOD")
    assert devices.volume_name(Path("E:\\"), platform="win32") == "MY IPOD"


def test_windows_detection_checks_each_candidate(monkeypatch, tmp_path):
    ipod = tmp_path / "E"
    (ipod / ".rockbox").mkdir(parents=True)
    monkeypatch.setattr(devices, "candidate_mounts", lambda *args, **kwargs: [tmp_path / "D", ipod])
    monkeypatch.setattr(devices, "_windows_label", lambda mount: "MY IPOD")
    assert [d.name for d in devices.find_rockbox(platform="win32")] == ["MY IPOD"]


def test_device_public_hides_the_path_object():
    device = devices.Device(id="/Volumes/IPOD", name="IPOD", mount=Path("/Volumes/IPOD"), free_bytes=123)
    assert device.public() == {"id": "/Volumes/IPOD", "name": "IPOD", "free_bytes": 123}
```

- [ ] **Step 2: Write the failing tests `tests/test_ipod.py`**

```python
from types import SimpleNamespace

import pytest

import ipod
from models import RetroError, Track

TRACK = Track(title="Kool Kats", artist="Kevin MacLeod", album="Jazz Sampler")


@pytest.fixture
def mount(tmp_path):
    root = tmp_path / "IPOD"
    (root / ".rockbox").mkdir(parents=True)
    return root


def test_destination_path(mount):
    assert ipod.destination_path(mount, TRACK, "m4a") == mount / "Music" / "Kevin MacLeod" / "Jazz Sampler" / "Kevin MacLeod - Kool Kats.m4a"


def test_destination_path_without_album_and_with_unsafe_names(mount):
    track = Track(title="What: Now?", artist="Glass/Arcade")
    assert ipod.destination_path(mount, track, "opus") == mount / "Music" / "GlassArcade" / "Singles" / "GlassArcade - What Now.opus"


def test_copy_saves_song_and_cover(mount, silent_file, jpeg_bytes):
    song = silent_file("m4a")
    art = jpeg_bytes(progressive=False)
    assert ipod.copy_to_ipod(song, TRACK, art, mount) == "Saved to iPod"
    target = ipod.destination_path(mount, TRACK, "m4a")
    assert target.read_bytes() == song.read_bytes()
    assert (target.parent / "cover.jpg").read_bytes() == art
    assert list(target.parent.glob("*.part")) == []


def test_copy_skips_an_identical_song(mount, silent_file):
    song = silent_file("m4a")
    ipod.copy_to_ipod(song, TRACK, None, mount)
    assert ipod.copy_to_ipod(song, TRACK, None, mount) == "Already on iPod"
    assert len(list(ipod.destination_path(mount, TRACK, "m4a").parent.glob("*.m4a"))) == 1


def test_copy_keeps_a_different_file_with_the_same_name(mount, silent_file):
    target = ipod.destination_path(mount, TRACK, "m4a")
    target.parent.mkdir(parents=True)
    target.write_bytes(b"older song")
    song = silent_file("m4a")
    assert ipod.copy_to_ipod(song, TRACK, None, mount) == "Saved to iPod"
    assert target.read_bytes() == b"older song"
    assert (target.parent / "Kevin MacLeod - Kool Kats (2).m4a").read_bytes() == song.read_bytes()


def test_existing_cover_is_kept(mount, silent_file, jpeg_bytes):
    folder = ipod.destination_path(mount, TRACK, "m4a").parent
    folder.mkdir(parents=True)
    (folder / "cover.jpg").write_bytes(b"my cover")
    ipod.copy_to_ipod(silent_file("m4a"), TRACK, jpeg_bytes(), mount)
    assert (folder / "cover.jpg").read_bytes() == b"my cover"


def test_disconnected_ipod(tmp_path, silent_file):
    with pytest.raises(RetroError, match="iPod disconnected"):
        ipod.copy_to_ipod(silent_file("m4a"), TRACK, None, tmp_path / "GONE")


def test_full_ipod(mount, silent_file, monkeypatch):
    monkeypatch.setattr(ipod.shutil, "disk_usage", lambda path: SimpleNamespace(free=10))
    with pytest.raises(RetroError, match="iPod is full"):
        ipod.copy_to_ipod(silent_file("m4a"), TRACK, None, mount)
```

- [ ] **Step 3: Extend the existing tests**

`tests/test_download.py` — in `test_fetch_tags_renames_and_labels`, add after `assert result.quality == "AAC 130"`:
```python
    assert result.art[:2] == b"\xff\xd8"  # the cover art is returned for iPod copies
```

`tests/test_jobs.py` — add `from devices import Device` to the imports and append:
```python
def ipod_device(tmp_path):
    return Device(id=str(tmp_path / "IPOD"), name="IPOD", mount=tmp_path / "IPOD", free_bytes=10**9)


def test_ipod_job_copies_each_song_and_offers_no_file(tmp_path, fake_fetch, wait_job):
    copies = []

    def fake_copy(file, track, art, mount):
        copies.append((track.title, mount))
        return "Saved to iPod"

    device = ipod_device(tmp_path)
    manager = jobs.JobManager(root=tmp_path / "jobs", fetch=fake_fetch(), match=lambda track: track, copy=fake_copy)
    job = manager.start(TRACKS[:2], "m4a", "Mix", destination=device)
    status = wait_job(manager, job.id)
    assert status["destination_name"] == "IPOD"
    assert [r["saved"] for r in status["results"]] == ["Saved to iPod", "Saved to iPod"]
    assert sorted(copies) == [("Song 0", device.mount), ("Song 1", device.mount)]
    with pytest.raises(RetroError, match="These songs were saved to your iPod"):
        manager.file(job.id)


def test_ipod_copy_errors_count_as_failures(tmp_path, fake_fetch, wait_job):
    def full(file, track, art, mount):
        raise RetroError("iPod is full")

    manager = jobs.JobManager(root=tmp_path / "jobs", fetch=fake_fetch(), match=lambda track: track, copy=full)
    job = manager.start(TRACKS[:1], "m4a", "Mix", destination=ipod_device(tmp_path))
    status = wait_job(manager, job.id)
    assert (status["status"], status["done"], status["failed"]) == ("failed", 0, 1)
    assert status["results"] == [{"title": "Song 0", "artist": "Artist", "error": "iPod is full"}]


def test_download_jobs_say_downloads(tmp_path, fake_fetch, wait_job):
    manager = manager_for(tmp_path, fake_fetch())
    job = manager.start(TRACKS[:1], "m4a", "Mix")
    assert wait_job(manager, job.id)["destination_name"] == "Downloads"
```

`tests/test_app.py` — in `build_app`, change the options line to:
```python
    options = {"checker": FakeChecker(), "restart": lambda: None, "find_devices": lambda: [], **overrides}
```
Add `from devices import Device` to the imports; in `test_index_page` add `assert 'id="destination"' in response.text`; append:
```python
def test_devices_route(tmp_path, fake_fetch):
    device = Device(id="/Volumes/IPOD", name="IPOD", mount=Path("/Volumes/IPOD"), free_bytes=123)
    client = local_client(build_app(tmp_path, fake_fetch, find_devices=lambda: [device]))
    assert client.get("/api/devices").json() == [{"id": "/Volumes/IPOD", "name": "IPOD", "free_bytes": 123}]


def test_job_to_a_missing_ipod_is_rejected(client):
    response = client.post("/api/jobs", json={"tracks": [{"title": "a", "artist": "b", "video_id": "v"}], "destination": "/Volumes/NOPE"})
    assert response.status_code == 400
    assert response.json() == {"error": "iPod not found — plug it in and try again"}


def test_job_to_a_detected_ipod(tmp_path, fake_fetch):
    device = Device(id=str(tmp_path / "IPOD"), name="IPOD", mount=tmp_path / "IPOD", free_bytes=10**9)
    manager = jobs.JobManager(root=tmp_path / "jobs", fetch=fake_fetch(), match=lambda track: track, copy=lambda *args: "Saved to iPod")
    client = local_client(build_app(tmp_path, fake_fetch, manager=manager, find_devices=lambda: [device]))
    job_id = client.post("/api/jobs", json={"tracks": [{"title": "a", "artist": "b", "video_id": "v"}], "destination": device.id}).json()["id"]
    status = wait_for(client, job_id)
    assert (status["destination_name"], status["results"][0]["saved"]) == ("IPOD", "Saved to iPod")
    response = client.get(f"/api/jobs/{job_id}/file")
    assert response.status_code == 400
    assert response.json() == {"error": "These songs were saved to your iPod"}
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest tests/test_devices.py tests/test_ipod.py tests/test_download.py tests/test_jobs.py tests/test_app.py -v`
Expected: FAIL — `No module named 'devices'` / `'ipod'`, `Result` has no `art`, `JobManager` rejects `copy`.

- [ ] **Step 5: Write `devices.py`**

```python
"""Find plugged-in iPods running Rockbox."""
from __future__ import annotations

import shutil
import string
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Device:
    id: str
    name: str
    mount: Path
    free_bytes: int

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "free_bytes": self.free_bytes}


def candidate_mounts(platform: str | None = None, volumes: Path = Path("/Volumes")) -> list[Path]:
    platform = platform or sys.platform
    if platform == "win32":
        return [Path(f"{letter}:\\") for letter in string.ascii_uppercase[3:]]  # D: to Z:
    if platform == "darwin":
        try:
            return sorted(path for path in volumes.iterdir() if path.is_dir())
        except OSError:
            return []
    return []


def _windows_label(mount: Path) -> str:
    import ctypes

    buffer = ctypes.create_unicode_buffer(261)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(ctypes.c_wchar_p(str(mount)), buffer, len(buffer), None, None, None, None, 0)
    return buffer.value if ok else ""


def volume_name(mount: Path, platform: str | None = None) -> str:
    if (platform or sys.platform) == "win32":
        return _windows_label(mount) or f"iPod ({str(mount)[:2]})"
    return mount.name


def find_rockbox(platform: str | None = None, volumes: Path = Path("/Volumes")) -> list[Device]:
    found = []
    for mount in candidate_mounts(platform, volumes):
        try:
            if not (mount / ".rockbox").is_dir():
                continue
            free = shutil.disk_usage(mount).free
        except OSError:  # empty card readers and ejecting drives
            continue
        found.append(Device(id=str(mount), name=volume_name(mount, platform), mount=mount, free_bytes=free))
    return found
```

- [ ] **Step 6: Write `ipod.py`**

```python
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
```

- [ ] **Step 7: Return cover art from `download.fetch`**

In `download.py`, change the `Result` dataclass to:
```python
@dataclass
class Result:
    path: Path
    quality: str
    art: bytes | None = None
```
In `fetch`, replace
```python
        tags.write_tags(source, track, tags.fetch_art(track.art_url))
```
with
```python
        art = tags.fetch_art(track.art_url)
        tags.write_tags(source, track, art)
```
and the return line with
```python
        return Result(path=final, quality=quality_label(fmt, info.get("acodec"), info.get("abr")), art=art)
```

- [ ] **Step 8: Add the iPod destination to `jobs.py`**

1. Add imports: `import ipod` (after `import download`) and `from devices import Device` (before `from models import …`).
2. In the `Job` dataclass, add `destination: Device | None = None` directly above the `lock` field.
3. In `Job.public()`, add `"destination_name": self.destination.name if self.destination else "Downloads",` after `"cancelled": self.cancelled,`.
4. Change `JobManager.__init__` to accept and store `copy`:
```python
    def __init__(
        self,
        root: Path = ROOT,
        fetch: Callable = download.fetch,
        match: Callable = ytmusic.match,
        workers: int = WORKERS,
        copy: Callable = ipod.copy_to_ipod,
    ):
        self.root = root
        self.jobs: dict[str, Job] = {}
        self._fetch = fetch
        self._match = match
        self._workers = workers
        self._copy = copy
        root.mkdir(parents=True, exist_ok=True)
```
5. Change `start` to:
```python
    def start(self, tracks: list[Track], fmt: str, name: str, destination: Device | None = None) -> Job:
        if not tracks:
            raise ValueError("No songs to download")
        if fmt not in download.FORMATS:
            raise ValueError(f"Unknown format: {fmt}")
        self.cleanup()
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id, name=name.strip() or "retro-ears", fmt=fmt, tracks=list(tracks), dir=self.root / job_id, destination=destination)
        job.dir.mkdir(parents=True)
        self.jobs[job_id] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job
```
6. In `file`, insert right after the `"Still downloading"` check:
```python
            if job.destination:
                raise RetroError("These songs were saved to your iPod")
```
7. Replace the whole `_one` method with:
```python
    def _one(self, job: Job, track: Track) -> None:
        with job.lock:
            if job.cancelled:
                return
            job.current = f"{track.title} — {track.artist}"
        try:
            matched = self._match(track)
            result = self._fetch(matched, job.fmt, job.dir)
            saved = self._copy(result.path, matched, result.art, job.destination.mount) if job.destination else None
        except Exception as exc:  # one bad song must not stop the rest of the playlist
            with job.lock:
                job.failed += 1
                job.results.append({"title": track.title, "artist": track.artist, "error": (str(exc) or type(exc).__name__)[:200]})
            return
        entry = {"title": track.title, "artist": track.artist, "quality": result.quality}
        if saved:
            entry["saved"] = saved
        with job.lock:
            job.done += 1
            job.files.append(result.path)
            job.results.append(entry)
```

- [ ] **Step 9: Add devices and the job destination to `app.py`**

1. Add `import devices` to the imports.
2. Add to `JobIn`: `destination: str = Field(default="download", max_length=500)`.
3. Change the `create_app` signature and add the default:
```python
def create_app(manager: jobs.JobManager | None = None, checker=None, restart=None, find_devices=None) -> FastAPI:
```
and below `restart = restart or updates.schedule_restart`:
```python
    find_devices = find_devices or devices.find_rockbox
```
4. Replace the `start_job` route with:
```python
    @app.post("/api/jobs")
    def start_job(body: JobIn):
        destination = None
        if body.destination != "download":
            # Only a Rockbox iPod we can see right now, never an arbitrary path from the request.
            destination = next((device for device in find_devices() if device.id == body.destination), None)
            if destination is None:
                raise HTTPException(400, "iPod not found — plug it in and try again")
        try:
            job = manager.start([Track(**track.model_dump()) for track in body.tracks], body.format, body.name, destination=destination)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        return {"id": job.id}
```
5. Add before `return app`:
```python
    @app.get("/api/devices")
    def list_devices():
        return [device.public() for device in find_devices()]
```

- [ ] **Step 10: Add the Save-to menu to `static/index.html`**

1. In `<style>`, insert before `  @media (max-width: 560px) {`:
```css
  .toolbar-right { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
  .hint { margin: -4px 0 12px; color: var(--muted); font-size: 13px; }
```

2. Replace the Format label (from `    <label class="format">Format` through the toolbar's closing `  </div>`) with:
```html
    <div class="toolbar-right">
      <label class="format">Format
        <select id="format">
          <option value="m4a">AAC (.m4a) · iPod</option>
          <option value="opus">Opus · Rockbox</option>
          <option value="mp3">MP3 320</option>
        </select>
      </label>
      <label class="format">Save to
        <select id="destination">
          <option value="download">Downloads</option>
        </select>
      </label>
    </div>
  </div>
  <p class="hint" id="ipodHint">Rockbox iPod not found. Stock iPod? Download, then drag into Music or iTunes and sync.</p>
```

3. Insert before `  /* ---------- version & updates ---------- */`:
```js
  /* ---------- Rockbox iPods ---------- */

  const destEls = { select: $("#destination"), hint: $("#ipodHint") };

  async function refreshDevices() {
    if (document.hidden) return;
    let found = [];
    try { found = await api("/api/devices"); } catch { /* keep Downloads only */ }
    const current = destEls.select.value;
    destEls.select.replaceChildren(
      h("option", { value: "download" }, "Downloads"),
      ...found.map((device) => h("option", { value: device.id }, `${device.name} (Rockbox)`)));
    destEls.select.value = found.some((device) => device.id === current) ? current : "download";
    destEls.hint.hidden = found.length > 0;
  }
```

4. In `startJob`, replace `body: JSON.stringify({ tracks, format: els.format.value, name })` with:
```js
body: JSON.stringify({ tracks, format: els.format.value, name, destination: destEls.select.value })
```

5. In `setDock`, replace `result.error ? h("span", { class: "bad" }, result.error) : result.quality)));` with:
```js
result.error ? h("span", { class: "bad" }, result.error) : [result.quality, result.saved].filter(Boolean).join(" · "))));
```

6. In `pollJob`, replace everything from `    state.jobId = null;` to the end of the final `setDock({ … });` call with:
```js
    state.jobId = null;
    const toIpod = job.destination_name !== "Downloads";
    if (job.status === "done" && !toIpod) saveFile(id);
    const first = job.results[0] || {};
    let sub;
    if (toIpod) {
      const songs = `${job.done} song${job.done === 1 ? "" : "s"}`;
      sub = `Copied ${songs} to ${job.destination_name}${job.failed ? ` · ${job.failed} failed` : ""} — eject the iPod before unplugging`;
    } else if (single) {
      sub = job.done ? `Downloaded · ${first.quality}` : `Failed · ${first.error || "Cancelled"}`;
    } else {
      sub = `${job.done} done · ${job.failed} failed${job.cancelled ? " · cancelled" : ""}`;
    }
    setDock({
      title: job.name,
      sub,
      error: job.status === "failed",
      results: single && !toIpod ? null : job.results,
      action: job.failed > 0 && canUpdate ? { label: "Update yt-dlp", run: updateYtdlp } : closeAction,
    });
```

7. After `  loadVersion();` at the end of the script, add:
```js
  refreshDevices();
  setInterval(refreshDevices, 5000);
  document.addEventListener("visibilitychange", refreshDevices);
```

- [ ] **Step 11: Run the tests to verify they pass**

Run: `uv run pytest -v`
Expected: all passed, 0 failed.

- [ ] **Step 12: Manual check with a fake Rockbox iPod (FAT32 disk image)**

```bash
S=/private/tmp/claude-501/-Users-kushalsharma/21efb2ca-02fd-4b06-ac48-4074a9ed64cb/scratchpad
hdiutil create -size 64m -fs MS-DOS -volname RETROTEST "$S/retrotest.dmg"
hdiutil attach "$S/retrotest.dmg"
mkdir /Volumes/RETROTEST/.rockbox
```
1. Start the launcher (`RETRO_NO_PAUSE=1 bash "Start retro-ears.command" --no-browser`, background) and open `http://127.0.0.1:8787` in the headless browser.
2. Within 5 s the Save-to menu lists `RETROTEST (Rockbox)` and the hint disappears.
3. Search `kevin macleod`, choose Save to `RETROTEST (Rockbox)`, download two songs one after another.
4. `find /Volumes/RETROTEST/Music -type f` shows `Kevin MacLeod/<Album or Singles>/Kevin MacLeod - <Title>.m4a` plus `cover.jpg`; the dock says `Copied 1 song to RETROTEST — eject the iPod before unplugging`.
5. `hdiutil detach /Volumes/RETROTEST` → within 5 s the menu is back to Downloads and the hint returns.
6. Stop the launcher and delete `"$S/retrotest.dmg"`.

- [ ] **Step 13: Commit**

```bash
git add devices.py ipod.py download.py jobs.py app.py static/index.html tests/test_devices.py tests/test_ipod.py tests/test_download.py tests/test_jobs.py tests/test_app.py
git commit -m "feat: save songs straight to a Rockbox iPod"
```

---

### Task 5: Release zips, CI and release workflows

**Files:**
- Create: `scripts/build_release.py`, `tests/test_build_release.py`, `.github/workflows/ci.yml`, `.github/workflows/release.yml`

**Interfaces:**
- Consumes: every app file from §4.1 of the spec, both launchers (Task 2), `VERSION`.
- Produces:
  - `build_release.ROOT: Path`, `build_release.APP_FILES: list[str]`, `build_release.UV_ASSETS: dict`
  - `build_release.fetch_uv(asset: str, version: str, get=download) -> bytes` (verifies `.sha256`; `SystemExit("Checksum mismatch for <asset>")`)
  - `build_release.build(platform: str, uv_version: str, out: Path, get=download) -> Path` → `out/retro-ears-<platform>.zip`
  - CLI: `uv run python scripts/build_release.py --platform mac|windows [--uv-version 0.12.15] [--out dist]`

- [ ] **Step 1: Write the failing tests `tests/test_build_release.py`**

```python
import hashlib
import io
import tarfile
import zipfile

import pytest

from scripts import build_release


def fake_get():
    def tar_gz(folder):
        data = f"#!fake uv {folder}".encode()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            info = tarfile.TarInfo(f"{folder}/uv")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        return buffer.getvalue()

    def windows_zip():
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("uv.exe", b"MZ fake uv")
            archive.writestr("uvx.exe", b"MZ")
        return buffer.getvalue()

    archives = {
        "uv-aarch64-apple-darwin.tar.gz": tar_gz("uv-aarch64-apple-darwin"),
        "uv-x86_64-apple-darwin.tar.gz": tar_gz("uv-x86_64-apple-darwin"),
        "uv-x86_64-pc-windows-msvc.zip": windows_zip(),
    }

    def get(url):
        name = url.rsplit("/", 1)[1]
        if name.endswith(".sha256"):
            asset = name[: -len(".sha256")]
            return f"{hashlib.sha256(archives[asset]).hexdigest()}  {asset}\n".encode()
        return archives[name]

    return get


def mode(info):
    return (info.external_attr >> 16) & 0o777


def test_mac_zip(tmp_path):
    path = build_release.build("mac", "0.12.15", tmp_path, get=fake_get())
    assert path == tmp_path / "retro-ears-mac.zip"
    with zipfile.ZipFile(path) as archive:
        infos = {info.filename: info for info in archive.infolist()}
        assert {f"retro-ears/{name}" for name in build_release.APP_FILES} <= set(infos)
        assert "retro-ears/Start retro-ears.command" in infos
        assert not any(name.endswith(".bat") or "/tests/" in name or "/docs/" in name for name in infos)
        assert mode(infos["retro-ears/Start retro-ears.command"]) == 0o755
        assert mode(infos["retro-ears/bin/uv-arm64"]) == 0o755
        assert mode(infos["retro-ears/bin/uv-x86_64"]) == 0o755
        assert mode(infos["retro-ears/app.py"]) == 0o644
        assert archive.read("retro-ears/bin/uv-arm64") == b"#!fake uv uv-aarch64-apple-darwin"
        assert b"\r\n" not in archive.read("retro-ears/Start retro-ears.command")


def test_windows_zip(tmp_path):
    path = build_release.build("windows", "0.12.15", tmp_path, get=fake_get())
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        assert "retro-ears/Start retro-ears.bat" in names
        assert "retro-ears/bin/uv.exe" in names
        assert not any(name.endswith(".command") for name in names)
        assert archive.read("retro-ears/bin/uv.exe") == b"MZ fake uv"
        launcher = archive.read("retro-ears/Start retro-ears.bat")
        assert b"\n" not in launcher.replace(b"\r\n", b"")  # every line ends with CRLF


def test_checksum_mismatch_stops_the_build(tmp_path):
    good = fake_get()

    def tampered(url):
        return b"0" * 64 + b"  tampered\n" if url.endswith(".sha256") else good(url)

    with pytest.raises(SystemExit, match="Checksum mismatch"):
        build_release.build("windows", "0.12.15", tmp_path, get=tampered)


def test_every_app_module_is_packaged():
    modules = {path.name for path in build_release.ROOT.glob("*.py")}
    assert modules <= set(build_release.APP_FILES)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_build_release.py -v`
Expected: FAIL — `cannot import name 'build_release' from 'scripts'`.

- [ ] **Step 3: Write `scripts/build_release.py`**

```python
"""Build the downloadable retro-ears zips for macOS and Windows.

Usage: uv run python scripts/build_release.py --platform mac|windows [--uv-version 0.12.15] [--out dist]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import tarfile
import zipfile
from pathlib import Path
from typing import Callable

import certifi
import httpx

ROOT = Path(__file__).resolve().parent.parent
APP_FILES = [
    "app.py", "devices.py", "download.py", "ipod.py", "jobs.py", "links.py", "models.py", "tags.py", "updates.py", "ytmusic.py",
    "static/index.html", "pyproject.toml", "uv.lock", ".python-version", "VERSION", "README.md", "LICENSE",
]
LAUNCHERS = {"mac": "Start retro-ears.command", "windows": "Start retro-ears.bat"}
UV_ASSETS = {
    "mac": [("uv-aarch64-apple-darwin.tar.gz", "bin/uv-arm64"), ("uv-x86_64-apple-darwin.tar.gz", "bin/uv-x86_64")],
    "windows": [("uv-x86_64-pc-windows-msvc.zip", "bin/uv.exe")],
}
EXECUTABLE, REGULAR = 0o755, 0o644


def download(url: str) -> bytes:
    response = httpx.get(url, follow_redirects=True, timeout=120, verify=certifi.where())
    response.raise_for_status()
    return response.content


def extract_uv(asset: str, archive: bytes) -> bytes:
    if asset.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            return bundle.read("uv.exe")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        member = next(m for m in bundle.getmembers() if Path(m.name).name == "uv")
        return bundle.extractfile(member).read()


def fetch_uv(asset: str, version: str, get: Callable[[str], bytes] = download) -> bytes:
    url = f"https://github.com/astral-sh/uv/releases/download/{version}/{asset}"
    archive = get(url)
    expected = get(f"{url}.sha256").decode().split()[0]
    if hashlib.sha256(archive).hexdigest() != expected:
        raise SystemExit(f"Checksum mismatch for {asset}")
    return extract_uv(asset, archive)


def launcher_bytes(name: str) -> bytes:
    lf = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
    return lf.replace(b"\n", b"\r\n") if name.endswith(".bat") else lf  # cmd needs CRLF, bash needs LF


def add(bundle: zipfile.ZipFile, arcname: str, data: bytes, mode: int) -> None:
    info = zipfile.ZipInfo(f"retro-ears/{arcname}", date_time=(2026, 1, 1, 0, 0, 0))
    info.create_system = 3  # Unix, so Archive Utility keeps the executable bit
    info.external_attr = (0o100000 | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    bundle.writestr(info, data)


def build(platform: str, uv_version: str, out: Path, get: Callable[[str], bytes] = download) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"retro-ears-{platform}.zip"
    with zipfile.ZipFile(target, "w") as bundle:
        for name in APP_FILES:
            add(bundle, name, (ROOT / name).read_bytes(), REGULAR)
        launcher = LAUNCHERS[platform]
        add(bundle, launcher, launcher_bytes(launcher), EXECUTABLE)
        for asset, arcname in UV_ASSETS[platform]:
            add(bundle, arcname, fetch_uv(asset, uv_version, get), EXECUTABLE)
    return target


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build a retro-ears release zip.")
    parser.add_argument("--platform", choices=sorted(LAUNCHERS), required=True)
    parser.add_argument("--uv-version", default="0.12.15")
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    args = parser.parse_args(argv)
    print(build(args.platform, args.uv_version, args.out))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -v`
Expected: all passed, 0 failed.

- [ ] **Step 5: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [macos-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v7.0.1
      - uses: astral-sh/setup-uv@v10.1.0
      - run: uv sync --frozen
      - run: uv run pytest -v

  launcher-smoke:
    strategy:
      fail-fast: false
      matrix:
        os: [macos-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v7.0.1
      - uses: astral-sh/setup-uv@v10.1.0
      - name: Start the macOS launcher
        if: runner.os == 'macOS'
        run: RETRO_NO_PAUSE=1 nohup bash "Start retro-ears.command" --no-browser > launcher.log 2>&1 &
      - name: Start the Windows launcher
        if: runner.os == 'Windows'
        shell: pwsh
        run: |
          $env:RETRO_NO_PAUSE = "1"
          Start-Process -FilePath cmd.exe -ArgumentList '/c', '""Start retro-ears.bat" --no-browser > launcher.log 2>&1"' -WindowStyle Hidden
      - name: Wait for retro-ears to answer
        shell: bash
        run: |
          for attempt in $(seq 1 180); do
            if curl -fsS http://127.0.0.1:8787/api/version; then exit 0; fi
            sleep 1
          done
          cat launcher.log
          exit 1
```

- [ ] **Step 6: Write `.github/workflows/release.yml`**

```yaml
name: Release

on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7.0.1
      - uses: astral-sh/setup-uv@v10.1.0
      - name: Tag must match VERSION
        run: test "$GITHUB_REF_NAME" = "v$(tr -d '[:space:]' < VERSION)"
      - run: uv sync --frozen
      - run: uv run pytest
      - run: uv run python scripts/build_release.py --platform mac --out dist
      - run: uv run python scripts/build_release.py --platform windows --out dist
      - name: Publish the release
        env:
          GH_TOKEN: ${{ github.token }}
        run: >
          gh release create "$GITHUB_REF_NAME" dist/retro-ears-mac.zip dist/retro-ears-windows.zip
          --title "retro-ears $GITHUB_REF_NAME"
          --notes "Download the zip for your computer, unzip it, and double-click the Start file. Step-by-step guide: https://github.com/kandooswill/retro-ears#quick-start"
```

- [ ] **Step 7: Build a real mac zip and run it like a user would**

```bash
S=/private/tmp/claude-501/-Users-kushalsharma/21efb2ca-02fd-4b06-ac48-4074a9ed64cb/scratchpad
uv run python scripts/build_release.py --platform mac --out "$S/dist"
uv run python scripts/build_release.py --platform windows --out "$S/dist"
rm -rf "$S/unzipped" && mkdir "$S/unzipped" && ditto -x -k "$S/dist/retro-ears-mac.zip" "$S/unzipped"
ls -l "$S/unzipped/retro-ears/Start retro-ears.command" "$S/unzipped/retro-ears/bin"
```
Expected: both zips built (mac about 30–40 MB, Windows about 20 MB); the launcher and `bin/uv-*` show `-rwxr-xr-x`.

Then run the unzipped copy with a PATH that has no uv, so only the bundled binary can be used: `RETRO_NO_PAUSE=1 PATH=/usr/bin:/bin bash "$S/unzipped/retro-ears/Start retro-ears.command" --no-browser` (background), wait for `curl -fsS http://127.0.0.1:8787/api/version` to answer, confirm `can_update: true` and that `.runtime/` was created inside `$S/unzipped/retro-ears/`. Stop it and delete `$S/unzipped` and `$S/dist`.

- [ ] **Step 8: Commit**

```bash
git add scripts/build_release.py tests/test_build_release.py .github/workflows/ci.yml .github/workflows/release.yml
git commit -m "build: add release zip builder, CI and release workflows"
```

---

### Task 6: Friendly README with screenshots

**Files:**
- Modify: `README.md` (rewrite), `tests/test_repo_hygiene.py` (append)
- Create: `docs/images/search.png`, `docs/images/playlist.png`

**Interfaces:**
- Consumes: the finished app from Tasks 2–4 (for screenshots), release asset names from Task 5.
- Produces: README anchors `#quick-start` (linked from release notes).

- [ ] **Step 1: Append the failing README test to `tests/test_repo_hygiene.py`**

```python
def test_readme_screenshots_exist():
    readme = (ROOT / "README.md").read_text("utf-8")
    images = re.findall(r"\((docs/images/[^)]+\.png)\)", readme)
    assert images, "README should show screenshots"
    assert all((ROOT / image).is_file() for image in images)
    assert "## Quick start" in readme
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_repo_hygiene.py::test_readme_screenshots_exist -v`
Expected: FAIL — `README should show screenshots`.

- [ ] **Step 3: Take the screenshots**

1. Start the launcher in the background: `RETRO_NO_PAUSE=1 bash "Start retro-ears.command" --no-browser`.
2. With the `browse` skill: `viewport 1280x800`, `goto http://127.0.0.1:8787`, fill `#q` with `kevin macleod`, click `#searchForm button[type="submit"]`, wait for `#results li:first-child`, `screenshot --viewport docs/images/search.png`.
3. Fill `#q` with `https://open.spotify.com/album/5G34ftqKz03s5y2No2eRu3`, submit, wait for `.pl-head`, `screenshot --viewport docs/images/playlist.png`.
4. Shrink both if larger than 600 KB: `sips -Z 1600 docs/images/*.png`.
5. Look at both images (Read tool): only Kevin MacLeod music visible, no personal data. Stop the launcher.

- [ ] **Step 4: Rewrite `README.md`**

````markdown
# retro-ears

Search songs and playlists — or paste a YouTube, YouTube Music, Spotify or Apple Music link — and get music ready for your iPod, with title, artist, album and cover art built in. Works with stock iPods and Rockbox.

![retro-ears search results](docs/images/search.png)

**[Download retro-ears](https://github.com/kandooswill/retro-ears/releases/latest)** — free, for macOS and Windows.

## Quick start

### macOS

1. Download **retro-ears-mac.zip** from the [latest release](https://github.com/kandooswill/retro-ears/releases/latest) and double-click it to unzip.
2. Open the **retro-ears** folder and double-click **Start retro-ears.command**.
   - The first time, macOS says it can't verify the app. Click **Done**, open **System Settings → Privacy & Security**, scroll down, click **Open Anyway** next to "Start retro-ears.command", and confirm. You only do this once.
3. A Terminal window sets things up (1–2 minutes the first time), then retro-ears opens in your browser. Keep that window open while you use retro-ears; close it to quit.

### Windows

1. Download **retro-ears-windows.zip** from the [latest release](https://github.com/kandooswill/retro-ears/releases/latest), right-click it and choose **Extract All**.
2. Open the **retro-ears** folder and double-click **Start retro-ears.bat**.
   - If you see "Windows protected your PC", click **More info → Run anyway**. (Or, before extracting, right-click the zip → **Properties** → tick **Unblock**.)
3. A black window sets things up (1–2 minutes the first time), then your browser opens. Keep that window open; close it to quit.

There's nothing else to install: retro-ears downloads its own copy of Python into its folder.

## Using it

- Type a song or artist, or switch to **Playlists**. You can also paste a link.
- Pick a **Format**, then click **↓** next to a song, or **Download all** on a playlist (playlists arrive as one ZIP).

![A playlist ready to download](docs/images/playlist.png)

## Getting music onto your iPod

- **Stock iPod (Apple software):** choose **AAC (.m4a)**. Drag the downloaded files into the Music app (macOS) or iTunes / Apple Music (Windows), then sync your iPod.
- **Rockbox iPod:** plug it in and within a few seconds it appears under **Save to**. Pick it and songs are copied straight to `Music/Artist/Album/` with cover art. Eject the iPod before unplugging it. Windows can't read Mac-formatted iPods; Rockbox iPods are usually formatted FAT32 and work on both.

## Formats

| Format | What you get | Best for |
|---|---|---|
| **AAC (.m4a)** | YouTube's own AAC audio, not converted (about 130 kbps) | Stock iPod |
| **Opus** | YouTube's own Opus audio, not converted (about 130 kbps) | Rockbox |
| **MP3 320** | Converted from the best stream — plays anywhere, but isn't better than the source | Everything else |

Each finished song shows the quality it actually got.

## Updating

- **Downloads suddenly failing?** YouTube probably changed something. Click **Update yt-dlp** at the bottom of the page; retro-ears updates and restarts itself.
- **New retro-ears version?** A banner at the top links to it. Download the new zip and replace your old folder; the first start sets up again.

## FAQ

**Why about 130 kbps?** That's the best YouTube serves without its paid, bot-protected streams. High-resolution videos carry the same audio, and converting to MP3 320 can't add detail back.

**Can I use my YouTube Premium account for better quality?** No. Premium's 256 kbps streams need tokens that retro-ears doesn't generate.

**Why does a Spotify playlist stop at 100 songs?** Spotify's public page only lists the first 100.

**How do I uninstall?** Delete the retro-ears folder. Everything lives inside it.

**Is it safe to run?** retro-ears only runs on your own computer (`127.0.0.1`) and refuses connections from anywhere else.

## Troubleshooting

- **"Setup failed — check your internet connection and try again"** — the first start needs internet to fetch Python and packages. Connect and start again.
- **"Port 8787 is in use by another program"** — close the program using that port, or restart your computer.
- **My iPod isn't listed under Save to** — only Rockbox iPods (with a `.rockbox` folder) appear. Stock iPods sync through Music or iTunes.
- **Antivirus complains about uv.exe** — it's [uv](https://github.com/astral-sh/uv), the official tool retro-ears uses to install Python. Allow it.
- **Downloads fail** — click **Update yt-dlp**.

## Personal use

retro-ears is for personal use. You're responsible for what you download and for following copyright law and YouTube's terms. Screenshots show music by Kevin MacLeod ([incompetech.com](https://incompetech.com)), licensed CC BY 4.0.

## Development

```bash
uv sync
uv run pytest                   # offline tests
uv run pytest -m live -s        # real downloads of Creative Commons tracks
bash "Start retro-ears.command"  # macOS launcher (uses uv from PATH in a git clone)
```

To release: set the new version in `VERSION` and `pyproject.toml`, commit, then `git tag vX.Y.Z && git push origin vX.Y.Z`. GitHub Actions tests, builds both zips and publishes the release.

## License

[GPL-3.0](LICENSE)
````

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest -v`
Expected: all passed, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/images/search.png docs/images/playlist.png tests/test_repo_hygiene.py
git commit -m "docs: rewrite README for non-technical iPod owners"
```

---

### Task 7: Ship v1.0.0

**Files:** none (git, GitHub and manual checks)

**Interfaces:**
- Consumes: everything above.
- Produces: GitHub Release `v1.0.0` with `retro-ears-mac.zip` and `retro-ears-windows.zip`.

- [ ] **Step 1: Final local verification**

Run: `uv run pytest -v` → all passed. Run: `uv run pytest -m live -s -v` → all passed.

- [ ] **Step 2: Push and open the pull request**

```bash
git push -u origin feature/easy-install
gh pr create --base main --head feature/easy-install --title "Easy install: double-click launchers, one-click updates, Rockbox copy" --body-file "$TMPDIR/easy-install-pr.md"
```
Write `$TMPDIR/easy-install-pr.md` first: it summarises Tasks 1–6, lists verification results, notes Windows is CI-tested only, and ends with the Claude Code attribution lines.

- [ ] **Step 3: Get CI green**

Run: `gh pr checks --watch`
Expected: `test (macos-latest)`, `test (windows-latest)`, `launcher-smoke (macos-latest)`, `launcher-smoke (windows-latest)` all pass. Fix any failure on the branch (the Windows launcher tests have only ever run in CI), push, and re-watch.

- [ ] **Step 4: Merge — ask Kushal first**

After Kushal approves: `gh pr merge --merge` then `git checkout main && git pull`.

- [ ] **Step 5: Publish v1.0.0 — ask Kushal first**

After Kushal approves publishing the public release:
```bash
git tag v1.0.0
git push origin v1.0.0
gh run watch "$(gh run list --workflow release.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
gh release view v1.0.0
```
Expected: the release lists `retro-ears-mac.zip` and `retro-ears-windows.zip`.

- [ ] **Step 6: Kushal's hands-on check (macOS)**

Ask Kushal to:
1. Download `retro-ears-mac.zip` from the release page in Safari and unzip it.
2. Double-click `Start retro-ears.command`, follow the Privacy & Security → Open Anyway steps from the README.
3. Wait for first-run setup; search, download one song in AAC, open it in Music.
4. Click **Update yt-dlp** and confirm the page comes back.
5. Plug in the Rockbox iPod, pick it under **Save to**, copy two songs, eject, and play them on the iPod with cover art.

Record what worked and anything confusing in the README wording; fix wording issues in a follow-up PR.
