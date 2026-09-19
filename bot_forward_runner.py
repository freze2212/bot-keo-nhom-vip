import os
import sys
import json
import re
import sqlite3
import time
import random
import shutil
import atexit
import ctypes
import argparse
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import asyncio
from telethon import TelegramClient
from telethon.errors import (
    AuthKeyDuplicatedError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
    FloodWaitError,
)
from telethon.tl.types import Channel, Chat, MessageMediaWebPage

# Terminal UTF-8 config on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

TZ = timezone(timedelta(hours=7))  # GMT+7 — dùng thống nhất cho log + lịch


def now_vn():
    return datetime.now(TZ)


_QUIET_SKIP = (
    "[SCHEDULE AUDIT]",
    "Tin mở đầu ",
    "Tin kết thúc ",
    "Lịch chạy:",
    "Chờ 20s rồi",
    "Hết 20s — đang chờ",
    "Chờ cố định 20s",
    "Đã báo bàn round cũ",
    "copy=",
)


def log(msg, bot_name="BOT"):
    text = str(msg or "")
    if any(s in text for s in _QUIET_SKIP):
        return
    print(f"[{now_vn().strftime('%Y-%m-%d %H:%M:%S')}][{bot_name}] {msg}", flush=True)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_CONFIG_FILE = os.path.join(ROOT_DIR, 'tele_forward_accounts.json')
SCREENSHOT_DIR = os.path.join(ROOT_DIR, 'public', 'screenshots')
API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:3201')
API_KEY = os.getenv('API_KEY', 'your-static-api-key')

RESULT_IMAGE_DIRS = {
    'wincai': 'images/wincai',
    'losecai': 'images/losecai',
    'wincon': 'images/wincon',
    'losecon': 'images/losecon',
    'tie': 'images/tie',
}
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')

SCHEDULE_INTERVAL = int(os.getenv('SCHEDULE_INTERVAL', '10'))
SCHEDULE_START_HOUR, SCHEDULE_START_MINUTE = 12, 0
SCHEDULE_END_HOUR, SCHEDULE_END_MINUTE = 22, 10
sent_slots = set()

def winner_from_shot_filename(filepath):
    if not filepath:
        return None
    bname = os.path.basename(filepath).upper()
    if "_WB_" in bname or "_WB." in bname or "WINCAI" in bname:
        return "B"
    if "_WP_" in bname or "_WP." in bname or "WINCON" in bname:
        return "P"
    if "_WT_" in bname or "_WT." in bname or "TIE" in bname:
        return "T"
    return None


def resolve_shot_winner(filepath, api_winner=None):
    """Winner trên tên file (ảnh gửi đi) thắng API — tránh Hòa đè lên ảnh CÁI/CON."""
    file_w = winner_from_shot_filename(filepath)
    api_w = str(api_winner or "").strip().upper()
    if api_w not in ("B", "P", "T"):
        api_w = None
    if file_w and api_w and file_w != api_w:
        return file_w
    return file_w or api_w

def load_accounts_config(include_disabled=False):
    if not os.path.exists(ACCOUNTS_CONFIG_FILE):
        return []
    try:
        with open(ACCOUNTS_CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            accounts = data.get('accounts', [])
            if include_disabled:
                return accounts
            return [a for a in accounts if a.get('enabled', True)]
    except Exception as e:
        log(f"Lỗi đọc {ACCOUNTS_CONFIG_FILE}: {e}")
        return []

def get_account_by_id(account_id):
    accounts = load_accounts_config(include_disabled=True)
    for acc in accounts:
        if acc.get('id') == account_id or acc.get('phone') == account_id:
            return acc
    return None

def parse_bet_amount_numeric(label):
    """'500' -> 500, '5000' -> 5000. Label có % thì trả 0 (chế độ %)."""
    raw = str(label or "").strip()
    if "%" in raw:
        return 0
    try:
        return int(float(raw.replace(",", "")))
    except ValueError:
        return 0

def uses_pnl_messages(config):
    """Chỉ nhóm bot 9/10 dùng format lợi nhuận + lệnh hô in đậm."""
    return str((config or {}).get('profit_style', 'legacy')).lower() == 'pnl'

def uses_html_messages(config):
    """HTML đậm: bot 9/10 (pnl) hoặc bot 7/8 (winloss_result)."""
    return uses_pnl_messages(config) or bool((config or {}).get('winloss_result'))

def format_profit_message(pnl):
    """Tin lợi nhuận HTML đơn giản, chữ đậm."""
    if pnl > 0:
        return f"💰 <b>LỢI NHUẬN CA NÀY +{pnl}🔥</b>"
    if pnl < 0:
        return f"💰 <b>LỢI NHUẬN CA NÀY {pnl}</b>"
    return f"💰 <b>LỢI NHUẬN CA NÀY 0</b>"

def build_profit_result_text(bet_amount_label, norm_winner, norm_bet):
    """Thay Húp/Thua bằng tin lợi nhuận có format đẹp."""
    amount = parse_bet_amount_numeric(bet_amount_label)
    if amount <= 0:
        if norm_winner == "T" or not norm_winner:
            return format_profit_message(0)
        if norm_winner == norm_bet:
            return "💰 <b>LỢI NHUẬN CA NÀY +10%🔥</b>"
        return "💰 <b>LỢI NHUẬN CA NÀY -10%</b>"

    if norm_winner == "T" or not norm_winner:
        pnl = 0
    elif norm_winner == norm_bet:
        pnl = amount
    else:
        pnl = -amount

    return format_profit_message(pnl)

def build_virtual_profit_text(bet_amount_label, outcome):
    amount = parse_bet_amount_numeric(bet_amount_label) or 500
    if outcome == "WIN":
        pnl = amount
    elif outcome == "LOSS":
        pnl = -amount
    else:
        pnl = 0
    return format_profit_message(pnl)

def format_bet_text_legacy(bet_text, bet_amount_label):
    label = str(bet_amount_label or '').strip()
    if label == "5000":
        return f"{bet_text} 5000"
    if label == "1000":
        return f"{bet_text} 1000"
    return f"{bet_text} {label}"

def format_bet_for_config(config, bet_text):
    label = config.get('bet_amount_label', '10%')
    if uses_pnl_messages(config) or config.get('winloss_result'):
        return format_bet_text_with_amount(bet_text, label)
    return format_bet_text_legacy(bet_text, label)

def build_winloss_result_text(bet_amount_label, norm_winner=None, norm_bet=None, outcome=None):
    """Tin Thắng/Thua/Hòa có icon — chỉ nhóm bật winloss_result (bot 7/8)."""
    amount = parse_bet_amount_numeric(bet_amount_label) or 1000
    if outcome is not None:
        key = str(outcome or '').upper()
        if key == 'TIE':
            return "🤝 Hòa 0"
        if key == 'WIN':
            return f"🎉 Thắng +{amount} 🔥"
        return f"❌ Thua -{amount}"
    if norm_winner == 'T' or not norm_winner:
        return "🤝 Hòa 0"
    if norm_winner == norm_bet:
        return f"🎉 Thắng +{amount} 🔥"
    return f"❌ Thua -{amount}"

def build_virtual_result_for_config(config, outcome):
    label = config.get('bet_amount_label', '10%')
    if config.get('winloss_result'):
        return build_winloss_result_text(label, outcome=outcome)
    if uses_pnl_messages(config):
        return build_virtual_profit_text(label, outcome)
    if outcome == 'WIN':
        return f"🎉 Húp +{label}"
    if outcome == 'LOSS':
        return f"❌ Thua -{label}"
    return "🤝 Hòa +0"

def build_real_result_for_config(config, norm_winner, norm_bet, outcome=None):
    label = config.get('bet_amount_label', '10%')
    if config.get('winloss_result'):
        return build_winloss_result_text(label, norm_winner, norm_bet, outcome=outcome)
    if uses_pnl_messages(config):
        return build_profit_result_text(label, norm_winner, norm_bet)
    if label == "5000":
        if norm_winner == 'T':
            return "🤝 Hòa +0"
        if norm_winner == norm_bet:
            return "🎉 Húp +5000"
        return "❌ Thua -5000"
    if label == "1000":
        if norm_winner == 'T':
            return "🤝 Hòa +0"
        if norm_winner == norm_bet:
            return "🎉 Húp +1000"
        return "❌ Thua -1000"
    if norm_winner == 'T':
        return "🤝 Hòa +0%"
    if norm_winner == norm_bet:
        return "🎉 Húp +10%"
    return "❌ Thua -10%"

def outcome_key_from_real(norm_winner, norm_bet):
    if not norm_winner:
        return None
    if norm_winner == 'T':
        return 'TIE'
    if norm_winner == norm_bet:
        return 'WIN'
    return 'LOSS'

def outcome_key_from_virtual(outcome):
    return str(outcome or 'TIE').upper()


def pick_bet_side_for_virtual_outcome(winner, outcome):
    """Ảnh CON/CÁI: WIN hô đúng cửa, LOSS hô cửa ngược. Ảnh Hòa: vẫn hô CON hoặc CÁI."""
    w = str(winner or '').strip().upper()
    o = str(outcome or '').strip().upper()
    if w == 'T' or o == 'TIE':
        return random.choice(('B', 'P'))
    if w not in ('B', 'P'):
        return None
    if o == 'LOSS':
        return 'P' if w == 'B' else 'B'
    return w


def roll_virtual_outcome(config, known_winner):
    """
    Ảnh ván cũ quyết định:
    - Hòa → luôn TIE (vẫn hô, gửi ảnh hòa, báo Hòa)
    - CON/CÁI → 80% WIN (hô đúng cửa ảnh), 20% LOSS (hô cửa ngược)
    """
    w = str(known_winner or '').strip().upper()
    if w == 'T':
        return 'TIE'
    if w not in ('B', 'P'):
        return None

    win_rate = float(config.get('win_rate', 0.80))
    loss_rate = float(config.get('loss_rate', 0.20))
    non_tie = win_rate + loss_rate
    if non_tie <= 0:
        win_rate, loss_rate = 0.80, 0.20
        non_tie = 1.0
    win_p = win_rate / non_tie
    return 'WIN' if random.random() < win_p else 'LOSS'


def fetch_latest_capture_from_api(table_name):
    """Lấy ảnh capture + winner từ API (ưu tiên hơn đọc disk)."""
    try:
        q = urllib.parse.quote(str(table_name or '').strip().upper())
        url = f"{API_BASE_URL.rstrip('/')}/api/latest-screenshot?tableName={q}"
        req = urllib.request.Request(url, headers=get_api_headers())
        with urllib.request.urlopen(req, timeout=4) as r:
            data = json.loads(r.read().decode('utf-8'))
        if not data.get('success'):
            return None, None
        item = data.get('data') or {}
        fp = item.get('filepath')
        resolved = resolve_screenshot_path(fp) if fp else None
        winner = resolve_shot_winner(resolved or fp, item.get('resultWinner'))
        if resolved and os.path.exists(resolved) and is_real_screenshot_file(resolved) and winner:
            return resolved, winner
    except Exception:
        pass
    return None, None


def peek_valid_capture(table_name, max_age_s=None, allow_tie=True):
    """Kiểm tra bàn có ảnh capture hợp lệ (chưa copy)."""
    max_age_s = max_age_s if max_age_s is not None else int(
        os.getenv('VIRTUAL_CAPTURE_MAX_AGE_S', '300') or '300'
    )
    allowed = ('B', 'P', 'T') if allow_tie else ('B', 'P')
    src, winner = fetch_latest_capture_from_api(table_name)
    if winner not in allowed:
        src, winner = None, None
    if not src:
        src = get_latest_local_screenshot_for_table(table_name, winners=allowed)
        winner = winner_from_shot_filename(src)
    resolved = resolve_screenshot_path(src) if src else None
    if not resolved or not os.path.exists(resolved):
        return None, None
    if not is_real_screenshot_file(resolved):
        return None, None
    winner = resolve_shot_winner(resolved, winner)
    if winner not in allowed:
        return None, None
    try:
        if (time.time() - os.path.getmtime(resolved)) > max_age_s:
            return None, None
    except OSError:
        return None, None
    return resolved, winner


def request_live_capture(table_name, result_winner=None, name_service=None):
    """Gọi vision (qua server socket) chụp live — dùng lúc báo bàn."""
    try:
        body = {"tableName": str(table_name or "").upper()}
        if result_winner:
            body["resultWinner"] = result_winner
        if name_service:
            body["nameService"] = name_service
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{API_BASE_URL.rstrip('/')}/api/request-capture-now",
            data=data,
            headers={**get_api_headers(), "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as ex:
        log(f"[CAPTURE REQUEST] lỗi: {ex}")
        return None


def get_newest_shot_any(table_name, newer_than_mtime=None):
    """File sexy_* mới nhất của bàn (kể cả PREVIEW)."""
    search_dirs = [
        os.path.join(ROOT_DIR, "public", "screenshots"),
        os.path.join(ROOT_DIR, "screenshots"),
    ]
    tbl = str(table_name or "").upper()
    best = None
    best_m = -1
    for sdir in search_dirs:
        if not os.path.isdir(sdir):
            continue
        try:
            for name in os.listdir(sdir):
                low = name.lower()
                if not low.startswith("sexy_") or not low.endswith(".png"):
                    continue
                if tbl.lower() not in low:
                    continue
                path = os.path.join(sdir, name)
                try:
                    m = os.path.getmtime(path)
                except OSError:
                    continue
                if newer_than_mtime is not None and m <= newer_than_mtime:
                    continue
                if m > best_m:
                    best_m = m
                    best = path
        except OSError:
            pass
    return best


def list_main_shots_for_table(table_name, winners=None):
    """Ảnh sexy_* của main trên bàn, mới nhất trước. PREVIEW không tính vào kết quả B/P/T."""
    search_dirs = [
        os.path.join(ROOT_DIR, 'public', 'screenshots'),
        os.path.join(ROOT_DIR, 'screenshots'),
    ]
    tbl_norm = str(table_name or '').lower()
    allowed = winners or ('B', 'P', 'T')
    found = []
    for sdir in search_dirs:
        if not os.path.exists(sdir):
            continue
        try:
            for name in os.listdir(sdir):
                low = name.lower()
                if not low.startswith('sexy_') or not low.endswith(IMAGE_EXTENSIONS):
                    continue
                if 'preview' in low:
                    continue
                if f"_{tbl_norm}_" not in low and f"{tbl_norm}_" not in low:
                    continue
                path = os.path.join(sdir, name)
                if not is_real_screenshot_file(path):
                    continue
                win = resolve_shot_winner(path)
                if win not in allowed:
                    continue
                found.append((os.path.getmtime(path), path, win))
        except OSError:
            pass
    found.sort(key=lambda x: x[0], reverse=True)
    # unique by basename, keep newest
    seen = set()
    out = []
    for item in found:
        key = os.path.basename(item[1])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def pick_old_main_shot(table_name, max_age_s=None):
    """Ảo: ảnh round cũ sexy_* (ưu tiên shot mới nhì). Không skip vì tuổi file."""
    shots = list_main_shots_for_table(table_name)
    if not shots:
        return None, None
    for item in (shots[1:] if len(shots) >= 2 else shots):
        path, win = item[1], item[2]
        if win in ('B', 'P', 'T') and os.path.exists(path):
            return path, win
    path, win = shots[0][1], shots[0][2]
    if win in ('B', 'P', 'T') and os.path.exists(path):
        return path, win
    return None, None


HELD_SHOT_DIR = os.path.join(SCREENSHOT_DIR, 'held')


def hold_main_shot_copy(src, tag=""):
    """Copy sexy_* ra thư mục held — cleanup bàn không được xóa file đang gửi."""
    if not src or not os.path.exists(src):
        return None
    try:
        os.makedirs(HELD_SHOT_DIR, exist_ok=True)
        base = os.path.basename(src)
        safe_tag = re.sub(r'[^A-Za-z0-9_-]+', '_', str(tag or 'x'))[:40]
        dest = os.path.join(HELD_SHOT_DIR, f"{safe_tag}_{base}")
        shutil.copy2(src, dest)
        if os.path.exists(dest) and os.path.getsize(dest) >= 40000:
            return dest
    except OSError:
        pass
    return src if os.path.exists(src) else None


def release_held_shot(path):
    """Xóa bản copy held sau khi đã gửi xong round."""
    if not path:
        return
    try:
        held = os.path.abspath(HELD_SHOT_DIR)
        if os.path.abspath(path).startswith(held + os.sep) and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def fallback_any_main_shot():
    """Khi bàn đang chọn không còn file: lấy sexy_* còn trên disk, ưu tiên mới nhì."""
    search_dirs = [
        os.path.join(ROOT_DIR, 'public', 'screenshots'),
        os.path.join(ROOT_DIR, 'screenshots'),
    ]
    found = []
    for sdir in search_dirs:
        if not os.path.exists(sdir):
            continue
        try:
            for name in os.listdir(sdir):
                low = name.lower()
                if not low.startswith('sexy_') or not low.endswith(IMAGE_EXTENSIONS):
                    continue
                path = os.path.join(sdir, name)
                if not is_real_screenshot_file(path):
                    continue
                win = resolve_shot_winner(path)
                if win not in ('B', 'P', 'T'):
                    continue
                found.append((os.path.getmtime(path), path, win))
        except OSError:
            pass
    found.sort(key=lambda x: x[0], reverse=True)
    if len(found) >= 2:
        return found[1][1], found[1][2]
    if found:
        return found[0][1], found[0][2]
    return None, None


def get_old_round_screenshot_for_table(table_name):
    """Báo bàn thật = round cũ (shot mới nhì). Không gửi shot mới nhất."""
    shots = list_main_shots_for_table(table_name)
    if len(shots) >= 2:
        return shots[1][1]
    if shots:
        return shots[0][1]
    return get_latest_local_screenshot_for_table(table_name)


VIRTUAL_PAIR_DIR = os.path.join(ROOT_DIR, 'public', 'screenshots', 'virtual_pair')


def _virtual_pair_dir(table_name):
    d = os.path.join(VIRTUAL_PAIR_DIR, str(table_name or 'T').strip().upper())
    os.makedirs(d, exist_ok=True)
    return d


def _clear_slot(pair_dir, slot):
    """Xóa old_* hoặc new_* trong thư mục cặp."""
    for name in os.listdir(pair_dir):
        if name.startswith(slot + '_') and name.lower().endswith('.png'):
            try:
                os.remove(os.path.join(pair_dir, name))
            except OSError:
                pass


def _copy_main_to_slot(pair_dir, slot, src, winner):
    ext = os.path.splitext(src)[1].lower() or '.png'
    if ext not in IMAGE_EXTENSIONS:
        ext = '.png'
    dest = os.path.join(pair_dir, f"{slot}_W{winner}{ext}")
    shutil.copy2(src, dest)
    return dest if os.path.exists(dest) and os.path.getsize(dest) >= 40000 else None


def load_virtual_pair(table_name):
    pair_dir = _virtual_pair_dir(table_name)
    meta_path = os.path.join(pair_dir, 'pair.json')
    meta = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f) or {}
        except (OSError, ValueError):
            meta = {}
    old_path = os.path.join(pair_dir, meta['old']) if meta.get('old') else None
    new_path = os.path.join(pair_dir, meta['new']) if meta.get('new') else None
    if old_path and not os.path.exists(old_path):
        old_path = None
    if new_path and not os.path.exists(new_path):
        new_path = None
    return meta, old_path, new_path, pair_dir, meta_path


def save_virtual_pair(meta_path, meta):
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False)


