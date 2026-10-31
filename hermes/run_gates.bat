@echo off
REM The objective pass/fail gate. Every role runs this and reports its RAW output.
REM A model saying "looks good" is not a pass; "GATES PASSED" from this script is.
REM
REM Each gate below runs only if its test file exists. If NO gate runs, this script FAILS on purpose,
REM so an empty setup can never report a pass. Add or change gates for your project in the GATES section.
setlocal
cd /d "%~dp0.."

REM ---- find a Python that actually runs ----
set "PYX="
for %%C in ("python" "py -3" "python3" "py") do (
  if not defined PYX (
    %%~C -c "import sys" >nul 2>nul && set "PYX=%%~C"
  )
)
if not defined PYX (
  echo GATES FAILED: no working Python found
  exit /b 2
)

set "FAILED=0"
set "RAN=0"

REM ---------------- GATES ----------------
if exist app\tests\test_core.py (
  echo [gate] app core tests
  set /a RAN+=1
  %PYX% app\tests\test_core.py
  if errorlevel 1 set "FAILED=1"
)

if exist app\tests\test_edit.py (
  echo [gate] app palette-edit tests
  set /a RAN+=1
  %PYX% app\tests\test_edit.py
  if errorlevel 1 set "FAILED=1"
)

if exist app\tests\test_gui.py (
  echo [gate] app GUI tests
  set /a RAN+=1
  %PYX% app\tests\test_gui.py
  if errorlevel 1 set "FAILED=1"
)

if exist mst\tests (
  echo [gate] MST toolkit tests
  set /a RAN+=1
  pushd mst
  %PYX% -m unittest discover -s tests
  if errorlevel 1 set "FAILED=1"
  popd
)
REM -------------- END GATES --------------

echo.
if "%RAN%"=="0" (
  echo GATES FAILED: no gates are configured. Edit hermes\run_gates.bat and add your project's checks.
  exit /b 3
)
if "%FAILED%"=="1" (
  echo GATES FAILED
  exit /b 1
)
echo GATES PASSED ^(%RAN% gates^)
exit /b 0
