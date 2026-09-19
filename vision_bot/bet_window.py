"""Phát hiện cửa đặt cược MỞ thật.

Tín hiệu chuẩn (Sexy Baccarat):
  - Đồng hồ đếm ngược SỐ XANH neon (HSV) góc live — không phải vòng 'Mở bài'
  - Banner xanh 'Chúc may mắn' trên lưới cược
  - Không có banner vàng 'Đang mở bài' / flash hết ván
  - Giữ ổn định hold_sec (mặc định 5s) rồi mới cho đặt
"""
from __future__ import annotations

import time

import cv2
import numpy as np


def _crop(frame, roi):
    if frame is None or not roi or "width" not in roi:
        return None
    x, y = int(roi["x"]), int(roi["y"])
    w, h = int(roi["width"]), int(roi["height"])
    if y + h > frame.shape[0] or x + w > frame.shape[1] or x < 0 or y < 0:
        return None
    return frame[y : y + h, x : x + w]


def _roi_around(pt: dict, w=140, h=70) -> dict:
    return {
        "x": max(0, int(pt["x"]) - w // 2),
        "y": max(0, int(pt["y"]) - h // 2),
        "width": w,
        "height": h,
    }


def _mean_brightness(img) -> float:
    if img is None or img.size == 0:
        return 0.0
    return float(np.mean(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)))


def _timer_neon_green_ratio(img) -> float:
    """Số đếm ngược xanh neon thật (HSV). Vòng 'Mở bài' → ~0."""
    if img is None or img.size == 0:
        return 0.0
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (40, 80, 80), (95, 255, 255))
    return float(mask.mean() / 255.0)


def _banner_yellow_ratio(img) -> float:
    """Banner vàng 'Đang mở bài'."""
    if img is None or img.size == 0:
        return 0.0
    b, g, r = cv2.split(img)
    mask = (
        (r > 140)
        & (g > 120)
        & (b < 170)
        & ((r.astype(np.int16) + g.astype(np.int16)) > (2 * b.astype(np.int16) + 40))
        & (np.abs(r.astype(np.int16) - g.astype(np.int16)) < 45)
    )
    return float(np.mean(mask.astype(np.float32)))


def _banner_luck_green_ratio(img) -> float:
    """Banner xanh 'Chúc may mắn' khi cửa đặt mở."""
    if img is None or img.size == 0:
        return 0.0
    b, g, r = cv2.split(img)
    mask = (g > 130) & (g > r + 40) & (g > b + 30) & (r < 120)
    return float(np.mean(mask.astype(np.float32)))


def _timer_roi(config: dict) -> dict:
    if config.get("roi_round_timer") and config["roi_round_timer"].get("width"):
        return config["roi_round_timer"]
    return {"x": 1520, "y": 150, "width": 160, "height": 140}


def _status_roi(config: dict, player: dict) -> dict:
    if config.get("roi_bet_status") and config["roi_bet_status"].get("width"):
        return config["roi_bet_status"]
    # Thanh trạng thái ngay trên lưới cược (Chúc may mắn / Đang mở bài)
    if player.get("x"):
        return {
            "x": max(0, int(player["x"]) - 140),
            "y": max(0, int(player["y"]) - 140),
            "width": 520,
            "height": 50,
        }
    return {"x": 700, "y": 780, "width": 520, "height": 50}


def betting_open_score(frame, config: dict) -> dict:
    bp = config.get("bet_points") or {}
    player = bp.get("player") or {}
    banker = bp.get("banker") or {}
    confirm = bp.get("confirm") or {}

    t_img = _crop(frame, _timer_roi(config))
    s_img = _crop(frame, _status_roi(config, player))
    p_roi = config.get("roi_zone_player") or (_roi_around(player, 180, 100) if player.get("x") else None)
    b_roi = config.get("roi_zone_banker") or (_roi_around(banker, 180, 100) if banker.get("x") else None)
    c_roi = config.get("roi_confirm") or (_roi_around(confirm, 160, 56) if confirm.get("x") else None)
    p_img = _crop(frame, p_roi)
    b_img = _crop(frame, b_roi)
    c_img = _crop(frame, c_roi)

    timer_green = _timer_neon_green_ratio(t_img)
    status_yellow = _banner_yellow_ratio(s_img)
    luck_green = _banner_luck_green_ratio(s_img)
    p_bri = _mean_brightness(p_img)
    b_bri = _mean_brightness(b_img)
    c_bri = _mean_brightness(c_img)

    green_min = float(config.get("bet_open_timer_green_min") or 0.04)
    yellow_max = float(config.get("bet_open_yellow_max") or 0.05)
    luck_min = float(config.get("bet_open_luck_green_min") or 0.05)

    dealing_banner = status_yellow >= yellow_max
    timer_ok = timer_green >= green_min
    luck_ok = luck_green >= luck_min
    # Flash thắng hết ván: ô Cái sáng mạnh, không có timer neon
    win_flash = (b_bri > p_bri + 50) and (not timer_ok)
    open_ok = bool(timer_ok and luck_ok and not dealing_banner and not win_flash)

    return {
        "open": open_ok,
        "confirm_ready": c_bri >= 55,
        "dealing_banner": dealing_banner,
        "win_flash": win_flash,
        "timer_green": round(timer_green, 3),
        "status_yellow": round(status_yellow, 3),
        "luck_green": round(luck_green, 3),
        "p_bri": round(p_bri, 1),
        "b_bri": round(b_bri, 1),
        "c_bri": round(c_bri, 1),
        "c_green": round(luck_green, 3),
        "p_blue": 0.0,
        "b_red": 0.0,
    }


