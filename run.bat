@echo off
setlocal enabledelayedexpansion
title Tourism ERP Server
cd /d "%~dp0"

REM ===== 1. التأكد من cloudflared =====
set "CF="
where cloudflared >nul 2>nul && set "CF=cloudflared"
if not defined CF (
    if exist "cloudflared\cloudflared.exe" (
        set "CF=%~dp0cloudflared\cloudflared.exe"
    ) else (
        echo [1/4] Downloading cloudflared.exe...
        if not exist "cloudflared" mkdir cloudflared
        powershell -Command "try{ Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared\cloudflared.exe' -UseBasicParsing; Write-Output 'ok' }catch{ Write-Output 'fail' }" > "%TEMP%\cf_dl.txt"
        set /p cf_dl=<"%TEMP%\cf_dl.txt"
        if "!cf_dl!"=="ok" (
            set "CF=%~dp0cloudflared\cloudflared.exe"
            echo        Done.
        ) else ( echo        Failed. )
        del "%TEMP%\cf_dl.txt" 2>nul
    )
)

REM ===== 2. تشغيل التونل في الخلفية =====
if defined CF (
    echo [2/4] Starting tunnel...
    start /b "" "!CF!" tunnel --url http://localhost:8000 > "%TEMP%\cf_tunnel.log" 2>&1
) else ( echo [2/4] Skipping tunnel )

REM ===== 3. استخراج اللينك + إرساله للموبايل =====
echo [3/4] Waiting for public URL...
set "PUBLIC_URL="
if defined CF (
    powershell -ExecutionPolicy Bypass -File "%~dp0tunnel_helper.ps1" -LogFile "%TEMP%\cf_tunnel.log" > "%TEMP%\cf_url.txt"
    set /p PUBLIC_URL=<"%TEMP%\cf_url.txt"
    del "%TEMP%\cf_url.txt" 2>nul
)

cls
echo.
echo  ╔═══════════════════════════════════════════╗
echo  ║       Tourism ERP — System Ready          ║
echo  ╚═══════════════════════════════════════════╝
echo.
echo   Local:   http://localhost:8000
if defined PUBLIC_URL (
    echo   Remote:  !PUBLIC_URL!
    echo.
    echo   ✅ Sent to your phone via ntfy.sh/mahmoud-erp-2026
)
echo.
echo   Close this window to stop everything.
echo.

REM ===== 4. تشغيل السيرفر =====
echo [4/4] Starting server...
python -m uvicorn main:app --host 0.0.0.0 --port 8000

echo.
echo Server stopped.
pause
