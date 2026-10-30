@echo off
REM Pick which tool to open.
cd /d "%~dp0"
:menu
echo.
echo   NES Art Tools
echo   [1] NES Colorizer  (make art NES-compliant)
echo   [2] NES Auditor    (check art that is already built)
echo   [Q] Quit
choice /c 12Q /n /m "Choose: "
if errorlevel 3 exit /b
if errorlevel 2 call run_auditor.bat & goto menu
if errorlevel 1 call run_colorizer.bat & goto menu
