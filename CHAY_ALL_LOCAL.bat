@echo off
chcp 65001 >nul
title KHOI DONG TOAN BO BOT KEO BCR (LOCAL WINDOWS)
color 0F
cd /d "%~dp0"
echo ===================================================
echo     DANG BAT TOAN BO HE THONG TREN WINDOWS LOCAL
echo ===================================================
echo.
echo [1/2] Dang khoi dong Server...
start "" "1_CHAY_SERVER.bat"
timeout /t 3 /nobreak >nul

echo [2/2] Dang mo Google Chrome Python Controller (60 FPS Native)...
start "" "2_CHAY_PYTHON_SESSION.bat"

echo.
echo ===================================================
echo   DA KHOI DONG THANH CONG CAC CUA SO!
echo   - Cua so 1: Server Backend
echo   - Cua so 2: Google Chrome That (Dang vao ban)
echo ===================================================
timeout /t 5
