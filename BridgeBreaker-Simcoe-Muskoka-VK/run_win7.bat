@echo off
setlocal
cd /d "%~dp0"
set "VENV_DIR=%LOCALAPPDATA%\BridgeBreaker-Simcoe-Muskoka-VK-venv"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo The virtual environment is missing. Run setup_win7.bat first.
    pause
    exit /b 1
)

"%VENV_DIR%\Scripts\python.exe" "%~dp0dataqlogapp_win7.py"
if errorlevel 1 (
    echo.
    echo The app exited with an error. Confirm its dependencies are installed with setup_win7.bat.
    pause
)
