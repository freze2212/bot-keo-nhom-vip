import cv2
import numpy as np

class VisualDetector:
    def __init__(self, color_thresholds=None):
        self.thresholds = color_thresholds or {
            "banker_red": {"r_min": 160, "g_max": 90, "b_max": 90},
            "player_blue": {"r_max": 90, "g_max": 150, "b_min": 160},
            "tie_green": {"r_max": 100, "g_min": 160, "b_max": 100}
        }

    def detect_color_dominance(self, img_bgr):
        """
        Phân tích vùng ảnh xem đang chiếm ưu thế bởi màu Đỏ (Banker), Xanh Dương (Player) hay Xanh Lá (Tie/Timer)
        """
        if img_bgr is None or img_bgr.size == 0:
            return "UNKNOWN", 0.0

        # Tách kênh B, G, R
        b = img_bgr[:, :, 0]
        g = img_bgr[:, :, 1]
        r = img_bgr[:, :, 2]

        total_pixels = img_bgr.shape[0] * img_bgr.shape[1]
        if total_pixels == 0:
            return "UNKNOWN", 0.0

        # Mask cho Banker (Màu đỏ: R cao, G và B thấp)
        red_mask = (r > 150) & (g < 100) & (b < 100)
        red_count = np.sum(red_mask)

        # Mask cho Player (Màu xanh dương: B cao, R và G thấp)
        blue_mask = (b > 150) & (r < 100)
        blue_count = np.sum(blue_mask)

        # Mask cho Tie / Timer (Màu xanh lá: G cao, R và B thấp)
        green_mask = (g > 150) & (r < 110) & (b < 110)
        green_count = np.sum(green_mask)

        red_ratio = red_count / total_pixels
        blue_ratio = blue_count / total_pixels
        green_ratio = green_count / total_pixels

        # Ngưỡng nhận diện (chỉ cần > 10% diện tích ô hoặc vùng có màu đặc trưng)
        if red_ratio > 0.12 and red_ratio > blue_ratio and red_ratio > green_ratio:
            return "BANKER", red_ratio
        elif blue_ratio > 0.12 and blue_ratio > red_ratio and blue_ratio > green_ratio:
            return "PLAYER", blue_ratio
        elif green_ratio > 0.12 and green_ratio > red_ratio and green_ratio > blue_ratio:
            return "TIE_OR_TIMER", green_ratio

        return "EMPTY_OR_UNKNOWN", 0.0

    def match_template(self, screen_img, template_img, threshold=0.85):
        """So khớp hình ảnh mẫu với vùng chụp màn hình"""
        if screen_img is None or template_img is None:
            return False, 0.0, None

        result = cv2.matchTemplate(screen_img, template_img, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            return True, max_val, max_loc
        return False, max_val, max_loc

class GameStateMachine:
    """
    Quản lý vòng lặp chu kỳ ván cược (Betting -> Dealing -> Result)
    Chống gửi trùng lặp kết quả trong cùng 1 ván
    """
    STATE_WAITING = "WAITING"
    STATE_BETTING = "BETTING"
    STATE_DEALING = "DEALING"
    STATE_RESULT = "RESULT"

    def __init__(self):
        self.current_state = self.STATE_WAITING
        self.last_result = None
        self.is_result_sent = False
        self.round_counter = 0

    def update_state(self, timer_color_status, result_detected):
        """
        timer_color_status: 'TIE_OR_TIMER' (khi đồng hồ xanh đang chạy), 'EMPTY_OR_UNKNOWN' (khi hết giờ)
        result_detected: 'BANKER', 'PLAYER', 'TIE_OR_TIMER' hoặc 'EMPTY_OR_UNKNOWN'
        """
        event = None

        # 1. Phát hiện bắt đầu mở cược ván mới
        if timer_color_status == "TIE_OR_TIMER":
            if self.current_state != self.STATE_BETTING:
                self.current_state = self.STATE_BETTING
                self.is_result_sent = False # Mở khóa cho ván mới
                self.round_counter += 1
                event = ("NEW_ROUND_START", self.round_counter)

        # 2. Hết thời gian cược -> Dealer đang chia / mở bài
        elif self.current_state == self.STATE_BETTING and timer_color_status != "TIE_OR_TIMER":
            self.current_state = self.STATE_DEALING
            event = ("DEALING_STARTED", None)

        # 3. Phát hiện có kết quả (và chưa được gửi)
        if result_detected in ["BANKER", "PLAYER", "TIE_OR_TIMER"] and result_detected != "EMPTY_OR_UNKNOWN":
            if not self.is_result_sent and self.current_state in [self.STATE_DEALING, self.STATE_BETTING]:
                self.current_state = self.STATE_RESULT
                self.last_result = "TIE" if result_detected == "TIE_OR_TIMER" else result_detected
                self.is_result_sent = True # KHÓA CHỐNG TRÙNG NGAY LẬP TỨC
                event = ("RESULT_FOUND", {
                    "round": self.round_counter,
                    "winner": self.last_result
                })

        return self.current_state, event
