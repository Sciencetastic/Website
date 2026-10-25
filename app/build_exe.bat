@echo off
REM Builds standalone Windows .exe files (no Python needed on the target PC).
REM Run this once on a Windows machine that has Python installed.
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name NES_Colorizer nes_colorizer.py
python -m PyInstaller --noconfirm --onefile --windowed --name NES_Auditor nes_auditor.py
echo.
echo Done. The programs are in the "dist" folder: NES_Colorizer.exe and NES_Auditor.exe
pause
