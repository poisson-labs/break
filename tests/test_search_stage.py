"""The search stage (spec §5.3, §11.3): what Break holds every strategy to, whatever the strategy returns.

- BK6.1   No condition twice: a repeat is dropped, logged as dropped, and costs no run.
- BK6.6   Every proposal is logged with its strategy, its reason and its probability; a bad one is refused before any run of
  its batch; the log replays to the same sequence.
- BK6.13  The selection: what `run` is handed carries the strategy and the probability (the stored record's end-to-end test
  waits for the runs module's names, ruling 29).
- §11.3 invariant 7: a strategy's exception stops the stage with what was kept.
- Rulings 4, 5, 17, 18, 19, 20, 21, 24 and 25 of `evidence/bk6/open-points.md`.

`run` is a callable handed in, so the runs module goes behind it later. No refusal test here reads a message's words, except
that a refusal of a change names the change, which is a fact it carries.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from tests.changes_support import changes
from tests.search_support import (
    ENV,
    Fixed,
    Scripted,
    by_state,
    catalogue,
    condition,
    duck,
    logged,
    of_state,
    proposal,
    records,
    rng,
    row,
    search,
    seen,
    stage,
    text_of,
)

A1, A2, B1 = "tool:a#1=error", "tool:a#2=error", "tool:b#1=error"
A1T = "tool:a#1=timeout"
PAIR = "tool:a#1=error + tool:b#1=timeout"
PAIR_OTHER_WAY = ("tool:b#1=timeout", "tool:a#1=error")


def _in_another_order(*texts: str) -> Any:
    """A hand-built condition with its changes in the order given, as a strategy from outside might make one."""
    ones = [changes().parse(t).changes[0] for t in texts]
    return changes().Condition(changes=tuple(ones))


# ---------------------------------------------------------------------------
# a plain stage
# ---------------------------------------------------------------------------


def test_a_stage_runs_what_is_proposed_and_gives_back_the_last_seen_the_log_and_no_stop() -> None:
    run = Scripted(lambda text, case: "failed")
    result = stage(Fixed([proposal(A1), proposal(B1)]), seen(budget=100, cases_per_condition=2), run=run)
    assert run.ran == [A1, B1]
    assert logged(result) == [(A1, "run"), (B1, "run")]
    assert result.stopped is None
    # c2 alone calls b, so B1 has one case.
    assert run.runs == 3
    assert result.seen.budget == 97
    fresh = result.seen.runs[len(seen().runs):]
    assert [text_of(r.condition) for r in fresh] == [A1, A1, B1]
    assert all(r.outcome == "failed" for r in fresh)
    assert result.seen.proposals == result.log


def test_the_log_is_in_the_order_proposed_across_batches() -> None:
    result = stage(Fixed([proposal(B1), proposal(A1)], [proposal(A2)]), seen())
    assert [t for t, _ in logged(result)] == [B1, A1, A2]


def test_a_stage_is_keyword_only_but_for_the_strategy() -> None:
    with pytest.raises(TypeError):
        search().search_stage(Fixed(), "screen", seen(), rng(), Scripted())


def test_stage_result_refuses_assignment() -> None:
    result = stage(Fixed([proposal(A1)]))
    for field in ("seen", "log", "stopped"):
        with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
            setattr(result, field, None)
    assert isinstance(result.log, tuple)


def test_a_log_entry_refuses_assignment() -> None:
    entry = stage(Fixed([proposal(A1)])).log[0]
    for field in ("strategy", "condition", "reason", "probability", "state", "cases"):
        with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
            setattr(entry, field, None)


def test_the_stage_passes_propose_the_budget_left_in_runs() -> None:
    """§11.3: `budget` is the number of runs the stage may still spend, and `seen.budget` says the same."""
    strategy = Fixed([proposal(A1)], [proposal(A2)], [])
    stage(strategy, seen(budget=11, cases_per_condition=2))
    # A1 runs on both cases (c1, c2 call a); A2 only on c1, the one case calling a twice.
    assert [shown[1] for shown in strategy.shown] == [11, 9, 8]
    assert [shown[0].budget for shown in strategy.shown] == [11, 9, 8]


# ---------------------------------------------------------------------------
# BK6.1  no condition twice
# ---------------------------------------------------------------------------


def test_a_repeat_within_a_batch_is_dropped_the_first_kept() -> None:
    run = Scripted()
    result = stage(Fixed([proposal(A1, reason="first", probability=0.5), proposal(A1, reason="second", probability=0.25)]), run=run)
    assert run.ran == [A1]
    assert logged(result) == [(A1, "run"), (A1, "dropped")]
    assert result.log[0].reason == "first"


def test_a_repeat_of_an_earlier_batch_is_dropped() -> None:
    run = Scripted()
    result = stage(Fixed([proposal(A1)], [proposal(A1), proposal(B1)]), run=run)
    assert run.ran == [A1, B1]
    assert logged(result) == [(A1, "run"), (A1, "dropped"), (B1, "run")]


def test_a_condition_already_in_seen_runs_is_a_repeat() -> None:
    """The stage may start from a `Seen` with runs in it: a resumed stage, say. They were run."""
    start = seen(runs=[row("", "c1"), row(A1, "c1")])
    run = Scripted()
    result = stage(Fixed([proposal(A1), proposal(B1)]), start, run=run)
    assert run.ran == [B1]
    assert logged(result) == [(A1, "dropped"), (B1, "run")]


def test_a_dropped_repeat_costs_no_run() -> None:
    run = Scripted()
    result = stage(Fixed([proposal(A1)], [proposal(A1), proposal(A1), proposal(A1)]), seen(budget=3, cases_per_condition=2), run=run)
    assert run.runs == 2
    assert result.seen.budget == 1
    assert len(by_state(result, "dropped")) == 3


def test_dropping_is_not_paying_for() -> None:
    """A repeat ahead of a new condition does not use up the budget the new one needs."""
    run = Scripted()
    result = stage(Fixed([proposal(A1), proposal(A1), proposal(A2)]), seen(budget=3, cases_per_condition=2), run=run)
    assert run.ran == [A1, A2]
    assert by_state(result, "dropped") == [A1]


def test_a_dropped_repeat_is_logged_with_its_strategy_reason_and_probability() -> None:
    result = stage(Fixed([proposal(A1)], [proposal(A1, reason="once more", probability=0.125)]), name="mine:Own")
    entry = of_state(result.log, "dropped")[0]
    assert (text_of(entry.condition), entry.strategy, entry.reason, entry.probability) == (A1, "mine:Own", "once more", 0.125)


def test_a_second_spelling_is_a_repeat() -> None:
    """§3.1: two spellings of the same condition have one name. `parse` writes these as one already; ruling 20 has the stage
    do it for a condition built by hand."""
    run = Scripted()
    result = stage(Fixed([proposal(PAIR), search().Proposal(condition=_in_another_order(*PAIR_OTHER_WAY), reason="r", probability=0.5)]),
                   run=run)
    assert run.ran == [PAIR]
    assert logged(result) == [(PAIR, "run"), (PAIR, "dropped")]


def test_a_condition_built_in_another_order_runs_under_its_canonical_name() -> None:
    """Ruling 20: written canonically before comparing. A session treats any other order as an instrument error, so what reaches
    `run` is the canonical condition, and a session can be made from it."""
    run = Scripted()
    result = stage(Fixed([search().Proposal(condition=_in_another_order(*PAIR_OTHER_WAY), reason="r", probability=0.5)]), run=run)
    assert logged(result) == [(PAIR, "run")]
    assert run.ran == [PAIR]


def test_a_condition_parse_could_not_write_is_refused() -> None:
    """Ruling 20."""
    bad = changes().Condition(changes=(changes().Change(surface="tool", tool="a", fault="no_such_fault", call="#1"),))
    run = Scripted()
    result = stage(Fixed([duck(0, condition=bad)]), run=run)
    assert run.ran == []
    assert isinstance(result.stopped, search().SearchError)


def test_the_control_proposed_is_dropped_as_a_repeat() -> None:
    """Ruling 20: the control has run."""
    run = Scripted()
    result = stage(Fixed([proposal("")]), run=run)
    assert run.ran == []
    assert logged(result) == [("", "dropped")]
    assert result.stopped is None


class _Noisy:
    """Whatever it has been told, proposes the same few conditions in a shuffled batch, repeats included, every time."""

    def propose(self, seen: Any, budget: int, *, rng: Any) -> list[Any]:
        texts = [A1, A1T, A2, B1, PAIR] * 2
        rng.shuffle(texts)
        return [proposal(t) for t in texts]


@pytest.mark.parametrize("budget", [0, 1, 2, 3, 4, 7, 9, 40, 400])
@pytest.mark.parametrize("make", ["Screen", "Random", "noisy"])
def test_no_condition_runs_twice_for_any_strategy_over_any_budget(make: str, budget: int) -> None:
    strategy = _Noisy() if make == "noisy" else getattr(search(), make)()
    run = Scripted()
    result = stage(strategy, seen(budget=budget, cases_per_condition=2), run=run)
    assert len(run.ran) == len(set(run.ran))
    assert run.runs <= budget
    assert result.seen.budget == budget - run.runs
    assert by_state(result, "run") == run.ran


def test_no_condition_runs_twice_on_any_of_several_seeds() -> None:
    for seed in range(20):
        run = Scripted()
        stage(_Noisy(), seen(budget=40, cases_per_condition=1), run=run, generator=rng(seed))
        assert len(run.ran) == len(set(run.ran)), seed


def test_a_repeating_strategy_loaded_by_path_is_held_too() -> None:
    run = Scripted()
    start = seen(control={"c1": {"lookup_order": 1}},
                 cat=catalogue(tools={"lookup_order": "read"}))
    result = stage(search().load_strategy("tests.strategies:AlwaysTheSame"), start, name="tests.strategies:AlwaysTheSame", run=run)
    assert run.ran == ["tool:lookup_order#1=error"]
    assert by_state(result, "dropped") == ["tool:lookup_order#1=error"]
    assert result.stopped is None


# ---------------------------------------------------------------------------
# ruling 17  how the stage ends
# ---------------------------------------------------------------------------


def test_an_empty_batch_ends_the_stage_with_budget_left() -> None:
    strategy = Fixed([])
    run = Scripted()
    result = stage(strategy, seen(budget=100), run=run)
    assert len(strategy.shown) == 1
    assert run.ran == [] and result.log == ()
    assert result.stopped is None
    assert result.seen.budget == 100


def test_a_batch_with_nothing_new_ends_the_stage() -> None:
    """A strategy that repeats itself cannot loop for ever. `Fixed` raises if asked sixty times, which would read as a stop."""
    def same(shown: Any) -> list[Any]:
        return [proposal(A1)]

    strategy = Fixed([proposal(A1)], *[same] * 80)
    run = Scripted()
    result = stage(strategy, seen(budget=100), run=run)
    assert len(strategy.shown) == 2
    assert run.ran == [A1]
    assert result.stopped is None
    assert by_state(result, "dropped") == [A1]
    assert len(run.batches) == 1, "a batch with nothing to run is not handed to run"


def test_a_batch_with_something_new_among_repeats_does_not_end_the_stage() -> None:
    run = Scripted()
    strategy = Fixed([proposal(A1)], [proposal(A1), proposal(A2)], [proposal(B1)])
    stage(strategy, seen(budget=100), run=run)
    assert run.ran == [A1, A2, B1]


def test_the_stage_ends_when_the_budget_cannot_pay_for_the_next_condition() -> None:
    """A condition runs whole or not at all: 5 runs left, 2 a condition, so two conditions and one run unspent."""
    texts = [f"tool:a#1={f}" for f in ("error", "timeout")] + ["tool:a#2=error", "tool:b#1=error", "tool:b#1=timeout"]
    start = seen(control={"c1": {"a": 2, "b": 1}, "c2": {"a": 2, "b": 1}}, budget=5, cases_per_condition=2)
    run = Scripted()
    result = stage(Fixed([proposal(t) for t in texts]), start, run=run)
    assert run.ran == texts[:2]
    assert run.runs == 4
    assert result.seen.budget == 1
    assert result.stopped is None
    assert all(len(e.cases) == 2 for batch in run.batches for e in batch)


def test_the_stage_does_not_skip_past_a_condition_it_cannot_pay_for() -> None:
    """Ruling 17: the stage ends at the next condition the budget cannot pay for, so what follows is not run on the change left,
    even when it has few enough cases to fit."""
    run = Scripted()
    result = stage(Fixed([proposal(A1), proposal(A2)]), seen(budget=1, cases_per_condition=2), run=run)
    assert run.ran == []
    assert logged(result) == [(A1, "not run"), (A2, "not run")]
    assert result.seen.budget == 1


def test_what_the_budget_cannot_pay_for_is_logged_not_run() -> None:
    texts = ["tool:a#1=error", "tool:a#1=timeout", "tool:a#2=error", "tool:a#2=timeout"]
    start = seen(control={"c1": {"a": 2}, "c2": {"a": 2}}, budget=4, cases_per_condition=2)
    run = Scripted()
    result = stage(Fixed([proposal(t, reason=f"r{i}", probability=0.5) for i, t in enumerate(texts)]), start, run=run)
    assert logged(result) == [(texts[0], "run"), (texts[1], "run"), (texts[2], "not run"), (texts[3], "not run")]
    assert [e.reason for e in of_state(result.log, "not run")] == ["r2", "r3"]
    assert run.ran == texts[:2]


def test_with_no_budget_nothing_runs() -> None:
    run = Scripted()
    result = stage(Fixed([proposal(A1)]), seen(budget=0), run=run)
    assert run.ran == []
    assert result.seen.budget == 0
    assert not by_state(result, "run")


def test_a_condition_with_too_few_cases_is_still_run_on_those_it_has() -> None:
    """Ruling 17's exception and ruling 11: fewer if fewer fit. One case calls `b`, so `tool:b#1=error` costs one run though a
    condition is four, and one run left can pay for it."""
    start = seen(control={"c1": {"a": 1}, "c2": {"a": 1, "b": 1}}, budget=1, cases_per_condition=4)
    run = Scripted()
    result = stage(Fixed([proposal(B1)]), start, run=run)
    assert run.ran == [B1]
    assert [list(e.cases) for batch in run.batches for e in batch] == [["c2"]]
    assert result.seen.budget == 0


# ---------------------------------------------------------------------------
# ruling 24  what is held back for shrinking
# ---------------------------------------------------------------------------


def test_a_reserve_stops_the_stage_short_by_that_many_runs() -> None:
    start = seen(control={c: {"a": 3, "w": 3} for c in ("c1", "c2", "c3", "c4")}, budget=20, cases_per_condition=2)
    run = Scripted()
    result = stage(search().Screen(), start, run=run, reserve=14)
    assert run.runs == 6
    assert result.stopped is None
    assert len(run.ran) == 3


def test_no_reserve_spends_it_all() -> None:
    start = seen(control={c: {"a": 3, "w": 3} for c in ("c1", "c2", "c3", "c4")}, budget=8, cases_per_condition=2)
    run = Scripted()
    stage(search().Screen(), start, run=run)
    assert run.runs == 8


def test_a_reserve_of_the_whole_budget_or_more_runs_nothing() -> None:
    for reserve in (10, 11, 400):
        run = Scripted()
        stage(search().Screen(), seen(budget=10), run=run, reserve=reserve)
        assert run.ran == [], reserve


def test_a_strategy_is_not_told_it_may_spend_the_reserve() -> None:
    strategy = Fixed([proposal(A1)])
    stage(strategy, seen(budget=20, cases_per_condition=2), reserve=14)
    assert strategy.shown[0][1] <= 6


# ---------------------------------------------------------------------------
# BK6.6  every proposal is logged: strategy, reason, probability
# ---------------------------------------------------------------------------


def test_every_proposal_is_logged_with_its_strategy_its_reason_and_its_probability() -> None:
    result = stage(Fixed([proposal(A1, reason="the first", probability=0.25), proposal(B1, reason="the other", probability=1)],
                         [proposal(A2, reason="later", probability=1 / 3)]), name="module:Name")
    assert [(e.strategy, text_of(e.condition), e.reason, e.probability) for e in result.log] == [
        ("module:Name", A1, "the first", 0.25), ("module:Name", B1, "the other", 1), ("module:Name", A2, "later", 1 / 3)]


def test_a_log_entry_says_the_cases_it_runs_on() -> None:
    run = Scripted()
    result = stage(Fixed([proposal(A1)]), seen(budget=100, cases_per_condition=2), run=run)
    assert tuple(result.log[0].cases) == tuple(run.batches[0][0].cases)
    assert set(result.log[0].cases) == {"c1", "c2"}


def test_a_proposal_that_did_not_run_has_no_cases() -> None:
    result = stage(Fixed([proposal(A1), proposal(A1)]), seen(budget=100))
    assert not of_state(result.log, "dropped")[0].cases


# ---------------------------------------------------------------------------
# BK6.13  the selection
# ---------------------------------------------------------------------------


def test_each_entry_handed_to_run_carries_the_selection_its_record_must_hold() -> None:
    """The proposal that produced a run and the record's `selection` are the same two facts. The stored record's own end-to-end
    test waits on the runs module's names (ruling 29)."""
    run = Scripted()
    stage(Fixed([proposal(A1, probability=0.25), proposal(B1, probability=1)], [proposal(A2, probability=1 / 3)]), name="my.mod:Thing", run=run)
    handed = [e for batch in run.batches for e in batch]
    assert [e.selection for e in handed] == [records().Selection(strategy="my.mod:Thing", probability=p) for p in (0.25, 1, 1 / 3)]
    assert all(isinstance(e.selection, records().Selection) for e in handed)
    assert [e.state for e in handed] == ["run"] * 3


