"""`allowed` and `screen` (spec §5.3).

- BK6.2   `screen` is blind to outcomes.
- BK6.3   `screen` covers before it repeats.
- BK6.4   `screen` proposes only what can land, and nothing a session refuses: tested against a real `Session`, and not against a
  second copy of the rule.
- BK6.6   `screen` logs 1 on its fixed order.
- BK6.10  A found failure is found: on a scripted agent with one planted weakness, `screen` within a stated budget ranks that
  condition first, under real sessions and the real checks.
- Rulings 3, 12, 13 and 14 of `evidence/bk6/open-points.md`.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from typing import Any

import pytest

from tests.apply_support import fresh
from tests.changes_support import TOOL_FAULTS, changes
from tests.search_support import (
    AGENT_TOOLS,
    CONTROL,
    ENV,
    INPUTS,
    TOOLS,
    RealRuns,
    Scripted,
    apply_module,
    by_state,
    caps,
    catalogue,
    condition,
    control_rows,
    rng,
    row,
    search,
    seen,
    singles,
    space_of,
    stage,
    text_of,
    vary,
)

READ = "read"
WRITE = {"class": "write", "repeatable": True}
OFF = "off"


def _screen() -> Any:
    return search().Screen()


def _names(proposals: Any) -> list[str]:
    return [text_of(p.condition) for p in proposals]


def _tool_changes(sequence: list[str]) -> list[str]:
    return [t for t in sequence if t.startswith("tool:")]


def _parts(text: str) -> tuple[str, int, str]:
    """`tool:a#2=error` as (a, 2, error)."""
    change = changes().parse(text).changes[0]
    return change.tool, int(change.call[1:]), change.fault


# ---------------------------------------------------------------------------
# ruling 3  the catalogue the settings allow
# ---------------------------------------------------------------------------


def _faults_on(allowed_: Any) -> dict[str, set[str]]:
    return {tool: set(faults) for tool, faults in allowed_.tools.items() if faults}


def test_allowed_gives_each_tool_the_faults_the_settings_allow_and_a_session_accepts() -> None:
    made = search().allowed(vary=vary(("error", "lost_reply"), ("typos",)),
                            tools={"r": READ, "w": WRITE, "s": {"class": "write", "stand_in": "tests.apply_support_standin:refund"},
                                   "both": {"class": "read", "stand_in": "tests.apply_support_standin:refund"}, "o": OFF},
                            capabilities=caps())
    assert _faults_on(made) == {"r": {"error"}, "w": {"error", "lost_reply"}, "s": {"error", "lost_reply"}, "both": {"error"}}


def test_allowed_holds_the_rest_of_the_table() -> None:
    made = search().allowed(vary=vary(("error",), ("typos", "padded"), max_call=2, env={"inventory": ("full", "empty")}),
                            tools={"r": READ}, capabilities=caps())
    assert set(made.inputs) == {"typos", "padded"}
    assert {name: tuple(values) for name, values in made.env.items()} == {"inventory": ("full", "empty")}
    assert made.max_call == 2


def test_allowed_names_the_faults_turned_off() -> None:
    made = search().allowed(vary=vary(("error", "timeout")), tools={"r": READ}, capabilities=caps())
    assert set(made.faults_off) == set(TOOL_FAULTS) - {"error", "timeout"}


def test_a_fault_a_session_refuses_on_a_tool_is_not_a_fault_turned_off() -> None:
    """The user did not turn `lost_reply` off; it cannot land on a read."""
    made = search().allowed(vary=vary(TOOL_FAULTS), tools={"r": READ}, capabilities=caps())
    assert "lost_reply" not in made.faults_off
    assert set(made.faults_off) == set()


def test_a_way_in_that_cannot_route_tool_calls_gets_no_tool_fault_but_keeps_inputs() -> None:
    """§7.1: an agent reachable only as an endpoint can vary its inputs and nothing else."""
    made = search().allowed(vary=vary(("error",), ("typos",)), tools={"r": READ}, capabilities=caps(tool_calls=False))
    assert _faults_on(made) == {}
    assert set(made.inputs) == {"typos"}


def test_allowed_is_read_only() -> None:
    made = catalogue(inputs=INPUTS)
    for field in ("tools", "inputs", "env", "max_call", "faults_off"):
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            setattr(made, field, None)
    with pytest.raises(TypeError):
        made.tools["a"] = ("stale",)
    assert isinstance(made.inputs, (tuple, frozenset))


def test_allowed_keeps_nothing_of_the_mappings_it_was_given() -> None:
    table = vary(("error",))
    lines = {"r": READ}
    made = search().allowed(vary=table, tools=lines, capabilities=caps())
    table["tools"].append("stale")
    lines["w"] = WRITE
    assert _faults_on(made) == {"r": {"error"}}


def test_a_fault_added_from_outside_is_in_the_catalogue_when_the_settings_list_it() -> None:
    """§11.1: told from a launch fault by nothing. It is proposed by name, and it is off by name."""
    class Flip:
        name = "flip"
        surface = "tool"
        description = "the real result reversed"
        parameters: dict[str, object] = {}
        real_runs = True

        def apply(self, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
            return call

    source: Iterator[Any] = fresh()
    fresh_changes, _ = next(source)
    try:
        fresh_changes.register(Flip())
        import importlib

        s = importlib.import_module("poisson_break.search")
        interfaces = importlib.import_module("poisson_break.interfaces")
        tool_calls = interfaces.Capabilities(tool_calls=True, model_calls=False, conversation=False)
        listed = s.allowed(vary=vary(("flip",)), tools={"r": READ}, capabilities=tool_calls)
        assert _faults_on(listed) == {"r": {"flip"}}
        unlisted = s.allowed(vary=vary(("error",)), tools={"r": READ}, capabilities=tool_calls)
        assert "flip" in unlisted.faults_off
        start = s.Seen(control={"c1": {"r": 1}}, runs=(), proposals=(), budget=4, catalogue=listed, set_aside=(), cases_per_condition=1)
        assert [fresh_changes.name(p.condition) for p in s.Screen().propose(start, 4, rng=rng())] == ["tool:r#1=flip"]
    finally:
        next(source, None)


# ---------------------------------------------------------------------------
# BK6.2  screen is blind to outcomes
# ---------------------------------------------------------------------------


def _shown_outcomes(outcome: str) -> Any:
    """A `Seen` whose runs differ only in their outcomes."""
    runs = control_rows(CONTROL, outcome=lambda _c, _i: outcome)
    runs += tuple(row(text, case, outcome, seed=70 + i) for i, (text, case) in enumerate(
        [("tool:a#1=error", "c1"), ("tool:a#1=error", "c2"), ("tool:w#1=timeout", "c1")]))
    return seen(runs=runs)


def test_screens_proposals_are_identical_whatever_results_it_is_shown() -> None:
    first = _screen().propose(_shown_outcomes("ok"), 400, rng=rng())
    for outcome in ("failed", "not counted"):
        assert _screen().propose(_shown_outcomes(outcome), 400, rng=rng()) == first
    assert first


def test_screen_is_blind_when_outcomes_differ_row_by_row() -> None:
    plain = seen(runs=control_rows(CONTROL))
    odd = seen(runs=control_rows(CONTROL, outcome=lambda case, i: "failed" if (case == "c1") == (i % 2 == 0) else "ok"))
    assert _screen().propose(plain, 400, rng=rng()) == _screen().propose(odd, 400, rng=rng())


def test_a_whole_screen_stage_is_identical_whatever_the_runs_come_back_as() -> None:
    start = seen(budget=60, cases_per_condition=2, cat=catalogue(inputs=INPUTS))
    answers = [Scripted(), Scripted(lambda _t, _c: "failed"), Scripted(lambda text, _c: "failed" if "tool:a" in text else "ok"),
               Scripted(lambda _t, _c: "not counted")]
    logs = [[(text_of(e.condition), e.reason, e.probability) for e in stage(_screen(), start, run=run).log] for run in answers]
    assert logs[0]
    assert all(log == logs[0] for log in logs)


def test_screens_order_takes_nothing_from_the_generator() -> None:
    """§5.3: 1 on its fixed order. A generator that has been drawn from, or another seed, changes nothing, and it draws nothing."""
    start = seen()
    assert _screen().propose(start, 400, rng=rng(1)) == _screen().propose(start, 400, rng=rng(2))
    generator = rng(3)
    state = generator.getstate()
    _screen().propose(start, 400, rng=generator)
    assert generator.getstate() == state


# ---------------------------------------------------------------------------
# BK6.3, ruling 14  screen covers before it repeats
# ---------------------------------------------------------------------------

MAPS = [
    pytest.param({"c1": {"a": 3, "b": 2, "w": 1}}, TOOLS, TOOL_FAULTS, id="ten faults on three tools"),
    pytest.param({"c1": {"a": 2, "b": 2}, "c2": {"a": 1, "w": 2}}, TOOLS, ("error", "timeout"), id="three tools, two faults"),
    pytest.param({"c1": {f"t{i}": 2 for i in range(6)}}, {f"t{i}": READ for i in range(6)}, ("error", "timeout"), id="more tools than faults"),
    pytest.param({"c1": {"a": 2, "b": 2}}, TOOLS, ("error", "timeout"), id="as many tools as faults"),
    pytest.param({"c1": {"a": 2}}, TOOLS, TOOL_FAULTS, id="one tool"),
    # `lost_reply` lands on the write alone, and the write sorts first: taking `error` for it would leave `lost_reply` for later.
    pytest.param({"c1": {"aw": 2, "b": 2}}, {"aw": WRITE, "b": READ}, ("error", "lost_reply"), id="a fault one tool alone takes"),
]


@pytest.mark.parametrize("control, lines, faults", MAPS)
def test_every_pair_is_proposed_once_before_any_pair_at_a_second_call(control: Any, lines: Any, faults: Any) -> None:
    start = seen(control=control, cat=catalogue(faults, tools=lines), budget=4000, cases_per_condition=1)
    sequence = [_parts(t) for t in _tool_changes(space_of(_screen(), start))]
    first_pass = [(tool, fault) for tool, call, fault in sequence if call == 1]
    later = [i for i, (_t, call, _f) in enumerate(sequence) if call > 1]
    assert later, "the fixture has second calls"
    assert later[0] == len(first_pass), "a second call came before the first pass was done"
    assert len(set(first_pass)) == len(first_pass)
    on = {tool: set(fs) for tool, fs in catalogue(faults, tools=lines).tools.items()}
    assert set(first_pass) == {(tool, fault) for tool in {t for r in control.values() for t in r} for fault in on.get(tool, ())}


@pytest.mark.parametrize("control, lines, faults", MAPS)
def test_within_the_first_max_of_tools_and_faults_every_tool_and_every_fault_has_appeared(control: Any, lines: Any, faults: Any) -> None:
    """Ruling 14: the stronger reading of "each tool and each fault once before any repeats"."""
    start = seen(control=control, cat=catalogue(faults, tools=lines), budget=4000, cases_per_condition=1)
    sequence = [_parts(t) for t in _tool_changes(space_of(_screen(), start))]
    on = {tool: set(fs) for tool, fs in catalogue(faults, tools=lines).tools.items()}
    tools = {t for reach in control.values() for t in reach if on.get(t)}
    in_play = {f for t in tools for f in on[t]}
    width = max(len(tools), len(in_play))
    opening = sequence[:width]
    assert {t for t, _c, _f in opening} == tools
    assert {f for _t, _c, f in opening} == in_play


def test_a_small_budget_touches_every_tool_before_a_tool_is_saturated() -> None:
    """Why ruling 14: on a budget of three conditions with ten faults, all three tools have been tried."""
    start = seen(control={"c1": {"a": 1, "b": 1, "w": 1}}, cat=catalogue(TOOL_FAULTS), budget=3, cases_per_condition=1)
    result = stage(_screen(), start)
    assert {_parts(t)[0] for t in by_state(result, "run")} == {"a", "b", "w"}


def test_screen_proposes_each_reachable_single_exactly_once_and_nothing_else() -> None:
    """§5.3: every single change the control's map makes reachable, worked out by hand."""
    start = seen(control={"c1": {"a": 2, "w": 1}, "c2": {"b": 1}}, cat=catalogue(("error", "lost_reply"), ("typos",), env={"inventory": ("full", "empty")}), budget=4000, cases_per_condition=1)
    sequence = space_of(_screen(), start)
    assert len(sequence) == len(set(sequence))
    assert set(sequence) == {
        "tool:a#1=error", "tool:a#2=error", "tool:b#1=error", "tool:w#1=error", "tool:w#1=lost_reply",
        "input:typos", "env:inventory=full", "env:inventory=empty"}


