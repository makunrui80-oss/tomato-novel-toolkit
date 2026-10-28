@echo off
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 toolkit.py
) else (
    python toolkit.py
)
if errorlevel 1 (
    echo Please install Python 3.10 or later with Tcl/Tk and add it to PATH.
    pause
)
