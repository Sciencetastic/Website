@echo off
REM NES Colorizer launcher - just double-click this file.
cd /d "%~dp0"
call find_python.bat
if not defined PYX (
  echo No working Python was found.
  echo Install Python 3.9 or newer from python.org ^(tick "Add Python to PATH"^), then run this again.
  start "" https://www.python.org/downloads/windows/
  pause
  exit /b 1
)
for /f "delims=" %%V in ('%PYX% -c "import sys;print(sys.version.split()[0])"') do echo Using Python %%V  ^(%PYX%^)

%PYX% -c "import tkinter" >nul 2>nul
if errorlevel 1 (
  echo.
  echo tkinter is missing from this Python. Reinstall Python from python.org with the default options.
  pause
  exit /b 1
)

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

REM launch without a console window when possible (errors are shown in a dialog and saved to nes_tools_error.log)
if "%PYX%"=="python" ( start "" pythonw nes_colorizer.py & exit /b 0 )
if "%PYX%"=="py -3" ( start "" pyw -3 nes_colorizer.py & exit /b 0 )
if "%PYX%"=="py" ( start "" pyw nes_colorizer.py & exit /b 0 )
%PYX% nes_colorizer.py
if errorlevel 1 pause
