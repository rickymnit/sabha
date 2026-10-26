"""Rubric scoring calls with grounded evidence (plan task P5.6).

The LLM only judges (golden rule 5): it picks an anchor 1-5 per rubric dimension and must back each score with
quotes from the transcript. Every quote is checked by sabha_analytics.grounding before anything is kept. Numbers
(talk share, question counts, pace, ...) are computed in code (P5.5) and passed in as context, never re-derived.

Seams (agreed interfaces; this module imports neither sabha_analytics.rubric nor .metrics):

- `RubricSpec` / `DimensionSpec`: read-only Protocols any rubric object satisfies (the P5.4 Pydantic models do).
- Computed metrics: records {"key", "value", "unit", "definition"} (P5.5); extra keys are kept.
- `JudgeModel`: the one method the P5.1 gateway must provide. The gateway owns provider routing by `task`
  (`TASK_SCORING` and `TASK_SYNTHESIS`, the "mid tier"), temperature 0, retries on transport errors, budgets,
  prompt caching of `system` plus `cache_prefix`, Langfuse tracing and, as a second line of defence, PII redaction
  (golden rule 8). Fallback to another model happens only when configured and is visible in `model_id` (rule 7).
  Callers here already send only redacted text: the transcript is redacted in `prepare_transcript`, and
  `check_prompt_redacted` refuses any prompt in which the pattern recognisers still find a phone, Aadhaar, PAN or
  email. NOTE for P5.1: sabha_llm.redact.redact() raises on text that already contains placeholders, so the
  gateway must not blindly re-redact these prompts; see the open question in the P5.6 hand-over.

Calls (deterministic):

- Dimensions are grouped in rubric order into ceil(n / 3) contiguous groups, at most 3, sizes as even as possible
  (earlier groups take the extra one): the 6-dimension teaching rubric makes 2 calls of 3, a 3-dimension rubric 1
  call, 7-9 dimensions 3 calls, more than 9 still 3 calls. Neighbouring dimensions in a rubric are related
  (clarity and examples; checks and questioning), so one call sees related anchors together, and fewer calls
  mean fewer tokens because the long transcript is re-read once per call (from cache).
- Every call has the same `system` text and starts with the same context (rubric with all dimensions, metrics,
  redacted transcript with utterance ids and original times): that is `cache_prefix`, so every call and re-ask
  after the first reads it from the prompt cache. Only the short task part at the end differs.
- The model answers {"dimensions": [{key, score, rationale, evidence: [{quote, utterance_id, start_ms}]}]}.
  `validate` checks: exactly the requested keys, once each; score an integer 1-5; rationale non-blank, at most
  60 words, no placeholder (a placeholder would name a student once un-redacted, golden rule 10); evidence at
  least `min_quotes` items of the right shape; every quote verified by grounding; at least `min_quotes` DISTINCT
  verified passages (the same passage twice does not count twice).
- Not applicable: a dimension whose rubric entry has `not_applicable_when` (reception's escalation handling: a call
  with nothing to escalate) may be answered with `score: null`. The model must still give a rationale and at least
  ONE verified quote showing what the conversation was about (golden rule 5: no unsupported claim, including
  "nothing to escalate"). For any other dimension a null score is a problem like any other.
- A dimension that fails any check is re-asked ONCE, alone, with the specific problems as feedback. If it fails
  again it is kept with verified=False, no score, no rationale and no evidence: it is excluded from the overall
  score and from the UI. Quotes are never dropped or fixed to make a dimension pass.

Prompts live in packages/analytics/prompts/*.md. The first line of each is `<!-- version: N -->`; the SHA-256 of
the whole file is stored with every result, so any edit is traceable even if someone forgets to bump the version.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Any, Protocol

from sabha_analytics.grounding import (
    MIN_QUOTE_WORDS,
    GroundingResult,
    PreparedTranscript,
    verify_quote,
)
from sabha_llm.redact import redact

TASK_SCORING = "analysis.scoring"
"""Gateway task name of a scoring call (routing tier chosen by P5.1)."""
TASK_SYNTHESIS = "analysis.synthesis"
"""Gateway task name of the synthesis call (mid tier, P5.7)."""

MAX_DIMENSIONS_PER_CALL = 3
MAX_CALLS = 3
MAX_RATIONALE_WORDS = 60
SCORE_MIN = 1
SCORE_MAX = 5

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
"""packages/analytics/prompts. Not inside the Python package: deployments must ship the source tree (Docker does)."""

PLACEHOLDER = re.compile(r"\[[A-Za-z]{2,20}_[0-9]+\]")


# --- seams -------------------------------------------------------------------------------------------------------


class DimensionSpec(Protocol):
    """One rubric dimension, as the P5.4 rubric model exposes it."""

    @property
    def key(self) -> str: ...
    @property
    def name(self) -> str: ...
    @property
    def weight(self) -> float: ...
    @property
    def definition(self) -> str: ...
    @property
    def min_quotes(self) -> int: ...
    @property
    def anchors(self) -> Mapping[int, str]: ...
    @property
    def examples(self) -> Mapping[int, str]: ...


class RubricSpec(Protocol):
    """A rubric version, as the P5.4 rubric model exposes it."""

    @property
    def id(self) -> str: ...
    @property
    def version(self) -> str: ...
    @property
    def dimensions(self) -> Sequence[DimensionSpec]: ...
    @property
    def output_values(self) -> Mapping[str, Sequence[str]] | None: ...
    @property
    def roles(self) -> Sequence[str]: ...


# What each conversation type is called in the prompts. The rubric's first role is the person analysed; the second
# names everyone else, who are context only (golden rule 10 for students; the same care for callers and customers).
CONVERSATION_KINDS = {
    "teaching": "school lesson",
    "reception": "front-desk call",
    "sales": "sales meeting",
    "meeting": "team meeting",
    "counselling": "counselling session",
}


def prompt_roles(rubric_id: str, roles: Sequence[str]) -> dict[str, str]:
    """$conversation, $staff_role and $others for the system prompts, from the rubric."""
    kind = rubric_id.split(".", 1)[0]
    staff = roles[0] if roles else "staff member"
    others = roles[1] if len(roles) > 1 else "others"
    return {
        "conversation": CONVERSATION_KINDS.get(kind, "conversation"),
        "staff_role": staff.replace("_", " "),
        "others": others.replace("_", " "),
    }


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Tokens of one or more calls, as the provider reported them. Cost is computed by the gateway, not here."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
        )

    def to_record(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }


@dataclass(frozen=True, slots=True)
class JudgeResponse:
    """What `JudgeModel.complete_json` returns.

    `data` is the parsed JSON of the model's answer, or None if the answer was not valid JSON (the gateway does not
    raise for that: the caller treats it as a failed attempt and re-asks once). `model_id` is the model that
    actually answered, including its version.
    """

    data: object
    model_id: str
    usage: TokenUsage


class JudgeModel(Protocol):
    """The LLM seam. P5.1's gateway implements it; tests use a fake. Nothing here calls a provider directly.

    - `task`: TASK_SCORING or TASK_SYNTHESIS; the gateway routes it to a model tier and applies its budget.
    - `system`: stable instructions (same for every call of a task and prompt version).
    - `messages`: [{"role": "user" | "assistant", "content": str}, ...]; already redacted.
    - `json_schema`: the JSON Schema the answer must follow (for structured output); the caller validates again.
    - `cache_prefix`: when not None, `messages[0]["content"]` starts with exactly this text; the gateway caches
      `system` plus this prefix (a cache breakpoint after it).
    Temperature is 0. Transport errors are retried inside the gateway; if it gives up it raises, and the analyze
    task fails visibly (no silent fallback, golden rule 7).
    """

    def complete_json(
        self,
        *,
        task: str,
        system: str,
        messages: Sequence[Mapping[str, str]],
        json_schema: Mapping[str, Any],
        cache_prefix: str | None,
    ) -> JudgeResponse: ...


@dataclass(frozen=True, slots=True)
class CallRecord:
    """One model call, for usage accounting and the report."""

    task: str
    attempt: int
    """1 for a first call, 2 for a re-ask."""
    keys: tuple[str, ...]
    """Dimension keys asked for (empty for synthesis)."""
    model_id: str
    usage: TokenUsage


# --- prompts -----------------------------------------------------------------------------------------------------

_VERSION_LINE = re.compile(r"<!-- version: ([0-9]+) -->")


@dataclass(frozen=True, slots=True)
class Prompt:
    """A prompt file: `body` is the text after the version line; `sha256` is of the whole file."""

    name: str
    version: str
    sha256: str
    body: str = field(repr=False)

    def render(self, **values: str) -> str:
        """`body` with $name placeholders filled. Raises KeyError for a missing value."""
        return Template(self.body).substitute(values).strip("\n")

    def to_record(self) -> dict[str, str]:
        return {"version": self.version, "sha256": self.sha256}


def load_prompt(name: str, directory: Path = PROMPTS_DIR) -> Prompt:
    """Load `<directory>/<name>.md`. Raises ValueError if its first line is not `<!-- version: N -->`."""
    data = (directory / f"{name}.md").read_bytes()
    text = data.decode("utf-8")
    first, _, body = text.partition("\n")
    found = _VERSION_LINE.fullmatch(first.strip())
    if found is None:
        raise ValueError(f"prompt {name!r} must start with a line '<!-- version: N -->'")
    return Prompt(name=name, version=found.group(1), sha256=hashlib.sha256(data).hexdigest(), body=body)


# --- PII guard ---------------------------------------------------------------------------------------------------


class PromptNotRedacted(ValueError):
    """A prompt still contains something the PII recognisers match. Nothing was sent."""


def check_prompt_redacted(*texts: str) -> None:
    """Raise PromptNotRedacted if a phone, Aadhaar, PAN or email pattern matches any of `texts`.

    A defence in depth before every model call (golden rule 8): the transcript is already redacted, so this only
    fires on a bug. Names are guaranteed by construction (only redacted utterance text reaches a prompt), not
    re-checked here, because rubric examples contain fictional names that could equal a real student's name.
    Placeholders are cut out first (redact() refuses text containing them) with a line break, which the
    recognisers never read across.
    """
    for text in texts:
        found = redact(PLACEHOLDER.sub("\n\n", text)).counts
        if found:
            kinds = ", ".join(f"{kind} x{count}" for kind, count in sorted(found.items()))
            raise PromptNotRedacted(f"prompt text still contains PII-like values ({kinds}); refusing to send it")


# --- metrics -----------------------------------------------------------------------------------------------------

_METRIC_KEYS = ("key", "value", "unit", "definition")


def normalise_metrics(records: Iterable[Mapping[str, object]]) -> tuple[dict[str, Any], ...]:
    """Validate computed-metric records and return JSON-safe copies, in the given order.

    Each record needs "key" (unique, non-blank), "value", "unit" and "definition" (strings); extra keys are kept.
    Raises ValueError otherwise. Values are never changed (golden rule 5: numbers come from code).
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, Mapping) or not all(name in record for name in _METRIC_KEYS):
            raise ValueError(f"metric {index} must have the keys {', '.join(_METRIC_KEYS)}")
        key = record["key"]
        if not isinstance(key, str) or not key.strip() or key in seen:
            raise ValueError(f"metric {index} key must be a unique non-blank string")
        if not isinstance(record["unit"], str) or not isinstance(record["definition"], str):
            raise ValueError(f"metric {key!r} unit and definition must be strings")
        seen.add(key)
        try:
            copy: dict[str, Any] = json.loads(json.dumps(dict(record), ensure_ascii=False, allow_nan=False))
        except (TypeError, ValueError) as error:
            raise ValueError(f"metric {key!r} must be JSON-serialisable: {error}") from error
        out.append(copy)
    return tuple(out)


