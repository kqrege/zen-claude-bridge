@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

cd /d "%~dp0.."
set "ROOT=%CD%"

echo ============================================
echo  Zen Claude Bridge — Start All Services
echo ============================================
echo.

:: Pre-flight checks
if not exist ".env" (
    echo [ERROR] .env file not found.
    echo         Run scripts\setup-windows.bat first.
    pause
    exit /b 1
)

if not exist ".external\deepseek-cursor-proxy\" (
    echo [ERROR] deepseek-cursor-proxy is not installed.
    echo         Run scripts\setup-windows.bat first.
    pause
    exit /b 1
)

if not exist ".venv\" (
    echo [ERROR] Virtual environment not found.
    echo         Run scripts\setup-windows.bat first.
    pause
    exit /b 1
)

:: Read key from .env for display
set "GATEWAY_KEY=sk-local-zen"
for /f "tokens=1,2 delims==" %%a in (.env) do (
    if /i "%%a"=="CLAUDE_GATEWAY_KEY" set "GATEWAY_KEY=%%b"
)

echo  zen-claude-bridge is starting...
echo.
echo [1/2] Starting DeepSeek proxy on http://127.0.0.1:9000
start "DeepSeek Proxy" cmd /c "scripts\run-deepseek-proxy.bat"

:: Give the proxy a moment to initialize
timeout /t 3 /nobreak >nul

echo [2/2] Starting Claude bridge on http://127.0.0.1:4000
start "Zen Claude Bridge" cmd /c "scripts\run-bridge.bat"

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
