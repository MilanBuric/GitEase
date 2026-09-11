"""
GitHub OAuth Device Flow login.

This lets the user click "Sign in with GitHub" instead of pasting a
Personal Access Token by hand. It requires a GitHub OAuth App with
Device Flow enabled:

  1. Go to https://github.com/settings/developers -> "New OAuth App".
  2. Fill in any name/homepage URL (e.g. your GitHub repo URL);
     the callback URL field can be anything, e.g. http://localhost --
     device flow doesn't use it.
  3. After creating the app, open its settings and check
     "Enable Device Flow".
  4. Copy the "Client ID" shown on that page and paste it below as
     GITHUB_CLIENT_ID. No client secret is needed for device flow.

Until GITHUB_CLIENT_ID is set, DeviceFlowLogin will fail immediately
with a clear message instead of trying to call GitHub.
"""

import time

import requests
from PySide6.QtCore import QThread, Signal

GITHUB_CLIENT_ID = "Ov23lisCqEgxyzhmaitH"  # <-- paste your OAuth App's Client ID here

DEVICE_CODE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
SCOPE = "repo"


class DeviceFlowLogin(QThread):
    code_ready = Signal(str, str)   # user_code, verification_uri -- show these to the user
    success = Signal(str)           # access token
    failed = Signal(str)

    def run(self):
        if not GITHUB_CLIENT_ID:
            self.failed.emit(
                "GitHub sign-in isn't configured yet -- GITHUB_CLIENT_ID is empty in "
                "github_oauth.py. Register an OAuth App at "
                "https://github.com/settings/developers, enable Device Flow, and paste "
                "the Client ID in that file. You can still use a manual token below."
            )
            return

        try:
            resp = requests.post(
                DEVICE_CODE_URL,
                data={"client_id": GITHUB_CLIENT_ID, "scope": SCOPE},
                headers={"Accept": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            device_code = data["device_code"]
            user_code = data["user_code"]
            verification_uri = data["verification_uri"]
            interval = data.get("interval", 5)
            expires_in = data.get("expires_in", 900)

            self.code_ready.emit(user_code, verification_uri)

            waited = 0
            while waited < expires_in:
                time.sleep(interval)
                waited += interval

                token_resp = requests.post(
                    TOKEN_URL,
                    data={
                        "client_id": GITHUB_CLIENT_ID,
                        "device_code": device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                    headers={"Accept": "application/json"},
                    timeout=15,
                )
                token_data = token_resp.json()

                if "access_token" in token_data:
                    self.success.emit(token_data["access_token"])
                    return

                error = token_data.get("error")
                if error == "authorization_pending":
                    continue
                elif error == "slow_down":
                    interval += 5
                    continue
                elif error:
                    self.failed.emit(f"GitHub login failed: {error}")
                    return

            self.failed.emit("Login timed out waiting for authorization -- please try again.")

        except requests.RequestException as e:
            self.failed.emit(f"Network error during GitHub login: {e}")