def test_a_selection_goes_into_a_stored_record_as_it_is() -> None:
    """What `run` is handed fits the published shape with no conversion."""
    run = Scripted()
    stage(Fixed([proposal(A1, probability=0.25)]), name="screen", run=run)
    entry = run.batches[0][0]
    r = records()
    record = r.RunRecord(hunt="h", stage="search", arm="h-search", case=entry.cases[0],
                         condition=r.Condition(name=text_of(entry.condition),
                                               changes=(r.Applied(surface="tool", tool="a", fault="error", call="#1", applied=True, applied_call=1),)),
                         failure=r.Failure(kind=None, signals=r.Signals(gave_up=0, retry_storm=0, over_budget=0)),
                         selection=entry.selection, calls=(), judged_by="break", target_outcome=None)
    assert r.RunRecord.from_json(record.to_json()).selection == r.Selection(strategy="screen", probability=0.25)


def test_the_built_ins_selections_are_their_probabilities() -> None:
    """§5.3: `screen` logs 1, whatever its name, and it is the name given that goes into the selection."""
    run = Scripted()
    stage(search().Screen(), seen(budget=8, cases_per_condition=1), name="screen", run=run)
    assert run.ran
    assert all(e.selection == records().Selection(strategy="screen", probability=1) for batch in run.batches for e in batch)


