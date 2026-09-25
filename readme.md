# bot-keo-nhom-vip

Vision Chrome GUI + Telegram forward 3 mode + panel khách.

## Stack đang dùng

| Thành phần | Entry |
|------------|--------|
| Server + panel | `node server.js` / `1_CHAY_SERVER.bat` |
| Vision | `python vision_bot/runner.py` / `CHAY_BOT_VISION_AUTO.bat` |
| Forward | `python bot_forward_runner.py` / `3_CHAY_FORWARD_BOT.bat` |
| PM2 VPS | `pm2 start ecosystem.config.vip.js` |

**3 mode** (`tele_forward_accounts.json`): thật · ảo · 24/24 continuous.

## Local full

```bat
CHAY_ALL_LOCAL.bat
```

## Tách máy (vision local · panel/forward VPS)

1. VPS Ubuntu: `server.js` + `bot_forward_runner` + Nginx HTTPS → `/panel/`
2. Local: chỉ vision; trong `.env`:
   - `API_BASE_URL=https://domain-cua-ban`
   - `SERVER_HOSTNAME=https://domain-cua-ban`
   - `UPLOAD_SHOTS=1` → ảnh JPEG gửi kèm `/api/notify-screenshot` (cùng request, crop sẵn → gần mượt như local)

Hô text (`match_vision`) chỉ JSON — không chờ ảnh.

## Panel

http://localhost:3201/panel/ — license khách, nhiều nhóm, template/gấp thếp, token_bot.
