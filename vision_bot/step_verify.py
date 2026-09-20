"""
Verify từng bước vision (không chỉ click): page / login / sexy / sảnh / bàn / bet.
Khi FAIL → soft recover: gõ lại URL rồi chạy lại enter flow.
"""
from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Callable

import cv2
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


def _sv(config: dict) -> dict:
    return dict(config.get("step_verify") or {})


def _crop(frame, roi: dict | None):
    if frame is None or not roi:
        return None
    x = int(roi.get("x", 0))
    y = int(roi.get("y", 0))
    w = int(roi.get("width") or roi.get("w") or 0)
    h = int(roi.get("height") or roi.get("h") or 0)
    if w <= 0 or h <= 0:
        return None
    H, W = frame.shape[:2]
    x2, y2 = min(W, x + w), min(H, y + h)
    x, y = max(0, x), max(0, y)
    if x2 <= x or y2 <= y:
        return None
    return frame[y:y2, x:x2]


def _gray_std(img) -> float:
    if img is None or img.size == 0:
        return 0.0
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
    return float(np.std(g))


def _mean_bgr(img) -> tuple[float, float, float]:
    if img is None or img.size == 0:
        return (0.0, 0.0, 0.0)
    m = cv2.mean(img)
    return (float(m[0]), float(m[1]), float(m[2]))


def _frame_diff_ratio(a, b) -> float:
    """Tỉ lệ pixel đổi đáng kể giữa 2 frame (0..1)."""
    if a is None or b is None:
        return 0.0
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]))
    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    d = cv2.absdiff(ga, gb)
    return float(np.mean(d > 18))


def _colorfulness(img) -> float:
    """Hasler–Süsstrunk-ish: sảnh tile thường nhiều màu hơn trang login trắng."""
    if img is None or img.size == 0:
        return 0.0
    b, g, r = cv2.split(img.astype(np.float32))
    rg = np.abs(r - g)
    yb = np.abs(0.5 * (r + g) - b)
    return float(np.sqrt(np.std(rg) ** 2 + np.std(yb) ** 2) + 0.3 * np.sqrt(np.mean(rg) ** 2 + np.mean(yb) ** 2))


