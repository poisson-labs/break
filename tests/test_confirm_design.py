"""The candidates handed to confirm, and the design: fixed before the first run, every case, the cost as planned.

Plan BK7.1 (fresh seeds), BK7.2 (the design is fixed before the first run and written to the hunt), BK7.3 (cases are not
chosen by outcome), BK7.4 (the cost in the plan is the cost); spec §5.5, "Who is tested", "The design" and "The cost".
Ruling 7 of `evidence/bk7/open-points.md` (`write_candidates`, `read_candidates`, `candidates.json`) and ruling 8
(`design`, `Design`, `confirm.json`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests import confirm_targets as targets
from tests.confirm_support import (
    PLANTED,
    Scenario,
    condition,
    confirm_module,
    hunt_module,
    name_of,
    names,
    on,
    open_scenario,
    per_case,
    read_json,
    ready,
    records,
    refused,
    rows,
    seeds,
    settings_module,
    stand_in,
)

NOT_SET_ASIDE = [f"k{i}" for i in range(1, 7)]


@pytest.fixture
def trace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return stand_in(monkeypatch, tmp_path)


def _summary(**over: Any) -> Any:
    """A control's summary, made by hand: `design` is pure and takes one."""
    held: dict[str, Any] = {"runs": 14, "failed": 3, "not_counted": 0, "rate": 3 / 14,
                            "per_case": {"a": 0.0, "b": 1.0, "c": 0.5}, "calls": {"a": {}, "b": {}, "c": {}},
                            "set_aside": ("b",), "high_base_rate": False, "dollars_per_run": None,
                            "seconds_per_run": 0.01, "rows": ()}
    held.update(over)
    return hunt_module().ControlSummary(**held)


def _settings(tmp_path: Path, **confirm: Any) -> Any:
    return PLANTED.settings(tmp_path, confirm=confirm)


# ---------------------------------------------------------------------------
# ruling 7: the candidates, on disk
# ---------------------------------------------------------------------------


def test_the_candidates_written_read_back_in_their_order(tmp_path: Path) -> None:
    h = open_scenario(tmp_path, PLANTED)
    given = [condition(on("timeout")), condition(on("error")), condition(on("empty"))]
    confirm_module().write_candidates(h, given)
    assert names(confirm_module().read_candidates(h)) == names(given)


def test_the_candidates_file_is_numbered_from_one_best_first_by_name(tmp_path: Path) -> None:
    h = open_scenario(tmp_path, PLANTED)
    confirm_module().write_candidates(h, [condition(on("timeout")), condition(on("error"))])
    held = read_json(h.folder / "candidates.json")
    assert held["schema"] == "poisson_break.candidates/1"
    assert held["candidates"] == [{"number": 1, "condition": on("timeout")}, {"number": 2, "condition": on("error")}]


@pytest.mark.parametrize("given", [
    pytest.param([], id="none"),
    pytest.param([on("error"), on("error")], id="one twice"),
    pytest.param([""], id="the empty condition"),
    pytest.param([on("error"), on("timeout"), on("empty"), on("stale")], id="more than the settings' candidates"),
])
def test_candidates_that_cannot_be_confirmed_are_refused(tmp_path: Path, given: list[str]) -> None:
    h = open_scenario(tmp_path, PLANTED, confirm={"candidates": 3})
    refused(confirm_module().write_candidates, h, [condition(c) for c in given])
    assert not (h.folder / "candidates.json").exists()


def test_as_many_candidates_as_the_settings_allow_are_taken(tmp_path: Path) -> None:
    """The accepted control of the refusal above: three of three."""
    h = open_scenario(tmp_path, PLANTED, confirm={"candidates": 3})
    confirm_module().write_candidates(h, [condition(c) for c in (on("error"), on("timeout"), on("empty"))])
    assert len(confirm_module().read_candidates(h)) == 3


def test_a_condition_given_twice_under_two_spellings_is_one_condition_twice(tmp_path: Path) -> None:
    """"A condition twice (by its name)": the canonical name, so a pair written in either order is one."""
    h = open_scenario(tmp_path, PLANTED)
    pair = "tool:lookup_order#1=error + tool:lookup_order#2=timeout"
    other = "tool:lookup_order#2=timeout + tool:lookup_order#1=error"
    refused(confirm_module().write_candidates, h, [condition(pair), condition(other)])


def test_confirm_with_no_candidates_written_refuses_and_runs_nothing(tmp_path: Path, trace: Path) -> None:
    h = open_scenario(tmp_path, PLANTED)
    hunt_module().control(h)
    error = refused(confirm_module().confirm, h)
    assert error.reason == "no candidates"
    assert [a for a in _arms(h) if "confirm" in a] == []


def test_confirm_with_no_control_refuses_and_runs_nothing(tmp_path: Path, trace: Path) -> None:
    h = open_scenario(tmp_path, PLANTED)
    confirm_module().write_candidates(h, [condition(on("error"))])
    error = refused(confirm_module().confirm, h)
    assert error.reason == "no control"
    assert _arms(h) == []


