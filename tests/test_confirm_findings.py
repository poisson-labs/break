"""Findings: what one carries, its file, its reference run, and replaying it.

Plan BK7.11 (a finding file round-trips, and holds everything `replay` and `recheck` need), BK7.12 (the reference stage
runs exactly the confirmed findings, each its own arm, over every case, on fresh seeds), BK7.13 (`replay` runs one
finding on one case once and returns the calls in order with what was applied to each); spec §5.5, "What a finding
carries", §6.1 and §6.2. Rulings 14 (`Finding` and its file), 15 (the reference stage) and 16 (`replay`) of
`evidence/bk7/open-points.md`.
"""

from __future__ import annotations

import dataclasses
import shlex
import tomllib
from pathlib import Path
from typing import Any

import pytest

from tests.confirm_support import (
    GAPS,
    PLANTED,
    RECHECK,
    confirm_module,
    hunt_module,
    name_of,
    on,
    open_scenario,
    ready,
    record,
    refused,
    rows,
    stand_in,
)

NOT_SET_ASIDE = tuple(f"k{i}" for i in range(1, 7))


@pytest.fixture
def trace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return stand_in(monkeypatch, tmp_path)


def _confirmed(tmp_path: Path, scenario: Any, **over: Any) -> tuple[Any, Any]:
    h = ready(tmp_path / "hunts", scenario, **over)
    return h, confirm_module().confirm(h)


def _arm_names(h: Any) -> list[str]:
    from poisson_prove.store import Store

    return sorted(Store(h.store).runs())


# ---------------------------------------------------------------------------
# ruling 14: what a finding carries
# ---------------------------------------------------------------------------


def test_a_finding_carries_what_the_spec_says_from_its_tested_candidate_and_its_arm(tmp_path: Path,
                                                                                    trace: Path) -> None:
    h, done = _confirmed(tmp_path, PLANTED)
    (f,) = done.findings
    t = done.tested[0]
    assert (f.number, f.hunt, name_of(f.condition), tuple(f.cases), f.repeats, f.stage) == (
        1, "planted", on("error"), NOT_SET_ASIDE, 5, 1)
    assert (f.arm, f.control_arm) == ("planted-confirm-1", "planted-confirm-control")
    for field in ("rate", "control_rate", "difference", "lo", "hi", "p", "adjusted_p"):
        assert getattr(f, field) == getattr(t, field), field
    assert tuple(f.flagged) == tuple(t.flagged)
    assert dict(f.left_out) == dict(t.left_out)
    assert f.q == 0.05
    assert f.reference == "planted-reference-1"
    assert f.judged_by == "break"


def test_a_finding_s_kinds_and_signals_are_counted_over_its_arm(tmp_path: Path, trace: Path) -> None:
    """"The failure kinds seen; the signals": each kind with how many of the arm's runs failed with it, and each of
    the three signals with its count over the arm, read here from the stored records."""
    h, done = _confirmed(tmp_path, PLANTED)
    (f,) = done.findings
    kinds: dict[str, int] = {}
    signals = {"gave_up": 0, "retry_storm": 0, "over_budget": 0}
    for row in rows(h, "confirm-1"):
        failure = record(row).failure
        if failure.kind is not None:
            kinds[failure.kind] = kinds.get(failure.kind, 0) + 1
        for name in signals:
            signals[name] += getattr(failure.signals, name)
    assert dict(f.kinds) == kinds and kinds["failed"] > 0
    assert dict(f.signals) == signals and signals["gave_up"] > 0


def test_a_finding_judged_by_the_user_s_check_says_so(tmp_path: Path, trace: Path) -> None:
    """Spec §4: findings that rest on the user's own check are marked "judged by your check". The planted desk judged
    by a check that fails the runs it reports `unresolved` fails the same runs, so Trace's answers are the same, and
    its finding says `your check`, with the check's kind."""
    h, done = _confirmed(tmp_path, PLANTED, fails={"outcomes": [], "own": "tests.confirm_targets:unresolved"})
    (f,) = done.findings
    assert f.judged_by == "your check"
    assert set(f.kinds) == {"own:unresolved"}
    assert confirm_module().read_finding(h, 1) == f


