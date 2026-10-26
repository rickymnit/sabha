"""The small-LLM tie-breaker for speaker roles (plan task P3.6), used only when the heuristics are unsure.

sabha_asr.roles calls it for a low-confidence result with the opening of the recording (first 2 minutes, speaker
by speaker). It asks the `roles.tiebreak` task (small tier) through sabha_llm's gateway, which redacts PII before
anything leaves our servers (golden rule 8) and records the call. The model names ONE speaker as the staff member
(teacher or receptionist) or says "unsure"; everyone else gets the other role.

Returns None (so the recording goes to NEEDS_REVIEW with `unclear_roles`) when the model is unsure, gives
confidence below the threshold the caller applies, or the call fails. A failed call is logged with its reason: it
never turns into a guess (golden rule 7).
"""

from __future__ import annotations

import logging
from typing import Any

from sabha_asr.roles import RoleAssignment, SpeakerRole, TieBreakRequest
from sabha_llm.errors import LlmError
from sabha_llm.gateway import Gateway
from sabha_llm.types import Message

log = logging.getLogger("sabha.workers.roles")

TASK = "roles.tiebreak"
PROMPT_VERSION = "roles.tiebreak@1"
METHOD = "llm_tiebreak"
UNSURE = "unsure"
MAX_OPENING_CHARS = 6_000

SYSTEM = (
    "You read the opening of a recorded {kind} and say which speaker is the {staff}. Everyone else is the {other}. "
    "Speakers are anonymous labels. Placeholders such as [NAME_1] hide private details. Answer with JSON only. "
    'If the text does not make it clear, answer "unsure" rather than guess.'
)
KINDS = {"teaching": "classroom lesson", "reception": "front-desk phone call",
         "sales": "in-person sales meeting or product demo"}  # fmt: skip


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
        schema: dict[str, Any] = {
            "type": "object",
            "additionalProperties": False,
            "required": ["staff_speaker", "confidence"],
            "properties": {
                "staff_speaker": {"enum": [*labels, UNSURE]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
        }
        system = SYSTEM.format(kind=KINDS.get(request.recording_type, "conversation"), staff=staff_role,
                               other=other_role)  # fmt: skip
        user = (
            f"Speakers: {', '.join(labels)}.\nOpening, one line per stretch of one speaker:\n\n{_opening(request)}\n\n"
            f'Which speaker is the {staff_role}? Give staff_speaker (a label, or "{UNSURE}") and your confidence.'
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
        return RoleAssignment(
            {
                label: SpeakerRole(staff_role if label == staff else other_role, round(float(confidence), 3), METHOD)
                for label in labels
            }
        )
