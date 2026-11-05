"""What the search module's tests share: `Seen` fixtures, a scripted `run`, real runs of the scripted agents, and how a test
reads a log.

`poisson_break.search` is imported lazily, so on a tree without it each test fails on its own and the rest of the suite
still runs.

No run here goes through the runs module, which does not exist yet. `search_stage` takes its `run` as a callable, so a test
hands in `Scripted` (rows from a table of outcomes) or `RealRuns` (a scripted agent under a real `Session`, read by the real
`watch` and `judge`), and the runs module goes behind the same callable later.

A condition is compared by its canonical name throughout, since a `LogEntry` is free to hold a condition or its name.
"""

from __future__ import annotations

import importlib
import random
from collections.abc import Callable, Iterable, Mapping, Sequence
from types import ModuleType, SimpleNamespace
from typing import Any

from tests.changes_support import TOOL_FAULTS, changes

NAME = "screen"
SEARCH_SEED = 20261005

# §9.4's own [vary] table, with `slow` and `malformed` taken out of the small one so that a space can be worked by hand.
FAULTS = ("error", "timeout", "lost_reply")
INPUTS = ("typos", "reordered")
ENV = {"inventory": ("full", "empty"), "region": ("us",)}

TOOLS: dict[str, Any] = {
    "a": "read",
    "b": "read",
    "w": {"class": "write", "repeatable": True},
    "silent": "off",
}

CONTROL = {"c1": {"a": 2, "w": 1}, "c2": {"a": 1, "b": 1}}

TOOL_CALLS_ONLY = {"tool_calls": True, "model_calls": False, "conversation": False}


def search() -> ModuleType:
    return importlib.import_module("poisson_break.search")


def interfaces() -> ModuleType:
    return importlib.import_module("poisson_break.interfaces")


def records() -> ModuleType:
    return importlib.import_module("poisson_break.records")


def apply_module() -> ModuleType:
    return importlib.import_module("poisson_break.apply")


def checks() -> ModuleType:
    return importlib.import_module("poisson_break.checks")


def agents() -> ModuleType:
    return importlib.import_module("tests.agents")


def condition(text: str, *, env: Mapping[str, Any] | None = None) -> Any:
    return changes().parse(text, env=ENV if env is None else env)


def text_of(what: Any) -> str:
    """A condition's canonical name, whether a test holds the object or its name."""
    return what if isinstance(what, str) else changes().name(what)


def caps(**over: bool) -> Any:
    return interfaces().Capabilities(**{**TOOL_CALLS_ONLY, **over})


def vary(faults: Iterable[str] = FAULTS, inputs: Iterable[str] = (), *, max_call: int = 3,
         env: Mapping[str, Any] | None = None, **rest: Any) -> dict[str, Any]:
    """The `[vary]` table as a mapping, as the settings file spells it."""
    table: dict[str, Any] = {"tools": list(faults), "inputs": list(inputs), "max_call": max_call, **rest}
    if env:
        table["env"] = {k: list(v) for k, v in env.items()}
    return table


def catalogue(faults: Iterable[str] = FAULTS, inputs: Iterable[str] = (), *, max_call: int = 3,
              env: Mapping[str, Any] | None = None, tools: Mapping[str, Any] | None = None, capabilities: Any = None,
              **rest: Any) -> Any:
    return search().allowed(vary=vary(faults, inputs, max_call=max_call, env=env, **rest),
                            tools=TOOLS if tools is None else tools,
                            capabilities=caps() if capabilities is None else capabilities)


def control_rows(control: Mapping[str, Any], *, repeats: int = 5, outcome: Callable[[str, int], str] | None = None,
                 first_seed: int = 1000) -> tuple[Any, ...]:
    """The control's rows: every case `repeats` times. `outcome(case, i)` gives each row's outcome, `ok` by default."""
    rows = []
    seed = first_seed
    for case in control:
        for i in range(repeats):
            rows.append(search().SeenRun(condition=changes().parse(""), case=case, seed=seed,
                                         outcome="ok" if outcome is None else outcome(case, i)))
            seed += 1
    return tuple(rows)


def seen(*, control: Mapping[str, Any] | None = None, runs: Sequence[Any] | None = None, proposals: Sequence[Any] = (),
         budget: int = 400, cat: Any = None, set_aside: Sequence[str] = (), cases_per_condition: int = 4) -> Any:
    """A `Seen`: the one place a test builds one."""
    control = CONTROL if control is None else control
    return search().Seen(control=control, runs=control_rows(control) if runs is None else tuple(runs),
                         proposals=tuple(proposals), budget=budget, catalogue=catalogue() if cat is None else cat,
                         set_aside=tuple(set_aside), cases_per_condition=cases_per_condition)


