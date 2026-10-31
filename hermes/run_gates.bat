@echo off
REM The objective pass/fail gate. Every role runs this and reports its RAW output.
REM A model saying "looks good" is not a pass; "GATES PASSED" from this script is.
REM Add or change checks in the GATES section for whatever the project needs.
setlocal
cd /d "%~dp0.."
call app\find_python.bat
if not defined PYX (
  echo GATES FAILED: no working Python found
  exit /b 2
)

set "FAILED=0"

REM ---------------- GATES ----------------
echo [gate] app core tests
%PYX% app\tests\test_core.py || set "FAILED=1"

echo [gate] app palette-edit tests
%PYX% app\tests\test_edit.py || set "FAILED=1"

echo [gate] app GUI tests
%PYX% app\tests\test_gui.py || set "FAILED=1"

echo [gate] MST toolkit tests
pushd mst
%PYX% -m unittest discover -s tests
if errorlevel 1 set "FAILED=1"
popd
REM -------------- END GATES --------------

echo.
if "%FAILED%"=="1" (
  echo GATES FAILED
  exit /b 1
)
echo GATES PASSED
exit /b 0
