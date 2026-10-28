#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
python3 -m venv .build-venv
".build-venv/bin/python" -m pip install --upgrade pip pyinstaller
".build-venv/bin/pyinstaller" --noconfirm --clean --onefile --windowed --name TomatoNovelToolkit toolkit.py
echo "Done: dist/TomatoNovelToolkit"
