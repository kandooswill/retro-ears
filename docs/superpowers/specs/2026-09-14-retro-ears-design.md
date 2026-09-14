# retro-ears — Design Spec

- **Date:** 2026-09-14
- **Status:** Design approved in brainstorming; written spec pending review
- **Owner:** Kushal

## 1. Goal

A local app for Mac and Windows that lets a person:

1. Search for a song and download it.
2. Paste a Spotify, Apple Music, YouTube Music or YouTube playlist link and download the whole list.
3. Paste any other media link (YouTube video, SoundCloud, Bandcamp) and download it.

Every file comes out at the best quality available to that user, fully tagged (title, artist, album, track number, year, cover art), and delivered to either a stock iPod (via the Music app / iTunes sync) or a Rockbox iPod (copied straight to the device).

## 2. Non-goals

- **No public hosted service.** The app runs on the user's own computer and binds to `127.0.0.1` only.
- **No DRM circumvention.** Spotify and Apple Music audio is never touched. Only public playlist metadata (track names, artists, durations) is read; audio comes from YouTube.
- **No shared Premium account.** Each user may connect their own YouTube Premium login; nobody's account is used on another person's behalf.
- **No lossless import in v1.** Importing owned FLAC/WAV files is a later phase.
- **Linux is not a target.** It may work incidentally; it is not tested.

## 3. Verified facts (2026-09-14)

These were checked during brainstorming and shape the design:

