#!/bin/zsh
cd "$(dirname "$0")" || exit 1
python3 toolkit.py
if [ $? -ne 0 ]; then
  echo "启动失败。请安装包含 Tkinter 的 Python 3.10 或更新版本。"
  read "?按回车关闭…"
fi
