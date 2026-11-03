"""The transcribe stage for an imported transcript (ADR 0009): read the file instead of the audio.

A recording with `source == "transcript"` was uploaded as a meeting transcript (Google Meet .txt). It skips
preprocess and diarize (UPLOADED -> TRANSCRIBING, `imported=True` in sabha_core.state) and this `work` runs in their
place:

1. Downloads the original from the audio bucket (at most MAX_BYTES) and reads it as UTF-8. Missing:
   PermanentError `missing_input`; not a transcript Sabha can read (sabha_asr.imported): PermanentError with the
   reader's code (`not_a_transcript`, `no_timestamps`).
2. Writes `segments@v1.json` in this stage's folder: one segment covering the whole meeting, because a transcript
   says nothing about silence. The analyze stage reads it from here and leaves the silence metrics out.
3. Stores on the recording its length, the speakers' names from the file (`voice_names`, display only; models only
   ever see S1, S2) and, when the file name says when the meeting started and the uploader did not, `recorded_at`.
4. Hands the words and turns to sabha_workers.stages.transcript.finish_transcript, exactly as speech recognition
   does: speaker roles (heuristics, then the LLM tie-breaker, then a reviewer), transcript@v1.json with
   `word_timing` "approximate", and NEEDS_REVIEW when the roles are unclear.

Nothing is sent to a speech provider, so nothing is billed for speech.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from sabha_asr.imported import SOURCE_MODEL, TranscriptImportError, meeting_start_from_name, parse_meet_transcript
from sabha_core.timemap import Segment, SegmentMap
from sabha_workers.stages.preprocess import Originals
from sabha_workers.stages.runner import PermanentError, StageContext, Work
from sabha_workers.stages.transcript import AsrOutput, TranscriptDeps, finish_transcript

log = logging.getLogger("sabha.workers.imported")

MAX_BYTES = 5 * 1024 * 1024  # a two-hour meeting's transcript is well under 1 MB

RecordImport = Callable[[str, str, int, dict[str, str], datetime | None], None]
"""(tenant_id, recording_id, duration_ms, voice_names, recorded_at or None): store them on the recording."""


def make_work(originals: Originals, record: RecordImport, transcript: TranscriptDeps) -> Work:
    def work(ctx: StageContext) -> dict[str, Any]:
        recording = ctx.recording
        if not recording.storage_key:
            raise PermanentError("missing_input", "the recording has no uploaded file")
        with tempfile.TemporaryDirectory(prefix="sabha-import-") as tmp:
            path = Path(tmp) / "transcript.txt"
            try:
                originals.download(recording.storage_key, path)
            except FileNotFoundError as exc:
                raise PermanentError("missing_input", f"uploaded transcript not found: {exc}") from exc
            if path.stat().st_size > MAX_BYTES:
                raise PermanentError("not_a_transcript", f"the file is larger than {MAX_BYTES} bytes")
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise PermanentError("not_a_transcript", "the file is not UTF-8 text") from exc
        try:
            imported = parse_meet_transcript(text)
        except TranscriptImportError as exc:
            raise PermanentError(exc.code, exc.detail) from exc

        whole = SegmentMap((Segment(0, imported.duration_ms, 0),))
        ctx.artefacts.put(ctx.prefix + "segments@v1.json", whole.to_json().encode(), "application/json")
        started = None if recording.recorded_at is not None else meeting_start_from_name(recording.file_name or "")
        record(ctx.tenant_id, recording.id, imported.duration_ms, imported.names, started)
        meta = {"source": "transcript", "lines": len(imported.lines), "words": len(imported.words),
                "audio_s": round(imported.duration_ms / 1000, 1)}  # fmt: skip
        log.info("transcript imported", extra={"recording_id": recording.id, **meta})
        asr = AsrOutput(imported.words, SOURCE_MODEL, "approximate", [], whole)
        refreshed = ctx.recording.model_copy(update={"duration_ms": imported.duration_ms})
        context = StageContext(ctx.tenant_id, refreshed, ctx.prefix, ctx.artefacts, ctx.attempt)
        return {**meta, **finish_transcript(context, asr, transcript, turns=imported.turns)}

    return work
