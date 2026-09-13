"""
SettingsDialog: houses authentication controls for all three supported
git hosts. Each provider gets its own token field and its own keyring
entry -- previously there was one shared token field, which meant
saving a GitLab token silently overwrote a saved GitHub one (or vice
versa). Now they're independent.

Self-contained: reads/writes tokens directly via keyring and emits
tokens_changed with the full {provider: token} dict whenever anything
changes, so MainWindow just listens for that rather than owning any of
this UI.
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
# One keyring entry per provider -- this is the fix for the old
# single-token-field design, which could only hold one provider's
# credential at a time.
PROVIDERS = ["GitHub", "GitLab", "Bitbucket"]
KEYRING_USERNAMES = {
    "GitHub": "github-pat",
    "GitLab": "gitlab-pat",
    "Bitbucket": "bitbucket-pat",
}


def load_all_tokens():
    """Reads all three provider tokens from the system keyring. Used at
    app startup and by the dialog itself."""
    tokens = {}
    for provider in PROVIDERS:
        try:
            tokens[provider] = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAMES[provider]) or ""
        except Exception:
            tokens[provider] = ""
    return tokens


class SettingsDialog(QDialog):
    tokens_changed = Signal(dict)   # {"GitHub": "...", "GitLab": "...", "Bitbucket": "..."}

    def __init__(self, current_tokens=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(460)
        self.login_worker = None
        self.tokens = dict(current_tokens or {})
        self.token_inputs = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Git Authentication")
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(title)

        info = QLabel(
            "Each provider has its own token, so you can work with private\n"
            "repos on more than one host at once. GitEase detects the host\n"
            "from the repo URL and uses the matching token automatically."
        )
        info.setStyleSheet("color: #8b949e;")
        layout.addWidget(info)

        for provider in PROVIDERS:
            label = QLabel(f"{provider.upper()} TOKEN")
            label.setObjectName("sectionLabel")
            layout.addWidget(label)

            row = QHBoxLayout()
            row.setSpacing(8)
            token_input = QLineEdit()
            token_input.setEchoMode(_QLE.Password)
            token_input.setText(self.tokens.get(provider, ""))
            token_input.setPlaceholderText(f"{provider} Personal Access Token")
            token_input.setMinimumHeight(32)
            row.addWidget(token_input)
            save_btn = QPushButton("Save")
            save_btn.setMinimumHeight(32)
            save_btn.clicked.connect(lambda _checked, p=provider: self.save_token(p))
            row.addWidget(save_btn)
            layout.addLayout(row)

            self.token_inputs[provider] = token_input

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

    def save_token(self, provider):
        token = self.token_inputs[provider].text().strip()
        if not token:
            QMessageBox.warning(self, "No token", f"Enter a {provider} token before saving.")
            return
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAMES[provider], token)
            self.tokens[provider] = token
            self.tokens_changed.emit(dict(self.tokens))
            QMessageBox.information(self, "Saved", f"{provider} token saved to the system keyring.")
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
        self.token_inputs["GitHub"].setText(token)
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAMES["GitHub"], token)
        except Exception:
            pass
        self.tokens["GitHub"] = token
        self.tokens_changed.emit(dict(self.tokens))
        QMessageBox.information(self, "Signed in", "Signed in with GitHub -- token saved.")

    def _on_failed(self, msg):
        QMessageBox.warning(self, "Sign-in unavailable", msg)