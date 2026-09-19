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
    Đăng nhập OK: form modal mờ/đổi mạnh HOẶC header balance có nội dung
    (không còn đứng yên form trắng).
    """
    sv = _sv(config)
    if frame is None:
        return False, "frame=None"
    form = _crop(frame, form_modal_roi(config, frame))
    bal = _crop(frame, config.get("roi_balance"))
    bal_std = _gray_std(bal)
    form_diff = _frame_diff_ratio(before_form, form) if before_form is not None else 0.0
    form_std = _gray_std(form)
    # Form trắng thường std thấp; sau login trang home std cao hơn hoặc form biến mất
    need_diff = float(sv.get("login_form_change_min") or 0.06)
    bal_min = float(sv.get("balance_std_min") or 5.0)
    ok = form_diff >= need_diff or bal_std >= bal_min or form_std >= 25.0
    return ok, f"form_diff={form_diff:.3f} form_std={form_std:.1f} bal_std={bal_std:.1f}"


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
    ok = std >= std_min and cf >= cf_min and form_white < 0.55
    return ok, f"lobby_std={std:.1f} color={cf:.1f} form_white={form_white:.2f}"


def check_on_table(frame, config: dict) -> tuple[bool, str]:
    """Đã vào bàn live: timer xanh / may mắn / đang mở bài."""
    from bet_window import betting_open_score

    if frame is None:
        return False, "frame=None"
    sc = betting_open_score(frame, config)
    tg = float(sc.get("timer_green") or 0)
    lg = float(sc.get("luck_green") or 0)
    yel = float(sc.get("status_yellow") or 0)
    ok = tg > 0.01 or lg > 0.01 or yel > 0.05
    return ok, f"timer_g={tg:.3f} luck_g={lg:.3f} yel={yel:.3f}"


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
    Soft recover: KHÔNG kill Chrome — focus → gõ lại URL → chờ page_open → enter Sexy.
    skip_login=True: đã đặt+capture OK → không gõ TK/MK, chỉ Sexy → phòng → bàn.
    Trả (win_rect, on_table_ok).
    """
    from chrome_launcher import navigate_chrome_to_url
    from input_click import focus_hwnd
    from login_flow import login_home_url, run_enter_sexy_flow

    url = login_home_url(config)
    if log:
        mode = "skip_login→Sexy" if skip_login else "full_login"
        log.event("SOFT_RECOVER", f"{reason} → URL {url} ({mode})")
        log.warn(
            f"SOFT_RECOVER vì: {reason} — nhập lại URL rồi "
            + ("Sexy→phòng (không login)" if skip_login else "login+Sexy từ đầu")
        )

    try:
        if hwnd is None and wc is not None:
            hwnd = getattr(wc, "hwnd", None)
        focus_hwnd(hwnd)
    except Exception:
        pass

    navigate_chrome_to_url(url, wait_sec=float((_sv(config).get("url_wait_sec") or 6.0)))
    time.sleep(1.0)

    profile = None
    try:
        rel = config.get("chrome_profile_dir") or "chrome_user_data_vision"
        profile = rel if os.path.isabs(rel) else os.path.join(_HERE, rel)
    except Exception:
        profile = None

    win_rect = None
    if wc is not None:
        win_rect = wc.get_rect() if hasattr(wc, "get_rect") else None
        if hasattr(wc, "find_and_setup_window"):
            wr = config.get("window_rect") or {}
            found = wc.find_and_setup_window(
                target_x=int(wr.get("x", 0)),
                target_y=int(wr.get("y", 0)),
                target_w=int(wr.get("width", 1920)),
                target_h=int(wr.get("height", 1080)),
                maximize=False,
                profile_dir=profile,
            )
            if found:
                win_rect = found

    if not win_rect:
        if log:
            log.err("SOFT_RECOVER FAIL: không lấy được window rect")
        return None, False

    if nav is not None:
        nav.set_window_rect(win_rect)

    # Chờ trang mở
    def _page(f):
        return check_page_open(f, config)

    ok_page, det, frame = wait_gate(
        grabber,
        win_rect,
        config,
        _page,
        timeout_sec=float((_sv(config).get("page_timeout_sec") or 20)),
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
        recover_on_fail=False,  # tránh đệ quy
        skip_login=skip_login,
    )
    win_rect = wc.get_rect() if wc and hasattr(wc, "get_rect") else win_rect
    if nav is not None and win_rect:
        nav.set_window_rect(win_rect)
    frame = grabber.grab_window(win_rect) if grabber else None
    on_table, tdet = check_on_table(frame, config)
    log_step(log, "on_table_after_recover", on_table, tdet)
    save_step_shot(frame, "recover_table", config, log)
    # Ưu tiên đã vào bàn — dù enter báo fail giữa chừng (sexy gate)
    ok = on_table or bool(result.get("ok") if isinstance(result, dict) else result)
    if log:
        if on_table:
            log.ok("SOFT_RECOVER_DONE — đã vào bàn")
        elif ok:
            log.ok("SOFT_RECOVER_DONE — enter ok (chưa timer)")
        else:
            log.err("SOFT_RECOVER_DONE nhưng chưa chắc trên bàn")
    return win_rect, ok
