"""BK6.9: coverage adds up (spec §5.3, ruling 10 of `evidence/bk6/open-points.md`).

Tried plus untried equals the reachable space, per tool and per fault, and the five "not looked at" lines are each present when
they apply. The lines are data: the words on screen are the commands module's, so no test reads a word. Every figure is worked
by hand from the fixture beside it, and two tests hold coverage to what `screen` and `random` actually propose, so the three
cannot drift apart.
"""

from __future__ import annotations

from typing import Any

from tests.changes_support import TOOL_FAULTS
from tests.search_support import (
    ENV,
    INPUTS,
    Fixed,
    by_state,
    catalogue,
    control_rows,
    proposal,
    rng,
    row,
    search,
    seen,
    stage,
)

LINES: dict[str, Any] = {"a": "read", "w": {"class": "write", "repeatable": True}}
FAULTS = ("error", "timeout", "lost_reply")
# By hand. `a` is called twice and is a read: two calls by two faults, 4. `w` once, three faults, 3. So 7 singles on tools:
#   per tool   a 4, w 3
#   per fault  error 3 (a#1, a#2, w#1), timeout 3, lost_reply 1 (w#1)
CONTROL = {"c1": {"a": 2, "w": 1}}


def _start(*rows: Any, control: Any = None, **over: Any) -> Any:
    control = CONTROL if control is None else control
    fields: dict[str, Any] = {"cat": catalogue(FAULTS, tools=LINES), "control": control,
                              "runs": [*control_rows(control), *rows]}
    return seen(**{**fields, **over})


def _count(c: Any) -> tuple[int, int, int]:
    return (c.reachable, c.tried, c.untried)


def test_per_tool_and_per_fault_with_nothing_tried() -> None:
    made = search().coverage(_start())
    assert {t: _count(made.per_tool[t]) for t in ("a", "w")} == {"a": (4, 0, 4), "w": (3, 0, 3)}
    assert {f: _count(made.per_fault[f]) for f in FAULTS} == {"error": (3, 0, 3), "timeout": (3, 0, 3), "lost_reply": (1, 0, 1)}


def test_per_tool_and_per_fault_with_some_tried() -> None:
    made = search().coverage(_start(row("tool:a#1=error", "c1"), row("tool:a#1=error", "c1"), row("tool:w#1=lost_reply", "c1")))
    assert {t: _count(made.per_tool[t]) for t in ("a", "w")} == {"a": (4, 1, 3), "w": (3, 1, 2)}
    assert {f: _count(made.per_fault[f]) for f in FAULTS} == {"error": (3, 1, 2), "timeout": (3, 0, 3), "lost_reply": (1, 1, 0)}


def test_tried_plus_untried_is_reachable_for_every_line_of_every_fixture() -> None:
    for rows in ([], [row("tool:a#2=timeout", "c1")], [row("tool:a#1=error", "c1"), row("tool:w#1=error", "c1"), row("tool:a#9=error", "c1")]):
        made = search().coverage(_start(*rows))
        for table in (made.per_tool, made.per_fault):
            for key, c in table.items():
                assert c.tried + c.untried == c.reachable, key


def test_a_run_outside_the_space_is_not_counted_as_trying_it() -> None:
    """A strategy from outside may run `#9`, a rate, or `#*`. None of them is one of the reachable singles, so tried plus untried
    still equals reachable and nothing goes negative."""
    made = search().coverage(_start(row("tool:a#9=error", "c1"), row("tool:a~0.5=error", "c1"), row("tool:a#*=error", "c1")))
    assert _count(made.per_tool["a"]) == (4, 0, 4)
    assert _count(made.per_fault["error"]) == (3, 0, 3)


def test_tried_means_it_has_a_run_so_dropped_or_refused_or_not_run_do_not_count() -> None:
    """Ruling 10. A log entry is a proposal: only `seen.runs` says something ran."""
    result = stage(Fixed([proposal("tool:a#1=error"), proposal("tool:a#1=error")], [proposal("tool:a#2=error")]), _start(budget=1, cases_per_condition=1))
    assert by_state(result, "run") == ["tool:a#1=error"]
    assert by_state(result, "dropped") == ["tool:a#1=error"]
    assert by_state(result, "not run") == [] or by_state(result, "not run") == ["tool:a#2=error"]
    made = search().coverage(result.seen)
    assert _count(made.per_tool["a"]) == (4, 1, 3)


def test_a_condition_proposed_in_seen_but_with_no_run_is_untried() -> None:
    entry = stage(Fixed([proposal("tool:a#1=error"), proposal("tool:a#2=error")]), _start(budget=1, cases_per_condition=1)).log[1]
    assert entry.state == "not run"
    made = search().coverage(_start(proposals=(entry,)))
    assert _count(made.per_tool["a"]) == (4, 0, 4)


