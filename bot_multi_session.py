import os
import sys
import json
import re
import sqlite3
import time
import random
import atexit
import ctypes
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import asyncio
from telethon import TelegramClient
from telethon.errors import (
    PasswordHashInvalidError,
    PhoneCodeEmptyError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
    FloodWaitError,
)
from telethon.tl.types import Channel, Chat

# Terminal UTF-8 config on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

# ----------------- SESSION & LOCK CONFIGURATION -----------------
def get_name_service():
    """Lấy tên service hiện tại (NS1, NS2, NS3, NS4) từ biến môi trường."""
    return (os.getenv('NAME_SERVICE') or 'NS1').strip().upper() or 'NS1'

def lock_file_path():
    ns = get_name_service()
    return f'bot_{ns}.lock'

def is_process_running(pid):
    if pid <= 0:
        return False
    if sys.platform == 'win32':
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def ensure_single_instance():
    """Đảm bảo mỗi tiến trình NS (NS1, NS2, NS3, NS4) có lock riêng biệt."""
    lock_path = lock_file_path()
    if os.path.exists(lock_path):
        try:
            with open(lock_path, encoding='utf-8') as f:
                old_pid = int(f.read().strip())
            if is_process_running(old_pid):
                log(f"[ERROR] Bot {lock_path} đang chạy ở PID {old_pid}. Tắt bot cũ trước khi chạy lại.")
                sys.exit(1)
        except (ValueError, OSError):
            pass
    with open(lock_path, 'w', encoding='utf-8') as f:
        f.write(str(os.getpid()))

def release_lock():
    try:
        if os.path.exists(lock_file_path()):
            os.remove(lock_file_path())
    except OSError:
        pass

# ----------------- DIRECTORIES & POST CONFIGURATION -----------------
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'groups_config.json')
POSTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'posts.json')

FIXED_IMAGES_DIR = 'images/fixed'
WINCAI_IMAGES_DIR = 'images/wincai'
LOSECAI_IMAGES_DIR = 'images/losecai'
WINCON_IMAGES_DIR = 'images/wincon'
LOSECON_IMAGES_DIR = 'images/losecon'
TIE_IMAGES_DIR = 'images/tie'

RESULT_IMAGE_DIRS = {
    'wincai': WINCAI_IMAGES_DIR,
    'losecai': LOSECAI_IMAGES_DIR,
    'wincon': WINCON_IMAGES_DIR,
    'losecon': LOSECON_IMAGES_DIR,
    'tie': TIE_IMAGES_DIR,
}
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')

# Schedule & Timezone: 12h00 -> 22h10, mỗi 10 phút
TZ = timezone(timedelta(hours=7))  # GMT+7 (Việt Nam)
SCHEDULE_INTERVAL = int(os.getenv('SCHEDULE_INTERVAL', '10'))
SCHEDULE_START_HOUR, SCHEDULE_START_MINUTE = 12, 0
SCHEDULE_END_HOUR, SCHEDULE_END_MINUTE = 22, 10
sent_slots = set()

# Telegram Credentials
raw_api_id = (os.getenv('API_ID') or '').strip()
api_id = int(raw_api_id) if raw_api_id.isdigit() else 0
api_hash = (os.getenv('API_HASH') or '').strip()
phone = (os.getenv('PHONE') or '').strip().replace(' ', '')
source_username = (os.getenv('SOURCE_USERNAME') or 'frezeit').strip() or 'frezeit'

def session_name_from_phone(phone_number):
    digits = ''.join(c for c in (phone_number or '') if c.isdigit())
    ns = get_name_service().lower()
    return f'user_session_{digits}_{ns}' if digits else f'user_session_{ns}'

SESSION_NAME = session_name_from_phone(phone)
client = None

def get_client():
    global client
    if client is None:
        raise RuntimeError('Telegram client chưa được khởi tạo')
    return client

