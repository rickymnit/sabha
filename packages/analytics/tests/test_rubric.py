"""Tests for sabha_analytics.rubric and the sabha-rubric CLI: schema, content hash, immutable versions (P5.4).

Written before the implementation. Invalid rubrics are made by changing one thing in a valid file, so each test
fails for exactly the reason it names.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from sabha_analytics import cli
from sabha_analytics.rubric import (
    InMemoryRubricStore,
    PublishOutcome,
    Rubric,
    RubricError,
    RubricVersionConflictError,
    RubricVersionExistsError,
    canonical_json,
    diff_rubrics,
    find_previous_version,
    load_rubric,
    parse_rubric,
    publish_rubric,
    rubric_hash,
)

REPO = Path(__file__).resolve().parents[3]
RUBRICS = REPO / "rubrics"
TEACHING = RUBRICS / "teaching.school.v0.1.yaml"
RECEPTION = RUBRICS / "reception.school.v0.1.yaml"
RECEPTION_V0_2 = RUBRICS / "reception.school.v0.2.yaml"
FIXTURE = Path(__file__).parent / "fixtures" / "rubrics" / "teaching.testing.v1.0.yaml"


def fixture_data() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    return data


def write(folder: Path, data: dict[str, Any], name: str | None = None) -> Path:
    path = folder / (name or f"{data['id']}.yaml")
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def problems_of(data: dict[str, Any], tmp_path: Path) -> str:
    """Load a changed copy of the fixture and return all problems as one string; fails if it loads."""
    with pytest.raises(RubricError) as caught:
        load_rubric(write(tmp_path, data))
    assert caught.value.problems, "a RubricError must name at least one problem"
    return "\n".join(caught.value.problems)


def changed(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    data = copy.deepcopy(fixture_data())
    change(data)
    return data


# --- the existing draft files ----------------------------------------------------------------------------------


def test_teaching_v0_1_validates() -> None:
    rubric, content_hash = load_rubric(TEACHING)
    assert (rubric.id, rubric.type, rubric.segment, rubric.version) == (
        "teaching.school.v0.1",
        "teaching",
        "school",
        "0.1",
    )
    assert rubric.roles == ("teacher", "students")
    assert rubric.primary_role == "teacher"
    assert [d.key for d in rubric.dimensions] == [
        "concept_clarity",
        "use_of_examples",
        "checks_for_understanding",
        "questioning_quality",
        "pacing",
        "recap_and_closure",
    ]
    assert rubric.computed_metrics[0] == "teacher_talk_share"
    assert rubric.output == ("summary", "strengths", "gaps", "suggestions")
    assert rubric.output_values is None
    assert (rubric.visibility_gate.metric, rubric.visibility_gate.min) == ("cohens_kappa", 0.60)
    assert re.fullmatch(r"[0-9a-f]{64}", content_hash)


def test_reception_v0_1_validates_with_output_values() -> None:
    rubric, _ = load_rubric(RECEPTION)
    assert (rubric.type, rubric.segment, rubric.version) == ("reception", "school", "0.1")
    assert rubric.primary_role == "receptionist"
    assert len(rubric.dimensions) == 5
    assert "call_duration_s" in rubric.computed_metrics
    assert rubric.output_values is not None
    assert rubric.output_values["status"] == ("resolved", "follow_up_needed", "escalated")
    assert "complaint" in rubric.output_values["category"]


def test_reception_v0_2_is_v0_1_plus_not_applicable_escalation() -> None:
    # Reviewed and approved as-is by the academic head (2026-10-20); escalation is not applicable on calls with
    # nothing to escalate (owner's decision).
    old, _ = load_rubric(RECEPTION)
    new, _ = load_rubric(RECEPTION_V0_2)
    assert new.version == "0.2"
    changes = diff_rubrics(old, new)
    assert [(c.dimension, c.item) for c in changes] == [("escalation_handling", "not_applicable_when")]
    escalation = next(d for d in new.dimensions if d.key == "escalation_handling")
    assert escalation.not_applicable_when is not None and "nothing to escalate" in escalation.not_applicable_when
    assert all(d.not_applicable_when is None for d in new.dimensions if d.key != "escalation_handling")


def test_not_applicable_when_must_not_be_blank(tmp_path: Path) -> None:
    def blank(data: dict[str, Any]) -> None:
        data["dimensions"][0]["not_applicable_when"] = "   "

    assert "not_applicable_when" in problems_of(changed(blank), tmp_path)


def test_adding_the_optional_field_keeps_old_hashes() -> None:
    # exclude_none: rubrics without not_applicable_when hash exactly as before the field existed.
    rubric, content_hash = load_rubric(RECEPTION)
    assert "not_applicable_when" not in canonical_json(rubric)
    assert rubric_hash(rubric) == content_hash


def test_dimension_interface_agreed_with_scoring() -> None:
    rubric, _ = load_rubric(TEACHING)
    dimension = rubric.dimensions[0]
    assert dimension.key == "concept_clarity"
    assert dimension.name == "Concept clarity"
    assert dimension.weight == 0.25
    assert dimension.definition.startswith("The teacher states the main idea")
    assert dimension.min_quotes == 2
    assert sorted(dimension.anchors) == [1, 2, 3, 4, 5]
    assert dimension.anchors[1].startswith("The teacher never states the main idea")
    assert sorted(dimension.examples) == [1, 5]
    assert isinstance(rubric.dimensions, tuple)
    assert isinstance(rubric.roles, tuple)
    assert isinstance(rubric.computed_metrics, tuple)


def test_models_are_immutable() -> None:
    rubric, _ = load_rubric(FIXTURE)
    with pytest.raises(ValidationError):
        rubric.version = "9.9"  # assigning to a frozen model must fail
    with pytest.raises(TypeError):
        rubric.dimensions[0].anchors[1] = "changed"  # type: ignore[index]  # anchors are read-only mappings


# --- validation ------------------------------------------------------------------------------------------------


def test_fixture_is_valid() -> None:
    rubric, _ = load_rubric(FIXTURE)
    assert rubric.id == "teaching.testing.v1.0"


def test_weights_must_sum_to_one(tmp_path: Path) -> None:
    data = changed(lambda d: d["dimensions"][0].update(weight=0.7))  # 0.7 + 0.4 = 1.1
    assert "sum" in problems_of(data, tmp_path)


def test_weights_within_tolerance_are_accepted() -> None:
    parse_rubric(changed(lambda d: d["dimensions"][0].update(weight=0.6009)))  # sum 1.0009, inside +-0.001


def test_weights_just_outside_tolerance_fail() -> None:
    with pytest.raises(RubricError, match="sum"):
        parse_rubric(changed(lambda d: d["dimensions"][0].update(weight=0.602)))  # sum 1.002


def test_weight_must_be_positive(tmp_path: Path) -> None:
    def change(d: dict[str, Any]) -> None:
        d["dimensions"][0]["weight"] = 0.0
        d["dimensions"][1]["weight"] = 1.0

    assert "weight" in problems_of(changed(change), tmp_path)


def test_missing_anchor_fails(tmp_path: Path) -> None:
    data = changed(lambda d: d["dimensions"][1]["anchors"].pop(3))
    problems = problems_of(data, tmp_path)
    assert "anchor" in problems
    assert "3" in problems


def test_extra_anchor_fails() -> None:
    with pytest.raises(RubricError, match="anchor"):
        parse_rubric(changed(lambda d: d["dimensions"][0]["anchors"].update({6: "Beyond the scale."})))


def test_blank_anchor_fails(tmp_path: Path) -> None:
    data = changed(lambda d: d["dimensions"][0]["anchors"].update({4: "   "}))
    assert "anchors" in problems_of(data, tmp_path)


def test_examples_need_levels_1_and_5(tmp_path: Path) -> None:
    data = changed(lambda d: d["dimensions"][0]["examples"].pop(5))
    assert "example" in problems_of(data, tmp_path)


def test_duplicate_dimension_key_fails(tmp_path: Path) -> None:
    data = changed(lambda d: d["dimensions"][1].update(key="concept_clarity"))
    assert "duplicate" in problems_of(data, tmp_path)


def test_dimension_key_must_be_snake_case() -> None:
    with pytest.raises(RubricError, match="key"):
        parse_rubric(changed(lambda d: d["dimensions"][0].update(key="ConceptClarity")))


def test_min_quotes_at_least_one(tmp_path: Path) -> None:
    data = changed(lambda d: d["dimensions"][0].update(min_quotes=0))
    assert "min_quotes" in problems_of(data, tmp_path)


@pytest.mark.parametrize(
    "gate",
    [
        {"metric": "accuracy", "min": 0.6},
        {"metric": "cohens_kappa", "min": 0},
        {"metric": "cohens_kappa", "min": 1.5},
        {"metric": "cohens_kappa"},
    ],
)
def test_visibility_gate_rules(gate: dict[str, Any]) -> None:
    with pytest.raises(RubricError, match="visibility_gate"):
        parse_rubric(changed(lambda d: d.update(visibility_gate=gate)))


def test_visibility_gate_of_one_is_allowed() -> None:
    rubric = parse_rubric(changed(lambda d: d.update(visibility_gate={"metric": "cohens_kappa", "min": 1})))
    assert rubric.visibility_gate.min == 1.0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("segment", "college"),  # id says testing
        ("version", "1.1"),  # id says 1.0
        ("id", "lesson.testing.v1.0"),  # not a conversation type
        ("id", "teaching.testing.1.0"),  # no "v"
    ],
)
def test_id_must_match_type_segment_and_version(field: str, value: str) -> None:
    with pytest.raises(RubricError, match="id"):
        parse_rubric(changed(lambda d: d.update({field: value})))


@pytest.mark.parametrize("version", ["1", "v1.0", "1.0.0", "01.0", 1.0])
def test_version_must_be_a_major_minor_string(version: object) -> None:
    with pytest.raises(RubricError, match="version"):
        parse_rubric(changed(lambda d: d.update(version=version)))


def test_file_name_must_match_id(tmp_path: Path) -> None:
    path = write(tmp_path, fixture_data(), name="teaching.testing.v2.0.yaml")
    with pytest.raises(RubricError, match="file name"):
        load_rubric(path)


def test_unknown_top_level_key_fails() -> None:
    with pytest.raises(RubricError, match="weigths"):
        parse_rubric(changed(lambda d: d.update(weigths=[0.5, 0.5])))


def test_duplicate_yaml_key_fails(tmp_path: Path) -> None:
    text = FIXTURE.read_text(encoding="utf-8").replace(
        '      4: "The main idea is stated and every key term is defined."',
        '      3: "A second level-3 anchor."',
        1,
    )
    path = tmp_path / FIXTURE.name
    path.write_text(text, encoding="utf-8")
    with pytest.raises(RubricError, match="duplicate key"):
        load_rubric(path)


def test_unknown_computed_metric_fails() -> None:
    with pytest.raises(RubricError, match="teacher_happiness"):
        parse_rubric(changed(lambda d: d["computed_metrics"].append("teacher_happiness")))


def test_role_metric_needs_the_role_in_the_rubric() -> None:
    with pytest.raises(RubricError, match="caller_talk_share"):
        parse_rubric(changed(lambda d: d["computed_metrics"].append("caller_talk_share")))


def test_output_values_must_name_an_output_section() -> None:
    with pytest.raises(RubricError, match="output_values"):
        parse_rubric(changed(lambda d: d.update(output_values={"category": ["fee_query"]})))


def test_output_values_for_a_listed_section_are_accepted() -> None:
    def change(d: dict[str, Any]) -> None:
        d["output"].append("category")
        d["output_values"] = {"category": ["fee_query", "other"]}

    rubric = parse_rubric(changed(change))
    assert rubric.output_values is not None
    assert rubric.output_values["category"] == ("fee_query", "other")


def test_not_a_mapping_fails(tmp_path: Path) -> None:
    path = tmp_path / FIXTURE.name
    path.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(RubricError):
        load_rubric(path)


def test_invalid_yaml_fails(tmp_path: Path) -> None:
    path = tmp_path / FIXTURE.name
    path.write_text("id: [unclosed\n", encoding="utf-8")
    with pytest.raises(RubricError, match="YAML"):
        load_rubric(path)


# --- content hash ----------------------------------------------------------------------------------------------


def test_hash_ignores_comments_whitespace_and_key_order(tmp_path: Path) -> None:
    _, original = load_rubric(FIXTURE)
    data = fixture_data()
    reordered = {key: data[key] for key in reversed(list(data))}  # same content, different key order
    reordered["dimensions"] = [{k: v for k, v in reversed(list(dim.items()))} for dim in data["dimensions"]]
    path = tmp_path / FIXTURE.name
    path.write_text("# a new comment\n\n" + yaml.safe_dump(reordered, sort_keys=False, indent=4), encoding="utf-8")
    _, rewritten = load_rubric(path)
    assert rewritten == original


def test_hash_changes_when_content_changes() -> None:
    base = parse_rubric(fixture_data())
    edited = parse_rubric(changed(lambda d: d["dimensions"][0]["anchors"].update({3: "Changed wording."})))
    assert rubric_hash(base) != rubric_hash(edited)


def test_hash_is_stable_for_the_same_model() -> None:
    assert rubric_hash(parse_rubric(fixture_data())) == rubric_hash(parse_rubric(fixture_data()))


# --- publishing: immutable versions ----------------------------------------------------------------------------


def test_publish_new_version() -> None:
    store = InMemoryRubricStore()
    rubric, content_hash = load_rubric(FIXTURE)
    assert publish_rubric(rubric, content_hash, store) is PublishOutcome.PUBLISHED
    assert store.get("teaching", "testing", "1.0") == content_hash


def test_republishing_same_content_is_idempotent(tmp_path: Path) -> None:
    store = InMemoryRubricStore()
    rubric, content_hash = load_rubric(FIXTURE)
    publish_rubric(rubric, content_hash, store)
    # The same content with different comments and layout hashes the same, so it is a no-op too.
    path = tmp_path / FIXTURE.name
    path.write_text("# reformatted\n" + yaml.safe_dump(fixture_data(), sort_keys=True), encoding="utf-8")
    again, again_hash = load_rubric(path)
    assert publish_rubric(again, again_hash, store) is PublishOutcome.UNCHANGED
    assert len(store) == 1


def test_changed_content_without_version_bump_fails() -> None:
    store = InMemoryRubricStore()
    rubric, content_hash = load_rubric(FIXTURE)
    publish_rubric(rubric, content_hash, store)
    edited = parse_rubric(changed(lambda d: d["dimensions"][0].update(definition="A different definition.")))
    with pytest.raises(RubricVersionConflictError, match="bump the version"):
        publish_rubric(edited, rubric_hash(edited), store)
    assert store.get("teaching", "testing", "1.0") == content_hash  # the published version is untouched


def test_changed_content_with_version_bump_publishes() -> None:
    store = InMemoryRubricStore()
    rubric, content_hash = load_rubric(FIXTURE)
    publish_rubric(rubric, content_hash, store)

    def bump(d: dict[str, Any]) -> None:
        d["version"] = "1.1"
        d["id"] = "teaching.testing.v1.1"
        d["dimensions"][0]["definition"] = "A different definition."

    bumped = parse_rubric(changed(bump))
    assert publish_rubric(bumped, rubric_hash(bumped), store) is PublishOutcome.PUBLISHED
    assert len(store) == 2


def test_store_insert_refuses_an_existing_version() -> None:
    store = InMemoryRubricStore()
    rubric, content_hash = load_rubric(FIXTURE)
    store.insert(rubric, content_hash)
    with pytest.raises(RubricVersionExistsError):
        store.insert(rubric, content_hash)


def test_publish_rejects_a_hash_that_does_not_match_the_rubric() -> None:
    rubric, _ = load_rubric(FIXTURE)
    with pytest.raises(ValueError, match="hash"):
        publish_rubric(rubric, "0" * 64, InMemoryRubricStore())


# --- diff ------------------------------------------------------------------------------------------------------


def test_diff_of_identical_rubrics_is_empty() -> None:
    rubric = parse_rubric(fixture_data())
    assert diff_rubrics(rubric, rubric) == ()


def test_diff_reports_weights_anchors_definitions_and_dimensions() -> None:
    old = parse_rubric(fixture_data())

    def change(d: dict[str, Any]) -> None:
        d["dimensions"][0]["weight"] = 0.5
        d["dimensions"][0]["anchors"][2] = "New level-2 wording."
        d["dimensions"][1]["definition"] = "New definition."
        d["dimensions"][1]["weight"] = 0.3
        extra = copy.deepcopy(d["dimensions"][1])
        extra.update(key="use_of_examples", name="Use of examples", weight=0.2)
        d["dimensions"].append(extra)

    new = parse_rubric(changed(change))
    lines = [str(change) for change in diff_rubrics(old, new)]
    assert any("concept_clarity" in line and "weight" in line and "0.6" in line and "0.5" in line for line in lines)
    assert any("concept_clarity" in line and "anchors[2]" in line for line in lines)
    assert any("recap_and_closure" in line and "definition" in line for line in lines)
    assert any("use_of_examples" in line and "added" in line for line in lines)
    assert not any("anchors[1]" in line for line in lines)


def test_diff_reports_a_removed_dimension() -> None:
    old = parse_rubric(fixture_data())

    def change(d: dict[str, Any]) -> None:
        d["dimensions"].pop()
        d["dimensions"][0]["weight"] = 1.0

    lines = [str(c) for c in diff_rubrics(old, parse_rubric(changed(change)))]
    assert any("recap_and_closure" in line and "removed" in line for line in lines)


def test_find_previous_version_compares_numbers_not_text(tmp_path: Path) -> None:
    for version in ("0.9", "0.10", "1.0", "2.0"):
        major, minor = version.split(".")
        (tmp_path / f"teaching.testing.v{major}.{minor}.yaml").write_text("", encoding="utf-8")
    (tmp_path / "reception.testing.v0.95.yaml").write_text("", encoding="utf-8")  # another type: ignored
    assert find_previous_version(tmp_path / "teaching.testing.v1.0.yaml") == tmp_path / "teaching.testing.v0.10.yaml"
    assert find_previous_version(tmp_path / "teaching.testing.v0.9.yaml") is None


# --- CLI -------------------------------------------------------------------------------------------------------


def test_cli_validate_ok(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["validate", str(TEACHING), str(RECEPTION)]) == 0
    out = capsys.readouterr().out
    assert "teaching.school.v0.1" in out
    assert "reception.school.v0.1" in out


def test_cli_validate_reports_problems(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, changed(lambda d: d["dimensions"][0].update(weight=0.9)))
    assert cli.main(["validate", str(path)]) == 1
    assert "sum" in capsys.readouterr().out


def test_cli_diff_two_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def bump(d: dict[str, Any]) -> None:
        d["version"] = "1.1"
        d["id"] = "teaching.testing.v1.1"
        d["dimensions"][0]["anchors"][3] = "Changed."

    new = write(tmp_path, changed(bump))
    assert cli.main(["diff", str(FIXTURE), str(new)]) == 0
    assert "anchors[3]" in capsys.readouterr().out


def test_cli_diff_against_previous_version_in_folder(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, fixture_data())

    def bump(d: dict[str, Any]) -> None:
        d["version"] = "1.1"
        d["id"] = "teaching.testing.v1.1"
        d["dimensions"][1]["definition"] = "Changed."

    new = write(tmp_path, changed(bump))
    assert cli.main(["diff", str(new)]) == 0
    out = capsys.readouterr().out
    assert "teaching.testing.v1.0" in out
    assert "definition" in out


def test_cli_diff_without_previous_version_fails(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["diff", str(FIXTURE)]) == 1
    assert "no previous version" in capsys.readouterr().err


def test_cli_publish_is_a_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["publish", str(TEACHING)]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "P1.6" in out


def test_cli_publish_version_conflict_exits_non_zero(capsys: pytest.CaptureFixture[str]) -> None:
    store = InMemoryRubricStore()
    edited = parse_rubric(changed(lambda d: d["dimensions"][0].update(name="Renamed")))
    store.insert(edited, rubric_hash(edited))  # someone already published different content as v1.0
    assert cli.main(["publish", str(FIXTURE)], store=store) == 1
    assert "bump the version" in capsys.readouterr().err


def test_cli_publish_same_content_twice_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    store = InMemoryRubricStore()
    assert cli.main(["publish", str(FIXTURE)], store=store) == 0
    assert cli.main(["publish", str(FIXTURE)], store=store) == 0
    assert "unchanged" in capsys.readouterr().out


def test_rubric_is_exported_type() -> None:
    assert isinstance(parse_rubric(fixture_data()), Rubric)
