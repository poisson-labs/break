"""Search without learning: what a hunt tries after its control, and what every strategy is held to.

A **strategy** proposes conditions and Break runs them. ``propose(seen, budget, *, rng)`` returns a
list of ``Proposal``: a condition, the reason for it in one line, and the probability the strategy
gave that condition, above 0 and at most 1. Nothing else about a strategy is known here. Two are
built in, and neither looks at an outcome:

- ``Screen`` proposes every single change the control's map makes reachable, in a fixed order:
  every tool and every fault once, as early as that can be done; then every input operator and
  every listed value of a setting; then the rest of the first call of each tool; then the second
  call, and so on. Its probability is 1.
- ``Random`` draws single changes and pairs of them, as one set, uniformly and never twice. Its
  probability is 1 over the size of that set, whatever has been drawn already. A pair that could
  not be drawn to any purpose is not in the set: two changes on one call of one tool, two values of
  one setting, and a pair no one case can hold.

Both vary tool faults at a call number, input operators and the values of a setting; neither
proposes a rate, a fault on every call, or a change to the conversation or the model's own calls.
Those stay open to a strategy written outside this package, which is found by its import path
(``load_strategy("my_app.search:Mine")``) and goes through the same door as the two here.

``Seen`` is all a strategy is shown, read-only: the control's map (for each case, each tool and
the most calls of it in one control run), every run so far with its condition, case, seed and
outcome, every proposal so far, the runs left, what the settings allow (``Allowed``, from
``allowed``), the cases set aside, and how many cases a condition runs on.

``search_stage`` is the loop. It asks the strategy, checks what comes back, drops what has been
proposed before, writes every proposal to the log, and only then hands what is left to ``run``, a
callable it is given, which runs each condition on its cases and hands back the rows. What it
holds every strategy to:

- **No condition twice.** A condition is written canonically before it is compared, so a second
  spelling is a repeat, and the empty condition is a repeat of the control. A repeat is logged
  ``dropped`` and costs no run. A batch with nothing new ends the stage.
- **Every proposal is logged first,** with the strategy's name, its reason and its probability, in
  the order proposed. With ``log`` given, each is one JSON line in that file before its run, and
  ``read_log`` reads the file back as the same entries.
- **A bad proposal refuses its whole batch before any of it runs:** a probability that is missing
  or outside (0, 1], a reason that is not one line of text, a return that is not a list, a
  condition the catalogue could not have written, or a change outside what the settings allow,
  which the refusal names. The batch is logged ``refused`` and the stage stops with what it had.
- **A strategy's exception stops the stage** with what it had, as an ``InstrumentError``. Ctrl-C
  passes through, and so does anything ``run`` raises.
- **A condition is run whole or not at all.** It runs on ``cases_for`` it: cases not set aside on
  which every tool change can land, drawn with the stage's generator, fewer when fewer fit. What
  the runs left cannot pay for is logged ``not run`` and ends the stage; what no case can take is
  logged ``not run`` and does not. ``reserve`` holds runs back from the stage for shrinking.

The stage returns a ``Stage``: the last ``Seen``, its own log, and why it stopped or ``None``.

``score`` is how a condition did: its share of failed runs, less the control's share on the same
cases, with runs not counted left out. ``shrink`` makes a candidate smaller, one change at a time,
for as long as the smaller condition fails at least as often as the candidate did, less one run.
``coverage`` says what a hunt did not look at. Each takes what it needs as data or as a callable,
so nothing here runs an agent, stores a run or reads a settings file.

A refusal of this module's own is a ``SearchError``, one line.
"""

from __future__ import annotations

import importlib
import json
import math
import operator
import os
import random
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from poisson_break import changes as _catalogue
from poisson_break.apply import Session, ToolRefused
from poisson_break.changes import Change, Condition, InstrumentError, NeedsAdapter
from poisson_break.changes import name as _name_of
from poisson_break.interfaces import STRATEGY_INTERFACE_VERSION, Capabilities, Strategy
from poisson_break.records import Selection

__all__ = [
    "STRATEGY_INTERFACE_VERSION",
    "Strategy",
    "SearchError",
    "Proposal",
    "SeenRun",
    "LogEntry",
    "Allowed",
    "allowed",
    "Seen",
    "Stage",
    "search_stage",
    "read_log",
    "cases_for",
    "Screen",
    "Random",
    "load_strategy",
    "score",
    "shrink",
    "Count",
    "Coverage",
    "coverage",
]

_JOIN = " + "

_OUTCOMES = ("ok", "failed", "not counted")
"""What a run came to: the agent did the job, the run failed, or the run says nothing about the
agent."""

_STATES = ("run", "dropped", "refused", "not run")
"""What became of a proposal: it ran; it repeated one made before; its batch was refused; or it
had no case to run on, or the runs left could not pay for it."""

_BUILT_IN = ("screen", "random")

_NOT_BUILT = ("adaptive",)
"""A strategy the settings file offers by a word and this version does not hold."""

_SURFACES = ("tool", "input", "user", "model", "env")

_ASKS_WITH_NOTHING_RUN = 100
"""How many times in a row a strategy may be asked and propose nothing that runs before the stage
stops. A proposal no case can take does not end the stage, and nothing else would end a strategy
that went on inventing them."""

_TOOL_PIECE = re.compile(r"([^#~=]+)([#~][^=]*)=(.*)", re.DOTALL)


class SearchError(ValueError):
    """A proposal, a strategy, a path or a value the search will not take: one line."""


# ---------------------------------------------------------------------------
# small things every part shares
# ---------------------------------------------------------------------------


def _shown(value: object) -> str:
    """A value inside a refusal, on one line whatever it holds."""
    if isinstance(value, str):
        return json.dumps(value if len(value) <= 60 else value[:57] + "...")
    if value is None or isinstance(value, bool | int | float):
        return repr(value)
    return type(value).__name__


def _one_line(wrong: BaseException) -> str:
    text = " ".join(str(wrong).split())
    return f"{type(wrong).__name__}: {text}" if text else type(wrong).__name__


def _is_probability(value: object) -> bool:
    return (not isinstance(value, bool) and isinstance(value, int | float)
            and bool(0 < value <= 1))


def _is_reason(value: object) -> bool:
    """One line of text that says something: not blank, and with no line break of any kind."""
    return isinstance(value, str) and value.strip() != "" and value.splitlines() == [value]


def _whole(value: object, *, least: int) -> int | None:
    """``value`` as a whole number of ``least`` or more, or ``None``."""
    if isinstance(value, bool):
        return None
    try:
        number = operator.index(value)  # type: ignore[arg-type]
    except TypeError:
        return None
    return number if number >= least else None


def _ordered(changes: Iterable[Change]) -> Condition:
    """A condition of these changes as a name writes one: sorted by name, each once."""
    named = {_name_of(change): change for change in changes}
    return Condition(changes=tuple(named[text] for text in sorted(named)))


def _key(condition: Condition) -> str:
    """A condition's canonical name, whatever order its changes were handed over in."""
    return _JOIN.join(sorted({_name_of(change) for change in condition.changes}))


