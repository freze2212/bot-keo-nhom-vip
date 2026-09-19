"""Mở / kill Chrome profile riêng — không Playwright, không cần người mở tay."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


def find_chrome_exe(explicit: str | None = None) -> str:
    if explicit and os.path.isfile(explicit):
        return explicit
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return "chrome.exe"


def _profile_marker(profile_dir: str) -> str:
    return os.path.normcase(os.path.abspath(profile_dir)).lower()


def is_profile_chrome_running(profile_dir: str) -> bool:
    """True nếu đã có Chrome/Edge đang giữ đúng user-data-dir vision."""
    marker = _profile_marker(profile_dir)
    try:
        import psutil
    except Exception:
        return False

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if "chrome" not in name and "msedge" not in name:
                continue
            cmd = os.path.normcase(" ".join(proc.info.get("cmdline") or [])).lower()
            if marker in cmd:
                return True
        except Exception:
            continue
    return False


def kill_profile_chrome(profile_dir: str) -> int:
    """Kill chỉ Chrome đang giữ ĐÚNG user-data-dir vision (không đụng Chrome thường)."""
    killed = 0
    marker = _profile_marker(profile_dir)
    try:
        import psutil
    except Exception:
        print("[CHROME] Thiếu psutil — không kill mù chrome.exe toàn máy")
        return 0

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if "chrome" not in name and "msedge" not in name:
                continue
            cmd = os.path.normcase(" ".join(proc.info.get("cmdline") or [])).lower()
            if marker in cmd:
                proc.kill()
                killed += 1
        except Exception:
            pass

    lock = Path(profile_dir) / "lockfile"
    if lock.exists():
        try:
            lock.unlink()
        except Exception:
            pass
    return killed


def process_uses_profile(pid: int, profile_dir: str) -> bool:
    marker = _profile_marker(profile_dir)
    try:
        import psutil

        cmd = os.path.normcase(" ".join(psutil.Process(pid).cmdline() or [])).lower()
        return marker in cmd
    except Exception:
        return False


def launch_chrome(
    url: str,
    profile_dir: str,
    chrome_exe: str | None = None,
    extra_args: list | None = None,
    window_w: int = 1920,
    window_h: int = 1080,
) -> subprocess.Popen:
    """
    Chrome thật + profile cố định (cookie login giữ qua crash).
    Không --remote-debugging-port → không CDP / không lag kiểu Playwright.
    """
    Path(profile_dir).mkdir(parents=True, exist_ok=True)
    exe = find_chrome_exe(chrome_exe)
    args = [
        exe,
        f"--user-data-dir={os.path.abspath(profile_dir)}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--hide-crash-restore-bubble",
        f"--window-size={int(window_w)},{int(window_h)}",
        "--window-position=0,0",
        "--enable-gpu",
        "--ignore-gpu-blocklist",
    ]
    # Chỉ mở URL khi cold-start — tránh tab mới làm site đá session
    if url:
        args.append(url)
    if extra_args:
        args[1:1] = list(extra_args)
    print(f"[CHROME] Launch: {exe}")
    print(f"[CHROME] Profile: {profile_dir}")
    print(f"[CHROME] URL: {url or '(reuse / no new tab)'}")
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ensure_chrome_up(
    url: str,
    profile_dir: str,
    chrome_exe: str | None = None,
    force_restart: bool = False,
    wait_sec: float = 8.0,
    window_w: int = 1920,
    window_h: int = 1080,
    reuse_if_running: bool = True,
    open_new_tab: bool = False,
) -> str:
    """
    Returns: 'reused' | 'launched' | 'restarted' | 'navigated'
    - Mặc định: Chrome đang chạy → REUSE, không mở tab mới (tránh about:blank)
    - open_new_tab=True vẫn navigate trên cửa sổ hiện có nếu đã chạy
    """
    if force_restart:
        n = kill_profile_chrome(profile_dir)
        print(f"[CHROME] Kill profile processes: {n}")
        time.sleep(1.2)
        launch_chrome(
            url, profile_dir, chrome_exe=chrome_exe, window_w=window_w, window_h=window_h
        )
        time.sleep(wait_sec)
        return "restarted"

    running = is_profile_chrome_running(profile_dir)

    if running and (reuse_if_running or open_new_tab):
        print("[CHROME] Reuse Chrome đang chạy — KHÔNG mở tab mới (tránh about:blank)")
        time.sleep(0.4)
        return "reused"

    launch_chrome(
        url, profile_dir, chrome_exe=chrome_exe, window_w=window_w, window_h=window_h
    )
    time.sleep(wait_sec)
    return "launched"


def navigate_chrome_to_url(url: str, wait_sec: float = 4.0) -> None:
    """Focus omnibox tab hiện tại → vào URL (không spawn about:blank)."""
    from input_click import focus_omnibox_and_goto

    print(f"[CHROME] Goto URL trên tab hiện tại: {url}")
    focus_omnibox_and_goto(url)
    time.sleep(wait_sec)
