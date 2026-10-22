"""The diarize stage: who spoke when (plan task P3.4a; queue gpu.speech).

`work(ctx)`:

1. Reads the preprocess stage's `compact.wav` (speech only) and `segments@v1.json`. Missing: PermanentError
   `missing_input` (the preprocess stage did not finish; replay it).
2. Runs the configured diarizer (sabha_asr.diarization) on compact.wav. Teaching recordings may have any number of
   speakers (role assignment, P3.6, groups the students); no speaker limits are passed for now.
3. Writes `diarization@v1.json` with the turns twice: on the COMPACT timeline (what ASR will see) and on the
   ORIGINAL recording timeline (golden rule 4). A compact turn that crosses a join where silence was cut out
   becomes one original turn per segment it touches, so no original turn spans removed silence.
4. Returns processing time, audio length, real-time factor and device for the stage run (`meta`).

No speaker turns at all, although VAD found speech: NeedsReviewError `no_speakers`.
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sabha_asr.diarization import Diarizer, Turn
from sabha_core.storage import artefact_prefix
from sabha_core.timemap import SegmentMap
from sabha_workers.stages.runner import NeedsReviewError, PermanentError, StageContext, Work

log = logging.getLogger("sabha.workers.diarize")

VERSION = "diarization@v1"
NO_SPEAKERS = "no_speakers"


def to_original(turns: list[Turn], segment_map: SegmentMap) -> list[Turn]:
    """Compact turns -> original turns, split at the joins between segments (module docstring, step 3)."""
    out = []
    for turn in turns:
        for segment in segment_map.segments:
            start = max(turn.start_ms, segment.compact_start_ms)
            end = min(turn.end_ms, segment.compact_end_ms)
            if start < end:
                offset = segment.orig_start_ms - segment.compact_start_ms
                out.append(Turn(turn.speaker, start + offset, end + offset))
    return sorted(out, key=lambda t: (t.start_ms, t.end_ms, t.speaker))


def _records(turns: list[Turn]) -> list[dict[str, Any]]:
    return [{"speaker_label": t.speaker, "start_ms": t.start_ms, "end_ms": t.end_ms} for t in turns]


def make_work(diarizer: Callable[[], Diarizer], preprocess_version: str, device: str) -> Work:
    """The diarize `work` function for StageRunner. `diarizer` returns the (cached) model."""

    def work(ctx: StageContext) -> dict[str, Any]:
        source = artefact_prefix(ctx.tenant_id, ctx.recording.id, "preprocess", preprocess_version)
        with tempfile.TemporaryDirectory(prefix="sabha-diarize-") as tmp:
            compact = Path(tmp) / "compact.wav"
            try:
                segment_map = SegmentMap.from_json(ctx.artefacts.get(source + "segments@v1.json"))
                ctx.artefacts.download(source + "compact.wav", compact)
            except FileNotFoundError as exc:
                raise PermanentError("missing_input", f"preprocess output not found: {exc}") from exc
            model = diarizer()
            started = time.monotonic()
            turns = model.diarize(compact)
            seconds = time.monotonic() - started
        if not turns:
            raise NeedsReviewError(NO_SPEAKERS, "diarization found no speaker turns in the speech")
        original = to_original(turns, segment_map)
        speakers = sorted({t.speaker for t in turns}, key=lambda name: int(name[1:]))
        document = {
            "version": VERSION,
            "model": model.model_id,
            "speakers": speakers,
            "compact": _records(turns),
            "original": _records(original),
        }
        ctx.artefacts.put(ctx.prefix + "diarization@v1.json", json.dumps(document).encode(), "application/json")
        audio_s = segment_map.compact_length_ms / 1000
        meta = {
            "device": device,
            "model": model.model_id,
            "processing_s": round(seconds, 1),
            "audio_s": round(audio_s, 1),
            "real_time_factor": round(seconds / audio_s, 4) if audio_s else None,
            "speakers": len(speakers),
            "turns": len(turns),
        }
        log.info("diarized", extra={"recording_id": ctx.recording.id, **meta})
        return meta

    return work
