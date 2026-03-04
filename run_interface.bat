@echo off
setlocal
cd /d %~dp0

set "PYTHONPATH=%CD%"

if not exist "scripts\run_interface.py" (
    echo [ERROR] Could not find scripts\run_interface.py
    echo Please ensure you are running this from the project root.
    pause
    exit /b 1
)

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
        echo [ERROR] Python was not found on PATH. Install Python 3 and retry.
    )
)

endlocal
