import shutil
from pathlib import Path

import pytest
import yt_dlp
from mutagen.mp4 import MP4

import download
import tags
from models import RetroError, Track

TRACK = Track(title="Song", artist="Artist", album="Album", duration_s=1, art_url="https://art.example/cover", video_id="abc123def45")


@pytest.mark.parametrize(
    "fmt,premium,expected",
    [
        ("m4a", False, "140/bestaudio[ext=m4a]"),
        ("m4a", True, "141/140/bestaudio[ext=m4a]"),
        ("opus", False, "251/bestaudio[acodec=opus]"),
        ("opus", True, "774/251/bestaudio[acodec=opus]"),
        ("mp3", False, "251/140/bestaudio"),
        ("mp3", True, "774/141/251/140/bestaudio"),
    ],
)
def test_format_string(fmt, premium, expected):
    assert download.format_string(fmt, premium) == expected


def test_postprocessor_copies_m4a_and_opus_streams():
    assert download.postprocessor("m4a") == {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}
    assert download.postprocessor("opus") == {"key": "FFmpegExtractAudio", "preferredcodec": "opus"}


def test_postprocessor_mp3_is_320():
    assert download.postprocessor("mp3") == {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"}


def test_cookie_opts():
    assert download.cookie_opts("off") == {}
    assert download.cookie_opts("") == {}
    assert download.cookie_opts("chrome") == {"cookiesfrombrowser": ("chrome", None, None, None)}
    assert download.cookie_opts("file:/tmp/cookies.txt") == {"cookiefile": "/tmp/cookies.txt"}


def test_build_opts_without_premium(tmp_path):
    opts = download.build_opts("opus", tmp_path, "off")
    assert opts["format"] == "251/bestaudio[acodec=opus]"
    assert opts["outtmpl"] == str(tmp_path / "%(id)s.%(ext)s")
    assert opts["postprocessors"] == [download.postprocessor("opus")]
    assert opts["noplaylist"] is True
    assert Path(opts["ffmpeg_location"]).exists()
    assert "cookiesfrombrowser" not in opts and "cookiefile" not in opts


def test_build_opts_with_premium(tmp_path):
    opts = download.build_opts("m4a", tmp_path, "firefox")
    assert opts["format"] == "141/140/bestaudio[ext=m4a]"
    assert opts["cookiesfrombrowser"] == ("firefox", None, None, None)


def test_deno_is_found_in_the_virtualenv(tmp_path):
    assert download.deno_path() is not None
    assert download.build_opts("m4a", tmp_path, "off")["js_runtimes"] == {"deno": {"path": download.deno_path()}}


@pytest.mark.parametrize(
    "fmt,acodec,abr,label",
    [
        ("m4a", "mp4a.40.2", 129.548, "AAC 130"),
        ("m4a", "mp4a.40.2", 255.9, "AAC 256"),
        ("opus", "opus", 132.978, "Opus 133"),
        ("mp3", "opus", 132.978, "MP3 320 (from Opus 133)"),
        ("opus", None, None, "Audio ?"),
    ],
)
def test_quality_label(fmt, acodec, abr, label):
    assert download.quality_label(fmt, acodec, abr) == label


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('AC/DC - Back: In "Black"?', "ACDC - Back In Black"),
        ("  spaced   out.. ", "spaced out"),
        ("CON", "_CON"),
        ("nul.txt", "_nul.txt"),
        ("", "track"),
        ("\x00\x1f", "track"),
    ],
)
def test_safe_filename(raw, expected):
    assert download.safe_filename(raw) == expected


def test_safe_filename_caps_length():
    assert len(download.safe_filename("a" * 300)) == 150


def test_unique_path_adds_counter(tmp_path):
    (tmp_path / "Artist - Song.m4a").write_bytes(b"")
    (tmp_path / "Artist - Song (2).m4a").write_bytes(b"")
    assert download.unique_path(tmp_path, "Artist - Song", "m4a") == tmp_path / "Artist - Song (3).m4a"