def _written(change: object) -> str:
    """The whole name of one change, when it is one the catalogue could have written."""
    if not isinstance(change, Change):
        raise SearchError(f"a condition holds {_shown(change)}, which is not a change")
    try:
        text = _name_of(change)
        if change.surface == "env":
            fits = (isinstance(change.tool, str) and isinstance(change.fault, str)
                    and change.call is None)
        else:
            fits = _catalogue.parse(text).changes == (change,)
    except Exception as wrong:
        raise SearchError("a condition holds a change the catalogue could not have written "
                          f"({_one_line(wrong)})") from None
    if not fits:
        raise SearchError(f"a condition holds a change the catalogue could not have written, "
                          f"{_shown(text)}")
    return text


def _canonical(condition: object) -> Condition:
    """A condition as ``parse`` would have written it, or a refusal."""
    if not isinstance(condition, Condition) or not isinstance(condition.changes, tuple):
        raise SearchError(f"a proposal's condition is {_shown(condition)}, not a condition")
    named = {_written(change): change for change in condition.changes}
    return Condition(changes=tuple(named[text] for text in sorted(named)))


def _named(condition: object) -> Condition | None:
    """What a log entry keeps of a condition that was refused: the condition, canonical when it
    can be, as it was handed over when it can at least be named, and nothing otherwise."""
    if not isinstance(condition, Condition):
        return None
    try:
        return _canonical(condition)
    except SearchError:
        pass
    try:
        _name_of(condition)
    except Exception:
        return None
    return condition


# ---------------------------------------------------------------------------
# a proposal, a run, a log entry
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Proposal:
    """What a strategy proposes: a condition, the reason for it in one line, and the probability
    the strategy gave that condition, above 0 and at most 1. Refused when made if any of the
    three is not that."""

    condition: Condition
    reason: str
    probability: float

    def __post_init__(self) -> None:
        if not isinstance(self.condition, Condition):
            raise SearchError(f"a proposal's condition is {_shown(self.condition)}, not a "
                              "condition")
        if not _is_reason(self.reason):
            raise SearchError(f"a proposal's reason is {_shown(self.reason)}, not one line of "
                              "text")
        if not _is_probability(self.probability):
            raise SearchError(f"a proposal's probability is {_shown(self.probability)}, not a "
                              "number above 0 and at most 1")


@dataclass(frozen=True, kw_only=True)
class SeenRun:
    """One run so far: its condition (the empty one for a control run), the case, the run's seed,
    and what it came to: ``ok``, ``failed`` or ``not counted``. Any other word is refused."""

    condition: Condition
    case: str
    seed: int
    outcome: str

    def __post_init__(self) -> None:
        if not isinstance(self.condition, Condition):
            raise SearchError(f"a run's condition is {_shown(self.condition)}, not a condition")
        if not isinstance(self.outcome, str) or self.outcome not in _OUTCOMES:
            raise SearchError(f"a run's outcome is {_shown(self.outcome)}, not ok, failed or "
                              "not counted")


@dataclass(frozen=True, kw_only=True)
class LogEntry:
    """One proposal as the stage logged it: the strategy's name, the condition, the reason, the
    probability, what became of it (``run``, ``dropped``, ``refused`` or ``not run``) and, for one
    that ran, the cases it ran on.

    An entry that is not ``refused`` holds a condition, a reason of one line and a probability
    above 0 and at most 1. A ``refused`` entry holds what the strategy handed back, whatever that
    was, and ``None`` for a condition that was none. ``selection`` is the strategy and the
    probability as a stored run's record carries them."""

    strategy: str
    condition: Condition | None
    reason: str
    probability: float
    state: str
    cases: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, str) or not self.strategy:
            raise SearchError(f"a log entry's strategy is {_shown(self.strategy)}, not a name")
        if not isinstance(self.state, str) or self.state not in _STATES:
            raise SearchError(f"a log entry's state is {_shown(self.state)}, not run, dropped, "
                              "refused or not run")
        if isinstance(self.cases, str) or not isinstance(self.cases, Iterable):
            raise SearchError(f"a log entry's cases are {_shown(self.cases)}, not a list of "
                              "case ids")
        cases = tuple(self.cases)
        if not all(isinstance(case, str) for case in cases):
            raise SearchError("a log entry's cases are not all case ids, which are text")
        object.__setattr__(self, "cases", cases)
        if (self.state == "run") != bool(cases):
            raise SearchError("a log entry has cases exactly when its proposal ran, and this "
                              f"one is {self.state} with {len(cases)}")
        if self.state == "refused":
            if self.condition is not None and not isinstance(self.condition, Condition):
                raise SearchError("a refused log entry's condition is "
                                  f"{_shown(self.condition)}, not a condition or None")
            return
        if not isinstance(self.condition, Condition):
            raise SearchError(f"a log entry's condition is {_shown(self.condition)}, not a "
                              "condition")
        if not _is_reason(self.reason):
            raise SearchError(f"a log entry's reason is {_shown(self.reason)}, not one line of "
                              "text")
        if not _is_probability(self.probability):
            raise SearchError(f"a log entry's probability is {_shown(self.probability)}, not a "
                              "number above 0 and at most 1")

    @property
    def selection(self) -> Selection:
        """The strategy and the probability it gave the condition, as a run's record holds
        them."""
        if not _is_probability(self.probability):
            raise SearchError(f"a proposal with a probability of {_shown(self.probability)} has "
                              "no selection")
        return Selection(strategy=self.strategy, probability=self.probability)


# ---------------------------------------------------------------------------
# what the settings allow
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Allowed:
    """What the settings allow a search to change, read-only: ``tools``, each tool that is not
    ``off`` with the faults that may land on it; ``inputs``, the input operators; ``env``, each
    setting with the values listed for it, as text; ``max_call``, the latest call of a tool a
    fault may be put on; and ``faults_off``, the tool faults the settings leave out."""

    tools: Mapping[str, tuple[str, ...]]
    inputs: tuple[str, ...]
    env: Mapping[str, tuple[str, ...]]
    max_call: int
    faults_off: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tools", _frozen_lists(self.tools, "tools"))
        object.__setattr__(self, "inputs", _words(self.inputs, "inputs"))
        object.__setattr__(self, "env", _frozen_lists(self.env, "env"))
        most = _whole(self.max_call, least=1)
        if most is None:
            raise SearchError(f"max_call is {_shown(self.max_call)}, not a whole number of 1 or "
                              "more")
        object.__setattr__(self, "max_call", most)
        object.__setattr__(self, "faults_off", _words(self.faults_off, "faults_off"))


def _words(value: object, what: str) -> tuple[str, ...]:
    """A list of words, each once, in the order given."""
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise SearchError(f"{what} is {_shown(value)}, not a list of names")
    words = tuple(value)
    if not all(isinstance(word, str) for word in words):
        raise SearchError(f"{what} holds something that is not a name")
    return tuple(dict.fromkeys(words))


