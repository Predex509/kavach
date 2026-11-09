"""Spoken warnings with Gnani Timbre (REST /api/v1/tts/inference). Results are cached on disk."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import httpx

TTS_URL = "https://api.vachana.ai/api/v1/tts/inference"
CACHE = Path(__file__).parent / ".tts_cache"
CACHE.mkdir(exist_ok=True)

# Timbre v3.0 voices speak all 10 languages. v2.5 is a fallback.
PRIMARY = {"model": "timbre-v3.0", "voice": os.getenv("TTS_VOICE", "Shivani")}
FALLBACK = {"model": "timbre-v2.5", "voice": "Nalini"}

# Short, calm, clear. Numbers/abbreviations are written as spoken words for TTS.
WARNINGS = {
    "danger": {
        "en": "Warning! This call looks like a scam. Do not share any OTP, PIN, or bank details, and do not send money. Please cut the call now.",
        "hi": "घबराइए मत। यह कॉल धोखा लग रहा है। ओ टी पी, पिन या पैसे किसी को मत दीजिए। अभी फ़ोन रख दीजिए।",
        "te": "కంగారు పడకండి. ఈ కాల్ మోసంలా ఉంది. ఓ టీ పీ, పిన్ ఎవరికీ చెప్పకండి, డబ్బులు పంపకండి. ఇప్పుడే ఫోన్ పెట్టేయండి.",
        "ta": "எச்சரிக்கை! இந்த அழைப்பு மோசடியாகத் தெரிகிறது. யாரிடமும் ஓடிபி, பின் அல்லது வங்கி விவரங்களைச் சொல்லாதீர்கள், பணம் அனுப்பாதீர்கள். உடனே அழைப்பைத் துண்டியுங்கள்.",
        "kn": "ಎಚ್ಚರಿಕೆ! ಈ ಕರೆ ವಂಚನೆಯಂತೆ ಕಾಣುತ್ತಿದೆ. ಯಾರಿಗೂ ಓಟಿಪಿ, ಪಿನ್ ಅಥವಾ ಬ್ಯಾಂಕ್ ವಿವರಗಳನ್ನು ಹೇಳಬೇಡಿ, ಹಣ ಕಳುಹಿಸಬೇಡಿ. ಈಗಲೇ ಕರೆ ಕಟ್ ಮಾಡಿ.",
        "bn": "সাবধান! এই কলটি প্রতারণা বলে মনে হচ্ছে। কাউকে ওটিপি, পিন বা ব্যাংকের তথ্য দেবেন না, টাকা পাঠাবেন না। এখনই কলটি কেটে দিন।",
        "mr": "सावधान! हा कॉल फसवणुकीचा वाटतो. कोणालाही ओ टी पी, पिन किंवा बँकेची माहिती देऊ नका, आणि पैसे पाठवू नका. आत्ताच कॉल कट करा.",
    },
    "caution": {
        "en": "Be careful. This call is asking about sensitive things. Never share an OTP or PIN on a call.",
        "hi": "ज़रा ध्यान दीजिए, यह कॉल कुछ निजी बातें पूछ रहा है। फ़ोन पर ओ टी पी या पिन कभी मत बताइए।",
        "te": "కొంచెం జాగ్రత్తగా ఉండండి. ఈ కాల్ వ్యక్తిగత విషయాలు అడుగుతోంది. ఫోన్‌లో ఓ టీ పీ, పిన్ ఎప్పుడూ చెప్పకండి.",
        "ta": "கவனமாக இருங்கள். இந்த அழைப்பு முக்கியமான தகவல்களைக் கேட்கிறது. தொலைபேசியில் ஒருபோதும் ஓடிபி அல்லது பின் சொல்லாதீர்கள்.",
        "kn": "ಎಚ್ಚರದಿಂದಿರಿ. ಈ ಕರೆ ಸೂಕ್ಷ್ಮ ವಿಷಯಗಳ ಬಗ್ಗೆ ಕೇಳುತ್ತಿದೆ. ಫೋನ್‌ನಲ್ಲಿ ಎಂದಿಗೂ ಓಟಿಪಿ ಅಥವಾ ಪಿನ್ ಹೇಳಬೇಡಿ.",
        "bn": "সতর্ক থাকুন। এই কলে সংবেদনশীল তথ্য চাওয়া হচ্ছে। ফোনে কখনও ওটিপি বা পিন বলবেন না।",
        "mr": "काळजी घ्या. हा कॉल संवेदनशील माहितीबद्दल विचारत आहे. फोनवर कधीही ओ टी पी किंवा पिन सांगू नका.",
    },
}


def warning_text(level: str, lang: str) -> str:
    table = WARNINGS.get(level, WARNINGS["danger"])
    return table.get(lang, table["en"])


async def synthesize(text: str, lang: str, api_key: str) -> bytes:
    """Return WAV bytes for `text`. Cached by (text, lang)."""
    key = hashlib.sha1(f"{lang}|{text}|{PRIMARY}".encode()).hexdigest()
    cached = CACHE / f"{key}.wav"
    if cached.exists():
        return cached.read_bytes()

    language = f"{lang}-IN" if len(lang) == 2 else lang
    last_error = None
    async with httpx.AsyncClient(timeout=30) as client:
        for cfg in (PRIMARY, FALLBACK):
            body = {
                "text": text,
                "model": cfg["model"],
                "voice": cfg["voice"],
                "language": language,
                "speed": 0.95,  # a touch slower for elderly listeners
                "audio_config": {
                    "sample_rate": 24000, "num_channels": 1, "sample_width": 2,
                    "encoding": "linear_pcm", "container": "wav",
                },
            }
            r = await client.post(TTS_URL, json=body, headers={"X-API-Key-ID": api_key})
            if r.status_code == 200 and r.content:
                cached.write_bytes(r.content)
                return r.content
            last_error = f"{cfg['model']}: HTTP {r.status_code} {r.text[:200]}"
    raise RuntimeError(f"TTS failed ({last_error})")
