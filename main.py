"""
GitEase
----------------
Clone, pull, view status across, and commit/push GitHub/GitLab/Bitbucket
repos -- no terminal needed. See README.md for the full feature list and
KNOWN_LIMITATIONS.md for what this app deliberately does NOT try to handle.
"""

import sys
import os

# Must be set before any git subprocess runs: without this, git falls back
# to an interactive terminal prompt for missing/invalid credentials, which
# has nowhere to go from a background thread in a GUI app -- it just hangs
# forever with no explanation. This makes git fail fast with a real error
# instead, which every worker below then turns into a clear message.
os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")

import platform
import subprocess
import webbrowser
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QPlainTextEdit,
    QMessageBox, QComboBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QTextEdit, QProgressBar
)
from PySide6.QtGui import QTextCursor, QFont, QIcon
from PySide6.QtCore import Qt, QSettings

from git import Repo, InvalidGitRepositoryError
from git.exc import GitCommandError

from clone_worker import CloneWorker
from pull_worker import PullWorker
from branch_worker import BranchListWorker
from repo_registry import RepoRegistry, RepoStatusWorker
from commit_push_worker import CommitPushWorker
from settings_dialog import SettingsDialog, load_all_tokens
from git_providers import detect_provider
from style import DARK_THEME

MAX_RECENT = 8


