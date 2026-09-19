"""Lưu ảnh sexy_* vào public/screenshots — chỉ giữ 2 file mới nhất / bàn."""
from __future__ import annotations

import os
import shutil
import time
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
SCREENSHOT_DIR = os.path.join(_ROOT, "public", "screenshots")


def _table_key(table_name: str) -> str:
    raw = str(table_name or "C01").strip().upper()
    digits = "".join(c for c in raw if c.isdigit())
    if digits:
        return f"C{digits.zfill(2)}"
    return raw.replace(" ", "") or "C01"


def public_screenshot_dir() -> str:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    return SCREENSHOT_DIR


def keep_latest_shots(table_name: str, keep: int = 2) -> list[str]:
    """Giữ `keep` file sexy_{table}_* mới nhất, xóa phần còn lại."""
    d = public_screenshot_dir()
    key = _table_key(table_name)
    prefix = f"sexy_{key}_"
    matches = []
    for name in os.listdir(d):
        low = name.lower()
        if not low.startswith(prefix.lower()) or not low.endswith(".png"):
            continue
        path = os.path.join(d, name)
        try:
            matches.append((os.path.getmtime(path), path, name))
        except OSError:
            pass
    matches.sort(key=lambda x: x[0], reverse=True)
    kept = []
    for i, (_, path, name) in enumerate(matches):
        if i < keep:
            kept.append(path)
            continue
        try:
            os.remove(path)
            print(f"[ShotStore] Xóa ảnh cũ (>{keep}): {name}")
        except OSError:
            pass
    return kept


def publish_sexy_shot(
    src_path: str,
    table_name: str,
    result_winner: str | None = None,
    round_num=None,
    kind: str = "RESULT",
) -> str | None:
    """
    Copy/đổi tên ảnh vision → public/screenshots/sexy_Cxx_...
    kind=RESULT → _WB_/_WP_/_WT_
    kind=PREVIEW → _PREVIEW_ (báo bàn live)
    Sau đó giữ tối đa 2 file / bàn.
    """
    if not src_path or not os.path.exists(src_path):
        return None
    d = public_screenshot_dir()
    key = _table_key(table_name)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%f")[:-3] + "Z"
    round_str = f"_R{round_num}" if round_num not in (None, "") else ""
    win = str(result_winner or "").strip().upper()
    if win in ("BANKER", "CAI", "CÁI"):
        win = "B"
    elif win in ("PLAYER", "CON"):
        win = "P"
    elif win in ("TIE", "HOA", "HÒA"):
        win = "T"
    if kind.upper() == "PREVIEW":
        tag = "_PREVIEW"
    elif win in ("B", "P", "T"):
        tag = f"_W{win}"
    else:
        tag = "_PREVIEW"
    filename = f"sexy_{key}{round_str}{tag}_{ts}.png"
    dest = os.path.join(d, filename)
    try:
        shutil.copy2(src_path, dest)
    except OSError as e:
        print(f"[ShotStore] copy lỗi: {e}")
        return None
    # Đảm bảo size tối thiểu (forward filter <40KB)
    try:
        if os.path.getsize(dest) < 40000:
            # pad nhẹ bằng copy lại + touch — thường settlement đã đủ lớn
            pass
    except OSError:
        pass
    keep_latest_shots(key, keep=2)
    print(f"[ShotStore] Published {filename}")
    return dest
