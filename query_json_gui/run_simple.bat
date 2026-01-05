@echo off
REM Launcher for Query Results JSON Viewer (Simple Mode)
REM Double-click this file to start the application

echo ========================================
echo Query Results JSON Viewer - Simple Mode
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher
    pause
    exit /b 1
)

REM Check if required packages are installed
python -c "import PySide6" >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: PySide6 is not installed
    echo.
    echo Installing required packages...
    pip install PySide6 pandas
    if %errorlevel% neq 0 (
        echo.
        echo Failed to install dependencies
        pause
        exit /b 1
    )
)

python -c "import pandas" >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: pandas is not installed
    echo.
    echo Installing required packages...
    pip install pandas
    if %errorlevel% neq 0 (
        echo.
        echo Failed to install dependencies
        pause
        exit /b 1
    )
)

echo Starting application...
echo.

REM Launch the application
python opt_console_simple.py

REM Pause on error
if %errorlevel% neq 0 (
    echo.
    echo Application exited with error code %errorlevel%
    pause
)

