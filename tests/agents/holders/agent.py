"""The holders module's agent: it holds its tools every way a tool can be held.

The five tools come by `from ... import`, and are in the dict `TOOLS` and the list `TOOL_LIST` at the top of the
module. `lookup_order`, and no other tool, is held four more ways: by the closure `AGENT`, whose function keeps the
tool in a cell of its own; by the partial `FIND`; by the tuple `HELP`; and by `BOX`, an object whose attribute
`lookup` is the tool. `desk(cfg, seed)` is the entry: it calls `TOOLS["lookup_order"]` once with the case's input.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping
from typing import Any

from tests.agents.holders.tools import cancel_order, check_policy, issue_refund, lookup_order, send_email
from tests.load_episode import Episode

TOOLS: dict[str, Callable[..., str]] = {
    "lookup_order": lookup_order, "check_policy": check_policy, "issue_refund": issue_refund,
    "send_email": send_email, "cancel_order": cancel_order}
TOOL_LIST: list[Callable[..., str]] = [lookup_order, check_policy, issue_refund, send_email, cancel_order]


def make_agent(tool: Callable[..., str]) -> Callable[[str], str]:
    """An agent that keeps the tool it was made with."""
    def agent(query: str) -> str:
        return tool(query)
    return agent


class Box:
    """An object that keeps a tool as an attribute."""

    def __init__(self, lookup: Callable[..., str]) -> None:
        self.lookup = lookup


AGENT = make_agent(lookup_order)
FIND = functools.partial(lookup_order)
HELP = (lookup_order, "Look an order up.")
BOX = Box(lookup_order)


def desk(cfg: Mapping[str, Any], seed: int) -> Episode:
    """One run: the order is looked up through the dict, once."""
    found = TOOLS["lookup_order"](cfg["input"])
    return Episode(outcome="done", t=0.0, horizon=1.0, meta={"reply": found})
