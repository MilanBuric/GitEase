"""
PullWorker: runs `git pull` on an existing local repo, on a background thread,
reporting progress and errors the same way CloneWorker does.
"""

import os

from PySide6.QtCore import QThread, Signal
from git import Repo, InvalidGitRepositoryError
from git.exc import GitCommandError


class PullWorker(QThread):
    log_message = Signal(str)
    finished_ok = Signal(str, str)   # emits (local path, origin URL) on success
    failed = Signal(str)

    def __init__(self, repo_path):
        super().__init__()
        self.repo_path = repo_path

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

            origin = repo.remotes.origin
            self.log_message.emit(f"Pulling from {origin.url} ...")
            pull_info = origin.pull()

            for info in pull_info:
                self.log_message.emit(f"Updated ref: {info.ref}  ({info.note or 'ok'})")

            self.log_message.emit("Pull complete -- local repo is up to date.")
            self.finished_ok.emit(self.repo_path, origin.url)

        except InvalidGitRepositoryError:
            msg = f"Not a git repository: {self.repo_path}"
            self.log_message.emit(f"ERROR: {msg}")
            self.failed.emit(msg)
        except GitCommandError as e:
            msg = str(e)
            self.log_message.emit(f"ERROR (git command failed): {msg}")
            self.failed.emit(msg)
        except Exception as e:
            self.log_message.emit(f"ERROR: {e}")
            self.failed.emit(str(e))