@echo off
setlocal
cd /d %~dp0

set "PYTHONPATH=%CD%"

rem Standardize raw charts into data\charts_cl
rem A log CSV will be written to outputs\standardize_log.csv (override with --log)

python -V >nul 2>&1
if %errorlevel%==0 (
  python scripts\standardize.py %*
) else (
  rem Fallback to py launcher
  py -3 -V >nul 2>&1
  if %errorlevel%==0 (
    py -3 scripts\standardize.py %*
  ) else (
    echo Python was not found on PATH. Install Python 3 and retry.
  )
)

endlocal
pause



