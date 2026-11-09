"""
Kavach experiment: does Prisma's context (keyterms + topic) help on noisy phone calls?

    .venv/bin/python eval_calls.py                                 # every call in demo_calls/
    .venv/bin/python eval_calls.py --dirs demo_calls demo_calls_noisy
    .venv/bin/python eval_calls.py --only scam_kyc_anydesk_hinglish --configs with_context
    .venv/bin/python eval_calls.py --dirs recordings --configs with_context   # replay saved mic tests
    .venv/bin/python eval_calls.py --via-server --rounds 3   # through the running server, like the page

Each demo call (8 kHz WAV) is streamed to Gnani Prisma v3.0 at real-time speed, once WITH keyterms
and topic and once WITHOUT, using the same VAD settings as the app. Every transcript goes through the
same detector the app uses. For each run it records:
  * when the first alert (caution) and the danger alert fired, in seconds of call audio
  * the final verdict (normal calls must stay "safe")
  * how many of the scam words actually spoken (AnyDesk, KYC, OTP, ...) Prisma transcribed recognisably
Results print as a markdown table and are saved to eval_results.md.

Runs take as long as the audio (about 2-3 minutes per folder per setting) and use STT credits.
Never prints the API key.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
import wave
from array import array
from pathlib import Path

import websockets

from detector import CallRisk
from make_demo_calls import CALLS
from server import API_KEY, KEYTERMS, STT_MODEL, STT_URL, TOPIC

HERE = Path(__file__).parent

# Scam words worth hearing correctly, with the spellings Prisma uses (Latin or Indic script).
TERMS = {
    "AnyDesk": [r"any ?desk", "एनीडेस्क", "एनी डेस्क", "ఎనీడెస్క్"],
    "KYC": [r"\bkyc\b", "केवाईसी", "के वाई सी", "కేవైసీ", "కేవైసి"],
    "OTP": [r"\botp\b", "ओटीपी", "ओ टी पी", "ఓటీపీ", "ఓటిపి"],
    "PIN": [r"\bpin\b", "पिन", "పిన్"],
    "UPI": [r"\bupi\b", "यूपीआई", "यू पी आई", "యూపీఐ", "యూ పీ ఐ"],
    "QR code": [r"qr ?code", "क्यूआर", "क्यू आर", "క్యూఆర్", "క్యూ ఆర్"],
    "digital arrest": [r"digital arrest", "डिजिटल अरेस्ट"],
    "money laundering": [r"money laundering", "मनी लॉन्ड्रिंग", "मनी लांड्रिंग"],
    "crime branch": [r"crime branch", "क्राइम ब्रांच"],
    "SBI": [r"\bsbi\b", "एसबीआई", "एस बी आई", "ఎస్‌బిఐ", "ఎస్ బి ఐ"],
    "HDFC": [r"\bhdfc\b", "एचडीएफसी", "एच डी एफ सी"],
    "customer care": [r"customer care", "कस्टमर केयर"],
}


def _found(term: str, text: str) -> bool:
    low = text.lower()
    return any((re.search(p, low) if p.isascii() else p in text) for p in TERMS[term])


def spoken_terms(name: str) -> list[str]:
    """Scam words that are actually in this call's script."""
    script = " ".join(t for _, t in CALLS.get(name, ("", []))[1])
    return [t for t in TERMS if _found(t, script)]


def headers(language: str, with_context: bool, rate: int = 8000) -> dict:
    h = {
        "x-api-key-id": API_KEY,
        "model": STT_MODEL,
        "language_code": language,
        "x-sample-rate": str(rate),  # 8 kHz demo calls, or 16 kHz mic recordings
        "x-vad-threshold": "0.6",
        "x-min-silence-ms": "600",
        "x-min-speech-ms": "150",
        "x-max-speech-s": "15",
        "x-idle-timeout-sec": "60",
    }
    if with_context:
        h["keyterms"] = json.dumps(KEYTERMS)
        h["topic"] = TOPIC
    return h


