import json
import os
import sys
from datetime import datetime

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "vision_config.json")
_LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")


class VisionLogger:
    """Logger file + console."""

    def __init__(self, prefix: str = "vision"):
        os.makedirs(_LOG_DIR, exist_ok=True)
        day = datetime.now().strftime("%Y%m%d")
        self.path = os.path.join(_LOG_DIR, f"{prefix}_{day}.log")

    def log(self, level: str, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{ts}] [{level}] {msg}"
        try:
            print(line, flush=True)
        except Exception:
            enc = sys.stdout.encoding or "utf-8"
            print(line.encode(enc, errors="replace").decode(enc, errors="replace"), flush=True)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def info(self, msg: str) -> None:
        self.log("INFO", msg)

    def ok(self, msg: str) -> None:
        self.log("OK", msg)

    def warn(self, msg: str) -> None:
        self.log("WARN", msg)

    def err(self, msg: str) -> None:
        self.log("ERR", msg)

    def event(self, code: str, msg: str = "") -> None:
        self.log("EVENT", f"{code} {msg}".strip())

    def step(self, name: str, ok: bool, detail: str = "") -> None:
        code = "STEP_OK" if ok else "STEP_FAIL"
        self.log("OK" if ok else "ERR", f"{code} {name}" + (f" | {detail}" if detail else ""))
        self.event(code, f"{name} {detail}".strip())


DEFAULT_CONFIG = {
    "window_title_keyword": "Google Chrome|Microsoft Edge|Chrome",
    "window_rect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
    "maximize_window": False,
    "auto_launch_chrome": True,
    "auto_navigate": True,
    "auto_recover": True,
    "auto_login": True,
    "account_index": 2,
    "login_url": "",
    "login_wait_sec": 5,
    "auto_bet_on_new_round": False,
    "auto_bet_random": True,
    "default_bet_side": "P",
    "listen_socket_place_bet": True,
    "server_url": "http://127.0.0.1:3201",
    "name_service": "NS1",
    "table_name": "C01",
    "capture_dir": "captures/live",
    "game_url": "",
    "chrome_exe": "",
    "chrome_profile_dir": "chrome_user_data_vision",
    "chrome_boot_wait_sec": 12,
    "recover_no_window_sec": 25,
    "recover_stale_sec": 180,
    "recover_cooldown_sec": 45,
    "settlement_threshold": 8.0,
    "settlement_min_dealing_ms": 1500,
    "bet_verify_delay_sec": 0.6,
    "scroll_after_table": True,
    "scroll_notches": -18,
    "scroll_settle_sec": 1.2,
    "review_capture_dir": "captures/review",
    "dismiss_steps": [],
    "login_points": {
        "open_login": {"x": 1750, "y": 40, "delay_after": 1.2},
        "username": {"x": 960, "y": 420},
        "password": {"x": 960, "y": 500},
        "submit": {"x": 960, "y": 600},
    },
    "roi_timer": {"x": 580, "y": 210, "width": 120, "height": 50},
    "roi_result": {"x": 500, "y": 320, "width": 280, "height": 100},
    "roi_balance": {"x": 1000, "y": 8, "width": 220, "height": 40},
    "roi_zone_banker": {"x": 700, "y": 520, "width": 200, "height": 120},
    "roi_zone_player": {"x": 320, "y": 520, "width": 200, "height": 120},
    "roi_bead_road": {"x": 100, "y": 550, "width": 400, "height": 150},
    "color_thresholds": {
        "banker_red": {"r_min": 170, "g_max": 90, "b_max": 90},
        "player_blue": {"r_max": 90, "g_max": 140, "b_min": 170},
        "tie_green": {"r_max": 90, "g_min": 160, "b_max": 90},
    },
    "navigation_steps": [
        {"name": "5. Click Sexy / Casino", "x": 450, "y": 180, "delay_after": 2.5},
        {"name": "6. Click Chơi ngay", "x": 620, "y": 350, "delay_after": 4.0},
        {"name": "7. Click Chọn Bàn", "x": 300, "y": 420, "delay_after": 3.0},
    ],
    "bet_points": {
        "player": {"x": 841, "y": 923, "description": "Đặt CON"},
        "banker": {"x": 1091, "y": 922, "description": "Đặt CÁI"},
        "confirm": {"x": 1055, "y": 1007, "description": "Xác nhận cược"},
    },
    "step_verify": {
        "enabled": True,
        "save_debug": True,
        "debug_dir": "captures/step_debug",
        "auto_recover": True,
        "recover_on_bet_miss": True,
        "strict_input": False,
        "page_std_min": 8.0,
        "field_delta_min": 0.008,
        "login_ok_wait_sec": 10,
        "sexy_change_min": 0.035,
        "lobby_std_min": 12.0,
        "lobby_color_min": 8.0,
        "on_table_timeout_sec": 25,
        "url_wait_sec": 6.0,
        "no_bet_recover_sec": 60,
    },
}

_MERGE_KEYS = (
    "bet_points",
    "window_rect",
    "roi_timer",
    "roi_result",
    "roi_balance",
    "roi_zone_banker",
    "roi_zone_player",
    "roi_bead_road",
    "color_thresholds",
    "login_points",
)


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = dict(DEFAULT_CONFIG)
            merged.update(data)
            for key in _MERGE_KEYS:
                if isinstance(DEFAULT_CONFIG.get(key), dict) and isinstance(data.get(key), dict):
                    tmp = dict(DEFAULT_CONFIG[key])
                    tmp.update(data[key])
                    merged[key] = tmp
            return merged
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(config_data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=4, ensure_ascii=False)
