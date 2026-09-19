@echo off
chcp 65001 >nul
title [PLAYWRIGHT] RR88 - SOI ELEMENT RUT TIEN
color 0A
cd /d "%~dp0"
echo ===================================================
echo     DANG MO TRINH DUYET PLAYWRIGHT HEADED
echo ===================================================
echo.
node run_withdraw_playwright.js
pause
