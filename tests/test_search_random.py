"""`random` (spec §5.3).

- BK6.5  `random` is uniform over the declared space within a stated band, and its draws come from the search seed only.
- BK6.6  It logs the base distribution's probability of the condition.
- Ruling 15 (the space and its probability) and ruling 16 (a pair that meets on every call), `evidence/bk6/open-points.md`.

The band, stated: over `DRAWS` first proposals, each condition's count is within five standard deviations of the mean of a
fair draw. The space has eleven conditions or so, so a fair `random` falls outside it about once in a hundred thousand runs of
this test, and the seeds are fixed, so a build that passes keeps passing.
"""

from __future__ import annotations

import itertools
import math
import random
from typing import Any

import pytest

from tests.search_support import (
    ENV,
    INPUTS,
    Scripted,
    catalogue,
    condition,
    control_rows,
    logged,
    proposal,
    rng,
    row,
    search,
    seen,
    stage,
    text_of,
)

DRAWS = 6000

SMALL_CONTROL = {"c1": {"a": 2, "b": 1}}
# a#1, a#2 and b#1 by two faults, and one operator: seven singles.
SMALL_SINGLES = {"tool:a#1=error", "tool:a#1=timeout", "tool:a#2=error", "tool:a#2=timeout", "tool:b#1=error", "tool:b#1=timeout", "input:typos"}


def _small(**over: Any) -> Any:
    fields: dict[str, Any] = {"control": SMALL_CONTROL, "cat": catalogue(("error", "timeout"), ("typos",)), "budget": 40000, "cases_per_condition": 1}
    return seen(**{**fields, **over})


def _canonical(*texts: str) -> str:
    return text_of(condition(" + ".join(texts)))


def _meets(first: str, second: str) -> bool:
    """Ruling 16: two changes on one tool at one call number."""
    return first.startswith("tool:") and second.startswith("tool:") and first.split("=")[0] == second.split("=")[0]


def small_pairs() -> set[str]:
    """By hand. Seven singles make 21 pairs, and three of them are one tool at one call: a#1, a#2 and b#1. So 18, and 25 in all."""
    return {_canonical(x, y) for x, y in itertools.combinations(sorted(SMALL_SINGLES), 2) if not _meets(x, y)}


def _drain(start: Any = None, *, seed: int = 1) -> list[str]:
    result = stage(search().Random(), _small() if start is None else start, generator=rng(seed))
    return [t for t, state in logged(result) if state == "run"]


# ---------------------------------------------------------------------------
# ruling 15  the space
# ---------------------------------------------------------------------------


def test_given_budget_it_proposes_every_single_and_pair_of_the_space_exactly_once() -> None:
    drawn = _drain()
    assert len(drawn) == len(set(drawn))
    assert set(drawn) == SMALL_SINGLES | small_pairs()


def test_both_singles_and_pairs_turn_up_early() -> None:
    """One set, one uniform draw: not all singles and then the pairs, nor the reverse."""
    drawn = _drain()
    first = drawn[:12]
    assert any(" + " in t for t in first)
    assert any(" + " not in t for t in first)


def test_a_pair_across_two_calls_of_one_tool_is_in_the_space() -> None:
    assert "tool:a#1=error + tool:a#2=timeout" in small_pairs()
    assert "tool:a#1=error + tool:a#2=timeout" in _drain()


def test_a_pair_of_two_operators_is_in_the_space() -> None:
    drawn = _drain(_small(cat=catalogue(("error",), ("typos", "padded"))))
    assert "input:padded + input:typos" in drawn


def test_a_pair_of_a_tool_and_an_operator_is_in_the_space() -> None:
    assert _canonical("tool:a#1=error", "input:typos") in _drain()


def test_it_proposes_nothing_of_three_changes_or_more() -> None:
    assert all(t.count(" + ") <= 1 for t in _drain())


# ---------------------------------------------------------------------------
# ruling 16  a pair that meets on every call
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pair", ["tool:a#1=error + tool:a#1=timeout", "tool:a#2=error + tool:a#2=timeout", "tool:b#1=error + tool:b#1=timeout"])
def test_a_pair_on_one_call_of_one_tool_is_skipped(pair: str) -> None:
    """`tool:a#1=error + tool:a#1=timeout` is `tool:a#1=error` in disguise, by BK2.12."""
    for seed in range(5):
        assert pair not in _drain(seed=seed)


