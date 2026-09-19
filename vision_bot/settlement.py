"""Phát hiện hết ván → chụp WIN+ / LOSE-.

Popup ± tiền / WIN / LOSE nằm CÙNG chỗ với:
  - 'Đặt cược thành công'
  - 'Tạm ngừng đặt cược'
ROI toast phải (≈ x=1250..1650, y=700..820).

Không bắt lúc trừ chip đặt cược — chỉ sau 'Đang mở bài',
khi toast ROI sáng lên (WIN+/LOSE-).
"""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from dataclasses import dataclass, field

import cv2
import numpy as np


def _fingerprint(img_bgr) -> np.ndarray | None:
    if img_bgr is None or img_bgr.size == 0:
        return None
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (48, 16), interpolation=cv2.INTER_AREA)
    return small.astype(np.float32)


def _delta(a: np.ndarray | None, b: np.ndarray | None) -> float:
    if a is None or b is None:
        return 0.0
    return float(np.mean(np.abs(a - b)))


def _crop(frame, roi):
    if frame is None or not roi or "width" not in roi:
        return None
    x, y, w, h = int(roi["x"]), int(roi["y"]), int(roi["width"]), int(roi["height"])
    if y < 0 or x < 0 or y + h > frame.shape[0] or x + w > frame.shape[1]:
        return None
    return frame[y : y + h, x : x + w]


def _toast_roi(config: dict | None) -> dict:
    cfg = config or {}
    r = cfg.get("roi_toast_popup")
    if r and r.get("width"):
        return r
    # Mặc định: chỗ 'Đặt cược thành công' (đo từ ảnh thật)
    return {"x": 1450, "y": 720, "width": 360, "height": 70}


def _score_toast_crop_core(crop) -> dict:
    empty = {
        "green": 0.0,
        "gold": 0.0,
        "red": 0.0,
        "bri": 0.0,
        "bright": 0.0,
        "active": False,
        "kind": "none",
    }
    if crop is None or crop.size == 0:
        return empty
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    green = float(cv2.inRange(hsv, (32, 50, 70), (95, 255, 255)).mean() / 255.0)
    gold = float(cv2.inRange(hsv, (12, 80, 140), (38, 255, 255)).mean() / 255.0)
    # LOSE toast đỏ tối (bri thấp) — nới S/V
    red_a = cv2.inRange(hsv, (0, 50, 40), (15, 255, 220))
    red_b = cv2.inRange(hsv, (160, 50, 40), (180, 255, 220))
    red = float(cv2.bitwise_or(red_a, red_b).mean() / 255.0)
    yellow = float(cv2.inRange(hsv, (18, 60, 100), (40, 255, 255)).mean() / 255.0)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    bri = float(np.mean(gray))
    bright = float(np.mean(gray > 140))
    if yellow >= 0.35 and green < 0.20 and gold < 0.15 and red < 0.12:
        return {
            "green": round(green, 3),
            "gold": round(gold, 3),
            "red": round(red, 3),
            "bri": round(bri, 1),
            "bright": round(bright, 3),
            "active": False,
            "kind": "dealing",
            "yellow": round(yellow, 3),
        }
    # Đỏ LOSE vs vàng kim WIN: banner WIN+ thường có gold mạnh — ưu tiên gold
    # (ROI toast dễ dính chữ đỏ 'Nhà cái' / cầu đỏ → false LOSE)
    lose_like = red >= 0.18 and green < 0.45 and gold < 0.10
    win_like = (bright >= 0.15 and (green >= 0.28 or gold >= 0.10)) or gold >= 0.14
    active = lose_like or win_like
    if not active:
        kind = "none"
    elif gold >= 0.10 and gold >= red * 0.35:
        kind = "win"
    elif gold >= 0.12 and gold >= green * 0.35:
        kind = "win"
    elif lose_like and red >= green * 0.35:
        kind = "lose"
    elif green >= 0.30:
        kind = "green_toast"
    else:
        kind = "none"
    return {
        "green": round(green, 3),
        "gold": round(gold, 3),
        "red": round(red, 3),
        "bri": round(bri, 1),
        "bright": round(bright, 3),
        "active": active,
        "kind": kind,
        "yellow": round(yellow, 3),
    }


