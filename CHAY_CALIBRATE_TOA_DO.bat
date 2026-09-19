@echo off
chcp 65001 >nul
title CALIBRATE TOA DO VISION
cd /d "%~dp0"
python vision_bot\calibrate_gui.py
pause
