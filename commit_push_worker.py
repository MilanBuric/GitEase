"""
CommitPushWorker: stages all changes, commits with a given message, and
pushes to origin -- on a background thread, same pattern as the other
workers.

Push uses temporarily_authed_remote so a token is only ever present in
the remote URL for the duration of the push call itself, never left
behind in .git/config.
"""

import os

from PySide6.QtCore import QThread, Signal
from git import Repo, InvalidGitRepositoryError
from git.exc import GitCommandError

from git_providers import temporarily_authed_remote


class CommitPushWorker(QThread):
    log_message = Signal(str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, repo_path, commit_message, token=None):
        super().__init__()
        self.repo_path = repo_path
        self.commit_message = commit_message
        self.token = token

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
            with temporarily_authed_remote(repo, self.token) as origin:
                push_infos = origin.push()

                for info in push_infos:
                    summary = (info.summary or "").strip()
                    if summary:
                        self.log_message.emit(f"Push result: {summary}")
                    if info.flags & info.ERROR:
                        raise GitCommandError("push", 1, stderr=summary or "push failed")
                    if info.flags & info.REJECTED:
                        raise GitCommandError("push", 1, stderr=summary or "push rejected")

            self.log_message.emit("Commit and push complete.")
            self.finished_ok.emit("Changes committed and pushed.")

        except InvalidGitRepositoryError:
            msg = f"Not a git repository: {self.repo_path}"
            self.log_message.emit(f"ERROR: {msg}")
            self.failed.emit(msg)
        except GitCommandError as e:
            msg = str(e)
            if self.token:
                msg = msg.replace(self.token, "****")
            if "non-fast-forward" in msg or "rejected" in msg.lower() or "fetch first" in msg.lower():
                msg = ("Push rejected -- the remote has commits you don't have locally "
                       "(someone else likely pushed first). Go to Pull Latest, pull the "
                       "changes into this folder, then try Commit && Push again.")
            elif "could not read Username" in msg or "terminal prompts disabled" in msg:
                msg = ("Authentication required but no valid token was provided "
                       "(or the token is wrong/expired, or lacks push access). "
                       "Check the token in Settings and try again.")
            self.log_message.emit(f"ERROR (git command failed): {msg}")
            self.failed.emit(msg)
        except Exception as e:
            msg = str(e)
            if self.token:
                msg = msg.replace(self.token, "****")
            self.log_message.emit(f"ERROR: {msg}")
            self.failed.emit(msg)