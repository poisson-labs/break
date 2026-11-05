"""How a stage stops short, and how a stopped hunt goes on.

Plan BK5.9 (the cap holds), BK5.10 (resume), BK5.11 (Ctrl-C), BK5.12 (instrument errors stop a stage), spec §3.6 (a
tool nobody classed stops the hunt) and BK5.3's last clause (a tool that never returns), with the shapes of rulings 6,
7, 15, 18 and 23 to 28 and 32 of 2026-11-05 (`evidence/bk5/open-points.md`, all ruled yes).

Ruling 33: what a command prints about a stop, its exit code and the question before spending are held by the commands
module's tests. Here every fact those lines print is held: why the stage stopped, in which arm, what was kept, how many
runs were not counted, and that nothing past the cap ran.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import REPO
from tests.hunt_support import (
    CONTROL_CALLS,
    apply_module,
    arms,
    case,
    condition,
    desk,
    entry,
    hunt,
    open_new,
    record,
    rollout,
    rows,
    settings_for,
    some_cases,
    stopped,
    store_of,
    targets,
    told,
)

PRICED = {"input_per_million": 1.0, "output_per_million": 2.0}
# A thousand tokens in and five hundred out at those prices: $0.002 a run.
TOKENS = [1000, 500]


@pytest.fixture(autouse=True)
def _fresh() -> None:
    targets().reset()


def root(tmp_path: Path) -> Path:
    return tmp_path / "break-runs"


def pairs(n: int, ids: Any = ("c1", "c2")) -> list[Any]:
    """`n` conditions, each on `ids`: single faults on the desk's tools, all different."""
    texts = [f"tool:{tool}#{call}={fault}" for fault in ("error", "timeout", "empty", "cut_off")
             for tool, call in (("lookup_order", 1), ("check_policy", 1), ("lookup_order", 2))]
    return [entry(text, ids) for text in texts[:n]]


def stored(h: Any) -> int:
    return sum(store_of(h).count(run) for run in arms(h))


def reopened(tmp_path: Path, name: str, *, target: Any = None, cases: Any = None, **over: Any) -> Any:
    return hunt().open_hunt(settings_for(root(tmp_path), **over), target=desk() if target is None else target,
                            cases=some_cases() if cases is None else tuple(cases), name=name, existing=True)


def interrupting_on(run: int) -> Any:
    def before(n: int) -> None:
        if n == run:
            raise KeyboardInterrupt
    return before


# ---------------------------------------------------------------------------
# `Budget` (ruling 6)
# ---------------------------------------------------------------------------


def test_a_new_hunts_budget_is_the_settings_caps_with_nothing_spent(tmp_path: Path) -> None:
    """Ruling 6: read from what is stored. With no prices there are no dollars to count."""
    budget = open_new(root(tmp_path), search={"runs": 50}, limits={"hours": 3}).budget()
    assert (budget.runs, budget.runs_spent, budget.runs_left) == (50, 0, 50)
    assert (budget.dollars, budget.dollars_spent) == (None, None)
    assert (budget.hours, budget.seconds_spent) == (3, 0)
    with pytest.raises(Exception):  # noqa: B017 - which exception a frozen object raises is the build's
        budget.runs_spent = 7
    assert type(budget) is hunt().Budget


def test_the_budget_counts_the_control_the_search_and_the_shrink_and_not_a_confirm_arm(tmp_path: Path) -> None:
    """Ruling 6, BK4.8 and BK4.9: `runs` is the hunt's budget, the control comes out of it, search and shrink use the
    rest, and confirming has its own plan. `runs_left` is what a search's first `Seen.budget` is."""
    h = open_new(root(tmp_path), search={"runs": 50})
    hunt().control(h)
    assert (h.budget().runs_spent, h.budget().runs_left) == (6, 44)
    hunt().run_search(h, pairs(2))
    hunt().run_search(h, pairs(1), stage="shrink")
    assert (h.budget().runs_spent, h.budget().runs_left) == (12, 38)
    hunt().run_arm(h, "confirm-control", ["c1", "c2", "c3"], condition(""), repeats=2)
    hunt().run_arm(h, "reference-1", ["c1"], condition("input:typos"), repeats=2)
    assert (h.budget().runs_spent, h.budget().runs_left) == (12, 38)
    assert stored(h) == 20


