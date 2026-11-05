"""BK6.11: a strategy is added without editing the core (spec §11.3, ruling 6 of `evidence/bk6/open-points.md`).

A test-only strategy, found by its import path, runs a search stage end to end, holding to everything `screen` and `random` are
held to. The same hunt with it absent fails before any run with one line. Each refusal is its type, one line, and an accepted
control; no test reads a refusal's words.

That `doctor` and `hunt` call `load_strategy` once the settings are loaded is an order of events that needs the commands
module: BK8.6 holds it, and it has no test here.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import run_python
from tests.search_support import (
    AGENT_TOOLS,
    RealRuns,
    Scripted,
    by_state,
    catalogue,
    logged,
    records,
    search,
    seen,
    stage,
    text_of,
)

FIXED = "tests.strategies:Fixed"


@pytest.fixture
def outside(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """A folder on the import path that is no part of this repository: where a user's strategy, or Monte, would be."""
    monkeypatch.syspath_prepend(str(tmp_path))
    written: list[str] = []

    def write(module: str, text: str) -> str:
        (tmp_path / f"{module}.py").write_text(text)
        written.append(module)
        return module

    yield write
    for module in written:
        sys.modules.pop(module, None)


# ---------------------------------------------------------------------------
# what is loaded
# ---------------------------------------------------------------------------


def test_the_two_built_ins_load_by_name() -> None:
    assert isinstance(search().load_strategy("screen"), search().Screen)
    assert isinstance(search().load_strategy("random"), search().Random)


def test_a_built_in_by_its_import_path_is_a_strategy_like_any_other() -> None:
    assert isinstance(search().load_strategy("poisson_break.search:Screen"), search().Screen)


def test_a_class_on_an_import_path_is_called_with_no_arguments() -> None:
    from tests import strategies

    loaded = search().load_strategy(FIXED)
    assert type(loaded) is strategies.Fixed
    assert isinstance(loaded, search().Strategy)


def test_anything_else_with_a_propose_is_used_as_it_is() -> None:
    from tests import strategies

    assert search().load_strategy("tests.strategies:AN_OBJECT") is strategies.AN_OBJECT


def test_an_object_that_can_also_be_called_is_not_called() -> None:
    from tests import strategies

    assert search().load_strategy("tests.strategies:A_CALLABLE_OBJECT") is strategies.A_CALLABLE_OBJECT


def test_loading_a_class_twice_gives_two_objects() -> None:
    """§11.3 invariant 4: a strategy carries no state from one hunt to the next through Break."""
    assert search().load_strategy(FIXED) is not search().load_strategy(FIXED)


# ---------------------------------------------------------------------------
# what is refused: one line, one type, before anything runs
# ---------------------------------------------------------------------------


def _refused(path: Any) -> str:
    with pytest.raises(search().SearchError) as caught:
        search().load_strategy(path)
    said = str(caught.value)
    assert said.strip(), "a refusal says something"
    assert "\n" not in said and "\r" not in said, f"not one line: {said!r}"
    return said


@pytest.mark.parametrize("path", [
    "no_such_module_anywhere:Fixed",            # the module is absent
    "tests.no_such_module:Fixed",               # a parent is there, the module is not
    "tests.strategies:NoSuchName",              # the name is absent
    "tests.strategies:NoPropose",               # no propose
    "tests.strategies:NOT_ANYTHING",            # not a strategy at all
    "tests.strategies:NeedsArguments",          # a class that needs arguments
    "adaptive",                                 # the core does not ship it
    "Screen",                                   # a word that is neither, in the wrong case
    "screen ",
    "",
    "module:",
    ":Name",
    "a:b:c",
])
def test_a_strategy_that_cannot_be_loaded_is_one_refusal_of_one_line(path: str) -> None:
    _refused(path)


@pytest.mark.parametrize("path", [None, 7, ["screen"]], ids=repr)
def test_something_that_is_not_text_is_refused_the_same_way(path: Any) -> None:
    _refused(path)


@pytest.mark.parametrize("line", ["raise ImportError('two\\nlines')", "raise ValueError('at import')",
                                  "import a_module_that_is_not_there", "raise SystemExit(4)", "1/0"])
