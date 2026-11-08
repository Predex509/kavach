"""Run: python test_detector.py  — checks the pattern engine on sample calls.

Expected levels:  "danger" = must reach danger,  "alert" = caution or danger is fine,
                  "safe"   = must stay safe (a false alarm here is a bug).
Segments look like Prisma v3.0 output: Indic script, with English words often in Latin script.
"""

from detector import CallRisk

SCAMS = [
    ("Digital arrest (Hindi)", "danger", [
        "नमस्ते, मैं मुंबई क्राइम ब्रांच से इंस्पेक्टर राठौड़ बोल रहा हूँ।",
        "आपके आधार कार्ड से एक पार्सल बुक हुआ है जिसमें ड्रग्स मिले हैं।",
        "आप अभी digital arrest में हैं, यह बात किसी को मत बताइए और कॉल मत काटिए।",
    ]),
    ("Digital arrest (real Prisma output, Nov 8)", "danger", [
        "नमस्ते, मैं मुंबई crime branch से inspector राठौड़ बोल रहा हूँ।",
        "आपके आधार कार्ड से एक पार्सल बुक हुआ है जिसमें drugs मिले हैं, आपके नाम पर money laundering का case है।",
        "अब आप digital arrest में हैं, यह बात किसी को मत बताइए और call मत काटिए।",
        "जाँच के लिए आपको अपने पैसे एक safe account में transfer करने होंगे।",
    ]),
    ("Digital arrest (English)", "danger", [
        "This is Officer Sharma from the CBI cyber crime unit.",
        "A FedEx parcel in your name contains drugs and fake passports.",
        "You are under digital arrest. Do not disconnect the call and don't tell anyone.",
    ]),
    ("Digital arrest (Telugu)", "danger", [
        "నేను సీబీఐ ఆఫీసర్ ని మాట్లాడుతున్నాను.",
        "మీ పేరు మీద డ్రగ్స్ ఉన్న పార్సెల్ దొరికింది.",
        "ఈ విషయం ఎవరికీ చెప్పకండి, కాల్ కట్ చేయకండి.",
    ]),
    ("KYC + AnyDesk (Hinglish Latin)", "danger", [
        "Hello sir main SBI customer care se bol raha hoon",
        "aapka KYC aaj expire ho raha hai, account block ho jayega",
        "aap Play Store se AnyDesk download kijiye",
        "ab jo OTP aaya hai woh bata dijiye",
    ]),
    ("KYC + AnyDesk (real Prisma output, Nov 8)", "danger", [
        "Hello sir, मैं SBI customer care से बोल रहा हूँ।",
        "सर, आपका KYC आज expire हो रहा है, आपका account block हो जाएगा।",
        "आप Play Store से AnyDesk app download कीजिए, मैं आपकी मदद करता हूँ।",
        "अब आपके फोन पर जो ओटीपी आया है वो मुझे बता दीजिए।",
    ]),
    ("KYC + OTP (Telugu)", "danger", [
        "నమస్తే సార్, నేను మీ బ్యాంక్ నుంచి మాట్లాడుతున్నాను",
        "మీ కేవైసీ ఈరోజు expire అవుతుంది, మీ అకౌంట్ బ్లాక్ అవుతుంది",
        "ఇప్పుడే మీ ఫోన్‌కి ఒక ఓటీపీ వచ్చింది, అది చెప్పండి",
    ]),
    ("KYC + OTP (Telugu, real Prisma output, Nov 8)", "danger", [
        "నమస్తే sir, నేను మీ bank నుంచి మాట్లాడుతున్నాను.",
        "మీ KYC ఈరోజు expire అవుతుంది, మీ account block అవుతుంది.",
        "ఇప్పుడే మీ ఫోన్‌కి ఒక OTP వచ్చింది, అది నాకు చెప్పండి.",
    ]),
    ("Lottery (English)", "danger", [
        "Congratulations, you have won the KBC lucky draw of 25 lakh rupees",
        "to claim the prize please pay the processing fee by UPI immediately",
    ]),
    ("Lottery (Telugu)", "danger", [
        "మీరు లాటరీ గెలుచుకున్నారు.",
        "పది వేల రూపాయలు ప్రాసెసింగ్ ఫీజు కట్టండి.",
    ]),
    ("OLX army officer QR (Hinglish)", "danger", [
        "Main army mein hoon, aapka sofa kharidna hai.",
        "Main QR code bhej raha hoon, scan karke apna UPI PIN daaliye, paise aapke account mein aa jayenge.",
    ]),
    ("Part-time task job (Hinglish)", "danger", [
        "Part time job hai, YouTube videos like karo aur roz 5000 kamao.",
        "Pehle 2000 ka task deposit karna hoga, phir paisa double.",
    ]),
    ("Relative in trouble (Hinglish)", "danger", [
        "Papa main police station mein hoon, bahut problem ho gayi hai.",
        "Jaldi 50000 is number pe bhej do, mummy ko mat batana.",
    ]),
    ("Credit card reward points (English)", "danger", [
        "Your credit card reward points will expire today.",
        "Please share the OTP you received to redeem them.",
    ]),
    ("Electricity cut (Hinglish)", "alert", [
        "Aapka bijli connection aaj raat 9:30 baje cut ho jayega.",
        "Pichhle mahine ka bill update nahi hua hai, abhi turant is link par click karke payment kijiye.",
    ]),
    ("Electricity cut (Hindi)", "alert", [
        "आपका बिजली का कनेक्शन आज रात काट दिया जाएगा।",
        "तुरंत इस नंबर पर कॉल करें।",
    ]),
]

