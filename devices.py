"""Find plugged-in iPods running Rockbox."""
from __future__ import annotations

import shutil
import string
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Device:
    id: str
    name: str
    mount: Path
    free_bytes: int

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "free_bytes": self.free_bytes}


def candidate_mounts(platform: str | None = None, volumes: Path = Path("/Volumes")) -> list[Path]:
    platform = platform or sys.platform
    if platform == "win32":
        return [Path(f"{letter}:\\") for letter in string.ascii_uppercase[3:]]  # D: to Z:
    if platform == "darwin":
        try:
            return sorted(path for path in volumes.iterdir() if path.is_dir())
        except OSError:
            return []
    return []


def _windows_label(mount: Path) -> str:
    import ctypes

    buffer = ctypes.create_unicode_buffer(261)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(ctypes.c_wchar_p(str(mount)), buffer, len(buffer), None, None, None, None, 0)
    return buffer.value if ok else ""


def volume_name(mount: Path, platform: str | None = None) -> str:
    if (platform or sys.platform) == "win32":
        return _windows_label(mount) or f"iPod ({str(mount)[:2]})"
    return mount.name


def find_rockbox(platform: str | None = None, volumes: Path = Path("/Volumes")) -> list[Device]:
    found = []
    for mount in candidate_mounts(platform, volumes):
        try:
            if not (mount / ".rockbox").is_dir():
                continue
            free = shutil.disk_usage(mount).free
        except OSError:  # empty card readers and ejecting drives
            continue
        found.append(Device(id=str(mount), name=volume_name(mount, platform), mount=mount, free_bytes=free))
    return found