def test_two_values_of_one_setting_are_skipped_and_two_settings_are_not() -> None:
    cat = catalogue((), env=ENV)
    drawn = _drain(_small(cat=cat))
    assert "env:inventory=empty + env:inventory=full" not in drawn
    assert "env:inventory=empty + env:region=us" in drawn
    assert "env:inventory=full + env:region=us" in drawn
    assert len(drawn) == 3 + 2


def test_parse_still_accepts_the_pair_it_skips() -> None:
    """Ruling 16 changes what `random` draws, not what a user may type. And a strategy from outside may still propose one."""
    pair = "tool:a#1=error + tool:a#1=timeout"
    result = stage(_FixedOnce(proposal(pair)), _small())
    assert logged(result) == [(pair, "run")]


class _FixedOnce:
    def __init__(self, one: Any) -> None:
        self.one = one

    def propose(self, seen: Any, budget: int, *, rng: Any) -> list[Any]:
        return [] if seen.proposals else [self.one]


# ---------------------------------------------------------------------------
# BK6.5  uniform within the stated band
# ---------------------------------------------------------------------------


def _first_draws(position: int = 0) -> dict[str, int]:
    """Over `DRAWS` search seeds, how often each condition comes at a given place in the draw."""
    counts: dict[str, int] = {}
    start = _small()
    for seed in range(DRAWS):
        drawn = text_of(search().Random().propose(start, 40000, rng=random.Random(seed))[position].condition)
        counts[drawn] = counts.get(drawn, 0) + 1
    return counts


def _in_band(count: int, *, n: int, p: float) -> bool:
    mean = n * p
    return abs(count - mean) <= 5 * math.sqrt(n * p * (1 - p))


def test_the_first_draw_is_uniform_within_the_band() -> None:
    counts = _first_draws()
    space = SMALL_SINGLES | small_pairs()
    assert set(counts) == space
    outside = {t: c for t, c in counts.items() if not _in_band(c, n=DRAWS, p=1 / len(space))}
    assert outside == {}, outside


def test_singles_and_pairs_together_have_their_share_of_the_space() -> None:
    """A draw that picked singles and pairs half and half would pass per condition on a space this small only by accident:
    here it fails on the singles' share, 7 in 25."""
    counts = _first_draws()
    n_singles = sum(c for t, c in counts.items() if " + " not in t)
    assert _in_band(n_singles, n=DRAWS, p=7 / 25), n_singles


def test_a_later_draw_is_uniform_too() -> None:
    """Skipping what has been proposed does not bend what comes next, on the second place."""
    counts: dict[str, int] = {}
    start = _small()
    n = 0
    for seed in range(DRAWS):
        proposed = search().Random().propose(start, 40000, rng=random.Random(seed))
        if len(proposed) < 2:
            pytest.skip("this build proposes one at a time; the stage test below holds the same")
        counts[text_of(proposed[1].condition)] = counts.get(text_of(proposed[1].condition), 0) + 1
        n += 1
    space = SMALL_SINGLES | small_pairs()
    assert {t: c for t, c in counts.items() if not _in_band(c, n=n, p=1 / len(space))} == {}


def test_over_a_stage_the_second_condition_run_is_uniform_too() -> None:
    """The same, through a stage: however a build batches its draws."""
    counts: dict[str, int] = {}
    n = 1500
    start = _small(budget=2)
    for seed in range(n):
        drawn = [t for t, state in logged(stage(search().Random(), start, generator=random.Random(seed))) if state == "run"]
        counts[drawn[1]] = counts.get(drawn[1], 0) + 1
    space = SMALL_SINGLES | small_pairs()
    assert {t: c for t, c in counts.items() if not _in_band(c, n=n, p=1 / len(space))} == {}


def test_the_band_fails_a_draw_that_is_not_uniform() -> None:
    """The control: the band can tell. A draw that favours the first of a sorted space by half again is outside it."""
    space = sorted(SMALL_SINGLES | small_pairs())
    generator = random.Random(1)
    counts = dict.fromkeys(space, 0)
    weights = [1.5] + [1.0] * (len(space) - 1)
    for t in generator.choices(space, weights=weights, k=DRAWS):
        counts[t] += 1
    assert not all(_in_band(c, n=DRAWS, p=1 / len(space)) for c in counts.values())


# ---------------------------------------------------------------------------
# BK6.6  the probability it logs
# ---------------------------------------------------------------------------


def test_it_logs_one_over_the_size_of_the_space() -> None:
    proposed = search().Random().propose(_small(), 40000, rng=rng())
    assert proposed
    assert all(p.probability == pytest.approx(1 / 25, abs=1e-15) for p in proposed)


