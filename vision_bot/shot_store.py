"""
Lưu ảnh sexy_* theo slot / bàn (đè in-place, không phình ổ):

  LAST_WIN   — chỉ đè khi settle WIN
  LAST_LOSS  — chỉ đè khi settle LOSS
  LAST_TIE   — chỉ đè khi settle TIE
  CURRENT    — mọi settle (nhóm thật gửi sau hô)
  PREVIEW    — báo bàn live (1 file)
"""
from __future__ import annotations

import glob
import os
import shutil
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
SCREENSHOT_DIR = os.path.join(_ROOT, "public", "screenshots")

KEEP_SHOTS = 5  # LAST_WIN/LOSS/TIE + CURRENT + PREVIEW
SLOT_KINDS = ("last_win", "last_loss", "last_tie", "current", "preview")


def _table_key(table_name: str) -> str:
    raw = str(table_name or "C01").strip().upper()
    digits = "".join(c for c in raw if c.isdigit())
    if digits:
        return f"C{digits.zfill(2)}"
    return raw.replace(" ", "") or "C01"


def public_screenshot_dir() -> str:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    return SCREENSHOT_DIR


def _norm_winner(result_winner: str | None) -> str | None:
    win = str(result_winner or "").strip().upper()
    if win in ("BANKER", "CAI", "CÁI", "B"):
        return "B"
    if win in ("PLAYER", "CON", "P"):
        return "P"
    if win in ("TIE", "HOA", "HÒA", "T"):
        return "T"
    return None


def _norm_outcome(result_outcome: str | None) -> str | None:
    out = str(result_outcome or "").strip().upper()
    if out in ("WIN+", "WIN"):
        return "WIN"
    if out in ("LOSE-", "LOSE", "LOSS"):
        return "LOSS"
    if out in ("WIN+TIE", "TIE", "HÒA", "HOA"):
        return "TIE"
    return None


def time_mtime() -> float:
    return time.time()


def _rm_glob(pattern: str) -> int:
    n = 0
    for path in glob.glob(pattern):
        try:
            os.remove(path)
            n += 1
        except OSError:
            pass
    return n


def _write_file(src_path: str, dest: str) -> str | None:
    try:
        if not src_path or not os.path.exists(src_path):
            return None
        # Chặn ghi slot từ ảnh Cursor/blank (<350KB)
        try:
            if os.path.getsize(src_path) < 350_000:
                print(f"[ShotStore] SKIP write — file quá nhỏ: {src_path}")
                return None
        except OSError:
            return None
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        shutil.copy2(src_path, dest)
        now = time_mtime()
        os.utime(dest, (now, now))
        return dest if os.path.exists(dest) else None
    except OSError as e:
        print(f"[ShotStore] ghi lỗi: {e}")
        return None


def _winner_from_name(path: str) -> str | None:
    up = os.path.basename(path).upper()
    if "CURRENT_WB" in up or "LAST_WIN_WB" in up or "LAST_LOSS_WB" in up or "_WB_" in up or "_WB_WIN" in up or "_WB_LOSS" in up:
        return "B"
    if "CURRENT_WP" in up or "LAST_WIN_WP" in up or "LAST_LOSS_WP" in up or "_WP_" in up or "_WP_WIN" in up or "_WP_LOSS" in up:
        return "P"
    if "CURRENT_WT" in up or "LAST_TIE" in up or "_WT_" in up or "_WT_TIE" in up:
        return "T"
    return None


def _find_slot(table_name: str, slot: str) -> str | None:
    d = public_screenshot_dir()
    key = _table_key(table_name)
    if slot == "preview":
        path = os.path.join(d, f"sexy_{key}_PREVIEW.png")
        return path if os.path.exists(path) else None
    slot_u = slot.upper()  # LAST_WIN / LAST_LOSS / LAST_TIE / CURRENT
    pats = [
        os.path.join(d, f"sexy_{key}_{slot_u}_*.png"),
        os.path.join(d, f"sexy_{key}_{slot_u}.png"),
    ]
    found = []
    for pat in pats:
        for path in glob.glob(pat):
            try:
                found.append((os.path.getmtime(path), path))
            except OSError:
                pass
    if not found:
        return None
    found.sort(key=lambda x: x[0], reverse=True)
    return found[0][1]