# ---------------------------------------------------------------------------
# BK6.6, ruling 18  a bad proposal is refused before any run of its batch
# ---------------------------------------------------------------------------

BAD_PROBABILITIES = [None, 0, 0.0, -0.5, 1.5, 2, math.inf, -math.inf, math.nan, True, False, "0.5"]


@pytest.mark.parametrize("bad", BAD_PROBABILITIES, ids=repr)
def test_a_returned_probability_outside_the_range_is_refused_before_any_run(bad: Any) -> None:
    run = Scripted()
    result = stage(Fixed([duck(A1, probability=bad)]), run=run)
    assert run.ran == []
    assert isinstance(result.stopped, search().SearchError)
    assert result.seen.budget == 400


@pytest.mark.parametrize("bad", BAD_PROBABILITIES, ids=repr)
def test_a_real_proposal_with_that_probability_put_on_it_later_is_refused_too(bad: Any) -> None:
    """The stage checks again, since a strategy can return anything: `Proposal` refusing when made is not enough."""
    made = proposal(A1)
    object.__setattr__(made, "probability", bad)
    run = Scripted()
    result = stage(Fixed([made]), run=run)
    assert run.ran == []
    assert isinstance(result.stopped, search().SearchError)


@pytest.mark.parametrize("good", [1, 1.0, 0.5, 5e-324], ids=repr)
def test_a_returned_probability_in_the_range_runs(good: float) -> None:
    run = Scripted()
    result = stage(Fixed([proposal(A1, probability=good)]), run=run)
    assert run.ran == [A1]
    assert result.stopped is None


