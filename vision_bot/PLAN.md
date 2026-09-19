# Vision Bot — OS SendInput (không CDP)

## Chạy
```bat
CHAY_CALIBRATE_TOA_DO.bat   :: chỉnh tọa độ
CHAY_BOT_VISION_AUTO.bat    :: 24/7 runner
CHAY_VISION_FULL_TEST.bat   :: dry-run boot
```

## File chính (`vision_bot/`)
- `runner.py` — vòng 24/7 + watchdog
- `login_flow.py` / `step_verify.py` — login + Sexy + recover
- `settlement.py` — WIN/LOSE/Hòa + crop capture
- `bet_window.py` — cửa đặt + BetVerifier
- `navigator.py` / `input_click.py` — click OS
- `chrome_launcher.py` / `window_controller.py` / `screen_grabber.py`
- `visual_detector.py` / `bridge.py` / `config_manager.py`
- `calibrate_gui.py` — ARM+F8

Log: `vision_bot/logs/` (gitignore)
