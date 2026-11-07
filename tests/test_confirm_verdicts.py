"""The confirm stage's verdicts, and every number in them Trace's or Prove's.

Plan BK7.5 (every number is Trace's or Prove's, compared with a direct call of each), BK7.6 (the three verdicts on
stored arms from a scripted agent), BK7.7 (the correction covers every candidate tested), BK7.9 (a candidate that fails
less is not confirmed, with a note), BK7.10 (a second confirm is read alone), BK7.17 (an arm with no outcome rows is
reported, and Trace's `inputs.left_out` shown), BK7.20 (the rows carry their stage); spec §5.5. Rulings 9 to 13 of
`evidence/bk7/open-points.md`. Candidates are never findings: a `Tested` is never a `Finding`, and only a confirmed
candidate has one.

"Trace's command, called directly" is the stand-in, which answers with what the pinned Trace printed for the same
counts; "Prove's adjustment, called directly" is `poisson_prove.diff.bh`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.confirm_support import (
    CORRECTION,
    DEAD,
    GAPS,
    LEFT_OUT,
    LESS,
    PLANTED,
    SMALL,
    STEADY,
    adjusted,
    confirm_module,
    fix_checks,
    hunt_module,
    name_of,
    on,
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

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def trace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return stand_in(monkeypatch, tmp_path)


def _confirmed(tmp_path: Path, scenario: Any) -> tuple[Any, Any]:
    h = ready(tmp_path / "hunts", scenario)
    return h, confirm_module().confirm(h)


def _flagged(doc: dict[str, Any]) -> tuple[str, ...]:
    return tuple(row["config"]["case"] for row in doc["changes"]["rows"] if row["flag"] is not None)


# ---------------------------------------------------------------------------
# BK7.5: every number Trace's or Prove's
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", [PLANTED, CORRECTION, LESS, GAPS], ids=lambda s: s.name)
def test_every_number_is_trace_s_for_those_two_runs_and_the_adjustment_prove_s(tmp_path: Path, trace: Path,
                                                                                scenario: Any) -> None:
    h, done = _confirmed(tmp_path, scenario)
    docs = [trace_document(h, "confirm-control", f"confirm-{t.number}") for t in done.tested]
    for t, doc in zip(done.tested, docs, strict=True):
        assert t.rate == doc["rows"]["new"]["failed"] / doc["rows"]["new"]["runs"]
        assert t.control_rate == doc["rows"]["old"]["failed"] / doc["rows"]["old"]["runs"]
        assert (t.difference, t.lo, t.hi) == (doc["difference"]["points"], doc["difference"]["lo"],
                                              doc["difference"]["hi"])
        assert t.p == doc["test"]["p"]
        guidance = doc["guidance"] or {}
        assert (t.repeats_needed, t.inputs_needed) == (guidance.get("repeats"), guidance.get("inputs"))
        assert dict(t.left_out) == doc["inputs"]["left_out"]
        assert tuple(t.flagged) == _flagged(doc)
    want = adjusted([d["test"]["p"] for d in docs], h.settings.confirm.q)
    assert [t.adjusted_p for t in done.tested] == want


def test_numbers_planted_in_trace_s_answer_are_the_numbers_handed_back(tmp_path: Path,
                                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    """Break computes none of these: numbers no test could give for these counts, planted in the answer for the
    second candidate, come back exactly, and the first and third are as Trace printed them. A rate is Trace's failed
    over Trace's runs, whatever its count of runs with no outcome."""
    planted = {"test.p": 0.012345678, "difference.points": 0.4321, "difference.lo": 0.1111, "difference.hi": 0.7777,
               "rows.new.failed": 7, "rows.new.runs": 29, "rows.old.failed": 2, "rows.old.runs": 31,
               "rows.new.no_outcome": 3, "rows.old.no_outcome": 1,
               "verdict": "too small to tell", "guidance": {"repeats": 17, "inputs": 23, "accepts_at": 0.5}}
    stand_in(monkeypatch, tmp_path, patch={"confirm-2": {"set": planted}})
    h, done = _confirmed(tmp_path, PLANTED)
    second = done.tested[1]
    assert (second.p, second.difference, second.lo, second.hi) == (0.012345678, 0.4321, 0.1111, 0.7777)
    assert (second.rate, second.control_rate) == (7 / 29, 2 / 31)
    assert (second.verdict, second.repeats_needed, second.inputs_needed) == ("too small to tell", 17, 23)
    first = trace_document(h, "confirm-control", "confirm-1")
    assert done.tested[0].p == first["test"]["p"]
    assert [t.adjusted_p for t in done.tested] == adjusted([t.p for t in done.tested], 0.05)


