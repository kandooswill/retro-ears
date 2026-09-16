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


def spotify_cover(url: str) -> str | None:
    """Album embeds carry no cover image, so ask Spotify's public oEmbed endpoint instead."""
    try:
        response = httpx.get(
            "https://open.spotify.com/oembed",
            params={"url": url},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
            verify=certifi.where(),
        )
        return response.json().get("thumbnail_url") if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


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
        playlist = parse_spotify(fetch_page(spotify_embed_url(route.value)))
        if not playlist.art_url:
            playlist.art_url = spotify_cover(route.value)
        return {"type": "playlist", "playlist": playlist}
    return {"type": "playlist", "playlist": parse_apple(fetch_page(route.value))}
