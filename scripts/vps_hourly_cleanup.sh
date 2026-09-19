#!/bin/bash
# Dọn log/ảnh tạm mỗi giờ — tránh đầy ổ 16GB
set +e
ROOT="/var/www/bot-keo-nhom-bcr-main"
SHOT="$ROOT/public/screenshots"

# PM2 log
pm2 flush >/dev/null 2>&1

# Ảnh held copy (ảo) > 1h
if [ -d "$SHOT/held" ]; then
  find "$SHOT/held" -type f -mmin +60 -delete 2>/dev/null
fi

# ho_* leak (không dùng nữa)
find "$SHOT" -maxdepth 1 -type f -name 'ho_*.png' -delete 2>/dev/null

# Ảnh sexy cũ hơn 6h (giữ disk nhẹ; mỗi bàn vẫn có shot mới từ session)
find "$SHOT" -maxdepth 1 -type f -name 'sexy_*.png' -mmin +360 -delete 2>/dev/null

# Log project
find "$ROOT/logs" -type f -name '*.log' -exec truncate -s 0 {} \; 2>/dev/null

# Tmp rác tele
find /tmp -maxdepth 1 -type f \( -name 'tele_*.jpg' -o -name '*.tgz' \) -mtime +0 -delete 2>/dev/null

# Journal + apt
journalctl --vacuum-size=80M >/dev/null 2>&1
apt-get clean >/dev/null 2>&1

df -h / | tail -1
