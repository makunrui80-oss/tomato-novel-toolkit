@echo off
cd /d "%~dp0"
TomatoNovelToolkit.exe
if errorlevel 1 pause