def resource_path(relative_path):
    """Resolves a bundled resource (like the icon) whether running from
    source or from a PyInstaller-built exe, where files are unpacked
    into a temp folder referenced by sys._MEIPASS."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def open_in_file_manager(path):
    """Opens a folder in the OS's file manager. Falls back to a plain
    message instead of crashing if the expected command isn't present
    (e.g. a minimal Linux install with no xdg-open) -- we can't fully
    verify this on real macOS/Linux hardware, so failing safely here
    matters more than usual."""
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(path)  # noqa: only exists on Windows, guarded above
        elif system == "Darwin":
            subprocess.run(["open", path], check=True)
        else:
            subprocess.run(["xdg-open", path], check=True)
        return True, None
    except Exception as e:
        return False, str(e)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitEase")
        self.resize(900, 800)
        self.setMinimumSize(700, 600)

        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.settings = QSettings("GitEase", "GitEase")
        self.registry = RepoRegistry()
        self.worker = None
        self.branch_worker = None
        self.status_worker = None
        self._last_cloned_path = None
        self._detected_branches = []
        self.tokens = {}       # {"GitHub": "...", "GitLab": "...", "Bitbucket": "..."}
        self._busy = False     # guards against overlapping clone/pull/push operations

        central = QWidget()
        self.setCentralWidget(central)
        outer_layout = QVBoxLayout(central)
        outer_layout.setContentsMargins(24, 20, 24, 20)
        outer_layout.setSpacing(12)

        # --- Header ---
        header_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_label = QLabel("GitEase")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title_label.setFont(title_font)
        subtitle_label = QLabel("Clone, pull, track, and push repos -- no terminal needed.")
        subtitle_label.setStyleSheet("color: #8b949e; font-weight: 400;")
        title_col.addWidget(title_label)
        title_col.addWidget(subtitle_label)
        header_row.addLayout(title_col)
        header_row.addStretch(1)

        settings_btn = QPushButton("\u2699 Settings")
        settings_btn.setMinimumHeight(34)
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.clicked.connect(self.open_settings)
        header_row.addWidget(settings_btn, alignment=Qt.AlignmentFlag.AlignTop)
        outer_layout.addLayout(header_row)
        outer_layout.addSpacing(4)

        # --- Tabs ---
        self.tabs = QTabWidget()
        outer_layout.addWidget(self.tabs)

        self.clone_tab = QWidget()
        self.pull_tab = QWidget()
        self.dashboard_tab = QWidget()
        self.commit_tab = QWidget()
        self.tabs.addTab(self.clone_tab, "Clone New")
        self.tabs.addTab(self.pull_tab, "Pull Latest")
        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.commit_tab, "Commit && Push")

        self._build_clone_tab()
        self._build_pull_tab()
        self._build_dashboard_tab()
        self._build_commit_tab()

        self.tabs.currentChanged.connect(self._on_tab_changed)

        # --- Log view (shared by all tabs) ---
        log_header_row = QHBoxLayout()
        log_label = QLabel("LOG")
        log_label.setObjectName("sectionLabel")
        log_header_row.addWidget(log_label)
        log_header_row.addStretch(1)
        clear_log_btn = QPushButton("Clear")
        clear_log_btn.setMinimumHeight(22)
        clear_log_btn.setMaximumWidth(70)
        clear_log_btn.clicked.connect(self.clear_log)
        log_header_row.addWidget(clear_log_btn)
        outer_layout.addLayout(log_header_row)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setMaximumHeight(160)
        outer_layout.addWidget(self.log_view)

        self.tokens = load_all_tokens()
        if any(self.tokens.values()):
            self.append_log("Loaded saved token(s) from the system keyring.")
        self._refresh_recent_combo()
        self._refresh_dashboard()

    # ================= Clone tab =================
    def _build_clone_tab(self):
        layout = QVBoxLayout(self.clone_tab)
        layout.setSpacing(10)
        layout.setContentsMargins(4, 12, 4, 4)

        recent_label = QLabel("RECENT REPOS")
        recent_label.setObjectName("sectionLabel")
        layout.addWidget(recent_label)
        self.recent_combo = QComboBox()
        self.recent_combo.setMinimumHeight(32)
        self.recent_combo.currentIndexChanged.connect(self._on_recent_selected)
        layout.addWidget(self.recent_combo)

        url_label = QLabel("REPO URL  (GitHub, GitLab, or Bitbucket)")
        url_label.setObjectName("sectionLabel")
        layout.addWidget(url_label)
        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://github.com/user/repo.git")
        self.url_input.setMinimumHeight(34)
        self.url_input.textChanged.connect(self._update_provider_label)
        url_row.addWidget(self.url_input)
        list_branches_btn = QPushButton("List Branches")
        list_branches_btn.setMinimumHeight(34)
        list_branches_btn.clicked.connect(self.fetch_branches)
        url_row.addWidget(list_branches_btn)
        layout.addLayout(url_row)

        self.provider_label = QLabel("")
        self.provider_label.setStyleSheet("color: #8b949e; font-weight: 400;")
        layout.addWidget(self.provider_label)

        branch_label = QLabel("BRANCH")
        branch_label.setObjectName("sectionLabel")
        layout.addWidget(branch_label)
        self.branch_combo = QComboBox()
        self.branch_combo.setMinimumHeight(32)
        self.branch_combo.addItem("(default branch)")
        layout.addWidget(self.branch_combo)

        dest_label = QLabel("DESTINATION FOLDER")
        dest_label.setObjectName("sectionLabel")
        layout.addWidget(dest_label)
        dest_layout = QHBoxLayout()
        dest_layout.setSpacing(8)
        self.dest_input = QLineEdit()
        self.dest_input.setMinimumHeight(34)
        dest_layout.addWidget(self.dest_input)
        browse_btn = QPushButton("Browse...")
        browse_btn.setMinimumHeight(34)
        browse_btn.clicked.connect(self.browse_folder)
        dest_layout.addWidget(browse_btn)
        layout.addLayout(dest_layout)

        self.clone_progress = QProgressBar()
        self.clone_progress.setRange(0, 100)
        self.clone_progress.setValue(0)
        self.clone_progress.setTextVisible(True)
        self.clone_progress.setVisible(False)
        layout.addWidget(self.clone_progress)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.clone_btn = QPushButton("Clone && Connect")
        self.clone_btn.setObjectName("primaryButton")
        self.clone_btn.setMinimumHeight(42)
        self.clone_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clone_btn.clicked.connect(self.start_clone)
        action_row.addWidget(self.clone_btn, stretch=3)

        self.cancel_clone_btn = QPushButton("Cancel")
        self.cancel_clone_btn.setMinimumHeight(42)
        self.cancel_clone_btn.setVisible(False)
        self.cancel_clone_btn.clicked.connect(self.cancel_current_operation)
        action_row.addWidget(self.cancel_clone_btn, stretch=1)

        self.open_folder_btn = QPushButton("Open in Explorer")
        self.open_folder_btn.setMinimumHeight(42)
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self.open_last_cloned_folder)
        action_row.addWidget(self.open_folder_btn, stretch=1)
        layout.addLayout(action_row)

        layout.addStretch(1)

    def _update_provider_label(self):
        url = self.url_input.text().strip()
        if not url:
            self.provider_label.setText("")
            return
        provider = detect_provider(url)
        if provider == "Unknown":
            self.provider_label.setText("")
        else:
            has_token = bool(self.tokens.get(provider))
            suffix = " (token saved)" if has_token else " (no token saved)"
            self.provider_label.setText(f"Detected: {provider}{suffix}")

    # ================= Pull tab =================
    def _build_pull_tab(self):
        layout = QVBoxLayout(self.pull_tab)
        layout.setSpacing(10)
        layout.setContentsMargins(4, 12, 4, 4)

        info_label = QLabel(
            "Point GitEase at a folder you've already cloned to fetch and merge\n"
            "the latest changes from its remote."
        )
        info_label.setStyleSheet("color: #8b949e; font-weight: 400;")
        layout.addWidget(info_label)

        repo_label = QLabel("EXISTING LOCAL REPO FOLDER")
        repo_label.setObjectName("sectionLabel")
        layout.addWidget(repo_label)
        repo_row = QHBoxLayout()
        repo_row.setSpacing(8)
        self.pull_path_input = QLineEdit()
        self.pull_path_input.setMinimumHeight(34)
        repo_row.addWidget(self.pull_path_input)
        pull_browse_btn = QPushButton("Browse...")
        pull_browse_btn.setMinimumHeight(34)
        pull_browse_btn.clicked.connect(self.browse_pull_folder)
        repo_row.addWidget(pull_browse_btn)
        layout.addLayout(repo_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.pull_btn = QPushButton("Pull Latest Changes")
        self.pull_btn.setObjectName("primaryButton")
        self.pull_btn.setMinimumHeight(42)
        self.pull_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pull_btn.clicked.connect(self.start_pull)
        action_row.addWidget(self.pull_btn, stretch=3)

        self.cancel_pull_btn = QPushButton("Cancel")
        self.cancel_pull_btn.setMinimumHeight(42)
        self.cancel_pull_btn.setVisible(False)
        self.cancel_pull_btn.clicked.connect(self.cancel_current_operation)
        action_row.addWidget(self.cancel_pull_btn, stretch=1)
        layout.addLayout(action_row)

        abort_merge_btn = QPushButton("Abort In-Progress Merge (if a pull left a conflict)")
        abort_merge_btn.setMinimumHeight(34)
        abort_merge_btn.clicked.connect(self.abort_merge)
        layout.addWidget(abort_merge_btn)

        layout.addStretch(1)

    # ================= Dashboard tab =================
    def _build_dashboard_tab(self):
        layout = QVBoxLayout(self.dashboard_tab)
        layout.setSpacing(10)
        layout.setContentsMargins(4, 12, 4, 4)

        info_label = QLabel("Every repo you've cloned or added, at a glance.")
        info_label.setStyleSheet("color: #8b949e; font-weight: 400;")
        layout.addWidget(info_label)

        self.dashboard_table = QTableWidget(0, 4)
        self.dashboard_table.setHorizontalHeaderLabels(["Repo", "Branch", "Status", "Path"])
        self.dashboard_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.dashboard_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.dashboard_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.dashboard_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.dashboard_table.verticalHeader().setVisible(False)
        self.dashboard_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.dashboard_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.dashboard_table)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        add_existing_btn = QPushButton("Add Existing Folder")
        add_existing_btn.setMinimumHeight(38)
        add_existing_btn.clicked.connect(self.add_existing_folder)
        btn_row.addWidget(add_existing_btn)

        refresh_btn = QPushButton("Refresh Status")
        refresh_btn.setMinimumHeight(38)
        refresh_btn.clicked.connect(self._refresh_dashboard)
        btn_row.addWidget(refresh_btn)

        self.pull_all_btn = QPushButton("Pull All")
        self.pull_all_btn.setObjectName("primaryButton")
        self.pull_all_btn.setMinimumHeight(38)
        self.pull_all_btn.clicked.connect(self.pull_all_repos)
        btn_row.addWidget(self.pull_all_btn)

        remove_btn = QPushButton("Remove Selected from List")
        remove_btn.setMinimumHeight(38)
        remove_btn.clicked.connect(self.remove_selected_repo)
        btn_row.addWidget(remove_btn)
        layout.addLayout(btn_row)

    # ================= Commit & Push tab =================
    def _build_commit_tab(self):
        layout = QVBoxLayout(self.commit_tab)
        layout.setSpacing(10)
        layout.setContentsMargins(4, 12, 4, 4)

        info_label = QLabel("Stages all changes, commits with your message, and pushes to origin.")
        info_label.setStyleSheet("color: #8b949e; font-weight: 400;")
        layout.addWidget(info_label)

        repo_label = QLabel("LOCAL REPO FOLDER")
        repo_label.setObjectName("sectionLabel")
        layout.addWidget(repo_label)
        repo_row = QHBoxLayout()
        repo_row.setSpacing(8)
        self.commit_path_input = QLineEdit()
        self.commit_path_input.setMinimumHeight(34)
        repo_row.addWidget(self.commit_path_input)
        commit_browse_btn = QPushButton("Browse...")
        commit_browse_btn.setMinimumHeight(34)
        commit_browse_btn.clicked.connect(self.browse_commit_folder)
        repo_row.addWidget(commit_browse_btn)
        layout.addLayout(repo_row)

        msg_label = QLabel("COMMIT MESSAGE")
        msg_label.setObjectName("sectionLabel")
        layout.addWidget(msg_label)
        self.commit_message_input = QTextEdit()
        self.commit_message_input.setPlaceholderText("Describe what changed...")
        self.commit_message_input.setMaximumHeight(90)
        layout.addWidget(self.commit_message_input)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.commit_push_btn = QPushButton("Stage All, Commit && Push")
        self.commit_push_btn.setObjectName("primaryButton")
        self.commit_push_btn.setMinimumHeight(42)
        self.commit_push_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.commit_push_btn.clicked.connect(self.start_commit_push)
        action_row.addWidget(self.commit_push_btn, stretch=3)

        self.cancel_commit_btn = QPushButton("Cancel")
        self.cancel_commit_btn.setMinimumHeight(42)
        self.cancel_commit_btn.setVisible(False)
        self.cancel_commit_btn.clicked.connect(self.cancel_current_operation)
        action_row.addWidget(self.cancel_commit_btn, stretch=1)
        layout.addLayout(action_row)

        layout.addStretch(1)

    def _on_tab_changed(self, index):
        if self.tabs.widget(index) is self.dashboard_tab:
            self._refresh_dashboard()

    # ---------------- Busy guard (prevents overlapping operations) ----------------
    def _try_start_operation(self):
        if self._busy:
            QMessageBox.warning(
                self, "Busy",
                "Another operation is already running. Wait for it to finish, or "
                "click Cancel on that tab first."
            )
            return False
        self._busy = True
        return True

    def _end_operation(self):
        self._busy = False

    def cancel_current_operation(self):
        if not self.worker or not self.worker.isRunning():
            self._end_operation()
            self._reset_action_buttons()
            return
        reply = QMessageBox.question(
            self, "Cancel operation?",
            "This forcefully stops the current git operation. It's a hard "
            "interrupt, not a graceful stop -- check the repo's state "
            "afterward (e.g. with Dashboard or Pull Latest) before assuming "
            "everything is consistent. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.worker.terminate()
        self.worker.wait(3000)
        self.append_log("Operation cancelled by user (forced stop).")
        self._end_operation()
        self._reset_action_buttons()

    def _reset_action_buttons(self):
        self.clone_btn.setEnabled(True)
        self.clone_btn.setText("Clone && Connect")
        self.clone_progress.setVisible(False)
        self.cancel_clone_btn.setVisible(False)

        self.pull_btn.setEnabled(True)
        self.pull_btn.setText("Pull Latest Changes")
        self.cancel_pull_btn.setVisible(False)

        self.commit_push_btn.setEnabled(True)
        self.commit_push_btn.setText("Stage All, Commit && Push")
        self.cancel_commit_btn.setVisible(False)

    # ---------------- Settings / token handling ----------------
    def open_settings(self):
        dialog = SettingsDialog(self.tokens, self)
        dialog.tokens_changed.connect(self._on_tokens_changed)
        dialog.exec()

    def _on_tokens_changed(self, tokens):
        self.tokens = tokens
        self.append_log("Token(s) updated.")
        self._update_provider_label()

    def _token_for_url(self, url):
        provider = detect_provider(url)
        return self.tokens.get(provider) or None

    def _token_for_local_repo(self, path):
        """Reads a local repo's origin URL (fast, no network) to figure out
        which saved token applies to it, for pull/push/status operations."""
        try:
            repo = Repo(path)
            provider = detect_provider(repo.remotes.origin.url)
            return self.tokens.get(provider) or None
        except Exception:
            return None

    # ---------------- Branch listing ----------------
    def fetch_branches(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Missing URL", "Enter a repository URL first.")
            return
        self.append_log(f"Looking up branches for {url} ...")
        self.branch_worker = BranchListWorker(url, self._token_for_url(url))
        self.branch_worker.branches_ready.connect(self._on_branches_ready)
        self.branch_worker.failed.connect(self._on_branches_failed)
        self.branch_worker.start()

    def _on_branches_ready(self, branches, default_branch):
        self._detected_branches = branches
        self.branch_combo.clear()
        self.branch_combo.addItem(f"(default: {default_branch})")
        self.branch_combo.addItems(sorted(branches))
        self.append_log(f"Found {len(branches)} branch(es). Default: {default_branch}")

    def _on_branches_failed(self, msg):
        self.append_log(f"Could not list branches: {msg}")
        QMessageBox.warning(self, "Branch lookup failed", msg)

    # ---------------- Recent repos ----------------
    def _get_recent_urls(self):
        return self.settings.value("recent_urls", [], type=list) or []

    def _add_recent_url(self, url):
        recent = self._get_recent_urls()
        recent = [u for u in recent if u != url]
        recent.insert(0, url)
        recent = recent[:MAX_RECENT]
        self.settings.setValue("recent_urls", recent)
        self._refresh_recent_combo()

    def _refresh_recent_combo(self):
        self.recent_combo.blockSignals(True)
        self.recent_combo.clear()
        recent = self._get_recent_urls()
        if recent:
            self.recent_combo.addItem("-- Select a recent repo --")
            self.recent_combo.addItems(recent)
        else:
            self.recent_combo.addItem("(no recent repos yet)")
        self.recent_combo.blockSignals(False)

    def _on_recent_selected(self, index):
        if index <= 0:
            return
        url = self.recent_combo.currentText()
        self.url_input.setText(url)

    # ---------------- Folder picking ----------------
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose parent folder")
        if not folder:
            return
        url = self.url_input.text().strip()
        repo_name = self._repo_name_from_url(url) if url else ""
        full_path = os.path.join(folder, repo_name) if repo_name else folder
        self.dest_input.setText(full_path)

    def browse_pull_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose an existing repo folder")
        if folder:
            self.pull_path_input.setText(folder)

    def browse_commit_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose a repo folder")
        if folder:
            self.commit_path_input.setText(folder)

    @staticmethod
    def _repo_name_from_url(url):
        name = url.rstrip("/").split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]
        return name

    def open_last_cloned_folder(self):
        if self._last_cloned_path and os.path.isdir(self._last_cloned_path):
            ok, err = open_in_file_manager(self._last_cloned_path)
            if not ok:
                QMessageBox.warning(
                    self, "Couldn't open folder",
                    f"GitEase couldn't open a file manager for this folder:\n{err}\n\n"
                    f"You can navigate there manually:\n{self._last_cloned_path}"
                )
        else:
            QMessageBox.warning(self, "No folder", "No successfully cloned folder to open yet.")

    # ---------------- Logging ----------------
    def append_log(self, text):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{timestamp}] {text}")
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)

    def clear_log(self):
        self.log_view.clear()

    # ---------------- Clone flow ----------------
    def start_clone(self):
        if not self._try_start_operation():
            return

        url = self.url_input.text().strip()
        dest = self.dest_input.text().strip()

        branch = None
        if self.branch_combo.currentIndex() > 0:
            branch = self.branch_combo.currentText()

        if not url:
            self._end_operation()
            QMessageBox.warning(self, "Missing URL", "Please enter a repository URL.")
            return
        if not dest:
            self._end_operation()
            QMessageBox.warning(self, "Missing destination", "Please choose a destination folder.")
            return

        self.clone_btn.setEnabled(False)
        self.clone_btn.setText("Cloning...")
        self.cancel_clone_btn.setVisible(True)
        self.clone_progress.setValue(0)
        self.clone_progress.setVisible(True)
        self.append_log("=" * 60)
        self.append_log(f"Clone requested: {url} -> {dest}")

        self.worker = CloneWorker(url, dest, self._token_for_url(url), branch)
        self.worker.log_message.connect(self.append_log)
        self.worker.progress_percent.connect(self.clone_progress.setValue)
        self.worker.finished_ok.connect(lambda path: self.on_clone_success(path, url))
        self.worker.failed.connect(self.on_clone_failed)
        self.worker.start()

    def on_clone_success(self, path, url):
        self._end_operation()
        self._reset_action_buttons()
        self._last_cloned_path = path
        self.open_folder_btn.setEnabled(True)
        self._add_recent_url(url)
        self.registry.add_path(path)
        self._refresh_dashboard()
        QMessageBox.information(self, "Success", f"Repository cloned and connected at:\n{path}")

    def on_clone_failed(self, error_msg):
        self._end_operation()
        self._reset_action_buttons()
        QMessageBox.critical(
            self, "Clone failed",
            f"Something went wrong:\n\n{error_msg}\n\nScroll the log above for full details."
        )

    # ---------------- Pull flow ----------------
    def start_pull(self):
        if not self._try_start_operation():
            return

        path = self.pull_path_input.text().strip()
        if not path:
            self._end_operation()
            QMessageBox.warning(self, "Missing folder", "Please choose an existing repo folder.")
            return

        self.pull_btn.setEnabled(False)
        self.pull_btn.setText("Pulling...")
        self.cancel_pull_btn.setVisible(True)
        self.append_log("=" * 60)
        self.append_log(f"Pull requested for: {path}")

        self.worker = PullWorker(path, self._token_for_local_repo(path))
        self.worker.log_message.connect(self.append_log)
        self.worker.finished_ok.connect(self.on_pull_success)
        self.worker.failed.connect(self.on_pull_failed)
        self.worker.start()

    def on_pull_success(self, path, origin_url):
        self._end_operation()
        self._reset_action_buttons()
        self.registry.add_path(path)
        if origin_url:
            self._add_recent_url(origin_url)
        QMessageBox.information(self, "Up to date", f"Pulled the latest changes into:\n{path}")

    def on_pull_failed(self, error_msg):
        self._end_operation()
        self._reset_action_buttons()
        QMessageBox.critical(
            self, "Pull failed",
            f"Something went wrong:\n\n{error_msg}\n\nScroll the log above for full details."
        )

    def abort_merge(self):
        path = self.pull_path_input.text().strip()
        if not path:
            QMessageBox.warning(self, "Missing folder", "Choose the repo folder first.")
            return
        reply = QMessageBox.question(
            self, "Abort merge?",
            "This discards the in-progress merge and any partially-resolved "
            "changes from it. Your commits from before the pull are safe. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            repo = Repo(path)
            repo.git.merge("--abort")
            self.append_log(f"Merge aborted for {path}.")
            QMessageBox.information(self, "Merge aborted", "The in-progress merge was aborted.")
        except InvalidGitRepositoryError:
            QMessageBox.warning(self, "Not a repo", "That folder isn't a git repository.")
        except GitCommandError as e:
            QMessageBox.warning(
                self, "Nothing to abort",
                f"Git couldn't abort a merge here -- there may not be one in progress:\n\n{e}"
            )

    # ---------------- Dashboard ----------------
    def _refresh_dashboard(self):
        paths = self.registry.get_paths()
        self.dashboard_table.setRowCount(len(paths))
        for row, path in enumerate(paths):
            name_item = QTableWidgetItem(os.path.basename(path.rstrip("\\/")))
            branch_item = QTableWidgetItem("checking...")
            status_item = QTableWidgetItem("")
            path_item = QTableWidgetItem(path)
            self.dashboard_table.setItem(row, 0, name_item)
            self.dashboard_table.setItem(row, 1, branch_item)
            self.dashboard_table.setItem(row, 2, status_item)
            self.dashboard_table.setItem(row, 3, path_item)

        if not paths:
            return

        self.append_log(f"Checking status for {len(paths)} repo(s)...")
        self.status_worker = RepoStatusWorker(paths, self.tokens)
        self.status_worker.repo_status.connect(self._on_repo_status)
        self.status_worker.all_done.connect(lambda: self.append_log("Dashboard status check complete."))
        self.status_worker.start()

    def _find_row_for_path(self, path):
        for row in range(self.dashboard_table.rowCount()):
            item = self.dashboard_table.item(row, 3)
            if item and item.text() == path:
                return row
        return -1

    def _on_repo_status(self, path, info):
        row = self._find_row_for_path(path)
        if row < 0:
            return
        branch = info.get("branch") or "?"
        self.dashboard_table.setItem(row, 1, QTableWidgetItem(branch))

        if info.get("error"):
            status_text = info["error"]
        else:
            ahead, behind = info.get("ahead", 0), info.get("behind", 0)
            if ahead == 0 and behind == 0:
                status_text = "Up to date"
            else:
                parts = []
                if ahead:
                    parts.append(f"{ahead} ahead")
                if behind:
                    parts.append(f"{behind} behind")
                status_text = ", ".join(parts)
        self.dashboard_table.setItem(row, 2, QTableWidgetItem(status_text))

    def pull_all_repos(self):
        if not self._try_start_operation():
            return
        paths = self.registry.get_paths()
        if not paths:
            self._end_operation()
            QMessageBox.information(self, "Nothing to pull", "No repos tracked yet.")
            return
        self.append_log("=" * 60)
        self.append_log(f"Pulling {len(paths)} repo(s)...")
        self._pull_all_queue = list(paths)
        self._pull_next_in_queue()

    def _pull_next_in_queue(self):
        if not self._pull_all_queue:
            self.append_log("Pull All complete.")
            self._end_operation()
            self._refresh_dashboard()
            return
        path = self._pull_all_queue.pop(0)
        self.append_log(f"Pulling: {path}")
        worker = PullWorker(path, self._token_for_local_repo(path))
        worker.log_message.connect(self.append_log)
        worker.finished_ok.connect(lambda _p, _u: self._pull_next_in_queue())
        worker.failed.connect(lambda _msg: self._pull_next_in_queue())
        self.worker = worker  # keep a reference so it isn't garbage-collected mid-run
        worker.start()

    def add_existing_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose an existing local repo folder")
        if not folder:
            return
        if not os.path.isdir(os.path.join(folder, ".git")):
            QMessageBox.warning(
                self, "Not a git repository",
                f"This folder doesn't look like a git repository (no .git folder found):\n{folder}"
            )
            return
        self.registry.add_path(folder)
        self.append_log(f"Added existing repo to Dashboard: {folder}")
        self._refresh_dashboard()

    def remove_selected_repo(self):
        selected = self.dashboard_table.selectedItems()
        if not selected:
            QMessageBox.information(self, "Nothing selected", "Select a row first.")
            return
        row = selected[0].row()
        path_item = self.dashboard_table.item(row, 3)
        if path_item:
            self.registry.remove_path(path_item.text())
            self._refresh_dashboard()

    # ---------------- Commit & push flow ----------------
    def start_commit_push(self):
        if not self._try_start_operation():
            return

        path = self.commit_path_input.text().strip()
        message = self.commit_message_input.toPlainText().strip()

        if not path:
            self._end_operation()
            QMessageBox.warning(self, "Missing folder", "Please choose a repo folder.")
            return
        if not message:
            self._end_operation()
            QMessageBox.warning(self, "Missing message", "Please enter a commit message.")
            return

        self.commit_push_btn.setEnabled(False)
        self.commit_push_btn.setText("Working...")
        self.cancel_commit_btn.setVisible(True)
        self.append_log("=" * 60)
        self.append_log(f"Commit && push requested for: {path}")

        self.worker = CommitPushWorker(path, message, self._token_for_local_repo(path))
        self.worker.log_message.connect(self.append_log)
        self.worker.finished_ok.connect(self.on_commit_push_success)
        self.worker.failed.connect(self.on_commit_push_failed)
        self.worker.start()

    def on_commit_push_success(self, summary):
        self._end_operation()
        self._reset_action_buttons()
        self.commit_message_input.clear()
        QMessageBox.information(self, "Done", summary)

    def on_commit_push_failed(self, error_msg):
        self._end_operation()
        self._reset_action_buttons()
        QMessageBox.critical(
            self, "Commit/push failed",
            f"Something went wrong:\n\n{error_msg}\n\nScroll the log above for full details."
        )


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_THEME)
    icon_path = resource_path("icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()