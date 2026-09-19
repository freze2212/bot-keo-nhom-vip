@echo off
chcp 65001 >nul
title XEM BROWSER NS1
color 0A
echo.
echo ============================================
echo   XEM BROWSER NS1 - Firefox tren man hinh RDP
echo ============================================
echo Dang STOP BCR-session1 (service chay ngam)...
"C:\tools\nssm\nssm-2.24\win64\nssm.exe" stop BCR-session1
timeout /t 3 /nobreak >nul
cd /d C:\apps\bot-keo-nhom-bcr-main
set HEADLESS=0
set USE_FIREFOX=1
set ACCOUNT_INDEX=1
set PLAYWRIGHT_BROWSERS_PATH=C:\ms-playwright
set DOTENV_CONFIG_PATH=C:\apps\bot-keo-nhom-bcr-main\.env
echo.
echo Mo Firefox... Dong cua so nay = tat session debug
echo.
"C:\Program Files\nodejs\node.exe" --max-old-space-size=1536 -r dotenv/config servicePuppeteer\session.js
echo.
echo Khoi dong lai BCR-session1 service...
"C:\tools\nssm\nssm-2.24\win64\nssm.exe" start BCR-session1
pause
