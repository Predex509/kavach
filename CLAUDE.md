# Kavach — project notes for Claude Code

Live scam-call detector for the Great Indian AI Internship Challenge (Gnani AI).
Hard deadline: Nov 10, 2026, 11:59 PM IST. Team target: submit by 8 PM.
Keep changes small and working. No rewrites, no new frameworks.

## How it works
- `server.py` (FastAPI): browser sends 16 kHz mono PCM over `/ws`; server forwards exact
  1024-byte frames to Gnani Prisma v3.0 streaming STT (`wss://api.vachana.ai/stt/v3/stream`,
  headers: x-api-key-id, model=prisma-v3.0, language_code, format=codemix, keyterms, topic, VAD).
- `detector.py`: regex pattern engine, 10 red-flag categories in Latin + Indic scripts, combo
  bonuses name the scam. Score 0-100; caution >= 35, danger >= 65. Indic patterns are substrings
  (Python `\b` breaks on combining marks); ASCII patterns get word boundaries automatically.
- `gnani_tts.py`: spoken warnings via Gnani Timbre (POST /api/v1/tts/inference, timbre-v3.0), cached in `.tts_cache/`.
- `evon.py`: optional Evon v3.3 via an OpenAI-compatible endpoint (EVON_BASE_URL). Off when unset.
- `static/index.html`: UI, AudioWorklet mic capture, "Play a test call" file mode.
- `make_demo_calls.py`: synthetic noisy 8 kHz calls with Timbre into `demo_calls/`.
- Gnani docs: https://docs.gnani.ai

## Commands
- Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Tests: `python test_detector.py` (must stay all-pass)
- Run: `uvicorn server:app --port 8000` then open http://localhost:8000 (mic needs localhost)
- Check which Prisma streaming settings Gnani accepts: `python stt_check.py`
- New demo calls only (skips existing): `python make_demo_calls.py`; noisy copy: `python make_demo_calls.py --noise 0.07 --out demo_calls_noisy`
- Experiment (keyterms on/off, writes eval_results.md): `python eval_calls.py --dirs demo_calls demo_calls_noisy`

## Known facts (Nov 8 tests)
- Gnani streaming rejects (close 1008) the two-language list `hi-IN,en-IN` and/or `format: codemix`.
  `language_code: indic-auto` works best; it is the UI default. server.py falls back automatically.
- Prisma writes English words in Latin script inside Indic sentences ("bank నుంచి", "KYC"), and
  sometimes in Indic script ("ओटीपी"). Detector patterns must cover both.
- Real-bank safety advice ("bank kabhi OTP nahi maangta") must stay safe: see _ADVICE/_REQUEST in detector.py.

## File ownership (two people, separate files)
- Aditya: server.py, evon.py, README.md, eval_calls.py
- Shri: detector.py, test_detector.py, gnani_tts.py, make_demo_calls.py, static/index.html
Only edit the files the current task names. Ask before touching the other person's files.

## Rules
- Never print, log or commit the contents of `.env` or any API key.
- `.gitignore` must include: .env, .venv/, .tts_cache/, __pycache__/
- Run `python test_detector.py` after any change to detector.py.
- Live API calls cost credits: test with files in demo_calls/ before live mic calls.
