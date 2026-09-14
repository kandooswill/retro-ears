# retro-ears — Design Spec (v2, simplified)

- **Date:** 2026-09-14
- **Status:** v2 design approved; replaces the v1 spec (commit a243b78)
- **Owner:** Kushal
- **Reference:** ytmp3.gl — one input, one button, a file download. retro-ears keeps that simplicity and adds search, playlists, iPod-ready tags and honest quality choices.

## 1. Goal

A single local web page where a person can:

1. Search **songs** and download one.
2. Search **playlists**, open one, and download all of it as a ZIP.
3. Paste a YouTube, YouTube Music, Spotify or Apple Music link (song or playlist) and download it.

Files come out at the best quality available, with title, artist, album and cover art embedded, ready to drag into the Music app (stock iPod) or onto a Rockbox iPod.

Runs on the user's own computer (macOS and Windows) at `http://127.0.0.1:8787`.

## 2. Non-goals

- Public hosted service.
- Touching Spotify or Apple Music audio (DRM). Only public track names/artists/durations are read; audio comes from YouTube.
- Auto-copying files into the Music app or onto an iPod. Downloads are normal browser downloads.
- Library management, duplicate detection, a match-review screen.
- Links from other sites (SoundCloud, Bandcamp, …) — shows "Link not supported".
- Lossless import. Linux as a tested target.

## 3. Verified facts (2026-09-14)

