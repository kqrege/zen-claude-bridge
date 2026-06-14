@echo off
setlocal EnableExtensions

cd /d "%~dp0.."
set "ROOT=%CD%"

echo ============================================
echo  Zen Claude Bridge - Start All Services
echo ============================================
echo.

set "VALID=1"

if not exist "%ROOT%\.env" (
    echo [ERROR] .env file not found at:
    echo         %ROOT%\.env
    echo         Run scripts\setup-windows.bat first.
    set "VALID=0"
)

if not exist "%ROOT%\.venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at:
    echo         %ROOT%\.venv\Scripts\python.exe
    echo         Run scripts\setup-windows.bat first.
    set "VALID=0"
)

set "PROXY_DIR=%ROOT%\.external\deepseek-cursor-proxy"

if not exist "%PROXY_DIR%\" (
    echo [ERROR] deepseek-cursor-proxy directory not found.
    echo         Run scripts\setup-windows.bat first.
    set "VALID=0"
)

if not exist "%PROXY_DIR%\.git\" (
    echo [ERROR] deepseek-cursor-proxy clone is incomplete - missing .git.
    echo         Run scripts\setup-windows.bat first.
    set "VALID=0"
)

if not exist "%PROXY_DIR%\pyproject.toml" (
    echo [ERROR] deepseek-cursor-proxy clone is incomplete - missing pyproject.toml.
    echo         Run scripts\setup-windows.bat first.
    set "VALID=0"
)

if not exist "%PROXY_DIR%\src\" (
    echo [ERROR] deepseek-cursor-proxy clone is incomplete - missing src.
    echo         Run scripts\setup-windows.bat first.
    set "VALID=0"
)

if "%VALID%"=="0" (
    echo.
    echo  For detailed diagnostics, run: scripts\diagnose-windows.bat
    echo.
    pause
    exit /b 1
)

set "GATEWAY_KEY=sk-local-zen"
if exist "%ROOT%\.env" (
    for /f "tokens=1,2 delims==" %%a in (%ROOT%\.env) do (
        if /i "%%a"=="CLAUDE_GATEWAY_KEY" set "GATEWAY_KEY=%%b"
    )
)

echo  zen-claude-bridge is starting...
echo.
echo [1/2] Starting DeepSeek proxy on http://127.0.0.1:9000
start "DeepSeek Proxy" cmd /k call "%ROOT%\scripts\run-deepseek-proxy.bat"

timeout /t 3 /nobreak >nul

echo [2/2] Starting Claude bridge on http://127.0.0.1:4000
start "Zen Claude Bridge" cmd /k call "%ROOT%\scripts\run-bridge.bat"

echo.
echo ============================================
echo  Claude Gateway settings:
echo ============================================
echo.
echo    URL:      http://127.0.0.1:4000
echo    API key:  %GATEWAY_KEY%
echo    Auth:     Bearer
echo.
echo ============================================
echo.
echo  Quick test prompt:
echo    "Reply exactly: OK_PROXY_WORKS"
echo.
echo  To stop: close each window or press Ctrl+C.
echo.
pause
