@echo off
setlocal EnableExtensions

cd /d "%~dp0.."
set "ROOT=%CD%"

echo ============================================
echo  Zen Claude Bridge - Windows Diagnostics
echo ============================================
echo.

echo  ROOT: %ROOT%
echo.

echo  ---------- Environment ----------
echo  DEEPSEEK_CURSOR_PROXY_DIR=%DEEPSEEK_CURSOR_PROXY_DIR%
echo  DEEPSEEK_PROXY_PORT=%DEEPSEEK_PROXY_PORT%
echo  BRIDGE_PORT=%BRIDGE_PORT%
echo  DEEPSEEK_PROXY_DEBUG_REJECT=%DEEPSEEK_PROXY_DEBUG_REJECT%
echo.

echo  ---------- Project Files ----------
if exist "%ROOT%\.env" (echo  .env:                 YES) else (echo  .env:                 NO)
if exist "%ROOT%\.venv\Scripts\python.exe" (echo  .venv\Scripts\python.exe: YES) else (echo  .venv\Scripts\python.exe: NO)
if exist "%ROOT%\.venv\" (echo  .venv dir:           YES) else (echo  .venv dir:           NO)
echo.

echo  ---------- Managed Proxy (.external\deepseek-cursor-proxy) ----------
set "PROXY_DIR=%ROOT%\.external\deepseek-cursor-proxy"
echo  Proxy dir: %PROXY_DIR%
echo.

if exist "%PROXY_DIR%\" (echo  Exists dir:          YES) else (echo  Exists dir:          NO)
if exist "%PROXY_DIR%\.git\" (echo  Exists .git:         YES) else (echo  Exists .git:         NO)
if exist "%PROXY_DIR%\pyproject.toml" (echo  Exists pyproject.toml: YES) else (echo  Exists pyproject.toml: NO)
if exist "%PROXY_DIR%\src\" (echo  Exists src:           YES) else (echo  Exists src:           NO)
echo.

if exist "%PROXY_DIR%\.git\" (
    for /f "tokens=*" %%h in ('git -C "%PROXY_DIR%" rev-parse --short HEAD 2^>nul') do echo  Git commit: %%h
    for /f "tokens=*" %%r in ('git -C "%PROXY_DIR%" remote get-url origin 2^>nul') do echo  Remote:     %%r
) else (
    echo  Git info: N/A (not a git repository)
)
echo.

echo  ---------- Path Resolution Test ----------
echo  Simulating run-deepseek-proxy.bat logic:
echo.

set "TEST_DIR="
if defined DEEPSEEK_CURSOR_PROXY_DIR (
    if not "%DEEPSEEK_CURSOR_PROXY_DIR%"=="" (
        set "TEST_DIR=%DEEPSEEK_CURSOR_PROXY_DIR%"
        echo  Would use: DEEPSEEK_CURSOR_PROXY_DIR (custom path)
    )
)
if not defined TEST_DIR (
    set "TEST_DIR=%PROXY_DIR%"
    echo  Would use: managed .external path
)
echo  Resolved proxy dir: %TEST_DIR%
echo.

if exist "%TEST_DIR%\" (echo  Dir exists:         YES) else (echo  Dir exists:         NO)
if exist "%TEST_DIR%\.git\" (echo  .git exists:        YES) else (echo  .git exists:        NO)
if exist "%TEST_DIR%\pyproject.toml" (echo  pyproject.toml exists: YES) else (echo  pyproject.toml exists: NO)
if exist "%TEST_DIR%\src\" (echo  src exists:         YES) else (echo  src exists:         NO)
echo.

echo  ---------- PATH Check ----------
where python 2>nul || echo  python not found in PATH
where uv 2>nul || echo  uv not found in PATH
where git 2>nul || echo  git not found in PATH
where curl 2>nul || echo  curl not found in PATH
echo.

echo  ---------- Python ----------
python --version 2>nul || echo  python not available
echo.

echo  ---------- uv ----------
uv --version 2>nul || echo  uv not available
echo.

echo  ---------- Ports ----------
echo  Checking if port 4000 is in use:
netstat -ano 2>nul | findstr /c:"127.0.0.1:4000" >nul 2>&1 && (
    echo  Port 4000: IN USE
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr /c:"127.0.0.1:4000"') do (
        echo  PID: %%a
    )
) || (
    echo  Port 4000: FREE
)

echo  Checking if port 9000 is in use:
netstat -ano 2>nul | findstr /c:"127.0.0.1:9000" >nul 2>&1 && (
    echo  Port 9000: IN USE
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr /c:"127.0.0.1:9000"') do (
        echo  PID: %%a
    )
) || (
    echo  Port 9000: FREE
)
echo.

echo ============================================
echo  Diagnostics complete.
echo ============================================
echo.
echo  If the managed proxy is broken, repair:
echo.
echo    CMD: rmdir /s /q "%ROOT%\.external\deepseek-cursor-proxy"
echo    PowerShell: Remove-Item "%ROOT%\.external\deepseek-cursor-proxy" -Recurse -Force
echo.
echo  Then re-run: scripts\setup-windows.bat
echo.
pause
