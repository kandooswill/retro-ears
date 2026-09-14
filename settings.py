"""The one setting retro-ears keeps: where to read a YouTube Premium login from."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEFAULTS = {"cookie_source": "off"}
BROWSERS = ("firefox", "safari", "chrome")


def settings_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "retro-ears" / "settings.json"


def validate_cookie_source(value: str, platform: str | None = None) -> str:
    platform = platform or sys.platform
    if value == "off":
        return value
    if value in BROWSERS:
        if value == "safari" and platform != "darwin":
            raise ValueError("Safari is only available on macOS")
        if value == "chrome" and platform == "win32":
            raise ValueError("Chrome logins can't be read on Windows — use Firefox or a cookies.txt file")
        return value
    if value.startswith("file:"):
        cookie_file = value[len("file:"):].strip()
        if not cookie_file or not Path(cookie_file).is_file():
            raise ValueError("cookies.txt file not found")
        return f"file:{cookie_file}"
    raise ValueError("Unknown login source")


def load(path: Path | None = None) -> dict:
    path = path or settings_path()
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULTS)
    if not isinstance(data, dict):
        return dict(DEFAULTS)
    return {**DEFAULTS, **{key: value for key, value in data.items() if key in DEFAULTS}}


def save(values: dict, path: Path | None = None) -> dict:
    path = path or settings_path()
    merged = {**load(path), "cookie_source": validate_cookie_source(values.get("cookie_source", "off"))}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2), "utf-8")
    return merged
