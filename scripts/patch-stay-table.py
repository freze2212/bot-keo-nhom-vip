#!/usr/bin/env python3
from pathlib import Path

p = Path("/var/www/bot-keo-nhom-bcr/bot-keo-nhom-bcr-main/bot.py")
lines = p.read_text(encoding="utf-8").splitlines(True)

# Find the wait-loop change-table block by unique English/code markers
start = None
end = None
for i, ln in enumerate(lines):
    if start is None and "if not profile.get('ready'):" in ln:
        # look ahead for pick_beautiful within next 25 lines
        window = "".join(lines[i : i + 25])
        if "pick_beautiful_table_api" in window:
            start = i
    if start is not None and end is None:
        if ln.strip() == "break" and i > start and "asyncio.sleep(2)" in lines[i - 1]:
            end = i
            break

if start is None or end is None:
    raise SystemExit(f"range not found start={start} end={end}")

new = [
    "                if not profile.get('ready'):\n",
    "                    # Stay on table — disable road-based table hop (1-group VPS)\n",
    "                    if time.time() - last_road_log_at >= 8:\n",
    "                        last_road_log_at = time.time()\n",
    "                        print(\n",
    "                            f\"[ROAD] {target_table} not ready \"\n",
    "                            f\"type={profile.get('road_type')} \"\n",
    "                            f\"({profile.get('hand_count')}/{ROAD_ANALYSIS_MIN_BP}) \"\n",
    "                            f\"conf={profile.get('confidence')} — KEEP TABLE\",\n",
    "                            flush=True,\n",
    "                        )\n",
    "                    await asyncio.sleep(1.2)\n",
    "                    continue\n",
]

out = lines[:start] + new + lines[end + 1 :]
p.write_text("".join(out), encoding="utf-8")
print(f"replaced lines {start+1}-{end+1}")

import py_compile
py_compile.compile(str(p), doraise=True)
print("syntax ok")
for i, ln in enumerate(out, 1):
    if "request_change_table_api" in ln and not ln.strip().startswith("def "):
        print("call still at", i, ln.strip()[:80])
