import base64
import io

import httpx
import pytest
from mutagen.flac import Picture
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from PIL import Image

import tags
from models import Track

TRACK = Track(title="Café Song", artist="Some Artist", album="Some Album", duration_s=1, video_id="abc123def45")


def is_baseline(data: bytes) -> bool:
    return b"\xff\xc0" in data and b"\xff\xc2" not in data


def test_to_baseline_jpeg_converts_progressive_and_resizes(jpeg_bytes):
    out = tags.to_baseline_jpeg(jpeg_bytes(size=(1200, 1200), progressive=True))
    image = Image.open(io.BytesIO(out))
    assert image.format == "JPEG"
    assert image.size == (600, 600)
    assert is_baseline(out)


def test_to_baseline_jpeg_accepts_png_with_alpha():
    buffer = io.BytesIO()
    Image.new("RGBA", (100, 100), (0, 0, 0, 0)).save(buffer, "PNG")
    out = tags.to_baseline_jpeg(buffer.getvalue())
    image = Image.open(io.BytesIO(out))
    assert image.mode == "RGB"
    assert image.size == (100, 100)


def test_fetch_art_without_url_returns_none():
    assert tags.fetch_art(None) is None


def test_fetch_art_network_error_returns_none(monkeypatch):
    def boom(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(tags.httpx, "get", boom)
    assert tags.fetch_art("https://example.com/cover.jpg") is None


def test_fetch_art_non_image_returns_none(monkeypatch):
    response = httpx.Response(200, content=b"not an image", request=httpx.Request("GET", "https://x"))
    monkeypatch.setattr(tags.httpx, "get", lambda *args, **kwargs: response)
    assert tags.fetch_art("https://x") is None


def test_fetch_art_returns_baseline_jpeg(monkeypatch, jpeg_bytes):
    response = httpx.Response(200, content=jpeg_bytes(), request=httpx.Request("GET", "https://x"))
    monkeypatch.setattr(tags.httpx, "get", lambda *args, **kwargs: response)
    assert is_baseline(tags.fetch_art("https://x"))


def test_m4a_tags_round_trip(silent_file, jpeg_bytes):
    path = silent_file("m4a")
    art = tags.to_baseline_jpeg(jpeg_bytes())
    tags.write_tags(path, TRACK, art)
    audio = MP4(path)
    assert audio["\xa9nam"] == ["Café Song"]
    assert audio["\xa9ART"] == ["Some Artist"]
    assert audio["\xa9alb"] == ["Some Album"]
    assert bytes(audio["covr"][0]) == art


def test_opus_tags_round_trip(silent_file, jpeg_bytes):
    path = silent_file("opus")
    art = tags.to_baseline_jpeg(jpeg_bytes())
    tags.write_tags(path, TRACK, art)
    audio = OggOpus(path)
    assert audio["title"] == ["Café Song"]
    assert audio["artist"] == ["Some Artist"]
    assert audio["album"] == ["Some Album"]
    picture = Picture(base64.b64decode(audio["metadata_block_picture"][0]))
    assert picture.data == art
    assert picture.type == 3
    assert picture.mime == "image/jpeg"


def test_mp3_tags_round_trip_as_id3v23(silent_file, jpeg_bytes):
    path = silent_file("mp3")
    art = tags.to_baseline_jpeg(jpeg_bytes())
    tags.write_tags(path, TRACK, art)
    audio = ID3(path)
    assert audio.version == (2, 3, 0)
    assert audio["TIT2"].text == ["Café Song"]
    assert audio["TPE1"].text == ["Some Artist"]
    assert audio["TALB"].text == ["Some Album"]
    assert audio.getall("APIC")[0].data == art


def test_write_tags_skips_missing_album_and_art(silent_file):
    path = silent_file("m4a")
    tags.write_tags(path, Track(title="T", artist="A"), None)
    audio = MP4(path)
    assert audio["\xa9nam"] == ["T"]
    assert "\xa9alb" not in audio.tags
    assert "covr" not in audio.tags


def test_write_tags_rejects_unknown_extension(tmp_path):
    path = tmp_path / "song.wav"
    path.write_bytes(b"")
    with pytest.raises(ValueError):
        tags.write_tags(path, TRACK, None)