SENTINEL = r'''
import json, sys
import numpy as np
import poisson_prove.diff as diff

asked = []

def bh(p, q=0.05):
    asked.append({"p": [float(x) for x in np.asarray(p).reshape(-1)], "q": q})
    return np.asarray([0.0004 + 0.001 * i for i in range(np.asarray(p).size)], dtype=np.float64)

diff.bh = bh
from poisson_break import confirm, hunt
from tests import confirm_support as cs, confirm_targets as ct
h = hunt.open_hunt(cs.PLANTED.settings(sys.argv[1]), target=ct.Coin(), cases=cs.PLANTED.cases, name="planted",
                   existing=True)
done = confirm.confirm(h)
print(json.dumps({"asked": asked, "adjusted": [t.adjusted_p for t in done.tested], "p": [t.p for t in done.tested]}))
'''


def test_the_adjustment_is_prove_s_own_function_called_on_trace_s_p_values(tmp_path: Path, trace: Path) -> None:
    """Prove's `bh` swapped for one that answers what no adjustment could: what `confirm` hands back is what it
    answered, and it was handed Trace's p-values, in the candidates' order, at the settings' `q`."""
    h, done = _confirmed(tmp_path, PLANTED)
    child = subprocess.run([sys.executable, "-c", SENTINEL, str(tmp_path / "hunts")], capture_output=True, text=True,
                           cwd=REPO, timeout=300)
    assert child.returncode == 0, child.stderr[-2000:]
    held = json.loads(child.stdout.strip().splitlines()[-1])
    assert held["adjusted"] == [0.0004 + 0.001 * i for i in range(3)]
    assert held["asked"] == [{"p": [t.p for t in done.tested], "q": 0.05}]


# ---------------------------------------------------------------------------
# BK7.6: the three verdicts
# ---------------------------------------------------------------------------


def test_a_planted_weakness_is_confirmed(tmp_path: Path, trace: Path) -> None:
    h, done = _confirmed(tmp_path, PLANTED)
    doc = trace_document(h, "confirm-control", "confirm-1")
    assert (doc["verdict"], doc["direction"]) == ("different", "failed more in new")
    first = done.tested[0]
    assert (name_of(first.condition), first.verdict, first.note) == (on("error"), "confirmed", None)
    assert first.adjusted_p <= 0.05
    assert [name_of(f.condition) for f in done.findings] == [on("error")]


def test_no_effect_in_a_design_that_could_have_seen_one_is_not_confirmed(tmp_path: Path, trace: Path) -> None:
    h, done = _confirmed(tmp_path, STEADY)
    doc = trace_document(h, "confirm-control", "confirm-1")
    assert doc["verdict"] == "no significant difference"
    assert (done.tested[0].verdict, done.tested[0].repeats_needed) == ("not confirmed", None)
    assert done.findings == ()


def test_no_effect_in_a_design_that_could_not_have_seen_one_is_too_small_with_trace_s_repeats(tmp_path: Path,
                                                                                                trace: Path) -> None:
    h, done = _confirmed(tmp_path, SMALL)
    doc = trace_document(h, "confirm-control", "confirm-1")
    assert doc["verdict"] == "too small to tell"
    only = done.tested[0]
    assert only.verdict == "too small to tell"
    assert only.repeats_needed == doc["guidance"]["repeats"] and only.repeats_needed is not None
    assert done.findings == ()


@pytest.mark.parametrize("verdict, direction, p, want", [
    ("different", "failed more in new", 0.001, ("confirmed", None)),
    ("different", "failed less in new", 0.001, ("not confirmed", "failed less")),
    ("no significant difference", "failed more in new", 0.4, ("not confirmed", None)),
    ("no significant difference", "no direction", 1.0, ("not confirmed", None)),
    ("too small to tell", "failed more in new", 0.2, ("too small to tell", None)),
])
def test_the_verdict_is_read_from_trace_s_words(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verdict: str,
                                                direction: str, p: float, want: tuple[str, str | None]) -> None:
    """Spec §5.5's three verdicts from Trace's `verdict` and `direction`, the one candidate's p adjusted alone, on
    the small scenario's runs."""
    stand_in(monkeypatch, tmp_path, patch={"confirm-1": {"set": {"verdict": verdict, "direction": direction,
                                                                  "test.p": p}}})
    h = ready(tmp_path / "hunts", SMALL)
    t = confirm_module().confirm(h).tested[0]
    assert (t.verdict, t.note) == want


