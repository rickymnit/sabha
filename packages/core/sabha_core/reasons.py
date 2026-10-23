"""Plain-language explanations of why a recording failed or needs review, keyed by the stable reason codes the
pipeline records (status_reason, report review_reasons). Shared by the emails (P2.7) and the API's report payload
(P5.7b) so people read the same words everywhere. Unknown codes get GENERIC.
"""

from __future__ import annotations

REASONS: dict[str, dict[str, str]] = {
    "en": {
        "unclear_roles": "We could not tell the speakers apart reliably.",
        "low_verification": "Too few scores could be checked against the transcript.",
        "synthesis_failed": "The written summary could not be produced.",
        "invalid_audio": "The audio file could not be read.",
        "too_short": "The recording is shorter than 30 seconds, too short to give feedback on.",
        "too_long": "The recording is longer than 3 hours. Split it into parts and upload each one.",
        "uncertain_type": "We could not tell what kind of conversation this is.",
        "no_speech": "No speech was found in the recording.",
        "no_speakers": "We could not tell who was speaking.",
        "no_transcript": "Speech was found but no words could be recognised.",
        "no_rubric": "There is no rubric for this kind of conversation yet.",
        "analysis_failed": "The feedback could not be produced; an administrator can retry it.",
        "ticket_failed": "The call ticket could not be written.",
        "unverified_dimensions": "Some parts could not be checked against the transcript and are left out.",
    },
    "hi": {
        "unclear_roles": "बोलने वालों को ठीक से अलग नहीं पहचाना जा सका।",
        "low_verification": "बहुत कम स्कोर ट्रांसक्रिप्ट से जाँचे जा सके।",
        "synthesis_failed": "लिखित सारांश नहीं बन सका।",
        "invalid_audio": "ऑडियो फ़ाइल पढ़ी नहीं जा सकी।",
        "too_short": "रिकॉर्डिंग 30 सेकंड से छोटी है, इस पर फ़ीडबैक देना संभव नहीं।",
        "too_long": "रिकॉर्डिंग 3 घंटे से लंबी है। इसे हिस्सों में बाँटकर अपलोड करें।",
        "uncertain_type": "यह किस तरह की बातचीत है, यह तय नहीं हो सका।",
        "no_speech": "रिकॉर्डिंग में कोई बोली नहीं मिली।",
        "no_speakers": "यह पता नहीं चल सका कि कौन बोल रहा था।",
        "no_transcript": "बोली मिली, लेकिन कोई शब्द पहचाने नहीं जा सके।",
        "no_rubric": "इस तरह की बातचीत के लिए अभी कोई रूब्रिक नहीं है।",
        "analysis_failed": "फ़ीडबैक नहीं बन सका; व्यवस्थापक इसे दोबारा चला सकते हैं।",
        "ticket_failed": "कॉल का टिकट नहीं लिखा जा सका।",
        "unverified_dimensions": "कुछ हिस्से ट्रांसक्रिप्ट से जाँचे नहीं जा सके, इसलिए वे शामिल नहीं हैं।",
    },
}

GENERIC = {
    "en": "Something went wrong while processing; an administrator can look at it.",
    "hi": "प्रोसेस करते समय कुछ गड़बड़ हुई; व्यवस्थापक इसे देख सकते हैं।",
}


def explain(code: str | None, language: str = "en") -> str:
    lang = language if language in REASONS else "en"
    return REASONS[lang].get(code or "", GENERIC[lang])
