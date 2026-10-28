#!/usr/bin/env python3
"""Download the matching official Tomato Novel Downloader release."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import stat
import sys
from urllib.request import Request, urlopen

VERSION = "v2.4.16"
REPOSITORY = "zhongbai2333/Tomato-Novel-Downloader"
BASE_URL = f"https://github.com/{REPOSITORY}/releases/download/{VERSION}/"


def asset_name() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        return "TomatoNovelDownloader-WinArm64-v2.4.16.exe" if machine in {"arm64", "aarch64"} else "TomatoNovelDownloader-Win64-v2.4.16.exe"
    if system == "darwin":
        return "TomatoNovelDownloader-macOS_arm64-v2.4.16" if machine in {"arm64", "aarch64"} else "TomatoNovelDownloader-macOS_amd64-v2.4.16"
    if system == "linux":
        return "TomatoNovelDownloader-Linux_arm64-v2.4.16" if machine in {"arm64", "aarch64"} else "TomatoNovelDownloader-Linux_amd64-v2.4.16"
    raise RuntimeError(f"暂不支持的系统：{platform.system()}。请使用 Docker 或手动安装官方下载器。")


def ensure_downloader(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    name = asset_name()
    target = directory / name
    if target.is_file() and target.stat().st_size > 0:
        return target
    url = BASE_URL + name
    request = Request(url, headers={"User-Agent": "tomato-novel-toolkit/1.0"})
    print(f"正在下载官方 Tomato Novel Downloader：{name}", file=sys.stderr)
    try:
        with urlopen(request, timeout=60) as response, target.open("wb") as stream:
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"下载失败：{url}\n请检查网络，或从官方 Releases 手动下载后放入 {directory}")
    if os.name != "nt":
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="获取当前系统对应的 Tomato Novel Downloader")
    parser.add_argument("--dir", type=Path, default=Path(__file__).resolve().parents[1] / "bin")
    parser.add_argument("--print-only", action="store_true", help="只输出当前系统对应的发行版文件名")
    args = parser.parse_args()
    if args.print_only:
        print(asset_name())
        return 0
    print(ensure_downloader(args.dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
