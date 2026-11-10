# Kavach (कवच): a live scam-call shield for Indian families

**Team:** Aditya Raj and Shri · **Built on:** Gnani AI Prisma v3.0 (speech to text) + Timbre v3.0 (text to speech)

## Problem
Digital-arrest, fake-KYC and OTP scams reach people on an ordinary phone call, in their own language and
often in code-mixed Hinglish. Elderly people are targeted most, and by the time the family finds out, the
money is gone. Warnings on TV and SMS don't help in the moment a scammer is talking.

## Solution
Put the call on speaker. **Kavach listens to the call live, recognises scam patterns, explains why it is
worried, and speaks a warning out loud in the caller's language**, with a one-tap **Call 1930** (National
Cyber Crime Helpline) button. Normal calls, even ones that mention the bank or an OTP, stay green.

## How it works
Browser mic (16 kHz) → FastAPI server → **Prisma v3.0 streaming** (automatic language detection,
**keyterms** for scam vocabulary such as AnyDesk, KYC, CBI, plus a topic hint) → rule-based detector →
risk score and spoken warning via **Timbre v3.0**.

- **Detector:** 10 red-flag categories (OTP/PIN request, remote-access apps, police/CBI threats, parcels,
  KYC/SIM block, payment pressure, secrecy, urgency, prize lures, impersonation), matched in Latin script
  and in Hindi, Telugu, Tamil, Kannada, Bengali and Marathi scripts. Combinations name the scam: a police
  threat plus "don't tell anyone" is a digital-arrest scam.
- **No false alarms on safety advice:** "the bank never asks for your OTP" is recognised as advice unless
  the caller also asks for the code.
- **Built for real calls:** echo cancellation and a filter so Kavach never scores its own warning,
  automatic reconnection, heartbeats, and a fallback chain so a warning is always spoken.

## Results
| Measure | Result |
| --- | --- |
| Correct verdicts, 7 calls (5 scams, 2 normal) on clean and noisy phone audio | **28/28** |
| Same calls streamed through the live server, 3 rounds | **21/21** |
| Detector tests / reliability tests | **40/40 / 17/17** |
| Transcription time per sentence | **~100–170 ms** |
| Scam words heard with keyterms vs without | **32/32 vs 30/32** ("AnyDesk" was heard as "एनी बेस्ट" without them) |

## Limitations and next steps
The call must be on speakerphone near the device, and a very noisy room reduces accuracy. Next: an Android
app using call screening so no speakerphone is needed, alerting a family member when danger is detected,
and on-device processing for privacy.

## Who did what
**Aditya:** speech pipeline, Prisma and Timbre integration, live-mic reliability, keyterms experiment.
**Shri:** detection rules and tests, spoken-warning wording, Call 1930 and large-text accessibility, demo video.
