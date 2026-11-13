"""Coaching for the next conversation (founder's Sales Executive dashboard doc, 2026-11-12; sales rubric v0.4).

From the redacted transcript and the verified rubric scores the model writes, every item with a quote it rests on:

- question_to_ask: a question the rep could have asked, at most 25 words, at the moment it was needed, or null;
- explain_better: what to explain better next time and how, at most 30 words, where it came up, or null;
- practice_point: the one thing to practise in the next call, at most 25 words.

It runs only for a rubric whose `output` lists `practice_point`, and only when there are verified scores. The
coaching is private to the person analysed (the API hides it from everyone else).

Approved product information (founder's doc, 2026-11-12): the tenant's active entries are given to the model as the
only source for product facts. When the client asked about a product topic, explain_better may name one entry by
its id (`product_info_id`) for the rep to review; an id that is not one of the entries given is refused like any
invalid answer, so coaching can never point at information that was not approved. Entry texts are company content,
not transcript text, so they are masked for pattern PII (sabha_llm.redact.redact_again) before the prompt.

Golden rule 5 applies as for the deal card (sales.QuoteCheck): every quote must be found in the transcript and is
stored in the transcript's own wording with that utterance's times. A failing answer is re-asked once with the
problems; then items whose quote is still not found are left out, never shown. If the second answer is not valid at
all there is no coaching; the scores and the rest of the report are not affected and nothing goes to review.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sabha_analytics.grounding import PreparedTranscript
from sabha_analytics.sales import Evidence, QuoteCheck, quoted_item
from sabha_analytics.scoring import (
    PROMPTS_DIR,
    TASK_SYNTHESIS,
    CallRecord,
    DimensionResult,
    JudgeModel,
    Problem,
    Prompt,
    call_model,
    feedback_text,
    load_prompt,
)
from sabha_llm.redact import redact_again

OUTPUT_SECTION = "practice_point"
"""A rubric asks for this coaching by listing this section in its `output`."""
KEYS = ("question_to_ask", "explain_better", "practice_point")
MAX_PRODUCT_INFO = 80  # the API allows as many active entries (product_info.MAX_ACTIVE)


@dataclass(frozen=True, slots=True)
class ProductFact:
    """One approved product information entry, as given to the model."""

    id: str
    title: str
    body: str


MAX_WORDS = {"question_to_ask": 25, "explain_better": 30, "practice_point": 25}


@dataclass(frozen=True, slots=True)
class Tip:
    text: str
    evidence: Evidence
    product_info_id: str | None = None  # explain_better only: the approved entry to review


@dataclass(frozen=True, slots=True)
class NextTime:
    question_to_ask: Tip | None
    explain_better: Tip | None
    practice_point: Tip | None  # None only when its quote could not be verified
    left_out: int = 0

    def to_record(self) -> dict[str, Any]:
        def tip(t: Tip | None) -> dict[str, Any] | None:
            if t is None:
                return None
            e = t.evidence
            evidence = {"quote": e.quote, "utterance_id": e.utterance_id, "start_ms": e.start_ms, "end_ms": e.end_ms}
            record: dict[str, Any] = {"text": t.text, "evidence": evidence}
            if t.product_info_id is not None:
                record["product_info_id"] = t.product_info_id
            return record

        return {
            "question_to_ask": tip(self.question_to_ask),
            "explain_better": tip(self.explain_better),
            "practice_point": tip(self.practice_point),
            "left_out": self.left_out,
        }


@dataclass(frozen=True, slots=True)
class NextTimeOutcome:
    next_time: NextTime | None
    attempts: int
    failure_reasons: tuple[str, ...]
    calls: tuple[CallRecord, ...]
    prompts: tuple[Prompt, ...]


def next_time_schema() -> dict[str, Any]:
    item = quoted_item({"text": {"type": "string", "minLength": 1}})
    explain = quoted_item({"text": {"type": "string", "minLength": 1}, "product_info_id": {"type": ["string", "null"]}})
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(KEYS),
        "properties": {
            "question_to_ask": {"anyOf": [{"type": "null"}, item]},
            "explain_better": {"anyOf": [{"type": "null"}, explain]},
            "practice_point": item,
        },
    }


_DEVANAGARI = re.compile(r"[\u0900-\u097F]")  # the rep reads coaching in English (prompt rule)


def validate_next_time(
    data: object, *, transcript: PreparedTranscript, product_ids: frozenset[str] = frozenset()
) -> tuple[NextTime | None, list[Problem]]:
    """The coaching (verified items only) and every problem found; None when the answer's shape or texts are invalid.
    Quote problems alone still give coaching, without those items."""
    if not isinstance(data, dict) or set(data) != set(KEYS):
        return None, [Problem("invalid_output", f"Answer with exactly {', '.join(KEYS)}.")]
    check = QuoteCheck(transcript)
    kept: dict[str, Tip | None] = {}
    for key in KEYS:
        raw = data[key]
        kept[key] = None
        if raw is None:
            if key == "practice_point":
                check.problems.append(Problem("invalid_shape", "practice_point is required."))
            continue
        if not isinstance(raw, dict):
            check.problems.append(Problem("invalid_shape", f"{key} must be null or {{text, quote...}}."))
            continue
        text = check.text(key, raw.get("text"), MAX_WORDS[key])
        if text is not None and _DEVANAGARI.search(text):
            check.problems.append(Problem(
                "not_english", f"{key}: write the text in English; only the quote stays as it was spoken.",
            ))  # fmt: skip
            continue
        evidence = check.evidence(key, raw)
        product_id = raw.get("product_info_id") if key == "explain_better" else None
        if product_id is not None and product_id not in product_ids:
            check.problems.append(Problem(
                "unknown_product_info",
                f"{key}: product_info_id {product_id!r} is not one of the approved entries; use one of their ids or "
                "null.",
            ))  # fmt: skip
            continue
        if text is not None and evidence is not None:
            kept[key] = Tip(text.strip(), evidence, product_id)
    if any(p.code != "quote_not_found" for p in check.problems):
        return None, check.problems
    found = NextTime(kept["question_to_ask"], kept["explain_better"], kept["practice_point"], check.unverified)
    return found, check.problems


def _scores(dimensions: Sequence[DimensionResult]) -> str:
    rows = [f"- {d.name}: {d.score}" for d in dimensions if d.verified and d.score is not None]
    return "\n".join(rows) or "- (none)"


def render_product_info(facts: Sequence[ProductFact]) -> str:
    if not facts:
        return "(none: give no product facts and leave product_info_id null)"
    return "\n".join(
        f"[{f.id}] {redact_again(' '.join(f.title.split()))}: {redact_again(' '.join(f.body.split()))}" for f in facts
    )


def write_next_time(
    transcript: PreparedTranscript,
    *,
    dimensions: Sequence[DimensionResult],
    model: JudgeModel,
    product_info: Sequence[ProductFact] = (),
    prompts_dir: Path = PROMPTS_DIR,
) -> NextTimeOutcome:
    """Ask for the coaching for the next conversation (module docstring)."""
    facts = tuple(product_info)[:MAX_PRODUCT_INFO]
    system_p, request_p = load_prompt("next_time.system", prompts_dir), load_prompt("next_time.request", prompts_dir)
    prefix = request_p.render(scores=_scores(dimensions), product_info=render_product_info(facts),
                              transcript=transcript.render())  # fmt: skip
    ids = frozenset(f.id for f in facts)
    calls: list[CallRecord] = []
    problems: list[Problem] = []
    found: NextTime | None = None
    for attempt in (1, 2):
        data = call_model(
            model,
            task=TASK_SYNTHESIS,
            system=system_p.render(),
            prefix=prefix,
            request=feedback_text(problems) if problems else "",
            json_schema=next_time_schema(),
            attempt=attempt,
            keys=(),
            calls=calls,
        )
        found, problems = validate_next_time(data, transcript=transcript, product_ids=ids)
        if found is not None and not problems:
            return NextTimeOutcome(found, attempt, (), tuple(calls), (system_p, request_p))
    reasons = tuple(dict.fromkeys(p.code for p in problems))
    return NextTimeOutcome(found, 2, reasons, tuple(calls), (system_p, request_p))