async def run_call(path: Path, language: str, with_context: bool) -> dict:
    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        if rate not in (8000, 16000) or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit(f"{path.name}: expected 8 or 16 kHz mono 16-bit WAV")
        pcm = w.readframes(w.getnframes())
    pcm += bytes(int(rate * 1.5) * 2)  # 1.5 s of silence so the last sentence is closed
    frame_s = 512 / rate  # 1024 bytes = 512 samples
    frames = [pcm[i:i + 1024].ljust(1024, b"\0") for i in range(0, len(pcm), 1024)]

    risk, lines, latencies = CallRisk(), [], []
    first_alert = danger_at = None
    error = None
    t0 = None

    def audio_time() -> float:
        return round(time.monotonic() - t0, 1)

    try:
        async with websockets.connect(STT_URL, additional_headers=headers(language, with_context, rate), max_size=None) as ws:
            t0 = time.monotonic()

            async def send():
                for i, f in enumerate(frames):  # keep real-time pace
                    await ws.send(f)
                    delay = t0 + (i + 1) * frame_s - time.monotonic()
                    if delay > 0:
                        await asyncio.sleep(delay)

            async def receive():
                nonlocal first_alert, danger_at, error
                async for raw in ws:
                    if isinstance(raw, bytes):
                        continue
                    msg = json.loads(raw)
                    if msg.get("type") == "transcript" and (msg.get("text") or "").strip():
                        lines.append(msg["text"].strip())
                        if msg.get("latency") is not None:
                            latencies.append(msg["latency"])
                        risk.add_segment(msg["text"])
                        level = risk.analyse()["level"]
                        if level != "safe" and first_alert is None:
                            first_alert = audio_time()
                        if level == "danger" and danger_at is None:
                            danger_at = audio_time()
                    elif msg.get("type") == "error":
                        error = msg.get("message")

            sender = asyncio.create_task(send())
            receiver = asyncio.create_task(receive())
            await sender
            try:
                await asyncio.wait_for(receiver, timeout=5)  # wait for the last transcripts
            except asyncio.TimeoutError:
                pass
    except websockets.exceptions.ConnectionClosed as e:
        code = e.rcvd.code if e.rcvd else None
        error = f"{error or 'connection closed'} (code {code})"
    except Exception as e:
        error = repr(e)

    transcript = " ".join(lines)
    expected = spoken_terms(path.stem)
    heard = [t for t in expected if _found(t, transcript)]
    analysis = risk.analyse()
    return {
        "call": path.stem,
        "folder": path.parent.name,
        "config": "with_context" if with_context else "no_context",
        "level": analysis["level"],
        "score": analysis["score"],
        "scam_type": analysis["scam_type_en"],
        "first_alert_s": first_alert,
        "danger_s": danger_at,
        "heard": heard,
        "missed": [t for t in expected if t not in heard],
        "expected_terms": expected,
        "median_latency_ms": sorted(latencies)[len(latencies) // 2] if latencies else None,
        "error": error,
        "transcript": transcript,
    }


def to_16k(pcm: bytes, rate: int) -> bytes:
    """The page always sends 16 kHz. Upsample 8 kHz demo calls by linear interpolation."""
    if rate == 16000:
        return pcm
    a = array("h", pcm)
    out = array("h", bytes(len(a) * 4))
    for i, v in enumerate(a):
        out[2 * i] = v
        out[2 * i + 1] = (v + a[i + 1]) // 2 if i + 1 < len(a) else v
    return out.tobytes()


async def run_call_via_server(path: Path, language: str, url: str) -> dict:
    """
    Stream one call through the running Kavach server exactly like the page does (16 kHz, 1024-byte
    frames, real time, 1.5 s trailing silence) and record what the server sends back, including
    stalls: the server pings every 5 s, so any gap over 7 s between messages is a stall.
    """
    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        pcm = to_16k(w.readframes(w.getnframes()), rate)
    pcm += bytes(16000 * 2 * 3 // 2)  # 1.5 s of silence, as the page sends
    frames = [pcm[i:i + 1024].ljust(1024, b"\0") for i in range(0, len(pcm), 1024)]

    msgs: list[tuple[float, dict]] = []
    t0 = time.monotonic()
    error = None
    try:
        async with websockets.connect(url, max_size=None) as ws:
            await ws.send(json.dumps({"type": "start", "language": language}))

            async def send():
                start = time.monotonic()
                for i, f in enumerate(frames):
                    await ws.send(f)
                    delay = start + (i + 1) * 0.032 - time.monotonic()
                    if delay > 0:
                        await asyncio.sleep(delay)
                await asyncio.sleep(4)  # the page waits 4 s for the last sentence, then stops
                await ws.send(json.dumps({"type": "stop"}))

            async def receive():
                async for raw in ws:
                    msgs.append((time.monotonic() - t0, json.loads(raw)))

            sender = asyncio.create_task(send())
            receiver = asyncio.create_task(receive())
            await sender
            try:
                await asyncio.wait_for(receiver, timeout=3)
            except asyncio.TimeoutError:
                receiver.cancel()
    except Exception as e:
        error = repr(e)

    of = lambda kind: [m for _, m in msgs if m.get("type") == kind]
    times = [0.0] + [t for t, _ in msgs]
    gaps = [b - a for a, b in zip(times, times[1:])]
    risks = of("risk")
    level = risks[-1]["level"] if risks else "safe"
    danger = next((m["danger_after_s"] for m in risks if m.get("danger_after_s") is not None), None)
    problems = [m.get("message") or m.get("reason") for m in of("error") + of("ended")]
    reconnects = sum(1 for m in of("status") if m.get("state") == "reconnecting")
    return {
        "call": path.stem, "folder": path.parent.name, "level": level,
        "score": risks[-1]["score"] if risks else 0, "danger_s": danger,
        "transcripts": len(of("transcript")), "pings": len(of("ping")),
        "max_gap_s": round(max(gaps), 1) if gaps else None, "reconnects": reconnects,
        "problems": problems, "error": error,
    }


async def main_via_server(args) -> None:
    files = []
    for d in args.dirs:
        files += sorted(p for p in (HERE / d).glob("*.wav") if not args.only or p.stem in args.only)
    if not files:
        raise SystemExit("No WAV files found.")
    rows = ["| Round | Call | Audio | Verdict | Danger at | Transcripts | Longest silence from server | Reconnects | Problems |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    results = []
    for rnd in range(1, args.rounds + 1):
        for path in files:
            print(f"[round {rnd}/{args.rounds}] {path.parent.name}/{path.name} ...", flush=True)
            r = await run_call_via_server(path, args.language, args.via_server)
            r["round"] = rnd
            r["ok"] = verdict_ok(r) and not r["error"] and not r["problems"] and (r["max_gap_s"] or 99) <= 7
            results.append(r)
            print(f"         {r['level']} {r['score']}, danger at {r['danger_s']}, {r['transcripts']} transcripts, "
                  f"longest gap {r['max_gap_s']}s, reconnects {r['reconnects']}, problems {r['problems']}, "
                  f"error {r['error']} -> {'OK' if r['ok'] else 'FAIL'}", flush=True)
            mark = "" if r["ok"] else " ✗"
            rows.append(f"| {rnd} | {r['call']} | {r['folder']} | {r['level']} {r['score']}{mark} | "
                        f"{r['danger_s'] if r['danger_s'] is not None else 'never'} | {r['transcripts']} | "
                        f"{r['max_gap_s']} s | {r['reconnects']} | {'; '.join(map(str, r['problems'])) or r['error'] or ''} |")
    ok = sum(r["ok"] for r in results)
    summary_line = f"**{ok}/{len(results)} runs correct with no stalls** ({args.rounds} rounds, through {args.via_server})"
    md = "\n".join(rows)
    print("\n" + md + "\n\n" + summary_line)
    (HERE / "eval_server_results.md").write_text(
        f"# Kavach reliability run (through the server)\n\nLanguage setting: `{args.language}`. Each call is "
        "streamed to the running server like the page does. A stall = more than 7 s with no message from "
        f"the server (it pings every 5 s).\n\n{md}\n\n{summary_line}\n", encoding="utf-8")
    print("\nSaved eval_server_results.md")
    if ok != len(results):
        raise SystemExit(1)


def verdict_ok(r: dict) -> bool:
    return r["level"] == "safe" if r["call"].startswith("normal") else r["level"] != "safe"


def table(results: list[dict]) -> str:
    rows = [
        "| Call | Audio | Setting | Verdict | First alert | Danger at | Scam words heard | Median latency |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        if r["error"] and not r["transcript"]:
            rows.append(f"| {r['call']} | {r['folder']} | {r['config']} | rejected: {r['error']} | | | | |")
            continue
        words = f"{len(r['heard'])}/{len(r['expected_terms'])}" if r["expected_terms"] else "n/a"
        if r["missed"]:
            words += f" (missed {', '.join(r['missed'])})"
        verdict = f"{r['level']} {r['score']}" + ("" if verdict_ok(r) else " ✗")
        fmt = lambda s: f"{s:.1f} s" if s is not None else "never"
        lat = f"{r['median_latency_ms']} ms" if r["median_latency_ms"] is not None else ""
        rows.append(f"| {r['call']} | {r['folder']} | {r['config']} | {verdict} | {fmt(r['first_alert_s'])} | "
                    f"{fmt(r['danger_s'])} | {words} | {lat} |")
    return "\n".join(rows)


def summary(results: list[dict]) -> str:
    out = []
    for cfg in ("with_context", "no_context"):
        rs = [r for r in results if r["config"] == cfg and not (r["error"] and not r["transcript"])]
        if not rs:
            continue
        exp = sum(len(r["expected_terms"]) for r in rs)
        heard = sum(len(r["heard"]) for r in rs)
        ok = sum(verdict_ok(r) for r in rs)
        dangers = [r["danger_s"] for r in rs if r["danger_s"] is not None and not r["call"].startswith("normal")]
        avg = f"{sum(dangers) / len(dangers):.1f} s" if dangers else "n/a"
        out.append(f"- **{cfg}**: correct verdict {ok}/{len(rs)}, scam words heard {heard}/{exp}, "
                   f"average time to danger {avg}")
    return "\n".join(out)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", nargs="+", default=["demo_calls"])
    ap.add_argument("--configs", nargs="+", default=["with_context", "no_context"],
                    choices=["with_context", "no_context"])
    ap.add_argument("--only", nargs="*", help="only these call names")
    ap.add_argument("--language", default="indic-auto")
    ap.add_argument("--via-server", metavar="WS_URL", nargs="?", const="ws://localhost:8000/ws",
                    help="stream through the running Kavach server instead of straight to Gnani")
    ap.add_argument("--rounds", type=int, default=1, help="with --via-server: run every call this many times")
    args = ap.parse_args()
    if args.via_server:
        return await main_via_server(args)
    if not API_KEY:
        raise SystemExit("GNANI_API_KEY is empty in .env")

    files = []
    for d in args.dirs:
        files += sorted(p for p in (HERE / d).glob("*.wav") if not args.only or p.stem in args.only)
    if not files:
        raise SystemExit("No WAV files found. Run make_demo_calls.py first.")

    results = []
    total = len(files) * len(args.configs)
    for i, path in enumerate(files):
        for j, cfg in enumerate(args.configs):
            n = i * len(args.configs) + j + 1
            print(f"[{n}/{total}] {path.parent.name}/{path.name}  {cfg} ...", flush=True)
            r = await run_call(path, args.language, cfg == "with_context")
            results.append(r)
            status = r["error"] if (r["error"] and not r["transcript"]) else \
                f"{r['level']} {r['score']}, danger at {r['danger_s']}, heard {r['heard']} missed {r['missed']}"
            print(f"         {status}", flush=True)

    md = table(results)
    summ = summary(results)
    print("\n" + md + "\n\n" + summ)
    report = (f"# Kavach evaluation\n\nLanguage setting: `{args.language}`, model `{STT_MODEL}`, "
              f"8 kHz synthetic phone calls made with Gnani Timbre.\n\n{md}\n\n{summ}\n\n"
              "## Transcripts\n\n" +
              "\n".join(f"- **{r['call']}** ({r['folder']}, {r['config']}): {r['transcript'] or '(none)'}"
                        for r in results))
    (HERE / "eval_results.md").write_text(report, encoding="utf-8")
    print("\nSaved eval_results.md")


if __name__ == "__main__":
    asyncio.run(main())