def render_metrics(metrics: Sequence[Mapping[str, Any]]) -> str:
    if not metrics:
        return "(none)"
    lines = []
    for metric in metrics:
        value = json.dumps(metric["value"], ensure_ascii=False)
        unit = f" {metric['unit']}" if metric["unit"] else ""
        lines.append(f"- {metric['key']} = {value}{unit}: {metric['definition']}")
    return "\n".join(lines)


# --- rubric ------------------------------------------------------------------------------------------------------


def check_rubric(rubric: RubricSpec) -> None:
    """Raise ValueError unless the rubric has unique keys, anchors 1-5, min_quotes >= 1 and positive weights."""
    keys = [dimension.key for dimension in rubric.dimensions]
    if not keys:
        raise ValueError("rubric has no dimensions")
    if len(set(keys)) != len(keys):
        raise ValueError("rubric dimension keys must be unique")
    for dimension in rubric.dimensions:
        if set(dimension.anchors) != set(range(SCORE_MIN, SCORE_MAX + 1)):
            raise ValueError(f"dimension {dimension.key!r} must have anchors 1 to 5")
        if dimension.min_quotes < 1:
            raise ValueError(f"dimension {dimension.key!r} must require at least one quote")
        if not dimension.weight > 0:
            raise ValueError(f"dimension {dimension.key!r} must have a positive weight")


