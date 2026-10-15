"""Rater kit (P4.4): blind export, strict import, weighted kappa."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from export_sheet import main as export_main
from import_scores import ScoreImportError, read_scores
from kit import load_rubric_dimensions
from practice_agreement import main as agreement_main
from practice_agreement import weighted_kappa

ROOT = Path(__file__).resolve().parents[3]
TEACHING = ROOT / "rubrics" / "teaching.school.v0.1.yaml"
KEYS = [d.key for d in load_rubric_dimensions(TEACHING)]


# --- weighted kappa --------------------------------------------------------------------------------------------------


def test_identical_ratings_have_kappa_one() -> None:
    assert weighted_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(1.0)


def test_hand_computed_quadratic_kappa() -> None:
    # Pairs (1,1) (1,2) (2,2) (2,2). Weights (i-j)^2/16. Observed weighted disagreement: 1/16.
    # Marginals A {1:2, 2:2}, B {1:1, 2:3}: expected E(1,2)=1.5, E(2,1)=0.5 -> weighted 2/16. kappa = 1 - 1/2 = 0.5.
    assert weighted_kappa([1, 1, 2, 2], [1, 2, 2, 2]) == pytest.approx(0.5)


def test_larger_disagreements_cost_more() -> None:
    near = weighted_kappa([1, 2, 3, 4, 5, 3], [2, 2, 3, 4, 5, 3])
    far = weighted_kappa([1, 2, 3, 4, 5, 3], [5, 2, 3, 4, 5, 3])
    assert near is not None and far is not None
    assert near > far


def test_kappa_is_undefined_without_variation() -> None:
    # Both raters gave every item a 3: chance agreement is total, so kappa cannot be computed.
    assert weighted_kappa([3, 3, 3], [3, 3, 3]) is None


def test_kappa_needs_paired_ratings() -> None:
    with pytest.raises(ValueError):
        weighted_kappa([1, 2], [1])


# --- export ---------------------------------------------------------------------------------------------------------


def export(tmp_path: Path, *raters: str) -> Path:
    out = tmp_path / "sheets"
    code = export_main([
        "--rubric", str(TEACHING), "--recordings", "lesson-1", "lesson-2", "--raters", *raters,
        "--out-dir", str(out), "--app-url", "https://app.example.in", "--seed", "1",
    ])  # fmt: skip
    assert code == 0
    return out


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_export_writes_one_blank_sheet_per_rater(tmp_path: Path) -> None:
    out = export(tmp_path, "r1", "r2", "r3")
    for rater in ("r1", "r2", "r3"):
        rows = read_csv(out / f"scores-{rater}.csv")
        assert len(rows) == 2 * len(KEYS)
        assert {(r["recording_id"], r["dimension_key"]) for r in rows} == {
            (rec, key) for rec in ("lesson-1", "lesson-2") for key in KEYS
        }
        assert all(r["score"] == "" and r["note"] == "" for r in rows)
        assert all(r["transcript_link"].startswith("https://app.example.in/recordings/") for r in rows)


def test_export_never_contains_ai_scores(tmp_path: Path) -> None:
    out = export(tmp_path, "r1")
    header = (out / "scores-r1.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header == "rater_id,recording_id,dimension_key,dimension_name,score,note,transcript_link"


def test_export_shuffles_order_per_rater(tmp_path: Path) -> None:
    out = export(tmp_path, "r1", "r2")
    order = [[(r["recording_id"], r["dimension_key"]) for r in read_csv(out / f"scores-{r}.csv")] for r in ("r1", "r2")]
    assert order[0] != order[1]  # raters do not see items in the same order


def test_export_writes_the_anchor_reference(tmp_path: Path) -> None:
    out = export(tmp_path, "r1")
    anchors = read_csv(out / "anchors.csv")
    assert len(anchors) == len(KEYS) * 5
    first = next(a for a in anchors if a["dimension_key"] == KEYS[0] and a["level"] == "1")
    assert first["anchor"]


# --- import ---------------------------------------------------------------------------------------------------------


def filled_sheet(tmp_path: Path, rater: str = "r1", score: str = "3") -> Path:
    out = export(tmp_path, rater)
    path = out / f"scores-{rater}.csv"
    rows = read_csv(path)
    for row in rows:
        row["score"] = score
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_import_accepts_a_complete_sheet(tmp_path: Path) -> None:
    scores = read_scores(filled_sheet(tmp_path), TEACHING)
    assert len(scores) == 2 * len(KEYS)
    assert {s.score for s in scores} == {3}


@pytest.mark.parametrize("bad", ["0", "6", "3.5", "three", "-1"])
def test_import_rejects_out_of_range_or_non_integer_scores(tmp_path: Path, bad: str) -> None:
    path = filled_sheet(tmp_path)
    text = path.read_text(encoding="utf-8").splitlines()
    text[1] = text[1].replace(",3,", f",{bad},", 1)
    path.write_text("\n".join(text) + "\n", encoding="utf-8")
    with pytest.raises(ScoreImportError, match="score must be a whole number from 1 to 5"):
        read_scores(path, TEACHING)


def test_import_rejects_a_missing_score(tmp_path: Path) -> None:
    path = filled_sheet(tmp_path)
    text = path.read_text(encoding="utf-8").splitlines()
    text[2] = text[2].replace(",3,", ",,", 1)
    path.write_text("\n".join(text) + "\n", encoding="utf-8")
    with pytest.raises(ScoreImportError, match="score is missing"):
        read_scores(path, TEACHING)


def test_import_rejects_a_missing_dimension(tmp_path: Path) -> None:
    path = filled_sheet(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")  # drop the last row
    with pytest.raises(ScoreImportError, match="not scored"):
        read_scores(path, TEACHING)


def test_import_rejects_unknown_dimensions(tmp_path: Path) -> None:
    path = filled_sheet(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace(KEYS[0], "made_up_dimension", 1), encoding="utf-8")
    with pytest.raises(ScoreImportError, match="unknown dimension"):
        read_scores(path, TEACHING)


def test_import_rejects_two_raters_in_one_sheet(tmp_path: Path) -> None:
    path = filled_sheet(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace("r1,", "r9,", 1)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ScoreImportError, match="one rater per sheet"):
        read_scores(path, TEACHING)


# --- agreement report -----------------------------------------------------------------------------------------------


def test_agreement_report_flags_targets_not_set(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sheets = [filled_sheet(tmp_path / r, r, s) for r, s in (("r1", "3"), ("r2", "3"), ("r3", "4"))]
    code = agreement_main(["--rubric", str(TEACHING), "--targets", str(tmp_path / "none.yaml"), *map(str, sheets)])
    out = capsys.readouterr().out
    assert code == 1  # constant scores give undefined kappa, so calibration cannot be confirmed
    assert "undefined" in out
    assert "threshold not set" in out
