import threading
import zipfile

import pytest

import jobs
from models import NotFound, RetroError, Track

TRACKS = [Track(title=f"Song {i}", artist="Artist", video_id=f"vid{i}") for i in range(3)]


def manager_for(tmp_path, fetch, **kwargs):
    return jobs.JobManager(root=tmp_path / "jobs", fetch=fetch, match=lambda track: track, **kwargs)


def test_playlist_job_builds_zip(tmp_path, fake_fetch, wait_job):
    manager = manager_for(tmp_path, fake_fetch())
    job = manager.start(TRACKS, "m4a", "My Mix")
    status = wait_job(manager, job.id)

    assert status["status"] == "done"
    assert (status["done"], status["failed"], status["total"]) == (3, 0, 3)
    assert status["current"] is None
    assert sorted(r["title"] for r in status["results"]) == ["Song 0", "Song 1", "Song 2"]
    assert all(r["quality"] == "AAC 130" for r in status["results"])

    path, filename = manager.file(job.id)
    assert filename == "My Mix.zip"
    with zipfile.ZipFile(path) as archive:
        assert sorted(archive.namelist()) == ["My Mix/Artist - Song 0.m4a", "My Mix/Artist - Song 1.m4a", "My Mix/Artist - Song 2.m4a"]
        assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())


def test_single_song_job_returns_the_file(tmp_path, fake_fetch, wait_job):
    manager = manager_for(tmp_path, fake_fetch())
    job = manager.start(TRACKS[:1], "opus", "Artist - Song 0")
    wait_job(manager, job.id)
    path, filename = manager.file(job.id)
    assert filename == "Artist - Song 0.opus"
    assert path.read_bytes() == b"audio"


def test_partial_failure_keeps_going(tmp_path, fake_fetch, wait_job):
    manager = manager_for(tmp_path, fake_fetch(fail_titles={"Song 1"}))
    job = manager.start(TRACKS, "m4a", "Mix")
    status = wait_job(manager, job.id)
    assert (status["status"], status["done"], status["failed"]) == ("done", 2, 1)
    assert {"title": "Song 1", "artist": "Artist", "error": "Unavailable on YouTube"} in status["results"]
    path, _ = manager.file(job.id)
    with zipfile.ZipFile(path) as archive:
        assert len(archive.namelist()) == 2


def test_all_failed_job_has_no_file(tmp_path, fake_fetch, wait_job):
    manager = manager_for(tmp_path, fake_fetch(fail_titles={"Song 0", "Song 1", "Song 2"}))
    job = manager.start(TRACKS, "m4a", "Mix")
    assert wait_job(manager, job.id)["status"] == "failed"
    with pytest.raises(RetroError, match="Nothing was downloaded"):
        manager.file(job.id)


def test_unexpected_errors_are_recorded(tmp_path, wait_job):
    def broken_fetch(track, fmt, workdir):
        raise ValueError("boom")

    manager = manager_for(tmp_path, broken_fetch)
    job = manager.start(TRACKS[:1], "m4a", "Mix")
    status = wait_job(manager, job.id)
    assert status["results"] == [{"title": "Song 0", "artist": "Artist", "error": "boom"}]


def test_match_failures_are_recorded(tmp_path, fake_fetch, wait_job):
    def no_match(track):
        raise RetroError("Not found on YouTube Music")

    manager = jobs.JobManager(root=tmp_path / "jobs", fetch=fake_fetch(), match=no_match)
    job = manager.start([Track(title="Lost", artist="Nobody")], "m4a", "Mix")
    assert wait_job(manager, job.id)["results"] == [{"title": "Lost", "artist": "Nobody", "error": "Not found on YouTube Music"}]


def test_cancel_skips_queued_songs(tmp_path, fake_fetch, wait_job):
    started, release = threading.Event(), threading.Event()
    base = fake_fetch()

    def slow_fetch(track, fmt, workdir):
        started.set()
        release.wait(5)
        return base(track, fmt, workdir)

    manager = manager_for(tmp_path, slow_fetch, workers=1)
    job = manager.start(TRACKS, "m4a", "Mix")
    assert started.wait(5)
    manager.cancel(job.id)
    release.set()
    status = wait_job(manager, job.id)
    assert (status["status"], status["done"], status["cancelled"]) == ("done", 1, True)


def test_file_while_running_raises(tmp_path, fake_fetch, wait_job):
    release = threading.Event()
    base = fake_fetch()

    def slow_fetch(track, fmt, workdir):
        release.wait(5)
        return base(track, fmt, workdir)

    manager = manager_for(tmp_path, slow_fetch)
    job = manager.start(TRACKS[:1], "m4a", "Mix")
    with pytest.raises(RetroError, match="Still downloading"):
        manager.file(job.id)
    release.set()
    wait_job(manager, job.id)


def test_format_is_passed_to_fetch(tmp_path, fake_fetch, wait_job):
    calls = []
    manager = manager_for(tmp_path, fake_fetch(calls=calls))
    job = manager.start(TRACKS[:1], "mp3", "Mix")
    wait_job(manager, job.id)
    assert calls[0][1] == "mp3"


def test_unknown_job_raises_not_found(tmp_path, fake_fetch):
    with pytest.raises(NotFound, match="Download not found"):
        manager_for(tmp_path, fake_fetch()).get("nope")


def test_start_validates_input(tmp_path, fake_fetch):
    manager = manager_for(tmp_path, fake_fetch())
    with pytest.raises(ValueError):
        manager.start([], "m4a", "Mix")
    with pytest.raises(ValueError):
        manager.start(TRACKS, "wav", "Mix")


def test_cleanup_removes_jobs_older_than_an_hour(tmp_path, fake_fetch, wait_job):
    manager = manager_for(tmp_path, fake_fetch())
    job = manager.start(TRACKS[:1], "m4a", "Mix")
    wait_job(manager, job.id)
    manager.cleanup(now=job.finished_at + jobs.KEEP_SECONDS - 1)
    assert job.id in manager.jobs
    manager.cleanup(now=job.finished_at + jobs.KEEP_SECONDS + 1)
    assert job.id not in manager.jobs
    assert not job.dir.exists()


def test_clear_root_empties_the_folder(tmp_path):
    (tmp_path / "old-job").mkdir()
    (tmp_path / "old-job" / "song.m4a").write_bytes(b"x")
    jobs.clear_root(tmp_path)
    assert tmp_path.exists()
    assert list(tmp_path.iterdir()) == []


def test_busy_while_a_job_runs(tmp_path, fake_fetch, wait_job):
    release = threading.Event()
    base = fake_fetch()

    def slow_fetch(track, fmt, workdir):
        release.wait(5)
        return base(track, fmt, workdir)

    manager = manager_for(tmp_path, slow_fetch)
    assert manager.busy() is False
    job = manager.start(TRACKS[:1], "m4a", "Mix")
    assert manager.busy() is True
    release.set()
    wait_job(manager, job.id)
    assert manager.busy() is False