@pytest.mark.parametrize(
    "message,expected",
    [
        ("ERROR: [youtube] abc: Sign in to confirm your age. This video may be inappropriate for some users.", "Age-restricted — needs a Premium login"),
        ("ERROR: [youtube] abc: Video unavailable", "Unavailable on YouTube"),
        ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access to this video", "Unavailable on YouTube"),
        ("ERROR: [youtube] abc: Requested format is not available. Use --list-formats", "No audio stream in this format"),
        ("ERROR: [youtube] abc: Unable to download API page: timed out", "Network error — check your connection"),
        ("ERROR: [youtube] abc: Something new broke", "Something new broke"),
    ],
)
def test_friendly_error(message, expected):
    assert download.friendly_error(message) == expected


def make_fake_extract(source: Path, ext: str, calls: list, fail_with_cookies: bool = False):
    def fake_extract(opts, url):
        calls.append((opts, url))
        if fail_with_cookies and ("cookiesfrombrowser" in opts or "cookiefile" in opts):
            raise RuntimeError("could not read cookies")
        out = Path(opts["outtmpl"]).parent / f"abc123def45.{ext}"
        shutil.copy(source, out)
        return {"acodec": "mp4a.40.2", "abr": 129.548, "requested_downloads": [{"filepath": str(out)}]}

    return fake_extract


def test_fetch_tags_renames_and_labels(tmp_path, monkeypatch, silent_file, jpeg_bytes):
    calls = []
    monkeypatch.setattr(download, "_extract", make_fake_extract(silent_file("m4a"), "m4a", calls))
    monkeypatch.setattr(tags, "fetch_art", lambda url: tags.to_baseline_jpeg(jpeg_bytes()))
    workdir = tmp_path / "job"

    result = download.fetch(TRACK, "m4a", workdir)

    assert result.path == workdir / "Artist - Song.m4a"
    assert result.quality == "AAC 130"
    assert calls[0][1] == "https://music.youtube.com/watch?v=abc123def45"
    audio = MP4(result.path)
    assert audio["\xa9nam"] == ["Song"]
    assert "covr" in audio.tags
    assert [p.name for p in workdir.iterdir()] == ["Artist - Song.m4a"]  # temp folder removed


def test_fetch_same_song_twice_gets_unique_names(tmp_path, monkeypatch, silent_file):
    monkeypatch.setattr(download, "_extract", make_fake_extract(silent_file("m4a"), "m4a", []))
    monkeypatch.setattr(tags, "fetch_art", lambda url: None)
    workdir = tmp_path / "job"
    first = download.fetch(TRACK, "m4a", workdir)
    second = download.fetch(TRACK, "m4a", workdir)
    assert first.path.name == "Artist - Song.m4a"
    assert second.path.name == "Artist - Song (2).m4a"


def test_fetch_falls_back_to_free_quality_when_login_fails(tmp_path, monkeypatch, silent_file):
    calls = []
    monkeypatch.setattr(download, "_extract", make_fake_extract(silent_file("m4a"), "m4a", calls, fail_with_cookies=True))
    monkeypatch.setattr(tags, "fetch_art", lambda url: None)

    result = download.fetch(TRACK, "m4a", tmp_path / "job", cookie_source="firefox")

    assert [opts["format"] for opts, _ in calls] == ["141/140/bestaudio[ext=m4a]", "140/bestaudio[ext=m4a]"]
    assert "cookiesfrombrowser" not in calls[1][0]
    assert result.path.exists()


def test_fetch_error_is_friendly_and_cleans_up(tmp_path, monkeypatch):
    def fake_extract(opts, url):
        raise yt_dlp.utils.DownloadError("ERROR: [youtube] abc123def45: Video unavailable")

    monkeypatch.setattr(download, "_extract", fake_extract)
    workdir = tmp_path / "job"
    with pytest.raises(RetroError, match="Unavailable on YouTube"):
        download.fetch(TRACK, "m4a", workdir)
    assert list(workdir.iterdir()) == []


def test_fetch_requires_video_id(tmp_path):
    with pytest.raises(RetroError):
        download.fetch(Track(title="Song", artist="Artist"), "m4a", tmp_path)


def test_fetch_rejects_unknown_format(tmp_path):
    with pytest.raises(ValueError):
        download.fetch(TRACK, "wav", tmp_path)
