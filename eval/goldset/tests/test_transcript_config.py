"""infra/annotation/transcript_config.xml parses and matches the names export_gold.py relies on."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from goldset_common import (
    AUDIO_DATA_KEY,
    AUDIO_TAG_NAME,
    LABEL_TO_ROLE,
    LABELS_TAG_NAME,
    TEXT_TAG_NAME,
)

CONFIG = Path(__file__).resolve().parents[3] / "infra" / "annotation" / "transcript_config.xml"


def _root() -> ET.Element:
    return ET.parse(CONFIG).getroot()  # noqa: S314  # our own committed config file, not untrusted input


def test_config_parses_with_view_root() -> None:
    assert _root().tag == "View"


def test_audio_labels_and_textarea_names() -> None:
    root = _root()
    audio = root.findall(".//Audio")
    labels = root.findall(".//Labels")
    textareas = root.findall(".//TextArea")
    assert len(audio) == len(labels) == len(textareas) == 1
    assert audio[0].get("name") == AUDIO_TAG_NAME
    assert audio[0].get("value") == f"${AUDIO_DATA_KEY}"
    assert labels[0].get("name") == LABELS_TAG_NAME
    assert labels[0].get("toName") == AUDIO_TAG_NAME
    assert labels[0].get("choice", "single") == "single"
    assert textareas[0].get("name") == TEXT_TAG_NAME
    assert textareas[0].get("toName") == AUDIO_TAG_NAME
    assert textareas[0].get("perRegion") == "true"
    assert textareas[0].get("maxSubmissions") == "1"


def test_label_values_match_speaker_roles() -> None:
    labels = _root().findall(".//Labels/Label")
    assert [label.get("value") for label in labels] == list(LABEL_TO_ROLE)
    hotkeys = [label.get("hotkey") for label in labels]
    assert len(set(hotkeys)) == len(hotkeys)


def test_names_unique() -> None:
    names = [el.get("name") for el in _root().iter() if el.get("name")]
    assert len(names) == len(set(names))
