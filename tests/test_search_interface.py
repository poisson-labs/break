"""The strategy interface (spec §11.3): the module's names, the version constant, `Proposal`, `Seen`, and no adaptive search.

- BK6.12  `Seen` is read-only and sufficient.
- BK6.6   a bad probability or reason is refused when a `Proposal` is made, as a record refuses one (the stage checks again,
  in `test_search_stage.py`, since a strategy can return anything).
- Rulings 1, 2, 7, 27 and 28 of `evidence/bk6/open-points.md`.

No refusal test here reads a message's words: a refusal is its type, with a control beside it that is accepted.
"""

from __future__ import annotations

import dataclasses
import inspect
import math
import random
from typing import Any

import pytest

from tests.changes_support import changes
from tests.conftest import run_python
from tests.search_support import (
    CONTROL,
    Fixed,
    catalogue,
    condition,
    interfaces,
    proposal,
    rng,
    row,
    search,
    seen,
    stage,
    text_of,
)

KW = inspect.Parameter.KEYWORD_ONLY
POS = inspect.Parameter.POSITIONAL_OR_KEYWORD


# ---------------------------------------------------------------------------
# the names, and the version
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["Strategy", "Proposal", "Seen", "SeenRun", "Screen", "Random", "score", "shrink", "coverage",
                                  "Coverage", "load_strategy", "STRATEGY_INTERFACE_VERSION", "SearchError", "allowed",
                                  "Allowed", "search_stage", "Stage", "LogEntry", "read_log", "cases_for"])
def test_the_public_names_are_declared(name: str) -> None:
    assert name in search().__all__
    assert hasattr(search(), name)


def test_the_interface_version_is_one_and_is_the_one_the_interfaces_module_declares() -> None:
    """Ruling 27: pinned here, and a strategy declares nothing. One that cares compares this constant on import."""
    assert type(search().STRATEGY_INTERFACE_VERSION) is int
    assert search().STRATEGY_INTERFACE_VERSION == 1
    assert search().STRATEGY_INTERFACE_VERSION == interfaces().STRATEGY_INTERFACE_VERSION


def test_a_strategy_that_declares_a_version_is_not_asked_about_it() -> None:
    """Nothing else about a strategy is known to the core (§11.3): an attribute of that name changes nothing."""
    class Says(Fixed):
        interface_version = 999

    result = stage(Says([proposal("tool:a#1=error")]))
    assert result.stopped is None
    assert [text_of(e.condition) for e in result.log] == ["tool:a#1=error"]


def test_strategy_is_the_protocol_the_interfaces_module_declares() -> None:
    assert search().Strategy is interfaces().Strategy


@pytest.mark.parametrize("built_in", ["Screen", "Random"])
def test_a_built_in_is_made_with_no_arguments_and_has_the_interface_shape(built_in: str) -> None:
    made = getattr(search(), built_in)()
    assert isinstance(made, search().Strategy)
    params = [(n, p.kind) for n, p in inspect.signature(made.propose).parameters.items()]
    assert params == [("seen", POS), ("budget", POS), ("rng", KW)]


def test_propose_returns_a_list_of_proposals() -> None:
    """§11.3's forcing clause: `propose` is asked for a list of proposals, and each built-in hands back exactly that."""
    for strategy in (search().Screen(), search().Random()):
        got = strategy.propose(seen(), 400, rng=rng())
        assert isinstance(got, list) and got
        assert all(isinstance(p, search().Proposal) for p in got)


# ---------------------------------------------------------------------------
# no adaptive search, no Monte: both are on demand
# ---------------------------------------------------------------------------


def test_nothing_in_the_module_is_an_adaptive_search() -> None:
    assert not [n for n in dir(search()) if "adaptive" in n.lower() or "bandit" in n.lower() or "ucb" in n.lower()]


