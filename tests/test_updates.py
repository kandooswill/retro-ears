import subprocess
import sys

import httpx
import pytest

import updates


class FakeChecker:
    def __init__(self, latest=None):
        self._latest = latest

    def latest(self):
        return self._latest


@pytest.mark.parametrize(
    "candidate,current,newer",
    [("v1.1.0", "1.0.0", True), ("1.0.0", "1.0.0", False), ("v0.9.9", "1.0.0", False), ("v1.10.0", "1.9.0", True), ("latest", "1.0.0", False)],
)
def test_is_newer(candidate, current, newer):
    assert updates.is_newer(candidate, current) is newer


def test_app_version_reads_version_file():
    assert updates.app_version() == (updates.APP_DIR / "VERSION").read_text("utf-8").strip()


def test_release_checker_caches_for_six_hours():
    calls, now = [], [0.0]
    checker = updates.ReleaseChecker(fetch=lambda: calls.append(1) or {"tag": "v2.0.0", "url": "u"}, clock=lambda: now[0])
    assert checker.latest() == {"tag": "v2.0.0", "url": "u"}
    now[0] = updates.CHECK_EVERY_S - 1
    checker.latest()
    assert len(calls) == 1
    now[0] = updates.CHECK_EVERY_S
    checker.latest()
    assert len(calls) == 2


def test_release_checker_failure_gives_none():
    def boom():
        raise httpx.ConnectError("offline")

    assert updates.ReleaseChecker(fetch=boom).latest() is None


def test_fetch_latest_parses_github(monkeypatch):
    response = httpx.Response(
        200,
        json={"tag_name": "v1.2.0", "html_url": "https://github.com/kandooswill/retro-ears/releases/tag/v1.2.0"},
        request=httpx.Request("GET", updates.RELEASES_API),
    )
    monkeypatch.setattr(updates.httpx, "get", lambda *args, **kwargs: response)
    assert updates.fetch_latest() == {"tag": "v1.2.0", "url": "https://github.com/kandooswill/retro-ears/releases/tag/v1.2.0"}


def test_fetch_latest_without_releases(monkeypatch):
    response = httpx.Response(404, request=httpx.Request("GET", updates.RELEASES_API))
    monkeypatch.setattr(updates.httpx, "get", lambda *args, **kwargs: response)
    assert updates.fetch_latest() is None


def test_version_info_with_newer_release(monkeypatch, tmp_path):
    uv = tmp_path / "uv"
    uv.write_text("")
    monkeypatch.setenv("RETRO_UV", str(uv))
    monkeypatch.setattr(updates, "app_version", lambda: "1.0.0")
    info = updates.version_info(FakeChecker({"tag": "v1.1.0", "url": "https://example.com/release"}))
    assert info == {
        "app": "1.0.0", "ytdlp": updates.ytdlp_version(), "can_update": True,
        "latest_app": "1.1.0", "release_url": "https://example.com/release", "started": updates.STARTED,
    }


def test_version_info_hides_older_release(monkeypatch):
    monkeypatch.delenv("RETRO_UV", raising=False)
    monkeypatch.setattr(updates, "app_version", lambda: "1.0.0")
    info = updates.version_info(FakeChecker({"tag": "v0.1.0", "url": "https://example.com/old"}))
    assert (info["latest_app"], info["release_url"], info["can_update"]) == (None, None, False)


def test_uv_path_needs_an_existing_file(monkeypatch, tmp_path):
    monkeypatch.delenv("RETRO_UV", raising=False)
    assert updates.uv_path() is None
    monkeypatch.setenv("RETRO_UV", str(tmp_path / "missing"))
    assert updates.uv_path() is None


def test_update_command(tmp_path):
    assert updates.update_command(tmp_path / "uv") == [str(tmp_path / "uv"), "pip", "install", "--python", sys.executable, "--upgrade", "yt-dlp[default]"]


@pytest.mark.parametrize("outcome,expected", [(0, True), (1, False), ("timeout", False)])
def test_update_ytdlp(monkeypatch, tmp_path, outcome, expected):
    uv = tmp_path / "uv"
    uv.write_text("")
    monkeypatch.setenv("RETRO_UV", str(uv))

    def fake_run(command, **kwargs):
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(command, 300)
        return subprocess.CompletedProcess(command, outcome, "", "")

    assert updates.update_ytdlp(run=fake_run) is expected


def test_update_ytdlp_without_uv(monkeypatch):
    monkeypatch.delenv("RETRO_UV", raising=False)
    assert updates.update_ytdlp(run=lambda *args, **kwargs: pytest.fail("must not run")) is False


def test_schedule_restart_exits_with_42():
    codes = []
    timer = updates.schedule_restart(delay_s=0, exit=codes.append)
    timer.join(2)
    assert codes == [42]
