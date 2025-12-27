@echo off
setlocal
cd /d %~dp0

REM Use UTF-8 to avoid UnicodeEncodeError on emojis
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
set "PYTHONLEGACYWINDOWSSTDIO=utf-8"

REM Set Python path to current directory so imports work
set "PYTHONPATH=%CD%"

echo ========================================
echo   INTERACTIVE OPTIMIZER
echo ========================================
echo.
echo Advanced optimization with full control:
echo   ✓ Select specific charts or all charts
echo   ✓ Choose optimization method (random/grid/lhs/sobol)
echo   ✓ Configure trials per chart
echo   ✓ Set K-fold validation and embargo
echo   ✓ Select performance mode
echo   ✓ Choose optimization metric
echo   ✓ All CPU optimizations included
echo.
echo Starting interactive session...
echo.

REM Try python first, fallback to py
python -V >nul 2>&1
if %errorlevel%==0 (
  python scripts/run_optimizer_cli.py
) else (
  py -3 -V >nul 2>&1
  if %errorlevel%==0 (
    py -3 scripts/run_optimizer_cli.py
  ) else (
    echo Python was not found on PATH. Install Python 3 and retry.
  )
)

echo.
echo ========================================
echo   Session Complete!
echo ========================================
endlocal
pause
