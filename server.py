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
import functools
import json
import os
import re
import time
import traceback
from array import array
from collections import Counter
from pathlib import Path
from typing import Optional

import websockets
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

load_dotenv()

# Flush every log line at once: when uvicorn's output goes to a file, Python buffers it and the
# [call]/[stt] lines showed up late and out of order, which hid what actually failed.
print = functools.partial(print, flush=True)  # noqa: A001

import evon  # noqa: E402  (reads env after load_dotenv)
import gnani_tts  # noqa: E402
from detector import CallRisk, normalize  # noqa: E402

API_KEY = os.getenv("GNANI_API_KEY", "")
STT_URL = "wss://api.vachana.ai/stt/v3/stream"
STT_MODEL = os.getenv("STT_MODEL", "prisma-v3.0")
# USE_CONTEXT=0 turns off keyterms/topic so you can measure how much they help.
USE_CONTEXT = os.getenv("USE_CONTEXT", "1") == "1"
# Listening (VAD) settings for live mic audio. Tune in .env without code changes:
# a phone on speaker sounds quieter and farther away than someone talking into the laptop,
# so a lower threshold keeps more of it; a longer silence keeps sentences from being cut in half.
VAD_THRESHOLD = os.getenv("VAD_THRESHOLD", "0.5")
MIN_SILENCE_MS = os.getenv("MIN_SILENCE_MS", "800")
# Longest sentence before Prisma is made to transcribe anyway. Room noise (fans, coolers) can
# hide the pauses between sentences; a short cap keeps transcripts flowing during a live call.
MAX_SPEECH_S = os.getenv("MAX_SPEECH_S", "8")
# SAVE_AUDIO=1 saves what the browser sent (16 kHz WAV) to recordings/, to debug missed speech.
# Off by default: Kavach does not store audio unless you turn this on for testing.
SAVE_AUDIO = os.getenv("SAVE_AUDIO", "0") == "1"
RECORDINGS = Path(__file__).parent / "recordings"

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


def _words(text: str) -> set[str]:
    # split on spaces/punctuation only: \w would break Hindi/Telugu words at vowel signs
    return {w for w in re.split(r"[\s.,!?।॥|:;\"'()\-]+", normalize(text)) if w}


# Kavach's own warnings, so the live mic does not score them if they leak back in.
_WARNING_WORDS = [_words(t) for level in gnani_tts.WARNINGS.values() for t in level.values()]


def is_own_warning(text: str) -> bool:
    """True when a transcript is mostly the words of one of Kavach's spoken warnings."""
    words = _words(text)
    if len(words) < 4:
        return False
    return any(len(words & w) / len(words) >= 0.6 for w in _WARNING_WORDS)

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
            "x-vad-threshold": VAD_THRESHOLD,   # lower = keeps quieter, farther speech (see .env)
            "x-min-silence-ms": MIN_SILENCE_MS,
            "x-min-speech-ms": "150",
            "x-max-speech-s": MAX_SPEECH_S,  # keep transcripts flowing even in a noisy room
            "x-idle-timeout-sec": "300",
        })
    if level <= 1 and USE_CONTEXT:
        # Keyterms help Prisma hear scam words: without them "AnyDesk" came out as "एनी बेस्ट".
        headers["keyterms"] = json.dumps(KEYTERMS)  # ASCII-safe JSON array
        headers["topic"] = TOPIC
    return headers


async def open_stt(headers: dict):
    """Open one Prisma stream. Tests replace this with a fake Gnani server."""
    return await websockets.connect(STT_URL, additional_headers=headers, max_size=None, ping_interval=20)


STATIC = Path(__file__).parent / "static"

# Spoken warnings: one Timbre try can hang for a long time, so cap each try, retry once, then
# fall back to the English warning (cached on disk at startup). The page falls back to the
# browser's own voice if even that fails, and the red screen never waits for any of this.
TTS_TIMEOUT_S = 10


async def tts(text: str, lang: str) -> bytes:
    return await asyncio.wait_for(gnani_tts.synthesize(text, lang, API_KEY), TTS_TIMEOUT_S)


