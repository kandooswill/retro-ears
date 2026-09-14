import io
import subprocess

import imageio_ffmpeg
import pytest
from PIL import Image

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