def test_a_proposal_with_no_probability_at_all_is_refused_before_any_run() -> None:
    run = Scripted()
    shaped = duck(A1)
    del shaped.probability
    result = stage(Fixed([shaped]), run=run)
    assert run.ran == []
    assert isinstance(result.stopped, search().SearchError)


def test_a_strategy_loaded_by_path_with_no_probability_is_refused() -> None:
    start = seen(control={"c1": {"lookup_order": 1}}, cat=catalogue(tools={"lookup_order": "read"}))
    run = Scripted()
    result = stage(search().load_strategy("tests.strategies:NoProbability"), start, run=run)
    assert run.ran == []
    assert isinstance(result.stopped, search().SearchError)


@pytest.mark.parametrize("bad", ["", None, 7, "two\nlines"], ids=repr)
def test_a_returned_reason_that_is_not_one_line_is_refused_before_any_run(bad: Any) -> None:
    """Ruling 21."""
    made = proposal(A1)
    object.__setattr__(made, "reason", bad)
    for returned in (duck(A1, reason=bad), made):
        run = Scripted()
        result = stage(Fixed([returned]), run=run)
        assert run.ran == []
        assert isinstance(result.stopped, search().SearchError)


@pytest.mark.parametrize("bad", [A1, None, 7], ids=repr)
def test_a_returned_condition_that_is_not_a_condition_is_refused_before_any_run(bad: Any) -> None:
    """Ruling 1."""
    run = Scripted()
    result = stage(Fixed([duck(0, condition=bad)]), run=run)
    assert run.ran == []
    assert isinstance(result.stopped, search().SearchError)