def test_a_module_whose_import_goes_wrong_is_one_refusal_of_one_line(outside: Any, line: str) -> None:
    module = outside("goes_wrong_on_import", line + "\n\nclass Fixed:\n    def propose(self, seen, budget, *, rng):\n        return []\n")
    _refused(f"{module}:Fixed")


def test_ctrl_c_during_an_import_passes_through(outside: Any) -> None:
    module = outside("interrupted_on_import", "raise KeyboardInterrupt\n")
    with pytest.raises(KeyboardInterrupt):
        search().load_strategy(f"{module}:Fixed")


def test_a_class_whose_making_raises_is_one_refusal(outside: Any) -> None:
    module = outside("raises_when_made", "class Fixed:\n    def __init__(self):\n        raise ValueError('no\\nthanks')\n"
                                         "    def propose(self, seen, budget, *, rng):\n        return []\n")
    _refused(f"{module}:Fixed")


def test_the_control_for_those_a_module_from_outside_that_loads_is_taken(outside: Any) -> None:
    module = outside("loads_fine", "class Fixed:\n    def propose(self, seen, budget, *, rng):\n        return []\n")
    assert hasattr(search().load_strategy(f"{module}:Fixed"), "propose")


def test_an_absent_strategy_stops_what_would_have_run_before_any_run() -> None:
    """The order a hunt keeps: `load_strategy` is called on the settings' word, and nothing else has happened yet. A stage cannot
    start with no strategy to give it."""
    run = Scripted()

    def hunt(path: str) -> Any:
        return stage(search().load_strategy(path), run=run)

    with pytest.raises(search().SearchError):
        hunt("tests.strategies:NoSuchName")
    assert run.batches == []


def test_loading_runs_nothing_of_the_strategy_but_its_making(outside: Any) -> None:
    """Rejected for ruling 18: `load_strategy` does not probe `propose` on a made-up `Seen`, which would run a paid strategy
    on nothing."""
    module = outside("counts_its_calls", "CALLS = []\n\nclass Fixed:\n    def propose(self, seen, budget, *, rng):\n"
                                         "        CALLS.append(1)\n        return []\n")
    search().load_strategy(f"{module}:Fixed")
    assert sys.modules[module].CALLS == []


# ---------------------------------------------------------------------------
# BK6.11  it works like screen and random
# ---------------------------------------------------------------------------


def test_a_strategy_loaded_from_a_path_runs_a_search_stage_end_to_end_on_a_scripted_agent() -> None:
    """On `repeats_write`, under real sessions and the real checks, with what it proposes logged under the path it was named by."""
    runs = RealRuns("repeats_write")
    start = runs.start(budget=40, faults=("error", "timeout", "lost_reply"))
    result = stage(search().load_strategy(FIXED), start, name=FIXED, run=runs)
    assert result.stopped is None
    assert [(text_of(e.condition), e.strategy, e.reason, e.probability) for e in result.log if e.state == "run"] == [
        ("tool:lookup_order#1=error", FIXED, "the first look-up", 0.25),
        ("tool:issue_refund#1=lost_reply", FIXED, "the write", 0.125)]
    # `check_policy` is a tool this agent never calls: no case fits, so nothing is spent on it.
    assert runs.tried == ["tool:lookup_order#1=error", "tool:issue_refund#1=lost_reply"]
    fresh = [r for r in result.seen.runs if r.condition.changes]
    assert {r.case for r in fresh} == {"c1", "c2", "c3", "c4"}
    outcome_of = {text_of(r.condition): r.outcome for r in fresh}
    assert outcome_of == {"tool:lookup_order#1=error": "ok", "tool:issue_refund#1=lost_reply": "failed"}
    assert result.seen.budget == 40 - 8


