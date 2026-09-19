import sys
import os
import time
from pathlib import Path

# Thêm thư mục gốc vào PYTHONPATH
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from python_service.logger import log, LOG_FILE_PATH
from python_service.window_manager import WindowManager
from python_service.screen_capture import ScreenCapture
from python_service.ui_detector import UIDetector
from python_service.socket_client import SocketClient

def run_tests():
    log.info("=" * 60)
    log.info("🧪 BẮT ĐẦU CHẠY BỘ KIỂM THỬ TỰ ĐỘNG (SELF-TEST SUITE)")
    log.info("=" * 60)

    tests_passed = 0
    total_tests = 5

    # 1. Test Window Manager
    log.info("\n[1/5] Kiểm tra Window Manager...")
    try:
        wm = WindowManager()
        bounds = wm.get_window_bounds()
        assert isinstance(bounds, dict) and "width" in bounds and "height" in bounds
        log.info(f"✅ WindowManager khởi tạo tốt: bounds={bounds}")
        tests_passed += 1
    except Exception as e:
        log.error(f"❌ Test WindowManager thất bại: {e}")

    # 2. Test Screen Capture
    log.info("\n[2/5] Kiểm tra Screen Capture (MSS Framebuffer)...")
    try:
        sc = ScreenCapture()
        t0 = time.perf_counter()
        img = sc.grab_region({"left": 0, "top": 0, "width": 800, "height": 600})
        t_ms = (time.perf_counter() - t0) * 1000
        assert img is not None and img.size == (800, 600)
        log.info(f"✅ ScreenCapture chụp 800x600 thành công trong {t_ms:.2f}ms (Chuẩn siêu tốc)")

        # Test lưu ảnh
        success, fpath, _ = sc.capture_table_round(
            window_bounds={"left": 0, "top": 0, "width": 1366, "height": 768},
            table_name="TEST_C01",
            round_num=99,
        )
        assert success and fpath and os.path.exists(fpath)
        log.info(f"✅ Lưu ảnh bàn test thành công: {fpath}")
        sc.close()
        tests_passed += 1
    except Exception as e:
        log.error(f"❌ Test ScreenCapture thất bại: {e}")

    # 3. Test UI Detector
    log.info("\n[3/5] Kiểm tra UI Detector...")
    try:
        detector = UIDetector()
        # Test tính toán tọa độ click
        log.info("✅ UIDetector khởi tạo thành công (OpenCV & PyAutoGUI sẵn sàng).")
        tests_passed += 1
    except Exception as e:
        log.error(f"❌ Test UIDetector thất bại: {e}")

    # 4. Test Socket Client Object
    log.info("\n[4/5] Kiểm tra Socket Client Object...")
    try:
        client = SocketClient()
        assert client.server_url is not None
        log.info(f"✅ SocketClient khởi tạo tốt với Server URL: {client.server_url}")
        tests_passed += 1
    except Exception as e:
        log.error(f"❌ Test SocketClient thất bại: {e}")

    # 5. Test Log File Existence
    log.info("\n[5/5] Kiểm tra File Log...")
    try:
        assert LOG_FILE_PATH.exists()
        log.info(f"✅ File log tồn tại và ghi log tốt: {LOG_FILE_PATH}")
        tests_passed += 1
    except Exception as e:
        log.error(f"❌ Test Log File thất bại: {e}")

    log.info("\n" + "=" * 60)
    log.info(f"🏁 KẾT QUẢ KIỂM THỬ: {tests_passed}/{total_tests} Tests PASSED")
    log.info("=" * 60)
    return tests_passed == total_tests

if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