def configure_sqlite_session(telegram_client):
    session = telegram_client.session
    if hasattr(session, '_cursor'):
        session._cursor()
        if getattr(session, '_conn', None):
            session._conn.execute('PRAGMA busy_timeout=30000')

# ----------------- CONFIG LOADER (GROUPS & SESSIONS) -----------------
def load_session_groups_config():
    """
    Tải cấu hình nhóm cho session hiện tại.
    """
    ns = get_name_service()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                full_config = json.load(f)
                if ns in full_config:
                    ns_conf = full_config[ns]
                    return {
                        'api_base_url': ns_conf.get('api_base_url', 'http://localhost:3201'),
                        'screenshot_dir': ns_conf.get('screenshot_dir', 'public/screenshots'),
                        'groups': ns_conf.get('groups', [])
                    }
        except Exception as e:
            log(f"[WARN] Lỗi đọc {CONFIG_FILE}: {e}. Dùng cấu hình fallback từ .env.")

    # Fallback to .env
    raw_groups = (os.getenv(f'GROUP_{ns}') or os.getenv('GROUP') or '').strip()
    group_ids = [g.strip() for g in re.split(r'[\n,;]+', raw_groups) if g.strip()]
    
    default_groups = []
    # Mặc định theo yêu cầu: index 0-3 là tin 1-4 mở đầu, index 4 là tin kết thúc
    for idx, gid in enumerate(group_ids):
        default_groups.append({
            'name': f"Nhóm {idx + 1} ({ns})",
            'id': gid,
            'opening_order': [0, 1, 2, 3],
            'opening_delays': [10, 10, 10, 10],
            'ending_order': [4],
            'ending_delays': [5]
        })

    return {
        'api_base_url': os.getenv('API_BASE_URL', 'http://localhost:3201'),
        'screenshot_dir': os.getenv('SCREENSHOT_DIR', 'public/screenshots'),
        'groups': default_groups
    }

# ----------------- REAL SCREENSHOT FETCHING & FALLBACK -----------------
def is_real_screenshot_file(filepath):
    """Kiểm tra file screenshot thật từ Puppeteer/Playwright."""
    if not filepath or not os.path.exists(filepath):
        return False
    norm = str(filepath).replace("\\", "/").lower()
    name = os.path.basename(norm)
    if "/images/" in norm and "/screenshots/" not in norm:
        return False
    try:
        if os.path.getsize(filepath) < 40000:
            return False
    except OSError:
        return False
    return ("/screenshots/" in norm) or name.startswith("sexy_") or name.startswith("real_")

def get_latest_local_screenshot(screenshot_dir):
    """Tìm file ảnh mới nhất trong thư mục screenshots của session."""
    if not os.path.exists(screenshot_dir):
        return None
    try:
        files = [
            os.path.join(screenshot_dir, f)
            for f in os.listdir(screenshot_dir)
            if f.lower().endswith(IMAGE_EXTENSIONS) and not f.startswith('.')
        ]
        if not files:
            return None
        files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        for f in files[:5]:
            if is_real_screenshot_file(f):
                return f
    except Exception as e:
        log(f"[WARN] Lỗi quét local screenshot {screenshot_dir}: {e}")
    return None

async def get_session_real_screenshot(api_base_url, screenshot_dir, table_name=None):
    """
    Lấy ảnh thật từ session:
    1. Ưu tiên gọi API Puppeteer latest-screenshot.
    2. Fallback quét file ảnh mới nhất trong thư mục screenshot_dir.
    """
    # 1. Thử gọi API
    if api_base_url:
        try:
            url = f"{api_base_url.rstrip('/')}/api/latest-screenshot"
            if table_name:
                url += f"?tableName={urllib.parse.quote(str(table_name))}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            loop = asyncio.get_event_loop()
            res_text = await loop.run_in_executor(
                None,
                lambda: urllib.request.urlopen(req, timeout=3).read().decode('utf-8')
            )
            res_data = json.loads(res_text)
            if res_data.get('success') and res_data.get('data'):
                filepath = res_data['data'].get('filepath')
                if filepath and os.path.exists(filepath) and is_real_screenshot_file(filepath):
                    log(f"[ẢNH THẬT API] Lấy thành công ảnh: {os.path.basename(filepath)}")
                    return filepath
        except Exception as e:
            pass

    # 2. Quét thư mục ảnh session
    local_path = get_latest_local_screenshot(screenshot_dir)
    if local_path:
        log(f"[ẢNH THẬT LOCAL] Lấy ảnh mới nhất: {os.path.basename(local_path)}")
        return local_path

    return None

