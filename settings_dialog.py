"""
SettingsDialog: houses authentication controls (manual token entry and
GitHub OAuth Device Flow sign-in) in a separate dialog, so the Clone tab
stays focused on cloning. Opened via the gear button in the header.

Self-contained: it reads/writes the token directly via keyring and emits
token_changed whenever the token is updated, so MainWindow just needs to
listen for that signal rather than own any of this UI.
"""

import webbrowser

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
)
from PySide6.QtWidgets import QLineEdit as _QLE
from PySide6.QtCore import Signal

import keyring

from github_oauth import DeviceFlowLogin

KEYRING_SERVICE = "repo-clone-tool"
KEYRING_USERNAME = "github-pat"


class SettingsDialog(QDialog):
    token_changed = Signal(str)

    def __init__(self, current_token="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(440)
        self.login_worker = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Git Authentication")
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(title)

        info = QLabel(
            "A token here is used for cloning and pulling private repos.\n"
            "Manual tokens work for GitHub, GitLab, and Bitbucket -- GitEase\n"
            "detects the host from the URL and formats the token correctly.\n"
            "\"Sign in with GitHub\" is GitHub-specific."
        )
        info.setStyleSheet("color: #8b949e;")
        layout.addWidget(info)

        token_label = QLabel("PERSONAL ACCESS TOKEN")
        token_label.setObjectName("sectionLabel")
        layout.addWidget(token_label)

        token_row = QHBoxLayout()
        token_row.setSpacing(8)
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(_QLE.Password)
        self.token_input.setText(current_token)
        self.token_input.setPlaceholderText("Personal Access Token")
        self.token_input.setMinimumHeight(32)
        token_row.addWidget(self.token_input)
        save_btn = QPushButton("Save")
        save_btn.setMinimumHeight(32)
        save_btn.clicked.connect(self.save_token)
        token_row.addWidget(save_btn)
        layout.addLayout(token_row)

        signin_btn = QPushButton("Sign in with GitHub instead")
        signin_btn.setMinimumHeight(32)
        signin_btn.clicked.connect(self.start_github_signin)
        layout.addWidget(signin_btn)

        layout.addStretch(1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.setMinimumHeight(32)
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    def save_token(self):
        token = self.token_input.text().strip()
        if not token:
            QMessageBox.warning(self, "No token", "Enter a token before saving.")
            return
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
            self.token_changed.emit(token)
            QMessageBox.information(self, "Saved", "Token saved to the system keyring.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save token: {e}")

    def start_github_signin(self):
        self.login_worker = DeviceFlowLogin()
        self.login_worker.code_ready.connect(self._on_code_ready)
        self.login_worker.success.connect(self._on_success)
        self.login_worker.failed.connect(self._on_failed)
        self.login_worker.start()

    def _on_code_ready(self, user_code, verification_uri):
        webbrowser.open(verification_uri)
        QMessageBox.information(
            self, "Sign in with GitHub",
            f"Your browser should have opened {verification_uri}.\n\n"
            f"Enter this code there:\n\n{user_code}\n\n"
            "This dialog will update automatically once you approve access."
        )

    def _on_success(self, token):
        self.token_input.setText(token)
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
        except Exception:
            pass
        self.token_changed.emit(token)
        QMessageBox.information(self, "Signed in", "Signed in with GitHub -- token saved.")

    def _on_failed(self, msg):
        QMessageBox.warning(self, "Sign-in unavailable", msg)