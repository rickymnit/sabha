"""Reading a meeting transcript file instead of the audio (ADR 0009): Google Meet's .txt export.

A Meet transcript looks like this (UTF-8, often with a BOM and CRLF line ends):

    Nov 2, 2026
    Attendance Management Demo : Example Ltd - Transcript
    00:00:04
    Asha Rao: Hello.
    Vikram Iyer: Hi, can you hear me?
    00:01:33
    Asha Rao: Yes. So these are the models we offer...
    Transcription ended after 00:24:44
    This editable transcript was computer generated and might contain errors. ...

`parse_meet_transcript(text)` returns the speakers' lines with estimated times on the ORIGINAL timeline:

- A line on its own like `00:01:33` is a time marker. Meet writes one about every minute, not one per line, so the
  lines between two markers share that stretch of time in proportion to their length in characters, and each word
  gets its share of its line the same way. The times are estimates (`word_timing` "approximate"), good to about
  the gap between markers. The text is exactly what the file says, so quotes are checked against it as usual.
- The stretch after the last marker ends at "Transcription ended after ..." when the file says it, otherwise after
  ESTIMATED_MS_PER_WORD per word.
- `Name: text` starts a speaker's line. Speakers become anonymous labels S1, S2, ... in order of first appearance;
  the names are returned separately (`names`) for display only and are never sent to a model. A line without a
  `Name:` prefix continues the line before it. Files that label speakers "Speaker 1", "Speaker 2" work the same way.
- Header lines before the first speaker line (date, title) and the closing lines are not speech.

A file with no speaker lines, or no time markers at all, is refused (TranscriptImportError with a code), because
every judgement must cite a time (golden rule 5) and without markers there is nothing to estimate times from.

`meeting_start_from_name(file_name)` reads the start time Meet puts in the file name ("2026_11_02 11_18 IST").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from itertools import pairwise

from sabha_asr.words import Turn, Word

SOURCE_MODEL = "import:google-meet"  # recorded as the transcript's asr_model
ESTIMATED_MS_PER_WORD = 400  # about 150 words a minute, only for the stretch after the last marker
MAX_SPEAKER_NAME_CHARS = 60
MAX_SPEAKER_NAME_WORDS = 5

_MARKER = re.compile(r"^(\d{1,2}):([0-5]\d):([0-5]\d)$")
_ENDED = re.compile(r"^Transcription ended after (\d{1,2}):([0-5]\d):([0-5]\d)$")
_FOOTER = "This editable transcript was computer generated"
_SPEAKER = re.compile(r"^([^:\d][^:]*?):\s+(\S.*)$")
_NAME_TIME = re.compile(r"(\d{4})_(\d{2})_(\d{2}) (\d{2})_(\d{2}) (IST)\b")
_ZONES = {"IST": timezone(timedelta(hours=5, minutes=30))}


class TranscriptImportError(ValueError):
    """The file is not a transcript Sabha can read. `code` is stable: not_a_transcript or no_timestamps."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class ImportedLine:
    speaker_label: str  # S1, S2, ...
    text: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class ImportedTranscript:
    lines: tuple[ImportedLine, ...]
    words: tuple[Word, ...]
    turns: tuple[Turn, ...]
    names: dict[str, str]  # S1 -> the name in the file (display only)
    duration_ms: int
    title: str | None


def _ms(hours: str, minutes: str, seconds: str) -> int:
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000


def _speaker(line: str) -> tuple[str, str] | None:
    match = _SPEAKER.match(line)
    if match is None:
        return None
    name, text = match.group(1).strip(), match.group(2).strip()
    if len(name) > MAX_SPEAKER_NAME_CHARS or len(name.split()) > MAX_SPEAKER_NAME_WORDS:
        return None
    return name, text


