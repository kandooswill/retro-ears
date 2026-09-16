from pathlib import Path

import devices


def test_finds_rockbox_volumes_on_macos(tmp_path):
    (tmp_path / "IPOD" / ".rockbox").mkdir(parents=True)
    (tmp_path / "Backup").mkdir()
    (tmp_path / "notes.txt").write_text("x")
    found = devices.find_rockbox(platform="darwin", volumes=tmp_path)
    assert [(d.id, d.name, d.mount) for d in found] == [(str(tmp_path / "IPOD"), "IPOD", tmp_path / "IPOD")]
    assert found[0].free_bytes > 0


def test_missing_volumes_folder_finds_nothing(tmp_path):
    assert devices.find_rockbox(platform="darwin", volumes=tmp_path / "missing") == []


def test_windows_candidates_are_drives_d_to_z():
    assert [str(mount)[:2] for mount in devices.candidate_mounts("win32")] == [f"{letter}:" for letter in "DEFGHIJKLMNOPQRSTUVWXYZ"]


def test_other_platforms_have_no_candidates():
    assert devices.candidate_mounts("linux") == []


def test_windows_name_uses_label_or_drive_letter(monkeypatch):
    monkeypatch.setattr(devices, "_windows_label", lambda mount: "")
    assert devices.volume_name(Path("E:\\"), platform="win32") == "iPod (E:)"
    monkeypatch.setattr(devices, "_windows_label", lambda mount: "MY IPOD")
    assert devices.volume_name(Path("E:\\"), platform="win32") == "MY IPOD"


def test_windows_detection_checks_each_candidate(monkeypatch, tmp_path):
    ipod = tmp_path / "E"
    (ipod / ".rockbox").mkdir(parents=True)
    monkeypatch.setattr(devices, "candidate_mounts", lambda *args, **kwargs: [tmp_path / "D", ipod])
    monkeypatch.setattr(devices, "_windows_label", lambda mount: "MY IPOD")
    assert [d.name for d in devices.find_rockbox(platform="win32")] == ["MY IPOD"]


def test_device_public_hides_the_path_object():
    device = devices.Device(id="/Volumes/IPOD", name="IPOD", mount=Path("/Volumes/IPOD"), free_bytes=123)
    assert device.public() == {"id": "/Volumes/IPOD", "name": "IPOD", "free_bytes": 123}