@contextlib.asynccontextmanager
async def lifespan(_app):
    async def warm():  # make the English fallback warnings instant (free when already cached)
        for level in ("danger", "caution"):
            for lang in ("en", "hi"):
                try:
                    await tts(gnani_tts.warning_text(level, lang), lang)
                except Exception as e:
                    print(f"[tts] could not pre-load the {lang} {level} warning: {e!r}")
    task = asyncio.create_task(warm()) if API_KEY else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="Scam Shield", lifespan=lifespan)


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
    level = req.level or "danger"
    text = req.text or gnani_tts.warning_text(level, req.lang)
    tries = [(text, req.lang, "requested"), (text, req.lang, "retry")]
    if not req.text and req.lang != "en":
        tries.append((gnani_tts.warning_text(level, "en"), "en", "english-fallback"))
    last = None
    for t, lang, label in tries:
        try:
            wav = await tts(t, lang)
            if label != "requested":
                print(f"[tts] {req.lang} {level}: used {label}")
            return Response(wav, media_type="audio/wav", headers={"X-Kavach-Voice": label})
        except Exception as e:
            last = e
            print(f"[tts] {label} ({lang}) failed: {e!r}")
    raise HTTPException(502, f"Spoken warning unavailable: {last!r}")


@app.websocket("/ws")
async def call_socket(ws: WebSocket):
    await ws.accept()
    session = CallSession(ws)
    try:
        await session.run()
    except WebSocketDisconnect:
        session.ended_by = "browser"
        session.end_reason = session.end_reason or "browser disconnected"
    except Exception as e:  # never die silently: log it and tell the page
        traceback.print_exc()
        session.end_reason = f"Kavach server error: {e!r}"
    finally:
        session.stopped = True
    # (Not reached when the server is shutting down: the page should reconnect then, not give up.)
    if session.ended_by != "browser":
        # Tell the page the session is over (and why) so it shows the reason instead of
        # trying to reconnect to a session that cannot work (bad key, speech service down).
        await session.send({"type": "ended", "reason": session.end_reason or "Session ended"})
    with contextlib.suppress(Exception):  # close properly instead of just dropping the connection
        await ws.close()