def _score_toast_crop(crop) -> dict:
    """Score toast; ROI rộng thì trượt cửa sổ để không bị thảm xanh pha loãng."""
    empty = _score_toast_crop_core(None)
    if crop is None or crop.size == 0:
        return empty
    h, w = crop.shape[:2]
    if w < 220:
        return _score_toast_crop_core(crop)
    best = empty
    best_key = -1.0
    win_w = min(220, w)
    step = 40
    for x0 in range(0, w - win_w + 1, step):
        sc = _score_toast_crop_core(crop[:, x0 : x0 + win_w])
        key = 0.0
        if sc.get("kind") == "win":
            # Ưu tiên WIN/gold hơn LOSE — tránh false LOSE vì chữ đỏ cạnh toast
            key = 120 + float(sc.get("gold") or 0) * 15 + float(sc.get("green") or 0) * 3
        elif sc.get("kind") == "lose":
            key = 90 + float(sc.get("red") or 0) * 10
        elif sc.get("kind") == "green_toast":
            key = 60 + float(sc.get("green") or 0) * 5
        elif sc.get("active"):
            key = 20
        if key > best_key:
            best_key = key
            best = sc
    return best if best_key > 0 else _score_toast_crop_core(crop)


def mid_status_toast_score(frame, config: dict | None = None) -> dict:
    """Thanh giữa trên lưới cược — Đang mở bài / Chúc may mắn / có thể WIN±."""
    cfg = config or {}
    r = cfg.get("roi_bet_status")
    if not r or not r.get("width"):
        r = {"x": 700, "y": 780, "width": 520, "height": 55}
    return _score_toast_crop(_crop(frame, r))


def toast_popup_score(frame, config: dict | None = None) -> dict:
    """Đo toast phải: xanh (thành công/WIN) / vàng kim / đỏ (lose)."""
    if frame is None:
        return _score_toast_crop(None)
    return _score_toast_crop(_crop(frame, _toast_roi(config)))


