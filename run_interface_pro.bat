@echo off
setlocal
cd /d %~dp0

echo ================================================
echo     PROFESSIONAL QUANT TRADING INTERFACE
echo ================================================
echo.
echo Advanced Strategy Analysis & MQL5 Integration
echo  - Multi-metric strategy analysis
echo  - Robust strategy scanning
echo  - Parameter sensitivity analysis
echo  - MQL5 integration tools
echo  - Professional reporting
echo.

set "PYTHONPATH=%CD%"

rem Try python first
python -V >nul 2>&1
if %errorlevel%==0 (
  python scripts\run_interface_pro.py
) else (
  rem Fallback to py launcher
  py -3 -V >nul 2>&1
  if %errorlevel%==0 (
    py -3 scripts\run_interface_pro.py
  ) else (
    echo Python was not found on PATH. Install Python 3 and retry.
  )
)

echo.
echo ================================================
endlocal
pause
