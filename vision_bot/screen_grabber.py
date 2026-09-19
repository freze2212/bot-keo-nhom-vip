import numpy as np
import cv2
from PIL import ImageGrab

class ScreenGrabber:
    def __init__(self):
        self.mss_instance = None
        try:
            import mss
            self.mss_instance = mss.mss()
        except Exception:
            self.mss_instance = None

    def grab_region(self, x, y, width, height):
        """Chụp 1 vùng màn hình chữ nhật (x, y, width, height) hỗ trợ đa màn hình"""
        x1, y1 = int(x), int(y)
        x2, y2 = int(x + width), int(y + height)

        # Thử chụp qua MSS trước (siêu tốc)
        if self.mss_instance:
            try:
                monitor = {"left": x1, "top": y1, "width": int(width), "height": int(height)}
                sct_img = self.mss_instance.grab(monitor)
                img_np = np.array(sct_img)
                return cv2.cvtColor(img_np, cv2.COLOR_BGRA2BGR)
            except Exception:
                pass

        # Fallback qua PIL ImageGrab (ổn định 100% trên Windows đa màn hình)
        try:
            img_pil = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
            img_np = np.array(img_pil)
            return cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        except Exception as e:
            print(f"[!] Lỗi khi chụp màn hình: {e}")
            return None

    def grab_window(self, win_rect):
        """Chụp toàn bộ cửa sổ game"""
        return self.grab_region(
            win_rect["left"],
            win_rect["top"],
            win_rect["width"],
            win_rect["height"]
        )

    def close(self):
        if self.mss_instance:
            try:
                self.mss_instance.close()
            except Exception:
                pass