# ---------------------------------------------------------------------------
# BK7.7: the correction covers every candidate tested; ruling 12
# ---------------------------------------------------------------------------


def test_different_by_trace_alone_and_not_after_the_correction_across_all_eight(tmp_path: Path, trace: Path) -> None:
    h, done = _confirmed(tmp_path, CORRECTION)
    error = done.tested[1]
    doc = trace_document(h, "confirm-control", "confirm-2")
    assert (doc["verdict"], doc["direction"]) == ("different", "failed more in new")
    assert doc["test"]["p"] < 0.05
    assert (name_of(error.condition), error.verdict, error.note) == (on("error"), "not confirmed",
                                                                      "not after the correction")
    assert error.adjusted_p > 0.05
    assert len(done.tested) == 8
    assert done.findings == ()


# ---------------------------------------------------------------------------
# BK7.9: fails less
# ---------------------------------------------------------------------------


def test_a_candidate_that_fails_less_than_the_control_is_not_confirmed_with_a_note(tmp_path: Path,
                                                                                   trace: Path) -> None:
    h, done = _confirmed(tmp_path, LESS)
    doc = trace_document(h, "confirm-control", "confirm-1")
    assert (doc["verdict"], doc["direction"]) == ("different", "failed less in new")
    t = done.tested[0]
    assert (t.verdict, t.note) == ("not confirmed", "failed less")
    assert t.difference < 0
    assert done.findings == ()


# ---------------------------------------------------------------------------
# ruling 9: what confirm hands back
# ---------------------------------------------------------------------------


def test_confirmation_holds_every_candidate_tested_and_only_confirmed_ones_as_findings(tmp_path: Path,
                                                                                       trace: Path) -> None:
    h, done = _confirmed(tmp_path, PLANTED)
    module = confirm_module()
    assert done.stage == 1
    assert [t.number for t in done.tested] == [1, 2, 3]
    assert [name_of(t.condition) for t in done.tested] == list(PLANTED.candidates)
    assert [t.arm for t in done.tested] == [f"{h.name}-confirm-{n}" for n in (1, 2, 3)]
    assert all(isinstance(t, module.Tested) and not isinstance(t, module.Finding) for t in done.tested)
    assert all(isinstance(f, module.Finding) for f in done.findings)
    assert {name_of(f.condition) for f in done.findings} == {
        name_of(t.condition) for t in done.tested if t.verdict == "confirmed"}
    with pytest.raises(AttributeError):
        done.tested[0].verdict = "confirmed"
    with pytest.raises(AttributeError):
        done.findings = ()


def test_only_a_confirmed_candidate_gets_a_finding_file(tmp_path: Path, trace: Path) -> None:
    h, done = _confirmed(tmp_path, PLANTED)
    files = sorted(p.name for p in (Path(h.folder) / "findings").glob("*.toml"))
    assert files == [f"{f.number}.toml" for f in done.findings] == ["1.toml"]


def test_a_finished_stage_asked_again_runs_nothing_and_says_the_same(tmp_path: Path, trace: Path) -> None:
    h, done = _confirmed(tmp_path, PLANTED)
    runs = h.target.runs
    again = confirm_module().confirm(h)
    assert h.target.runs == runs
    assert again.tested == done.tested
    assert again.findings == done.findings


def test_on_progress_counts_the_stage_s_runs(tmp_path: Path, trace: Path) -> None:
    h = ready(tmp_path / "hunts", SMALL)
    seen: list[tuple[int, int]] = []
    confirm_module().confirm(h, on_progress=lambda done, total: seen.append((done, total)))
    assert seen and seen[-1][0] == seen[-1][1]
    assert all(b >= a for (a, _), (b, _) in zip(seen, seen[1:], strict=False))


# ---------------------------------------------------------------------------
# BK7.10, ruling 13: asking again
# ---------------------------------------------------------------------------


def test_a_second_confirm_is_a_new_stage_on_new_seeds_read_alone(tmp_path: Path, trace: Path) -> None:
    h, first = _confirmed(tmp_path, SMALL)
    assert first.tested[0].verdict == "too small to tell"
    second = confirm_module().confirm(h, repeats=6)
    assert second.stage == 2
    assert per_case(h, "confirm-2-control") == per_case(h, "confirm-2-1") == {"k1": 6, "k2": 6}
    assert not (seeds(h, "confirm-2-control") | seeds(h, "confirm-2-1")) & (
        seeds(h, "confirm-control") | seeds(h, "confirm-1") | seeds(h, "control"))
    doc = trace_document(h, "confirm-2-control", "confirm-2-1")
    t = second.tested[0]
    assert t.arm == f"{h.name}-confirm-2-1"
    assert (t.p, t.difference) == (doc["test"]["p"], doc["difference"]["points"])
    assert t.rate == doc["rows"]["new"]["failed"] / doc["rows"]["new"]["runs"]
    assert doc["rows"]["new"]["runs"] == 12


