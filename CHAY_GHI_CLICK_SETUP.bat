@echo off
chcp 65001 >nul
cd /d "%~dp0"
title GHI CLICK SETUP

echo.
echo  ========================================
echo   GHI CLICK SETUP — dung de calibrate
echo  ========================================
echo.
echo  Cach dung (khong can F8):
echo   1. Bam "Mo web login"
echo   2. Bam "Khoa cua so Chrome"
echo   3. Re chuot dung cho tren Chrome
echo   4. Bam nut xanh "GHI DIEM NAY"
echo   5. Lap lai den het buoc
echo.
echo  Khi xong: bam "Luu config" chi khi muon ghi de file.
echo  May dang chay OK 1920x1080 — chon No neu chi thu.
echo.
echo  Dang mo tool...
echo.

python vision_bot\record_setup_clicks.py
if errorlevel 1 (
  echo.
  echo Loi chay. Thu: py -3 vision_bot\record_setup_clicks.py
  py -3 vision_bot\record_setup_clicks.py
)
echo.
pause
