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
