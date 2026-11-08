"""
Scam Shield - multilingual scam pattern engine.

Scores a live call transcript for scam risk. Works on Prisma v3.0 output,
which (with format=codemix) keeps English words like "OTP" or "KYC" in Latin
script and writes Hindi / Telugu / Tamil etc. in their native scripts. So every
category has patterns in Latin (English + romanised Hinglish) AND native scripts.

Design:
  * Each category fires once per call (repeats add evidence, not score).
  * Combinations of categories add a bonus and name the scam type,
    e.g. authority threat + secrecy  ->  "Digital arrest".
  * Score is 0-100.  >= CAUTION is "caution", >= DANGER is "danger".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CAUTION = 35
DANGER = 65

# ---------------------------------------------------------------------------
# Categories. Patterns are regexes. ASCII patterns are matched case-insensitively
# with word boundaries; native-script patterns are matched as substrings
# (Python's \b does not work reliably across Indic combining marks).
# ---------------------------------------------------------------------------

CATEGORIES: dict[str, dict] = {
    "credential": {
        "weight": 40,
        "en": "Asking for OTP / PIN / CVV",
        "hi": "OTP / PIN / CVV माँगना",
        "patterns": [
            r"o\.?\s?t\.?\s?p", r"one time password", r"cvv", r"atm pin", r"upi pin",
            r"pin(?! ?code)", r"password", r"card number", r"card ke (peeche|piche)",
            r"expiry date", r"net ?banking (id|password)",
            "ओटीपी", "ओ टी पी", "पिन(?! ?कोड)", "पासवर्ड", "सीवीवी", "सी वी वी", "कार्ड नंबर",
            "ఓటీపీ", "ఓటిపి", "పిన్", "పాస్‌వర్డ్", "పాస్వర్డ్", "సీవీవీ",
            "ஓடிபி", "ஓ டி பி", "பின் நம்பர்",
            "ಓಟಿಪಿ", "ಒಟಿಪಿ", "ಪಿನ್",
            "ওটিপি", "পিন",
        ],
    },
    "remote_access": {
        "weight": 35,
        "en": "Asking to install a remote-access app",
        "hi": "रिमोट ऐप (AnyDesk आदि) डाउनलोड कराना",
        "patterns": [
            r"any ?desk", r"team ?viewer", r"quick ?support", r"rust ?desk",
            r"screen ?shar(e|ing)", r"\.?apk", r"remote access", r"airdroid",
            "एनीडेस्क", "एनी डेस्क", "टीम व्यूअर", "स्क्रीन शेयर", "क्विक सपोर्ट", "रस्ट डेस्क",
            "ఎనీడెస్క్", "ఎనీ డెస్క్", "స్క్రీన్ షేర్",
            "எனிடெஸ்க்", "ಎನಿಡೆಸ್ಕ್", "এনিডেস্ক",
        ],
    },
    "authority_threat": {
        "weight": 30,
        "en": "Police / CBI / court threat",
        "hi": "पुलिस / CBI / गिरफ़्तारी की धमकी",
        "patterns": [
            r"digital arrest", r"arrest", r"warrant", r"\bcbi\b", r"crime branch",
            r"cyber (cell|crime|police)", r"police", r"customs", r"narcotics", r"\bncb\b",
            r"enforcement directorate", r"income tax", r"money laundering", r"\bfir\b",
            r"\bcourt\b", r"\bjail\b", r"\bdrugs?\b", r"illegal", r"\btrai\b", r"\brbi\b",
            "डिजिटल अरेस्ट", "अरेस्ट", "गिरफ्तार", "गिरफ़्तार", "वारंट", "सीबीआई", "सी बी आई", "एफ आई आर",
            "क्राइम ब्रांच", "पुलिस", "कस्टम", "नारकोटिक्स", "मनी लॉन्ड्रिंग",
            "मनी लांड्रिंग", "एफआईआर", "कोर्ट", "जेल", "ड्रग्स", "गैरकानूनी",
            "డిజిటల్ అరెస్ట్", "అరెస్ట్", "అరెస్టు", "వారెంట్", "సీబీఐ", "పోలీస్",
            "పోలీసు", "కస్టమ్స్", "మనీ లాండరింగ్", "కోర్టు", "జైలు", "డ్రగ్స్",
            "போலீஸ்", "கைது", "சிபிஐ", "ಪೊಲೀಸ್", "ಬಂಧನ", "ಅರೆಸ್ಟ್",
            "পুলিশ", "গ্রেফতার", "গ্রেপ্তার", "অ্যারেস্ট", "पोलीस", "अटक",
        ],
    },
    "parcel": {
        "weight": 15,
        "en": "Suspicious parcel / courier",
        "hi": "संदिग्ध पार्सल / कूरियर",
        "patterns": [
            r"parcel", r"courier", r"fed ?ex", r"\bdhl\b", r"package seized",
            "पार्सल", "कूरियर", "कुरियर", "फेडेक्स",
            "పార్సెల్", "పార్శిల్", "కొరియర్", "பார்சல்", "ಪಾರ್ಸೆಲ್", "পার্সেল",
        ],
    },
    "account_threat": {
        "weight": 25,
        "en": "Account / KYC / SIM block threat",
        "hi": "खाता / KYC / सिम बंद होने की धमकी",
        "patterns": [
            r"\bkyc\b", r"account (will be )?(block|band|freeze|suspend|close)",
            r"(block|band|freeze|suspend) ho (jayega|jaega|jaayega)",
            r"sim (card )?(block|band)", r"(electricity|bijli) (cut|kat|connection)",
            r"aadhaar (link|update|block)", r"pan (card )?(link|update|block)",
            "केवाईसी", "के वाई सी", "ब्लॉक", "खाता बंद", "अकाउंट बंद", "सिम बंद",
            r"(electricity|bijli|light) (ka |ki )?(connection|bill) (cut|kat|band|katega|update)",
            r"bill (update|pending) (nahi|not)", r"connection (cut|kat|disconnect)\w*",
            "बिजली कट", "बिजली का कनेक्शन", "कनेक्शन काट", "कनेक्शन कट", "बिल अपडेट",
            "కరెంట్ కట్", "కనెక్షన్ కట్", "బిల్ అప్‌డేట్",
            "కేవైసీ", "కేవైసి", "బ్లాక్", "అకౌంట్ క్లోజ్", "సిమ్ బ్లాక్",
            "கேஒய்சி", "முடக்க", "ಕೆವೈಸಿ", "ಬ್ಲಾಕ್", "কেওয়াইসি", "ব্লক",
        ],
    },
    "payment_pressure": {
        "weight": 30,
        "en": "Pressure to send money",
        "hi": "पैसे भेजने का दबाव",
        "patterns": [
            r"transfer", r"\bupi\b", r"qr ?code", r"scan (karo|kijiye|karein|this)",
            r"safe account", r"secure account", r"rbi account", r"verification (amount|fee|charge)",
            r"processing fee", r"registration fee", r"refundable", r"gift card",
            r"(google ?pay|phone ?pe|paytm) (karo|kijiye|kar do|kariye)",
            r"(paise|paisa|rupaye|amount) (bhejo|bhejiye|bhej do|transfer)",
            r"send (the )?money", r"pay (the )?(fine|penalty|fee)", r"penalty",
            r"deposit (karo|karna|kijiye|kar do|karein|karni)", r"pay(ment)? (karo|kijiye|kar do|kariye|karein)",
            r"(click|tap) (on )?(the |this |is )?link", r"link (pe|par) (click|jaake)",
            "लिंक पर क्लिक", "ఫీజు కట్టండి", "ఫీజు చెల్లించండి", "డబ్బులు కట్టండి", "లింక్ క్లిక్",
            "पैसे भेज", "पैसा भेज", "ट्रांसफर", "यूपीआई", "यू पी आई", "क्यूआर", "क्यू आर", "सेफ अकाउंट",
            "पेमेंट कीजिए", "पेमेंट करें", "पेमेंट कर दीजिए", "स्कैन कर", "यూ పీ ఐ", "క్యూ ఆర్",
            "जुर्माना", "फीस भर", "पेमेंट कर",
            "డబ్బు పంపండి", "డబ్బులు పంపండి", "ట్రాన్స్ఫర్", "ట్రాన్స్‌ఫర్", "యూపీఐ",
            "క్యూఆర్", "పేమెంట్ చేయండి", "జరిమానా",
            "பணம் அனுப்பு", "டிரான்ஸ்பர்", "ಹಣ ಕಳುಹಿಸಿ", "ಟ್ರಾನ್ಸ್‌ಫರ್",
            "টাকা পাঠান", "ট্রান্সফার", "पैसे पाठवा",
        ],
    },
    "secrecy": {
        "weight": 25,
        "en": "Telling you to keep it secret / stay on call",
        "hi": "किसी को न बताने / कॉल न काटने को कहना",
        "patterns": [
            r"(kisi|kissi) ko (bhi )?(mat|nahi|na) (batana|bataiye|batao|bataye|bataen)",
            r"(family|ghar|ghar wal\w*|bete|beti|mummy|mumm?y|papa|maa|mom|dad|wife|husband|biwi|pati) ko (bhi )?(mat|nahi|na) (batana|bataiye|batao)",
            "मम्मी को मत", "पापा को मत", "घर पर किसी को", "घरवालों को मत",
            r"(don'?t|do not) tell (anyone|anybody|your family)",
            r"(call|phone) (mat|na) (kaat|kat)\w*", r"(don'?t|do not) (disconnect|cut|hang up)",
            r"stay on (the )?(call|line|video)", r"video call (pe|par) (raho|rahiye|rahna)",
            r"confidential", r"\bsecret\b",
            "किसी को मत", "किसी को भी मत", "किसी को न बता", "किसी को नहीं बता",
            "कॉल मत काट", "फ़ोन मत काट", "फोन मत काट", "गोपनीय",
            "ఎవరికీ చెప్పకండి", "ఎవరికి చెప్పకండి", "ఎవరికీ చెప్పొద్దు", "కాల్ కట్ చేయకండి",
            "ఫోన్ కట్ చేయకండి", "రహస్యం",
            "யாரிடமும் சொல்லாதீர்கள்", "ಯಾರಿಗೂ ಹೇಳಬೇಡಿ", "কাউকে বলবেন না", "कोणालाही सांगू नका",
        ],
    },
    "urgency": {
        "weight": 10,
        "en": "Creating urgency",
        "hi": "जल्दबाज़ी का दबाव",
        "patterns": [
            r"immediately", r"urgent(ly)?", r"right now", r"abhi (ke abhi|turant)", r"turant",
            r"within (\w+ )?(minutes|hours)", r"last (warning|chance)", r"aaj hi", r"jaldi", r"aaj raat",
            r"today itself", "जल्दी", "आज रात",
            "तुरंत", "अभी के अभी", "फ़ौरन", "फौरन", "आख़िरी मौका", "आखिरी मौका",
            "వెంటనే", "ఇప్పుడే", "అర్జెంట్", "உடனே", "ತಕ್ಷಣ", "এখনই",
        ],
    },
    "lure": {
        "weight": 25,
        "en": "Prize / refund / easy-money lure",
        "hi": "इनाम / रिफंड / आसान कमाई का लालच",
        "patterns": [
            r"lottery", r"lucky draw", r"\bkbc\b", r"you (have )?won", r"prize",
            r"cash ?back", r"refund", r"part ?time (job|work)", r"work from home",
            r"(like|review|task)s? (and|&) earn", r"guaranteed (return|profit)",
            r"double (your|the) money", r"trading tips", r"investment (plan|scheme)",
            r"reward points?", r"youtube (videos? )?(like|subscribe)", r"(roz|daily|per day) \d+ (kamao|kamaiye|earn)",
            "रिवॉर्ड पॉइंट", "రివార్డ్ పాయింట్",
            "लॉटरी", "इनाम", "रिफंड", "कैशबैक", "जीत गए", "जीता है", "पैसे डबल",
            "లాటరీ", "బహుమతి", "రీఫండ్", "క్యాష్‌బ్యాక్", "గెలుచుకున్నారు",
            "லாட்டரி", "பரிசு", "ಲಾಟರಿ", "ಬಹುಮಾನ", "লটারি", "পুরস্কার",
        ],
    },
    "impersonation": {
        "weight": 15,
        "en": "Claims to be from a bank / officer",
        "hi": "बैंक / अधिकारी होने का दावा",
        "patterns": [
            r"(bank|sbi|hdfc|icici|axis|kotak|pnb) se (bol|baat)",
            r"(calling|speaking) from (your|the|sbi|hdfc|icici|axis) ?bank",
            r"bank manager", r"customer (care|service)", r"head office", r"\bofficer\b",
            r"inspector", r"from (the )?(rbi|trai|telecom department)",
            "बैंक से बोल", "बैंक से बात", "कस्टमर केयर", "अधिकारी", "इंस्पेक्टर", "हेड ऑफिस",
            "బ్యాంక్ నుంచి", "బ్యాంక్ నుండి", "కస్టమర్ కేర్", "ఆఫీసర్", "ఇన్‌స్పెక్టర్",
            # Prisma often writes the English word in Latin script inside an Indic sentence
            "bank నుంచి", "bank నుండి", "bank से", "bank থেকে", "bank இருந்து",
            r"(army|military|crpf|bsf|cisf) (mein|me|se|officer|man)", "आर्मी में", "ఆర్మీ",
            "வங்கியிலிருந்து", "ಬ್ಯಾಂಕ್‌ನಿಂದ", "ব্যাংক থেকে",
        ],
    },
}

# Combinations that name the scam and add a bonus on top of the base weights.
COMBOS = [
    ({"authority_threat", "secrecy"}, 25, "Digital arrest scam", "डिजिटल अरेस्ट स्कैम"),
    ({"authority_threat", "payment_pressure"}, 25, "Digital arrest scam", "डिजिटल अरेस्ट स्कैम"),
    ({"parcel", "authority_threat"}, 15, "Courier / parcel scam", "कूरियर / पार्सल स्कैम"),
    ({"payment_pressure", "credential"}, 20, "UPI / QR payment scam", "UPI / QR पेमेंट स्कैम"),
    ({"remote_access", "credential"}, 25, "Remote-access bank fraud", "रिमोट ऐप बैंक फ्रॉड"),
    ({"remote_access", "payment_pressure"}, 20, "Remote-access bank fraud", "रिमोट ऐप बैंक फ्रॉड"),
    ({"account_threat", "credential"}, 20, "Fake KYC / bank fraud", "फ़र्ज़ी KYC / बैंक फ्रॉड"),
    ({"impersonation", "credential"}, 20, "Fake KYC / bank fraud", "फ़र्ज़ी KYC / बैंक फ्रॉड"),
    ({"lure", "payment_pressure"}, 20, "Prize / job / refund scam", "इनाम / नौकरी / रिफंड स्कैम"),
    ({"lure", "credential"}, 20, "Prize / job / refund scam", "इनाम / नौकरी / रिफंड स्कैम"),
    ({"account_threat", "payment_pressure"}, 20, "Bill / account-block scam", "बिल / खाता बंद स्कैम"),
    ({"account_threat", "urgency"}, 10, "Bill / account-block scam", "बिल / खाता बंद स्कैम"),
]


def _compile(pattern: str) -> re.Pattern:
    pattern = pattern.replace("\u200c", "").replace("\u200d", "")  # match normalize()
    if pattern.isascii():
        return re.compile(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", re.IGNORECASE)
    return re.compile(re.escape(pattern) if not any(c in pattern for c in "\\()[]|?*+") else pattern)


_COMPILED = {name: [_compile(p) for p in cat["patterns"]] for name, cat in CATEGORIES.items()}

# A real bank says "we will NEVER ask for your OTP, don't share it with anyone". That mentions an OTP
# and "don't tell anyone" but is safety advice, not a scam. A segment counts as advice when it has an
# advice phrase and no request for the code ("bata dijiye", "tell me", "నాకు చెప్పండి").
_ADVICE = [_compile(p) for p in [
    r"never (ask|share|give|call)", r"(do not|don'?t|dont) (share|give|tell|disclose)",
    r"kabhi (bhi )?(nahi|na|mat)", r"(mat|na|nahi) (bataiye|batayein|batana|share)", r"share (mat|na|nahi)",
    "कभी", "मत बताइए", "मत बताएं", "मत बताना", "शेयर न", "शेयर मत",
    "ఎప్పుడూ", "అడగము", "అడగరు", "ఎవరికీ చెప్పకండి", "ఒருபோதும்", "ಎಂದಿಗೂ",
]]
_REQUEST = [_compile(p) for p in [
    r"(mujhe|muje|hume|humein|hamein) (bata|bhej|share|de)\w*", r"(bata|bol|bhej|share kar) (do|dijiye|dijie|dena|dijiyega)",
    r"batao", r"tell me", r"(share|give) (it )?(with|to) me", r"read (it |me )?(out|the otp)", r"what is (the|your) otp",
    "मुझे बता", "बता दीजिए", "बता दो", "बोल दीजिए", "నాకు చెప్పండి", "నాకు చెప్పు", "எனக்கு சொல்லுங்கள்",
]]
# Delivery agents legitimately ask for a delivery OTP. Only when nothing bank-related is in the sentence.
_DELIVERY = [_compile(p) for p in [
    r"(delivery|deliver|order|zomato|swiggy|amazon|flipkart|blinkit|zepto)", "डिलीवरी", "ऑर्डर", "డెలివరీ",
]]
_MONEY = [_compile(p) for p in [
    r"(bank|upi|card|account|atm|cvv|kyc|wallet)", "बैंक", "खाता", "కార్డ్", "బ్యాంక్", "అకౌంట్",
]]


def _any(rxs: list, text: str) -> bool:
    return any(rx.search(text) for rx in rxs)


def normalize(text: str) -> str:
    text = text.replace("‌", "").replace("‍", "")  # zero-width joiners
    return re.sub(r"\s+", " ", text).strip().lower()


def find_hits(text: str) -> list[dict]:
    """Return every category match in one transcript segment, with the matched phrase."""
    norm = normalize(text)
    hits = []
    for name, patterns in _COMPILED.items():
        for rx in patterns:
            m = rx.search(norm)
            if m:
                hits.append({"category": name, "phrase": m.group(0).strip()})
                break  # one phrase per category per segment is enough evidence

    cats = {h["category"] for h in hits}
    if "credential" in cats and _any(_ADVICE, norm) and not _any(_REQUEST, norm):
        hits = [h for h in hits if h["category"] not in ("credential", "secrecy")]
    elif "credential" in cats and _any(_DELIVERY, norm) and not _any(_MONEY, norm):
        hits = [h for h in hits if h["category"] != "credential"]
    return hits


@dataclass
class CallRisk:
    """Accumulates evidence over a whole call."""

    evidence: dict[str, list[str]] = field(default_factory=dict)

    def add_segment(self, text: str) -> list[dict]:
        hits = find_hits(text)
        for h in hits:
            phrases = self.evidence.setdefault(h["category"], [])
            if h["phrase"] not in phrases:
                phrases.append(h["phrase"])
        return hits

    def analyse(self) -> dict:
        fired = set(self.evidence)
        score = sum(CATEGORIES[c]["weight"] for c in fired)

        scam_type_en, scam_type_hi, best_bonus = None, None, 0
        seen_types = set()
        for needed, bonus, name_en, name_hi in COMBOS:
            if needed <= fired and name_en not in seen_types:
                seen_types.add(name_en)
                score += bonus
                if bonus > best_bonus:
                    best_bonus, scam_type_en, scam_type_hi = bonus, name_en, name_hi

        score = min(100, score)
        level = "danger" if score >= DANGER else "caution" if score >= CAUTION else "safe"

        if scam_type_en is None and fired:
            top = max(fired, key=lambda c: CATEGORIES[c]["weight"])
            scam_type_en, scam_type_hi = CATEGORIES[top]["en"], CATEGORIES[top]["hi"]

        reasons = [
            {
                "category": c,
                "en": CATEGORIES[c]["en"],
                "hi": CATEGORIES[c]["hi"],
                "phrases": self.evidence[c][:3],
                "weight": CATEGORIES[c]["weight"],
            }
            for c in sorted(fired, key=lambda c: -CATEGORIES[c]["weight"])
        ]
        return {
            "score": score,
            "level": level,
            "scam_type_en": scam_type_en,
            "scam_type_hi": scam_type_hi,
            "reasons": reasons,
        }
