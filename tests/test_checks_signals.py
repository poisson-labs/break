"""Giving up, retry storms and going over budget: counted beside a run, and failures only if promoted.

Invariant pinned here (Break — Plan, the failure check):
- BK3.5 Signals are not failures unless promoted, and each of `gave_up`, `retry_storm` and `over_budget` has a trigger
        and a control. `gave_up` does not count under a `#*` schedule.

What a count counts, what word a promoted signal is written down as, and where it falls in §4's order are in
`test_checks_ruled.py`. Here a test reads only whether one counted anything, and that the run failed with one kind.
"""

from __future__ import annotations

from typing import Any

import pytest

from poisson_break import records
from tests.apply_support import CASE, Tool
from tests.checks_support import (
    OK,
    all_tools,
    budget,
    checks,
    failed,
    judged,
    judged_by,
    kind_of,
    lines_of,
    outcome_of,
    plain,
    stated_retries,
    state_of,
    verdict,
    way_in,
)

GIVES_UP_FAULTS = ["error", "timeout", "rate_limited"]
OTHER_FAULTS = ["empty", "cut_off", "malformed", "stale", "planted_instruction"]


def counted(run: Any) -> dict[str, bool]:
    s = checks().signals(run)
    return {"gave_up": s.gave_up > 0, "retry_storm": s.retry_storm > 0, "over_budget": s.over_budget > 0}


NOTHING = {"gave_up": False, "retry_storm": False, "over_budget": False}


def only(signal: str) -> dict[str, bool]:
    return {**NOTHING, signal: True}


def calls(tool: str, n: int, **args: Any) -> list[tuple[str, dict[str, Any]]]:
    return [(tool, dict(args)) for _ in range(n)]


# ---------------------------------------------------------------------------
# gave_up
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fault", GIVES_UP_FAULTS)
@pytest.mark.parametrize("change", ["tool:lookup_order#1", "tool:check_policy#1", "tool:lookup_order#2"])
def test_it_gave_up_on_a_tool_whose_fault_had_a_schedule_that_ends(change: str, fault: str) -> None:
    assert counted(plain("gives_up", f"{change}={fault}").run)["gave_up"] is True


def test_it_gave_up_inside_a_schedule_with_a_range() -> None:
    """`#1-2` ends, whether the agent saw the end of it or not."""
    assert counted(plain("gives_up", "tool:lookup_order#1-2=error").run)["gave_up"] is True


def test_with_no_fault_nothing_gave_up() -> None:
    assert counted(plain("gives_up").run) == NOTHING


@pytest.mark.parametrize("fault", GIVES_UP_FAULTS)
def test_a_tool_under_an_every_call_schedule_does_not_count(fault: str) -> None:
    """BK3.5: with the tool down on every call, stopping is the sensible thing and says nothing of the agent."""
    scene = plain("gives_up", f"tool:lookup_order#*={fault}")
    assert len(scene.session.calls) == 1
    assert counted(scene.run)["gave_up"] is False


def test_an_every_call_schedule_on_one_tool_does_not_excuse_another() -> None:
    """Giving up is on a tool, and `a` had a schedule that ended."""
    scene = way_in("tool:a#1=error + tool:b#*=error", script=[("a", {}), ("b", {})])
    assert counted(scene.run)["gave_up"] is True


def test_calling_the_tool_again_is_not_giving_up() -> None:
    assert counted(plain("retries", "tool:lookup_order#1=error").run) == NOTHING


def test_a_later_call_of_it_in_any_form_is_calling_it_again() -> None:
    scene = way_in("tool:lookup_order#1=error", script=[("lookup_order", {"q": 1}), ("a", {}), ("lookup_order", {"q": 2})])
    assert counted(scene.run)["gave_up"] is False


def test_it_looks_at_the_last_call_of_the_tool_and_not_the_first() -> None:
    """Called and worked, called and failed, and never called again."""
    scene = way_in("tool:lookup_order#2=error", script=[("lookup_order", {"q": 1}), ("lookup_order", {"q": 2})])
    assert counted(scene.run)["gave_up"] is True


@pytest.mark.parametrize("fault", OTHER_FAULTS)
def test_a_fault_that_does_not_fail_is_nothing_to_give_up_on(fault: str) -> None:
    """§4 names three."""
    scene = way_in(f"tool:a#1={fault}", script=[("a", {})])
    assert counted(scene.run)["gave_up"] is False


def test_a_tools_own_failure_is_not_on_a_schedule() -> None:
    """§4: a tool returned one of three words on a schedule. There is none here, only a tool that broke."""
    tools = {**all_tools(), "lookup_order": Tool(raises=LookupError("the service is down"))}
    assert counted(plain("gives_up", tools=tools).run)["gave_up"] is False


