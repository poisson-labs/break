"""The four extension points: what a fault, a way in, a strategy and the user's own failure
check look like to the core.

Each is a protocol of keyword-only methods that pass frozen objects, never positional tuples,
so a field can be added without breaking an implementer. An implementation lives outside this
package and is found by name: a registration call for a fault, a ``kind`` for a way in, a
built-in name or an import path (``module:Name``) for a strategy, an import path for the
user's check. The core never imports an implementation it did not load by name from the
settings, and an implementation's exception is an instrument error: never a tool fault the
agent sees, never an agent failure.

Each interface carries a version constant, 1 today. An additive change (a new field with a
default, a new capability that defaults to cannot) keeps the number. Removing or renaming a
field or method, changing what an existing one means, or changing an invariant is a breaking
change: it bumps the number and is a core change with its own tests. No bump is expected
before 1.0.

The types an interface passes that another module defines are named in each docstring and
typed ``Any`` here: the call context and the two outcome forms belong to the catalogue
(``poisson_break.changes``); the session, the tool list's ``ToolInfo`` and the run result
``RunResult`` to the applying module (``poisson_break.apply``), from which the runs module
(``poisson_break.hunt``) hands them on; the search's view and the proposal to the search module
(``poisson_break.search``); the run view to the failure check (``poisson_break.checks``).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "FAULT_INTERFACE_VERSION",
    "TARGET_INTERFACE_VERSION",
    "STRATEGY_INTERFACE_VERSION",
    "CHECK_INTERFACE_VERSION",
    "Fault",
    "Capabilities",
    "Target",
    "Strategy",
    "Check",
]

FAULT_INTERFACE_VERSION = 1
"""Adding a fault (``Fault``)."""

TARGET_INTERFACE_VERSION = 1
"""Adding a way in (``Target``), an adapter or a proxy."""

STRATEGY_INTERFACE_VERSION = 1
"""Adding a strategy (``Strategy``), where a learned search plugs in too."""

CHECK_INTERFACE_VERSION = 1
"""The user's own failure check (``Check``)."""


@runtime_checkable
class Fault(Protocol):
    """A change to how a tool or the model behaves, registered from its own module.

    ``name`` is the word after ``=`` in a condition name and is unique within its surface (five
    words name both a tool fault and a model fault); ``surface`` is ``tool`` or ``model``;
    ``description`` is one line in plain words;
    ``parameters`` names each parameter with its one default; ``real_runs`` says whether the
    real tool runs, as the catalogue's table does.

    ``apply(call, *, real, params, rng)`` returns the outcome the agent should see: a result or
    an error, each a frozen object the core turns into whatever the way in presents. ``call``
    is the frozen call context (the tool's name, its arguments, the call number, the condition,
    the run's seed, the previous result of the same tool or none, which is what the real tool
    last returned, and the planted marker word or none) and is all the fault is given; ``real``
    runs the real tool once, taking no arguments, and ``apply`` calls it exactly as many times as
    ``real_runs`` declares, zero or one, which the core counts; ``params`` are the parameters
    for this run; ``rng`` is seeded by the core so that the same inputs give the same outcome,
    byte for byte. The fault writes no record: the core does.
    """

    name: str
    surface: str
    description: str
    parameters: Mapping[str, object]
    real_runs: bool

    def apply(self, call: Any, *, real: Callable[[], Any], params: Mapping[str, object],
              rng: Any) -> Any: ...


@dataclass(frozen=True, kw_only=True)
class Capabilities:
    """Which of the three things a way in can do: route tool calls through the session, fault
    the model's own calls, drive a scripted conversation. The core offers the user only what the
    way in can do, and refuses settings that ask for more at load. A fourth capability would be a
    new field whose default is cannot."""

    tool_calls: bool
    model_calls: bool
    conversation: bool


@runtime_checkable
class Target(Protocol):
    """A way in: how Break drives one kind of agent and reaches its tools.

    ``kind`` is the name the settings file uses; ``framework_versions`` are the framework
    versions the way in was checked against (empty for one that needs no framework).
    ``tools()`` lists the agent's tools before any run. ``capabilities()`` says which of the
    three it can do. ``run(case, session, *, seed, limits)`` runs the agent once, routing every
    tool call through ``session.call(tool, args, real)``, playing the case's turns where it can,
    and returns a frozen ``RunResult``: the reply, the outcome the target itself reports or
    none, tokens in and out where it can see them, and how the run ended (``returned``,
    ``raised``, or ``limit`` for its own step or turn limit). The core enforces the wall-clock
    limit, decides failure and writes the record; the way in decides nothing and never returns
    an outcome word of its own.

    ``session`` is one run's ``poisson_break.apply.Session``. In ``session.call``, ``args`` is
    the mapping of the call's arguments and ``real`` runs the real tool once and takes none. It
    returns what the agent should see, or raises ``ToolFailure``, which the way in catches to
    present in its own form. ``tools()`` lists each tool as a ``ToolInfo``. A way in that can
    fault the model's own calls will apply those changes through ``session.model_call(n,
    real)``; the core has no such method yet, and the first way in that needs it brings it.
    """

    kind: str
    framework_versions: Sequence[str]

    def tools(self) -> Sequence[Any]: ...

    def capabilities(self) -> Capabilities: ...

    def run(self, case: Any, session: Any, *, seed: int, limits: Any) -> Any: ...


@runtime_checkable
class Strategy(Protocol):
    """A search strategy: ``propose(seen, budget, *, rng)`` returns the next proposals.

    ``seen`` is the read-only view of the hunt so far: the control map, every run so far with
    its condition, case, seed and outcome, every proposal so far with its probability, the
    budget left and the catalogue the settings allow. ``budget`` is the number of runs the stage
    may still spend. ``rng`` is the search seed's generator, separate from every run seed. Each
    proposal carries the condition, the reason in one line and the probability the strategy gave
    that condition, in (0, 1]; a proposal without one is refused before any run. The core drops
    a repeated condition itself and spends no run on it; a strategy is not trusted to hold that.
    A strategy carries no state from one hunt to the next through Break.
    """

    def propose(self, seen: Any, budget: int, *, rng: Any) -> Sequence[Any]: ...


@runtime_checkable
class Check(Protocol):
    """The user's own failure check: ``check(run)`` returns ``None`` for ok or a failure kind,
    which Break records as ``own:<name>``.

    ``run`` is a read-only view: the case, the condition's name and changes with whether and
    where each applied, every tool call in order with its arguments, what the agent saw and
    whether the real tool ran, the agent's reply, the target's own outcome where there is one,
    tokens in and out where known, the run's seconds, and the kinds Break's own checks would
    give. A field a way in cannot fill is ``None``, never absent. The check runs once per run,
    after the run, only on a run Break's own checks found ok, and cannot change it. A check that
    raises, or returns anything but ``None`` or a string, is an instrument error. A check may
    call a model; findings that rest on it carry the mark "judged by your check".
    """

    def __call__(self, run: Any) -> str | None: ...
