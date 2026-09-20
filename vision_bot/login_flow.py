"""
Luồng vào Sexy bằng CHUỖI TỌA ĐỘ (không phụ thuộc cookie):

  Luồng chuẩn:
    load trang xong
    → tắt popup 1
    → login
    → tắt popup 2
    → Sexy
    → phòng chọn bàn

Mỗi bước: log STEP_OK/FAIL + verify ảnh (không tin click mù).
"""
from __future__ import annotations

import os
import time

import pyautogui

from input_click import click_relative, focus_hwnd, type_text_os, foreground_is_hwnd

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05


def _strip(v: str | None) -> str:
    return (v or "").strip().strip('"').strip("'")


def get_credentials(account_index: int = 1) -> tuple[str, str]:
    idx = int(account_index or 1)
    if idx <= 1:
        user = _strip(os.getenv("USERNAME_ACCOUNT"))
        pwd = _strip(os.getenv("PASSWORD_ACCOUNT"))
    else:
        user = _strip(os.getenv(f"USERNAME_ACCOUNT_{idx}"))
        pwd = _strip(os.getenv(f"PASSWORD_ACCOUNT_{idx}"))
    return user, pwd


def _paste_text(text: str, clear_first: bool = True) -> None:
    """Dán text qua clipboard + Ctrl+V (ổn định hơn pyautogui.write)."""
    if clear_first:
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.05)
        pyautogui.press("backspace")
        time.sleep(0.05)
    try:
        import win32clipboard

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(str(text))
        win32clipboard.CloseClipboard()
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)
    except Exception:
        pyautogui.write(str(text), interval=0.03)


def _type_text(text: str, clear_first: bool = True) -> None:
    _paste_text(text, clear_first=clear_first)


def _click_point(win_rect: dict, point: dict | None, name: str, log=None) -> bool:
    if not point or "x" not in point or "y" not in point:
        if log:
            log.warn(f"Thiếu tọa độ '{name}' — calibrate ARM+F8 rồi Lưu")
        return False
    delay = float(point.get("delay_after", 1.0))
    if log:
        log.info(f"CLICK {name} @ Rel ({point['x']},{point['y']}) chờ {delay}s")
    click_relative(win_rect, int(point["x"]), int(point["y"]))
    time.sleep(delay)
    return True


