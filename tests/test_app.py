import http.server
import json
import socket
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as app_module
import jobs
from models import NotFound, NotSupported, Offline, PlaylistInfo, Track

ROOT = Path(__file__).resolve().parent.parent


class FakeChecker:
    def __init__(self, latest=None):
        self._latest = latest

    def latest(self):
        return self._latest


def build_app(tmp_path, fake_fetch, manager=None, **overrides):
    manager = manager or jobs.JobManager(root=tmp_path / "jobs", fetch=fake_fetch(), match=lambda track: track)
    options = {"checker": FakeChecker(), "restart": lambda: None, **overrides}
    return app_module.create_app(manager=manager, **options)


def local_client(application):
    return TestClient(application, base_url="http://127.0.0.1:8787")


@pytest.fixture
def client(tmp_path, fake_fetch):
    return TestClient(build_app(tmp_path, fake_fetch), base_url="http://127.0.0.1:8787")


def wait_for(client, job_id):
    for _ in range(500):
        status = client.get(f"/api/jobs/{job_id}").json()
        if status["status"] != "running":
            return status
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_rejects_other_host_names(client):
    response = client.get("/api/jobs/nope", headers={"host": "evil.example:8787"})
    assert response.status_code == 403


def test_allows_localhost_name(tmp_path, fake_fetch):
    local = TestClient(build_app(tmp_path, fake_fetch), base_url="http://localhost:8787")
    assert local.get("/api/jobs/nope").status_code == 404


def test_search_returns_songs(client, monkeypatch):
    calls = []

    def fake_resolve(text, tab):
        calls.append((text, tab))
        return {"type": "songs", "songs": [Track(title="Song", artist="Artist", video_id="abc")]}

    monkeypatch.setattr(app_module.links, "resolve", fake_resolve)
    response = client.get("/api/search", params={"q": "song", "type": "songs"})
    assert response.status_code == 200
    assert response.json() == {
        "type": "songs",
        "songs": [{"title": "Song", "artist": "Artist", "album": None, "duration_s": None, "art_url": None, "video_id": "abc"}],
    }
    assert calls == [("song", "songs")]


def test_search_defaults_to_songs_tab(client, monkeypatch):
    calls = []
    monkeypatch.setattr(app_module.links, "resolve", lambda text, tab: calls.append(tab) or {"type": "songs", "songs": []})
    client.get("/api/search", params={"q": "x"})
    assert calls == ["songs"]


def test_search_requires_text(client):
    response = client.get("/api/search", params={"q": "   "})
    assert response.status_code == 400
    assert response.json() == {"error": "Type something to search"}


@pytest.mark.parametrize(
    "error,status",
    [
        (NotSupported("Link not supported — paste a YouTube, YouTube Music, Spotify or Apple Music link"), 400),
        (NotFound("This playlist is private or doesn't exist"), 404),
        (Offline("Couldn't reach YouTube Music. Check your connection."), 502),
    ],
)
def test_search_errors_become_json(client, monkeypatch, error, status):
    def boom(text, tab):
        raise error

    monkeypatch.setattr(app_module.links, "resolve", boom)
    response = client.get("/api/search", params={"q": "x"})
    assert response.status_code == status
    assert response.json() == {"error": str(error)}


def test_playlist_route(client, monkeypatch):
    monkeypatch.setattr(app_module.ytmusic, "get_playlist", lambda playlist_id: PlaylistInfo(id=playlist_id, name="Mix", count=0))
    response = client.get("/api/playlist", params={"id": "VLabc"})
    assert response.status_code == 200
    assert response.json()["id"] == "VLabc"
    assert response.json()["name"] == "Mix"


def test_job_lifecycle_returns_zip(client):
    body = {
        "tracks": [{"title": "One", "artist": "A", "video_id": "v1"}, {"title": "Two", "artist": "A", "video_id": "v2"}],
        "format": "m4a",
        "name": "Mix",
    }
    job_id = client.post("/api/jobs", json=body).json()["id"]
    status = wait_for(client, job_id)
    assert (status["status"], status["done"], status["total"]) == ("done", 2, 2)
    response = client.get(f"/api/jobs/{job_id}/file")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="Mix.zip"'


def test_job_rejects_bad_format(client):
    response = client.post("/api/jobs", json={"tracks": [{"title": "a", "artist": "b"}], "format": "wav"})
    assert response.status_code == 422


def test_job_rejects_empty_track_list(client):
    response = client.post("/api/jobs", json={"tracks": [], "format": "m4a"})
    assert response.status_code == 422


def test_unknown_job(client):
    response = client.get("/api/jobs/nope")
    assert response.status_code == 404
    assert response.json() == {"error": "Download not found"}


