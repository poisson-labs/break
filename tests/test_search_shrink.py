"""BK6.8: shrink ends, and only removes (spec §5.4; rulings 9, 22, 23 and 25 of `evidence/bk6/open-points.md`).

`failures(condition)` is handed in, so a table stands in for the runs, and real runs of a scripted agent show the invariant's
last clause: on an agent broken by one of two changes, it returns that one.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Callable
from typing import Any

import pytest

from tests.changes_support import changes
from tests.search_support import RealRuns, Runaway, condition, search, text_of

A, B, C, D = "input:typos", "tool:a#1=error", "tool:b#1=timeout", "tool:c#1=empty"


def _join(*texts: str) -> str:
    return text_of(condition(" + ".join(texts)))


class Table:
    """`failures` from a table of condition name to count. A name not in it is `other`. Every call is kept."""

    def __init__(self, table: dict[str, int], *, other: int = 0) -> None:
        self.table = table
        self.other = other
        self.asked: list[str] = []

    def __call__(self, candidate: Any) -> int:
        text = text_of(candidate)
        self.asked.append(text)
        if len(self.asked) > 500:
            raise Runaway("shrink went on asking")
        return self.table.get(text, self.other)


def _shrink(text: str, failures: Callable[[Any], int], *, calls: dict[str, int] | None = None, **over: Any) -> str:
    return text_of(search().shrink(condition(text), failures=failures, calls={} if calls is None else calls, **over))


# ---------------------------------------------------------------------------
# what it keeps
# ---------------------------------------------------------------------------


def test_a_removal_that_fails_as_often_is_kept() -> None:
    assert _shrink(_join(A, B), Table({_join(A, B): 4, B: 4, A: 0})) == B


def test_a_removal_that_fails_more_often_is_kept() -> None:
    assert _shrink(_join(A, B), Table({_join(A, B): 2, B: 4, A: 0})) == B


def test_a_removal_that_fails_less_one_run_is_kept() -> None:
    assert _shrink(_join(A, B), Table({_join(A, B): 4, B: 3, A: 0})) == B


def test_a_removal_that_fails_two_runs_less_is_not() -> None:
    assert _shrink(_join(A, B), Table({_join(A, B): 4, A: 2, B: 2})) == _join(A, B)


@pytest.mark.parametrize("baseline, kept", [(1, 0), (2, 1), (4, 3), (10, 9)])
def test_the_line_is_exactly_one_run(baseline: int, kept: int) -> None:
    pair = _join(A, B)
    assert _shrink(pair, Table({pair: baseline, B: kept, A: kept - 1})) == B
    assert _shrink(pair, Table({pair: baseline, B: kept - 1, A: kept - 1})) == pair


def test_a_candidate_that_never_failed_shrinks_as_far_as_it_can() -> None:
    """0 of 4, and its removals are 0 of 4: the rule does not ask why it is here. It keeps removing and never reaches nothing."""
    assert _shrink(_join(A, B, C), Table({}, other=0)) == C


# ---------------------------------------------------------------------------
# ruling 22  against the original, not the last kept
# ---------------------------------------------------------------------------


def test_less_one_run_is_measured_against_the_original_candidate() -> None:
    """A+B+C fails 4. Removing A leaves 3, within one run of 4: kept. Removing B from that leaves 2: within one of the 3 last kept,
    but two below the original, so not kept."""
    table = {_join(A, B, C): 4, _join(B, C): 3, _join(A, C): 0, _join(A, B): 0, C: 2, B: 2}
    assert _shrink(_join(A, B, C), Table(table)) == _join(B, C)


def test_a_walk_down_by_one_run_at_a_time_stops_at_the_first_step() -> None:
    four = _join(A, B, C, D)
    table = {four: 4, _join(B, C, D): 3, _join(C, D): 2, D: 1}
    assert _shrink(four, Table(table)) == _join(B, C, D)


def test_a_kept_step_that_failed_more_does_not_raise_the_line() -> None:
    """Failing more than the original at one step does not make the later steps answer to the higher count: A+B fails 2, B+C... the
    line stays the original less one."""
    three = _join(A, B, C)
    table = {three: 2, _join(B, C): 4, C: 1, B: 0}
    assert _shrink(three, Table(table)) == C


# ---------------------------------------------------------------------------
# ruling 9  the order, and repeating until no removal survives
# ---------------------------------------------------------------------------


def test_removals_are_tried_in_the_condition_s_order_first_kept_wins() -> None:
    """Every removal survives: the first change goes first, and then the next, so the last is what is left."""
    three = _join(A, B, C)
    table = Table({}, other=4)
    assert _shrink(three, table) == C
    assert table.asked == [three, _join(B, C), C]


def test_a_removal_that_fails_is_passed_over_and_the_next_tried() -> None:
    three = _join(A, B, C)
    table = Table({three: 4, _join(A, C): 4, A: 0, C: 0})
    assert _shrink(three, table) == _join(A, C)
    assert table.asked[:3] == [three, _join(B, C), _join(A, C)]


def test_it_repeats_until_no_removal_survives() -> None:
    """Keeping one removal goes round again, so a removal that failed before gets another try on what is left."""
    four = _join(A, B, C, D)
    table = {four: 4, _join(A, C, D): 4, _join(A, D): 4, A: 0, D: 4}
    assert _shrink(four, Table(table)) == D


def test_when_it_stops_no_removal_of_what_is_left_survives() -> None:
    """Over seeded random tables, for candidates of two, three and four changes: the result answers to the rule."""
    changes_ = [A, B, C, D]
    for seed in range(300):
        draw = random.Random(seed)
        size = draw.choice([2, 3, 4])
        pick = sorted(draw.sample(changes_, size))
        full = _join(*pick)
        table = {_join(*sub): draw.randint(0, 6) for k in range(1, size + 1) for sub in itertools.combinations(pick, k)}
        result = _shrink(full, Table(table))
        left = result.split(" + ")
        assert set(left) <= set(pick), seed
        line = table[full] - 1
        assert table[result] >= line, seed
        if len(left) > 1:
            for gone in left:
                assert table[_join(*[x for x in left if x != gone])] < line, (seed, result)


# ---------------------------------------------------------------------------
# BK6.8  it ends, and it only removes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("size", [2, 3, 4])
def test_it_ends_within_a_stated_number_of_tries(size: int) -> None:
    """Each kept removal shortens the condition and each round tries each change at most once: at most 1 + n(n+1)/2 calls."""
    for other in (0, 4):
        full = _join(*[A, B, C, D][:size])
        table = Table({full: 4}, other=other)
        _shrink(full, table)
        assert 1 <= len(table.asked) <= 1 + size * (size + 1) // 2


def test_the_result_is_a_subset_of_the_candidate_s_changes_whatever_the_answers() -> None:
    for seed in range(100):
        draw = random.Random(seed)
        full = _join(A, B, C, D)
        result = _shrink(full, lambda _c, d=draw: d.randint(0, 6))
        assert set(result.split(" + ")) <= {A, B, C, D}


def test_it_is_never_asked_about_the_control_and_never_returns_it() -> None:
    table = Table({}, other=9)
    assert _shrink(_join(A, B), table) != ""
    assert "" not in table.asked


@pytest.mark.parametrize("text", [A, B, "tool:a#2-3=error", "tool:a~0.3=error"])
def test_a_candidate_of_one_change_is_returned_as_it_is_with_no_run_spent(text: str) -> None:
    """§5.4: "For each candidate with more than one change". The one exception is a `#*`, below."""
    table = Table({}, other=4)
    assert _shrink(text, table, calls={"a": 3}) == text
    assert table.asked == []


def test_what_it_returns_is_a_condition_written_canonically() -> None:
    result = search().shrink(condition(_join(A, B, C)), failures=Table({}, other=4), calls={})
    assert isinstance(result, changes().Condition)
    assert changes().parse(changes().name(result)) == result


def test_each_condition_it_tries_is_one_a_session_can_be_made_from() -> None:
    """A session treats changes out of order as an instrument error: what `failures` is handed is canonical."""
    asked: list[Any] = []

    def failures(candidate: Any) -> int:
        asked.append(candidate)
        return 4

    search().shrink(condition(_join(A, B, C)), failures=failures, calls={})
    assert asked
    for one in asked:
        assert isinstance(one, changes().Condition)
        assert changes().parse(changes().name(one)) == one


def test_a_condition_holding_an_env_change_shrinks_without_needing_the_settings() -> None:
    """A name holding `env:` parses only against `[vary.env]`, and `shrink` is not given them: it takes changes away."""
    both = f"env:inventory=full + {B}"
    assert _shrink(both, Table({both: 4, B: 4, "env:inventory=full": 0})) == B


def test_a_condition_keeping_its_env_change_needs_no_settings_either() -> None:
    """The same with the `env:` change the one that stays."""
    both = f"env:inventory=full + {B}"
    assert _shrink(both, Table({both: 4, "env:inventory=full": 4, B: 0})) == "env:inventory=full"
    three = f"env:inventory=full + {B} + {C}"
    assert _shrink(three, Table({three: 4, f"env:inventory=full + {B}": 4, "env:inventory=full": 0, B: 0})) == f"env:inventory=full + {B}"


def test_the_candidate_is_left_as_it_was() -> None:
    held = condition(_join(A, B))
    search().shrink(held, failures=Table({}, other=4), calls={})
    assert text_of(held) == _join(A, B)


# ---------------------------------------------------------------------------
# ruling 9  `tries`
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tries", [0, 1, 2, 3, 4, 5])
def test_tries_caps_the_calls_of_failures(tries: int) -> None:
    table = Table({}, other=4)
    _shrink(_join(A, B, C, D), table, tries=tries)
    assert len(table.asked) <= tries


def test_out_of_tries_it_returns_the_smallest_so_far() -> None:
    four = _join(A, B, C, D)
    assert _shrink(four, Table({}, other=4), tries=0) == four
    assert _shrink(four, Table({}, other=4), tries=1) == four
    assert _shrink(four, Table({}, other=4), tries=2) == _join(B, C, D)
    assert _shrink(four, Table({}, other=4), tries=3) == _join(C, D)


def test_tries_left_unset_runs_to_the_end() -> None:
    assert _shrink(_join(A, B, C, D), Table({}, other=4)) == D


def test_enough_tries_is_the_same_as_none() -> None:
    table = {_join(A, B, C): 4, _join(A, C): 4, A: 0, C: 0}
    assert _shrink(_join(A, B, C), Table(table), tries=50) == _shrink(_join(A, B, C), Table(table))


# ---------------------------------------------------------------------------
# ruling 23  `#*` is tried as each single call
# ---------------------------------------------------------------------------

EVERY = "tool:a#*=error"


def test_every_call_is_tried_as_each_single_call_and_the_one_that_fails_is_kept() -> None:
    table = Table({EVERY: 4, "tool:a#2=error": 4})
    assert _shrink(EVERY, table, calls={"a": 3}) == "tool:a#2=error"
    assert table.asked == [EVERY, "tool:a#1=error", "tool:a#2=error"]


def test_every_call_is_tried_up_to_its_reach_and_no_further() -> None:
    table = Table({EVERY: 4})
    assert _shrink(EVERY, table, calls={"a": 2}) == EVERY
    assert table.asked == [EVERY, "tool:a#1=error", "tool:a#2=error"]


def test_when_no_single_call_fails_as_often_it_stays_every_call() -> None:
    assert _shrink(EVERY, Table({EVERY: 4}), calls={"a": 3}) == EVERY


def test_a_single_call_within_one_run_is_good_enough() -> None:
    assert _shrink(EVERY, Table({EVERY: 4, "tool:a#3=error": 3}), calls={"a": 3}) == "tool:a#3=error"


def test_the_first_single_call_that_survives_is_kept_and_the_others_are_not_tried() -> None:
    table = Table({EVERY: 4, "tool:a#1=error": 4, "tool:a#2=error": 4})
    assert _shrink(EVERY, table, calls={"a": 3}) == "tool:a#1=error"
    assert table.asked == [EVERY, "tool:a#1=error"]


def test_a_tool_with_no_reach_stays_every_call_with_nothing_spent_on_it() -> None:
    table = Table({EVERY: 4})
    assert _shrink(EVERY, table, calls={}) == EVERY
    assert all(t == EVERY for t in table.asked)


def test_every_call_beside_another_change() -> None:
    """Removing `input:typos` is tried first, in the condition's order: the result can lose both."""
    both = _join(EVERY, A)
    table = Table({both: 4, EVERY: 4, "tool:a#3=error": 4})
    assert _shrink(both, table, calls={"a": 3}) == "tool:a#3=error"


