@echo off
REM Starts the Kimi planner, which delegates to the coder / auditor / designer profiles.
REM Hermes uses the current folder as its working directory, so we start in the project root.
cd /d "%~dp0.."

where hermes >nul 2>nul
if errorlevel 1 (
  echo Hermes was not found on PATH.
  pause
  exit /b 1
)

hermes profile show planner >nul 2>nul
if errorlevel 1 (
  echo The planner profile does not exist yet. Run hermes\setup_hermes_team.bat first.
  pause
  exit /b 1
)

echo Project: %CD%
echo Starting Hermes team ^(planner = Kimi^)...
hermes -p planner chat %*
if errorlevel 1 pause
