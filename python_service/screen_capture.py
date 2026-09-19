import time
from pathlib import Path
from typing import Optional, Dict, Tuple, Union
import mss
import mss.tools
from PIL import Image, ImageGrab
import numpy as np
from .config import IMAGES_DIR, CAPTURE_CROP_BOX
from .logger import log

class ScreenCapture:
    def __init__(self):
        self._sct = None

    @property
    def sct(self):
        if self._sct is None:
            self._sct = mss.mss()
        return self._sct

    def grab_region(self, bbox: Dict[str, int]) -> Image.Image:
        """
        Chụp một vùng màn hình bằng MSS siêu tốc (3-5ms), tự động fallback sang ImageGrab nếu MSS gặp lỗi.
        bbox: {'left': int, 'top': int, 'width': int, 'height': int}
        """
        t0 = time.perf_counter()
        left = max(0, int(bbox["left"]))
        top = max(0, int(bbox["top"]))
        width = max(10, int(bbox["width"]))
        height = max(10, int(bbox["height"]))

        # 1. Thử chụp bằng MSS siêu tốc
        try:
            monitor = {
                "left": left,
                "top": top,
                "width": width,
                "height": height,
            }
            sct_img = self.sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            elapsed_ms = (time.perf_counter() - t0) * 1000
            log.debug(f"⚡ [MSS] Đã chụp vùng {width}x{height} trong {elapsed_ms:.2f}ms")
            return img
        except Exception as e:
            log.debug(f"MSS grab failed ({e}) -> Fallback sang PIL ImageGrab...")

        # 2. Fallback sang PIL ImageGrab (Tương thích 100% mọi màn hình Windows)
        try:
            bbox_tuple = (left, top, left + width, top + height)
            img = ImageGrab.grab(bbox=bbox_tuple, all_screens=True)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            log.debug(f"⚡ [ImageGrab] Đã chụp vùng {width}x{height} trong {elapsed_ms:.2f}ms")
            return img
        except Exception as e2:
            log.error(f"❌ Tất cả phương thức chụp màn hình đều thất bại: {e2}")
            # Trả về ảnh dummy để không làm crash luồng
            return Image.new("RGB", (width, height), color=(30, 30, 30))

    def capture_table_round(
        self,
        window_bounds: Dict[str, int],
        table_name: str = "C01",
        round_num: Optional[Union[str, int]] = None,
        winner: Optional[str] = None,
        custom_crop_ratio: Optional[Dict[str, float]] = None,
    ) -> Tuple[bool, Optional[str], Optional[Image.Image]]:
        """
        Chụp ảnh bảng cược bàn Baccarat, lưu ra thư mục images/ theo đúng định dạng.
        Trả về: (success, file_path, pil_image)
        """
        try:
            crop_config = custom_crop_ratio or CAPTURE_CROP_BOX
            
            w_left = window_bounds["left"]
            w_top = window_bounds["top"]
            w_width = window_bounds["width"]
            w_height = window_bounds["height"]

            # Tính toán vùng crop theo tỉ lệ cửa sổ
            crop_left = w_left + int(w_width * crop_config.get("left_ratio", 0.0))
            crop_top = w_top + int(w_height * crop_config.get("top_ratio", 0.40))
            crop_width = int(w_width * crop_config.get("width_ratio", 1.0))
            crop_height = int(w_height * crop_config.get("height_ratio", 0.60))

            bbox = {
                "left": max(0, crop_left),
                "top": max(0, crop_top),
                "width": max(100, crop_width),
                "height": max(100, crop_height),
            }

            img = self.grab_region(bbox)

            # Tên file ảnh chuẩn format của hệ thống: sexy_<TABLENAME>_R<ROUND>_W<WINNER>_<TIMESTAMP>.png
            clean_table = str(table_name).strip().upper()
            timestamp = int(time.time() * 1000)
            round_suffix = f"_R{round_num}" if round_num is not None else ""
            win_tag = f"_W{str(winner).strip().upper()}_" if winner else "_"
            filename = f"sexy_{clean_table}{round_suffix}{win_tag}{timestamp}.png"
            filepath = IMAGES_DIR / filename

            img.save(str(filepath), format="PNG")
            log.info(f"📸 Đã chụp & lưu ảnh bàn {clean_table}: {filepath.name}")
            return True, str(filepath), img
        except Exception as e:
            log.error(f"❌ Lỗi khi chụp ảnh bàn {table_name}: {e}")
            return False, None, None

    def close(self):
        try:
            if self._sct:
                self._sct.close()
                self._sct = None
        except Exception:
            pass
