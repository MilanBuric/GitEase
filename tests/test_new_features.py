"""
Unit tests for the newer GitEase modules: branch listing, the repo
registry (dashboard persistence), and commit/push. All git and Qt
calls are mocked, so these run instantly with no real network/git/UI.
"""

import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from branch_worker import BranchListWorker
from commit_push_worker import CommitPushWorker


class DummySignal:
    def __init__(self):
        self.emitted = []

    def emit(self, *args):
        self.emitted.append(args if len(args) > 1 else (args[0] if args else None))


# ---------------- BranchListWorker ----------------

def make_branch_worker(url="https://github.com/user/repo.git", token=None):
    worker = BranchListWorker(url, token)
    worker.branches_ready = DummySignal()
    worker.failed = DummySignal()
    return worker


def test_branch_authed_url_injects_token():
    worker = make_branch_worker(token="abc123")
    assert worker._authed_url() == "https://abc123@github.com/user/repo.git"


@patch("branch_worker.Git")
def test_run_parses_branches_and_default(mock_git_cls):
    mock_git = MagicMock()
    mock_git.ls_remote.side_effect = [
        "ref: refs/heads/main\tHEAD",   # --symref HEAD
        "abc\trefs/heads/main\ndef\trefs/heads/develop",  # --heads
    ]
    mock_git_cls.return_value = mock_git

    worker = make_branch_worker()
    worker.run()

    assert len(worker.branches_ready.emitted) == 1
    branches, default_branch = worker.branches_ready.emitted[0]
    assert set(branches) == {"main", "develop"}
    assert default_branch == "main"
    assert worker.failed.emitted == []


@patch("branch_worker.Git")
def test_run_fails_when_no_branches_found(mock_git_cls):
    mock_git = MagicMock()
    mock_git.ls_remote.side_effect = ["", ""]
    mock_git_cls.return_value = mock_git

    worker = make_branch_worker()
    worker.run()

    assert worker.branches_ready.emitted == []
    assert len(worker.failed.emitted) == 1


# ---------------- CommitPushWorker ----------------

def make_commit_worker(path=None, message="Test commit"):
    path = path or tempfile.mkdtemp()
    worker = CommitPushWorker(path, message)
    worker.log_message = DummySignal()
    worker.finished_ok = DummySignal()
    worker.failed = DummySignal()
    return worker, path


def test_commit_push_fails_on_missing_folder():
    worker, _ = make_commit_worker(path="/no/such/folder")
    worker.run()
    assert len(worker.failed.emitted) == 1
    assert "does not exist" in worker.failed.emitted[0]


def test_commit_push_fails_on_empty_message():
    worker, _ = make_commit_worker(message="   ")
    worker.run()
    assert len(worker.failed.emitted) == 1
    assert "empty" in worker.failed.emitted[0]


@patch("commit_push_worker.Repo")
def test_commit_push_reports_nothing_to_commit(mock_repo_cls):
    mock_repo = MagicMock()
    mock_repo.is_dirty.return_value = False
    mock_repo_cls.return_value = mock_repo

    worker, _ = make_commit_worker()
    worker.run()

    assert worker.finished_ok.emitted == ["Nothing to commit."]
    assert worker.failed.emitted == []
    mock_repo.git.add.assert_not_called()


@patch("commit_push_worker.Repo")
def test_commit_push_stages_commits_and_pushes(mock_repo_cls):
    mock_repo = MagicMock()
    mock_repo.is_dirty.return_value = True
    push_info = MagicMock()
    push_info.summary = "main -> main"
    push_info.flags = 0
    push_info.ERROR = 1 << 10       # bits that won't match flags=0
    push_info.REJECTED = 1 << 11
    mock_repo.remotes.origin.push.return_value = [push_info]
    # temporarily_authed_remote uses repo.remotes["origin"] (subscript),
    # same as real GitPython's IterableList -- MagicMock needs this wired
    # explicitly since it doesn't auto-support __getitem__.
    mock_repo.remotes.__getitem__.return_value = mock_repo.remotes.origin
    mock_repo_cls.return_value = mock_repo

    worker, _ = make_commit_worker(message="Fix bug")
    worker.run()

    mock_repo.git.add.assert_called_once_with(A=True)
    mock_repo.index.commit.assert_called_once_with("Fix bug")
    mock_repo.remotes.origin.push.assert_called_once()
    assert worker.finished_ok.emitted == ["Changes committed and pushed."]
    assert worker.failed.emitted == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))