def test_screen_stops_when_the_space_is_done_with_budget_left() -> None:
    start = seen(control={"c1": {"a": 1}}, cat=catalogue(("error",)), budget=400, cases_per_condition=1)
    run = Scripted()
    result = stage(_screen(), start, run=run)
    assert run.ran == ["tool:a#1=error"]
    assert result.seen.budget == 399
    assert result.stopped is None


def test_a_smaller_budget_is_the_start_of_the_same_order() -> None:
    """A fixed order: the budget decides where it stops, and not what comes first."""
    def run_on(budget: int) -> list[str]:
        return by_state(stage(_screen(), seen(budget=budget, cases_per_condition=1, cat=catalogue(TOOL_FAULTS, INPUTS))), "run")

    long = run_on(400)
    for budget in (1, 2, 5, 9, 13):
        assert run_on(budget) == long[:budget]


def test_screen_gives_probability_one_and_a_reason_of_one_line_to_all() -> None:
    proposed = _screen().propose(seen(cat=catalogue(TOOL_FAULTS, INPUTS, env=ENV)), 4000, rng=rng())
    assert proposed
    assert all(p.probability == 1 for p in proposed)
    assert all(isinstance(p.reason, str) and p.reason.strip() and "\n" not in p.reason for p in proposed)


def test_a_reason_says_something_about_its_own_condition() -> None:
    """§5.3: the reason is there "so the allocation can be read afterwards", so it is not one word for all."""
    result = stage(_screen(), seen(budget=4000, cases_per_condition=1))
    assert len(result.log) > 1
    assert len({e.reason for e in result.log}) > 1