def _frozen_lists(value: object, what: str) -> Mapping[str, tuple[str, ...]]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise SearchError(f"{what} is {_shown(value)}, not a table of names")
    return MappingProxyType({key: _words(words, f"{what}.{key}") for key, words in value.items()})


def _is_off(line: object) -> bool:
    return line == "off" or (isinstance(line, Mapping) and line.get("class") == "off")


def allowed(*, vary: Mapping[str, Any], tools: Mapping[str, Any],
            capabilities: Capabilities) -> Allowed:
    """What the settings allow, from the ``[vary]`` table as a mapping, each tool's line as the
    settings file writes it, and what the way in can do.

    ``vary`` holds ``tools`` (the tool faults that are on), ``inputs`` (the input operators that
    are on) and ``max_call``, and may hold ``env``, each setting with its values. A key left out
    is refused, since the file's defaults are the settings module's to fill in. A fault lands on
    a tool only where a session takes it: a real ``Session`` is asked, so the rule is the applying
    module's and not a second copy of it. A tool's line that no session takes is that module's
    ``ToolRefused``, passed on as it is."""
    if not isinstance(vary, Mapping):
        raise SearchError(f"vary is {_shown(vary)}, not the [vary] table")
    for key in ("tools", "inputs", "max_call"):
        if key not in vary:
            raise SearchError(f"vary has no {key}: the [vary] table is given whole")
    faults = _words(vary["tools"], "vary.tools")
    operators = _words(vary["inputs"], "vary.inputs")
    known = [line.name for line in _catalogue.CATALOG if line.surface == "tool"]
    known_operators = [line.name for line in _catalogue.CATALOG if line.surface == "input"]
    for fault in faults:
        if fault not in known:
            raise SearchError(f"vary.tools lists {_shown(fault)}, which is not a tool fault in "
                              "the catalogue")
    for operator_name in operators:
        if operator_name not in known_operators:
            raise SearchError(f"vary.inputs lists {_shown(operator_name)}, which is not an input "
                              "operator in the catalogue")
    most = _whole(vary["max_call"], least=1)
    if most is None:
        raise SearchError(f"vary.max_call is {_shown(vary['max_call'])}, not a whole number of "
                          "1 or more")
    settings = vary.get("env") or {}
    if not isinstance(settings, Mapping) or not all(isinstance(key, str) for key in settings):
        raise SearchError(f"vary.env is {_shown(settings)}, not a table of settings")
    env = {setting: tuple(dict.fromkeys(_values(values))) for setting, values in settings.items()}

    if not isinstance(tools, Mapping) or not all(isinstance(tool, str) for tool in tools):
        raise SearchError(f"tools is {_shown(tools)}, not each tool's line by the tool's name")
    routes = getattr(capabilities, "tool_calls", None)
    if not isinstance(routes, bool):
        raise SearchError(f"capabilities is {_shown(capabilities)}, not what a way in can do")
    lines = dict(tools)
    Session(Condition(changes=()), seed=0, tools=lines)  # every line, read as a run reads it
    on_tool: dict[str, tuple[str, ...]] = {}
    for tool, line in lines.items():
        if _is_off(line):
            continue
        on_tool[tool] = tuple(fault for fault in faults
                              if routes and _session_takes(tool, line, fault, capabilities))
    return Allowed(tools=on_tool, inputs=operators, env=env, max_call=most,
                   faults_off=tuple(fault for fault in known if fault not in faults))


def _values(values: object) -> list[str]:
    """A setting's listed values as text, which is how a condition's name writes one."""
    if isinstance(values, list | tuple):
        return [str(value) for value in values]
    return [str(values)]


def _session_takes(tool: str, line: object, fault: str, capabilities: Capabilities) -> bool:
    """Whether a run can be made with this fault on the first call of this tool."""
    change = Change(surface="tool", tool=tool, fault=fault, call="#1")
    try:
        Session(Condition(changes=(change,)), seed=0, tools={tool: line},
                capabilities=capabilities)
    except ToolRefused as refused:
        if refused.change is None:
            raise
        return False
    except (NeedsAdapter, InstrumentError):
        return False
    return True


# ---------------------------------------------------------------------------
# the view of the hunt so far
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Seen:
    """The hunt so far, as a strategy is shown it, read-only all the way down.

    ``control`` is the control's map: for each case, each tool it called and the most calls of
    that tool in one control run. ``runs`` is every run so far, the control's among them.
    ``proposals`` is every proposal so far, as logged, whatever became of it. ``budget`` is the
    runs left. ``catalogue`` is what the settings allow. ``set_aside`` is the cases that failed
    every control run, which no search runs on. ``cases_per_condition`` is how many cases a
    condition is run on."""

    control: Mapping[str, Mapping[str, int]]
    runs: tuple[SeenRun, ...]
    proposals: tuple[LogEntry, ...]
    budget: int
    catalogue: Allowed
    set_aside: tuple[str, ...]
    cases_per_condition: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "control", _frozen_map(self.control))
        runs = _listed(self.runs, "runs")
        if not all(isinstance(run, SeenRun) for run in runs):
            raise SearchError("runs holds something that is not a SeenRun")
        object.__setattr__(self, "runs", runs)
        proposals = _listed(self.proposals, "proposals")
        if not all(isinstance(entry, LogEntry) for entry in proposals):
            raise SearchError("proposals holds something that is not a LogEntry")
        object.__setattr__(self, "proposals", proposals)
        budget = _whole(self.budget, least=0)
        if budget is None:
            raise SearchError(f"budget is {_shown(self.budget)}, not a whole number of runs")
        object.__setattr__(self, "budget", budget)
        if not isinstance(self.catalogue, Allowed):
            raise SearchError(f"catalogue is {_shown(self.catalogue)}, not what allowed() gives")
        aside = _listed(self.set_aside, "set_aside")
        if not all(isinstance(case, str) for case in aside):
            raise SearchError("set_aside holds something that is not a case id")
        object.__setattr__(self, "set_aside", aside)
        each = _whole(self.cases_per_condition, least=1)
        if each is None:
            raise SearchError(f"cases_per_condition is {_shown(self.cases_per_condition)}, not "
                              "a whole number of 1 or more")
        object.__setattr__(self, "cases_per_condition", each)


def _listed(value: object, what: str) -> tuple[Any, ...]:
    if isinstance(value, str | Mapping) or not isinstance(value, Iterable):
        raise SearchError(f"{what} is {_shown(value)}, not a list")
    return tuple(value)


def _frozen_map(control: object) -> Mapping[str, Mapping[str, int]]:
    """The control's map as a copy nothing can change, at either depth."""
    if not isinstance(control, Mapping):
        raise SearchError(f"control is {_shown(control)}, not the control's map")
    frozen: dict[str, Mapping[str, int]] = {}
    for case, reach in control.items():
        if not isinstance(case, str) or not isinstance(reach, Mapping):
            raise SearchError("control maps each case's id to the tools it called")
        calls: dict[str, int] = {}
        for tool, count in reach.items():
            most = _whole(count, least=0)
            if not isinstance(tool, str) or most is None:
                raise SearchError(f"control gives {_shown(tool)} {_shown(count)} calls in "
                                  f"{_shown(case)}, not a tool and a whole number")
            calls[tool] = most
        frozen[case] = MappingProxyType(calls)
    return MappingProxyType(frozen)


