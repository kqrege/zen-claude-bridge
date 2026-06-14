@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

cd /d "%~dp0.."
set "ROOT=%CD%"

:: -------------------------------------------------------
:: Resolve proxy directory
:: -------------------------------------------------------
:: If DEEPSEEK_CURSOR_PROXY_DIR is set by the user, honour it.
:: Otherwise use the auto-managed copy in .external/.
if defined DEEPSEEK_CURSOR_PROXY_DIR (
    set "PROXY_DIR=%DEEPSEEK_CURSOR_PROXY_DIR%"
    set "PROXY_SOURCE=manual (%%DEEPSEEK_CURSOR_PROXY_DIR%%)"
) else (
    set "PROXY_DIR=%ROOT%\.external\deepseek-cursor-proxy"
    set "PROXY_SOURCE=auto-managed (.external\)"
)

if not exist "%PROXY_DIR%" (
    echo.
    echo [ERROR] deepseek-cursor-proxy not found.
    echo.
    echo   Source: %PROXY_SOURCE%
    echo   Path:   %PROXY_DIR%
    echo.
    if defined DEEPSEEK_CURSOR_PROXY_DIR (
        echo   The directory set in DEEPSEEK_CURSOR_PROXY_DIR does not exist.
        echo   Check that the path is correct.
    ) else (
        echo   Run scripts\setup-windows.bat first to clone it automatically.
    )
    echo.
    pause
    exit /b 1
)

:: -------------------------------------------------------
:: Check for uv
:: -------------------------------------------------------
uv --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] uv is not installed. Install it from https://docs.astral.sh/uv/
    pause
    exit /b 1
)

:: -------------------------------------------------------
:: Read proxy port from .env if available, default 9000
:: -------------------------------------------------------
set "PROXY_PORT=9000"
if exist "%ROOT%\.env" (
    for /f "tokens=1,2 delims==" %%a in (%ROOT%\.env) do (
        if /i "%%a"=="DEEPSEEK_PROXY_PORT" set "PROXY_PORT=%%b"
    )
)

echo [DeepSeek Proxy] Starting on http://127.0.0.1:%PROXY_PORT%
echo [DeepSeek Proxy] Source: %PROXY_SOURCE%
echo.
cd /d "%PROXY_DIR%"
uv run deepseek-cursor-proxy --no-ngrok --port %PROXY_PORT% --no-display-reasoning

if errorlevel 1 (
    echo.
    echo [ERROR] Proxy failed to start. Check the error above.
    pause
)