@dataclass
class SettlementDetector:
    change_threshold: float = 5.0
    min_dealing_ms: int = 2500
    cooldown_ms: int = 8000
    config: dict | None = None

    _baseline: np.ndarray | None = None
    _toast_base: np.ndarray | None = None
    _phase: str = "idle"
    _dealing_at: float = 0.0
    _last_fire_at: float = 0.0
    _armed: bool = False
    _saw_yellow: bool = False
    _baseline_locked: bool = False
    _yellow_gone_at: float = 0.0
    _buf: list = field(default_factory=list)
    _best_frame: np.ndarray | None = None
    _diag: dict = field(default_factory=dict)

    def reset_round(self) -> None:
        self._phase = "betting"
        self._armed = False
        self._baseline = None
        self._toast_base = None
        self._saw_yellow = False
        self._baseline_locked = False
        self._yellow_gone_at = 0.0
        self._buf = []
        self._best_frame = None

    def on_betting(self) -> None:
        """Đặt xong — chờ Đang mở bài. Bỏ qua toast 'Đặt cược thành công'."""
        self._phase = "wait_deal"
        self._armed = True
        self._saw_yellow = False
        self._baseline_locked = False
        self._baseline = None
        self._toast_base = None
        self._dealing_at = 0.0
        self._yellow_gone_at = 0.0
        self._buf = []
        self._best_frame = None

    def on_dealing(self, balance_crop, frame=None) -> None:
        self.on_betting()

    def _lock_after_yellow(self, balance_crop, frame) -> None:
        self._baseline = _fingerprint(balance_crop)
        toast = _crop(frame, _toast_roi(self.config))
        self._toast_base = _fingerprint(toast)
        self._baseline_locked = True
        self._dealing_at = time.time()
        self._phase = "dealing"
        self._yellow_gone_at = 0.0
        self._buf = []

    def _push_buf(self, frame, diag, mid, luck) -> None:
        if frame is None:
            return
        self._buf.append(
            {
                "t": time.time(),
                "frame": frame.copy(),
                "toast_on": bool(diag.get("toast_on")),
                "toast_kind": diag.get("toast_kind") or "none",
                "toast_g": float(diag.get("toast_g") or 0),
                "toast_gold": float(diag.get("toast_gold") or 0),
                "toast_red": float(diag.get("toast_red") or 0),
                "toast_bri": float(diag.get("toast_bri") or 0),
                "yellow": float(diag.get("yellow") or 0),
                "luck": float(luck or 0),
                "mid": mid,
                "bal_d": float(diag.get("bal_d") or 0),
            }
        )
        if len(self._buf) > 60:
            self._buf.pop(0)

    def _pick_best_from_buf(self) -> dict | None:
        """Chọn frame buffer có toast phải / mid kết quả (không phải Chúc may mắn)."""
        best = None
        best_score = -1.0
        for it in self._buf:
            score = 0.0
            kind = "none"
            if it["toast_on"]:
                # Ưu tiên gold (WIN+) hơn red — tránh false LOSE
                score += 10 + it["toast_bri"] / 20.0 + it["toast_gold"] * 8 + it["toast_red"] * 3
                kind = it["toast_kind"]
                if float(it.get("toast_gold") or 0) >= 0.12 and kind == "lose":
                    kind = "win"
                    score += 6
            mid = it.get("mid") or {}
            if mid.get("active") and mid.get("kind") in ("win", "lose", "green_toast"):
                # bỏ Chúc may mắn: luck cao + green thuần
                if not (it["luck"] >= 0.08 and mid.get("kind") == "green_toast" and float(mid.get("gold") or 0) < 0.05):
                    score += 8 + float(mid.get("bri") or 0) / 20.0 + float(mid.get("gold") or 0) * 6
                    # Không để mid win đè toast lose đỏ
                    if kind == "lose" and float(it.get("toast_red") or 0) >= 0.18:
                        pass
                    elif mid.get("kind") == "win" and float(it.get("toast_red") or 0) < 0.22:
                        kind = "win"
                    elif kind == "none":
                        kind = mid.get("kind")
                    elif mid.get("kind") == "lose" and kind != "win":
                        kind = "lose"
            if score > best_score:
                best_score = score
                best = {**it, "pick_kind": kind, "pick_score": score}
        if best is None or best_score < 8.0:
            return None
        return best

    @staticmethod
    def _tie_green_ratio(frame, config: dict | None) -> float:
        """
        Hòa: panel điểm góc phải nền XANH LÁ (Tay con/Nhà cái cùng màu xanh)
        + toast vẫn hiện WIN +0.00. Ô Hòa giữa bàn thường vàng kim, không xanh.
        """
        cfg = config or {}
        if frame is None:
            return 0.0
        # Panel điểm hết ván (đo từ ảnh Hòa H9/H14: xanh ~0.70; WIN/LOSE thường ~0.00–0.28)
        roi = cfg.get("roi_score_panel") or {"x": 1310, "y": 840, "width": 360, "height": 140}
        crop = _crop(frame, roi)
        if crop is None or crop.size == 0:
            return 0.0
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (35, 50, 50), (100, 255, 255))
        return float(mask.mean() / 255.0)

    @staticmethod
    def _resolve_kind(
        toast_kind: str,
        mid: dict | None,
        toast_gold: float = 0.0,
        toast_red: float = 0.0,
        tie_green: float = 0.0,
    ) -> str:
        """
        Gộp toast phải + mid.
        Toast LOSE đỏ rõ → không để mid/gold ghi đè (bug H2).
        WIN + ô Hòa xanh → tie (WIN+TIE).
        """
        mid = mid or {}
        mk = mid.get("kind") or "none"
        mg = float(mid.get("gold") or 0)
        tk = toast_kind or "none"
        tg = float(toast_gold or 0)
        tr = float(toast_red or 0)

        # 1) Toast phải: LOSE đỏ thuần vs WIN vàng kim (không để chữ đỏ 'Nhà cái' phá WIN)
        if tk == "lose" and tr >= 0.18 and (tg < 0.08 or tr >= tg * 2.0):
            kind = "lose"
        elif tk == "win" and tg >= 0.12:
            kind = "win"
        elif tr >= 0.40 and tg < 0.10:
            # Banner LOSE đỏ rõ, gần như không gold
            kind = "lose"
        elif tg >= 0.16 and tg >= tr * 0.45:
            kind = "win"
        elif mk == "win" and mg >= 0.18 and tr < 0.25 and tg >= 0.08:
            kind = "win"
        elif mk == "lose" and tr >= 0.25 and tg < 0.10:
            kind = "lose"
        elif tk in ("win", "lose", "green_toast"):
            kind = tk
        elif mk in ("win", "lose"):
            kind = mk
        else:
            kind = "none"

        # 2) Hòa: toast WIN (+0.00) + panel điểm xanh lá mạnh (không tin ô Hòa vàng)
        tie_g = float(tie_green or 0)
        if kind in ("win", "green_toast") and tie_g >= 0.45:
            kind = "tie"
        return kind

    @staticmethod
    def _outcome_label(kind: str) -> str:
        if kind == "lose":
            return "LOSE-"
        if kind == "tie":
            return "WIN+TIE"
        return "WIN+"

    def diagnose(self, balance_crop, frame=None) -> dict:
        from bet_window import betting_open_score

        cfg = self.config or {}
        sc = betting_open_score(frame, cfg) if frame is not None else {}
        toast = toast_popup_score(frame, cfg) if frame is not None else {}
        fp = _fingerprint(balance_crop)
        tfp = _fingerprint(_crop(frame, _toast_roi(cfg))) if frame is not None else None
        bal_d = _delta(self._baseline, fp) if self._baseline_locked else 0.0
        toast_d = _delta(self._toast_base, tfp) if self._baseline_locked else 0.0
        elapsed = int((time.time() - self._dealing_at) * 1000) if self._dealing_at else 0
        tie_g = self._tie_green_ratio(frame, cfg)
        self._diag = {
            "phase": self._phase,
            "armed": self._armed,
            "saw_yellow": self._saw_yellow,
            "baseline_locked": self._baseline_locked,
            "elapsed_ms": elapsed,
            "bal_d": round(bal_d, 2),
            "toast_d": round(toast_d, 2),
            "toast_g": toast.get("green", 0),
            "toast_gold": toast.get("gold", 0),
            "toast_red": toast.get("red", 0),
            "toast_bri": toast.get("bri", 0),
            "toast_kind": toast.get("kind", "none"),
            "toast_on": toast.get("active", False),
            "yellow": sc.get("status_yellow", 0),
            "luck": sc.get("luck_green", 0),
            "open": sc.get("open", False),
            "buf": len(self._buf),
            "gold": toast.get("gold", 0),
            "plus": toast.get("green", 0),
            "tie": round(tie_g, 3),
            "tie_green": round(tie_g, 3),
        }
        return self._diag

    def update(
        self,
        balance_crop,
        result_color: str = "EMPTY_OR_UNKNOWN",
        frame=None,
    ) -> dict | None:
        now = time.time()
        if (now - self._last_fire_at) * 1000 < self.cooldown_ms:
            return None
        if not self._armed:
            return None

        diag = self.diagnose(balance_crop, frame)
        yellow = float(diag.get("yellow") or 0)
        luck = float(diag.get("luck") or 0)
        mid = mid_status_toast_score(frame, self.config) if frame is not None else {}

        if self._phase == "wait_deal":
            if yellow >= 0.08:
                self._saw_yellow = True
                self._lock_after_yellow(balance_crop, frame)
            return None

        if self._phase not in ("dealing", "watch_toast") or not self._baseline_locked:
            return None

        elapsed_ms = diag["elapsed_ms"]
        # Buffer suốt dealing để bắt toast flash (biến mất trước Chúc may mắn)
        if elapsed_ms >= 1500:
            self._push_buf(frame, diag, mid, luck)

        if elapsed_ms < self.min_dealing_ms:
            return None

        toast_on = bool(diag.get("toast_on"))
        kind = self._resolve_kind(
            diag.get("toast_kind") or "none",
            mid,
            float(diag.get("toast_gold") or 0),
            float(diag.get("toast_red") or 0),
            float(diag.get("tie_green") or diag.get("tie") or 0),
        )

        # Live: toast phải sáng trong lúc / sau mở bài
        if toast_on and elapsed_ms >= 4000:
            return self._fire(
                frame,
                result_color,
                diag,
                mid,
                reason=f"live_{kind}",
                outcome=self._outcome_label(kind),
            )

        # Chuyển hết vàng / sang Chúc may mắn → quét buffer
        transition = yellow < 0.10 or luck >= 0.08
        if self._phase == "dealing" and transition and elapsed_ms >= 5000:
            self._phase = "watch_toast"
            self._yellow_gone_at = now
            picked = self._pick_best_from_buf()
            if picked is not None:
                pk = self._resolve_kind(
                    picked.get("pick_kind") or "none",
                    picked.get("mid") or {},
                    float(picked.get("toast_gold") or 0),
                    float(picked.get("toast_red") or 0),
                    self._tie_green_ratio(picked.get("frame"), self.config),
                )
                return self._fire(
                    picked["frame"],
                    result_color,
                    diag,
                    picked.get("mid") or {},
                    reason=f"buf_{pk}",
                    outcome=self._outcome_label(pk),
                )

        if self._phase == "watch_toast":
            if toast_on:
                return self._fire(
                    frame,
                    result_color,
                    diag,
                    mid,
                    reason=f"watch_{kind}",
                    outcome=self._outcome_label(kind),
                )
            bal_hit = float(diag.get("bal_d") or 0) >= self.change_threshold
            if bal_hit:
                return self._fire(
                    frame,
                    result_color,
                    diag,
                    mid,
                    reason="balance_delta",
                    outcome="WIN+" if float(diag.get("bal_d") or 0) > 0 else "LOSE-",
                )
            if (now - self._yellow_gone_at) > 8.0:
                # vẫn thử buffer lần cuối
                picked = self._pick_best_from_buf()
                if picked is not None:
                    pk = self._resolve_kind(
                        picked.get("pick_kind") or "none",
                        picked.get("mid") or {},
                        float(picked.get("toast_gold") or 0),
                        float(picked.get("toast_red") or 0),
                        self._tie_green_ratio(picked.get("frame"), self.config),
                    )
                    return self._fire(
                        picked["frame"],
                        result_color,
                        diag,
                        picked.get("mid") or {},
                        reason=f"late_buf_{pk}",
                        outcome=self._outcome_label(pk),
                    )
                self._armed = False
                self._phase = "missed"
            return None

        return None

    def _fire(self, frame, result_color, diag, mid, reason: str, outcome: str) -> dict:
        self._last_fire_at = time.time()
        self._armed = False
        self._phase = "settled"
        self._best_frame = frame
        return {
            "type": "SETTLEMENT",
            "delta": diag.get("bal_d"),
            "reason": reason,
            "outcome": outcome,
            "banner": result_color,
            "payout_gold": diag.get("toast_gold"),
            "payout_tie": 0.0,
            "payout_zone": "toast",
            "elapsed_ms": diag.get("elapsed_ms"),
            "diag": diag,
            "mid": mid,
            "frame": frame,
        }


