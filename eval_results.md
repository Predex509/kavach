# Kavach evaluation

Language setting: `indic-auto`, model `prisma-v3.0`, 8 kHz synthetic phone calls made with Gnani Timbre.

| Call | Audio | Setting | Verdict | First alert | Danger at | Scam words heard | Median latency |
| --- | --- | --- | --- | --- | --- | --- | --- |
| normal_mom_hindi | demo_calls | with_context | safe 0 | never | never | n/a | 109 ms |
| normal_mom_hindi | demo_calls | no_context | safe 0 | never | never | n/a | 110 ms |
| normal_real_bank_hinglish | demo_calls | with_context | safe 0 | never | never | 3/3 | 157 ms |
| normal_real_bank_hinglish | demo_calls | no_context | safe 0 | never | never | 3/3 | 153 ms |
| scam_digital_arrest_hindi | demo_calls | with_context | danger 100 | 5.3 s | 15.3 s | 3/3 | 143 ms |
| scam_digital_arrest_hindi | demo_calls | no_context | danger 100 | 5.3 s | 15.3 s | 3/3 | 141 ms |
| scam_electricity_hinglish | demo_calls | with_context | danger 85 | 13.9 s | 22.6 s | n/a | 114 ms |
| scam_electricity_hinglish | demo_calls | no_context | danger 85 | 13.9 s | 22.5 s | n/a | 108 ms |
| scam_kyc_anydesk_hinglish | demo_calls | with_context | danger 100 | 4.4 s | 12.5 s | 5/5 | 137 ms |
| scam_kyc_anydesk_hinglish | demo_calls | no_context | danger 100 | 4.4 s | 12.5 s | 4/5 (missed AnyDesk) | 137 ms |
| scam_kyc_telugu | demo_calls | with_context | danger 100 | 10.4 s | 17.5 s | 2/2 | 142 ms |
| scam_kyc_telugu | demo_calls | no_context | danger 100 | 10.4 s | 17.5 s | 2/2 | 138 ms |
| scam_olx_army_hindi | demo_calls | with_context | danger 100 | 13.2 s | 19.5 s | 3/3 | 166 ms |
| scam_olx_army_hindi | demo_calls | no_context | danger 100 | 13.2 s | 19.4 s | 3/3 | 152 ms |
| normal_mom_hindi | demo_calls_noisy | with_context | safe 0 | never | never | n/a | 97 ms |
| normal_mom_hindi | demo_calls_noisy | no_context | safe 0 | never | never | n/a | 101 ms |
| normal_real_bank_hinglish | demo_calls_noisy | with_context | safe 0 | never | never | 3/3 | 157 ms |
| normal_real_bank_hinglish | demo_calls_noisy | no_context | safe 0 | never | never | 3/3 | 161 ms |
| scam_digital_arrest_hindi | demo_calls_noisy | with_context | danger 100 | 5.6 s | 15.7 s | 3/3 | 136 ms |
| scam_digital_arrest_hindi | demo_calls_noisy | no_context | danger 100 | 5.4 s | 15.7 s | 3/3 | 140 ms |
| scam_electricity_hinglish | demo_calls_noisy | with_context | danger 85 | 13.8 s | 22.3 s | n/a | 119 ms |
| scam_electricity_hinglish | demo_calls_noisy | no_context | danger 85 | 13.8 s | 22.3 s | n/a | 110 ms |
| scam_kyc_anydesk_hinglish | demo_calls_noisy | with_context | danger 100 | 4.7 s | 11.7 s | 5/5 | 150 ms |
| scam_kyc_anydesk_hinglish | demo_calls_noisy | no_context | danger 100 | 4.7 s | 11.7 s | 4/5 (missed AnyDesk) | 141 ms |
| scam_kyc_telugu | demo_calls_noisy | with_context | danger 100 | 17.9 s | 17.9 s | 2/2 | 134 ms |
| scam_kyc_telugu | demo_calls_noisy | no_context | danger 100 | 17.9 s | 17.9 s | 2/2 | 148 ms |
| scam_olx_army_hindi | demo_calls_noisy | with_context | danger 100 | 13.0 s | 19.3 s | 3/3 | 169 ms |
| scam_olx_army_hindi | demo_calls_noisy | no_context | danger 100 | 13.0 s | 19.2 s | 3/3 | 163 ms |

- **with_context**: correct verdict 14/14, scam words heard 32/32, average time to danger 17.4 s
- **no_context**: correct verdict 14/14, scam words heard 30/32, average time to danger 17.4 s

## Transcripts

