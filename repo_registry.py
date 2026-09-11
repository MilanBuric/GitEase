"""
RepoRegistry: remembers which local folders GitEase has cloned (persisted via
QSettings, so it survives restarts) -- this powers the Dashboard tab.

RepoStatusWorker: for each tracked repo, fetches origin and reports the
current branch plus how many commits it's ahead/behind that branch's
upstream, all on a background thread.
"""

import os

from PySide6.QtCore import QThread, Signal, QSettings
from git import Repo, InvalidGitRepositoryError
from git.exc import GitCommandError

SETTINGS_ORG = "GitEase"
SETTINGS_APP = "GitEase"
REGISTRY_KEY = "cloned_repo_paths"


class RepoRegistry:
    def __init__(self):
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)

    def get_paths(self):
        paths = self.settings.value(REGISTRY_KEY, [], type=list) or []
        # Silently drop entries whose folder no longer exists.
        valid = [p for p in paths if os.path.isdir(p)]
        if valid != paths:
            self.settings.setValue(REGISTRY_KEY, valid)
        return valid

    def add_path(self, path):
        paths = self.get_paths()
        if path not in paths:
            paths.append(path)
            self.settings.setValue(REGISTRY_KEY, paths)

    def remove_path(self, path):
        paths = [p for p in self.get_paths() if p != path]
        self.settings.setValue(REGISTRY_KEY, paths)


class RepoStatusWorker(QThread):
    repo_status = Signal(str, dict)   # path, {branch, ahead, behind, error}
    all_done = Signal()

    def __init__(self, paths):
        super().__init__()
        self.paths = paths

    def run(self):
        for path in self.paths:
            info = {"branch": None, "ahead": 0, "behind": 0, "error": None}
            try:
                repo = Repo(path)
                branch = repo.active_branch.name
                info["branch"] = branch

                repo.remotes.origin.fetch()

                upstream_ref = f"origin/{branch}"
                # If there's no upstream tracking branch on the remote (e.g. a
                # local-only branch), just report the branch name with no counts.
                remote_refs = [r.name for r in repo.remotes.origin.refs]
                if upstream_ref in remote_refs:
                    info["ahead"] = sum(
                        1 for _ in repo.iter_commits(f"{upstream_ref}..{branch}")
                    )
                    info["behind"] = sum(
                        1 for _ in repo.iter_commits(f"{branch}..{upstream_ref}")
                    )
                else:
                    info["error"] = "No upstream branch on origin"

            except InvalidGitRepositoryError:
                info["error"] = "Not a git repository"
            except GitCommandError as e:
                info["error"] = str(e)
            except Exception as e:
                info["error"] = str(e)

            self.repo_status.emit(path, info)

        self.all_done.emit()