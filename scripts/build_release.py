"""Build the downloadable retro-ears zips for macOS and Windows.

Usage: uv run python scripts/build_release.py --platform mac|windows [--uv-version 0.12.15] [--out dist]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import tarfile
import zipfile
from pathlib import Path
from typing import Callable

import certifi
import httpx

ROOT = Path(__file__).resolve().parent.parent
APP_FILES = [
    "app.py", "devices.py", "download.py", "ipod.py", "jobs.py", "links.py", "models.py", "tags.py", "updates.py", "ytmusic.py",
    "static/index.html", "pyproject.toml", "uv.lock", ".python-version", "VERSION", "README.md", "LICENSE",
]
LAUNCHERS = {"mac": "Start retro-ears.command", "windows": "Start retro-ears.bat"}
UV_ASSETS = {
    "mac": [("uv-aarch64-apple-darwin.tar.gz", "bin/uv-arm64"), ("uv-x86_64-apple-darwin.tar.gz", "bin/uv-x86_64")],
    "windows": [("uv-x86_64-pc-windows-msvc.zip", "bin/uv.exe")],
}
EXECUTABLE, REGULAR = 0o755, 0o644


def download(url: str) -> bytes:
    response = httpx.get(url, follow_redirects=True, timeout=120, verify=certifi.where())
    response.raise_for_status()
    return response.content


def extract_uv(asset: str, archive: bytes) -> bytes:
    if asset.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            return bundle.read("uv.exe")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        member = next(m for m in bundle.getmembers() if Path(m.name).name == "uv")
        return bundle.extractfile(member).read()


def fetch_uv(asset: str, version: str, get: Callable[[str], bytes] = download) -> bytes:
    url = f"https://github.com/astral-sh/uv/releases/download/{version}/{asset}"
    archive = get(url)
    expected = get(f"{url}.sha256").decode().split()[0]
    if hashlib.sha256(archive).hexdigest() != expected:
        raise SystemExit(f"Checksum mismatch for {asset}")
    return extract_uv(asset, archive)


def launcher_bytes(name: str) -> bytes:
    lf = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
    return lf.replace(b"\n", b"\r\n") if name.endswith(".bat") else lf  # cmd needs CRLF, bash needs LF


def add(bundle: zipfile.ZipFile, arcname: str, data: bytes, mode: int) -> None:
    info = zipfile.ZipInfo(f"retro-ears/{arcname}", date_time=(2026, 1, 1, 0, 0, 0))
    info.create_system = 3  # Unix, so Archive Utility keeps the executable bit
    info.external_attr = (0o100000 | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    bundle.writestr(info, data)


def build(platform: str, uv_version: str, out: Path, get: Callable[[str], bytes] = download) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"retro-ears-{platform}.zip"
    with zipfile.ZipFile(target, "w") as bundle:
        for name in APP_FILES:
            add(bundle, name, (ROOT / name).read_bytes(), REGULAR)
        launcher = LAUNCHERS[platform]
        add(bundle, launcher, launcher_bytes(launcher), EXECUTABLE)
        for asset, arcname in UV_ASSETS[platform]:
            add(bundle, arcname, fetch_uv(asset, uv_version, get), EXECUTABLE)
    return target


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build a retro-ears release zip.")
    parser.add_argument("--platform", choices=sorted(LAUNCHERS), required=True)
    parser.add_argument("--uv-version", default="0.12.15")
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    args = parser.parse_args(argv)
    print(build(args.platform, args.uv_version, args.out))


if __name__ == "__main__":
    main()
