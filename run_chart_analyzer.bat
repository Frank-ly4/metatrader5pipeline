@echo off
setlocal
cd /d %~dp0

echo ================================================
echo        CHART ANALYZER
echo ================================================
echo.
set "PYTHONPATH=%CD%"

python -V >nul 2>&1
if %errorlevel%==0 (
  python scripts\chart_analyzer.py %*
) else (
  py -3 -V >nul 2>&1
  if %errorlevel%==0 (
    py -3 scripts\chart_analyzer.py %*
  ) else (
    echo Python was not found on PATH. Install Python 3 and retry.
  )
)

echo.
echo ================================================
endlocal
pause


