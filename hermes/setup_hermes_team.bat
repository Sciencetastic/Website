@echo off
REM Creates the four Hermes profiles (planner, coder, auditor, designer), points each at its
REM OpenRouter model, installs each role prompt as that profile's SOUL.md, and turns on the
REM advanced-delegation plugin (profile_routes) in the planner. Safe to re-run.
setlocal
cd /d "%~dp0"

REM ---- EDIT THESE: OpenRouter model IDs (check exact slugs at https://openrouter.ai/models) ----
set "M_PLANNER=moonshotai/kimi-k3"
set "M_CODER=qwen/qwen3.8-flash"
set "M_AUDITOR=z-ai/glm-5.3-flash"
set "M_DESIGNER=google/gemini-3.7-flash"
REM ------------------------------------------------------------------------------------------

where hermes >nul 2>nul
if errorlevel 1 (
  echo Hermes was not found on PATH. Install Hermes Agent first, then run this again.
  pause
  exit /b 1
)

set "HHOME=%USERPROFILE%\.hermes"
if defined HERMES_HOME set "HHOME=%HERMES_HOME%"

echo.
echo Paste your OpenRouter API key to store it in every profile ^(it will be visible as you type^).
echo Leave blank to skip if the profiles already have it.
set "ORKEY="
set /p "ORKEY=OpenRouter key: "

call :mkprofile planner  "%M_PLANNER%"
call :mkprofile coder    "%M_CODER%"
call :mkprofile auditor  "%M_AUDITOR%"
call :mkprofile designer "%M_DESIGNER%"

echo.
echo Enabling delegation in the planner profile...
call hermes -p planner plugins install advanced-delegation
call hermes -p planner config set delegation.backend profile_routes
call hermes -p planner config set delegation.backends.profile_routes.profiles "[{name: coder, description: First-pass implementer and final verifier. Writes code and runs the gates and reports raw output}, {name: auditor, description: Reviews code and runs the gates. When a check fails it fixes the bug and reports exactly what changed}, {name: designer, description: Vision reviewer for screenshots and art. Never edits game logic}]"
call hermes -p planner config set delegation.backends.profile_routes.default coder

echo.
echo ---- Planner delegation settings ----
call hermes -p planner delegation config --show
echo.
echo Done. Start the team with launch_hermes_team.bat
pause
exit /b 0

:mkprofile
echo.
echo === Profile %~1  ^(%~2^) ===
call hermes profile create %~1 >nul 2>nul
call hermes -p %~1 config set model.provider openrouter
call hermes -p %~1 config set model.default %~2
if defined ORKEY call hermes -p %~1 config set OPENROUTER_API_KEY %ORKEY%
if not exist "%HHOME%\profiles\%~1" (
  echo WARNING: %HHOME%\profiles\%~1 not found - run "hermes profile show %~1" to see where it lives,
  echo          then copy roles\%~1.md there as SOUL.md by hand.
  exit /b 0
)
copy /y "roles\%~1.md" "%HHOME%\profiles\%~1\SOUL.md" >nul
exit /b 0
