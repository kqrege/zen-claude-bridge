@echo off
SETLOCAL

cd /d "%~dp0.."

:: Load .env variables (simple key=value parsing)
if exist ".env" (
    for /f "tokens=*" %%a in (.env) do set %%a
)

:: Read bridge port from environment, default 4000
if "%BRIDGE_PORT%"=="" set "BRIDGE_PORT=4000"
if "%BRIDGE_HOST%"=="" set "BRIDGE_HOST=127.0.0.1"

:: Activate venv
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [WARN] Virtual environment not found. Run scripts\setup-windows.bat first.
    pause
    exit /b 1
)

echo [Zen Claude Bridge] Starting on http://%BRIDGE_HOST%:%BRIDGE_PORT%
echo.
python -m uvicorn zen_claude_bridge.app:app --host %BRIDGE_HOST% --port %BRIDGE_PORT%
if errorlevel 1 (
    echo.
    echo [ERROR] Bridge failed to start. Common causes:
    echo   - Port %BRIDGE_PORT% already in use (close other processes)
    echo   - Dependencies not installed (run scripts\setup-windows.bat)
    echo   - Python environment issue
    pause
)
