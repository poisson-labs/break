"""The control stage and what it measures.

Plan BK5.6 (the control map is right), BK5.7 (cases that always fail are set aside; a base rate above one half is
flagged), spec §5.2 and §11.2 invariant 3 (the tools a way in lists), with the shapes of rulings 4, 5 and 29 of
2026-11-05 (`evidence/bk5/open-points.md`, all ruled yes). The words of the "already failing" and base-rate lines are
the commands module's: here they are data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.hunt_support import (
    AGENT_NAMES,
    CONTROL_CALLS,
    arms,
    case,
    changes,
    condition,
    desk,
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
)

PRICES = {"input_per_million": 1.0, "output_per_million": 2.0, "dollars": 50.0}


@pytest.fixture(autouse=True)
def _fresh() -> None:
    targets().reset()


def root(tmp_path: Path) -> Path:
    return tmp_path / "break-runs"


class Boom(RuntimeError):
    """What a test's way in raises to make a chosen run crash."""


def crashing_on(*runs: int) -> Any:
    def before(n: int) -> None:
        if n in runs:
            raise Boom(f"run {n} fell over")
    return before


# ---------------------------------------------------------------------------
# what the control runs (spec §5.2, ruling 4)
# ---------------------------------------------------------------------------


def test_the_control_runs_every_case_the_settings_number_of_times_with_no_change(tmp_path: Path) -> None:
    """Spec §5.2: "every case runs `control_repeats` times with no change". BK5.13: the run count is `plan_hunt`'s."""
    target = desk()
    h = open_new(root(tmp_path), target=target, cases=some_cases(4), search={"control_repeats": 3})
    summary = hunt().control(h)
    found = rows(h, "control")
    assert arms(h) == [f"{h.name}-control"]
    assert len(found) == target.runs == summary.runs == h.plan.control_runs == 12
    assert sorted((record(r).case, r["replicate_index"]) for r in found) == [
        (c, k) for c in ("c1", "c2", "c3", "c4") for k in (0, 1, 2)]
    assert {record(r).condition.name for r in found} == {""} and {record(r).stage for r in found} == {"control"}
    assert all(t.condition == condition("") for t in target.handed)


def test_the_control_asked_for_again_runs_nothing_and_says_the_same(tmp_path: Path) -> None:
    """Ruling 4: `control` runs what is missing of the control arm and summarises the arm from the store, so on a
    finished control it runs nothing. A hunt opened again later reads the same summary."""
    target = desk(before=crashing_on(2))
    h = open_new(root(tmp_path), target=target, name="kept")
    first = hunt().control(h)
    assert hunt().control(h) == first and target.runs == 6
    later = desk()
    again = hunt().open_hunt(settings_for(root(tmp_path)), target=later, cases=some_cases(), name="kept", existing=True)
    assert hunt().control(again) == first and later.runs == 0
    assert first.failed == 1


def test_a_summary_is_frozen(tmp_path: Path) -> None:
    summary = hunt().control(open_new(root(tmp_path)))
    for field in ("runs", "failed", "not_counted", "rate", "per_case", "calls", "set_aside", "high_base_rate",
                  "dollars_per_run", "seconds_per_run", "rows"):
        before = getattr(summary, field)
        with pytest.raises(Exception):  # noqa: B017 - which exception a frozen object raises is the build's
            setattr(summary, field, None)
        assert getattr(summary, field) is before


def test_the_control_tells_progress_like_any_arm(tmp_path: Path) -> None:
    """Rulings 4 and 5."""
    seen: list[tuple[int, int]] = []
    hunt().control(open_new(root(tmp_path)), on_progress=lambda done, total: seen.append((done, total)))
    assert seen == [(i, 6) for i in range(1, 7)]


def test_the_summarys_rows_are_the_control_arms_runs(tmp_path: Path) -> None:
    """Ruling 4: `rows` is what the first `Seen` of a search is built from: every control run, with its case, its
    seed and its outcome, under the empty condition."""
    target = desk(before=crashing_on(3))
    h = open_new(root(tmp_path), target=target)
    summary = hunt().control(h)
    assert isinstance(summary.rows, tuple) and len(summary.rows) == 6
    assert all(type(r) is hunt().RunRow and r.condition == condition("") for r in summary.rows)
    assert sorted((r.case, r.seed, r.outcome, r.kind) for r in summary.rows) == sorted(
        (record(r).case, r["seed"], r["outcome"], record(r).failure.kind) for r in rows(h, "control"))
    assert [r.outcome for r in summary.rows].count("failed") == 1