def test_every_call_beside_another_change_stays_when_nothing_survives() -> None:
    both = _join(EVERY, A)
    assert _shrink(both, Table({both: 4}), calls={"a": 3}) == both


def test_a_single_call_put_in_place_of_every_call_sorts_canonically() -> None:
    """`#*` sorts before `#1`, and `#2` after it: the condition has to be written again, not edited in place."""
    both = _join("tool:a#*=error", "tool:a#1=timeout")
    assert both.index("#*") < both.index("#1")
    result = search().shrink(condition(both), failures=Table({both: 4, "tool:a#1=timeout + tool:a#2=error": 4}), calls={"a": 2})
    assert text_of(result) == "tool:a#1=timeout + tool:a#2=error"
    assert changes().parse(text_of(result)) == result


def test_the_result_holds_at_most_one_single_call_in_place_of_every_call() -> None:
    """Ruling 23: "at most one replacing it"."""
    table = Table({}, other=4)
    result = _shrink(EVERY, table, calls={"a": 3})
    assert result.count("tool:a#") == 1


def test_only_every_call_is_tried_as_single_calls() -> None:
    """§5.4 says `#*`. A range is one change: removed, or not."""
    pair = _join("tool:a#1-3=error", A)
    table = Table({pair: 4, A: 0, "tool:a#1-3=error": 0})
    assert _shrink(pair, table, calls={"a": 3}) == pair
    assert set(table.asked) == {pair, A, "tool:a#1-3=error"}


