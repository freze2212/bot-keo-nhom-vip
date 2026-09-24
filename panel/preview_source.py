"""
Preview tin nguồn cho Panel — in JSON ra stdout.
Usage: py -3.12 panel/preview_source.py --customer customers/xxx.json
   or:  py -3.12 panel/preview_source.py --session user_session_... --api-id N --api-hash H --source frezeit --limit 15
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.chdir(ROOT)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer", help="Path customers/*.json")
    ap.add_argument("--session")
    ap.add_argument("--api-id", type=int)
    ap.add_argument("--api-hash")
    ap.add_argument("--source", default="frezeit")
    ap.add_argument("--limit", type=int, default=15)
    args = ap.parse_args()

    session = args.session
    api_id = args.api_id
    api_hash = args.api_hash
    source = args.source

    if args.customer:
        with open(args.customer, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        phone = str(cfg.get("phone") or "")
        digits = "".join(c for c in phone if c.isdigit())
        session = cfg.get("session_name") or (
            f"user_session_{digits}" if digits else None
        )
        api_id = int(cfg.get("api_id") or 0)
        api_hash = str(cfg.get("api_hash") or "")
        source = str(cfg.get("source_username") or "frezeit")

    if not session or not api_id or not api_hash:
        print(json.dumps({"ok": False, "error": "Thiếu session/api_id/api_hash"}))
        return 1

    from telethon import TelegramClient

    client = TelegramClient(session, api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        print(json.dumps({"ok": False, "error": "Chưa login session — chạy OTP trước"}))
        await client.disconnect()
        return 2

    entity = await client.get_entity(source)
    rows = []
    msgs = []
    async for m in client.iter_messages(entity, limit=max(args.limit, 5)):
        msgs.append(m)
    msgs.sort(key=lambda x: x.id)
    for i, m in enumerate(msgs):
        text = (m.message or getattr(m, "text", None) or "")[:200]
        has_media = bool(m.media)
        rows.append(
            {
                "index": i,
                "msg_id": m.id,
                "text": text,
                "has_media": has_media,
                "date": m.date.isoformat() if m.date else None,
            }
        )
    await client.disconnect()
    print(json.dumps({"ok": True, "source": source, "messages": rows}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        raise SystemExit(1)