def get_last_outcome_shot(table_name: str, outcome: str) -> tuple[str | None, str | None]:
    """Ảo: lấy slot LAST_{WIN|LOSS|TIE} + winner cửa bàn."""
    out = _norm_outcome(outcome) or str(outcome or "").upper()
    slot_map = {"WIN": "last_win", "LOSS": "last_loss", "TIE": "last_tie"}
    slot = slot_map.get(out)
    if not slot:
        return None, None
    path = _find_slot(table_name, slot)
    if not path:
        return None, None
    return path, _winner_from_name(path)


def get_last_win_shot(table_name: str) -> tuple[str | None, str | None]:
    return get_last_outcome_shot(table_name, "WIN")


def get_current_shot(table_name: str) -> str | None:
    return _find_slot(table_name, "current")


def get_preview_shot(table_name: str) -> str | None:
    return _find_slot(table_name, "preview")


def prune_table_to_slots(table_name: str) -> int:
    d = public_screenshot_dir()
    key = _table_key(table_name)
    prefix = f"sexy_{key}_".lower()
    keep = set()
    for slot in SLOT_KINDS:
        p = _find_slot(key, slot)
        if p:
            keep.add(os.path.abspath(p))
    removed = 0
    try:
        names = list(os.listdir(d))
    except OSError:
        return 0
    for name in names:
        low = name.lower()
        if not low.startswith(prefix) or not low.endswith(".png"):
            continue
        path = os.path.abspath(os.path.join(d, name))
        if path in keep:
            continue
        try:
            os.remove(path)
            removed += 1
            print(f"[ShotStore] Xóa ngoài slot: {name}")
        except OSError:
            pass
    return removed


def rekey_table_slots(old_table: str, new_table: str) -> int:
    """Khi OCR đổi C01→C09: copy slot sexy_old_* → sexy_new_* (giữ file cũ)."""
    old_k = _table_key(old_table)
    new_k = _table_key(new_table)
    if old_k == new_k:
        return 0
    d = public_screenshot_dir()
    n = 0
    try:
        names = list(os.listdir(d))
    except OSError:
        return 0
    prefix = f"sexy_{old_k}_"
    for name in names:
        if not name.startswith(prefix) or not name.lower().endswith(".png"):
            continue
        src = os.path.join(d, name)
        dest_name = name.replace(prefix, f"sexy_{new_k}_", 1)
        dest = os.path.join(d, dest_name)
        if os.path.exists(dest):
            continue
        if _write_file(src, dest):
            n += 1
            print(f"[ShotStore] Rekey {name} → {dest_name}")
    if n:
        prune_table_to_slots(new_k)
    return n


def migrate_legacy_to_slots(table_name: str) -> None:
    """Boot: đổ legacy vào LAST_WIN/LOSS/TIE + CURRENT + PREVIEW."""
    d = public_screenshot_dir()
    key = _table_key(table_name)
    if _find_slot(key, "last_win") or _find_slot(key, "current"):
        prune_table_to_slots(key)
        return
    buckets = {"win": [], "loss": [], "tie": [], "settle": [], "preview": []}
    try:
        names = os.listdir(d)
    except OSError:
        return
    for name in names:
        low = name.lower()
        if not low.startswith(f"sexy_{key}_".lower()) or not low.endswith(".png"):
            continue
        path = os.path.join(d, name)
        try:
            m = os.path.getmtime(path)
        except OSError:
            continue
        if "preview" in low:
            buckets["preview"].append((m, path, name))
        elif "_loss" in low:
            buckets["loss"].append((m, path, name))
            buckets["settle"].append((m, path, name))
        elif "_tie" in low:
            buckets["tie"].append((m, path, name))
            buckets["settle"].append((m, path, name))
        elif "_win" in low:
            buckets["win"].append((m, path, name))
            buckets["settle"].append((m, path, name))
        elif "_wb_" in low or "_wp_" in low or "_wt_" in low:
            buckets["settle"].append((m, path, name))

    def _pick_win_tag(name: str) -> str:
        low = name.lower()
        if "_wb" in low:
            return "B"
        if "_wp" in low:
            return "P"
        if "_wt" in low:
            return "T"
        return "B"

    if buckets["win"] and not _find_slot(key, "last_win"):
        buckets["win"].sort(key=lambda x: x[0], reverse=True)
        path, name = buckets["win"][0][1], buckets["win"][0][2]
        w = _pick_win_tag(name)
        _write_file(path, os.path.join(d, f"sexy_{key}_LAST_WIN_W{w}_WIN.png"))
        print(f"[ShotStore] Migrate LAST_WIN ← {name}")
    if buckets["loss"] and not _find_slot(key, "last_loss"):
        buckets["loss"].sort(key=lambda x: x[0], reverse=True)
        path, name = buckets["loss"][0][1], buckets["loss"][0][2]
        w = _pick_win_tag(name)
        _write_file(path, os.path.join(d, f"sexy_{key}_LAST_LOSS_W{w}_LOSS.png"))
        print(f"[ShotStore] Migrate LAST_LOSS ← {name}")
    if buckets["tie"] and not _find_slot(key, "last_tie"):
        buckets["tie"].sort(key=lambda x: x[0], reverse=True)
        path, name = buckets["tie"][0][1], buckets["tie"][0][2]
        _write_file(path, os.path.join(d, f"sexy_{key}_LAST_TIE_WT_TIE.png"))
        print(f"[ShotStore] Migrate LAST_TIE ← {name}")
    if buckets["settle"] and not _find_slot(key, "current"):
        buckets["settle"].sort(key=lambda x: x[0], reverse=True)
        path, name = buckets["settle"][0][1], buckets["settle"][0][2]
        low = name.lower()
        w = _pick_win_tag(name)
        o = "LOSS" if "_loss" in low else ("TIE" if "_tie" in low else "WIN")
        _write_file(path, os.path.join(d, f"sexy_{key}_CURRENT_W{w}_{o}.png"))
        print(f"[ShotStore] Migrate CURRENT ← {name}")
    if buckets["preview"] and not _find_slot(key, "preview"):
        buckets["preview"].sort(key=lambda x: x[0], reverse=True)
        _write_file(buckets["preview"][0][1], os.path.join(d, f"sexy_{key}_PREVIEW.png"))
        print(f"[ShotStore] Migrate PREVIEW ← {buckets['preview'][0][2]}")
    prune_table_to_slots(key)


