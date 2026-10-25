@echo off
REM NES Auditor launcher - just double-click this file.
cd /d "%~dp0"
set "PYX="

REM --- find a Python that actually RUNS (the 'py' launcher can point at a missing install)
for %%C in ("python" "py -3" "python3" "py") do (
  if not defined PYX (
    %%~C -c "import sys" >nul 2>nul && set "PYX=%%~C"
  )
)
if not defined PYX (
  echo No working Python was found.
  echo Install Python 3.9 or newer from python.org ^(tick "Add Python to PATH"^), then run this again.
  echo Tip: in a Command Prompt, "python --version" should print a version.
  start "" https://www.python.org/downloads/windows/
  pause
  exit /b 1
)
for /f "delims=" %%V in ('%PYX% -c "import sys;print(sys.version.split()[0])"') do echo Using Python %%V  ^(%PYX%^)

REM --- tkinter ships with python.org's installer
%PYX% -c "import tkinter" >nul 2>nul
if errorlevel 1 (
  echo.
  echo tkinter is missing from this Python. Reinstall Python from python.org with the default options.
  pause
  exit /b 1
)

REM --- Pillow + numpy
%PYX% -c "import PIL, numpy" >nul 2>nul
if errorlevel 1 (
  echo First run: installing Pillow and numpy...
  %PYX% -m pip install --user -r requirements.txt
  %PYX% -c "import PIL, numpy" >nul 2>nul
  if errorlevel 1 (
    echo.
    echo Could not install Pillow/numpy. Try in a Command Prompt:  %PYX% -m pip install pillow numpy
    pause
    exit /b 1
  )
)

REM --- launch (no console window when pythonw is available)
if "%PYX%"=="python" ( start "" pythonw nes_auditor.py & exit /b 0 )
if "%PYX%"=="py -3" ( start "" pyw -3 nes_auditor.py & exit /b 0 )
%PYX% nes_auditor.py
if errorlevel 1 pause
