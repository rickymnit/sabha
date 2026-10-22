"""Who is emailed about a recording, and what the email says (plan task P2.7).

Rules:

- COMPLETED: the person analysed, if they have not turned report emails off, and their manager(s). The email says
  the report is ready and links to it. It never carries a score, a quote or any transcript text: those stay behind
  login and the audit log. `render_email` has no parameter for them, so they cannot be passed by mistake.
- FAILED and NEEDS_REVIEW: the tenant's admins and owners, with the reason code and a plain explanation.
- Nothing else is emailed.
- Each planned email has a delivery key derived from (event_id, recipient), so a retried event never sends the same
  email twice (the notify task records sent keys).
- Words such as "Lesson" or "Teacher" come from the tenant's labels, never from the templates (CLAUDE.md).
- English and Hindi templates; any other language falls back to English, and the result says so.
"""

from __future__ import annotations

import hashlib
import html
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from string import Template
from typing import Literal

EmailKind = Literal["report_ready", "needs_attention"]
LANGUAGES = ("en", "hi")
PROBLEM_STATUSES = frozenset({"FAILED", "NEEDS_REVIEW"})
ADMIN_ROLES = frozenset({"admin", "owner"})


@dataclass(frozen=True)
class Recipient:
    user_id: str
    email: str
    role: str
    language: str
    wants_report_emails: bool
    is_subject: bool = False
    """True for the staff member the recording analyses."""


@dataclass(frozen=True)
class PlannedEmail:
    recipient: Recipient
    kind: EmailKind
    delivery_key: str


def delivery_key(event_id: str, user_id: str, kind: str) -> str:
    """Stable id of one email for one event and recipient."""
    return hashlib.sha256(f"{event_id}\x1f{user_id}\x1f{kind}".encode()).hexdigest()


def plan_emails(event_id: str, status: str, recipients: Sequence[Recipient]) -> list[PlannedEmail]:
    """The emails to send for a recording reaching `status`. `recipients` are the people linked to the recording:
    the person analysed, their unit's managers and the tenant's admins."""
    if status == "COMPLETED":
        chosen = [r for r in recipients if (r.is_subject or r.role == "manager") and r.wants_report_emails]
        kind: EmailKind = "report_ready"
    elif status in PROBLEM_STATUSES:
        chosen = [r for r in recipients if r.role in ADMIN_ROLES]
        kind = "needs_attention"
    else:
        return []
    return [PlannedEmail(r, kind, delivery_key(event_id, r.user_id, kind)) for r in chosen]


@dataclass(frozen=True)
class RenderedEmail:
    language: str
    subject: str
    text: str
    html: str


REASONS: dict[str, dict[str, str]] = {
    "en": {
        "unclear_roles": "We could not tell the speakers apart reliably.",
        "low_verification": "Too few scores could be checked against the transcript.",
        "synthesis_failed": "The written summary could not be produced.",
        "invalid_audio": "The audio file could not be read.",
        "uncertain_type": "We could not tell what kind of conversation this is.",
        "no_speech": "No speech was found in the recording.",
        "no_speakers": "We could not tell who was speaking.",
        "no_transcript": "Speech was found but no words could be recognised.",
    },
    "hi": {
        "unclear_roles": "बोलने वालों को ठीक से अलग नहीं पहचाना जा सका।",
        "low_verification": "बहुत कम स्कोर ट्रांसक्रिप्ट से जाँचे जा सके।",
        "synthesis_failed": "लिखित सारांश नहीं बन सका।",
        "invalid_audio": "ऑडियो फ़ाइल पढ़ी नहीं जा सकी।",
        "uncertain_type": "यह किस तरह की बातचीत है, यह तय नहीं हो सका।",
        "no_speech": "रिकॉर्डिंग में कोई बोली नहीं मिली।",
        "no_speakers": "यह पता नहीं चल सका कि कौन बोल रहा था।",
        "no_transcript": "बोली मिली, लेकिन कोई शब्द पहचाने नहीं जा सके।",
    },
}

_TEMPLATES: dict[tuple[str, str], tuple[str, str]] = {
    ("report_ready", "en"): (
        "Your $recording report is ready: $title",
        'The $recording report for "$title" is ready.\n\nOpen it here: $link\n\nYou need to sign in to see it.',
    ),
    ("report_ready", "hi"): (
        "आपकी $recording की रिपोर्ट तैयार है: $title",
        '"$title" की $recording रिपोर्ट तैयार है।\n\nयहाँ देखें: $link\n\nदेखने के लिए साइन इन करना होगा।',
    ),
    ("needs_attention", "en"): (
        "A $recording needs attention: $title",
        '"$title" could not be completed automatically.\n\nReason ($reason): $explanation\n\nReview it here: $link',
    ),
    ("needs_attention", "hi"): (
        "एक $recording पर ध्यान देना है: $title",
        '"$title" अपने-आप पूरी नहीं हो सकी।\n\nकारण ($reason): $explanation\n\nयहाँ देखें: $link',
    ),
}


def render_email(
    kind: EmailKind,
    language: str,
    *,
    labels: Mapping[str, str],
    link: str,
    recording_title: str,
    reason: str | None = None,
) -> RenderedEmail:
    """Subject, plain text and HTML for one email. There is deliberately no way to pass a score or a quote."""
    lang = language if language in LANGUAGES else "en"
    subject_t, body_t = _TEMPLATES[(kind, lang)]
    recording_word = labels.get("recording", "recording")
    if lang == "en":
        recording_word = recording_word.lower()
    values = {
        "recording": recording_word,
        "title": recording_title,
        "link": link,
        "reason": reason or "unknown",
        "explanation": REASONS[lang].get(reason or "")
        or ("See the recording for details." if lang == "en" else "विवरण रिकॉर्डिंग में देखें।"),
    }
    subject = Template(subject_t).substitute(values)
    text = Template(body_t).substitute(values)
    escaped = {k: html.escape(v) for k, v in values.items()}
    body_html = "".join(f"<p>{line}</p>" for line in Template(body_t).substitute(escaped).split("\n\n")).replace(
        escaped["link"], f'<a href="{escaped["link"]}">{escaped["link"]}</a>'
    )
    return RenderedEmail(lang, subject, text, f'<!doctype html><html lang="{lang}"><body>{body_html}</body></html>')
