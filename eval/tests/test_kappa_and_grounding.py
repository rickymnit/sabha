"""Calibration split, AI-vs-human agreement and grounding evaluation (P4.6), on fictional fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from calibration import HoldoutForbidden, make_split, read_calibration_manifest, recordings_for
from calibration import main as split_main
from grounding import main as grounding_main
from kappa import main as kappa_main
from kappa import median_reference

ROOT = Path(__file__).resolve().parents[2]
TEACHING = ROOT / "rubrics" / "teaching.school.v0.1.yaml"
DIMS = [
    "concept_clarity",
    "use_of_examples",
    "checks_for_understanding",
    "questioning_quality",
    "pacing",
    "recap_and_closure",
]


def write_manifest(path: Path, rows: list[tuple[str, str, str]]) -> Path:
    path.write_text("recording_id,tenant,type\n" + "".join(f"{r},{t},{k}\n" for r, t, k in rows), encoding="utf-8")
    return path


ROWS = [(f"rec-{s}-{i}", s, "teaching") for s in ("school-a", "school-b") for i in range(10)]


# --- split ----------------------------------------------------------------------------------------------------------


def test_split_is_deterministic_and_stratified(tmp_path: Path) -> None:
    rows = read_calibration_manifest(write_manifest(tmp_path / "m.csv", ROWS))
    first, second = make_split(rows, holdout_share=0.3, seed=7), make_split(rows, holdout_share=0.3, seed=7)
    assert first == second
    holdout = [r for r, part in first["assignments"].items() if part == "holdout"]
    # 3 of 10 from each school
    assert sum(r.startswith("rec-school-a") for r in holdout) == 3
    assert sum(r.startswith("rec-school-b") for r in holdout) == 3
    assert make_split(rows, holdout_share=0.3, seed=8)["assignments"] != first["assignments"]


def test_split_is_written_once(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path / "m.csv", ROWS)
    out = tmp_path / "split.json"
    args = ["split", "--manifest", str(manifest), "--out", str(out), "--holdout-share", "0.3"]
    assert split_main(args) == 0
    assert split_main(args) == 1  # never overwritten


def test_the_holdout_cannot_be_used_for_tuning(tmp_path: Path) -> None:
    split = make_split(read_calibration_manifest(write_manifest(tmp_path / "m.csv", ROWS)), holdout_share=0.3, seed=1)
    assert len(recordings_for(split, "train", purpose="tuning")) == 14
    assert len(recordings_for(split, "holdout", purpose="evaluation")) == 6
    with pytest.raises(HoldoutForbidden):
        recordings_for(split, "holdout", purpose="tuning")


# --- kappa ----------------------------------------------------------------------------------------------------------


def test_reference_is_the_median_of_an_odd_number_of_raters() -> None:
    assert median_reference([2, 3, 2]) == 2
    assert median_reference([1, 5, 4]) == 4
    assert median_reference([2, 3]) is None  # even count: no whole-number median
    assert median_reference([4]) is None  # fewer than three raters


def ai_report(rid: str, scores: dict[str, int | None], *, model: str = "o3-mini", prompt_sha: str = "a" * 64,
              grounding: tuple[int, int] = (2, 2), attempts: int = 1) -> dict[str, Any]:  # fmt: skip
    return {
        "version": "analysis@v1",
        "model_ids": [model],
        "prompts": {"scoring.request": {"version": "1", "sha256": prompt_sha}},
        "dimensions": [
            {"key": k, "verified": s is not None, "score": s, "attempts": attempts,
             "grounding": {"quotes_offered": grounding[0], "quotes_verified": grounding[1] if s is not None else 0}}
            for k, s in scores.items()
        ],
    }  # fmt: skip


@pytest.fixture
def calibration(tmp_path: Path) -> dict[str, Path]:
    """4 holdout recordings with hand-made scores for concept_clarity; every other dimension constant."""
    rids = ["c1", "c2", "c3", "c4"]
    split = {"seed": 0, "holdout_share": 1.0, "assignments": {r: "holdout" for r in rids}}
    (tmp_path / "split.json").write_text(json.dumps(split), encoding="utf-8")
    # concept_clarity: AI [1, 1, 2, 2]; raters (1,1,2) (2,2,3) (2,1,2) (2,3,2) -> medians [1, 2, 2, 2].
    # Hand-computed quadratic-weighted kappa of [1,1,2,2] vs [1,2,2,2] is 0.5 (see eval/raters tests).
    ai = {"c1": 1, "c2": 1, "c3": 2, "c4": 2}
    raters = {"c1": (1, 1, 2), "c2": (2, 2, 3), "c3": (2, 1, 2), "c4": (2, 3, 2)}
    ai_dir = tmp_path / "ai"
    ai_dir.mkdir()
    for rid in rids:
        scores: dict[str, int | None] = {k: 3 for k in DIMS}
        scores["concept_clarity"] = ai[rid]
        (ai_dir / f"{rid}.json").write_text(json.dumps(ai_report(rid, scores)), encoding="utf-8")
    records = []
    for rid in rids:
        for n, rater in enumerate(("r1", "r2", "r3")):
            for k in DIMS:
                score = raters[rid][n] if k == "concept_clarity" else 3
                records.append({"recording_id": rid, "rater_id": rater, "dimension": k, "score": score, "note": ""})
    (tmp_path / "scores.json").write_text(json.dumps(records), encoding="utf-8")
    return {"split": tmp_path / "split.json", "ai": ai_dir, "scores": tmp_path / "scores.json", "out": tmp_path / "rep"}


def run_kappa(c: dict[str, Path]) -> tuple[int, dict[str, Any]]:
    code = kappa_main([
        "--rubric", str(TEACHING), "--split", str(c["split"]), "--ai-dir", str(c["ai"]),
        "--rater-scores", str(c["scores"]), "--out-dir", str(c["out"]),
    ])  # fmt: skip
    return code, json.loads(next(c["out"].glob("kappa-*.json")).read_text(encoding="utf-8"))


def test_hand_computed_kappa_against_the_human_median(calibration: dict[str, Path]) -> None:
    _, report = run_kappa(calibration)
    concept = next(d for d in report["dimensions"] if d["key"] == "concept_clarity")
    assert concept["n"] == 4
    assert concept["kappa"] == pytest.approx(0.5)
    assert concept["exact_agreement"] == pytest.approx(0.75)  # c1, c3, c4 equal
    assert concept["within_one"] == pytest.approx(1.0)
    assert concept["status"] == "FAIL"  # 0.5 < 0.60, the rubric's visibility gate
    assert report["threshold"] == pytest.approx(0.6)


def test_constant_scores_are_not_assessed_rather_than_passed(calibration: dict[str, Path]) -> None:
    _, report = run_kappa(calibration)
    pacing = next(d for d in report["dimensions"] if d["key"] == "pacing")
    assert pacing["kappa"] is None  # everyone gave 3: kappa undefined
    assert pacing["status"] == "not assessed"


def test_unverified_ai_dimensions_are_excluded_and_counted(calibration: dict[str, Path]) -> None:
    path = calibration["ai"] / "c1.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    for d in doc["dimensions"]:
        if d["key"] == "concept_clarity":
            d["verified"], d["score"] = False, None
    path.write_text(json.dumps(doc), encoding="utf-8")
    code, report = run_kappa(calibration)
    concept = next(d for d in report["dimensions"] if d["key"] == "concept_clarity")
    assert concept["n"] == 3
    assert concept["excluded"]["ai_unverified"] == 1
    assert code == 1  # nothing passes


def test_only_the_requested_split_is_scored(calibration: dict[str, Path]) -> None:
    split = json.loads(calibration["split"].read_text(encoding="utf-8"))
    split["assignments"]["c4"] = "train"
    calibration["split"].write_text(json.dumps(split), encoding="utf-8")
    _, report = run_kappa(calibration)
    assert next(d for d in report["dimensions"] if d["key"] == "concept_clarity")["n"] == 3


# --- grounding ------------------------------------------------------------------------------------------------------


def test_grounding_shares_per_model_and_prompt_version(tmp_path: Path) -> None:
    ai_dir = tmp_path / "ai"
    ai_dir.mkdir()
    reports = [
        ai_report("g1", {"a": 4, "b": None}, grounding=(2, 1)),  # b is unverified, so its verified count is 0
        ai_report("g2", {"a": 3, "b": 4}, grounding=(2, 2), attempts=2),
        ai_report("g3", {"a": 5, "b": 5}, model="other-model", grounding=(1, 1)),
    ]
    for n, r in enumerate(reports, start=1):
        (ai_dir / f"g{n}.json").write_text(json.dumps(r), encoding="utf-8")
    out = tmp_path / "rep"
    assert grounding_main(["--ai-dir", str(ai_dir), "--out-dir", str(out)]) == 0
    data = json.loads(next(out.glob("grounding-*.json")).read_text(encoding="utf-8"))
    groups = {g["model_ids"]: g for g in data["groups"]}
    o3 = groups["o3-mini"]
    # g1: a offered 2 verified 1, b (unverified) offered 2 verified 0; g2: both offered 2 verified 2 -> 5 of 8.
    assert (o3["quotes_offered"], o3["quotes_verified"]) == (8, 5)
    assert o3["dimensions"] == 4 and o3["excluded"] == 1 and o3["verified_after_reask"] == 2
    assert groups["other-model"]["quotes_verified_share"] == pytest.approx(1.0)
