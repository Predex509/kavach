"""
Check which Prisma streaming settings Gnani accepts.

    .venv/bin/python stt_check.py                 # default language list hi-IN,en-IN
    .venv/bin/python stt_check.py te-IN,en-IN

For each settings level in server.FALLBACK_LEVELS it connects, sends 2 seconds of silence
(costs almost nothing) and prints what the server answered. Never prints the API key.
"""

from __future__ import annotations

import asyncio
import json
import sys

import websockets

from server import API_KEY, FALLBACK_LEVELS, STT_URL, build_stt_headers


async def try_level(language: str, level: int) -> None:
    headers = build_stt_headers(language, level)
    shown = {k: (v if len(v) < 50 else v[:47] + "...") for k, v in headers.items() if k != "x-api-key-id"}
    print(f"\n=== level {level}: {FALLBACK_LEVELS[level]}")
    print(f"    headers: {shown}")
    try:
        async with websockets.connect(STT_URL, additional_headers=headers, max_size=None) as ws:
            for _ in range(62):  # ~2 s of silence at real-time pace (1024-byte frames, 32 ms each)
                await ws.send(bytes(1024))
                await asyncio.sleep(0.032)
            try:
                while True:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=1.5))
                    print(f"    server -> {msg.get('type')}: {msg.get('message') or msg.get('config') or ''}")
            except asyncio.TimeoutError:
                print("    RESULT: accepted (connection stayed open)")
    except websockets.exceptions.ConnectionClosed as e:
        code = e.rcvd.code if e.rcvd else None
        reason = e.rcvd.reason if e.rcvd else ""
        print(f"    RESULT: REJECTED, close code {code} {reason!r}")
    except Exception as e:
        print(f"    RESULT: could not connect: {e!r}")


async def main() -> None:
    if not API_KEY:
        raise SystemExit("GNANI_API_KEY is empty in .env")
    language = sys.argv[1] if len(sys.argv) > 1 else "hi-IN,en-IN"
    print(f"websockets version {websockets.__version__}, language {language}")
    for level in range(len(FALLBACK_LEVELS)):
        await try_level(language, level)


if __name__ == "__main__":
    asyncio.run(main())
