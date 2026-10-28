#!/usr/bin/env python3
"""EPUB to UTF-8 TXT. GUI by default; --cli exposes batch conversion."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import posixpath
import queue
import re
import subprocess
import sys
import threading
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile


class ConversionError(Exception):
    pass


@dataclass
class Book:
    title: str
    authors: list[str]
    chapters: list[str]


class TextExtractor(HTMLParser):
    BLOCKS = set("address article aside blockquote caption dd div dl dt figcaption figure footer h1 h2 h3 h4 h5 h6 header hr li main ol p pre section table tr ul".split())
    IGNORE = {"head", "script", "style", "noscript", "rt", "rp", "svg"}
    VOID = set("area base br col embed hr img input link meta param source track wbr".split())

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if self.skip_depth:
            if tag not in self.VOID:
                self.skip_depth += 1
            return
        if tag in self.IGNORE:
            self.skip_depth = 1
        elif tag in self.BLOCKS:
            self.parts.append("\n\n")
        elif tag == "br":
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append(" ")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.skip_depth:
            if tag not in self.VOID:
                self.skip_depth -= 1
        elif tag in self.BLOCKS:
            self.parts.append("\n\n")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(re.sub(r"\s+", " ", data.replace("\u200b", "")))

    def text(self):
        value = "".join(self.parts)
        value = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines())
        return re.sub(r"\n{3,}", "\n\n", value).strip()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def archive_path(base: str, href: str) -> str:
    parts = urlsplit(href)
    if parts.scheme or parts.netloc or parts.path.startswith("/"):
        raise ConversionError(f"电子书引用了非本地内容：{href}")
    result = posixpath.normpath(posixpath.join(base, unquote(parts.path)))
    if result == ".." or result.startswith("../"):
        raise ConversionError("电子书内部路径超出了书籍目录。")
    return result


def read_entry(archive: ZipFile, name: str) -> bytes:
    try:
        info = archive.getinfo(name)
        if info.file_size > 32 * 1024 * 1024:
            raise ConversionError(f"内部文件过大，无法处理：{name}")
        return archive.read(info)
    except KeyError as exc:
        raise ConversionError(f"电子书缺少内部文件：{name}") from exc
    except RuntimeError as exc:
        raise ConversionError(f"无法读取内部文件，可能已加密：{name}") from exc


def parse_xml(data: bytes, name: str):
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise ConversionError(f"电子书的 {name} 格式不正确。") from exc


def decode_document(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    # EPUB normally uses UTF-8; support common legacy Chinese books too.
    match = re.search(br"(?:encoding|charset)\s*=\s*[\"']?\s*([a-zA-Z0-9_-]+)", data[:2048], re.I)
    candidates = [match.group(1).decode("ascii")] if match else []
    for encoding in candidates + ["utf-8-sig", "gb18030"]:
        try:
            return data.decode(encoding)
        except (UnicodeError, LookupError):
            pass
    raise ConversionError("某个章节的文字编码无法识别。")


def read_book(source: Path) -> Book:
    if source.suffix.lower() != ".epub":
        raise ConversionError("请选择 .epub 格式的电子书。")
    try:
        with ZipFile(source) as archive:
            if sum(item.file_size for item in archive.infolist()) > 256 * 1024 * 1024:
                raise ConversionError("电子书解压后的内容超过 256 MB，暂不支持。")
            container = parse_xml(read_entry(archive, "META-INF/container.xml"), "container.xml")
            roots = [node for node in container.iter() if local_name(node.tag) == "rootfile"]
            root = next((node for node in roots if node.get("media-type") == "application/oebps-package+xml"), roots[0] if roots else None)
            if root is None or not root.get("full-path"):
                raise ConversionError("找不到电子书的 OPF 目录文件。")
            opf_path = archive_path("", root.get("full-path"))
            package = parse_xml(read_entry(archive, opf_path), "OPF")
            base = posixpath.dirname(opf_path)
            metadata = next((node for node in package if local_name(node.tag) == "metadata"), None)
            title = source.stem
            authors = []
            if metadata is not None:
                for node in metadata:
                    text = "".join(node.itertext()).strip()
                    if local_name(node.tag) == "title" and text:
                        title = text
                        break
                authors = ["".join(node.itertext()).strip() for node in metadata if local_name(node.tag) == "creator" and "".join(node.itertext()).strip()]
            manifest = {node.get("id"): node for node in package.iter() if local_name(node.tag) == "item"}
            spine = next((node for node in package if local_name(node.tag) == "spine"), None)
            if spine is None:
                raise ConversionError("找不到章节阅读顺序（spine），无法可靠转换。")
            encrypted = set()
            if "META-INF/encryption.xml" in archive.namelist():
                encryption = parse_xml(read_entry(archive, "META-INF/encryption.xml"), "encryption.xml")
                encrypted = {archive_path("", node.get("URI")) for node in encryption.iter() if local_name(node.tag) == "CipherReference" and node.get("URI")}
            chapters = []
            seen = set()
            for ref in spine:
                if local_name(ref.tag) != "itemref" or ref.get("linear", "yes") == "no":
                    continue
                item = manifest.get(ref.get("idref"))
                if item is None or not item.get("href"):
                    raise ConversionError(f"某个章节的目录引用已损坏：{ref.get('idref', '未知章节')}")
                if "nav" in item.get("properties", "").split():
                    continue
                if item.get("media-type") not in {"application/xhtml+xml", "text/html"}:
                    continue
                path = archive_path(base, item.get("href"))
                if path in encrypted:
                    raise ConversionError("正文已加密或受 DRM 保护，无法直接转换。")
                if path in seen:
                    continue
                seen.add(path)
                parser = TextExtractor()
                parser.feed(decode_document(read_entry(archive, path)))
                parser.close()
                text = parser.text()
                if text:
                    chapters.append(text)
            if not chapters:
                raise ConversionError("没有找到可提取的正文；纯图片电子书需要先做 OCR。")
            return Book(title, authors, chapters)
    except (BadZipFile, OSError, UnicodeError) as exc:
        raise ConversionError(f"无法读取电子书：{exc}") from exc


def convert(source: Path, output_dir: Path | None = None) -> Path:
    book = read_book(source)
    folder = output_dir if output_dir is not None else source.parent
    folder.mkdir(parents=True, exist_ok=True)
    header = book.title + ("\n作者：" + "、".join(book.authors) if book.authors else "")
    content = header + "\n\n" + "\n\n".join(book.chapters) + "\n"
    number = 1
    while True:
        suffix = "" if number == 1 else f"_{number}"
        target = folder / f"{source.stem}{suffix}.txt"
        try:
            # Exclusive creation protects existing files and simultaneous conversions.
            stream = target.open("x", encoding="utf-8-sig", newline="\n")
        except FileExistsError:
            number += 1
            continue
        try:
            with stream:
                stream.write(content)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target


def launch_gui(initial_files: list[str]):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("EPUB 转 TXT")
    left = max(0, (root.winfo_screenwidth() - 820) // 2)
    top = max(0, (root.winfo_screenheight() - 560) // 2)
    root.geometry(f"820x560+{left}+{top}")
    root.minsize(680, 460)
    root.configure(bg="#f5f4ef")
    style = ttk.Style(root)
    style.configure("Treeview", rowheight=30)
    style.configure("TButton", padding=(12, 7))
    outer = ttk.Frame(root, padding=24)
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text="EPUB 转 TXT", font=("Arial", 26, "bold")).pack(anchor="w")
    ttk.Label(outer, text="按书籍原有章节顺序导出纯文本 · 支持批量转换", padding=(0, 8, 0, 20)).pack(anchor="w")
    toolbar = ttk.Frame(outer)
    toolbar.pack(fill="x")
    files: dict[str, Path] = {}
    results: list[Path] = []
    events = queue.Queue()
    busy = False
    output_var = tk.StringVar()
    status_var = tk.StringVar(value="添加 EPUB 文件后，点击“开始转换”。")
    table = ttk.Treeview(outer, columns=("file", "status"), show="headings", selectmode="extended")
    table.heading("file", text="电子书文件")
    table.heading("status", text="状态")
    table.column("file", width=480)
    table.column("status", width=160)
    table.pack(fill="both", expand=True, pady=12)
    scroll = ttk.Scrollbar(table, orient="vertical", command=table.yview)
    scroll.pack(side="right", fill="y")
    table.configure(yscrollcommand=scroll.set)

    def add_files(paths):
        known = set(files.values())
        for filename in paths:
            path = Path(filename).resolve()
            if path not in known and path.suffix.lower() == ".epub":
                item_id = table.insert("", "end", values=(path.name, "等待转换"))
                files[item_id] = path
                known.add(path)
        status_var.set(f"已添加 {len(files)} 本电子书。")

    def choose_files():
        add_files(filedialog.askopenfilenames(title="选择电子书（可多选）", filetypes=[("EPUB 电子书", "*.epub *.EPUB"), ("所有文件", "*")]))

    def clear_files():
        table.delete(*table.get_children())
        files.clear()
        results.clear()
        status_var.set("列表已清空。")

    def choose_folder():
        chosen = filedialog.askdirectory(title="选择 TXT 保存文件夹")
        if chosen:
            output_var.set(chosen)

    add_button = ttk.Button(toolbar, text="＋ 添加电子书", command=choose_files)
    add_button.pack(side="left")
    clear_button = ttk.Button(toolbar, text="清空列表", command=clear_files)
    clear_button.pack(side="left", padx=8)
    destination = ttk.Frame(outer)
    destination.pack(fill="x", pady=(2, 12))
    ttk.Label(destination, text="保存位置").pack(side="left", padx=(0, 10))
    entry = ttk.Entry(destination, textvariable=output_var)
    entry.pack(side="left", fill="x", expand=True)
    browse = ttk.Button(destination, text="选择文件夹", command=choose_folder)
    browse.pack(side="left", padx=(8, 0))
    ttk.Label(outer, text="保存位置留空：放在原 EPUB 旁边。同名 TXT 自动编号，不会覆盖已有文件。").pack(anchor="w")
    progress = ttk.Progressbar(outer, mode="determinate")
    progress.pack(fill="x", pady=(16, 8))
    ttk.Label(outer, textvariable=status_var, wraplength=720).pack(anchor="w")
    actions = ttk.Frame(outer)
    actions.pack(fill="x", pady=(14, 0))

    def set_busy(value):
        nonlocal busy
        busy = value
        for widget in (add_button, clear_button, browse, entry, start_button, open_button):
            widget.configure(state="disabled" if value else "normal")

    def worker(items, folder):
        for item_id, source in items:
            events.put(("working", item_id, None))
            try:
                target = convert(source, folder)
                events.put(("success", item_id, target))
            except Exception as exc:
                events.put(("error", item_id, str(exc)))
        events.put(("done", None, None))

    failures = []
    completed = 0

    def start():
        nonlocal completed
        if not files:
            messagebox.showinfo("请先添加文件", "点击“添加电子书”，选择一个或多个 .epub 文件。")
            return
        raw = output_var.get().strip()
        folder = Path(raw).expanduser() if raw else None
        failures.clear()
        results.clear()
        completed = 0
        progress.configure(value=0, maximum=len(files))
        for item_id, path in files.items():
            table.item(item_id, values=(path.name, "等待转换"))
        set_busy(True)
        status_var.set("正在转换，请稍候…")
        threading.Thread(target=worker, args=(list(files.items()), folder), daemon=True).start()

    def poll():
        nonlocal completed
        try:
            while True:
                kind, item_id, payload = events.get_nowait()
                if kind == "done":
                    set_busy(False)
                    status_var.set(f"转换完成：成功 {len(results)} 本，失败 {len(failures)} 本。")
                    if failures:
                        messagebox.showwarning("部分文件未能转换", "\n\n".join(failures[:8]))
                else:
                    name = files[item_id].name
                    label = {"working": "正在转换…", "success": "✓ 转换成功", "error": "转换失败"}[kind]
                    table.item(item_id, values=(name, label))
                    if kind != "working":
                        completed += 1
                        progress.configure(value=completed)
                    if kind == "success":
                        results.append(payload)
                    elif kind == "error":
                        failures.append(f"{name}：{payload}")
        except queue.Empty:
            pass
        root.after(100, poll)

    def open_folder():
        import os
        if results:
            folder = results[-1].parent
        elif output_var.get().strip():
            folder = Path(output_var.get().strip()).expanduser()
        elif files:
            folder = next(iter(files.values())).parent
        else:
            messagebox.showinfo("尚未选择文件", "添加电子书或完成转换后，即可打开保存文件夹。")
            return
        if not folder.is_dir():
            messagebox.showerror("无法打开", "保存文件夹尚不存在。")
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(folder))
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(folder)])
        except OSError as exc:
            messagebox.showerror("无法打开", str(exc))

    def close():
        if busy:
            messagebox.showinfo("正在转换", "请等当前转换完成后再关闭窗口。")
        else:
            root.destroy()

    start_button = ttk.Button(actions, text="开始转换", command=start)
    start_button.pack(side="right")
    open_button = ttk.Button(actions, text="打开保存文件夹", command=open_folder)
    open_button.pack(side="left")
    root.protocol("WM_DELETE_WINDOW", close)
    if initial_files:
        add_files(initial_files)
    root.after(100, poll)
    root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(description="将 EPUB 按阅读顺序转换成 UTF-8 TXT")
    parser.add_argument("files", nargs="*", help="EPUB 文件路径")
    parser.add_argument("--cli", action="store_true", help="命令行模式；不打开窗口")
    parser.add_argument("-o", "--output", type=Path, help="TXT 输出文件夹（仅命令行模式）")
    args = parser.parse_args()
    if not args.cli:
        if args.output:
            parser.error("--output 需要与 --cli 一起使用")
        launch_gui(args.files)
        return 0
    if not args.files:
        parser.error("命令行模式需要提供至少一个 EPUB 文件")
    failed = False
    for filename in args.files:
        try:
            print(f"成功：{convert(Path(filename).expanduser(), args.output)}")
        except Exception as exc:
            failed = True
            print(f"失败：{filename}：{exc}", file=sys.stderr)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
