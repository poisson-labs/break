"""What the failure check's tests share: how a scripted agent's run reaches the check, and how a test reads
what comes back.

`judge` and `signals` take a `FinishedRun`, which `watch` makes (rulings 1 to 6, Taylor, 2026-11-04, each in
`test_checks_ruled.py`). The plan's `judge(run: RunRecord)` could not work: a `RunRecord` holds no reply, no arguments and
no word on how the run ended, and it already holds the failure. The shape is written here, so that the tests speak of
what a run did.

`poisson_break.checks` is imported lazily, so on a tree without it each test fails on its own.

A run here is always something a scripted agent did: a session is made as the runs module will make it, the agent
runs on its tools, and the check reads the result. What a real target adds around an agent (an outcome word, a count
of tokens, a reply of its own, a sleep) is given to `plain` and `way_in`, which layer it on top of the agent.
"""

from __future__ import annotations

import dataclasses
import importlib
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from tests.apply_support import CASE, SEED, Tool, agents, apply, plain_tools, session, wrap_all
from tests.changes_support import changes

HUNT = "refund-agent-1"

# §9.4's default list, as `init` writes it.
DEFAULT_CHECKS = ["crashed", "hung", "ran_out", "forbidden_call", "followed_plant", "duplicate_write", "wrong"]

# §4's order, with `failed` in its place and `own:` after it. `failed` has no word in `checks`: §9.4's default leaves
# it out and still has `outcomes` work when uncommented.
ORDER = ["crashed", "hung", "ran_out", "forbidden_call", "followed_plant", "duplicate_write", "failed", "wrong"]

CLASSES: dict[str, Any] = {
    "a": "read",
    "b": "read",
    "lookup_order": "read",
    "check_policy": "read",
    "issue_refund": {"class": "write", "repeatable": True},
    "update_notes": {"class": "write", "repeatable": True},
    "delete_account": {"class": "write", "repeatable": True},
}

OK = ("ok", None)
NOT_COUNTED = ("not counted", None)


def failed(kind: str) -> tuple[str, str]:
    return ("failed", kind)


def checks() -> ModuleType:
    return importlib.import_module("poisson_break.checks")


def own_module() -> ModuleType:
    return importlib.import_module("tests.checks_own")


def own(name: str) -> str:
    """A user's check, named in `[fails] own` by its import path."""
    return f"tests.checks_own:{name}"


# ---------------------------------------------------------------------------
# reading a verdict
# ---------------------------------------------------------------------------


def verdict(run: Any) -> tuple[str, str | None]:
    """The state and the kind."""
    v = checks().judge(run)
    return (v.state, v.kind)


def judged(run: Any) -> Any:
    return checks().judge(run)


def state_of(v: Any) -> str:
    return v.state


def kind_of(v: Any) -> str | None:
    return v.kind


def outcome_of(v: Any) -> str | None:
    return v.outcome


def judged_by(v: Any) -> str | None:
    return v.judged_by


def error_of(v: Any) -> str | None:
    return v.error


# ---------------------------------------------------------------------------
# the keys of `[fails]` that §9.4 does not write
# ---------------------------------------------------------------------------


def stated_retries(n: int) -> dict[str, Any]:
    """§4: "more than a stated number of times in a row (default 5)". The key is ruling 6's."""
    return {"retry_storm_after": n}


def budget(*, tool_calls: int | None = None, tokens: int | None = None) -> dict[str, Any]:
    """§4: "more tokens or tool calls than the settings allow". The keys are ruling 6's."""
    out: dict[str, Any] = {}
    if tool_calls is not None:
        out["max_tool_calls"] = tool_calls
    if tokens is not None:
        out["max_tokens"] = tokens
    return out


# ---------------------------------------------------------------------------
# reading a view
# ---------------------------------------------------------------------------

# Every field of §11.4's list, by the words of §11.4, and how each is read.
VIEW_FIELDS: dict[str, Callable[[Any], Any]] = {
    "case id": lambda v: v.case.id,
    "case input": lambda v: v.case.input,
    "case turns": lambda v: v.case.turns,
    "condition name": lambda v: v.condition.name,
    "condition changes": lambda v: v.condition.changes,
    "calls": lambda v: v.calls,
    "reply": lambda v: v.reply,
    "outcome": lambda v: v.outcome,
    "tokens in": lambda v: v.tokens_in,
    "tokens out": lambda v: v.tokens_out,
    "seconds": lambda v: v.seconds,
    "kinds": lambda v: v.kinds,
}