def _spread(start_ms: int, end_ms: int, weights: list[int]) -> list[tuple[int, int]]:
    """Split [start_ms, end_ms) into consecutive pieces in proportion to `weights` (each piece at least 1 ms)."""
    total = sum(weights) or 1
    pieces = []
    done = 0
    cursor = start_ms
    for weight in weights:
        done += weight
        end = max(start_ms + (end_ms - start_ms) * done // total, cursor + 1)
        pieces.append((cursor, end))
        cursor = end
    return pieces


def parse_meet_transcript(text: str) -> ImportedTranscript:
    """The speakers' lines, words and turns of a Google Meet .txt transcript (module docstring)."""
    blocks: list[tuple[int, list[tuple[str, str]]]] = []  # (marker ms, [(name, text)])
    title: str | None = None
    ended_ms: int | None = None
    started = False
    raw_lines = [line.strip() for line in text.lstrip("\ufeff").splitlines()]
    for line in raw_lines:
        if not line:
            continue
        if line.startswith(_FOOTER):
            break
        if (ended := _ENDED.match(line)) is not None:
            ended_ms = _ms(*ended.groups())
            continue
        if (marker := _MARKER.match(line)) is not None:
            blocks.append((_ms(*marker.groups()), []))
            started = True
            continue
        if not started:  # the header: the date and "<title> - Transcript"
            if line.endswith("- Transcript"):
                title = title or line.removesuffix("- Transcript").strip() or None
            elif _speaker(line) is not None:  # speech before any marker: no time to place it at
                raise TranscriptImportError(
                    "no_timestamps", "the transcript has no time marker such as 00:01:33 before speech"
                )
            continue
        spoken = _speaker(line)
        if spoken is not None:
            blocks[-1][1].append(spoken)
        elif blocks[-1][1]:  # a line without "Name:" continues the previous speaker line
            name, before = blocks[-1][1][-1]
            blocks[-1][1][-1] = (name, f"{before} {line}")

    if not any(block for _, block in blocks):
        raise TranscriptImportError("not_a_transcript", "no 'Name: text' lines were found")
    for (earlier, _), (later, _) in pairwise(blocks):
        if later < earlier:
            raise TranscriptImportError("not_a_transcript", "the time markers go backwards")

    labels: dict[str, str] = {}
    lines: list[ImportedLine] = []
    words: list[Word] = []
    for index, (start_ms, block) in enumerate(blocks):
        if not block:
            continue
        if index + 1 < len(blocks):
            end_ms = blocks[index + 1][0]
        else:
            estimate = start_ms + ESTIMATED_MS_PER_WORD * sum(len(t.split()) for _, t in block)
            end_ms = ended_ms if ended_ms is not None and ended_ms > start_ms else estimate
        start_ms = max(start_ms, lines[-1].end_ms if lines else 0)
        end_ms = max(end_ms, start_ms + 1)
        for (name, said), (line_start, line_end) in zip(
            block, _spread(start_ms, end_ms, [len(t) for _, t in block]), strict=True
        ):
            label = labels.setdefault(name, f"S{len(labels) + 1}")
            lines.append(ImportedLine(label, said, line_start, line_end))
            tokens = said.split()
            for token, (word_start, word_end) in zip(
                tokens, _spread(line_start, line_end, [len(t) for t in tokens]), strict=True
            ):
                words.append(Word(token, min(word_start, line_end), min(word_end, line_end), None))

    turns = tuple(Turn(line.speaker_label, line.start_ms, line.end_ms) for line in lines)
    duration_ms = max(lines[-1].end_ms, ended_ms or 0)
    names = {label: name for name, label in labels.items()}
    return ImportedTranscript(tuple(lines), tuple(words), turns, names, duration_ms, title)


def meeting_start_from_name(file_name: str) -> datetime | None:
    """The meeting's start (UTC) from a Meet file name such as "Demo - 2026_11_02 11_18 IST.txt", or None."""
    match = _NAME_TIME.search(file_name)
    if match is None:
        return None
    year, month, day, hour, minute, zone = match.groups()
    try:
        local = datetime(int(year), int(month), int(day), int(hour), int(minute), tzinfo=_ZONES[zone])
    except ValueError:
        return None
    return local.astimezone(UTC)
