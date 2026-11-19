"""The Gemini speaker check: Gemini listens to the call and says who said each transcript line (owner 2026-11-18).

Why: pyannote separates voices by sound alone. On a mono phone line with two similar voices and turns of a second or
two (the Roshan call's opening, 0:06 to 0:33) it gave every turn to one voice, and Deepgram's own speaker labels did
the same. Gemini also follows the conversation (a question and its answer are different people) and got that
opening right. Chosen per recording at upload (Recording.speaker_model "gemini"), on top of pyannote: pyannote's
turns keep the times; the check only moves whole lines between speakers.

1. `lines_of`: the words (as speech-to-text gave them, with the speaker each was given) become lines: a run of one
   speaker's words, ended at a sentence end (। ? . !) or a change of speaker.
2. The caller sends Gemini windows of the ORIGINAL audio (WINDOW_MS) with the numbered lines heard in each, their
   text masked for PII first (golden rule 8). `GeminiSpeakerAsker` asks which lines the staff member said and which
   it cannot tell (the rest are the customer's), with low thinking. Model: Gemini 3.8 Flash (owner 2026-11-19). On the
   Roshan call (2026-11-18) it cost about Rs 10.8 per audio hour, moved 39 of 264 lines and could not tell 6, and got
   the opening right; 3.1 Flash-Lite (about Rs 6.8) moved 25, could not tell 86 and left Roshan's own lines with the
   customer.
3. `relabel`: a line of at least MIN_WORDS words that Gemini gives to the other side moves there: to the staff
   speaker (on a transferred call, the agent of that side of the handover) or to the customer-side voice heard
   nearest in time. Shorter lines ("ठीक", "ओके") and lines Gemini cannot tell stay as pyannote had them: on the
   Roshan call Gemini's answers for backchannels looked like guesses, while its moves of longer lines were right
   wherever the text could be checked. MIN_WORDS is a starting value, not measured.

Nothing here is a fallback: if Gemini fails, the caller fails the stage (retried like speech-to-text), never a
transcript without the check that was asked for (golden rule 7).
"""

from __future__ import annotations

import base64
import json
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from sabha_asr.provider import ProviderError, TokenUsage
from sabha_asr.providers import _http
from sabha_asr.providers.gemini import DEFAULT_BASE_URL, usage_of
from sabha_asr.words import Word

NAME = "gemini-speakers"
MODEL = "gemini-3.8-flash"
MODEL_ID = f"gemini/{MODEL}"
WINDOW_MS = 180_000
"""Audio per question: three minutes of the original recording (and the lines that start in it)."""
WINDOW_TAIL_MS = 5_000
"""Audio after a window's end, so its last line is heard to the end."""
MIN_WORDS = 3
SENTENCE_ENDS = ("।", "?", ".", "!", "|")
_NOT_RETRYABLE = frozenset({"PERMISSION_DENIED", "UNAUTHENTICATED", "INVALID_ARGUMENT", "FAILED_PRECONDITION"})

Verdict = Literal["staff", "customer", "unsure"]

log = logging.getLogger("sabha.asr.speaker_check")


@dataclass(frozen=True, slots=True)
class Line:
    """One line: consecutive words of one speaker up to a sentence end. Times are on the words' (compact) timeline."""

    index: int
    start_ms: int
    end_ms: int
    text: str
    label: str
    word_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Change:
    index: int
    start_ms: int
    from_label: str
    to_label: str
    text: str


def lines_of(words: Sequence[Word], labels: Sequence[str]) -> list[Line]:
    """Step 1. `labels[i]` is the speaker label word i was given."""
    lines: list[Line] = []
    current: list[int] = []

    def close() -> None:
        if current:
            first, last = words[current[0]], words[current[-1]]
            text = " ".join(words[i].text for i in current)
            lines.append(Line(len(lines), first.start_ms, last.end_ms, text, labels[current[0]], tuple(current)))
            current.clear()

    for i, word in enumerate(words):
        if current and labels[i] != labels[current[0]]:
            close()
        current.append(i)
        if word.text.endswith(SENTENCE_ENDS):
            close()
    close()
    return lines


def _nearest(label_spans: Sequence[tuple[str, int, int]], candidates: set[str], at_ms: int) -> str | None:
    best: tuple[int, str] | None = None
    for label, start, end in label_spans:
        if label in candidates:
            distance = 0 if start <= at_ms <= end else min(abs(at_ms - start), abs(at_ms - end))
            if best is None or distance < best[0]:
                best = (distance, label)
    return None if best is None else best[1]


