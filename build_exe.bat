@echo off
cd /d "%~dp0"
pip install pyinstaller
pyinstaller --onefile --windowed --name CleanExit --icon ssak.ico --add-data "ssak.ico;." main.py
echo.
echo Done: dist\CleanExit.exe
pause
