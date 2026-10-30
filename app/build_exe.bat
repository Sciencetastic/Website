@echo off
REM Builds standalone Windows .exe files (no Python needed on the target PC).
cd /d "%~dp0"
call find_python.bat
if not defined PYX (
  echo No working Python was found. Install Python from python.org first.
  pause
  exit /b 1
)
echo Using %PYX%
%PYX% -m pip install --user -r requirements.txt pyinstaller
if errorlevel 1 ( echo pip failed. & pause & exit /b 1 )
%PYX% -m PyInstaller --noconfirm --onefile --windowed --name NES_Colorizer nes_colorizer.py
if errorlevel 1 ( echo Building NES_Colorizer failed. & pause & exit /b 1 )
%PYX% -m PyInstaller --noconfirm --onefile --windowed --name NES_Auditor nes_auditor.py
if errorlevel 1 ( echo Building NES_Auditor failed. & pause & exit /b 1 )
if not exist dist\NES_Colorizer.exe ( echo Build did not produce NES_Colorizer.exe & pause & exit /b 1 )
echo.
echo Done. The programs are in the "dist" folder: NES_Colorizer.exe and NES_Auditor.exe
pause
