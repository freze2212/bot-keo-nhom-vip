import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env từ thư mục gốc của bot
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Cấu hình Server & Socket
SERVER_PORT = int(os.getenv("SERVER_PORT", 3201))
SOCKET_SERVER_URL = os.getenv("SOCKET_SERVER_URL", f"http://127.0.0.1:{SERVER_PORT}")
NAME_SERVICE = os.getenv("NAME_SERVICE", "NS1").strip().upper()

# Game URL
GAME_DOMAIN = os.getenv("DOMAIN", "https://www.rr9900.com").rstrip("/")
ROUTER_URL_BACARAT_SEXY = os.getenv("ROUTER_URL_BACARAT_SEXY", "/seamless?gameType=LIVE")
GAME_URL = f"{GAME_DOMAIN}{ROUTER_URL_BACARAT_SEXY}"

# Cấu hình Đường dẫn & Thư mục
IMAGES_DIR = BASE_DIR / "images"
LOGS_DIR = BASE_DIR / "logs"
TEMPLATES_DIR = BASE_DIR / "python_service" / "templates"
CHROME_PROFILE_DIR = BASE_DIR / "chrome_user_data"

IMAGES_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

# File Log riêng cho Python Controller
LOG_FILE_PATH = LOGS_DIR / "python_session.log"

# Cấu hình Kích thước Cửa sổ Chrome Chuẩn (Window Layout)
# Định vị cửa sổ cố định để tọa độ click & vùng chụp ảnh luôn chuẩn xác 100%
TARGET_WINDOW_TITLE_KEYWORDS = ["RR88", "Sexy", "Baccarat", "Live Casino", "Casino", "seamless", "rr9900", "rr199", "rr8391", "SEXY BACCARAT", "TRANG CHỦ CHÍNH THỨC RR88"]
DEFAULT_WINDOW_X = 0
DEFAULT_WINDOW_Y = 0
DEFAULT_WINDOW_WIDTH = 1366
DEFAULT_WINDOW_HEIGHT = 768

# Tọa độ vùng bảng cầu cược Sexy Baccarat (Tỉ lệ theo cửa sổ 1366x768 hoặc tự căn theo bounding box)
CAPTURE_CROP_BOX = {
    "left_ratio": 0.05,
    "top_ratio": 0.45,
    "width_ratio": 0.90,
    "height_ratio": 0.50,
}

# Thời gian chờ (Timeout)
OPENCV_CONFIDENCE_THRESHOLD = 0.75
CLICK_DELAY_SECONDS = 0.5
RECONNECT_INTERVAL_SECONDS = 3.0
