#!/usr/bin/env python3
"""Unified launcher for Tomato Novel Downloader and EPUB to TXT."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import threading
import webbrowser

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
SERVER_URL = "http://127.0.0.1:18423/"


def ensure_downloader() -> Path:
    from scripts.get_downloader import ensure_downloader as _ensure
    return _ensure(ROOT / "bin")


def start_downloader() -> subprocess.Popen:
    executable = ensure_downloader()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    args = [str(executable), "--server", "--data-dir", str(DATA_DIR)]
    password = os.environ.get("TOMATO_WEB_PASSWORD")
    if password:
        args.extend(["--password", password])
    process = subprocess.Popen(args, cwd=ROOT)
    threading.Timer(1.0, lambda: webbrowser.open(SERVER_URL)).start()
    return process


def launch_converter(files: list[str] | None = None) -> None:
    from epub_to_txt import launch_gui
    launch_gui(files or [])


def launch_gui() -> None:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("Tomato Novel Toolkit")
    root.geometry("620x360")
    root.minsize(520, 300)
    root.configure(bg="#f5f4ef")
    frame = tk.Frame(root, bg="#f5f4ef", padx=36, pady=30)
    frame.pack(fill="both", expand=True)
    tk.Label(frame, text="Tomato Novel Toolkit", font=("Arial", 24, "bold"), bg="#f5f4ef").pack(anchor="w")
    tk.Label(frame, text="获取番茄小说 · 下载 EPUB · 转换为 TXT", font=("Arial", 12), fg="#555555", bg="#f5f4ef", pady=10).pack(anchor="w")
    status = tk.StringVar(value="选择一个功能开始。")
    tk.Label(frame, textvariable=status, anchor="w", justify="left", wraplength=540, bg="#f5f4ef").pack(fill="x", pady=(8, 20))

    def downloader():
        try:
            start_downloader()
            status.set("下载器已启动，浏览器正在打开 Web UI。首次启动可能需要几秒钟。")
        except Exception as exc:
            messagebox.showerror("无法启动下载器", str(exc))
            status.set("下载器启动失败，请查看错误提示。")

    def converter():
        root.withdraw()
        try:
            launch_converter()
        finally:
            root.deiconify()

    tk.Button(frame, text="启动番茄小说下载器", command=downloader, width=24, height=2).pack(pady=6)
    tk.Button(frame, text="EPUB 转 TXT", command=converter, width=24, height=2).pack(pady=6)
    tk.Label(frame, text="下载器数据保存在 data/；EPUB 转 TXT 支持批量处理。", fg="#666666", bg="#f5f4ef").pack(anchor="w", pady=(18, 0))
    root.mainloop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="番茄小说下载器与 EPUB 转 TXT 整合工具")
    parser.add_argument("--server", action="store_true", help="启动下载器 Web UI，不打开整合窗口")
    parser.add_argument("--cli", action="store_true", help="直接进入 EPUB 转 TXT 命令行模式")
    parser.add_argument("files", nargs="*", help="--cli 模式下的 EPUB 文件")
    args = parser.parse_args(argv)
    if args.server and args.cli:
        parser.error("--server 和 --cli 不能同时使用")
    if args.server:
        process = start_downloader()
        return process.wait()
    if args.cli:
        command = [sys.executable, str(ROOT / "epub_to_txt.py"), "--cli", *args.files]
        return subprocess.call(command)
    launch_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
