import logging
import sys
from pathlib import Path
from .config import LOG_FILE_PATH

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def setup_logger(name: str = "PYTHON_CONTROLLER") -> logging.Logger:
    """Khởi tạo hệ thống logging đồng thời ra Console và File log để theo dõi/tự fix lỗi."""
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console Handler with UTF-8 support
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File Handler (Lưu chi tiết DEBUG)
    try:
        fh = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8", mode="a")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception as e:
        print(f"Warning: Không thể mở file log: {e}", file=sys.stderr)

    return logger

log = setup_logger()