def test_the_budget_prices_what_was_spent_and_times_it(tmp_path: Path) -> None:
    """Ruling 6 and 24: dollars are each stored run's tokens at the two prices; seconds are the stored runs'."""
    cases = [case("a", tokens=TOKENS, nap=0.05), case("b", tokens=[3000, 1500], nap=0.05)]
    h = open_new(root(tmp_path), cases=cases, limits={**PRICED, "dollars": 9.0})
    hunt().control(h)
    budget = h.budget()
    assert budget.dollars == 9.0
    assert budget.dollars_spent == pytest.approx(2 * 0.002 + 2 * 0.006)
    assert 4 * 0.05 <= budget.seconds_spent < 2.0, "four runs of a twentieth of a second each, with room for a busy machine"


def test_the_budget_is_read_from_the_store_by_a_hunt_opened_again(tmp_path: Path) -> None:
    """Ruling 6: nothing the caller has to carry. A hunt opened later reads the same spending."""
    cases = some_cases(3, tokens=TOKENS, nap=0.02)
    h = open_new(root(tmp_path), cases=cases, name="kept", limits={**PRICED, "dollars": 9.0})
    hunt().control(h)
    hunt().run_search(h, pairs(2))
    first = h.budget()
    again = reopened(tmp_path, "kept", cases=cases, limits={**PRICED, "dollars": 9.0}).budget()
    assert (again.runs_spent, again.runs_left) == (first.runs_spent, first.runs_left) == (10, 390)
    assert again.dollars_spent == pytest.approx(first.dollars_spent) == pytest.approx(0.020)
    assert again.seconds_spent == pytest.approx(first.seconds_spent)


# ---------------------------------------------------------------------------
# BK5.9: the run cap (ruling 23)
# ---------------------------------------------------------------------------


def test_a_search_stops_before_the_run_that_would_pass_the_run_cap(tmp_path: Path) -> None:
    """BK5.9: "without prices, at the run cap". Three cases twice is a control of 6; a cap of 9 leaves 3 runs, and a
    search asked for 8 stops before its fourth, with the three it finished stored."""
    target = desk()
    h = open_new(root(tmp_path), target=target, search={"runs": 9})
    hunt().control(h)
    stop = stopped(lambda: hunt().run_search(h, pairs(4)))
    assert (stop.reason, stop.arm, stop.kept) == ("runs", f"{h.name}-search", 3)
    assert isinstance(stop, hunt().HuntStopped) and str(stop).strip() and "\n" not in str(stop)
    assert target.runs == 9 and stored(h) == 9
    assert (h.budget().runs_spent, h.budget().runs_left) == (9, 0)
    assert [(record(r).condition.name, record(r).case) for r in rows(h, "search")] and len(rows(h, "search")) == 3


def test_a_search_that_fits_the_cap_exactly_is_not_stopped(tmp_path: Path) -> None:
    h = open_new(root(tmp_path), search={"runs": 10})
    hunt().control(h)
    assert len(hunt().run_search(h, pairs(2))) == 4
    assert h.budget().runs_left == 0


def test_runs_not_counted_spend_the_run_cap_too(tmp_path: Path) -> None:
    """Ruling 23: a run that was not counted still ran, so a hunt whose runs are all dead still ends."""
    cases = [case("c1", does="instrument"), case("c2"), case("c3")]
    target = desk()
    h = open_new(root(tmp_path), target=target, cases=cases, search={"runs": 9})
    hunt().control(h)
    stop = stopped(lambda: hunt().run_search(h, pairs(4, ["c1"])))
    assert (stop.reason, stop.kept) == ("runs", 3) and target.runs == 9
    assert store_of(h).tally(f"{h.name}-search").no_outcome == 3


def test_shrinks_runs_come_out_of_the_same_cap(tmp_path: Path) -> None:
    """BK4.8: "search and shrink up to the rest of `runs`"."""
    target = desk()
    h = open_new(root(tmp_path), target=target, search={"runs": 9})
    hunt().control(h)
    hunt().run_search(h, pairs(1))
    stop = stopped(lambda: hunt().run_search(h, pairs(2), stage="shrink"))
    assert (stop.reason, stop.arm, stop.kept) == ("runs", f"{h.name}-shrink", 1)
    assert target.runs == 9


def test_a_stage_asked_for_again_at_the_cap_stops_at_once_and_runs_nothing(tmp_path: Path) -> None:
    """BK5.9 with the brief's words: no hunt spends past what its plan said. Asking again does not buy a run."""
    target = desk()
    h = open_new(root(tmp_path), target=target, search={"runs": 8})
    hunt().control(h)
    stopped(lambda: hunt().run_search(h, pairs(3)))
    for _ in range(3):
        stop = stopped(lambda: hunt().run_search(h, pairs(3)))
        assert (stop.reason, stop.kept) == ("runs", 2)
    assert target.runs == 8 and stored(h) == 8


