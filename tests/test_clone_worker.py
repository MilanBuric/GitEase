"""
Unit tests for clone_worker.CloneWorker.

Run with:
    pytest tests/

These mock out GitPython entirely, so no real network calls or git
processes run -- they test GitEase's own logic (validation, token
handling, error scrubbing), not git itself.
"""

import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clone_worker import CloneWorker


class DummySignal:
    """Stand-in for a Qt Signal so CloneWorker.run() can be called directly
    in a test, outside of a real QThread/QApplication event loop."""

    def __init__(self):
        self.emitted = []

    def emit(self, value):
        self.emitted.append(value)


def make_worker(url="https://github.com/user/repo.git", dest=None, token=None):
    dest = dest or tempfile.mkdtemp()
    worker = CloneWorker(url, dest, token)
    # Replace the real Qt signals with plain recorders so run() can execute
    # synchronously without a Qt application/event loop.
    worker.log_message = DummySignal()
    worker.finished_ok = DummySignal()
    worker.failed = DummySignal()
    return worker, dest


def test_authed_url_injects_token_for_https():
    worker, _ = make_worker(url="https://github.com/user/repo.git", token="abc123")
    assert worker._authed_url() == "https://abc123@github.com/user/repo.git"


def test_authed_url_leaves_ssh_untouched():
    worker, _ = make_worker(url="git@github.com:user/repo.git", token="abc123")
    assert worker._authed_url() == "git@github.com:user/repo.git"


def test_authed_url_no_token_unchanged():
    worker, _ = make_worker(url="https://github.com/user/repo.git", token=None)
    assert worker._authed_url() == "https://github.com/user/repo.git"


def test_scrub_removes_token_from_messages():
    worker, _ = make_worker(token="super-secret-token")
    text = "fatal: could not read https://super-secret-token@github.com/user/repo.git"
    scrubbed = worker._scrub(text)
    assert "super-secret-token" not in scrubbed
    assert "****" in scrubbed


def test_run_fails_on_nonempty_destination():
    dest = tempfile.mkdtemp()
    with open(os.path.join(dest, "existing_file.txt"), "w") as f:
        f.write("not empty")

    worker, _ = make_worker(dest=dest)
    worker.run()

    assert len(worker.failed.emitted) == 1
    assert "not empty" in worker.failed.emitted[0]
    assert len(worker.finished_ok.emitted) == 0


@patch("clone_worker.Repo.clone_from")
def test_run_succeeds_and_reports_origin(mock_clone_from):
    mock_repo = MagicMock()
    mock_repo.remotes.origin.url = "https://github.com/user/repo.git"
    mock_clone_from.return_value = mock_repo

    dest = tempfile.mkdtemp()
    os.rmdir(dest)  # clone_from expects to create this itself
    worker, _ = make_worker(url="https://github.com/user/repo.git", dest=dest)
    worker.run()

    assert worker.finished_ok.emitted == [dest]
    assert worker.failed.emitted == []
    mock_clone_from.assert_called_once()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))