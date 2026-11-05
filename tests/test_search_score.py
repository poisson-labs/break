"""BK6.7: the score (spec §5.3, ruling 8 of `evidence/bk6/open-points.md`), and `cases_for`, which decides what a score is over
(§5.3, ruling 11).

The score is the failure share on the condition's cases less the control's failure share on the same cases. Every figure is
worked by hand in the test. A condition scored on a case set aside is refused: a refusal is its type and a control beside it.
"""

from __future__ import annotations

import random
from typing import Any

import pytest

from tests.search_support import catalogue, condition, rng, row, search, seen, stage, text_of

X = "tool:a#1=error"
Y = "tool:b#1=timeout"


def _score(runs: list[Any], *, set_aside: tuple[str, ...] = (), text: str = X) -> float:
    return search().score(seen(runs=runs, set_aside=set_aside), condition(text))


def _rows(text: str, case: str, failed: int, total: int) -> list[Any]:
    return [row(text, case, "failed" if i < failed else "ok", seed=i) for i in range(total)]


def test_the_share_less_the_controls_share_on_the_same_cases() -> None:
    """3 of 4 under the condition, 2 of 10 under the control on those two cases."""
    runs = _rows("", "c1", 1, 5) + _rows("", "c2", 1, 5) + _rows(X, "c1", 2, 2) + _rows(X, "c2", 1, 2)
    assert _score(runs) == pytest.approx(3 / 4 - 2 / 10)


def test_only_the_condition_s_own_cases_count_on_the_controls_side() -> None:
    """c3's control rows are full of failures, and it is not a case this condition ran on."""
    runs = _rows("", "c1", 1, 5) + _rows("", "c3", 4, 5) + _rows(X, "c1", 2, 2)
    assert _score(runs) == pytest.approx(1 - 1 / 5)


def test_only_the_condition_s_own_runs_count_on_its_side() -> None:
    runs = _rows("", "c1", 0, 5) + _rows(X, "c1", 1, 4) + _rows(Y, "c1", 4, 4) + _rows(f"{X} + {Y}", "c1", 4, 4)
    assert _score(runs) == pytest.approx(1 / 4)


def test_each_side_is_pooled_so_a_case_with_more_runs_weighs_more() -> None:
    """Ruling 8. Under the condition 3 of 3 on c1 and 0 of 1 on c2: pooled 3/4, not the mean of shares, 1/2. Under the control
    1 of 2 on c1 and 0 of 6 on c2: pooled 1/8, not 1/4."""
    runs = _rows("", "c1", 1, 2) + _rows("", "c2", 0, 6) + _rows(X, "c1", 3, 3) + _rows(X, "c2", 0, 1)
    assert _score(runs) == pytest.approx(3 / 4 - 1 / 8)


def test_a_condition_can_score_below_zero() -> None:
    """A candidate that fails less than the control. Which is what BK7.9 goes on to say."""
    assert _score(_rows("", "c1", 4, 5) + _rows(X, "c1", 0, 4)) == pytest.approx(-4 / 5)


def test_a_condition_with_no_more_failures_than_the_control_scores_zero() -> None:
    assert _score(_rows("", "c1", 1, 4) + _rows(X, "c1", 1, 4)) == 0


def test_a_run_not_counted_is_left_out_on_both_sides() -> None:
    """A row that says nothing about the agent: 1 of 2 counted, not 1 of 3; 1 of 4 counted, not 1 of 5."""
    runs = (_rows("", "c1", 1, 4) + [row("", "c1", "not counted")]
            + _rows(X, "c1", 1, 2) + [row(X, "c1", "not counted")])
    assert _score(runs) == pytest.approx(1 / 2 - 1 / 4)


def test_the_score_does_not_care_what_the_seeds_were_or_the_order_of_the_rows() -> None:
    runs = _rows("", "c1", 1, 5) + _rows(X, "c1", 2, 4)
    assert _score(runs) == _score(list(reversed(runs)))


