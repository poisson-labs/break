"""The bare twin: the help desk as a whole target with no line of anything else's in it.

The same agent as `tests/agents/twins/wrapped/twin_desk.py`, line for line but for that twin's import of `wrap` and
its three lines. Each is the module `twin_desk` when its own folder is first on the import path. This twin's tools are
reached through its settings, which say where each one is: `at = "twin_desk:<tool>"`. Each tool is defined under its
own name and held under no other.

`desk(cfg, seed)` runs the plain scripted agent the case names (`gives_up` when it names none) over this module's own
three tools, each looked up by its name when the call is made, and hands back an `Episode`: the outcome `unresolved`
when any call failed and `done` when none did, and in `meta` the agent's `reply`, its `run` and `raised`, every
exception a tool call raised, in order. Each real run of a tool, or of the stand-in, is added to `EXECUTED`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from tests.agents.plain import follows_plant, gives_up, repeats_write, retries
from tests.load_episode import Episode

EXECUTED: list[tuple[str, dict[str, Any]]] = []
"""Each real run of a tool or of the stand-in, as its name and the arguments it was given."""

TOOL_NAMES = ("lookup_order", "check_policy", "issue_refund")
_AGENTS = {"gives_up": gives_up, "retries": retries, "follows_plant": follows_plant,
           "repeats_write": repeats_write}


def _given(**args: Any) -> dict[str, Any]:
    return {name: value for name, value in args.items() if value is not None}


def lookup_order(query: str, detail: str | None = None) -> str:
    """Look an order up."""
    EXECUTED.append(("lookup_order", _given(query=query, detail=detail)))
    return "Order 7 shipped on Tuesday."


def check_policy(topic: str, note: str | None = None) -> str:
    """Read the refund policy."""
    EXECUTED.append(("check_policy", _given(topic=topic, note=note)))
    return "Refunds within thirty days."


def issue_refund(request: str) -> str:
    """Move the money back."""
    EXECUTED.append(("issue_refund", _given(request=request)))
    return "Refund issued."


def refund_stand_in(request: str) -> str:
    """What the settings may name to be called in `issue_refund`'s place."""
    EXECUTED.append(("refund_stand_in", _given(request=request)))
    return "Refund issued."


def desk(cfg: Mapping[str, Any], seed: int) -> Episode:
    """One run of the plain agent the case names, over this module's tools by name."""
    raised: list[Exception] = []

    def by_name(name: str) -> Callable[..., Any]:
        def call(**args: Any) -> Any:
            try:
                return globals()[name](**args)
            except Exception as wrong:
                raised.append(wrong)
                raise
        return call

    run = _AGENTS[cfg.get("agent", "gives_up")](cfg, {name: by_name(name) for name in TOOL_NAMES})
    failed = any(seen.error is not None for seen in run.seen)
    return Episode(outcome="unresolved" if failed else "done", t=0.0, horizon=1.0,
                   meta={"reply": run.reply, "run": run, "raised": tuple(raised)})