def field_roi_from_point(pt: dict | None, w: int = 320, h: int = 44) -> dict | None:
    if not pt or "x" not in pt or "y" not in pt:
        return None
    return {
        "x": max(0, int(pt["x"]) - w // 2),
        "y": max(0, int(pt["y"]) - h // 2),
        "width": w,
        "height": h,
    }


def lobby_roi(config: dict, frame=None) -> dict:
    """Vùng giữa màn — lưới bàn sảnh (không phải header/login)."""
    custom = (config.get("step_verify") or {}).get("roi_lobby")
    if custom and custom.get("width"):
        return custom
    H = int(frame.shape[0]) if frame is not None else 1080
    W = int(frame.shape[1]) if frame is not None else 1920
    return {"x": int(W * 0.12), "y": int(H * 0.22), "width": int(W * 0.76), "height": int(H * 0.55)}


def form_modal_roi(config: dict, frame=None) -> dict:
    custom = (config.get("step_verify") or {}).get("roi_login_form")
    if custom and custom.get("width"):
        return custom
    pts = config.get("login_points") or {}
    u = pts.get("username") or {}
    if u.get("x"):
        return {"x": max(0, int(u["x"]) - 220), "y": max(0, int(u["y"]) - 80), "width": 440, "height": 360}
    H = int(frame.shape[0]) if frame is not None else 1080
    W = int(frame.shape[1]) if frame is not None else 1920
    return {"x": int(W * 0.32), "y": int(H * 0.28), "width": int(W * 0.36), "height": int(H * 0.42)}


def save_step_shot(frame, step: str, config: dict, log=None) -> str | None:
    sv = _sv(config)
    if not sv.get("save_debug", True) or frame is None:
        return None
    rel = sv.get("debug_dir") or "captures/step_debug"
    out_dir = rel if os.path.isabs(rel) else os.path.join(_HERE, rel)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{datetime.now().strftime('%H%M%S_%f')[:-3]}_{step}.png")
    try:
        cv2.imwrite(path, frame)
        if log:
            log.info(f"STEP_SHOT {step} → {path}")
        return path
    except Exception:
        return None


def log_step(log, name: str, ok: bool, detail: str = "") -> None:
    """Ghi STEP_OK / STEP_FAIL rõ ràng để đọc log bắt lỗi."""
    code = "STEP_OK" if ok else "STEP_FAIL"
    msg = f"{name}" + (f" | {detail}" if detail else "")
    if log is None:
        print(f"[{code}] {msg}")
        return
    if ok:
        log.ok(f"{code} {msg}")
        log.event(code, msg)
    else:
        log.err(f"{code} {msg}")
        log.event(code, msg)


def check_page_open(frame, config: dict) -> tuple[bool, str]:
    """Trang đã load (không blank/trắng)."""
    sv = _sv(config)
    if frame is None:
        return False, "frame=None"
    std = _gray_std(frame)
    mn = float(sv.get("page_std_min") or 8.0)
    ok = std >= mn
    return ok, f"frame_std={std:.1f} need>={mn}"


def check_field_changed(before_crop, after_crop, config: dict, label: str) -> tuple[bool, str]:
    """Ô input đổi sau khi gõ (chữ hiện / nền đổi)."""
    sv = _sv(config)
    if before_crop is None or after_crop is None:
        return False, f"{label} crop=None"
    diff = _frame_diff_ratio(before_crop, after_crop)
    # mean cũng đổi khi có chữ
    mb, ma = _mean_bgr(before_crop), _mean_bgr(after_crop)
    mean_d = abs(mb[0] - ma[0]) + abs(mb[1] - ma[1]) + abs(mb[2] - ma[2])
    need = float(sv.get("field_delta_min") or 0.008)
    ok = diff >= need or mean_d >= 4.0
    return ok, f"{label} diff={diff:.4f} meanΔ={mean_d:.1f} need_diff>={need}"


def check_login_ok(frame, before_form, config: dict) -> tuple[bool, str]:
    """
    Đăng nhập OK: form modal phải ĐỔI rõ sau submit VÀ modal trắng gần như biến mất.
    Tránh pass ảo khi chỉ mở/đóng form mà vẫn còn ĐĂNG NHẬP.
    """
    sv = _sv(config)
    if frame is None:
        return False, "frame=None"
    form = _crop(frame, form_modal_roi(config, frame))
    bal = _crop(frame, config.get("roi_balance"))
    bal_std = _gray_std(bal)
    form_diff = _frame_diff_ratio(before_form, form) if before_form is not None else 0.0
    form_std = _gray_std(form)
    need_diff = float(sv.get("login_form_change_min") or 0.12)
    bal_min = float(sv.get("balance_std_min") or 5.0)
    form_white = 0.0
    if form is not None and form.size:
        g = cv2.cvtColor(form, cv2.COLOR_BGR2GRAY)
        form_white = float(np.mean(g > 230))
    white_max = float(sv.get("login_form_white_max") or 0.35)
    # Modal trắng còn chiếm giữa → chưa login xong
    if form_white >= white_max:
        return False, (
            f"form_diff={form_diff:.3f} form_std={form_std:.1f} "
            f"bal_std={bal_std:.1f} form_white={form_white:.2f} (modal còn)"
        )
    if before_form is not None:
        ok = form_diff >= need_diff or (form_diff >= 0.05 and bal_std >= bal_min)
    else:
        ok = bal_std >= bal_min and form_white < white_max
    return ok, (
        f"form_diff={form_diff:.3f} form_std={form_std:.1f} "
        f"bal_std={bal_std:.1f} form_white={form_white:.2f}"
    )


def check_sexy_ok(before, after, config: dict) -> tuple[bool, str]:
    """Click Sexy OK: màn hình đổi rõ (vào lobby/game hub)."""
    sv = _sv(config)
    if after is None:
        return False, "frame=None"
    diff = _frame_diff_ratio(before, after)
    need = float(sv.get("sexy_change_min") or 0.035)
    # Sảnh thường nhiều màu hơn trang chủ
    mid_b = _crop(before, lobby_roi(config, before)) if before is not None else None
    mid_a = _crop(after, lobby_roi(config, after))
    cf_b, cf_a = _colorfulness(mid_b), _colorfulness(mid_a)
    ok = diff >= need or cf_a >= cf_b + 3.0
    return ok, f"diff={diff:.3f} color={cf_b:.1f}→{cf_a:.1f} need_diff>={need}"


def check_lobby_ok(frame, config: dict) -> tuple[bool, str]:
    """
    Sảnh game OK: vùng giữa có lưới bàn — std + colorfulness đủ cao.
    (Click đúng tọa độ nhưng vẫn trang lỗi/login → std thấp / trắng.)
    """
    sv = _sv(config)
    if frame is None:
        return False, "frame=None"
    mid = _crop(frame, lobby_roi(config, frame))
    std = _gray_std(mid)
    cf = _colorfulness(mid)
    std_min = float(sv.get("lobby_std_min") or 12.0)
    cf_min = float(sv.get("lobby_color_min") or 8.0)
    # Không còn form login trắng chiếm giữa
    form = _crop(frame, form_modal_roi(config, frame))
    form_white = 0.0
    if form is not None:
        g = cv2.cvtColor(form, cv2.COLOR_BGR2GRAY)
        form_white = float(np.mean(g > 230))
    # Siết: còn modal login → fail (trước 0.55 dễ dính)
    ok = std >= std_min and cf >= cf_min and form_white < 0.40
    return ok, f"lobby_std={std:.1f} color={cf:.1f} form_white={form_white:.2f}"


def check_on_table(frame, config: dict) -> tuple[bool, str]:
    """Đã vào bàn live: timer xanh / may mắn / status vàng — không tin red đơn độc (homepage false)."""
    from bet_window import betting_open_score, _crop, _timer_roi
    import cv2
    import numpy as np

    if frame is None:
        return False, "frame=None"
    sc = betting_open_score(frame, config)
    tg = float(sc.get("timer_green") or 0)
    lg = float(sc.get("luck_green") or 0)
    yel = float(sc.get("status_yellow") or 0)

    red = 0.0
    t_img = _crop(frame, _timer_roi(config))
    if t_img is not None and t_img.size:
        hsv = cv2.cvtColor(t_img, cv2.COLOR_BGR2HSV)
        r1 = cv2.inRange(hsv, (0, 70, 70), (12, 255, 255))
        r2 = cv2.inRange(hsv, (165, 70, 70), (180, 255, 255))
        red = float(max(r1.mean(), r2.mean()) / 255.0)

    zone = _crop(frame, config.get("roi_zone_player") or {"x": 751, "y": 868, "width": 180, "height": 110})
    zone_std = 0.0
    if zone is not None and zone.size:
        zone_std = float(np.std(cv2.cvtColor(zone, cv2.COLOR_BGR2GRAY)))

    # red chỉ tính khi kèm timer/luck (tránh homepage đỏ → giả on_table)
    ok = tg > 0.015 or lg > 0.08 or yel > 0.04 or (red > 0.04 and (tg > 0.005 or lg > 0.03))
    return ok, f"timer_g={tg:.3f} luck_g={lg:.3f} yel={yel:.3f} red={red:.3f} zone_std={zone_std:.1f}"


def wait_gate(
    grabber,
    win_rect: dict,
    config: dict,
    checker: Callable,
    timeout_sec: float,
    poll: float = 0.4,
    log=None,
    name: str = "gate",
) -> tuple[bool, str, Any]:
    deadline = time.time() + max(0.5, float(timeout_sec))
    last_detail = ""
    frame = None
    while time.time() < deadline:
        frame = grabber.grab_window(win_rect) if grabber and win_rect else None
        ok, detail = checker(frame)
        last_detail = detail
        if ok:
            if log:
                log.info(f"GATE {name} PASS {detail}")
            return True, detail, frame
        time.sleep(poll)
    if log:
        log.warn(f"GATE {name} TIMEOUT {last_detail}")
    return False, last_detail, frame


def soft_recover_to_home(
    config: dict,
    wc,
    nav,
    grabber,
    log,
    reason: str,
    hwnd=None,
    skip_login: bool = False,
) -> tuple[dict | None, bool]:
    """
    HARD recover: kill Chrome profile → launch lại URL → enter FULL (luôn login).
    Không gõ omnibox / không skip login / không Soft URL.
    skip_login bị bỏ qua (giữ param để không vỡ caller cũ).
    """
    from chrome_launcher import ensure_chrome_up
    from login_flow import login_home_url, run_enter_sexy_flow

    url = login_home_url(config)
    rel = config.get("chrome_profile_dir") or "chrome_user_data_vision"
    profile = rel if os.path.isabs(rel) else os.path.join(_ROOT, rel)
    wr = config.get("window_rect") or {}
    ww = int(wr.get("width") or 1920)
    wh = int(wr.get("height") or 1080)

    if log:
        log.event("HARD_RECOVER", f"{reason} → kill Chrome + relaunch {url}")
        log.warn(f"HARD_RECOVER vì: {reason} — restart Chrome toàn bộ rồi login+Sexy từ đầu")
        if skip_login:
            log.info("HARD_RECOVER: bỏ qua skip_login — luôn login lại sau restart")

    ensure_chrome_up(
        url=url,
        profile_dir=profile,
        chrome_exe=(config.get("chrome_exe") or None) or None,
        force_restart=True,
        wait_sec=float(config.get("chrome_boot_wait_sec") or 12),
        window_w=ww,
        window_h=wh,
    )

    win_rect = None
    if wc is not None and hasattr(wc, "find_and_setup_window"):
        for _ in range(25):
            found = wc.find_and_setup_window(
                target_x=int(wr.get("x", 0)),
                target_y=int(wr.get("y", 0)),
                target_w=ww,
                target_h=wh,
                maximize=False,
                profile_dir=profile,
            )
            if found:
                win_rect = found
                break
            time.sleep(0.8)

    if not win_rect:
        if log:
            log.err("HARD_RECOVER FAIL: không lấy được window rect sau restart Chrome")
        return None, False

    if nav is not None:
        nav.set_window_rect(win_rect)

    def _page(f):
        return check_page_open(f, config)

    ok_page, det, frame = wait_gate(
        grabber,
        win_rect,
        config,
        _page,
        timeout_sec=float((_sv(config).get("page_timeout_sec") or 25)),
        log=log,
        name="page_open",
    )
    log_step(log, "page_open", ok_page, det)
    save_step_shot(frame, "recover_page", config, log)
    if not ok_page:
        return win_rect, False

    result = run_enter_sexy_flow(
        nav,
        win_rect,
        config,
        log=log,
        grabber=grabber,
        verify=True,
        recover_on_fail=False,
        skip_login=False,  # luôn login sau kill Chrome
        wc=wc,
    )
    win_rect = wc.get_rect() if wc and hasattr(wc, "get_rect") else win_rect
    if nav is not None and win_rect:
        nav.set_window_rect(win_rect)
    frame = grabber.grab_window(win_rect) if grabber else None
    on_table, tdet = check_on_table(frame, config)
    log_step(log, "on_table_after_recover", on_table, tdet)
    save_step_shot(frame, "recover_table", config, log)
    # Chỉ coi OK khi THẬT sự trên bàn — không tin enter.ok / red giả
    ok = bool(on_table)
    if log:
        if on_table:
            log.ok("HARD_RECOVER_DONE — đã vào bàn")
        else:
            log.err("HARD_RECOVER_DONE nhưng chưa chắc trên bàn")
    return win_rect, ok
