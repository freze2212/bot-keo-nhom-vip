"""
Calibrate Vision — hướng dẫn dùng:
1) Bấm "Khóa cửa sổ" → Chrome cố định 1920x1080.
2) ARM hàng cần ghi → rê chuột trên game → F8.
3) F9 thử click. Lưu cấu hình.
"""
from __future__ import annotations

import os
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import pyautogui

from config_manager import load_config, save_config
from window_controller import WindowController

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "vision_config.json")


class CalibrateApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CALIBRATE VISION — Rel + F8")
        self.root.geometry("620x920")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        self.running_tracker = True
        self.config = load_config()
        self.win_left = int(self.config.get("window_rect", {}).get("x", 0))
        self.win_top = int(self.config.get("window_rect", {}).get("y", 0))
        self.armed = None  # ("xy", ex, ey, label) | ("roi", ents, label)
        self.last_rel = (0, 0)

        self.create_widgets()
        self.root.bind_all("<F8>", self.on_hotkey_f8)
        self.root.bind_all("<F9>", self.on_hotkey_f9_test)
        threading.Thread(target=self.track_mouse_loop, daemon=True).start()

    def create_widgets(self):
        tip = (
            "Cố định Chrome 1920x1080.\n"
            "Chuỗi vào Sexy (ARM+F8 từng hàng): open_login → user → pass → submit\n"
            "→ Sexy → Chơi ngay → Chọn bàn. TK/MK lấy từ .env, không cần cookie.",
        )
        ttk.Label(self.root, text=tip, justify="left", foreground="#063").pack(
            fill="x", padx=10, pady=6
        )

        ttk.Button(
            self.root, text="1) Khóa Chrome 1920x1080", command=self.lock_window
        ).pack(fill="x", padx=10)

        frame_mouse = ttk.LabelFrame(
            self.root, text=" Chuột realtime (chỉ xem — dùng F8 để ghi) ", padding=8
        )
        frame_mouse.pack(fill="x", padx=10, pady=4)
        self.lbl_coord = ttk.Label(
            frame_mouse, text="Abs 0,0 | Rel 0,0", font=("Consolas", 12, "bold")
        )
        self.lbl_coord.pack()
        self.lbl_color = ttk.Label(frame_mouse, text="RGB", font=("Consolas", 9))
        self.lbl_color.pack()
        self.lbl_arm = ttk.Label(
            frame_mouse,
            text="ARM: chưa chọn — bấm ARM ở hàng bên dưới",
            font=("Segoe UI", 10, "bold"),
            foreground="#a40",
        )
        self.lbl_arm.pack(pady=4)

        self.nav_entries = []
        frame_nav = ttk.LabelFrame(self.root, text=" Navigate vào sảnh/bàn (điểm click X,Y) ", padding=6)
        frame_nav.pack(fill="x", padx=10, pady=3)
        for i, step in enumerate(self.config.get("navigation_steps", [])):
            self.nav_entries.append(
                self._xy_row(
                    frame_nav,
                    step.get("name", f"B{i+1}"),
                    step.get("x", 0),
                    step.get("y", 0),
                )
            )

        self.bet_entries = {}
        frame_bet = ttk.LabelFrame(
            self.root,
            text=" Click chip / ô cược — player = ô CON (1 điểm giữa ô) ",
            padding=6,
        )
        frame_bet.pack(fill="x", padx=10, pady=3)
        bp = self.config.get("bet_points") or {}
        for key in ("chip_50", "player", "banker"):
            pt = bp.get(key, {})
            self.bet_entries[key] = self._xy_row(
                frame_bet, key, pt.get("x", 0), pt.get("y", 0)
            )

        self.login_entries = {}
        frame_login = ttk.LabelFrame(
            self.root, text=" Auto-login (.env USER/PASS) — ARM + F8 ", padding=6
        )
        frame_login.pack(fill="x", padx=10, pady=3)
        lp = self.config.get("login_points") or {}
        for key in ("open_login", "username", "password", "submit"):
            pt = lp.get(key, {})
            self.login_entries[key] = self._xy_row(
                frame_login, key, pt.get("x", 0), pt.get("y", 0)
            )

        self.roi_vars = {}
        frame_roi = ttk.LabelFrame(
            self.root,
            text=" ROI = hình chữ nhật X Y W H (không ghi abs vào W/H) ",
            padding=6,
        )
        frame_roi.pack(fill="x", padx=10, pady=3)
        ttk.Label(
            frame_roi,
            text="ROI: ARM → F8 góc trên-trái | giữ Shift+F8 góc dưới-phải (tính W/H)",
            font=("Segoe UI", 8),
        ).pack(anchor="w")
        for name, key in (
            ("timer", "roi_timer"),
            ("result", "roi_result"),
            ("balance", "roi_balance"),
            ("zone_B", "roi_zone_banker"),
            ("zone_P", "roi_zone_player"),
        ):
            roi = self.config.get(key, {})
            row = ttk.Frame(frame_roi)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=name, width=8).pack(side="left")
            ents = []
            for field, default in (("x", 0), ("y", 0), ("width", 100), ("height", 40)):
                e = ttk.Entry(row, width=5)
                e.insert(0, str(roi.get(field, default)))
                e.pack(side="left", padx=1)
                ents.append(e)

            def arm_roi(n=name, e=ents):
                self.arm_roi(n, e)

            ttk.Button(row, text="ARM", width=5, command=arm_roi).pack(side="left", padx=2)
            self.roi_vars[name] = (key, ents)

        ttk.Label(
            self.root,
            text="Ví dụ ô CON: ARM hàng player → chuột giữa ô Con trên game → F8. "
            "Không điền 844 vào cột W của ROI.",
            wraplength=580,
            foreground="#333",
        ).pack(fill="x", padx=10, pady=4)

        ttk.Button(self.root, text="LƯU CẤU HÌNH", command=self.save_all).pack(
            fill="x", padx=10, pady=8
        )

    def _xy_row(self, parent, label, x, y):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=1)
        ttk.Label(row, text=str(label)[:18], width=18).pack(side="left")
        ex = ttk.Entry(row, width=6)
        ex.insert(0, str(x))
        ex.pack(side="left", padx=1)
        ey = ttk.Entry(row, width=6)
        ey.insert(0, str(y))
        ey.pack(side="left", padx=1)

        def arm():
            self.armed = ("xy", ex, ey, str(label))
            self.lbl_arm.config(
                text=f"ARM: {label} — rê chuột lên GAME rồi nhấn F8",
                foreground="#060",
            )

        ttk.Button(row, text="ARM", width=5, command=arm).pack(side="left", padx=2)
        ttk.Button(
            row, text="Thử", width=5, command=lambda: self.test_rel_click(ex.get(), ey.get())
        ).pack(side="right")
        return ex, ey

    def arm_roi(self, name, ents):
        self.armed = ("roi", ents, name)
        self.lbl_arm.config(
            text=f"ARM ROI {name}: F8 = góc TL | Shift+F8 = góc BR (W/H)",
            foreground="#060",
        )

    def lock_window(self):
        wr = self.config.get("window_rect", {})
        wc = WindowController(
            keyword=self.config.get("window_title_keyword", "Google Chrome|Chrome")
        )
        rect = wc.find_and_setup_window(
            target_x=int(wr.get("x", 0)),
            target_y=int(wr.get("y", 0)),
            target_w=int(wr.get("width", 1920)),
            target_h=int(wr.get("height", 1080)),
            maximize=bool(self.config.get("maximize_window", False)),
        )
        if not rect:
            messagebox.showerror(
                "Lỗi",
                "Không thấy Chrome game.\nMở RR88 bằng runner hoặc Chrome profile vision trước.",
            )
            return
        self.win_left = rect["left"]
        self.win_top = rect["top"]
        messagebox.showinfo(
            "Đã khóa",
            f"Chrome {rect['width']}x{rect['height']} @ ({self.win_left},{self.win_top})\n"
            "Cố định 1920x1080 — calibrate và chạy bot giữ đúng size này.",
        )

    def track_mouse_loop(self):
        while self.running_tracker:
            try:
                x, y = pyautogui.position()
                rx, ry = x - self.win_left, y - self.win_top
                self.last_rel = (rx, ry)
                self.lbl_coord.config(text=f"Abs {x},{y}  |  Rel {rx},{ry}")
                pix = pyautogui.pixel(x, y)
                self.lbl_color.config(text=f"RGB ({pix[0]}, {pix[1]}, {pix[2]})")
            except Exception:
                pass
            time.sleep(0.05)

    def on_hotkey_f8(self, _event=None):
        # Shift+F8 cho góc BR của ROI
        shift = bool(self.root.tk.call("set", "::tk::Priv(shifted)") if False else False)
        # Dùng state từ event
        return self._capture(shift_br=False)

    def on_hotkey_f9_test(self, _event=None):
        if not self.armed or self.armed[0] != "xy":
            rx, ry = self.last_rel
            self.test_rel_click(str(rx), str(ry))
            return
        _, ex, ey, _ = self.armed
        self.test_rel_click(ex.get(), ey.get())

    def _capture(self, shift_br: bool = False):
        rx, ry = self.last_rel
        if not self.armed:
            messagebox.showwarning(
                "Chưa ARM",
                "Bấm ARM ở hàng cần ghi (vd: player),\nrồi rê chuột lên ô Con trên game, nhấn F8.",
            )
            return
        kind = self.armed[0]
        if kind == "xy":
            _, ex, ey, label = self.armed
            ex.delete(0, tk.END)
            ex.insert(0, str(rx))
            ey.delete(0, tk.END)
            ey.insert(0, str(ry))
            self.lbl_arm.config(text=f"ĐÃ GHI {label} = Rel ({rx},{ry}) — F9 thử click", foreground="#060")
            return
        if kind == "roi":
            _, ents, name = self.armed
            if not shift_br:
                # góc trên-trái
                ents[0].delete(0, tk.END)
                ents[0].insert(0, str(rx))
                ents[1].delete(0, tk.END)
                ents[1].insert(0, str(ry))
                self.lbl_arm.config(
                    text=f"ROI {name} góc TL=({rx},{ry}) — rê góc dưới-phải rồi Ctrl+F8",
                    foreground="#060",
                )
            else:
                x0 = int(ents[0].get() or 0)
                y0 = int(ents[1].get() or 0)
                w = max(1, rx - x0)
                h = max(1, ry - y0)
                ents[2].delete(0, tk.END)
                ents[2].insert(0, str(w))
                ents[3].delete(0, tk.END)
                ents[3].insert(0, str(h))
                self.lbl_arm.config(
                    text=f"ROI {name} W,H=({w},{h}) từ BR Rel ({rx},{ry})",
                    foreground="#060",
                )

    def on_ctrl_f8(self, _event=None):
        self._capture(shift_br=True)

    def test_rel_click(self, xs, ys):
        try:
            from input_click import click_relative

            click_relative({"left": self.win_left, "top": self.win_top}, int(xs), int(ys))
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))

    def save_all(self):
        try:
            steps = self.config.get("navigation_steps", [])
            for i, (ex, ey) in enumerate(self.nav_entries):
                if i < len(steps):
                    steps[i]["x"] = int(ex.get())
                    steps[i]["y"] = int(ey.get())
            self.config["navigation_steps"] = steps

            bp = self.config.get("bet_points") or {}
            for key, (ex, ey) in self.bet_entries.items():
                bp[key] = dict(bp.get(key) or {})
                bp[key]["x"] = int(ex.get())
                bp[key]["y"] = int(ey.get())
            self.config["bet_points"] = bp

            if getattr(self, "login_entries", None):
                lp = self.config.get("login_points") or {}
                for key, (ex, ey) in self.login_entries.items():
                    lp[key] = dict(lp.get(key) or {})
                    lp[key]["x"] = int(ex.get())
                    lp[key]["y"] = int(ey.get())
                self.config["login_points"] = lp
                self.config["auto_login"] = True

            for _name, (cfg_key, ents) in self.roi_vars.items():
                block = dict(self.config.get(cfg_key) or {})
                block["x"] = int(ents[0].get())
                block["y"] = int(ents[1].get())
                block["width"] = int(ents[2].get())
                block["height"] = int(ents[3].get())
                # cảnh báo nếu W/H quá lớn (nhầm abs vào W/H)
                if block["width"] > 900 or block["height"] > 700:
                    messagebox.showwarning(
                        "ROI lạ",
                        f"{cfg_key} W/H = {block['width']}x{block['height']} — "
                        "có vẻ bạn nhét Abs vào W/H.\n"
                        "ROI chỉ là khung nhỏ quanh vùng cần nhìn.",
                    )
                self.config[cfg_key] = block

            save_config(self.config)
            messagebox.showinfo("OK", f"Đã lưu\n{CONFIG_PATH}")
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))


def main():
    root = tk.Tk()
    app = CalibrateApp(root)
    root.bind_all("<Control-F8>", app.on_ctrl_f8)
    # Windows đôi khi cần KeyPress-F8
    root.bind_all("<KeyPress-F8>", app.on_hotkey_f8)
    root.bind_all("<KeyPress-F9>", app.on_hotkey_f9_test)
    root.mainloop()


if __name__ == "__main__":
    main()
