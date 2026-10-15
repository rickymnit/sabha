"""Word and character error rates (P4.3): hand-computed cases, aggregation and bootstrap."""

from __future__ import annotations

import pytest
from wer import Counts, FileResult, align, bootstrap_ci, corpus_counts, group_results


def counts(ref: str, hyp: str) -> Counts:
    return align(ref.split(), hyp.split())


def test_identical_text_has_no_errors() -> None:
    c = counts("a b c d", "a b c d")
    assert (c.ref_words, c.substitutions, c.deletions, c.insertions) == (4, 0, 0, 0)
    assert c.wer == 0.0


def test_one_substitution_and_one_insertion() -> None:
    # ref: a b c d / hyp: a x c d e  ->  b->x substituted, e inserted: WER = 2/4
    c = counts("a b c d", "a x c d e")
    assert (c.substitutions, c.deletions, c.insertions) == (1, 0, 1)
    assert c.wer == pytest.approx(0.5)


def test_everything_deleted() -> None:
    c = counts("a b c", "")
    assert (c.substitutions, c.deletions, c.insertions) == (0, 3, 0)
    assert c.wer == 1.0


def test_wer_can_exceed_one_with_insertions() -> None:
    c = counts("a", "x y z")
    assert c.errors == 3
    assert c.wer == pytest.approx(3.0)


def test_empty_reference_has_no_defined_wer() -> None:
    c = counts("", "a b")
    assert c.insertions == 2
    assert c.wer is None


def test_classic_example() -> None:
    # "the cat sat on the mat" vs "the cat sit on mat": 1 substitution (sat->sit), 1 deletion (the) = 2/6
    c = counts("the cat sat on the mat", "the cat sit on mat")
    assert (c.substitutions, c.deletions, c.insertions) == (1, 1, 0)
    assert c.wer == pytest.approx(2 / 6)


def test_privacy_token_matches_any_single_word() -> None:
    c = counts("[student] की copy", "aman की copy")
    assert c.errors == 0
    assert c.wildcard_matches == 1


def test_privacy_token_is_still_deleted_when_nothing_was_heard() -> None:
    c = counts("[student] की copy", "की copy")
    assert c.deletions == 1


def test_character_errors_follow_the_word_alignment() -> None:
    # sat->sit is 1 character; deleted "the" is 3 characters; reference has 3+3+3+2+3+3 = 17 characters without spaces.
    c = counts("the cat sat on the mat", "the cat sit on mat")
    assert c.ref_chars == 17
    assert c.char_errors == 4
    assert c.cer == pytest.approx(4 / 17)


def test_wildcard_match_has_no_character_errors() -> None:
    c = counts("[student] ok", "aman ok")
    assert c.char_errors == 0


def _result(rid: str, ref_words: int, errors: int, *, mix: str = "hinglish", room: str = "classroom") -> FileResult:
    c = Counts(ref_words=ref_words, substitutions=errors, deletions=0, insertions=0, ref_chars=ref_words * 4,
               char_errors=errors)  # fmt: skip
    return FileResult(recording_id=rid, language_mix=mix, room_type=room, raw=c, transliterated=c)


def test_corpus_wer_is_word_weighted_not_a_mean_of_files() -> None:
    results = [_result("f1", 4, 1), _result("f2", 6, 3)]
    total = corpus_counts(r.raw for r in results)
    # (1 + 3) / (4 + 6) = 0.4, not the mean of 0.25 and 0.5 (0.375).
    assert total.wer == pytest.approx(0.4)


def test_results_group_by_language_mix_and_room_type() -> None:
    results = [_result("a", 10, 1, mix="hindi"), _result("b", 10, 3, mix="hindi"), _result("c", 10, 5, mix="english")]
    groups = group_results(results, key=lambda r: r.language_mix)
    assert sorted(groups) == ["english", "hindi"]
    assert corpus_counts(r.raw for r in groups["hindi"]).wer == pytest.approx(0.2)


def test_bootstrap_is_reproducible_with_a_seed_and_brackets_the_estimate() -> None:
    results = [_result(f"f{i}", 100, e) for i, e in enumerate([5, 10, 15, 20, 25, 30])]
    first = bootstrap_ci(results, lambda r: r.raw, seed=7, iterations=500)
    second = bootstrap_ci(results, lambda r: r.raw, seed=7, iterations=500)
    assert first == second
    assert first is not None
    low, high = first
    estimate = corpus_counts(r.raw for r in results).wer
    assert estimate is not None
    assert low <= estimate <= high


def test_bootstrap_needs_at_least_two_files() -> None:
    assert bootstrap_ci([_result("only", 100, 5)], lambda r: r.raw, seed=0) is None
