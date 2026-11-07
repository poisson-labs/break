"""The scripted desk the confirm module's tests confirm against: one way in whose failures are drawn from the seed.

`Coin` is a `Target` written outside the package, like the runs module's `Desk`, routing its one tool call through
`session.call`. Unlike the plain scripted agents it is random on purpose, and only through the seed it is handed, so
the same seed gives the same run and a stage on fresh seeds draws fresh outcomes. No model, no framework.

What a run does is decided by the case, the seed and which fault, if any, landed on its call of `lookup_order`. A case
may carry keys only this desk reads:

- `rate`: the share of runs that fail when no fault in `weak_to` landed (0 if not given): a fixed failure rate;
- `weak` and `weak_to`: the share of runs that fail when a fault named in `weak_to` landed: the planted weakness. A
  fault not named makes no difference, so a condition of only such faults is a condition with no effect;
- `dead_to`: when a fault named here landed, the way in fails and the run is not counted: no outcome;
- `dead`: every run of the case is not counted;
- `tokens`: the tokens in and out every run of the case reports, for a hunt with prices.

`Coin(weak=...)` overrides every case's `weak`: the same agent mended (`weak` at the case's `rate`) or made worse. A
run that fails reports the outcome `unresolved`, which the settings list as failing, so its kind is `failed`. `CALLS`
writes down every run as (case id, seed, the fault that landed or None).
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from typing import Any

from poisson_break.apply import RunResult, ToolInfo
from poisson_break.changes import InstrumentError
from poisson_break.interfaces import Capabilities

FAILING = "unresolved"
TOOL = "lookup_order"
MENDED = "mended"

CALLS: list[tuple[str, int, str | None]] = []


def _lookup(query: str) -> str:
    return f"Order {query} shipped."


def draw(seed: int, case_id: str) -> float:
    """The one number a run of `case_id` on `seed` decides by, in [0, 1)."""
    return random.Random(f"{seed}:{case_id}").random()


def _landed(session: Any) -> str | None:
    for one in session.applied:
        if one.applied and one.tool == TOOL:
            return str(one.fault)
    return None


class Coin:
    """A way in over the desk: one call of `lookup_order`, then a failure drawn from the seed."""

    kind = "coin"
    framework_versions: Sequence[str] = ()

    def __init__(self, *, weak: float | str | None = None) -> None:
        self.weak = weak
        self.runs = 0

    def tools(self) -> list[ToolInfo]:
        return [ToolInfo(name=TOOL)]

    def capabilities(self) -> Capabilities:
        return Capabilities(tool_calls=True, model_calls=False, conversation=False)

    def run(self, case: Mapping[str, Any], session: Any, *, seed: int, limits: Any) -> RunResult:
        self.runs += 1
        ident = str(case["id"])
        try:
            session.call(TOOL, {"query": ident}, lambda: _lookup(ident))
        except InstrumentError:
            raise
        except Exception:
            pass
        fault = _landed(session)
        CALLS.append((ident, seed, fault))
        if case.get("dead") or (fault is not None and fault in case.get("dead_to", ())):
            raise InstrumentError("the way in could not reach this case")
        rate = float(case.get("rate", 0.0))
        share = rate
        if fault is not None and fault in case.get("weak_to", ()):
            weak = case.get("weak", rate) if self.weak is None else self.weak
            share = rate if weak == MENDED else float(weak)
        failed = draw(seed, ident) < share
        tokens = case.get("tokens") or (None, None)
        return RunResult(reply="done", outcome=FAILING if failed else "done", tokens_in=tokens[0],
                         tokens_out=tokens[1], ended="returned")


def reset() -> None:
    CALLS.clear()


def unresolved(run: Any) -> str | None:
    """A user's own check (`[fails] own = "tests.confirm_targets:unresolved"`): it fails exactly the runs the desk
    reports as `unresolved`, so a hunt judged by it fails the same runs as one judged by `[fails] outcomes`."""
    return "unresolved" if run.outcome == FAILING else None
