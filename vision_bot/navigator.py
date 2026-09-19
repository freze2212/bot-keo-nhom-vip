"""Click điều hướng / đặt cược — OS SendInput, không Playwright."""
from __future__ import annotations

import time

from input_click import click_relative, scroll_relative


class Navigator:
    def __init__(self, window_rect=None):
        self.window_rect = window_rect

    def set_window_rect(self, rect):
        self.window_rect = rect

    def click_relative(self, rel_x, rel_y, delay_after=1.0, clicks=1):
        abs_x, abs_y = click_relative(self.window_rect, rel_x, rel_y, clicks=clicks)
        print(f"[Mouse] Click ({abs_x}, {abs_y}) [rel {rel_x},{rel_y}]")
        if delay_after > 0:
            time.sleep(delay_after)

    def scroll_to_bottom(self, rel_x: int | None = None, rel_y: int | None = None, notches: int = -18):
        """Focus vùng bàn rồi kéo scroll xuống cuối (âm = xuống)."""
        wr = self.window_rect or {}
        cx = int(rel_x if rel_x is not None else (wr.get("width") or 1920) // 2)
        cy = int(rel_y if rel_y is not None else int((wr.get("height") or 1080) * 0.55))
        print(f"[Mouse] Scroll xuống @ Rel ({cx},{cy}) notches={notches}")
        # click nhẹ để focus iframe/canvas
        click_relative(self.window_rect, cx, cy, clicks=1)
        time.sleep(0.25)
        scroll_relative(self.window_rect, cx, cy, notches=notches)
        time.sleep(0.6)

    def execute_sequence(self, steps):
        print(f"[*] Chạy {len(steps)} bước điều hướng (OS click)...")
        for i, step in enumerate(steps, 1):
            name = step.get("name", f"Bước {i}")
            x = int(step["x"])
            y = int(step["y"])
            delay = float(step.get("delay_after", 1.5))
            clicks = int(step.get("clicks", 1))
            print(f" -> [{i}/{len(steps)}] {name} ({x}, {y})")
            self.click_relative(x, y, delay_after=delay, clicks=clicks)
        print("[+] Xong chuỗi điều hướng.")

    def place_bet(self, bet_points: dict, side: str, chip_key: str | None = None) -> bool:
        """
        Luồng Sexy: click Đặt CON/CÁI → click Xác nhận.
        bet_points: { player, banker, confirm [, chip_...] }
        """
        if not bet_points:
            print("[!] Chưa cấu hình bet_points trong vision_config.json")
            return False

        side_u = str(side or "P").strip().upper()
        is_banker = side_u.startswith("B") or side_u in ("CAI", "CÁI", "BANKER")
        target_key = "banker" if is_banker else "player"
        target = bet_points.get(target_key)
        if not target or "x" not in target:
            print(f"[!] Thiếu tọa độ '{target_key}' trong bet_points")
            return False

        chip = None
        if chip_key and chip_key in bet_points:
            chip = bet_points[chip_key]
        else:
            for k in ("chip", "chip_50", "chip_100", "chip_default"):
                if k in bet_points and "x" in (bet_points.get(k) or {}):
                    chip = bet_points[k]
                    break
        if chip:
            print(f"[BET] Chọn chip @ ({chip['x']}, {chip['y']})")
            self.click_relative(int(chip["x"]), int(chip["y"]), delay_after=0.35)

        label = "CÁI/BANKER" if is_banker else "CON/PLAYER"
        print(f"[BET] Đặt {label} @ ({target['x']}, {target['y']})")
        self.click_relative(int(target["x"]), int(target["y"]), delay_after=0.55)

        confirm = bet_points.get("confirm")
        if confirm and "x" in confirm:
            # Đợi nút Xác nhận sáng một nhịp (sau khi chọn ô)
            time.sleep(0.35)
            print(f"[BET] Xác nhận @ ({confirm['x']}, {confirm['y']})")
            self.click_relative(int(confirm["x"]), int(confirm["y"]), delay_after=0.5)
        else:
            print("[BET] Không có tọa độ confirm — bỏ qua nút xác nhận")
        return True
