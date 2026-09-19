@echo off
chcp 65001 >nul
title VISION DRY RUN
cd /d "%~dp0"
set VISION_DRY_RUN=1
python vision_bot\runner.py
pause
