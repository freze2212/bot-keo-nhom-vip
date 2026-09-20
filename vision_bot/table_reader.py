"""Đọc mã bàn Sexy từ ảnh (góc trái dưới: 'Baccarat C09')."""
from __future__ import annotations

import os
import re
from typing import Any

import cv2
import numpy as np

_OCR = None
_TABLE_RE = re.compile(r"(?:baccarat\s*)?c\s*0*(\d{1,2})\b", re.I)
_TABLE_RE_GLUE = re.compile(r"baccarat\s*c\s*0*(\d{1,2})", re.I)


def _get_ocr():
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR

        _OCR = RapidOCR()
    return _OCR


def _norm_table(num: int) -> str:
    return f"C{int(num):02d}"


def _parse_table_text(text: str) -> str | None:
    if not text:
        return None
    t = str(text).replace(" ", "")
    m = _TABLE_RE_GLUE.search(t) or _TABLE_RE.search(str(text))
    if not m:
        m = _TABLE_RE.search(t)
    if not m:
        return None
    n = int(m.group(1))
    if 1 <= n <= 99:
        return _norm_table(n)
    return None


def _default_rois(h: int, w: int) -> list[tuple[int, int, int, int]]:
    """ROI tương đối — khớp cả full Chrome lẫn ảnh đã crop top."""
    return [
        (0, int(h * 0.70), int(w * 0.28), int(h * 0.10)),
        (0, int(h * 0.72), int(w * 0.22), int(h * 0.08)),
        (0, int(h * 0.68), int(w * 0.25), int(h * 0.12)),
        (0, int(h * 0.55), int(w * 0.30), int(h * 0.12)),  # full frame (chưa crop top)
        (0, int(h * 0.78), int(w * 0.20), int(h * 0.06)),
    ]


def _rois_from_config(h: int, w: int, config: dict | None) -> list[tuple[int, int, int, int]]:
    cfg = config or {}
    roi = cfg.get("roi_table_name")
    out: list[tuple[int, int, int, int]] = []
    if isinstance(roi, dict) and all(k in roi for k in ("x", "y", "width", "height")):
        out.append(
            (
                int(roi["x"]),
                int(roi["y"]),
                int(roi["width"]),
                int(roi["height"]),
            )
        )
    out.extend(_default_rois(h, w))
    return out


def read_table_from_frame(
    frame: np.ndarray | None,
    config: dict | None = None,
) -> tuple[str | None, str]:
    """
    Trả (Cxx | None, detail).
    """
    if frame is None or not getattr(frame, "size", 0):
        return None, "frame=None"
    h, w = frame.shape[:2]
    ocr = _get_ocr()
    texts: list[str] = []
    for x, y, ww, hh in _rois_from_config(h, w, config):
        if ww <= 0 or hh <= 0:
            continue
        x2, y2 = min(w, x + ww), min(h, y + hh)
        x1, y1 = max(0, x), max(0, y)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            continue
        try:
            res, _ = ocr(crop)
        except Exception as ex:
            return None, f"ocr_err|{ex}"
        if not res:
            continue
        for item in res:
            t = item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else str(item)
            texts.append(t)
            hit = _parse_table_text(t)
            if hit:
                return hit, f"ok text={t!r} roi=({x1},{y1},{x2 - x1},{y2 - y1})"
        # Ghép nhiều dòng trong cùng ROI (Baccarat + C09)
        joined = " ".join(texts[-4:])
        hit = _parse_table_text(joined)
        if hit:
            return hit, f"ok joined={joined!r}"
    return None, f"miss texts={texts[:8]}"


def read_table_from_image(
    path: str,
    config: dict | None = None,
) -> tuple[str | None, str]:
    if not path or not os.path.exists(path):
        return None, "missing"
    img = cv2.imread(path)
    if img is None:
        return None, "read_fail"
    return read_table_from_frame(img, config)


def read_table_batch(paths: list[str], config: dict | None = None) -> list[dict[str, Any]]:
    out = []
    for p in paths:
        table, detail = read_table_from_image(p, config)
        out.append(
            {
                "path": p,
                "file": os.path.basename(p),
                "table": table,
                "detail": detail,
            }
        )
    return out


if __name__ == "__main__":
    import glob
    import json

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    patterns = [
        os.path.join(root, "public", "screenshots", "sexy_*.png"),
        os.path.join(root, "vision_bot", "captures", "live", "*.png"),
    ]
    files: list[str] = []
    for pat in patterns:
        files.extend(glob.glob(pat))
    files = sorted(set(files), key=os.path.getmtime, reverse=True)
    rows = read_table_batch(files)
    for r in rows:
        print(f"{r['table'] or '????'}  {r['file']}  | {r['detail']}")
    ok = sum(1 for r in rows if r["table"])
    print(json.dumps({"ok": ok, "total": len(rows)}, ensure_ascii=False))