def test_a_finding_says_how_to_replay_it_and_where_trace_s_full_report_is(tmp_path: Path, trace: Path) -> None:
    h, done = _confirmed(tmp_path, PLANTED)
    (f,) = done.findings
    assert shlex.split(f.replay) == ["poisson-break", "replay", "1", "--hunt", "planted"]
    words = shlex.split(f.trace)
    assert words[:4] == ["poisson-trace", "fix-check", "planted-confirm-control", "planted-confirm-1"]
    flags = dict(zip(words[4::2], words[5::2], strict=False))
    assert set(flags) == {"--inputs", "--event", "--max-mde", "--store"}
    assert (flags["--inputs"], flags["--event"], float(flags["--max-mde"])) == ("all", "failed", 0.2)
    assert Path(flags["--store"]).resolve() == Path(h.store).resolve()


# ---------------------------------------------------------------------------
# BK7.11: the file round-trips
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", [PLANTED, GAPS, RECHECK], ids=lambda s: s.name)
def test_every_finding_file_reads_back_equal(tmp_path: Path, trace: Path, scenario: Any) -> None:
    h, done = _confirmed(tmp_path, scenario)
    assert done.findings
    for f in done.findings:
        assert confirm_module().read_finding(h, f.number) == f


def test_the_file_is_toml_with_its_schema_first(tmp_path: Path, trace: Path) -> None:
    h, done = _confirmed(tmp_path, PLANTED)
    path = Path(h.folder) / "findings" / "1.toml"
    held = tomllib.loads(path.read_text(encoding="utf-8"))
    assert next(iter(held)) == "schema"
    assert held["schema"] == "poisson_break.finding/1"
    assert held["condition"] == on("error") and held["number"] == 1


def test_a_value_that_is_none_is_left_out_and_read_back_as_none(tmp_path: Path, trace: Path) -> None:
    """TOML has no null (ruling 14). A finding with no interval is written without `lo` and `hi`."""
    h, done = _confirmed(tmp_path, PLANTED)
    bare = dataclasses.replace(done.findings[0], lo=None, hi=None)
    path = confirm_module().write_finding(h, bare)
    held = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    assert "lo" not in held and "hi" not in held
    assert confirm_module().read_finding(h, 1) == bare


def test_a_finding_that_is_not_there_is_refused(tmp_path: Path, trace: Path) -> None:
    h, _ = _confirmed(tmp_path, PLANTED)
    assert refused(confirm_module().read_finding, h, 2).reason == "unknown finding"
    assert refused(confirm_module().replay, h, 2).reason == "unknown finding"


def test_the_file_is_what_replay_runs(tmp_path: Path, trace: Path) -> None:
    """The file is the unit of hand-off (spec §6.1): the condition written in it is what is run, not one remembered."""
    h, done = _confirmed(tmp_path, PLANTED)
    path = Path(h.folder) / "findings" / "1.toml"
    path.write_text(path.read_text(encoding="utf-8").replace(on("error"), on("timeout")), encoding="utf-8")
    replayed = confirm_module().replay(h, 1)
    assert [c.change for c in replayed.calls] == [on("timeout")]


# ---------------------------------------------------------------------------
# BK7.12, ruling 15: the reference stage
# ---------------------------------------------------------------------------


def test_the_reference_stage_runs_exactly_the_confirmed_findings_each_its_own_arm_over_every_case(
        tmp_path: Path, trace: Path) -> None:
    h, done = _confirmed(tmp_path, PLANTED)
    assert [n for n in _arm_names(h) if "-reference-" in n] == ["planted-reference-1"]
    cases: dict[str, int] = {}
    for row in rows(h, "reference-1"):
        cases[record(row).case] = cases.get(record(row).case, 0) + 1
        assert record(row).condition.name == on("error")
    assert cases == dict.fromkeys(NOT_SET_ASIDE, 5)


def test_two_findings_have_two_reference_arms(tmp_path: Path, trace: Path) -> None:
    h, done = _confirmed(tmp_path, RECHECK)
    assert [f.number for f in done.findings] == [1, 2]
    assert [n for n in _arm_names(h) if "-reference-" in n] == ["recheck-reference-1", "recheck-reference-2"]
    for f in done.findings:
        assert {record(r).condition.name for r in rows(h, f"reference-{f.number}")} == {name_of(f.condition)}


def test_a_hunt_with_no_finding_has_no_reference_arm(tmp_path: Path, trace: Path) -> None:
    from tests.confirm_support import LESS

    h, done = _confirmed(tmp_path, LESS)
    assert done.findings == ()
    assert [n for n in _arm_names(h) if "-reference-" in n] == []
    assert confirm_module().reference(h) == ()


