"""
Scam Shield server.

Browser mic (16 kHz PCM)  ->  this server  ->  Gnani Prisma v3.0 streaming STT
                                    |
                     transcript -> pattern engine (+ optional Evon)
                                    |
                     risk + alerts -> browser  (spoken warning via Gnani Timbre)

Run:  uvicorn server:app --reload --port 8000   then open http://localhost:8000
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Optional

import websockets
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

load_dotenv()

import evon  # noqa: E402  (reads env after load_dotenv)
import gnani_tts  # noqa: E402
from detector import CallRisk  # noqa: E402

API_KEY = os.getenv("GNANI_API_KEY", "")
STT_URL = "wss://api.vachana.ai/stt/v3/stream"
STT_MODEL = os.getenv("STT_MODEL", "prisma-v3.0")
# USE_CONTEXT=0 turns off keyterms/topic so you can measure how much they help.
USE_CONTEXT = os.getenv("USE_CONTEXT", "1") == "1"

# Words scammers use that a generic model often mishears. Prisma v3.0 "keyterms" bias recognition.
KEYTERMS = [
    "OTP", "KYC", "PIN", "CVV", "UPI", "QR code", "AnyDesk", "TeamViewer", "QuickSupport",
    "CBI", "RBI", "TRAI", "NCB", "FIR", "FedEx", "DHL", "customs", "narcotics",
    "digital arrest", "money laundering", "crime branch", "cyber crime", "Aadhaar", "PAN card",
    "safe account", "lucky draw", "KBC", "refund", "processing fee", "SBI", "HDFC", "ICICI",
]
TOPIC = ("A phone call in India on speakerphone. The caller may mention a bank, KYC, OTP, "
         "a parcel, police, an app to install, or a payment.")

LEVELS = {"safe": 0, "caution": 1, "danger": 2}

# If Gnani refuses a header (close code 1008), the server steps down through these.
# Tested Nov 8: Gnani streaming rejects `format: codemix` and/or a two-language list such as
# "hi-IN,en-IN", but accepts keyterms + topic with `indic-auto` or a single language.
FALLBACK_LEVELS = [
    "keyterms, topic, VAD tuning",
    "single language, keyterms, topic, VAD tuning",
    "single language, no keyterms/topic",
    "minimal: key, model, language, sample rate",
]


def build_stt_headers(language: str, level: int = 0) -> dict:
    """Prisma streaming headers. Higher `level` = fewer optional settings (fallback when one is rejected)."""
    if level >= 1 and "," in language:
        language = language.split(",")[0]
    headers = {
        "x-api-key-id": API_KEY,
        "model": STT_MODEL,
        "language_code": language,
        "x-sample-rate": "16000",
    }
    if level <= 2:
        headers.update({
            "x-vad-threshold": "0.6",       # speakerphone in a room: a bit stricter than a clean mic
            "x-min-silence-ms": "600",
            "x-min-speech-ms": "150",
            "x-max-speech-s": "15",         # scammers monologue; keep transcripts flowing
            "x-idle-timeout-sec": "300",
        })
    if level <= 1 and USE_CONTEXT:
        # Keyterms help Prisma hear scam words: without them "AnyDesk" came out as "एनी बेस्ट".
        headers["keyterms"] = json.dumps(KEYTERMS)  # ASCII-safe JSON array
        headers["topic"] = TOPIC
    return headers
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Scam Shield")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/config")
async def config():
    return {"has_key": bool(API_KEY), "evon": evon.ENABLED, "context": USE_CONTEXT, "stt_model": STT_MODEL}


class SpeakRequest(BaseModel):
    # Optional[...] instead of `str | None`: pydantic evaluates these at runtime, and
    # the `|` syntax fails on Python 3.9 (the macOS system Python).
    lang: str = "hi"
    level: Optional[str] = None
    text: Optional[str] = None


@app.post("/api/speak")
async def speak(req: SpeakRequest):
    if not API_KEY:
        raise HTTPException(500, "GNANI_API_KEY missing in .env")
    text = req.text or gnani_tts.warning_text(req.level or "danger", req.lang)
    try:
        wav = await gnani_tts.synthesize(text, req.lang, API_KEY)
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    return Response(wav, media_type="audio/wav")


@app.websocket("/ws")
async def call_socket(ws: WebSocket):
    await ws.accept()
    session = CallSession(ws)
    try:
        await session.run()
    except WebSocketDisconnect:
        pass
    finally:
        session.stopped = True


class CallSession:
    FRAME = 1024  # Prisma expects exactly 1024-byte frames (512 samples of 16-bit PCM)

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.send_lock = asyncio.Lock()
        self.audio: asyncio.Queue[bytes] = asyncio.Queue(maxsize=300)
        self.stopped = False
        self.language = "indic-auto"
        self.last_stt_error: str | None = None
        self.reset()

    def reset(self):
        self.risk = CallRisk()
        self.lines: list[str] = []
        self.langs: Counter[str] = Counter()
        self.started = time.monotonic()
        self.alerted = 0
        self.danger_after: float | None = None
        self.evon_result: dict | None = None
        self.evon_busy = False

    async def send(self, payload: dict):
        async with self.send_lock:
            with contextlib.suppress(Exception):
                await self.ws.send_text(json.dumps(payload, ensure_ascii=False))

    # ---------------------------------------------------------------- lifecycle
    async def run(self):
        start = await self.ws.receive_json()
        if start.get("type") != "start":
            await self.send({"type": "error", "message": "expected a start message"})
            return
        if not API_KEY:
            await self.send({"type": "error", "message": "GNANI_API_KEY is missing. Add it to .env and restart."})
            return
        self.language = start.get("language") or "indic-auto"
        self.reset()

        browser = asyncio.create_task(self.read_browser())
        upstream = asyncio.create_task(self.upstream_loop())
        done, pending = await asyncio.wait({browser, upstream}, return_when=asyncio.FIRST_COMPLETED)
        self.stopped = True
        for task in pending:
            task.cancel()
        for task in done:
            if task.exception() and not isinstance(task.exception(), WebSocketDisconnect):
                await self.send({"type": "error", "message": str(task.exception())})

    async def read_browser(self):
        buf = bytearray()
        while not self.stopped:
            msg = await self.ws.receive()
            if msg["type"] == "websocket.disconnect":
                return
            if msg.get("bytes"):
                buf.extend(msg["bytes"])
                while len(buf) >= self.FRAME:
                    frame, buf = bytes(buf[: self.FRAME]), buf[self.FRAME:]
                    if self.audio.full():  # never let latency build up
                        self.audio.get_nowait()
                    self.audio.put_nowait(frame)
            elif msg.get("text"):
                data = json.loads(msg["text"])
                if data.get("type") == "stop":
                    return
                if data.get("type") == "reset":
                    self.reset()
                    await self.send({"type": "reset"})

    # ---------------------------------------------------------------- Gnani STT
    def stt_headers(self, level: int = 0) -> dict:
        return build_stt_headers(self.language, level)

    async def upstream_loop(self):
        """
        Keeps a Prisma stream open. If Gnani rejects the settings straight away (close code 1008),
        retry with simpler settings (see FALLBACK_LEVELS). Reconnects after the 15-minute session cap.
        """
        level = 0
        while not self.stopped:
            opened = time.monotonic()
            self.last_stt_error = None
            close_code = None
            try:
                async with websockets.connect(
                    STT_URL, additional_headers=self.stt_headers(level), max_size=None, ping_interval=20
                ) as stt:
                    print(f"[stt] connected with settings level {level} ({FALLBACK_LEVELS[level]})")
                    sender = asyncio.create_task(self.pump_audio(stt))
                    try:
                        await self.read_stt(stt)
                    finally:
                        sender.cancel()
            except asyncio.CancelledError:
                raise
            except websockets.exceptions.ConnectionClosed as e:
                close_code = e.rcvd.code if e.rcvd else None
                print(f"[stt] closed: code={close_code} reason={e.rcvd.reason if e.rcvd else ''!r} "
                      f"server_error={self.last_stt_error!r}")
            except Exception as e:  # handshake refused (e.g. HTTP 401 = bad key) or network problem
                print(f"[stt] could not connect: {e!r}")
                await self.send({"type": "error", "message": f"Speech service: {e}. Check GNANI_API_KEY in .env."})
                return

            quick = time.monotonic() - opened < 5
            if quick and close_code == 1008 and level + 1 < len(FALLBACK_LEVELS):
                level += 1
                print(f"[stt] settings rejected ({self.last_stt_error}); retrying with level {level} "
                      f"({FALLBACK_LEVELS[level]})")
                await self.send({"type": "notice",
                                 "message": f"Speech service rejected a setting, retrying with simpler settings "
                                            f"({FALLBACK_LEVELS[level]})"})
                continue
            if quick:  # closed almost immediately even with the simplest settings: don't hammer the API
                detail = self.last_stt_error or f"close code {close_code}"
                await self.send({"type": "error", "message": f"Speech service closed the connection: {detail}"})
                return
            await self.send({"type": "status", "state": "reconnecting"})

    async def pump_audio(self, stt):
        while True:
            frame = await self.audio.get()
            await stt.send(frame)

    async def read_stt(self, stt):
        async for raw in stt:
            if isinstance(raw, bytes):
                continue
            msg = json.loads(raw)
            kind = msg.get("type")
            if kind == "connected":
                await self.send({"type": "status", "state": "listening", "config": msg.get("config", {})})
            elif kind in ("speech_start", "processing"):
                await self.send({"type": kind})
            elif kind == "transcript":
                await self.on_transcript(msg)
            elif kind == "error":
                self.last_stt_error = msg.get("message", "speech error")
                print(f"[stt] server error message: {self.last_stt_error!r}")
                await self.send({"type": "error", "message": self.last_stt_error})

    # ---------------------------------------------------------------- detection
    async def on_transcript(self, msg: dict):
        text = (msg.get("text") or "").strip()
        if not text:
            return
        lang = (msg.get("detected_language_code") or "")[:2]
        if lang:
            self.langs[lang] += 1
        self.lines.append(text)
        hits = self.risk.add_segment(text)
        await self.send({
            "type": "transcript",
            "text": text,
            "lang": lang,
            "hits": hits,
            "t": round(time.monotonic() - self.started, 1),
            "latency_ms": msg.get("latency"),
        })
        await self.publish_risk()
        if evon.ENABLED and not self.evon_busy:
            self.evon_busy = True
            asyncio.create_task(self.run_evon())

    async def run_evon(self):
        try:
            result = await evon.assess("\n".join(self.lines))
            if result:
                self.evon_result = result
                await self.publish_risk()
        finally:
            self.evon_busy = False

    def warning_lang(self) -> str:
        native = [(l, n) for l, n in self.langs.most_common() if l != "en"]
        if native:
            return native[0][0]
        if self.langs:
            return "en"
        first = self.language.split(",")[0][:2]
        return first if first not in ("in", "") else "hi"

    async def publish_risk(self):
        analysis = self.risk.analyse()
        score = analysis["score"]
        if self.evon_result:
            score = max(score, self.evon_result["risk"])
        level = "danger" if score >= 65 else "caution" if score >= 35 else "safe"
        elapsed = round(time.monotonic() - self.started, 1)
        if level == "danger" and self.danger_after is None:
            self.danger_after = elapsed

        await self.send({
            "type": "risk",
            **analysis,
            "score": score,
            "rule_score": analysis["score"],
            "level": level,
            "evon": self.evon_result,
            "danger_after_s": self.danger_after,
        })

        if LEVELS[level] > self.alerted:
            self.alerted = LEVELS[level]
            lang = self.warning_lang()
            await self.send({
                "type": "alert",
                "level": level,
                "lang": lang,
                "scam_type_en": analysis["scam_type_en"],
                "scam_type_hi": analysis["scam_type_hi"],
                "reason": (self.evon_result or {}).get("reason"),
            })
