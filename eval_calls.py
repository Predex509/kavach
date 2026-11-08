"""
Kavach experiment: does Prisma's context (keyterms + topic) help on noisy phone calls?

    .venv/bin/python eval_calls.py                                 # every call in demo_calls/
    .venv/bin/python eval_calls.py --dirs demo_calls demo_calls_noisy
    .venv/bin/python eval_calls.py --only scam_kyc_anydesk_hinglish --configs with_context

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


def headers(language: str, with_context: bool) -> dict:
    h = {
        "x-api-key-id": API_KEY,
        "model": STT_MODEL,
        "language_code": language,
        "x-sample-rate": "8000",  # demo calls are narrowband phone audio
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
        if w.getframerate() != 8000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit(f"{path.name}: expected 8 kHz mono 16-bit (made by make_demo_calls.py)")
        pcm = w.readframes(w.getnframes())
    pcm += bytes(24000)  # 1.5 s of silence so the last sentence is closed
    frames = [pcm[i:i + 1024].ljust(1024, b"\0") for i in range(0, len(pcm), 1024)]

    risk, lines, latencies = CallRisk(), [], []
    first_alert = danger_at = None
    error = None
    t0 = None

    def audio_time() -> float:
        return round(time.monotonic() - t0, 1)

    try:
        async with websockets.connect(STT_URL, additional_headers=headers(language, with_context), max_size=None) as ws:
            t0 = time.monotonic()

            async def send():
                for i, f in enumerate(frames):  # 1024 bytes = 64 ms at 8 kHz; keep real-time pace
                    await ws.send(f)
                    delay = t0 + (i + 1) * 0.064 - time.monotonic()
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
    args = ap.parse_args()
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
