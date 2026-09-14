import io
import subprocess
import time

import imageio_ffmpeg
import pytest
from PIL import Image

import download
from models import RetroError

CODEC_ARGS = {
    "m4a": ["-c:a", "aac", "-b:a", "128k"],
    "opus": ["-c:a", "libopus", "-b:a", "96k"],
    "mp3": ["-c:a", "libmp3lame", "-b:a", "128k"],
}


@pytest.fixture
def silent_file(tmp_path):
    """Make a 1-second silent audio file with the bundled ffmpeg."""

    def make(ext, name="silent"):
        path = tmp_path / f"{name}.{ext}"
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "1",
                *CODEC_ARGS[ext], str(path),
            ],
            check=True,
        )
        return path

    return make


@pytest.fixture
def jpeg_bytes():
    def make(size=(800, 800), progressive=True):
        buffer = io.BytesIO()
        Image.new("RGB", size, (200, 60, 40)).save(buffer, "JPEG", progressive=progressive)
        return buffer.getvalue()

    return make


@pytest.fixture
def fake_fetch():
    """Stand-in for download.fetch that writes a tiny file instead of downloading."""

    def make(fail_titles=(), calls=None):
        def fetch(track, fmt, workdir, cookie_source="off"):
            if calls is not None:
                calls.append((track, fmt, cookie_source))
            if track.title in fail_titles:
                raise RetroError("Unavailable on YouTube")
            path = download.unique_path(workdir, download.safe_filename(f"{track.artist} - {track.title}"), fmt)
            path.write_bytes(b"audio")
            return download.Result(path=path, quality="AAC 130")

        return fetch

    return make


@pytest.fixture
def wait_job():
    def wait(manager, job_id, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = manager.get(job_id).public()
            if status["status"] != "running":
                return status
            time.sleep(0.02)
        raise AssertionError("job did not finish in time")

    return wait
