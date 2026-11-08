"""
Optional reasoning layer with Gnani Evon v3.3.

Evon is open-weight (gnani/gnani-evon-v3.3-30B-A3B on Hugging Face). Serve it with any
OpenAI-compatible server (vLLM, SGLang, llama.cpp server, LM Studio) and set:

    EVON_BASE_URL=http://localhost:8000/v1
    EVON_MODEL=gnani-evon-v3.3          # whatever name your server exposes
    EVON_API_KEY=...                    # only if your server needs one

If EVON_BASE_URL is not set, Scam Shield runs on the pattern engine alone.
"""

from __future__ import annotations

import json
import os
import re

import httpx

BASE_URL = os.getenv("EVON_BASE_URL", "").rstrip("/")
MODEL = os.getenv("EVON_MODEL", "gnani-evon-v3.3")
API_KEY = os.getenv("EVON_API_KEY", "")

ENABLED = bool(BASE_URL)

SYSTEM = """You protect elderly people in India from phone scams.
You get a live transcript of a phone call (it may mix Hindi, English, Telugu or other Indian languages).
Common scams: digital arrest (fake police/CBI, parcel with drugs, "don't tell anyone, stay on video call"),
fake KYC / bank calls asking for OTP or PIN, remote-access apps (AnyDesk), lottery / refund / prize,
job or investment schemes, electricity disconnection threats.
A normal call (family, friends, deliveries, a real bank telling you NOT to share OTP) is not a scam.

Reply with ONLY a JSON object, no other text:
{"risk": <integer 0-100>, "scam_type": "<short name or none>",
 "reason": "<one short sentence, max 20 words, in the SAME language as the caller, explaining the red flag to an elderly person>"}"""


def _extract_json(text: str) -> dict | None:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        data["risk"] = max(0, min(100, int(data.get("risk", 0))))
        return data
    except (ValueError, TypeError):
        return None


async def assess(transcript: str) -> dict | None:
    """Ask Evon to judge the call so far. Returns {"risk", "scam_type", "reason"} or None."""
    if not ENABLED:
        return None
    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Call transcript so far:\n{transcript[-3000:]}"},
        ],
        "temperature": 0.1,
        "max_tokens": 200,
        "chat_template_kwargs": {"enable_thinking": False},  # Evon supports disabling reasoning traces
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(f"{BASE_URL}/chat/completions", json=body, headers=headers)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"] or ""
            return _extract_json(content)
    except Exception as e:  # never let the optional layer break the live call
        print(f"[evon] skipped: {e}")
        return None
