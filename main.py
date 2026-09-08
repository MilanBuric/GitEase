"""
GitEase
----------------
Paste a GitHub repo URL, pick a destination folder, hit "Clone && Connect".
Cloning already wires up the 'origin' remote automatically (that's how
`git clone` works) -- this app just gives you a GUI for it, with an
optional saved token for private repos and a full log if anything goes wrong.
"""

import sys
import os
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QPlainTextEdit,
    QMessageBox, QGroupBox
)
from PySide6.QtGui import QTextCursor, QFont
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit as _QLE  # for EchoMode enum access

import keyring

from clone_worker import CloneWorker
from style import DARK_THEME

KEYRING_SERVICE = "repo-clone-tool"
KEYRING_USERNAME = "github-pat"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitEase")
        self.resize(760, 620)
        self.setMinimumSize(600, 480)

        self.worker = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # --- Header ---
        title_label = QLabel("GitEase")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title_label.setFont(title_font)
        subtitle_label = QLabel("Clone a GitHub repo and connect it locally -- no terminal needed.")
        subtitle_label.setStyleSheet("color: #8b949e; font-weight: 400;")
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addSpacing(6)

        # --- Repo URL ---
        url_label = QLabel("GITHUB REPO URL")
        url_label.setObjectName("sectionLabel")
        layout.addWidget(url_label)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://github.com/user/repo.git")
        self.url_input.setMinimumHeight(34)
        layout.addWidget(self.url_input)

        # --- Destination folder ---
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

        # --- Auth (optional) ---
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

        # --- Action button ---
        self.clone_btn = QPushButton("Clone && Connect")
        self.clone_btn.setObjectName("primaryButton")
        self.clone_btn.setMinimumHeight(42)
        self.clone_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clone_btn.clicked.connect(self.start_clone)
        layout.addWidget(self.clone_btn)

        # --- Log view ---
        log_label = QLabel("LOG")
        log_label.setObjectName("sectionLabel")
        layout.addWidget(log_label)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        layout.addWidget(self.log_view)

        self.load_saved_token()

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

    # ---------------- Folder picking ----------------
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose parent folder")
        if not folder:
            return
        url = self.url_input.text().strip()
        repo_name = self._repo_name_from_url(url) if url else ""
        full_path = os.path.join(folder, repo_name) if repo_name else folder
        self.dest_input.setText(full_path)

    @staticmethod
    def _repo_name_from_url(url):
        name = url.rstrip("/").split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]
        return name

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
        self.worker.finished_ok.connect(self.on_clone_success)
        self.worker.failed.connect(self.on_clone_failed)
        self.worker.start()

    def on_clone_success(self, path):
        self.clone_btn.setEnabled(True)
        self.clone_btn.setText("Clone && Connect")
        QMessageBox.information(self, "Success", f"Repository cloned and connected at:\n{path}")

    def on_clone_failed(self, error_msg):
        self.clone_btn.setEnabled(True)
        self.clone_btn.setText("Clone && Connect")
        QMessageBox.critical(
            self, "Clone failed",
            f"Something went wrong:\n\n{error_msg}\n\nScroll the log above for full details."
        )


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_THEME)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()