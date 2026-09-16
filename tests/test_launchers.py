import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MAC = "Start retro-ears.command"
WIN = "Start retro-ears.bat"

FAKE_UV_SH = """#!/bin/bash
echo "$(basename "$0") $*" >> "$FAKE_LOG"
echo "env RETRO_UV=$RETRO_UV UV_PROJECT_ENVIRONMENT=$UV_PROJECT_ENVIRONMENT UV_PYTHON_PREFERENCE=$UV_PYTHON_PREFERENCE" >> "$FAKE_LOG"
if [ "$1" = "sync" ]; then exit "${FAKE_SYNC_EXIT:-0}"; fi
count=$(cat "$FAKE_COUNT" 2>/dev/null || echo 0)
count=$((count + 1))
echo "$count" > "$FAKE_COUNT"
codes=(${FAKE_RUN_CODES:-0})
exit "${codes[$((count - 1))]:-0}"
"""

FAKE_UV_CMD = "\r\n".join([
    "@echo off",
    'echo uv %*>>"%FAKE_LOG%"',
    'echo env RETRO_UV=%RETRO_UV% UV_PROJECT_ENVIRONMENT=%UV_PROJECT_ENVIRONMENT%>>"%FAKE_LOG%"',
    'if "%1"=="sync" exit /b %FAKE_SYNC_EXIT%',
    'set /p N=<"%FAKE_COUNT%"',
    "set /a N=N+1",
    '>"%FAKE_COUNT%" echo %N%',
    'if "%N%"=="1" exit /b %FAKE_FIRST_RUN_EXIT%',
    "exit /b 0",
]) + "\r\n"


def make_app(tmp_path, launcher):
    app = tmp_path / "retro-ears"
    app.mkdir()
    shutil.copy(ROOT / launcher, app / launcher)
    (app / "VERSION").write_text("9.9.9", "utf-8")
    return app


def commands(log):
    return [line for line in log.splitlines() if not line.startswith("env ")]


@pytest.mark.skipif(sys.platform == "win32", reason="macOS launcher")
class TestMacLauncher:
    def launch(self, app, tmp_path, *, bundled=True, sync_exit="0", run_codes="0", path="/usr/bin:/bin"):
        log, count = tmp_path / "uv.log", tmp_path / "count"
        if bundled:
            (app / "bin").mkdir(exist_ok=True)
            for name in ("uv-arm64", "uv-x86_64"):
                fake = app / "bin" / name
                fake.write_text(FAKE_UV_SH, "utf-8")
                fake.chmod(0o755)
        env = {
            "PATH": path, "HOME": str(tmp_path), "RETRO_NO_PAUSE": "1", "FAKE_LOG": str(log),
            "FAKE_COUNT": str(count), "FAKE_SYNC_EXIT": sync_exit, "FAKE_RUN_CODES": run_codes,
        }
        result = subprocess.run(["bash", str(app / MAC), "--no-browser"], env=env, capture_output=True, text=True, timeout=30)
        return result, log.read_text("utf-8") if log.exists() else ""

    def test_first_run_sets_up_then_restarts_on_42(self, tmp_path):
        app = make_app(tmp_path, MAC)
        result, log = self.launch(app, tmp_path, run_codes="42 0")
        uv = "uv-arm64" if platform.machine() == "arm64" else "uv-x86_64"
        run = f"{uv} run --no-sync python app.py --no-browser"
        assert commands(log) == [f"{uv} sync --frozen --no-dev", run, run]
        assert "Setting up retro-ears — the first run takes 1–2 minutes…" in result.stdout
        assert "Restarting…" in result.stdout
        assert "retro-ears stopped. You can close this window." in result.stdout
        assert result.returncode == 0
        assert (app / ".runtime" / "installed-version").read_text("utf-8") == "9.9.9"
        env_line = next(line for line in log.splitlines() if line.startswith("env "))
        assert f"RETRO_UV={app / 'bin' / uv}" in env_line
        assert f"UV_PROJECT_ENVIRONMENT={app / '.runtime' / 'venv'}" in env_line
        assert "UV_PYTHON_PREFERENCE=only-managed" in env_line

    def test_same_version_skips_setup(self, tmp_path):
        app = make_app(tmp_path, MAC)
        (app / ".runtime").mkdir()
        (app / ".runtime" / "installed-version").write_text("9.9.9", "utf-8")
        result, log = self.launch(app, tmp_path)
        assert not any(" sync " in line for line in commands(log))
        assert "Setting up" not in result.stdout

    def test_new_version_sets_up_again(self, tmp_path):
        app = make_app(tmp_path, MAC)
        (app / ".runtime").mkdir()
        (app / ".runtime" / "installed-version").write_text("1.0.0", "utf-8")
        _, log = self.launch(app, tmp_path)
        assert " sync --frozen --no-dev" in commands(log)[0]

    def test_setup_failure_stops(self, tmp_path):
        app = make_app(tmp_path, MAC)
        result, log = self.launch(app, tmp_path, sync_exit="1")
        assert result.returncode == 1
        assert "Setup failed — check your internet connection and try again" in result.stdout
        assert not any(" run " in line for line in commands(log))
        assert not (app / ".runtime" / "installed-version").exists()

    def test_other_exit_codes_end_the_loop(self, tmp_path):
        app = make_app(tmp_path, MAC)
        result, log = self.launch(app, tmp_path, run_codes="1")
        assert result.returncode == 1
        assert len([line for line in commands(log) if " run " in line]) == 1

    def test_uses_uv_from_path_when_not_bundled(self, tmp_path):
        tools = tmp_path / "tools"
        tools.mkdir()
        fake = tools / "uv"
        fake.write_text(FAKE_UV_SH, "utf-8")
        fake.chmod(0o755)
        app = make_app(tmp_path, MAC)
        _, log = self.launch(app, tmp_path, bundled=False, path=f"{tools}:/usr/bin:/bin")
        assert commands(log)[0] == "uv sync --frozen --no-dev"

    def test_without_uv_points_to_releases(self, tmp_path):
        app = make_app(tmp_path, MAC)
        result, _ = self.launch(app, tmp_path, bundled=False)
        assert result.returncode == 1
        assert "Download retro-ears from https://github.com/kandooswill/retro-ears/releases" in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher")
