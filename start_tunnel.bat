@echo off
title Tourism ERP - Server + Cloudflare Tunnel
color 0A

echo.
echo  ==========================================
echo   Tourism ERP - Starting...
echo  ==========================================
echo.

cd /d "%~dp0"

REM تشغيل السيرفر في نافذة منفصلة
start "Tourism ERP Server" cmd /k "uvicorn main:app --host 127.0.0.1 --port 8000"

REM انتظر 3 ثواني عشان السيرفر يبدأ
timeout /t 3 /nobreak >nul

echo  [+] Server started on http://127.0.0.1:8000
echo.
echo  [+] Starting Cloudflare Tunnel...
echo  [+] Wait for your public URL below:
echo.

REM تشغيل Cloudflare Tunnel
cloudflared tunnel --url http://localhost:8000

pause