def test_cancel_job(client):
    job_id = client.post("/api/jobs", json={"tracks": [{"title": "a", "artist": "b", "video_id": "v"}]}).json()["id"]
    assert client.post(f"/api/jobs/{job_id}/cancel").json() == {"ok": True}


def test_settings_routes_are_gone(client):
    assert client.get("/api/settings").status_code == 404


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<title>retro-ears</title>" in response.text
    assert 'id="searchForm"' in response.text
    assert "Premium" not in response.text
    assert 'id="updateBtn"' in response.text


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_port_status_free():
    assert app_module.port_status(port=free_port()) == "free"


def test_port_status_other_program():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        assert app_module.port_status(port=listener.getsockname()[1], timeout=0.5) == "other"


def test_port_status_retro_ears_already_running():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"app": "1.0.0"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert app_module.port_status(port=server.server_address[1]) == "retro-ears"
    finally:
        server.shutdown()
        server.server_close()


def test_main_opens_the_running_copy(monkeypatch, capsys):
    opened = []
    monkeypatch.setattr(app_module, "port_status", lambda **kwargs: "retro-ears")
    monkeypatch.setattr(app_module.webbrowser, "open", opened.append)
    monkeypatch.setattr(app_module.sys, "argv", ["app.py"])
    with pytest.raises(SystemExit) as exit_info:
        app_module.main()
    assert exit_info.value.code == 0
    assert "retro-ears is already running" in capsys.readouterr().out
    assert opened == ["http://127.0.0.1:8787"]


def test_main_port_taken_by_another_program(monkeypatch, capsys):
    monkeypatch.setattr(app_module, "port_status", lambda **kwargs: "other")
    monkeypatch.setattr(app_module.sys, "argv", ["app.py", "--no-browser"])
    with pytest.raises(SystemExit) as exit_info:
        app_module.main()
    assert exit_info.value.code == 1
    assert "Port 8787 is in use by another program" in capsys.readouterr().out


def test_version_route(tmp_path, fake_fetch, monkeypatch):
    monkeypatch.delenv("RETRO_UV", raising=False)
    release = {"tag": "v99.0.0", "url": "https://github.com/kandooswill/retro-ears/releases/tag/v99.0.0"}
    info = local_client(build_app(tmp_path, fake_fetch, checker=FakeChecker(release))).get("/api/version").json()
    assert info["app"] == (ROOT / "VERSION").read_text("utf-8").strip()
    assert (info["latest_app"], info["release_url"], info["can_update"]) == ("99.0.0", release["url"], False)
    assert info["ytdlp"]
    assert isinstance(info["started"], float)


def test_update_needs_the_launcher(client, monkeypatch):
    monkeypatch.delenv("RETRO_UV", raising=False)
    response = client.post("/api/update")
    assert response.status_code == 400
    assert response.json() == {"error": "Updating only works when retro-ears is started with its launcher"}


def test_update_refused_while_downloading(tmp_path, fake_fetch, monkeypatch):
    uv = tmp_path / "uv"
    uv.write_text("")
    monkeypatch.setenv("RETRO_UV", str(uv))
    release = threading.Event()
    base = fake_fetch()

    def slow_fetch(track, fmt, workdir):
        release.wait(5)
        return base(track, fmt, workdir)

    manager = jobs.JobManager(root=tmp_path / "jobs", fetch=slow_fetch, match=lambda track: track)
    client = local_client(build_app(tmp_path, fake_fetch, manager=manager))
    client.post("/api/jobs", json={"tracks": [{"title": "a", "artist": "b", "video_id": "v"}]})
    response = client.post("/api/update")
    release.set()
    assert response.status_code == 409
    assert response.json() == {"error": "Wait for the current download to finish"}


def test_update_success_restarts(tmp_path, fake_fetch, monkeypatch):
    uv = tmp_path / "uv"
    uv.write_text("")
    monkeypatch.setenv("RETRO_UV", str(uv))
    monkeypatch.setattr(app_module.updates, "update_ytdlp", lambda: True)
    restarts = []
    client = local_client(build_app(tmp_path, fake_fetch, restart=lambda: restarts.append(True)))
    response = client.post("/api/update")
    assert response.json() == {"ok": True, "restarting": True}
    assert restarts == [True]


def test_update_failure_keeps_running(tmp_path, fake_fetch, monkeypatch):
    uv = tmp_path / "uv"
    uv.write_text("")
    monkeypatch.setenv("RETRO_UV", str(uv))
    monkeypatch.setattr(app_module.updates, "update_ytdlp", lambda: False)
    restarts = []
    client = local_client(build_app(tmp_path, fake_fetch, restart=lambda: restarts.append(True)))
    response = client.post("/api/update")
    assert response.status_code == 502
    assert response.json() == {"error": "Update failed — check your internet connection"}
    assert restarts == []
