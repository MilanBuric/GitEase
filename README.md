# GitEase

GitEase is a lightweight desktop app for Windows, macOS, and Linux that clones, updates, tracks, and pushes changes to GitHub, GitLab, and Bitbucket repositories — all without touching a terminal or Git Bash.

Paste a repo URL, pick a destination folder, and click **Clone & Connect**. GitEase handles the rest: it connects the local folder to its remote, shows you a live progress bar and a detailed log of every step, and remembers the repo for next time. From there you can pull updates, check the status of everything you've cloned in one dashboard, commit and push changes, and manage authentication for all three supported git hosts — all from one window.

## Features

- **One-click clone.** Paste a URL, pick a folder, click a button. No git commands typed anywhere.

- **Branch picker.** Click "List Branches" before cloning to see every branch on the remote, and choose which one to clone instead of always getting the default.

- **GitHub, GitLab, and Bitbucket support.** GitEase detects which of the three a URL belongs to as you type (shown live under the URL field), and applies the correct authentication format for that host automatically — each of the three expects a slightly different way of pairing a token with a username over HTTPS, and GitEase handles that difference for you.

- **A separate saved token per provider.** Settings has one token field for GitHub, one for GitLab, and one for Bitbucket, each stored independently. You can have private repos on all three at once without one token overwriting another.

- **Tokens are never left sitting in plaintext.** A token is only ever embedded in a repo's remote URL for the few seconds an actual clone, pull, push, or status-check network call is in flight. The instant that call finishes — whether it succeeds or fails — the clean, token-free URL is restored. Nothing sensitive is left behind in `.git/config` afterward.

- **Clear, specific error messages instead of silent hangs.** If git needs interactive credentials it has no way to ask for from a background thread, GitEase fails fast with an explanation rather than freezing indefinitely. If a pull hits a merge conflict, or a push is rejected because someone else pushed first, you get a plain-English explanation of what happened and what to do next — not a raw git stack trace.

- **Abort a stuck merge** right from the Pull tab if a pull ever leaves you mid-conflict, without needing to open a terminal.

- **Cancel button** on Clone, Pull, and Commit && Push. Stops a hung or unwanted operation. This is a hard interrupt (not a graceful stop), and GitEase says so plainly when you use it, with a reminder to double-check the repo's state afterward.

- **Only one operation runs at a time.** Trying to start a second clone/pull/push while one is already in progress is blocked with a clear message, instead of letting two operations silently step on each other.

- **Weighted, monotonic clone progress bar.** Tracks git's real internal phases — counting objects, compressing, receiving, resolving deltas, checking out — and weights them so the bar climbs steadily from 0 to 100 instead of visibly resetting every time git moves to a new phase.

- **Automatic remote setup.** The moment a clone finishes, the local folder is already connected to its origin remote — this is just how `git clone` works, but GitEase confirms it in the log so you can see it happened.

- **Pull Latest tab.** Point GitEase at a folder you've already cloned to fetch and merge the newest changes from its remote.

- **Dashboard tab.** Every repo you've cloned or manually added, in one table: current branch, and whether it's ahead of, behind, or in sync with its remote. "Pull All" updates everything in one click. "Add Existing Folder" registers a repo you cloned outside of GitEase (e.g. via a plain `git clone` in a terminal) without needing to pull it first just to make it show up.

- **Commit && Push tab.** Stage all changes, write a commit message, and push — all from one screen.

- **Settings dialog.** All authentication controls — the three provider token fields and "Sign in with GitHub" — live behind a gear-icon button in the header, out of the way of the Clone tab.

- **Sign in with GitHub.** An alternative to pasting a token by hand: GitHub's OAuth Device Flow lets you authorize GitEase by visiting a GitHub page and entering a short code, no token copy-pasting required. (GitHub-specific; see setup below.)

- **Recent repos.** Your last several cloned or pulled URLs are remembered in a dropdown on the Clone tab.

- **Open in file manager.** Jump straight into a freshly cloned folder — opens Explorer on Windows, Finder on macOS, or your default file manager on Linux, auto-detected. If the expected system command isn't available, GitEase tells you plainly instead of crashing.