class CallSession:
    FRAME = 1024  # Prisma expects exactly 1024-byte frames (512 samples of 16-bit PCM)
    PING_S = 5.0  # heartbeat to the page; it reconnects if pings stop for 12 s
    OPEN_TIMEOUT_S = 10.0  # connect + Gnani's "connected" message must arrive within this
    STALL_S = 30.0  # speech went in but Gnani said nothing for this long: reconnect
    STALL_SPEECH_S = 5.0  # ...counting only if there was speech at least this long after its last message
    BACKOFF_S = (0.5, 1.0, 2.0, 2.0, 2.0)  # speech-stream reconnect waits: at most 5 tries in a row
    STABLE_S = 20.0  # a stream that stayed up this long resets the try counter
    WATCH_S = 0.5  # how often the stream watchdog looks

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.send_lock = asyncio.Lock()
        self.audio: asyncio.Queue[bytes] = asyncio.Queue(maxsize=300)  # ~9.6 s
        self.stopped = False
        self.language = "indic-auto"
        self.last_stt_error: str | None = None
        self.ended_by: str | None = None  # "browser" or "speech service"
        self.end_reason: str | None = None
        self.dropped_frames = 0
        self.odd_chunks = 0
        self.bad_stt_messages = 0
        self.audio_bytes = 0
        self.recording = bytearray()
        self.stt_ready = False
        self.last_stt_msg = 0.0
        self.last_loud_at = 0.0
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

    def restore(self, state: dict):
        """
        The page lost its connection and came back mid-call. Replay the transcript it already has
        so the risk score, alerts already given and call clock carry on instead of starting at 0.
        """
        lines = [str(t) for t in (state.get("lines") or []) if str(t).strip()][-300:]
        for i, text in enumerate(lines):  # same steps as on_transcript, so the score matches
            self.lines.append(text)
            self.risk.add_segment(text)
            if i:
                self.risk.add_segment(lines[i - 1] + " " + text)
        for code, n in (state.get("langs") or {}).items():
            self.langs[str(code)[:2]] += int(n)
        self.alerted = LEVELS.get(str(state.get("alerted")), 0)
        self.started -= max(0.0, float(state.get("elapsed") or 0))
        if state.get("danger_after") is not None:
            self.danger_after = float(state["danger_after"])
        print(f"[call] resumed after a dropped page connection: {len(lines)} transcripts, "
              f"level {self.risk.analyse()['level']}")

    def elapsed(self) -> float:
        return round(time.monotonic() - self.started, 1)

    async def send(self, payload: dict):
        async with self.send_lock:
            with contextlib.suppress(Exception):
                await self.ws.send_text(json.dumps(payload, ensure_ascii=False))

    # ---------------------------------------------------------------- lifecycle
    async def run(self):
        try:
            start = await self.ws.receive_json()
        except (ValueError, KeyError):
            start = {}
        if start.get("type") != "start":
            self.end_reason = "The page sent an unexpected first message. Reload the page."
            print(f"[call] {self.end_reason}")
            return
        if not API_KEY:
            self.end_reason = "GNANI_API_KEY is missing. Add it to .env and restart the server."
            print(f"[call] {self.end_reason}")
            return
        self.language = start.get("language") or "indic-auto"
        self.reset()
        if isinstance(start.get("resume"), dict):
            try:
                self.restore(start["resume"])
            except Exception as e:  # a bad resume must not stop the call: start fresh instead
                print(f"[call] could not restore the previous transcript: {e!r}")
                self.reset()
        print(f"[call] started, language={self.language}, vad={VAD_THRESHOLD}, silence={MIN_SILENCE_MS}ms")
        if self.lines:
            await self.publish_risk()  # put the page back in sync after a reconnect

        browser = asyncio.create_task(self.read_browser())
        upstream = asyncio.create_task(self.upstream_loop())
        helpers = [asyncio.create_task(self.audio_watchdog()), asyncio.create_task(self.heartbeat())]
        try:
            done, pending = await asyncio.wait({browser, upstream}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            self.stopped = True
            for task in [browser, upstream, *helpers]:
                task.cancel()
            await asyncio.gather(browser, upstream, *helpers, return_exceptions=True)

        for task in done:
            exc = task.exception()
            if exc and not isinstance(exc, WebSocketDisconnect):
                print(f"[call] {'browser reader' if task is browser else 'speech stream'} crashed: {exc!r}")
                traceback.print_exception(type(exc), exc, exc.__traceback__)
                self.end_reason = f"Kavach server error: {exc!r}"
        self.ended_by = "browser" if browser in done else "speech service"
        print(f"[call] received {self.audio_bytes / 32000:.1f}s of audio from the browser"
              + (f", dropped {self.dropped_frames} frames (queue full)" if self.dropped_frames else "")
              + (f", fixed {self.odd_chunks} odd-sized chunks" if self.odd_chunks else "")
              + (f", ignored {self.bad_stt_messages} malformed speech messages" if self.bad_stt_messages else ""))
        print(f"[call] ended by {self.ended_by} ({self.end_reason or 'no reason given'}) after "
              f"{self.elapsed():.0f}s, {len(self.lines)} transcripts, final {self.risk.analyse()['level']}")
        if SAVE_AUDIO and self.recording:
            import wave
            RECORDINGS.mkdir(exist_ok=True)
            path = RECORDINGS / f"call-{time.strftime('%Y%m%d-%H%M%S')}.wav"
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(bytes(self.recording))
            print(f"[call] saved {path.name} ({len(self.recording) / 32000:.1f}s)")

    async def heartbeat(self):
        while not self.stopped:
            await asyncio.sleep(self.PING_S)
            await self.send({"type": "ping", "t": self.elapsed()})

    async def audio_watchdog(self):
        """Tell the user if the browser is not sending audio (mic blocked, browser bug)."""
        await asyncio.sleep(4)
        if self.audio_bytes == 0 and not self.stopped:
            print("[call] WARNING: no audio received from the browser after 4s")
            await self.send({"type": "error", "message": "No audio is reaching Kavach from the browser. "
                             "Check the microphone permission, or try Chrome."})

    async def read_browser(self):
        buf = bytearray()
        while not self.stopped:
            msg = await self.ws.receive()
            if msg["type"] == "websocket.disconnect":
                self.end_reason = self.end_reason or f"browser disconnected (code {msg.get('code')})"
                return
            data = msg.get("bytes")
            if data:
                self.audio_bytes += len(data)
                if SAVE_AUDIO:
                    self.recording.extend(data)
                if len(data) % 2:  # half a sample would shift every later sample: drop the odd byte
                    self.odd_chunks += 1
                    data = data[:-1]
                buf.extend(data)
                while len(buf) >= self.FRAME:  # always exact 1024-byte frames, remainder kept
                    frame = bytes(buf[: self.FRAME])
                    del buf[: self.FRAME]
                    if self.audio.full():  # never let latency build up: drop the oldest frame
                        self.audio.get_nowait()
                        self.dropped_frames += 1
                        if self.dropped_frames == 1 or self.dropped_frames % 100 == 0:
                            print(f"[call] audio queue full, dropped {self.dropped_frames} frames so far "
                                  f"({self.dropped_frames * 0.032:.1f}s)")
                    self.audio.put_nowait(frame)
            elif msg.get("text"):
                try:
                    data = json.loads(msg["text"])
                except ValueError:
                    print("[call] ignored a malformed message from the page")
                    continue
                if data.get("type") == "stop":
                    self.end_reason = "stopped by user"
                    return
                if data.get("type") == "reset":
                    self.reset()
                    await self.send({"type": "reset"})

    # ---------------------------------------------------------------- Gnani STT
    def stt_headers(self, level: int = 0) -> dict:
        return build_stt_headers(self.language, level)

    async def upstream_loop(self):
        """
        Keeps a Prisma stream open for the whole call. If Gnani rejects the settings straight away
        (close code 1008), retry with simpler settings (FALLBACK_LEVELS). If the stream drops for
        any other reason (network, idle timeout, 15-minute cap, Gnani going silent), reconnect with
        backoff. The transcript and risk score live on this session, so nothing is lost.
        """
        level = 0
        failures = 0
        while not self.stopped:
            opened = time.monotonic()
            self.last_stt_error = None
            close_code, problem = None, None
            try:
                stt = await asyncio.wait_for(open_stt(self.stt_headers(level)), self.OPEN_TIMEOUT_S)
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                problem = f"no answer from the speech service within {self.OPEN_TIMEOUT_S:.0f}s"
            except Exception as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status in (401, 403):  # retrying cannot fix a wrong key
                    self.end_reason = f"Speech service refused the API key (HTTP {status}). Check GNANI_API_KEY in .env."
                    print(f"[stt] {self.end_reason}")
                    return
                problem = f"could not connect: {e!r}"
            else:
                print(f"[stt] connected with settings level {level} ({FALLBACK_LEVELS[level]})")
                try:
                    close_code, problem = await self.stream(stt)
                finally:
                    with contextlib.suppress(Exception):
                        await stt.close()
            if self.stopped:
                return

            lasted = time.monotonic() - opened
            if lasted < 5 and close_code == 1008:
                if level + 1 < len(FALLBACK_LEVELS):
                    level += 1
                    print(f"[stt] settings rejected ({self.last_stt_error}); retrying with level {level} "
                          f"({FALLBACK_LEVELS[level]})")
                    await self.send({"type": "notice",
                                     "message": f"Speech service rejected a setting, retrying with simpler "
                                                f"settings ({FALLBACK_LEVELS[level]})"})
                    continue
                self.end_reason = ("Speech service rejected even the simplest settings: "
                                   f"{self.last_stt_error or 'close code 1008'}")
                print(f"[stt] {self.end_reason}")
                return

            failures = 1 if lasted >= self.STABLE_S else failures + 1
            if failures > len(self.BACKOFF_S):
                self.end_reason = (f"Speech service keeps dropping ({problem}). Check the internet "
                                   "connection, then press Start again.")
                print(f"[stt] giving up after {len(self.BACKOFF_S)} tries: {problem}")
                return
            delay = self.BACKOFF_S[failures - 1]
            print(f"[stt] {problem}; reconnecting in {delay}s (try {failures}/{len(self.BACKOFF_S)})")
            await self.send({"type": "status", "state": "reconnecting", "attempt": failures,
                             "of": len(self.BACKOFF_S), "reason": problem})
            await asyncio.sleep(delay)

    async def stream(self, stt) -> tuple[Optional[int], str]:
        """Run one Prisma connection until it ends. Returns (close code, why it ended)."""
        self.stt_ready = False
        self.last_stt_msg = time.monotonic()
        tasks = {
            asyncio.create_task(self.pump_audio(stt)): "sending audio",
            asyncio.create_task(self.read_stt(stt)): "reading transcripts",
            asyncio.create_task(self.stt_watch()): "watchdog",
        }
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        task = done.pop()
        what = tasks[task]
        if task.cancelled():
            return None, f"{what} stopped"
        exc = task.exception()
        if isinstance(exc, websockets.exceptions.ConnectionClosed):
            code = exc.rcvd.code if exc.rcvd else None
            reason = exc.rcvd.reason if exc.rcvd else ""
            print(f"[stt] closed: code={code} reason={reason!r} server_error={self.last_stt_error!r}")
            return code, f"speech stream closed (code {code}{', ' + self.last_stt_error if self.last_stt_error else ''})"
        if exc:
            print(f"[stt] {what} failed: {exc!r}")
            return None, f"{what} failed: {exc!r}"
        if what == "watchdog":
            print(f"[stt] {task.result()}")
            return None, task.result()
        code = getattr(stt, "close_code", None)  # the stream ended normally
        print(f"[stt] closed: code={code} server_error={self.last_stt_error!r}")
        return code, f"speech stream closed (code {code})"

    async def stt_watch(self) -> str:
        """Notice a Gnani stream that is open but has gone silent, so it can be replaced."""
        opened = time.monotonic()
        while True:
            await asyncio.sleep(self.WATCH_S)
            now = time.monotonic()
            if not self.stt_ready and now - opened > self.OPEN_TIMEOUT_S:
                return f"speech service connected but sent nothing for {self.OPEN_TIMEOUT_S:.0f}s"
            if (self.stt_ready and now - self.last_stt_msg > self.STALL_S
                    and self.last_loud_at - self.last_stt_msg > self.STALL_SPEECH_S):
                return f"speech service silent for {self.STALL_S:.0f}s while speech was going in"

    async def pump_audio(self, stt):
        while True:
            frame = await self.audio.get()
            await stt.send(frame)
            samples = array("h", frame)
            if max(samples) > 2500 or min(samples) < -2500:  # speech-loud peaks (about -22 dB), not fan hum
                self.last_loud_at = time.monotonic()

    async def read_stt(self, stt):
        async for raw in stt:
            self.last_stt_msg = time.monotonic()
            if isinstance(raw, bytes):
                continue
            try:
                msg = json.loads(raw)
                if not isinstance(msg, dict):
                    raise ValueError("not a JSON object")
            except ValueError:
                self.bad_stt_messages += 1
                print(f"[stt] ignored a malformed message: {raw[:80]!r}")
                continue
            try:
                await self.on_stt_message(msg)
            except Exception as e:  # one bad message must never end the call
                print(f"[call] error handling a {msg.get('type')!r} message, carrying on: {e!r}")
                traceback.print_exc()

    async def on_stt_message(self, msg: dict):
        kind = msg.get("type")
        if not self.stt_ready:
            self.stt_ready = True
            await self.send({"type": "status", "state": "listening", "config": msg.get("config", {})})
            if kind == "connected":
                return
        if kind in ("speech_start", "processing"):
            await self.send({"type": kind})
        elif kind == "transcript":
            await self.on_transcript(msg)
        elif kind == "error":
            self.last_stt_error = msg.get("message", "speech error")
            print(f"[stt] server error message: {self.last_stt_error!r}")
            await self.send({"type": "error", "message": f"Speech service: {self.last_stt_error}"})

    # ---------------------------------------------------------------- detection
    async def on_transcript(self, msg: dict):
        text = (msg.get("text") or "").strip()
        if not text:
            # Speech was heard but nothing could be made out: show it in the transcript so the
            # conversation reads complete instead of silently skipping that part.
            await self.send({"type": "unclear", "t": self.elapsed()})
            return
        if is_own_warning(text):
            print(f"[stt] ignored Kavach's own warning: {text}")
            return
        lang = (msg.get("detected_language_code") or "")[:2]
        if lang:
            self.langs[lang] += 1
        self.lines.append(text)
        hits = self.risk.add_segment(text)
        if len(self.lines) > 1:
            # A phrase can be split across two captions ("…digital" | "arrest…") when the mic
            # audio is cut mid-sentence; also check the previous caption joined with this one.
            self.risk.add_segment(self.lines[-2] + " " + text)
        print(f"[stt] {self.elapsed():5.1f}s [{lang}] {text}")
        await self.send({
            "type": "transcript",
            "text": text,
            "lang": lang,
            "hits": hits,
            "t": self.elapsed(),
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
        except Exception as e:
            print(f"[evon] error, carrying on without it: {e!r}")
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
        try:
            analysis = self.risk.analyse()
        except Exception as e:
            print(f"[call] risk analysis failed, keeping the last verdict: {e!r}")
            traceback.print_exc()
            return
        score = analysis["score"]
        if self.evon_result:
            score = max(score, self.evon_result.get("risk", 0))
        level = "danger" if score >= 65 else "caution" if score >= 35 else "safe"
        if level == "danger" and self.danger_after is None:
            self.danger_after = self.elapsed()

        # The alert goes out first: the red screen and warning must never wait on anything else.
        if LEVELS[level] > self.alerted:
            self.alerted = LEVELS[level]
            lang = self.warning_lang()
            print(f"[call] ALERT {level} at {self.elapsed()}s ({analysis.get('scam_type_en')}), warning in {lang}")
            await self.send({
                "type": "alert",
                "level": level,
                "lang": lang,
                "scam_type_en": analysis.get("scam_type_en"),
                "scam_type_hi": analysis.get("scam_type_hi"),
                "reason": (self.evon_result or {}).get("reason"),
                # The words to speak, so the page can use the browser's own voice if Timbre fails.
                "text": gnani_tts.warning_text(level, lang),
                "text_en": gnani_tts.warning_text(level, "en"),
            })
        await self.send({
            "type": "risk",
            **analysis,
            "score": score,
            "rule_score": analysis["score"],
            "level": level,
            "evon": self.evon_result,
            "danger_after_s": self.danger_after,
        })