def test_an_arm_of_the_confirm_stage_is_not_stopped_by_the_hunts_run_cap(tmp_path: Path) -> None:
    """BK4.9: "`plan_confirm` has no such limit, since `runs` is the hunt's budget"."""
    h = open_new(root(tmp_path), search={"runs": 8})
    hunt().control(h)
    hunt().run_search(h, pairs(1))
    assert len(hunt().run_arm(h, "confirm-control", ["c1", "c2", "c3"], condition(""), repeats=3)) == 9
    assert h.budget().runs_left == 0


# ---------------------------------------------------------------------------
# BK5.9: the dollar cap (ruling 24)
# ---------------------------------------------------------------------------


def priced_hunt(tmp_path: Path, cases: Any, dollars: float, *, target: Any = None, name: str = "priced") -> Any:
    return open_new(root(tmp_path), target=target, cases=cases, name=name, search={"control_repeats": 1},
                    limits={**PRICED, "dollars": dollars})


def test_a_stage_stops_before_the_run_that_would_pass_the_dollar_cap(tmp_path: Path) -> None:
    """BK5.9: "with prices given, a stage stops before the run that would pass the dollar cap, measured from recorded
    usage". Runs of $0.002 under a cap of $0.009: the control's two and two of the search's four fit, and a fifth
    would make $0.010."""
    target = desk()
    h = priced_hunt(tmp_path, some_cases(2, tokens=TOKENS), 0.009, target=target)
    hunt().control(h)
    stop = stopped(lambda: hunt().run_search(h, pairs(2)))
    assert (stop.reason, stop.arm, stop.kept) == ("dollars", f"{h.name}-search", 2)
    assert target.runs == 4
    assert h.budget().dollars_spent == pytest.approx(0.008) and h.budget().dollars_spent <= 0.009


def test_a_run_that_lands_exactly_on_the_cap_is_made(tmp_path: Path) -> None:
    """The edge of "would pass". At a dollar a token, a run of three tokens costs exactly $3, with nothing lost to
    rounding. With $12 spent, a fifth run lands on a cap of $15 and does not pass it, so it is made; a sixth would."""
    target = desk()
    h = open_new(root(tmp_path), target=target, cases=some_cases(2, tokens=[3, 0]), search={"control_repeats": 1},
                 limits={"input_per_million": 1000000.0, "output_per_million": 1000000.0, "dollars": 15.0})
    hunt().control(h)
    stop = stopped(lambda: hunt().run_search(h, pairs(2)))
    assert (stop.reason, stop.kept) == ("dollars", 3) and target.runs == 5
    assert h.budget().dollars_spent == 15.0


def test_the_next_run_is_priced_at_the_dearest_run_stored_and_not_at_the_mean(tmp_path: Path) -> None:
    """Ruling 24. Runs of $0.001, $0.004, $0.001, $0.001 under a cap of $0.0085: after the first two, $0.005 is spent.
    Priced at the dearest, a third could cost $0.004 and pass the cap, so the stage stops with two. Priced at the mean
    it would have gone on."""
    cases = [case("cheap", tokens=[1000, 0]), case("dear", tokens=[4000, 0]), case("c", tokens=[1000, 0]),
             case("d", tokens=[1000, 0])]
    target = desk()
    h = priced_hunt(tmp_path, cases, 0.0085, target=target)
    stop = stopped(lambda: hunt().control(h))
    assert (stop.reason, stop.arm, stop.kept) == ("dollars", f"{h.name}-control", 2)
    assert target.runs == 2 and h.budget().dollars_spent == pytest.approx(0.005)


def test_the_first_run_of_a_hunt_runs_whatever_the_cap(tmp_path: Path) -> None:
    """Ruling 24: with nothing recorded there is nothing to price a run at, so the first run runs. It is the one way
    a cap can be passed, and by a single run."""
    target = desk()
    h = priced_hunt(tmp_path, some_cases(3, tokens=TOKENS), 0.001, target=target)
    stop = stopped(lambda: hunt().control(h))
    assert (stop.reason, stop.kept) == ("dollars", 1) and target.runs == 1


def test_the_dollar_cap_holds_across_a_hunt_opened_again(tmp_path: Path) -> None:
    """Rulings 6 and 24: what was spent is read from the store, so stopping and opening the hunt again buys nothing."""
    cases = some_cases(2, tokens=TOKENS)
    h = priced_hunt(tmp_path, cases, 0.009)
    hunt().control(h)
    stopped(lambda: hunt().run_search(h, pairs(2)))
    target = desk()
    again = hunt().open_hunt(settings_for(root(tmp_path), search={"control_repeats": 1},
                                          limits={**PRICED, "dollars": 0.009}),
                             target=target, cases=cases, name="priced", existing=True)
    stop = stopped(lambda: hunt().run_search(again, pairs(2)))
    assert (stop.reason, stop.kept) == ("dollars", 2) and target.runs == 0