def test_it_reads_a_stage_s_own_seen() -> None:
    """What a stage gives back is what a score is taken on."""
    from tests.search_support import Fixed, Scripted, proposal

    start = seen(runs=_rows("", "c1", 1, 5) + _rows("", "c2", 1, 5), budget=40, cases_per_condition=2)
    result = stage(Fixed([proposal(X)]), start, run=Scripted(lambda text, case: "failed" if case == "c1" else "ok"))
    assert search().score(result.seen, condition(X)) == pytest.approx(1 / 2 - 2 / 10)


# ---------------------------------------------------------------------------
# what is refused
# ---------------------------------------------------------------------------


def test_a_condition_scored_on_a_case_set_aside_is_refused() -> None:
    runs = _rows("", "c1", 5, 5) + _rows("", "c2", 1, 5) + _rows(X, "c1", 2, 2) + _rows(X, "c2", 2, 2)
    assert _score(runs) == pytest.approx(1 - 6 / 10)
    with pytest.raises(search().SearchError):
        _score(runs, set_aside=("c1",))


def test_a_case_set_aside_that_the_condition_did_not_run_on_does_not_matter() -> None:
    """The control: `c9` is set aside and has no row under this condition, so nothing is wrong."""
    runs = _rows("", "c1", 1, 5) + _rows("", "c9", 5, 5) + _rows(X, "c1", 2, 2)
    assert _score(runs, set_aside=("c9",)) == pytest.approx(1 - 1 / 5)


def test_a_condition_never_run_is_refused() -> None:
    with pytest.raises(search().SearchError):
        _score(_rows("", "c1", 1, 5))


def test_a_condition_whose_every_run_went_uncounted_is_refused() -> None:
    with pytest.raises(search().SearchError):
        _score(_rows("", "c1", 1, 5) + [row(X, "c1", "not counted"), row(X, "c1", "not counted")])


# ---------------------------------------------------------------------------
# ruling 11  which cases a condition runs on
# ---------------------------------------------------------------------------

CASES = {"c1": {"a": 3, "b": 1}, "c2": {"a": 1}, "c3": {"a": 2, "b": 2}, "c4": {"b": 1}, "c5": {"a": 1, "b": 1}}


def _for(text: str, *, generator: Any = None, c: int = 4, set_aside: tuple[str, ...] = ()) -> tuple[str, ...]:
    start = seen(control=CASES, cases_per_condition=c, set_aside=set_aside)
    return tuple(search().cases_for(start, condition(text), rng=rng() if generator is None else generator))


def _over_seeds(text: str, **over: Any) -> set[str]:
    return {case for seed in range(200) for case in _for(text, generator=random.Random(seed), **over)}


@pytest.mark.parametrize("text, can_land", [
    ("tool:a#1=error", {"c1", "c2", "c3", "c5"}),                               # calls a at all
    ("tool:a#2=error", {"c1", "c3"}),                                           # calls a twice
    ("tool:a#3=error", {"c1"}),
    ("tool:b#2=error", {"c3"}),
    ("tool:a#1=error + tool:b#1=error", {"c1", "c3", "c5"}),                    # every tool change can land
    ("tool:a#2=error + tool:b#2=error", {"c3"}),
    ("input:typos", {"c1", "c2", "c3", "c4", "c5"}),                            # no tool: all of them
    ("tool:a#2=error + input:typos", {"c1", "c3"}),
])
def test_it_picks_only_cases_the_map_says_the_condition_can_land_on(text: str, can_land: set[str]) -> None:
    assert _over_seeds(text, c=4) == can_land


def test_a_schedule_or_a_rate_lands_on_any_case_that_calls_the_tool() -> None:
    for text in ("tool:a#*=error", "tool:a~0.5=error"):
        assert _over_seeds(text, c=2) == {"c1", "c2", "c3", "c5"}


def test_a_range_lands_where_its_first_call_can() -> None:
    assert _over_seeds("tool:a#2-3=error", c=4) == {"c1", "c3"}