def get_fallback_image(result_type):
    """Fallback lấy ảnh từ thư mục images/ nếu session chưa có ảnh thật."""
    target_dir = RESULT_IMAGE_DIRS.get(result_type, WINCAI_IMAGES_DIR)
    if os.path.exists(target_dir):
        files = [
            os.path.join(target_dir, f)
            for f in os.listdir(target_dir)
            if f.lower().endswith(IMAGE_EXTENSIONS) and not f.startswith('.')
        ]
        if files:
            chosen = random.choice(files)
            log(f"[ẢNH FALLBACK] Dùng ảnh dự phòng: {chosen}")
            return chosen
    return None

# ----------------- TELEGRAM HELPER & LOGIN -----------------
async def login_client():
    telegram_client = get_client()
    if not telegram_client.is_connected():
        log('Đang mở kết nối tới Telegram...')
        await telegram_client.connect()
    if await telegram_client.is_user_authorized():
        log('Session đã đăng nhập sẵn.')
        return
    
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        log(f'[INFO] Đang gửi yêu cầu mã OTP lần {attempt}/{max_attempts} tới số {phone}...')
        sent_code = await telegram_client.send_code_request(phone)
        log(f'>>> ĐÃ GỬI MÃ OTP VỀ SỐ {phone}. Vui lòng nhập mã code Telegram:')
        code = input('Nhập mã OTP: ').strip().replace(' ', '')
        try:
            await telegram_client.sign_in(phone=phone, code=code, phone_code_hash=sent_code.phone_code_hash)
            log('[INFO] Đăng nhập thành công!')
            return
        except SessionPasswordNeededError:
            log('[INFO] Tài khoản có 2FA, đang xử lý đăng nhập 2FA...')
            pwd = (os.getenv('TELEGRAM_2FA_PASSWORD') or '').strip()
            if not pwd:
                pwd = input('Nhập mật khẩu 2FA: ').strip()
            await telegram_client.sign_in(password=pwd)
            log('[INFO] Đăng nhập 2FA thành công!')
            return
        except PhoneCodeExpiredError:
            log(f'[WARN] Mã OTP đã hết hạn ({attempt}/{max_attempts}). Đang xin mã mới...')
        except PhoneCodeInvalidError:
            log(f'[WARN] Mã OTP không chính xác ({attempt}/{max_attempts}). Vui lòng nhập đúng mã mới nhất...')
        except Exception as e:
            log(f'[ERROR] Lỗi đăng nhập: {e}')
            if attempt == max_attempts:
                raise

_dialog_cache = {}

async def warm_up_dialog_cache(telegram_client):
    """Quét và cache sẵn toàn bộ nhóm/channel của tài khoản."""
    global _dialog_cache
    _dialog_cache = {}
    async for d in telegram_client.iter_dialogs():
        entity = d.entity
        _dialog_cache[str(d.id)] = entity
        _dialog_cache[str(getattr(entity, 'id', d.id))] = entity
        
        raw_id = str(d.id)
        if raw_id.startswith('-100'):
            _dialog_cache[raw_id[4:]] = entity
            _dialog_cache[f"-{raw_id[4:]}"] = entity
        elif d.id > 0:
            _dialog_cache[f"-100{d.id}"] = entity
            _dialog_cache[f"-{d.id}"] = entity

        uname = getattr(entity, 'username', None)
        if uname:
            _dialog_cache[uname.lower().lstrip('@')] = entity

