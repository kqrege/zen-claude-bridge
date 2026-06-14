@echo off
setlocal EnableExtensions

cd /d "%~dp0.."
set "ROOT=%CD%"

set "PROXY_DIR="
set "PROXY_SOURCE="

if defined DEEPSEEK_CURSOR_PROXY_DIR (
    if not "%DEEPSEEK_CURSOR_PROXY_DIR%"=="" (
        set "PROXY_DIR=%DEEPSEEK_CURSOR_PROXY_DIR%"
        set "PROXY_SOURCE=DEEPSEEK_CURSOR_PROXY_DIR env var"
    )
)

if not defined PROXY_DIR (
    set "PROXY_DIR=%ROOT%\.external\deepseek-cursor-proxy"
    set "PROXY_SOURCE=managed .external"
)

set "VALID=1"

if not exist "%PROXY_DIR%\" set "VALID=0"
if not exist "%PROXY_DIR%\.git\" set "VALID=0"
if not exist "%PROXY_DIR%\pyproject.toml" set "VALID=0"
if not exist "%PROXY_DIR%\src\" set "VALID=0"

if "%VALID%"=="0" (
    echo.
    echo [ERROR] deepseek-cursor-proxy is missing or incomplete.
    echo.
    echo   Source:   %PROXY_SOURCE%
    echo   Path:     %PROXY_DIR%
    echo.
    echo   Checks:
    if exist "%PROXY_DIR%\" (echo     Exists dir:          YES) else (echo     Exists dir:          NO)
    if exist "%PROXY_DIR%\.git\" (echo     Exists .git:         YES) else (echo     Exists .git:         NO)
    if exist "%PROXY_DIR%\pyproject.toml" (echo     Exists pyproject.toml: YES) else (echo     Exists pyproject.toml: NO)
    if exist "%PROXY_DIR%\src\" (echo     Exists src:           YES) else (echo     Exists src:           NO)
    echo.
    echo   Root:     %ROOT%
    echo.
    if defined DEEPSEEK_CURSOR_PROXY_DIR (
        if not "%DEEPSEEK_CURSOR_PROXY_DIR%"=="" (
            echo   The directory set in DEEPSEEK_CURSOR_PROXY_DIR does not exist
            echo   or is incomplete. Check that the path is correct.
        )
    ) else (
        echo   The managed proxy clone is broken.
        echo   Repair with one of these commands:
        echo.
        echo     CMD: rmdir /s /q "%ROOT%\.external\deepseek-cursor-proxy"
        echo     PowerShell: Remove-Item "%ROOT%\.external\deepseek-cursor-proxy" -Recurse -Force
        echo.
        echo   Then re-run: scripts\setup-windows.bat
    )
    echo.
    pause
    exit /b 1
)

uv --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] uv is not installed. Install it from https://docs.astral.sh/uv/
    pause
    exit /b 1
)

set "PROXY_PORT=9000"
if exist "%ROOT%\.env" (
    for /f "tokens=1,2 delims==" %%a in (%ROOT%\.env) do (
        if /i "%%a"=="DEEPSEEK_PROXY_PORT" set "PROXY_PORT=%%b"
    )
)

echo [DeepSeek Proxy] Starting on http://127.0.0.1:%PROXY_PORT%
echo [DeepSeek Proxy] Source: %PROXY_SOURCE%
if defined DEEPSEEK_PROXY_DEBUG_REJECT (
    if "%DEEPSEEK_PROXY_DEBUG_REJECT%"=="1" (
        echo [DeepSeek Proxy] DEBUG REJECT MODE ENABLED
        echo [DeepSeek Proxy]   --missing-reasoning-strategy reject
        echo [DeepSeek Proxy]   --verbose --trace-dir .\trace-dumps
        echo [DeepSeek Proxy] WARNING: Traces may contain prompts, code, or secrets.
    )
)
echo.

pushd "%PROXY_DIR%" || (
    echo [ERROR] Could not change to proxy directory.
    pause
    exit /b 1
)

if defined DEEPSEEK_PROXY_DEBUG_REJECT (
    if "%DEEPSEEK_PROXY_DEBUG_REJECT%"=="1" (
        uv run deepseek-cursor-proxy --no-ngrok --port %PROXY_PORT% --no-display-reasoning --missing-reasoning-strategy reject --verbose --trace-dir .\trace-dumps
    ) else (
        uv run deepseek-cursor-proxy --no-ngrok --port %PROXY_PORT% --no-display-reasoning
    )
) else (
    uv run deepseek-cursor-proxy --no-ngrok --port %PROXY_PORT% --no-display-reasoning
)

popd

if errorlevel 1 (
    echo.
    echo [ERROR] Proxy failed to start. Check the error above.
    pause
)