@pytest.mark.parametrize("cat, control, n", [
    (lambda: catalogue(("error",)), {"c1": {"a": 1}}, 1),
    (lambda: catalogue(("error", "timeout")), {"c1": {"a": 1}}, 2),                 # the pair meets, so no pair
    (lambda: catalogue(("error",), ("typos",)), {"c1": {"a": 1}}, 2 + 1),
    (lambda: catalogue(("error",)), {"c1": {"a": 2, "b": 1}}, 3 + 3),
    (lambda: catalogue(("error",), max_call=1), {"c1": {"a": 2, "b": 1}}, 2 + 1),
], ids=["one single", "two that meet", "single and operator", "three singles", "held to the first call"])
def test_the_size_of_the_space_is_what_was_worked_by_hand(cat: Any, control: Any, n: int) -> None:
    start = seen(control=control, cat=cat(), budget=4000, cases_per_condition=1)
    result = stage(search().Random(), start)
    assert all(e.probability == pytest.approx(1 / n, abs=1e-15) for e in result.log)
    assert len(result.log) == n


def test_the_probability_is_the_base_distributions_on_every_batch() -> None:
    """Ruling 15: it skips what is proposed, and p stays 1/N. Not 1 over what is left."""
    result = stage(search().Random(), _small(budget=40000))
    assert len(result.log) == 25
    assert all(e.probability == pytest.approx(1 / 25, abs=1e-15) for e in result.log)


def test_a_set_aside_case_narrows_the_space_and_so_the_probability() -> None:
    """Ruling 12."""
    start = seen(control={"c1": {"a": 1}, "gone": {"b": 1}}, cat=catalogue(("error",)), set_aside=("gone",), budget=4000, cases_per_condition=1)
    assert [(e.probability, text_of(e.condition)) for e in stage(search().Random(), start).log] == [(1.0, "tool:a#1=error")]


def test_every_proposal_has_a_reason_of_one_line() -> None:
    proposed = search().Random().propose(_small(), 40000, rng=rng())
    assert all(isinstance(p.reason, str) and p.reason.strip() and "\n" not in p.reason for p in proposed)


# ---------------------------------------------------------------------------
# ruling 15  it skips what seen.proposals holds
# ---------------------------------------------------------------------------


def test_it_skips_what_has_been_proposed() -> None:
    half = stage(search().Random(), _small(budget=10), generator=rng(4))
    already = {t for t, _ in logged(half)}
    assert len(already) == 10
    later = search().Random().propose(half.seen, 40000, rng=rng(5))
    assert later
    assert not ({text_of(p.condition) for p in later} & already)
    assert all(p.probability == pytest.approx(1 / 25, abs=1e-15) for p in later), "1/N, and not 1 over what is left"


def test_a_small_space_runs_out_and_the_stage_ends_with_budget_left() -> None:
    start = seen(control={"c1": {"a": 1}}, cat=catalogue(("error",)), budget=400, cases_per_condition=1)
    run = Scripted()
    result = stage(search().Random(), start, run=run)
    assert run.ran == ["tool:a#1=error"]
    assert result.seen.budget == 399
    assert result.stopped is None


def test_nothing_left_is_an_empty_list() -> None:
    drained = stage(search().Random(), _small())
    assert search().Random().propose(drained.seen, 40000, rng=rng()) == []


def test_no_budget_ends_early_because_of_a_drop() -> None:
    """Because it does not repeat itself, the stage does not end early on a batch of repeats (ruling 17): the whole budget is
    spent before the space is, on any seed."""
    for seed in range(10):
        start = _small(budget=20)
        run = Scripted()
        result = stage(search().Random(), start, run=run, generator=rng(seed))
        assert run.runs == 20, seed
        assert not [t for t, s in logged(result) if s == "dropped"], seed


# ---------------------------------------------------------------------------
# BK6.5, §11.3 invariant 5  its draws come from the search seed only
# ---------------------------------------------------------------------------


def _as_shown(**over: Any) -> Any:
    return seen(runs=control_rows(SMALL_CONTROL, **over), control=SMALL_CONTROL, cat=catalogue(("error", "timeout"), ("typos",)), budget=40000, cases_per_condition=1)


def _proposed(start: Any, seed: int = 9) -> list[str]:
    return [text_of(p.condition) for p in search().Random().propose(start, 40000, rng=random.Random(seed))]