async def resolve_entity_safe(telegram_client, chat_target):
    """Resolve channel/group entity an toàn và nhanh nhất."""
    target_str = str(chat_target).strip().lower().lstrip('@')
    if target_str in _dialog_cache:
        return _dialog_cache[target_str]
    
    try:
        try:
            return await telegram_client.get_entity(int(chat_target))
        except (ValueError, TypeError):
            return await telegram_client.get_entity(chat_target)
    except Exception:
        # Nếu chưa tìm thấy, refresh lại cache 1 lần
        await warm_up_dialog_cache(telegram_client)
        return _dialog_cache.get(target_str)

# ----------------- SINGLE GROUP EXECUTION -----------------
async def execute_group_round(telegram_client, group_conf, messages_to_send, round_outcome, session_screenshot_path, delay_offset=0):
    """
    Chạy phiên cược cho 1 nhóm theo đúng yêu cầu:
    1. Forward tin 1 -> 4 (index 0, 1, 2, 3) từ @frezeit.
    2. Gửi tin hô text: '🔵 CON' hoặc '🔴 CÁI'.
    3. Gửi ảnh kết quả (ảnh thật từ session hoặc fallback).
    4. Gửi tin kết quả: '🎉 Húp +10%', '❌ Thua -10%', hoặc '🤝 Hòa +0%'.
    5. Gửi tin/ảnh thứ 5 (index 4) từ @frezeit làm tin kết thúc.
    """
    group_id = group_conf.get('id')
    group_name = group_conf.get('name', str(group_id))
    
    if delay_offset > 0:
        await asyncio.sleep(delay_offset)

    entity = await resolve_entity_safe(telegram_client, group_id)
    if not entity:
        log(f"[{group_name}] [ERROR] Không tìm thấy nhóm ID={group_id}")
        return

    log(f"\n>>> [{group_name}] BẮT ĐẦU PHIÊN CHO NHÓM ({group_id})")

    async def forward_idx(index, label):
        if index < len(messages_to_send):
            try:
                await telegram_client.forward_messages(entity, messages_to_send[index], silent=True, drop_author=True)
                log(f"[{group_name}] {label} (msg_id={messages_to_send[index].id}, index={index})")
            except FloodWaitError as fe:
                log(f"[{group_name}] [FLOOD WAIT] Chờ {fe.seconds}s...")
                await asyncio.sleep(fe.seconds + 1)
                await telegram_client.forward_messages(entity, messages_to_send[index], silent=True, drop_author=True)
            except Exception as ex:
                log(f"[{group_name}] [LỖI FORWARD index {index}]: {ex}")

    async def send_text_msg(text_msg, label):
        try:
            await telegram_client.send_message(entity, text_msg)
            log(f"[{group_name}] {label}: {text_msg}")
        except FloodWaitError as fe:
            log(f"[{group_name}] [FLOOD WAIT] Chờ {fe.seconds}s...")
            await asyncio.sleep(fe.seconds + 1)
            await telegram_client.send_message(entity, text_msg)
        except Exception as ex:
            log(f"[{group_name}] [LỖI SEND TEXT]: {ex}")

    # 1. Gửi các tin mở đầu 1-4 (index 0, 1, 2, 3)
    opening_order = group_conf.get('opening_order', [0, 1, 2, 3])
    opening_delays = group_conf.get('opening_delays', [10, 10, 10, 10])
    for step_num, idx in enumerate(opening_order):
        await forward_idx(idx, f"Tin mở đầu {step_num + 1}/{len(opening_order)}")
        delay = opening_delays[step_num] if step_num < len(opening_delays) else 10
        await asyncio.sleep(delay)

    # 2. Tin HÔ: '🔵 CON' hoặc '🔴 CÁI'
    bet_text = round_outcome['bet_text']
    await send_text_msg(bet_text, "Đã gửi tin HÔ")

    await asyncio.sleep(15)

    # 3. Trả ẢNH KẾT QUẢ
    if session_screenshot_path and os.path.exists(session_screenshot_path):
        try:
            await telegram_client.send_file(entity, session_screenshot_path)
            log(f"[{group_name}] Đã gửi ảnh kết quả thật: {os.path.basename(session_screenshot_path)}")
        except Exception as ex:
            log(f"[{group_name}] [LỖI GỬI ẢNH]: {ex}")

    await asyncio.sleep(5)

    # 4. Trả TIN KẾT QUẢ: '🎉 Húp +10%', '❌ Thua -10%', hoặc '🤝 Hòa +0%'
    res_text = round_outcome['result_text']
    await send_text_msg(res_text, "Đã gửi tin KẾT QUẢ")

    await asyncio.sleep(10)

    # 5. Gửi tin/ảnh thứ 5 (index 4) làm kết thúc
    ending_order = group_conf.get('ending_order', [4])
    ending_delays = group_conf.get('ending_delays', [5])
    for step_num, idx in enumerate(ending_order):
        await forward_idx(idx, f"Tin kết thúc (tin thứ {idx + 1}, index {idx})")
        delay = ending_delays[step_num] if step_num < len(ending_delays) else 5
        await asyncio.sleep(delay)

    log(f"<<< [{group_name}] HOÀN THÀNH PHIÊN CHO NHÓM THÀNH CÔNG!\n")