def relabel(
    lines: Sequence[Line],
    verdicts: Mapping[int, Verdict],
    labels: Sequence[str],
    roles: Mapping[str, str],
    staff_role: str,
    *,
    agents: tuple[str, str] | None = None,
    handover_ms: int | None = None,
) -> tuple[list[str], list[Change]]:
    """Step 3. `verdicts` maps a line's index to Gemini's answer; `roles` maps labels to roles, `staff_role` being the
    rubric's staff role and every other label the customer's side. Returns the new label of every word and the lines
    that moved."""
    staff_labels = {label for label, role in roles.items() if role == staff_role}
    customer_labels = {label for label in roles if label not in staff_labels}
    spans = [(line.label, line.start_ms, line.end_ms) for line in lines]
    new = list(labels)
    changes: list[Change] = []
    for line in lines:
        verdict = verdicts.get(line.index)
        if verdict not in ("staff", "customer") or len(line.word_ids) < MIN_WORDS:
            continue
        if verdict == "staff" and line.label not in staff_labels:
            if agents and handover_ms is not None:
                target: str | None = agents[0] if line.start_ms < handover_ms else agents[1]
            else:
                target = next(iter(staff_labels)) if len(staff_labels) == 1 else None
        elif verdict == "customer" and line.label not in customer_labels:
            middle = (line.start_ms + line.end_ms) // 2
            target = _nearest(spans, customer_labels, middle) or (next(iter(customer_labels), None))
        else:
            continue
        if target is None or target == line.label:
            continue
        for i in line.word_ids:
            new[i] = target
        changes.append(Change(line.index, line.start_ms, line.label, target, line.text))
    return new, changes


class GeminiSpeakerAsker:
    """Step 2: one question per window. Call with the window's WAV, its start (seconds on the original timeline),
    the numbered lines (number, start in seconds, masked text) and the staff member's job word ("sales rep")."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        timeout_s: float = 300.0,
    ) -> None:
        if not api_key:
            raise ValueError("the Gemini speaker check needs GEMINI_API_KEY")
        self._api_key = api_key
        self._url = f"{base_url.rstrip('/')}/v1beta/models/{MODEL}:generateContent"
        self._client = client or httpx.Client(timeout=timeout_s)
        self._sleep = sleep

    @staticmethod
    def prompt(window_start_s: float, numbered: Sequence[tuple[int, float, str]], staff_word: str) -> str:
        listing = "\n".join(f"{n}. [{start:.0f}s] {text}" for n, start, text in numbered)
        return (
            f"This audio is part of a phone call or meeting between a {staff_word} and a customer, in Hindi and "
            "English. Below are the transcript's lines for it, numbered, with rough start times in seconds from the "
            f"start of the WHOLE recording (this audio starts at {window_start_s:.0f}s). Say who said each line: the "
            f"{staff_word} or the customer. Use the voices and the flow of the conversation: a question and its "
            "answer are said by different people.\n\n" + listing + "\n\nAnswer with the numbers of the lines said by "
            f"the {staff_word}, and separately the numbers of the lines you cannot tell. Every other line is the "
            "customer's."
        )

    def __call__(
        self, wav: bytes, window_start_s: float, numbered: Sequence[tuple[int, float, str]], staff_word: str
    ) -> tuple[dict[int, Verdict], TokenUsage | None]:
        schema = {"type": "OBJECT", "properties": {"staff": {"type": "ARRAY", "items": {"type": "INTEGER"}},
                                                   "unsure": {"type": "ARRAY", "items": {"type": "INTEGER"}}},
                  "required": ["staff", "unsure"]}  # fmt: skip
        body = {
            "contents": [{"role": "user", "parts": [
                {"inline_data": {"mime_type": "audio/wav", "data": base64.b64encode(wav).decode("ascii")}},
                {"text": self.prompt(window_start_s, numbered, staff_word)},
            ]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": schema,
                                 "thinkingConfig": {"thinkingLevel": "low"}},
        }  # fmt: skip

        def request() -> httpx.Response:
            return self._client.post(self._url, headers={"x-goog-api-key": self._api_key}, json=body)

        response = _http.send(NAME, request, not_retryable=_NOT_RETRYABLE, sleep=self._sleep, log=log,
                              chunk_id=f"window@{window_start_s:.0f}s")  # fmt: skip
        if response.status_code != 200:
            raise _http.error_for(NAME, response, _NOT_RETRYABLE)
        answer = _http.json_body(NAME, response)
        return _verdicts(answer, [n for n, _, _ in numbered]), usage_of(answer)


def _verdicts(answer: Any, numbers: Sequence[int]) -> dict[int, Verdict]:
    try:
        candidate = answer["candidates"][0]
        if candidate.get("finishReason") not in (None, "STOP"):
            raise ProviderError(NAME, f"answer stopped early ({candidate.get('finishReason')})", retryable=False)
        raw = "".join(p.get("text", "") for p in candidate["content"]["parts"] if not p.get("thought"))
        got = json.loads(raw)
        staff, unsure = {int(n) for n in got["staff"]}, {int(n) for n in got["unsure"]}
    except ProviderError:
        raise
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ProviderError(NAME, "answer is not the expected JSON", retryable=False) from exc
    return {n: "unsure" if n in unsure else "staff" if n in staff else "customer" for n in numbers}
