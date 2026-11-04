"""The small-LLM tie-breaker for speaker roles (plan task P3.6), used only when the heuristics are unsure.

sabha_asr.roles calls it for a low-confidence result with the opening of the recording (first 2 minutes, speaker
by speaker). It asks the `roles.tiebreak` task (small tier) through sabha_llm's gateway, which redacts PII before
anything leaves our servers (golden rule 8) and records the call. The model names ONE speaker as the staff member
(teacher or receptionist) or says "unsure"; everyone else gets the other role.

Returns None (so the recording goes to NEEDS_REVIEW with `unclear_roles`) when the model is unsure, gives
confidence below the threshold the caller applies, or the call fails. A failed call is logged with its reason: it
never turns into a guess (golden rule 7).

With guidance (a type with an evidence profile, sabha_asr.role_evidence; support calls), the model is told what such
conversations look like and must answer with its evidence: quotes for the staff member and for the other side, each
naming its speaker, and whether a person should check. An answer is used only if it does not ask for review and at
least one staff quote by the staff speaker and one other-side quote by another speaker are found in what those
speakers said (placeholders in a quote stand for words the redaction hid). Unfound quotes are dropped, never shown.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sabha_analytics.scoring import WALK_IN_KIND
from sabha_asr.roles import VISITOR, RoleAssignment, SpeakerRole, TieBreakRequest, normalise_text
from sabha_llm.errors import LlmError
from sabha_llm.gateway import Gateway
from sabha_llm.types import Message

log = logging.getLogger("sabha.workers.roles")

TASK = "roles.tiebreak"
PROMPT_VERSION = "roles.tiebreak@3"
METHOD = "llm_tiebreak"
UNSURE = "unsure"
MAX_OPENING_CHARS = 6_000
MAX_QUOTES = 4
_PLACEHOLDER = re.compile(r"\[[A-Z_]+_\d+\]")

SYSTEM = (
    "You read the opening of a recorded {kind} and say which speaker is the {staff}. Everyone else is the {other}. "
    "Speakers are anonymous labels. Placeholders such as [NAME_1] hide private details. Answer with JSON only. "
    'If the text does not make it clear, answer "unsure" rather than guess.'
)
KINDS = {"teaching": "classroom lesson", "reception": "front-desk phone call",
         "sales": "in-person sales meeting or product demo", "support": "customer support phone call"}  # fmt: skip


def _evidence_schema(labels: list[str]) -> dict[str, Any]:
    quotes = {
        "type": "array",
        "maxItems": MAX_QUOTES,
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["speaker", "quote"],
            "properties": {"speaker": {"enum": labels}, "quote": {"type": "string", "minLength": 1}},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["staff_speaker", "confidence", "staff_evidence", "other_evidence", "needs_review"],
        "properties": {
            "staff_speaker": {"enum": [*labels, UNSURE]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "staff_evidence": quotes,
            "other_evidence": quotes,
            "needs_review": {"type": "boolean"},
        },
    }


def _said(request: TieBreakRequest) -> dict[str, str]:
    said: dict[str, list[str]] = {}
    for label, text in request.opening:
        said.setdefault(label, []).append(normalise_text(text))
    return {label: " ".join(texts) for label, texts in said.items()}


def _found(quote: str, text: str) -> bool:
    """Whether every piece of the quote between placeholders is in the speaker's own words."""
    pieces = [normalise_text(piece) for piece in _PLACEHOLDER.split(quote)]
    pieces = [piece for piece in pieces if piece]
    return bool(pieces) and all(f" {piece} " in f" {text} " for piece in pieces)


def _verified(answer: dict[str, Any], staff: str, said: dict[str, str]) -> tuple[dict[str, str], ...] | None:
    """The quotes found in what their speakers said; None unless both sides have one (module docstring)."""
    kept = []
    for side, key in (("staff", "staff_evidence"), ("other", "other_evidence")):
        for item in answer.get(key) or []:
            if not isinstance(item, dict):
                continue
            speaker, quote = item.get("speaker"), item.get("quote")
            right_side = (speaker == staff) == (side == "staff")
            if (
                isinstance(speaker, str)
                and isinstance(quote, str)
                and right_side
                and _found(quote, said.get(speaker, ""))
            ):
                kept.append({"speaker": speaker, "side": side, "quote": quote})
    sides = {item["side"] for item in kept}
    return tuple(kept) if sides == {"staff", "other"} else None


