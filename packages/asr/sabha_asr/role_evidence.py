"""Evidence-based speaker roles for conversation types with an evidence profile (support calls first).

Owner's decision (2026-11-04): on a support call, the agent is not "who speaks first" or "who explains the problem".
Roles come from behaviour, weighed for both speakers, with the AI only as a tie-breaker and a person deciding when
the evidence is not enough. A call has exactly one agent and one customer (owner's decision), so this is a
two-speaker classifier; any other number of speakers is left to the rules in sabha_asr.roles.

Evidence (`EvidenceProfile`): each `Cue` is a behaviour that points to the staff member ("asks for the AnyDesk ID")
or to the other side ("describes a problem in the software"), with a weight. A cue is looked for in each stretch of
one speaker's talk, over the whole conversation or only the opening; it counts at most once per speaker, so
repeating a phrase adds nothing. Some cues need the organisation's name in the same stretch ("greets and names
SchoolLog") or its absence ("I am calling from <some> school", which must not be the organisation itself). The
weights are the owner's starting values, NOT measured: calibrate them on reviewer corrections (eval/role_corrections.py)
and the gold set (eval/roles.py).

Decision (`judge`): for speakers A and B, "A is staff" is supported by A's staff cues plus B's other-side cues, and
the reverse likewise. With h the winning side's total and l the losing side's:
- confidence = 0.5 + 0.5 * (h - l) / (h + l) * min(1, (h + l) / FULL_EVIDENCE); 0.5 with no evidence at all;
- CONFLICT when the losing side also has strong evidence (l >= CONFLICT_MIN and h < 2 * l), or when the first two
  minutes point to the other speaker (with confidence >= LEAN) than the whole conversation does;
- AUTO at confidence >= 0.9; CORROBORATED at >= 0.75 when at least two different cues support the winner;
  otherwise WEAK. These thresholds are the owner's starting values, not measured probabilities.
A conflict goes to a reviewer; weak evidence goes to the AI tie-breaker, whose answer is used only if it is at least
90% sure and does not contradict the evidence's lean (sabha_asr.roles.assign_roles).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sabha_asr.words import Turn, Word, assign_words_to_turns

Side = Literal["staff", "other"]
Decision = Literal["auto", "corroborated", "weak", "conflict"]

OPENING_MS = 30_000
"""Greetings and introductions count only in the first 30 s of speech."""
EARLY_MS = 120_000
"""The first two minutes, compared with the whole conversation for consistency."""
FULL_EVIDENCE = 10.0
"""Total evidence at which the margin alone sets the confidence."""
CONFLICT_MIN = 6.0
"""Losing-side evidence at least this strong is a conflict unless the winner has twice as much."""
LEAN = 0.6
"""Evidence at least this confident is a lean the AI must not contradict, and that a different early winner breaks."""
AUTO = 0.9
CORROBORATED = 0.75
MIN_INDEPENDENT_CUES = 2
SNIPPET_CHARS = 160


@dataclass(frozen=True, slots=True)
class Cue:
    """A behaviour pointing to one side. Phrases are normalised (sabha_asr.roles.normalise_text) and matched as whole
    words; `also` needs one of its phrases in the same stretch too; `pattern` is a regex on the normalised text."""

    key: str
    side: Side
    weight: float
    phrases: tuple[str, ...] = ()
    also: tuple[str, ...] = ()
    pattern: str | None = None
    organisation: bool | None = None  # True: the organisation's name must be said in the stretch; False: must not
    opening_only: bool = False
    unless: tuple[str, ...] = ()  # not counted in a stretch that has any of these (an offer to do it, for example)


@dataclass(frozen=True, slots=True)
class EvidenceProfile:
    cues: tuple[Cue, ...]
    guidance: str  # for the AI tie-breaker; "{organisation}" is the organisation's name
    ai_min_confidence: float = AUTO


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """One cue found: who said it, what it points to, and the stretch of talk it was found in."""

    speaker: str
    cue: str
    side: Side
    weight: float
    start_ms: int
    text: str

    def to_record(self) -> dict[str, object]:
        return {"speaker": self.speaker, "cue": self.cue, "side": self.side, "weight": self.weight,
                "start_ms": self.start_ms, "text": self.text}  # fmt: skip


@dataclass(frozen=True, slots=True)
class RoleEvidence:
    """The outcome of `judge`: the staff speaker the evidence points to, how strongly, and why."""

    staff: str
    confidence: float
    decision: Decision
    items: tuple[EvidenceItem, ...]
    early_staff: str | None  # who the first two minutes point to, when they lean (>= LEAN)
    reason: str

    def to_record(self) -> dict[str, object]:
        return {"staff": self.staff, "confidence": self.confidence, "decision": self.decision,
                "early_staff": self.early_staff, "reason": self.reason,
                "items": [item.to_record() for item in self.items]}  # fmt: skip


_GREETINGS = ("namaste", "namaskar", "good morning", "good afternoon", "good evening", "hello", "hi", "welcome",
              "नमस्ते", "नमस्कार", "हेलो", "हैलो", "गुड मॉर्निंग", "गुड आफ्टरनून", "गुड इवनिंग")  # fmt: skip
_REMOTE = ("anydesk", "any desk", "एनीडेस्क", "एनी डेस्क", "एनीडेक्स", "एनी डेक्स", "teamviewer", "team viewer",
           "टीमव्यूअर", "टीम व्यूअर", "रिमोट", "remote")  # fmt: skip
_ASK = ("दीजिए", "दीजिये", "दे दीजिए", "बताइए", "बताइये", "बता दीजिए", "बोलिए", "भेजिए", "भेज दीजिए", "खोलिए",
        "ओपन कीजिए", "ओपन करिए", "dijiye", "bataiye", "batao", "bhejiye", "kholiye", "share", "शेयर")  # fmt: skip
# The agent offering to act ("I will add it for you", "I will look into it"), said by a man or a woman. A customer's
# request or problem is not counted in a stretch with one of these: the agent restates the problem as they offer
# ("your fee is not showing, isn't it? I'll look into it"), which on 2026-11-04 counted for the customer.
_OFFERS = ("करवा देता हूं", "करवा देता हूँ", "करवा देती हूं", "करवा देती हूँ", "कर देता हूं", "कर देता हूँ",
           "कर देती हूं", "कर देती हूँ", "देख लेता हूं", "देख लेता हूँ", "देख लेती हूं", "देख लेती हूँ",
           "चेक कर लेता", "चेक कर लेती", "चेक करवा लेता", "चेक करवा लेती", "कर दूंगा", "कर दूँगा", "कर दूंगी",
           "कर दूँगी", "करवा दूंगा", "करवा दूँगा", "करवा दूंगी", "करवा दूँगी", "बता देता हूं कैसे", "बता देता हूँ कैसे",
           "बता देती हूं कैसे", "बता देती हूँ कैसे", "बताता हूं कैसे", "बताता हूँ कैसे", "बताती हूं कैसे",
           "बताती हूँ कैसे")  # fmt: skip
_GIVE = ("लीजिए", "लीजिये", "ले लीजिए", "नोट कीजिए", "नोट करिए", "नोट कर लीजिए", "lijiye", "note kijiye")

SUPPORT_PROFILE = EvidenceProfile(
    cues=(
        # The agent (staff). Owner's starting weights (2026-11-04).
        Cue("greets_with_organisation", "staff", 4, _GREETINGS, organisation=True, opening_only=True),
        Cue(
            "introduces_as_support",
            "staff",
            3,
            (
                "support से",
                "सपोर्ट से",
                "support se",
                "support team",
                "सपोर्ट टीम",
                "technical team",
                "टेक्निकल टीम",
                "customer care",
                "कस्टमर केयर",
                "helpdesk",
                "हेल्पडेस्क",
            ),
        ),
        Cue("asks_for_remote_access_id", "staff", 3, _REMOTE, also=_ASK),
        Cue("offers_to_do_it", "staff", 3, _OFFERS),
        Cue(
            "asks_which_school",
            "staff",
            2,
            (
                "स्कूल का नाम",
                "कौन से स्कूल",
                "किस स्कूल",
                "कौन सा स्कूल",
                "school ka naam",
                "which school",
                "स्कूल कोड",
                "school code",
                "संस्था का नाम",
            ),
        ),
        Cue(
            "guides_software_steps",
            "staff",
            3,
            (
                "क्लिक कीजिए",
                "क्लिक करिए",
                "क्लिक करें",
                "click kijiye",
                "click karo",
                "में जाइए",
                "में जाइये",
                "में जाकर",
                "पर जाइए",
                "सेलेक्ट कीजिए",
                "सेलेक्ट करिए",
                "रिफ्रेश कीजिए",
                "रिफ्रेश करिए",
                "लॉगआउट करके",
                "ड्रॉपडाउन",
                "dropdown",
                "टैब में",
            ),
        ),
        Cue(
            "explains_a_module",
            "staff",
            3,
            ("मॉड्यूल", "module", "फीचर", "feature", "ऑप्शन है", "ऑप्शन दिया", "option hai", "सेटिंग में", "सेटिंग्स में", "मास्टर में"),
        ),
        Cue(
            "asks_for_details",
            "staff",
            2,
            ("स्क्रीनशॉट", "screenshot", "स्क्रीन शॉट", "आईडी बताइए", "नंबर बताइए", "डिटेल भेज", "details bhej"),
        ),
        Cue(
            "explains_resolution",
            "staff",
            2,
            (
                "अब चेक कीजिए",
                "अब देखिए",
                "अब ट्राई कीजिए",
                "अब हो जाएगा",
                "ठीक कर दिया",
                "अपडेट कर दिया",
                "सही कर दिया",
                "check kijiye",
                "ho jayega",
            ),
        ),
        Cue(
            "arranges_technical_help",
            "staff",
            2,
            (
                "डेवलपमेंट टीम",
                "डेवलपर",
                "developer",
                "टिकट",
                "ticket",
                "एस्केलेट",
                "escalate",
                "चेक करवा",
                "कॉल पे बने रहें",
                "होल्ड पर",
                "होल्ड पे",
                "hold",
            ),
        ),
        # The customer (other side).
        Cue(
            "introduces_as_school",
            "other",
            3,
            (
                "से बात कर रहा",
                "से बात कर रही",
                "से बात करता",
                "से बात करती",
                "से बोल रहा",
                "से बोल रही",
                "se bol raha",
                "se baat kar",
            ),
            also=("स्कूल", "school", "गुरुकुल", "विद्यालय", "कॉलेज", "college", "एकेडमी", "academy", "पब्लिक", "कॉन्वेंट"),
            organisation=False,
        ),
        Cue(
            "describes_a_problem",
            "other",
            3,
            (
                "नहीं आ रहा",
                "नहीं आ रही",
                "नहीं हो रहा",
                "नहीं हो रही",
                "नहीं खुल",
                "नहीं चल रहा",
                "नहीं दिख रहा",
                "गलत आ रहा",
                "गलत दिखा",
                "गलत आ रही",
                "एरर",
                "error",
                "प्रॉब्लम",
                "problem",
                "दिक्कत",
                "इशू",
                "issue",
                "not working",
                "nahi aa raha",
                "nahi ho raha",
            ),
            unless=_OFFERS,
        ),
        Cue("gives_remote_access_id", "other", 3, _REMOTE, also=_GIVE),
        Cue("reads_out_a_long_number", "other", 2, pattern=r"\d{6,}"),
        Cue(
            "asks_how_to",
            "other",
            2,
            ("कैसे करें", "कैसे करना", "कैसे होगा", "कैसे करते", "kaise kare", "kaise karna", "how to", "how do i"),
            unless=_OFFERS,
        ),
        Cue(
            "requests_a_change",
            "other",
            3,
            (
                "रिपोर्ट चाहिए",
                "लिस्ट चाहिए",
                "करवाना है",
                "ठीक करना है",
                "सही करवा",
                "ठीक करवा",
                "ऐड करवा",
                "चेंज करवा",
                "हटवाना",
            ),
            unless=_OFFERS,
        ),
        Cue(
            "asks_for_help",
            "other",
            2,
            ("मदद", "समझा दीजिए", "समझ नहीं आ", "समझ नहीं पा", "बता दीजिए कैसे"),
            unless=_OFFERS,
        ),
        Cue("confirms_it_works", "other", 1, ("हाँ हो गया", "अब आ गया", "अब सही", "अब हो गया", "आ गया सर", "हो गया सर")),
    ),
    guidance=(
        "This is a support call about the software of {organisation}. The agent works for {organisation}; the customer "
        "usually represents a school. The customer usually describes the problem, names their school, asks how to do "
        "something and may read out a remote-access ID (AnyDesk) or other numbers; the agent usually asks for those "
        "details and explains how to do things in the software, step by step. Do not decide from one sentence, do not "
        "assume the speaker who talks more or speaks first is the agent, and use only what is in the transcript."
    ),
)

PROFILES: dict[str, EvidenceProfile] = {"support": SUPPORT_PROFILE}
"""Conversation types judged by evidence; the others keep the rules in sabha_asr.roles."""


def _norm(text: str) -> str:
    from sabha_asr.roles import normalise_text  # roles imports this module: import here to avoid a cycle

    return normalise_text(text)


def _has(text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text} "


def speaker_stretches(turns: Sequence[Turn], words: Sequence[Word]) -> list[tuple[str, int, str]]:
    """(speaker_label, start_ms, text) for each run of consecutive words by one speaker, in time order."""
    ordered = sorted(words, key=lambda w: (w.start_ms, w.end_ms))
    runs: list[tuple[str, int, list[str]]] = []
    for word, turn in zip(ordered, assign_words_to_turns(ordered, turns), strict=True):
        if runs and runs[-1][0] == turn.speaker_label:
            runs[-1][2].append(word.text)
        else:
            runs.append((turn.speaker_label, word.start_ms, [word.text]))
    return [(label, start, " ".join(texts)) for label, start, texts in runs]


def _matches(cue: Cue, text: str, organisation: Sequence[str]) -> bool:
    if cue.phrases and not any(_has(text, p) for p in cue.phrases):
        return False
    if cue.also and not any(_has(text, p) for p in cue.also):
        return False
    if cue.pattern is not None and not re.search(cue.pattern, text):
        return False
    if cue.organisation is not None and any(_has(text, name) for name in organisation) is not cue.organisation:
        return False
    if cue.unless and any(_has(text, p) for p in cue.unless):
        return False
    return bool(cue.phrases or cue.pattern)


def find_evidence(
    stretches: Sequence[tuple[str, int, str]], profile: EvidenceProfile, organisation: Sequence[str], until_ms: int
) -> list[EvidenceItem]:
    """Every cue found, at most once per speaker and cue (the first stretch it is found in), before `until_ms`."""
    names = [n for n in (_norm(name) for name in organisation) if n]
    found: dict[tuple[str, str], EvidenceItem] = {}
    for label, start, raw in stretches:
        if start >= until_ms:
            break
        text = _norm(raw)
        for cue in profile.cues:
            if (label, cue.key) in found or (cue.opening_only and start >= OPENING_MS):
                continue
            if _matches(cue, text, names):
                found[(label, cue.key)] = EvidenceItem(label, cue.key, cue.side, cue.weight, start, raw[:SNIPPET_CHARS])
    return sorted(found.values(), key=lambda item: (item.start_ms, item.speaker, item.cue))


def _weigh(items: Sequence[EvidenceItem], labels: tuple[str, str], first: str | None) -> tuple[str, float, float, int]:
    """(winner, winner's support, loser's support, distinct cues for the winner); speaking first is +0.5 for staff."""
    support = {label: 0.0 for label in labels}
    cues: dict[str, set[str]] = {label: set() for label in labels}
    for item in items:
        staff = item.speaker if item.side == "staff" else next(label for label in labels if label != item.speaker)
        support[staff] += item.weight
        cues[staff].add(item.cue)
    if first in support:
        support[first] += 0.5
    a, b = labels
    winner, loser = (a, b) if support[a] >= support[b] else (b, a)
    return winner, support[winner], support[loser], len(cues[winner])


def _confidence(high: float, low: float) -> float:
    total = high + low
    if total <= 0:
        return 0.5
    return round(0.5 + 0.5 * (high - low) / total * min(1.0, total / FULL_EVIDENCE), 3)


def judge(
    turns: Sequence[Turn], words: Sequence[Word], profile: EvidenceProfile, organisation: Sequence[str]
) -> RoleEvidence | None:
    """Weigh the evidence for exactly two speakers (module docstring); None for any other number of speakers."""
    labels = sorted({t.speaker_label for t in turns})
    if len(labels) != 2:
        return None
    pair = (labels[0], labels[1])
    stretches = speaker_stretches(turns, words)
    first = stretches[0][0] if stretches else None
    items = find_evidence(stretches, profile, organisation, until_ms=max((s for _, s, _ in stretches), default=0) + 1)
    staff, high, low, distinct = _weigh(items, pair, first)
    confidence = _confidence(high, low)

    early_items = [item for item in items if item.start_ms < EARLY_MS]
    early_staff, early_high, early_low, _ = _weigh(early_items, pair, first)
    early_lean = early_staff if _confidence(early_high, early_low) >= LEAN else None

    if low >= CONFLICT_MIN and high < 2 * low:
        decision: Decision = "conflict"
        reason = f"strong evidence for both speakers ({high:g} against {low:g})"
    elif early_lean is not None and early_lean != staff and confidence >= LEAN:
        decision, reason = "conflict", "the first two minutes point to the other speaker"
    elif confidence >= AUTO:
        decision, reason = "auto", "strong evidence"
    elif confidence >= CORROBORATED and distinct >= MIN_INDEPENDENT_CUES:
        decision, reason = "corroborated", f"{distinct} independent cues agree"
    else:
        decision, reason = "weak", "not enough evidence"
    return RoleEvidence(staff, confidence, decision, tuple(items), early_lean, reason)
