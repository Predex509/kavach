# Kavach (कवच) — a live scam-call shield for Indian families

**📄 One-page solution pitch: [PITCH.md](PITCH.md)** · **🎥 Demo video:** _link added at submission_

Put the phone on speaker. Kavach listens to the call, understands it in Hindi, Telugu, Tamil,
English or a mix, and the moment it hears a scam pattern it **speaks a warning out loud in the
caller's language**: *"सावधान! यह कॉल धोखाधड़ी लग रही है… अभी कॉल काट दीजिए।"*

Built for the Great Indian AI Internship Challenge on Gnani AI's models.

## Gnani AI technology used

| Model | How Kavach uses it |
|---|---|
| **Prisma v3.0** (streaming STT) | Real-time transcription of the call over WebSocket with automatic language detection (`indic-auto`), **keyterms** for scam vocabulary (AnyDesk, CBI, KYC, digital arrest…), a **topic** hint, and VAD tuned for speakerphone audio. Falls back to simpler settings automatically if Gnani rejects one. |
| **Timbre v3.0** (TTS) | Speaks the warning in the language the caller is using (7 languages), slightly slowed for elderly listeners. Also used to generate synthetic test calls. |
| **Evon v3.3** (optional) | Reads the running transcript and returns a risk score plus a one-line explanation in the caller's language, which Kavach also speaks aloud. |

## Run it (Mac / Linux)

```bash
cd scam-shield
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then paste your key from app.gnani.ai → API Keys
uvicorn server:app --port 8000
```

Open **http://localhost:8000** (the mic only works on localhost or https). Pick the call language,
press **Start listening**, and put a phone call on speaker next to the laptop.

### Test calls without a phone

```bash
python make_demo_calls.py               # writes demo_calls/*.wav (phone-quality, with line noise)
python make_demo_calls.py --noise 0.07  # a much noisier line
```

Then click **Play a test call** and pick a file. The call plays aloud and streams to Prisma at
real-time speed, exactly like a live call. Included: Hindi digital arrest, Hinglish KYC + AnyDesk,
Telugu KYC/OTP, Hinglish electricity cut-off, Hindi OLX army QR code, and two calls that must stay
green: a genuine bank fraud-team call and a call from mom.

### Detector tests (no API key needed)

```bash
python test_detector.py   # 30 cases: 16 scams, 14 normal calls
```

## How it works

```
mic / test call ──16 kHz PCM──▶ server.py ──1024-byte frames──▶ Prisma v3.0 (wss stream)
                                   │                                  │
                                   │◀──────── transcript + language ──┘
                                   ▼
                     detector.py: 10 red-flag categories in Latin + 7 Indic scripts
                     (OTP/PIN, remote-access apps, police/CBI threats, parcels, KYC/SIM
                     block, payment pressure, secrecy, urgency, prize lures, impersonation)
                     + combinations that name the scam (authority + secrecy = digital arrest)
                                   │            ╲
                                   │             ╲── evon.py (optional): risk + reason
                                   ▼
                  browser: risk light, red-flag evidence, transcript ── /api/speak ──▶ Timbre
```

* A red flag counts once per call; repeating it adds evidence, not score, so one stray word
  never triggers a scam alert. Normal calls that mention a bank or a money transfer stay safe.
* Alerts escalate once each: **caution** (score ≥ 35) then **danger** (≥ 65).
* Warnings are prefetched and cached, so the voice plays instantly when danger is detected.
* Prisma sessions cap at 15 minutes; the server reconnects automatically for long calls.

## Results (Nov 9, 2026)

Seven synthetic phone calls (8 kHz, made with Gnani Timbre, two voices): five scams and two normal calls,
in Hindi, Hinglish and Telugu. Each was streamed to Prisma v3.0 at real-time speed with automatic language
detection (`indic-auto`), on clean phone audio and on a noisier line (`--noise 0.07`), with keyterms on and
off. 28 runs in total. Full table and transcripts: `eval_results.md`. Reproduce with
`python eval_calls.py --dirs demo_calls demo_calls_noisy`.