def group_dimensions(dimensions: Sequence[DimensionSpec]) -> list[tuple[DimensionSpec, ...]]:
    """Split dimensions, in rubric order, into the calls described in the module docstring."""
    count = len(dimensions)
    if count == 0:
        return []
    groups = min(MAX_CALLS, math.ceil(count / MAX_DIMENSIONS_PER_CALL))
    size, extra = divmod(count, groups)
    out: list[tuple[DimensionSpec, ...]] = []
    start = 0
    for index in range(groups):
        end = start + size + (1 if index < extra else 0)
        out.append(tuple(dimensions[start:end]))
        start = end
    return out


def not_applicable_when(dimension: DimensionSpec) -> str | None:
    """The rubric's condition under which this dimension does not apply, or None (most dimensions)."""
    condition = getattr(dimension, "not_applicable_when", None)
    return condition if isinstance(condition, str) and condition.strip() else None


def render_dimension(dimension: DimensionSpec) -> str:
    lines = [
        f"## {dimension.key}: {dimension.name} (minimum quotes: {dimension.min_quotes})",
        "",
        f"Definition: {dimension.definition}",
        "",
        "Anchors:",
        *(f"{level}: {dimension.anchors[level]}" for level in range(SCORE_MIN, SCORE_MAX + 1)),
    ]
    condition = not_applicable_when(dimension)
    if condition is not None:
        lines += [
            "",
            f"Not applicable when: {condition} In that case answer score null, say in the rationale why it does not "
            "apply, and quote at least one line showing what the conversation was about.",
        ]
    if dimension.examples:
        lines += ["", "Examples (illustrative, not from this recording):"]
        lines += [f"{level}: {dimension.examples[level]}" for level in sorted(dimension.examples)]
    return "\n".join(lines)