def auto_login(
    nav_window_rect: dict,
    config: dict,
    log=None,
    hwnd=None,
    grabber=None,
    verify: bool = True,
) -> dict:
    """
    Bước 1–4: mở form → gõ TK/MK → submit.
    Trả {"ok": bool, "failed_step": str|None, "steps": {name: ok}}.
    """
    from step_verify import (
        check_field_changed,
        check_login_ok,
        field_roi_from_point,
        form_modal_roi,
        log_step,
        save_step_shot,
        _crop,
    )

    steps: dict[str, bool] = {}

    def _log(msg: str):
        if log:
            log.info(msg)
        else:
            print(f"[LOGIN] {msg}")

    def _fail(step: str, detail: str = "") -> dict:
        steps[step] = False
        log_step(log, step, False, detail)
        return {"ok": False, "failed_step": step, "steps": steps}

    if not config.get("auto_login", True):
        _log("auto_login=false — bỏ qua")
        return {"ok": True, "failed_step": None, "steps": {"auto_login_skip": True}}

    idx = int(config.get("account_index") or 1)
    user, pwd = get_credentials(idx)
    if not user or not pwd:
        return _fail("credentials", f"Thiếu USER/PASS account_index={idx} trong .env")

    points = config.get("login_points") or {}
    for key in ("username", "password", "submit"):
        if key not in points or "x" not in points[key]:
            return _fail(f"login_points.{key}", "Chưa calibrate (ARM + F8)")

    _log(f"=== LOGIN chuỗi tọa độ | account={idx} user={user} ===")
    if hwnd is None:
        try:
            import win32gui

            hwnd = win32gui.GetForegroundWindow()
        except Exception:
            hwnd = None
    focus_hwnd(hwnd)

    def _grab():
        if grabber is None:
            return None
        return grabber.grab_window(nav_window_rect)

    # 1) Nút mở form đăng nhập
    open_btn = points.get("open_login")
    before_open = _grab()
    if open_btn and "x" in open_btn:
        _click_point(nav_window_rect, open_btn, "1.open_login", log)
    else:
        _log("Bỏ open_login (không có tọa độ) — giả sử form đã hiện")
    after_open = _grab()
    if verify and grabber is not None and before_open is not None and after_open is not None:
        from step_verify import _frame_diff_ratio

        diff = _frame_diff_ratio(before_open, after_open)
        # Form có thể đã mở sẵn → chỉ log, không fail
        steps["open_login"] = True
        log_step(log, "open_login", True, f"diff={diff:.3f} (tiếp tục form)")
    else:
        steps["open_login"] = True
        log_step(log, "open_login", True, "clicked/skip")

    focus_hwnd(hwnd)
    time.sleep(0.3)

    # 2) Username
    u = points["username"]
    ux, uy = int(u["x"]), int(u["y"])
    focus_hwnd(hwnd)
    click_relative(nav_window_rect, ux, uy, clicks=1)
    time.sleep(0.55)
    focus_hwnd(hwnd)
    roi_u = field_roi_from_point(u)
    before_u = _crop(_grab(), roi_u) if verify else None
    _log(f"2. Gõ USERNAME → {user}")
    type_text_os(user, clear_first=False, interval=0.06)
    time.sleep(float(u.get("delay_after", 0.6)))
    after_u = _crop(_grab(), roi_u) if verify else None
    if verify and grabber is not None:
        ok_u, det_u = check_field_changed(before_u, after_u, config, "username")
        # Gõ SendInput đôi khi không đổi pixel rõ trên canvas — warn nhưng vẫn fail nếu verify bắt buộc
        strict = bool((config.get("step_verify") or {}).get("strict_input", False))
        if not ok_u and not strict:
            log_step(log, "username_input", True, f"SOFT {det_u} (strict=false — tin đã gõ)")
            steps["username_input"] = True
        elif not ok_u:
            save_step_shot(_grab(), "fail_username", config, log)
            return _fail("username_input", det_u)
        else:
            log_step(log, "username_input", True, det_u)
            steps["username_input"] = True
    else:
        steps["username_input"] = True
        log_step(log, "username_input", True, f"typed={user}")

    # 3) Password
    p = points["password"]
    px, py = int(p["x"]), int(p["y"])
    focus_hwnd(hwnd)
    click_relative(nav_window_rect, px, py, clicks=1)
    time.sleep(0.4)
    roi_p = field_roi_from_point(p)
    before_p = _crop(_grab(), roi_p) if verify else None
    _log("3. Gõ PASSWORD")
    type_text_os(pwd, clear_first=True, interval=0.05)
    time.sleep(float(p.get("delay_after", 0.5)))
    after_p = _crop(_grab(), roi_p) if verify else None
    if verify and grabber is not None:
        ok_p, det_p = check_field_changed(before_p, after_p, config, "password")
        strict = bool((config.get("step_verify") or {}).get("strict_input", False))
        if not ok_p and not strict:
            log_step(log, "password_input", True, f"SOFT {det_p}")
            steps["password_input"] = True
        elif not ok_p:
            save_step_shot(_grab(), "fail_password", config, log)
            return _fail("password_input", det_p)
        else:
            log_step(log, "password_input", True, det_p)
            steps["password_input"] = True
    else:
        steps["password_input"] = True
        log_step(log, "password_input", True, "typed")

    # 4) Submit + verify login OK
    s = dict(points["submit"])
    if "delay_after" not in s:
        s["delay_after"] = float(config.get("login_wait_sec") or 5.0)
    before_form = _crop(_grab(), form_modal_roi(config, _grab())) if verify else None
    focus_hwnd(hwnd)
    _click_point(nav_window_rect, s, "4.submit_dang_nhap", log)

    if verify and grabber is not None:
        wait_sec = float((config.get("step_verify") or {}).get("login_ok_wait_sec") or max(6.0, float(s.get("delay_after", 5))))
        deadline = time.time() + wait_sec
        ok_login = False
        det = ""
        frame = None
        while time.time() < deadline:
            frame = _grab()
            ok_login, det = check_login_ok(frame, before_form, config)
            if ok_login:
                break
            time.sleep(0.5)
        save_step_shot(frame, "after_login", config, log)
        if not ok_login:
            return _fail("login_ok", det)
        log_step(log, "login_ok", True, det)
        steps["login_ok"] = True
    else:
        steps["login_ok"] = True
        log_step(log, "login_ok", True, "submit clicked (no grabber verify)")

    return {"ok": True, "failed_step": None, "steps": steps}


