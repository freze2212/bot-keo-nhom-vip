"""
SETUP ghi click — rê chuột tới chỗ cần → F8 (không cần rê về tool).

Hoặc: bấm nút xanh «SẴN SÀNG» → click trái một phát trên Chrome = ghi điểm đó.

Chạy: python vision_bot/record_setup_clicks.py
"""
from __future__ import annotations

import os
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

import pyautogui

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from chrome_launcher import ensure_chrome_up  # noqa: E402
from config_manager import load_config, save_config  # noqa: E402
from login_flow import login_home_url  # noqa: E402
from window_controller import WindowController  # noqa: E402

DEFAULT_STEPS: list[dict[str, Any]] = [
    {"id": "pre_dismiss", "label": "Đóng popup TRƯỚC login", "kind": "dismiss_pre"},
    {"id": "open_login", "label": "Nút Đăng nhập (mở form)", "kind": "login", "key": "open_login"},
    {"id": "username", "label": "Ô TÀI KHOẢN", "kind": "login", "key": "username"},
    {"id": "password", "label": "Ô MẬT KHẨU", "kind": "login", "key": "password"},
    {"id": "submit", "label": "Nút Submit / Đăng nhập", "kind": "login", "key": "submit"},
    {"id": "post_dismiss", "label": "Đóng popup SAU login", "kind": "dismiss_post"},
    {"id": "sexy", "label": "Casino / Sexy", "kind": "nav", "name": "5. Click Casino/Sexy", "delay": 3.5},
    {"id": "lobby", "label": "Vào phòng chọn bàn", "kind": "nav", "name": "6. Click vào phòng chọn bàn", "delay": 8.0},
    {"id": "table1", "label": "Chọn BÀN — vị trí 1/3 (random mỗi lần chạy)", "kind": "table_cand", "idx": 0},
    {"id": "table2", "label": "Chọn BÀN — vị trí 2/3", "kind": "table_cand", "idx": 1},
    {"id": "table3", "label": "Chọn BÀN — vị trí 3/3", "kind": "table_cand", "idx": 2},
    {"id": "scroll", "label": "Điểm FOCUS scroll — Bỏ qua OK (bot tự lăn)", "kind": "scroll"},
    {"id": "popup1", "label": "Đóng tin nhắn trên bàn (1)", "kind": "table_popup", "idx": 0},
    {"id": "popup2", "label": "Đóng tin nhắn trên bàn (2) — Bỏ qua nếu không có", "kind": "table_popup", "idx": 1},
    {"id": "player", "label": "Ô CON / PLAYER", "kind": "bet", "key": "player"},
    {"id": "banker", "label": "Ô CÁI / BANKER", "kind": "bet", "key": "banker"},
    {"id": "confirm", "label": "Nút XÁC NHẬN cược", "kind": "bet", "key": "confirm"},
]


class RecordSetupApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("GHI CLICK — F8 hoặc SẴN SÀNG rồi click")
        self.root.geometry("580x680")
        self.root.attributes("-topmost", True)

        self.config = load_config()
        wr = self.config.get("window_rect") or {}
        self.win_left = int(wr.get("x") or 0)
        self.win_top = int(wr.get("y") or 0)
        self.win_w = int(wr.get("width") or 1920)
        self.win_h = int(wr.get("height") or 1080)

        self.steps = [dict(s) for s in DEFAULT_STEPS]
        self.idx = 0
        self.recorded: dict[str, dict] = {}
        self.last_rel = (0, 0)
        self.last_abs = (0, 0)
        self._alive = True
        self._extra_n = 0
        self._armed = False
        self._ignore_until = 0.0
        self._mouse_listener = None
        self._key_listener = None

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        threading.Thread(target=self._track_loop, daemon=True).start()
        self._start_global_listeners()
        self._refresh()

    def _build_ui(self):
        tip = ttk.LabelFrame(self.root, text=" Cách dùng (quan trọng) ", padding=10)
        tip.pack(fill="x", padx=12, pady=8)
        ttk.Label(
            tip,
            text=(
                "1) Rê chuột đúng chỗ trên Chrome — KHÔNG rê về tool\n"
                "2) Bấm phím F8  →  ghi ngay vị trí chuột đang đứng\n"
                "   HOẶC bấm nút vàng «SẴN SÀNG» rồi click 1 phát trên Chrome"
            ),
            font=("Segoe UI", 10),
            justify="left",
        ).pack(anchor="w")

        top = ttk.Frame(self.root, padding=(10, 0))
        top.pack(fill="x")
        ttk.Button(top, text="① Mở web login", command=self.open_url).pack(side="left", padx=3)
        ttk.Button(top, text="② Khóa cửa sổ Chrome", command=self.lock_window).pack(
            side="left", padx=3
        )

        self.lbl_win = ttk.Label(self.root, text="Chưa khóa cửa sổ", foreground="#666")
        self.lbl_win.pack(anchor="w", padx=12)

        self.lbl_mouse = ttk.Label(
            self.root, text="Chuột Rel: 0, 0", font=("Consolas", 16, "bold")
        )
        self.lbl_mouse.pack(pady=6)

        step_fr = ttk.LabelFrame(self.root, text=" Bước cần ghi ", padding=12)
        step_fr.pack(fill="x", padx=12, pady=4)
        self.lbl_progress = ttk.Label(step_fr, text="1 / 15", font=("Segoe UI", 11))
        self.lbl_progress.pack(anchor="w")
        self.lbl_step = ttk.Label(
            step_fr,
            text="",
            font=("Segoe UI", 15, "bold"),
            wraplength=520,
            foreground="#0a5",
        )
        self.lbl_step.pack(anchor="w", pady=6)
        self.lbl_hint = ttk.Label(
            step_fr,
            text="Rê chuột tới chỗ cần → nhấn F8",
            foreground="#c60",
            font=("Segoe UI", 10, "bold"),
        )
        self.lbl_hint.pack(anchor="w")

        self.btn_arm = tk.Button(
            self.root,
            text="SẴN SÀNG — click tiếp theo trên Chrome sẽ được ghi",
            font=("Segoe UI", 13, "bold"),
            bg="#e6a800",
            fg="black",
            activebackground="#cc9400",
            height=2,
            command=self.arm_next_click,
        )
        self.btn_arm.pack(fill="x", padx=12, pady=8)

        ttk.Label(
            self.root,
            text="F8 = ghi vị trí chuột hiện tại (không cần bấm nút trên tool)",
            font=("Segoe UI", 9),
            foreground="#333",
        ).pack(anchor="w", padx=14)

        nav = ttk.Frame(self.root)
        nav.pack(fill="x", padx=12, pady=6)
        ttk.Button(nav, text="← Lùi bước", command=self.prev_step).pack(side="left", padx=2)
        ttk.Button(nav, text="Bỏ qua bước →", command=self.skip_step).pack(side="left", padx=2)
        ttk.Button(nav, text="Thử click lại", command=self.test_click).pack(side="left", padx=2)
        ttk.Button(nav, text="Hủy sẵn sàng", command=self.disarm).pack(side="left", padx=2)

        self.lst = tk.Listbox(self.root, height=9, font=("Consolas", 9))
        self.lst.pack(fill="both", expand=True, padx=12, pady=4)

        bot = ttk.Frame(self.root)
        bot.pack(fill="x", padx=12, pady=10)
        ttk.Button(bot, text="Thêm click tùy ý", command=self.add_custom).pack(side="left")
        ttk.Button(bot, text="Lưu config (hỏi xác nhận)", command=self.finish_confirm).pack(
            side="right"
        )

    def _tool_rect(self):
        """Vùng cửa sổ tool (để bỏ qua click lên chính tool)."""
        try:
            self.root.update_idletasks()
            geo = self.root.geometry()
            wh, _, rest = geo.partition("+")
            w, _, h = wh.partition("x")
            parts = rest.split("+")
            return int(parts[0]), int(parts[1]), int(w), int(h)
        except Exception:
            return 0, 0, 0, 0

    def _in_tool(self, x: int, y: int) -> bool:
        tx, ty, tw, th = self._tool_rect()
        return tw > 0 and tx <= x <= tx + tw and ty <= y <= ty + th

    def _track_loop(self):
        while self._alive:
            try:
                x, y = pyautogui.position()
                self.last_abs = (x, y)
                rx, ry = x - self.win_left, y - self.win_top
                self.last_rel = (rx, ry)
                arm = "  [ĐANG CHỜ CLICK…]" if self._armed else ""
                self.root.after(
                    0,
                    lambda rx=rx, ry=ry, x=x, y=y, arm=arm: self.lbl_mouse.config(
                        text=f"Chuột Rel: {rx}, {ry}   (Abs {x},{y}){arm}"
                    ),
                )
            except Exception:
                pass
            time.sleep(0.05)

    def _start_global_listeners(self):
        try:
            from pynput import keyboard, mouse
        except ImportError:
            messagebox.showwarning(
                "Thiếu pynput",
                "Cần: pip install pynput\nKhông có thì F8 / click-ghi sẽ không hoạt động.",
            )
            return

        def on_press(key):
            try:
                if key == keyboard.Key.f8:
                    self.root.after(0, self.record_here)
            except Exception:
                pass

        def on_click(x, y, button, pressed):
            if not pressed:
                return
            if str(button) not in ("Button.left", "button.left"):
                return
            if time.time() < self._ignore_until:
                return
            if not self._armed:
                return
            if self._in_tool(int(x), int(y)):
                return
            # Ghi vị trí click trên Chrome (không phải nút tool)
            self.root.after(0, lambda: self._record_abs(int(x), int(y)))

        self._key_listener = keyboard.Listener(on_press=on_press)
        self._key_listener.daemon = True
        self._key_listener.start()

        self._mouse_listener = mouse.Listener(on_click=on_click)
        self._mouse_listener.daemon = True
        self._mouse_listener.start()

    def _stop_listeners(self):
        for lis in (self._mouse_listener, self._key_listener):
            if lis is not None:
                try:
                    lis.stop()
                except Exception:
                    pass
        self._mouse_listener = None
        self._key_listener = None

    def arm_next_click(self):
        if self.idx >= len(self.steps):
            messagebox.showinfo("Xong", "Hết bước rồi.")
            return
        self._armed = True
        self._ignore_until = time.time() + 0.25  # bỏ qua click vừa bấm nút
        self.btn_arm.config(bg="#ff4444", text="ĐANG CHỜ… click 1 phát trên Chrome (Esc hủy)")
        self.lbl_hint.config(text="Đã sẵn sàng — click TRÊN CHROME (đừng click tool)", foreground="#c00")

    def disarm(self):
        self._armed = False
        self.btn_arm.config(
            bg="#e6a800",
            text="SẴN SÀNG — click tiếp theo trên Chrome sẽ được ghi",
        )
        self.lbl_hint.config(text="Rê chuột tới chỗ cần → nhấn F8", foreground="#c60")

    def open_url(self):
        self._ignore_until = time.time() + 1.0
        url = login_home_url(self.config)
        profile = self.config.get("chrome_profile_dir") or "chrome_user_data_vision"
        if not os.path.isabs(profile):
            profile = os.path.join(_ROOT, profile)
        ensure_chrome_up(
            url=url,
            profile_dir=profile,
            chrome_exe=(self.config.get("chrome_exe") or None) or None,
            force_restart=False,
            wait_sec=float(self.config.get("chrome_boot_wait_sec") or 8),
            window_w=self.win_w,
            window_h=self.win_h,
        )
        messagebox.showinfo("OK", f"Đã mở:\n{url}\n\nTiếp: bấm «Khóa cửa sổ Chrome».")

    def lock_window(self):
        self._ignore_until = time.time() + 1.0
        wc = WindowController(
            keyword=self.config.get("window_title_keyword", "Google Chrome|Chrome")
        )
        profile = self.config.get("chrome_profile_dir") or "chrome_user_data_vision"
        if not os.path.isabs(profile):
            profile = os.path.join(_ROOT, profile)
        rect = wc.find_and_setup_window(
            target_x=int(self.config.get("window_rect", {}).get("x", 0)),
            target_y=int(self.config.get("window_rect", {}).get("y", 0)),
            target_w=self.win_w,
            target_h=self.win_h,
            maximize=bool(self.config.get("maximize_window", False)),
            profile_dir=profile,
        )
        if not rect:
            messagebox.showerror("Lỗi", "Không thấy Chrome. Bấm Mở web login trước.")
            return
        self.win_left = int(rect.get("left") or rect.get("x") or 0)
        self.win_top = int(rect.get("top") or rect.get("y") or 0)
        self.win_w = int(rect.get("width") or self.win_w)
        self.win_h = int(rect.get("height") or self.win_h)
        self.lbl_win.config(
            text=f"OK — cửa sổ {self.win_w}×{self.win_h} @ ({self.win_left},{self.win_top}) — chưa lưu file"
        )
        messagebox.showinfo(
            "Đã khóa",
            "Giữ nguyên kích thước cửa sổ.\n"
            "Rê chuột trên Chrome → F8 để ghi.\n"
            "Config disk chưa đổi đến khi bạn Lưu.",
        )

    def _refresh(self):
        total = len(self.steps)
        if self.idx >= total:
            self.lbl_progress.config(text=f"Xong {total}/{total}")
            self.lbl_step.config(text="Đã ghi hết — bấm «Lưu config» nếu muốn ghi file.")
            self.disarm()
        else:
            st = self.steps[self.idx]
            self.lbl_progress.config(text=f"Bước {self.idx + 1} / {total}")
            prev = self.recorded.get(st["id"])
            extra = f"\n(đã ghi: {prev['x']}, {prev['y']})" if prev else ""
            self.lbl_step.config(text=st["label"] + extra)
            if not self._armed:
                self.lbl_hint.config(
                    text="Rê chuột tới chỗ cần → nhấn F8  (hoặc nút vàng rồi click)",
                    foreground="#c60",
                )

        self.lst.delete(0, tk.END)
        for i, st in enumerate(self.steps):
            r = self.recorded.get(st["id"])
            mark = f"{r['x']},{r['y']}" if r else "—"
            prefix = "→ " if i == self.idx else ("✓ " if r else "  ")
            self.lst.insert(tk.END, f"{prefix}{i+1}. {st['label'][:36]}  [{mark}]")

    def record_here(self):
        """F8: ghi đúng chỗ chuột đang đứng — không cần rê về tool."""
        x, y = pyautogui.position()
        self._record_abs(int(x), int(y))

    def _record_abs(self, x: int, y: int):
        self._record_rel(x - self.win_left, y - self.win_top)

    def _record_rel(self, rx: int, ry: int):
        if self.idx >= len(self.steps):
            messagebox.showinfo("Xong", "Hết bước. Bấm Lưu nếu muốn ghi file.")
            self.disarm()
            return
        st = self.steps[self.idx]
        self.recorded[st["id"]] = {
            "x": int(rx),
            "y": int(ry),
            "kind": st.get("kind"),
            "key": st.get("key"),
            "name": st.get("name"),
            "delay": st.get("delay"),
            "idx": st.get("idx"),
            "label": st.get("label"),
        }
        self._armed = False
        self._ignore_until = time.time() + 0.4
        self.btn_arm.config(
            bg="#e6a800",
            text="SẴN SÀNG — click tiếp theo trên Chrome sẽ được ghi",
        )
        self.idx += 1
        self._refresh()
        # flash xác nhận ngắn
        self.lbl_hint.config(
            text=f"✓ Đã ghi Rel ({rx}, {ry}) — bước tiếp theo",
            foreground="#080",
        )
        if self.idx >= len(self.steps):
            self.root.after(200, self.finish_confirm)

    def prev_step(self):
        if self.idx > 0:
            self.idx -= 1
            self.disarm()
            self._refresh()

    def skip_step(self):
        if self.idx < len(self.steps):
            self.idx += 1
            self.disarm()
            self._refresh()

    def test_click(self):
        self._ignore_until = time.time() + 0.8
        if self.idx > 0:
            prev = self.steps[self.idx - 1]
            r = self.recorded.get(prev["id"])
            if r:
                pyautogui.click(self.win_left + r["x"], self.win_top + r["y"])
                return
        rx, ry = self.last_rel
        pyautogui.click(self.win_left + rx, self.win_top + ry)

    def add_custom(self):
        self._extra_n += 1
        eid = f"extra_{self._extra_n}"
        self.steps.append(
            {"id": eid, "label": f"Click tùy ý #{self._extra_n}", "kind": "extra"}
        )
        self.idx = len(self.steps) - 1
        self.disarm()
        self._refresh()

    def finish_confirm(self):
        n = len(self.recorded)
        if n == 0:
            messagebox.showwarning("Trống", "Chưa ghi điểm nào — không lưu.")
            return
        ok = messagebox.askyesno(
            "Xác nhận lưu?",
            f"Đã ghi {n}/{len(self.steps)} điểm.\n\n"
            "Yes = GHI ĐÈ vào vision_config.json\n"
            "No = không đụng file (giữ tọa độ 1920×1080 cũ)\n\n"
            "Máy đang chạy OK thì nên chọn No trừ khi bạn cố ý calibrate lại.",
        )
        if ok:
            self.save_all()

    def save_all(self):
        cfg = load_config()
        cfg["window_rect"] = {
            "x": self.win_left,
            "y": self.win_top,
            "width": self.win_w,
            "height": self.win_h,
        }

        pre = self.recorded.get("pre_dismiss")
        post = self.recorded.get("post_dismiss")
        if post or pre:
            use = post or pre
            cfg["dismiss_steps"] = [
                {
                    "name": "close_thong_bao",
                    "x": use["x"],
                    "y": use["y"],
                    "delay_after": 1.0,
                }
            ]

        lp = dict(cfg.get("login_points") or {})
        delays = {"open_login": 1.5, "username": 0.6, "password": 0.5, "submit": 6.0}
        for key in ("open_login", "username", "password", "submit"):
            r = self.recorded.get(key)
            if r:
                lp[key] = {"x": r["x"], "y": r["y"], "delay_after": delays[key]}
        cfg["login_points"] = lp

        nav = []
        for sid, dly in (("sexy", 3.5), ("lobby", 8.0)):
            r = self.recorded.get(sid)
            if not r:
                continue
            meta = next((s for s in self.steps if s["id"] == sid), {})
            nav.append(
                {
                    "name": meta.get("name") or sid,
                    "x": r["x"],
                    "y": r["y"],
                    "delay_after": float(meta.get("delay") or dly),
                }
            )

        table_cands = []
        for sid in ("table1", "table2", "table3"):
            r = self.recorded.get(sid)
            if r:
                table_cands.append({"x": int(r["x"]), "y": int(r["y"])})
        if table_cands:
            cfg["table_click_candidates"] = table_cands
            cfg["random_table_click"] = True
            first = table_cands[0]
            nav.append(
                {
                    "name": "7. Click chọn bàn (ngẫu nhiên)",
                    "x": first["x"],
                    "y": first["y"],
                    "delay_after": 5.0,
                    "candidates": list(table_cands),
                }
            )
        if nav:
            cfg["navigation_steps"] = nav

        sc = self.recorded.get("scroll")
        if sc:
            cfg["scroll_focus"] = {"x": sc["x"], "y": sc["y"]}
            cfg["scroll_after_table"] = True

        pops = []
        for sid in ("popup1", "popup2"):
            r = self.recorded.get(sid)
            if r:
                pops.append(
                    {
                        "name": f"close_tin_nhan_{len(pops)+1}",
                        "x": r["x"],
                        "y": r["y"],
                        "delay_after": 0.6,
                    }
                )
        if pops:
            cfg["table_popup_dismiss_steps"] = pops

        bp = dict(cfg.get("bet_points") or {})
        for key, desc in (
            ("player", "Đặt CON"),
            ("banker", "Đặt CÁI"),
            ("confirm", "Xác nhận cược"),
        ):
            r = self.recorded.get(key)
            if r:
                bp[key] = {"x": r["x"], "y": r["y"], "description": desc}
        cfg["bet_points"] = bp

        extras = [
            {"id": k, "x": v["x"], "y": v["y"], "label": v.get("label")}
            for k, v in self.recorded.items()
            if str(k).startswith("extra_")
        ]
        if extras:
            cfg["setup_extra_clicks"] = extras
        cfg["setup_recorded_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_config(cfg)
        messagebox.showinfo("Đã lưu", f"Đã ghi {len(self.recorded)} điểm → vision_config.json")

    def on_close(self):
        self._alive = False
        self._stop_listeners()
        self.root.destroy()


def main():
    root = tk.Tk()
    RecordSetupApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
