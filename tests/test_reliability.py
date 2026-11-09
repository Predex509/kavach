"""
Reliability tests for the live call session (server.py), no API key or network needed.

Runs the real CallSession against a fake Gnani speech stream and a fake browser, and checks that
every failure either recovers or tells the user clearly, and never hangs or crashes.

    .venv/bin/python tests/test_reliability.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from websockets.exceptions import ConnectionClosedError  # noqa: E402
from websockets.frames import Close  # noqa: E402

import gnani_tts  # noqa: E402
import server  # noqa: E402

server.API_KEY = "test-key"  # never used for a real request: Gnani is faked below
server.print = lambda *a, **k: None  # keep test output readable; failures still show

# Fast timings so the whole suite runs in seconds. Same logic, shorter waits.
S = server.CallSession
S.PING_S = 0.2
S.OPEN_TIMEOUT_S = 0.4
S.STALL_S = 0.8
S.STALL_SPEECH_S = 0.3
S.BACKOFF_S = (0.05, 0.1, 0.2, 0.2, 0.2)
S.STABLE_S = 2.0
S.WATCH_S = 0.05

KYC = "Main SBI bank se bol raha hoon, aapka KYC expire ho gaya hai"  # caution on its own
OTP = "Abhi aapke phone pe OTP aaya hoga, woh bata dijiye"  # with KYC: danger
LOUD = array("h", [3000, -3000] * 512).tobytes()  # 1024 bytes of "speech"


# ---------------------------------------------------------------------------- fakes
class FakeBrowser:
    """Stands in for the page's WebSocket: sends audio, records everything the server says."""

    def __init__(self, start: dict | None = None):
        self.start = start or {"type": "start", "language": "indic-auto"}
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.sent: list[dict] = []

    async def accept(self):
        pass

    async def receive_json(self):
        return self.start

    async def receive(self):
        return await self.inbox.get()

    async def send_text(self, text: str):
        self.sent.append(json.loads(text))

    def audio(self, data: bytes):
        self.inbox.put_nowait({"type": "websocket.receive", "bytes": data})

    def stop(self):
        self.inbox.put_nowait({"type": "websocket.receive", "text": json.dumps({"type": "stop"})})

    def of(self, kind: str) -> list[dict]:
        return [m for m in self.sent if m.get("type") == kind]


class FakeSTT:
    """A fake Prisma stream. `script(conn)` decides what Gnani says and when it hangs up."""

    def __init__(self, script):
        self.q: asyncio.Queue = asyncio.Queue()
        self.frames: list[bytes] = []
        self.closed = False
        self.close_code = None
        self.fail_send = False
        self.task = asyncio.ensure_future(script(self))

    async def say(self, msg):
        await self.q.put(msg if isinstance(msg, str) else json.dumps(msg))

    async def hang_up(self, code: int, reason: str = ""):
        await self.q.put(("close", code, reason))

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.q.get()
        if isinstance(item, tuple):
            _, code, reason = item
            self.closed, self.close_code = True, code
            if code == 1000:
                raise StopAsyncIteration
            raise ConnectionClosedError(Close(code, reason), None)
        return item

    async def send(self, frame: bytes):
        if self.closed or self.fail_send:
            raise ConnectionClosedError(None, None)
        assert len(frame) == 1024, f"frame of {len(frame)} bytes sent to Gnani"
        self.frames.append(frame)

    async def close(self):
        self.closed = True
        self.task.cancel()


async def forever():
    await asyncio.Event().wait()


def transcript(text: str, lang: str = "hi") -> dict:
    return {"type": "transcript", "text": text, "detected_language_code": f"{lang}-IN"}


async def healthy(conn, lines=(), then=None):
    """A working Gnani: says connected, sends the lines, and keeps answering (speech events)."""
    async def keepalive():
        while True:
            await asyncio.sleep(0.2)
            await conn.say({"type": "speech_start"})

    alive = asyncio.ensure_future(keepalive())
    try:
        await conn.say({"type": "connected", "config": {}})
        for line in lines:
            await asyncio.sleep(0.1)
            await conn.say(transcript(line))
        if then:
            await then(conn)
        await forever()
    finally:
        alive.cancel()


