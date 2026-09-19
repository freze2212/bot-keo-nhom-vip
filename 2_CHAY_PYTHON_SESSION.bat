@echo off
chcp 65001 >nul
title [2] PYTHON NATIVE CONTROLLER - SEXY BACCARAT (60 FPS NATIVE)
color 0A
cd /d "%~dp0"
echo =============================================================
echo     KHOI DONG PYTHON NATIVE CONTROLLER (FULL GPU 60 FPS)
echo =============================================================
echo.

python -m python_service.session_controller
pause
