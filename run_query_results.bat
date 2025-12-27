@echo off
setlocal
cd /d %~dp0

REM Set Python path to current directory so imports work correctly
set "PYTHONPATH=%CD%"

echo ========================================
echo   INTERACTIVE RESULTS QUERY TOOL
echo ========================================
echo.
echo This tool allows you to:
echo   - Select a recent optimization run
echo   - Interactively filter the results
echo   - View the top N results sorted by any metric
echo.

rem Try python first, fallback to py
python -V >nul 2>&1
if %errorlevel%==0 (
  python scripts/query_results.py
) else (
  py -3 -V >nul 2>&1
  if %errorlevel%==0 (
    py -3 scripts/query_results.py
  ) else (
    echo Python was not found on PATH. Install Python 3 and retry.
  )
)

endlocal
pause
