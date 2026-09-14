"""YouTube Music search, playlists and song matching. No login needed."""
from __future__ import annotations

import re
from dataclasses import replace
from functools import lru_cache

import requests
from ytmusicapi import YTMusic
from ytmusicapi.exceptions import YTMusicServerError

from models import NotFound, Offline, PlaylistInfo, Track

MATCH_TOLERANCE_S = 10
OFFLINE_MESSAGE = "Couldn't reach YouTube Music. Check your connection."
PLAYLIST_MISSING = "This playlist is private or doesn't exist"


@lru_cache(maxsize=1)
def client() -> YTMusic:
    return YTMusic()


def _call(fn):
    try:
        return fn()
    except requests.RequestException as exc:
        raise Offline(OFFLINE_MESSAGE) from exc


def big_art(url: str | None, size: int = 600) -> str | None:
    if not url:
        return None
    return re.sub(r"=w\d+-h\d+", f"=w{size}-h{size}", url)


def _art(item: dict) -> str | None:
    thumbnails = item.get("thumbnails") or []
    return big_art(thumbnails[-1].get("url")) if thumbnails else None


def _artist(item: dict) -> str:
    names = [artist["name"] for artist in item.get("artists") or [] if artist.get("name")]
    return ", ".join(names) or "Unknown Artist"


def song_to_track(item: dict) -> Track:
    album = item.get("album") or {}
    return Track(
        title=item.get("title") or "Unknown Title",
        artist=_artist(item),
        album=album.get("name"),
        duration_s=item.get("duration_seconds"),
        art_url=_art(item),
        video_id=item.get("videoId"),
    )


def search_songs(query: str, limit: int = 20) -> list[Track]:
    items = _call(lambda: client().search(query, filter="songs", limit=limit))
    return [song_to_track(item) for item in items if item.get("videoId")][:limit]


def search_playlists(query: str, limit: int = 20) -> list[PlaylistInfo]:
    featured = _call(lambda: client().search(query, filter="featured_playlists", limit=limit))
    community = _call(lambda: client().search(query, filter="community_playlists", limit=limit))
    seen: set[str] = set()
    playlists: list[PlaylistInfo] = []
    for item in [*featured, *community]:
        playlist_id = item.get("browseId")
        if not playlist_id or playlist_id in seen:
            continue
        seen.add(playlist_id)
        playlists.append(PlaylistInfo(id=playlist_id, name=item.get("title") or "Playlist", art_url=_art(item), count=item.get("itemCount")))
    return playlists[:limit]


def get_playlist(playlist_id: str) -> PlaylistInfo:
    try:
        data = _call(lambda: client().get_playlist(playlist_id, limit=None))
    except (KeyError, YTMusicServerError) as exc:  # ytmusicapi raises KeyError when the page has no playlist
        raise NotFound(PLAYLIST_MISSING) from exc
    tracks = [song_to_track(item) for item in data.get("tracks") or [] if item.get("videoId")]
    return PlaylistInfo(
        id=data.get("id") or playlist_id,
        name=data.get("title") or "Playlist",
        art_url=_art(data),
        count=len(tracks),
        tracks=tracks,
    )


def get_song(video_id: str) -> Track:
    try:
        details = _call(lambda: client().get_song(video_id)).get("videoDetails") or {}
    except (KeyError, YTMusicServerError) as exc:
        raise NotFound("This video is unavailable") from exc
    if not details.get("title"):
        raise NotFound("This video is unavailable")
    thumbnails = (details.get("thumbnail") or {}).get("thumbnails") or []
    artist = re.sub(r"\s+-\s+Topic$", "", details.get("author") or "") or "Unknown Artist"
    length = details.get("lengthSeconds")
    return Track(
        title=details["title"],
        artist=artist,
        duration_s=int(length) if length else None,
        art_url=big_art(thumbnails[-1].get("url")) if thumbnails else None,
        video_id=video_id,
    )


def pick_match(results: list[dict], duration_s: int | None) -> dict:
    if duration_s is not None:
        for item in results:
            seconds = item.get("duration_seconds")
            if seconds is not None and abs(seconds - duration_s) <= MATCH_TOLERANCE_S:
                return item
    return results[0]


def match(track: Track) -> Track:
    """Find a YouTube Music song for a Spotify/Apple track (title + artist + duration)."""
    if track.video_id:
        return track
    results = _call(lambda: client().search(f"{track.title} {track.artist}", filter="songs", limit=5))
    results = [item for item in results if item.get("videoId")]
    if not results:
        raise NotFound("Not found on YouTube Music")
    best = pick_match(results, track.duration_s)
    return replace(
        track,
        video_id=best["videoId"],
        album=track.album or (best.get("album") or {}).get("name"),
        art_url=track.art_url or _art(best),
    )
