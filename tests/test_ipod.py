from types import SimpleNamespace

import pytest

import ipod
from models import RetroError, Track

TRACK = Track(title="Kool Kats", artist="Kevin MacLeod", album="Jazz Sampler")


@pytest.fixture
def mount(tmp_path):
    root = tmp_path / "IPOD"
    (root / ".rockbox").mkdir(parents=True)
    return root


def test_destination_path(mount):
    assert ipod.destination_path(mount, TRACK, "m4a") == mount / "Music" / "Kevin MacLeod" / "Jazz Sampler" / "Kevin MacLeod - Kool Kats.m4a"


def test_destination_path_without_album_and_with_unsafe_names(mount):
    track = Track(title="What: Now?", artist="Glass/Arcade")
    assert ipod.destination_path(mount, track, "opus") == mount / "Music" / "GlassArcade" / "Singles" / "GlassArcade - What Now.opus"


def test_copy_saves_song_and_cover(mount, silent_file, jpeg_bytes):
    song = silent_file("m4a")
    art = jpeg_bytes(progressive=False)
    assert ipod.copy_to_ipod(song, TRACK, art, mount) == "Saved to iPod"
    target = ipod.destination_path(mount, TRACK, "m4a")
    assert target.read_bytes() == song.read_bytes()
    assert (target.parent / "cover.jpg").read_bytes() == art
    assert list(target.parent.glob("*.part")) == []


def test_copy_skips_an_identical_song(mount, silent_file):
    song = silent_file("m4a")
    ipod.copy_to_ipod(song, TRACK, None, mount)
    assert ipod.copy_to_ipod(song, TRACK, None, mount) == "Already on iPod"
    assert len(list(ipod.destination_path(mount, TRACK, "m4a").parent.glob("*.m4a"))) == 1


def test_copy_keeps_a_different_file_with_the_same_name(mount, silent_file):
    target = ipod.destination_path(mount, TRACK, "m4a")
    target.parent.mkdir(parents=True)
    target.write_bytes(b"older song")
    song = silent_file("m4a")
    assert ipod.copy_to_ipod(song, TRACK, None, mount) == "Saved to iPod"
    assert target.read_bytes() == b"older song"
    assert (target.parent / "Kevin MacLeod - Kool Kats (2).m4a").read_bytes() == song.read_bytes()


def test_existing_cover_is_kept(mount, silent_file, jpeg_bytes):
    folder = ipod.destination_path(mount, TRACK, "m4a").parent
    folder.mkdir(parents=True)
    (folder / "cover.jpg").write_bytes(b"my cover")
    ipod.copy_to_ipod(silent_file("m4a"), TRACK, jpeg_bytes(), mount)
    assert (folder / "cover.jpg").read_bytes() == b"my cover"


def test_disconnected_ipod(tmp_path, silent_file):
    with pytest.raises(RetroError, match="iPod disconnected"):
        ipod.copy_to_ipod(silent_file("m4a"), TRACK, None, tmp_path / "GONE")


def test_full_ipod(mount, silent_file, monkeypatch):
    monkeypatch.setattr(ipod.shutil, "disk_usage", lambda path: SimpleNamespace(free=10))
    with pytest.raises(RetroError, match="iPod is full"):
        ipod.copy_to_ipod(silent_file("m4a"), TRACK, None, mount)