# ---------------------------------------------------------------------------
# which cases a condition runs on
# ---------------------------------------------------------------------------


def _first_call(position: str | None) -> int:
    """The first call of a tool a change written at ``position`` can land on: its number, the
    start of its range, and 1 for every call or a rate."""
    if position is None or position == "#*" or position.startswith("~"):
        return 1
    try:
        return int(position[1:].split("-", 1)[0])
    except ValueError:
        raise SearchError(f"{_shown(position)} is not a call of a tool") from None


def _lands(reach: Mapping[str, int], changes: Sequence[Change]) -> bool:
    return all(reach.get(change.tool or "", 0) >= _first_call(change.call) for change in changes)


def _fitting(seen: Seen, condition: Condition) -> list[str]:
    """The cases a condition could run on, in the map's order: those not set aside on which the
    map says every tool change can land, and where there is none, those that call each tool the
    condition names at all."""
    aside = set(seen.set_aside)
    on_tools = [change for change in condition.changes if change.surface == "tool"]
    open_cases = [case for case in seen.control if case not in aside]
    fits = [case for case in open_cases if _lands(seen.control[case], on_tools)]
    if fits:
        return fits
    return [case for case in open_cases
            if all(seen.control[case].get(change.tool or "", 0) >= 1 for change in on_tools)]


def cases_for(seen: Seen, condition: Condition, *, rng: random.Random) -> tuple[str, ...]:
    """The cases a condition runs on: ``cases_per_condition`` of those not set aside on which the
    control's map says every tool change can land, drawn with ``rng``, in the map's order; all of
    them when no more than that fit. A change with no tool lands on any case. Where no case fits
    by the map, the draw is over the cases that call each tool named at all, so a change at a call
    the control never saw has somewhere to run. A condition no case can take gets none."""
    if not isinstance(condition, Condition):
        raise SearchError(f"cases_for is given a condition, not {_shown(condition)}")
    fits = _fitting(seen, condition)
    if len(fits) <= seen.cases_per_condition:
        return tuple(fits)
    drawn = set(rng.sample(fits, seen.cases_per_condition))
    return tuple(case for case in fits if case in drawn)


# ---------------------------------------------------------------------------
# the space the two built-in strategies and coverage share
# ---------------------------------------------------------------------------


class _Space:
    """Every single change the control's map makes reachable, in a fixed order, and which pairs
    of them one case can hold. Built from ``Seen``'s public fields and nothing else."""

    def __init__(self, seen: Seen) -> None:
        aside = set(seen.set_aside)
        on = seen.catalogue
        cases = [case for case in seen.control if case not in aside]
        self.singles: list[Change] = []
        self.holders: list[int] = []
        self.reach: dict[str, int] = {}
        everywhere = (1 << len(cases)) - 1
        for tool, faults in on.tools.items():
            counts = [seen.control[case].get(tool, 0) for case in cases]
            top = min(max(counts, default=0), on.max_call)
            self.reach[tool] = top
            for call in range(1, top + 1):
                holders = sum(1 << at for at, count in enumerate(counts) if count >= call)
                for fault in faults:
                    self.singles.append(Change(surface="tool", tool=tool, fault=fault,
                                               call=f"#{call}"))
                    self.holders.append(holders)
        if cases:
            for word in on.inputs:
                self.singles.append(Change(surface="input", tool=None, fault=word, call=None))
                self.holders.append(everywhere)
            for setting, values in on.env.items():
                for value in values:
                    self.singles.append(Change(surface="env", tool=setting, fault=value,
                                               call=None))
                    self.holders.append(everywhere)
        self.index = {change: at for at, change in enumerate(self.singles)}

    def holds(self, first: int, second: int) -> bool:
        """Whether two singles make a pair worth drawing: one case can hold both, and they are
        not two changes on one call of one tool or two values of one setting."""
        if first == second or not self.holders[first] & self.holders[second]:
            return False
        a, b = self.singles[first], self.singles[second]
        if a.surface == b.surface == "tool":
            return (a.tool, a.call) != (b.tool, b.call)
        if a.surface == b.surface == "env":
            return a.tool != b.tool
        return True

    def pairs(self) -> list[tuple[int, int]]:
        return [(first, second) for first in range(len(self.singles))
                for second in range(first + 1, len(self.singles)) if self.holds(first, second)]

    def slot(self, condition: object) -> tuple[int, ...] | None:
        """Where a condition sits in the space, as the places of its one or two singles, or
        ``None`` for a condition that is not in it."""
        if not isinstance(condition, Condition):
            return None
        places = sorted({self.index.get(change, -1) for change in condition.changes})
        if len(places) != len(condition.changes) or not places or places[0] < 0:
            return None
        if len(places) == 1:
            return (places[0],)
        if len(places) == 2 and self.holds(places[0], places[1]):
            return (places[0], places[1])
        return None

    def condition(self, slot: tuple[int, ...]) -> Condition:
        return _ordered(self.singles[at] for at in slot)


def _proposed(space: _Space, seen: Seen) -> set[tuple[int, ...]]:
    """What a built-in strategy leaves out as proposed already: everything in ``seen.proposals``
    but an entry logged ``not run``, which had no run to pay for it and may be tried again."""
    slots = {space.slot(entry.condition) for entry in seen.proposals if entry.state != "not run"}
    return {slot for slot in slots if slot is not None}