# The same, as attributes: the object each sits on and the name it sits under.
VIEW_ATTRIBUTES: list[tuple[Callable[[Any], Any], str]] = [
    (lambda v: v, "case"), (lambda v: v, "condition"), (lambda v: v, "calls"), (lambda v: v, "reply"),
    (lambda v: v, "outcome"), (lambda v: v, "tokens_in"), (lambda v: v, "tokens_out"), (lambda v: v, "seconds"),
    (lambda v: v, "kinds"),
    (lambda v: v.case, "id"), (lambda v: v.case, "input"), (lambda v: v.case, "turns"),
    (lambda v: v.condition, "name"), (lambda v: v.condition, "changes"),
    (lambda v: v.condition.changes[0], "applied"), (lambda v: v.condition.changes[0], "applied_call"),
    (lambda v: v.calls[0], "tool"), (lambda v: v.calls[0], "call"), (lambda v: v.calls[0], "args"),
    (lambda v: v.calls[0], "saw"), (lambda v: v.calls[0], "error"), (lambda v: v.calls[0], "real_ran"),
]

TOP_LEVEL_FIELDS = {"case", "condition", "calls", "reply", "outcome", "tokens_in", "tokens_out", "seconds", "kinds"}


def view_calls(view: Any) -> list[tuple[Any, ...]]:
    """Each tool call in order: the tool, its number, its arguments, what the agent saw, whether the real tool ran."""
    return [(c.tool, c.call, dict(c.args), saw_of(c), c.real_ran) for c in view.calls]


def saw_of(call: Any) -> tuple[Any, ...]:
    """What the agent saw on one call: a result, or a failure with its kind."""
    if call.error is not None:
        return ("failure", call.error.kind)
    return ("result", call.saw)


def view_changes(view: Any) -> list[tuple[Any, ...]]:
    return [(c.surface, c.tool, c.fault, c.call, c.applied, c.applied_call) for c in view.condition.changes]


# ---------------------------------------------------------------------------
# the run's own facts, read, and changed by hand where no session can produce them
# ---------------------------------------------------------------------------


def reply_of(run: Any) -> Any:
    return run.reply


def seconds_of(run: Any) -> float:
    return float(run.seconds)


def with_tool_line(run: Any, tool: str, line: Any) -> Any:
    """A session refuses `lost_reply` on a read, so no run can show one: only the record's own field can."""
    return dataclasses.replace(run, tools={**run.tools, tool: line})


def with_fails(run: Any, fails: dict[str, Any]) -> Any:
    """The same run read again under other settings, as a test that wants a second look does."""
    return dataclasses.replace(run, fails=fails)


def with_seconds(run: Any, seconds: float) -> Any:
    """The default limit is 120 s, which no test waits out."""
    return dataclasses.replace(run, seconds=seconds)


# ---------------------------------------------------------------------------
# making a run
# ---------------------------------------------------------------------------


def all_tools() -> dict[str, Tool]:
    return {**plain_tools(), "a": Tool("a's answer"), "b": Tool("b's answer"), "update_notes": Tool("Noted."),
            "delete_account": Tool("Deleted.")}


def marker(*, hunt: str = HUNT, case: str | None = None) -> str:
    return changes().marker(hunt=hunt, case=CASE["id"] if case is None else case)


@dataclass
class Scene:
    """One run, and what stands around it."""

    run: Any
    session: Any
    tools: dict[str, Any]
    seen: tuple[Any, ...]
    marker: str | None


Layer = Callable[[tuple[Any, ...]], Any]


def _value(given: Any, seen: tuple[Any, ...]) -> Any:
    return given(seen) if callable(given) else given


