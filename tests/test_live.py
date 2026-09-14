"""Network tests. Run with: .venv/bin/pytest -m live -s
Set RETRO_COOKIES=<firefox|safari|chrome|file:/path> to test with a Premium login."""
import os

import mutagen
import pytest

import download
import ytmusic
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
