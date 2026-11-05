"""The targets the runs module's tests hunt: one scripted desk, reached two ways.

`Desk` is a way in written outside the package (plan BK5.15): a `Target` that routes every tool call through
`session.call` and reports how the run ended. `refund_agent` and the functions beside it are plain Prove targets,
`(cfg, seed) -> Episode`, whose tools are wrapped with `wrap`, one function call each (spec §7.1). Both run the same
`act`, so what a run did does not depend on how Break reached it, and a record made one way can be held to the other.

No model, no framework, nothing random: what a run does is decided by the case it is handed. Besides `id` and `input`,
which every case has, a case may carry keys only this desk reads, which the case reader keeps and hands over (spec §9.4):

- `agent`: which of the four plain scripted agents answers (`retries`, `gives_up`, `follows_plant`, `repeats_write`);
- `does`: something else to do instead or as well: `crash`, `exit`, `limit`, `instrument`, `mystery`, `interrupt`;
- `nap`: seconds slept before anything else, outside every tool; `linger`: seconds slept after its last call;
- `outcome`: the outcome word the target reports, `done` if none;
- `tokens`: the tokens it reports, in and out.

An input that starts with `stuck:` makes the real `lookup_order` sleep far past any limit a test sets: a tool that
never returns.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from poisson_prove import Episode

from poisson_break.apply import RunResult, ToolInfo, wrap
from poisson_break.changes import InstrumentError
from poisson_break.interfaces import Capabilities
from tests import agents

STUCK_SECONDS = 12.0
TOOL_NAMES = ("lookup_order", "check_policy", "issue_refund")

# Every real execution of a tool, in order: (tool, arguments). A test clears it and reads it.
EXECUTED: list[tuple[str, dict[str, Any]]] = []
# Whatever a stuck tool went on to do after it was cut off. It should stay empty.
AFTER_STUCK: list[str] = []


def lookup_order(query: str, detail: str | None = None) -> str:
    EXECUTED.append(("lookup_order", {"query": query, "detail": detail}))
    if query.startswith("stuck:"):
        time.sleep(STUCK_SECONDS)
        AFTER_STUCK.append(query)
    return "Order 7 shipped on Tuesday."


def check_policy(topic: str, note: str | None = None) -> str:
    EXECUTED.append(("check_policy", {"topic": topic, "note": note}))
    return "Refunds within thirty days."


def issue_refund(request: str) -> str:
    EXECUTED.append(("issue_refund", {"request": request}))
    return "Refund issued."


def mystery() -> str:
    """A tool nobody classed in the settings."""
    EXECUTED.append(("mystery", {}))
    return "nobody classed me"


REAL: dict[str, Callable[..., Any]] = {"lookup_order": lookup_order, "check_policy": check_policy,
                                       "issue_refund": issue_refund, "mystery": mystery}


def refund_stand_in(request: str) -> str:
    """A stand-in for `issue_refund`, named in `[tools]` by its import path."""
    EXECUTED.append(("refund_stand_in", {"request": request}))
    return "Refund issued (stand-in)."


NOT_CALLABLE = 3


@dataclass(frozen=True)
class Acted:
    """What the desk did in one run, before either way in puts it in its own form."""

    reply: Any
    outcome: str
    tokens_in: int | None
    tokens_out: int | None
    ended: str


def act(case: Mapping[str, Any], tools: Mapping[str, Callable[..., Any]], *, agent: str = "gives_up") -> Acted:
    """One run of the desk on `case`, calling `tools` by name with keyword arguments. Raising is how a tool fails."""
    nap = case.get("nap")
    if nap:
        time.sleep(float(nap))
    does = case.get("does")
    if does == "crash":
        raise RuntimeError("the agent fell over")
    if does == "exit":
        raise SystemExit(3)
    if does == "instrument":
        raise InstrumentError("the way in could not reach the agent")
    if does == "interrupt":
        raise KeyboardInterrupt
    if does == "mystery":
        tools["mystery"]()
    done = getattr(agents, str(case.get("agent", agent)))(case, tools)
    if case.get("linger"):
        time.sleep(float(case["linger"]))
    tokens = case.get("tokens") or (None, None)
    return Acted(reply=done.reply, outcome=str(case.get("outcome", "done")), tokens_in=tokens[0], tokens_out=tokens[1],
                 ended="limit" if does == "limit" else "returned")


# ---------------------------------------------------------------------------
# the way in from outside the package
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Handed:
    """What one call of `Desk.run` was handed, kept so a test can read it afterwards."""

    case: dict[str, Any]
    seed: int
    limits: Any
    run_seconds: float | None
    marker: str | None
    condition: Any
    session_seed: int


class Desk:
    """A `Target` over the desk. `listed` is what `tools()` says, the three real tools if not given. `can` overrides
    what `capabilities()` says. `before(n)` is called at the start of the n-th run, counted from 1, and may raise."""

    kind = "desk"
    framework_versions: Sequence[str] = ()

    def __init__(self, agent: str = "gives_up", *, listed: Sequence[str] | None = None,
                 can: Mapping[str, bool] | None = None, before: Callable[[int], None] | None = None) -> None:
        self.agent = agent
        self.listed = tuple(TOOL_NAMES if listed is None else listed)
        self.can = {"tool_calls": True, "model_calls": False, "conversation": False, **(can or {})}
        self.before = before
        self.handed: list[Handed] = []
        self.asked_tools = 0
        self.asked_capabilities = 0

    def tools(self) -> list[ToolInfo]:
        self.asked_tools += 1
        return [ToolInfo(name=name) for name in self.listed]

    def capabilities(self) -> Capabilities:
        self.asked_capabilities += 1
        return Capabilities(**self.can)

    def run(self, case: Mapping[str, Any], session: Any, *, seed: int, limits: Any) -> RunResult:
        self.handed.append(Handed(case=dict(case), seed=seed, limits=limits, run_seconds=session.run_seconds,
                                  marker=session.marker, condition=session.condition,
                                  session_seed=session.seed))
        if self.before is not None:
            self.before(len(self.handed))

        def through(name: str) -> Callable[..., Any]:
            return lambda **args: session.call(name, args, lambda: REAL[name](**args))

        done = act(case, {name: through(name) for name in REAL}, agent=self.agent)
        return RunResult(reply=done.reply, outcome=done.outcome, tokens_in=done.tokens_in, tokens_out=done.tokens_out,
                         ended=done.ended)

    @property
    def runs(self) -> int:
        return len(self.handed)


# ---------------------------------------------------------------------------
# plain Prove targets: `(cfg, seed) -> Episode`, tools wrapped one call each
# ---------------------------------------------------------------------------

WRAPPED: dict[str, Callable[..., Any]] = {name: wrap(name, fn) for name, fn in REAL.items()}

# Every call of a plain target below: (cfg, seed).
ROLLOUTS: list[tuple[dict[str, Any], int]] = []


def _episode(done: Acted) -> Episode:
    meta: dict[str, Any] = {"reply": done.reply, "ended": done.ended, "a_secret_of_the_targets_own": "do not store me"}
    if done.tokens_in is not None:
        meta["tokens_in"] = done.tokens_in
    if done.tokens_out is not None:
        meta["tokens_out"] = done.tokens_out
    return Episode(outcome=done.outcome, t=0.0, horizon=1.0, meta=meta)


def refund_agent(cfg: Mapping[str, Any], seed: int) -> Episode:
    """The desk as a plain Prove target."""
    ROLLOUTS.append((dict(cfg), seed))
    return _episode(act(cfg, WRAPPED))


def bare_agent(cfg: Mapping[str, Any], seed: int) -> Episode:
    """A plain Prove target that says nothing beyond what an `Episode` must: an outcome, and an empty `meta`."""
    ROLLOUTS.append((dict(cfg), seed))
    return Episode(outcome=act(cfg, WRAPPED).outcome, t=0.0, horizon=1.0)


def hands_back_text(cfg: Mapping[str, Any], seed: int) -> Any:
    """A target that forgets to hand back an `Episode`."""
    ROLLOUTS.append((dict(cfg), seed))
    return "done"


# ---------------------------------------------------------------------------
# the user's own check, for the tests that load one
# ---------------------------------------------------------------------------

CHECKED: list[str] = []
CHECKED_INPUTS: list[str] = []


def counting_check(run: Any) -> str | None:
    """A check that passes every run and writes down each one it was shown: its case, and the input as it saw it."""
    CHECKED.append(run.case.id)
    CHECKED_INPUTS.append(run.case.input)
    return None


def reset() -> None:
    """Forget everything the targets wrote down."""
    for kept in (EXECUTED, AFTER_STUCK, ROLLOUTS, CHECKED, CHECKED_INPUTS):
        kept.clear()
