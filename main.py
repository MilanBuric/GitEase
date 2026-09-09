"""
GitEase
----------------
Paste a GitHub repo URL, pick a destination folder, hit "Clone && Connect".
Cloning already wires up the 'origin' remote automatically (that's how
`git clone` works) -- this app just gives you a GUI for it, with an
optional saved token for private repos, a "Pull latest" tool for repos you
already have, and a full log if anything goes wrong.
"""

import sys
import os
import subprocess
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QPlainTextEdit,
    QMessageBox, QGroupBox, QComboBox, QTabWidget
)
from PySide6.QtGui import QTextCursor, QFont, QIcon
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import QLineEdit as _QLE  # for EchoMode enum access

import keyring

from clone_worker import CloneWorker
from pull_worker import PullWorker
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
        self.resize(780, 680)
        self.setMinimumSize(620, 520)

        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.settings = QSettings("GitEase", "GitEase")
        self.worker = None

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
        subtitle_label = QLabel("Clone and update GitHub repos locally -- no terminal needed.")
        subtitle_label.setStyleSheet("color: #8b949e; font-weight: 400;")
        outer_layout.addWidget(title_label)
        outer_layout.addWidget(subtitle_label)
        outer_layout.addSpacing(4)

        # --- Tabs: Clone vs Pull ---
        self.tabs = QTabWidget()
        outer_layout.addWidget(self.tabs)

        self.clone_tab = QWidget()
        self.pull_tab = QWidget()
        self.tabs.addTab(self.clone_tab, "Clone New")
        self.tabs.addTab(self.pull_tab, "Pull Latest")

        self._build_clone_tab()
        self._build_pull_tab()

        # --- Log view (shared by both tabs) ---
        log_label = QLabel("LOG")
        log_label.setObjectName("sectionLabel")
        outer_layout.addWidget(log_label)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        outer_layout.addWidget(self.log_view)

        self.load_saved_token()
        self._refresh_recent_combo()

    # ================= Clone tab =================
    def _build_clone_tab(self):
        layout = QVBoxLayout(self.clone_tab)
        layout.setSpacing(10)
        layout.setContentsMargins(4, 12, 4, 4)

        # Recent repos
        recent_label = QLabel("RECENT REPOS")
        recent_label.setObjectName("sectionLabel")
        layout.addWidget(recent_label)
        self.recent_combo = QComboBox()
        self.recent_combo.setMinimumHeight(32)
        self.recent_combo.currentIndexChanged.connect(self._on_recent_selected)
        layout.addWidget(self.recent_combo)

        # Repo URL
        url_label = QLabel("GITHUB REPO URL")
        url_label.setObjectName("sectionLabel")
        layout.addWidget(url_label)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://github.com/user/repo.git")
        self.url_input.setMinimumHeight(34)
        layout.addWidget(self.url_input)

        # Destination folder
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

        # Auth (optional)
        token_group = QGroupBox("GitHub Token  ·  optional, only needed for private repos")
        token_layout = QHBoxLayout()
        token_layout.setSpacing(8)
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(_QLE.Password)
        self.token_input.setPlaceholderText("Personal Access Token")
        self.token_input.setMinimumHeight(32)
        token_layout.addWidget(self.token_input)
        save_token_btn = QPushButton("Save")
        save_token_btn.setMinimumHeight(32)
        save_token_btn.clicked.connect(self.save_token)
        token_layout.addWidget(save_token_btn)
        token_group.setLayout(token_layout)
        layout.addWidget(token_group)

        # Action row: Clone + Open in Explorer
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
        self._last_cloned_path = None

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

        self.worker = CloneWorker(url, dest, token)
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

    def on_pull_success(self, path):
        self.pull_btn.setEnabled(True)
        self.pull_btn.setText("Pull Latest Changes")
        QMessageBox.information(self, "Up to date", f"Pulled the latest changes into:\n{path}")

    def on_pull_failed(self, error_msg):
        self.pull_btn.setEnabled(True)
        self.pull_btn.setText("Pull Latest Changes")
        QMessageBox.critical(
            self, "Pull failed",
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