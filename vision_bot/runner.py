"""
Vision 24/7 — hoàn thiện theo PLAN.md
Done khi: đặt đúng ô (BET_OK) + chụp đúng lúc ± tiền (SETTLEMENT capture).
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
else:
    print("[!] Cần Windows GUI.")
    sys.exit(1)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import cv2

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_ROOT, ".env"))
except Exception:
    pass

from config_manager import load_config, save_config, VisionLogger
from window_controller import WindowController
from navigator import Navigator
from screen_grabber import ScreenGrabber
from visual_detector import VisualDetector, GameStateMachine
from bridge import VisionBridge
from chrome_launcher import ensure_chrome_up
from settlement import SettlementDetector, save_settlement_capture, get_taskbar_height
from bet_window import BetVerifier, betting_open_score
from login_flow import run_enter_sexy_flow, login_home_url
from shot_store import (
    publish_sexy_shot,
    prune_live_captures,
    clear_step_debug,
    keep_latest_shots,
    migrate_legacy_to_slots,
    KEEP_SHOTS,
)
import random

@dataclass
class HealthWatchdog:
    max_no_window_sec: float = 25.0
    max_stale_sec: float = 180.0
    recover_cooldown_sec: float = 45.0
    max_recovers_per_hour: int = 20
    _no_window_since: float | None = None
    _last_activity: float = field(default_factory=time.time)
    _last_recover: float = 0.0
    _recover_times: list = field(default_factory=list)

    def mark_activity(self) -> None:
        self._last_activity = time.time()
        self._no_window_since = None

    def mark_window_missing(self) -> None:
        if self._no_window_since is None:
            self._no_window_since = time.time()

    def mark_window_ok(self) -> None:
        self._no_window_since = None

    def need_recover(self, has_window: bool, saw_game_signal: bool) -> tuple[bool, str]:
        now = time.time()
        if has_window:
            self.mark_window_ok()
            if saw_game_signal:
                self.mark_activity()
        else:
            self.mark_window_missing()
        if self._last_recover and (now - self._last_recover) < self.recover_cooldown_sec:
            return False, ""
        self._recover_times = [t for t in self._recover_times if now - t < 3600]
        if len(self._recover_times) >= self.max_recovers_per_hour:
            return False, "recover_rate_limited"
        if not has_window and self._no_window_since:
            if now - self._no_window_since >= self.max_no_window_sec:
                return True, "chrome_window_missing"
        if has_window and (now - self._last_activity) >= self.max_stale_sec:
            return True, "game_stale_no_signal"
        return False, ""

    def note_recover(self) -> None:
        now = time.time()
        self._last_recover = now
        self._recover_times.append(now)
        self._no_window_since = None
        self._last_activity = now


def _ensure_capture_dir(config) -> str:
    rel = config.get("capture_dir") or "captures"
    path = rel if os.path.isabs(rel) else os.path.join(_HERE, rel)
    os.makedirs(path, exist_ok=True)
    return path


def _profile_dir(config) -> str:
    rel = config.get("chrome_profile_dir") or "chrome_user_data_vision"
    return rel if os.path.isabs(rel) else os.path.join(_ROOT, rel)


def _game_url(config) -> str:
    url = (config.get("game_url") or "").strip().strip('"').strip("'")
    if url:
        return url
    domain = (os.getenv("DOMAIN") or "").strip().strip('"').strip("'").rstrip("/")
    router = (os.getenv("ROUTER_URL_BACARAT_SEXY") or "/seamless?gameType=LIVE").strip().strip('"')
    if domain:
        return f"{domain}{router}"
    return "https://www.google.com"


def _server_url(config) -> str:
    env_socket = (os.getenv("SOCKET_SERVER_URL") or "").strip().strip('"')
    if env_socket:
        return env_socket.rstrip("/")
    host = (os.getenv("SERVER_HOSTNAME") or "http://127.0.0.1").strip().strip('"').rstrip("/")
    port = (os.getenv("SERVER_PORT") or "3201").strip().strip('"')
    explicit = (config.get("server_url") or "").strip().rstrip("/")
    if explicit and not explicit.endswith(":3000"):
        return explicit
    return f"{host}:{port}"


def _crop_roi(frame, roi):
    if frame is None or not roi:
        return None
    x, y = int(roi["x"]), int(roi["y"])
    w, h = int(roi["width"]), int(roi["height"])
    if y + h > frame.shape[0] or x + w > frame.shape[1] or x < 0 or y < 0:
        return None
    return frame[y : y + h, x : x + w]


def _frame_looks_like_game(frame, config, log=None) -> tuple[bool, str]:
    """Chặn ảnh Cursor/IDE/homepage — chỉ nhận khi đang trên bàn Sexy."""
    if frame is None:
        return False, "frame=None"
    try:
        from step_verify import check_on_table

        ok, detail = check_on_table(frame, config)
        if ok:
            return True, detail
        return False, f"not_on_table|{detail}"
    except Exception as ex:
        return False, f"check_err|{ex}"


def _relock_grab(wc, grabber, target_rect, maximize, profile, nav, win_rect_fallback, log=None):
    """Khóa lại Chrome profile rồi chụp — tránh grab nhầm Cursor/cửa sổ khác."""
    live = None
    try:
        live = lock_window(
            wc, target_rect, retries=3, maximize=maximize, profile_dir=profile
        )
    except Exception as ex:
        if log:
            log.warn(f"relock fail: {ex}")
    if live:
        nav.set_window_rect(live)
        fr = grabber.grab_window(live)
        if fr is not None:
            return live, fr
    fr = grabber.grab_window(win_rect_fallback) if win_rect_fallback else None
    return win_rect_fallback, fr


def _winner_code(label: str) -> str:
    u = str(label or "").upper()
    if u.startswith("B") or u == "BANKER":
        return "B"
    if u.startswith("P") or u == "PLAYER":
        return "P"
    if "TIE" in u or u == "T":
        return "T"
    return "X"


def _infer_winner_from_bet(side, outcome, reason="") -> str:
    """Banner trống → suy winner từ cửa đã hô + WIN+/LOSE- toast."""
    side_u = str(side or "").strip().upper()
    o = str(outcome or "").upper()
    r = str(reason or "").upper()
    if "TIE" in o or r.endswith("_TIE") or "_TIE" in r:
        return "T"
    if side_u not in ("B", "P"):
        return "X"
    won = ("WIN" in o and "TIE" not in o) or "LIVE_WIN" in r or "BUF_WIN" in r or "WATCH_WIN" in r
    lost = (
        "LOSE" in o
        or "LOSS" in o
        or "LIVE_LOSE" in r
        or "BUF_LOSE" in r
        or "WATCH_LOSE" in r
    )
    if won:
        return side_u
    if lost:
        return "P" if side_u == "B" else "B"
    return "X"


def _outcome_key_from_settlement(outcome, reason="") -> str | None:
    """Toast settlement → WIN / LOSS / TIE (caption Telegram)."""
    o = str(outcome or "").upper()
    r = str(reason or "").upper()
    if "TIE" in o or r.endswith("_TIE") or "_TIE" in r:
        return "TIE"
    if "LOSE" in o or "LOSS" in o or "LIVE_LOSE" in r or "BUF_LOSE" in r or "WATCH_LOSE" in r:
        return "LOSS"
    if ("WIN" in o and "TIE" not in o) or "LIVE_WIN" in r or "BUF_WIN" in r or "WATCH_WIN" in r:
        return "WIN"
    return None


def _alert(log: VisionLogger, msg: str) -> None:
    log.warn(msg)
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
    chat = (
        os.getenv("GROUP")
        or os.getenv("GROUP_NS2")
        or os.getenv("ALERT_CHAT_ID")
        or os.getenv("ID_TELEGRAM_RECIPIENT")
        or ""
    ).strip()
    if not token or not chat:
        return
    try:
        import requests

        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": f"[VISION] {msg}"},
            timeout=8,
        )
    except Exception:
        pass


def lock_window(
    wc: WindowController,
    target_rect: dict,
    retries: int = 20,
    maximize: bool = False,
    profile_dir: str | None = None,
):
    for _ in range(retries):
        rect = wc.find_and_setup_window(
            target_x=int(target_rect["x"]),
            target_y=int(target_rect["y"]),
            target_w=int(target_rect["width"]),
            target_h=int(target_rect["height"]),
            maximize=maximize,
            profile_dir=profile_dir,
        )
        if rect:
            return rect
        time.sleep(1.0)
    return None


def full_recover(config, wc, nav, log: VisionLogger, reason: str, grabber=None):
    _alert(log, f"AUTO-RECOVER: {reason}")
    log.event("RECOVER_START", reason)
    target_rect = config.get("window_rect", {"x": 0, "y": 0, "width": 1920, "height": 1080})
    profile = _profile_dir(config)
    if config.get("auto_launch_chrome", True):
        ensure_chrome_up(
            url=login_home_url(config),
            profile_dir=profile,
            chrome_exe=(config.get("chrome_exe") or None) or None,
            force_restart=True,
            wait_sec=float(config.get("chrome_boot_wait_sec") or 12),
            window_w=int(target_rect.get("width") or 1920),
            window_h=int(target_rect.get("height") or 1080),
        )
    win_rect = lock_window(
        wc,
        target_rect,
        retries=25,
        maximize=bool(config.get("maximize_window", False)),
        profile_dir=profile,
    )
    if not win_rect:
        _alert(log, "RECOVER FAIL: no browser window")
        return None
    nav.set_window_rect(win_rect)
    dismiss = config.get("dismiss_steps") or []
    if dismiss:
        nav.execute_sequence(dismiss)
    # Luồng tọa độ: login → Sexy → Chơi ngay → bàn (có STEP verify)
    res = run_enter_sexy_flow(
        nav, win_rect, config, log=log, grabber=grabber, verify=True, recover_on_fail=False, wc=wc
    )
    ok = bool(res.get("ok")) if isinstance(res, dict) else bool(res)
    if ok:
        log.ok("RECOVER_DONE")
    else:
        log.err(f"RECOVER_DONE nhưng enter FAIL step={res.get('failed_step') if isinstance(res, dict) else '?'}")
    return win_rect


def place_and_verify(
    nav: Navigator,
    grabber: ScreenGrabber,
    win_rect: dict,
    config: dict,
    side: str,
    verifier: BetVerifier,
    log: VisionLogger,
    wc=None,
    allow_recover: bool = True,
) -> bool:
    from step_verify import log_step, soft_recover_to_home

    bet_points = config.get("bet_points") or {}
    frame0 = grabber.grab_window(win_rect)
    verifier.snapshot_before(
        _crop_roi(frame0, config.get("roi_zone_banker")),
        _crop_roi(frame0, config.get("roi_zone_player")),
    )
    log.event("BET_CLICK", f"side={side}")
    if not nav.place_bet(bet_points, side):
        log.err("BET_FAIL missing bet_points")
        log_step(log, "bet", False, "missing bet_points")
        return False
    time.sleep(float(config.get("bet_verify_delay_sec") or 0.6))
    frame1 = grabber.grab_window(win_rect)
    result = verifier.verify(
        side,
        _crop_roi(frame1, config.get("roi_zone_banker")),
        _crop_roi(frame1, config.get("roi_zone_player")),
    )
    if result["ok"]:
        log.ok(f"BET_OK side={result['side']} delta={result['delta']} B={result['score_B']} P={result['score_P']}")
        log_step(log, "bet", True, f"delta={result['delta']}")
        return True
    log.warn(
        f"BET_MISS side={result['side']} delta={result['delta']} "
        f"B={result['score_B']} P={result['score_P']} — calibrate lại bet_points/ROI zone"
    )
    log_step(log, "bet", False, f"delta={result['delta']}")

    # Đặt lỗi → kill Chrome + login lại rồi đặt lại 1 lần
    recover_miss = bool((config.get("step_verify") or {}).get("recover_on_bet_miss", True))
    if allow_recover and recover_miss and wc is not None:
        new_rect, rok = soft_recover_to_home(
            config,
            wc,
            nav,
            grabber,
            log,
            reason=f"BET_MISS side={side}",
            hwnd=getattr(wc, "hwnd", None),
            skip_login=False,
        )
        if new_rect:
            nav.set_window_rect(new_rect)
            win_rect = new_rect
        if rok:
            return place_and_verify(
                nav, grabber, win_rect, config, side, verifier, log, wc=wc, allow_recover=False
            )
    return False


def main():
    log = VisionLogger()
    log.info("=" * 60)
    log.info("VISION 24/7 — bet đúng ô + chụp đúng lúc ± tiền")
    log.info(f"Log file: {log.path}")
    log.info("Xem PLAN: vision_bot/PLAN.md")

    config = load_config()
    cfg_path = os.path.join(_HERE, "vision_config.json")
    if not os.path.exists(cfg_path):
        save_config(config)

    capture_dir = _ensure_capture_dir(config)
    # 3 slot: LAST_WIN + CURRENT + PREVIEW; xóa step_debug / legacy
    clear_step_debug((config.get("step_verify") or {}).get("debug_dir"))
    migrate_legacy_to_slots(config.get("table_name") or "C01")
    prune_live_captures(capture_dir, keep=KEEP_SHOTS)
    keep_latest_shots(config.get("table_name") or "C01", keep=KEEP_SHOTS)
    log.info(
        f"Shot store: LAST_WIN + CURRENT + PREVIEW | live={capture_dir}"
    )
    target_rect = config.get("window_rect", {"x": 0, "y": 0, "width": 1920, "height": 1080})
    maximize = bool(config.get("maximize_window", False))
    profile = _profile_dir(config)
    wc = WindowController(keyword=config.get("window_title_keyword", "Google Chrome|Chrome"))
    nav = Navigator()
    grabber = ScreenGrabber()

    # LUÔN dùng Chrome profile vision — không bám Chrome tay khác (mất cookie)
    win_rect = lock_window(wc, target_rect, retries=3, maximize=maximize, profile_dir=profile)
    if not win_rect and config.get("auto_launch_chrome", True):
        log.info(f"Mở Chrome profile vision + trang login: {login_home_url(config)}")
        ensure_chrome_up(
            url=login_home_url(config),
            profile_dir=profile,
            chrome_exe=(config.get("chrome_exe") or None) or None,
            force_restart=False,
            wait_sec=float(config.get("chrome_boot_wait_sec") or 12),
            window_w=int(target_rect.get("width") or 1920),
            window_h=int(target_rect.get("height") or 1080),
        )
        win_rect = lock_window(wc, target_rect, retries=30, maximize=maximize, profile_dir=profile)

    if not win_rect:
        win_rect = full_recover(config, wc, nav, log, "boot_no_browser", grabber=grabber)
    else:
        nav.set_window_rect(win_rect)
        skip = os.environ.get("VISION_SKIP_NAV", "").strip().lower() in ("1", "true", "yes")
        dry = os.environ.get("VISION_DRY_RUN", "").strip().lower() in ("1", "true", "yes")
        if dry:
            log.info("DRY_RUN — khóa browser profile OK, thoát")
            grabber.close()
            return
        if not skip:
            # Chuỗi tọa độ cố định: Đăng nhập → TK/MK → Submit → Sexy → Chơi ngay → Bàn
            log.info("Chạy luồng vào Sexy bằng tọa độ + STEP verify")
            res = run_enter_sexy_flow(
                nav,
                win_rect,
                config,
                log=log,
                grabber=grabber,
                verify=True,
                recover_on_fail=bool((config.get("step_verify") or {}).get("auto_recover", True)),
                wc=wc,
            )
            if isinstance(res, dict) and not res.get("ok"):
                log.err(f"Enter flow FAIL @ {res.get('failed_step')} — HARD recover kill Chrome")
                from step_verify import soft_recover_to_home

                new_rect, _ = soft_recover_to_home(
                    config,
                    wc,
                    nav,
                    grabber,
                    log,
                    reason=f"boot_enter:{res.get('failed_step')}",
                    hwnd=wc.hwnd,
                    skip_login=False,
                )
                if new_rect:
                    win_rect = new_rect
                    nav.set_window_rect(win_rect)

    table_name = str(config.get("table_name") or "C01").upper()
    name_service = str(config.get("name_service") or "NS2").upper()
    pending_bet_side = {"side": None}
    last_vision_bet = {"side": None, "round": None}
    stats = {"bet_ok": 0, "bet_miss": 0, "settlement_cap": 0}
    # Bàn sống — OCR từ màn (Baccarat Cxx), không tin cứng C01
    live_table = {"name": table_name, "last_ocr": 0.0}

    def current_table() -> str:
        return str(live_table.get("name") or table_name or "C01").upper()

    def refresh_live_table(frame, force: bool = False, reason: str = "") -> str:
        """Đọc Baccarat Cxx trên frame → cập nhật live_table + notify server."""
        now = time.time()
        interval = float(config.get("table_ocr_interval_sec") or 12)
        if not force and (now - float(live_table.get("last_ocr") or 0)) < interval:
            return current_table()
        live_table["last_ocr"] = now
        if frame is None:
            return current_table()
        try:
            from table_reader import read_table_from_frame

            detected, detail = read_table_from_frame(frame, config)
        except Exception as ex:
            log.warn(f"TABLE OCR lỗi: {ex}")
            return current_table()
        if not detected:
            if force:
                log.warn(f"TABLE OCR miss ({reason}): {detail}")
            return current_table()
        prev = current_table()
        if detected != prev:
            live_table["name"] = detected
            log.ok(f"TABLE OCR {prev} → {detected} ({reason or 'poll'}) | {detail}")
            try:
                from shot_store import rekey_table_slots

                moved = rekey_table_slots(prev, detected)
                if moved:
                    log.info(f"Shot store rekey {prev}→{detected}: {moved} file(s)")
            except Exception as ex:
                log.warn(f"rekey slots: {ex}")
            try:
                config["table_name"] = detected
                save_config(config)
            except Exception:
                pass
            try:
                bridge.notify_active_table(detected)
            except Exception:
                pass
        elif force or not live_table.get("notified"):
            live_table["notified"] = True
            try:
                bridge.notify_active_table(detected)
            except Exception:
                pass
            if force:
                log.info(f"TABLE OCR confirm {detected} ({reason}) | {detail}")
        return current_table()

    verifier = BetVerifier()
    settlement = SettlementDetector(
        change_threshold=float(config.get("settlement_threshold") or 8.0),
        min_dealing_ms=int(config.get("settlement_min_dealing_ms") or 1500),
        config=config,
    )
    tb = int(config.get("capture_taskbar_px") or get_taskbar_height())
    top_skip = float(config.get("capture_top_skip_frac") or 0.25)
    side_skip = float(config.get("capture_side_skip_frac") or 0.10)
    log.info(
        f"Capture crop: bỏ {int(top_skip*100)}% trên + {int(side_skip*100)}% mỗi bên "
        f"+ taskbar {tb}px"
    )

    def handle_place_bet(data):
        side = data.get("betSide") or data.get("side") or config.get("default_bet_side") or "P"
        pending_bet_side["side"] = side
        live = lock_window(wc, target_rect, retries=3, maximize=maximize, profile_dir=profile) or wc.get_rect() or win_rect
        if live:
            nav.set_window_rect(live)
        ok = place_and_verify(nav, grabber, live, config, side, verifier, log, wc=wc)
        stats["bet_ok" if ok else "bet_miss"] += 1
        if ok:
            last_vision_bet["side"] = side
            tbl = current_table()
            bridge.notify_vision_bet(tbl, side, last_vision_bet.get("round"))
            log.event("VISION_BET_PUBLISH", f"side={side} table={tbl} (socket place_bet)")

    def handle_force_capture(data):
        """Tele báo bàn → chụp Chrome bàn Sexy (không nhận Cursor/IDE)."""
        nonlocal win_rect
        live2, frame = _relock_grab(
            wc, grabber, target_rect, maximize, profile, nav, win_rect or nav.window_rect, log
        )
        if live2:
            win_rect = live2
        if frame is None:
            log.warn("FORCE_CAPTURE skip — grab None")
            return
        ok_g, det = _frame_looks_like_game(frame, config, log)
        if not ok_g:
            log.warn(f"FORCE_CAPTURE skip — không phải bàn game ({det})")
            return
        tbl = refresh_live_table(frame, force=True, reason="force_capture")
        winner = data.get("resultWinner") or ""
        kind = "PREVIEW" if not winner or str(winner).upper() in ("X", "PREVIEW", "") else "RESULT"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(capture_dir, f"FORCE_{tbl}_{kind}_{stamp}.png")
        save_settlement_capture(frame, path, top_skip, tb, side_skip_frac=side_skip)
        if not os.path.exists(path) or os.path.getsize(path) < 200_000:
            log.warn("FORCE_CAPTURE skip — file quá nhỏ / blank")
            return
        pub = publish_sexy_shot(
            path,
            tbl,
            result_winner=winner if kind == "RESULT" else None,
            round_num=data.get("roundNum"),
            kind=kind,
        )
        log.event("FORCE_CAPTURE", f"{pub or path} table={tbl}")
        if kind == "RESULT" and winner:
            bridge.notify_screenshot(tbl, pub or path, winner, data.get("roundNum"))

    bridge = VisionBridge(
        server_url=_server_url(config),
        name_service=name_service,
        on_place_bet=handle_place_bet if config.get("listen_socket_place_bet", True) else None,
        on_force_capture=handle_force_capture,
    )
    if config.get("listen_socket_place_bet", True):
        bridge.start_socket()
        log.info(f"Socket → {_server_url(config)}")
    bridge.notify_active_table(current_table())

    detector = VisualDetector(config.get("color_thresholds"))
    state_machine = GameStateMachine()
    auto_bet = bool(config.get("auto_bet_on_new_round", False))
    auto_bet_random = bool(config.get("auto_bet_random", True))
    default_side = config.get("default_bet_side") or "P"
    dog = HealthWatchdog(
        max_no_window_sec=float(config.get("recover_no_window_sec") or 25),
        max_stale_sec=float(config.get("recover_stale_sec") or 180),
        recover_cooldown_sec=float(config.get("recover_cooldown_sec") or 45),
    )

    log.ok(f"Loop start table={current_table()} ns={name_service}")
    log.info(
        f"DoD: BET_OK + SETTLEMENT | auto_bet={auto_bet} random={auto_bet_random} "
        f"| slots LAST_WIN/LOSS/TIE + CURRENT + PREVIEW | OCR bàn live"
    )
    log.info("-" * 60)
    last_profile_check = 0.0
    last_frame = None

    try:
        while True:
            live = wc.get_rect()
            has_window = live is not None
            if live:
                nav.set_window_rect(live)
                win_rect = live

            frame = grabber.grab_window(win_rect) if win_rect else None
            last_frame = frame
            saw_signal = False
            timer_status = "EMPTY_OR_UNKNOWN"
            result_status = "EMPTY_OR_UNKNOWN"
            bal_c = None

            # Mỗi 30s: chắc hwnd đúng Chrome profile vision
            now = time.time()
            if now - last_profile_check >= 30.0:
                last_profile_check = now
                ok_prof = False
                try:
                    from chrome_launcher import process_uses_profile
                    import win32gui
                    import win32process

                    if wc.hwnd and win32gui.IsWindow(wc.hwnd):
                        _, pid = win32process.GetWindowThreadProcessId(wc.hwnd)
                        ok_prof = process_uses_profile(pid, profile)
                except Exception:
                    ok_prof = False
                if not ok_prof and last_frame is not None:
                    try:
                        from step_verify import check_on_table

                        on_tbl, _ = check_on_table(last_frame, config)
                        if on_tbl:
                            ok_prof = True
                    except Exception:
                        pass
                if not ok_prof:
                    log.warn("HWND lệch profile vision — khóa lại đúng Chrome profile")
                    live2 = lock_window(
                        wc, target_rect, retries=5, maximize=maximize, profile_dir=profile
                    )
                    if live2:
                        win_rect = live2
                        nav.set_window_rect(live2)
                        frame = grabber.grab_window(win_rect)
                        last_frame = frame

            if frame is not None:
                # Đọc mã bàn Baccarat Cxx (định kỳ)
                refresh_live_table(frame, force=False, reason="poll")
                # Cửa đặt: dùng bet_window (HSV neon góc live + Chúc may mắn)
                # — không dùng roi_timer BGR giữa màn (luôn EMPTY → không AUTO_BET).
                sc = betting_open_score(frame, config)
                timer_status = (
                    "TIE_OR_TIMER" if sc.get("open") else "EMPTY_OR_UNKNOWN"
                )
                result_c = _crop_roi(frame, config.get("roi_result"))
                bal_c = _crop_roi(frame, config.get("roi_balance"))
                result_status, _ = detector.detect_color_dominance(result_c)
                if sc.get("open") or float(sc.get("timer_green") or 0) > 0.02 or result_status in (
                    "BANKER",
                    "PLAYER",
                    "TIE_OR_TIMER",
                ):
                    saw_signal = True

            state, event = state_machine.update_state(timer_status, result_status)

            if event:
                et, ed = event
                if et == "NEW_ROUND_START":
                    settlement.reset_round()
                    settlement.on_betting()
                    if frame is not None:
                        refresh_live_table(frame, force=True, reason="new_round")
                    log.event("NEW_ROUND", f"#{ed} table={current_table()}")
                    if auto_bet:
                        if pending_bet_side["side"]:
                            side = pending_bet_side["side"]
                        elif auto_bet_random:
                            side = random.choice(["B", "P"])
                        else:
                            side = default_side
                        pending_bet_side["side"] = None
                        log.info(f"AUTO_BET random/side={side} table={current_table()}")
                        ok = place_and_verify(
                            nav, grabber, win_rect, config, side, verifier, log, wc=wc
                        )
                        stats["bet_ok" if ok else "bet_miss"] += 1
                        if ok:
                            last_vision_bet["side"] = side
                            last_vision_bet["round"] = ed
                            bridge.notify_vision_bet(current_table(), side, ed)
                            log.event(
                                "VISION_BET_PUBLISH",
                                f"side={side} round={ed} table={current_table()}",
                            )
                elif et == "DEALING_STARTED":
                    settlement.on_dealing(bal_c)
                    log.event("DEALING", "arm settlement detector")
                elif et == "RESULT_FOUND":
                    log.event("RESULT_BANNER", str(ed))

            # Chụp ĐÚNG LÚC ± tiền / WIN (mỗi frame, không chỉ khi có event)
            if frame is not None:
                sett = settlement.update(bal_c, result_status, frame=frame)
                if sett:
                    winner = sett.get("banner") or "EMPTY_OR_UNKNOWN"
                    wcode = _winner_code(winner if winner != "EMPTY_OR_UNKNOWN" else "X")
                    if wcode == "X" and state_machine.last_result:
                        wcode = _winner_code(state_machine.last_result)
                    if wcode == "X":
                        wcode = _infer_winner_from_bet(
                            last_vision_bet.get("side"),
                            sett.get("outcome"),
                            sett.get("reason"),
                        )
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    tbl = current_table()
                    path = os.path.join(
                        capture_dir,
                        f"{tbl}_{wcode}_{stamp}_SETTLE.png",
                    )
                    time.sleep(0.5)
                    live2, frame_shot = _relock_grab(
                        wc,
                        grabber,
                        target_rect,
                        maximize,
                        profile,
                        nav,
                        win_rect,
                        log,
                    )
                    if live2:
                        win_rect = live2
                    if frame_shot is None:
                        frame_shot = frame
                    ok_g, det = _frame_looks_like_game(frame_shot, config, log)
                    if not ok_g:
                        log.warn(f"SETTLEMENT skip publish — không phải bàn game ({det})")
                        continue
                    tbl = refresh_live_table(
                        frame_shot, force=True, reason="settlement"
                    )
                    path = os.path.join(
                        capture_dir,
                        f"{tbl}_{wcode}_{stamp}_SETTLE.png",
                    )
                    save_settlement_capture(
                        frame_shot, path, top_skip, tb, side_skip_frac=side_skip
                    )
                    if not os.path.exists(path) or os.path.getsize(path) < 200_000:
                        log.warn("SETTLEMENT skip publish — file quá nhỏ (có thể ảnh Cursor/blank)")
                        continue
                    out_key = _outcome_key_from_settlement(
                        sett.get("outcome"), sett.get("reason")
                    )
                    # Đọc lại toast trên frame vừa chụp — tránh live_lose nhầm khi ảnh rõ WIN+
                    try:
                        from settlement import classify_settlement_frame

                        cls = classify_settlement_frame(frame_shot, config)
                        if cls.get("ok"):
                            frame_key = _outcome_key_from_settlement(
                                cls.get("outcome"), ""
                            )
                            if frame_key and frame_key != out_key:
                                log.warn(
                                    f"SETTLEMENT toast frame≠sett: "
                                    f"sett={out_key} frame={frame_key} ({cls.get('detail')}) "
                                    f"→ dùng frame"
                                )
                                out_key = frame_key
                                w2 = _infer_winner_from_bet(
                                    last_vision_bet.get("side"),
                                    cls.get("outcome"),
                                    "",
                                )
                                if w2 != "X":
                                    wcode = w2
                            elif frame_key:
                                out_key = frame_key
                    except Exception as ex:
                        log.warn(f"SETTLEMENT reclassify skip: {ex}")
                    # LOSS → CURRENT+LAST_LOSS; WIN → CURRENT+LAST_WIN; TIE → LAST_TIE
                    pub = publish_sexy_shot(
                        path,
                        tbl,
                        result_winner=wcode if wcode != "X" else None,
                        round_num=state_machine.round_counter,
                        kind="RESULT",
                        result_outcome=out_key,
                    )
                    stats["settlement_cap"] += 1
                    log.ok(
                        f"SETTLEMENT capture reason={sett['reason']} "
                        f"outcome={sett.get('outcome')} →{out_key} delta={sett['delta']} "
                        f"banner={sett['banner']} wcode={wcode} "
                        f"bet={last_vision_bet.get('side')} table={tbl} → {pub or path}"
                    )
                    notify_win = wcode if wcode != "X" else _winner_code(state_machine.last_result or "")
                    if notify_win in ("B", "P", "T"):
                        bridge.notify_screenshot(
                            tbl,
                            pub or path,
                            notify_win,
                            state_machine.round_counter,
                        )
                    log.info(
                        f"STATS bet_ok={stats['bet_ok']} bet_miss={stats['bet_miss']} "
                        f"settle_cap={stats['settlement_cap']} table={tbl}"
                    )

            if config.get("auto_recover", True):
                need, reason = dog.need_recover(has_window, saw_signal)
                if need and reason != "recover_rate_limited":
                    dog.note_recover()
                    new_rect = full_recover(config, wc, nav, log, reason, grabber=grabber)
                    if new_rect:
                        win_rect = new_rect
                        bridge.notify_active_table(current_table())
                        state_machine = GameStateMachine()
                        settlement = SettlementDetector(
                            change_threshold=float(config.get("settlement_threshold") or 8.0),
                            min_dealing_ms=int(config.get("settlement_min_dealing_ms") or 1500),
                            config=config,
                        )

            time.sleep(0.05)
    except KeyboardInterrupt:
        log.info("Stop Ctrl+C")
        log.info(
            f"FINAL STATS bet_ok={stats['bet_ok']} bet_miss={stats['bet_miss']} "
            f"settle_cap={stats['settlement_cap']}"
        )
    finally:
        grabber.close()


if __name__ == "__main__":
    main()