# ---------------------------------------------------------------------------- harness
class Run:
    def __init__(self, connections, browser: FakeBrowser | None = None):
        """`connections`: one entry per connect attempt (the last one repeats). Each entry is a
        script for FakeSTT, or the string "hang" (connect never completes), or an exception."""
        self.connections = connections
        self.browser = browser or FakeBrowser()
        self.headers: list[dict] = []
        self.streams: list[FakeSTT] = []

    async def open_stt(self, headers):
        i = len(self.headers)
        self.headers.append(headers)
        spec = self.connections[min(i, len(self.connections) - 1)]
        if spec == "hang":
            await forever()
        if isinstance(spec, Exception):
            raise spec
        conn = FakeSTT(spec)
        self.streams.append(conn)
        return conn

    async def go(self, until, timeout: float = 8.0, audio: bytes = LOUD, stop: bool = True):
        """Run the session, feeding audio, until `until(browser)` is true (then the user presses
        Stop) or the session ends by itself. Fails if anything takes longer than `timeout`."""
        server.open_stt = self.open_stt
        b = self.browser

        async def feed():
            while True:
                b.audio(audio)
                await asyncio.sleep(0.01)

        feeder = asyncio.ensure_future(feed())
        session = asyncio.ensure_future(server.call_socket(b))
        t0 = time.monotonic()
        try:
            while not session.done() and not until(b):
                assert time.monotonic() - t0 < timeout, f"hung: {[m['type'] for m in b.sent][-12:]}"
                await asyncio.sleep(0.02)
            if not session.done() and stop:
                b.stop()
            await asyncio.wait_for(session, timeout)  # must end promptly, never hang
        finally:
            feeder.cancel()
            for s in self.streams:
                s.task.cancel()
        return b


def has_line(b: FakeBrowser, text: str) -> bool:
    return any(m.get("text") == text for m in b.of("transcript"))


def last_level(b: FakeBrowser) -> str | None:
    risks = b.of("risk")
    return risks[-1]["level"] if risks else None


def ended_reason(b: FakeBrowser) -> str:
    ended = b.of("ended")
    return ended[-1]["reason"] if ended else ""


# ---------------------------------------------------------------------------- cases
async def case_a_closes_after_3s():
    """(a) Gnani drops the stream 3 s into the call: reconnect, keep transcript + score."""
    async def first(conn):
        async def drop(c):
            await asyncio.sleep(3)
            await c.hang_up(1011, "internal error")
        await healthy(conn, [KYC], then=drop)

    async def second(conn):
        await healthy(conn, [OTP])

    run = Run([first, second])
    t0 = time.monotonic()
    b = await run.go(lambda b: has_line(b, OTP))
    assert time.monotonic() - t0 >= 3, "the first stream should have lasted until Gnani dropped it"
    assert len(run.headers) == 2, "should have reconnected once"
    states = [m.get("state") for m in b.of("status")]
    assert "reconnecting" in states and states[-1] == "listening", states
    assert has_line(b, KYC) and has_line(b, OTP)
    assert last_level(b) == "danger", "score from before the drop must carry over"
    assert [a["level"] for a in b.of("alert")] == ["caution", "danger"]
    assert not b.of("ended"), "the user stopped the call, the server must not end it"


async def case_b_1008_fallback():
    """(b) Gnani rejects the settings (1008): retry with simpler settings, then work."""
    async def reject(conn):
        await conn.say({"type": "error", "message": "unsupported format"})
        await conn.hang_up(1008, "policy violation")

    run = Run([reject, lambda c: healthy(c, [KYC])], FakeBrowser({"type": "start", "language": "hi-IN,en-IN"}))
    b = await run.go(lambda b: has_line(b, KYC))
    assert run.headers[0]["language_code"] == "hi-IN,en-IN"
    assert run.headers[1]["language_code"] == "hi-IN", "level 1 must use a single language"
    assert b.of("notice"), "user should be told settings were simplified"
    assert last_level(b) == "caution"


async def case_b_1008_always():
    """(b) Gnani rejects every setting level: end the session with a clear reason, no hang."""
    async def reject(conn):
        await conn.hang_up(1008, "policy violation")

    run = Run([reject])
    b = await run.go(lambda b: False, stop=False)
    assert len(run.headers) == len(server.FALLBACK_LEVELS)
    assert "rejected" in ended_reason(b), ended_reason(b)


async def case_c_malformed_json():
    """(c) Gnani sends garbage: ignore it, keep transcribing."""
    async def garbage(conn):
        await conn.say({"type": "connected"})
        await conn.say("{not json")
        await conn.say("[1, 2, 3]")
        await conn.say(json.dumps({"type": "transcript", "text": None}))
        await conn.say(transcript(KYC))
        await forever()

    run = Run([garbage])
    b = await run.go(lambda b: has_line(b, KYC))
    assert len(run.headers) == 1, "garbage must not cause a reconnect"
    assert last_level(b) == "caution"


