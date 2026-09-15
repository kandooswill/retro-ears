# retro-ears — Easy Install Design Spec

- **Date:** 2026-09-16
- **Status:** Design approved in brainstorming; written spec pending review
- **Owner:** Kushal
- **Builds on:** `docs/superpowers/specs/2026-09-14-retro-ears-design.md` (v2.1, merged in PR #1)

## 1. Goal

Anyone with a Mac or Windows PC — no terminal, no Python — can:

1. Download retro-ears from the GitHub Releases page.
2. Unzip it and double-click a launcher to run it.
3. Keep downloads working when YouTube breaks yt-dlp, with one button.
4. If their iPod runs Rockbox, save songs straight onto it.

## 2. Non-goals

- Paid code signing or notarization. Unsigned-app warnings are explained in the README.
- Real app bundles (`.app` / `.exe` built with PyInstaller or similar).
- Linux packaging. The repo still runs on Linux with `uv`, untested.
- Writing to a stock iPod's music library (iTunesDB). Stock iPods keep "drag into Music / iTunes and sync".
- retro-ears replacing its own files. A banner links to the new release instead.
- A landing page, or any hosted / public service.

## 3. Verified facts (2026-09-16)

| Fact | Evidence |
|---|---|
| `uv` 0.12.15 release assets: `uv-aarch64-apple-darwin.tar.gz` (15 MB), `uv-x86_64-apple-darwin.tar.gz` (19 MB), `uv-x86_64-pc-windows-msvc.zip` (16 MB), `uv-aarch64-pc-windows-msvc.zip` (18 MB) | GitHub releases API |
| `uv sync --frozen` installs the locked versions; `uv pip install --upgrade <pkg>` upgrades in place; `uv run --no-sync` keeps the upgrade; `uv run --frozen` re-syncs and silently downgrades it | Local probe with uv 0.11.23 (six 1.15.0 → 1.17.0 kept only with `--no-sync`) |
| `uv` downloads and uses a managed Python 3.12 when `.python-version` says 3.12 | Same probe ran Python 3.12.13 |
| Kevin MacLeod uploads that YouTube marks "Creative Commons Attribution license (reuse allowed)": `5viHgHli590` "Kool Kats" (202 s), `nLYAfzwBR8s` "The Descent" (191 s), `tw0DF6_1s6E` (235 s) | yt-dlp `license` field |
| youtube-dl's 2020 GitHub takedown cited its tests and README referencing copyrighted music videos | RIAA DMCA notice (public record) |
| Stock iPod firmware only plays songs listed in its iTunesDB; Rockbox plays files from its `Music` folder and is identified by a `.rockbox` folder at the drive root | Rockbox manual (not re-tested today) |

## 4. Release package

### 4.1 Layout

```
retro-ears-mac.zip
└── retro-ears/
    ├── Start retro-ears.command      (executable)
    ├── app.py  devices.py  download.py  ipod.py  jobs.py  links.py
    ├── models.py  tags.py  updates.py  ytmusic.py
    ├── static/index.html
    ├── pyproject.toml  uv.lock  .python-version  VERSION
    ├── bin/uv-arm64  bin/uv-x86_64   (executable)
    └── README.md  LICENSE

retro-ears-windows.zip
└── retro-ears\
    ├── Start retro-ears.bat
    ├── (same app files)
    ├── bin\uv.exe
    └── README.md  LICENSE
```

Tests, docs and CI files are not in the zips.

### 4.2 Project metadata

- `pyproject.toml`: `name = "retro-ears"`, `requires-python = ">=3.10"`, the current dependencies, a `dev` dependency group with `pytest`, and `[tool.uv] package = false`.
- `uv.lock` is committed. `.python-version` contains `3.12`.
- `VERSION` holds the app version (first release `1.0.0`) and is the single source of truth.
- `requirements.txt`, `requirements-dev.txt`, `run.sh` and `run.ps1` are removed.
- `.gitignore` adds `.runtime/` and `dist/`.

### 4.3 Launchers

Both launchers do the same steps:

1. Change to their own folder.
2. Pick `uv`: macOS uses `bin/uv-arm64` when `uname -m` is `arm64`, otherwise `bin/uv-x86_64`; Windows uses `bin\uv.exe`. If the bundled binary is missing (a git clone), use `uv` from PATH. If neither exists, print "Download retro-ears from https://github.com/kandooswill/retro-ears/releases" and wait for a key.
3. Keep everything inside the app folder:
   - `UV_PYTHON_INSTALL_DIR=<app>/.runtime/python`
   - `UV_CACHE_DIR=<app>/.runtime/cache`
   - `UV_PROJECT_ENVIRONMENT=<app>/.runtime/venv`
   - `UV_PYTHON_PREFERENCE=only-managed`
   - `RETRO_UV=<path to the uv binary>` (used by the update button)
4. If `.runtime/installed-version` is missing or differs from `VERSION`: print "Setting up retro-ears — the first run takes 1–2 minutes…", run `uv sync --frozen --no-dev`, then write `VERSION` into `.runtime/installed-version`. On failure print "Setup failed — check your internet connection and try again", wait for a key, and exit.
5. Loop: run `uv run --no-sync python app.py` (passing the launcher's own arguments, e.g. `--no-browser`). Exit code **42** means "restart after update": print "Restarting…" and run again. Any other exit code ends the loop.
6. After the loop: print "retro-ears stopped. You can close this window." (Windows: `pause`).

The app prints "retro-ears is running at http://127.0.0.1:8787 — keep this window open; close it to stop."

**Second launch:** if port 8787 is already taken and `GET http://127.0.0.1:8787/api/version` answers, the new process prints "retro-ears is already running", opens the browser to the running copy and exits with code 0. If the port is taken by something else, it prints "Port 8787 is in use by another program" and exits with code 1.

Deleting the `retro-ears` folder removes the app, its Python and all packages.

### 4.4 Unsigned-app warnings (documented in the README)

- **macOS:** the first double-click shows "Apple could not verify…". Click **Done**, open **System Settings → Privacy & Security**, click **Open Anyway** next to "Start retro-ears.command", then confirm.
- **Windows:** "Windows protected your PC" → **More info** → **Run anyway**. Alternative: right-click the zip → **Properties** → tick **Unblock** before extracting.

## 5. Updates — `updates.py`

### 5.1 Version endpoint

`GET /api/version` →

```json
{"app": "1.0.0", "ytdlp": "2026.08.19", "can_update": true, "latest_app": "1.1.0", "release_url": "https://github.com/kandooswill/retro-ears/releases/tag/v1.1.0"}
```

- `app` from `VERSION`; `ytdlp` from `yt_dlp.version.__version__`.
- `can_update` is true when `RETRO_UV` points to an existing file.
- `latest_app` / `release_url` come from `https://api.github.com/repos/kandooswill/retro-ears/releases/latest` (httpx + certifi, 5 s timeout), cached for 6 hours. Any failure gives `null` for both. `latest_app` is only returned when it is newer than `app` (compare `X.Y.Z` numerically; tags are `vX.Y.Z`).

### 5.2 Update yt-dlp

`POST /api/update`:

- 409 `{"error": "Wait for the current download to finish"}` if any job is running.
- 400 `{"error": "Updating only works when retro-ears is started with its launcher"}` if `can_update` is false.
- Runs `[RETRO_UV, "pip", "install", "--python", sys.executable, "--upgrade", "yt-dlp[default]"]` with a 300 s timeout.
- Success: returns `{"ok": true, "restarting": true}`, then exits the process with code 42 about 1 second later.
- Failure: 502 `{"error": "Update failed — check your internet connection"}`; the app keeps running.

### 5.3 UI

- **Footer:** `retro-ears 1.0.0 · yt-dlp 2026.08.19 · Update yt-dlp` (the button only when `can_update`).
- **Clicking Update:** the button reads "Updating…", then the dock shows "Restarting retro-ears…". The page polls `/api/version` every second for up to 60 s, then reloads. If it never comes back: "retro-ears didn't restart — start it again with the launcher".
- **After a job with failures**, when `can_update` is true, the dock also shows **Update yt-dlp** ("Downloads failing? YouTube may have changed — update yt-dlp").
- **Release banner** at the top when `latest_app` is set: "retro-ears 1.1.0 is out — Download". It links to `release_url` and can be dismissed per version (remembered in `localStorage`).

## 6. Save to a Rockbox iPod

### 6.1 Detection — `devices.py`

`find_rockbox() -> list[Device]`, where `Device(id: str, name: str, mount: Path, free_bytes: int)`:

- **macOS:** each `/Volumes/*` directory containing a `.rockbox` folder. `name` = volume name.
- **Windows:** drive letters `D:`–`Z:` containing `\.rockbox\`. `name` = volume label (via `GetVolumeInformationW`), falling back to `iPod (E:)`.
- `id` = the mount path as a string; `free_bytes` from `shutil.disk_usage`.

`GET /api/devices` → `[{"id": "/Volumes/IPOD", "name": "IPOD", "free_bytes": 12345}]`.

### 6.2 Copying — `ipod.py`

- `destination_path(mount: Path, track: Track, ext: str) -> Path` → `<mount>/Music/<Artist>/<Album or "Singles">/<Artist - Title>.<ext>`, every segment passed through `download.safe_filename`.
- `copy_to_ipod(file: Path, track: Track, art: bytes | None, mount: Path) -> str`:
  1. If `<mount>/.rockbox` no longer exists → `RetroError("iPod disconnected")`.
  2. If a file already exists at the destination with the same size → return `"Already on iPod"` without copying.
  3. If free space < file size + 1 MB → `RetroError("iPod is full")`.
  4. Create folders, copy to `<name>.part`, then rename to the final name (a different existing file gets ` (2)`).
  5. If art is available and the album folder has no `cover.jpg`, write it (the same baseline JPEG ≤ 600 px used for tags).
  6. Return `"Saved to iPod"`.
- `download.Result` gains `art: bytes | None` so the art isn't fetched twice.

### 6.3 Jobs and API

- `POST /api/jobs` accepts `destination`: `"download"` (default) or a device `id`.
- A device `id` must match a currently detected Rockbox iPod, otherwise 400 `{"error": "iPod not found — plug it in and try again"}`. This stops the API writing to arbitrary paths.
- For iPod jobs, each finished song is copied right after its download. The result entry gets `"saved": "Saved to iPod" | "Already on iPod"`, or an `error` from `copy_to_ipod`.
- Job status adds `destination_name` (`"Downloads"` or the iPod name). `GET /api/jobs/{id}/file` returns 400 `{"error": "These songs were saved to your iPod"}` for iPod jobs.

### 6.4 UI

- **Toolbar:** a **Save to** menu next to Format. Options: `Downloads` plus one entry per detected iPod (`<name> (Rockbox)`).
- **Detection:** the page polls `/api/devices` every 5 s while visible. If the selected iPod disappears, the menu switches back to Downloads.
- **No iPod found:** the menu shows only Downloads, with the hint "Rockbox iPod not found. Stock iPod? Download, then drag into Music or iTunes and sync."
- **iPod job finished:** the dock shows "Copied 23 songs to <name> · 2 failed — eject the iPod before unplugging". No browser download.

## 7. README and legal hygiene

- **README structure:**
  1. One-line pitch and a screenshot.
  2. **Download** (link to Releases).
  3. **Quick start**: three steps each for macOS and Windows, including the warning bypass from §4.4.
  4. **Getting music onto your iPod**: stock vs Rockbox.
  5. **Formats** table.
  6. **Updating**: the yt-dlp button, and the release banner.
  7. **FAQ**: why ~130 kbps is the ceiling, why there's no Premium login, Spotify's 100-song cap, uninstall = delete the folder.
  8. **Troubleshooting**: setup fails, port in use, iPod not detected, downloads failing.
  9. **Personal-use note.**
  10. **Development**: `uv sync`, `uv run pytest`, release steps.
  11. **License.**
- **Screenshots** in `docs/images/`, taken while searching Kevin MacLeod. Attribution: "Music shown: Kevin MacLeod (incompetech.com), CC BY 4.0."
- **No real song examples** in the README beyond the CC-licensed screenshots.
- **Replace major-label references:**
  - `tests/test_live.py`: download `5viHgHli590` ("Kool Kats", Kevin MacLeod); search for "kevin macleod"; match "Kool Kats" / "Kevin MacLeod"; Spotify and Apple link tests use a Kevin MacLeod album link (exact links chosen and pinned in the plan).
  - Both existing spec and plan docs: replace song and artist examples with fictional ones.
- **`LICENSE`:** full GPL-3.0 text.

## 8. CI and releases

- **`.github/workflows/ci.yml`** (push and pull request), matrix `macos-latest` and `windows-latest`:
  - `astral-sh/setup-uv`, then `uv sync --frozen`, then `uv run pytest`.
  - **Launcher smoke test:** start the platform launcher with `--no-browser` (uv from PATH), poll `http://127.0.0.1:8787/api/version` for up to 120 s, expect 200, then stop the process.
- **`scripts/build_release.py`** `--platform mac|windows --uv-version 0.12.15 --out dist/`:
  1. Download the matching `uv` assets and verify each against its published `.sha256`.
  2. Copy the app files listed in §4.1.
  3. Write `dist/retro-ears-<platform>.zip` with Unix permissions 755 on `Start retro-ears.command` and `bin/uv-*`.
- **`.github/workflows/release.yml`** (tag `v*`):
  1. Fail if the tag doesn't equal `v` + `VERSION`.
  2. Run tests.
  3. Build both zips.
  4. `gh release create <tag> dist/*.zip` with notes pointing to the README quick start.

## 9. Error handling

| Situation | What the user sees |
|---|---|
| First-run setup has no internet | Launcher: "Setup failed — check your internet connection and try again" |
| No `uv` found | Launcher: "Download retro-ears from https://github.com/kandooswill/retro-ears/releases" |
| Launched twice | Browser opens the running copy; the second launcher window says "retro-ears is already running" and can be closed |
| Port 8787 used by another program | Launcher window: "Port 8787 is in use by another program" |
| Update while a download is running | "Wait for the current download to finish" |
| Update fails | "Update failed — check your internet connection"; app keeps running |
| GitHub release check fails | No banner; nothing else changes |
| iPod unplugged during a job | Remaining songs fail with "iPod disconnected" |
| iPod full | Songs fail with "iPod is full" |
| Job sent to an iPod that isn't plugged in | "iPod not found — plug it in and try again" |
| Song already on the iPod | Result "Already on iPod"; not copied again |

## 10. Testing

- **Unit (offline):**
  - `devices`: macOS and Windows branches with platform and filesystem mocked.
  - `ipod`: paths, same-size skip, `(2)` naming, `cover.jpg`, full, disconnected — in temp folders containing `.rockbox`.
  - `updates`: version comparison, GitHub check caching and failure, update command construction.
  - `jobs`: iPod destination flow and results.
  - API: `/api/version`, `/api/update` (409 / 400 / success schedules exit 42 with the subprocess mocked), `/api/devices`, destination validation, `file` refused for iPod jobs.
  - `build_release`: zip contents and permission bits using fake uv files, with no network.
- **Live (`-m live`):** Kool Kats in all three formats; Creative Commons search and match; Spotify and Apple Kevin MacLeod album links.
- **CI:** tests plus launcher smoke on macOS and Windows.
- **Manual (Kushal, macOS):**
  1. Download `retro-ears-mac.zip` from the Release in a browser.
  2. Go through the Gatekeeper flow; first-run setup; search and download.
  3. Click Update yt-dlp and confirm it restarts.
  4. Copy songs to his Rockbox iPod, eject, and confirm they play with cover art.
- **Windows:** CI only until a Windows user tries a release.

## 11. Risks

| Risk | Mitigation |
|---|---|
| Apple changes the Gatekeeper flow wording | README uses text steps, not only screenshots |
| Antivirus flags `uv.exe` | It is the official signed Astral binary; README troubleshooting mentions it |
| A takedown notice like youtube-dl's | Creative Commons examples only, no piracy framing, personal-use note |
| FAT32 iPods copy slowly | Progress per song in the dock |
| Windows never hand-tested | CI launcher smoke; ask the first Windows users to report issues |
| `uv` behaviour changes | uv version pinned in the build script |

## 12. Build order

1. `pyproject.toml`, `uv.lock`, `.python-version`, `VERSION`, `LICENSE`. Remove requirements files and run scripts. Move tests and docs to Creative Commons examples.
2. Launchers plus second-launch / port handling in `app.py`.
3. `updates.py`, `/api/version`, `/api/update`, footer, banner.
4. `devices.py`, `ipod.py`, job destination, `/api/devices`, Save-to menu.
5. `scripts/build_release.py`, `ci.yml`, `release.yml`.
6. README rewrite and screenshots.
7. Tag `v1.0.0`, publish the release, manual check.
