# bot-keo-nhom-vip

Bot kéo nhóm Baccarat Sexy — vision capture + Telegram forward.

## Nhóm local/VPS (đang bật)

- **Thật**: `bot_forward_20` → `-1002566053276`
- **Ảo**: `bot_forward_21` → `-1004394354578`

## Chạy nhanh

```bash
# Server
node server.js

# Vision (Windows GUI)
python vision_bot/runner.py

# Forward 2 nhóm
python bot_forward_runner.py --run-now
```

## VPS

```bash
pm2 start ecosystem.config.vip.js
```
