"""Rechecking findings on the agent as it is now: its arms, Trace's answer read as four phrases, and side by side.

Plan BK7.14 (`recheck` runs each finding over the same cases as its reference arm, names its arms
`<hunt>-recheck-<n>-<finding>`, and maps Trace's verdict and direction to exactly one of four phrases), BK7.15 (the
JSON, not the exit code), BK7.16 (`--old` runs both in the same session and compares those two; without it the gap in
days since the reference run), BK7.17 (`inputs.left_out` shown), BK7.20 (recheck rows carry their stage and name the
finding); spec §6.2. Rulings 17 (`recheck`, `Rechecked`), 18 (the four phrases) and 19 (the finding named through
the arm) of `evidence/bk7/open-points.md`.

The agent "as it is now" is the desk opened again: mended (`Coin(weak=MENDED)`: a landed `error` fails no more
than the control), made worse (`Coin(weak=1.0)`), or left alone.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from tests import confirm_targets as targets
from tests.confirm_support import (
    PHRASES,
    PLANTED,
    RECHECK,
    adjusted,
    confirm_module,
    fix_checks,
    hunt_module,
    name_of,
    open_scenario,
    per_case,
    ready,
    record,
    refused,
    rows,
    seeds,
    stand_in,
    trace_document,
)


@pytest.fixture
def trace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return stand_in(monkeypatch, tmp_path)


def _confirmed(tmp_path: Path, scenario: Any, **over: Any) -> Any:
    h = ready(tmp_path / "hunts", scenario, **over)
    assert confirm_module().confirm(h).findings
    return h


def _now(tmp_path: Path, scenario: Any, weak: Any = None, **over: Any) -> Any:
    """The hunt opened again with the agent as it is now."""
    return open_scenario(tmp_path / "hunts", scenario, weak=weak, existing=True, **over)


def _arm_names(h: Any) -> list[str]:
    from poisson_prove.store import Store

    return sorted(Store(h.store).runs())


# ---------------------------------------------------------------------------
# BK7.14: arms, cases, names
# ---------------------------------------------------------------------------


def test_recheck_runs_each_finding_over_its_reference_arm_s_cases_in_arms_named_for_it(tmp_path: Path,
                                                                                       trace: Path) -> None:
    _confirmed(tmp_path, RECHECK)
    now = _now(tmp_path, RECHECK, weak=targets.MENDED)
    found = confirm_module().recheck(now)
    assert [r.finding for r in found] == [1, 2]
    assert [n for n in _arm_names(now) if "-recheck-" in n] == ["recheck-recheck-1-1", "recheck-recheck-1-2"]
    for r in found:
        assert (r.before, r.now) == (f"recheck-reference-{r.finding}", f"recheck-recheck-1-{r.finding}")
        assert per_case(now, f"recheck-1-{r.finding}") == per_case(now, f"reference-{r.finding}")
        assert {record(x).condition.name for x in rows(now, f"recheck-1-{r.finding}")} == {name_of(r.condition)}
    assert now.target.runs == 2 * 12 * 5


def test_recheck_rows_carry_their_stage_and_name_the_finding_through_their_arm(tmp_path: Path, trace: Path) -> None:
    _confirmed(tmp_path, RECHECK)
    now = _now(tmp_path, RECHECK, weak=targets.MENDED)
    confirm_module().recheck(now)
    for f in (1, 2):
        held = {(record(x).stage, record(x).arm) for x in rows(now, f"recheck-1-{f}")}
        assert held == {("recheck", f"recheck-recheck-1-{f}")}


def test_recheck_seeds_are_none_an_earlier_arm_used(tmp_path: Path, trace: Path) -> None:
    h = _confirmed(tmp_path, PLANTED)
    confirm_module().recheck(_now(tmp_path, PLANTED))
    earlier = set().union(*(seeds(h, n[len(h.name) + 1:]) for n in _arm_names(h) if "-recheck-" not in n))
    assert not seeds(h, "recheck-1-1") & earlier


def test_a_second_recheck_is_numbered_on(tmp_path: Path, trace: Path) -> None:
    _confirmed(tmp_path, PLANTED)
    confirm_module().recheck(_now(tmp_path, PLANTED))
    second = confirm_module().recheck(_now(tmp_path, PLANTED))
    assert second[0].now == "planted-recheck-2-1"
    assert [n for n in _arm_names(_now(tmp_path, PLANTED)) if "-recheck-" in n] == [
        "planted-recheck-1-1", "planted-recheck-2-1"]


def test_an_unfinished_recheck_is_finished_before_a_new_one_is_begun(tmp_path: Path, trace: Path) -> None:
    """Every run costs $0.001; the control, confirm and reference stages spend $0.164, so a cap of $0.1745 stops the
    recheck after ten runs. Opened again with the cap lifted, `recheck` finishes recheck 1 and begins no second."""
    priced = dataclasses.replace(PLANTED, name="priced", cases=tuple({**c, "tokens": [1000, 0]} for c in PLANTED.cases),
                                 limits={"dollars": 0.1745, "input_per_million": 1.0, "output_per_million": 1.0})
    _confirmed(tmp_path, priced)
    with pytest.raises(hunt_module().HuntStopped):
        confirm_module().recheck(_now(tmp_path, priced))
    h = _now(tmp_path, priced, limits={"dollars": 100.0})
    assert len(rows(h, "recheck-1-1")) == 10
    found = confirm_module().recheck(h)
    assert found[0].now == "priced-recheck-1-1"
    assert len(rows(h, "recheck-1-1")) == 30
    assert [n for n in _arm_names(h) if "-recheck-" in n] == ["priced-recheck-1-1"]


# ---------------------------------------------------------------------------
# BK7.14, ruling 18: four phrases, from Trace's words
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("weak, phrases", [
    pytest.param(targets.MENDED, ["fails less", "fails less"], id="mended"),
    pytest.param(None, None, id="left alone"),
    pytest.param(1.0, None, id="made worse"),
])
def test_each_phrase_is_trace_s_verdict_and_direction_on_the_recorded_runs(tmp_path: Path, trace: Path, weak: Any,
                                                                           phrases: list[str] | None) -> None:
    h = _confirmed(tmp_path, RECHECK)
    found = confirm_module().recheck(_now(tmp_path, RECHECK, weak=weak))
    docs = [trace_document(h, f"reference-{r.finding}", f"recheck-1-{r.finding}") for r in found]
    ps = adjusted([d["test"]["p"] for d in docs])
    for r, doc, p in zip(found, docs, ps, strict=True):
        if doc["verdict"] == "different" and p <= 0.05:
            want = {"failed less in new": "fails less", "failed more in new": "fails more"}[doc["direction"]]
        elif doc["verdict"] == "different":
            want = "no significant difference"
        else:
            want = doc["verdict"]
        assert r.phrase == want
        assert r.phrase in PHRASES
    if phrases is not None:
        assert [r.phrase for r in found] == phrases
    if weak == 1.0:
        assert "fails more" in [r.phrase for r in found]


@pytest.mark.parametrize("patch, want", [
    pytest.param({"verdict": "different", "direction": "failed less in new", "test.p": 0.001}, "fails less",
                 id="different, less"),
    pytest.param({"verdict": "different", "direction": "failed more in new", "test.p": 0.001}, "fails more",
                 id="different, more"),
    pytest.param({"verdict": "no significant difference", "direction": "failed more in new", "test.p": 0.6},
                 "no significant difference", id="no significant difference"),
    pytest.param({"verdict": "too small to tell", "direction": "failed less in new", "test.p": 0.3},
                 "too small to tell", id="too small to tell"),
    pytest.param({"verdict": "different", "direction": "failed less in new", "difference.points": 0.5,
                  "test.p": 0.001}, "fails less", id="the direction word, whatever the difference's sign"),
    pytest.param({"verdict": "no significant difference", "direction": "failed less in new", "test.p": 0.0001},
                 "no significant difference", id="the verdict word, whatever the p-value"),
])
def test_the_phrase_is_read_from_trace_s_words(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                               patch: dict[str, Any], want: str) -> None:
    stand_in(monkeypatch, tmp_path, patch={"recheck-1-1": {"set": patch}})
    _confirmed(tmp_path, PLANTED)
    (found,) = confirm_module().recheck(_now(tmp_path, PLANTED))
    assert found.phrase == want


def test_different_but_not_after_the_correction_across_the_findings_is_no_significant_difference(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ruling 18: two findings, the first *different, failed less* at p 0.04 and the second at p 0.9: adjusted across
    the two, 0.08, above `q`."""
    stand_in(monkeypatch, tmp_path, patch={
        "recheck-1-1": {"set": {"verdict": "different", "direction": "failed less in new", "test.p": 0.04}},
        "recheck-1-2": {"set": {"verdict": "no significant difference", "direction": "no direction", "test.p": 0.9}}})
    _confirmed(tmp_path, RECHECK)
    first, second = confirm_module().recheck(_now(tmp_path, RECHECK))
    assert (first.p, first.adjusted_p) == (0.04, adjusted([0.04, 0.9])[0])
    assert first.adjusted_p > 0.05
    assert (first.phrase, second.phrase) == ("no significant difference", "no significant difference")