| Fact | Evidence |
|---|---|
| yt-dlp 2026.8.19, ytmusicapi 1.12.2, mutagen 1.48.1, fastapi 0.141.1 all require Python ≥ 3.10 | PyPI metadata |
| yt-dlp needs a JS runtime for YouTube; the PyPI `deno` package (2.9.6) works as that runtime, so end users need no Node install | Ran `yt-dlp --js-runtimes deno:<pip deno> -F` successfully on macOS arm64; `deno` ships `win_amd64` and macOS wheels |
| `imageio-ffmpeg` 0.6.0 ships static ffmpeg for macOS (intel + arm64) and Windows | PyPI wheels |
| Free YouTube audio: format 140 = AAC 130k `.m4a`; format 251 = Opus 129k `.webm` | `yt-dlp -F` on a live video |
| Premium audio: format 141 = AAC 256k; format 774 = Opus 256k. Both need a Premium login. Availability has been reported as intermittent even with valid cookies (yt-dlp issues #12891, #14208) | Web research; **not yet verified with a real account** |
| Spotify: `open.spotify.com/embed/playlist/{id}` contains `__NEXT_DATA__` JSON with `trackList` (title, `subtitle` = artists, duration ms). The embed caps at **100 tracks** | 50-track playlist → 50; 150-track playlist → 100 |
| Apple Music: public playlist page contains an `ld+json` `MusicPlaylist` (track name, ISO duration) and `serialized-server-data` JSON (fuller data including artist, `trackCount`) | Fetched a public playlist page |
| iTunes Search API: free, no key; returns album, track number, release date, artwork URL, duration. Ranking is not by popularity (a cover version outranked the original) | Live query |
| Chrome/Edge cookies on Windows cannot be read by external tools (app-bound encryption, Chrome 127+). Firefox cookies and exported `cookies.txt` files still work | Web research, yt-dlp issue #15401 |

## 4. Architecture

Python backend (FastAPI) + React frontend (Vite + TypeScript). The backend serves the built frontend, so users only need Python.

```
retro-ears/
  server/
    main.py          FastAPI app: API routes, SSE stream, static frontend
    models.py        Track, Playlist, MatchResult, Job, JobState
    paths.py         every OS-specific path in one place (macOS / Windows)
    settings.py      load/save settings JSON
    search.py        iTunes Search API → list[Track]
    routing.py       classify pasted input: search text / playlist link / direct link
    playlists.py     playlist link → Playlist
    enrich.py        fill missing album / track number / year / art via iTunes
    matcher.py       Track → best YouTube Music video, with confidence score
    downloader.py    yt-dlp download at chosen quality, remux, progress callback
    tagger.py        write tags + cover art (m4a and opus)
    library.py       master library folder, safe file names, duplicate detection
    delivery.py      Music app auto-add folder / Rockbox device copy
    devices.py       detect Rockbox iPods and the Music auto-add folder
    jobs.py          in-memory queue, 3 workers, state events
    static/          built frontend (committed, so users need no Node)
    tests/
  web/               Vite + React + TypeScript source
  requirements.txt
  run.sh             macOS launcher
  run.ps1            Windows launcher
  README.md
```

### 4.1 Data model

```python
@dataclass
class Track:
    title: str
    artist: str                  # primary artist display string, "A, B" for features
    album: str | None
    track_no: int | None
    year: int | None
    duration_ms: int | None
    artwork_url: str | None
    video_id: str | None = None  # set when the source already is YouTube
    source_url: str | None = None

@dataclass
class Playlist:
    name: str
    cover_url: str | None
    tracks: list[Track]
    total: int | None            # real track count if known
    truncated: bool              # True when more tracks exist or may exist (Spotify: exactly 100 returned)

class JobState(Enum):
    QUEUED, MATCHING, NEEDS_REVIEW, DOWNLOADING, TAGGING, DELIVERING, DONE, FAILED
```

### 4.2 Components

Each unit has one job and can be tested alone.

**`routing.py`** — `classify(text) -> Route`
- Spotify `open.spotify.com/(playlist|album|track)/{id}` → `SPOTIFY`
- Apple `music.apple.com/.../(playlist|album|song)/...` → `APPLE`
- `music.youtube.com/playlist?list=` or `youtube.com/playlist?list=` → `YOUTUBE_PLAYLIST`
- Any other `http(s)://` URL → `DIRECT`
- Anything else → `SEARCH`

Spotify albums/tracks and Apple albums/songs use the same page-parsing approach as playlists, so they are included at near-zero cost.

**`search.py`** — `search(query, limit=25) -> list[Track]`
iTunes Search API, `entity=song`. Artwork URL rewritten from `100x100bb` to `600x600bb`. Results shown as a list so the user picks the right version.

**`playlists.py`** — `load(url) -> Playlist`
- Spotify: fetch embed page, parse `__NEXT_DATA__` → `trackList`. The embed does not expose the real track count, so `total=None`, and `truncated=True` whenever exactly 100 tracks come back.
- Apple: fetch public page, parse `serialized-server-data` for title/artist/duration; fall back to `ld+json` for names + durations.
- YouTube Music playlist: `ytmusicapi.get_playlist` (gives artist, album, video id).
- YouTube playlist: yt-dlp flat extraction (video id + title); titles like "Artist - Song (Official Video)" are cleaned before enrichment.
- Raises `PlaylistError(kind)` where kind is `PRIVATE`, `NOT_FOUND`, or `PARSE_CHANGED`.

**`enrich.py`** — `enrich(track) -> Track`
For tracks missing album/track number/year/art: iTunes lookup on `"{artist} {title}"`. Accept the first result whose normalized title and artist match and whose duration is within ±7 s. Otherwise keep what we have and use the YouTube thumbnail as art.

**`matcher.py`** — `match(track) -> MatchResult(video_id, score, candidates)`
- Skipped when `track.video_id` is already set.
- `ytmusicapi.search(f"{artist} {title}", filter="songs")`, top 10.
- Score per candidate (0–1): title similarity × 0.5 + artist similarity × 0.3 + duration score × 0.2 (full at ≤ 7 s difference, linear to 0 at 20 s).
- Penalty −0.3 when the candidate title contains `live`, `remix`, `cover`, `karaoke`, `sped up`, `slowed`, `instrumental` and the requested title does not.
- `score ≥ 0.75` → auto-accept. Below → job goes to `NEEDS_REVIEW` with the top 3 candidates.

**`downloader.py`** — `download(video_id, profile, quality, workdir, on_progress) -> DownloadResult(path, codec, bitrate_kbps)`

Format selection:

| Quality | Profile | yt-dlp format string | Output |
|---|---|---|---|
| Best | stock | `141/140/bestaudio[ext=m4a]` | `.m4a` (FFmpeg m4a fixup, no re-encode) |
| Best | rockbox | `774/251/bestaudio` | Opus remuxed from WebM to Ogg `.opus` (stream copy, no re-encode); `.m4a` if an AAC stream won |
| Standard | either | `140/bestaudio[ext=m4a]` | `.m4a` |

- Premium format ids (141, 774) are only included when a cookie source is configured; without one the strings are `140/bestaudio[ext=m4a]` (stock) and `251/bestaudio` (rockbox). If Premium formats are missing, yt-dlp falls through to the free format automatically; the result's real codec and bitrate are reported, never assumed.
- JS runtime: the `deno` binary from the app's virtualenv, passed via `js_runtimes`.
- ffmpeg: `imageio_ffmpeg.get_ffmpeg_exe()`, passed via `ffmpeg_location`.
- Cookie source (from settings): `none` | `browser:<firefox|safari|chrome|...>` | `file:<path to cookies.txt>`.

**`tagger.py`** — `tag(path, track, art_jpeg: bytes | None)`
- `.m4a`: MP4 atoms `©nam ©ART ©alb trkn ©day covr`.
- `.opus`: Vorbis comments + `METADATA_BLOCK_PICTURE`.
- Art is fetched once, resized to max 600 px, and re-saved as **baseline** JPEG with Pillow (Rockbox cannot decode progressive JPEG).

**`library.py`**
- Master copy: `<Music>/retro-ears/<Artist>/<Album>/<NN> <Title>.<ext>` (`<Music>` from `paths.py`).
- File names sanitized for both OSes: strip `<>:"/\|?*` and control chars, trim trailing dots/spaces, avoid reserved names (`CON`, `NUL`, `COM1`…), cap each segment at 120 chars.
- Duplicate key: normalized `artist + title + album` + extension. If a file for that key already exists at equal or higher bitrate, the download is skipped and only delivery runs.
- Stock delivery needs `.m4a`. If the library only holds `.opus` for a track, a `.m4a` is downloaded for it.

**`devices.py`**
- `find_rockbox() -> list[Device(mount, name, free_bytes)]`
  - macOS: `/Volumes/*` containing `.rockbox/`.
  - Windows: drive letters `D:`–`Z:` containing `\.rockbox\`.
- `find_music_autoadd() -> Path | None`
  - macOS: `~/Music/Music/Media.localized/Automatically Add to Music.localized` (also the non-`.localized` spelling).
  - Windows: `%USERPROFILE%\Music\iTunes\iTunes Media\Automatically Add to iTunes`, then a search under `%USERPROFILE%\Music` for a folder named `Automatically Add to*` (covers the Apple Music app, whose exact path is not verified).
  - `settings.music_folder_override` wins when set.

**`delivery.py`** — `deliver(library_file, destination) -> Path`
- `music_app`: copy into the auto-add folder. The Music app / iTunes imports it; the user syncs with Finder (macOS) or Apple Devices / iTunes (Windows).
- `rockbox`: copy to `<device>/Music/<Artist>/<Album>/`, and write `cover.jpg` in that album folder (reliable album art on Rockbox regardless of codec). Check free space first.
- Copy, never move — the library keeps the master.

**`jobs.py`**
- In-memory `asyncio` queue, 3 concurrent workers.
- Flow: `QUEUED → MATCHING → (NEEDS_REVIEW) → DOWNLOADING(pct) → TAGGING → DELIVERING → DONE | FAILED(reason)`.
- Each state change is pushed to the browser over Server-Sent Events.
- Jobs do not survive an app restart in v1. Library duplicate detection makes re-queueing cheap.

**`settings.py`**
- macOS: `~/Library/Application Support/retro-ears/settings.json`
- Windows: `%APPDATA%\retro-ears\settings.json`
- Fields: `destination` (`music_app` | `rockbox`), `quality` (`best` | `standard`, default `best`), `cookie_source`, `music_folder_override`, `library_root`.

### 4.3 API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/search?q=` | Search results |
| POST | `/api/resolve` `{text}` | Classify input; returns search results, a Playlist, or a direct-link Track |
| POST | `/api/jobs` `{tracks: Track[]}` | Queue downloads; returns job ids |
| POST | `/api/jobs/{id}/choose` `{video_id}` | Pick a candidate for a `NEEDS_REVIEW` job |
| POST | `/api/jobs/{id}/retry` | Retry a failed job |
| POST | `/api/jobs/{id}/redeliver` | Copy a finished file to the destination again |
| GET | `/api/events` | SSE stream of job updates |
| GET / PUT | `/api/settings` | Read / update settings |
| GET | `/api/devices` | Detected Rockbox devices + Music auto-add folder |
| POST | `/api/ytdlp/update` | `pip install -U yt-dlp yt-dlp-ejs` inside the app's virtualenv, waits for active downloads to finish, then asks the user to restart the app |

## 5. Interface

Modern minimal, dark. Single page.

- **Header:** app name, destination switch (**Music app** / **Rockbox iPod** — the Rockbox option is disabled with a hint when no device is detected), settings button.
- **Input bar:** one field. Text → search results. Playlist link → playlist view. Other link → single-track confirm row.
- **Search results:** rows with 48 px art, title, artist · album · year, duration, Download button.
- **Playlist view:** cover, name, track count, and a notice when truncated ("Spotify only shares the first 100 songs — this playlist may have more"). Track list with checkboxes (all checked) and a **Download selected** button.
- **Queue panel:** one row per job with state and progress bar. Finished rows show the real quality badge (e.g. `AAC 256`, `Opus 129`). Clicking a row shows the matched YouTube source. `NEEDS_REVIEW` rows expand to show 3 candidates to pick from. Failed rows show the reason and **Retry**. Delivery failures show **Copy again**.
- **Settings sheet:** quality (Best / Standard), YouTube Premium login source (None / browser / cookies.txt file, with the Windows Chrome/Edge limitation explained), Music folder override, library location, **Update yt-dlp** button.

Components: `InputBar`, `SearchResults`, `PlaylistView`, `QueuePanel`, `QueueRow`, `CandidatePicker`, `DestinationSwitch`, `SettingsSheet`. State from one SSE subscription plus a small store.

## 6. Error handling

| Situation | Behavior |
|---|---|
| Match score below threshold | `NEEDS_REVIEW` with top 3 candidates; never download a guess |
| yt-dlp failure (age-restricted, region-blocked, removed, YouTube change) | `FAILED` with a human-readable reason + Retry; Settings offers **Update yt-dlp** |
| Premium formats unavailable or login expired | Silent fallback to free format; badge shows real quality; Settings shows a "Premium login not working" notice after 3 consecutive fallbacks |
| Playlist private / not found / page layout changed | Clear message naming which of the three |
| Spotify playlist over 100 songs | Import the first 100 and show the truncation notice |
| Rockbox iPod unplugged mid-copy or out of space | File stays in the library; delivery `FAILED` with reason + **Copy again** |
| Music auto-add folder not found | Prompt: open the Music app / iTunes once, or choose the folder in Settings |
| Network offline | Search and jobs fail fast with "No internet connection" |
| Windows + Chrome/Edge chosen as cookie source | Blocked in Settings with the explanation and the Firefox / cookies.txt alternatives |

## 7. Security

- Server binds to `127.0.0.1:8787` only; never `0.0.0.0`.
- Requests whose `Host` header is not `127.0.0.1:8787` or `localhost:8787` are rejected (blocks DNS-rebinding attacks from web pages).
- No CORS for other origins.
- Browser cookies are read by yt-dlp at download time and never copied into the library, the repo, logs, or settings. Settings store only the cookie *source* (browser name or file path).
- Logs redact cookie values and `cookies.txt` contents.
- `.gitignore` excludes `*.cookies.txt`, `cookies*.txt`, `.venv/`, settings files.

## 8. Install and run

- **Requirement for users:** Python 3.10+. Nothing else (ffmpeg and deno come from pip; the frontend is prebuilt in `server/static/`).
- `run.sh` (macOS) / `run.ps1` (Windows):
  1. Check Python ≥ 3.10; print install instructions if missing.
  2. Create `.venv` if absent; `pip install -r requirements.txt`.
  3. Start uvicorn on `127.0.0.1:8787`.
  4. Open the default browser.
- **Developers** rebuild the frontend with `npm run build` in `web/`, which outputs to `server/static/`.
- `README.md` states the app is for personal use and that users are responsible for what they download.

## 9. Testing

- **Unit tests (pytest), offline, with saved fixtures:**
  - `routing` — every supported link shape + plain text.
  - `playlists` — Spotify embed HTML (normal + 100-cap), Apple page HTML, ytmusicapi playlist JSON, yt-dlp flat playlist JSON.
  - `enrich` / `matcher` — scoring, penalties, threshold, duration tolerance, using saved iTunes / ytmusicapi JSON.
  - `tagger` — write then read back tags and art on 1-second silent `.m4a` and `.opus` files generated with the bundled ffmpeg; art is baseline JPEG.
  - `library` — sanitizing (Windows reserved names/chars), duplicate detection, bitrate comparison.
  - `paths` / `devices` — macOS and Windows branches with the platform and filesystem mocked.
  - `downloader` — format string chosen for each quality × profile × cookie combination.
- **Live smoke test (`pytest -m live`, opt-in):** search → match → download a short track → tag → deliver to a temp folder.
- **Manual checklist (macOS):** search download; Spotify, Apple Music, YouTube Music and YouTube playlist imports; Music app delivery + Finder sync; Rockbox delivery; Premium login on/off and the quality badge.
- **Windows:** cannot be verified from the development Mac. Unit tests cover Windows paths via mocks; a GitHub Actions `windows-latest` job runs the unit suite once the repo has a remote. A real Windows click-through is needed before calling Windows done.

## 10. Risks

| Risk | Mitigation |
|---|---|
| YouTube changes break yt-dlp | In-app **Update yt-dlp** button; pinned minimum version in requirements |
| Premium formats 141/774 unreliable | Automatic fallback; real quality always shown; verify with Kushal's account early |
| Spotify / Apple page structure changes | Parsers isolated in `playlists.py` with fixture tests; clear `PARSE_CHANGED` error |
| Rockbox does not show art embedded in Opus | `cover.jpg` in every album folder; verify on device |
| Windows Apple Music auto-add path differs from our guess | Folder search + manual override in Settings |
| Wrong song matched | Confidence threshold + review step + visible source link |

## 11. Build phases

1. **Core pipeline:** models, paths, settings, search, enrich, matcher, downloader, tagger, library + unit tests + live smoke test.
2. **Playlists and jobs:** routing, playlists, jobs queue, FastAPI routes, SSE, localhost-only binding + Host header check.
3. **Frontend:** Vite + React UI, built into `server/static/`.
4. **Delivery and Premium:** devices, delivery (Music app + Rockbox), cookie source setting, quality badge, log redaction.
5. **Windows and packaging:** Windows paths, `run.ps1`, `run.sh`, README, CI workflow.