def _batch(seen: Seen, budget: int) -> int:
    """How many conditions a built-in strategy hands over at once: as many as the runs left pay
    for at a full set of cases each, and one when less than a full set is left."""
    if budget <= 0:
        return 0
    return max(1, budget // seen.cases_per_condition)


# ---------------------------------------------------------------------------
# screen
# ---------------------------------------------------------------------------


def _matched(takes: Mapping[str, Sequence[str]]) -> dict[str, str]:
    """A largest pairing of tools with faults in which no tool and no fault comes twice. A fault
    only some tools take is not crowded out by one any tool takes: a tool gives up its fault for
    another when that lets one more tool in."""
    held_by: dict[str, str] = {}

    def place(tool: str, tried: set[str]) -> bool:
        for fault in takes[tool]:
            if fault in tried:
                continue
            tried.add(fault)
            if fault not in held_by or place(held_by[fault], tried):
                held_by[fault] = tool
                return True
        return False

    for tool in takes:
        place(tool, set())
    return {tool: fault for fault, tool in held_by.items()}


def _first_pass(takes: Mapping[str, Sequence[str]]) -> tuple[list[tuple[str, str]], int]:
    """Every (tool, fault) the tools take, in ``screen``'s order, and how many of them open it.

    The opening is the shortest run in which every tool and every fault has appeared: the largest
    pairing first, so the first proposals are each a new tool and a new fault, then one proposal
    for each tool and each fault the pairing left out. The rest follow, the least-tried tool
    first and, on a tie, the least-tried fault."""
    tools = {tool: at for at, tool in enumerate(takes)}
    faults = {fault: at for at, fault in
              enumerate(dict.fromkeys(fault for tool in takes for fault in takes[tool]))}
    on_tool = dict.fromkeys(tools, 0)
    on_fault = dict.fromkeys(faults, 0)
    order: list[tuple[str, str]] = []

    def take(tool: str, fault: str) -> None:
        order.append((tool, fault))
        on_tool[tool] += 1
        on_fault[fault] += 1

    pairing = _matched(takes)
    for tool in tools:
        if tool in pairing:
            take(tool, pairing[tool])
    for tool in tools:
        if tool not in pairing:
            take(tool, min(takes[tool], key=lambda fault: (on_fault[fault], faults[fault])))
    for fault in faults:
        if on_fault[fault] == 0:
            takers = [tool for tool in tools if fault in takes[tool]]
            take(min(takers, key=lambda tool: (on_tool[tool], tools[tool])), fault)
    opening = len(order)
    taken = set(order)
    left = [(tool, fault) for tool in tools for fault in takes[tool]
            if (tool, fault) not in taken]
    while left:
        following = min(left, key=lambda pair: (on_tool[pair[0]], on_fault[pair[1]],
                                                tools[pair[0]], faults[pair[1]]))
        left.remove(following)
        take(*following)
    return order, opening


class Screen:
    """Every single change the control's map makes reachable, each once, in a fixed order, with a
    probability of 1. It reads no outcome and draws nothing from the generator.

    The order: every tool and every fault once, in as few proposals as that takes; every input
    operator; every listed value of each setting; the rest of the first call of each tool; then
    the same faults on the second call of each tool that reaches one, and so on up to
    ``max_call``. Asked again, it goes on from where the proposals so far leave off."""

    def propose(self, seen: Seen, budget: int, *, rng: random.Random) -> list[Proposal]:
        space = _Space(seen)
        done = _proposed(space, seen)
        left = [(at, reason) for at, reason in _screen_order(space, seen) if (at,) not in done]
        return [Proposal(condition=space.condition((at,)), reason=reason, probability=1.0)
                for at, reason in left[:_batch(seen, budget)]]


def _screen_order(space: _Space, seen: Seen) -> list[tuple[int, str]]:
    """Each single's place in the space, in ``screen``'s order, with the reason it is there."""
    takes = {tool: faults for tool, faults in seen.catalogue.tools.items()
             if faults and space.reach.get(tool, 0) >= 1}
    pairs, opening = _first_pass(takes)

    def at(tool: str, call: int, fault: str) -> int:
        return space.index[Change(surface="tool", tool=tool, fault=fault, call=f"#{call}")]

    order = [(at(tool, 1, fault), f"every tool and every fault once: {fault} on {tool}")
             for tool, fault in pairs[:opening]]
    for place, change in enumerate(space.singles):
        if change.surface == "input":
            order.append((place, f"every input operator once: {change.fault}"))
    for place, change in enumerate(space.singles):
        if change.surface == "env":
            order.append((place, "every listed value of every setting once: "
                                 f"{change.tool} as {change.fault}"))
    order += [(at(tool, 1, fault), f"the rest of the first call of each tool: {fault} on {tool}")
              for tool, fault in pairs[opening:]]
    for call in range(2, max(space.reach.values(), default=0) + 1):
        order += [(at(tool, call, fault), f"call {call} of each tool that reaches it: {fault} "
                                          f"on {tool}")
                  for tool, fault in pairs if space.reach[tool] >= call]
    return order


# ---------------------------------------------------------------------------
# random
# ---------------------------------------------------------------------------


class Random:
    """Single changes and pairs of them, as one set, drawn uniformly with the generator it is
    given and never twice. The probability it gives each is 1 over the size of the whole set,
    the chance of that condition on a first draw, whatever has been drawn since.

    The set is every reachable single change and every pair of them that one case not set aside
    can hold, less two changes on one call of one tool and two values of one setting. It reads no
    outcome."""

    def propose(self, seen: Seen, budget: int, *, rng: random.Random) -> list[Proposal]:
        space = _Space(seen)
        slots: list[tuple[int, ...]] = [(at,) for at in range(len(space.singles))]
        slots += space.pairs()
        done = _proposed(space, seen)
        left = [slot for slot in slots if slot not in done]
        count = min(len(left), _batch(seen, budget))
        if count == 0:
            return []
        size = len(slots)
        reason = (f"drawn uniformly from the {size} single changes and pairs" if size > 1
                  else "the one change in reach")
        return [Proposal(condition=space.condition(slot), reason=reason, probability=1 / size)
                for slot in rng.sample(left, count)]


# ---------------------------------------------------------------------------
# loading a strategy
# ---------------------------------------------------------------------------


def load_strategy(name_or_path: str) -> Strategy:
    """The strategy a word or an import path names. ``screen`` and ``random`` are built in.
    ``module:Name`` is imported: a class is made with no arguments, and anything else with a
    ``propose`` is used as it is. Nothing of the strategy runs but its import and its making.

    Whatever goes wrong is one ``SearchError`` of one line: a word that is neither, a module or a
    name that is not there, an import or a making that raises, a class that needs arguments, a
    thing with no ``propose``. Ctrl-C passes through."""
    if not isinstance(name_or_path, str):
        raise SearchError(f"a strategy is named by a word or an import path, not "
                          f"{_shown(name_or_path)}")
    if name_or_path == "screen":
        return Screen()
    if name_or_path == "random":
        return Random()
    if name_or_path in _NOT_BUILT:
        raise SearchError(f"the strategy {_shown(name_or_path)} is not in this version of Break: "
                          "use screen or random, or a strategy of your own written module:Name")
    module_name, colon, attribute = name_or_path.partition(":")
    if not colon or not module_name or not attribute or ":" in attribute:
        raise SearchError(f"{_shown(name_or_path)} is not a strategy: use screen or random, or a "
                          "strategy of your own written module:Name")
    try:
        found: Any = importlib.import_module(module_name)
    except (Exception, SystemExit) as wrong:
        raise SearchError(f"the strategy {_shown(name_or_path)} could not be loaded: importing "
                          f"{module_name} raised {_one_line(wrong)}") from None
    for part in attribute.split("."):
        try:
            found = getattr(found, part)
        except (Exception, SystemExit):
            raise SearchError(f"the strategy {_shown(name_or_path)} could not be loaded: "
                              f"{module_name} has no {attribute}") from None
    if not callable(getattr(found, "propose", None)):
        raise SearchError(f"{_shown(name_or_path)} is not a strategy: it has no propose")
    if not isinstance(found, type):
        return found  # type: ignore[no-any-return]
    try:
        made: Strategy = found()
    except (Exception, SystemExit) as wrong:
        raise SearchError(f"the strategy {_shown(name_or_path)} could not be made with no "
                          f"arguments: {_one_line(wrong)}") from None
    return made


# ---------------------------------------------------------------------------
# the log on disk
# ---------------------------------------------------------------------------


def _plain(value: object) -> Any:
    """A refused proposal's reason or probability as JSON can hold it: itself when it is text, a
    whole number, true, false or nothing, or a number JSON has; its own text for a number JSON
    has not; and its type's name in angle brackets for anything else."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    return f"<{type(value).__name__}>"


def _line(entry: LogEntry) -> str:
    """One entry as one line of the file: plain ASCII, so no character of a reason or a name can
    break a line, and the same bytes for the same entry every time."""
    held = {
        "strategy": entry.strategy,
        "condition": None if entry.condition is None else _name_of(entry.condition),
        "reason": _plain(entry.reason),
        "probability": _plain(entry.probability),
        "state": entry.state,
        "cases": list(entry.cases),
    }
    return json.dumps(held, ensure_ascii=True, allow_nan=False) + "\n"


def _append(path: Path, entries: Sequence[LogEntry]) -> None:
    """Add entries to the end of the file and see them onto the disk before returning."""
    with open(path, "a", encoding="utf-8", newline="\n") as file:
        file.write("".join(_line(entry) for entry in entries))
        file.flush()
        os.fsync(file.fileno())


def _condition_named(text: str) -> Condition:
    """A condition from its name as the log wrote it, read by its form alone: the settings'
    ``[vary.env]`` table is not needed, and neither is the catalogue."""
    if text == "":
        return Condition(changes=())
    pieces: list[str] = []
    for piece in text.split(_JOIN):
        if piece.split(":", 1)[0] in _SURFACES and ":" in piece:
            pieces.append(piece)
        elif pieces and pieces[-1].startswith("env:"):
            pieces[-1] += _JOIN + piece  # a setting's value that holds the join itself
        else:
            raise SearchError(f"{_shown(piece)} is not a change")
    found: list[Change] = []
    for piece in pieces:
        surface, rest = piece.split(":", 1)
        if surface == "tool":
            form = _TOOL_PIECE.fullmatch(rest)
            if form is None:
                raise SearchError(f"{_shown(piece)} is not a change")
            found.append(Change(surface="tool", tool=form.group(1), fault=form.group(3),
                                call=form.group(2)))
        elif surface == "input":
            found.append(Change(surface="input", tool=None, fault=rest, call=None))
        elif surface == "user":
            move, at, turn = rest.rpartition("@")
            found.append(Change(surface="user", tool=None, fault=move, call=at + turn))
        elif surface == "model":
            fault, mark, call = rest.partition("#")
            found.append(Change(surface="model", tool=None, fault=fault, call=mark + call))
        else:
            setting, _, value = rest.partition("=")
            found.append(Change(surface="env", tool=setting, fault=value, call=None))
    condition = Condition(changes=tuple(found))
    if _name_of(condition) != text:
        raise SearchError(f"{_shown(text)} is not a condition's name")
    return condition


def _no_constant(word: str) -> Any:
    raise ValueError(f"{word} is not JSON")


def read_log(path: str | os.PathLike[str]) -> tuple[LogEntry, ...]:
    """The proposals a log file holds, in order, as the entries the stage logged. A file that is
    not there yet holds none. A line that is not an entry is refused, named by its number."""
    where = Path(path)
    try:
        text = where.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ()
    entries: list[LogEntry] = []
    for number, line in enumerate(text.split("\n"), 1):
        if not line.strip():
            continue
        try:
            held = json.loads(line, parse_constant=_no_constant)
            if not isinstance(held, dict):
                raise ValueError("not a table")
            unknown = sorted(set(held) ^ {"strategy", "condition", "reason", "probability",
                                          "state", "cases"})
            if unknown:
                raise ValueError(f"it has or lacks {', '.join(unknown)}")
            condition = held["condition"]
            if condition is not None and not isinstance(condition, str):
                raise ValueError("its condition is not a name")
            if not isinstance(held["cases"], list):
                raise ValueError("its cases are not a list")
            entries.append(LogEntry(
                strategy=held["strategy"],
                condition=None if condition is None else _condition_named(condition),
                reason=held["reason"], probability=held["probability"], state=held["state"],
                cases=tuple(held["cases"])))
        except ValueError as wrong:
            raise SearchError(f"line {number} of {where.name} is not a logged proposal: "
                              f"{' '.join(str(wrong).split())}") from None
    return tuple(entries)


# ---------------------------------------------------------------------------
# the stage
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Stage:
    """How a search stage ended: ``seen``, the hunt as it now stands, its budget everything that
    is left, a reserve included; ``log``, the stage's own proposals in the order proposed; and
    ``stopped``, why the stage was stopped (a ``SearchError`` for a batch that was refused, an
    ``InstrumentError`` for a strategy that raised) or ``None`` for one that ended of itself."""

    seen: Seen
    log: tuple[LogEntry, ...]
    stopped: Exception | None


def _outside(condition: Condition, on: Allowed) -> tuple[str, str] | None:
    """The first change of a condition that is outside what the settings allow, by its whole
    name, and why; ``None`` when every change is within them."""
    for change in condition.changes:
        text = _name_of(change)
        if change.surface == "tool":
            tool = change.tool or ""
            if tool not in on.tools:
                return text, f"{_shown(tool)} is off or has no line in the settings"
            if change.fault not in on.tools[tool]:
                if change.fault in on.faults_off:
                    return text, f"{change.fault} is turned off in the settings"
                return text, f"{change.fault} cannot land on {_shown(tool)}"
            first = _first_call(change.call)
            if first > on.max_call:
                return text, (f"call {first} is past the settings' max_call of {on.max_call}")
        elif change.surface == "input":
            if change.fault not in on.inputs:
                return text, f"{change.fault} is turned off in the settings"
        elif change.surface == "env":
            if change.fault not in on.env.get(change.tool or "", ()):
                return text, "the settings do not list that value"
        else:
            return text, ("no search can propose a change to the conversation or to the model's "
                          "own calls in this version of Break")
    return None


def search_stage(strategy: Strategy, *, name: str, seen: Seen, rng: random.Random,
                 run: Callable[[Sequence[LogEntry]], Iterable[SeenRun]],
                 log: str | os.PathLike[str] | None = None, reserve: int = 0) -> Stage:
    """Run one search stage: ask ``strategy`` for proposals until its batch is empty or holds
    nothing new, or the runs left cannot pay for the next condition.

    ``name`` is the strategy's name as the settings gave it, which the log and every run's
    selection carry. ``seen`` is the hunt so far. ``rng`` is the search seed's generator: the
    strategy is handed it as it is, and the cases each condition runs on are drawn with it.
    ``run(entries)`` runs each entry's condition once on each of its cases and returns one
    ``SeenRun`` a run; what it raises passes through untouched, with the log already written.
    ``log`` is the file each proposal is added to before its run; with none, nothing is written.
    ``reserve`` is how many runs the stage leaves unspent for shrinking.

    The strategy is asked with the runs it may still spend, the reserve already out, and shown a
    ``Seen`` whose budget says the same. It is not asked at all with none to spend."""
    if not isinstance(name, str) or not name or name.splitlines() != [name]:
        raise SearchError(f"a strategy's name is one line of text, not {_shown(name)}")
    if not isinstance(seen, Seen):
        raise SearchError(f"a search stage starts from a Seen, not {_shown(seen)}")
    held_back = _whole(reserve, least=0)
    if held_back is None:
        raise SearchError(f"reserve is {_shown(reserve)}, not a whole number of runs")
    path = None if log is None else Path(log)

    runs = list(seen.runs)
    proposals = list(seen.proposals)
    entries: list[LogEntry] = []
    known = {""} | {_key(row.condition) for row in runs}
    known |= {_key(entry.condition) for entry in proposals
              if entry.state == "run" and entry.condition is not None}
    spent = 0
    quiet = 0
    stopped: Exception | None = None

    def view(budget: int) -> Seen:
        return Seen(control=seen.control, runs=tuple(runs), proposals=tuple(proposals),
                    budget=budget, catalogue=seen.catalogue, set_aside=seen.set_aside,
                    cases_per_condition=seen.cases_per_condition)

    def keep(batch: Sequence[LogEntry]) -> None:
        if path is not None and batch:
            _append(path, batch)
        entries.extend(batch)
        proposals.extend(batch)

    while (left := seen.budget - held_back - spent) > 0:
        shown = view(left)
        try:
            batch = strategy.propose(shown, left, rng=rng)
        except (Exception, SystemExit) as wrong:
            stopped = InstrumentError(f"the strategy {_shown(name)} raised {_one_line(wrong)}")
            break
        if not isinstance(batch, list):
            stopped = SearchError(f"the strategy {_shown(name)} handed back {_shown(batch)}, "
                                  "not a list of proposals")
            break
        if not batch:
            break

        read: list[tuple[Condition, str, float]] = []
        refusal: SearchError | None = None
        for item in batch:
            try:
                read.append(_checked(item, name, seen.catalogue))
            except SearchError as wrong:
                refusal = refusal or wrong
        if refusal is not None:
            keep([_refused(item, name) for item in batch])
            stopped = refusal
            break

        logged: list[LogEntry] = []
        to_run: list[LogEntry] = []
        new = False
        cannot_pay = False
        for condition, reason, probability in read:
            text = _name_of(condition)
            state = "not run"
            cases: tuple[str, ...] = ()
            if text in known:
                state = "dropped"
            else:
                known.add(text)
                new = True
                fits = _fitting(shown, condition)
                cost = min(len(fits), seen.cases_per_condition)
                if cost > left:
                    cannot_pay = True
                if fits and not cannot_pay:
                    state, cases = "run", cases_for(shown, condition, rng=rng)
                    left -= cost
            entry = LogEntry(strategy=name, condition=condition, reason=reason,
                             probability=probability, state=state, cases=cases)
            logged.append(entry)
            if state == "run":
                to_run.append(entry)
        keep(logged)

        handed = sum(len(entry.cases) for entry in to_run)
        rows: list[SeenRun] = []
        if to_run:
            rows = list(run(tuple(to_run)))
            for row in rows:
                if not isinstance(row, SeenRun):
                    raise SearchError(f"run handed back {_shown(row)}, not a SeenRun")
            runs.extend(rows)
            spent += len(rows)
        if not new or cannot_pay or len(rows) < handed:
            break
        quiet = 0 if rows else quiet + 1
        if quiet >= _ASKS_WITH_NOTHING_RUN:
            stopped = SearchError(f"the strategy {_shown(name)} was asked {quiet} times in a row "
                                  "and proposed nothing that could run")
            break

    return Stage(seen=view(max(0, seen.budget - spent)), log=tuple(entries), stopped=stopped)


def _refused(item: object, name: str) -> LogEntry:
    """What the log keeps of one item of a refused batch: whatever it held, as it was handed
    over."""
    reason: Any = getattr(item, "reason", None)
    probability: Any = getattr(item, "probability", None)
    return LogEntry(strategy=name, condition=_named(getattr(item, "condition", None)),
                    reason=reason, probability=probability, state="refused", cases=())


def _checked(item: object, name: str, on: Allowed) -> tuple[Condition, str, float]:
    """One thing a strategy handed back, read as a proposal: its condition written canonically,
    its reason and its probability, or the refusal of the first of them that is not right."""
    missing = [field for field in ("condition", "reason", "probability")
               if not hasattr(item, field)]
    if missing:
        raise SearchError(f"the strategy {_shown(name)} handed back {_shown(item)}, which has no "
                          f"{missing[0]}: a proposal holds a condition, a reason and a "
                          "probability")
    handed: Any = item
    probability, reason = handed.probability, handed.reason
    if not _is_probability(probability):
        raise SearchError(f"the strategy {_shown(name)} gave a probability of "
                          f"{_shown(probability)}, not a number above 0 and at most 1")
    if not _is_reason(reason):
        raise SearchError(f"the strategy {_shown(name)} gave {_shown(reason)} as its reason, "
                          "not one line of text")
    try:
        condition = _canonical(handed.condition)
    except SearchError as wrong:
        raise SearchError(f"the strategy {_shown(name)} proposed something that is not a "
                          f"condition: {wrong}") from None
    trouble = _outside(condition, on)
    if trouble is not None:
        raise SearchError(f"the strategy {_shown(name)} proposed {json.dumps(trouble[0])}, "
                          f"which is outside what the settings allow: {trouble[1]}")
    return condition, reason, probability


# ---------------------------------------------------------------------------
# the score
# ---------------------------------------------------------------------------


def score(seen: Seen, condition: Condition) -> float:
    """How a condition did: failed runs over counted runs under it, less failed control runs over
    counted control runs on the cases it has a counted run on. Each side is pooled, so a case
    with more runs weighs more, and a run not counted is left out of both.

    Refused: a condition with a run on a case set aside, one with no counted run, and one whose
    cases have no counted control run to compare with."""
    if not isinstance(condition, Condition):
        raise SearchError(f"score is given a condition, not {_shown(condition)}")
    text = _key(condition)
    said = _shown(text) if text else "the control"
    own = [row for row in seen.runs if _key(row.condition) == text]
    aside = sorted({row.case for row in own} & set(seen.set_aside))
    if aside:
        raise SearchError(f"{said} ran on {_shown(aside[0])}, a case set aside: it already fails "
                          "with no change, so its runs say nothing of the condition")
    counted = [row for row in own if row.outcome != "not counted"]
    if not counted:
        raise SearchError(f"{said} has no counted run to score")
    cases = {row.case for row in counted}
    control = [row for row in seen.runs
               if not row.condition.changes and row.case in cases
               and row.outcome != "not counted"]
    if not control:
        raise SearchError(f"{said} has no counted control run on its cases to compare with")
    failed = sum(row.outcome == "failed" for row in counted)
    failed_control = sum(row.outcome == "failed" for row in control)
    return failed / len(counted) - failed_control / len(control)


# ---------------------------------------------------------------------------
# shrink
# ---------------------------------------------------------------------------


class _OutOfTries(Exception):
    """The cap on ``failures`` calls is spent."""


def shrink(condition: Condition, *, failures: Callable[[Condition], int],
           calls: Mapping[str, int], tries: int | None = None) -> Condition:
    """The smallest version of a candidate that still fails about as often.

    ``failures(condition)`` runs a condition on the candidate's cases and returns how many of
    those runs failed. The candidate itself is asked about first, and the line is its count less
    one run: the line stays there, however a smaller condition does. Then, round after round, each
    change is taken out in the condition's order, and the first smaller condition that fails at
    least as often as the line is kept. When no change can go, a fault on every call (``#*``) is
    tried as each single call of its tool, from 1 to ``calls[tool]``, and the first that holds the
    line replaces it. It ends when nothing more can go, or when ``tries`` calls of ``failures``
    are spent, and returns the smallest condition it kept.

    A candidate with nothing to try, one change that is not on every call, costs no run. What it
    returns holds only changes of the candidate, or a single call of an every-call change in it.
    It is given no history: it may try a condition a search already ran."""
    if not isinstance(condition, Condition):
        raise SearchError(f"shrink is given a condition, not {_shown(condition)}")
    if not all(isinstance(change, Change) for change in condition.changes):
        raise SearchError("shrink is given a condition that holds something that is not a change")
    if not isinstance(calls, Mapping):
        raise SearchError(f"calls is {_shown(calls)}, not each tool's reach")
    cap = None if tries is None else _whole(tries, least=0)
    if tries is not None and cap is None:
        raise SearchError(f"tries is {_shown(tries)}, not a whole number of runs' worth of asks")
    asked = 0

    def ask(candidate: Condition) -> int:
        nonlocal asked
        if cap is not None and asked >= cap:
            raise _OutOfTries
        asked += 1
        count = failures(candidate)
        try:
            return operator.index(count)
        except TypeError:
            raise SearchError(f"failures handed back {_shown(count)}, not a count of failed "
                              "runs") from None

    def reach(tool: str | None) -> int:
        return _whole(calls.get(tool or "", 0), least=0) or 0

    current = _ordered(condition.changes)
    every_call = [change for change in current.changes
                  if change.surface == "tool" and change.call == "#*" and reach(change.tool) >= 1]
    if len(current.changes) < 2 and not every_call:
        return current
    try:
        line = ask(current) - 1
        while True:
            kept: Condition | None = None
            if len(current.changes) > 1:
                for change in current.changes:
                    smaller = _ordered(c for c in current.changes if c != change)
                    if ask(smaller) >= line:
                        kept = smaller
                        break
            if kept is None:
                kept = _one_call(current, ask, reach, line)
            if kept is None:
                return current
            current = kept
    except _OutOfTries:
        return current


def _one_call(current: Condition, ask: Callable[[Condition], int],
              reach: Callable[[str | None], int], line: int) -> Condition | None:
    """``current`` with one of its every-call changes narrowed to the first single call that
    holds the line, or ``None`` when none does."""
    for change in current.changes:
        if change.surface != "tool" or change.call != "#*":
            continue
        rest = [c for c in current.changes if c != change]
        for call in range(1, reach(change.tool) + 1):
            single = Change(surface="tool", tool=change.tool, fault=change.fault,
                            call=f"#{call}")
            if single in rest:
                continue  # that is the every-call change taken out, which did not hold
            narrowed = _ordered([*rest, single])
            if ask(narrowed) >= line:
                return narrowed
    return None


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Count:
    """How much of something a search could reach, tried and left: ``tried`` plus ``untried`` is
    ``reachable``."""

    reachable: int
    tried: int
    untried: int


@dataclass(frozen=True, kw_only=True)
class Coverage:
    """What a hunt looked at and what it did not, as data.

    ``per_tool`` and ``per_fault`` count the reachable single tool changes on each tool the
    settings allow and under each fault some tool takes. The rest is what was not looked at, each
    empty or zero when it does not apply: ``never_called``, the tools no case called in the
    control; ``past_limit``, each tool a case not set aside called more often than ``max_call``,
    with the most calls of it; ``faults_off``, the tool faults the settings leave out;
    ``set_aside``, the cases no search runs on; ``singles_untried`` and ``pairs_untried``, how
    many reachable single changes, and pairs of them one case can hold, have no run."""

    per_tool: Mapping[str, Count]
    per_fault: Mapping[str, Count]
    never_called: tuple[str, ...]
    past_limit: Mapping[str, int]
    faults_off: tuple[str, ...]
    set_aside: tuple[str, ...]
    singles_untried: int
    pairs_untried: int


def coverage(seen: Seen) -> Coverage:
    """What the hunt so far has tried of the space ``screen`` and ``random`` draw on. Tried means
    it has a run: a proposal that was dropped, refused or not run does not count, a pair is not a
    try of either of its changes, and a run of a condition outside the space is a try of
    nothing."""
    space = _Space(seen)
    on = seen.catalogue
    tried = {space.slot(row.condition) for row in seen.runs}
    reachable_tool = dict.fromkeys(on.tools, 0)
    tried_tool = dict.fromkeys(on.tools, 0)
    faults = dict.fromkeys(fault for takes in on.tools.values() for fault in takes)
    reachable_fault = dict.fromkeys(faults, 0)
    tried_fault = dict.fromkeys(faults, 0)
    singles_tried = 0
    for at, change in enumerate(space.singles):
        has_run = (at,) in tried
        singles_tried += has_run
        if change.surface == "tool" and change.tool is not None:
            reachable_tool[change.tool] += 1
            reachable_fault[change.fault] += 1
            tried_tool[change.tool] += has_run
            tried_fault[change.fault] += has_run
    pairs = space.pairs()
    pairs_tried = sum(pair in tried for pair in pairs)

    aside = set(seen.set_aside)
    most = {tool: max((reach.get(tool, 0) for case, reach in seen.control.items()
                       if case not in aside), default=0) for tool in on.tools}
    return Coverage(
        per_tool=MappingProxyType({
            tool: Count(reachable=reachable_tool[tool], tried=tried_tool[tool],
                        untried=reachable_tool[tool] - tried_tool[tool]) for tool in on.tools}),
        per_fault=MappingProxyType({
            fault: Count(reachable=reachable_fault[fault], tried=tried_fault[fault],
                         untried=reachable_fault[fault] - tried_fault[fault])
            for fault in faults}),
        never_called=tuple(tool for tool in on.tools
                           if not any(reach.get(tool, 0) for reach in seen.control.values())),
        past_limit=MappingProxyType({tool: top for tool, top in most.items()
                                     if top > on.max_call}),
        faults_off=on.faults_off,
        set_aside=tuple(seen.set_aside),
        singles_untried=len(space.singles) - singles_tried,
        pairs_untried=len(pairs) - pairs_tried)
