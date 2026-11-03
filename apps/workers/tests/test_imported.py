"""The transcribe stage for an imported Meet transcript (ADR 0009). No services: artefacts and the uploaded file live
in memory. The transcript is fictional."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from sabha_core.models import Recording, Tenant, Transcript
from sabha_core.profiles import ConversationType
from sabha_core.quota import Plan
from sabha_workers.rubrics import rubric_for
from sabha_workers.stages import imported
from sabha_workers.stages.runner import PermanentError, StageContext
from sabha_workers.stages.transcript import TranscriptDeps

RUBRICS = Path(__file__).resolve().parents[3] / "rubrics"
TENANT = Tenant.from_profile("company", name="Brightpath Software", plan=Plan.PILOT, id="t1")
FILE_NAME = "Attendance Demo _ Example Traders \u2013 2026_11_02 16_05 IST.txt"
MEET = "\r\n".join([
    "Nov 2, 2026",
    "Attendance Demo : Example Traders - Transcript",
    "00:00:03",
    "Asha Rao: Good evening sir, I am Asha from Brightpath. Today I will show you our attendance devices.",
    "Vikram Iyer: Okay.",
    "Asha Rao: This model marks five people a second and holds ten thousand users, so a queue never builds up.",
    "00:01:10",
    "Vikram Iyer: What does it cost?",
    "Asha Rao: The base model suits fifty staff. I will send the quotation today and call you on Friday at 11.",
    "Transcription ended after 00:02:00",
])  # fmt: skip


class Memory:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def exists(self, key: str) -> bool:
        return key in self.files

    def put(self, key: str, body: bytes, content_type: str = "") -> None:
        self.files[key] = body

    def put_file(self, key: str, path: Path, content_type: str) -> None:
        self.files[key] = path.read_bytes()

    def get(self, key: str) -> bytes:
        if key not in self.files:
            raise FileNotFoundError(key)
        return self.files[key]

    def download(self, key: str, path: Path) -> None:
        path.write_bytes(self.get(key))


def run(text: bytes, recorded_at: datetime | None = None) -> tuple[Memory, list[Transcript], list[tuple[Any, ...]]]:
    store, uploads = Memory(), Memory()
    uploads.put("t1/r1/original/demo.txt", text)
    saved: list[Transcript] = []
    recorded: list[tuple[Any, ...]] = []
    deps = TranscriptDeps(
        diarize_version="v1", tenant=lambda _: TENANT, rubric=lambda t, k: rubric_for(t, k, RUBRICS),
        tie_breaker=lambda *_: None, save=lambda _, doc: saved.append(doc),
    )  # fmt: skip
    work = imported.make_work(uploads, lambda *args: recorded.append(args), deps)
    recording = Recording(id="r1", tenant_id="t1", type=ConversationType.SALES, source="transcript",
                          storage_key="t1/r1/original/demo.txt", file_name=FILE_NAME,
                          recorded_at=recorded_at)  # fmt: skip
    work(StageContext("t1", recording, "t1/r1/transcribe@v1/", store, 1))
    return store, saved, recorded


def test_a_meet_transcript_becomes_a_transcript_with_roles_and_no_speech_stages() -> None:
    store, saved, recorded = run(MEET.encode())

    transcript = json.loads(store.get("t1/r1/transcribe@v1/transcript@v1.json"))
    assert transcript["word_timing"] == "approximate" and transcript["asr_model"] == "import:google-meet"
    roles = [u["role"] for u in transcript["utterances"]]
    assert roles == ["sales_rep", "customer", "sales_rep", "customer", "sales_rep"]
    assert transcript["utterances"][0]["start_ms"] == 3_000
    (doc,) = saved
    assert doc.roles == {"S1": "sales_rep", "S2": "customer"} and not doc.roles_need_review
    assert doc.asr_billed_ms is None and doc.asr_cost_inr is None  # nothing went to a speech provider
    # One segment for the whole meeting: the analyze stage reads it here and shows no silence figures.
    assert json.loads(store.get("t1/r1/transcribe@v1/segments@v1.json")) == [
        {"orig_start_ms": 0, "orig_end_ms": 120_000, "compact_start_ms": 0}
    ]
    # Length, the names for display only, and the start time from the file name (16:05 IST).
    assert recorded == [("t1", "r1", 120_000, {"S1": "Asha Rao", "S2": "Vikram Iyer"},
                         datetime(2026, 11, 2, 10, 35, tzinfo=UTC))]  # fmt: skip


def test_names_never_reach_the_transcript_that_models_read() -> None:
    store, _, _ = run(MEET.encode())
    text = store.get("t1/r1/transcribe@v1/transcript@v1.json").decode()
    assert "Vikram Iyer" not in text  # speakers are S1 and S2; a name spoken aloud stays, as in any recording


def test_a_time_the_uploader_gave_is_not_replaced_by_the_file_name() -> None:
    given = datetime(2026, 11, 2, 4, 0, tzinfo=UTC)
    _, _, recorded = run(MEET.encode(), recorded_at=given)
    assert recorded[0][4] is None


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (b"Asha Rao: hello\r\nVikram Iyer: hi\r\n", "no_timestamps"),
        (b"meeting notes, nothing else", "not_a_transcript"),
        ("00:00:01\nAsha: नमस्ते".encode("utf-16"), "not_a_transcript"),
    ],
    ids=["no time markers", "no speakers", "not utf-8"],
)
def test_a_file_that_is_not_a_readable_transcript_fails_with_its_reason(body: bytes, code: str) -> None:
    with pytest.raises(PermanentError) as raised:
        run(body)
    assert raised.value.code == code
