@echo off
cd /d "%~dp0"
python main.py --user-data-dir "C:\CleanExitTest"
if errorlevel 1 pause
