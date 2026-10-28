# Tomato Novel Toolkit

一个面向 Windows、macOS 和 Linux 的整合工具：

- **番茄小说下载器**：启动官方 [Tomato Novel Downloader](https://github.com/zhongbai2333/Tomato-Novel-Downloader) Web UI，用浏览器搜索和下载小说。
- **EPUB 转 TXT**：把 EPUB 按章节阅读顺序批量导出为 UTF-8 TXT，保留书名、作者和基本段落。

## 最快使用

先安装 Python 3.10 或更新版本（需要 Tkinter），然后：

### macOS

双击 `启动整合工具.command`。首次点击“启动番茄小说下载器”时，程序会从官方 Releases 下载当前 Mac 架构的下载器；数据保存在项目目录的 `data/`。

### Windows

双击 `启动整合工具.bat`。如果希望生成无需 Python 的 EXE，在 Windows 上双击 `build_windows.bat`，生成的文件位于 `dist/TomatoNovelToolkit.exe`。

### Linux

```bash
python3 toolkit.py
```

Linux 需要安装 Tkinter，例如 Debian/Ubuntu：`sudo apt install python3-tk`。

## 命令行

EPUB 批量转换：

```bash
python3 toolkit.py --cli "第一本.epub" "第二本.epub"
python3 epub_to_txt.py --cli "小说.epub" -o "导出目录"
```

只启动下载器 Web UI：

```bash
python3 toolkit.py --server
```

默认地址是 <http://127.0.0.1:18423/>。如需密码锁定 Web UI，可以先设置环境变量 `TOMATO_WEB_PASSWORD`。

## 打包与 GitHub Actions

本项目不依赖第三方 Python 包。`build_windows.bat` 和 `build_unix.sh` 会临时安装 PyInstaller；GitHub Actions 在 Windows、macOS、Linux 三个平台分别构建桌面包。构建后的包第一次启动下载器时会按系统和 CPU 架构获取官方发行版。

## 支持与限制

- EPUB 转换器支持 EPUB 2/3、批量转换、GB18030 等常见编码；不会覆盖已有 TXT，会自动使用 `_2`、`_3` 编号。
- 扫描图片书需要另行 OCR；受 DRM 保护的正文不会被解密。
- 下载器使用上游项目提供的网络接口和功能，首次下载需要网络；下载器的配置和日志在 `data/`。
- 当前固定使用官方 Tomato Novel Downloader `v2.4.16`，需要升级时修改 `scripts/get_downloader.py` 的版本常量。

## 许可

本仓库自己的代码采用 MIT License。下载器的版权、许可和来源见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。请遵守当地法律、上游服务条款和版权要求，仅下载你有权保存的内容。
