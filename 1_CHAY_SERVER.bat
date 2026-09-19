@echo off
chcp 65001 >nul
title [1] SERVER BACKEND BCR (Port 3201)
color 0A
cd /d "%~dp0"
echo ===================================================
echo       DANG KHOI DONG SERVER BACKEND (PORT 3201)
echo ===================================================
echo.
node server.js
pause