@pytest.mark.parametrize("patch", [
    pytest.param({"set": {"verdict": "fixed"}}, id="a verdict word Trace does not have"),
    pytest.param({"set": {"direction": "less"}}, id="a direction word Trace does not have"),
    pytest.param({"stdout": "{not json\n"}, id="no document"),
    pytest.param({"stdout": "", "exit": 1}, id="nothing printed and an exit of 1"),
])
def test_a_word_trace_does_not_have_is_no_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                 patch: dict[str, Any]) -> None:
    stand_in(monkeypatch, tmp_path, patch={"recheck-1-1": patch})
    _confirmed(tmp_path, PLANTED)
    now = _now(tmp_path, PLANTED)
    assert refused(confirm_module().recheck, now).reason == "trace answer"
    assert len(rows(now, "recheck-1-1")) == 30


# ---------------------------------------------------------------------------
# the numbers, the exit code, what was left out
# ---------------------------------------------------------------------------


def test_every_number_is_trace_s_and_the_adjustment_prove_s(tmp_path: Path, trace: Path) -> None:
    h = _confirmed(tmp_path, RECHECK)
    found = confirm_module().recheck(_now(tmp_path, RECHECK, weak=targets.MENDED))
    docs = [trace_document(h, f"reference-{r.finding}", f"recheck-1-{r.finding}") for r in found]
    for r, doc in zip(found, docs, strict=True):
        assert r.rate_before == doc["rows"]["old"]["failed"] / doc["rows"]["old"]["runs"]
        assert r.rate_now == doc["rows"]["new"]["failed"] / doc["rows"]["new"]["runs"]
        assert (r.difference, r.lo, r.hi, r.p) == (doc["difference"]["points"], doc["difference"]["lo"],
                                                   doc["difference"]["hi"], doc["test"]["p"])
        assert r.repeats_needed == (doc["guidance"] or {}).get("repeats")
        assert dict(r.left_out) == doc["inputs"]["left_out"]
    assert [r.adjusted_p for r in found] == adjusted([d["test"]["p"] for d in docs])