def rotate_virtual_pair_from_main(table_name, max_age_s=None):
    """Ảo: chỉ lấy ảnh round cũ + winner. Ảnh kết quả = đúng file này."""
    path, win = pick_old_main_shot(table_name, max_age_s)
    if not path:
        return None, None, None, None
    return path, win, path, win

def config_step_delay(config, default=20):
    try:
        return max(1, int(config.get("step_delay", default) or default))
    except (TypeError, ValueError):
        return default


async def send_post_result_endings(config, forward_idx, outcome_key):
    """Sau kết quả: tin theo thắng/thua/hòa, rồi ending_order."""
    omap = config.get('outcome_message_map') or {}
    key = str(outcome_key or '').upper()
    idx = omap.get(key)
    step = config_step_delay(config, 20)
    if idx is not None:
        await forward_idx(idx, f"Tin kết quả ({key}) — tin thứ {idx + 1}, index {idx}")
        await asyncio.sleep(step)

    ending_order = config.get('ending_order', [3, 4])
    ending_delays = config.get('ending_delays', [step] * len(ending_order))
    for step_num, end_idx in enumerate(ending_order):
        await forward_idx(end_idx, f"Tin kết thúc (tin thứ {end_idx + 1}, index {end_idx})")
        delay = ending_delays[step_num] if step_num < len(ending_delays) else step
        await asyncio.sleep(delay)

def min_source_messages_for_config(config):
    indices = []
    for key in ("opening_order", "opening_after_preview", "ending_order"):
        vals = config.get(key) or []
        if isinstance(vals, list):
            indices.extend(vals)
    outcome_map = config.get("outcome_message_map") or {}
    if isinstance(outcome_map, dict):
        indices.extend(outcome_map.values())
    if uses_ho_source_forward(config):
        ho_map = config.get("ho_source_forward") or {}
        for v in ho_map.values():
            try:
                indices.append(int(v))
            except (TypeError, ValueError):
                pass
    needed = (max(indices) + 1) if indices else 5
    try:
        cfg_min = int(config.get("min_source_messages", 0) or 0)
        if cfg_min > 0:
            needed = max(needed, cfg_min)
    except (TypeError, ValueError):
        pass
    return needed