@pytest.mark.parametrize("bad", [None, 7, "tool:a#1=error", {"condition": A1}], ids=repr)
def test_an_item_that_is_no_kind_of_proposal_is_refused_before_any_run(bad: Any) -> None:
    run = Scripted()
    result = stage(Fixed([bad]), run=run)
    assert run.ran == []
    assert isinstance(result.stopped, search().SearchError)


@pytest.mark.parametrize("make", [lambda: None, lambda: 7, lambda: "tool:a#1=error", lambda: {"condition": A1},
                                  lambda: proposal(A1), lambda: (proposal(A1),), lambda: iter([proposal(A1)])],
                         ids=["none", "number", "text", "mapping", "one proposal", "tuple", "generator"])
def test_a_return_that_is_not_a_list_is_refused_before_any_run(make: Any) -> None:
    """Ruling 18, and §11.3's forcing clause: `propose` returns a list of proposals."""
    run = Scripted()
    result = stage(Fixed(lambda shown: make()), run=run)
    assert run.ran == []
    assert isinstance(result.stopped, search().SearchError)


def test_one_bad_item_refuses_its_whole_batch() -> None:
    run = Scripted()
    result = stage(Fixed([proposal(A1, reason="good"), duck(B1, probability=2.0, reason="bad"), proposal(A2, reason="after")]), run=run)
    assert run.ran == []
    assert isinstance(result.stopped, search().SearchError)
    assert logged(result) == [(A1, "refused"), (B1, "refused"), (A2, "refused")]


