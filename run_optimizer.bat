@echo off
setlocal
cd /d %~dp0

set "PYTHONPATH=%CD%"

if not exist "scripts\run_optimizer_interactive.py" (
    echo [ERROR] Could not find scripts\run_optimizer_interactive.py
    echo Please ensure you are running this from the project root.
    pause
    exit /b 1
)

echo ========================================================
echo             OPTIMIZER LAUNCHER
echo ========================================================

python -V >nul 2>&1
if %errorlevel%==0 (
    python scripts\run_optimizer_interactive.py
) else (
    rem Fallback to py launcher
    py -3 -V >nul 2>&1
    if %errorlevel%==0 (
        py -3 scripts\run_optimizer_interactive.py
    ) else (
        echo [ERROR] Python was not found on PATH. Install Python 3 and retry.
        pause
    )
)

endlocal