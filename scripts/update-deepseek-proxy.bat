@echo off
setlocal EnableExtensions

cd /d "%~dp0.."
set "ROOT=%CD%"
set "PROXY_DIR=%ROOT%\.external\deepseek-cursor-proxy"

echo ============================================
echo  Update deepseek-cursor-proxy
echo ============================================
echo.

set "PROXY_VALID=1"
if not exist "%PROXY_DIR%\" set "PROXY_VALID=0"
if not exist "%PROXY_DIR%\.git\" set "PROXY_VALID=0"
if not exist "%PROXY_DIR%\pyproject.toml" set "PROXY_VALID=0"
if not exist "%PROXY_DIR%\src\" set "PROXY_VALID=0"

if not exist "%PROXY_DIR%\" (
    echo  deepseek-cursor-proxy is not installed.
    echo  Cloning from yxlao/deepseek-cursor-proxy...
    echo.
    if not exist "%ROOT%\.external\" mkdir "%ROOT%\.external"
    git clone https://github.com/yxlao/deepseek-cursor-proxy.git "%PROXY_DIR%"
    if errorlevel 1 (
        echo [ERROR] Git clone failed.
        pause
        exit /b 1
    )
    echo.
    echo  Cloned successfully.
) else (
    if "%PROXY_VALID%"=="1" (
        echo  Updating deepseek-cursor-proxy...
        echo.
        pushd "%PROXY_DIR%" || exit /b 1
        git pull --ff-only
        if errorlevel 1 (
            popd
            echo.
            echo [WARN] Git pull failed. This may mean:
            echo   - You have local changes (commit or stash them first)
            echo   - Network is unavailable
            echo.
            pause
            exit /b 1
        )
        popd
        echo.
        echo  Updated successfully.
    ) else (
        echo  deepseek-cursor-proxy folder exists but is incomplete.
        echo  Checks:
        if exist "%PROXY_DIR%\" (echo    Exists dir:          YES) else (echo    Exists dir:          NO)
        if exist "%PROXY_DIR%\.git\" (echo    Exists .git:         YES) else (echo    Exists .git:         NO)
        if exist "%PROXY_DIR%\pyproject.toml" (echo    Exists pyproject.toml: YES) else (echo    Exists pyproject.toml: NO)
        if exist "%PROXY_DIR%\src\" (echo    Exists src:           YES) else (echo    Exists src:           NO)
        echo.
        echo  Repair with one of these commands:
        echo.
        echo    CMD: rmdir /s /q "%PROXY_DIR%"
        echo    PowerShell: Remove-Item "%PROXY_DIR%" -Recurse -Force
        echo.
        echo  Then run: scripts\setup-windows.bat
        pause
        exit /b 1
    )
)

echo.
for /f "tokens=*" %%h in ('git -C "%PROXY_DIR%" rev-parse --short HEAD') do set "CURR_HASH=%%h"
echo  Current commit: %CURR_HASH%
echo.
echo  deepseek-cursor-proxy is maintained by yxlao:
echo  https://github.com/yxlao/deepseek-cursor-proxy
echo.
pause