def stamp_outcome_on_image(src_path, outcome, bet_amount_label, out_dir=None):
    """Ghi THẮNG +N / THUA -N / HÒA 0 lên ảnh rồi trả path file mới."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return src_path
    if not src_path or not os.path.exists(src_path):
        return src_path
    amount = parse_bet_amount_numeric(bet_amount_label) or 1000
    key = str(outcome or "").upper()
    if key == "WIN":
        text = f"THẮNG +{amount}"
        fill = (20, 200, 70)
    elif key == "LOSS":
        text = f"THUA -{amount}"
        fill = (230, 40, 40)
    else:
        text = "HÒA 0"
        fill = (255, 190, 40)
    try:
        img = Image.open(src_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        w, h = img.size
        font_size = max(28, min(w, h) // 14)
        font = None
        for fp in (
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ):
            if os.path.exists(fp):
                try:
                    font = ImageFont.truetype(fp, font_size)
                    break
                except OSError:
                    pass
        if font is None:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad = max(8, font_size // 4)
        x = max(0, (w - tw) // 2)
        y = max(0, h - th - pad * 3)
        draw.rectangle(
            [x - pad, y - pad, x + tw + pad, y + th + pad],
            fill=(0, 0, 0),
        )
        draw.text((x, y), text, font=font, fill=fill)
        dest_dir = out_dir or os.path.join(SCREENSHOT_DIR, "stamped")
        os.makedirs(dest_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(src_path))[0]
        dest = os.path.join(dest_dir, f"{base}_{key}_stamp.png")
        img.save(dest, "PNG")
        return dest if os.path.exists(dest) else src_path
    except Exception as ex:
        log(f"[STAMP IMAGE] lỗi: {ex}")
        return src_path


def outcome_from_ho_and_winner(bet_side, shot_winner):
    """So hô với winner trên ảnh → WIN / LOSS / TIE."""
    w = normalize_side(shot_winner)
    s = normalize_side(bet_side)
    if w == "T" or not w:
        return "TIE"
    if s and w == s:
        return "WIN"
    return "LOSS"

def format_bet_text_with_amount(bet_text, bet_amount_label):
    amount = parse_bet_amount_numeric(bet_amount_label)
    suffix = str(amount) if amount > 0 else bet_amount_label
    upper = bet_text.upper()
    if 'CON' in upper or '🔵' in bet_text:
        return f"🔵 <b>CON {suffix}</b>"
    return f"🔴 <b>CÁI {suffix}</b>"


def ho_source_index_for_side(config, bet_side):
    """Index tin nguồn để forward HÔ: mặc định tin 7=CÁI (6), tin 8=CON (7)."""
    mapping = config.get('ho_source_forward') or {}
    side = str(bet_side or '').strip().upper()
    if side == 'B':
        return int(mapping.get('B', mapping.get('CÁI', 6)))
    if side == 'P':
        return int(mapping.get('P', mapping.get('CON', 7)))
    return None


def uses_ho_source_forward(config):
    return bool((config or {}).get('ho_source_forward'))

def resolve_screenshot_path(filepath):
    if not filepath:
        return None
    if os.path.isabs(filepath) and os.path.exists(filepath):
        return filepath
    candidates = [
        os.path.join(ROOT_DIR, filepath),
        os.path.join(ROOT_DIR, 'public', 'screenshots', os.path.basename(filepath)),
        os.path.join(ROOT_DIR, 'public', filepath),
        os.path.join(ROOT_DIR, 'screenshots', os.path.basename(filepath)),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def is_real_screenshot_file(filepath):
    if not filepath:
        return False
    resolved = resolve_screenshot_path(filepath)
    if not resolved or not os.path.exists(resolved):
        return False
    norm = str(resolved).replace("\\", "/").lower()
    name = os.path.basename(norm)
    if "/images/" in norm and "/screenshots/" not in norm:
        return False
    try:
        if os.path.getsize(resolved) < 40000:
            return False
    except OSError:
        return False
    return ("/screenshots/" in norm) or name.startswith("sexy_") or name.startswith("real_") or name.startswith("ho_")

def extract_winner_from_filename(filepath):
    if not filepath:
        return None
    bname = os.path.basename(filepath).upper()
    if "_WB_" in bname or "_WB." in bname or "WINCAI" in bname:
        return "B"
    if "_WP_" in bname or "_WP." in bname or "WINCON" in bname:
        return "P"
    if "_WT_" in bname or "_WT." in bname or "TIE" in bname:
        return "T"
    return None

def get_latest_local_screenshot_for_table(
    table_name="C01", min_stamp_ms=None, exclude_file=None, winners=None
):
    search_dirs = [
        os.path.join(ROOT_DIR, 'public', 'screenshots'),
        os.path.join(ROOT_DIR, 'screenshots'),
    ]
    tbl_norm = table_name.lower()
    min_mtime = (min_stamp_ms / 1000.0) if min_stamp_ms else 0

    for sdir in search_dirs:
        if not os.path.exists(sdir):
            continue
        try:
            files = [
                os.path.join(sdir, f)
                for f in os.listdir(sdir)
                if f.lower().startswith('sexy_') and f.lower().endswith(IMAGE_EXTENSIONS) and not f.startswith('.')
            ]
            if not files:
                continue
            tbl_files = [f for f in files if f"_{tbl_norm}_" in f.lower() or f"{tbl_norm}_" in f.lower()]
            target_list = tbl_files if tbl_files else files
            target_list.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            for f in target_list:
                if not is_real_screenshot_file(f):
                    continue
                file_win = extract_winner_from_filename(f)
                if not file_win:
                    continue
                if winners and file_win not in winners:
                    continue
                if exclude_file and os.path.abspath(f) == os.path.abspath(exclude_file):
                    continue
                if min_mtime > 0 and os.path.getmtime(f) < (min_mtime - 3):
                    continue
                return f
        except Exception:
            pass
    return None

def get_real_screenshot_by_winner(table_name="C01", winner="B", exclude_file=None):
    """
    Tìm ảnh chụp THẬT từ Playwright trong public/screenshots khớp với bàn table_name và kết quả winner ('B'/'P'/'T').
    TUYỆT ĐỐI chỉ lấy ảnh thật bắt đầu bằng sexy_, không bao giờ lấy ảnh ảo!
    """
    search_dirs = [
        os.path.join(ROOT_DIR, 'public', 'screenshots'),
        os.path.join(ROOT_DIR, 'screenshots'),
    ]
    tbl_norm = table_name.lower()
    norm_win = normalize_side(winner)
    win_tag = "_wb" if norm_win == 'B' else ("_wp" if norm_win == 'P' else "_wt")

    candidates = []
    for sdir in search_dirs:
        if not os.path.exists(sdir):
            continue
        try:
            files = [
                os.path.join(sdir, f)
                for f in os.listdir(sdir)
                if f.lower().startswith('sexy_') and f.lower().endswith(IMAGE_EXTENSIONS)
            ]
            for f in files:
                if exclude_file and os.path.abspath(f) == os.path.abspath(exclude_file):
                    continue
                fname = os.path.basename(f).lower()
                if (f"_{tbl_norm}_" in fname or f"{tbl_norm}_" in fname) and win_tag in fname:
                    candidates.append((os.path.getmtime(f), f))
        except Exception:
            pass

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    # Nếu không có ảnh đúng bàn đó có winner đó, lấy ảnh thật của bàn khác bất kỳ có đúng winner đó
    fallback_candidates = []
    for sdir in search_dirs:
        if not os.path.exists(sdir):
            continue
        try:
            files = [
                os.path.join(sdir, f)
                for f in os.listdir(sdir)
                if f.lower().startswith('sexy_') and f.lower().endswith(IMAGE_EXTENSIONS)
            ]
            for f in files:
                if exclude_file and os.path.abspath(f) == os.path.abspath(exclude_file):
                    continue
                fname = os.path.basename(f).lower()
                if win_tag in fname:
                    fallback_candidates.append((os.path.getmtime(f), f))
        except Exception:
            pass

    if fallback_candidates:
        fallback_candidates.sort(key=lambda x: x[0], reverse=True)
        return fallback_candidates[0][1]

    return None

def get_any_table_preview_screenshot():
    """Lấy 1 ảnh bàn cược tổng quan Sexy Baccarat bất kỳ sạch sẽ từ thư mục ảnh chụp gần đây hoặc ảnh mẫu."""
    search_dirs = [
        os.path.join(ROOT_DIR, 'public', 'screenshots'),
        os.path.join(ROOT_DIR, 'screenshots'),
        os.path.join(ROOT_DIR, 'images', 'sexy'),
        os.path.join(ROOT_DIR, 'images'),
    ]
    for sdir in search_dirs:
        if not os.path.exists(sdir):
            continue
        try:
            files = [
                os.path.join(sdir, f)
                for f in os.listdir(sdir)
                if f.lower().endswith(IMAGE_EXTENSIONS) and not f.startswith('.')
            ]
            if files:
                files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                return files[0]
        except Exception:
            pass
    for fb_type in ['wincai', 'wincon']:
        fb = get_fallback_image(fb_type)
        if fb and os.path.exists(fb):
            return fb
    return None

def get_virtual_result_image(bet_side, outcome):
    """
    Lấy ảnh kết quả từ folder ảnh ảo theo cửa cược (B/P) và kết quả (WIN/LOSS/TIE).
    - WIN: cược B -> lấy wincai, cược P -> lấy wincon
    - LOSS: cược B -> lấy losecai / wincon, cược P -> lấy losecon / wincai
    - TIE: lấy tie
    """
    if outcome == 'TIE':
        target_folders = ['images/tie']
    elif outcome == 'WIN':
        target_folders = ['images/wincai'] if bet_side == 'B' else ['images/wincon']
    else:  # LOSS
        target_folders = ['images/losecai', 'images/wincon'] if bet_side == 'B' else ['images/losecon', 'images/wincai']

    candidates = []
    search_dirs = [
        ROOT_DIR,
        '/var/www/bot-keo-nhom-bcr-main',
        r'C:\apps\bot-keo-nhom-bcr-main',
        os.path.dirname(os.path.abspath(__file__)),
        '.',
    ]
    for tf in target_folders:
        for base_dir in search_dirs:
            fpath = os.path.join(base_dir, tf)
            if os.path.isdir(fpath):
                imgs = [
                    os.path.join(fpath, f)
                    for f in os.listdir(fpath)
                    if f.lower().endswith(IMAGE_EXTENSIONS) and not f.startswith('.')
                ]
                if imgs:
                    candidates.extend(imgs)
        if candidates:
            break

    if candidates:
        return random.choice(candidates)

    res_type = 'tie' if outcome == 'TIE' else ('wincai' if (outcome == 'WIN') == (bet_side == 'B') else 'wincon')
    return get_fallback_image(res_type)

def get_api_headers():
    return {
        'User-Agent': 'Mozilla/5.0',
        'x-api-key': API_KEY,
    }

def _probe_ns_active_table(ns, now_ms=None):
    """Đọc bàn đang active của 1 NS. Trả None nếu pause / chưa vào bàn."""
    try:
        url = f"{API_BASE_URL.rstrip('/')}/api/get-active-table?nameService={ns}"
        req = urllib.request.Request(url, headers=get_api_headers())
        with urllib.request.urlopen(req, timeout=2.5) as r:
            data = json.loads(r.read().decode('utf-8'))
        if data.get('paused', False):
            return None
        if not data.get('success'):
            return None
        table = str(data.get('activeTable') or '').upper().strip()
        if not table or table in ('NONE', 'LOBBY'):
            return None
        ready_at = data.get('readyAt')
        try:
            ready_ms = int(ready_at or 0)
        except (TypeError, ValueError):
            ready_ms = 0
        now_ms = now_ms or int(time.time() * 1000)
        return {
            'name_service': ns,
            'table': table,
            'ready_at': ready_ms,
            'age_s': max(0, (now_ms - ready_ms) // 1000) if ready_ms else 0,
        }
    except Exception:
        return None


async def get_healthy_active_sessions():
    """
    Quét NS1..NS4 — session đang trong bàn (success=true, không pause).
    Ở bàn lâu vẫn OK — không lọc theo readyAt (session 24/24 ngồi 1 bàn hàng giờ là bình thường).
    """
    loop = asyncio.get_event_loop()
    now_ms = int(time.time() * 1000)

    def probe():
        res_list = []
        for ns in ['NS1', 'NS2', 'NS3', 'NS4']:
            row = _probe_ns_active_table(ns, now_ms)
            if row:
                res_list.append(row)
        return res_list

    try:
        return await loop.run_in_executor(None, probe)
    except Exception as e:
        log(f"[WARN] Lỗi kiểm tra session health: {e}")
        return []

BOT_PREFERRED_SESSIONS = {
    'bot_forward_1': ['NS1', 'NS4', 'NS2', 'NS3'],
    'bot_forward_2': ['NS2', 'NS4', 'NS1', 'NS3'],
    'bot_forward_3': ['NS3', 'NS4', 'NS1', 'NS2'],
}
GLOBAL_BOT_TABLE_CLAIMS = {}
GLOBAL_NS_CLAIMS = {}
GLOBAL_CLAIM_LOCK = asyncio.Lock()
NS_ROTATION_ORDER = ['NS1', 'NS2', 'NS3', 'NS4']
HO_CAPTURE_MAX_AGE_S = int(os.getenv('HO_CAPTURE_MAX_AGE_S', '180') or '180')
PRIORITY_ROUND_GROUP_IDS = [
    g.strip()
    for g in re.split(
        r'[\s,;]+',
        os.getenv('PRIORITY_ROUND_GROUPS', '-1002691928353,-1004296530499') or '',
    )
    if g.strip()
]


def _group_ids_for_ns(ns):
    raw = os.getenv(f'GROUP_{ns}', '') or ''
    return {g.strip() for g in re.split(r'[\s,;]+', raw) if g.strip()}


def round_ns_priority():
    """
    Round bot ưu tiên 2 session đang kéo 2 nhóm main:
    -1002691928353 (GROUP_NS3) và -1004296530499 (GROUP_NS2).
    Lỗi / pause / không hô → đẩy sang 2 NS còn lại.
    """
    primary = []
    seen = set()
    for ns in NS_ROTATION_ORDER:
        groups = _group_ids_for_ns(ns)
        if groups & set(PRIORITY_ROUND_GROUP_IDS):
            if ns not in seen:
                primary.append(ns)
                seen.add(ns)
    if not primary:
        primary = ['NS2', 'NS3']
    fallback = [ns for ns in NS_ROTATION_ORDER if ns not in seen]
    return primary, fallback


def order_ns_rows_by_priority(rows):
    primary, _fallback = round_ns_priority()
    pri = [r for r in rows if r.get('name_service') in primary]
    fb = [r for r in rows if r.get('name_service') not in primary]
    random.shuffle(pri)
    random.shuffle(fb)
    return pri + fb


_pri0, _fb0 = round_ns_priority()
log(
    f"[ROUND NS] Ưu tiên {_pri0} (nhóm {','.join(PRIORITY_ROUND_GROUP_IDS)}) "
    f"| fallback {_fb0}"
)


def table_has_recent_capture(table_name, max_age_s=None):
    """NS capture ổn: có ảnh thật gần đây trên bàn đó."""
    max_age_s = max_age_s or HO_CAPTURE_MAX_AGE_S
    shot = get_latest_local_screenshot_for_table(table_name)
    if not shot or not is_real_screenshot_file(shot):
        return False
    try:
        return (time.time() - os.path.getmtime(shot)) <= max_age_s
    except OSError:
        return False


async def pick_random_healthy_ns_for_ho_round(bot_id, bot_name=""):
    """
    Đến round HÔ: random 1 NS đang chạy mượt (trong bàn + capture gần đây).
    Tránh trùng NS với bot round khác đang chạy cùng lúc nếu còn lựa chọn.
    """
    async with GLOBAL_CLAIM_LOCK:
        loop = asyncio.get_event_loop()
        now_ms = int(time.time() * 1000)

        def probe_capture_ready():
            rows = []
            for ns in NS_ROTATION_ORDER:
                row = _probe_ns_active_table(ns, now_ms)
                if not row:
                    continue
                if not table_has_recent_capture(row['table']):
                    continue
                rows.append(row)
            return rows

        candidates = await loop.run_in_executor(None, probe_capture_ready)
        if not candidates:
            candidates = await get_healthy_active_sessions()
            log(
                f"[{bot_name or bot_id}] [HO ROUND] Không có NS capture mới — "
                f"dùng NS active ({len(candidates)})"
            )

        claimed_ns = {
            str(ns).upper()
            for bid, ns in GLOBAL_NS_CLAIMS.items()
            if bid != bot_id and ns
        }
        pool = [h for h in candidates if h['name_service'] not in claimed_ns] or candidates
        if not pool:
            return None, None

        ordered = order_ns_rows_by_priority(pool)
        chosen = ordered[0]
        GLOBAL_NS_CLAIMS[bot_id] = chosen['name_service']
        GLOBAL_BOT_TABLE_CLAIMS[bot_id] = chosen['table']
        primary, _fb = round_ns_priority()
        log(
            f"[{bot_name or bot_id}] [HO ROUND] Ưu tiên {chosen['name_service']} — "
            f"bàn {chosen['table']} (primary={','.join(primary)}, pool={len(pool)})"
        )
        return chosen['name_service'], chosen['table']


async def pick_virtual_ns_and_reserve(bot_id, bot_name=""):
    """Ảo: chọn bàn main, lấy ảnh round cũ (có sẵn kết quả) để hô ra đúng WIN/LOSS/TIE."""
    async with GLOBAL_CLAIM_LOCK:
        loop = asyncio.get_event_loop()
        base_age = int(os.getenv('VIRTUAL_CAPTURE_MAX_AGE_S', '300') or '300')

        def collect_active_ns():
            return [
                row for ns in NS_ROTATION_ORDER
                if (row := _probe_ns_active_table(ns))
            ]

        all_active = await loop.run_in_executor(None, collect_active_ns)
        if not all_active:
            log(f"[{bot_name or bot_id}] [ẢO] 4 NS đều off/pause/chưa vào bàn")
            return None, None, None, None

        claimed_ns = {
            str(ns).upper()
            for bid, ns in GLOBAL_NS_CLAIMS.items()
            if bid != bot_id and ns
        }

        for pass_label, age_mult in (('fresh', 1), ('relaxed', 4)):
            max_age = base_age * age_mult
            pool = [r for r in all_active if r['name_service'] not in claimed_ns] or list(all_active)
            ordered = order_ns_rows_by_priority(pool)
            tried = []
            for row in ordered:
                ns, table = row['name_service'], row['table']
                old_path, old_w = pick_old_main_shot(table, max_age)
                if old_path and old_w in ('B', 'P', 'T'):
                    held = hold_main_shot_copy(old_path, bot_id)
                    send_path = held or old_path
                    GLOBAL_NS_CLAIMS[bot_id] = ns
                    GLOBAL_BOT_TABLE_CLAIMS[bot_id] = table
                    log(
                        f"[{bot_name or bot_id}] [ẢO] Ván cũ {ns}/{table} "
                        f"{os.path.basename(old_path)}({old_w}) "
                        f"copy={os.path.basename(send_path)} pass={pass_label}"
                    )
                    return ns, table, send_path, old_w
                tried.append(f"{ns}/{table}:no-old")
            if tried:
                log(
                    f"[{bot_name or bot_id}] [ẢO] Pass {pass_label} thất bại: "
                    + ", ".join(tried)
                )

        active_labels = [f"{r['name_service']}/{r['table']}" for r in all_active]
        log(
            f"[{bot_name or bot_id}] [ẢO] Hết 4 NS active ({', '.join(active_labels)}) "
            f"— chưa có ảnh round cũ"
        )
        return None, None, None, None


def request_prepare_round_listen(table_name, listen_after_ms, name_service=None):
    try:
        body = json.dumps({
            "tableName": table_name,
            "listenAfterMs": int(listen_after_ms or 0),
            "nameService": str(name_service or "").strip().upper(),
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{API_BASE_URL.rstrip('/')}/api/prepare-round-listen",
            data=body,
            headers={**get_api_headers(), "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
            return int(data.get("skipped") or 0)
    except Exception as ex:
        log(f"[PREPARE ROUND LISTEN WARN] {ex}")
        return 0


def poll_main_ho_once(
    table_name=None,
    listen_after_ms=0,
    name_service=None,
    any_table=False,
    prefer_ns=None,
    prefer_only=False,
):
    """Poll HO. prefer_only=True: chỉ 2 session nhóm main, không lấy NS khác."""
    try:
        listen_ms = int(listen_after_ms or 0)
        params = {"listenAfterMs": str(listen_ms)}
        if any_table:
            params["any"] = "1"
            pref = prefer_ns
            if not pref:
                pref, _fb = round_ns_priority()
            if pref:
                params["preferNs"] = ",".join(pref)
            if prefer_only:
                params["preferOnly"] = "1"
        else:
            params["tableName"] = str(table_name or "").strip().upper()
            ns = str(name_service or "").strip().upper()
            if ns:
                params["nameService"] = ns
        qs = urllib.parse.urlencode(params)
        url = f"{API_BASE_URL.rstrip('/')}/api/poll-main-ho-for-round?{qs}"
        req = urllib.request.Request(url, headers=get_api_headers())
        with urllib.request.urlopen(req, timeout=4) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data.get("success") and data.get("signal"):
            sig = data["signal"]
            bet_side = normalize_side(sig.get("betSide")) or "P"
            bet_text = "🔴 CÁI" if bet_side == "B" else "🔵 CON"
            signal_id = int(sig.get("signalId") or 0)
            return bet_side, bet_text, signal_id, sig
    except Exception as ex:
        log(f"[MAIN HO POLL WARN] {ex}")
    return None, None, None, None


async def wait_main_ho_any_healthy_ns(
    bot_id, bot_name, listen_after_ms, max_wait_s=300, table_name=None, name_service=None
):
    """Round THẬT: chờ lệnh HÔ mới của session main, bê nguyên lệnh đó."""
    loop = asyncio.get_event_loop()
    listen_ms = int(listen_after_ms or 0)
    primary, _fallback = round_ns_priority()
    lock_table = str(table_name or "").strip().upper()
    lock_ns = str(name_service or "").strip().upper()
    if lock_table:
        log(
            f"[{bot_name or bot_id}] [THẬT] Chờ HÔ main {lock_ns or '/'.join(primary)}/{lock_table} "
            f"— ké đúng bàn đã báo"
        )
    else:
        log(f"[{bot_name or bot_id}] [THẬT] Chờ HÔ main ({','.join(primary)}) rồi bê nguyên lệnh")

    start_t = time.time()
    while time.time() - start_t < max_wait_s:
        bet_side, bet_text, signal_id, sig = await loop.run_in_executor(
            None,
            lambda: poll_main_ho_once(
                table_name=lock_table or None,
                listen_after_ms=listen_ms,
                name_service=lock_ns or None,
                any_table=not bool(lock_table),
                prefer_ns=primary,
                prefer_only=True,
            ),
        )
        if signal_id and sig:
            ns = str(sig.get("nameService") or "").strip().upper() or "NS2"
            table = str(sig.get("tableName") or "").strip().upper()
            async with GLOBAL_CLAIM_LOCK:
                GLOBAL_NS_CLAIMS[bot_id] = ns
                GLOBAL_BOT_TABLE_CLAIMS[bot_id] = table
            log(
                f"✅ [MAIN HO PICK] signalId={signal_id} {bet_text} "
                f"bê từ {ns}/{table} sau {time.time() - start_t:.1f}s"
            )
            return ns, table, bet_side, bet_text, signal_id, sig
        await asyncio.sleep(0.3)

    log(f"[{bot_name or bot_id}] [THẬT] Main chưa hô trong ca này")
    return None, None, None, None, None, None


async def pick_live_main_table(bot_id="", bot_name=""):
    """Bàn đang chạy của session main — dùng để báo bàn trước khi nghe HÔ."""
    loop = asyncio.get_event_loop()
    primary, fallback = round_ns_priority()

    def probe():
        for ns in list(primary) + list(fallback):
            row = _probe_ns_active_table(ns)
            if row and row.get("table"):
                return row["name_service"], row["table"]
        return None, None

    ns, table = await loop.run_in_executor(None, probe)
    if ns:
        log(f"[{bot_name or bot_id}] [BÁO BÀN] Session đang chạy {ns}/{table}")
    return ns, table


async def select_next_healthy_session(
    bot_id,
    previous_table=None,
    preferred_sessions=None,
    bot_name="",
    fallback_ns=None,
    fallback_table=None,
):
    """
    Chọn NS + bàn đang hoạt động. Ưu tiên NS config, tránh trùng bàn bot khác.
    4 session 24/24 luôn chạy — chỉ skip khi API lỗi hẳn, còn lại luôn có fallback.
    """
    async with GLOBAL_CLAIM_LOCK:
        healthy = await get_healthy_active_sessions()
        if not healthy:
            await asyncio.sleep(2)
            healthy = await get_healthy_active_sessions()

        ns_map = {h['name_service']: h for h in healthy}
        claimed_tables = {
            str(t).upper().strip()
            for b_id, t in GLOBAL_BOT_TABLE_CLAIMS.items()
            if b_id != bot_id and t
        }
        pref_list = list(preferred_sessions or BOT_PREFERRED_SESSIONS.get(bot_id, ['NS1', 'NS2', 'NS3', 'NS4']))

        chosen = None
        for ns in pref_list:
            if ns in ns_map:
                cand = ns_map[ns]
                if cand['table'] not in claimed_tables:
                    chosen = cand
                    break

        if not chosen and healthy:
            unclaimed = [h for h in healthy if h['table'] not in claimed_tables]
            if unclaimed:
                chosen = unclaimed[0]

        if not chosen:
            loop = asyncio.get_event_loop()
            for ns in pref_list:
                live = await loop.run_in_executor(None, _probe_ns_active_table, ns)
                if live and live['table'] not in claimed_tables:
                    chosen = live
                    log(f"[{bot_name}] Fallback live API {ns}/{live['table']}")
                    break

        fb_ns = str(fallback_ns or pref_list[0] if pref_list else 'NS1').strip().upper()
        fb_table = str(fallback_table or 'C01').strip().upper()

        if not chosen:
            if fb_ns in ns_map and ns_map[fb_ns]['table'] not in claimed_tables:
                chosen = ns_map[fb_ns]
                log(f"[{bot_name}] Fallback NS map {fb_ns}/{chosen['table']}")
            elif fb_table not in claimed_tables:
                GLOBAL_BOT_TABLE_CLAIMS[bot_id] = fb_table
                log(
                    f"[{bot_name}] Fallback config {fb_ns}/{fb_table} "
                    f"(API tạm chưa đủ — 4 session vẫn chạy, dùng bàn config)"
                )
                return fb_ns, fb_table

        if not chosen:
            any_h = healthy[0] if healthy else None
            if any_h:
                chosen = any_h
                log(f"[{bot_name}] Fallback bàn bất kỳ đang active {chosen['name_service']}/{chosen['table']}")

        if not chosen:
            GLOBAL_BOT_TABLE_CLAIMS[bot_id] = fb_table
            log(f"[{bot_name}] [WARN] API không phản hồi — dùng config {fb_ns}/{fb_table}")
            return fb_ns, fb_table

        GLOBAL_BOT_TABLE_CLAIMS[bot_id] = chosen['table']
        log(
            f"[{bot_name or bot_id}] [SESSION ASSIGNED] {chosen['name_service']} - {chosen['table']} "
            f"(claimed={list(claimed_tables)})"
        )
        return chosen['name_service'], chosen['table']

def get_latest_round(rounds):
    """Lấy ván cược MỚI NHẤT từ mảng totalRound (sắp xếp theo stampTime và id lớn nhất)."""
    if not isinstance(rounds, list) or not rounds:
        return None
    valid = []
    for r in rounds:
        if isinstance(r, dict):
            try:
                st = int(r.get('stampTime') or 0)
                rid = int(r.get('id') or 0)
                valid.append((st, rid, r))
            except (TypeError, ValueError):
                pass
    if not valid:
        return rounds[-1] if rounds else None
    valid.sort(key=lambda x: (x[0], x[1]))
    return valid[-1][2]

async def wait_for_main_ho_signal(table_name, listen_after_ms, name_service=None, max_wait_s=120):
    """
    Chờ lệnh HÔ từ main 24/24 sau mốc listen_after_ms.
    Bỏ qua mọi HÔ main trước mốc nghe; chỉ lấy HÔ mới khi các ván main trước đó (sau mốc nghe) đã có ảnh kết quả.
    """
    start_t = time.time()
    q_table = str(table_name).strip().upper()
    ns = str(name_service or "").strip().upper()
    listen_ms = int(listen_after_ms or 0)
    log(
        f"⏳ [MAIN HO LISTEN] bàn {table_name} ({ns or 'any'}) "
        f"sau mốc {listen_ms} — chờ main hô mới..."
    )
    loop = asyncio.get_event_loop()
    while time.time() - start_t < max_wait_s:
        bet_side, bet_text, signal_id, sig = await loop.run_in_executor(
            None,
            lambda: poll_main_ho_once(table_name, listen_after_ms, name_service),
        )
        if signal_id and sig:
            log(
                f"✅ [MAIN HO PICK] signalId={signal_id} {bet_text} "
                f"hoAt={sig.get('hoAt')} sau {time.time() - start_t:.1f}s"
            )
            return bet_side, bet_text, signal_id, sig
        await asyncio.sleep(1.0)
    log(f"⚠️ [MAIN HO TIMEOUT] Không có lệnh main mới bàn {table_name} sau {max_wait_s}s")
    return None, None, None, None


def consume_main_ho_signal(signal_id, consumer="round"):
    if not signal_id:
        return False
    try:
        body = json.dumps({"signalId": int(signal_id), "consumer": consumer}).encode("utf-8")
        req = urllib.request.Request(
            f"{API_BASE_URL.rstrip('/')}/api/consume-main-ho",
            data=body,
            headers={**get_api_headers(), "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
            return bool(data.get("success"))
    except Exception as ex:
        log(f"[CONSUME MAIN HO ERROR] signalId={signal_id}: {ex}")
        return False


def shot_winner(filepath, api_winner=None):
    return (
        winner_from_shot_filename(filepath)
        or extract_winner_from_filename(filepath)
        or normalize_side(api_winner)
    )


async def wait_for_main_ho_result_image(signal_id, max_wait_s=180, table_name=None, min_stamp_ms=None):
    """Chờ đúng lệnh HÔ này xong ván — bê ảnh + thắng/thua từ main, không đoán bàn khác."""
    if not signal_id:
        return None, None, None
    start_t = time.time()
    url = f"{API_BASE_URL.rstrip('/')}/api/main-ho-status?signalId={int(signal_id)}"
    last_sig = None
    while time.time() - start_t < max_wait_s:
        try:
            loop = asyncio.get_event_loop()
            req = urllib.request.Request(url, headers=get_api_headers())
            res_text = await loop.run_in_executor(
                None,
                lambda: urllib.request.urlopen(req, timeout=4).read().decode("utf-8")
            )
            sig = (json.loads(res_text) or {}).get("signal") or {}
            last_sig = sig
            if not sig.get("resultCompleted"):
                await asyncio.sleep(0.5)
                continue
            fp = resolve_screenshot_path(sig.get("resultFilepath"))
            winner = normalize_side(sig.get("resultWinner")) or shot_winner(fp)
            if fp and os.path.exists(fp) and is_real_screenshot_file(fp):
                log(
                    f"✅ [MAIN HO RESULT] signalId={signal_id} "
                    f"bê nguyên file main {os.path.basename(fp)} "
                    f"winner={winner} outcome={sig.get('resultOutcome')}"
                )
                return fp, winner, sig
        except Exception:
            pass
        await asyncio.sleep(0.5)
    log(f"❌ [MAIN HO RESULT TIMEOUT] signalId={signal_id} — main chưa trả ảnh")
    return None, None, last_sig

def normalize_side(val):
    if not val:
        return None
    s = str(val).strip().upper()
    if s in ('B', 'BANKER', 'CAI', 'CÁI') or s.startswith('B'):
        return 'B'
    if s in ('P', 'PLAYER', 'CON') or s.startswith('P'):
        return 'P'
    if s in ('T', 'TIE', 'HÒA', 'HOA') or s.startswith('T'):
        return 'T'
    return None

async def wait_for_table_screenshot_and_result(table_name="C01", bet_side="B", min_stamp_ms=None, initial_round_count=0, initial_round_id=0, exclude_shot=None, max_wait_s=75):
    """
    Chờ kết quả ván thật từ bàn và lấy ảnh chụp thật vừa hoàn thành của ĐÚNG ván đó.
    QUY TẮC ĐỐI CHIẾU CHUẨN XÁC:
    1. Bắt buộc kiểm tra Database bàn cược (/predict/get-table-by-name) xem đã có ván mới kết thúc chưa (id > initial_round_id hoặc số round tăng).
    2. CHỈ KHI DB ĐÃ MỞ THƯỞNG VÁN MỚI thì mới lấy kết quả và ảnh chụp tương ứng.
    3. Tuyệt đối không lấy ảnh chụp lúc đang đếm giây trước khi dealer lật bài.
    """
    start_time = time.time()
    q = urllib.parse.quote(str(table_name).strip().upper())
    predict_url = f"{API_BASE_URL.rstrip('/')}/predict/get-table-by-name?tableName={q}"
    shot_url = f"{API_BASE_URL.rstrip('/')}/api/latest-screenshot?tableName={q}"
    min_valid_stamp = min_stamp_ms or int(time.time() * 1000)
    
    db_winner = None
    db_round_id = None

    while time.time() - start_time < max_wait_s:
        try:
            loop = asyncio.get_event_loop()
            
            # 1. Kiểm tra Database bàn cược xem ván mới đã hoàn thành chưa (lấy ván mới nhất từ totalRound)
            req_db = urllib.request.Request(predict_url, headers=get_api_headers())
            res_db_text = await loop.run_in_executor(
                None,
                lambda: urllib.request.urlopen(req_db, timeout=3).read().decode('utf-8')
            )
            res_db = json.loads(res_db_text)
            rounds = res_db.get('totalRound', [])
            latest_r = get_latest_round(rounds)
            if latest_r:
                cur_id = int(latest_r.get('id') or 0)
                cur_winner = normalize_side(latest_r.get('roadFormat'))
                cur_stamp = int(latest_r.get('stampTime') or 0)
                if (cur_id > initial_round_id or cur_stamp > min_valid_stamp or len(rounds) > initial_round_count) and cur_winner in ('B', 'P', 'T'):
                    if not db_winner:
                        db_winner = cur_winner
                        db_round_id = cur_id
                        log(f"[DB RESULT] Bàn {table_name} đã ghi nhận ván mới #{db_round_id} kết quả: {db_winner} (sau {time.time() - start_time:.1f}s)")

            # 2. CHỈ KHI DATABASE ĐÃ CÓ KẾT QUẢ VÁN MỚI thì mới tìm ảnh kết quả
            if db_winner:
                req_shot = urllib.request.Request(shot_url, headers=get_api_headers())
                res_shot_text = await loop.run_in_executor(
                    None,
                    lambda: urllib.request.urlopen(req_shot, timeout=3).read().decode('utf-8')
                )
                res_shot = json.loads(res_shot_text)
                if res_shot.get('success') and res_shot.get('data'):
                    shot_data = res_shot['data']
                    filepath = shot_data.get('filepath')
                    raw_winner = shot_data.get('resultWinner') or shot_data.get('winner')
                    shot_round = int(shot_data.get('roundNum') or 0)
                    stamp = int(shot_data.get('stampTime') or 0)
                    
                    if filepath and os.path.exists(filepath) and is_real_screenshot_file(filepath):
                        if not (exclude_shot and os.path.abspath(filepath) == os.path.abspath(exclude_shot)):
                            file_win = extract_winner_from_filename(filepath)
                            norm_win = normalize_side(raw_winner) or file_win
                            
                            # Ảnh phải chụp sau khi hô lệnh hoặc khớp đúng ván/kết quả mở thưởng
                            is_truly_new = (stamp >= (min_valid_stamp + 10000)) or (db_round_id and shot_round >= db_round_id) or (file_win == db_winner)
                            if is_truly_new and norm_win in ('B', 'P', 'T') and file_win:
                                log(f"[MATCH SHOT] Đã khớp ảnh chụp thật ván #{db_round_id}: {os.path.basename(filepath)} | Kết quả: {db_winner}")
                                return filepath, db_winner

                # Tìm ảnh cục bộ nếu API trả về trễ
                local_shot = get_latest_local_screenshot_for_table(table_name, min_stamp_ms=min_valid_stamp + 10000, exclude_file=exclude_shot)
                if local_shot:
                    return local_shot, db_winner
                
                real_match = get_real_screenshot_by_winner(table_name, db_winner, exclude_file=exclude_shot)
                if real_match:
                    return real_match, db_winner

        except Exception:
            pass
        await asyncio.sleep(1.5)

    # Nếu hết max_wait_s:
    if db_winner:
        real_match = get_real_screenshot_by_winner(table_name, db_winner, exclude_file=exclude_shot)
        if real_match:
            return real_match, db_winner

    real_match = get_real_screenshot_by_winner(table_name, bet_side, exclude_file=exclude_shot)
    return real_match, bet_side

def get_fallback_image(result_type):
    target_dir = RESULT_IMAGE_DIRS.get(result_type, 'images/wincai')
    if os.path.exists(target_dir):
        files = [
            os.path.join(target_dir, f)
            for f in os.listdir(target_dir)
            if f.lower().endswith(IMAGE_EXTENSIONS) and not f.startswith('.')
        ]
        if files:
            return random.choice(files)
    return None

def request_place_bet_api(table_name, bet_side, name_service=None, bet_amount=None):
    try:
        url = f"{API_BASE_URL.rstrip('/')}/api/place-bet"
        body = {
            "tableName": table_name,
            "betSide": bet_side,
            "side": bet_side,
        }
        if name_service:
            body["nameService"] = name_service
        if bet_amount:
            try:
                body["betAmount"] = float(bet_amount)
            except (ValueError, TypeError):
                pass
        data_bytes = json.dumps(body).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={**get_api_headers(), 'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=4) as res:
            res_json = json.loads(res.read().decode('utf-8'))
            log(f"🎰 [AUTO BET API] Đã gửi lệnh đặt cược tự động bàn {table_name} ({bet_side}) -> {res_json}")
            return res_json
    except Exception as ex:
        log(f"⚠️ [AUTO BET API ERROR] Không thể gửi lệnh đặt cược: {ex}")
        return None

SHARED_TELEGRAM_CLIENTS = {}

async def get_or_create_client(session_name, api_id, api_hash):
    if session_name in SHARED_TELEGRAM_CLIENTS:
        client = SHARED_TELEGRAM_CLIENTS[session_name]
        if not client.is_connected():
            await client.connect()
        return client
    client = TelegramClient(session_name, api_id, api_hash)
    await client.connect()
    SHARED_TELEGRAM_CLIENTS[session_name] = client
    return client

class TelegramForwardBot:
    def __init__(self, config):
        self.config = config
        self.bot_id = config.get('id', 'bot_fw')
        self.name = config.get('name', self.bot_id)
        self.phone = config.get('phone', '').strip().replace(' ', '')
        self.api_id = int(config.get('api_id'))
        self.api_hash = config.get('api_hash', '').strip()
        self.twofa = config.get('twofa', '').strip()
        self.group_id = config.get('group_id')
        self.session_table = config.get('session_table', 'C01')
        self.name_service = config.get('name_service', 'NS1')
        self.source_username = config.get('source_username', 'frezeit')
        self.bet_amount_label = str(config.get('bet_amount_label', '10%')).strip()
        self.last_used_table = None
        self.is_running_round = False
        self.pending_slots = []
        cfg_ns = str(config.get('name_service') or '').strip().upper()
        if cfg_ns:
            self.preferred_sessions = [cfg_ns]
        elif self.bot_id == 'bot_forward_1':
            self.preferred_sessions = ['NS1']
        elif self.bot_id == 'bot_forward_2':
            self.preferred_sessions = ['NS2']
        elif self.bot_id == 'bot_forward_5':
            self.preferred_sessions = ['NS4']
        else:
            self.preferred_sessions = ['NS1', 'NS2', 'NS3', 'NS4']
        
        phone_digits = ''.join(c for c in self.phone if c.isdigit())
        self.session_name = config.get('session_name') or (
            f'user_session_{phone_digits}' if phone_digits else f'user_session_{self.bot_id}'
        )
        self.client = None
        self.dialog_cache = {}
        self.current_slot_key = None

    def audit(self, action):
        return

    def log(self, msg):
        log(msg, self.name)

    async def connect_and_login(self, interactive=True):
        try:
            self.client = await get_or_create_client(self.session_name, self.api_id, self.api_hash)
        except AuthKeyDuplicatedError:
            self.log(
                f"[ERROR] Session {self.session_name} bị Telegram khóa (AuthKeyDuplicated) — "
                f"đang dùng cùng session ở 2 IP. Xóa file .session và chạy lại: "
                f"python bot_forward_runner.py --login {self.bot_id}"
            )
            return False
        except Exception as e:
            self.log(f"[ERROR] Không kết nối Telegram ({self.session_name}): {e}")
            return False

        if await self.client.is_user_authorized():
            me = await self.client.get_me()
            self.log(f"Đã đăng nhập: {me.first_name} (@{me.username}) | SĐT: {self.phone}")
            await self.warm_up_cache()
            return True

        if not interactive:
            self.log("[ERROR] Tài khoản chưa đăng nhập session. Vui lòng chạy lệnh login trước.")
            return False

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            self.log(f"Đang gửi mã OTP ({attempt}/{max_attempts}) tới số {self.phone}...")
            sent_code = await self.client.send_code_request(self.phone)
            self.log(f">>> ĐÃ GỬI MÃ OTP VỀ SỐ {self.phone}. Nhập mã:")
            code = ""
            env_code = (os.getenv("TELEGRAM_OTP") or "").strip().replace(" ", "")
            otp_file = os.path.join(ROOT_DIR, "telegram_otp.txt")
            if env_code:
                code = env_code
                self.log("Dùng OTP từ biến môi trường TELEGRAM_OTP")
            elif os.path.exists(otp_file):
                try:
                    with open(otp_file, "r", encoding="utf-8") as f:
                        code = f.read().strip().replace(" ", "")
                except OSError:
                    code = ""
                if code:
                    self.log(f"Dùng OTP từ file {otp_file}")
                    try:
                        os.remove(otp_file)
                    except OSError:
                        pass
            if not code:
                # Ưu tiên chờ file (shell agent không nhập được stdin)
                self.log(
                    f"Chờ OTP: tạo file {otp_file} chứa mã (vd: 12345) hoặc set TELEGRAM_OTP. "
                    f"Timeout 180s..."
                )
                deadline = time.time() + 180
                while time.time() < deadline and not code:
                    await asyncio.sleep(2)
                    if os.path.exists(otp_file):
                        try:
                            with open(otp_file, "r", encoding="utf-8") as f:
                                code = f.read().strip().replace(" ", "")
                        except OSError:
                            code = ""
                        if code:
                            try:
                                os.remove(otp_file)
                            except OSError:
                                pass
                            break
                    if interactive and sys.stdin and sys.stdin.isatty():
                        # Không block input() — chỉ thử non-blocking nếu đã có sẵn
                        pass
                if not code and interactive:
                    try:
                        if sys.stdin and sys.stdin.isatty():
                            code = input(f"[{self.name}] Nhập mã OTP: ").strip().replace(' ', '')
                    except EOFError:
                        code = ""
                if not code:
                    self.log("[ERROR] Hết hạn chờ OTP — ghi mã vào telegram_otp.txt rồi chạy lại --login")
                    return False
            try:
                await self.client.sign_in(phone=self.phone, code=code, phone_code_hash=sent_code.phone_code_hash)
                self.log("Đăng nhập thành công!")
                me = await self.client.get_me()
                self.log(f"Chào mừng: {me.first_name} (@{me.username})")
                await self.warm_up_cache()
                return True
            except SessionPasswordNeededError:
                self.log("Đang nhập mật khẩu 2FA...")
                pwd = self.twofa or (os.getenv("TELEGRAM_2FA") or "").strip()
                if not pwd:
                    fa_file = os.path.join(ROOT_DIR, "telegram_2fa.txt")
                    if os.path.exists(fa_file):
                        try:
                            with open(fa_file, "r", encoding="utf-8") as f:
                                pwd = f.read().strip()
                        except OSError:
                            pwd = ""
                if not pwd and interactive:
                    try:
                        if sys.stdin and sys.stdin.isatty():
                            pwd = input(f"[{self.name}] Nhập 2FA: ").strip()
                    except EOFError:
                        pwd = ""
                if not pwd:
                    self.log("[ERROR] Cần 2FA — ghi vào telegram_2fa.txt hoặc TELEGRAM_2FA / twofa config")
                    return False
                await self.client.sign_in(password=pwd)
                self.log("Đăng nhập 2FA thành công!")
                await self.warm_up_cache()
                return True
            except PhoneCodeExpiredError:
                self.log("Mã OTP hết hạn, đang thử lại...")
            except PhoneCodeInvalidError:
                self.log("Mã OTP không đúng, vui lòng nhập mã mới...")
            except Exception as e:
                self.log(f"Lỗi: {e}")
                if attempt == max_attempts:
                    raise
        return False

    async def warm_up_cache(self):
        self.dialog_cache = {}
        async for d in self.client.iter_dialogs():
            self.dialog_cache[str(d.id)] = d.entity
            raw = str(d.id)
            if raw.startswith('-100'):
                self.dialog_cache[raw[4:]] = d.entity
                self.dialog_cache[f"-{raw[4:]}"] = d.entity
            elif d.id > 0:
                self.dialog_cache[f"-100{d.id}"] = d.entity
                self.dialog_cache[f"-{d.id}"] = d.entity
            uname = getattr(d.entity, 'username', None)
            if uname:
                self.dialog_cache[uname.lower().lstrip('@')] = d.entity

    async def ensure_connected(self):
        if not self.client:
            self.client = await get_or_create_client(self.session_name, self.api_id, self.api_hash)
        if not self.client.is_connected():
            try:
                await self.client.connect()
            except Exception as e:
                self.log(f"[RECONNECT] Đang kết nối lại Telegram: {e}")

    async def resolve_entity(self, target):
        await self.ensure_connected()
        if not target:
            return None
        target_str = str(target).strip().lower().lstrip('@')
        if target_str in self.dialog_cache:
            return self.dialog_cache[target_str]
        try:
            try:
                return await self.client.get_entity(int(target))
            except (ValueError, TypeError):
                return await self.client.get_entity(target)
        except Exception:
            await self.warm_up_cache()
            return self.dialog_cache.get(target_str)

    def dedicated_preview_group_id(self):
        """Nhóm báo bàn riêng — không trùng nhóm hô/kết quả."""
        raw = self.config.get('table_preview_group_id')
        if not raw:
            return None
        preview = str(raw).strip()
        round_gid = str(self.group_id or '').strip()
        if not preview or preview == round_gid:
            return None
        return preview

    def preview_group_id(self):
        """Nhóm nhận ảnh báo bàn. Báo bàn trước hô thì được gửi vào đúng nhóm round."""
        if self.config.get('table_preview_before_ho') or self.config.get('flow_prior_round'):
            raw = self.config.get('table_preview_group_id') or self.group_id
            return str(raw).strip() if raw else None
        return self.dedicated_preview_group_id()

    async def _forward_order(self, forward_idx, order, delays, label_prefix, default_delay=20):
        order = order or []
        delays = delays or []
        for step_num, idx in enumerate(order):
            await forward_idx(idx, f"{label_prefix} {step_num + 1}/{len(order)}")
            delay = delays[step_num] if step_num < len(delays) else default_delay
            await asyncio.sleep(delay)

    async def _send_preview_shot(self, entity, preview_shot, caption):
        if not preview_shot or not os.path.exists(preview_shot):
            self.log("[SKIP ẢNH BÁO BÀN] Không có ảnh round cũ")
            return False
        try:
            self.log(f"Gửi ảnh báo bàn: {os.path.basename(preview_shot)}")
            await self.client.send_file(entity, preview_shot, caption=caption or None)
            self.audit("Ảnh báo bàn")
            return True
        except Exception as ex:
            self.log(f"[LỖI GỬI ẢNH BÁO BÀN]: {ex}")
            if caption:
                try:
                    await self.client.send_message(entity, caption)
                except Exception:
                    pass
            return False

    async def _execute_prior_round_flow(self, messages_to_send, entity, forward_idx, send_text):
        """
        Luồng: tin1 tin2 → ảnh báo bàn (round cũ) → tin3 → hô 🔵/🔴 ngẫu nhiên
        → ảnh kết quả stamp THẮNG/THUA/HÒA → tin outcome → tin kết thúc.
        Ảo: ảnh kết quả = round cũ. Thật: ảnh kết quả = round mới.
        """
        step = config_step_delay(self.config, 5)
        is_virtual = bool(self.config.get("is_virtual"))
        self.log(
            f"BẮT ĐẦU PHIÊN PRIOR-ROUND "
            f"({'ẢO' if is_virtual else 'THẬT'} | cược {self.bet_amount_label})"
        )

        await self._forward_order(
            forward_idx,
            self.config.get("opening_order", [0, 1]),
            self.config.get("opening_delays", [step, step]),
            "Tin mở đầu",
            step,
        )

        # Báo bàn: nhờ vision chụp LIVE đúng lúc này
        before_m = time.time() - 0.5
        self.log(f"[BÁO BÀN] Request capture live bàn {self.session_table}...")
        request_live_capture(self.session_table, name_service=self.name_service)
        preview_shot = None
        for _ in range(20):
            await asyncio.sleep(0.4)
            cand = get_newest_shot_any(self.session_table, newer_than_mtime=before_m)
            if cand and os.path.exists(cand):
                preview_shot = cand
                break
        if not preview_shot:
            shots = list_main_shots_for_table(self.session_table)
            preview_shot = shots[0][1] if shots else None
            self.log("[BÁO BÀN] Không có capture live — fallback shot disk")

        shots = list_main_shots_for_table(self.session_table)
        old_shot = shots[1][1] if len(shots) >= 2 else (shots[0][1] if shots else None)
        new_shot = shots[0][1] if shots else None
        old_win = shots[1][2] if len(shots) >= 2 else (shots[0][2] if shots else None)
        new_win = shots[0][2] if shots else None

        if self.config.get("send_table_preview", True):
            cap = str(
                self.config.get(
                    "send_table_preview_caption",
                    "🎰 SẢNH SEXY BÀN : {table} 💎",
                )
            ).replace("{table}", self.session_table)
            await self._send_preview_shot(entity, preview_shot or old_shot or new_shot, cap)
            await asyncio.sleep(step)

        await self._forward_order(
            forward_idx,
            self.config.get("opening_after_preview", [2]),
            self.config.get("opening_after_preview_delays", [step]),
            "Tin sau báo bàn",
            step,
        )

        # Hô: khớp winner ảnh round trước (ảo) hoặc ngẫu nhiên (thật / mặc định)
        result_shot = old_shot if is_virtual else (new_shot or old_shot)
        result_win = old_win if is_virtual else (new_win or old_win)
        ho_mode = str(self.config.get("ho_mode") or ("match_shot" if is_virtual else "random")).lower()
        if ho_mode == "match_shot" and result_win in ("B", "P"):
            bet_side = result_win
        else:
            bet_side = random.choice(["B", "P"])
        bet_text_base = "🔵 CON" if bet_side == "P" else "🔴 CÁI"
        bet_text_to_send = format_bet_for_config(self.config, bet_text_base)
        await send_text(bet_text_to_send, f"Đã gửi tin HÔ {bet_text_to_send}")
        await asyncio.sleep(step)

        if not result_shot or not os.path.exists(result_shot):
            # Fallback folder ảo nếu chưa có sexy_*
            outcome_key = random.choices(
                ["WIN", "LOSS", "TIE"],
                weights=[
                    float(self.config.get("win_rate", 0.7)),
                    float(self.config.get("loss_rate", 0.25)),
                    float(self.config.get("tie_rate", 0.05)),
                ],
            )[0]
            result_shot = get_virtual_result_image(bet_side, outcome_key)
            result_win = (
                "T"
                if outcome_key == "TIE"
                else (bet_side if outcome_key == "WIN" else ("P" if bet_side == "B" else "B"))
            )
        else:
            outcome_key = outcome_from_ho_and_winner(bet_side, result_win)

        send_path = result_shot
        if self.config.get("stamp_result_on_image", True):
            send_path = stamp_outcome_on_image(
                result_shot, outcome_key, self.bet_amount_label
            )

        if send_path and os.path.exists(send_path):
            try:
                self.log(
                    f"Gửi ảnh kết quả ({outcome_key}): {os.path.basename(send_path)} "
                    f"(hô={bet_side} winner ảnh={result_win})"
                )
                await self.client.send_file(entity, send_path)
                self.audit(f"Ảnh kết quả stamped {outcome_key}")
            except Exception as ex:
                self.log(f"[LỖI GỬI ẢNH KẾT QUẢ]: {ex}")
        else:
            self.log("[CẢNH BÁO] Không có ảnh kết quả để gửi")

        await asyncio.sleep(step)

        if not self.config.get("result_via_source_messages"):
            result_text = build_virtual_result_for_config(self.config, outcome_key)
            await send_text(result_text, f"Tin kết quả text ({outcome_key})")
            await asyncio.sleep(step)

        if self.config.get("outcome_message_map"):
            await send_post_result_endings(self.config, forward_idx, outcome_key)
        else:
            await self._forward_order(
                forward_idx,
                self.config.get("ending_order", [4]),
                self.config.get("ending_delays", [step]),
                "Tin kết thúc",
                step,
            )

        self.log(
            f"HOÀN THÀNH CA PRIOR-ROUND ({'ẢO' if is_virtual else 'THẬT'}) "
            f"nhóm {self.group_id} | {outcome_key}\n"
        )

    async def execute_round(self, messages_to_send, exclude_tables=None):
        if not self.group_id:
            self.log("[ERROR] Chưa cấu hình group_id cho tài khoản này.")
            return

        if self.is_running_round:
            self.log("[BUSY] Đang trong ca chạy dở, bỏ qua lệnh gọi trùng lặp!")
            return

        await self.ensure_connected()
        entity = await self.resolve_entity(self.group_id)
        if not entity:
            self.log(f"[ERROR] Không tìm thấy nhóm ID={self.group_id}")
            return

        self.is_running_round = True
        try:
            self.log(f"BẮT ĐẦU PHIÊN (Mức cược: {self.bet_amount_label})")

            async def copy_idx(index, label):
                """Gửi lại nội dung (không forward) — timestamp Telegram = lúc bot gửi, không lấy giờ @frezeit."""
                if index >= len(messages_to_send):
                    return
                msg = messages_to_send[index]
                caption = msg.message or getattr(msg, "text", None)

                async def _send_copy():
                    await self.ensure_connected()
                    if msg.media and not isinstance(msg.media, MessageMediaWebPage):
                        await self.client.send_file(
                            entity,
                            msg.media,
                            caption=caption,
                            formatting_entities=msg.entities,
                            silent=True,
                        )
                    elif caption:
                        await self.client.send_message(
                            entity,
                            caption,
                            formatting_entities=msg.entities,
                            silent=True,
                        )
                    elif isinstance(msg.media, MessageMediaWebPage):
                        wp = getattr(msg.media, "webpage", None)
                        fallback = caption
                        if wp:
                            parts = [
                                getattr(wp, "title", None),
                                getattr(wp, "description", None),
                                getattr(wp, "url", None),
                            ]
                            fallback = fallback or "\n".join(p for p in parts if p)
                        if fallback:
                            await self.client.send_message(
                                entity,
                                fallback,
                                silent=True,
                            )

                try:
                    await _send_copy()
                    self.audit(f"{label} (index={index})")
                    self.log(f"{label} (msg_id={msg.id}, index={index})")
                except FloodWaitError as fe:
                    self.log(f"[FLOOD WAIT] Chờ {fe.seconds}s...")
                    await asyncio.sleep(fe.seconds + 1)
                    await _send_copy()
                except Exception as ex:
                    self.log(f"[LỖI COPY index {index}]: {ex}")

            async def forward_idx(index, label):
                await copy_idx(index, label)

            async def send_text(txt, label, parse_mode=None):
                try:
                    await self.ensure_connected()
                    await self.client.send_message(entity, txt, parse_mode=parse_mode)
                    self.audit(label)
                    self.log(f"{label}: {txt}")
                except FloodWaitError as fe:
                    await asyncio.sleep(fe.seconds + 1)
                    await self.ensure_connected()
                    await self.client.send_message(entity, txt, parse_mode=parse_mode)
                except Exception as ex:
                    self.log(f"[LỖI SEND TEXT]: {ex}")

            async def announce_table_round(picked_ns):
                """Báo bàn sau khi đã biết NS/bàn từ main HO."""
                self.log(
                    f"[HO ROUND] NS {picked_ns} bàn {self.session_table} — "
                    f"{'ảo tự hô' if self.config.get('is_virtual') else 'sync main, mirror HÔ vào nhóm'}"
                )

                if self.config.get('send_custom_table_text'):
                    custom_table_text = str(self.config['send_custom_table_text']).replace(
                        '{table}', self.session_table
                    )
                    await send_text(custom_table_text, f"Đã gửi tin báo bàn {self.session_table}")
                    await asyncio.sleep(20)

                if self.config.get('send_table_preview'):
                    target_preview_group = self.preview_group_id()
                    if not target_preview_group:
                        self.log(
                            "[SKIP ẢNH BÁO BÀN] Không có nhóm báo bàn riêng — "
                            "không gửi ảnh bàn vào nhóm hô (tránh 2 ảnh kết quả)"
                        )
                    else:
                        shots = list_main_shots_for_table(self.session_table)
                        newest_name = os.path.basename(shots[0][1]) if shots else '-'
                        if len(shots) < 2:
                            self.log(
                                f"[SKIP ẢNH BÁO BÀN] Chưa có round cũ — "
                                f"ảnh hiện có là round mới {newest_name}"
                            )
                            preview_shot = None
                        else:
                            preview_shot = shots[1][1]
                        caption_template = self.config.get(
                            'send_table_preview_caption',
                            '🎰 SẢNH SEXY BÀN : {table} 💎',
                        )
                        preview_caption = str(caption_template).replace('{table}', self.session_table)
                        target_preview_entity = await self.resolve_entity(target_preview_group)

                        if preview_shot and os.path.exists(preview_shot) and target_preview_entity:
                            try:
                                self.log(
                                    f"Đang gửi ảnh báo bàn ROUND CŨ sang nhóm {target_preview_group}: "
                                    f"{os.path.basename(preview_shot)} "
                                    f"(không gửi round mới {newest_name})"
                                )
                                await self.client.send_file(
                                    target_preview_entity,
                                    preview_shot,
                                    caption=preview_caption,
                                )
                                self.log(
                                    f"✅ Đã báo bàn {self.session_table} ({picked_ns}) "
                                    f"sang nhóm {target_preview_group}"
                                )
                            except Exception as ex:
                                self.log(f"[LỖI GỬI ẢNH BÁO BÀN]: {ex}")
                                await self.client.send_message(target_preview_entity, preview_caption)
                        elif target_preview_entity:
                            await self.client.send_message(target_preview_entity, preview_caption)
                        elif target_preview_group:
                            self.log(
                                f"[SKIP ẢNH BÁO BÀN] Không resolve được nhóm {target_preview_group}"
                            )
                    # Không sleep 20s ở đây — lệnh HÔ đã gửi trước, không được chặn round hô.
                return True

            # Luồng mới: tin1-2 → báo bàn → tin3 → hô → ảnh stamp → outcome → tin5
            if self.config.get("flow_prior_round"):
                try:
                    await self._execute_prior_round_flow(
                        messages_to_send, entity, forward_idx, send_text
                    )
                finally:
                    GLOBAL_BOT_TABLE_CLAIMS.pop(self.bot_id, None)
                    GLOBAL_NS_CLAIMS.pop(self.bot_id, None)
                return

            # NẾU LÀ BOT CHẠY CHẾ ĐỘ ẢO (VIRTUAL / PRESET IMAGES & RATES)
            if self.config.get('is_virtual', False):
                self.log(f"BẮT ĐẦU PHIÊN ẢO (Tỉ lệ Thắng: {float(self.config.get('win_rate', 0.75))*100:.0f}% | Mức cược: {self.bet_amount_label})")

                # 1. Forward các tin mở đầu (Ảnh 5, Ảnh 1, Ảnh 2)
                opening_order = self.config.get('opening_order', [4, 0, 1])
                opening_delays = self.config.get('opening_delays', [20] * len(opening_order))
                for step_num, idx in enumerate(opening_order):
                    await forward_idx(idx, f"Tin mở đầu {step_num + 1}/{len(opening_order)}")
                    delay = opening_delays[step_num] if step_num < len(opening_delays) else 20
                    await asyncio.sleep(delay)

                # Gửi tin chuẩn bị vào lệnh (nếu có cấu hình)
                intro_text = self.config.get('send_intro_text', None)
                if intro_text:
                    await send_text(intro_text, "Đã gửi tin chuẩn bị vào lệnh")
                    await asyncio.sleep(20)

                try:
                    # Quyết định kết quả ảo & cửa cược ngẫu nhiên theo tỉ lệ
                    win_r = float(self.config.get('win_rate', 0.75))
                    loss_r = float(self.config.get('loss_rate', 0.20))
                    tie_r = float(self.config.get('tie_rate', 0.05))
                    outcome_key = random.choices(['WIN', 'LOSS', 'TIE'], weights=[win_r, loss_r, tie_r])[0]
                    bet_side = random.choice(['B', 'P'])
                    ho_label = 'CÁI' if bet_side == 'B' else 'CON'

                    # Lấy ảnh kết quả từ folder ảnh ảo (images/wincai, images/wincon, images/losecai, images/losecon, images/tie)
                    send_shot = get_virtual_result_image(bet_side, outcome_key)

                    self.log(
                        f"[ẢO FOLDER] Hô {ho_label} | Kết quả={outcome_key} | "
                        f"Ảnh={os.path.basename(send_shot) if send_shot else 'None'}"
                    )

                    self.log("Chờ 20s rồi hô...")
                    await asyncio.sleep(20)

                    bet_text_base = "🔵 CON" if bet_side == 'P' else "🔴 CÁI"
                    bet_text_to_send = format_bet_for_config(self.config, bet_text_base)
                    if uses_ho_source_forward(self.config):
                        ho_idx = ho_source_index_for_side(self.config, bet_side)
                        if ho_idx is None:
                            self.log(f"[SKIP CA ẢO] Không map được tin HÔ cho cửa {bet_side}")
                            ending_order = self.config.get('ending_order', [4, 5])
                            ending_delays = self.config.get('ending_delays', [20, 20])
                            for step_num, idx in enumerate(ending_order):
                                await forward_idx(idx, f"Tin kết thúc (tin thứ {idx + 1}, index {idx})")
                                delay = ending_delays[step_num] if step_num < len(ending_delays) else 20
                                await asyncio.sleep(delay)
                            self.log(f"HOÀN THÀNH CA ẢO (skip) NHÓM ({self.group_id})\n")
                            return
                        await forward_idx(
                            ho_idx,
                            f"Tin HÔ ảo (tin thứ {ho_idx + 1}, index {ho_idx})",
                        )
                    else:
                        await send_text(
                            bet_text_to_send,
                            "Đã gửi tin HÔ (Ảo)",
                            parse_mode='html' if uses_html_messages(self.config) else None,
                        )

                    self.log("Chờ 20s rồi gửi ảnh kết quả từ folder ảnh ảo...")
                    await asyncio.sleep(20)

                    if send_shot and os.path.exists(send_shot):
                        try:
                            self.log(
                                f"Đang gửi ảnh kết quả ảo ({outcome_key}): "
                                f"{os.path.basename(send_shot)}..."
                            )
                            await self.client.send_file(entity, send_shot)
                            self.audit(f"Ảnh kết quả ảo folder ({outcome_key})")
                            self.log(f"✅ Đã gửi ảnh kết quả ảo: {os.path.basename(send_shot)}")
                        except Exception as ex:
                            self.log(f"[LỖI GỬI ẢNH KẾT QUẢ ẢO]: {ex}")
                    else:
                        self.log(f"[CẢNH BÁO] Không tìm thấy ảnh trong folder ảo: {send_shot}")

                    await asyncio.sleep(10)

                    result_text = build_virtual_result_for_config(self.config, outcome_key)
                    self.log(
                        f"[XÁC ĐỊNH KẾT QUẢ ẢO] Hô={bet_text_to_send} | "
                        f"outcome={outcome_key} | Tin={result_text}"
                    )
                    if not self.config.get('result_via_source_messages'):
                        await send_text(
                            result_text,
                            f"Đã gửi tin KẾT QUẢ ẢO ({outcome_key}): {result_text}",
                            parse_mode='html' if uses_html_messages(self.config) else None,
                        )
                        await asyncio.sleep(20)
                    else:
                        await asyncio.sleep(8)

                    if self.config.get('outcome_message_map'):
                        await send_post_result_endings(self.config, forward_idx, outcome_key)
                    else:
                        ending_order = self.config.get('ending_order', [4, 5])
                        ending_delays = self.config.get('ending_delays', [20, 20])
                        for step_num, idx in enumerate(ending_order):
                            await forward_idx(idx, f"Tin kết thúc (tin thứ {idx + 1}, index {idx})")
                            delay = ending_delays[step_num] if step_num < len(ending_delays) else 20
                            await asyncio.sleep(delay)

                    self.log(f"HOÀN THÀNH CA ẢO CHO NHÓM ({self.group_id}) THÀNH CÔNG!\n")
                    return
                finally:
                    GLOBAL_BOT_TABLE_CLAIMS.pop(self.bot_id, None)
                    GLOBAL_NS_CLAIMS.pop(self.bot_id, None)
                return

            # 1. Forward tin mở đầu
            opening_order = self.config.get('opening_order', [0, 1, 2, 3])
            opening_delays = self.config.get('opening_delays', [20, 20, 20, 20])
            for step_num, idx in enumerate(opening_order):
                await forward_idx(idx, f"Tin mở đầu {step_num + 1}/{len(opening_order)}")
                delay = opening_delays[step_num] if step_num < len(opening_delays) else 20
                await asyncio.sleep(delay)

            # 2. Báo bàn xong → chờ đúng 20s → mới bắt đầu nghe HÔ main
            preview_first = bool(
                self.config.get('send_table_preview')
                or self.config.get('send_custom_table_text')
                or self.config.get('table_preview_before_ho')
            )
            if preview_first:
                ns0, table0 = await pick_live_main_table(self.bot_id, self.name)
                if ns0 and table0:
                    self.name_service = ns0
                    self.session_table = table0
                    self.last_used_table = table0
                await announce_table_round(self.name_service)
                self.log("Đã báo bàn round cũ — chờ cố định 20s, rồi chờ lệnh HÔ MỚI từ main")
                await asyncio.sleep(20)
            else:
                self.log("Chờ cố định 20s, rồi chờ lệnh HÔ MỚI từ main để bê nguyên sang")
                await asyncio.sleep(20)

            round_listen_ms = int(time.time() * 1000)
            self.log("Hết 20s — đang chờ HÔ mới từ main...")
            ns, table, bet_side, bet_text, main_signal_id, main_signal = (
                await wait_main_ho_any_healthy_ns(
                    self.bot_id,
                    self.name,
                    round_listen_ms,
                    max_wait_s=300,
                    table_name=self.session_table if preview_first else None,
                    name_service=self.name_service if preview_first else None,
                )
            )

            if not main_signal_id:
                self.log(
                    "[SKIP CA] Hết 20s rồi main không hô lệnh mới — không bịa."
                )
                ending_order = self.config.get('ending_order', [4, 5])
                ending_delays = self.config.get('ending_delays', [20, 20])
                for step_num, idx in enumerate(ending_order):
                    await forward_idx(idx, f"Tin kết thúc (tin thứ {idx + 1}, index {idx})")
                    delay = ending_delays[step_num] if step_num < len(ending_delays) else 20
                    await asyncio.sleep(delay)
                self.log(f"HOÀN THÀNH CA (không sync main) NHÓM ({self.group_id})\n")
                return

            self.name_service = ns
            self.session_table = table
            self.last_used_table = table

            consume_main_ho_signal(main_signal_id, consumer=self.bot_id)
            bet_text_to_send = format_bet_for_config(self.config, bet_text)
            norm_bet = normalize_side(main_signal.get("betSide")) or normalize_side(bet_side)
            if uses_ho_source_forward(self.config):
                ho_idx = ho_source_index_for_side(self.config, norm_bet)
                if ho_idx is None:
                    self.log(f"[SKIP CA] Không map tin HÔ nguồn cho cửa {norm_bet}")
                    return
                await forward_idx(
                    ho_idx,
                    f"Tin HÔ main (tin thứ {ho_idx + 1}, index {ho_idx}, signalId={main_signal_id})",
                )
            else:
                await send_text(
                    bet_text_to_send,
                    f"Đã mirror HÔ main {bet_text_to_send} (signalId={main_signal_id})",
                    parse_mode='html' if uses_html_messages(self.config) else None,
                )
            self.log(
                f"[SYNC MAIN] signalId={main_signal_id} {bet_text_to_send} "
                f"— hô theo main {ns}/{table}, ảnh kết quả bê nguyên file main"
            )

            resolved_shot, raw_winner, result_sig = await wait_for_main_ho_result_image(
                main_signal_id, max_wait_s=120
            )
            result_sig = result_sig or {}
            norm_winner = (
                normalize_side(result_sig.get("resultWinner"))
                or normalize_side(raw_winner)
                or shot_winner(resolved_shot)
            )
            outcome_key = str(result_sig.get("resultOutcome") or "").strip().upper()
            if outcome_key not in ("WIN", "LOSS", "TIE"):
                outcome_key = outcome_key_from_real(norm_winner, norm_bet)

            if not resolved_shot or not os.path.exists(resolved_shot) or not outcome_key:
                self.log(
                    f"[LỖI] signalId={main_signal_id} main chưa trả ảnh/kết quả — bỏ tin giả"
                )
                ending_order = self.config.get('ending_order', [4, 5])
                ending_delays = self.config.get('ending_delays', [20, 20])
                for step_num, idx in enumerate(ending_order):
                    await forward_idx(idx, f"Tin kết thúc (tin thứ {idx + 1}, index {idx})")
                    delay = ending_delays[step_num] if step_num < len(ending_delays) else 20
                    await asyncio.sleep(delay)
                self.log(f"HOÀN THÀNH CA (thiếu kết quả main) NHÓM ({self.group_id})\n")
                return

            try:
                self.log(
                    f"Đang bê nguyên ảnh kết quả main (không chụp mới): "
                    f"{os.path.basename(resolved_shot)}..."
                )
                await self.client.send_file(entity, resolved_shot)
                self.audit(f"Ảnh kết quả main signalId={main_signal_id} ({outcome_key})")
                self.log(
                    f"✅ Đã gửi ảnh kết quả main bàn {self.session_table}: "
                    f"{os.path.basename(resolved_shot)}"
                )
            except Exception as ex:
                self.log(f"[LỖI GỬI ẢNH]: {ex}")
                return

            result_text = build_real_result_for_config(
                self.config, norm_winner, norm_bet, outcome=outcome_key
            )
            self.log(
                f"[BÊ MAIN] Hô={bet_text_to_send} | Ảnh={norm_winner} | "
                f"Main={outcome_key} | Tin={result_text}"
            )
            if not self.config.get('result_via_source_messages'):
                await send_text(
                    result_text,
                    f"Đã gửi tin KẾT QUẢ (Ván bàn {self.session_table} ra {norm_winner})",
                    parse_mode='html' if uses_html_messages(self.config) else None,
                )
                await asyncio.sleep(20)
            else:
                await asyncio.sleep(8)

            if self.config.get('outcome_message_map'):
                await send_post_result_endings(self.config, forward_idx, outcome_key)
            else:
                ending_order = self.config.get('ending_order', [4, 5])
                ending_delays = self.config.get('ending_delays', [20, 20])
                for step_num, idx in enumerate(ending_order):
                    await forward_idx(idx, f"Tin kết thúc (tin thứ {idx + 1}, index {idx})")
                    delay = ending_delays[step_num] if step_num < len(ending_delays) else 20
                    await asyncio.sleep(delay)

            self.log(f"HOÀN THÀNH CA CHO NHÓM ({self.group_id}) THEO BÀN {self.session_table} THÀNH CÔNG!\n")
        finally:
            GLOBAL_BOT_TABLE_CLAIMS.pop(self.bot_id, None)
            GLOBAL_NS_CLAIMS.pop(self.bot_id, None)
            self.is_running_round = False

def generate_slots_for_config(interval=10, start_str="10:00", end_str="23:00"):
    slots = []
    sh, sm = map(int, start_str.split(':'))
    eh, em = map(int, end_str.split(':'))
    start_minutes = sh * 60 + sm
    end_minutes = eh * 60 + em
    minutes = start_minutes
    while minutes <= end_minutes:
        hour, minute = divmod(minutes, 60)
        slots.append(f"{hour:02d}:{minute:02d}")
        minutes += interval
    return slots


def generate_slots_from_config(config):
    """Sinh danh sách mốc chạy ca từ config (hỗ trợ nhiều khung giờ)."""
    interval = config.get('interval_minutes', 10)
    windows = config.get('schedule_windows')
    if windows:
        slots = []
        for w in windows:
            slots.extend(
                generate_slots_for_config(
                    interval,
                    w.get('start_time', config.get('start_time', '10:00')),
                    w.get('end_time', config.get('end_time', '23:00')),
                )
            )
        return sorted(set(slots))
    return generate_slots_for_config(
        interval,
        config.get('start_time', '10:00'),
        config.get('end_time', '23:00'),
    )

async def sleep_until_minute_boundary():
    """Ngủ tới đúng giây :00 của phút kế — tránh kích lệch sớm/muộn."""
    now = now_vn()
    delay = 60 - now.second - now.microsecond / 1_000_000
    if delay < 0.05:
        delay += 60
    await asyncio.sleep(delay)


async def launch_bot_round(bot, all_bots, slot_key):
    """Lấy tin nguồn rồi chạy 1 ca. Trả True nếu đã create_task execute_round."""
    bot.current_slot_key = slot_key
    try:
        await bot.ensure_connected()
        source_entity = await bot.resolve_entity(bot.source_username)
        if not source_entity:
            bot.log(f"[ERROR] Không tìm thấy nguồn @{bot.source_username}")
            return False
        messages = []
        need = min_source_messages_for_config(bot.config)
        async for m in bot.client.iter_messages(source_entity, limit=max(need + 4, 20)):
            messages.append(m)
        messages.sort(key=lambda x: x.id)
        if len(messages) < need:
            bot.log(
                f"[WARN] Nguồn @{bot.source_username} chưa đủ {need} tin "
                f"(hiện có {len(messages)}) — bỏ qua ca {slot_key}."
            )
            return False
        other_tables = [
            b.session_table for b in all_bots
            if b != bot and b.is_running_round and b.session_table
        ]
        asyncio.create_task(
            bot.execute_round(messages, exclude_tables=other_tables)
        )
        return True
    except Exception as e:
        bot.log(f"[LỖI TRONG CA]: {e}")
        return False


async def run_single_bot_schedule(bot, all_bots):
    interval = bot.config.get('interval_minutes', 10)
    slots = generate_slots_from_config(bot.config)
    slots_set = set(slots)
    sent_slots = set()

    windows = bot.config.get('schedule_windows')
    if windows:
        parts = [f"{w.get('start_time')}-{w.get('end_time')}" for w in windows]
        bot.log(
            f"Lịch chạy: {', '.join(parts)} (mỗi {interval} phút, {len(slots)} ca/ngày)"
        )
    else:
        bot.log(
            f"Lịch chạy: Từ {slots[0]} đến {slots[-1]} "
            f"(mỗi {interval} phút, {len(slots)} ca/ngày)"
        )
    
    while True:
        await sleep_until_minute_boundary()
        now = now_vn()
        if now.second > 2:
            continue
        time_str = f"{now.hour:02d}:{now.minute:02d}"
        
        launched_now = False
        if time_str in slots_set:
            slot_key = now.strftime('%Y-%m-%d %H:%M')
            if slot_key not in sent_slots:
                sent_slots.add(slot_key)
                if bot.is_running_round:
                    bot.pending_slots.append(slot_key)
                    bot.log(
                        f"[QUEUE] Ca {slot_key} xếp hàng "
                        f"(đang chạy ca trước, sẽ chạy ngay khi xong — không bỏ ca)"
                    )
                else:
                    bot.log(
                        f"Bắt đầu ca {slot_key} (đúng mốc {now.strftime('%H:%M:%S')} GMT+7)..."
                    )
                    await launch_bot_round(bot, all_bots, slot_key)
                    launched_now = True

        if (not launched_now) and (not bot.is_running_round) and bot.pending_slots:
            nxt = bot.pending_slots.pop(0)
            bot.log(f"[QUEUE] Chạy ca xếp hàng {nxt}")
            await launch_bot_round(bot, all_bots, nxt)

        if now.hour == 0 and now.minute == 1:
            sent_slots = set()
            bot.pending_slots = []

async def main():
    parser = argparse.ArgumentParser(description="Multi-Account Telegram Forward Runner")
    parser.add_argument('--account', type=str, help="ID của tài khoản cần chạy (ví dụ bot_forward_1)")
    parser.add_argument('--login', type=str, help="Đăng nhập OTP cho tài khoản cụ thể (ví dụ bot_forward_1 hoặc bot_forward_2)")
    parser.add_argument('--all', action='store_true', help="Chạy toàn bộ tài khoản trong config song song")
    parser.add_argument('--run-now', action='store_true', default=False, help="Chạy ngay 1 ca test khi khởi động")
    args = parser.parse_args()

    accounts = load_accounts_config()
    if not accounts:
        log("[ERROR] Không tìm thấy tài khoản nào trong tele_forward_accounts.json")
        sys.exit(1)

    # Chế độ Login riêng từng tài khoản
    if args.login:
        acc = get_account_by_id(args.login)
        if not acc:
            log(f"[ERROR] Không tìm thấy tài khoản ID '{args.login}' trong tele_forward_accounts.json")
            sys.exit(1)
        bot = TelegramForwardBot(acc)
        await bot.connect_and_login(interactive=True)
        await bot.client.disconnect()
        return

    # Chọn danh sách bot cần chạy
    target_accounts = []
    if args.account:
        acc = get_account_by_id(args.account)
        if not acc:
            log(f"[ERROR] Không tìm thấy tài khoản ID '{args.account}'")
            sys.exit(1)
        target_accounts = [acc]
    else:
        target_accounts = accounts

    log(f"=== KHỞI ĐỘNG HỆ THỐNG FORWARD ĐA SESSION VỚI {len(target_accounts)} TÀI KHOẢN ===")
    bots = []
    failed_ids = []
    for acc in target_accounts:
        b = TelegramForwardBot(acc)
        try:
            ok = await b.connect_and_login(interactive=False)
        except Exception as e:
            b.log(f"[ERROR] Login thất bại: {e}")
            ok = False
        if ok:
            bots.append(b)
        else:
            failed_ids.append(b.bot_id)

    if failed_ids:
        log(
            f"[WARN] {len(failed_ids)} tài khoản chưa login/khóa session: "
            + ", ".join(failed_ids)
        )

    if not bots:
        log("[ERROR] Không có tài khoản nào đăng nhập thành công. Vui lòng đăng nhập trước bằng --login <id>")
        sys.exit(1)

    log(f"=== SẴN SÀNG {len(bots)}/{len(target_accounts)} NHÓM FORWARD ===")

    # Chạy ngay 1 ca test khi khởi động (--run-now hoặc run_now_on_start trong config)
    bots_to_run_now = bots if args.run_now else [b for b in bots if b.config.get('run_now_on_start')]
    if bots_to_run_now:
        log(f"[RUN_NOW] Bắt đầu chạy ngay 1 ca kiểm tra cho {len(bots_to_run_now)} bot...")
        for b in bots_to_run_now:
            if not b.group_id:
                b.log("[WARN] Bỏ qua ca test vì chưa cấu hình group_id.")
                continue
            if b.is_running_round:
                b.log("[WARN] Bot đang chạy ca, bỏ qua run_now.")
                continue
            source_entity = await b.resolve_entity(b.source_username)
            if not source_entity:
                b.log(f"[WARN] Không tìm thấy nguồn @{b.source_username}, bỏ qua run_now.")
                continue
            messages = []
            need = min_source_messages_for_config(b.config)
            async for m in b.client.iter_messages(source_entity, limit=max(need + 4, 20)):
                messages.append(m)
            messages.sort(key=lambda x: x.id)
            if len(messages) < need:
                b.log(
                    f"[WARN] Nguồn @{b.source_username} chưa đủ {need} tin "
                    f"(hiện có {len(messages)}) — bỏ qua run_now."
                )
                continue
            other_tables = [other.session_table for other in bots if other != b and other.session_table]
            b.log(f"[RUN_NOW] Khởi chạy ca test ngay (cần {need} tin nguồn, có {len(messages)}).")
            asyncio.create_task(b.execute_round(messages, exclude_tables=other_tables))

    # Chạy schedule song song độc lập cho từng bot
    tasks = [run_single_bot_schedule(b, bots) for b in bots]
    try:
        await asyncio.gather(*tasks)
    finally:
        for b in bots:
            if b.client and b.client.is_connected():
                await b.client.disconnect()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("Đã dừng runner.")
