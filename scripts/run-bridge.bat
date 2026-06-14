@echo off
SETLOCAL
cd /d "%~dp0.."

:: Load .env if present
if exist ".env" (
    for /f "tokens=*" %%a in (.env) do set %%a
)

:: Activate venv
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [WARN] Virtual environment not found. Run scripts\setup-windows.bat first.
)

echo [Zen Claude Bridge] Starting on http://127.0.0.1:4000
echo.
python -m uvicorn zen_claude_bridge.app:app --host 127.0.0.1 --port 4000
if errorlevel 1 (
    echo.
    echo [ERROR] Bridge failed to start. Common causes:
    echo   - Port 4000 already in use (close other processes)
    echo   - Dependencies not installed (run setup-windows.bat)
    echo   - Python environment issue
    pause
)
