"""Shared data shapes and user-facing errors."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Track:
    title: str
    artist: str
    album: str | None = None
    duration_s: int | None = None
    art_url: str | None = None
    video_id: str | None = None  # None for Spotify/Apple tracks until matched


@dataclass
class PlaylistInfo:
    id: str | None
    name: str
    art_url: str | None = None
    count: int | None = None
    tracks: list[Track] = field(default_factory=list)
    note: str | None = None


class RetroError(Exception):
    """An error whose message is safe to show to the user."""


class NotSupported(RetroError):
    pass


class NotFound(RetroError):
    pass


class ParseChanged(RetroError):
    pass


class Offline(RetroError):
    pass
