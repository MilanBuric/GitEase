"""
PullWorker: runs `git pull` on an existing local repo, on a background
thread, reporting progress and errors the same way CloneWorker does.

If a token is available for the repo's host, it's applied only for the
duration of the fetch/merge call (via temporarily_authed_remote) and
never left sitting in .git/config -- same protection CloneWorker gives
newly-cloned repos.
"""

import os

from PySide6.QtCore import QThread, Signal
from git import Repo, InvalidGitRepositoryError
from git.exc import GitCommandError

from git_providers import temporarily_authed_remote


class PullWorker(QThread):
    log_message = Signal(str)
    finished_ok = Signal(str, str)   # emits (local path, origin URL) on success
    failed = Signal(str)

    def __init__(self, repo_path, token=None):
        super().__init__()
        self.repo_path = repo_path
        self.token = token

    def run(self):
        try:
            if not os.path.isdir(self.repo_path):
                raise ValueError(f"Folder does not exist: {self.repo_path}")

            self.log_message.emit(f"Opening repo at {self.repo_path}")
            repo = Repo(self.repo_path)

            if repo.bare:
                raise ValueError("This folder is a bare repository -- nothing to pull into.")

            if repo.is_dirty(untracked_files=False):
                self.log_message.emit(
                    "Warning: you have uncommitted local changes. Pulling anyway; "
                    "git will stop and report a conflict if it can't merge cleanly."
                )

            clean_url = repo.remotes.origin.url
            with temporarily_authed_remote(repo, self.token) as origin:
                self.log_message.emit(f"Pulling from {clean_url} ...")
                pull_info = origin.pull()

            for info in pull_info:
                self.log_message.emit(f"Updated ref: {info.ref}  ({info.note or 'ok'})")

            self.log_message.emit("Pull complete -- local repo is up to date.")
            self.finished_ok.emit(self.repo_path, repo.remotes.origin.url)

        except InvalidGitRepositoryError:
            msg = f"Not a git repository: {self.repo_path}"
            self.log_message.emit(f"ERROR: {msg}")
            self.failed.emit(msg)
        except GitCommandError as e:
            msg = str(e)
            if self.token:
                msg = msg.replace(self.token, "****")
            if "CONFLICT" in msg or "conflict" in msg.lower():
                msg = ("Merge conflict -- git couldn't automatically combine your local "
                       "changes with the remote's. GitEase can't resolve conflicts for you; "
                       "open a terminal in this folder, resolve the conflicting files, then "
                       "commit. If you'd rather discard your local changes and start clean, "
                       "run 'git merge --abort' first.")
            elif "could not read Username" in msg or "terminal prompts disabled" in msg:
                msg = ("Authentication required but no valid token was provided "
                       "(or the token is wrong/expired). Add a token in Settings and try again.")
            self.log_message.emit(f"ERROR (git command failed): {msg}")
            self.failed.emit(msg)
        except Exception as e:
            msg = str(e)
            if self.token:
                msg = msg.replace(self.token, "****")
            self.log_message.emit(f"ERROR: {msg}")
            self.failed.emit(msg)