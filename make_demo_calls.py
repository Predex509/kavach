"""
Generate synthetic test calls with Gnani Timbre: two voices, 8 kHz phone-quality audio, line noise.

    python make_demo_calls.py                                   # new calls only, default noise
    python make_demo_calls.py --noise 0.07 --out demo_calls_noisy  # a much noisier copy of every call
    python make_demo_calls.py --only scam_olx_army_hindi --force   # remake one call

Writes WAV files to ./demo_calls/ (or --out). Use them with "Play a test call" in the app.
Calls that already exist are skipped. The clean voice audio is cached in demo_calls/clean/,
so making a noisier copy later costs no extra TTS credits.
"""

from __future__ import annotations

import argparse
import os
import random
import struct
import wave
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GNANI_API_KEY", "")
URL = "https://api.vachana.ai/api/v1/tts/inference"
RATE = 8000  # narrowband telephone audio
CALLER, VICTIM = "Avinash", "Lakshmi"  # Timbre v3.0 voices (each speaks all supported languages)

CALLS = {
    "scam_digital_arrest_hindi": ("hi-IN", [
        (CALLER, "नमस्ते, मैं मुंबई क्राइम ब्रांच से इंस्पेक्टर राठौड़ बोल रहा हूँ।"),
        (VICTIM, "जी, बोलिए, क्या हुआ?"),
        (CALLER, "आपके आधार कार्ड से एक पार्सल बुक हुआ है, जिसमें ड्रग्स मिले हैं। आपके नाम पर मनी लॉन्ड्रिंग का केस है।"),
        (VICTIM, "क्या? मैंने तो कोई पार्सल नहीं भेजा।"),
        (CALLER, "अब आप डिजिटल अरेस्ट में हैं। यह बात किसी को मत बताइए, और कॉल मत काटिए।"),
        (CALLER, "जाँच के लिए आपको अपने पैसे एक सेफ अकाउंट में ट्रांसफर करने होंगे।"),
    ]),
    "scam_kyc_anydesk_hinglish": ("hi-en", [
        (CALLER, "Hello sir, main SBI customer care se bol raha hoon."),
        (VICTIM, "Haan ji, boliye."),
        (CALLER, "Sir aapka KYC aaj expire ho raha hai, aapka account block ho jayega."),
        (VICTIM, "Arre, ab kya karna hoga?"),
        (CALLER, "Aap Play Store se AnyDesk app download kijiye, main aapki madad karta hoon."),
        (CALLER, "Ab aapke phone par jo OTP aaya hai, woh mujhe bata dijiye."),
    ]),
    "scam_kyc_telugu": ("te-IN", [
        (CALLER, "నమస్తే సార్, నేను మీ బ్యాంక్ నుంచి మాట్లాడుతున్నాను."),
        (VICTIM, "చెప్పండి."),
        (CALLER, "మీ కేవైసీ ఈరోజు ఎక్స్‌పైర్ అవుతుంది, మీ అకౌంట్ బ్లాక్ అవుతుంది."),
        (VICTIM, "అయ్యో, ఇప్పుడు ఏం చేయాలి?"),
        (CALLER, "ఇప్పుడే మీ ఫోన్‌కి ఒక ఓటీపీ వచ్చింది, అది నాకు చెప్పండి."),
    ]),
    "scam_electricity_hinglish": ("hi-en", [
        (CALLER, "Namaste, main bijli vibhag se bol raha hoon."),
        (VICTIM, "Haan ji, boliye."),
        (CALLER, "Aapka pichhle mahine ka bill update nahi hua hai, aaj raat nau baje aapka bijli connection cut ho jayega."),
        (VICTIM, "Lekin maine toh bill bhar diya tha."),
        (CALLER, "Abhi turant main ek link bhej raha hoon, us link par click karke das rupaye ka payment kijiye."),
    ]),
    "scam_olx_army_hindi": ("hi-IN", [
        (CALLER, "नमस्ते, मैं आर्मी में हूँ, आपका सोफ़ा खरीदना चाहता हूँ।"),
        (VICTIM, "जी, सोफ़ा अभी भी है।"),
        (CALLER, "मैं अभी आपको एक क्यूआर कोड भेज रहा हूँ, पेमेंट मैं एडवांस में कर देता हूँ।"),
        (CALLER, "बस क्यूआर कोड स्कैन करके अपना यूपीआई पिन डाल दीजिए, पैसे आपके खाते में आ जाएँगे।"),
    ]),
    # A genuine bank call. It mentions the bank, a card, OTP and "don't tell anyone",
    # but as safety advice. Kavach must keep this one GREEN.
    "normal_real_bank_hinglish": ("hi-en", [
        (CALLER, "Namaste, main HDFC bank ki fraud team se bol raha hoon."),
        (VICTIM, "Ji, kya hua?"),
        (CALLER, "Aapke card par aaj ek transaction hua hai, kya woh aapne kiya tha?"),
        (VICTIM, "Haan, woh maine hi kiya tha."),
        (CALLER, "Theek hai. Yaad rakhiye, bank kabhi bhi aapka OTP ya PIN nahi maangta, kisi ko bhi mat bataiye."),
    ]),
    "normal_mom_hindi": ("hi-IN", [
        (VICTIM, "हाँ बेटा, खाना खाया?"),
        (CALLER, "हाँ माँ, अभी खाया। आप बताइए?"),
        (VICTIM, "आज मैं बैंक गई थी, पासबुक अपडेट करवाई। शाम को आते समय सब्ज़ी ले आना।"),
        (CALLER, "ठीक है माँ, सात बजे तक आ जाऊँगा।"),
    ]),
}


