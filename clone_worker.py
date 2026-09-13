"""
CloneWorker: runs `git clone` on a background thread so the GUI never freezes,
and streams every step (and any error) back to the main window's log view.

Two things worth knowing about how this behaves:

1. The token is only ever embedded in the URL for the duration of the
   `git clone` network call itself. The moment cloning succeeds, the
   locally-stored 'origin' remote is rewritten back to the clean,
   token-free URL -- so nothing sensitive is left sitting in
   .git/config afterward.
2. Progress is weighted across git's real phases (counting, compressing,
   receiving, resolving deltas, checking out) so the bar climbs
   monotonically instead of resetting to 0 every time git moves to a
   new phase.
"""

import os

from PySide6.QtCore import QThread, Signal
from git import Repo, RemoteProgress
from git.exc import GitCommandError

from git_providers import build_authed_url

# Rough weight of each clone phase, summing to 100. Receiving objects is
# usually the slowest (network-bound) phase, so it gets the most room.
# All seven of GitPython's known op-codes are covered on purpose: leaving
# any out meant an unweighted phase fell back to a 0-100 range of its own,
# which could make the bar visibly jump backward mid-clone -- exactly the
# "resetting" problem this weighting exists to prevent.
_STAGE_WEIGHTS = {
    RemoteProgress.COUNTING: (0, 5),
    RemoteProgress.COMPRESSING: (5, 10),
    RemoteProgress.WRITING: (15, 10),
    RemoteProgress.RECEIVING: (25, 45),
    RemoteProgress.FINDING_SOURCES: (70, 5),
    RemoteProgress.RESOLVING: (75, 20),
    RemoteProgress.CHECKING_OUT: (95, 5),
}


class CloneProgress(RemoteProgress):
    """Forwards git's own progress lines up to the log view in real time,
    and reports a monotonic 0-100 percent value for a visual progress bar."""

    def __init__(self, log_signal, percent_signal=None):
        super().__init__()
        self.log_signal = log_signal
        self.percent_signal = percent_signal
        self._max_percent_seen = 0  # belt-and-suspenders: never let the bar go backward,
                                     # even for a stage this table somehow doesn't cover

    def update(self, op_code, cur_count, max_count=None, message=""):
        if message:
            self.log_signal.emit(message)
        elif max_count:
            percent = (cur_count / max_count) * 100
            self.log_signal.emit(f"Progress: {percent:.0f}% ({int(cur_count)}/{int(max_count)})")

        if self.percent_signal and max_count:
            stage = op_code & self.OP_MASK
            start, weight = _STAGE_WEIGHTS.get(stage, (0, 100))
            stage_fraction = min(cur_count / max_count, 1.0) if max_count else 0
            overall = int(min(start + stage_fraction * weight, 99))  # 100 is reserved for true completion
            # Never let the bar visibly move backward, even if a stage this
            # table doesn't recognize computes a lower value than we've
            # already shown -- climbing steadily is the whole point.
            self._max_percent_seen = max(self._max_percent_seen, overall)
            self.percent_signal.emit(self._max_percent_seen)

    def line_dropped(self, line):
        self.log_signal.emit(line)


class CloneWorker(QThread):
    log_message = Signal(str)       # any line to append to the log
    progress_percent = Signal(int)  # 0-100, monotonic, for a visual progress bar
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

            # Strip the token out of the stored remote immediately -- git
            # would otherwise keep it in plaintext in .git/config forever.
            if self.token:
                repo.remotes.origin.set_url(self.url)

            origin_url = repo.remotes.origin.url
            self.progress_percent.emit(100)
            self.log_message.emit("Clone finished.")
            self.log_message.emit(f"Local repo is connected to remote 'origin' -> {origin_url}")
            self.finished_ok.emit(self.dest_path)

        except GitCommandError as e:
            msg = self._scrub(str(e))
            if "could not read Username" in msg or "terminal prompts disabled" in msg:
                msg = ("Authentication required but no valid token was provided "
                       "(or the token is wrong/expired). Add a token in Settings and try again.")
            self.log_message.emit(f"ERROR (git command failed): {msg}")
            self.failed.emit(msg)
        except Exception as e:
            msg = self._scrub(str(e))
            self.log_message.emit(f"ERROR: {msg}")
            self.failed.emit(msg)