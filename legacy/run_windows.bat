@echo off
setlocal
cd /d "%~dp0.."

if not exist "venv\Scripts\python.exe" (
    echo The virtual environment is missing. Run legacy\setup_windows.bat first.
    pause
    exit /b 1
)

start "" powershell -NoProfile -WindowStyle Hidden -Command "$url='http://localhost:8501'; for($i=0;$i -lt 30;$i++){ try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 $url | Out-Null; Start-Process $url; exit } catch { Start-Sleep -Seconds 1 } }; Start-Process $url"
"venv\Scripts\python.exe" -m streamlit run legacy/app.py

if errorlevel 1 (
    echo.
    echo The app stopped with an error. Copy the error and send it in ChatGPT.
    pause
)