# --- output schema and validation --------------------------------------------------------------------------------


def scoring_output_schema(dimensions: Sequence[DimensionSpec]) -> dict[str, Any]:
    """The JSON Schema of a scoring answer for these dimensions (given to the gateway for structured output)."""
    evidence = {
        "type": "object",
        "additionalProperties": False,
        "required": ["quote", "utterance_id", "start_ms"],
        "properties": {
            "quote": {"type": "string", "minLength": 1},
            "utterance_id": {"type": "string", "pattern": "^u[0-9]{4,}$"},
            "start_ms": {"type": "integer", "minimum": 0},
        },
    }
    item = {
        "type": "object",
        "additionalProperties": False,
        "required": ["key", "score", "rationale", "evidence"],
        "properties": {
            "key": {"enum": [dimension.key for dimension in dimensions]},
            "score": {
                "type": ["integer", "null"] if any(not_applicable_when(d) for d in dimensions) else "integer",
                "minimum": SCORE_MIN,
                "maximum": SCORE_MAX,
            },
            "rationale": {"type": "string", "minLength": 1},
            "evidence": {
                "type": "array",
                "minItems": 1
                if any(not_applicable_when(d) for d in dimensions)
                else min(dimension.min_quotes for dimension in dimensions),
                "items": evidence,
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["dimensions"],
        "properties": {
            "dimensions": {"type": "array", "minItems": len(dimensions), "maxItems": len(dimensions), "items": item}
        },
    }


@dataclass(frozen=True, slots=True)
class Problem:
    """Why an answer was refused: a stable `code` (stored) and a specific `message` (sent back to the model)."""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class Judgement:
    """One dimension's answer after validation. `ok` iff there are no problems."""

    key: str
    score: int | None
    rationale: str | None
    evidence: tuple[GroundingResult, ...]
    problems: tuple[Problem, ...]
    not_applicable: bool = False

    @property
    def ok(self) -> bool:
        return not self.problems


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _short(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def word_count(text: str) -> int:
    return len(text.split())


_ID_IN_TEXT = re.compile(r"\bu[0-9]{4,}\b")


def _check_text(where: str, text: object, max_words: int) -> list[Problem]:
    """Problems with one piece of model prose: blank, too long, containing a placeholder (golden rule 10), or
    naming an internal utterance id such as u0042 (people read this text; the report links moments itself)."""
    if not isinstance(text, str) or not text.strip():
        return [Problem("invalid_shape", f"{where} must be a non-blank string.")]
    problems = []
    words = word_count(text)
    if words > max_words:
        problems.append(Problem("too_long", f"{where} has {words} words; the limit is {max_words}."))
    if PLACEHOLDER.search(text):
        problems.append(
            Problem("placeholder_in_text", f"{where} contains a placeholder such as [STUDENT_1]; say 'a student'.")
        )
    found = _ID_IN_TEXT.search(text)
    if found:
        problems.append(
            Problem("id_in_text", f"{where} mentions {found.group()}; describe the moment in words, never by its id.")
        )
    return problems


def _verify_evidence(
    dimension: DimensionSpec, evidence: object, transcript: PreparedTranscript, min_quotes: int | None = None
) -> tuple[list[GroundingResult], list[Problem]]:
    key = dimension.key
    if not isinstance(evidence, list):
        return [], [Problem("invalid_shape", f"{key}: evidence must be a list.")]
    problems: list[Problem] = []
    results: list[GroundingResult] = []
    for number, item in enumerate(evidence, start=1):
        if (
            not isinstance(item, dict)
            or set(item) != {"quote", "utterance_id", "start_ms"}
            or not isinstance(item["quote"], str)
            or not isinstance(item["utterance_id"], str)
            or not _is_int(item["start_ms"])
            or item["start_ms"] < 0
        ):
            problems.append(
                Problem(
                    "invalid_shape",
                    f"{key}: evidence {number} must be {{quote: string, utterance_id: string, start_ms: integer}}.",
                )
            )
            continue
        result = verify_quote(transcript, item["quote"], start_ms=item["start_ms"], utterance_id=item["utterance_id"])
        results.append(result)
        quoted = _short(item["quote"])
        if result.reason == "too_short":
            problems.append(
                Problem("quote_too_short", f'{key}: quote {number} "{quoted}" is shorter than {MIN_QUOTE_WORDS} words.')
            )
        elif result.reason == "not_found":
            problems.append(
                Problem(
                    "quote_not_found",
                    f'{key}: quote {number} "{quoted}" was not found in any single transcript line. Copy the words '
                    "exactly from one line.",
                )
            )
        elif result.reason == "time_mismatch":
            problems.append(
                Problem(
                    "quote_time_mismatch",
                    f'{key}: quote {number} "{quoted}" is on line {result.utterance_id} (start_ms={result.start_ms}), '
                    f"not near the claimed start_ms={item['start_ms']}.",
                )
            )
    verified = [result for result in results if result.verified]
    distinct = {(result.utterance_id, result.original_range) for result in verified}
    if len(distinct) < len(verified):
        problems.append(Problem("duplicate_quote", f"{key}: the same passage is quoted more than once."))
    needed = dimension.min_quotes if min_quotes is None else min_quotes
    if len(distinct) < needed:
        problems.append(
            Problem(
                "too_few_quotes",
                f"{key}: needs at least {needed} different verified quotes; found {len(distinct)}.",
            )
        )
    return results, problems


def _judge_item(item: object, dimension: DimensionSpec, transcript: PreparedTranscript) -> Judgement:
    key = dimension.key
    if not isinstance(item, dict) or set(item) != {"key", "score", "rationale", "evidence"}:
        problem = Problem("invalid_shape", f"{key}: the entry must have exactly key, score, rationale and evidence.")
        return Judgement(key, None, None, (), (problem,))
    problems: list[Problem] = []
    score = item["score"]
    not_applicable = score is None and not_applicable_when(dimension) is not None
    if score is None and not not_applicable:
        problems.append(Problem("invalid_score", f"{key}: this dimension always applies; give a score from 1 to 5."))
    elif not not_applicable and (not _is_int(score) or not SCORE_MIN <= score <= SCORE_MAX):
        problems.append(Problem("invalid_score", f"{key}: score must be a whole number from 1 to 5."))
    rationale = item["rationale"]
    problems += _check_text(f"{key}: rationale", rationale, MAX_RATIONALE_WORDS)
    # Not applicable still needs evidence: at least one quote showing what the conversation was about.
    evidence, evidence_problems = _verify_evidence(
        dimension, item["evidence"], transcript, min_quotes=1 if not_applicable else None
    )
    problems += evidence_problems
    return Judgement(
        key=key,
        score=score if _is_int(score) else None,
        rationale=rationale if isinstance(rationale, str) else None,
        evidence=tuple(evidence),
        problems=tuple(problems),
        not_applicable=not_applicable,
    )


def validate(data: object, dimensions: Sequence[DimensionSpec], transcript: PreparedTranscript) -> list[Judgement]:
    """Check one scoring answer for `dimensions` (in that order); see the module docstring for the rules.

    A problem with the answer as a whole (not an object, unrequested or unattributable entries) fails every
    requested dimension, because the key set must be exactly the one asked for.
    """
    requested = [dimension.key for dimension in dimensions]
    general: list[Problem] = []
    by_key: dict[str, list[object]] = {}
    if not isinstance(data, dict) or set(data) != {"dimensions"} or not isinstance(data["dimensions"], list):
        general.append(Problem("invalid_output", 'The answer must be one JSON object {"dimensions": [...]}.'))
    else:
        for index, item in enumerate(data["dimensions"]):
            key = item.get("key") if isinstance(item, dict) else None
            if isinstance(key, str) and key in requested:
                by_key.setdefault(key, []).append(item)
            else:
                general.append(
                    Problem(
                        "unexpected_dimension",
                        f"dimensions[{index}] has key {_short(str(key), 40)!r}; answer only {', '.join(requested)}.",
                    )
                )
    judgements = []
    for dimension in dimensions:
        items = by_key.get(dimension.key, [])
        if len(items) == 1:
            judgement = _judge_item(items[0], dimension, transcript)
        elif not items:
            problem = Problem("missing", f"{dimension.key}: no answer was given for this dimension.")
            judgement = Judgement(dimension.key, None, None, (), (problem,))
        else:
            problem = Problem("duplicate", f"{dimension.key}: answered {len(items)} times; answer once.")
            judgement = Judgement(dimension.key, None, None, (), (problem,))
        if general:
            judgement = Judgement(
                judgement.key, judgement.score, judgement.rationale, judgement.evidence, (*general, *judgement.problems)
            )
        judgements.append(judgement)
    return judgements


# --- results -----------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DimensionResult:
    """The final result for one dimension. Unverified results carry no score, rationale or evidence."""

    key: str
    name: str
    weight: float
    verified: bool
    score: int | None
    rationale: str | None
    evidence: tuple[GroundingResult, ...]
    """Verified quotes only (all of them, since one unverified quote fails the dimension)."""
    attempts: int
    failure_reasons: tuple[str, ...] = ()
    """Problem codes of the last attempt when unverified (for review and metrics, not shown to staff)."""
    quotes_offered: int = 0
    """Well-formed quotes the model offered for this dimension, over all attempts (for eval/grounding.py)."""
    quotes_verified: int = 0
    """How many of those passed the grounding verifier."""
    not_applicable: bool = False
    """Verified as not applying to this conversation (rubric `not_applicable_when`): no score, left out of the
    overall score; the rationale and evidence say why."""


@dataclass(frozen=True, slots=True)
class ScoringOutcome:
    dimensions: tuple[DimensionResult, ...]
    """In rubric order."""
    calls: tuple[CallRecord, ...]
    prompts: tuple[Prompt, ...]
    metrics: tuple[dict[str, Any], ...]


def _result(dimension: DimensionSpec, judgement: Judgement, *all_attempts: Judgement) -> DimensionResult:
    """The result from the last attempt `judgement`; quote counts are summed over `all_attempts` (which include it)."""
    attempts = len(all_attempts)
    offered = sum(len(j.evidence) for j in all_attempts)
    verified = sum(1 for j in all_attempts for e in j.evidence if e.verified)
    scored_or_not_applicable = judgement.score is not None or judgement.not_applicable
    if judgement.ok and scored_or_not_applicable and judgement.rationale is not None:  # ok implies both are set
        return DimensionResult(
            dimension.key,
            dimension.name,
            float(dimension.weight),
            True,
            None if judgement.not_applicable else judgement.score,
            judgement.rationale,
            judgement.evidence,
            attempts,
            quotes_offered=offered,
            quotes_verified=verified,
            not_applicable=judgement.not_applicable,
        )
    codes = tuple(dict.fromkeys(problem.code for problem in judgement.problems))
    return DimensionResult(
        dimension.key,
        dimension.name,
        float(dimension.weight),
        False,
        None,
        None,
        (),
        attempts,
        codes,
        quotes_offered=offered,
        quotes_verified=verified,
    )


def feedback_text(problems: Sequence[Problem]) -> str:
    """The re-ask feedback block for a request prompt."""
    lines = "\n".join(f"- {problem.message}" for problem in problems)
    return (
        "\n# Problems with your previous answer\n\n"
        f"{lines}\n\n"
        "Answer again and fix every problem. Quote only words that appear exactly in one transcript line, with that "
        "line's utterance id and start_ms."
    )


@dataclass(frozen=True, slots=True)
class _ScoringPrompts:
    system: Prompt
    context: Prompt
    request: Prompt

    def all(self) -> tuple[Prompt, ...]:
        return (self.system, self.context, self.request)


def load_scoring_prompts(directory: Path = PROMPTS_DIR) -> _ScoringPrompts:
    return _ScoringPrompts(
        load_prompt("scoring.system", directory),
        load_prompt("scoring.context", directory),
        load_prompt("scoring.request", directory),
    )


def call_model(
    model: JudgeModel,
    *,
    task: str,
    system: str,
    prefix: str,
    request: str,
    json_schema: Mapping[str, Any],
    attempt: int,
    keys: tuple[str, ...],
    calls: list[CallRecord],
) -> object:
    """Check the prompt is redacted, call the model with `prefix` as cache prefix, record the call, return data.

    The single user message is `prefix`, then a blank line and `request` if `request` is not empty."""
    content = f"{prefix}\n\n{request}" if request else prefix
    check_prompt_redacted(system, content)
    response = model.complete_json(
        task=task,
        system=system,
        messages=[{"role": "user", "content": content}],
        json_schema=json_schema,
        cache_prefix=prefix,
    )
    if not isinstance(response, JudgeResponse) or not isinstance(response.model_id, str) or not response.model_id:
        raise TypeError("JudgeModel.complete_json must return a JudgeResponse with a model_id")
    calls.append(CallRecord(task, attempt, keys, response.model_id, response.usage))
    return response.data


def score_dimensions(
    *,
    rubric: RubricSpec,
    transcript: PreparedTranscript,
    metrics: Iterable[Mapping[str, object]],
    model: JudgeModel,
    prompts_dir: Path = PROMPTS_DIR,
) -> ScoringOutcome:
    """Score every rubric dimension with grounded evidence (module docstring). Raises PromptNotRedacted, and lets
    gateway errors propagate: a failed call fails the stage visibly rather than producing a partial report."""
    check_rubric(rubric)
    metric_records = normalise_metrics(metrics)
    prompts = load_scoring_prompts(prompts_dir)
    dimensions = list(rubric.dimensions)
    prefix = prompts.context.render(
        rubric_id=rubric.id,
        rubric_version=rubric.version,
        dimensions="\n\n".join(render_dimension(dimension) for dimension in dimensions),
        metrics=render_metrics(metric_records),
        transcript=transcript.render(),
    )
    system = prompts.system.render(**prompt_roles(rubric.id, rubric.roles))
    calls: list[CallRecord] = []
    results: dict[str, DimensionResult] = {}

    def ask(group: Sequence[DimensionSpec], feedback: str, attempt: int) -> list[Judgement]:
        request = prompts.request.render(
            dimension_list=", ".join(dimension.key for dimension in group),
            min_quotes=", ".join(f"{dimension.key} {dimension.min_quotes}" for dimension in group),
            feedback=feedback,
        )
        data = call_model(
            model,
            task=TASK_SCORING,
            system=system,
            prefix=prefix,
            request=request,
            json_schema=scoring_output_schema(group),
            attempt=attempt,
            keys=tuple(dimension.key for dimension in group),
            calls=calls,
        )
        return validate(data, group, transcript)

    for group in group_dimensions(dimensions):
        for dimension, first in zip(group, ask(group, "", 1), strict=True):
            if not first.ok:
                (second,) = ask((dimension,), feedback_text(first.problems), 2)
                results[dimension.key] = _result(dimension, second, first, second)
            else:
                results[dimension.key] = _result(dimension, first, first)
    return ScoringOutcome(
        dimensions=tuple(results[dimension.key] for dimension in dimensions),
        calls=tuple(calls),
        prompts=prompts.all(),
        metrics=metric_records,
    )
