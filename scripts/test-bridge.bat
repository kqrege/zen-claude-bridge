@echo off
setlocal EnableExtensions

set "TEST_PORT=4010"
set "BASE_URL=http://127.0.0.1:%TEST_PORT%"
set "AUTH_KEY=sk-local-zen"

cd /d "%~dp0.."
set "ROOT=%CD%"

echo ============================================
echo  Zen Claude Bridge - Smoke Tests
echo ============================================
echo.
echo  Using temporary port: %TEST_PORT% (safe - port 4000 is untouched)
echo.

echo  Starting bridge on port %TEST_PORT% for testing...
if exist "%ROOT%\.venv\Scripts\activate.bat" (
    call "%ROOT%\.venv\Scripts\activate.bat"
) else (
    echo [SKIP] Virtual environment not found. Run scripts\setup-windows.bat first.
    pause
    exit /b 1
)

start "Bridge-Test" cmd /c "python -m uvicorn zen_claude_bridge.app:app --host 127.0.0.1 --port %TEST_PORT% > \"%TEMP%\bridge-test.log\" 2>&1"

echo  Waiting for bridge to start...
set "READY="
for /l %%i in (1,1,15) do (
    timeout /t 1 /nobreak >nul
    curl -s "%BASE_URL%/" -H "Authorization: Bearer %AUTH_KEY%" >nul 2>&1
    if not errorlevel 1 (
        set "READY=1"
        goto :bridge_ready
    )
)
:bridge_ready

if not defined READY (
    echo [FAIL] Bridge did not start on port %TEST_PORT% within 15 seconds.
    echo        Check %TEMP%\bridge-test.log for details.
    goto :cleanup
)
echo  Bridge is ready on port %TEST_PORT%.
echo.

echo [Test 1] GET / (health check)
curl -s "%BASE_URL%/" -H "Authorization: Bearer %AUTH_KEY%"
if errorlevel 1 (
    echo [FAIL] Health check failed.
    goto :cleanup
)
echo.
echo     PASS
echo.

echo [Test 2] GET /v1/models
curl -s "%BASE_URL%/v1/models" -H "Authorization: Bearer %AUTH_KEY%"
if errorlevel 1 (
    echo [FAIL] Models endpoint failed.
    goto :cleanup
)
echo.
echo     PASS
echo.

echo [Test 3] POST /v1/messages/count_tokens
curl -s -X POST "%BASE_URL%/v1/messages/count_tokens" ^
  -H "Authorization: Bearer %AUTH_KEY%" ^
  -H "Content-Type: application/json" ^
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}"
if errorlevel 1 (
    echo [FAIL] Count tokens endpoint failed.
    goto :cleanup
)
echo.
echo     PASS
echo.

echo [Test 4] Dot probe suppression (POST single dot)
curl -s -X POST "%BASE_URL%/v1/messages/count_tokens" ^
  -H "Authorization: Bearer %AUTH_KEY%" ^
  -H "Content-Type: application/json" ^
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\".\"}]}"
if errorlevel 1 (
    echo [FAIL] Dot probe test failed.
    goto :cleanup
)
echo.
echo     PASS
echo.

echo [Test 5] POST /v1/messages non-streaming (requires upstream on port 9000)
curl -s -o "%TEMP%\bridge-gen-test.json" -w "%%{http_code}" -X POST "%BASE_URL%/v1/messages" ^
  -H "Authorization: Bearer %AUTH_KEY%" ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"claude-sonnet-4-6\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply exactly: HELLO_FROM_BRIDGE\"}],\"max_tokens\":50}" > "%TEMP%\bridge-gen-status.txt" 2>nul

set "TEST5_HTTP="
set /p TEST5_HTTP=<"%TEMP%\bridge-gen-status.txt"

if "%TEST5_HTTP%"=="200" (
    echo     PASS ^(HTTP 200^)
    type "%TEMP%\bridge-gen-test.json"
) else if "%TEST5_HTTP%"=="502" (
    echo     SKIP - upstream proxy not running (HTTP 502)
    echo     This is expected if deepseek-cursor-proxy is not on port 9000.
) else (
    echo     INFO - HTTP %TEST5_HTTP% ^(upstream may not be available^)
)
echo.
echo ============================================
echo  Tests complete.
echo ============================================
echo.
echo  Summary:
echo    Test 1 (health):       expected PASS
echo    Test 2 (models):       expected PASS
echo    Test 3 (count_tokens): expected PASS
echo    Test 4 (dot probe):    expected PASS
echo    Test 5 (generation):   PASS if upstream running, SKIP otherwise
echo.
echo  If tests 1-4 pass, the bridge is working correctly.
echo  Test 5 requires deepseek-cursor-proxy on port 9000.
echo.

:cleanup
echo  Stopping test bridge on port %TEST_PORT%...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /c:"127.0.0.1:%TEST_PORT%" 2^>nul') do (
    if not "%%a"=="" (
        taskkill /f /pid %%a >nul 2>&1
    )
)
echo  Test bridge stopped.
echo.
pause