def test_the_refused_are_logged_with_their_reason_and_strategy() -> None:
    result = stage(Fixed([proposal(A1, reason="good", probability=0.25), duck(B1, probability=2.0, reason="bad")]), name="mine:Own")
    assert [(e.strategy, e.reason, e.probability) for e in result.log] == [("mine:Own", "good", 0.25), ("mine:Own", "bad", 2.0)]


def test_a_refused_condition_is_not_a_repeat_later_and_cost_nothing() -> None:
    """The stage stopped, so nothing later runs. What was kept is what ran before it, and the budget is what they left."""
    run = Scripted()
    strategy = Fixed([proposal(A1)], [proposal(A2), duck(B1, probability=0)], [proposal("tool:a#1=timeout")])
    result = stage(strategy, seen(budget=100, cases_per_condition=2), run=run)
    assert run.ran == [A1]
    assert len(strategy.shown) == 2
    assert isinstance(result.stopped, search().SearchError)
    assert logged(result) == [(A1, "run"), (A2, "refused"), (B1, "refused")]
    assert result.seen.budget == 98
    assert [text_of(r.condition) for r in result.seen.runs[len(seen().runs):]] == [A1, A1]


def test_a_refusal_is_one_line() -> None:
    result = stage(Fixed([duck(A1, probability="a\nb"), duck(A1, reason="x\ny")]))
    assert isinstance(result.stopped, search().SearchError)
    assert str(result.stopped).strip()
    assert "\n" not in str(result.stopped)


# ---------------------------------------------------------------------------
# ruling 19  a proposal outside what the settings allow
# ---------------------------------------------------------------------------

_LINES: dict[str, Any] = {"a": "read", "w": {"class": "write", "repeatable": True}, "n": {"class": "write", "stand_in": "tests.apply_support_standin:refund"},
                          "silent": "off"}


def _allowing(*, faults: Any = ("error", "lost_reply"), inputs: Any = ("typos",), env: Any = None, max_call: int = 3, control: Any = None) -> Any:
    return seen(control={"c1": {"a": 1, "w": 1}} if control is None else control,
                cat=catalogue(faults, inputs, tools=_LINES, env=env, max_call=max_call))


@pytest.mark.parametrize("text", [
    "tool:a#1=timeout",                 # a fault the user turned off
    "tool:a~0.5=timeout",               # the same, by a rate
    "tool:a#*=timeout",                 # and on every call
    "tool:silent#1=error",              # an `off` tool
    "tool:unknown#1=error",             # a tool with no line
    "tool:a#1=lost_reply",              # on a read, where a session refuses it
    "tool:a~0.5=lost_reply",
    "tool:a#4=error",                   # past max_call
    "input:reordered",                  # an operator the user turned off
    "tool:w#1=error + tool:a#1=timeout",  # one of a pair is enough
    "tool:a#1=error + tool:w#1=timeout",  # whichever comes first
    "model:error#1",                    # a way in that cannot
    "user:repeats@1",
])
def test_a_proposal_outside_what_the_settings_allow_is_refused_before_any_run(text: str) -> None:
    run = Scripted()
    result = stage(Fixed([proposal(text, env={})]), _allowing(), run=run)
    assert run.ran == []
    assert isinstance(result.stopped, search().SearchError)
    assert by_state(result, "refused") == [text_of(condition(text, env={}))]


@pytest.mark.parametrize("text", ["tool:a#1=timeout", "tool:silent#1=error", "tool:a#1=lost_reply", "tool:a#4=error", "input:reordered"])
def test_the_refusal_names_the_change(text: str) -> None:
    """Ruling 19: "naming the change". The rest of the batch's names are not in it."""
    result = stage(Fixed([proposal("tool:w#1=error"), proposal(text)]), _allowing())
    said = str(result.stopped)
    assert text in said
    assert "tool:w#1=error" not in said
    assert "\n" not in said


def test_an_env_value_the_settings_do_not_list_is_refused() -> None:
    run = Scripted()
    result = stage(Fixed([proposal("env:inventory=empty", env=ENV)]), _allowing(env={"inventory": ("full",)}), run=run)
    assert run.ran == []
    assert isinstance(result.stopped, search().SearchError)


@pytest.mark.parametrize("text", [
    "tool:a#1=error",
    "tool:a#2=error",                   # within max_call, never seen by the control: allowed
    "tool:a#3=error",
    "tool:a~0.5=error",                 # a rate stays open to a strategy from outside
    "tool:a#*=error",                   # and so does every call
    "tool:w#1=lost_reply",              # safe to repeat
    "tool:n#1=lost_reply",              # a stand-in
    "tool:w#1=error + tool:a#1=error",
    "input:typos",
])
def test_what_the_settings_allow_is_not_refused(text: str) -> None:
    run = Scripted()
    result = stage(Fixed([proposal(text)]), _allowing(), run=run)
    assert result.stopped is None
    assert by_state(result, "refused") == []