def test_with_prices_and_no_tokens_seen_the_dollar_cap_never_stops_a_stage(tmp_path: Path) -> None:
    """Ruling 24: a run whose way in saw no tokens costs nothing, so the run cap and the time cap are what hold."""
    h = priced_hunt(tmp_path, some_cases(2), 0.000001)
    hunt().control(h)
    assert len(hunt().run_search(h, pairs(3))) == 6 and h.budget().dollars_spent == 0


# ---------------------------------------------------------------------------
# BK5.9: the time cap (ruling 25)
# ---------------------------------------------------------------------------


def test_a_stage_stops_once_the_stored_runs_seconds_reach_the_time_cap(tmp_path: Path) -> None:
    """BK5.9: "or the time cap". Ruling 25: the cap is counted as the seconds of the hunt's stored runs. Eight runs of
    at least a tenth of a second under a cap of 0.35 seconds: by the fourth run the sum has passed it, so no fifth is
    made, and it stops only once the sum is there. On a busy machine a run takes longer and fewer are made."""
    target = desk()
    h = open_new(root(tmp_path), target=target, cases=some_cases(4, nap=0.1), name="timed",
                 limits={"hours": 0.35 / 3600})
    stop = stopped(lambda: hunt().control(h))
    assert stop.reason == "hours" and stop.arm == "timed-control"
    assert stop.kept == target.runs == stored(h) and 1 <= stop.kept <= 4
    assert h.budget().seconds_spent >= 0.35, "it stopped before the stored runs' seconds had reached the cap"


def test_a_resume_does_not_start_the_clock_again(tmp_path: Path) -> None:
    """Ruling 25: the sum is the hunt's, so opening it again later does not buy more time, and the time that passed
    between the stop and the resume is not charged."""
    cases = some_cases(4, nap=0.1)
    h = open_new(root(tmp_path), cases=cases, name="timed", limits={"hours": 0.35 / 3600})
    kept = stopped(lambda: hunt().control(h)).kept
    spent = h.budget().seconds_spent
    time.sleep(0.4)
    target = desk()
    again = reopened(tmp_path, "timed", target=target, cases=cases, limits={"hours": 0.35 / 3600})
    stop = stopped(lambda: hunt().control(again))
    assert (stop.reason, stop.kept) == ("hours", kept) and target.runs == 0
    assert again.budget().seconds_spent == pytest.approx(spent), "the wait between the stop and the resume was charged"


def test_the_default_time_cap_does_not_stop_a_quick_hunt(tmp_path: Path) -> None:
    h = open_new(root(tmp_path), cases=some_cases(2, nap=0.05))
    assert hunt().control(h).runs == 4


# ---------------------------------------------------------------------------
# BK5.12: a tenth not counted (ruling 26)
# ---------------------------------------------------------------------------


def broken(*places: int, of: int = 20) -> list[dict[str, Any]]:
    """`of` cases, the ones at `places` (counted from 1) breaking the way in, so their runs are not counted."""
    return [case(f"k{i:02d}", **({"does": "instrument"} if i in places else {})) for i in range(1, of + 1)]


def control_of(tmp_path: Path, cases: Any) -> tuple[Any, Any]:
    target = desk()
    return open_new(root(tmp_path), target=target, cases=cases, search={"control_repeats": 1}), target


def test_a_stage_whose_every_run_is_not_counted_stops_at_its_tenth_run_with_the_count(tmp_path: Path) -> None:
    """BK5.12: "instrument errors stop a stage when they pass a tenth of its runs, with the count". Ruling 26: judged
    after every run once ten are stored, so a way in that is simply broken costs ten runs and not a whole stage."""
    h, target = control_of(tmp_path, broken(*range(1, 21)))
    stop = stopped(lambda: hunt().control(h))
    assert (stop.reason, stop.arm, stop.kept, stop.count) == ("not counted", f"{h.name}-control", 10, 10)
    assert target.runs == 10 and store_of(h).tally(f"{h.name}-control").no_outcome == 10


@pytest.mark.parametrize(("places", "kept", "count"), [((1, 2), 10, 2), ((1, 15), 15, 2), ((9, 10, 11), 10, 2),
                                                       ((3, 12, 13), 12, 2), ((3, 20, 25), 25, 3)])
