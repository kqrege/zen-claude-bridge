@echo off
SETLOCAL

:: Location of deepseek-cursor-proxy (adjust if needed)
if not defined DEEPSEEK_CURSOR_PROXY_DIR (
    set DEEPSEEK_CURSOR_PROXY_DIR=%USERPROFILE%\deepseek-cursor-proxy
)

:: Check if the proxy directory exists
if not exist "%DEEPSEEK_CURSOR_PROXY_DIR%" (
    echo.
    echo [ERROR] deepseek-cursor-proxy not found at:
    echo         %DEEPSEEK_CURSOR_PROXY_DIR%
    echo.
    echo   To install it:
    echo     git clone https://github.com/mylxsw/deepseek-cursor-proxy.git
    echo     cd deepseek-cursor-proxy
    echo     uv sync
    echo.
    echo   Then set DEEPSEEK_CURSOR_PROXY_DIR to the cloned path, or
    echo   edit this script to point to the correct directory.
    echo.
    pause
    exit /b 1
)

:: Check for uv
uv --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] uv is not installed. Install it from https://docs.astral.sh/uv/
    pause
    exit /b 1
)

echo [DeepSeek Proxy] Starting on http://127.0.0.1:9000
echo [DeepSeek Proxy] Using directory: %DEEPSEEK_CURSOR_PROXY_DIR%
echo.
cd /d "%DEEPSEEK_CURSOR_PROXY_DIR%"
uv run deepseek-cursor-proxy --no-ngrok --port 9000 --no-display-reasoning
if errorlevel 1 (
    echo.
    echo [ERROR] Proxy failed to start. Check the error above.
    pause
)
