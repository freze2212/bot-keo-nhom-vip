import time
import requests
import socketio
from typing import Optional, Callable, Dict, Any
from .config import SOCKET_SERVER_URL, NAME_SERVICE, RECONNECT_INTERVAL_SECONDS
from .logger import log

class SocketClient:
    def __init__(
        self,
        on_change_table: Optional[Callable[[str, str], None]] = None,
        on_capture_request: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_reload_request: Optional[Callable[[], None]] = None,
    ):
        self.sio = socketio.Client(reconnection=True, reconnection_delay=2)
        self.server_url = SOCKET_SERVER_URL
        self.name_service = NAME_SERVICE
        self.on_change_table = on_change_table
        self.on_capture_request = on_capture_request
        self.on_reload_request = on_reload_request
        self.is_connected = False

        self._setup_events()

    def _setup_events(self):
        @self.sio.event
        def connect():
            self.is_connected = True
            log.info(f"🔗 Đã kết nối Socket.IO tới Server: {self.server_url} (NS: {self.name_service})")

        @self.sio.event
        def disconnect():
            self.is_connected = False
            log.warning("⚠️ Mất kết nối Socket.IO với Server. Đang tự động kết nối lại...")

        @self.sio.on("request_change_table")
        def handle_change_table(data):
            ns = str(data.get("nameService", "")).upper()
            if not ns or ns == self.name_service:
                target = data.get("tableName") or data.get("targetTable") or "C02"
                reason = data.get("reason", "Tín hiệu đổi bàn")
                log.info(f"📩 Nhận lệnh đổi bàn từ Server: {target} (Lý do: {reason})")
                if self.on_change_table:
                    self.on_change_table(target, reason)

        @self.sio.on("set_target_table")
        def handle_target_table(data):
            target = data.get("tableName")
            log.info(f"🎯 Nhận lệnh set_target_table: {target}")
            if self.on_change_table and target:
                self.on_change_table(target, "Server target")

        @self.sio.on("force_signal_reload")
        def handle_reload(data):
            ns = str(data.get("nameService", "")).upper()
            if not ns or ns == self.name_service:
                log.info("🔄 Nhận lệnh force_signal_reload")
                if self.on_reload_request:
                    self.on_reload_request()

        @self.sio.on("new_round_completed")
        def handle_new_round(data):
            # Nhận thông báo ván cược kết thúc -> Trigger chụp ảnh bảng cầu
            log.info(f"🎲 Round mới hoàn thành: {data.get('tableName')} | Thắng: {data.get('winner')}")
            if self.on_capture_request:
                self.on_capture_request(data)

    def start(self):
        """Khởi động kết nối socket trong thread riêng có tự động thử lại liên tục."""
        import threading
        def connect_worker():
            while not self.is_connected:
                try:
                    log.info(f"Đang kết nối Socket.IO tới {self.server_url}...")
                    self.sio.connect(self.server_url, transports=["websocket", "polling"])
                    break
                except Exception as e:
                    log.debug(f"Chưa kết nối được Socket.IO ({self.server_url}) — thử lại sau 3s: {e}")
                    time.sleep(RECONNECT_INTERVAL_SECONDS)

        t = threading.Thread(target=connect_worker, daemon=True)
        t.start()

    def notify_active_table(self, table_name: str) -> bool:
        """Thông báo bàn cược hiện tại lên Server (REST API)."""
        try:
            url = f"{self.server_url}/api/notify-active-table"
            payload = {
                "tableName": table_name,
                "nameService": self.name_service,
            }
            res = requests.post(url, json=payload, timeout=3)
            if res.status_code == 200:
                log.info(f"📢 Đã thông báo Active Table '{table_name}' lên Server thành công.")
                return True
            else:
                log.warning(f"⚠️ Notify Active Table trả về status {res.status_code}: {res.text}")
                return False
        except Exception as e:
            log.error(f"Lỗi khi notify_active_table: {e}")
            return False

    def stop(self):
        try:
            if self.sio.connected:
                self.sio.disconnect()
        except Exception:
            pass
