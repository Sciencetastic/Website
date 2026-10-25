@echo off
REM NES Colorizer launcher - just double-click this file.
cd /d "%~dp0"
set "PYX="
where py >nul 2>nul && set "PYX=py -3"
if not defined PYX where python >nul 2>nul && set "PYX=python"
if not defined PYX (
  echo Python is not installed. Opening the download page...
  echo Install Python 3.9 or newer and tick "Add Python to PATH", then run this again.
  start "" https://www.python.org/downloads/windows/
  pause
  exit /b 1
)
%PYX% -c "import PIL, numpy, tkinter" >nul 2>nul
if errorlevel 1 (
  echo First run: installing Pillow and numpy...
  %PYX% -m pip install --user -r requirements.txt
  %PYX% -c "import tkinter" >nul 2>nul || (echo tkinter is missing - reinstall Python from python.org with the default options. & pause & exit /b 1)
)
REM pythonw runs without a console window; fall back to a visible one if it is not found
set "PYW=%PYX:python=pythonw%"
if "%PYX%"=="py -3" set "PYW=pyw -3"
start "" %PYW% nes_colorizer.py
if errorlevel 1 (%PYX% nes_colorizer.py & pause)