def test_it_stops_at_the_run_that_takes_the_share_past_a_tenth(tmp_path: Path, places: tuple[int, ...], kept: int,
                                                              count: int) -> None:
    """Ruling 26: more than a tenth of the runs stored so far. Two of ten is; one of ten is not, and neither is one
    of fourteen, so the second dead run at the fifteenth is what stops it. Two of twenty is not either, and the third
    at the twenty-fifth is."""
    h, target = control_of(tmp_path, broken(*places, of=30))
    stop = stopped(lambda: hunt().control(h))
    assert (stop.reason, stop.kept, stop.count) == ("not counted", kept, count)
    assert target.runs == kept


@pytest.mark.parametrize("places", [(1,), (1, 20), (7, 20), ()], ids=["one of twenty", "two of twenty, the second last",
                                                                      "two of twenty again", "none"])
def test_exactly_a_tenth_is_not_more_than_a_tenth(tmp_path: Path, places: tuple[int, ...]) -> None:
    """§4: "more than a tenth". Two of twenty is a tenth, reached only at the last run, and the stage finishes."""
    h, target = control_of(tmp_path, broken(*places))
    summary = hunt().control(h)
    assert (summary.runs, summary.not_counted) == (20, len(places)) and target.runs == 20


def test_a_stage_of_fewer_than_ten_runs_is_not_stopped_by_this_rule(tmp_path: Path) -> None:
    """Ruling 26: "once the stage has stored ten". Five dead runs of five are five rows not counted, said as such."""
    h, target = control_of(tmp_path, broken(1, 2, 3, 4, 5, of=5))
    summary = hunt().control(h)
    assert (summary.runs, summary.not_counted, target.runs) == (5, 5, 5)


def test_the_share_is_the_stages_over_every_call_that_added_to_it(tmp_path: Path) -> None:
    """Ruling 26: "of its stored runs". A search grows batch by batch; nine runs with two dead do not stop it, and the
    tenth run, in a later batch, does."""
    cases = [case("bad1", does="instrument"), case("bad2", does="instrument"), *some_cases(3)]
    target = desk()
    h = open_new(root(tmp_path), target=target, cases=cases)
    first = [entry("tool:lookup_order#1=error", ["bad1", "bad2", "c1", "c2", "c3"]),
             entry("tool:check_policy#1=error", ["c1", "c2", "c3"]), entry("input:typos", ["c1"])]
    assert len(hunt().run_search(h, first)) == 9
    stop = stopped(lambda: hunt().run_search(h, [entry("input:typos", ["c2", "c3"])]))
    assert (stop.reason, stop.arm, stop.kept, stop.count) == ("not counted", f"{h.name}-search", 10, 2)
    assert target.runs == 10


def test_each_stage_is_judged_on_its_own_runs(tmp_path: Path) -> None:
    """Ruling 26: "a stage in which more than a tenth of the runs were not counted". A control with dead runs does not
    stop the search that follows it."""
    cases = [case("bad", does="instrument"), *some_cases(4)]
    h = open_new(root(tmp_path), cases=cases, search={"control_repeats": 1})
    assert hunt().control(h).not_counted == 1
    good = [entry(f"tool:lookup_order#{n}={fault}", ["c1", "c2", "c3", "c4"]) for n in (1, 2)
            for fault in ("error", "timeout", "empty")]
    assert len(hunt().run_search(h, good)) == 24


# ---------------------------------------------------------------------------
# spec §3.6: a tool nobody classed (ruling 27)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("way", ["a way in", "a plain Prove target"])
def test_a_tool_nobody_classed_stops_the_hunt_and_that_run_is_not_stored(tmp_path: Path, way: str) -> None:
    """Spec §3.6: "a tool that appears during a run and is not classed stops the hunt with one line naming it". BK5.3:
    "a `ToolRefused` stops the hunt". Ruling 27: the stop carries the session's own refusal, the runs finished before
    it are kept, the run that met the tool is not stored, and the tool itself never ran."""
    cases = [case("a"), case("b", does="mystery"), case("c")]
    if way == "a way in":
        h = open_new(root(tmp_path), target=desk(), cases=cases, search={"control_repeats": 1})
    else:
        settings = settings_for(root(tmp_path), search={"control_repeats": 1})
        h = hunt().open_hunt(settings, target=rollout(settings), cases=cases, name=None)
    stop = stopped(lambda: hunt().control(h))
    assert (stop.reason, stop.arm, stop.kept) == ("refused", f"{h.name}-control", 1)
    assert isinstance(stop.cause, apply_module().ToolRefused) and stop.cause.tool == "mystery"
    assert [record(r).case for r in rows(h, "control")] == ["a"]
    assert "mystery" not in [tool for tool, _args in targets().EXECUTED]


