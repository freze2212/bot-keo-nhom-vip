#!/bin/bash
# Chạy trên VPS khi session không lên: bash scripts/vps_fix_sessions.sh
set -e
ROOT="/var/www/bot-keo-nhom-bcr-main"
cd "$ROOT"

echo "===== DISK ====="
df -h /

echo "===== DỌN NHANH ====="
bash "$ROOT/scripts/vps_hourly_cleanup.sh" || true

echo "===== MONGO ====="
systemctl reset-failed mongod 2>/dev/null || true
systemctl start mongod 2>/dev/null || systemctl start mongodb 2>/dev/null || true
sleep 2
systemctl is-active mongod || echo "WARN: mongod chưa chạy"

echo "===== RESTART PM2 ====="
pm2 restart server_sexy session_sexy_1 session_sexy_2 session_sexy_3 session_sexy_4 \
  bot_sexy_1 bot_sexy_2 bot_sexy_3 bot_sexy_4 forward-bot
sleep 8

echo "===== PM2 STATUS ====="
pm2 status

echo "===== SESSION LOG (tail) ====="
for i in 1 2 3 4; do
  echo "--- session_sexy_$i ---"
  tail -n 8 /root/.pm2/logs/session-sexy-$i-error.log 2>/dev/null || true
  tail -n 5 /root/.pm2/logs/session-sexy-$i-out.log 2>/dev/null || true
done
