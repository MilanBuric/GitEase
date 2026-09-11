"""
CloneWorker: runs `git clone` on a background thread so the GUI never freezes,
and streams every step (and any error) back to the main window's log view.
"""

import os

from PySide6.QtCore import QThread, Signal
from git import Repo, RemoteProgress
from git.exc import GitCommandError

from git_providers import build_authed_url


class CloneProgress(RemoteProgress):
    """Forwards git's own progress lines (counting objects, receiving objects,
    resolving deltas, etc.) up to the log view in real time, and reports a
    0-100 percent value (per phase) for a visual progress bar."""

    def __init__(self, log_signal, percent_signal=None):
        super().__init__()
        self.log_signal = log_signal
        self.percent_signal = percent_signal

    def update(self, op_code, cur_count, max_count=None, message=""):
        if message:
            self.log_signal.emit(message)
        elif max_count:
            percent = (cur_count / max_count) * 100
            self.log_signal.emit(f"Progress: {percent:.0f}% ({int(cur_count)}/{int(max_count)})")
            if self.percent_signal:
                self.percent_signal.emit(int(percent))

    def line_dropped(self, line):
        # Catches raw lines git prints that don't match the structured
        # "counting/compressing/receiving" format above.
        self.log_signal.emit(line)


class CloneWorker(QThread):
    log_message = Signal(str)       # any line to append to the log
    progress_percent = Signal(int)  # 0-100, for a visual progress bar
    finished_ok = Signal(str)       # emits the local path on success
    failed = Signal(str)            # emits a human-readable error message

    def __init__(self, url, dest_path, token=None, branch=None):
        super().__init__()
        self.url = url
        self.dest_path = dest_path
        self.token = token
        self.branch = branch  # None = clone the repo's default branch

    def _authed_url(self):
        """Injects the token into an https:// URL, using the auth format the
        repo's host (GitHub/GitLab/Bitbucket/other) expects. Never touches
        ssh:// URLs, which use the user's own SSH keys instead."""
        return build_authed_url(self.url, self.token)

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
            if self.branch:
                self.log_message.emit(f"Branch: {self.branch}")

            if os.path.exists(self.dest_path) and os.listdir(self.dest_path):
                raise ValueError(
                    f"Destination folder already exists and is not empty: {self.dest_path}"
                )

            progress = CloneProgress(self.log_message, self.progress_percent)
            clone_kwargs = {"progress": progress}
            if self.branch:
                clone_kwargs["branch"] = self.branch
            repo = Repo.clone_from(self._authed_url(), self.dest_path, **clone_kwargs)

            # git clone already sets up 'origin' automatically -- this just
            # confirms it and surfaces the (token-free) remote URL in the log.
            origin_url = self._scrub(repo.remotes.origin.url)
            self.progress_percent.emit(100)
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