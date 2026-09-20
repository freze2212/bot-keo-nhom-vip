"""Cầu nối vision_bot ↔ server.js (hô / place_bet / screenshot)."""
from __future__ import annotations

import os
import threading
import time
from typing import Callable, Optional

import requests

try:
    import socketio
except Exception:  # pragma: no cover
    socketio = None


class VisionBridge:
    def __init__(
        self,
        server_url: str,
        name_service: str = "NS2",
        on_place_bet: Optional[Callable[[dict], None]] = None,
        on_force_capture: Optional[Callable[[dict], None]] = None,
    ):
        self.server_url = (server_url or "http://127.0.0.1:3000").rstrip("/")
        self.name_service = str(name_service or "NS2").upper()
        self.on_place_bet = on_place_bet
        self.on_force_capture = on_force_capture
        self._sio = None
        self._thread = None

    def start_socket(self) -> bool:
        if socketio is None:
            print("[Bridge] Thiếu python-socketio — chỉ dùng HTTP notify.")
            return False
        self._sio = socketio.Client(reconnection=True, reconnection_attempts=0)

        @self._sio.event
        def connect():
            print(f"[Bridge] Socket connected → {self.server_url} ({self.name_service})")

        @self._sio.event
        def disconnect():
            print("[Bridge] Socket disconnected")

        @self._sio.on("place_bet")
        def _place_bet(data):
            data = data or {}
            ns = str(data.get("nameService") or "").upper()
            if ns and ns != self.name_service:
                return
            print(f"[Bridge] place_bet ← {data}")
            if self.on_place_bet:
                self.on_place_bet(data)

        @self._sio.on("force_capture_now")
        def _force_cap(data):
            data = data or {}
            print(f"[Bridge] force_capture_now ← {data}")
            if self.on_force_capture:
                self.on_force_capture(data)

        def _run():
            try:
                self._sio.connect(self.server_url, wait_timeout=10)
                self._sio.wait()
            except Exception as e:
                print(f"[Bridge] Socket lỗi: {e}")

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        return True

    def notify_screenshot(
        self,
        table_name: str,
        filepath: str,
        result_winner: str,
        round_num=None,
    ) -> bool:
        filename = os.path.basename(filepath)
        winner = str(result_winner or "").strip().upper()
        if winner in ("BANKER", "B", "CAI", "CÁI"):
            winner = "B"
        elif winner in ("PLAYER", "P", "CON"):
            winner = "P"
        elif winner in ("TIE", "T", "HOA", "HÒA"):
            winner = "T"
        else:
            print(f"[Bridge] Bỏ notify — winner không hợp lệ: {result_winner}")
            return False

        payload = {
            "tableName": table_name,
            "filename": filename,
            "filepath": filepath,
            "roundNum": round_num,
            "resultWinner": winner,
            "nameService": self.name_service,
        }
        try:
            r = requests.post(
                f"{self.server_url}/api/notify-screenshot",
                json=payload,
                timeout=8,
            )
            ok = r.status_code < 300
            print(f"[Bridge] notify-screenshot {winner} → {r.status_code}")
            return ok
        except Exception as e:
            print(f"[Bridge] notify-screenshot lỗi: {e}")
            return False

    def notify_active_table(self, table_name: str) -> None:
        try:
            requests.post(
                f"{self.server_url}/api/notify-active-table",
                json={"tableName": table_name, "nameService": self.name_service},
                timeout=5,
            )
        except Exception:
            pass

    def notify_vision_bet(
        self,
        table_name: str,
        bet_side: str,
        round_num=None,
    ) -> bool:
        """Công bố cửa vision vừa đặt — forward hô cùng nguồn này."""
        side = str(bet_side or "").strip().upper()
        if side.startswith("B") or side in ("CAI", "CÁI"):
            side = "B"
        elif side.startswith("P") or side == "CON":
            side = "P"
        else:
            print(f"[Bridge] Bỏ notify-vision-bet — side không hợp lệ: {bet_side}")
            return False
        payload = {
            "tableName": table_name,
            "betSide": side,
            "side": side,
            "nameService": self.name_service,
            "roundCount": round_num,
            "hoAt": int(time.time() * 1000),
            "source": "vision",
        }
        try:
            r = requests.post(
                f"{self.server_url}/api/notify-main-ho",
                json=payload,
                timeout=5,
            )
            ok = r.status_code < 300
            print(f"[Bridge] notify-vision-bet {side} → {r.status_code}")
            return ok
        except Exception as e:
            print(f"[Bridge] notify-vision-bet lỗi: {e}")
            return False