def test_once_the_tool_is_classed_the_run_that_met_it_is_made(tmp_path: Path) -> None:
    """Ruling 27: not stored, because a stored run is never made again (ruling 18), and this one should be."""
    cases = [case("a"), case("b", does="mystery"), case("c")]
    h = open_new(root(tmp_path), cases=cases, name="kept", search={"control_repeats": 1})
    stopped(lambda: hunt().control(h))
    tools = {"lookup_order": "read", "check_policy": "read", "issue_refund": {"class": "write", "repeatable": True},
             "mystery": "read"}
    target = desk(listed=["lookup_order", "check_policy", "issue_refund", "mystery"])
    again = reopened(tmp_path, "kept", target=target, cases=cases, tools=tools, search={"control_repeats": 1})
    summary = hunt().control(again)
    assert [t.case["id"] for t in target.handed] == ["b", "c"]
    assert (summary.runs, summary.failed, summary.not_counted) == (3, 0, 0)
    assert dict(summary.calls["b"]) == {"mystery": 1, **CONTROL_CALLS["gives_up"]}


# ---------------------------------------------------------------------------
# BK5.3: a tool that never returns (ruling 28)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("way", ["a way in", "a plain Prove target"])
def test_a_tool_that_never_returns_is_cut_off_and_the_run_is_hung(tmp_path: Path, way: str) -> None:
    """BK5.3: "it is this module that interrupts a tool that never returns, which a session cannot see, and hands that
    over as `RunOutOfTime`". The tool here sleeps twelve seconds under a limit of three tenths. The run is a `failed`
    row with `hung`, the stage is back well inside the tool's twelve, and the run after it is the control's own, untouched."""
    cases = [case("before"), {"id": "stuck", "input": "stuck: where is my order?"}, case("after")]
    over = {"fails": {"run_seconds": 0.3}, "search": {"control_repeats": 1}}
    if way == "a way in":
        h = open_new(root(tmp_path), target=desk(), cases=cases, **over)
    else:
        settings = settings_for(root(tmp_path), **over)
        h = hunt().open_hunt(settings, target=rollout(settings), cases=cases, name=None)
    started = time.monotonic()
    handed = hunt().run_arm(h, "control", ["before", "stuck", "after"], condition(""), repeats=1)
    assert time.monotonic() - started < 8.0, "the stage waited for a tool that never returns"
    assert [(r.case, r.outcome, r.kind) for r in handed] == [("before", "ok", None), ("stuck", "failed", "hung"),
                                                              ("after", "ok", None)]
    found = {record(r).case: r for r in rows(h, "control")}
    assert told(found["stuck"]) == ("failed", "hung")
    assert [(c.tool, c.call) for c in record(found["stuck"]).calls] == [("lookup_order", 1)]
    assert [(c.tool, c.call, c.change, c.real_ran) for c in record(found["after"]).calls] == [
        (c.tool, c.call, c.change, c.real_ran) for c in record(found["before"]).calls]
    assert len(record(found["after"]).calls) == 3
    assert store_of(h).tally(f"{h.name}-control").timed_out == 0
    assert targets().AFTER_STUCK == []


def test_a_run_cut_off_is_counted_as_a_run_of_about_its_limit(tmp_path: Path) -> None:
    """The time a stuck run cost is its limit, not the tool's twelve seconds, so a time cap is not eaten by it."""
    cases = [{"id": "stuck", "input": "stuck: where is my order?"}]
    h = open_new(root(tmp_path), cases=cases, fails={"run_seconds": 0.3}, search={"control_repeats": 1, "runs": 9})
    hunt().run_arm(h, "control", ["stuck"], condition(""), repeats=1)
    assert 0.3 <= h.budget().seconds_spent < 6.0


def test_off_the_main_thread_a_late_run_is_still_hung_by_the_sessions_clock_and_the_checks(tmp_path: Path) -> None:
    """Ruling 28's limit: cutting a tool off holds for a hunt run from a program's main thread, and "from another
    thread the session's own clock still catches a run on its next call". Spec §4: a run that came back past its limit
    with no call noticing is `hung` too, read from the clock against `[fails] run_seconds`. One case naps before its
    calls and one lingers after its last, on a thread that is not the main one."""
    import threading

    cases = [case("naps", nap=0.3), case("lingers", linger=0.3), case("quick")]
    h = open_new(root(tmp_path), cases=cases, fails={"run_seconds": 0.1}, search={"control_repeats": 1})
    handed: list[Any] = []
    worker = threading.Thread(target=lambda: handed.extend(
        hunt().run_arm(h, "control", ["naps", "lingers", "quick"], condition(""), repeats=1)))
    worker.start()
    worker.join(timeout=60)
    assert not worker.is_alive()
    assert [(r.case, r.outcome, r.kind) for r in handed] == [("naps", "failed", "hung"), ("lingers", "failed", "hung"),
                                                              ("quick", "ok", None)]
    assert len(record({record(r).case: r for r in rows(h, "control")}["lingers"]).calls) == 3, "it made all its calls"