def test_it_does_not_propose_again_what_it_has_proposed() -> None:
    """BK6.3: once before any repeat. A strategy is shown its own proposals, and `screen` holds to it, whatever Break would drop."""
    half_way = stage(_screen(), seen(budget=3, cases_per_condition=1))
    proposed = set(by_state(half_way, "run"))
    assert len(proposed) == 3
    ran = [e for e in half_way.log if e.state == "run"]
    later = {text_of(p.condition) for p in _screen().propose(seen(runs=half_way.seen.runs, proposals=ran, budget=4000, cases_per_condition=1), 4000, rng=rng())}
    assert later
    assert not later & proposed


def test_a_stage_goes_on_past_conditions_that_cost_less_than_a_full_one() -> None:
    """Each condition here has one case to run on, against four a condition: a batch sized for four runs a condition leaves budget, the
    stage asks again, and `screen` has to go on from where it was, or a batch of repeats ends the stage with budget unspent."""
    start = seen(control={"c1": {"a": 3, "b": 3}}, budget=8, cases_per_condition=4, cat=catalogue(("error", "timeout"), tools={"a": READ, "b": READ}))
    run = Scripted()
    result = stage(_screen(), start, run=run)
    assert run.runs == 8
    assert result.seen.budget == 0
    assert len(set(run.ran)) == 8