def dismiss_popups(win_rect: dict, config: dict, log=None, tag: str = "dismiss") -> None:
    def _log(msg: str):
        if log:
            log.info(msg)
        else:
            print(f"[DISMISS] {msg}")

    steps = config.get("dismiss_steps") or []
    if not steps:
        _log(f"{tag}: không có dismiss_steps")
        return
    for i, step in enumerate(steps, 1):
        if "x" not in step or "y" not in step:
            continue
        _click_point(win_rect, step, f"{tag}_{i}_{step.get('name', '')}", log)


def run_enter_sexy_flow(
    nav,
    win_rect: dict,
    config: dict,
    log=None,
    grabber=None,
    verify: bool = True,
    recover_on_fail: bool = False,
    wc=None,
    skip_login: bool = False,
) -> dict:
    """
    Luồng chuẩn:
      load xong → tắt popup → login → tắt popup
      → Sexy → phòng → chọn bàn → scroll xuống cuối → (đặt cược ở runner/e2e)

    Trả {"ok": bool, "failed_step": str|None, "steps": {...}}.
    """
    from step_verify import (
        check_lobby_ok,
        check_on_table,
        check_page_open,
        check_sexy_ok,
        log_step,
        save_step_shot,
        soft_recover_to_home,
    )

    out_steps: dict[str, bool] = {}

    def _log(msg: str):
        if log:
            log.info(msg)
        else:
            print(f"[ENTER] {msg}")

    def _grab():
        if grabber is None:
            return None
        return grabber.grab_window(win_rect)

    def _fail(step: str, detail: str = "") -> dict:
        out_steps[step] = False
        log_step(log, step, False, detail)
        frame = _grab()
        save_step_shot(frame, f"fail_{step}", config, log)
        result = {"ok": False, "failed_step": step, "steps": out_steps}
        if recover_on_fail and wc is not None and grabber is not None:
            new_rect, ok = soft_recover_to_home(
                config, wc, nav, grabber, log, reason=f"fail:{step}", hwnd=getattr(wc, "hwnd", None)
            )
            if new_rect:
                win_rect.update(new_rect) if isinstance(win_rect, dict) else None
            result["recovered"] = ok
            result["ok"] = ok
        return result

    do_verify = bool(verify and (config.get("step_verify") or {}).get("enabled", True))
    nav.set_window_rect(win_rect)

    # 0) Page open
    if do_verify and grabber is not None:
        frame0 = _grab()
        ok_p, det_p = check_page_open(frame0, config)
        out_steps["page_open"] = ok_p
        log_step(log, "page_open", ok_p, det_p)
        save_step_shot(frame0, "page_open", config, log)
        if not ok_p:
            return _fail("page_open", det_p)
    else:
        out_steps["page_open"] = True
        log_step(log, "page_open", True, "skip verify")

    # 1) Tắt popup trước login
    _log("=== 1/5 DISMISS trước login ===")
    dismiss_popups(win_rect, config, log=log, tag="pre_login_dismiss")
    time.sleep(0.5)
    out_steps["pre_login_dismiss"] = True
    log_step(log, "pre_login_dismiss", True, "done")

    # 2) Login — skip nếu đã đặt+capture OK trong session (cookie còn)
    if skip_login:
        _log("=== 2/5 LOGIN skip (đã auth session — chỉ Sexy → phòng) ===")
        out_steps["login_ok"] = True
        log_step(log, "login_ok", True, "skip_login=session_authed")
    elif config.get("auto_login", True):
        _log("=== 2/5 LOGIN ===")
        login_res = auto_login(
            win_rect, config, log=log, hwnd=getattr(wc, "hwnd", None) if wc else None, grabber=grabber, verify=do_verify
        )
        out_steps.update(login_res.get("steps") or {})
        if not login_res.get("ok"):
            return _fail(login_res.get("failed_step") or "login_ok", "auto_login failed")
    else:
        _log("=== 2/5 LOGIN skip ===")
        out_steps["login_ok"] = True
        log_step(log, "login_ok", True, "auto_login=false")

    # 3) Tắt popup sau login
    if not skip_login:
        _log("=== 3/5 DISMISS sau login ===")
        dismiss_popups(win_rect, config, log=log, tag="post_login_dismiss")
        time.sleep(0.6)
        out_steps["post_login_dismiss"] = True
        log_step(log, "post_login_dismiss", True, "done")
    else:
        out_steps["post_login_dismiss"] = True
        log_step(log, "post_login_dismiss", True, "skip")

    # 4) Sexy → phòng → chọn bàn (verify từng click quan trọng)
    steps = config.get("navigation_steps") or []
    if steps and config.get("auto_navigate", True):
        _log(f"=== 4/5 NAV {len(steps)} bước: Sexy → phòng → bàn ===")
        for i, step in enumerate(steps, 1):
            name = str(step.get("name") or f"nav_{i}")
            before = _grab() if do_verify else None
            x, y = int(step["x"]), int(step["y"])
            delay = float(step.get("delay_after", 1.5))
            clicks = int(step.get("clicks", 1))
            if log:
                log.info(f"NAV [{i}/{len(steps)}] {name} @ ({x},{y}) chờ {delay}s")
            nav.click_relative(x, y, delay_after=delay, clicks=clicks)
            after = _grab() if do_verify else None
            save_step_shot(after, f"nav_{i}", config, log)

            low = name.lower()
            if do_verify and grabber is not None:
                if i == 1 or "sexy" in low or "casino" in low:
                    ok_s, det_s = check_sexy_ok(before, after, config)
                    # Session recover: trang đã login, Sexy có thể đổi nhẹ hơn
                    if not ok_s and skip_login:
                        from step_verify import _frame_diff_ratio

                        diff = _frame_diff_ratio(before, after)
                        if diff >= 0.015:
                            ok_s, det_s = True, f"SOFT skip_login diff={diff:.3f}"
                    if not ok_s:
                        # Đã vào lobby/hub thì coi Sexy OK
                        ok_l, det_l = check_lobby_ok(after, config)
                        if ok_l:
                            ok_s, det_s = True, f"SOFT via lobby_ok | {det_l}"
                    if not ok_s:
                        # Timer/bàn đã hiện → bỏ qua Sexy
                        ok_t, det_t = check_on_table(after, config)
                        if ok_t:
                            ok_s, det_s = True, f"SOFT via on_table | {det_t}"
                    out_steps["sexy_ok"] = ok_s
                    log_step(log, "sexy_ok", ok_s, det_s)
                    if not ok_s:
                        return _fail("sexy_ok", det_s)
                elif i == 2 or "phòng" in low or "phong" in low or "chơi" in low or "choi" in low:
                    ok_l, det_l = check_lobby_ok(after, config)
                    # phòng chọn bàn đôi khi load chậm — cho thêm chờ
                    if not ok_l:
                        time.sleep(2.0)
                        after = _grab()
                        ok_l, det_l = check_lobby_ok(after, config)
                    out_steps["lobby_ok"] = ok_l
                    log_step(log, "lobby_ok", ok_l, det_l)
                    if not ok_l:
                        return _fail("lobby_ok", det_l)
                elif i >= 3 or "bàn" in low or "ban" in low:
                    # sau chọn bàn: chờ tín hiệu bàn
                    wait_t = float((config.get("step_verify") or {}).get("on_table_timeout_sec") or 20)
                    deadline = time.time() + wait_t
                    ok_t, det_t = False, ""
                    while time.time() < deadline:
                        after = _grab()
                        ok_t, det_t = check_on_table(after, config)
                        if ok_t:
                            break
                        time.sleep(0.5)
                    # chưa thấy timer ngay cũng có thể đang load — warn, fail chỉ nếu vẫn trắng login
                    if not ok_t:
                        ok_l2, det_l2 = check_lobby_ok(after, config)
                        if not ok_l2:
                            out_steps["table_click"] = False
                            return _fail("table_click", f"{det_t} | still_not_lobby={det_l2}")
                        log_step(log, "table_click", True, f"SOFT chưa timer nhưng còn sảnh/load: {det_t}")
                        out_steps["table_click"] = True
                    else:
                        log_step(log, "table_click", True, det_t)
                        out_steps["table_click"] = True
                else:
                    from step_verify import _frame_diff_ratio

                    diff = _frame_diff_ratio(before, after)
                    ok_n = diff >= 0.01
                    tag = f"nav_{i}"
                    out_steps[tag] = ok_n or True
                    log_step(log, tag, True, f"{name} diff={diff:.3f}")
            else:
                tag = f"nav_{i}"
                out_steps[tag] = True
                log_step(log, tag, True, name)
    else:
        _log("=== 4/5 NAV skip ===")
        out_steps["nav_skip"] = True

    # 5) Scroll xuống cuối trang
    if config.get("scroll_after_table", True):
        _log("=== 5/5 SCROLL xuống cuối bàn ===")
        bp = config.get("bet_points") or {}
        focus = bp.get("player") or bp.get("confirm") or {}
        sx = int(focus.get("x") or (win_rect.get("width") or 1920) // 2)
        sy = int(focus.get("y") or int((win_rect.get("height") or 1080) * 0.55))
        notches = int(config.get("scroll_notches") or -18)
        nav.scroll_to_bottom(rel_x=sx, rel_y=max(400, sy - 80), notches=notches)
        time.sleep(float(config.get("scroll_settle_sec") or 1.2))
        out_steps["scroll"] = True
        log_step(log, "scroll", True, f"notches={notches}")
    else:
        _log("=== 5/5 SCROLL skip ===")

    # 6) Tắt popup tin nhắn góc phải trên bàn
    table_pop = config.get("table_popup_dismiss_steps") or []
    if table_pop:
        _log("=== 6/6 DISMISS popup tin nhắn trên bàn ===")
        for i, step in enumerate(table_pop, 1):
            if "x" not in step or "y" not in step:
                continue
            _click_point(win_rect, step, f"table_popup_{i}_{step.get('name', '')}", log)
        time.sleep(0.4)

    # Final on_table check — chưa vào bàn thật thì FAIL (hard recover kill Chrome)
    if do_verify and grabber is not None:
        frame_f = _grab()
        ok_t, det_t = check_on_table(frame_f, config)
        if not ok_t:
            wait_t = float((config.get("step_verify") or {}).get("on_table_timeout_sec") or 20)
            deadline = time.time() + min(15.0, wait_t)
            while time.time() < deadline and not ok_t:
                time.sleep(0.5)
                frame_f = _grab()
                ok_t, det_t = check_on_table(frame_f, config)
        if not ok_t:
            out_steps["on_table"] = False
            return _fail("on_table", det_t)
        out_steps["on_table"] = True
        log_step(log, "on_table", True, det_t)
        save_step_shot(frame_f, "on_table", config, log)

    _log("Xong luồng chuẩn (… → bàn → scroll)")
    return {"ok": True, "failed_step": None, "steps": out_steps}


def login_home_url(config: dict) -> str:
    explicit = _strip(config.get("login_url"))
    if explicit:
        return explicit
    domain = _strip(os.getenv("DOMAIN")).rstrip("/")
    if domain:
        return domain
    return "https://www.google.com"