def test_a_strategy_written_in_a_folder_of_its_own_runs_a_stage(outside: Any) -> None:
    """What Monte is: another package, importing only what Break publishes."""
    module = outside("somebody_elses_search", '''
from poisson_break.changes import parse
from poisson_break.search import Proposal, STRATEGY_INTERFACE_VERSION

assert STRATEGY_INTERFACE_VERSION == 1


class Mine:
    def propose(self, seen, budget, *, rng):
        tools = sorted({tool for reach in seen.control.values() for tool in reach})
        return [Proposal(condition=parse(f"tool:{tool}#1=error"), reason=f"{budget} runs left", probability=0.75)
                for tool in tools if not seen.proposals]
''')
    path = f"{module}:Mine"
    run = Scripted()
    result = stage(search().load_strategy(path), seen(budget=20, cases_per_condition=1, cat=catalogue(tools={"a": "read", "b": "read", "w": {"class": "write", "repeatable": True}})),
                   name=path, run=run)
    assert run.ran == ["tool:a#1=error", "tool:b#1=error", "tool:w#1=error"]
    assert {(e.strategy, e.reason, e.probability) for e in result.log} == {(path, "20 runs left", 0.75)}
    assert result.stopped is None


def test_what_holds_screen_holds_a_strategy_from_outside(outside: Any) -> None:
    """A repeat is dropped, a bad probability refused and a refused change named, whichever strategy it came from."""
    module = outside("somebody_elses_repeats", '''
from poisson_break.changes import parse
from poisson_break.search import Proposal


class Twice:
    def propose(self, seen, budget, *, rng):
        made = Proposal(condition=parse("tool:a#1=error"), reason="again", probability=0.5)
        return [made, made]


class OutOfRange:
    def propose(self, seen, budget, *, rng):
        class Mine:
            condition = parse("tool:a#1=error")
            reason = "I am sure"
            probability = 1.5
        return [Mine()]


class TurnedOff:
    def propose(self, seen, budget, *, rng):
        return [Proposal(condition=parse("tool:a#1=stale"), reason="not allowed", probability=0.5)]
''')
    run = Scripted()
    twice = stage(search().load_strategy(f"{module}:Twice"), run=run)
    assert run.ran == ["tool:a#1=error"]
    assert set(by_state(twice, "dropped")) == {"tool:a#1=error"}
    run = Scripted()
    out_of_range = stage(search().load_strategy(f"{module}:OutOfRange"), run=run)
    assert run.ran == [] and isinstance(out_of_range.stopped, search().SearchError)
    run = Scripted()
    turned_off = stage(search().load_strategy(f"{module}:TurnedOff"), run=run)
    assert run.ran == [] and isinstance(turned_off.stopped, search().SearchError)
    assert "tool:a#1=stale" in str(turned_off.stopped)


def test_the_built_ins_go_through_the_same_door_as_any_other(outside: Any) -> None:
    """A strategy from outside that hands over what `screen` proposes gives the same log but for the name. Nothing in the
    stage treats a built-in specially."""
    module = outside("screen_again", '''
from poisson_break.search import Screen as Theirs


class Screen:
    def propose(self, seen, budget, *, rng):
        return Theirs().propose(seen, budget, rng=rng)
''')
    start = seen(budget=12, cases_per_condition=1)
    theirs = stage(search().load_strategy(f"{module}:Screen"), start, name="x")
    ours = stage(search().load_strategy("screen"), start, name="x")
    assert theirs.log == ours.log
    assert logged(theirs)


def test_a_loaded_path_goes_into_the_selection_as_it_was_given() -> None:
    """§6.4: the strategy's name is "the import path given"."""
    run = Scripted()
    start = seen(control={"c1": {"lookup_order": 1, "issue_refund": 1, "check_policy": 1}},
                 cat=catalogue(tools=AGENT_TOOLS))
    stage(search().load_strategy(FIXED), start, name=FIXED, run=run)
    handed = [e for batch in run.batches for e in batch]
    assert [e.selection for e in handed] == [records().Selection(strategy=FIXED, probability=p) for p in (0.25, 0.125, 0.5)]


def test_the_module_does_not_load_an_implementation_until_it_is_named() -> None:
    """§11: the core never imports an implementation it did not load by name from the settings."""
    ran = run_python("import sys\nfrom poisson_break import search\nassert 'tests.strategies' not in sys.modules\n"
                     "assert not [n for n in sys.modules if n == 'tests' or n.startswith('tests.')]\nprint('ok')\n")
    assert ran.exit == 0, ran.stderr
    assert ran.stdout.strip() == "ok"
