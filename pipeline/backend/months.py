"""Month names in the app's 13 languages, for the "link checked" date.

The monthly run sets every scheme's lastVerified to the current month, such as
"November 2026". Writing that date in each language from this table avoids
sending 12 identical one-line strings to a translator every month. The
September spellings match the ones already in the data.
"""

EN = ["January", "February", "March", "April", "May", "June", "July",
      "August", "September", "October", "November", "December"]

MONTHS = {
    "hi": "जनवरी फ़रवरी मार्च अप्रैल मई जून जुलाई अगस्त सितंबर अक्टूबर नवंबर दिसंबर",
    "gu": "જાન્યુઆરી ફેબ્રુઆરી માર્ચ એપ્રિલ મે જૂન જુલાઈ ઑગસ્ટ સપ્ટેમ્બર ઑક્ટોબર નવેમ્બર ડિસેમ્બર",
    "mr": "जानेवारी फेब्रुवारी मार्च एप्रिल मे जून जुलै ऑगस्ट सप्टेंबर ऑक्टोबर नोव्हेंबर डिसेंबर",
    "bn": "জানুয়ারি ফেব্রুয়ারি মার্চ এপ্রিল মে জুন জুলাই আগস্ট সেপ্টেম্বর অক্টোবর নভেম্বর ডিসেম্বর",
    "ta": "ஜனவரி பிப்ரவரி மார்ச் ஏப்ரல் மே ஜூன் ஜூலை ஆகஸ்ட் செப்டம்பர் அக்டோபர் நவம்பர் டிசம்பர்",
    "te": "జనవరి ఫిబ్రవరి మార్చి ఏప్రిల్ మే జూన్ జూలై ఆగస్టు సెప్టెంబర్ అక్టోబర్ నవంబర్ డిసెంబర్",
    "kn": "ಜನವರಿ ಫೆಬ್ರವರಿ ಮಾರ್ಚ್ ಏಪ್ರಿಲ್ ಮೇ ಜೂನ್ ಜುಲೈ ಆಗಸ್ಟ್ ಸೆಪ್ಟೆಂಬರ್ ಅಕ್ಟೋಬರ್ ನವೆಂಬರ್ ಡಿಸೆಂಬರ್",
    "ml": "ജനുവരി ഫെബ്രുവരി മാർച്ച് ഏപ്രിൽ മേയ് ജൂൺ ജൂലൈ ഓഗസ്റ്റ് സെപ്റ്റംബർ ഒക്ടോബർ നവംബർ ഡിസംബർ",
    "pa": "ਜਨਵਰੀ ਫ਼ਰਵਰੀ ਮਾਰਚ ਅਪ੍ਰੈਲ ਮਈ ਜੂਨ ਜੁਲਾਈ ਅਗਸਤ ਸਤੰਬਰ ਅਕਤੂਬਰ ਨਵੰਬਰ ਦਸੰਬਰ",
    "or": "ଜାନୁଆରୀ ଫେବୃଆରୀ ମାର୍ଚ୍ଚ ଏପ୍ରିଲ ମେ ଜୁନ ଜୁଲାଇ ଅଗଷ୍ଟ ସେପ୍ଟେମ୍ବର ଅକ୍ଟୋବର ନଭେମ୍ବର ଡିସେମ୍ବର",
    "as": "জানুৱাৰী ফেব্ৰুৱাৰী মাৰ্চ এপ্ৰিল মে জুন জুলাই আগষ্ট ছেপ্তেম্বৰ অক্টোবৰ নৱেম্বৰ ডিচেম্বৰ",
    "ur": "جنوری فروری مارچ اپریل مئی جون جولائی اگست ستمبر اکتوبر نومبر دسمبر",
}
MONTHS = {lang: names.split() for lang, names in MONTHS.items()}
assert all(len(v) == 12 for v in MONTHS.values())


def english(year, month):
    return f"{EN[month - 1]} {year}"


def local(lang, year, month):
    return f"{MONTHS[lang][month - 1]} {year}"