@pytest.mark.parametrize("code", [1, 4])
def test_recheck_reads_the_document_whatever_the_exit_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                           code: int) -> None:
    """BK7.15: "shown with a recorded document whose process exits non-zero"."""
    stand_in(monkeypatch, tmp_path, patch={"recheck-1-1": {"exit": code}, "recheck-1-2": {"exit": code}})
    _confirmed(tmp_path, RECHECK)
    found = confirm_module().recheck(_now(tmp_path, RECHECK, weak=targets.MENDED))
    assert [r.phrase for r in found] == ["fails less", "fails less"]


def test_what_trace_left_out_is_shown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    left = {"not re-run on the old version": 0, "not re-run on the new version": 0,
            "no outcome on the old version": 1, "no outcome on the new version": 2}
    stand_in(monkeypatch, tmp_path, patch={"recheck-1-1": {"set": {"inputs.left_out": left}}})
    _confirmed(tmp_path, PLANTED)
    (found,) = confirm_module().recheck(_now(tmp_path, PLANTED))
    assert dict(found.left_out) == left


# ---------------------------------------------------------------------------
# BK7.16: the gap, and side by side
# ---------------------------------------------------------------------------


def test_without_old_the_gap_is_trace_s_seconds_between_the_runs_in_days(tmp_path: Path,
                                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    stand_in(monkeypatch, tmp_path, patch={"recheck-1-1": {"set": {"gap_seconds": 3 * 86400 + 43200}}})
    _confirmed(tmp_path, PLANTED)
    (found,) = confirm_module().recheck(_now(tmp_path, PLANTED))
    assert found.gap_days == 3.5


def test_with_old_both_run_now_side_by_side_and_trace_compares_those_two(tmp_path: Path, trace: Path) -> None:
    h = _confirmed(tmp_path, PLANTED)
    now = _now(tmp_path, PLANTED, weak=targets.MENDED)
    old = targets.Coin()
    (found,) = confirm_module().recheck(now, old=old)
    assert (found.before, found.now) == ("planted-recheck-1-1-old", "planted-recheck-1-1")
    assert found.gap_days is None
    assert old.runs == now.target.runs == 30
    assert per_case(h, "recheck-1-1-old") == per_case(h, "recheck-1-1") == per_case(h, "reference-1")
    asked = [(c["argv"][1], c["argv"][2]) for c in fix_checks(trace) if "recheck" in c["argv"][2]]
    assert asked == [("planted-recheck-1-1-old", "planted-recheck-1-1")]
    doc = trace_document(h, "recheck-1-1-old", "recheck-1-1")
    assert found.p == doc["test"]["p"]
    assert found.phrase == "fails less"
    assert {record(x).stage for x in rows(h, "recheck-1-1-old")} == {"recheck"}


def test_without_old_trace_compares_the_reference_arm_and_the_new_one(tmp_path: Path, trace: Path) -> None:
    _confirmed(tmp_path, PLANTED)
    confirm_module().recheck(_now(tmp_path, PLANTED, weak=targets.MENDED))
    asked = [(c["argv"][1], c["argv"][2]) for c in fix_checks(trace) if "recheck" in c["argv"][2]]
    assert asked == [("planted-reference-1", "planted-recheck-1-1")]
