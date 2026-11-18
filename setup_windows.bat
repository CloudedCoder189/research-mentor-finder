@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3.11 or newer and enable "Add Python to PATH".
    pause
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    echo Creating the virtual environment...
    python -m venv venv
    if errorlevel 1 goto error
) else (
    echo Reusing the existing virtual environment...
)

echo Installing or confirming required packages...
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error

echo.
echo Setup complete. Run run_windows.bat to start the website.
pause
exit /b 0

:error
echo.
echo Setup failed. Copy the error shown above and send it in ChatGPT.
pause
exit /b 1