def test_changing_the_run_seeds_does_not_change_its_proposals() -> None:
    assert _proposed(_as_shown(first_seed=1)) == _proposed(_as_shown(first_seed=999_999))


def test_changing_the_outcomes_does_not_change_its_proposals() -> None:
    """§5.3's table: it does not look at outcomes."""
    assert _proposed(_as_shown()) == _proposed(_as_shown(outcome=lambda _c, _i: "failed"))


def test_changing_the_outcomes_under_a_condition_does_not_change_its_proposals() -> None:
    """Rows under a condition that failed, against the same rows ok: a `random` that shied away from a tool that failed is learning."""
    def shown(outcome: str) -> Any:
        rows = [*control_rows(SMALL_CONTROL), row("tool:a#1=error", "c1", outcome), row("tool:b#1=timeout", "c1", outcome)]
        return seen(control=SMALL_CONTROL, runs=rows, cat=catalogue(("error", "timeout"), ("typos",)), budget=40000, cases_per_condition=1)

    assert _proposed(shown("ok")) == _proposed(shown("failed"))


def test_a_run_of_some_other_condition_changes_nothing() -> None:
    """Only what has been proposed is skipped: a row with no proposal is not read as one."""
    plain = _as_shown()
    more = seen(control=SMALL_CONTROL, runs=[*control_rows(SMALL_CONTROL), row("tool:z#1=error", "c1", "failed")], cat=catalogue(("error", "timeout"), ("typos",)), budget=40000, cases_per_condition=1)
    assert _proposed(plain) == _proposed(more)


def test_a_whole_stage_is_the_same_whatever_seeds_the_runs_carry() -> None:
    start = _small(budget=12)
    first = stage(search().Random(), start, generator=rng(2), run=Scripted(first_seed=1))
    second = stage(search().Random(), start, generator=rng(2), run=Scripted(first_seed=10_000_000))
    assert first.log == second.log


def test_the_global_generator_is_neither_read_nor_moved() -> None:
    start = _small()
    random.seed(1)
    state = random.getstate()
    first = _proposed(start)
    assert random.getstate() == state
    random.seed(2)
    assert _proposed(start) == first


def test_another_search_seed_is_another_draw() -> None:
    start = _small()
    assert len({tuple(_proposed(start, seed)) for seed in range(8)}) > 1


def test_the_generator_it_is_given_is_the_one_it_draws_from() -> None:
    generator = rng(3)
    state = generator.getstate()
    search().Random().propose(_small(), 40000, rng=generator)
    assert generator.getstate() != state


def test_it_gives_the_same_answer_for_the_same_seed_in_another_process() -> None:
    """A hash of a string differs between processes unless the order is fixed: a space built from a set, drawn by position,
    would replay differently in the next process."""
    from tests.conftest import run_python

    code = (
        "import random\n"
        "from poisson_break import changes, interfaces, search\n"
        "cat = search.allowed(vary={'tools': ['error', 'timeout'], 'inputs': ['typos', 'padded'], 'max_call': 3},\n"
        "                     tools={'a': 'read', 'b': 'read', 'c': 'read'},\n"
        "                     capabilities=interfaces.Capabilities(tool_calls=True, model_calls=False, conversation=False))\n"
        "start = search.Seen(control={'c1': {'a': 2, 'b': 1, 'c': 1}}, runs=(), proposals=(), budget=4000, catalogue=cat,\n"
        "                    set_aside=(), cases_per_condition=1)\n"
        "for strategy in (search.Random(), search.Screen()):\n"
        "    print([changes.name(p.condition) for p in strategy.propose(start, 4000, rng=random.Random(5))])\n")
    outs = {run_python(code).stdout for _ in range(4)}
    assert len(outs) == 1
    assert "tool:a#1=error" in next(iter(outs))


def test_inputs_defaulting_to_none_of_them_is_a_tool_only_space() -> None:
    start = seen(control={"c1": {"a": 1, "b": 1}}, cat=catalogue(("error",), ()), budget=400, cases_per_condition=1)
    assert set(_drain(start)) == {"tool:a#1=error", "tool:b#1=error", "tool:a#1=error + tool:b#1=error"}


def test_every_input_operator_listed_counts() -> None:
    start = seen(control={"c1": {"a": 1}}, cat=catalogue(("error",), INPUTS), budget=400, cases_per_condition=1)
    assert set(_drain(start)) == {"tool:a#1=error", "input:typos", "input:reordered", "input:reordered + input:typos",
                                  "input:typos + tool:a#1=error", "input:reordered + tool:a#1=error"}
