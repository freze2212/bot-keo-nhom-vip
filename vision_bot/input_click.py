"""Click chuột cấp OS (SendInput) — không gắn CDP/Playwright vào browser."""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

# Prefer SendInput so Chrome canvas nhận input như chuột thật.
user32 = ctypes.windll.user32

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT(ctypes.Structure):
    class _I(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    _fields_ = [("type", wintypes.DWORD), ("i", _I)]


def _to_absolute(x: int, y: int) -> tuple[int, int]:
    screen_w = max(user32.GetSystemMetrics(0), 1)
    screen_h = max(user32.GetSystemMetrics(1), 1)
    abs_x = int(x * 65535 / screen_w)
    abs_y = int(y * 65535 / screen_h)
    return abs_x, abs_y


def move_to(x: int, y: int) -> None:
    ax, ay = _to_absolute(int(x), int(y))
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.i.mi = MOUSEINPUT(ax, ay, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, None)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def click_at(x: int, y: int, clicks: int = 1, move_pause: float = 0.05) -> None:
    """Di chuyển + click trái tại tọa độ màn hình tuyệt đối."""
    move_to(x, y)
    time.sleep(move_pause)
    for _ in range(max(1, int(clicks))):
        down = INPUT()
        down.type = INPUT_MOUSE
        down.i.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, None)
        up = INPUT()
        up.type = INPUT_MOUSE
        up.i.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, None)
        user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
        time.sleep(0.03)
        user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
        time.sleep(0.05)


def click_relative(window_rect: dict | None, rel_x: int, rel_y: int, clicks: int = 1) -> tuple[int, int]:
    if not window_rect:
        abs_x, abs_y = int(rel_x), int(rel_y)
    else:
        abs_x = int(window_rect["left"]) + int(rel_x)
        abs_y = int(window_rect["top"]) + int(rel_y)
    click_at(abs_x, abs_y, clicks=clicks)
    return abs_x, abs_y


def scroll_at(x: int, y: int, notches: int = -8, pause: float = 0.08) -> None:
    """
    Lăn chuột tại (x,y). notches âm = xuống, dương = lên.
    Mỗi notch ≈ 120 WHEEL_DELTA.
    """
    move_to(x, y)
    time.sleep(0.05)
    direction = -1 if notches < 0 else 1
    for _ in range(abs(int(notches))):
        inp = INPUT()
        inp.type = INPUT_MOUSE
        # mouseData: signed wheel delta as DWORD
        delta = ctypes.c_long(direction * WHEEL_DELTA).value & 0xFFFFFFFF
        inp.i.mi = MOUSEINPUT(0, 0, delta, MOUSEEVENTF_WHEEL, 0, None)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        time.sleep(pause)


def scroll_relative(window_rect: dict | None, rel_x: int, rel_y: int, notches: int = -10) -> None:
    if not window_rect:
        abs_x, abs_y = int(rel_x), int(rel_y)
    else:
        abs_x = int(window_rect["left"]) + int(rel_x)
        abs_y = int(window_rect["top"]) + int(rel_y)
    scroll_at(abs_x, abs_y, notches=notches)


def focus_hwnd(hwnd) -> None:
    """Đưa cửa sổ browser lên trước khi gõ (tránh input vào Cursor/terminal)."""
    if not hwnd:
        return
    try:
        user32.ShowWindow(int(hwnd), 9)  # SW_RESTORE
        user32.SetForegroundWindow(int(hwnd))
        time.sleep(0.2)
    except Exception:
        pass


def type_text_os(text: str, clear_first: bool = True, interval: float = 0.045) -> None:
    """Gõ ASCII bằng keybd_event — ổn định hơn pyautogui trên ô input web."""
    import win32api
    import win32con

    if clear_first:
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(ord("A"), 0, 0, 0)
        time.sleep(0.03)
        win32api.keybd_event(ord("A"), 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.05)
        win32api.keybd_event(win32con.VK_BACK, 0, 0, 0)
        win32api.keybd_event(win32con.VK_BACK, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.08)

    for ch in str(text):
        vk = win32api.VkKeyScan(ch)
        if vk == -1:
            continue
        code = vk & 0xFF
        shift = bool(vk & 0x100)
        if shift:
            win32api.keybd_event(win32con.VK_SHIFT, 0, 0, 0)
        win32api.keybd_event(code, 0, 0, 0)
        time.sleep(0.012)
        win32api.keybd_event(code, 0, win32con.KEYEVENTF_KEYUP, 0)
        if shift:
            win32api.keybd_event(win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(interval)


# --- Keyboard (navigate URL, tránh about:blank) ---
def focus_omnibox_and_goto(url: str) -> None:
    """Ctrl+L → gõ URL → Enter (tab hiện tại, không tạo about:blank)."""
    import win32api
    import win32con

    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    time.sleep(0.05)
    win32api.keybd_event(ord("L"), 0, 0, 0)
    time.sleep(0.05)
    win32api.keybd_event(ord("L"), 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.3)
    # gõ URL qua clipboard + Ctrl+V (ổn định hơn Unicode SendInput)
    try:
        import win32clipboard

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(url)
        win32clipboard.CloseClipboard()
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(ord("V"), 0, 0, 0)
        time.sleep(0.05)
        win32api.keybd_event(ord("V"), 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
    except Exception:
        for ch in url:
            vk = win32api.VkKeyScan(ch)
            if vk == -1:
                continue
            win32api.keybd_event(vk & 0xFF, 0, 0, 0)
            win32api.keybd_event(vk & 0xFF, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.01)
    time.sleep(0.15)
    win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
    time.sleep(0.05)
    win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)

