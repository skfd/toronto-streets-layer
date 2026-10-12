"""update's skip rule and failure exit.

"Source unchanged" must mean the current release is live, not merely on disk:
a build that dies after the download must be rebuilt by the scheduled retry,
not skipped -- otherwise the month's run is lost without a word.
"""

import argparse
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import run  # noqa: E402
from src import config  # noqa: E402

RELEASE = "centreline-2026-10-09.geojson"
STEPS = ("slim", "history", "vector", "raster", "site", "publish")


class Pipeline:
    """Every update step stubbed: records what ran, fails the step named."""

    def __init__(self):
        self.ran = []
        self.status = "SKIPPED"   # what the download reports
        self.fail = None


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "LAST_BUILT_PATH", str(tmp_path / ".last-built.json"))
    monkeypatch.setattr(config, "LAST_PUBLISHED_PATH",
                        str(tmp_path / ".last-published.json"))
    (tmp_path / RELEASE).write_text("{}", encoding="utf-8")
    p = Pipeline()
    monkeypatch.setattr(run, "cmd_download",
                        lambda a: (p.status, str(tmp_path / RELEASE)))
    for step in STEPS:
        def stub(args, step=step):
            if step == p.fail:
                raise RuntimeError(f"{step} broke")
            p.ran.append(step)
        monkeypatch.setattr(run, f"cmd_{step}", stub)
    return p


def args(force=False):
    return argparse.Namespace(force=force, command="update")


def test_a_downloaded_but_unpublished_release_is_rebuilt(pipeline):
    # Last run downloaded 10-09 then died; the download now says SKIPPED.
    run.cmd_update(args())
    assert pipeline.ran == list(STEPS)


def test_the_published_release_is_skipped(pipeline):
    run._write_marker(config.LAST_PUBLISHED_PATH, RELEASE)
    run.cmd_update(args())
    assert pipeline.ran == []


def test_force_rebuilds_the_published_release(pipeline):
    run._write_marker(config.LAST_PUBLISHED_PATH, RELEASE)
    run.cmd_update(args(force=True))
    assert pipeline.ran == list(STEPS)


def test_a_failed_build_leaves_the_release_unpublished_so_the_retry_rebuilds(
        pipeline):
    pipeline.status = "DOWNLOADED"
    pipeline.fail = "raster"
    with pytest.raises(RuntimeError):
        run.cmd_update(args())
    assert run._read_marker(config.LAST_PUBLISHED_PATH) is None

    # The scheduler's retry: the download is now SKIPPED, the build runs again.
    pipeline.status, pipeline.fail = "SKIPPED", None
    pipeline.ran.clear()
    run.cmd_update(args())
    assert pipeline.ran == list(STEPS)


def test_a_successful_publish_marks_the_release_published(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LAST_BUILT_PATH", str(tmp_path / ".last-built.json"))
    monkeypatch.setattr(config, "LAST_PUBLISHED_PATH",
                        str(tmp_path / ".last-published.json"))
    monkeypatch.setattr("src.publish.publish", lambda: None)
    run._write_marker(config.LAST_BUILT_PATH, RELEASE)
    run.cmd_publish(args())
    assert run._read_marker(config.LAST_PUBLISHED_PATH) == RELEASE


def test_a_failed_push_marks_nothing_published(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LAST_BUILT_PATH", str(tmp_path / ".last-built.json"))
    monkeypatch.setattr(config, "LAST_PUBLISHED_PATH",
                        str(tmp_path / ".last-published.json"))

    def push_fails():
        raise RuntimeError("git push --force origin gh-pages failed (exit 1)")

    monkeypatch.setattr("src.publish.publish", push_fails)
    run._write_marker(config.LAST_BUILT_PATH, RELEASE)
    with pytest.raises(RuntimeError):
        run.cmd_publish(args())
    assert run._read_marker(config.LAST_PUBLISHED_PATH) is None


def test_any_failure_exits_nonzero_with_an_error_line(monkeypatch, capsys):
    def broken(a):
        raise RuntimeError("tippecanoe exited 1")

    monkeypatch.setitem(run.COMMANDS, "update", (broken, "update"))
    monkeypatch.setattr(sys, "argv", ["run.py", "update"])
    with pytest.raises(SystemExit) as exit_:
        run.main()
    assert exit_.value.code == run.EXIT_FAILED != 0
    out = capsys.readouterr().out
    assert "ERROR " in out
    assert "run.py update failed: RuntimeError: tippecanoe exited 1" in out