# ---------------------------------------------------------------------------
# BK5.6: the control map is right
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("way", ["a way in", "a plain Prove target"])
@pytest.mark.parametrize("agent", AGENT_NAMES)
def test_the_control_map_is_exactly_the_tools_and_call_counts_the_agent_makes(tmp_path: Path, way: str,
                                                                              agent: str) -> None:
    """BK5.6: "for a scripted agent with a known call pattern, `ControlSummary` reports exactly the tools and call
    counts it makes". Per case, each tool with the most calls of it in one run: two repeats do not double a count,
    and a tool the agent never calls is not in the map."""
    cases = some_cases(2, agent=agent)
    if way == "a way in":
        h = open_new(root(tmp_path), target=desk(agent), cases=cases)
    else:
        settings = settings_for(root(tmp_path))
        h = hunt().open_hunt(settings, target=rollout(settings), cases=cases, name=None)
    summary = hunt().control(h)
    assert {ident: dict(tools) for ident, tools in summary.calls.items()} == {"c1": CONTROL_CALLS[agent],
                                                                             "c2": CONTROL_CALLS[agent]}


def test_the_control_map_is_kept_case_by_case(tmp_path: Path) -> None:
    """Spec §5.2: "the tools each case calls and how many times, which is the map of where a tool fault can land at
    all". Four cases answered by four agents give four different lines."""
    cases = [case(agent, agent=agent) for agent in AGENT_NAMES]
    summary = hunt().control(open_new(root(tmp_path), cases=cases))
    assert {ident: dict(tools) for ident, tools in summary.calls.items()} == CONTROL_CALLS


def test_a_tool_that_is_off_is_not_in_the_control_map(tmp_path: Path) -> None:
    """Spec §3.6: an `off` tool is one "Break never touches, and never counts"."""
    tools = {"lookup_order": "read", "check_policy": "off", "issue_refund": {"class": "write", "repeatable": True}}
    summary = hunt().control(open_new(root(tmp_path), cases=some_cases(1), tools=tools))
    assert {ident: dict(found) for ident, found in summary.calls.items()} == {"c1": {"lookup_order": 2}}
    assert ("check_policy", {"topic": "refunds", "note": None}) in targets().EXECUTED


def test_a_case_whose_runs_made_no_call_has_an_empty_line_in_the_map(tmp_path: Path) -> None:
    summary = hunt().control(open_new(root(tmp_path), cases=[case("a"), case("b", does="crash")]))
    assert {ident: dict(found) for ident, found in summary.calls.items()} == {"a": CONTROL_CALLS["gives_up"], "b": {}}


# ---------------------------------------------------------------------------
# BK5.7 and spec §5.2: rates, cases set aside, a high base rate
# ---------------------------------------------------------------------------


def mixed(tmp_path: Path) -> Any:
    """Four cases at four repeats: `a` never fails, `b` always crashes, the first run of `c` is not counted, and `d`
    crashes on three of its four runs. Runs go case by case, so `c`'s first is the ninth and `d`'s are the thirteenth
    to the sixteenth."""
    def before(n: int) -> None:
        if n == 9:
            raise changes().InstrumentError("the way in lost its agent")
        if n in (13, 14, 15):
            raise Boom(f"run {n} fell over")

    cases = [case("a"), case("b", does="crash"), case("c"), case("d")]
    h = open_new(root(tmp_path), target=desk(before=before), cases=cases, search={"control_repeats": 4})
    return hunt().control(h)


def test_the_summary_counts_runs_failures_and_runs_not_counted(tmp_path: Path) -> None:
    """Spec §5.2: "the share of runs that fail with no help, per case and overall". Ruling 4: failed over counted,
    so a run that was not counted is in neither side of a rate."""
    summary = mixed(tmp_path)
    assert (summary.runs, summary.failed, summary.not_counted) == (16, 7, 1)
    assert summary.rate == pytest.approx(7 / 15)
    assert dict(summary.per_case) == {"a": 0.0, "b": 1.0, "c": 0.0, "d": 0.75}
    assert summary.high_base_rate is False


def test_a_case_that_fails_every_control_run_is_set_aside_and_named(tmp_path: Path) -> None:
    """BK5.7, spec §5.2: "a case that fails every control run is set aside". One that failed three times in four is
    not, and neither is one with a run that was not counted and no failure."""
    summary = mixed(tmp_path)
    assert tuple(summary.set_aside) == ("b",)


def test_a_case_none_of_whose_runs_counted_is_not_set_aside(tmp_path: Path) -> None:
    """Spec §5.2 sets aside a case that "fails every control run". A case whose runs were all not counted failed
    none, and says nothing about the agent."""
    cases = [case("a"), case("b", does="instrument"), case("c", does="crash")]
    summary = hunt().control(open_new(root(tmp_path), cases=cases))
    assert tuple(summary.set_aside) == ("c",) and summary.not_counted == 2


def test_the_cases_set_aside_are_named_in_the_cases_own_order(tmp_path: Path) -> None:
    cases = [case("z", does="crash"), case("m"), case("a", does="exit"), case("k", does="limit")]
    summary = hunt().control(open_new(root(tmp_path), cases=cases))
    assert tuple(summary.set_aside) == ("z", "a", "k")


