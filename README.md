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
| **AAC (.m4a)** | YouTube's own AAC audio, not converted (about 130 kbps) | Stock iPod |
| **Opus** | YouTube's own Opus audio, not converted (about 130 kbps) | Rockbox |
| **MP3 320** | Converted from the best stream — plays anywhere, but isn't better than the source | Everything else |

Each finished song shows the quality it actually got. About 130 kbps is the best YouTube gives without its paid, bot-protected streams, and higher-resolution videos don't carry better audio. Spotify playlists only share their first 100 songs.

## Getting songs onto the iPod

- **Stock iPod:** drag the files into the Music app (macOS) or iTunes / Apple Music (Windows), then sync.
- **Rockbox:** copy the files into the iPod's `Music` folder.

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest              # offline tests
.venv/bin/pytest -m live -s   # real downloads and lookups
```