def test_a_pair_is_not_a_try_of_either_single() -> None:
    made = search().coverage(_start(row("tool:a#1=error + tool:w#1=error", "c1")))
    assert _count(made.per_tool["a"]) == (4, 0, 4)
    assert _count(made.per_tool["w"]) == (3, 0, 3)
    assert _count(made.per_fault["error"]) == (3, 0, 3)


def test_a_run_of_not_counted_is_still_a_try() -> None:
    """It has a run. Whether it counted is the score's to say."""
    made = search().coverage(_start(row("tool:a#1=error", "c1", "not counted")))
    assert _count(made.per_tool["a"]) == (4, 1, 3)


def test_the_control_is_not_a_try_of_anything() -> None:
    assert _count(search().coverage(_start()).per_tool["a"]) == (4, 0, 4)


def test_the_reach_stops_at_the_call_limit() -> None:
    made = search().coverage(seen(control={"c1": {"a": 5}}, cat=catalogue(("error",), max_call=2, tools=LINES)))
    assert _count(made.per_tool["a"]) == (2, 0, 2)


def test_a_set_aside_case_narrows_the_reach() -> None:
    """Ruling 12."""
    made = search().coverage(seen(control={"c1": {"a": 1}, "gone": {"a": 3, "w": 1}}, cat=catalogue(("error",), tools=LINES), set_aside=("gone",)))
    assert _count(made.per_tool["a"]) == (1, 0, 1)
    assert _count(made.per_fault["error"]) == (1, 0, 1)
    assert "w" not in made.per_tool or _count(made.per_tool["w"]) == (0, 0, 0)


# ---------------------------------------------------------------------------
# BK6.9  the five lines, each present when it applies
# ---------------------------------------------------------------------------


def _none_apply() -> Any:
    """A hunt where not one line applies: every tool called, within the limit, every fault on, nothing set aside, all tried."""
    control = {"c1": {"a": 1}}
    cat = catalogue(TOOL_FAULTS, tools={"a": "read"}, max_call=1)
    rows = [row(f"tool:a#1={f}", "c1") for f in TOOL_FAULTS if f != "lost_reply"]
    return seen(control=control, cat=cat, runs=[*control_rows(control), *rows])


def test_when_no_line_applies_every_line_is_empty() -> None:
    made = search().coverage(_none_apply())
    assert not made.never_called
    assert not made.past_limit
    assert not made.faults_off
    assert not made.set_aside
    assert not made.singles_untried
    assert not made.pairs_untried


def test_a_tool_the_control_never_saw_called_is_named() -> None:
    made = search().coverage(seen(control={"c1": {"a": 1}}, cat=catalogue(("error",), tools={"a": "read", "quiet": "read", "w": {"class": "write", "repeatable": True}})))
    assert set(made.never_called) == {"quiet", "w"}


def test_a_tool_only_one_case_calls_is_not_a_tool_the_control_never_saw() -> None:
    made = search().coverage(seen(control={"c1": {"a": 1}, "c2": {"b": 1}}, cat=catalogue(("error",), tools={"a": "read", "b": "read"})))
    assert not made.never_called


def test_a_tool_turned_off_is_not_a_tool_the_control_never_saw() -> None:
    """The user told Break never to touch it."""
    made = search().coverage(seen(control={"c1": {"a": 1}}, cat=catalogue(("error",), tools={"a": "read", "silent": "off"})))
    assert set(made.never_called) == set()


def test_call_numbers_past_the_limit_are_named() -> None:
    within = search().coverage(seen(control={"c1": {"a": 3, "b": 1}}, cat=catalogue(("error",), max_call=3, tools={"a": "read", "b": "read"})))
    assert not within.past_limit
    past = search().coverage(seen(control={"c1": {"a": 4, "b": 1}}, cat=catalogue(("error",), max_call=3, tools={"a": "read", "b": "read"})))
    assert past.past_limit
    assert "a" in past.past_limit
    assert "b" not in past.past_limit


def test_a_case_past_the_limit_that_is_set_aside_does_not_count() -> None:
    """No search runs on it, so nothing has been passed over."""
    made = search().coverage(seen(control={"c1": {"a": 1}, "gone": {"a": 9}}, cat=catalogue(("error",), max_call=3, tools={"a": "read"}), set_aside=("gone",)))
    assert not made.past_limit


def test_the_faults_turned_off_are_named() -> None:
    made = search().coverage(seen(cat=catalogue(("error", "timeout"))))
    assert set(made.faults_off) == set(TOOL_FAULTS) - {"error", "timeout"}