def _opening(request: TieBreakRequest) -> str:
    lines = [f"{label}: {text}" for label, text in request.opening]
    text = "\n".join(lines)
    return text[:MAX_OPENING_CHARS]


class LlmRoleTieBreaker:
    def __init__(self, gateway: Gateway, tenant_id: str, recording_id: str) -> None:
        self._gateway = gateway
        self._tenant_id = tenant_id
        self._recording_id = recording_id

    def __call__(self, request: TieBreakRequest) -> RoleAssignment | None:
        staff_role, other_role = request.rubric_roles
        labels = sorted(request.heuristic.speakers)
        if not labels or not request.opening:
            return None
        guided = bool(request.guidance)
        schema: dict[str, Any] = (
            _evidence_schema(labels)
            if guided
            else {
                "type": "object",
                "additionalProperties": False,
                "required": ["staff_speaker", "confidence"],
                "properties": {
                    "staff_speaker": {"enum": [*labels, UNSURE]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            }
        )
        kind = WALK_IN_KIND if other_role == VISITOR else KINDS.get(request.recording_type, "conversation")
        system = SYSTEM.format(kind=kind, staff=staff_role, other=other_role)
        works_for = (
            f"The {staff_role} works for {request.organisation[0]} (it may be said or written as "
            f"{', '.join(request.organisation)}); the {other_role} does not.\n"
            if request.organisation
            else ""
        )
        guidance = ""
        if guided:
            organisation = request.organisation[0] if request.organisation else "the organisation"
            guidance = request.guidance.format(organisation=organisation) + "\n"
        ask = (
            f'Which speaker is the {staff_role}? Give staff_speaker (a label, or "{UNSURE}"), your confidence, up '
            f"to {MAX_QUOTES} quotes copied word for word that show who is the {staff_role} (staff_evidence) and who "
            f"is the {other_role} (other_evidence), each with the speaker who said it, and needs_review: true if a "
            "person should check."
            if guided
            else f'Which speaker is the {staff_role}? Give staff_speaker (a label, or "{UNSURE}") and your confidence.'
        )
        user = (
            f"{guidance}{works_for}Speakers: {', '.join(labels)}.\n"
            f"Opening, one line per stretch of one speaker:\n\n{_opening(request)}\n\n{ask}"
        )
        try:
            result = self._gateway.complete(
                task=TASK, messages=[Message("system", system), Message("user", user)], tenant_id=self._tenant_id,
                recording_id=self._recording_id, json_schema=schema, prompt_version=PROMPT_VERSION,
            )  # fmt: skip
        except LlmError as exc:
            log.warning("role tie-break call failed; the recording will ask for review",
                        extra={"recording_id": self._recording_id, "reason": str(exc)[:300]})  # fmt: skip
            return None
        answer = result.json if isinstance(result.json, dict) else {}
        staff = answer.get("staff_speaker")
        confidence = answer.get("confidence")
        if staff not in labels or not isinstance(confidence, int | float) or isinstance(confidence, bool):
            return None
        quotes: tuple[dict[str, str], ...] = ()
        if guided:
            if answer.get("needs_review") is not False:
                return None
            verified = _verified(answer, staff, _said(request))
            if verified is None:
                log.info("role tie-break quotes not found in the transcript; the recording will ask for review",
                         extra={"recording_id": self._recording_id})  # fmt: skip
                return None
            quotes = verified
        return RoleAssignment(
            {
                label: SpeakerRole(staff_role if label == staff else other_role, round(float(confidence), 3), METHOD)
                for label in labels
            },
            ai_evidence=quotes,
        )
