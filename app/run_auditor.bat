@echo off
REM NES Auditor launcher (Windows). Needs Python 3.9+ from python.org (tkinter is included).
cd /d "%~dp0"
python -c "import PIL, numpy" 2>nul || (echo Installing Pillow and numpy... & python -m pip install -r requirements.txt)
python nes_auditor.py
if errorlevel 1 pause
