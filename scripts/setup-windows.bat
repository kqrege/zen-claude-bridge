@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

:: Change to repo root (works from scripts\ or repo root)
cd /d "%~dp0.."
set "ROOT=%CD%"

echo ============================================
echo  Zen Claude Bridge — Windows Setup
echo ============================================
echo.
echo  Root: %ROOT%
echo.

:: -------------------------------------------------------
:: 1. Check Python
:: -------------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not in PATH. Please install Python 3.10+ from:
    echo         https://www.python.org/downloads/
    echo.
    echo         Make sure "Add Python to PATH" is checked during installation.
    pause
    exit /b 1
)

:: -------------------------------------------------------
:: 2. Python virtual environment
:: -------------------------------------------------------
if not exist ".venv\" (
    echo [1/6] Creating Python virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/6] Virtual environment already exists.
)

call .venv\Scripts\activate.bat

:: -------------------------------------------------------
:: 3. Install Python dependencies
:: -------------------------------------------------------
echo [2/6] Installing Python dependencies...
python -m pip install -U pip >nul 2>&1
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)
pip install -e . >nul 2>&1

:: -------------------------------------------------------
:: 4. Check uv (required by deepseek-cursor-proxy)
:: -------------------------------------------------------
echo [3/6] Checking uv...
uv --version >nul 2>&1
if errorlevel 1 (
    echo         uv not found — attempting to install via pip...
    python -m pip install uv >nul 2>&1
    if errorlevel 1 (
        echo.
        echo [ERROR] Could not install uv automatically.
        echo.
        echo  deepseek-cursor-proxy requires uv to run.
        echo  Please install it manually:
        echo.
        echo    powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
        echo.
        echo  Or from: https://docs.astral.sh/uv/
        echo.
        pause
        exit /b 1
    )
    echo         Installed uv via pip.
)
for /f "tokens=*" %%i in ('uv --version') do set "UV_VER=%%i"
echo         Found: %UV_VER%

:: -------------------------------------------------------
:: 5. Clone / update deepseek-cursor-proxy into .external/
:: -------------------------------------------------------
echo [4/6] Setting up deepseek-cursor-proxy...
if not exist ".external\" mkdir ".external"

if not exist ".external\deepseek-cursor-proxy\" (
    echo         Cloning yxlao/deepseek-cursor-proxy into .external\...
    git clone https://github.com/yxlao/deepseek-cursor-proxy.git ".external\deepseek-cursor-proxy"
    if errorlevel 1 (
        echo [ERROR] Git clone failed. Check your internet connection.
        pause
        exit /b 1
    )
    echo         Cloned successfully.
) else (
    echo         deepseek-cursor-proxy already exists in .external\.
    echo         To update it later, run: scripts\update-deepseek-proxy.bat
)

:: -------------------------------------------------------
:: 6. Create .env from .env.example if missing
:: -------------------------------------------------------
echo [5/6] Checking .env...
if not exist ".env" (
    copy .env.example .env >nul
    echo         Created .env from .env.example.
) else (
    echo         .env already exists — keeping your settings.
)

echo.
echo ============================================
echo  Setup complete!
echo ============================================
echo.
echo  Next steps:
echo.
echo    1. Edit .env and set your API key:
echo         notepad .env
echo.
echo       Change:  OPENCODE_ZEN_API_KEY=replace_me
echo       To:      OPENCODE_ZEN_API_KEY=your_actual_key
echo.
echo    2. Start everything:
echo         scripts\run-all.bat
echo.
echo    3. Configure Claude Gateway:
echo         URL:      http://127.0.0.1:4000
echo         API key:  sk-local-zen
echo         Auth:     Bearer
echo.
echo  Individual scripts:
echo     scripts\run-deepseek-proxy.bat    (proxy on port 9000)
echo     scripts\run-bridge.bat            (bridge on port 4000)
echo     scripts\update-deepseek-proxy.bat (update deepseek-cursor-proxy)
echo     scripts\test-bridge.bat           (smoke tests)
echo.
pause