def test_an_env_value_the_settings_list_is_not_refused() -> None:
    result = stage(Fixed([proposal("env:inventory=full", env=ENV)]), _allowing(env={"inventory": ("full",)}))
    assert result.stopped is None
    assert by_state(result, "run") == ["env:inventory=full"]


def test_screen_and_random_are_never_refused_by_their_own_stage() -> None:
    for strategy in (search().Screen(), search().Random()):
        result = stage(strategy, seen(cat=catalogue(inputs=("typos",), env=ENV), budget=4000))
        assert result.stopped is None
        assert not by_state(result, "refused")


# ---------------------------------------------------------------------------
# §11.3 invariant 7, ruling 18  a strategy's exception
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wrong", [ValueError("x"), ZeroDivisionError("y"), KeyError("z"), SystemExit(3), RuntimeError("r")],
                         ids=["value", "zero", "key", "exit", "runtime"])
def test_a_strategys_exception_is_an_instrument_error_that_stops_the_stage_with_what_was_kept(wrong: BaseException) -> None:
    run = Scripted()
    strategy = Fixed([proposal(A1)], wrong, [proposal(A2)])
    result = stage(strategy, seen(budget=100, cases_per_condition=2), run=run)
    assert isinstance(result.stopped, changes().InstrumentError)
    assert run.ran == [A1]
    assert logged(result) == [(A1, "run")]
    assert result.seen.budget == 98
    assert len(strategy.shown) == 2


def test_an_exception_on_the_first_ask_stops_with_nothing_run() -> None:
    run = Scripted()
    result = stage(Fixed(ValueError("x")), run=run)
    assert isinstance(result.stopped, changes().InstrumentError)
    assert run.ran == [] and result.log == ()


def test_a_strategy_with_a_mistake_loaded_by_path_stops_the_stage() -> None:
    run = Scripted()
    result = stage(search().load_strategy("tests.strategies:Raises"), run=run)
    assert isinstance(result.stopped, changes().InstrumentError)
    assert run.ran == []


def test_ctrl_c_in_a_strategy_passes_through() -> None:
    with pytest.raises(KeyboardInterrupt):
        stage(Fixed(KeyboardInterrupt()))


def test_a_stage_that_ended_of_itself_has_no_stop() -> None:
    assert stage(Fixed([proposal(A1)])).stopped is None


# ---------------------------------------------------------------------------
# BK6.6, ruling 5  the file, and replaying
# ---------------------------------------------------------------------------


def _mixed(generator_seed: int = 3) -> Fixed:
    return Fixed([proposal(A1, reason="one", probability=0.25), proposal(A1, reason="again", probability=0.5)],
                 [proposal(A2, reason="two", probability=1), proposal(B1, reason="three", probability=1 / 3)])


def test_the_file_has_one_json_line_per_proposal_the_condition_by_its_name(tmp_path: Path) -> None:
    path = tmp_path / "proposals.jsonl"
    result = stage(_mixed(), name="mine:Own", log=path)
    lines = path.read_text().splitlines()
    assert len(lines) == len(result.log) == 4
    decoded = [json.loads(line) for line in lines]
    assert [d["condition"] for d in decoded] == [A1, A1, A2, B1]
    assert [d["strategy"] for d in decoded] == ["mine:Own"] * 4
    assert [d["reason"] for d in decoded] == ["one", "again", "two", "three"]
    assert [d["probability"] for d in decoded] == [0.25, 0.5, 1, 1 / 3]
    assert [d["state"] for d in decoded] == ["run", "dropped", "run", "run"]


def test_the_file_reads_back_equal_to_the_stage_log(tmp_path: Path) -> None:
    path = tmp_path / "proposals.jsonl"
    result = stage(_mixed(), log=path)
    assert tuple(search().read_log(path)) == tuple(result.log)


def test_reading_back_gives_entries_that_still_carry_their_selection(tmp_path: Path) -> None:
    path = tmp_path / "proposals.jsonl"
    stage(Fixed([proposal(A1, probability=0.25)]), name="mine:Own", log=path)
    assert search().read_log(path)[0].selection == records().Selection(strategy="mine:Own", probability=0.25)


def test_an_env_condition_reads_back(tmp_path: Path) -> None:
    """A name holding `env:` parses only against the settings' `[vary.env]`, and `read_log` is given the path alone."""
    path = tmp_path / "proposals.jsonl"
    start = _allowing(env={"inventory": ("full",)})
    result = stage(Fixed([proposal("env:inventory=full", env=ENV)]), start, log=path)
    assert tuple(search().read_log(path)) == tuple(result.log)


def test_every_entry_is_on_disk_before_its_run(tmp_path: Path) -> None:
    """It cannot be backfilled: a crash in a run leaves the proposal that caused it in the file."""
    path = tmp_path / "proposals.jsonl"
    on_disk_at_run: list[list[str]] = []

    def during(entries: Any) -> None:
        on_disk_at_run.append([text_of(e.condition) for e in search().read_log(path)])

    stage(Fixed([proposal(A1)], [proposal(A1), proposal(A2)]), run=Scripted(during=during), log=path)
    assert on_disk_at_run == [[A1], [A1, A1, A2]]