NORMAL = [
    ("Normal: mom calling (Hindi)", [
        "हाँ बेटा, खाना खाया?",
        "आज मैं बैंक गई थी, पासबुक अपडेट करवाई",
        "शाम को आते समय सब्ज़ी ले आना, और पापा का pin code वाला form भी",
    ]),
    ("Normal: mom calling (real Prisma output, Nov 8)", [
        "हाँ बेटा, खाना खाया?",
        "हाँ माँ, अभी खाया। आप बताइए?",
        "आज मैं बैंक गई हूँ, passbook update करवाऊँ। शाम को आते समय सब्जी ले आऊँ।",
        "ठीक है माँ, 7 बजे तक आ जाऊँगा।",
    ]),
    ("Normal: friend (Hinglish)", [
        "bhai kal match dekhne chal raha hai kya",
        "maine tujhe paise transfer kar diye the, mil gaye?",
        "haan theek hai, kal milte hain",
    ]),
    ("Normal: delivery (English)", [
        "Hi, I am outside your building with the delivery",
        "can you come down to the gate please",
    ]),
    ("Normal: real bank fraud team (Hinglish)", [
        "Namaste, main HDFC bank fraud team se bol raha hoon.",
        "Hum kabhi bhi aapka OTP ya PIN nahi maangte. Kisi ko bhi OTP mat bataiye.",
    ]),
    ("Normal: real bank reminder (English)", [
        "This is a reminder from your bank.",
        "Never share your OTP, PIN or CVV with anyone, even if they claim to be from the bank.",
    ]),
    ("Normal: real bank (Hindi)", [
        "नमस्ते, यह आपके बैंक की ओर से एक सूचना है।",
        "बैंक कभी भी आपका ओटीपी या पिन नहीं माँगता, किसी को भी मत बताइए।",
    ]),
    ("Normal: delivery OTP (Hinglish)", [
        "Sir Amazon delivery hai, main gate pe khada hoon.",
        "Order ka OTP bata dijiye please.",
    ]),
    ("Normal: traffic police (Hinglish)", [
        "Bhaiya main traffic police se bol raha hoon.",
        "Aapki gaadi galat jagah parked hai, please aake hata lijiye.",
    ]),
    ("Normal: parcel arriving (English)", [
        "Your parcel is out for delivery and will arrive by 6 pm.",
    ]),
    ("Normal: doctor reminder (Hindi)", [
        "दवाई समय पर लेना, और कल डॉक्टर के पास चलेंगे।",
    ]),
    ("Normal: son coming home (Telugu)", [
        "అమ్మా, నేను ఇంటికి వస్తున్నాను.",
        "బ్యాంక్ పని అయిపోయింది, సాయంత్రం కలుద్దాం.",
    ]),
    ("Normal: electricity meter (Hinglish)", [
        "Bijli wale aaye the, meter reading le gaye.",
        "Is mahine ka bill kam aayega shayad.",
    ]),
    ("Normal: lottery joke (Hinglish)", [
        "Yaar maine lottery ka ticket liya hai, dekhte hain kya hota hai.",
    ]),
]

CASES = SCAMS + [(name, "safe", segs) for name, segs in NORMAL]

failures = 0
for name, expected, segments in CASES:
    call = CallRisk()
    flagged_at = None
    for i, seg in enumerate(segments, 1):
        call.add_segment(seg)
        if flagged_at is None and call.analyse()["level"] != "safe":
            flagged_at = i
    r = call.analyse()
    ok = (r["level"] == expected) or (expected == "alert" and r["level"] in ("caution", "danger"))
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name:48s} score={r['score']:3d} level={r['level']:7s}"
          f" type={r['scam_type_en']}"
          + (f"  (alert at segment {flagged_at}/{len(segments)})" if flagged_at and expected != "safe" else ""))
    if not ok:
        for reason in r["reasons"]:
            print(f"        - {reason['en']}: {reason['phrases']}")

print(f"\n{len(CASES) - failures}/{len(CASES)} passed  ({len(SCAMS)} scams, {len(NORMAL)} normal calls)")
raise SystemExit(failures)