def wait_betting_open(
    grabber,
    win_rect: dict,
    config: dict,
    log=None,
    timeout_sec: float = 120.0,
    poll: float = 0.2,
    need_closed_first: bool = False,
    hold_sec: float | None = None,
) -> bool:
    """Chờ timer neon + banner 'Chúc may mắn' ổn định hold_sec rồi mới đặt."""

    def _log(msg):
        if log:
            log.info(msg)
        else:
            print(f"[BETWIN] {msg}")

    hold = float(hold_sec if hold_sec is not None else config.get("bet_open_hold_sec") or 5.0)
    t0 = time.time()
    saw_closed = not need_closed_first
    open_since = None
    last = ""

    while time.time() - t0 < timeout_sec:
        frame = grabber.grab_window(win_rect)
        sc = betting_open_score(frame, config)
        held = 0.0 if open_since is None else (time.time() - open_since)
        tag = (
            f"open={sc['open']} timerG={sc['timer_green']} luck={sc.get('luck_green', 0)} "
            f"yellow={sc['status_yellow']} flash={sc['win_flash']} held={held:.1f}s/{hold:.0f}s"
        )
        if tag != last:
            _log(tag)
            last = tag

        if not sc["open"]:
            saw_closed = True
            open_since = None
        elif saw_closed and sc["open"]:
            if open_since is None:
                open_since = time.time()
                _log(f"Thấy CỬA XANH (timer+Chúc may mắn) — giữ {hold:.0f}s rồi mới đặt…")
            elif time.time() - open_since >= hold:
                _log(f"CỬA ĐẶT ỔN ĐỊNH {hold:.0f}s — bắt đầu đặt cược")
                return True
        time.sleep(poll)

    _log("TIMEOUT — chưa thấy cửa đặt xanh ổn định đủ lâu")
    return False


def _chip_score(img_bgr) -> float:
    """Chip vàng/cam/đỏ/trắng trên nền tối ô cược."""
    if img_bgr is None or img_bgr.size == 0:
        return 0.0
    b, g, r = cv2.split(img_bgr)
    warm = (r > 140) & (g > 90) & (b < 120) & (r > b + 30)
    red = (r > 160) & (g < 100) & (b < 100)
    bright = (r > 180) & (g > 180) & (b > 180)
    return float(np.mean((warm | red | bright).astype(np.float32)))


class BetVerifier:
    """Xác nhận chip đã nằm đúng ô Banker/Player sau khi click."""

    def __init__(self, min_score: float = 0.02, min_delta: float = 0.008):
        self.min_score = min_score
        self.min_delta = min_delta
        self._before = {"B": 0.0, "P": 0.0}

    def snapshot_before(self, banker_crop, player_crop) -> None:
        self._before["B"] = _chip_score(banker_crop)
        self._before["P"] = _chip_score(player_crop)

    def verify(self, side: str, banker_crop, player_crop) -> dict:
        side_u = "B" if str(side).upper().startswith("B") else "P"
        after_b = _chip_score(banker_crop)
        after_p = _chip_score(player_crop)
        target_before = self._before[side_u]
        target_after = after_b if side_u == "B" else after_p
        other_after = after_p if side_u == "B" else after_b
        delta = target_after - target_before
        ok = (target_after >= self.min_score and delta >= self.min_delta) or (
            target_after > other_after + 0.005 and target_after >= self.min_score * 0.7
        )
        return {
            "ok": bool(ok),
            "side": side_u,
            "score_B": round(after_b, 4),
            "score_P": round(after_p, 4),
            "delta": round(delta, 4),
            "before": round(target_before, 4),
        }