# ---------------------------------------------------------------------------
# BK5.11: Ctrl-C (ruling 32)
# ---------------------------------------------------------------------------

STAGES = {
    "control": lambda h: hunt().control(h),
    "an arm": lambda h: hunt().run_arm(h, "confirm-1", ["c1", "c2", "c3"], condition("input:typos"), repeats=2),
    "a search": lambda h: hunt().run_search(h, pairs(3)),
}


@pytest.mark.parametrize("stage", sorted(STAGES))
def test_ctrl_c_passes_through_with_every_finished_run_stored(tmp_path: Path, stage: str) -> None:
    """BK5.11: "Ctrl-C stores finished runs". Ruling 32: it passes through `control`, `run_arm` and `run_search` as it
    is, the three runs finished before it are in the store with their records, and the fourth left no row."""
    target = desk(before=interrupting_on(4))
    h = open_new(root(tmp_path), target=target)
    with pytest.raises(KeyboardInterrupt):
        STAGES[stage](h)
    assert target.runs == 4 and stored(h) == 3
    found = [r for run in arms(h) for r in rows(h, run[len(h.name) + 1:])]
    assert [told(r) for r in found] == [("ok", None)] * 3 and all(record(r).hunt == h.name for r in found)


def test_an_agents_own_ctrl_c_is_not_a_crash_and_stops_the_stage(tmp_path: Path) -> None:
    """Spec §4: "`KeyboardInterrupt` is not [a crash], and passes through, so that Ctrl-C still works"."""
    h = open_new(root(tmp_path), cases=[case("a"), case("b", does="interrupt"), case("c")])
    with pytest.raises(KeyboardInterrupt):
        hunt().control(h)
    assert [record(r).case for r in rows(h, "control")] == ["a", "a"]


# ---------------------------------------------------------------------------
# BK5.10: resume (rulings 15, 18, 21, 32)
# ---------------------------------------------------------------------------


def whole(h: Any, word: str) -> list[tuple[Any, ...]]:
    """An arm's rows as what a resumed arm must share with an unstopped one: cell, repeat, seed, outcome, error or
    not, and the whole record."""
    return sorted((r["config_hash"], r["replicate_index"], r["seed"], r["outcome"], r["error"] is None,
                   record(r).to_dict()) for r in rows(h, word))


RESUME_CASES = [case("a"), case("b", does="crash"), case("c", expect={"reply_contains": "zebra"}),
                case("d", does="limit")]


def test_a_stopped_control_resumes_without_repeating_a_stored_run(tmp_path: Path) -> None:
    """BK5.10: "a stopped arm resumes without repeating a stored run". Eight runs, stopped at the fourth: the hunt
    opened again runs the fourth to the eighth and nothing else."""
    first = desk(before=interrupting_on(4))
    h = open_new(tmp_path / "stopped", target=first, cases=RESUME_CASES, name="nightly")
    with pytest.raises(KeyboardInterrupt):
        hunt().control(h)
    second = desk()
    again = hunt().open_hunt(settings_for(tmp_path / "stopped"), target=second, cases=RESUME_CASES, name="nightly",
                             existing=True)
    summary = hunt().control(again)
    assert [t.case["id"] for t in first.handed] == ["a", "a", "b", "b"]
    assert [t.case["id"] for t in second.handed] == ["b", "c", "c", "d", "d"]
    assert summary.runs == stored(again) == 8
    assert sorted(t.seed for t in first.handed[:3] + second.handed) == sorted(r["seed"] for r in rows(again, "control"))


def test_a_resumed_arms_rows_equal_an_unstopped_arms(tmp_path: Path) -> None:
    """BK5.10: "the resumed arm's stored rows equal an unstopped one's for a scripted agent". Cell, repeat, seed,
    outcome and record, with failures of three kinds among them."""
    h = open_new(tmp_path / "stopped", target=desk(before=interrupting_on(4)), cases=RESUME_CASES, name="nightly")
    with pytest.raises(KeyboardInterrupt):
        hunt().control(h)
    again = hunt().open_hunt(settings_for(tmp_path / "stopped"), target=desk(), cases=RESUME_CASES, name="nightly",
                             existing=True)
    resumed = hunt().control(again)
    straight = open_new(tmp_path / "straight", cases=RESUME_CASES, name="nightly")
    unstopped = hunt().control(straight)
    assert whole(again, "control") == whole(straight, "control")
    assert len(whole(again, "control")) == 8
    assert (resumed.failed, resumed.set_aside, resumed.calls) == (unstopped.failed, unstopped.set_aside, unstopped.calls)
    assert sorted((r.case, r.seed, r.outcome, r.kind) for r in resumed.rows) == sorted(
        (r.case, r.seed, r.outcome, r.kind) for r in unstopped.rows)