- **normal_mom_hindi** (demo_calls, with_context): हाँ बेटा, खाना खाया? हाँ माँ, अभी खाया। आप बताइए? आज मैं बैंक गई, पासबुक अपडेट करवा। शाम को आते समय सब्जी ले आना। ठीक है माँ, सात बजे तक आ जाना।
- **normal_mom_hindi** (demo_calls, no_context): हाँ बेटा, खाना खाया? हाँ माँ, अभी खाया। आप बताइए? आज मैं बैंक गई थी, पासबुक अपडेट करवा। शाम को आते समय सब्जी ले आई। ठीक है माँ, सात बजे तक आ जाना।
- **normal_real_bank_hinglish** (demo_calls, with_context): नमस्ते मैम, एच डी एफ सी बैंक की फ्रॉड टीम से बोल रहे हैं। क्या हुआ? आपके कार्ड पर आज एक ट्रांजैक्शन हुआ है, क्या वो आपने किया था? हाँ, वो मैंने हाई किया था। ठीक है, याद रखिए, बैंक कभी भी आपका ओटीपी या पिन नहीं मांगता है। किसी को भी मत बताइएगा।
- **normal_real_bank_hinglish** (demo_calls, no_context): नमस्ते मैम एच डी एफ सी बैंक की फ्रॉड टीम से बोल रहे हैं। क्या हुआ? आपके कार्ड पर आज एक ट्रांजेक्शन हुआ है, क्या वो आपने किया था। हाँ, वो मैंने हाई किया था। ठीक है, याद रखिए, बैंक कभी भी आपका ओ टी पी या पिन नहीं मांगता है। किसी को भी मत बताएगा।
- **scam_digital_arrest_hindi** (demo_calls, with_context): नमस्ते, मैं मुंबई क्राइम ब्रांच से इंस्पेक्टर राठौड़ बोल रहा हूँ। बोलो, क्या हुआ? आपके आधार कार्ड से एक पार्सल बुक हुआ है जिसमें ड्रग्स मिले हैं, आपके नाम पर मनी लॉन्ड्रिंग का केस है। क्या? मैंने तो कोई पार्सल नहीं भेजा। अब आप डिजिटल अरेस्ट में हैं, यह बात किसी को मत बताइये और कॉल मत काटिये। जाँच के लिए आपको अपने पैसे एक सेफ अकाउंट में ट्रांसफर करने होंगे।
- **scam_digital_arrest_hindi** (demo_calls, no_context): नमस्ते, मैं मुंबई क्राइम ब्रांच से इंस्पेक्टर राठौड़ बोल रहा हूँ। बोलो क्या हुआ? आपके आधार कार्ड से एक पार्सल बुक हुआ है जिसमें ड्रग्स मिले हैं, आपके नाम पर मनी लॉन्ड्रिंग का केस है। क्या? मैंने तो कोई पार्सल नहीं भेजा। अब आप डिजिटल अरेस्ट में हैं, यह बात किसी को मत बताइए और कॉल मत काटिए। जाँच के लिए आपको अपने पैसे एक सेफ अकाउंट में ट्रांसफर करने होंगे।
- **scam_electricity_hinglish** (demo_calls, with_context): नमस्ते, मैं बिजली विभाग से बोल रहा हूँ। हाँ जी, बोलिए। आपका पिछले महीने का बिल अपडेट नहीं हुआ है। आज रात नौ बजे आपका बिजली कनेक्शन कट हो जाएगा। लेकिन मैंने तो बिल भर दिया था। अभी तुरंत मैं एक लिंक भेज रहा हूँ, उस लिंक पर क्लिक करके दस रुपये का पेमेंट कीजिए।
- **scam_electricity_hinglish** (demo_calls, no_context): नमस्ते, मैं बिजली विभाग से बोल रहा हूँ। हां जी, बोलिए। आपका पिछले महीने का बिल अपडेट नहीं हुआ है। आज रात नौ बजे आपका बिजली कनेक्शन कट हो जाएगा। लेकिन मैंने तो बिल भर दिया अभी तुरंत मैं एक लिंक भेज रहा हूँ, उस लिंक पर क्लिक करके दस रुपये का पेमेंट कीजिए।
- **scam_kyc_anydesk_hinglish** (demo_calls, with_context): हेलो सर, मैं एस बी आई कस्टमर केयर से बोल रहा हूँ। हाँ जी, बोलिए। सर, आपका के वाई सी आज एक्सपायर हो रहा है, आपका अकाउंट ब्लॉक हो जाएगा। अरे, अब क्या करना होगा? आप प्ले स्टोर से एनीडेस्क ऐप डाउनलोड कीजिए, मैं आपकी मदद करता हूँ। अब आपके फोन पर जो ओटीपी आया है, वो मुझे बता दीजिए।
- **scam_kyc_anydesk_hinglish** (demo_calls, no_context): हेलो सर, मैं एसबीआई कस्टमर केयर से बोल रहा हूँ। हां जी, बोलिए। सर, आपका के वाई सी आज एक्सपायर हो रहा है, आपका अकाउंट ब्लॉक हो जाएगा। अरे, अब क्या करना होगा? आप प्ले स्टोर से एनी बेस्ट ऐप डाउनलोड कीजिए, मैं आपकी मदद करता हूँ। अब आपके फोन पर जो ओटीपी आया है वो मुझे बता दीजिए।
- **scam_kyc_telugu** (demo_calls, with_context): నమస్తే సార్, నేను మీ బ్యాంక్ నుంచి మాట్లాడుతున్నాను. చెప్పండి. మీ కేవైసీ ఈరోజు ఎక్స్‌పైర్ అవుతుంది, మీ అకౌంట్ బ్లాక్ అవుతుంది. అయ్యో, ఇప్పుడు ఏం చేయాలి? ఇప్పుడే మీ ఫోన్‌కి ఒక ఓటిపి వచ్చింది, అది నాకు చెప్పండి.
- **scam_kyc_telugu** (demo_calls, no_context): నమస్తే సార్, నేను మీ బ్యాంక్ నుంచి మాట్లాడుతున్నాను. చెప్పండి మీ కేవైసీ ఈరోజు ఎక్స్‌పైర్ అవుతుంది మీ అకౌంట్ బ్లాక్ అవుతుంది. అయ్యో, ఇప్పుడు ఏం చేయాలి? ఇప్పుడే మీ ఫోన్‌కి ఒక ఓటిపి వచ్చింది అది నాకు చెప్పండి.
- **scam_olx_army_hindi** (demo_calls, with_context): नमस्ते, मैं आर्मी में हूँ। आपका सोफा खरीदना चाहता हूँ। हाँ, पैसा अभी दूँगा। मैं अभी आपको एक क्यू आर कोड भेज रहा हूँ, पेमेंट मैं एडवांस में कर देता हूँ। बस क्यू आर कोड स्कैन करके अपना यू पी आई पिन डाल दीजिए, पैसे आपके खाते में आ जाएंगे।
- **scam_olx_army_hindi** (demo_calls, no_context): नमस्ते, मैं आर्मी में हूँ, आपका सोफा खरीदना चाहता हूँ। हम्म, पैसा अभी देंगे। मैं अभी आपको एक क्यू आर कोड भेज रहा हूँ, पेमेंट मैं एडवांस में कर देता हूँ। बस क्यूआर कोड स्कैन करके अपना यू पी आई पिन डाल दीजिए, पैसे आपके खाते में आ जाएंगे।
- **normal_mom_hindi** (demo_calls_noisy, with_context): Thank you. हाँ माँ, अभी था। आप बताइए। सबकी ले लेंगे। ठीक है मैम, सात बजे तक आ जाना।
- **normal_mom_hindi** (demo_calls_noisy, no_context): മന്ത്രി ഡോ. हाँ माँ, अभी खाया। आप बताइए? सबकी मदद। ठीक है मैम, सात बजे तक आ जाना।
- **normal_real_bank_hinglish** (demo_calls_noisy, with_context): नमस्ते मैम, एच डी एफ सी बैंक की शॉर्ट मनी से बोल रही हूँ। के कार्ड पर आगे ट्रांजेक्शन हुआ है, क्या वो आप मुझे बता सकते हैं? मैंने हाई किया। ठीक है, याद रखिए, बैंक कभी भी आपका ओटीपी या पिन नहीं मांगता है, किसी को भी नहीं पता।
- **normal_real_bank_hinglish** (demo_calls_noisy, no_context): नमस्ते, मैं एच डी एफ सी बैंक की शॉर्ट्स मनी से बोल रहा हूँ। आपके कार्ड पर आज एक ट्रांजेक्शन हुआ है, क्या वो आपने किया था। ನಾನೇ ಹೈಟ್ಗೆ ठीक है, याद रखिए, बैंक कभी भी आपका ओटीपी या पिन नहीं मांगता है, किसी को भी नहीं पता।
- **scam_digital_arrest_hindi** (demo_calls_noisy, with_context): नमस्ते, मैं मुंबई क्राइम ब्रांच से इंस्पेक्टर राठौड़ बोल रहा हूँ। जी बोलिए, क्या है? आपके आधार कार्ड से एक पार्सल बुक हुआ है, उसमें ड्रग्स मिले हैं, आपके नाम पर मनी लॉन्ड्रिंग केस है। Ma'am. अब आप डिजिटल अरेस्ट में हैं, यह बात किसी को मत बताना और कॉल मत काट देना। डाक के लिए आपको अपने पैसे उस सेफ अकाउंट में ट्रांसफर करने होंगे।
- **scam_digital_arrest_hindi** (demo_calls_noisy, no_context): नमस्ते, मैं मुंबई क्राइम ब्रांच से इंस्पेक्टर राठौड़ बोल रहा हूँ। जी बोलिए क्या हुआ? आपके आधार कार्ड से एक पार्सल बुक हुआ है, इसमें ड्रग्स मिले हैं, आपके नाम पर मनी लॉन्ड्रिंग रिपोर्ट है। मैम। अब आप डिजिटल अरेस्ट में हैं, ये बात किसी को मत बताना और कॉल मत काट देना। डाक के लिए आपको अपने पैसे इस सेव अकाउंट में ट्रांसफर करने होंगे।
- **scam_electricity_hinglish** (demo_calls_noisy, with_context): नमस्ते, मैं बिजली विभाग से बोल रहा हूँ। Thank you. आपका पिछले महीने का बिल अपडेट नहीं हुआ है। आज रात नौ बजे आपका बिजली कनेक्शन कट हो जाएगा। बैंक अभी तुरंत मैं एक लिंक भेज रहा हूँ, उस लिंक पर क्लिक करके दस रुपये का पेमेंट कर दें।
- **scam_electricity_hinglish** (demo_calls_noisy, no_context): नमस्ते, मैं बिजली विभाग से बोल रहा हूँ। थँक्यू। आपका पिछले महीने का बिल अपडेट नहीं हुआ है। आज रात नौ बजे आपका बिजली कनेक्शन कट हो जाएगा। எழுதி. अभी तुरंत मैं एक लिंक भेज रहा हूँ। उस लिंक पर क्लिक करके दस रुपये का पेमेंट कर दें।
- **scam_kyc_anydesk_hinglish** (demo_calls_noisy, with_context): हेलो सर, मैं एस बी आई कस्टमर केयर से बोल रही हूँ। जी। सर, आपका के वाई सी आज एक्सपायर हो रहा है, आपका अकाउंट ब्लॉक हो जाएगा। प्ले स्टोर से एनीडेस्क ऐप डाउनलोड कीजिए, मैं आपकी मदद करता हूँ। अब आपके फोन पर जो ओटीपी आया है, वह मुझे बता दीजिए।
- **scam_kyc_anydesk_hinglish** (demo_calls_noisy, no_context): हेलो सर, मैं एसबीआई कस्टमर केयर से बोल रही हूँ। हो। सर, आपका केवाईसी आज एक्सपायर हो रहा है, आपका अकाउंट ब्लॉक हो जाएगा। प्ले स्टोर से एनीडेस्ट ऐप डाउनलोड कीजिए, मैं आपकी मदद करता हूं। अब आपके फोन पर जो ओटीपी आया है वह मुझे बता दीजिए।
- **scam_kyc_telugu** (demo_calls_noisy, with_context): नमस्ते सर, मैं बैंक मित्र से बात कर रहा हूँ। ये केवाईसी ईरोज़ी अच्छा रहता है। ये अकाउंट ब्लॉक हो गया। ఇప్పుడే మీ ఫోన్‌కి ఒక ఓటిపి వస్తుంది, అది నాకు చెప్పండి.
- **scam_kyc_telugu** (demo_calls_noisy, no_context): నమస్తే సార్, నేను మీ బ్యాంక్ మేనేజర్ని మాట్లాడుతున్నాను. మీ కేవైసీ ఈరోజు ఎక్సక్ట్ గా రాసింది. ही अकाउंट ब्लॉक होतील। ఇప్పుడే మీ ఫోన్‌కి ఒక ఓటిపి వస్తుంది అది నాకు చెప్పండి.
- **scam_olx_army_hindi** (demo_calls_noisy, with_context): नमस्ते, मैं आर्मी में हूँ। आपका सोफ़ा खरीदना चाहता हूँ। हाँ, अभी नहीं। मैं अभी आपको एक क्यू आर कोड भेज रहा हूँ, पेमेंट मैं एडवांस में कर देता हूँ। बस क्यू आर कोड स्कैन करके अपना यू पी आई पिन डाल दीजिए, पैसे आपके खाते में आ जाएंगे।
- **scam_olx_army_hindi** (demo_calls_noisy, no_context): नमस्ते, मैं आर्मी में हूँ, आपका सोफा खरीदना चाहता हूँ। हाँ, अभी। मैं अभी आपको एक क्यू आर कोड भेज रहा हूँ, पेमेंट मैं एडवांस में कर देता हूँ। बस क्यू आर कोड स्कैन करके अपना यू पी आई पिन डाल दीजिए, पैसे आपके खाते में आ जाएंगे।