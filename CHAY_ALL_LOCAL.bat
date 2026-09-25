@echo off
chcp 65001 >nul
title KHOI DONG LOCAL — server + vision + forward
color 0F
cd /d "%~dp0"
echo ===================================================
echo   LOCAL: server + vision Chrome + forward 3 mode
echo ===================================================
echo.
echo [1/3] Server + panel...
start "" "1_CHAY_SERVER.bat"
timeout /t 3 /nobreak >nul

echo [2/3] Vision (Chrome GUI)...
start "" "CHAY_BOT_VISION_AUTO.bat"
timeout /t 2 /nobreak >nul

echo [3/3] Forward Tele...
start "" "3_CHAY_FORWARD_BOT.bat"

echo.
echo   - Server: 1_CHAY_SERVER
echo   - Vision: CHAY_BOT_VISION_AUTO
echo   - Forward: 3_CHAY_FORWARD_BOT
echo ===================================================
timeout /t 4
