@echo off
cd /d "%~dp0"
py -3 -m venv .build-venv
if errorlevel 1 goto fail
".build-venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 goto fail
".build-venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name TomatoNovelToolkit toolkit.py
if errorlevel 1 goto fail
echo Done: dist\TomatoNovelToolkit.exe
pause
exit /b 0
:fail
echo Build failed. Install Python 3.10 or later and check the messages above.
pause
exit /b 1
