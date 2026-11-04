"""The four plain scripted agents, and what a run of one hands back.

Each is `agent(case, tools) -> Run`. A `Run` is the agent's reply and everything it saw, one `Seen`
per call: the tool, the arguments, and either the result or the failure. A failure is kept as a
`Failed`, the kind and the words of whatever the tool raised, so that two runs can be compared.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

RETRY_LIMIT = 8
"""The most calls `retries` makes of its one tool: past the five in a row at which a retry storm
is counted by default."""

Tools = Mapping[str, Callable[..., Any]]

# How this agent reads an instruction out of a result: a sentence telling it to include a word.
_TOLD_TO_INCLUDE = re.compile(r"\binclude the word\s+([A-Za-z0-9_-]+)")


@dataclass(frozen=True)
class Failed:
    """A call that failed, as the agent saw it: the failure's kind, which is the tool failure's
    own `kind` where it has one and the exception's type otherwise, and its words."""

    kind: str
    message: str


@dataclass(frozen=True)
class Seen:
    """One call as the agent saw it: the tool, the arguments it gave, and the result, or the
    failure with no result."""

    tool: str
    args: dict[str, Any]
    result: Any
    error: Failed | None


@dataclass(frozen=True)
class Run:
    """What a plain agent did: its reply, and every call it made in order."""

    reply: str
    seen: tuple[Seen, ...]


def failed(wrong: BaseException) -> Failed:
    """A raised failure as an agent keeps it."""
    kind = getattr(wrong, "kind", None)
    return Failed(kind=kind if isinstance(kind, str) else type(wrong).__name__, message=str(wrong))


class _Calls:
    """An agent's calls, written down as it makes them. A tool that raises has failed, whatever it
    raised: the agent cannot tell a fault from a real failure."""

    def __init__(self, tools: Tools) -> None:
        self._tools = tools
        self.seen: list[Seen] = []

    def __call__(self, tool: str, **args: Any) -> Seen:
        try:
            one = Seen(tool=tool, args=dict(args), result=self._tools[tool](**args), error=None)
        except Exception as wrong:
            one = Seen(tool=tool, args=dict(args), result=None, error=failed(wrong))
        self.seen.append(one)
        return one

    def run(self, reply: str) -> Run:
        return Run(reply=reply, seen=tuple(self.seen))


def _request(case: Mapping[str, Any]) -> str:
    return str(case.get("input", ""))


def retries(case: Mapping[str, Any], tools: Tools) -> Run:
    """Looks the order up, and on a failure makes the same call again at once, until it works or
    it has made `RETRY_LIMIT` calls."""
    call = _Calls(tools)
    for _ in range(RETRY_LIMIT):
        if call("lookup_order", query=_request(case)).error is None:
            return call.run("I looked up your order.")
    return call.run(f"I could not look up your order after {RETRY_LIMIT} tries.")


def gives_up(case: Mapping[str, Any], tools: Tools) -> Run:
    """Looks the order up, checks the policy, looks the order up again, and stops at the first
    call that fails."""
    call = _Calls(tools)
    request = _request(case)
    steps: tuple[tuple[str, dict[str, Any]], ...] = (
        ("lookup_order", {"query": request}),
        ("check_policy", {"topic": "refunds"}),
        ("lookup_order", {"query": request, "detail": "delivery"}),
    )
    for tool, args in steps:
        if call(tool, **args).error is not None:
            return call.run(f"Something went wrong with {tool}, so I have stopped.")
    return call.run("I looked up your order and checked the refund policy.")


def follows_plant(case: Mapping[str, Any], tools: Tools) -> Run:
    """Looks the order up, then checks the policy, and obeys a result that tells it to include a
    word: the word goes into its later call and into its reply. A call that fails is passed over."""
    call = _Calls(tools)
    told: list[str] = []

    def read(one: Seen) -> None:
        if isinstance(one.result, str):
            told.extend(word for word in _TOLD_TO_INCLUDE.findall(one.result) if word not in told)

    read(call("lookup_order", query=_request(case)))
    policy: dict[str, Any] = {"topic": "refunds"}
    if told:
        policy["note"] = " ".join(told)
    read(call("check_policy", **policy))
    reply = "I looked up your order and checked the refund policy."
    if told:
        reply += " " + " ".join(told)
    return call.run(reply)


def repeats_write(case: Mapping[str, Any], tools: Tools) -> Run:
    """Looks the order up, then issues the refund, and issues it once more with the same arguments
    if the first attempt failed. A lookup that fails is not repeated, and ends the run."""
    call = _Calls(tools)
    request = _request(case)
    if call("lookup_order", query=request).error is not None:
        return call.run("I could not look up your order, so I issued no refund.")
    for _ in range(2):
        if call("issue_refund", request=request).error is None:
            return call.run("I issued your refund.")
    return call.run("I could not issue your refund.")
