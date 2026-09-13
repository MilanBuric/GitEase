"""
Recovery from a forcefully-cancelled git operation.

QThread.terminate() (used by GitEase's Cancel button) is a hard kill --
it can interrupt git mid-write. When that happens, git can leave a
*.lock marker file behind (most commonly .git/index.lock, but also
HEAD.lock, config.lock, or a lock under refs/) that silently blocks
every future git operation on that repo with a confusing "Another git
process seems to be running" error, until the lock file is removed.

Since a cancel means GitEase itself just killed the only process that
could plausibly still be using that lock, it's safe for GitEase to
detect and offer to remove it immediately afterward, rather than
leaving the user to puzzle out a cryptic git error and go delete a
file by hand.
"""

import os


def find_stale_lock_files(repo_path):
    """Scans a repo's .git directory for leftover *.lock files. Returns
    an empty list if the path isn't a git repo at all (e.g. a clone that
    was cancelled before .git even existed)."""
    git_dir = os.path.join(repo_path, ".git")
    if not os.path.isdir(git_dir):
        return []

    locks = []
    for root, _dirs, files in os.walk(git_dir):
        for name in files:
            if name.endswith(".lock"):
                locks.append(os.path.join(root, name))
    return locks


def remove_lock_files(lock_paths):
    """Attempts to delete each given lock file. Returns (removed, failed)
    -- failed is a list of (path, error_message) for anything that
    couldn't be deleted (e.g. a permissions issue), so the caller can
    tell the user exactly what still needs manual attention."""
    removed = []
    failed = []
    for path in lock_paths:
        try:
            os.remove(path)
            removed.append(path)
        except Exception as e:
            failed.append((path, str(e)))
    return removed, failed