def proposal(text: str = "tool:a#1=error", *, reason: str = "because", probability: Any = 0.5, env: Any = None) -> Any:
    return search().Proposal(condition=condition(text, env=env), reason=reason, probability=probability)


def row(text: str, case: str, outcome: str = "ok", *, seed: int = 1) -> Any:
    return search().SeenRun(condition=condition(text), case=case, seed=seed, outcome=outcome)


def rng(seed: int = SEARCH_SEED) -> random.Random:
    return random.Random(seed)


# ---------------------------------------------------------------------------
# a run, scripted
# ---------------------------------------------------------------------------


class Scripted:
    """A `run` for `search_stage`: one row per case of each entry, outcomes from a table. Every call is kept, and whatever
    happened by then can be looked at from `during`."""

    def __init__(self, outcome: Callable[[str, str], str] | None = None, *, first_seed: int = 5000,
                 during: Callable[[Sequence[Any]], None] | None = None) -> None:
        self.outcome = outcome or (lambda _condition, _case: "ok")
        self.seed = first_seed
        self.batches: list[tuple[Any, ...]] = []
        self.during = during

    def __call__(self, entries: Sequence[Any]) -> list[Any]:
        entries = tuple(entries)
        self.batches.append(entries)
        if self.during is not None:
            self.during(entries)
        rows = []
        for entry in entries:
            text = text_of(entry.condition)
            for case in entry.cases:
                rows.append(search().SeenRun(condition=condition(text), case=case, seed=self.seed,
                                             outcome=self.outcome(text, case)))
                self.seed += 1
        return rows

    @property
    def ran(self) -> list[str]:
        """Every condition handed to run, in order."""
        return [text_of(e.condition) for batch in self.batches for e in batch]

    @property
    def runs(self) -> int:
        return sum(len(e.cases) for batch in self.batches for e in batch)


class Runaway(BaseException):
    """A loop that should have ended. A `BaseException`, so that nothing a stage catches hides it: a mistake that loops for ever
    fails the test that found it and does not hang the suite."""


class Bounded:
    """Hands a stage the strategy it was given, and stops it if it is asked far more often than any space here could need."""

    def __init__(self, strategy: Any) -> None:
        self.strategy = strategy
        self.asked = 0

    def propose(self, seen: Any, budget: int, *, rng: Any) -> Any:
        self.asked += 1
        if self.asked > 20000:
            raise Runaway("the stage went on asking")
        return self.strategy.propose(seen, budget, rng=rng)


def stage(strategy: Any, start: Any = None, *, name: str = NAME, run: Any = None, generator: Any = None, **over: Any) -> Any:
    return search().search_stage(Bounded(strategy), name=name, seen=seen() if start is None else start,
                                 rng=rng() if generator is None else generator, run=Scripted() if run is None else run,
                                 **over)


def logged(result: Any) -> list[tuple[str, str]]:
    """The log as (condition, state)."""
    return [(text_of(e.condition), e.state) for e in result.log]


def by_state(result: Any, state: str) -> list[str]:
    return [text_of(e.condition) for e in result.log if e.state == state]


def of_state(entries: Iterable[Any], state: str) -> list[Any]:
    return [e for e in entries if e.state == state]


class Fixed:
    """A strategy for one test: its batches in turn, then nothing. Whatever it was shown is kept, and a batch may be a
    callable that takes the `Seen`, or raise."""

    def __init__(self, *batches: Any) -> None:
        self.batches = list(batches)
        self.shown: list[tuple[Any, int, Any]] = []

    def propose(self, seen: Any, budget: int, *, rng: Any) -> Any:
        self.shown.append((seen, budget, rng))
        if len(self.shown) > 60:
            raise AssertionError("the stage went on asking long past where it should have stopped")
        if not self.batches:
            return []
        batch = self.batches.pop(0)
        if isinstance(batch, BaseException):
            raise batch
        return batch(seen) if callable(batch) else batch


def duck(text: Any = "tool:a#1=error", **over: Any) -> SimpleNamespace:
    """Anything a strategy might hand back that looks like a proposal."""
    fields = {"condition": condition(text) if isinstance(text, str) else text, "reason": "because", "probability": 0.5}
    return SimpleNamespace(**{**fields, **over})


# ---------------------------------------------------------------------------
# the first-pass spaces, by hand
# ---------------------------------------------------------------------------


def singles(control: Mapping[str, Any], faults: Mapping[str, Sequence[str]], *, max_call: int = 3) -> set[str]:
    """Every (tool, call, fault) the map reaches: the expected answer, worked out here and not read from the module."""
    out = set()
    for tool, on_it in faults.items():
        top = max((tools.get(tool, 0) for tools in control.values()), default=0)
        for call in range(1, min(top, max_call) + 1):
            out |= {f"tool:{tool}#{call}={fault}" for fault in on_it}
    return out


