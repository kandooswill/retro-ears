import json

import httpx
import pytest

import links
from models import NotFound, NotSupported, Offline, ParseChanged, PlaylistInfo, Track

SPOTIFY_URL = "https://open.spotify.com/playlist/1a2B3c4D5e6F7g8H9i0JkL?si=abc"
APPLE_URL = "https://music.apple.com/us/playlist/calm-mix/pl.u-0000000000000"


@pytest.mark.parametrize(
    "text,kind,value",
    [
        ("neon night", "search", "neon night"),
        ("  glass arcade  ", "search", "glass arcade"),
        ("https://www.youtube.com/watch?v=5viHgHli590", "song", "5viHgHli590"),
        ("https://youtu.be/5viHgHli590?si=abc", "song", "5viHgHli590"),
        ("https://music.youtube.com/watch?v=5viHgHli590&feature=share", "song", "5viHgHli590"),
        ("https://m.youtube.com/watch?v=5viHgHli590", "song", "5viHgHli590"),
        ("https://www.youtube.com/watch?v=5viHgHli590&list=RD5viHgHli590", "song", "5viHgHli590"),
        ("https://www.youtube.com/playlist?list=PLabc123", "youtube_playlist", "PLabc123"),
        ("https://music.youtube.com/playlist?list=RDCLAK5uy_abc", "youtube_playlist", "RDCLAK5uy_abc"),
        ("https://www.youtube.com/watch?v=5viHgHli590&list=PLabc123", "youtube_playlist", "PLabc123"),
        (SPOTIFY_URL, "spotify", SPOTIFY_URL),
        ("https://open.spotify.com/intl-de/album/5G34ftqKz03s5y2No2eRu3", "spotify", "https://open.spotify.com/intl-de/album/5G34ftqKz03s5y2No2eRu3"),
        (APPLE_URL, "apple", APPLE_URL),
        ("https://music.apple.com/us/album/light-electronic/1887659157", "apple", "https://music.apple.com/us/album/light-electronic/1887659157"),
    ],
)
def test_classify(text, kind, value):
    assert links.classify(text) == links.Route(kind, value)


@pytest.mark.parametrize(
    "text",
    [
        "https://soundcloud.com/artist/song",
        "https://open.spotify.com/track/9zY8xW7vU6tS5rQ4pO3nMl",
        "https://www.youtube.com/@somechannel",
        "https://example.com",
    ],
)
def test_classify_rejects_unsupported_links(text):
    with pytest.raises(NotSupported, match="Link not supported"):
        links.classify(text)


def test_spotify_embed_url():
    assert links.spotify_embed_url(SPOTIFY_URL) == "https://open.spotify.com/embed/playlist/1a2B3c4D5e6F7g8H9i0JkL"
    assert links.spotify_embed_url("https://open.spotify.com/intl-de/album/5G34ftqKz03s5y2No2eRu3") == "https://open.spotify.com/embed/album/5G34ftqKz03s5y2No2eRu3"


def spotify_html(entity):
    data = {"props": {"pageProps": {"state": {"data": {"entity": entity}}}}}
    return f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></body></html>'


def spotify_row(i):
    return {"title": f"Song {i}", "subtitle": "Glass Arcade, Low Tide", "duration": 201400, "uri": f"spotify:track:{i}"}


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
    assert links.resolve("https://youtu.be/5viHgHli590", "playlists") == {"type": "songs", "songs": [song]}
    assert links.resolve("https://www.youtube.com/playlist?list=PLx", "songs") == {"type": "playlist", "playlist": playlist}
    assert links.resolve(SPOTIFY_URL, "songs") == {"type": "playlist", "playlist": playlist}
    assert links.resolve(APPLE_URL, "songs") == {"type": "playlist", "playlist": playlist}
    assert fetched == ["https://open.spotify.com/embed/playlist/1a2B3c4D5e6F7g8H9i0JkL", APPLE_URL]
