import json
from pathlib import Path

import pytest

import settings


def test_load_returns_defaults_when_file_missing(tmp_path):
    assert settings.load(tmp_path / "settings.json") == {"cookie_source": "off"}


def test_load_ignores_corrupt_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", "utf-8")
    assert settings.load(path) == {"cookie_source": "off"}


def test_load_ignores_unknown_keys(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"cookie_source": "firefox", "other": 1}), "utf-8")
    assert settings.load(path) == {"cookie_source": "firefox"}


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "nested" / "settings.json"
    assert settings.save({"cookie_source": "firefox"}, path) == {"cookie_source": "firefox"}
    assert settings.load(path) == {"cookie_source": "firefox"}
    assert json.loads(path.read_text("utf-8")) == {"cookie_source": "firefox"}


def test_save_rejects_unknown_source(tmp_path):
    with pytest.raises(ValueError, match="Unknown login source"):
        settings.save({"cookie_source": "netscape"}, tmp_path / "settings.json")


@pytest.mark.parametrize(
    "platform,source,allowed",
    [
        ("darwin", "safari", True),
        ("darwin", "chrome", True),
        ("darwin", "firefox", True),
        ("win32", "firefox", True),
        ("win32", "chrome", False),
        ("win32", "safari", False),
        ("linux", "safari", False),
    ],
)
def test_browser_sources_per_platform(platform, source, allowed):
    if allowed:
        assert settings.validate_cookie_source(source, platform) == source
    else:
        with pytest.raises(ValueError):
            settings.validate_cookie_source(source, platform)


def test_cookie_file_must_exist(tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    with pytest.raises(ValueError, match="cookies.txt file not found"):
        settings.validate_cookie_source(f"file:{cookie_file}")
    with pytest.raises(ValueError, match="cookies.txt file not found"):
        settings.validate_cookie_source("file:")
    cookie_file.write_text("# Netscape HTTP Cookie File\n", "utf-8")
    assert settings.validate_cookie_source(f"file:{cookie_file}") == f"file:{cookie_file}"


def test_settings_path_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(settings.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert settings.settings_path() == tmp_path / "retro-ears" / "settings.json"


def test_settings_path_on_macos(monkeypatch):
    monkeypatch.setattr(settings.sys, "platform", "darwin")
    assert settings.settings_path() == Path.home() / "Library" / "Application Support" / "retro-ears" / "settings.json"
