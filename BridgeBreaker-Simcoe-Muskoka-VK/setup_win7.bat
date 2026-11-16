@echo off
setlocal
set "VENV_DIR=%LOCALAPPDATA%\BridgeBreaker-Simcoe-Muskoka-VK-venv"

py -3.8-64 -c "import struct,sys; sys.exit(0 if sys.version_info[:3] == (3,8,10) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
    echo Python 3.8.10 64-bit is required to create the virtual environment.
    echo Install it and make sure the Python Launcher can find it.
    pause
    exit /b 1
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating virtual environment at "%VENV_DIR%"...
    py -3.8-64 -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo Virtual environment creation failed.
        pause
        exit /b 1
    )
)

"%VENV_DIR%\Scripts\python.exe" -c "import struct,sys; sys.exit(0 if sys.version_info[:3] == (3,8,10) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
    echo The existing virtual environment is not Python 3.8.10 64-bit.
    echo Remove "%VENV_DIR%" and run this script again.
    pause
    exit /b 1
)

"%VENV_DIR%\Scripts\python.exe" -m pip install -r "%~dp0requirements-win7.txt"
if errorlevel 1 (
    echo Dependency installation failed.
    pause
    exit /b 1
)

echo Virtual environment dependencies installed successfully.
pause