def test_the_core_has_no_adaptive_module_and_knows_only_the_two_built_ins() -> None:
    ran = run_python(
        "import importlib.util, sys\n"
        "from poisson_break import search\n"
        "for name in ('poisson_break.adaptive', 'poisson_break.search_adaptive', 'poisson_break.monte'):\n"
        "    assert importlib.util.find_spec(name) is None, name\n"
        "assert isinstance(search.load_strategy('screen'), search.Screen)\n"
        "assert isinstance(search.load_strategy('random'), search.Random)\n"
        "print('ok')\n")
    assert ran.exit == 0, ran.stderr
    assert ran.stdout.strip() == "ok"


def test_loading_the_module_and_searching_imports_neither_prove_nor_the_runs_module_nor_monte_nor_any_implementation() -> None:
    """§11.5 and MT6.6: open-source Break runs with Monte absent. The core never imports an implementation it did not load by
    name (§11): `tests.strategies` is not loaded until a path names it. `search` is written against `Seen`, and the runs go
    behind a callable, so nothing of the runs module or Prove comes in with it."""
    ran = run_python(
        "import random, sys\n"
        "from poisson_break import apply, changes, interfaces, search\n"
        "control = {'c1': {'a': 1}}\n"
        "cat = search.allowed(vary={'tools': ['error'], 'inputs': [], 'max_call': 3}, tools={'a': 'read'},\n"
        "                     capabilities=interfaces.Capabilities(tool_calls=True, model_calls=False, conversation=False))\n"
        "start = search.Seen(control=control, runs=(), proposals=(), budget=4, catalogue=cat, set_aside=(), cases_per_condition=1)\n"
        "result = search.search_stage(search.load_strategy('screen'), name='screen', seen=start, rng=random.Random(1),\n"
        "                             run=lambda entries: [search.SeenRun(condition=e.condition if not isinstance(e.condition, str) else changes.parse(e.condition),\n"
        "                                                                 case=c, seed=9, outcome='ok') for e in entries for c in e.cases])\n"
        "assert len(result.seen.runs) == 1\n"
        "for name in sys.modules:\n"
        "    root = name.split('.')[0]\n"
        "    assert root not in ('poisson_prove', 'monte', 'scipy', 'numpy', 'tests'), name\n"
        "    assert name != 'poisson_break.hunt', name\n"
        "print('ok')\n")
    assert ran.exit == 0, ran.stderr
    assert ran.stdout.strip() == "ok"


# ---------------------------------------------------------------------------
# a proposal
# ---------------------------------------------------------------------------


def test_a_proposal_holds_its_three_fields_and_only_those() -> None:
    """Ruling 28: no fourth field. Monte's score goes in its reason or its own log."""
    made = search().Proposal(condition=condition("tool:a#1=error"), reason="the first call", probability=0.25)
    assert made.condition == condition("tool:a#1=error")
    assert made.reason == "the first call"
    assert made.probability == 0.25
    assert [f.name for f in dataclasses.fields(made)] == ["condition", "reason", "probability"]


def test_a_proposal_is_frozen_and_keyword_only() -> None:
    made = proposal()
    for field in ("condition", "reason", "probability"):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(made, field, None)
    with pytest.raises(TypeError):
        search().Proposal(condition("tool:a#1=error"), "why", 0.5)


@pytest.mark.parametrize("missing", ["condition", "reason", "probability"])
def test_a_proposal_needs_all_three(missing: str) -> None:
    given = {"condition": condition("tool:a#1=error"), "reason": "why", "probability": 0.5}
    search().Proposal(**given)
    del given[missing]
    with pytest.raises((TypeError, search().SearchError)):
        search().Proposal(**given)


def test_a_search_error_is_a_value_error() -> None:
    assert issubclass(search().SearchError, ValueError)


BAD_PROBABILITIES = [0, 0.0, -0.1, -1, 1.0000001, 2, math.inf, -math.inf, math.nan, True, False, None, "0.5", [0.5]]
GOOD_PROBABILITIES = [1, 1.0, 0.5, 5e-324, 1 / 3]


@pytest.mark.parametrize("bad", BAD_PROBABILITIES, ids=repr)
def test_a_probability_outside_above_zero_to_one_is_refused_when_made(bad: Any) -> None:
    with pytest.raises(search().SearchError):
        search().Proposal(condition=condition("tool:a#1=error"), reason="why", probability=bad)


