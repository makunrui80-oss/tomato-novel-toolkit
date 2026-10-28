@echo off
setlocal
cd /d "%~dp0"
py -3 -m venv .build-venv
if errorlevel 1 goto fail
".build-venv\Scripts\python.exe" -m pip install --upgrade pip pyinstaller
if errorlevel 1 goto fail
".build-venv\Scripts\pyinstaller.exe" --noconfirm --clean --onefile --windowed --name TomatoNovelToolkit toolkit.py
if errorlevel 1 goto fail
echo Done: dist\TomatoNovelToolkit.exe
exit /b 0
:fail
echo Build failed. Install Python 3.10 or later with Tcl/Tk.
exit /b 1
