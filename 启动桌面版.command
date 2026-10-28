#!/bin/zsh
cd "$(dirname "$0")" || exit 1
xattr -d com.apple.quarantine ./TomatoNovelToolkit 2>/dev/null || true
exec ./TomatoNovelToolkit