def test_the_cases_set_aside_are_named() -> None:
    assert set(search().coverage(seen(set_aside=("c2", "c1"))).set_aside) == {"c1", "c2"}


def test_how_many_singles_and_pairs_are_left_untried() -> None:
    """Seven singles on tools, by hand above, and 7 × 6 / 2 = 21 pairs, less the same-tool same-call ones: a#1 has 2 faults, a#2 has
    2, w#1 has 3, so 1 + 1 + 3 = 5 meet. 16."""
    made = search().coverage(_start())
    assert made.singles_untried == 7
    assert made.pairs_untried == 16


def test_untried_counts_inputs_and_env_with_the_singles() -> None:
    """§5.3: "how many reachable single changes and pairs". 7 + 2 operators + 3 settings' values = 12 singles. 12 × 11 / 2 = 66 pairs,
    less the 5 above and the 1 pair of two values of `inventory`: 60."""
    made = search().coverage(_start(cat=catalogue(FAULTS, INPUTS, env=ENV, tools=LINES)))
    assert made.singles_untried == 12
    assert made.pairs_untried == 60


def test_trying_one_single_takes_one_off_the_singles_and_nothing_off_the_pairs() -> None:
    made = search().coverage(_start(row("tool:a#1=error", "c1")))
    assert (made.singles_untried, made.pairs_untried) == (6, 16)


def test_trying_one_pair_takes_one_off_the_pairs_and_nothing_off_the_singles() -> None:
    made = search().coverage(_start(row("tool:a#1=error + tool:w#1=error", "c1")))
    assert (made.singles_untried, made.pairs_untried) == (7, 15)


def test_a_pair_that_meets_on_every_call_is_not_in_the_count() -> None:
    """Ruling 16: run by a strategy from outside, it takes nothing off."""
    made = search().coverage(_start(row("tool:a#1=error + tool:a#1=timeout", "c1")))
    assert (made.singles_untried, made.pairs_untried) == (7, 16)


# ---------------------------------------------------------------------------
# coverage against what the strategies actually propose
# ---------------------------------------------------------------------------


def _roomy(**over: Any) -> Any:
    fields: dict[str, Any] = {"control": {"c1": {"a": 2, "w": 1, "b": 1}}, "budget": 40000, "cases_per_condition": 1,
                              "cat": catalogue(("error", "timeout", "lost_reply"), INPUTS, env=ENV)}
    return seen(**{**fields, **over})


def test_after_screen_has_run_its_whole_space_no_single_is_left_and_the_pairs_are_untouched() -> None:
    start = _roomy()
    before = search().coverage(start)
    result = stage(search().Screen(), start)
    after = search().coverage(result.seen)
    assert len(by_state(result, "run")) == before.singles_untried
    assert after.singles_untried == 0
    assert after.pairs_untried == before.pairs_untried
    for table in (after.per_tool, after.per_fault):
        for key, c in table.items():
            assert c.untried == 0 and c.tried == c.reachable, key


def test_after_random_has_run_its_whole_space_nothing_is_left() -> None:
    start = _roomy()
    before = search().coverage(start)
    result = stage(search().Random(), start)
    after = search().coverage(result.seen)
    assert len(by_state(result, "run")) == before.singles_untried + before.pairs_untried
    assert (after.singles_untried, after.pairs_untried) == (0, 0)


def test_random_s_probability_is_one_over_what_coverage_counts() -> None:
    """The two must agree on N, or a reader's weights are wrong."""
    start = _roomy()
    before = search().coverage(start)
    assert search().Random().propose(start, 40000, rng=rng(1))[0].probability == 1 / (before.singles_untried + before.pairs_untried)


def test_a_stage_stopped_short_leaves_the_rest_untried() -> None:
    start = _roomy(budget=3)
    before = search().coverage(start)
    result = stage(search().Screen(), start)
    after = search().coverage(result.seen)
    assert after.singles_untried == before.singles_untried - 3


def test_coverage_refuses_assignment() -> None:
    made = search().coverage(_start())
    for field in ("per_tool", "per_fault", "never_called", "past_limit", "faults_off", "set_aside", "singles_untried", "pairs_untried"):
        try:
            setattr(made, field, None)
        except (AttributeError, TypeError):
            continue
        raise AssertionError(f"{field} took an assignment")


def test_coverage_reads_a_seen_and_changes_nothing_in_it() -> None:
    start = _start(row("tool:a#1=error", "c1"))
    runs, proposals = start.runs, start.proposals
    search().coverage(start)
    assert start.runs is runs and start.proposals is proposals
