@echo off
SETLOCAL
cd /d "%~dp0.."

echo ============================================
echo  Zen Claude Bridge — Start All Services
echo ============================================
echo.
echo  This will open two terminal windows:
echo    Window 1: deepseek-cursor-proxy (port 9000)
echo    Window 2: zen-claude-bridge    (port 4000)
echo.
echo  Close both windows with Ctrl+C when done.
echo.

:: Start proxy in a new window
echo [1/2] Starting deepseek-cursor-proxy on port 9000...
start "DeepSeek Proxy" cmd /c "scripts\run-deepseek-proxy.bat"

:: Give the proxy a moment to initialize
timeout /t 3 /nobreak >nul

:: Start bridge in a new window
echo [2/2] Starting zen-claude-bridge on port 4000...
start "Zen Claude Bridge" cmd /c "scripts\run-bridge.bat"

echo.
echo  Both services started in separate windows.
echo  Configure Claude Gateway to use:
echo    URL:  http://127.0.0.1:4000
echo    Key:  sk-local-zen
echo.
echo  To stop: close each window or press Ctrl+C in each.
echo.
pause
