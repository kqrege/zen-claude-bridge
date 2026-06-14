@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

:: Resolve paths relative to script location (scripts\.. = repo root)
cd /d "%~dp0.."
set "ROOT=%CD%"

echo ============================================
echo  Zen Claude Bridge — Windows Setup
echo ============================================
echo.
echo  Root: %ROOT%
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not in PATH. Please install Python 3.10+ from python.org
    echo        and make sure "python" is available in your terminal.
    pause
    exit /b 1
)

:: Create virtual environment if missing
if not exist ".venv\" (
    echo [1/3] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/3] Virtual environment already exists.
)

:: Activate and install
echo [2/3] Installing requirements...
call .venv\Scripts\activate.bat
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

:: Create .env from example if missing
if not exist ".env" (
    echo [3/3] Creating .env from .env.example...
    copy .env.example .env >nul
    echo        Please edit .env and set your OPENCODE_ZEN_API_KEY.
) else (
    echo [3/3] .env already exists — skipping.
)

echo.
echo ============================================
echo  Setup complete!
echo ============================================
echo.
echo  Next steps:
echo    1. Edit .env and set OPENCODE_ZEN_API_KEY=your_key
echo    2. Run scripts\run-deepseek-proxy.bat   (in one terminal)
echo    3. Run scripts\run-bridge.bat           (in another terminal)
echo    4. Configure Claude Gateway to use http://127.0.0.1:4000
echo.
pause