async def case_d_never_answers():
    """(d) Gnani accepts the connection but never says anything: replace the stream."""
    async def silent(conn):
        await forever()

    run = Run([silent, lambda c: healthy(c, [KYC])])
    b = await run.go(lambda b: has_line(b, KYC))
    assert len(run.headers) == 2
    assert any(m.get("state") == "reconnecting" for m in b.of("status"))


async def case_d_connect_hangs():
    """(d) The connection itself never completes: retry with backoff, then tell the user."""
    run = Run(["hang"])
    b = await run.go(lambda b: False, stop=False)
    assert len(run.headers) == 6, f"expected first try + 5 retries, got {len(run.headers)}"
    attempts = [m["attempt"] for m in b.of("status") if m.get("state") == "reconnecting"]
    assert attempts == [1, 2, 3, 4, 5], attempts
    assert "keeps dropping" in ended_reason(b), ended_reason(b)


async def case_d_goes_silent_mid_call():
    """(d) Gnani stops answering mid-call while speech keeps going in: reconnect."""
    async def stalls(conn):
        await conn.say({"type": "connected"})
        await conn.say(transcript(KYC))
        await forever()

    run = Run([stalls, lambda c: healthy(c, [OTP])])
    b = await run.go(lambda b: has_line(b, OTP))
    assert len(run.headers) == 2
    assert last_level(b) == "danger"


async def case_e_empty_transcript():
    """(e) Gnani sends an empty transcript: show "couldn't make out", carry on."""
    async def empty(conn):
        await conn.say({"type": "connected"})
        await conn.say(transcript(""))
        await conn.say(transcript("   "))
        await conn.say(transcript(KYC))
        await forever()

    run = Run([empty])
    b = await run.go(lambda b: has_line(b, KYC))
    assert len(b.of("unclear")) == 2
    assert last_level(b) == "caution"


async def case_handler_crash():
    """A bug in transcript handling (detector, Evon...) must not end the call."""
    run = Run([lambda c: healthy(c, ["first line", KYC])])
    original = server.CallRisk.add_segment
    calls = {"n": 0}

    def flaky(self, text):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return original(self, text)

    server.CallRisk.add_segment = flaky
    real_tb = server.traceback.print_exc
    server.traceback.print_exc = lambda *a, **k: None  # the crash is on purpose: keep output clean
    try:
        b = await run.go(lambda b: has_line(b, KYC))
    finally:
        server.CallRisk.add_segment = original
        server.traceback.print_exc = real_tb
    assert last_level(b) == "caution"
    assert len(run.headers) == 1


async def case_send_fails():
    """Sending audio to Gnani fails (network blip): reconnect instead of going quiet."""
    async def breaks(conn):
        await conn.say({"type": "connected"})
        await asyncio.sleep(0.3)
        conn.fail_send = True
        await forever()

    run = Run([breaks, lambda c: healthy(c, [KYC])])
    b = await run.go(lambda b: has_line(b, KYC))
    assert len(run.headers) == 2


async def case_bad_key():
    """HTTP 401 from Gnani: no pointless retries, tell the user to check the key."""
    class Refused(Exception):
        def __init__(self):
            super().__init__("server rejected WebSocket connection: HTTP 401")
            self.response = type("R", (), {"status_code": 401})()

    run = Run([Refused()])
    b = await run.go(lambda b: False, stop=False)
    assert len(run.headers) == 1
    assert "GNANI_API_KEY" in ended_reason(b)


async def case_heartbeat():
    """The server pings the page every few seconds so the page can spot a dead connection."""
    run = Run([lambda c: healthy(c)])
    b = await run.go(lambda b: len(b.of("ping")) >= 3)
    assert len(b.of("ping")) >= 3


async def case_resume_after_page_reconnect():
    """The page reconnects mid-call and sends what it had: score and alerts carry on."""
    start = {"type": "start", "language": "indic-auto",
             "resume": {"lines": [KYC], "langs": {"hi": 1}, "alerted": "caution", "elapsed": 42.0}}
    run = Run([lambda c: healthy(c, [OTP])], FakeBrowser(start))
    b = await run.go(lambda b: has_line(b, OTP))
    assert b.of("risk")[0]["level"] == "caution", "state must be restored before new speech"
    assert last_level(b) == "danger"
    assert [a["level"] for a in b.of("alert")] == ["danger"], "caution was already given, don't repeat it"
    assert b.of("transcript")[-1]["t"] >= 42, "call clock must continue"