def classify_settlement_frame(frame, config: dict | None = None) -> dict:
    """Phân loại WIN+/LOSE-/WIN+TIE từ 1 frame full cửa sổ."""
    cfg = config or {}
    if frame is None:
        return {"outcome": "END", "kind": "none", "ok": False, "detail": "frame=None"}
    toast = toast_popup_score(frame, cfg)
    mid = mid_status_toast_score(frame, cfg)
    tie_g = SettlementDetector._tie_green_ratio(frame, cfg)
    kind = SettlementDetector._resolve_kind(
        toast.get("kind") or "none",
        mid,
        float(toast.get("gold") or 0),
        float(toast.get("red") or 0),
        tie_g,
    )
    outcome = SettlementDetector._outcome_label(kind)
    return {
        "ok": kind in ("win", "lose", "tie"),
        "kind": kind,
        "outcome": outcome,
        "toast": toast,
        "mid": mid,
        "tie_green": round(tie_g, 3),
        "detail": (
            f"kind={kind} toast={toast.get('kind')} g={toast.get('gold')} "
            f"r={toast.get('red')} mid={mid.get('kind')} tie_g={tie_g:.3f}"
        ),
    }


def _pad_capture_to_full(img, top_skip_frac: float = 0.25, taskbar_px: int = 48):
    """Ảnh đã crop (bỏ top+taskbar) → pad lại gần full để ROI config còn khớp."""
    if img is None:
        return None
    h, w = img.shape[:2]
    # crop_h ≈ H*(1-top_skip) - taskbar → H ≈ (crop_h + taskbar)/(1-top_skip)
    frac = max(0.05, min(0.5, float(top_skip_frac)))
    full_h = int(round((h + int(taskbar_px)) / (1.0 - frac)))
    pad_top = max(0, int(round(full_h * frac)))
    pad_bot = max(0, full_h - pad_top - h)
    return cv2.copyMakeBorder(img, pad_top, pad_bot, 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))