def test_candidates_cannot_be_written_again_once_a_confirm_stage_is_on_disk(tmp_path: Path, trace: Path) -> None:
    h = ready(tmp_path, PLANTED)
    confirm_module().confirm(h)
    refused(confirm_module().write_candidates, h, [condition(on("stale"))])
    assert names(confirm_module().read_candidates(h)) == list(PLANTED.candidates)


def _arms(h: Any) -> list[str]:
    from poisson_prove.store import Store

    return sorted(Store(h.store).runs()) if Path(h.store).exists() else []


# ---------------------------------------------------------------------------
# ruling 8: `design`, pure
# ---------------------------------------------------------------------------


def test_design_is_one_control_arm_and_one_arm_per_candidate_on_the_cases_not_set_aside(tmp_path: Path) -> None:
    made = confirm_module().design([condition(on("error")), condition(on("timeout"))], _settings(tmp_path),
                                   _summary())
    assert made.cases == ("a", "c")
    assert made.repeats == 5
    assert [(word, name_of(c)) for word, c in made.arms] == [
        ("confirm-control", ""), ("confirm-1", on("error")), ("confirm-2", on("timeout"))]


@pytest.mark.parametrize("candidates, n_cases, repeats", [(1, 1, 1), (3, 2, 5), (8, 12, 5), (2, 11, 7)])
def test_design_counts_are_the_plan_s(tmp_path: Path, candidates: int, n_cases: int, repeats: int) -> None:
    """BK7.4: "(1 + candidates) × cases × repeats for the confirm stage, and cases × repeats per finding for the
    reference stage, as `plan_confirm` works them out"."""
    ids = [f"c{i}" for i in range(n_cases)]
    control = _summary(per_case=dict.fromkeys(ids, 0.0), calls={i: {} for i in ids}, set_aside=())
    settings = _settings(tmp_path, repeats=repeats)
    made = confirm_module().design([condition(on(f)) for f in ("error", "timeout", "empty", "stale", "cut_off",
                                                               "malformed", "rate_limited",
                                                               "planted_instruction")[:candidates]],
                                   settings, control)
    plan = settings_module().plan_confirm(settings, cases=n_cases, candidates=candidates)
    assert (made.confirm_runs, made.reference_per_finding, made.reference_runs, made.runs) == (
        plan.confirm_runs, plan.reference_per_finding, plan.reference_runs, plan.runs)
    assert made.confirm_runs == (1 + candidates) * n_cases * repeats


def test_design_prices_each_run_at_the_control_s_cost(tmp_path: Path) -> None:
    made = confirm_module().design([condition(on("error"))], _settings(tmp_path), _summary(dollars_per_run=0.004))
    assert made.dollars == pytest.approx(2 * 2 * 5 * 0.004, rel=1e-12)
    assert made.reference_dollars == pytest.approx(1 * 2 * 5 * 0.004, rel=1e-12)


def test_design_has_no_dollars_without_prices(tmp_path: Path) -> None:
    made = confirm_module().design([condition(on("error"))], _settings(tmp_path), _summary())
    assert (made.dollars, made.reference_dollars) == (None, None)


def test_design_runs_nothing_and_writes_nothing(tmp_path: Path) -> None:
    h = open_scenario(tmp_path, PLANTED)
    hunt_module().control(h)
    before = sorted(p.name for p in h.folder.iterdir())
    runs = h.target.runs
    confirm_module().design([condition(on("error"))], h.settings, hunt_module().control(h))
    assert h.target.runs == runs
    assert sorted(p.name for p in h.folder.iterdir()) == before


def test_design_is_frozen(tmp_path: Path) -> None:
    made = confirm_module().design([condition(on("error"))], _settings(tmp_path), _summary())
    with pytest.raises(AttributeError):
        made.repeats = 9


# ---------------------------------------------------------------------------
# BK7.2 to BK7.4, on a confirm that runs
# ---------------------------------------------------------------------------


def test_every_arm_holds_every_case_not_set_aside_the_same_number_of_times(tmp_path: Path, trace: Path) -> None:
    """BK7.2 and BK7.3: "the same cases and the same number of repeats in each"; k7 fails every control run and is
    set aside, and is in no arm."""
    h = ready(tmp_path, PLANTED)
    assert hunt_module().control(h).set_aside == ("k7",)
    confirm_module().confirm(h)
    for arm in ("confirm-control", "confirm-1", "confirm-2", "confirm-3"):
        assert per_case(h, arm) == dict.fromkeys(NOT_SET_ASIDE, 5), arm


def test_cases_are_not_chosen_by_what_discovery_saw(tmp_path: Path, trace: Path) -> None:
    """BK7.3: the search ran `error` on two cases only, where it failed; its confirm arm still holds all six."""
    h = open_scenario(tmp_path, PLANTED)
    hunt_module().control(h)
    hunt_module().run_search(h, [_Entry(condition(on("error")), ("k1", "k2"))])
    confirm_module().write_candidates(h, [condition(on("error"))])
    confirm_module().confirm(h)
    assert sorted(per_case(h, "confirm-1")) == NOT_SET_ASIDE


class _Entry:
    def __init__(self, cond: Any, case_ids: tuple[str, ...]) -> None:
        self.condition, self.cases = cond, case_ids
        self.selection = records().Selection(strategy="screen", probability=1)


