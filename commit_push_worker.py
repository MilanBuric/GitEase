"""
CommitPushWorker: stages all changes, commits with a given message, and
pushes to origin -- on a background thread, same pattern as the other
workers.
"""

import os

from PySide6.QtCore import QThread, Signal
from git import Repo, InvalidGitRepositoryError
from git.exc import GitCommandError


class CommitPushWorker(QThread):
    log_message = Signal(str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, repo_path, commit_message):
        super().__init__()
        self.repo_path = repo_path
        self.commit_message = commit_message

    def run(self):
        try:
            if not os.path.isdir(self.repo_path):
                raise ValueError(f"Folder does not exist: {self.repo_path}")
            if not self.commit_message.strip():
                raise ValueError("Commit message cannot be empty.")

            self.log_message.emit(f"Opening repo at {self.repo_path}")
            repo = Repo(self.repo_path)

            if not repo.is_dirty(untracked_files=True):
                self.log_message.emit("Nothing to commit -- working tree is already clean.")
                self.finished_ok.emit("Nothing to commit.")
                return

            self.log_message.emit("Staging all changes...")
            repo.git.add(A=True)

            self.log_message.emit(f"Committing: {self.commit_message}")
            repo.index.commit(self.commit_message)

            self.log_message.emit("Pushing to origin...")
            push_infos = repo.remotes.origin.push()
            for info in push_infos:
                summary = (info.summary or "").strip()
                if summary:
                    self.log_message.emit(f"Push result: {summary}")
                if info.flags & info.ERROR:
                    raise GitCommandError("push", 1, stderr=summary or "push failed")

            self.log_message.emit("Commit and push complete.")
            self.finished_ok.emit("Changes committed and pushed.")

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