@pytest.mark.parametrize("good", GOOD_PROBABILITIES, ids=repr)
def test_a_probability_up_to_and_including_one_is_taken(good: float) -> None:
    assert search().Proposal(condition=condition("tool:a#1=error"), reason="why", probability=good).probability == good


@pytest.mark.parametrize("bad", ["", None, 7, "two\nlines", "two\rlines", "ends\n", b"bytes"], ids=repr)
def test_a_reason_that_is_empty_not_text_or_more_than_one_line_is_refused_when_made(bad: Any) -> None:
    """Ruling 21."""
    with pytest.raises(search().SearchError):
        search().Proposal(condition=condition("tool:a#1=error"), reason=bad, probability=0.5)


@pytest.mark.parametrize("reason", ["why", "a longer reason, with commas and a colon: fine", "é"])
def test_a_reason_of_one_line_is_taken(reason: str) -> None:
    assert search().Proposal(condition=condition("tool:a#1=error"), reason=reason, probability=0.5).reason == reason


@pytest.mark.parametrize("bad", ["tool:a#1=error", None, 7, ("tool:a#1=error",)], ids=repr)
def test_a_condition_that_is_not_a_condition_is_refused_when_made(bad: Any) -> None:
    """Ruling 1: a condition, not its name."""
    with pytest.raises(search().SearchError):
        search().Proposal(condition=bad, reason="why", probability=0.5)


def test_the_control_can_be_made_as_a_proposal_and_is_dropped_by_the_stage() -> None:
    """Ruling 20: the empty condition is a condition. It is the stage, knowing the control ran, that drops it."""
    made = search().Proposal(condition=changes().parse(""), reason="why", probability=0.5)
    result = stage(Fixed([made]))
    assert [(text_of(e.condition), e.state) for e in result.log] == [("", "dropped")]


# ---------------------------------------------------------------------------
# BK6.12  Seen is read-only ...
# ---------------------------------------------------------------------------


def test_seen_holds_what_it_was_given() -> None:
    """The control map, every run with its condition, case, seed and outcome, every proposal, the budget left, the catalogue,
    and the two ruling 2 adds."""
    cat = catalogue()
    first = stage(Fixed([proposal("tool:a#1=error", probability=0.25)])).log[0]
    runs = (row("", "c1", "ok", seed=7), row("tool:a#1=error", "c2", "failed", seed=8))
    made = seen(control=CONTROL, runs=runs, proposals=(first,), budget=33, cat=cat, set_aside=("c2",), cases_per_condition=2)
    assert {case: dict(reach) for case, reach in made.control.items()} == CONTROL
    assert made.runs == runs
    assert [(text_of(r.condition), r.case, r.seed, r.outcome) for r in made.runs] == [
        ("", "c1", 7, "ok"), ("tool:a#1=error", "c2", 8, "failed")]
    assert made.proposals == (first,) and made.proposals[0].probability == 0.25
    assert made.budget == 33
    assert made.catalogue == cat
    assert tuple(made.set_aside) == ("c2",)
    assert made.cases_per_condition == 2


def test_seen_is_keyword_only() -> None:
    with pytest.raises(TypeError):
        search().Seen(CONTROL, (), (), 4, catalogue(), (), 4)


@pytest.mark.parametrize("field", ["control", "runs", "proposals", "budget", "catalogue", "set_aside", "cases_per_condition"])
def test_seen_refuses_assignment(field: str) -> None:
    made = seen()
    before = getattr(made, field)
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        setattr(made, field, before)
    assert getattr(made, field) is before


def test_seen_refuses_a_new_attribute() -> None:
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        seen().notes = "kept for later"


def test_the_control_map_refuses_a_change_at_either_depth() -> None:
    made = seen()
    with pytest.raises(TypeError):
        made.control["c9"] = {}
    with pytest.raises(TypeError):
        made.control["c1"]["a"] = 99
    with pytest.raises(TypeError):
        del made.control["c1"]