def prune_live_captures(capture_dir: str, keep: int = KEEP_SHOTS) -> int:
    if not capture_dir or not os.path.isdir(capture_dir):
        return 0
    buckets = {
        "current": [],
        "last_win": [],
        "last_loss": [],
        "last_tie": [],
        "preview": [],
        "other_ok": [],
    }
    removed = 0
    for name in os.listdir(capture_dir):
        path = os.path.join(capture_dir, name)
        if not os.path.isfile(path):
            continue
        low = name.lower()
        if not low.endswith((".png", ".jpg", ".jpeg", ".webp")):
            continue
        try:
            m = os.path.getmtime(path)
        except OSError:
            continue
        if "last_win" in low and "settle" in low:
            buckets["last_win"].append((m, path, name))
        elif "last_loss" in low and "settle" in low:
            buckets["last_loss"].append((m, path, name))
        elif "last_tie" in low and "settle" in low:
            buckets["last_tie"].append((m, path, name))
        elif "current" in low and "settle" in low:
            buckets["current"].append((m, path, name))
        elif "force_" in low and "preview" in low:
            buckets["preview"].append((m, path, name))
        elif low.endswith("_settle.png"):
            buckets["other_ok"].append((m, path, name))
        else:
            try:
                os.remove(path)
                removed += 1
                print(f"[ShotStore] Xóa live linh tinh: {name}")
            except OSError:
                pass

    def keep_n(items, n):
        nonlocal removed
        items.sort(key=lambda x: x[0], reverse=True)
        for i, (_, path, name) in enumerate(items):
            if i < n:
                continue
            try:
                os.remove(path)
                removed += 1
                print(f"[ShotStore] Xóa live dư: {name}")
            except OSError:
                pass

    for k in ("last_win", "last_loss", "last_tie", "current", "preview"):
        keep_n(buckets[k], 1)
    keep_n(buckets["other_ok"], 0 if buckets["current"] else 1)
    return removed


def clear_step_debug(debug_dir: str | None = None) -> int:
    candidates = []
    if debug_dir:
        if os.path.isabs(debug_dir):
            candidates.append(debug_dir)
        else:
            candidates.append(os.path.join(_HERE, debug_dir))
            candidates.append(os.path.join(_ROOT, debug_dir))
            candidates.append(debug_dir)
    else:
        candidates.append(os.path.join(_HERE, "captures", "step_debug"))
    target = next((p for p in candidates if os.path.isdir(p)), None)
    if not target:
        return 0
    n = 0
    for name in os.listdir(target):
        path = os.path.join(target, name)
        if not os.path.isfile(path):
            continue
        if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            continue
        try:
            os.remove(path)
            n += 1
        except OSError:
            pass
    if n:
        print(f"[ShotStore] Đã xóa {n} ảnh step_debug ({target})")
    return n