def test_a_case_set_aside_is_never_picked() -> None:
    assert _over_seeds("tool:a#1=error", c=4, set_aside=("c1",)) == {"c2", "c3", "c5"}
    assert "c3" not in _over_seeds("tool:a#2=error", c=4, set_aside=("c3",))


@pytest.mark.parametrize("c, n", [(1, 1), (2, 2), (4, 4), (5, 4), (9, 4)])
def test_it_picks_as_many_as_the_stage_asks_for_or_as_fit(c: int, n: int) -> None:
    picked = _for("tool:a#1=error", c=c)
    assert len(picked) == n
    assert len(set(picked)) == n


def test_it_draws_over_all_that_can_land_so_a_search_gets_past_the_first_cases() -> None:
    """The other answer ruling 11 turned down: first in file order never searches past the first four."""
    assert _over_seeds("tool:a#1=error", c=1) == {"c1", "c2", "c3", "c5"}
    assert _over_seeds("input:typos", c=2) == {"c1", "c2", "c3", "c4", "c5"}


def test_it_draws_each_of_them_about_as_often() -> None:
    """Nothing in §5.3 favours a case. The band is generous: each of four at a count of 1 in 2000 draws."""
    counts = dict.fromkeys(("c1", "c2", "c3", "c5"), 0)
    for seed in range(2000):
        counts[_for("tool:a#1=error", generator=random.Random(seed), c=1)[0]] += 1
    assert all(350 <= n <= 650 for n in counts.values()), counts


def test_it_draws_only_with_the_generator_it_is_given() -> None:
    start = seen(control=CASES, cases_per_condition=2)
    random.seed(1)
    state = random.getstate()
    first = tuple(search().cases_for(start, condition("input:typos"), rng=random.Random(7)))
    assert random.getstate() == state
    random.seed(2)
    assert tuple(search().cases_for(start, condition("input:typos"), rng=random.Random(7))) == first


def test_the_same_seed_gives_the_same_cases() -> None:
    assert _for("tool:a#1=error", generator=random.Random(3), c=2) == _for("tool:a#1=error", generator=random.Random(3), c=2)


def test_the_stage_runs_a_condition_on_cases_that_can_land() -> None:
    from tests.search_support import Fixed, Scripted, proposal

    start = seen(control=CASES, budget=100, cases_per_condition=2, cat=catalogue(inputs=("typos",)))
    run = Scripted()
    stage(Fixed([proposal("tool:a#3=error"), proposal("tool:a#2=error"), proposal("input:typos")]), start, run=run)
    cases = {text_of(e.condition): set(e.cases) for batch in run.batches for e in batch}
    assert cases["tool:a#3=error"] == {"c1"}
    assert cases["tool:a#2=error"] == {"c1", "c3"}
    assert len(cases["input:typos"]) == 2


def test_the_stage_draws_cases_from_the_generator_it_was_given() -> None:
    """Over seeds, a stage does not always pick one pair of cases; and on one seed, it always picks the same."""
    from tests.search_support import Fixed, Scripted, proposal

    def picked(seed: int) -> frozenset[str]:
        run = Scripted()
        stage(Fixed([proposal("input:typos")]), seen(control=CASES, budget=100, cases_per_condition=2, cat=catalogue(inputs=("typos",))), run=run, generator=random.Random(seed))
        return frozenset(run.batches[0][0].cases)

    assert picked(1) == picked(1)
    assert len({picked(seed) for seed in range(30)}) > 1


def test_a_control_row_is_not_needed_for_cases_for() -> None:
    """The map is what it reads: a stage with no control rows at all still knows where a change lands."""
    start = seen(control=CASES, runs=(), cases_per_condition=2)
    assert set(search().cases_for(start, condition("tool:a#3=error"), rng=rng())) == {"c1"}


def test_catalogue_is_not_consulted_for_where_a_change_can_land() -> None:
    """A condition is checked against the settings elsewhere (ruling 19): `cases_for` reads the map."""
    start = seen(control=CASES, cat=catalogue(("timeout",)), cases_per_condition=2)
    assert set(search().cases_for(start, condition("tool:a#3=error"), rng=rng())) == {"c1"}