def test_tries_holds_for_single_calls_too() -> None:
    table = Table({EVERY: 4})
    _shrink(EVERY, table, calls={"a": 3}, tries=2)
    assert len(table.asked) <= 2


# ---------------------------------------------------------------------------
# BK6.8  on a scripted agent broken by one of two changes
# ---------------------------------------------------------------------------

WEAK = "tool:issue_refund#1=lost_reply"


@pytest.mark.parametrize("harmless", ["tool:check_policy#1=empty", "tool:lookup_order#1=empty", "input:typos"])
def test_on_a_scripted_agent_broken_by_one_of_two_changes_it_returns_that_one(harmless: str) -> None:
    """`repeats_write`, real sessions, the real checks, on the same four cases, with the weak change first in the condition's
    order or last."""
    runs = RealRuns("repeats_write")
    pair = _join(WEAK, harmless)
    assert runs.failures(condition(pair)) == 4
    assert runs.failures(condition(harmless)) == 0
    assert runs.failures(condition(WEAK)) == 4
    assert text_of(search().shrink(condition(pair), failures=runs.failures, calls={})) == WEAK


def test_on_a_scripted_agent_broken_only_by_every_call_it_stays() -> None:
    """With `retry_storm` promoted, `retries` fails under an error on every call, and under an error on no one call, so `#*`
    stays."""
    runs = RealRuns("retries", fails={"also": ["retry_storm"], "retry_storm_after": 3})
    every = "tool:lookup_order#*=error"
    assert runs.failures(condition(every)) == 4
    assert text_of(search().shrink(condition(every), failures=runs.failures, calls={"lookup_order": 3})) == every


def test_on_a_scripted_agent_a_single_call_is_enough_for_every_call_it_narrows() -> None:
    """`repeats_write` under `lost_reply` on every call of its write fails on the first call alone."""
    runs = RealRuns("repeats_write")
    every = "tool:issue_refund#*=lost_reply"
    assert runs.failures(condition(every)) == 4
    assert text_of(search().shrink(condition(every), failures=runs.failures, calls={"issue_refund": 2})) == WEAK


# ---------------------------------------------------------------------------
# ruling 25  no-repeats does not bind shrink
# ---------------------------------------------------------------------------


def test_shrink_tries_a_condition_whatever_has_run_before() -> None:
    """Whom "no condition twice" binds is what a strategy proposes: `shrink` is given no `Seen`, and may try a condition search ran."""
    import inspect

    params = inspect.signature(search().shrink).parameters
    assert "seen" not in params
    table = Table({_join(A, B): 4, A: 0, B: 4})
    assert _shrink(_join(A, B), table) == B
    assert table.asked.count(B) == 1
