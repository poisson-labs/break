"""Strategies written outside the core, for the tests. Each is found by its import path, as a user's or Monte's would be, and
imports nothing Break does not publish: the plan's `strategy = "tests.strategies:Fixed"` is this file.

Nothing in the package may import this file. A strategy declares nothing about itself: the core knows it by the path it was
loaded from.
"""

from __future__ import annotations

from typing import Any

from poisson_break.changes import parse
from poisson_break.search import Proposal


def _batch(*items: tuple[str, str, float]) -> list[Proposal]:
    return [Proposal(condition=parse(text), reason=reason, probability=probability) for text, reason, probability in items]


class Fixed:
    """Proposes three conditions, each once, with its own reason and probability, then nothing."""

    PROPOSED = (("tool:lookup_order#1=error", "the first look-up", 0.25),
                ("tool:issue_refund#1=lost_reply", "the write", 0.125),
                ("tool:check_policy#1=timeout", "the policy", 0.5))

    def propose(self, seen: Any, budget: int, *, rng: Any) -> list[Proposal]:
        done = {p.condition if isinstance(p.condition, str) else _name(p.condition) for p in seen.proposals}
        return _batch(*(p for p in self.PROPOSED if p[0] not in done))


def _name(condition: Any) -> str:
    from poisson_break.changes import name

    return name(condition)


class AlwaysTheSame:
    """Proposes the same condition every time it is asked, whatever came of it."""

    def propose(self, seen: Any, budget: int, *, rng: Any) -> list[Proposal]:
        return _batch(("tool:lookup_order#1=error", "again", 0.5))


class NoProbability:
    """Hands back something shaped like a proposal with no probability on it: it cannot be made as a `Proposal`."""

    def propose(self, seen: Any, budget: int, *, rng: Any) -> list[Any]:
        class Unmarked:
            condition = parse("tool:lookup_order#1=error")
            reason = "I cannot say how likely"

        return [Unmarked()]


class Raises:
    """A strategy with a mistake in it."""

    def propose(self, seen: Any, budget: int, *, rng: Any) -> list[Proposal]:
        raise ZeroDivisionError("the strategy's own mistake")


class FollowsFailures:
    """Learns within the hunt from `Seen` alone: with nothing failed it goes across the tools, one fault at a time, and after a
    failure it stays on the tool that failed. Not a search anyone should use: it shows what `Seen` is sufficient for."""

    def propose(self, seen: Any, budget: int, *, rng: Any) -> list[Proposal]:
        tried = {_name(r.condition) for r in seen.runs if r.condition.changes}
        tools = sorted({tool for reach in seen.control.values() for tool in reach})
        on = {tool: sorted(seen.catalogue.tools.get(tool, ())) for tool in tools}
        failed = [c.tool for r in seen.runs if r.outcome == "failed" for c in r.condition.changes]
        wanted = [(tool, fault) for tool in failed for fault in on.get(tool, ())]
        wanted += [(tool, fault) for fault in sorted({f for faults in on.values() for f in faults})
                   for tool in tools if fault in on[tool]]
        for tool, fault in wanted:
            text = f"tool:{tool}#1={fault}"
            if text not in tried:
                return _batch((text, f"{len(failed)} failed so far", 1 / (1 + len(tried))))
        return []


# Not a class: an object with a `propose` is used as it is.
AN_OBJECT = Fixed()


class Callable:
    """Not a class on the path but an object, which can also be called: it is used as it is, and not called."""

    def __call__(self) -> Any:
        raise AssertionError("an object with a propose is used as it is")

    def propose(self, seen: Any, budget: int, *, rng: Any) -> list[Proposal]:
        return []


A_CALLABLE_OBJECT = Callable()


class NeedsArguments:
    """A class that cannot be made with no arguments."""

    def __init__(self, how_many: int) -> None:
        self.how_many = how_many

    def propose(self, seen: Any, budget: int, *, rng: Any) -> list[Proposal]:
        return []


class NoPropose:
    """Not a strategy."""

    def suggest(self, seen: Any, budget: int, *, rng: Any) -> list[Proposal]:
        return []


NOT_ANYTHING = 7