| Fact | Evidence |
|---|---|
| `ytmusicapi` without login: `search(filter="songs")` returns `videoId`, artists, album, duration, thumbnails | Live query |
| `ytmusicapi` without login: `search(filter="featured_playlists")` returns official playlists with `itemCount`; `filter="community_playlists"` returns user playlists; `get_playlist(id, limit=None)` returns every track with `videoId` | Live queries: official 100/100, community 150/150 (no cap) |
| YouTube Music thumbnail URLs accept a size rewrite: `=w120-h120…` → `=w600-h600` or `=w1200-h1200` returns a square baseline JPEG | Fetched both sizes and read the JPEG header |
| Free YouTube audio: 140 = AAC 130k `.m4a`; 251 = Opus 129k `.webm` | `yt-dlp -F` |
| Premium audio: 141 = AAC 256k; 774 = Opus 256k; need a Premium login; reported intermittent even with valid cookies (yt-dlp #12891, #14208) | Web research. 2026-09-14 test with Kushal's Safari login: macOS blocked reading Safari cookies (Terminal lacks Full Disk Access); downloads fell back to AAC 130 / Opus 133 as designed. 256k still unverified |
| yt-dlp needs a JS runtime for YouTube; PyPI `deno` works as that runtime (no Node needed) | `yt-dlp --js-runtimes deno:<path> -F` succeeded |
| `imageio-ffmpeg` bundles ffmpeg for macOS + Windows with `aac`, `libmp3lame`, `libopus` encoders | `ffmpeg -encoders` on the bundled binary |
| All key packages require Python ≥ 3.10 | PyPI metadata |
| Spotify embed page (`open.spotify.com/embed/playlist/{id}`) has `__NEXT_DATA__` → `trackList` (title, artists, duration), capped at 100 tracks | 150-track playlist returned 100 |
| Apple Music public playlist page has `serialized-server-data` JSON (title, artist, duration) and `ld+json` fallback | Fetched page |
| python.org Python on macOS has no CA certificates by default, so `urllib` HTTPS fails; `requests`/`httpx` with `certifi` works | `CERTIFICATE_VERIFY_FAILED` from urllib; the same URL fetched fine with requests + certifi |
| Chrome/Edge cookies on Windows cannot be read by yt-dlp (app-bound encryption); Firefox and `cookies.txt` work | yt-dlp #15401 |

## 4. The page

```
retro-ears                                            [⚙ Premium]
┌──────────────────────────────────────────────────┐ ┌────────┐
│ Search songs or playlists, or paste a link…      │ │ Search │
└──────────────────────────────────────────────────┘ └────────┘
 (● Songs) ( Playlists )                      Format: [ M4A ▾ ]

 ▣ Blinding Lights — The Weeknd · Blinding Lights    3:22  [↓]
 ▣ Starboy — The Weeknd · Starboy                    3:51  [↓]

 Playlists tab:
 ▣ '80s Summer Grooves · 100 songs          [View] [↓ All]

 ───────────────────────────────────────────────────────────────
 Downloading 23 / 100 · Beat It — Michael Jackson      [Cancel]
```

- **Search box:** plain text searches the active tab. A pasted link is recognized automatically (section 5.3).
- **Tabs:** Songs | Playlists.
- **Format menu:** M4A (default) | Opus | MP3 320. Remembered in `localStorage`.
- **Song row:** art, title, artist · album, duration, download button.
- **Playlist row:** art, name, song count, **View** (opens the track list with a **Download all** button) and **Download all**.
- **Progress bar** (bottom): appears while a download runs; shows `n / total` and the current song; **Cancel**. When finished the browser download starts automatically and the bar shows `98 done · 2 failed` with the failed song names and each finished song's real quality (e.g. `AAC 130`).
- **Premium menu (⚙):** Off | Firefox | Safari | Chrome | cookies.txt file. On Windows, Chrome/Edge are disabled with a one-line explanation.
- States: empty, loading, results, no results, error message.
- Style: modern minimal, dark. One `index.html` with inline CSS and vanilla JS — no build step.

## 5. How it works

### 5.1 Files

```
retro-ears/
  app.py            FastAPI: routes, Host check, serves static/index.html
  models.py         Track, PlaylistInfo, user-facing error classes
  ytmusic.py        song search, playlist search, playlist tracks, song match
  links.py          classify pasted text; parse Spotify and Apple pages
  download.py       yt-dlp format choice, ffmpeg convert/remux, file naming
  tags.py           cover art fetch + baseline JPEG, tag writing (m4a/opus/mp3)
  jobs.py           in-memory download jobs (thread pool), ZIP building, cleanup
  settings.py       Premium cookie source in a small JSON file
  static/index.html the whole UI
  tests/
  requirements.txt  fastapi, uvicorn, yt-dlp[default], ytmusicapi, mutagen, pillow, imageio-ffmpeg, deno, httpx, certifi
  run.sh / run.ps1  create .venv, install, start server, open browser
  README.md
```

### 5.2 Search

- `GET /api/search?q=&type=songs` → `ytmusic.search_songs(q)` → `ytmusicapi.search(q, filter="songs", limit=20)`.
- `GET /api/search?q=&type=playlists` → `ytmusic.search_playlists(q)` → featured playlists first, then community playlists, de-duplicated by id, max 20.
- `GET /api/playlist?id=` → `ytmusic.get_playlist(id)` → `get_playlist(id, limit=None)`.

Shared shapes:

```python
@dataclass
class Track:
    title: str
    artist: str
    album: str | None
    duration_s: int | None
    art_url: str | None
    video_id: str | None      # None for Spotify/Apple tracks until matched

@dataclass
class PlaylistInfo:
    id: str | None
    name: str
    art_url: str | None
    count: int | None
    tracks: list[Track]       # empty in search results
    note: str | None          # e.g. "Spotify only shares the first 100 songs"
```

### 5.3 Pasted links — `links.classify(text)`

| Input | Result |
|---|---|
| `youtube.com/watch?v=`, `youtu.be/`, `music.youtube.com/watch?v=` without `list=` | Single track (`ytmusicapi.get_song` for title/artist/art) |
| Any YouTube / YouTube Music URL with `list=` | Playlist via `get_playlist` |
| `open.spotify.com/playlist/…` or `/album/…` | Parse embed page → tracks (no `video_id`); if exactly 100 tracks, `note` = cap warning |
| `music.apple.com/…/playlist/…` or `/album/…` | Parse public page → tracks (no `video_id`) |
| Other URL | Error "Link not supported" |
| Plain text | Search |

All HTTP fetches use `httpx` with `certifi`.

### 5.4 Matching Spotify / Apple tracks — `ytmusic.match(track)`

At download time, for tracks without `video_id`:
`search(f"{title} {artist}", filter="songs", limit=5)` → first result within ±10 s of the source duration → else first result → else the track fails with "Not found on YouTube Music".

### 5.5 Downloading — `download.fetch(track, fmt, workdir, cookies) -> Result(path, quality_label)`

| Format | yt-dlp format string (with Premium) | Without Premium | Processing |
|---|---|---|---|
| M4A | `141/140/bestaudio[ext=m4a]` | `140/bestaudio[ext=m4a]` | m4a fixup, no re-encode |
| Opus | `774/251/bestaudio[acodec=opus]` | `251/bestaudio[acodec=opus]` | remux WebM → Ogg `.opus`, no re-encode |
| MP3 320 | `774/141/251/140/bestaudio` | `251/140/bestaudio` | ffmpeg `libmp3lame` 320k CBR |

- yt-dlp is called as a library with `ffmpeg_location = imageio_ffmpeg.get_ffmpeg_exe()` and the `deno` binary from the virtualenv as its JS runtime.
- Premium formats only appear in the format string when a cookie source is set. If they are unavailable, yt-dlp falls through to the free format.
- **Quality label** comes from what yt-dlp actually selected (`acodec`, `abr`): `AAC 130`, `Opus 256`, `MP3 320 (from Opus 129)`.
- **Tags** (mutagen): title, artist, album, cover art. M4A → MP4 atoms; Opus → Vorbis comments + `METADATA_BLOCK_PICTURE`; MP3 → ID3v2.3 `TIT2 TPE1 TALB APIC`.
- **Art:** thumbnail URL size rewritten to `=w600-h600` (verified to return a 600 px baseline JPEG), fetched with httpx, and passed through Pillow to guarantee a baseline JPEG ≤ 600 px (Rockbox cannot decode progressive JPEG). If the fetch fails, the largest provided thumbnail is used; if that fails, no art.
- **File name:** `Artist - Title.ext`, sanitized for Windows and macOS (strip `<>:"/\|?*` and control characters, trim trailing dots/spaces, avoid `CON`/`NUL`/`COM1`…, max 150 chars).

### 5.6 Jobs — `jobs.py`

- `POST /api/jobs {tracks, format, name}` → `{id}`. Used for both single songs and playlists.
- Each job runs its tracks on a 3-worker thread pool in a temp folder.
- `GET /api/jobs/{id}` → `{status, done, failed, total, current, results: [{title, artist, quality | error}]}`. The page polls every second.
- `GET /api/jobs/{id}/file` → the single file, or for more than one track a ZIP (`<name>/Artist - Title.ext`, `ZIP_STORED`) of the finished tracks.
- `POST /api/jobs/{id}/cancel` → stops queued tracks; running ones finish.
- Finished jobs older than 1 hour are deleted whenever a new job starts; all job folders are deleted on app start.
- A job with 0 successful tracks returns status `failed` and no file.

### 5.7 Premium — `settings.py`

- `GET/PUT /api/settings` → `{cookie_source: "off" | "firefox" | "safari" | "chrome" | "file:<path>"}`.
- Stored at `~/Library/Application Support/retro-ears/settings.json` (macOS) or `%APPDATA%\retro-ears\settings.json` (Windows).
- Only the source name/path is stored. Cookie values are read by yt-dlp at download time and never logged, copied, or returned by the API.

## 6. Errors

| Situation | What the user sees |
|---|---|
| Search fails / offline | "Couldn't reach YouTube Music. Check your connection." |
| No results | "No songs found" / "No playlists found" |
| Link not supported | "Link not supported — paste a YouTube, YouTube Music, Spotify or Apple Music link" |
| Private or removed playlist | "This playlist is private or doesn't exist" |
| Spotify/Apple page layout changed | "Couldn't read this playlist — the site may have changed" |
| One song fails in a playlist | Job continues; song listed under failed with reason (age-restricted, unavailable, not found) |
| Premium login set but formats unavailable | Download still succeeds at free quality; quality label shows the real bitrate |
| yt-dlp broken by a YouTube change | Song fails with the yt-dlp message; README explains `run.sh --update` |

## 7. Security

- Bind to `127.0.0.1:8787` only.
- Reject requests whose `Host` header is not `127.0.0.1:8787` or `localhost:8787` (DNS rebinding).
- No CORS.
- Cookie values never stored, logged, or sent to the browser. `.gitignore` covers `cookies*.txt`, `.venv/`.

## 8. Install and run

- Users need Python 3.10+ only.
- `run.sh` (macOS) / `run.ps1` (Windows): check Python version → create `.venv` if missing → `pip install -r requirements.txt` → start uvicorn → open browser. `--update` flag upgrades `yt-dlp` and `ytmusicapi`.
- README: what it does, how to run, formats explained, Premium setup, personal-use note.

## 9. Testing

- **Unit (pytest, offline, fixtures):**
  - `links.classify` for every link shape and plain text.
  - Spotify embed and Apple page parsers against saved HTML.
  - `ytmusic` result mapping and `match` duration rule against saved JSON.
  - `download` format-string choice for each format × Premium on/off; quality label; filename sanitizer.
  - Tag + art round-trip on 1-second silent M4A, Opus and MP3 files generated with the bundled ffmpeg; art is baseline JPEG.
  - `jobs`: ZIP layout, partial failure, cancel, all-failed.
- **API (FastAPI TestClient)** with services mocked: search, playlist, jobs lifecycle, Host header rejection.
- **Live smoke (`pytest -m live`, opt-in):** search one song → download in each of the three formats → tags present.
- **Manual (macOS):** song search download, playlist search download, each link type, Premium on/off.
- **Windows:** unit tests only from the Mac; needs one real Windows run before calling it done.

## 10. Risks

| Risk | Mitigation |
|---|---|
| YouTube breaks yt-dlp | `run.sh --update`; clear per-song error |
| Premium formats unreliable | Automatic fallback; real quality label; test with Kushal's account in phase 1 |
| Spotify/Apple pages change | Isolated parsers with fixture tests; clear error |
| Rockbox may not show art embedded in Opus files | Known limitation for v1; M4A works on both iPods |
| Wrong song matched for Spotify/Apple tracks | Duration rule; the finished-song list shows what was downloaded |

## 11. Build order

1. **Download core:** `download.py` (formats, convert, tags, art, naming) + tests + live smoke, including a Premium check with Kushal's account.
2. **Search and links:** `ytmusic.py`, `links.py` + tests.
3. **Jobs and API:** `jobs.py`, `settings.py`, `app.py` + API tests.
4. **Page:** `static/index.html`.
5. **Run scripts and docs:** `run.sh`, `run.ps1`, README, `.gitignore`.
