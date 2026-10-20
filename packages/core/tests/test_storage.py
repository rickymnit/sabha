"""Storage keys always start with the tenant and never climb out of their prefix (golden rules 1 and 3)."""

from __future__ import annotations

import pytest

from sabha_core.storage import artefact_prefix, belongs_to, original_key, safe_file_name, tenant_prefix


@pytest.mark.parametrize(
    ("name", "safe"),
    [
        ("lesson.mp3", "lesson.mp3"),
        ("Class 7B (Fractions).M4A", "Class_7B_Fractions.m4a"),
        ("Class 7B \u2013 Fractions.m4a", "Class_7B_Fractions.m4a"),  # an en dash is dropped
        ("C:\\Users\\Asha\\lesson.wav", "lesson.wav"),
        ("../../etc/passwd", "passwd"),
        ("नमस्ते.mp3", "recording.mp3"),
        ("...", "recording"),
        ("noextension", "noextension"),
        ("a" * 300 + ".webm", "a" * 95 + ".webm"),  # 100 characters in all
    ],
)
def test_safe_file_name(name: str, safe: str) -> None:
    assert safe_file_name(name) == safe


def test_original_key_has_the_documented_layout() -> None:
    assert original_key("t1", "r1", "My Lesson.mp3") == "t1/r1/original/My_Lesson.mp3"


def test_artefact_prefix_has_the_documented_layout() -> None:
    assert artefact_prefix("t1", "r1", "preprocess", "v1") == "t1/r1/preprocess@v1/"


@pytest.mark.parametrize("bad", ["", "..", "a/b", "../t2", "t 1", "x" * 65])
def test_ids_that_could_escape_the_prefix_are_refused(bad: str) -> None:
    with pytest.raises(ValueError):
        tenant_prefix(bad)
    with pytest.raises(ValueError):
        original_key("t1", bad, "a.mp3")
    with pytest.raises(ValueError):
        artefact_prefix("t1", bad, "preprocess", "v1")


@pytest.mark.parametrize(("stage", "version"), [("Pre/process", "v1"), ("preprocess", "v1/../x"), ("", "v1")])
def test_bad_stage_or_version_is_refused(stage: str, version: str) -> None:
    with pytest.raises(ValueError):
        artefact_prefix("t1", "r1", stage, version)


def test_belongs_to() -> None:
    assert belongs_to("t1", "t1/r1/original/a.mp3")
    assert not belongs_to("t1", "t10/r1/original/a.mp3")
    assert not belongs_to("t1", "t2/r1/original/a.mp3")
    assert not belongs_to("t1", "t1/../t2/r1/original/a.mp3")