- **Live, clearable log.** Every step — and any error — is shown in a scrollable panel with timestamps, with a one-click Clear button so it doesn't get unwieldy over a long session.

- **Runs in the background.** All git operations happen on separate threads, so the app's window never freezes while a clone, pull, or push is working.

## Requirements

- Windows 10/11, macOS 11+, or Linux
- [Git](https://git-scm.com/downloads) installed and available on your system PATH
- Python 3.10+ (only needed if running from source — not needed if you're using the prebuilt executable)

## Getting Started (from source)

```bash
git clone https://github.com/MilanBuric/GitEase.git
cd GitEase
python -m venv venv
```

Activate the virtual environment:

```bash
# Windows (PowerShell):
venv\Scripts\activate

# macOS/Linux:
source venv/bin/activate
```

Install dependencies and run:

```bash
pip install -r requirements.txt
python main.py
```

## GitHub Sign-In Setup (optional)

The "Sign in with GitHub" button in Settings uses GitHub's OAuth Device Flow. It requires a free GitHub OAuth App, which only takes a minute to set up:

1. Go to [github.com/settings/developers](https://github.com/settings/developers) → **New OAuth App**.
2. Fill in any application name and homepage URL (your GitEase repo's URL works fine for the homepage).
3. Fill in a redirect URI — any value works, e.g. `http://localhost`. Device flow doesn't actually use this field, but GitHub requires something be entered.
4. After registering, open the app's settings page and check **Enable Device Flow**.
5. Copy the **Client ID** shown on that page.
6. Open `github_oauth.py` in the project and paste the Client ID into the `GITHUB_CLIENT_ID` variable near the top of the file.

No client secret is needed — device flow doesn't use one. The Client ID itself is not a secret (it's meant to be publicly visible, the same way it's visible in the page source of any website with a "Sign in with GitHub" button), so it's safe to commit to a public repository.

Until `GITHUB_CLIENT_ID` is set, clicking "Sign in with GitHub" shows a clear message explaining that it isn't configured yet, and you can keep using a manual Personal Access Token in the meantime — nothing else in the app depends on sign-in being set up.

GitLab and Bitbucket don't have an equivalent sign-in button in GitEase — each would require its own separate OAuth app registration and a different authorization flow to support. Manual tokens (in the Settings dialog, one field per provider) work for all three hosts regardless of whether sign-in is configured.

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/
```

24 tests across 5 files, covering:

- Clone logic (`test_clone_worker.py`)
- Branch listing and commit/push logic (`test_new_features.py`)
- Provider detection and auth-URL formatting for GitHub/GitLab/Bitbucket (`test_git_providers.py`)
- Credential safety (`test_credential_safety.py`) — including a test that deliberately raises an exception mid-operation and confirms the token-free URL is still restored, proving the fix holds under failure, not just the happy path.

All git, network, and Qt calls are mocked, so the full suite runs in a fraction of a second with no real repos, network calls, or windows involved.

## Building a Standalone Executable

**Windows:**

```powershell
.\build.bat
```

**macOS/Linux:**

```bash
chmod +x build.sh   # first time only
./build.sh
```

Both scripts install [PyInstaller](https://pyinstaller.org/) into your virtual environment and build a standalone executable in `dist/` — `dist\GitEase.exe` on Windows, `dist/GitEase` on Linux, or `dist/GitEase.app` on macOS. Once built, you can create a desktop shortcut to that file and launch GitEase without ever opening a terminal or IDE again.

### Automated releases

Pushing a version tag triggers `.github/workflows/release.yml`, which builds the Windows executable, runs the full test suite, and attaches `GitEase.exe` to a new GitHub Release automatically:

```bash
git tag v1.0.0
git push origin v1.0.0
```

## Project Structure

```
GitEase/
├── .github/
│   └── workflows/
│       └── release.yml         # CI: builds GitEase.exe and runs tests on every version tag, publishes a Release
├── tests/
│   ├── test_clone_worker.py     # Clone logic: token injection, empty-folder check, success/failure paths
│   ├── test_new_features.py      # Branch listing and commit/push logic
│   ├── test_git_providers.py      # GitHub/GitLab/Bitbucket URL auth-format detection
│   └── test_credential_safety.py   # Proves tokens are never left behind, even when an operation fails
├── main.py                          # App entry point and main window: 4 tabs, header, log panel,
│                                     # busy-operation guard, cancel handling, merge-abort action
├── clone_worker.py                   # Background thread: clones a repo, optional branch, weighted
│                                     # progress reporting, strips the token from the remote right after cloning
├── pull_worker.py                     # Background thread: pulls an existing local repo, with
│                                     # temporary token auth and merge-conflict detection
├── branch_worker.py                    # Background thread: lists a remote's branches before cloning
├── repo_registry.py                     # Persists which repos GitEase is tracking (for the Dashboard),
│                                     # and checks each one's branch + ahead/behind status against origin
├── commit_push_worker.py                 # Background thread: stages all changes, commits, and pushes,
│                                     # with temporary token auth and push-rejection detection
├── github_oauth.py                        # GitHub OAuth Device Flow login
├── settings_dialog.py                      # The Settings dialog: one token field per provider, sign-in button
├── git_providers.py                         # Detects which host a URL belongs to, builds the correctly
│                                     # -formatted authenticated URL for that host, and provides the
│                                     # temporarily_authed_remote context manager used everywhere a
│                                     # git network call needs a token without persisting it
├── style.py                                  # Dark theme stylesheet (QSS)
├── icon.ico / icon.png                        # App icon (Windows/Linux window icon and taskbar/dock icon)
├── build.bat                                   # Builds a standalone Windows .exe via PyInstaller
├── build.sh                                     # Builds a standalone macOS/Linux executable via PyInstaller
├── requirements.txt                              # Runtime dependencies
├── requirements-dev.txt                           # Adds pytest and PyInstaller, for development and testing
├── LICENSE                                         # MIT License
└── README.md                                        # This file
```

## Tech Stack

- **[PySide6](https://doc.qt.io/qtforpython/)** — the cross-platform desktop GUI framework the whole app's interface is built with (Qt for Python).
- **[GitPython](https://gitpython.readthedocs.io/)** — a Python wrapper around the `git` command-line tool, used for every clone, pull, push, and status check.
- **[keyring](https://pypi.org/project/keyring/)** — secure, OS-level credential storage. Uses Windows Credential Manager on Windows, Keychain on macOS, and Secret Service (e.g. GNOME Keyring) on Linux, so tokens are never stored as plain files.
- **[requests](https://requests.readthedocs.io/)** — used for the HTTP calls involved in GitHub's OAuth Device Flow.
- **[PyInstaller](https://pyinstaller.org/)** — packages the Python app and all its dependencies into a single standalone executable.
- **[pytest](https://pytest.org/)** — the test framework used for the full test suite.

## Known Limitations

These are deliberate, documented scope boundaries rather than bugs or oversights:

- **No merge-conflict resolution UI.** GitEase detects a conflict clearly and can abort a stuck merge, but it doesn't provide any way to resolve conflicting files from within the app — that still requires a text editor or terminal.
- **Cancel is a hard interrupt, not a graceful stop.** Cancelling mid-operation can leave a git operation partway done. Always check the repo's state afterward — via the Dashboard tab, or by trying Pull Latest again — rather than assuming everything is consistent.
- **"Sign in with GitHub" is GitHub-specific.** GitLab and Bitbucket don't have an equivalent one-click sign-in in GitEase; both always use a manually-entered token.
- **The prebuilt Windows executable is unsigned.** Windows SmartScreen may show a "Windows protected your PC" warning the first time you run it, since it isn't signed with a paid code-signing certificate.
- **No macOS app icon (`.icns`) is included yet.** `icon.ico` covers the Windows and Linux window icon. `build.sh` will automatically use an `icon.icns` file if you add one to the project root, but one isn't provided out of the box.
- **macOS/Linux support is logically complete and covered by the test suite, but has not been verified on real macOS or Linux hardware.** It's been developed and tested inside a Linux sandbox environment, not run on an actual Mac or a typical end-user Linux desktop.
- **This is a single-user, single-machine tool.** Tokens are stored in that one machine's OS credential store. There's no concept of multiple GitEase user accounts, team-shared configuration, or syncing settings across devices.

## License

MIT — see [LICENSE](LICENSE).
