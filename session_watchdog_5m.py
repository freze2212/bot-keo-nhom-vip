import sys
import os
import time
import subprocess
import json
import urllib.request
import urllib.parse

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

NSSM = r'C:\tools\nssm\nssm-2.24\win64\nssm.exe'
API_BASE_URL = 'http://127.0.0.1:3201'
LOG_FILE = r'C:\apps\bot-keo-nhom-bcr-main\logs\auto_restart.log'
NS_LIST = ['NS1', 'NS2', 'NS3', 'NS4']
STUCK_THRESHOLD_S = 300   # 5 phút chưa ổn -> restart
GRACE_AFTER_RESTART_S = 90  # cho session boot/enter sau restart

_ns_state = {}


def log(msg):
    now_str = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{now_str}][WATCHDOG] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def normalize_nssm_status(raw):
    if not raw:
        return ''
    return raw.replace('\x00', '').replace(' ', '').strip().upper()


def run_nssm(cmd, timeout=30):
    return subprocess.run(cmd, capture_output=True, text=True, shell=True, timeout=timeout)


def service_status(name):
    res = run_nssm(f'"{NSSM}" status {name}', timeout=10)
    return normalize_nssm_status(res.stdout)


def restart_session(ns):
    session_num = ns.replace('NS', '').strip()
    s_name = f"BCR-session{session_num}"
    b_name = f"BCR-bot{session_num}"
    log(f"🚨 RESTART {s_name} + {b_name} ({ns})...")
    try:
        res = run_nssm(f'"{NSSM}" restart {s_name}', timeout=45)
        log(f"  -> {s_name}: {normalize_nssm_status(res.stdout) or 'OK'}")
        time.sleep(3)
        st = service_status(b_name)
        if 'RUNNING' not in st:
            run_nssm(f'"{NSSM}" start {b_name}', timeout=20)
            log(f"  -> start {b_name} (was {st or 'UNKNOWN'})")
        _ns_state[ns] = {'last_restart': time.time()}
    except Exception as e:
        log(f"  -> Loi restart {ns}: {e}")


def _issue_age(ns, issue_key):
    state = _ns_state.setdefault(ns, {})
    since_key = f'since_{issue_key}'
    if since_key not in state:
        state[since_key] = time.time()
    return time.time() - state[since_key]


def _clear_issues(ns):
    state = _ns_state.get(ns)
    if not state:
        return
    keep = {k: v for k, v in state.items() if k == 'last_restart'}
    if keep:
        _ns_state[ns] = keep
    else:
        _ns_state.pop(ns, None)


def _in_grace(ns):
    state = _ns_state.get(ns) or {}
    last_restart = state.get('last_restart', 0)
    return (time.time() - last_restart) < GRACE_AFTER_RESTART_S if last_restart else False


def check_and_heal():
    for ns in NS_LIST:
        try:
            if _in_grace(ns):
                continue

            url = f"{API_BASE_URL}/api/get-active-table?nameService={ns}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as r:
                data = json.loads(r.read().decode('utf-8'))

            table = data.get('activeTable')
            paused = data.get('paused', False)

            if paused:
                age = _issue_age(ns, 'paused')
                log(f"⏳ {ns}: Dang restart/pause ({age:.0f}s/{STUCK_THRESHOLD_S}s)")
                if age > STUCK_THRESHOLD_S:
                    restart_session(ns)
                continue

            if not table or table in ('NONE', 'LOBBY'):
                age = _issue_age(ns, 'no_table')
                log(f"⚠️ {ns}: Chua vao ban (table={table}) — {age:.0f}s/{STUCK_THRESHOLD_S}s")
                if age > STUCK_THRESHOLD_S:
                    restart_session(ns)
                continue

            shot_url = f"{API_BASE_URL}/api/latest-screenshot?tableName={urllib.parse.quote(str(table))}"
            with urllib.request.urlopen(urllib.request.Request(shot_url), timeout=4) as sr:
                sdata = json.loads(sr.read().decode('utf-8'))

            if sdata.get('success') and sdata.get('data'):
                stamp = sdata['data'].get('stampTime', 0)
                age_s = time.time() - (stamp / 1000)
                if age_s > STUCK_THRESHOLD_S:
                    stuck = _issue_age(ns, 'stale_shot')
                    log(f"❌ {ns} (Ban {table}): Anh cu {age_s:.0f}s — stuck {stuck:.0f}s/{STUCK_THRESHOLD_S}s")
                    if stuck > 60:  # xác nhận thêm 1 phút rồi restart
                        restart_session(ns)
                    continue

            _clear_issues(ns)
        except Exception as e:
            age = _issue_age(ns, 'api_error')
            log(f"⚠️ Loi kiem tra {ns}: {e} ({age:.0f}s)")
            if age > STUCK_THRESHOLD_S:
                restart_session(ns)


def check_bot_services():
    services = ['BCR-server', 'BCR-bot1', 'BCR-bot2', 'BCR-bot3', 'BCR-bot4', 'BCR-forward-bot']
    for s in services:
        try:
            status = service_status(s)
            if not status:
                continue
            if 'STOPPED' in status or 'PAUSED' in status:
                log(f"🚨 {s} DANG DUNG ({status}) -> START LAI!")
                run_nssm(f'"{NSSM}" start {s}', timeout=20)
            elif 'RUNNING' not in status and 'START' not in status:
                log(f"⚠️ {s} status la: {status}")
        except Exception as e:
            log(f"⚠️ Loi check {s}: {e}")


def main_loop():
    log("Khoi dong Watchdog 24/7 — restart session neu ket >5 phut...")
    while True:
        try:
            check_and_heal()
            check_bot_services()
        except Exception as e:
            log(f"Loi vong lap: {e}")
        time.sleep(45)


if __name__ == '__main__':
    main_loop()
