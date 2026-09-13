"""
Tests for repo_safety.py -- the stale-lock-file detection and cleanup
added after a real, confirmed failure mode: cancelling an operation
(QThread.terminate(), a hard kill) can interrupt git mid-write and
leave a *.lock marker file behind, which then silently blocks every
future git operation on that repo until removed.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from repo_safety import find_stale_lock_files, remove_lock_files


def test_find_stale_lock_files_finds_top_level_and_nested_locks():
    repo_dir = tempfile.mkdtemp()
    git_dir = os.path.join(repo_dir, ".git")
    os.makedirs(os.path.join(git_dir, "refs", "heads"))

    index_lock = os.path.join(git_dir, "index.lock")
    open(index_lock, "w").close()
    nested_lock = os.path.join(git_dir, "refs", "heads", "main.lock")
    open(nested_lock, "w").close()
    # A non-.lock file should never be picked up.
    open(os.path.join(git_dir, "HEAD"), "w").close()

    found = find_stale_lock_files(repo_dir)
    assert set(found) == {index_lock, nested_lock}


def test_find_stale_lock_files_returns_empty_for_non_repo():
    not_a_repo = tempfile.mkdtemp()
    assert find_stale_lock_files(not_a_repo) == []


def test_find_stale_lock_files_returns_empty_when_clean():
    repo_dir = tempfile.mkdtemp()
    os.makedirs(os.path.join(repo_dir, ".git"))
    assert find_stale_lock_files(repo_dir) == []


def test_remove_lock_files_deletes_and_reports_success():
    repo_dir = tempfile.mkdtemp()
    lock_path = os.path.join(repo_dir, "index.lock")
    open(lock_path, "w").close()

    removed, failed = remove_lock_files([lock_path])

    assert removed == [lock_path]
    assert failed == []
    assert not os.path.exists(lock_path)


def test_remove_lock_files_reports_failure_without_crashing():
    # A path that doesn't exist can't be removed -- must be reported as a
    # failure, not raise an unhandled exception.
    fake_path = "/no/such/path/index.lock"
    removed, failed = remove_lock_files([fake_path])

    assert removed == []
    assert len(failed) == 1
    assert failed[0][0] == fake_path