def test_a_fault_on_a_call_the_agent_never_made_is_nothing() -> None:
    assert counted(plain("gives_up", "tool:check_policy#4=error").run)["gave_up"] is False


# ---------------------------------------------------------------------------
# retry_storm
# ---------------------------------------------------------------------------


def test_six_in_a_row_is_a_storm() -> None:
    """More than five, by default. `retries` makes the six itself, failing five times and then getting through."""
    scene = plain("retries", "tool:lookup_order#1-5=error")
    assert len(scene.session.calls) == 6
    assert counted(scene.run)["retry_storm"] is True


def test_five_in_a_row_is_not() -> None:
    scene = plain("retries", "tool:lookup_order#1-4=error")
    assert len(scene.session.calls) == 5
    assert counted(scene.run)["retry_storm"] is False


def test_to_its_limit_it_is_a_storm() -> None:
    scene = plain("retries", "tool:lookup_order#*=error")
    assert counted(scene.run)["retry_storm"] is True


def test_it_does_not_depend_on_a_fault() -> None:
    """§4: called one tool too many times. That the tool worked each time does not matter."""
    assert counted(way_in(script=calls("a", 6)).run) == only("retry_storm")


def test_nor_on_the_arguments() -> None:
    assert counted(way_in(script=[("a", {"q": i}) for i in range(6)]).run)["retry_storm"] is True


def test_in_a_row_means_with_nothing_between() -> None:
    script = [*calls("a", 3), ("b", {}), *calls("a", 3)]
    assert counted(way_in(script=script).run)["retry_storm"] is False


def test_it_may_come_anywhere_in_the_run() -> None:
    for script in ([("b", {}), *calls("a", 6)], [*calls("a", 6), ("b", {})], [("b", {}), *calls("a", 6), ("b", {})]):
        assert counted(way_in(script=script).run)["retry_storm"] is True, script


def test_two_tools_are_not_one_tools_storm() -> None:
    assert counted(way_in(script=[*calls("a", 3), *calls("b", 3)]).run)["retry_storm"] is False


@pytest.mark.parametrize("stated, n, expected", [(2, 2, False), (2, 3, True), (10, 10, False), (10, 11, True)])
def test_the_number_can_be_stated(stated: int, n: int, expected: bool) -> None:
    assert counted(way_in(script=calls("a", n), fails=stated_retries(stated)).run)["retry_storm"] is expected


# ---------------------------------------------------------------------------
# over_budget
# ---------------------------------------------------------------------------


def test_more_tool_calls_than_the_settings_allow() -> None:
    assert counted(plain("gives_up", fails=budget(tool_calls=2)).run) == only("over_budget")


def test_as_many_as_they_allow_is_not_more() -> None:
    assert counted(plain("gives_up", fails=budget(tool_calls=3)).run) == NOTHING


def test_with_no_allowance_nothing_is_over_it() -> None:
    assert counted(way_in(script=calls("a", 3) + calls("b", 2) + calls("a", 3)).run)["over_budget"] is False


def test_calls_are_counted_across_every_tool() -> None:
    assert counted(way_in(script=[("a", {}), ("b", {}), ("a", {})], fails=budget(tool_calls=2)).run) == only("over_budget")


def test_a_failed_call_is_still_a_call() -> None:
    """The agent spent it. `error` does not run the tool."""
    scene = plain("retries", "tool:lookup_order#1-2=error", fails=budget(tool_calls=2))
    assert len(scene.session.calls) == 3
    assert counted(scene.run)["over_budget"] is True


def test_more_tokens_than_the_settings_allow() -> None:
    assert counted(plain("gives_up", tokens=(100, 100), fails=budget(tokens=50)).run) == only("over_budget")


def test_fewer_tokens_are_not() -> None:
    assert counted(plain("gives_up", tokens=(10, 10), fails=budget(tokens=50)).run) == NOTHING


def test_tokens_nobody_counted_are_not_over_anything() -> None:
    """A way in that cannot see tokens reports none (§11.2), which is not zero and is not a failure to read."""
    assert counted(way_in(tokens=(None, None), fails=budget(tokens=50)).run) == NOTHING


def test_tokens_with_no_allowance_are_not_over_it() -> None:
    assert counted(plain("gives_up", tokens=(10 ** 9, 10 ** 9)).run) == NOTHING


def test_one_allowance_does_not_stand_in_for_the_other() -> None:
    """Few calls, many tokens, and only calls have a line: and the other way about."""
    assert counted(way_in(tokens=(10 ** 6, 10 ** 6), fails=budget(tool_calls=50)).run)["over_budget"] is False
    assert counted(way_in(fails=budget(tokens=2)).run)["over_budget"] is False


