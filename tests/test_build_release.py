import hashlib
import io
import tarfile
import zipfile

import pytest

from scripts import build_release


def fake_get():
    def tar_gz(folder):
        data = f"#!fake uv {folder}".encode()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            info = tarfile.TarInfo(f"{folder}/uv")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        return buffer.getvalue()

    def windows_zip():
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("uv.exe", b"MZ fake uv")
            archive.writestr("uvx.exe", b"MZ")
        return buffer.getvalue()

    archives = {
        "uv-aarch64-apple-darwin.tar.gz": tar_gz("uv-aarch64-apple-darwin"),
        "uv-x86_64-apple-darwin.tar.gz": tar_gz("uv-x86_64-apple-darwin"),
        "uv-x86_64-pc-windows-msvc.zip": windows_zip(),
    }

    def get(url):
        name = url.rsplit("/", 1)[1]
        if name.endswith(".sha256"):
            asset = name[: -len(".sha256")]
            return f"{hashlib.sha256(archives[asset]).hexdigest()}  {asset}\n".encode()
        return archives[name]

    return get


def mode(info):
    return (info.external_attr >> 16) & 0o777


def test_mac_zip(tmp_path):
    path = build_release.build("mac", "0.12.15", tmp_path, get=fake_get())
    assert path == tmp_path / "retro-ears-mac.zip"
    with zipfile.ZipFile(path) as archive:
        infos = {info.filename: info for info in archive.infolist()}
        assert {f"retro-ears/{name}" for name in build_release.APP_FILES} <= set(infos)
        assert "retro-ears/Start retro-ears.command" in infos
        assert not any(name.endswith(".bat") or "/tests/" in name or "/docs/" in name for name in infos)
        assert mode(infos["retro-ears/Start retro-ears.command"]) == 0o755
        assert mode(infos["retro-ears/bin/uv-arm64"]) == 0o755
        assert mode(infos["retro-ears/bin/uv-x86_64"]) == 0o755
        assert mode(infos["retro-ears/app.py"]) == 0o644
        assert archive.read("retro-ears/bin/uv-arm64") == b"#!fake uv uv-aarch64-apple-darwin"
        assert b"\r\n" not in archive.read("retro-ears/Start retro-ears.command")


def test_windows_zip(tmp_path):
    path = build_release.build("windows", "0.12.15", tmp_path, get=fake_get())
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        assert "retro-ears/Start retro-ears.bat" in names
        assert "retro-ears/bin/uv.exe" in names
        assert not any(name.endswith(".command") for name in names)
        assert archive.read("retro-ears/bin/uv.exe") == b"MZ fake uv"
        launcher = archive.read("retro-ears/Start retro-ears.bat")
        assert b"\n" not in launcher.replace(b"\r\n", b"")  # every line ends with CRLF


def test_checksum_mismatch_stops_the_build(tmp_path):
    good = fake_get()

    def tampered(url):
        return b"0" * 64 + b"  tampered\n" if url.endswith(".sha256") else good(url)

    with pytest.raises(SystemExit, match="Checksum mismatch"):
        build_release.build("windows", "0.12.15", tmp_path, get=tampered)


def test_every_app_module_is_packaged():
    modules = {path.name for path in build_release.ROOT.glob("*.py")}
    assert modules <= set(build_release.APP_FILES)
