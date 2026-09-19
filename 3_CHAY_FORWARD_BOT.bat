@echo off
chcp 65001 >nul
title [3] BOT FORWARD TELEGRAM
color 0E
cd /d "%~dp0"
echo ===================================================
echo        DANG CHAY BOT FORWARD TELEGRAM
echo ===================================================
echo.
python bot_forward_runner.py
pause
