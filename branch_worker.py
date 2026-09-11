"""
BranchListWorker: fetches the list of branches for a remote repo URL
(via `git ls-remote --heads`) without cloning anything, so the UI can
offer a branch picker before you commit to a clone.
"""

from PySide6.QtCore import QThread, Signal
from git import Git
from git.exc import GitCommandError


class BranchListWorker(QThread):
    branches_ready = Signal(list, str)   # branch names, default branch name
    failed = Signal(str)

    def __init__(self, url, token=None):
        super().__init__()
        self.url = url
        self.token = token

    def _authed_url(self):
        if self.token and self.url.startswith("https://"):
            return self.url.replace("https://", f"https://{self.token}@", 1)
        return self.url

    def run(self):
        try:
            g = Git()
            # HEAD line tells us the default branch; refs/heads/* lines are branches.
            output = g.ls_remote("--symref", self._authed_url(), "HEAD")
            default_branch = None
            for line in output.splitlines():
                if line.startswith("ref:") and "refs/heads/" in line:
                    default_branch = line.split("refs/heads/")[1].split()[0]

            heads_output = g.ls_remote("--heads", self._authed_url())
            branches = []
            for line in heads_output.splitlines():
                if "refs/heads/" in line:
                    branches.append(line.split("refs/heads/")[1].strip())

            if not branches:
                raise ValueError("No branches found -- is the URL correct and reachable?")

            self.branches_ready.emit(branches, default_branch or branches[0])

        except GitCommandError as e:
            msg = str(e)
            if self.token:
                msg = msg.replace(self.token, "****")
            self.failed.emit(msg)
        except Exception as e:
            msg = str(e)
            if self.token:
                msg = msg.replace(self.token, "****")
            self.failed.emit(msg)