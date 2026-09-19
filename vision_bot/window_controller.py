"""Tìm cửa sổ Chrome/Edge THẬT — bỏ qua cửa sổ CMD/BAT có chữ Chrome trong title."""
from __future__ import annotations

import time

import pygetwindow as gw
import win32con
import win32gui
import win32process

# Title chứa các từ này → KHÔNG phải browser game
_EXCLUDE_TITLE = (
    "vision bot",
    "vision 24",
    "vision-24",
    "vision_24",
    "self-check",
    "calibrate",
    "cmd.exe",
    "powershell",
    "windows terminal",
    "cursor",
    "visual studio",
    "chay_",
    ".bat",
    "administrator:",
)

_BROWSER_CLASSES = (
    "chrome_widgetwin_1",  # Chrome / Edge / Chromium
    "mozillaWindowClass".lower(),
)


def _title_excluded(title: str) -> bool:
    t = (title or "").lower()
    return any(x in t for x in _EXCLUDE_TITLE)


def _is_browser_hwnd(hwnd) -> bool:
    try:
        cls = (win32gui.GetClassName(hwnd) or "").lower()
    except Exception:
        return False
    if cls in _BROWSER_CLASSES or cls.startswith("chrome_widgetwin"):
        return True
    # fallback: process name
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        import psutil

        name = (psutil.Process(pid).name() or "").lower()
        return name in ("chrome.exe", "msedge.exe", "brave.exe", "chromium.exe")
    except Exception:
        return False


class WindowController:
    def __init__(self, keyword="Google Chrome"):
        self.keyword = keyword
        self.hwnd = None
        self.window = None

    def list_all_windows(self):
        windows = []

        def enum_handler(hwnd, _extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                if title:
                    windows.append((hwnd, title))

        win32gui.EnumWindows(enum_handler, None)
        return windows

    def list_browser_candidates(self, keyword=None, profile_dir: str | None = None):
        kw = (keyword or self.keyword or "").lower()
        keywords = [k.strip() for k in kw.split("|") if k.strip()] or ["chrome"]
        out = []
        for w in gw.getAllWindows():
            if not w.visible or not w.title:
                continue
            title = w.title
            if _title_excluded(title):
                continue
            hwnd = getattr(w, "_hWnd", None)
            if not hwnd or not _is_browser_hwnd(hwnd):
                continue
            if profile_dir:
                try:
                    import win32process
                    from chrome_launcher import process_uses_profile

                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if not process_uses_profile(pid, profile_dir):
                        continue
                except Exception:
                    continue
            tl = title.lower()
            if any(k in tl for k in keywords):
                out.append(w)
        return out

    def find_and_setup_window(
        self,
        keyword=None,
        target_x=0,
        target_y=0,
        target_w=1280,
        target_h=720,
        maximize=False,
        profile_dir: str | None = None,
    ):
        if keyword:
            self.keyword = keyword

        matched = self.list_browser_candidates(self.keyword, profile_dir=profile_dir)
        if not matched:
            # fallback: bất kỳ browser khớp keyword (khi chưa truyền profile)
            if profile_dir:
                print(f"[!] Không thấy Chrome đúng profile vision — sẽ launch mới.")
            else:
                print(f"[!] Không thấy browser thật khớp '{self.keyword}' (đã loại CMD/BAT).")
            return None

        prefer = (
            "rr9900",
            "rr199",
            "rr88",
            "sexy",
            "baccarat",
            "seamless",
            "casino",
            "live",
            "trang chủ",
        )
        # Tránh khóa nhầm tab about:blank / New Tab
        bad_tab = ("about:blank", "new tab", "tab mới", "untitled")

        def _rank(w):
            tl = (w.title or "").lower()
            if any(b in tl for b in bad_tab) or tl.strip() in ("", "chrome", "google chrome"):
                return (2, 0)
            if any(p in tl for p in prefer):
                return (0, -((w.width or 0) * (w.height or 0)))
            return (1, -((w.width or 0) * (w.height or 0)))

        ranked = sorted(matched, key=_rank)
        win = ranked[0]
        self.window = win
        self.hwnd = win._hWnd

        print(f"[+] Browser: '{win.title}' (HWND: {self.hwnd})")

        if win32gui.IsIconic(self.hwnd):
            win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
            time.sleep(0.3)

        try:
            win32gui.SetForegroundWindow(self.hwnd)
        except Exception:
            pass

        try:
            if maximize:
                win32gui.ShowWindow(self.hwnd, win32con.SW_MAXIMIZE)
                time.sleep(0.35)
                print("[+] Maximize full màn (giữ size này lúc calibrate + chạy bot)")
            else:
                win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
                time.sleep(0.15)
                win32gui.MoveWindow(self.hwnd, target_x, target_y, target_w, target_h, True)
                time.sleep(0.3)
                print(f"[+] Khóa cửa sổ {target_w}x{target_h} @ ({target_x},{target_y})")
        except Exception as e:
            print(f"[!] MoveWindow/Maximize: {e}")

        return self.get_rect()

    def get_rect(self):
        if not self.hwnd:
            return None
        if not win32gui.IsWindow(self.hwnd):
            self.hwnd = None
            return None
        # Nếu hwnd cũ là CMD bị nhầm — từ chối
        if not _is_browser_hwnd(self.hwnd):
            return None
        title = win32gui.GetWindowText(self.hwnd) or ""
        if _title_excluded(title):
            return None
        rect = win32gui.GetWindowRect(self.hwnd)
        return {
            "left": rect[0],
            "top": rect[1],
            "right": rect[2],
            "bottom": rect[3],
            "width": rect[2] - rect[0],
            "height": rect[3] - rect[1],
        }


if __name__ == "__main__":
    wc = WindowController()
    print("--- Browser candidates ---")
    for w in wc.list_browser_candidates("chrome|edge"):
        print(f"- {w.title}")