def test_a_reference_stage_stopped_short_is_finished_by_reference(tmp_path: Path, trace: Path) -> None:
    """Every run costs $0.001; the control and the confirm stage spend $0.134, and a cap of $0.1445 stops the
    reference arm after ten runs, the finding's file already written. Opened again with the cap lifted, `reference`
    runs the other twenty and hands back the arm's name."""
    priced = dataclasses.replace(PLANTED, name="priced", cases=tuple({**c, "tokens": [1000, 0]} for c in PLANTED.cases),
                                 limits={"dollars": 0.1445, "input_per_million": 1.0, "output_per_million": 1.0})
    h = ready(tmp_path / "hunts", priced)
    with pytest.raises(hunt_module().HuntStopped):
        confirm_module().confirm(h)
    assert len(rows(h, "reference-1")) == 10
    assert (Path(h.folder) / "findings" / "1.toml").exists()
    again = open_scenario(tmp_path / "hunts", priced, existing=True, limits={"dollars": 100.0})
    assert confirm_module().reference(again) == ("priced-reference-1",)
    assert len(rows(h, "reference-1")) == 30
    assert confirm_module().reference(again) == ("priced-reference-1",)
    assert len(rows(h, "reference-1")) == 30


# ---------------------------------------------------------------------------
# BK7.13, ruling 16: replay
# ---------------------------------------------------------------------------


def _most_failed_case(h: Any, finding: Any) -> tuple[str, int]:
    """The first of the finding's cases with the most failed rows in its confirm arm, and the seed of its first
    failed row there."""
    arm = finding.arm[len(h.name) + 1:]
    failed: dict[str, list[int]] = {c: [] for c in finding.cases}
    for row in rows(h, arm):
        if row["outcome"] == "failed":
            failed[record(row).case].append(int(row["seed"]))
    most = max(len(v) for v in failed.values())
    case = next(c for c in finding.cases if len(failed[c]) == most)
    return case, failed[case][0]


def test_replay_runs_the_finding_once_where_it_failed_most_on_a_seed_it_failed_on(tmp_path: Path,
                                                                                  trace: Path) -> None:
    """On the recheck hunt's first finding, whose case that failed most is not its first case."""
    h, done = _confirmed(tmp_path, RECHECK)
    f = done.findings[0]
    case, seed = _most_failed_case(h, f)
    assert case != f.cases[0]
    runs = h.target.runs
    stored = {arm: len(rows(h, arm[len(h.name) + 1:])) for arm in _arm_names(h)}
    replayed = confirm_module().replay(h, 1)
    assert h.target.runs == runs + 1
    assert (replayed.finding, replayed.case, replayed.seed) == (1, case, seed)
    assert (replayed.outcome, replayed.kind) == ("failed", "failed")
    assert {arm: len(rows(h, arm[len(h.name) + 1:])) for arm in _arm_names(h)} == stored


def test_replay_returns_the_calls_in_order_with_what_was_applied_to_each(tmp_path: Path, trace: Path) -> None:
    h, done = _confirmed(tmp_path, PLANTED)
    replayed = confirm_module().replay(h, 1)
    call_type = __import__("poisson_break.records", fromlist=["Call"]).Call
    assert all(isinstance(c, call_type) for c in replayed.calls)
    assert [(c.tool, c.call, c.change, c.real_ran) for c in replayed.calls] == [
        ("lookup_order", 1, on("error"), False)]
    failed_row = next(r for r in rows(h, "confirm-1") if int(r["seed"]) == replayed.seed)
    assert tuple(replayed.calls) == tuple(record(failed_row).calls)


def test_replay_takes_a_finding_as_well_as_its_number(tmp_path: Path, trace: Path) -> None:
    h, done = _confirmed(tmp_path, PLANTED)
    assert confirm_module().replay(h, done.findings[0]) == confirm_module().replay(h, 1)


def test_replay_on_a_case_given_uses_that_case_s_first_row_s_seed(tmp_path: Path, trace: Path) -> None:
    """On a case whose first row in the confirm arm did not fail and a later one did: the first row's seed."""
    h, done = _confirmed(tmp_path, RECHECK)
    by_case: dict[str, list[dict[str, Any]]] = {}
    for row in rows(h, "confirm-1"):
        by_case.setdefault(record(row).case, []).append(row)
    case = next(c for c, held in by_case.items()
                if held[0]["outcome"] == "ok" and any(r["outcome"] == "failed" for r in held))
    replayed = confirm_module().replay(h, 1, case=case)
    assert (replayed.case, replayed.seed) == (case, int(by_case[case][0]["seed"]))
    assert replayed.outcome == "ok"
