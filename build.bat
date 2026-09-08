@echo off
REM Builds GitEase into a single standalone .exe using PyInstaller.
REM Run this from the GitEase folder, with the venv already created.

echo Installing PyInstaller (if not already installed)...
venv\Scripts\pip install pyinstaller

echo.
echo Building GitEase.exe ...
venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name GitEase main.py

echo.
echo Done! Your executable is at: dist\GitEase.exe
echo You can now create a desktop shortcut to that file.
pause