def keep_latest_shots(table_name: str, keep: int = KEEP_SHOTS) -> list[str]:
    migrate_legacy_to_slots(table_name)
    prune_table_to_slots(table_name)
    out = []
    for slot in SLOT_KINDS:
        p = _find_slot(table_name, slot)
        if p:
            out.append(p)
    return out


def publish_sexy_shot(
    src_path: str,
    table_name: str,
    result_winner: str | None = None,
    round_num=None,
    kind: str = "RESULT",
    result_outcome: str | None = None,
) -> str | None:
    if not src_path or not os.path.exists(src_path):
        return None
    d = public_screenshot_dir()
    key = _table_key(table_name)
    win = _norm_winner(result_winner)
    out = _norm_outcome(result_outcome)
    kind_u = str(kind or "RESULT").upper()
    live_dir = os.path.dirname(os.path.abspath(src_path))
    in_live = "captures" in live_dir.replace("\\", "/").lower()

    if kind_u == "PREVIEW":
        _rm_glob(os.path.join(d, f"sexy_{key}_PREVIEW*.png"))
        dest = os.path.join(d, f"sexy_{key}_PREVIEW.png")
        published = _write_file(src_path, dest)
        if in_live:
            live_p = os.path.join(live_dir, f"FORCE_{key}_PREVIEW.png")
            _write_file(src_path, live_p)
            if os.path.abspath(src_path) != os.path.abspath(live_p):
                try:
                    os.remove(src_path)
                except OSError:
                    pass
            prune_live_captures(live_dir)
        prune_table_to_slots(key)
        print("[ShotStore] PREVIEW slot OK")
        return published

    wtag = win if win in ("B", "P", "T") else "X"
    otag = out if out in ("WIN", "LOSS", "TIE") else "WIN"
    _rm_glob(os.path.join(d, f"sexy_{key}_CURRENT*.png"))
    dest = os.path.join(d, f"sexy_{key}_CURRENT_W{wtag}_{otag}.png")
    published = _write_file(src_path, dest)

    if in_live:
        _write_file(src_path, os.path.join(live_dir, f"{key}_CURRENT_SETTLE.png"))

    # Đè đúng slot outcome
    if out == "WIN" and win in ("B", "P"):
        _rm_glob(os.path.join(d, f"sexy_{key}_LAST_WIN*.png"))
        _write_file(src_path, os.path.join(d, f"sexy_{key}_LAST_WIN_W{win}_WIN.png"))
        print(f"[ShotStore] LAST_WIN đè ← {win}")
        if in_live:
            _write_file(src_path, os.path.join(live_dir, f"{key}_LAST_WIN_SETTLE.png"))
    elif out == "LOSS" and win in ("B", "P"):
        _rm_glob(os.path.join(d, f"sexy_{key}_LAST_LOSS*.png"))
        _write_file(src_path, os.path.join(d, f"sexy_{key}_LAST_LOSS_W{win}_LOSS.png"))
        print(f"[ShotStore] LAST_LOSS đè ← {win}")
        if in_live:
            _write_file(src_path, os.path.join(live_dir, f"{key}_LAST_LOSS_SETTLE.png"))
    elif out == "TIE":
        _rm_glob(os.path.join(d, f"sexy_{key}_LAST_TIE*.png"))
        _write_file(src_path, os.path.join(d, f"sexy_{key}_LAST_TIE_WT_TIE.png"))
        print("[ShotStore] LAST_TIE đè")
        if in_live:
            _write_file(src_path, os.path.join(live_dir, f"{key}_LAST_TIE_SETTLE.png"))
    else:
        print(f"[ShotStore] CURRENT {otag} winner={win} (không đè LAST_*)")

    if in_live:
        try:
            abs_src = os.path.abspath(src_path)
            base = os.path.basename(abs_src).upper()
            if (
                abs_src.endswith("_SETTLE.png")
                and "CURRENT" not in base
                and "LAST_WIN" not in base
                and "LAST_LOSS" not in base
                and "LAST_TIE" not in base
            ):
                os.remove(src_path)
        except OSError:
            pass
        prune_live_captures(live_dir)

    prune_table_to_slots(key)
    return published
