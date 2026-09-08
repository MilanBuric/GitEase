"""
CloneWorker: runs `git clone` on a background thread so the GUI never freezes,
and streams every step (and any error) back to the main window's log view.
"""

import os

from PySide6.QtCore import QThread, Signal
from git import Repo, RemoteProgress
from git.exc import GitCommandError


class CloneProgress(RemoteProgress):
    """Forwards git's own progress lines (counting objects, receiving objects,
    resolving deltas, etc.) up to the log view in real time."""

    def __init__(self, log_signal):
        super().__init__()
        self.log_signal = log_signal

    def update(self, op_code, cur_count, max_count=None, message=""):
        if message:
            self.log_signal.emit(message)
        elif max_count:
            percent = (cur_count / max_count) * 100
            self.log_signal.emit(f"Progress: {percent:.0f}% ({int(cur_count)}/{int(max_count)})")

    def line_dropped(self, line):
        # Catches raw lines git prints that don't match the structured
        # "counting/compressing/receiving" format above.
        self.log_signal.emit(line)


class CloneWorker(QThread):
    log_message = Signal(str)   # any line to append to the log
    finished_ok = Signal(str)   # emits the local path on success
    failed = Signal(str)        # emits a human-readable error message

    def __init__(self, url, dest_path, token=None):
        super().__init__()
        self.url = url
        self.dest_path = dest_path
        self.token = token

    def _authed_url(self):
        """Injects the PAT into an https:// URL so private repos can be cloned.
        Never touches ssh:// URLs, which use the user's own SSH keys instead."""
        if self.token and self.url.startswith("https://"):
            return self.url.replace("https://", f"https://{self.token}@", 1)
        return self.url

    def _scrub(self, text):
        """Strips the token out of any message before it reaches the log,
        so it never gets printed or accidentally shared."""
        if self.token:
            return text.replace(self.token, "****")
        return text

    def run(self):
        try:
            self.log_message.emit(f"Target URL: {self.url}")
            self.log_message.emit(f"Destination: {self.dest_path}")

            if os.path.exists(self.dest_path) and os.listdir(self.dest_path):
                raise ValueError(
                    f"Destination folder already exists and is not empty: {self.dest_path}"
                )

            progress = CloneProgress(self.log_message)
            repo = Repo.clone_from(self._authed_url(), self.dest_path, progress=progress)

            # git clone already sets up 'origin' automatically -- this just
            # confirms it and surfaces the (token-free) remote URL in the log.
            origin_url = self._scrub(repo.remotes.origin.url)
            self.log_message.emit("Clone finished.")
            self.log_message.emit(f"Local repo is connected to remote 'origin' -> {origin_url}")
            self.finished_ok.emit(self.dest_path)

        except GitCommandError as e:
            msg = self._scrub(str(e))
            self.log_message.emit(f"ERROR (git command failed): {msg}")
            self.failed.emit(msg)
        except Exception as e:
            msg = self._scrub(str(e))
            self.log_message.emit(f"ERROR: {msg}")
            self.failed.emit(msg)
