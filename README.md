# GitEase

GitEase is a lightweight desktop app for Windows that clones a GitHub repository, connects it to your local machine, and keeps it up to date — all without touching a terminal or Git Bash.

Paste a repo URL, pick a destination folder, and click **Clone & Connect**. GitEase handles the rest, including linking the local folder to its GitHub remote (`origin`), and shows you a full log of everything that happens along the way. Already have a repo cloned? Switch to the **Pull Latest** tab to fetch and merge new changes with one click.

## Features

- **One-click clone** — paste a URL, pick a folder, done.
- **Automatic remote setup** — the cloned folder is connected to its GitHub origin from the moment the clone finishes.
- **Pull latest changes** — update a repo you already have locally, without opening a terminal.
- **Recent repos** — your last few cloned URLs are remembered and one click away.
- **Open in Explorer** — jump straight into a freshly cloned folder.
- **Private repo support** — optionally save a GitHub Personal Access Token, stored securely in your OS's credential manager (via `keyring`), never in plain text.
- **Live log** — every step (and any error) is shown in a scrollable log panel.
- **Runs in the background** — cloning and pulling happen on a separate thread, so the app never freezes.

## Requirements

- Windows 10/11
- [Git](https://git-scm.com/downloads) installed and available on your system PATH (needed for both HTTPS and SSH repo URLs — SSH URLs use your existing SSH keys, the same as running `git clone` yourself)
- Python 3.10+ (only needed if running from source — not needed if you use the prebuilt `.exe`)

## Getting Started (from source)

1. Clone this repository:
   ```powershell
   git clone https://github.com/MilanBuric/GitEase.git
   cd GitEase
   ```
2. Create and activate a virtual environment:
   ```powershell
   python -m venv venv
   venv\Scripts\activate
   ```
3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4. Run the app:
   ```powershell
   python main.py
   ```

## Running Tests

```powershell
pip install -r requirements-dev.txt
pytest tests/
```

Tests mock out GitPython entirely, so they run instantly with no real network or git calls.

## Building a Standalone Executable

To package GitEase into a single `.exe` (with icon) that runs without Python or a terminal:

```powershell
.\build.bat
```

This installs [PyInstaller](https://pyinstaller.org/) into your virtual environment and builds `dist\GitEase.exe`. Create a shortcut to that file (right-click → Send to → Desktop) for one-click launching.

### Automated releases

Pushing a version tag (e.g. `v1.0.0`) triggers a GitHub Actions workflow (`.github/workflows/release.yml`) that builds the executable, runs the test suite, and attaches `GitEase.exe` to a new GitHub Release automatically:

```powershell
git tag v1.0.0
git push origin v1.0.0
```

## Project Structure

```
GitEase/
├── .github/workflows/release.yml   # CI: builds + releases GitEase.exe on version tags
├── tests/test_clone_worker.py       # Unit tests for the clone logic
├── main.py                           # App entry point and main window (UI)
├── clone_worker.py                    # Background thread that clones a repo
├── pull_worker.py                      # Background thread that pulls an existing repo
├── style.py                             # Dark theme stylesheet (QSS)
├── icon.ico / icon.png                   # App icon
├── build.bat                              # Builds a standalone .exe via PyInstaller
├── requirements.txt                        # Runtime dependencies
├── requirements-dev.txt                     # Adds pytest + PyInstaller for development
├── LICENSE
└── README.md
```

## Tech Stack

- **[PySide6](https://doc.qt.io/qtforpython/)** — desktop GUI framework
- **[GitPython](https://gitpython.readthedocs.io/)** — Python wrapper around Git
- **[keyring](https://pypi.org/project/keyring/)** — secure, OS-level credential storage
- **[PyInstaller](https://pyinstaller.org/)** — packages the app into a standalone executable
- **[pytest](https://pytest.org/)** — test suite for the clone/pull logic

## Known Limitations

- Windows-only for now (the "Open in Explorer" button and the build script are Windows-specific).
- The prebuilt `.exe` is unsigned, so Windows SmartScreen may show a warning on first run ("Windows protected your PC" → "More info" → "Run anyway"). Code signing isn't set up yet.

## License

MIT — see [LICENSE](LICENSE).
