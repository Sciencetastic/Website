@echo off
REM Starts the Kimi planner, which delegates to the coder / auditor / designer profiles.
REM Hermes uses the current folder as its working directory, so we start in the project root.
cd /d "%~dp0.."

call hermes --version >nul 2>nul
if errorlevel 1 (
  echo Could not run "hermes" from this Command Prompt. Install Hermes Agent or fix PATH, then run this again.
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