async def case_framing_never_drifts():
    """Odd-sized audio chunks from the page still reach Gnani as exact 1024-byte frames."""
    run = Run([lambda c: healthy(c)])
    chunks = [LOUD[:700], LOUD[:333], LOUD[:1000], LOUD[:1]]  # includes odd lengths
    b = run.browser

    async def odd_feed():
        for _ in range(40):
            for c in chunks:
                b.audio(c)
            await asyncio.sleep(0.005)

    # 333 and 1 are odd: one byte dropped from each, so samples stay aligned
    expected = 40 * (700 + 332 + 1000 + 0) // 1024
    feeder = asyncio.ensure_future(odd_feed())
    await run.go(lambda b: feeder.done() and run.streams and len(run.streams[0].frames) >= expected, audio=b"")
    frames = run.streams[0].frames
    assert len(frames) == expected and all(len(f) == 1024 for f in frames), (len(frames), expected)


async def case_queue_full_counted():
    """If Gnani stops taking audio and the queue fills, dropped frames are counted (and logged)."""
    async def stuck(conn):
        async def never_returns(frame):
            await forever()
        conn.send = never_returns  # Gnani accepts nothing
        await conn.say({"type": "connected"})
        await forever()

    sessions = []
    real_init = server.CallSession.__init__

    def spy(self, ws):
        real_init(self, ws)
        sessions.append(self)

    server.CallSession.__init__ = spy
    run = Run([stuck])
    try:
        for _ in range(400):  # 400 frames at once, the queue holds 300
            run.browser.audio(LOUD)
        await run.go(lambda b: sessions and sessions[0].dropped_frames >= 50, audio=b"")
    finally:
        server.CallSession.__init__ = real_init
    assert sessions[0].dropped_frames >= 50


async def case_tts_fallbacks():
    """Spoken warning: retry once, then the English warning, then a clear 502 for the page."""
    from fastapi import HTTPException

    real = gnani_tts.synthesize
    tries: list[str] = []

    async def hindi_down(text, lang, key):
        tries.append(lang)
        if lang != "en":
            raise RuntimeError("TTS failed (HTTP 503)")
        return b"RIFF-english"

    async def all_down(text, lang, key):
        tries.append(lang)
        await asyncio.sleep(10)  # hangs: the timeout must cut it off

    server.print = lambda *a, **k: None
    gnani_tts.synthesize = hindi_down
    old_timeout = server.TTS_TIMEOUT_S
    try:
        r = await server.speak(server.SpeakRequest(lang="hi", level="danger"))
        assert r.body == b"RIFF-english" and r.headers["x-kavach-voice"] == "english-fallback"
        assert tries == ["hi", "hi", "en"], tries

        tries.clear()
        gnani_tts.synthesize = all_down
        server.TTS_TIMEOUT_S = 0.1
        t0 = time.monotonic()
        try:
            await server.speak(server.SpeakRequest(lang="te", level="caution"))
            raise AssertionError("expected a 502")
        except HTTPException as e:
            assert e.status_code == 502
        assert time.monotonic() - t0 < 1.0, "a hanging TTS must not hold the warning"
        assert tries == ["te", "te", "en"]
    finally:
        gnani_tts.synthesize = real
        server.TTS_TIMEOUT_S = old_timeout


async def case_server_shutdown_lets_page_reconnect():
    """Server restarting (session cancelled): no "ended" message, so the page reconnects instead of giving up."""
    run = Run([lambda c: healthy(c)])
    server.open_stt = run.open_stt
    b = run.browser
    session = asyncio.ensure_future(server.call_socket(b))
    for _ in range(50):
        if b.of("status"):
            break
        await asyncio.sleep(0.02)
    session.cancel()
    await asyncio.gather(session, return_exceptions=True)
    for s_ in run.streams:
        s_.task.cancel()
    assert b.of("status"), "session never started"
    assert not b.of("ended"), "a shutting-down server must not tell the page to give up"


CASES = [
    case_a_closes_after_3s, case_b_1008_fallback, case_b_1008_always, case_c_malformed_json,
    case_d_never_answers, case_d_connect_hangs, case_d_goes_silent_mid_call, case_e_empty_transcript,
    case_handler_crash, case_send_fails, case_bad_key, case_heartbeat, case_resume_after_page_reconnect,
    case_framing_never_drifts, case_queue_full_counted, case_tts_fallbacks,
    case_server_shutdown_lets_page_reconnect,
]


async def main() -> int:
    failed = 0
    for case in CASES:
        t0 = time.monotonic()
        try:
            await asyncio.wait_for(case(), 20)
            print(f"PASS  {case.__name__:38s} {time.monotonic() - t0:4.1f}s  {case.__doc__.strip().splitlines()[0]}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {case.__name__:38s} {type(e).__name__}: {e}")
    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