# ----------------- SESSION MASTER DISPATCHER -----------------
async def run_session_round(telegram_client):
    """
    Chạy 1 ca cược cho các nhóm của Session:
    """
    ns = get_name_service()
    conf = load_session_groups_config()
    groups = conf.get('groups', [])

    if not groups:
        log(f"[{ns}] Không có nhóm nào được cấu hình cho {ns}.")
        return

    # Lấy tin nhắn mẫu từ nguồn @frezeit
    source_entity = await resolve_entity_safe(telegram_client, source_username)
    if not source_entity:
        log(f"[{ns}] [ERROR] Không tìm thấy tài khoản nguồn @{source_username}")
        return

    messages_to_send = []
    async for m in telegram_client.iter_messages(source_entity, limit=20):
        messages_to_send.append(m)
    
    # Sắp xếp thứ tự ID tăng dần (theo thứ tự gửi từ 1 -> ...)
    messages_to_send.sort(key=lambda x: x.id)

    if len(messages_to_send) < 5:
        log(f"[{ns}] [WARN] Nguồn @{source_username} mới có {len(messages_to_send)} tin (cần tối thiểu 5 tin: 4 tin mở đầu + 1 tin kết thúc).")
        return

    log(f"\n=======================================================")
    log(f"[{ns}] BẮT ĐẦU CA MỚI CHO {len(groups)} NHÓM DÙNG {ns}")
    log(f"=======================================================")

    # Tạo cược: CON hoặc CÁI
    is_cai = random.choice([True, False])
    bet_text = "🔴 CÁI" if is_cai else "🔵 CON"

    # Kết quả: Thắng (70%), Thua (25%), Hòa (5%)
    rand_res = random.random()
    if rand_res < 0.70:
        is_win, is_tie = True, False
        res_text = "🎉 Húp +10%"
        res_type = "wincai" if is_cai else "wincon"
    elif rand_res < 0.95:
        is_win, is_tie = False, False
        res_text = "❌ Thua -10%"
        res_type = "losecai" if is_cai else "losecon"
    else:
        is_win, is_tie = False, True
        res_text = "🤝 Hòa +0%"
        res_type = "tie"

    round_outcome = {
        'is_cai': is_cai,
        'is_win': is_win,
        'is_tie': is_tie,
        'bet_text': bet_text,
        'result_text': res_text,
        'result_type': res_type
    }

    # Lấy ảnh THẬT từ session (dùng chung cho các nhóm của NS này)
    real_screenshot = await get_session_real_screenshot(
        conf.get('api_base_url'),
        conf.get('screenshot_dir')
    )
    if not real_screenshot:
        real_screenshot = get_fallback_image(res_type)

    # Chạy song song cho các nhóm với delay lệch nhau 0.8s
    tasks = []
    for idx, grp in enumerate(groups):
        offset = idx * 0.8
        tasks.append(execute_group_round(
            telegram_client,
            grp,
            messages_to_send,
            round_outcome,
            real_screenshot,
            delay_offset=offset
        ))

    await asyncio.gather(*tasks, return_exceptions=True)
    log(f"[{ns}] HOÀN THÀNH TOÀN BỘ CA CHO {len(groups)} NHÓM.")