def test_with_no_case_always_failing_none_is_set_aside(tmp_path: Path) -> None:
    summary = hunt().control(open_new(root(tmp_path), target=desk(before=crashing_on(1, 4))))
    assert tuple(summary.set_aside) == () and summary.failed == 2


@pytest.mark.parametrize(("cases", "crash_on", "expected"), [
    ([case("a", does="crash"), case("b")], (3,), True),
    ([case("a", does="crash"), case("b")], (), False),
    ([case("a"), case("b")], (1,), False),
    ([case("a", does="crash"), case("a2", does="crash"), case("b", does="instrument"), case("c")], (), True),
    ([case("a", does="crash"), case("b", does="instrument"), case("c")], (), False),
], ids=["three of four", "exactly half", "one of four", "four of six counted, two more not counted",
        "two of four counted, two more not counted"])
def test_a_base_rate_above_one_half_is_flagged(tmp_path: Path, cases: Any, crash_on: tuple[int, ...],
                                              expected: bool) -> None:
    """BK5.7: "a base rate above one half produces the stated note"; spec §5.2: "if the agent already fails in more
    than half its control runs". Ruling 4: the summary says so as true or false, over the runs that counted, so
    exactly half is not above it and runs not counted do not dilute it."""
    h = open_new(root(tmp_path), target=desk(before=crashing_on(*crash_on)), cases=cases)
    summary = hunt().control(h)
    assert summary.high_base_rate is expected


# ---------------------------------------------------------------------------
# cost and time per run (spec §5.2, ruling 4)
# ---------------------------------------------------------------------------


def test_with_no_prices_the_summary_has_no_dollars(tmp_path: Path) -> None:
    """Spec §9.3: without prices Break "shows no dollars"."""
    summary = hunt().control(open_new(root(tmp_path), cases=some_cases(2, tokens=[1000, 500])))
    assert summary.dollars_per_run is None


def test_with_prices_the_cost_of_a_run_is_its_tokens_at_the_two_prices(tmp_path: Path) -> None:
    """Spec §5.2: "tokens and seconds per run where the adapter can see them". A thousand tokens in at $1 a million
    and five hundred out at $2 a million is $0.002; a run three times that size is $0.006, and the summary gives
    the mean over the control's runs."""
    cases = [case("a", tokens=[1000, 500]), case("b", tokens=[3000, 1500])]
    summary = hunt().control(open_new(root(tmp_path), cases=cases, limits=PRICES))
    assert summary.dollars_per_run == pytest.approx(0.004)


def test_a_run_whose_way_in_saw_no_tokens_costs_nothing(tmp_path: Path) -> None:
    """Ruling 24, spec §4: "tokens nobody counted are over nothing"."""
    summary = hunt().control(open_new(root(tmp_path), limits=PRICES))
    assert summary.dollars_per_run == 0


def test_the_time_of_a_run_is_measured(tmp_path: Path) -> None:
    """Spec §5.2: the control measures "the cost and time of one run". Four runs that each nap three tenths of a second
    take about that long each, not the 1.2 seconds of the four together. The margin is wide, for a busy machine."""
    summary = hunt().control(open_new(root(tmp_path), cases=some_cases(2, nap=0.3)))
    assert 0.3 <= summary.seconds_per_run < 1.0


# ---------------------------------------------------------------------------
# the tools a way in lists, after the control (spec §11.2 invariant 3, ruling 29)
# ---------------------------------------------------------------------------


def test_a_tool_the_control_saw_that_the_way_in_did_not_list_stops_the_hunt_and_is_named(tmp_path: Path) -> None:
    """Spec §11.2 invariant 3: "`tools()` before any run equals the set of tools seen during the control stage, or the
    difference is named ... and the hunt is refused". Ruling 29: a tool seen and not listed stops the hunt after the
    control, with the control's runs kept."""
    target = desk(listed=["lookup_order", "issue_refund"])
    h = open_new(root(tmp_path), target=target)
    stop = stopped(lambda: hunt().control(h))
    assert stop.reason == "tools" and tuple(stop.tools) == ("check_policy",)
    assert (stop.arm, stop.kept) == (f"{h.name}-control", 6)
    assert store_of(h).count(f"{h.name}-control") == 6
    assert stopped(lambda: hunt().control(h)).reason == "tools" and target.runs == 6


def test_a_tool_listed_and_never_called_is_no_difference(tmp_path: Path) -> None:
    """Ruling 29: a tool the agent has and did not use on these cases is coverage's first "not looked at" line (spec
    §5.3), not a reason to refuse a hunt. `gives_up` never issues a refund."""
    target = desk(listed=["lookup_order", "check_policy", "issue_refund"])
    summary = hunt().control(open_new(root(tmp_path), target=target))
    assert all("issue_refund" not in found for found in summary.calls.values()) and summary.runs == 6