def test_asking_again_tests_only_what_the_latest_stage_called_too_small(tmp_path: Path,
                                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """Planted: Trace says *too small to tell* of the second and third candidates; the third's answer made *no
    significant difference*, only the second is asked about again. (The second stage's answer is the first stage's
    document for it, since nothing was recorded for six repeats of the planted desk.)"""
    nsd = {"confirm-3": {"set": {"verdict": "no significant difference"}}}
    stand_in(monkeypatch, tmp_path, patch=nsd)
    h, first = _confirmed(tmp_path, PLANTED)
    assert [t.verdict for t in first.tested] == ["confirmed", "too small to tell", "not confirmed"]
    again = json.dumps(trace_document(h, "confirm-control", "confirm-2"))
    stand_in(monkeypatch, tmp_path, patch={**nsd, "confirm-2-2": {"stdout": again, "exit": 0}})
    second = confirm_module().confirm(h, repeats=6)
    assert [name_of(t.condition) for t in second.tested] == [on("timeout")]
    assert sorted(a for a in _arm_words(h) if a.startswith("confirm-2-")) == ["confirm-2-2", "confirm-2-control"]


def _arm_words(h: Any) -> list[str]:
    from poisson_prove.store import Store

    return [a[len(h.name) + 1:] for a in Store(h.store).runs()]


def test_nothing_too_small_is_nothing_to_ask_again(tmp_path: Path, trace: Path) -> None:
    h, done = _confirmed(tmp_path, STEADY)
    runs = h.target.runs
    assert refused(confirm_module().confirm, h, repeats=6).reason == "nothing to ask again"
    assert h.target.runs == runs


def test_asking_again_while_the_latest_stage_is_unfinished_is_refused(tmp_path: Path, trace: Path) -> None:
    """The planted stage stopped by the dollar cap after one run, its design on disk: asked again, refused, and
    nothing run."""
    priced = _priced()
    h = ready(tmp_path / "hunts", priced)
    with pytest.raises(hunt_module().HuntStopped):
        confirm_module().confirm(h)
    assert (Path(h.folder) / "confirm.json").exists() and len(rows(h, "confirm-control")) == 1
    runs = h.target.runs
    again = open_scenario(tmp_path / "hunts", priced, existing=True, limits={"dollars": 100.0})
    assert refused(confirm_module().confirm, again, repeats=6).reason == "unfinished"
    assert again.target.runs == 0 and h.target.runs == runs
    assert len(rows(h, "confirm-control")) == 1


def _priced() -> Any:
    """The planted scenario with every run costing $0.001: the control's fourteen runs spend $0.014, and a cap of
    $0.0155 stops the confirm stage after its first run."""
    import dataclasses

    return dataclasses.replace(PLANTED, name="priced", cases=tuple({**c, "tokens": [1000, 0]} for c in PLANTED.cases),
                               limits={"dollars": 0.0155, "input_per_million": 1.0, "output_per_million": 1.0})


def test_a_stopped_stage_resumed_asks_trace_before_its_next_run(tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """BK7.19 holds for a stage taken up again: with no Trace, nothing more is run."""
    stand_in(monkeypatch, tmp_path)
    priced = _priced()
    h = ready(tmp_path / "hunts", priced)
    with pytest.raises(hunt_module().HuntStopped):
        confirm_module().confirm(h)
    stand_in(monkeypatch, tmp_path, missing=True)
    again = open_scenario(tmp_path / "hunts", priced, existing=True, limits={"dollars": 100.0})
    assert refused(confirm_module().confirm, again).reason == "trace missing"
    assert again.target.runs == 0
    assert len(rows(h, "confirm-control")) == 1


def test_a_finding_is_numbered_in_the_order_confirmed_not_by_its_candidate(tmp_path: Path,
                                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    """Planted, with the first candidate's answer made *too small to tell* and the second's *different, failed more*
    at a p that holds: the one finding is finding 1, from candidate 2's arm, with reference arm 1."""
    stand_in(monkeypatch, tmp_path, patch={
        "confirm-1": {"set": {"verdict": "too small to tell"}},
        "confirm-2": {"set": {"verdict": "different", "direction": "failed more in new", "test.p": 0.001}}})
    h, done = _confirmed(tmp_path, PLANTED)
    assert [(f.number, f.arm) for f in done.findings] == [(1, "planted-confirm-2")]
    assert (Path(h.folder) / "findings" / "1.toml").exists()
    assert not (Path(h.folder) / "findings" / "2.toml").exists()
    assert {record(r).condition.name for r in rows(h, "reference-1")} == {on("timeout")}


def test_a_finding_of_a_second_stage_is_numbered_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Small, its first answer made *too small to tell* and its second *different, failed more* at a p that holds:
    the finding of stage 2 is finding 1, the first; with one already, it would be 2."""
    stand_in(monkeypatch, tmp_path, patch={"confirm-2-1": {"set": {"verdict": "different",
                                                                    "direction": "failed more in new",
                                                                    "test.p": 0.001}}})
    h, first = _confirmed(tmp_path, SMALL)
    second = confirm_module().confirm(h, repeats=6)
    assert [f.number for f in second.findings] == [1]
    assert second.findings[0].arm == f"{h.name}-confirm-2-1"
    assert second.findings[0].stage == 2


# ---------------------------------------------------------------------------
# BK7.17, rulings 10 and 11: no outcome
# ---------------------------------------------------------------------------


def test_a_case_with_no_outcome_in_an_arm_is_reported_beside_trace_s_left_out(tmp_path: Path, trace: Path) -> None:
    h, done = _confirmed(tmp_path, GAPS)
    doc = trace_document(h, "confirm-control", "confirm-1")
    assert doc["inputs"]["left_out"]["no outcome on the new version"] == 1
    t = done.tested[0]
    assert dict(t.left_out) == doc["inputs"]["left_out"]
    assert set(t.left_out) == set(LEFT_OUT)
    assert tuple(t.no_outcome) == ("k12",)
    assert all(r["outcome"] is None for r in rows(h, "confirm-1") if record(r).case == "k12")


def test_a_candidate_trace_cannot_compare_is_not_confirmed_and_left_out_of_the_adjustment(tmp_path: Path,
                                                                                         trace: Path) -> None:
    h, done = _confirmed(tmp_path, DEAD)
    gone, other = done.tested
    assert (gone.verdict, gone.note) == ("not confirmed", "nothing to compare")
    assert (gone.p, gone.adjusted_p, gone.difference, gone.rate) == (None, None, None, None)
    assert tuple(gone.no_outcome) == tuple(done.design.cases) and gone.no_outcome
    doc = trace_document(h, "confirm-control", "confirm-2")
    assert other.p == doc["test"]["p"]
    assert other.adjusted_p == adjusted([doc["test"]["p"]])[0]


def test_every_case_with_an_outcome_is_not_reported_as_without_one(tmp_path: Path, trace: Path) -> None:
    """The accepted control of the two above."""
    _, done = _confirmed(tmp_path, PLANTED)
    assert all(tuple(t.no_outcome) == () for t in done.tested)


# ---------------------------------------------------------------------------
# BK7.20: the stage in every row
# ---------------------------------------------------------------------------


def test_confirm_and_reference_rows_carry_their_stage_and_arm(tmp_path: Path, trace: Path) -> None:
    h, done = _confirmed(tmp_path, PLANTED)
    for arm in ("confirm-control", "confirm-1", "confirm-2", "confirm-3"):
        assert {(record(r).stage, record(r).arm) for r in rows(h, arm)} == {("confirm", f"{h.name}-{arm}")}
    for f in done.findings:
        arm = f"reference-{f.number}"
        assert {(record(r).stage, record(r).arm) for r in rows(h, arm)} == {("reference", f"{h.name}-{arm}")}
        assert {record(r).condition.name for r in rows(h, arm)} == {name_of(f.condition)}


def test_nothing_is_asked_of_trace_for_an_arm_that_is_not_a_candidate_s(tmp_path: Path, trace: Path) -> None:
    """Each candidate once, against the shared control: three questions for three candidates, and none of the
    control against itself or of one candidate against another."""
    h, _ = _confirmed(tmp_path, PLANTED)
    asked = [(c["argv"][1], c["argv"][2]) for c in fix_checks(trace)]
    assert asked == [(f"{h.name}-confirm-control", f"{h.name}-confirm-{n}") for n in (1, 2, 3)]