# ----------------- SCHEDULE LOOP -----------------
def generate_daily_slots():
    """Sinh danh sách các mốc giờ từ 12:00 đến 22:10, mỗi 10 phút."""
    slots = []
    start_minutes = SCHEDULE_START_HOUR * 60 + SCHEDULE_START_MINUTE
    end_minutes = SCHEDULE_END_HOUR * 60 + SCHEDULE_END_MINUTE
    
    minutes = start_minutes
    while minutes <= end_minutes:
        hour, minute = divmod(minutes, 60)
        slots.append(f"{hour:02d}:{minute:02d}")
        minutes += SCHEDULE_INTERVAL
    return slots

TIME_SLOTS = generate_daily_slots()
TIME_SLOTS_SET = set(TIME_SLOTS)

async def schedule_loop():
    global sent_slots
    ns = get_name_service()
    log(f"[{ns}] Lịch chạy: Từ {TIME_SLOTS[0]} đến {TIME_SLOTS[-1]} (mỗi {SCHEDULE_INTERVAL} phút, tổng {len(TIME_SLOTS)} ca/ngày)")
    
    while True:
        now = datetime.now(TZ)
        hour = now.hour
        minute = now.minute
        time_str = f"{hour:02d}:{minute:02d}"
        
        if time_str in TIME_SLOTS_SET:
            slot_key = now.strftime('%Y-%m-%d %H:%M')
            if slot_key not in sent_slots:
                log(f"[{ns}] Bắt đầu ca {slot_key}...")
                try:
                    await run_session_round(get_client())
                except Exception as e:
                    log(f"[{ns}] [LỖI TRONG CA]: {e}")
                sent_slots.add(slot_key)

        if hour == 0 and minute == 1:
            sent_slots = set()

        await asyncio.sleep(60 - now.second)

# ----------------- MAIN ENTRY POINT -----------------
async def main():
    global client
    ns = get_name_service()
    ensure_single_instance()
    atexit.register(release_lock)

    log(f"=== KHỞI ĐỘNG BOT TIẾN TRÌNH: {ns} ===")
    if not api_id or not api_hash:
        log("[ERROR] Chưa có API_ID hoặc API_HASH trong .env")
        sys.exit(1)

    client = TelegramClient(SESSION_NAME, api_id, api_hash)
    await login_client()
    configure_sqlite_session(client)
    me = await client.get_me()
    log(f"[{ns}] Đã đăng nhập thành công: {me.first_name} (@{me.username}) | Phone: {phone}")

    conf = load_session_groups_config()
    log(f"[{ns}] Đã nạp {len(conf.get('groups', []))} nhóm | API: {conf.get('api_base_url')}")

    # Chạy ngay 1 ca kiểm tra lúc khởi động để test ngay
    run_now = os.getenv('RUN_NOW', '1').strip().lower() not in ('0', 'false', 'no')
    if run_now:
        log(f"[{ns}] [RUN_NOW=1] Bắt đầu chạy ngay 1 ca kiểm tra lập tức...")
        try:
            await run_session_round(client)
        except Exception as e:
            log(f"[{ns}] [LỖI RUN_NOW]: {e}")

    try:
        await schedule_loop()
    finally:
        await client.disconnect()
        release_lock()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("Đã dừng bot.")
        release_lock()
