import time
import win32gui
import win32con
import win32process
import ctypes
from typing import Optional, Tuple, Dict, List
from .config import (
    TARGET_WINDOW_TITLE_KEYWORDS,
    DEFAULT_WINDOW_X,
    DEFAULT_WINDOW_Y,
    DEFAULT_WINDOW_WIDTH,
    DEFAULT_WINDOW_HEIGHT,
)
from .logger import log

class WindowManager:
    def __init__(self):
        self.target_hwnd: Optional[int] = None
        self.target_pid: Optional[int] = None
        self.last_rect: Optional[Dict[str, int]] = None

    def set_target_pid(self, pid: int):
        self.target_pid = pid

    def find_game_window(self, pid: Optional[int] = None) -> Optional[int]:
        """
        Tìm kiếm cửa sổ Chrome thật (Chrome_WidgetWin_1).
        Nếu có PID cụ thể, CHỈ bắt đúng process PID đó (và process con của nó).
        """
        check_pid = pid or self.target_pid
        allowed_pids = set()
        if check_pid:
            allowed_pids.add(check_pid)
            try:
                import psutil
                p = psutil.Process(check_pid)
                for child in p.children(recursive=True):
                    allowed_pids.add(child.pid)
            except Exception:
                pass

        matched_hwnds = []

        def enum_windows_callback(hwnd, extra):
            if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
                return
            class_name = win32gui.GetClassName(hwnd)
            title = win32gui.GetWindowText(hwnd).strip()
            if not title:
                return

            # Loại trừ tuyệt đối cửa sổ console / tool
            excluded_keywords = [
                "PYTHON NATIVE",
                "CHAY_",
                "cmd.exe",
                "powershell",
                "Windows PowerShell",
                "Command Prompt",
                "Administrator:",
                "Task Manager",
                "Discord",
                "Spaceship",
                "Domain Manager",
                "Cloudflare",
                "Workers & Pages",
                "Telegram",
                "Zalo",
                "ChatGPT",
                "Facebook",
                "Visual Studio Code",
                "Antigravity",
            ]
            if any(ex.lower() in title.lower() for ex in excluded_keywords):
                return
            if class_name in ["ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"]:
                return

            _, w_pid = win32process.GetWindowThreadProcessId(hwnd)
            is_chrome_class = (class_name == "Chrome_WidgetWin_1")

            # 1. Nếu có PID chỉ định, CHỈ bắt cửa sổ thuộc PID đó
            if allowed_pids and is_chrome_class:
                if w_pid in allowed_pids:
                    matched_hwnds.append((hwnd, title, 10))
                    return

            # 2. Hoặc tìm theo từ khóa sòng bài / game / URL (khi không có PID)
            if not check_pid and is_chrome_class:
                for kw in TARGET_WINDOW_TITLE_KEYWORDS:
                    if kw.lower() in title.lower():
                        matched_hwnds.append((hwnd, title, 5))
                        break

        win32gui.EnumWindows(enum_windows_callback, None)

        if matched_hwnds:
            # Sắp xếp ưu tiên độ khớp cao nhất
            matched_hwnds.sort(key=lambda x: x[2], reverse=True)
            self.target_hwnd = matched_hwnds[0][0]
            log.info(f"✅ Đã tìm thấy cửa sổ game: '{matched_hwnds[0][1]}' (HWND: {self.target_hwnd})")
            return self.target_hwnd

        log.warning("⚠️ Chưa tìm thấy cửa sổ Google Chrome thật.")
        return None

    def activate_and_align_window(
        self,
        hwnd: Optional[int] = None,
        maximize: bool = True,
        x: int = DEFAULT_WINDOW_X,
        y: int = DEFAULT_WINDOW_Y,
        width: int = DEFAULT_WINDOW_WIDTH,
        height: int = DEFAULT_WINDOW_HEIGHT,
    ) -> bool:
        """Kích hoạt cửa sổ lên trên cùng (Foreground) và phóng to Fullscreen (Maximize)."""
        target = hwnd or self.target_hwnd or self.find_game_window()
        if not target:
            return False

        try:
            # 1. Khôi phục nếu đang bị minimize
            if win32gui.IsIconic(target):
                win32gui.ShowWindow(target, win32con.SW_RESTORE)
                time.sleep(0.2)

            # 2. Focus & Đưa lên Foreground (Bypass Windows Foreground Lock)
            try:
                fg_hwnd = win32gui.GetForegroundWindow()
                if fg_hwnd and fg_hwnd != target:
                    cur_thread = win32process.GetWindowThreadProcessId(fg_hwnd)[0]
                    target_thread = win32process.GetWindowThreadProcessId(target)[0]
                    if cur_thread != target_thread:
                        ctypes.windll.user32.AttachThreadInput(cur_thread, target_thread, True)
                        win32gui.SetForegroundWindow(target)
                        ctypes.windll.user32.AttachThreadInput(cur_thread, target_thread, False)
                    else:
                        win32gui.SetForegroundWindow(target)
                else:
                    win32gui.SetForegroundWindow(target)
            except Exception as fe:
                log.debug(f"SetForegroundWindow notice: {fe}")
                win32gui.ShowWindow(target, win32con.SW_SHOW)
                win32gui.BringWindowToTop(target)

            time.sleep(0.2)

            # 3. Phóng to Fullscreen (Maximize) hoặc đặt kích thước chuẩn
            if maximize:
                win32gui.ShowWindow(target, win32con.SW_MAXIMIZE)
            else:
                win32gui.MoveWindow(target, x, y, width, height, True)
            time.sleep(0.2)

            rect = self.get_window_bounds(target)
            self.last_rect = rect
            log.info(f"📐 Đã căn chỉnh cửa sổ: X={rect['left']}, Y={rect['top']}, W={rect['width']}, H={rect['height']}")
            return True
        except Exception as e:
            log.error(f"❌ Lỗi khi căn chỉnh cửa sổ HWND {target}: {e}")
            return False

    def get_window_bounds(self, hwnd: Optional[int] = None) -> Dict[str, int]:
        """Lấy tọa độ thực tế của cửa sổ trên màn hình desktop."""
        target = hwnd or self.target_hwnd
        if not target or not win32gui.IsWindow(target):
            return {"left": 0, "top": 0, "width": DEFAULT_WINDOW_WIDTH, "height": DEFAULT_WINDOW_HEIGHT}

        left, top, right, bottom = win32gui.GetWindowRect(target)
        w = max(100, right - left)
        h = max(100, bottom - top)
        rect = {"left": left, "top": top, "width": w, "height": h, "right": right, "bottom": bottom}
        self.last_rect = rect
        return rect