| Call | Language | Verdict (clean / noisy) | Danger alert at (clean / noisy) |
| --- | --- | --- | --- |
| Digital arrest (fake crime branch, parcel, "don't tell anyone") | Hindi | danger 100 / danger 100 | 15.3 s / 15.7 s |
| KYC expiry + AnyDesk + OTP | Hinglish | danger 100 / danger 100 | 12.5 s / 11.7 s |
| KYC expiry + OTP | Telugu | danger 100 / danger 100 | 17.5 s / 17.9 s |
| Electricity disconnection + payment link | Hinglish | danger 85 / danger 85 | 22.6 s / 22.3 s |
| OLX "army officer" QR code + UPI PIN | Hindi | danger 100 / danger 100 | 19.5 s / 19.3 s |
| Genuine bank fraud team ("we never ask for your OTP") | Hinglish | safe 0 / safe 0 | never |
| Mother calling (mentions bank, passbook) | Hindi | safe 0 / safe 0 | never |

| Setting | Correct verdict | Scam words transcribed recognisably |
| --- | --- | --- |
| Keyterms + topic on | 14/14 | 32/32 |
| Keyterms + topic off | 14/14 | 30/32 |

What we learned:

- **No false alarms.** The genuine bank call mentions the bank, a card, OTP, PIN and "don't tell anyone",
  and stays safe because Kavach recognises safety advice ("bank kabhi OTP nahi maangta") unless the caller
  also asks for the code.
- **Keyterms fixed the most important word.** Without them Prisma heard "AnyDesk" as "एनी बेस्ट"
  ("any best") on both clean and noisy audio; with them it wrote "एनीडेस्क" both times. Verdicts were the
  same either way because other red flags (KYC, OTP) also fired, so keyterms are a safety margin, not the
  only line of defence. Keyterms are on in the app.
- **Fast.** Median transcription latency was 97–169 ms per sentence. Danger fires in the sentence where
  the scammer makes the ask (the OTP, the transfer, the payment link), 12–23 s into these calls.
- **Noise barely changed anything** at this level. The only shift: on the Telugu call the first caution
  came at 17.9 s instead of 10.4 s; danger still fired at the same point.
- **Prisma spells acronyms letter by letter** in Indic script on phone audio ("एस बी आई", "क्यू आर कोड",
  "यू पी आई"), and sometimes keeps English words in Latin script ("bank నుంచి"). The detector matches all
  of these forms.
- **Language setting matters.** Gnani's streaming API rejected a two-language hint (`hi-IN,en-IN`) and/or
  `format: codemix` (close code 1008), so Kavach uses `indic-auto`. Forcing Hindi on a Telugu call made
  Prisma output Hindi sentences and invent a line; auto-detect gave clean Telugu.

Limits of this test: synthetic voices, one run per setting, seven calls. Real calls with real callers on a
speakerphone are the next step.

## Optional: Evon v3.3

Evon is open-weight (`gnani/gnani-evon-v3.3-30B-A3B` on Hugging Face) and isn't part of the
hosted API credits. Serve it with any OpenAI-compatible server (vLLM, SGLang, llama.cpp,
LM Studio with a GGUF build; a 4-bit build needs roughly 20 GB+ of RAM) and set
`EVON_BASE_URL` in `.env`. Without it, Kavach runs on the pattern engine alone. It's worth asking
on the Gnani Discord whether participants can get hosted Evon access.

## Measuring it (for the write-up)

* **Time to flag:** the UI shows "Flagged Ns into the call" for each test call.
* **Does context help?** Run the test calls with `USE_CONTEXT=1` and `USE_CONTEXT=0` and compare
  how often scam words (AnyDesk, KYC, CBI) are transcribed correctly and how fast the alert fires,
  at `--noise 0.03` and `--noise 0.07`.

## Honest limitations

* The phone must be on speaker near the device; Kavach hears both sides mixed together.
* Pattern rules can be evaded by a scammer who avoids every keyword; Evon helps with that.
* It warns, it doesn't block. It's a second pair of ears, not a replacement for awareness.
* Audio is streamed to Gnani for transcription and isn't stored by Kavach.

Report fraud: National Cyber Crime Helpline **1930** · cybercrime.gov.in
