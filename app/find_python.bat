@echo off
REM Sets PYX to a Python command that actually RUNS (the Windows 'py' launcher can point at a missing install).
set "PYX="
for %%C in ("python" "py -3" "python3" "py") do (
  if not defined PYX (
    %%~C -c "import sys" >nul 2>nul && set "PYX=%%~C"
  )
)
