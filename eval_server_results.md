# Kavach reliability run (through the server)

Language setting: `indic-auto`. Each call is streamed to the running server like the page does. A stall = more than 7 s with no message from the server (it pings every 5 s).

| Round | Call | Audio | Verdict | Danger at | Transcripts | Longest silence from server | Reconnects | Problems |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | normal_mom_hindi | demo_calls | safe 0 | never | 4 | 4.3 s | 0 |  |
| 1 | normal_real_bank_hinglish | demo_calls | safe 0 | never | 4 | 5.0 s | 0 |  |
| 1 | scam_digital_arrest_hindi | demo_calls | danger 100 | 15.4 | 4 | 5.0 s | 0 |  |
| 1 | scam_electricity_hinglish | demo_calls | danger 85 | 23.0 | 5 | 4.1 s | 0 |  |
| 1 | scam_kyc_anydesk_hinglish | demo_calls | danger 100 | 12.7 | 6 | 5.0 s | 0 |  |
| 1 | scam_kyc_telugu | demo_calls | danger 100 | 17.8 | 4 | 5.0 s | 0 |  |
| 1 | scam_olx_army_hindi | demo_calls | danger 100 | 19.5 | 3 | 5.0 s | 0 |  |
| 2 | normal_mom_hindi | demo_calls | safe 0 | never | 4 | 5.0 s | 0 |  |
| 2 | normal_real_bank_hinglish | demo_calls | safe 0 | never | 4 | 5.0 s | 0 |  |
| 2 | scam_digital_arrest_hindi | demo_calls | danger 100 | 15.4 | 4 | 5.0 s | 0 |  |
| 2 | scam_electricity_hinglish | demo_calls | danger 85 | 22.9 | 5 | 4.1 s | 0 |  |
| 2 | scam_kyc_anydesk_hinglish | demo_calls | danger 100 | 12.7 | 6 | 5.0 s | 0 |  |
| 2 | scam_kyc_telugu | demo_calls | danger 100 | 17.9 | 4 | 3.9 s | 0 |  |
| 2 | scam_olx_army_hindi | demo_calls | danger 100 | 19.5 | 3 | 5.0 s | 0 |  |
| 3 | normal_mom_hindi | demo_calls | safe 0 | never | 4 | 4.4 s | 0 |  |
| 3 | normal_real_bank_hinglish | demo_calls | safe 0 | never | 4 | 5.0 s | 0 |  |
| 3 | scam_digital_arrest_hindi | demo_calls | danger 100 | 15.4 | 4 | 5.0 s | 0 |  |
| 3 | scam_electricity_hinglish | demo_calls | danger 85 | 22.7 | 5 | 4.1 s | 0 |  |
| 3 | scam_kyc_anydesk_hinglish | demo_calls | danger 100 | 12.7 | 6 | 5.0 s | 0 |  |
| 3 | scam_kyc_telugu | demo_calls | danger 100 | 17.7 | 4 | 4.0 s | 0 |  |
| 3 | scam_olx_army_hindi | demo_calls | danger 100 | 19.6 | 3 | 5.0 s | 0 |  |

**21/21 runs correct with no stalls** (3 rounds, through ws://localhost:8000/ws)
