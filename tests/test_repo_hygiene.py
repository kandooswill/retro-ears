import codecs
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Major-label names and IDs that must never appear in the repo. ROT13-encoded so this file doesn't contain them.
BANNED = [
    codecs.decode(term, "rot13")
    for term in (
        "jrrxaq", "oyvaqvat yvtugf", "fgneobl", "qnsg chax", "zvpunry wnpxfba", "zbetna jnyyra", "gnzr vzcnyn",
        "37v9qDMS1Q", "cy.s4q106srq", "W7c4omdYiPj", "3_t2ha5Z350", "4AEKk6H8NOD",
        "4lC0uqXBMCAfukHBwL0pMw", "7oknSM1B3pUxtYXZfqP3kE", "nsgre-ubhef/1499378108",
    )
]
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".zip"}


def tracked_files():
    output = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    for name in output.splitlines():
        path = ROOT / name
        if path.name in {"test_repo_hygiene.py", "uv.lock"} or path.suffix.lower() in SKIP_SUFFIXES or not path.is_file():
            continue
        yield path


def test_no_major_label_music_references():
    offenders = []
    for path in tracked_files():
        text = path.read_text("utf-8", errors="ignore").lower()
        offenders += [f"{path.relative_to(ROOT)}: {term}" for term in BANNED if term.lower() in text]
    assert offenders == []


def test_version_file_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", (ROOT / "VERSION").read_text("utf-8").strip())


def test_pyproject_version_matches_version_file():
    pyproject = (ROOT / "pyproject.toml").read_text("utf-8")
    version = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE).group(1)
    assert version == (ROOT / "VERSION").read_text("utf-8").strip()


def test_old_install_files_are_gone():
    for name in ("requirements.txt", "requirements-dev.txt", "run.sh", "run.ps1"):
        assert not (ROOT / name).exists(), name


def test_license_is_gpl3():
    text = (ROOT / "LICENSE").read_text("utf-8")
    assert "GNU GENERAL PUBLIC LICENSE" in text
    assert "Version 3, 29 June 2007" in text


def test_mac_launcher_is_executable_in_git():
    output = subprocess.run(["git", "ls-files", "-s", "Start retro-ears.command"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert output.split()[0] == "100755"


def test_line_endings_are_pinned():
    text = (ROOT / ".gitattributes").read_text("utf-8")
    assert "*.command text eol=lf" in text
    assert "*.bat text eol=crlf" in text


def test_windows_launcher_is_ascii():
    (ROOT / "Start retro-ears.bat").read_bytes().decode("ascii")
