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
