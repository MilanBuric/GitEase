# GitEase

GitEase is a lightweight desktop app for Windows that clones a GitHub repository and connects it to your local machine — without touching a terminal or Git Bash.

Paste a repo URL, pick a destination folder, and click **Clone & Connect**. GitEase handles the rest, including linking the local folder to its GitHub remote (`origin`), and shows you a full log of everything that happens along the way.

## Features

- **One-click clone** — paste a URL, pick a folder, done.
- **Automatic remote setup** — the cloned folder is connected to its GitHub origin from the moment the clone finishes.
- **Private repo support** — optionally save a GitHub Personal Access Token, stored securely in your OS's credential manager (via `keyring`), never in plain text.
- **Live log** — every step (and any error) is shown in a scrollable log panel, so you always know exactly what happened and why.
- **Runs in the background** — cloning happens on a separate thread, so the app never freezes while git works.

## Requirements

- Windows 10/11
- [Git](https://git-scm.com/downloads) installed and available on your system PATH
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

## Building a Standalone Executable

To package GitEase into a single `.exe` that runs without Python or a terminal:

```powershell
.\build.bat
```

This installs [PyInstaller](https://pyinstaller.org/) into your virtual environment and builds `dist\GitEase.exe`. Create a shortcut to that file (right-click → Send to → Desktop) for one-click launching.

## Project Structure

```
GitEase/
├── main.py            # App entry point and main window (UI)
├── clone_worker.py     # Background thread that runs the actual git clone
├── style.py            # Dark theme stylesheet (QSS)
├── build.bat            # Builds a standalone .exe via PyInstaller
├── requirements.txt      # Python dependencies
└── README.md
```

## Tech Stack

- **[PySide6](https://doc.qt.io/qtforpython/)** — desktop GUI framework
- **[GitPython](https://gitpython.readthedocs.io/)** — Python wrapper around Git
- **[keyring](https://pypi.org/project/keyring/)** — secure, OS-level credential storage
- **[PyInstaller](https://pyinstaller.org/)** — packages the app into a standalone executable

## License

No license has been chosen yet for this project.