# ---------------------------------------------------------------------------
# signals are not failures unless promoted
# ---------------------------------------------------------------------------

TRIGGER: dict[str, Any] = {
    "gave_up": lambda fails: plain("gives_up", "tool:lookup_order#1=error", fails=fails),
    "retry_storm": lambda fails: way_in(script=calls("a", 6), fails=fails),
    "over_budget": lambda fails: plain("gives_up", fails={**budget(tool_calls=1), **fails}),
}

CONTROL: dict[str, Any] = {
    "gave_up": lambda fails: plain("gives_up", fails=fails),
    "retry_storm": lambda fails: way_in(script=calls("a", 5), fails=fails),
    "over_budget": lambda fails: plain("gives_up", fails={**budget(tool_calls=3), **fails}),
}


@pytest.mark.parametrize("signal", TRIGGER)
def test_counted_it_is_not_a_failure(signal: str) -> None:
    run = TRIGGER[signal]({}).run
    assert counted(run)[signal] is True
    assert verdict(run) == OK


@pytest.mark.parametrize("signal", TRIGGER)
def test_promoted_it_is(signal: str) -> None:
    v = judged(TRIGGER[signal]({"also": [signal]}).run)
    assert state_of(v) == "failed"
    assert outcome_of(v) == "failed"
    assert isinstance(kind_of(v), str) and kind_of(v)


@pytest.mark.parametrize("signal", TRIGGER)
def test_promoted_with_nothing_to_count_it_is_not(signal: str) -> None:
    run = CONTROL[signal]({"also": [signal]}).run
    assert counted(run)[signal] is False
    assert verdict(run) == OK


@pytest.mark.parametrize("signal", TRIGGER)
def test_promoting_another_does_not_promote_this_one(signal: str) -> None:
    others = [s for s in TRIGGER if s != signal]
    run = TRIGGER[signal]({"also": others}).run
    assert counted(run)[signal] is True
    assert verdict(run) == OK


@pytest.mark.parametrize("signal", TRIGGER)
def test_promoting_it_leaves_the_count_as_it_was(signal: str) -> None:
    """Still counted and still printed. Promotion changes the verdict and nothing about what was counted."""
    assert checks().signals(TRIGGER[signal]({}).run) == checks().signals(TRIGGER[signal]({"also": [signal]}).run)


@pytest.mark.parametrize("signal", TRIGGER)
def test_a_promoted_signal_is_judged_by_break(signal: str) -> None:
    """Nothing but what the agent did decided it, and the user wrote no check."""
    assert judged_by(judged(TRIGGER[signal]({"also": [signal]}).run)) == "break"


@pytest.mark.parametrize("signal", TRIGGER)
def test_a_promoted_signal_can_be_written_to_the_record(signal: str) -> None:
    """Whatever word it comes to, the record has to be able to hold it. §6.4's set is closed, and a record that
    refused the word would turn the run into a failure of Break's."""
    run = TRIGGER[signal]({"also": [signal]}).run
    assert records.Failure(kind=kind_of(judged(run)), signals=checks().signals(run)).kind == kind_of(judged(run))


def test_a_promoted_signal_does_not_hide_that_the_run_also_met_a_kind() -> None:
    """A run that met both still has one verdict and one kind."""
    case = lines_of(CASE, reply_contains="never said")
    v = judged(plain("gives_up", "tool:lookup_order#1=error", case=case, fails={"also": ["gave_up"]}).run)
    assert state_of(v) == "failed"
    assert isinstance(kind_of(v), str)


@pytest.mark.parametrize("signal", TRIGGER)
def test_a_signal_is_counted_beside_a_failure_as_well(signal: str) -> None:
    """§4: "counted and printed beside every finding". It does not go quiet because a kind was found."""
    fails = {"never_call": ["a", "lookup_order"]}
    run = TRIGGER[signal](fails).run
    assert verdict(run) == failed("forbidden_call")
    assert counted(run)[signal] is True


def test_turning_every_check_off_leaves_a_promotion_standing() -> None:
    """BK3.8: "nothing else". `checks` is the list of kinds and `also` is a list of its own."""
    assert state_of(judged(TRIGGER["gave_up"]({"checks": [], "also": ["gave_up"]}).run)) == "failed"


def test_a_tools_class_has_nothing_to_do_with_giving_up() -> None:
    """`gave_up` holds on a write as on a read. A check that read only reads would miss the refund."""
    assert counted(way_in("tool:issue_refund#1=error", script=[("issue_refund", {})]).run)["gave_up"] is True
