"""What the applying module's tests share: how a session is made, a real tool that counts, what the
agent saw, and the lazy imports of `poisson_break.apply` and the scripted agents.

Both are imported lazily, so on a tree without them each test fails on its own and the rest of the
suite still runs.

`session(...)` is the one place a test builds a `Session` (rulings 1 and 5). A different answer to
those rulings changes this file and not the tests that use it.

Tool names are the spec's own, from §9.4: `lookup_order` and `check_policy` read, `issue_refund`
writes. `a` and `b` are read tools for the tests that care about nothing but the call numbers.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Iterator
from types import ModuleType
from typing import Any

from tests.changes_support import PACKAGE, changes

SEED = 20261104

CLASSES: dict[str, Any] = {
    "a": "read",
    "b": "read",
    "lookup_order": "read",
    "check_policy": "read",
    "issue_refund": {"class": "write", "repeatable": True},
}

# Every tool repeatable, so that all ten faults may land on it.
REPEATABLE: dict[str, Any] = {
    "a": {"class": "write", "repeatable": True},
    "b": {"class": "write", "repeatable": True},
}

# A way in that can do all three, as an adapter would. A session given no capabilities has a plain Prove
# target's: it routes tool calls and nothing more.
ALL_CAPABILITIES = {"tool_calls": True, "model_calls": True, "conversation": True}


def apply() -> ModuleType:
    return importlib.import_module("poisson_break.apply")


def agents() -> ModuleType:
    return importlib.import_module("tests.agents")


def records() -> ModuleType:
    return importlib.import_module("poisson_break.records")


def session(text: str = "", *, seed: int = SEED, tools: dict[str, Any] | None = None, **over: Any) -> Any:
    """One run's applier, for a condition name."""
    return apply().Session(changes().parse(text), seed=seed, tools=CLASSES if tools is None else tools, **over)


def fresh() -> Iterator[tuple[ModuleType, ModuleType]]:
    """A fresh import of the package, with a catalogue of its own, for a test that registers a fault:
    there is no public way to take one back out. The suite's own import comes back after."""
    def ours() -> list[str]:
        return [n for n in sys.modules
                if n == PACKAGE or n.startswith(PACKAGE + ".") or n == "tests.agents" or n.startswith("tests.agents.")]

    saved = {n: sys.modules[n] for n in ours()}
    for n in saved:
        del sys.modules[n]
    try:
        yield importlib.import_module("poisson_break.changes"), importlib.import_module("poisson_break.apply")
    finally:
        for n in ours():
            del sys.modules[n]
        sys.modules.update(saved)


class Tool:
    """A real tool: gives its values in turn, the last one for ever after, and logs every run."""

    def __init__(self, *values: Any, raises: BaseException | None = None) -> None:
        self.values = values or ("the real answer",)
        self.raises = raises
        self.log: list[dict[str, Any]] = []

    @property
    def runs(self) -> int:
        return len(self.log)

    def __call__(self, **args: Any) -> Any:
        self.log.append(args)
        if self.raises is not None:
            raise self.raises
        return self.values[min(len(self.log) - 1, len(self.values) - 1)]


def call(s: Any, name: str, tool: Callable[..., Any], **args: Any) -> Any:
    """One call through the session, as a way in routes it."""
    return s.call(name, args, lambda: tool(**args))


def seen(fn: Callable[[], Any]) -> tuple[Any, ...]:
    """What the agent saw: a result, or a failure with its kind and its words."""
    try:
        return ("result", fn())
    except apply().ToolFailure as failure:
        return ("failure", failure.kind, str(failure))


def seen_call(s: Any, name: str, tool: Callable[..., Any], **args: Any) -> tuple[Any, ...]:
    return seen(lambda: call(s, name, tool, **args))


def plain_tools() -> dict[str, Tool]:
    """The three tools the four plain scripted agents call."""
    return {"lookup_order": Tool("Order 7 shipped on Tuesday."),
            "check_policy": Tool("Refunds within thirty days."),
            "issue_refund": Tool("Refund issued.")}


def wrap_all(tools: dict[str, Any]) -> dict[str, Any]:
    """Each tool as a `rollout` target wraps it, with one function call each."""
    return {name: apply().wrap(name, fn) for name, fn in tools.items()}


def stand_in_module() -> Iterator[ModuleType]:
    """The stand-ins' module, with its log cleared, for a fixture to yield from."""
    module = importlib.import_module("tests.apply_support_standin")
    module.reset()
    yield module
    module.reset()


def run_plain_agent(agent: Callable[..., Any], text: str = "", *, case: dict[str, Any] | None = None,
                    tools: dict[str, Any] | None = None, classes: dict[str, Any] | None = None,
                    **over: Any) -> tuple[Any, Any, dict[str, Any]]:
    """A plain scripted agent on wrapped tools under a condition: its run, the session, the tools."""
    s = session(text, tools=classes, **over)
    tools = plain_tools() if tools is None else tools
    with s:
        run = agent(case or CASE, wrap_all(tools))
    return run, s, tools


def run_way_in(text: str = "", *, case: dict[str, Any] | None = None, tools: dict[str, Any] | None = None,
               classes: dict[str, Any] | None = None, script: list[tuple[str, dict[str, Any]]] | None = None,
               max_steps: int | None = None, **over: Any) -> tuple[Any, Any, Any, dict[str, Any]]:
    """The way-in agent under a condition: its result, the agent, the session, the tools."""
    s = session(text, tools=classes, **over)
    tools = plain_tools() if tools is None else tools
    agent = agents().WayIn(tools, script=script, max_steps=max_steps)
    result = agent.run(case or CASE, s, seed=over.get("seed", SEED), limits=None)
    return result, agent, s, tools


CASE: dict[str, Any] = {"id": "c1", "input": "Where is order 7? Please refund it."}

# A long real result: every fault that edits a result shows, whichever of them is on.
LONG = "Order 7 shipped on Tuesday. " * 12
MAPPING = {"order": 7, "status": "shipped", "carrier": "usual"}
LISTING = [{"order": 7}, {"order": 8}]
EARLIER = "the answer from the call before"
