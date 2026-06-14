@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

:: Resolve paths relative to script location
cd /d "%~dp0.."

set AUTH_HEADER=X-API-Key: sk-local-zen
set BASE_URL=http://127.0.0.1:4000

echo ============================================
echo  Zen Claude Bridge — Smoke Tests
echo ============================================
echo.

:: Test 1: Root endpoint
echo [Test 1] GET /
curl -s "%BASE_URL%/" -H "Authorization: Bearer sk-local-zen" 2>nul
if errorlevel 1 (
    echo [FAIL] Cannot reach bridge at %BASE_URL%
    echo        Make sure run-bridge.bat is running.
    goto :eof
)
echo.
echo.

:: Test 2: Models endpoint
echo [Test 2] GET /v1/models
curl -s "%BASE_URL%/v1/models" -H "Authorization: Bearer sk-local-zen" 2>nul
echo.
echo.

:: Test 3: Count tokens (no upstream needed)
echo [Test 3] POST /v1/messages/count_tokens
curl -s -X POST "%BASE_URL%/v1/messages/count_tokens" ^
  -H "Authorization: Bearer sk-local-zen" ^
  -H "Content-Type: application/json" ^
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}" 2>nul
echo.
echo.

:: Test 4: Short generation (requires upstream proxy on port 9000)
echo [Test 4] POST /v1/messages (non-streaming)
echo         (Requires deepseek-cursor-proxy on port 9000)
curl -s -X POST "%BASE_URL%/v1/messages" ^
  -H "Authorization: Bearer sk-local-zen" ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"claude-sonnet-4-6\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply exactly: HELLO_FROM_BRIDGE\"}],\"max_tokens\":50}" 2>nul
echo.
echo.

echo ============================================
echo  Tests complete.
echo ============================================
echo.
echo  If Test 4 failed but 1-3 passed, the bridge
echo  is working — deepseek-cursor-proxy may not
echo  be running on port 9000, or your API key
echo  in .env is not configured.
echo.
pause
