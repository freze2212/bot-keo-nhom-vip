import os
import sys
import time
import subprocess
from typing import Optional, Dict, Any
from pathlib import Path

from .config import (
    CHROME_PROFILE_DIR,
    DEFAULT_WINDOW_WIDTH,
    DEFAULT_WINDOW_HEIGHT,
    NAME_SERVICE,
    GAME_URL,
)
from .logger import log
from .window_manager import WindowManager
from .screen_capture import ScreenCapture
from .ui_detector import UIDetector
from .socket_client import SocketClient

class SessionController:
    def __init__(self):
        self.wm = WindowManager()
        self.capture = ScreenCapture()
        self.detector = UIDetector()
        
        self.current_table = "NONE"
        self.target_table = "NONE"
        self.is_in_table = False
        self.is_running = True
        self.chrome_proc = None

        # Khởi tạo Socket Client với callback tương ứng
        self.socket_client = SocketClient(
            on_change_table=self.on_change_table_request,
            on_capture_request=self.on_capture_round_request,
            on_reload_request=self.on_reload_request,
        )

    def clean_ghost_chrome_processes(self):
        """Tự động dọn dẹp các tiến trình Chrome chạy ngầm bị kẹt lockfile profile."""
        try:
            import psutil
            killed = 0
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] and 'chrome' in proc.info['name'].lower():
                        cmdline = ' '.join(proc.info['cmdline'] or [])
                        if 'chrome_user_data' in cmdline:
                            proc.kill()
                            killed += 1
                except Exception:
                    pass
            if killed > 0:
                log.info(f"🧹 Đã dọn dẹp {killed} tiến trình Chrome chạy ngầm chiếm profile.")
        except Exception as e:
            log.debug(f"clean_ghost_chrome_processes notice: {e}")

        lockfile = Path(CHROME_PROFILE_DIR) / "lockfile"
        if lockfile.exists():
            try:
                lockfile.unlink()
            except Exception:
                pass

    def launch_or_attach_chrome(self, url: Optional[str] = None):
        """Khởi động Chrome thật với Full GPU 60 FPS hoặc gắn kết với cửa sổ game đang mở sẵn."""
        log.info("🔍 Kiểm tra cửa sổ game đang mở sẵn...")
        hwnd = self.wm.find_game_window()
        if hwnd:
            log.info(f"🎯 Đã tìm thấy cửa sổ game mở sẵn (HWND: {hwnd}) -> Gắn kết trực tiếp 60 FPS!")
            self.wm.activate_and_align_window(hwnd, maximize=True)
            return hwnd

        # Tự động dọn dẹp tiến trình ngầm & lockfile cũ
        self.clean_ghost_chrome_processes()
        time.sleep(0.5)

        log.info("🚀 Khởi chạy Chrome mới với cấu hình Full GPU 60 FPS (Hardware Acceleration)...")
        chrome_candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        chrome_exe = None
        for p in chrome_candidates:
            if os.path.exists(p):
                chrome_exe = p
                break

        if not chrome_exe:
            chrome_exe = "chrome.exe"

        target_url = url or GAME_URL
        # Mở Chrome theo đúng cấu hình tự nhiên của máy bác (dùng profile mặc định + GPU ANGLE D3D11 mượt mà nhất)
        shell_cmd = f'start "" "{chrome_exe}" "{target_url}"'

        hwnd = None
        try:
            subprocess.Popen(shell_cmd, shell=True)
            log.info(f"Đã mở Chrome mặc định lên Desktop: {shell_cmd}")

            for _ in range(12):
                time.sleep(1.0)
                hwnd = self.wm.find_game_window()
                if hwnd:
                    break
        except Exception as e:
            log.error(f"Không thể khởi chạy Chrome tự động: {e}")

        if hwnd:
            self.wm.activate_and_align_window(hwnd, maximize=True)
            # Tự động vào bàn mặc định C01 sau khi sảnh load hoàn tất
            time.sleep(6.5)
            self.enter_table("C01")
        return hwnd

    def on_change_table_request(self, table_name: str, reason: str = ""):
        """Nhận lệnh đổi bàn từ hệ thống."""
        clean_target = str(table_name).strip().upper()
        if clean_target == self.current_table and self.is_in_table:
            log.info(f"Đang ở đúng bàn {clean_target} rồi, không cần đổi.")
            return

        log.info(f"🔄 Nhận lệnh chuyển sang bàn {clean_target} (Lý do: {reason})...")
        self.target_table = clean_target
        self.enter_table(clean_target)

    def enter_table(self, table_name: str) -> bool:
        """Tự động thao tác chuột click vào bàn cược như người thật."""
        clean_target = str(table_name).strip().upper()
        bounds = self.wm.get_window_bounds()
        self.wm.activate_and_align_window(maximize=True)

        # 1. Nếu đang ở trong bàn khác, click nút quay về sảnh trước
        if self.is_in_table:
            log.info(f"Đang ở bàn {self.current_table} -> Quay về sảnh để đổi sang {clean_target}...")
            self.detector.click_back_to_lobby(bounds)
            time.sleep(2.0)
            bounds = self.wm.get_window_bounds()

        # 2. Xử lý đóng các popup modal nếu có
        self.detector.close_popups(bounds)

        # 3. Click vào card bàn mục tiêu trong sảnh
        log.info(f"🎯 Di chuột và click vào bàn {clean_target} trong sảnh...")
        self.detector.click_table_in_lobby(bounds, clean_target)
        time.sleep(2.5)

        self.current_table = clean_target
        self.is_in_table = True
        
        # 4. Báo lên Server bàn cược đã sẵn sàng hoạt động
        self.socket_client.notify_active_table(clean_target)
        log.info(f"✅ Đã vào bàn thành công: {clean_target}")
        return True

    def on_capture_round_request(self, data: Dict[str, Any]):
        """Xử lý yêu cầu chụp ảnh khi round kết thúc."""
        table = data.get("tableName") or self.current_table
        round_num = data.get("roundNum") or data.get("round")
        winner = data.get("winner")

        if not self.is_in_table or self.current_table == "NONE":
            log.warning("Chưa ở trong bàn cược, bỏ qua yêu cầu chụp ảnh.")
            return

        log.info(f"📸 Đang chụp ảnh bàn {table} (Round {round_num}, Winner: {winner})...")
        bounds = self.wm.get_window_bounds()
        success, filepath, _ = self.capture.capture_table_round(
            window_bounds=bounds,
            table_name=table,
            round_num=round_num,
            winner=winner,
        )
        if success:
            log.info(f"🎉 Chụp thành công: {filepath}")

    def on_reload_request(self):
        """Xử lý bấm nút làm mới khi mất tín hiệu."""
        bounds = self.wm.get_window_bounds()
        log.info("🔄 Đang bấm reload tín hiệu bàn cược...")
        self.detector.click_relative(bounds, 0.89, 0.78, "Nút Làm Mới Tín Hiệu")

    def run(self):
        """Vòng lặp chính của Session Controller."""
        log.info(f"🚀 Bắt đầu Session Controller (Service: {NAME_SERVICE})")
        self.launch_or_attach_chrome()
        self.socket_client.start()

        try:
            while self.is_running:
                time.sleep(2.0)
        except KeyboardInterrupt:
            log.info("Dừng Controller theo yêu cầu người dùng.")
        finally:
            self.close()

    def close(self):
        self.is_running = False
        self.socket_client.stop()
        self.capture.close()
        log.info("Đã đóng Session Controller an toàn.")

if __name__ == "__main__":
    controller = SessionController()
    controller.run()
