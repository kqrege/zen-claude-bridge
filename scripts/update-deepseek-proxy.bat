@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

cd /d "%~dp0.."
set "PROXY_DIR=%CD%\.external\deepseek-cursor-proxy"

echo ============================================
echo  Update deepseek-cursor-proxy
echo ============================================
echo.

if not exist "%PROXY_DIR%" (
    echo  deepseek-cursor-proxy is not installed.
    echo  Cloning from yxlao/deepseek-cursor-proxy...
    echo.
    if not exist ".external\" mkdir ".external"
    git clone https://github.com/yxlao/deepseek-cursor-proxy.git "%PROXY_DIR%"
    if errorlevel 1 (
        echo [ERROR] Git clone failed.
        pause
        exit /b 1
    )
    echo.
    echo  Cloned successfully.
) else (
    echo  Updating deepseek-cursor-proxy...
    echo.
    cd /d "%PROXY_DIR%"
    git pull --ff-only
    if errorlevel 1 (
        echo.
        echo [WARN] Git pull failed. This may mean:
        echo   - You have local changes (commit or stash them first)
        echo   - Network is unavailable
        echo.
        pause
        exit /b 1
    )
    echo.
    echo  Updated successfully.
)

:: Print current commit hash
echo.
for /f "tokens=*" %%h in ('git -C "%PROXY_DIR%" rev-parse --short HEAD') do set "CURR_HASH=%%h"
echo  Current commit: %CURR_HASH%
echo.
echo  deepseek-cursor-proxy is maintained by yxlao:
echo  https://github.com/yxlao/deepseek-cursor-proxy
echo.
pause
