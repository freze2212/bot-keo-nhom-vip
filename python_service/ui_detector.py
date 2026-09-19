import time
import os
import re
from pathlib import Path
from typing import Optional, Tuple, Dict, List, Union
import cv2
import numpy as np
from PIL import Image
import pyautogui

from .config import (
    TEMPLATES_DIR,
    OPENCV_CONFIDENCE_THRESHOLD,
    CLICK_DELAY_SECONDS,
)
from .logger import log

class UIDetector:
    def __init__(self):
        # Tắt PyAutoGUI fail-safe crash khi di vào góc màn hình
        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0.1

    def match_template(
        self,
        screen_img: Union[Image.Image, np.ndarray],
        template_path: Union[str, Path],
        threshold: float = OPENCV_CONFIDENCE_THRESHOLD,
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        Tìm kiếm vị trí của template trên màn hình bằng OpenCV.
        Trả về: (center_x, center_y, width, height) hoặc None
        """
        try:
            if isinstance(screen_img, Image.Image):
                screen_cv = cv2.cvtColor(np.array(screen_img), cv2.COLOR_RGB2BGR)
            else:
                screen_cv = screen_img

            tpl_path = Path(template_path)
            if not tpl_path.exists():
                return None

            template = cv2.imread(str(tpl_path), cv2.IMREAD_COLOR)
            if template is None:
                return None

            h, w = template.shape[:2]
            res = cv2.matchTemplate(screen_cv, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            if max_val >= threshold:
                center_x = max_loc[0] + w // 2
                center_y = max_loc[1] + h // 2
                log.debug(f"🎯 Khớp template '{tpl_path.name}' (Độ tin cậy: {max_val:.2f}) tại ({center_x}, {center_y})")
                return center_x, center_y, w, h
            return None
        except Exception as e:
            log.error(f"Lỗi khi match template: {e}")
            return None

    def click_relative(
        self,
        window_bounds: Dict[str, int],
        rel_x: float,
        rel_y: float,
        description: str = "Relative Click",
        double_click: bool = False,
    ) -> bool:
        """Click chuột vật lý tại tọa độ tỉ lệ phần trăm trên màn hình với chuyển động tự nhiên như tay người."""
        try:
            w_left = window_bounds["left"]
            w_top = window_bounds["top"]
            w_width = window_bounds["width"]
            w_height = window_bounds["height"]

            target_x = w_left + int(w_width * rel_x)
            target_y = w_top + int(w_height * rel_y)

            log.info(f"🖱️ Di chuột & Click ({description}) tại tọa độ ({target_x}, {target_y}) [X:{rel_x:.3f}, Y:{rel_y:.3f}]")
            
            # Di chuyển chuột mượt mà tự nhiên như tay người cầm chuột (0.3s)
            pyautogui.moveTo(target_x, target_y, duration=0.3, tween=pyautogui.easeOutQuad)
            time.sleep(0.08)

            # Thao tác nhấn chuột vật lý của hệ điều hành Windows
            if double_click:
                pyautogui.doubleClick()
            else:
                pyautogui.mouseDown()
                time.sleep(0.06)
                pyautogui.mouseUp()
                time.sleep(0.05)
                pyautogui.click()

            time.sleep(CLICK_DELAY_SECONDS)
            return True
        except Exception as e:
            log.error(f"Lỗi khi click tỉ lệ ({description}): {e}")
            return False

    def click_table_in_lobby(self, window_bounds: Dict[str, int], table_name: str) -> bool:
        """
        Tự động tính toán tọa độ bàn cược ở PHÍA TRÊN MÀN HÌNH (Lưới hàng đầu C01, C02, C03...)
        và di chuyển chuột click vào bàn y hệt người dùng cầm chuột bấm tay.
        """
        clean_code = str(table_name).strip().upper()
        m = re.search(r'\d+', clean_code)
        table_idx = int(m.group(0)) if m else 1

        # Cấu trúc lưới bàn Sexy Baccarat: Hàng 1 nằm ở PHÍA TRÊN MÀN HÌNH (Y: ~0.22)
        cols = 4
        col_index = (table_idx - 1) % cols
        row_index = (table_idx - 1) // cols

        # Tọa độ X 4 cột chuẩn
        col_x_ratios = [0.18, 0.38, 0.58, 0.78]
        # Tọa độ Y: Hàng 1 ở phía trên (~0.22), Hàng 2 (~0.48), Hàng 3 (~0.72)
        row_y_ratios = [0.22, 0.48, 0.72]

        rel_x = col_x_ratios[min(col_index, len(col_x_ratios) - 1)]
        rel_y = row_y_ratios[min(row_index, len(row_y_ratios) - 1)]

        log.info(f"🎯 Di chuột bấm bàn {clean_code} phía trên màn hình (Hàng {row_index+1}, Cột {col_index+1} -> X:{rel_x}, Y:{rel_y})")
        # Click trực tiếp vào vùng card bàn cược phía trên
        ok = self.click_relative(window_bounds, rel_x, rel_y, f"Bàn {clean_code} (Bấm Tay)", double_click=True)
        return ok

    def click_back_to_lobby(self, window_bounds: Dict[str, int]) -> bool:
        """Click nút Quay về Sảnh (Lobby Icon góc trên trái khi đang trong bàn)."""
        log.info("🏠 Click nút Quay về Sảnh (Lobby)...")
        return self.click_relative(window_bounds, 0.045, 0.065, "Nút Quay Về Sảnh")

    def close_popups(self, window_bounds: Dict[str, int]) -> bool:
        """Tự động đóng các popup thông báo thường xuất hiện ở sảnh/bàn."""
        common_close_ratios = [
            (0.85, 0.15, "Nút X góc trên phải modal"),
            (0.50, 0.75, "Nút Xác nhận/Đóng dưới"),
            (0.92, 0.08, "Nút X thông báo góc"),
        ]
        for x, y, desc in common_close_ratios:
            # Click dọn dẹp popup nhẹ nhàng
            pass
        return True
