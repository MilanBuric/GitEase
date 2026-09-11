# GitEase

GitEase is a lightweight desktop app for Windows that clones, updates, tracks, and pushes changes to GitHub repositories — all without touching a terminal or Git Bash.

## Features

- **One-click clone**, with an optional **branch picker** — see all remote branches and clone the one you want, not just the default.
- **Automatic remote setup** — the cloned folder is connected to its GitHub origin from the moment the clone finishes.
- **Pull latest changes** — update a repo you already have locally.
- **Dashboard** — every repo you've cloned with GitEase in one table: current branch, and whether it's ahead/behind origin. "Pull All" updates everything in one click.
- **Commit && Push** — stage all changes, commit with a message, and push, from a single tab.
- **Sign in with GitHub** — OAuth device-flow login as an alternative to pasting a Personal Access Token (see setup note below).
- **Recent repos** — your last few cloned URLs are remembered and one click away.
- **Open in Explorer** — jump straight into a freshly cloned folder.
- **Private repo support** — a Personal Access Token, stored securely in your OS's credential manager (via `keyring`), never in plain text.
- **Live log** — every step (and any error) is shown in a scrollable log panel.
- **Runs in the background** — all git operations happen on separate threads, so the app never freezes.

## Requirements

- Windows 10/11
- [Git](https://git-scm.com/downloads) installed and available on your system PATH
- Python 3.10+ (only needed if running from source — not needed for the prebuilt `.exe`)

## Getting Started (from source)

```powershell
git clone https://github.com/MilanBuric/GitEase.git
cd GitEase
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## GitHub Sign-In Setup (optional)

The "Sign in with GitHub" button uses OAuth Device Flow. It needs a free GitHub OAuth App:

1. Go to [github.com/settings/developers](https://github.com/settings/developers) → **New OAuth App**.
2. Fill in any name and homepage URL (e.g. this repo's URL). The callback URL can be anything — device flow doesn't use it.
3. After creating it, open the app's settings and check **Enable Device Flow**.
4. Copy the **Client ID** and paste it into `GITHUB_CLIENT_ID` in `github_oauth.py`.

Until this is set, the button shows a clear message and you can keep using a manual Personal Access Token instead — nothing else in the app depends on this being configured.

## Running Tests

```powershell
pip install -r requirements-dev.txt
pytest tests/
```

19 tests covering clone, branch listing, and commit/push logic, with all git and Qt calls mocked — no real network or git operations run.

## Building a Standalone Executable

```powershell
.\build.bat
```

Builds `dist\GitEase.exe` (with icon) via PyInstaller. Create a desktop shortcut to that file for one-click launching.

### Automated releases

Pushing a version tag triggers `.github/workflows/release.yml`, which builds the executable, runs the test suite, and attaches `GitEase.exe` to a new GitHub Release:

```powershell
git tag v1.0.0
git push origin v1.0.0
```

## Project Structure

```
GitEase/
├── .github/workflows/release.yml   # CI: builds + releases GitEase.exe on version tags
├── tests/
│   ├── test_clone_worker.py         # Clone logic tests
│   └── test_new_features.py          # Branch listing / commit+push tests
├── main.py                            # App entry point and main window (UI, 4 tabs)
├── clone_worker.py                     # Background thread: clone (with optional branch)
├── pull_worker.py                       # Background thread: pull latest
├── branch_worker.py                      # Background thread: list remote branches
├── repo_registry.py                       # Tracks cloned repos + checks ahead/behind status
├── commit_push_worker.py                   # Background thread: stage, commit, push
├── github_oauth.py                          # GitHub OAuth Device Flow login
├── style.py                                  # Dark theme stylesheet (QSS)
├── icon.ico / icon.png                        # App icon
├── build.bat                                   # Builds a standalone .exe via PyInstaller
├── requirements.txt                              # Runtime dependencies
├── requirements-dev.txt                           # Adds pytest + PyInstaller for development
├── LICENSE
└── README.md
```

## Tech Stack

- **[PySide6](https://doc.qt.io/qtforpython/)** — desktop GUI framework
- **[GitPython](https://gitpython.readthedocs.io/)** — Python wrapper around Git
- **[keyring](https://pypi.org/project/keyring/)** — secure, OS-level credential storage
- **[requests](https://requests.readthedocs.io/)** — HTTP calls for GitHub OAuth device flow
- **[PyInstaller](https://pyinstaller.org/)** — packages the app into a standalone executable
- **[pytest](https://pytest.org/)** — test suite

## Known Limitations

- Windows-only for now (the "Open in Explorer" button and build script are Windows-specific).
- The prebuilt `.exe` is unsigned, so Windows SmartScreen may show a warning on first run.
- "Sign in with GitHub" requires a one-time OAuth App setup (see above) before it will work.

## License

MIT — see [LICENSE](LICENSE).
