@echo off
chcp 65001 >nul
title VISION BOT 24/7
cd /d "%~dp0"
python vision_bot\runner.py
pause
