@echo off
setlocal
cd /d %~dp0

set "PYTHONPATH=%CD%"

rem Try python first
python -V >nul 2>&1
if %errorlevel%==0 (
  python scripts\run_interface.py
) else (
  rem Fallback to py launcher
  py -3 -V >nul 2>&1
  if %errorlevel%==0 (
    py -3 scripts\run_interface.py
  ) else (
    echo Python was not found on PATH. Install Python 3 and retry.
  )
)

endlocal
pause