def test_seen_holds_copies_of_what_it_was_given() -> None:
    """A strategy, or the caller, holding the mapping it was made from reaches nothing."""
    control = {"c1": {"a": 2}}
    runs = [row("", "c1")]
    made = seen(control=control, runs=runs)
    control["c1"]["a"] = 99
    control["c2"] = {"a": 1}
    runs.append(row("", "c1"))
    assert {case: dict(reach) for case, reach in made.control.items()} == {"c1": {"a": 2}}
    assert len(made.runs) == 1


@pytest.mark.parametrize("field", ["runs", "proposals"])
def test_what_seen_lists_is_a_tuple_even_if_a_list_is_handed_in(field: str) -> None:
    """Ruling 2. A list could be appended to by a strategy. One handed in may be refused or turned into a tuple."""
    try:
        made = search().Seen(control=CONTROL, runs=[], proposals=[], budget=4, catalogue=catalogue(), set_aside=(), cases_per_condition=4)
    except (search().SearchError, TypeError):
        return
    assert isinstance(getattr(made, field), tuple)


def test_the_cases_set_aside_cannot_be_added_to() -> None:
    made = seen(set_aside=("c2",))
    assert isinstance(made.set_aside, (tuple, frozenset))
    assert set(made.set_aside) == {"c2"}


def test_a_seen_run_is_frozen_and_keyword_only() -> None:
    one = row("tool:a#1=error", "c1", "failed", seed=7)
    for field in ("condition", "case", "seed", "outcome"):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(one, field, None)
    with pytest.raises(TypeError):
        search().SeenRun(condition("tool:a#1=error"), "c1", 7, "failed")
    assert [f.name for f in dataclasses.fields(one)][:4] == ["condition", "case", "seed", "outcome"]


@pytest.mark.parametrize("outcome", ["ok", "failed", "not counted"])
def test_a_seen_run_takes_the_three_outcomes(outcome: str) -> None:
    assert row("", "c1", outcome).outcome == outcome


@pytest.mark.parametrize("outcome", ["passed", "FAILED", "Ok", "not_counted", "", " ok", None, 1, True])
def test_a_seen_run_with_any_other_outcome_is_refused_when_made(outcome: Any) -> None:
    """Ruling 32: or a misspelt word from the runs module would silently score as not failed."""
    with pytest.raises(search().SearchError):
        row("", "c1", outcome)


# ---------------------------------------------------------------------------
# BK6.12  ... and sufficient: screen and random are written against it and nothing else
# ---------------------------------------------------------------------------


class Only:
    """Stands in for `Seen`, holding only its seven public fields and noting which are read. A strategy that reached for
    anything else raises `AttributeError` here."""

    FIELDS = ("control", "runs", "proposals", "budget", "catalogue", "set_aside", "cases_per_condition")

    def __init__(self, real: Any) -> None:
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "read", set())

    def __getattr__(self, name: str) -> Any:
        if name not in Only.FIELDS:
            raise AttributeError(name)
        self.read.add(name)
        return getattr(self._real, name)


@pytest.fixture(params=["Screen", "Random"])
def built_in(request: pytest.FixtureRequest) -> Any:
    return getattr(search(), request.param)


def _same(first: Any, second: Any) -> bool:
    return ([(text_of(p.condition), p.reason, p.probability) for p in first]
            == [(text_of(p.condition), p.reason, p.probability) for p in second])


def test_each_built_in_needs_nothing_but_the_public_fields_of_seen(built_in: Any) -> None:
    start = seen(cat=catalogue(inputs=("typos",)))
    through_the_view = built_in().propose(Only(start), 400, rng=rng())
    assert _same(through_the_view, built_in().propose(start, 400, rng=rng()))


def test_each_built_in_keeps_nothing_on_itself(built_in: Any) -> None:
    """§11.3 invariant 4: the same strategy object shown the same `Seen` answers the same, whatever it answered between."""
    start = seen()
    other = seen(control={"c9": {"b": 1}})
    one = built_in()
    first = one.propose(start, 400, rng=rng())
    one.propose(other, 400, rng=rng())
    assert _same(first, one.propose(start, 400, rng=rng()))
    assert _same(first, built_in().propose(start, 400, rng=rng()))


