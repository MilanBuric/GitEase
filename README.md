# GitEase

GitEase is a lightweight desktop app for Windows, macOS, and Linux that clones, updates, tracks, and pushes changes to GitHub, GitLab, and Bitbucket repositories — all without touching a terminal.

## Features

- **One-click clone**, with an optional **branch picker** — see all remote branches and clone the one you want.
- **GitHub, GitLab, and Bitbucket support** — paste a URL from any of the three and GitEase automatically detects the host and formats your token correctly for it.
- **Automatic remote setup** — the cloned folder is connected to its origin remote from the moment the clone finishes.
- **Live clone progress bar**, alongside the detailed log.
- **Pull latest changes** — update a repo you already have locally.
- **Dashboard** — every repo you've cloned or added, in one table: current branch and ahead/behind status vs. origin. "Pull All" updates everything at once; "Add Existing Folder" registers a repo you cloned outside the app.
- **Commit && Push** — stage all changes, commit with a message, and push, from a single tab.
- **Settings dialog** — token entry and "Sign in with GitHub" (OAuth Device Flow) live in one place, out of the way of the Clone tab.
- **Recent repos** — your last few cloned/pulled URLs are remembered.
- **Open in file manager** — jump straight into a freshly cloned folder (Explorer / Finder / your Linux file manager, auto-detected).
- **Live, clearable log** — every step (and any error) shown in a scrollable panel, with a one-click Clear button.
- **Runs in the background** — all git operations happen on separate threads, so the app never freezes.

## Requirements

- Windows 10/11, macOS 11+, or Linux
- [Git](https://git-scm.com/downloads) installed and available on your system PATH
- Python 3.10+ (only needed if running from source — not needed for the prebuilt executable)

## Getting Started (from source)

```bash
git clone https://github.com/MilanBuric/GitEase.git
cd GitEase
python -m venv venv

# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
python main.py
```

## GitHub Sign-In Setup (optional)

"Sign in with GitHub" (in Settings) uses OAuth Device Flow and needs a free GitHub OAuth App:

1. Go to [github.com/settings/developers](https://github.com/settings/developers) → **New OAuth App**.
2. Fill in any name and homepage URL. The callback URL can be anything — device flow doesn't use it.
3. Check **Enable Device Flow** in the app's settings after creating it.
4. Copy the **Client ID** and paste it into `GITHUB_CLIENT_ID` in `github_oauth.py`. No client secret needed — it's not sensitive and is safe to commit.

Manual Personal Access Tokens (Settings dialog) work for GitHub, GitLab, and Bitbucket regardless of whether sign-in is configured.

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/
```

20 tests covering clone, branch listing, provider auth formatting, and commit/push logic — all git, network, and Qt calls mocked, so nothing real runs.

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

Both build `dist/GitEase` (or `dist\GitEase.exe` on Windows) via PyInstaller. On macOS this may instead produce `dist/GitEase.app`.

### Automated releases

Pushing a version tag triggers `.github/workflows/release.yml`, which builds the Windows executable, runs the test suite, and attaches `GitEase.exe` to a new GitHub Release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

## Project Structure

```
GitEase/
├── .github/workflows/release.yml   # CI: builds + releases GitEase.exe on version tags
├── tests/
│   ├── test_clone_worker.py         # Clone logic tests
│   ├── test_new_features.py          # Branch listing / commit+push tests
│   └── test_git_providers.py          # GitHub/GitLab/Bitbucket auth format tests
├── main.py                            # App entry point and main window (UI, 4 tabs)
├── clone_worker.py                     # Background thread: clone (branch + progress %)
├── pull_worker.py                       # Background thread: pull latest
├── branch_worker.py                      # Background thread: list remote branches
├── repo_registry.py                       # Tracks cloned repos + checks ahead/behind status
├── commit_push_worker.py                   # Background thread: stage, commit, push
├── github_oauth.py                          # GitHub OAuth Device Flow login
├── settings_dialog.py                        # Token entry + GitHub sign-in, in one dialog
├── git_providers.py                           # GitHub/GitLab/Bitbucket auth-format detection
├── style.py                                    # Dark theme stylesheet (QSS)
├── icon.ico / icon.png                          # App icon (Windows/Linux; see note below for macOS)
├── build.bat / build.sh                          # Standalone-executable builds (Windows / macOS+Linux)
├── requirements.txt                               # Runtime dependencies
├── requirements-dev.txt                            # Adds pytest + PyInstaller for development
├── LICENSE
└── README.md
```

## Tech Stack

- **[PySide6](https://doc.qt.io/qtforpython/)** — cross-platform desktop GUI framework
- **[GitPython](https://gitpython.readthedocs.io/)** — Python wrapper around Git
- **[keyring](https://pypi.org/project/keyring/)** — secure, OS-level credential storage (Windows Credential Manager / macOS Keychain / Linux Secret Service)
- **[requests](https://requests.readthedocs.io/)** — HTTP calls for GitHub OAuth device flow
- **[PyInstaller](https://pyinstaller.org/)** — packages the app into a standalone executable
- **[pytest](https://pytest.org/)** — test suite

## Known Limitations

- The prebuilt Windows `.exe` is unsigned, so Windows SmartScreen may show a warning on first run.
- "Sign in with GitHub" requires a one-time OAuth App setup (see above); it's GitHub-specific — GitLab/Bitbucket always use a manual token.
- `icon.ico` is used for the Windows/Linux window icon. A proper macOS app icon needs an `.icns` file, which isn't included yet — `build.sh` will use one automatically if you add `icon.icns` to the project root.
- macOS/Linux builds are new and less battle-tested than the Windows build.

## License

MIT — see [LICENSE](LICENSE).
