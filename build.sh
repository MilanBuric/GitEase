#!/bin/bash
# Builds GitEase into a single standalone executable using PyInstaller.
# Run this from the GitEase folder, with the venv already created:
#   python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt

set -e

echo "Installing PyInstaller (if not already installed)..."
venv/bin/pip install pyinstaller

ICON_FLAG=""
if [ -f "icon.icns" ]; then
    ICON_FLAG="--icon icon.icns"     # macOS app bundles need .icns, not .ico
elif [ -f "icon.ico" ]; then
    ICON_FLAG="--icon icon.ico"       # best-effort on Linux; often ignored by the WM
fi

echo
echo "Building GitEase ..."
venv/bin/pyinstaller --noconfirm --onefile --windowed --name GitEase $ICON_FLAG main.py

echo
echo "Done! Your executable is at: dist/GitEase"
echo "On macOS, PyInstaller may instead produce dist/GitEase.app -- launch that instead."