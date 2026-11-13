"""What the staff member said, right and wrong (owner, 2026-11-13: sales and support managers could not tell from the
scores what the agent said well or badly).

From the redacted transcript and the tenant's approved product information the model lists the call's key moments,
each with the quote it rests on:

- kind: "plus" (done or said well) or "drawback" (wrong, missed or badly handled);
- text: what happened and why it matters, in English, at most 30 words;
- fact: for a statement of product fact (price, feature, warranty, terms, policy) the check against the approved
  information: "matches" or "contradicts" (both with that entry's `product_info_id`), or "not_covered" (no entry
  says; never called wrong). null for moments that are not product statements. A contradicted fact is always a
  drawback.

The list is the call's evaluation, not private coaching: managers see it as well as the person analysed (owner,
2026-11-13). It is written for sales and support calls, whether or not the scores verified.

Golden rule 5 as for the deal card (sales.QuoteCheck): every quote is found in the transcript and stored in its own
wording with that utterance's times; an answer with problems is re-asked once with them, then moments whose quote is
still not found are left out. An id that is not one of the entries given, or a verdict that does not fit its id
("contradicts" without an id, "not_covered" with one, a contradicted "plus"), is refused like any invalid answer, so
a moment never claims a check against information that was not approved. If the second answer is still invalid
there is no list; the scores and the rest of the report are unaffected.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from sabha_analytics.grounding import PreparedTranscript
from sabha_analytics.next_time import MAX_PRODUCT_INFO, ProductFact, render_product_info
from sabha_analytics.sales import Evidence, QuoteCheck, quoted_item
from sabha_analytics.scoring import (
    PROMPTS_DIR,
    TASK_SYNTHESIS,
    CallRecord,
    Problem,
    Prompt,
    call_model,
    feedback_text,
    load_prompt,
)

MAX_MOMENTS = 10
MAX_WORDS = 30
KINDS = ("plus", "drawback")
FACTS = ("matches", "contradicts", "not_covered")

Kind = Literal["plus", "drawback"]
Fact = Literal["matches", "contradicts", "not_covered"]


@dataclass(frozen=True, slots=True)
class Moment:
    kind: Kind
    text: str
    evidence: Evidence
    fact: Fact | None = None
    product_info_id: str | None = None

    def to_record(self) -> dict[str, Any]:
        e = self.evidence
        record: dict[str, Any] = {
            "kind": self.kind,
            "text": self.text,
            "evidence": {"quote": e.quote, "utterance_id": e.utterance_id, "start_ms": e.start_ms, "end_ms": e.end_ms},
            "fact": self.fact,
        }
        if self.product_info_id is not None:
            record["product_info_id"] = self.product_info_id
        return record


@dataclass(frozen=True, slots=True)
class Moments:
    items: tuple[Moment, ...]
    left_out: int = 0

    def to_record(self) -> dict[str, Any]:
        ordered = sorted(self.items, key=lambda m: m.evidence.start_ms)  # in the order they happened
        return {"items": [m.to_record() for m in ordered], "left_out": self.left_out}


@dataclass(frozen=True, slots=True)
class MomentsOutcome:
    moments: Moments | None
    attempts: int
    failure_reasons: tuple[str, ...]
    calls: tuple[CallRecord, ...]
    prompts: tuple[Prompt, ...]


def moments_schema() -> dict[str, Any]:
    item = quoted_item({
        "kind": {"type": "string", "enum": list(KINDS)},
        "text": {"type": "string", "minLength": 1},
        "fact": {"anyOf": [{"type": "null"}, {"type": "string", "enum": list(FACTS)}]},
        "product_info_id": {"type": ["string", "null"]},
    })  # fmt: skip
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["moments"],
        "properties": {"moments": {"type": "array", "minItems": 1, "maxItems": MAX_MOMENTS, "items": item}},
    }


_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def validate_moments(
    data: object, *, transcript: PreparedTranscript, product_ids: frozenset[str] = frozenset()
) -> tuple[Moments | None, list[Problem]]:
    """The moments (verified quotes only) and every problem found; None when the answer's shape, texts or product
    checks are invalid. Quote problems alone still give a list, without those moments."""
    if not isinstance(data, dict) or set(data) != {"moments"} or not isinstance(data["moments"], list):
        return None, [Problem("invalid_output", 'Answer with exactly {"moments": [...]}.')]
    raw_items = data["moments"]
    if not 1 <= len(raw_items) <= MAX_MOMENTS:
        return None, [Problem("invalid_shape", f"Give between 1 and {MAX_MOMENTS} moments.")]
    check = QuoteCheck(transcript)
    kept: list[Moment] = []
    for i, raw in enumerate(raw_items, 1):
        where = f"moment {i}"
        if not isinstance(raw, dict):
            check.problems.append(Problem("invalid_shape", f"{where} must be an object."))
            continue
        kind, fact, pid = raw.get("kind"), raw.get("fact"), raw.get("product_info_id")
        if kind not in KINDS or (fact is not None and fact not in FACTS):
            check.problems.append(Problem("invalid_shape", f"{where}: kind is plus or drawback; fact is null, "
                                                           "matches, contradicts or not_covered."))  # fmt: skip
            continue
        if pid is not None and pid not in product_ids:
            check.problems.append(Problem(
                "unknown_product_info",
                f"{where}: product_info_id {pid!r} is not one of the approved entries; use one of their ids or null.",
            ))  # fmt: skip
            continue
        if fact in ("matches", "contradicts") and pid is None:
            check.problems.append(Problem("fact_without_entry", f"{where}: a fact that {fact} the approved "
                                          "information needs that entry's product_info_id."))  # fmt: skip
            continue
        if (fact is None or fact == "not_covered") and pid is not None:
            check.problems.append(Problem("entry_without_fact", f"{where}: give product_info_id only with fact "
                                          "matches or contradicts."))  # fmt: skip
            continue
        if fact == "contradicts" and kind != "drawback":
            check.problems.append(Problem("contradiction_as_plus", f"{where}: a statement that contradicts the "
                                          "approved information is a drawback."))  # fmt: skip
            continue
        text = check.text(f"{where} text", raw.get("text"), MAX_WORDS)
        if text is not None and _DEVANAGARI.search(text):
            check.problems.append(Problem(
                "not_english", f"{where}: write the text in English; only the quote stays as it was spoken."
            ))  # fmt: skip
            continue
        evidence = check.evidence(where, raw)
        if text is not None and evidence is not None:
            kept.append(Moment(cast(Kind, kind), text.strip(), evidence, cast(Fact | None, fact), pid))
    if any(p.code != "quote_not_found" for p in check.problems):
        return None, check.problems
    return Moments(tuple(kept), check.unverified), check.problems


def write_moments(
    transcript: PreparedTranscript,
    *,
    staff_role: str,
    conversation: str,
    model: Any,
    product_info: Sequence[ProductFact] = (),
    prompts_dir: Path = PROMPTS_DIR,
) -> MomentsOutcome:
    """Ask for the call's moments (module docstring). `staff_role` names the person analysed ("sales rep",
    "support agent"); `conversation` the kind of call ("sales call or meeting", "support call")."""
    facts = tuple(product_info)[:MAX_PRODUCT_INFO]
    system_p, request_p = load_prompt("moments.system", prompts_dir), load_prompt("moments.request", prompts_dir)
    system = system_p.render(staff_role=staff_role, conversation=conversation)
    prefix = request_p.render(product_info=render_product_info(facts), transcript=transcript.render())
    ids = frozenset(f.id for f in facts)
    calls: list[CallRecord] = []
    problems: list[Problem] = []
    found: Moments | None = None
    for attempt in (1, 2):
        data = call_model(
            model,
            task=TASK_SYNTHESIS,
            system=system,
            prefix=prefix,
            request=feedback_text(problems) if problems else "",
            json_schema=moments_schema(),
            attempt=attempt,
            keys=(),
            calls=calls,
        )
        found, problems = validate_moments(data, transcript=transcript, product_ids=ids)
        if found is not None and not problems:
            return MomentsOutcome(found, attempt, (), tuple(calls), (system_p, request_p))
    reasons = tuple(dict.fromkeys(p.code for p in problems))
    return MomentsOutcome(found, 2, reasons, tuple(calls), (system_p, request_p))