def classify_saved_capture(
    path: str,
    config: dict | None = None,
    top_skip_frac: float = 0.25,
    taskbar_px: int = 48,
) -> dict:
    """Đọc file capture đã crop → phân loại lại."""
    img = cv2.imread(path)
    if img is None:
        return {"ok": False, "outcome": "END", "kind": "none", "detail": "read_fail"}
    full = _pad_capture_to_full(img, top_skip_frac, taskbar_px)
    return classify_settlement_frame(full, config)


def outcome_from_filename(path: str) -> str:
    name = os.path.basename(path)
    for tag in ("WIN+TIE", "LOSE-", "WIN+", "TIE"):
        if f"_{tag}_" in f"_{name}_" or name.startswith(f"SETTLE_{tag}_"):
            return tag
    # SETTLE_LOSE-_H1_...
    if "LOSE-" in name or "_LOSE" in name:
        return "LOSE-"
    if "WIN+TIE" in name or "TIE" in name and "WIN" in name:
        return "WIN+TIE"
    if "WIN+" in name:
        return "WIN+"
    return "END"


def verify_capture_label(
    path: str,
    config: dict | None = None,
    top_skip_frac: float = 0.25,
    taskbar_px: int = 48,
    expected: str | None = None,
) -> dict:
    """
    Check tên file vs nội dung ảnh.
    Trùng → match=True. Sai → trả actual để rename.
    """
    label = expected or outcome_from_filename(path)
    cls = classify_saved_capture(path, config, top_skip_frac, taskbar_px)
    actual = cls.get("outcome") or "END"
    match = label == actual and cls.get("ok")
    return {
        "match": bool(match),
        "label": label,
        "actual": actual,
        "ok": bool(cls.get("ok")),
        "detail": cls.get("detail") or "",
        "path": path,
    }