def test_a_stopped_search_resumes_on_the_same_entries_and_equals_an_unstopped_one(tmp_path: Path) -> None:
    """Ruling 18 is the whole of resume for a search: the same entries again run exactly the pairs not yet stored."""
    entries = pairs(3, ["c1", "c2", "c3"])
    first = desk(before=interrupting_on(5))
    h = open_new(tmp_path / "stopped", target=first, name="nightly")
    with pytest.raises(KeyboardInterrupt):
        hunt().run_search(h, entries)
    second = desk()
    again = hunt().open_hunt(settings_for(tmp_path / "stopped"), target=second, cases=some_cases(), name="nightly",
                             existing=True)
    handed = hunt().run_search(again, entries)
    assert second.runs == 5 and len(handed) == 9
    straight = open_new(tmp_path / "straight", name="nightly")
    assert handed == hunt().run_search(straight, entries)
    assert whole(again, "search") == whole(straight, "search")


def test_a_hunt_stopped_at_its_cap_goes_on_under_a_raised_cap_and_ends_as_an_unstopped_one(tmp_path: Path) -> None:
    """Rulings 15 and 23: the settings handed in when a hunt is opened again apply from then on."""
    entries = pairs(3, ["c1", "c2", "c3"])
    h = open_new(tmp_path / "stopped", name="nightly", search={"runs": 10})
    hunt().control(h)
    assert stopped(lambda: hunt().run_search(h, entries)).kept == 4
    second = desk()
    again = hunt().open_hunt(settings_for(tmp_path / "stopped", search={"runs": 40}), target=second,
                             cases=some_cases(), name="nightly", existing=True)
    assert len(hunt().run_search(again, entries)) == 9 and second.runs == 5
    straight = open_new(tmp_path / "straight", name="nightly", search={"runs": 40})
    hunt().control(straight)
    hunt().run_search(straight, entries)
    assert whole(again, "search") == whole(straight, "search")
    assert whole(again, "control") == whole(straight, "control")


def test_a_run_not_counted_is_a_stored_run_and_is_not_made_again_on_resume(tmp_path: Path) -> None:
    """BK5.10: "without repeating a stored run". A row not counted is a row."""
    cases = [case("a", does="instrument"), case("b"), case("c")]
    h = open_new(root(tmp_path), target=desk(before=interrupting_on(4)), cases=cases, name="nightly")
    with pytest.raises(KeyboardInterrupt):
        hunt().control(h)
    second = desk()
    again = reopened(tmp_path, "nightly", target=second, cases=cases)
    summary = hunt().control(again)
    assert [t.case["id"] for t in second.handed] == ["b", "c", "c"]
    assert (summary.runs, summary.not_counted) == (6, 2)


KILLED = """
import os, sys
from tests import hunt_support as s
from poisson_break import hunt

def before(n):
    if n == 5:
        os._exit(9)

h = s.open_new(sys.argv[1], target=s.desk(before=before), name="nightly")
hunt.control(h)
"""


def test_a_killed_process_loses_no_finished_run_and_the_hunt_resumes(tmp_path: Path) -> None:
    """Ruling 32: "a run is stored the moment it finishes, so a stop of any kind, a kill of the process among them,
    loses nothing finished". The process dies inside its fifth run with no chance to tidy up; the four before it
    are in the store, and the hunt opened again runs the last two."""
    done = subprocess.run([sys.executable, "-c", KILLED, str(tmp_path / "killed")], cwd=REPO, env=os.environ.copy(),
                          capture_output=True, text=True)
    assert done.returncode == 9, done.stderr
    second = desk()
    again = hunt().open_hunt(settings_for(tmp_path / "killed"), target=second, cases=some_cases(), name="nightly",
                             existing=True)
    assert store_of(again).count("nightly-control") == 4
    assert [told(r) for r in rows(again, "control")] == [("ok", None)] * 4
    summary = hunt().control(again)
    assert second.runs == 2 and summary.runs == 6
    straight = open_new(tmp_path / "straight", name="nightly")
    hunt().control(straight)
    assert whole(again, "control") == whole(straight, "control")
