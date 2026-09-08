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
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QLineEdit as _QLE  # for EchoMode enum access

import keyring

from clone_worker import CloneWorker

KEYRING_SERVICE = "repo-clone-tool"
KEYRING_USERNAME = "github-pat"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitEase")
        self.resize(720, 560)

        self.worker = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- Repo URL ---
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("GitHub repo URL:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://github.com/user/repo.git")
        url_layout.addWidget(self.url_input)
        layout.addLayout(url_layout)

        # --- Destination folder ---
        dest_layout = QHBoxLayout()
        dest_layout.addWidget(QLabel("Destination folder:"))
        self.dest_input = QLineEdit()
        dest_layout.addWidget(self.dest_input)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_folder)
        dest_layout.addWidget(browse_btn)
        layout.addLayout(dest_layout)

        # --- Auth (optional) ---
        token_group = QGroupBox("GitHub token (optional -- only needed for private repos)")
        token_layout = QHBoxLayout()
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(_QLE.Password)
        self.token_input.setPlaceholderText("Personal Access Token")
        token_layout.addWidget(self.token_input)
        save_token_btn = QPushButton("Save token")
        save_token_btn.clicked.connect(self.save_token)
        token_layout.addWidget(save_token_btn)
        token_group.setLayout(token_layout)
        layout.addWidget(token_group)

        # --- Action button ---
        self.clone_btn = QPushButton("Clone && Connect")
        self.clone_btn.setMinimumHeight(36)
        self.clone_btn.clicked.connect(self.start_clone)
        layout.addWidget(self.clone_btn)

        # --- Log view ---
        layout.addWidget(QLabel("Log:"))
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
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()