def space_of(strategy: Any, start: Any, *, seed: int = SEARCH_SEED) -> list[str]:
    """Everything `strategy` will propose given budget to spare, in order, by feeding its proposals back through a stage."""
    result = stage(strategy, start, generator=rng(seed))
    return [text_of(e.condition) for e in result.log if e.state == "run"]


ALL_TOOL_FAULTS = TOOL_FAULTS


# ---------------------------------------------------------------------------
# real runs: a scripted agent, a real session, the real checks
# ---------------------------------------------------------------------------

REQUESTS = {f"c{i}": {"id": f"c{i}", "input": f"Where is order {i}? Please refund it."} for i in range(1, 6)}

AGENT_TOOLS: dict[str, Any] = {"lookup_order": "read", "check_policy": "read",
                               "issue_refund": {"class": "write", "repeatable": True}}

# `slow` cannot fail these agents and sleeps five real seconds a run.
QUICK_FAULTS = tuple(f for f in TOOL_FAULTS if f != "slow")


class RealRuns:
    """A `run` for `search_stage` on a plain scripted agent: each case under a real `Session`, read by `watch` and `judge`,
    so an outcome here is one Break really decided. It also gives the control's map and rows, and counts failures on the
    same cases for `shrink`."""

    def __init__(self, agent: str, *, cases: Sequence[str] = ("c1", "c2", "c3", "c4"), fails: dict[str, Any] | None = None,
                 tools: dict[str, Any] | None = None) -> None:
        self.agent = getattr(agents(), agent)
        self.cases = tuple(cases)
        self.fails = fails
        self.tools = AGENT_TOOLS if tools is None else tools
        self.seed = 1
        self.tried: list[str] = []
        self.batches: list[tuple[Any, ...]] = []

    def one(self, text: str, case: str) -> tuple[str, Any]:
        a = apply_module()
        word = changes().marker(hunt="refund-agent-1", case=case)
        session = a.Session(changes().parse(text), seed=self.seed, tools=self.tools, marker=word)
        self.seed += 1
        as_seen = session.case(REQUESTS[case])
        real = {"lookup_order": lambda **_: "Order 7 shipped on Tuesday.",
                "check_policy": lambda **_: "Refunds within thirty days.",
                "issue_refund": lambda **_: "Refund issued."}
        wrapped = {tool: a.wrap(tool, fn) for tool, fn in real.items()}

        def run_agent() -> Any:
            with session:
                done = self.agent(as_seen, wrapped)
            return a.RunResult(reply=done.reply, outcome=None, tokens_in=None, tokens_out=None, ended="returned")

        finished = checks().watch(run_agent, case=as_seen, session=session, fails=self.fails)
        return checks().judge(finished).state, session

    def control(self) -> dict[str, dict[str, int]]:
        """The map the control makes: for each case, each tool and the most calls of it in one run."""
        out: dict[str, dict[str, int]] = {}
        for case in self.cases:
            state, session = self.one("", case)
            assert state == "ok", f"the agent fails with no change on {case}"
            counts: dict[str, int] = {}
            for call in session.calls:
                counts[call.tool] = max(counts.get(call.tool, 0), call.call)
            out[case] = counts
        return out

    def start(self, *, budget: int, faults: Sequence[str] = QUICK_FAULTS, inputs: Sequence[str] = (),
              cases_per_condition: int = 4) -> Any:
        """The `Seen` a search stage starts from: the control really run, its rows beside its map."""
        control = self.control()
        rows = []
        for case in self.cases:
            for _ in range(3):
                state, _session = self.one("", case)
                rows.append(search().SeenRun(condition=changes().parse(""), case=case, seed=self.seed - 1, outcome=state))
        return seen(control=control, runs=rows, budget=budget, cat=catalogue(faults, inputs, tools=self.tools),
                    cases_per_condition=cases_per_condition)

    def __call__(self, entries: Sequence[Any]) -> list[Any]:
        entries = tuple(entries)
        self.batches.append(entries)
        rows = []
        for entry in entries:
            text = text_of(entry.condition)
            self.tried.append(text)
            for case in entry.cases:
                state, _session = self.one(text, case)
                rows.append(search().SeenRun(condition=changes().parse(text), case=case, seed=self.seed - 1,
                                             outcome=state))
        return rows

    def failures(self, candidate: Any) -> int:
        """For `shrink`: how many of the same cases fail under a condition."""
        return sum(self.one(text_of(candidate), case)[0] == "failed" for case in self.cases)