def test_handed_what_has_run_it_goes_on_from_there() -> None:
    """A batch of repeats would end the stage (ruling 17), so a stage that starts from a `Seen` with history goes on with the fixed
    order instead."""
    whole = space_of(_screen(), seen(budget=4000, cases_per_condition=1))
    half_way = stage(_screen(), seen(budget=len(whole) // 2, cases_per_condition=1))
    resumed = seen(runs=half_way.seen.runs, proposals=[e for e in half_way.log if e.state == "run"], budget=4000, cases_per_condition=1)
    assert by_state(half_way, "run") + by_state(stage(_screen(), resumed), "run") == whole


# ---------------------------------------------------------------------------
# BK6.4, rulings 12 and 13  screen proposes only what can land
# ---------------------------------------------------------------------------


def _session_takes(text: str, lines: dict[str, Any]) -> None:
    """The refusal itself: `ToolRefused` here is a condition a session will not run, and a hunt stops on it."""
    apply_module().Session(condition(text), seed=1, tools=lines)


CLASSED = {"r": READ, "w": WRITE, "s": {"class": "write", "stand_in": "tests.apply_support_standin:refund"},
           "both": {"class": "read", "stand_in": "tests.apply_support_standin:refund"}, "o": OFF}


def test_the_session_really_refuses_what_these_tests_say_it_does() -> None:
    """The control for the next two: a real session, refusing what `screen` must not propose."""
    for text in ("tool:r#1=lost_reply", "tool:both#1=lost_reply", "tool:o#1=error", "tool:unlined#1=error"):
        with pytest.raises(apply_module().ToolRefused):
            _session_takes(text, CLASSED)
    for text in ("tool:r#1=error", "tool:w#1=lost_reply", "tool:s#1=lost_reply", "tool:both#1=error"):
        _session_takes(text, CLASSED)


@pytest.mark.parametrize("make", ["Screen", "Random"])
def test_nothing_proposed_is_refused_by_a_real_session(make: str) -> None:
    """Every fault on every kind of tool, on a tool the control saw and on one with no line: for both strategies, since a hunt
    stops on its own proposal otherwise."""
    start = seen(control={"c1": {"r": 2, "w": 2, "s": 1, "both": 1, "o": 2, "unlined": 2}}, budget=40000, cases_per_condition=1,
                 cat=catalogue(TOOL_FAULTS, INPUTS, env=ENV, tools=CLASSED))
    run = Scripted()
    result = stage(getattr(search(), make)(), start, run=run)
    assert result.stopped is None
    assert run.ran
    lines = {**CLASSED}
    for text in run.ran:
        _session_takes(text, lines)
        assert "tool:o#" not in text and "tool:unlined#" not in text


def test_no_lost_reply_on_a_tool_not_safe_to_repeat_and_it_is_there_on_the_others() -> None:
    start = seen(control={"c1": {"r": 1, "w": 1, "s": 1, "both": 1}}, cat=catalogue(TOOL_FAULTS, tools=CLASSED), budget=4000, cases_per_condition=1)
    sequence = space_of(_screen(), start)
    assert "tool:r#1=lost_reply" not in sequence
    assert "tool:both#1=lost_reply" not in sequence
    assert "tool:w#1=lost_reply" in sequence
    assert "tool:s#1=lost_reply" in sequence


def test_no_change_on_a_tool_the_control_never_saw() -> None:
    start = seen(control={"c1": {"a": 1}}, cat=catalogue(("error",)), budget=4000)
    assert {_parts(t)[0] for t in space_of(_screen(), start)} == {"a"}


def test_no_change_at_a_call_number_the_control_never_saw() -> None:
    start = seen(control={"c1": {"a": 2}, "c2": {"a": 1}}, cat=catalogue(("error",)), budget=4000)
    assert set(space_of(_screen(), start)) == {"tool:a#1=error", "tool:a#2=error"}


def test_the_most_any_case_calls_a_tool_is_the_reach() -> None:
    start = seen(control={"c1": {"a": 1}, "c2": {"a": 3}}, cat=catalogue(("error",)), budget=4000)
    assert set(space_of(_screen(), start)) == {"tool:a#1=error", "tool:a#2=error", "tool:a#3=error"}


@pytest.mark.parametrize("max_call", [1, 2, 3, 5])
def test_no_change_past_the_call_limit(max_call: int) -> None:
    start = seen(control={"c1": {"a": 4}}, cat=catalogue(("error",), max_call=max_call), budget=4000)
    assert set(space_of(_screen(), start)) == singles({"c1": {"a": 4}}, {"a": ("error",)}, max_call=max_call)


def test_a_tool_only_a_set_aside_case_calls_is_not_reachable() -> None:
    """Ruling 12: no search runs on it."""
    start = seen(control={"c1": {"a": 1}, "gone": {"b": 1}}, cat=catalogue(("error",)), set_aside=("gone",), budget=4000)
    assert set(space_of(_screen(), start)) == {"tool:a#1=error"}


def test_a_call_only_a_set_aside_case_reaches_is_not_reachable() -> None:
    start = seen(control={"c1": {"a": 1}, "gone": {"a": 3}}, cat=catalogue(("error",)), set_aside=("gone",), budget=4000)
    assert set(space_of(_screen(), start)) == {"tool:a#1=error"}


def test_with_nothing_set_aside_the_same_map_reaches_all_of_it() -> None:
    """The control for the two above."""
    start = seen(control={"c1": {"a": 1}, "gone": {"a": 3, "b": 1}}, cat=catalogue(("error",)), budget=4000)
    assert set(space_of(_screen(), start)) == {"tool:a#1=error", "tool:a#2=error", "tool:a#3=error", "tool:b#1=error"}


def test_a_fault_turned_off_is_not_proposed() -> None:
    start = seen(cat=catalogue(("error",)), budget=4000)
    assert {_parts(t)[2] for t in space_of(_screen(), start)} == {"error"}


def test_an_operator_turned_off_is_not_proposed() -> None:
    on = seen(cat=catalogue(("error",), ("typos",)), budget=4000)
    assert [t for t in space_of(_screen(), on) if t.startswith("input:")] == ["input:typos"]


def test_every_listed_env_value_is_proposed() -> None:
    start = seen(cat=catalogue(("error",), env={"inventory": ("full", "empty"), "region": ("us",)}), budget=4000)
    assert {t for t in space_of(_screen(), start) if t.startswith("env:")} == {"env:inventory=full", "env:inventory=empty", "env:region=us"}


@pytest.mark.parametrize("make", ["Screen", "Random"])
def test_no_user_or_model_change_even_where_the_settings_and_the_way_in_offer_them(make: str) -> None:
    """Ruling 13: the map holds no turns or model calls."""
    cat = catalogue(("error",), ("typos",), capabilities=caps(model_calls=True, conversation=True),
                    conversation=["repeats"], model=["error"])
    sequence = space_of(getattr(search(), make)(), seen(cat=cat, budget=40000, cases_per_condition=1))
    assert sequence
    assert not [t for t in sequence if "user:" in t or "model:" in t]


@pytest.mark.parametrize("make", ["Screen", "Random"])
def test_no_rate_and_no_every_call_schedule(make: str) -> None:
    """Ruling 13, §3.2: the search varies the tool, the call and the fault."""
    sequence = space_of(getattr(search(), make)(), seen(budget=40000, cases_per_condition=1))
    assert sequence
    assert not [t for t in sequence if "~" in t or "#*" in t or "-" in t.split("#")[-1].split("=")[0]]


def test_screen_proposes_single_changes_only() -> None:
    sequence = space_of(_screen(), seen(budget=4000, cases_per_condition=1, cat=catalogue(TOOL_FAULTS, INPUTS, env=ENV)))
    assert all(" + " not in t for t in sequence)


def test_a_way_in_that_cannot_route_tool_calls_is_proposed_only_inputs() -> None:
    start = seen(cat=catalogue(("error",), ("typos",), capabilities=caps(tool_calls=False)), budget=4000)
    assert space_of(_screen(), start) == ["input:typos"]


# ---------------------------------------------------------------------------
# BK6.10  a found failure is found
# ---------------------------------------------------------------------------


def _ranked(result: Any) -> list[tuple[float, str]]:
    tried = by_state(result, "run")
    return sorted(((search().score(result.seen, condition(t)), t) for t in tried), key=lambda pair: (-pair[0], pair[1]))


def test_screen_within_its_first_pass_ranks_a_planted_weakness_first() -> None:
    """`repeats_write` under real sessions and the real checks: it fails under exactly one single change, `lost_reply` on its
    write. The budget is the first pass, two tools by nine faults at four cases a condition, less the one a read refuses: 17
    conditions, 68 runs. Nothing else scores above zero."""
    runs = RealRuns("repeats_write")
    start = runs.start(budget=17 * 4)
    result = stage(_screen(), start, run=runs)
    assert result.stopped is None
    assert len(by_state(result, "run")) == 17
    ranked = _ranked(result)
    assert ranked[0] == (1.0, "tool:issue_refund#1=lost_reply")
    assert all(score == 0.0 for score, _ in ranked[1:])


def test_screen_finds_it_with_outcomes_it_did_not_look_at() -> None:
    """The same weakness with a different agent's answers planted: the search is blind, so what is ranked first follows the
    runs and not the order. The planted condition comes last in the fixed order or first; either way it tops the ranking."""
    for planted in ("tool:lookup_order#1=error", "tool:issue_refund#1=timeout"):
        start = seen(control={c: {"lookup_order": 1, "issue_refund": 1} for c in ("c1", "c2", "c3", "c4")},
                     cat=catalogue(("error", "timeout"), tools=AGENT_TOOLS), budget=16)
        result = stage(_screen(), start, run=Scripted(lambda text, _case, weak=planted: "failed" if text == weak else "ok"))
        assert _ranked(result)[0] == (1.0, planted)
        assert _ranked(result)[1][0] == 0.0


def test_an_agent_with_two_weak_spots_has_both_at_the_top() -> None:
    """`follows_plant` obeys a planted instruction from either tool."""
    runs = RealRuns("follows_plant")
    start = runs.start(budget=9 * 4 * 2)
    ranked = _ranked(stage(_screen(), start, run=runs))
    assert {t for score, t in ranked if score == 1.0} == {"tool:lookup_order#1=planted_instruction", "tool:check_policy#1=planted_instruction"}
    assert all(score == 0.0 for score, t in ranked if "planted" not in t)