def _result(reply: Any, seen: tuple[Any, ...], *, was: Any, outcome: Any, tokens: tuple[int | None, int | None],
            over_reply: Any, ended: str = "returned", pause: float = 0) -> Any:
    if pause:
        time.sleep(pause)
    a = apply()
    return a.RunResult(reply=reply if over_reply is None else _value(over_reply, seen),
                       outcome=_value(outcome, seen) if outcome is not None else (None if was is None else was.outcome),
                       tokens_in=tokens[0], tokens_out=tokens[1],
                       ended=ended if was is None else was.ended)


def plain(agent: str, text: str = "", *, case: dict[str, Any] | None = None, tools: dict[str, Any] | None = None,
          classes: dict[str, Any] | None = None, fails: dict[str, Any] | None = None, outcome: Any = None,
          tokens: tuple[int | None, int | None] = (None, None), reply: Any = None, pause: float = 0,
          run_seconds: float | None = None, planted: bool = True) -> Scene:
    """One of the four plain scripted agents on wrapped tools under a condition, as a `rollout` target runs it."""
    case = CASE if case is None else case
    word = marker(case=case["id"]) if planted else None
    s = session(text, tools=CLASSES if classes is None else classes, marker=word, run_seconds=run_seconds)
    tools = all_tools() if tools is None else tools
    program = getattr(agents(), agent)
    seen: list[tuple[Any, ...]] = [()]

    as_seen = s.case(case)

    def run_agent() -> Any:
        with s:
            done = program(as_seen, wrap_all(tools))
        seen[0] = done.seen
        return _result(done.reply, done.seen, was=None, outcome=outcome, tokens=tokens, over_reply=reply, pause=pause)

    run = checks().watch(run_agent, case=as_seen, session=s, fails=fails)
    return Scene(run, s, tools, seen[0], word)


def way_in(text: str = "", *, script: list[tuple[str, dict[str, Any]]] | None = None, max_steps: int | None = None,
           case: dict[str, Any] | None = None, tools: dict[str, Any] | None = None,
           classes: dict[str, Any] | None = None, fails: dict[str, Any] | None = None, outcome: Any = None,
           tokens: tuple[int | None, int | None] = (None, None), reply: Any = None, pause: float = 0,
           run_seconds: float | None = None, planted: bool = True) -> Scene:
    """The scripted agent that speaks only the way-in protocol, under a condition."""
    case = CASE if case is None else case
    word = marker(case=case["id"]) if planted else None
    s = session(text, tools=CLASSES if classes is None else classes, marker=word, run_seconds=run_seconds)
    tools = all_tools() if tools is None else tools
    agent = agents().WayIn(tools, script=script, max_steps=max_steps)

    as_seen = s.case(case)

    def run_agent() -> Any:
        done = agent.run(as_seen, s, seed=SEED, limits=None)
        return _result(done.reply, agent.seen, was=done, outcome=outcome, tokens=tokens, over_reply=reply, pause=pause)

    run = checks().watch(run_agent, case=as_seen, session=s, fails=fails)
    return Scene(run, s, tools, agent.seen, word)


def target(run_agent: Callable[[Any], Any], text: str = "", *, case: dict[str, Any] | None = None,
           classes: dict[str, Any] | None = None, fails: dict[str, Any] | None = None,
           run_seconds: float | None = None) -> Scene:
    """A target of a test's own around the session: for what escapes an agent, which the five agents do not let
    happen. `run_agent(session)` is called inside the run and returns a `RunResult` or raises."""
    case = CASE if case is None else case
    word = marker(case=case["id"])
    s = session(text, tools=CLASSES if classes is None else classes, marker=word, run_seconds=run_seconds)
    run = checks().watch(lambda: run_agent(s), case=case, session=s, fails=fails)
    return Scene(run, s, {}, (), word)


def result(reply: Any = "done", *, outcome: str | None = None, ended: str = "returned") -> Any:
    return apply().RunResult(reply=reply, outcome=outcome, tokens_in=None, tokens_out=None, ended=ended)


def lines_of(case: Mapping[str, Any], **expect: Any) -> dict[str, Any]:
    return {**case, "expect": expect}


SLEEP = 0.05
LIMIT = 0.01
"""A run that sleeps `SLEEP` under a limit of `LIMIT` has passed it however loaded the machine is."""
