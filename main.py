"""
GitEase
----------------
Clone, pull, view status across, and commit/push GitHub repos -- no
terminal needed. See README.md for the full feature list.
"""

import sys
import os
import webbrowser
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QPlainTextEdit,
    QMessageBox, QGroupBox, QComboBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QTextEdit, QInputDialog
)
from PySide6.QtGui import QTextCursor, QFont, QIcon
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import QLineEdit as _QLE  # for EchoMode enum access

import keyring

from clone_worker import CloneWorker
from pull_worker import PullWorker
from branch_worker import BranchListWorker
from repo_registry import RepoRegistry, RepoStatusWorker
from commit_push_worker import CommitPushWorker
from github_oauth import DeviceFlowLogin
from style import DARK_THEME

KEYRING_SERVICE = "repo-clone-tool"
KEYRING_USERNAME = "github-pat"
MAX_RECENT = 8


def resource_path(relative_path):
    """Resolves a bundled resource (like the icon) whether running from
    source or from a PyInstaller-built exe, where files are unpacked
    into a temp folder referenced by sys._MEIPASS."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitEase")
        self.resize(880, 760)
        self.setMinimumSize(680, 560)

        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.settings = QSettings("GitEase", "GitEase")
        self.registry = RepoRegistry()
        self.worker = None
        self.branch_worker = None
        self.status_worker = None
        self.login_worker = None
        self._last_cloned_path = None
        self._detected_branches = []

        central = QWidget()
        self.setCentralWidget(central)
        outer_layout = QVBoxLayout(central)
        outer_layout.setContentsMargins(24, 20, 24, 20)
        outer_layout.setSpacing(12)

        # --- Header ---
        title_label = QLabel("GitEase")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title_label.setFont(title_font)
        subtitle_label = QLabel("Clone, pull, track, and push GitHub repos -- no terminal needed.")
        subtitle_label.setStyleSheet("color: #8b949e; font-weight: 400;")
        outer_layout.addWidget(title_label)
        outer_layout.addWidget(subtitle_label)
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
        log_label = QLabel("LOG")
        log_label.setObjectName("sectionLabel")
        outer_layout.addWidget(log_label)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setMaximumHeight(160)
        outer_layout.addWidget(self.log_view)

        self.load_saved_token()
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

        url_label = QLabel("GITHUB REPO URL")
        url_label.setObjectName("sectionLabel")
        layout.addWidget(url_label)
        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://github.com/user/repo.git")
        self.url_input.setMinimumHeight(34)
        url_row.addWidget(self.url_input)
        list_branches_btn = QPushButton("List Branches")
        list_branches_btn.setMinimumHeight(34)
        list_branches_btn.clicked.connect(self.fetch_branches)
        url_row.addWidget(list_branches_btn)
        layout.addLayout(url_row)

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

        token_group = QGroupBox("GitHub Authentication  ·  optional, only needed for private repos")
        token_layout = QVBoxLayout()
        token_layout.setSpacing(8)
        token_row = QHBoxLayout()
        token_row.setSpacing(8)
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(_QLE.Password)
        self.token_input.setPlaceholderText("Personal Access Token")
        self.token_input.setMinimumHeight(32)
        token_row.addWidget(self.token_input)
        save_token_btn = QPushButton("Save")
        save_token_btn.setMinimumHeight(32)
        save_token_btn.clicked.connect(self.save_token)
        token_row.addWidget(save_token_btn)
        token_layout.addLayout(token_row)

        signin_btn = QPushButton("Sign in with GitHub instead")
        signin_btn.setMinimumHeight(32)
        signin_btn.clicked.connect(self.start_github_signin)
        token_layout.addWidget(signin_btn)
        token_group.setLayout(token_layout)
        layout.addWidget(token_group)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.clone_btn = QPushButton("Clone && Connect")
        self.clone_btn.setObjectName("primaryButton")
        self.clone_btn.setMinimumHeight(42)
        self.clone_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clone_btn.clicked.connect(self.start_clone)
        action_row.addWidget(self.clone_btn, stretch=3)

        self.open_folder_btn = QPushButton("Open in Explorer")
        self.open_folder_btn.setMinimumHeight(42)
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self.open_last_cloned_folder)
        action_row.addWidget(self.open_folder_btn, stretch=1)
        layout.addLayout(action_row)

        layout.addStretch(1)

    # ================= Pull tab =================
    def _build_pull_tab(self):
        layout = QVBoxLayout(self.pull_tab)
        layout.setSpacing(10)
        layout.setContentsMargins(4, 12, 4, 4)

        info_label = QLabel(
            "Point GitEase at a folder you've already cloned to fetch and merge\n"
            "the latest changes from its GitHub remote."
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

        self.pull_btn = QPushButton("Pull Latest Changes")
        self.pull_btn.setObjectName("primaryButton")
        self.pull_btn.setMinimumHeight(42)
        self.pull_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pull_btn.clicked.connect(self.start_pull)
        layout.addWidget(self.pull_btn)

        layout.addStretch(1)

    # ================= Dashboard tab =================
    def _build_dashboard_tab(self):
        layout = QVBoxLayout(self.dashboard_tab)
        layout.setSpacing(10)
        layout.setContentsMargins(4, 12, 4, 4)

        info_label = QLabel("Every repo you've cloned with GitEase, at a glance.")
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

        pull_all_btn = QPushButton("Pull All")
        pull_all_btn.setObjectName("primaryButton")
        pull_all_btn.setMinimumHeight(38)
        pull_all_btn.clicked.connect(self.pull_all_repos)
        btn_row.addWidget(pull_all_btn)

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

        self.commit_push_btn = QPushButton("Stage All, Commit && Push")
        self.commit_push_btn.setObjectName("primaryButton")
        self.commit_push_btn.setMinimumHeight(42)
        self.commit_push_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.commit_push_btn.clicked.connect(self.start_commit_push)
        layout.addWidget(self.commit_push_btn)

        layout.addStretch(1)

    def _on_tab_changed(self, index):
        if self.tabs.widget(index) is self.dashboard_tab:
            self._refresh_dashboard()

    # ---------------- Token handling ----------------
    def load_saved_token(self):
        try:
            token = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
            if token:
                self.token_input.setText(token)
                self.append_log("Loaded saved GitHub token from the system keyring.")
        except Exception as e:
            self.append_log(f"Could not load saved token: {e}")

    def save_token(self):
        token = self.token_input.text().strip()
        if not token:
            QMessageBox.warning(self, "No token", "Enter a token before saving.")
            return
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
            self.append_log("Token saved to the system keyring.")
        except Exception as e:
            self.append_log(f"ERROR saving token: {e}")

    def start_github_signin(self):
        self.login_worker = DeviceFlowLogin()
        self.login_worker.code_ready.connect(self._on_login_code_ready)
        self.login_worker.success.connect(self._on_login_success)
        self.login_worker.failed.connect(self._on_login_failed)
        self.append_log("Starting GitHub sign-in...")
        self.login_worker.start()

    def _on_login_code_ready(self, user_code, verification_uri):
        self.append_log(f"Go to {verification_uri} and enter code: {user_code}")
        webbrowser.open(verification_uri)
        QMessageBox.information(
            self, "Sign in with GitHub",
            f"Your browser should have opened {verification_uri}.\n\n"
            f"Enter this code there:\n\n{user_code}\n\n"
            "This window will update automatically once you approve access."
        )

    def _on_login_success(self, token):
        self.token_input.setText(token)
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
            self.append_log("Signed in with GitHub -- token saved to the system keyring.")
        except Exception as e:
            self.append_log(f"Signed in, but could not save token: {e}")

    def _on_login_failed(self, msg):
        self.append_log(f"GitHub sign-in failed: {msg}")
        QMessageBox.warning(self, "Sign-in unavailable", msg)

    # ---------------- Branch listing ----------------
    def fetch_branches(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Missing URL", "Enter a GitHub repository URL first.")
            return
        token = self.token_input.text().strip() or None
        self.append_log(f"Looking up branches for {url} ...")
        self.branch_worker = BranchListWorker(url, token)
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
            os.startfile(self._last_cloned_path)  # Windows-only, matches target platform
        else:
            QMessageBox.warning(self, "No folder", "No successfully cloned folder to open yet.")

    # ---------------- Logging ----------------
    def append_log(self, text):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{timestamp}] {text}")
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)

    # ---------------- Clone flow ----------------
    def start_clone(self):
        url = self.url_input.text().strip()
        dest = self.dest_input.text().strip()
        token = self.token_input.text().strip() or None

        branch = None
        if self.branch_combo.currentIndex() > 0:
            branch = self.branch_combo.currentText()

        if not url:
            QMessageBox.warning(self, "Missing URL", "Please enter a GitHub repository URL.")
            return
        if not dest:
            QMessageBox.warning(self, "Missing destination", "Please choose a destination folder.")
            return

        self.clone_btn.setEnabled(False)
        self.clone_btn.setText("Cloning...")
        self.append_log("=" * 60)
        self.append_log(f"Clone requested: {url} -> {dest}")

        self.worker = CloneWorker(url, dest, token, branch)
        self.worker.log_message.connect(self.append_log)
        self.worker.finished_ok.connect(lambda path: self.on_clone_success(path, url))
        self.worker.failed.connect(self.on_clone_failed)
        self.worker.start()

    def on_clone_success(self, path, url):
        self.clone_btn.setEnabled(True)
        self.clone_btn.setText("Clone && Connect")
        self._last_cloned_path = path
        self.open_folder_btn.setEnabled(True)
        self._add_recent_url(url)
        self.registry.add_path(path)
        self._refresh_dashboard()
        QMessageBox.information(self, "Success", f"Repository cloned and connected at:\n{path}")

    def on_clone_failed(self, error_msg):
        self.clone_btn.setEnabled(True)
        self.clone_btn.setText("Clone && Connect")
        QMessageBox.critical(
            self, "Clone failed",
            f"Something went wrong:\n\n{error_msg}\n\nScroll the log above for full details."
        )

    # ---------------- Pull flow ----------------
    def start_pull(self):
        path = self.pull_path_input.text().strip()
        if not path:
            QMessageBox.warning(self, "Missing folder", "Please choose an existing repo folder.")
            return

        self.pull_btn.setEnabled(False)
        self.pull_btn.setText("Pulling...")
        self.append_log("=" * 60)
        self.append_log(f"Pull requested for: {path}")

        self.worker = PullWorker(path)
        self.worker.log_message.connect(self.append_log)
        self.worker.finished_ok.connect(self.on_pull_success)
        self.worker.failed.connect(self.on_pull_failed)
        self.worker.start()

    def on_pull_success(self, path, origin_url):
        self.pull_btn.setEnabled(True)
        self.pull_btn.setText("Pull Latest Changes")
        self.registry.add_path(path)
        if origin_url:
            self._add_recent_url(origin_url)
        QMessageBox.information(self, "Up to date", f"Pulled the latest changes into:\n{path}")

    def on_pull_failed(self, error_msg):
        self.pull_btn.setEnabled(True)
        self.pull_btn.setText("Pull Latest Changes")
        QMessageBox.critical(
            self, "Pull failed",
            f"Something went wrong:\n\n{error_msg}\n\nScroll the log above for full details."
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
        self.status_worker = RepoStatusWorker(paths)
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
        paths = self.registry.get_paths()
        if not paths:
            QMessageBox.information(self, "Nothing to pull", "No repos tracked yet.")
            return
        self.append_log("=" * 60)
        self.append_log(f"Pulling {len(paths)} repo(s)...")
        self._pull_all_queue = list(paths)
        self._pull_next_in_queue()

    def _pull_next_in_queue(self):
        if not self._pull_all_queue:
            self.append_log("Pull All complete.")
            self._refresh_dashboard()
            return
        path = self._pull_all_queue.pop(0)
        self.append_log(f"Pulling: {path}")
        worker = PullWorker(path)
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
        path = self.commit_path_input.text().strip()
        message = self.commit_message_input.toPlainText().strip()

        if not path:
            QMessageBox.warning(self, "Missing folder", "Please choose a repo folder.")
            return
        if not message:
            QMessageBox.warning(self, "Missing message", "Please enter a commit message.")
            return

        self.commit_push_btn.setEnabled(False)
        self.commit_push_btn.setText("Working...")
        self.append_log("=" * 60)
        self.append_log(f"Commit && push requested for: {path}")

        self.worker = CommitPushWorker(path, message)
        self.worker.log_message.connect(self.append_log)
        self.worker.finished_ok.connect(self.on_commit_push_success)
        self.worker.failed.connect(self.on_commit_push_failed)
        self.worker.start()

    def on_commit_push_success(self, summary):
        self.commit_push_btn.setEnabled(True)
        self.commit_push_btn.setText("Stage All, Commit && Push")
        self.commit_message_input.clear()
        QMessageBox.information(self, "Done", summary)

    def on_commit_push_failed(self, error_msg):
        self.commit_push_btn.setEnabled(True)
        self.commit_push_btn.setText("Stage All, Commit && Push")
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