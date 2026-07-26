@echo off
title Tourism ERP - Server + Cloudflare Tunnel
color 0A

cd /d "%~dp0"

echo.
echo  ==========================================
echo   Tourism ERP - Remote Access with Tunnel
echo  ==========================================
echo.

REM 1. التأكد من وجود cloudflared (تحميل تلقائي لو مش موجود)
echo  [1/4] Checking cloudflared.exe...
powershell -ExecutionPolicy Bypass -File "%~dp0ensure_cloudflared.ps1" > "%TEMP%\cf_check.tmp"
set /p cfStatus=<"%TEMP%\cf_check.tmp"
del "%TEMP%\cf_check.tmp" 2>nul

if "%cfStatus%"=="FAILED" (
    echo  ❌ Failed to download cloudflared.exe
    echo     Download manually from:
    echo     https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
    echo.
    pause
    exit /b 1
)
if "%cfStatus%"=="Downloading cloudflared.exe..." (
    echo  ⬇ Downloading cloudflared.exe (first time setup)...
    powershell -ExecutionPolicy Bypass -File "%~dp0ensure_cloudflared.ps1" > nul
    echo  ✅ Downloaded successfully
) else (
    echo  ✅ cloudflared.exe found
)

REM 2. إضافة cloudflared إلى PATH لو موجود محلياً
if exist "%~dp0cloudflared\cloudflared.exe" (
    set "PATH=%~dp0cloudflared;%PATH%"
)

REM 3. تشغيل السيرفر
echo  [2/4] Starting server...
start "Tourism ERP Server" cmd /k "uvicorn main:app --host 127.0.0.1 --port 8000"
timeout /t 3 /nobreak >nul
echo  ✅ Server running on http://127.0.0.1:8000

REM 4. تشغيل التونل
echo  [3/4] Starting Cloudflare Tunnel...
echo  [4/4] Copy the public URL below to access remotely:
echo.
echo  ════════════════════════════════════════════
echo.
cloudflared tunnel --url http://localhost:8000
echo.
pause
