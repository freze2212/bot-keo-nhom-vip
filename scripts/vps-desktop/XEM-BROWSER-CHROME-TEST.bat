@echo off
chcp 65001 >nul
title XEM CHROME TEST - testsexy123456
color 0B
echo.
echo ============================================
echo   CHROME THAT tren RDP - testsexy123456
echo ============================================
echo Dang STOP BCR-session1 (service Firefox)...
"C:\tools\nssm\nssm-2.24\win64\nssm.exe" stop BCR-session1
timeout /t 3 /nobreak >nul
cd /d C:\apps\bot-keo-nhom-bcr-main
set HEADLESS=0
set USE_FIREFOX=0
set USE_REAL_CHROME=1
set ACCOUNT_INDEX=1
set USERNAME_ACCOUNT=testsexy123456
set PASSWORD_ACCOUNT=admin123
set PREFERRED_TABLE=C01
set PLAYWRIGHT_BROWSERS_PATH=C:\ms-playwright
set DOTENV_CONFIG_PATH=C:\apps\bot-keo-nhom-bcr-main\.env
echo.
echo Mo Google Chrome... Dong cua so nay = tat session debug
echo.
"C:\Program Files\nodejs\node.exe" --max-old-space-size=1536 -r dotenv/config servicePuppeteer\session.js
echo.
echo Khoi dong lai BCR-session1 service...
"C:\tools\nssm\nssm-2.24\win64\nssm.exe" start BCR-session1
pause