def test_each_built_in_works_in_an_empty_folder_and_writes_nothing(built_in: Any, tmp_path: Any,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """There is no hunt, no store and no settings file behind a `Seen`."""
    monkeypatch.chdir(tmp_path)
    assert built_in().propose(seen(), 400, rng=rng())
    assert list(tmp_path.iterdir()) == []


def test_each_built_in_leaves_seen_as_it_was(built_in: Any) -> None:
    start = seen()
    before = (dict(start.control), start.runs, start.proposals, start.budget, start.set_aside)
    built_in().propose(start, 400, rng=rng())
    assert (dict(start.control), start.runs, start.proposals, start.budget, start.set_aside) == before


def test_each_built_in_answers_from_this_seen_and_not_a_module_level_one(built_in: Any) -> None:
    """Two hunts in one process, one after the other, on different maps."""
    first = {text_of(p.condition) for p in built_in().propose(seen(control={"c1": {"a": 1}}), 400, rng=rng())}
    second = {text_of(p.condition) for p in built_in().propose(seen(control={"c1": {"b": 1}}), 400, rng=rng())}
    assert all("tool:a#" in t and "tool:b#" not in t for t in first)
    assert all("tool:b#" in t and "tool:a#" not in t for t in second)


def test_a_strategy_from_outside_can_read_every_field_it_is_promised() -> None:
    """§11.3: what `Seen` promises is there for a strategy, shown from inside a stage. A later batch sees the earlier one's runs
    with their condition, case, seed and outcome, and its proposals with their probability, and the budget has moved."""
    def second(shown: Any) -> list[Any]:
        return []

    strategy = Fixed([proposal("tool:a#1=error", probability=0.125)], second)
    run = _Rows()
    stage(strategy, seen(budget=40, cases_per_condition=2), run=run)
    first_shown, second_shown = strategy.shown[0][0], strategy.shown[1][0]
    assert isinstance(first_shown, search().Seen) and isinstance(second_shown, search().Seen)
    assert first_shown.proposals == () and first_shown.budget == 40 and strategy.shown[0][1] == 40
    fresh = second_shown.runs[len(first_shown.runs):]
    assert [(text_of(r.condition), r.outcome) for r in fresh] == [("tool:a#1=error", "failed")] * 2
    assert {r.case for r in fresh} <= set(CONTROL)
    assert [r.seed for r in fresh] == run.seeds
    assert [(text_of(p.condition), p.probability, p.reason) for p in second_shown.proposals] == [("tool:a#1=error", 0.125, "because")]
    assert second_shown.budget == 38 and strategy.shown[1][1] == 38
    assert {c: dict(r) for c, r in second_shown.control.items()} == CONTROL
    assert second_shown.catalogue == first_shown.catalogue
    assert second_shown.set_aside == first_shown.set_aside and second_shown.cases_per_condition == 2


class _Rows:
    def __init__(self) -> None:
        self.seeds: list[int] = []

    def __call__(self, entries: Any) -> list[Any]:
        rows = []
        for entry in entries:
            for case in entry.cases:
                self.seeds.append(31 + len(self.seeds))
                rows.append(search().SeenRun(condition=condition(text_of(entry.condition)), case=case, seed=self.seeds[-1],
                                             outcome="failed"))
        return rows


def test_what_a_strategy_was_shown_earlier_does_not_change_under_it() -> None:
    """A `Seen` is a view of the hunt so far at that moment: a strategy holding the first one sees the same thing later."""
    strategy = Fixed([proposal("tool:a#1=error")], [proposal("tool:a#2=error")])
    stage(strategy, seen())
    first = strategy.shown[0][0]
    assert first.proposals == ()
    assert len(first.runs) == len(seen().runs)
    assert first.budget == 400


def test_the_seed_a_strategy_is_given_is_one_generator_the_whole_stage() -> None:
    """§11.3: `rng` is the search seed's generator, one for the stage, and it is passed as given."""
    generator = random.Random(5)
    strategy = Fixed([proposal("tool:a#1=error")], [proposal("tool:a#2=error")])
    stage(strategy, seen(), generator=generator)
    assert [shown[2] for shown in strategy.shown] == [generator, generator, generator]
    assert all(shown[2] is generator for shown in strategy.shown)