class TestWindowsLauncher:
    def launch(self, app, tmp_path, *, sync_exit="0", first_run_exit="0", with_uv=True):
        tools = tmp_path / "tools"
        tools.mkdir(exist_ok=True)
        if with_uv:
            (tools / "uv.cmd").write_bytes(FAKE_UV_CMD.encode("ascii"))
        log, count = tmp_path / "uv.log", tmp_path / "count"
        count.write_text("0")
        env = {
            **os.environ, "PATH": f"{tools};{os.environ['SystemRoot']}\\System32", "RETRO_NO_PAUSE": "1",
            "FAKE_LOG": str(log), "FAKE_COUNT": str(count), "FAKE_SYNC_EXIT": sync_exit, "FAKE_FIRST_RUN_EXIT": first_run_exit,
        }
        result = subprocess.run(f'"{app / WIN}" --no-browser', shell=True, env=env, capture_output=True, text=True, timeout=60)
        return result, log.read_text() if log.exists() else ""

    def test_first_run_sets_up_then_restarts_on_42(self, tmp_path):
        app = make_app(tmp_path, WIN)
        result, log = self.launch(app, tmp_path, first_run_exit="42")
        run = "uv run --no-sync python app.py --no-browser"
        assert commands(log) == ["uv sync --frozen --no-dev", run, run]
        assert "Restarting..." in result.stdout
        assert (app / ".runtime" / "installed-version").read_text() == "9.9.9"
        assert f"UV_PROJECT_ENVIRONMENT={app}\\.runtime\\venv" in log

    def test_setup_failure_stops(self, tmp_path):
        app = make_app(tmp_path, WIN)
        result, log = self.launch(app, tmp_path, sync_exit="1")
        assert result.returncode == 1
        assert "Setup failed - check your internet connection and try again" in result.stdout
        assert not any(" run " in line for line in commands(log))

    def test_without_uv_points_to_releases(self, tmp_path):
        app = make_app(tmp_path, WIN)
        result, _ = self.launch(app, tmp_path, with_uv=False)
        assert result.returncode == 1
        assert "Download retro-ears from https://github.com/kandooswill/retro-ears/releases" in result.stdout
