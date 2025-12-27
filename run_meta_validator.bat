@echo off
setlocal
cd /d %~dp0
set "PYTHONPATH=%CD%"

python -V >nul 2>&1
if %errorlevel%==0 (
  python meta\validators\meta_validator.py
) else (
  py -3 -V >nul 2>&1
  if %errorlevel%==0 (
    py -3 meta\validators\meta_validator.py
  ) else (
    echo Python not found.
  )
)

endlocal


