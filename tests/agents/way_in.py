"""The scripted agent that speaks only the way-in protocol: a `Target` with no framework behind it.

It runs a script of tool calls, each through `session.call(tool, args, real)` and no other way. A
`ToolFailure` is a failure the agent is shown, and the script goes on past it. Anything else a call
raises has escaped the agent, and the run ends as `raised`. Its calls are its script, whatever it
saw, so a condition changes what it is shown and never what it asks.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from poisson_break.apply import RunResult, ToolFailure, ToolInfo
from poisson_break.interfaces import Capabilities
from tests.agents.plain import Seen, failed

Script = Sequence[tuple[str, Mapping[str, Any]]]


class WayIn:
    """A way in over `tools`, a mapping of each tool's name to a callable taking keyword arguments.
    `script` is the calls it makes, in order; with none given it looks the order up, checks the
    policy and looks the order up again, asking with the case's request. `max_steps` is its own
    step limit: with calls of the script still to make after that many, the run ends as `limit`.
    `seen` holds what the last run saw, one `Seen` per call."""

    kind = "scripted"
    framework_versions: Sequence[str] = ()

    def __init__(self, tools: Mapping[str, Callable[..., Any]], *, script: Script | None = None,
                 max_steps: int | None = None) -> None:
        self._tools = tools
        self._script = script
        self._max_steps = max_steps
        self.seen: tuple[Seen, ...] = ()

    def _steps(self, case: Mapping[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
        if self._script is not None:
            return [(tool, dict(args)) for tool, args in self._script]
        request = "" if case is None else str(case.get("input", ""))
        return [("lookup_order", {"query": request}),
                ("check_policy", {"topic": "refunds"}),
                ("lookup_order", {"query": request, "detail": "delivery"})]

    def tools(self) -> list[ToolInfo]:
        """The tools its script calls, each once, in the order it first calls them."""
        return [ToolInfo(name=tool) for tool in dict.fromkeys(tool for tool, _ in self._steps(None))]

    def capabilities(self) -> Capabilities:
        """Like a bare Prove target: it routes tool calls, and nothing more."""
        return Capabilities(tool_calls=True, model_calls=False, conversation=False)

    def run(self, case: Mapping[str, Any], session: Any, *, seed: int, limits: Any) -> RunResult:
        seen: list[Seen] = []
        self.seen = ()
        ended = "returned"
        steps = self._steps(case)
        try:
            for step, (tool, args) in enumerate(steps):
                if self._max_steps is not None and step >= self._max_steps:
                    ended = "limit"
                    break
                fn = self._tools[tool]
                try:
                    result = session.call(tool, args, lambda fn=fn, args=args: fn(**args))
                except ToolFailure as failure:
                    seen.append(Seen(tool=tool, args=dict(args), result=None, error=failed(failure)))
                else:
                    seen.append(Seen(tool=tool, args=dict(args), result=result, error=None))
        except Exception:
            ended = "raised"
        finally:
            self.seen = tuple(seen)
        reply = f"I made {len(seen)} of my {len(steps)} calls."
        return RunResult(reply=reply, outcome=None, tokens_in=None, tokens_out=None, ended=ended)