def test_a_dropped_or_refused_entry_is_on_disk_when_the_stage_stops(tmp_path: Path) -> None:
    path = tmp_path / "proposals.jsonl"
    stage(Fixed([proposal(A1), duck(B1, probability=2.0)]), log=path)
    assert [(text_of(e.condition), e.state) for e in search().read_log(path)] == [(A1, "refused"), (B1, "refused")]


@pytest.mark.parametrize("bad", [None, "0.5", math.nan, math.inf, 2.0, True], ids=repr)
def test_a_refused_probability_of_any_kind_does_not_break_the_file(tmp_path: Path, bad: Any) -> None:
    """The strangest thing a strategy hands back has to be readable afterwards, or the hunt's record of why it stopped is lost."""
    path = tmp_path / "proposals.jsonl"
    result = stage(Fixed([proposal(A2), duck(A1, probability=bad)]), log=path)
    assert isinstance(result.stopped, search().SearchError)
    read = search().read_log(path)
    assert [(text_of(e.condition), e.state) for e in read] == [(A2, "refused"), (A1, "refused")]
    for line in path.read_text().splitlines():
        json.loads(line, parse_constant=_no_constant)


def _no_constant(word: str) -> Any:
    raise AssertionError(f"{word} is not JSON")


def test_with_no_log_named_no_file_is_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert stage(Fixed([proposal(A1)])).log
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("make", ["Screen", "Random"])
def test_the_same_strategy_seed_and_answers_give_an_identical_log(make: str, tmp_path: Path) -> None:
    """BK6.6: the log replays to the same sequence, in memory and in the file, byte for byte."""
    first, second = tmp_path / "1.jsonl", tmp_path / "2.jsonl"
    start = seen(control={"c1": {"a": 2, "b": 1, "w": 1}, "c2": {"a": 2, "b": 1, "w": 1}}, budget=60, cases_per_condition=2)
    one = stage(getattr(search(), make)(), start, generator=random.Random(11), log=first)
    two = stage(getattr(search(), make)(), start, generator=random.Random(11), log=second)
    assert one.log == two.log
    assert first.read_bytes() == second.read_bytes()
    assert len(one.log) > 3


def test_a_learning_strategy_replays_too_given_the_same_answers(tmp_path: Path) -> None:
    def answers(text: str, case: str) -> str:
        return "failed" if "tool:a#" in text else "ok"

    logs = []
    for i in range(2):
        path = tmp_path / f"{i}.jsonl"
        start = seen(budget=40, cases_per_condition=1, cat=catalogue(tools={"a": "read", "b": "read"}))
        logs.append((stage(search().load_strategy("tests.strategies:FollowsFailures"), start, name="tests.strategies:FollowsFailures",
                           run=Scripted(answers), log=path).log, path.read_bytes()))
    assert logs[0] == logs[1]
    assert logs[0][0]


def test_another_search_seed_gives_random_another_log() -> None:
    """The control for the test above: the seed is what the log follows."""
    start = seen(budget=60, cases_per_condition=2)
    assert stage(search().Random(), start, generator=random.Random(1)).log != stage(search().Random(), start, generator=random.Random(2)).log


# ---------------------------------------------------------------------------
# the whole door: a strategy loaded by path runs a stage on a real agent (BK6.11 is in `test_search_load.py`)
# ---------------------------------------------------------------------------


def test_a_learner_written_only_against_seen_runs_a_stage_and_learns() -> None:
    """§11.3 invariant 3: `Seen` is sufficient for a strategy that learns within the hunt. This one looks at outcomes: with
    every outcome ok it goes across the tools, and after a failure it stays on the tool that failed."""
    start = seen(control={"c1": {"a": 1, "b": 1}}, budget=40, cases_per_condition=1,
                 cat=catalogue(("error", "timeout"), tools={"a": "read", "b": "read"}))

    def order(run: Scripted) -> Any:
        return stage(search().load_strategy("tests.strategies:FollowsFailures"), start, run=run)

    never_fails = order(Scripted())
    assert [t for t, _ in logged(never_fails)] == ["tool:a#1=error", "tool:b#1=error", "tool:a#1=timeout", "tool:b#1=timeout"]
    fails_at_once = order(Scripted(lambda text, case: "failed" if text == "tool:a#1=error" else "ok"))
    assert [t for t, _ in logged(fails_at_once)] == ["tool:a#1=error", "tool:a#1=timeout", "tool:b#1=error", "tool:b#1=timeout"]
    assert [e.probability for e in fails_at_once.log] == [1.0, 0.5, 1 / 3, 0.25]
