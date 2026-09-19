@echo off
chcp 65001 >nul
title [2] GOOGLE CHROME SESSION THAT - SEXY BACCARAT
color 0B
cd /d "%~dp0"
echo ===================================================
echo     DANG MO GOOGLE CHROME THAT (HEADLESS=0)
echo ===================================================
echo.
set HEADLESS=0
set USE_FIREFOX=0
set USE_REAL_CHROME=1
set ACCOUNT_INDEX=1

node servicePuppeteer\session.js
pause
