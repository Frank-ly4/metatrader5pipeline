@echo off
setlocal
cd /d %~dp0

set "PYTHONPATH=%CD%"

if not exist "scripts\standardize.py" (
    echo [ERROR] Could not find scripts\standardize.py
    echo Please ensure you are running this from the project root.
    pause
    exit /b 1
)

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
        echo [ERROR] Python was not found on PATH. Install Python 3 and retry.
    )
)

endlocal
