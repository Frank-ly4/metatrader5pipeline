@echo off
setlocal
cd /d %~dp0

echo ================================================
echo         INTERACTIVE BACKTESTER v4.2
echo ================================================
echo.
echo This tool allows you to:
echo  - Select a trial UID from optimization results
echo  - Choose charts to backtest (all or specific)
echo  - Configure trading parameters (fees, capital, etc.)
echo  - View formatted results with capital tracking
echo.

set "PYTHONPATH=%CD%"

rem Try python first
python -V >nul 2>&1
if %errorlevel%==0 (
  python scripts\run_backtest_interactive.py
) else (
  rem Fallback to py launcher
  py -3 -V >nul 2>&1
  if %errorlevel%==0 (
    py -3 scripts\run_backtest_interactive.py
  ) else (
    echo Python was not found on PATH. Install Python 3 and retry.
  )
)

echo.
echo ================================================
endlocal
pause