def tts(text: str, voice: str, language: str) -> bytes:
    r = httpx.post(URL, timeout=60, headers={"X-API-Key-ID": API_KEY}, json={
        "text": text, "model": "timbre-v3.0", "voice": voice, "language": language,
        "audio_config": {"sample_rate": RATE, "num_channels": 1, "sample_width": 2,
                         "encoding": "linear_pcm", "container": "raw"},
    })
    if r.status_code != 200:
        raise SystemExit(f"TTS failed ({r.status_code}): {r.text[:300]}")
    return r.content


def to_phone_line(pcm: bytes, noise: float, rng: random.Random) -> list[int]:
    """Add hiss, occasional crackle and a little level drift, like a cheap phone line."""
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm[: len(pcm) // 2 * 2])
    out, gain = [], rng.uniform(0.7, 1.0)
    for i, s in enumerate(samples):
        if i % 800 == 0:
            gain = min(1.0, max(0.55, gain + rng.uniform(-0.08, 0.08)))
        v = s * gain + rng.gauss(0, noise * 32767)
        if rng.random() < 0.0004:  # crackle
            v += rng.choice((-1, 1)) * rng.uniform(0.2, 0.5) * 32767
        out.append(int(max(-32768, min(32767, v))))
    return out


def silence(seconds: float) -> bytes:
    return b"\x00\x00" * int(RATE * seconds)


def clean_audio(name: str, language: str, turns: list, rng: random.Random, clean_dir: Path) -> bytes:
    """The call without line noise. Cached so noisier copies don't cost extra TTS credits."""
    cached = clean_dir / f"{name}.wav"
    if cached.exists():
        with wave.open(str(cached), "rb") as w:
            return w.readframes(w.getnframes())
    audio = bytearray(silence(0.8))
    for speaker, text in turns:
        print(f"  {name}: {speaker}: {text[:50]}")
        audio += tts(text, speaker, language) + silence(rng.uniform(0.5, 0.9))
    audio += silence(1.0)
    with wave.open(str(cached), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(audio))
    return bytes(audio)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--noise", type=float, default=0.03, help="hiss level, 0 = clean, 0.08 = very noisy")
    ap.add_argument("--out", default="demo_calls", help="output folder (default demo_calls)")
    ap.add_argument("--only", nargs="*", help="only these call names")
    ap.add_argument("--force", action="store_true", help="remake calls that already exist")
    args = ap.parse_args()
    if not API_KEY:
        raise SystemExit("Put GNANI_API_KEY in .env first.")

    here = Path(__file__).parent
    out_dir = here / args.out
    out_dir.mkdir(exist_ok=True)
    clean_dir = here / "demo_calls" / "clean"
    clean_dir.mkdir(parents=True, exist_ok=True)

    for name, (language, turns) in CALLS.items():
        if args.only and name not in args.only:
            continue
        path = out_dir / f"{name}.wav"
        if path.exists() and not args.force:
            print(f"skip {path.name} (exists; use --force to remake)")
            continue
        if args.force and (clean_dir / f"{name}.wav").exists() and args.out == "demo_calls":
            (clean_dir / f"{name}.wav").unlink()
        rng = random.Random(name)  # same pauses and noise pattern for a call every time
        audio = clean_audio(name, language, turns, rng, clean_dir)
        noisy = to_phone_line(audio, args.noise, rng)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(struct.pack(f"<{len(noisy)}h", *noisy))
        print(f"wrote {path}  ({len(noisy) / RATE:.1f}s)")


if __name__ == "__main__":
    main()
