@echo off
setlocal
cd /d %~dp0

echo ================================================
echo      CODE GENERATOR v4.2 - PineScript & MQL5
echo ================================================
echo.
echo This tool generates trading code from optimized strategies:
echo  - PineScript for TradingView
echo  - MQL5 Expert Advisors for MetaTrader 5
echo  - Professional risk management included
echo  - Ready-to-use implementations
echo.

set "PYTHONPATH=%CD%"

python -V >nul 2>&1
if %errorlevel%==0 (
  python scripts\generate_pine.py --mode prompt
  goto :eof
) else (
  py -3 -V >nul 2>&1
  if %errorlevel%==0 (
    py -3 scripts\generate_pine.py --mode prompt
    goto :eof
  ) else (
    echo Python was not found on PATH. Install Python 3 and retry.
  )
)

echo.
echo ================================================
endlocal
pause