def get_taskbar_height(fallback: int = 48) -> int:
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW("Shell_TrayWnd", None)
        if not hwnd:
            return fallback
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return fallback
        h = int(rect.bottom - rect.top)
        if 24 <= h <= 120:
            return h
    except Exception:
        pass
    return fallback


def crop_capture_frame(frame, top_skip_frac: float = 0.25, taskbar_px: int | None = None):
    if frame is None or getattr(frame, "size", 0) == 0:
        return None, {"ok": False}
    h, w = frame.shape[:2]
    tb = int(taskbar_px if taskbar_px is not None else get_taskbar_height())
    tb = max(0, min(tb, h // 5))
    y0 = int(h * float(top_skip_frac))
    y1 = max(y0 + 1, h - tb)
    crop = frame[y0:y1, 0:w]
    return crop, {
        "ok": True,
        "y0": y0,
        "y1": y1,
        "taskbar_px": tb,
        "src_h": h,
        "src_w": w,
        "out_h": int(crop.shape[0]),
        "out_w": int(crop.shape[1]),
    }


def save_settlement_capture(
    frame,
    path: str,
    top_skip_frac: float = 0.25,
    taskbar_px: int | None = None,
) -> tuple[bool, dict]:
    cropped, meta = crop_capture_frame(frame, top_skip_frac, taskbar_px)
    if cropped is None:
        return False, meta
    gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
    if float(np.std(gray)) < 10 or float(np.mean(gray)) > 240:
        return False, {**meta, "ok": False, "reason": "blank_frame", "path": path}
    ok = bool(cv2.imwrite(path, cropped))
    meta["path"] = path
    meta["saved"] = ok
    return ok, meta


def grab_valid_window(grabber, win_rect, retries: int = 8, delay: float = 0.1):
    best, best_std = None, -1.0
    for _ in range(max(1, retries)):
        fr = grabber.grab_window(win_rect)
        if fr is None:
            time.sleep(delay)
            continue
        s = float(np.std(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)))
        if s > best_std:
            best_std, best = s, fr
        if s >= 12 and float(np.mean(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY))) < 230:
            return fr
        time.sleep(delay)
    return best