def _priced() -> Scenario:
    """The planted scenario with every run reporting a thousand tokens in, at $1 a million: $0.001 a run. The
    control's fourteen runs spend $0.014, so a cap of $0.0155 lets one more run and stops before the next. Its runs
    are the planted scenario's, on the same seeds."""
    return Scenario(name="priced",
                    cases=tuple({**c, "tokens": [1000, 0]} for c in PLANTED.cases),
                    candidates=PLANTED.candidates,
                    limits={"dollars": 0.0155, "input_per_million": 1.0, "output_per_million": 1.0})


def test_the_design_is_on_disk_before_the_first_run(tmp_path: Path, trace: Path) -> None:
    """BK7.2, ruling 8: `confirm.json` holds the whole design when the stage stops after its first run."""
    priced = _priced()
    h = open_scenario(tmp_path, priced)
    hunt_module().control(h)
    confirm_module().write_candidates(h, [condition(c) for c in priced.candidates])
    with pytest.raises(hunt_module().HuntStopped):
        confirm_module().confirm(h)
    assert len(rows(h, "confirm-control")) == 1
    held = read_json(h.folder / "confirm.json")
    assert held["schema"] == "poisson_break.confirm/1"
    assert len(held["stages"]) == 1
    stage = held["stages"][0]
    assert (stage["number"], stage["repeats"], stage["cases"]) == (1, 5, NOT_SET_ASIDE)
    arms = stage["arms"]
    assert [a if isinstance(a, list) else [a["arm"], a["condition"]] for a in arms] == [
        ["confirm-control", ""], ["confirm-1", on("error")], ["confirm-2", on("timeout")], ["confirm-3", on("empty")]]


def test_a_stopped_stage_resumes_under_its_written_design_whatever_the_settings_say_now(tmp_path: Path,
                                                                                        trace: Path) -> None:
    """BK7.2: fixed before the first run. Stopped by the dollar cap, then opened again with the cap lifted and
    another number of repeats, the stage finishes with five repeats in every arm, as written."""
    priced = _priced()
    h = open_scenario(tmp_path, priced)
    hunt_module().control(h)
    confirm_module().write_candidates(h, [condition(c) for c in priced.candidates])
    with pytest.raises(hunt_module().HuntStopped):
        confirm_module().confirm(h)
    again = open_scenario(tmp_path, priced, existing=True, confirm={"repeats": 3},
                          limits={"dollars": 100.0})
    done = confirm_module().confirm(again)
    assert done.design.repeats == 5
    for arm in ("confirm-control", "confirm-1", "confirm-2", "confirm-3"):
        assert per_case(h, arm) == dict.fromkeys(NOT_SET_ASIDE, 5), arm


def test_the_runs_stored_are_the_runs_the_design_counted(tmp_path: Path, trace: Path) -> None:
    """BK7.4: "the cost in the plan is the cost": the confirm stage stores `confirm_runs`, and the reference stage
    `reference_per_finding` for each finding."""
    h = ready(tmp_path, PLANTED)
    done = confirm_module().confirm(h)
    stored = sum(len(rows(h, a)) for a in ("confirm-control", "confirm-1", "confirm-2", "confirm-3"))
    assert stored == done.design.confirm_runs == 4 * 6 * 5
    assert done.findings
    for f in done.findings:
        assert len(rows(h, f"reference-{f.number}")) == done.design.reference_per_finding == 30


# ---------------------------------------------------------------------------
# BK7.1: fresh seeds
# ---------------------------------------------------------------------------


def test_no_confirm_or_reference_seed_was_used_by_an_earlier_stage(tmp_path: Path, trace: Path) -> None:
    h = open_scenario(tmp_path, PLANTED)
    hunt_module().control(h)
    hunt_module().run_search(h, [_Entry(condition(on("error")), tuple(NOT_SET_ASIDE)),
                                 _Entry(condition(on("timeout")), tuple(NOT_SET_ASIDE))])
    hunt_module().run_search(h, [_Entry(condition(on("error")), tuple(NOT_SET_ASIDE))], stage="shrink")
    confirm_module().write_candidates(h, [condition(c) for c in PLANTED.candidates])
    done = confirm_module().confirm(h)
    earlier = seeds(h, "control") | seeds(h, "search") | seeds(h, "shrink")
    later = [f"confirm-{w}" for w in ("control", 1, 2, 3)] + [f"reference-{f.number}" for f in done.findings]
    assert done.findings
    for arm in later:
        assert seeds(h, arm) and not seeds(h, arm) & earlier, arm
    every = [s for arm in later for s in seeds(h, arm)]
    assert len(every) == len(set(every))


def test_the_desk_was_handed_the_stored_seeds(tmp_path: Path, trace: Path) -> None:
    """The seeds read above are the ones the runs were made on, not a label beside them."""
    targets.reset()
    h = ready(tmp_path, PLANTED)
    targets.reset()
    confirm_module().confirm(h)
    handed = {seed for _, seed, _ in targets.CALLS}
    assert seeds(h, "confirm-1") <= handed
