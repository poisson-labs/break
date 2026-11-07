"""The targets the commands' tests hunt: plain Prove targets, `(cfg, seed) -> Episode`, as `target.entry` names them.

The commands load a target from `break.toml`, and the core loads the `rollout` kind only, so every target here is a
plain Prove target whose tools are wrapped with `wrap`, one function call each (spec §7.1). The command runs in a child
process, so what a target did is written to a file, not to a list: each run adds one JSON line to the file
`BREAK_TEST_RUNS_LOG` names, `{"target", "case", "seed"}`. A test counts runs by reading it.

What a run does is decided by the case and the seed, and by which fault, if any, the agent saw. A case may carry keys
only these targets read, which the case reader keeps and hands over (spec §9.4):

- `rate`: the share of runs that fail when no fault in `weak_to` was seen (0 if not given), drawn from the seed;
- `weak` and `weak_to`: the share of runs that fail when a look-up raised a fault named in `weak_to` (1 if not given):
  the planted weakness. A fault not named, and any fault on `check_policy`, makes no difference;
- `less_to`: faults that, raised by a look-up, make the run not fail at all: a condition that fails less;
- `lookups`: how many times the agent looks the order up (1 if not given), so a call number past `max_call` is seen;
- `outcome`: an outcome word reported on every run, whatever else happened;
- `tokens`: the tokens in and out every run reports, for a hunt with prices;
- `nap`: seconds slept before the run does anything, so a test can stop a command while it runs.

A run that fails reports the outcome `unresolved`, which the settings list as failing. `BREAK_TEST_MENDED=1` in the
environment is the agent mended: no run fails at all, so a recheck sees it fail less and a replay sees it not fail; and
`BREAK_TEST_WEAK=<share>` is the agent changed so that its weakness fails that share of runs, so a recheck can see it
fail more. `old_desk` is the
agent before it was mended, whatever the environment says, for `recheck --old`.

No model, no framework.
"""

from __future__ import annotations

import json
import os
import random
import time
from collections.abc import Mapping
from typing import Any

from poisson_prove import Episode

from poisson_break.apply import wrap

FAILING = "unresolved"
TOOLS = ("lookup_order", "check_policy")


def _lookup_order(query: str) -> str:
    return f"Order {query} shipped on Tuesday."


def _check_policy(topic: str) -> str:
    return "Refunds within thirty days."


lookup_order = wrap("lookup_order", _lookup_order)
check_policy = wrap("check_policy", _check_policy)


def draw(seed: int, case_id: str) -> float:
    """The one number a run of `case_id` on `seed` decides by, in [0, 1)."""
    return random.Random(f"{seed}:{case_id}").random()


def _note(target: str, cfg: Mapping[str, Any], seed: int) -> None:
    path = os.environ.get("BREAK_TEST_RUNS_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as out:
            out.write(json.dumps({"target": target, "case": str(cfg.get("id")), "seed": int(seed)}) + "\n")


def _act(cfg: Mapping[str, Any], seed: int, *, mended: bool) -> Episode:
    ident = str(cfg.get("id"))
    if cfg.get("nap"):
        time.sleep(float(cfg["nap"]))
    seen: list[str] = []
    for _ in range(int(cfg.get("lookups", 1))):
        try:
            lookup_order(ident)
        except Exception as wrong:  # the agent cannot tell a fault from a real failure
            seen.append(str(getattr(wrong, "kind", type(wrong).__name__)))
    try:
        check_policy("refunds")
    except Exception:  # the policy is read and nothing hangs on it: a fault here makes no difference
        pass
    rate = float(cfg.get("rate", 0.0))
    share = rate
    if any(kind in cfg.get("weak_to", ()) for kind in seen):
        share = float(os.environ.get("BREAK_TEST_WEAK") or cfg.get("weak", 1.0))
    if any(kind in cfg.get("less_to", ()) for kind in seen):
        share = 0.0
    if mended:
        share = 0.0
    failed = draw(seed, ident) < share
    outcome = str(cfg["outcome"]) if "outcome" in cfg else (FAILING if failed else "done")
    meta: dict[str, Any] = {"reply": "done", "ended": "returned"}
    if cfg.get("tokens"):
        meta["tokens_in"], meta["tokens_out"] = cfg["tokens"]
    return Episode(outcome=outcome, t=0.0, horizon=1.0, meta=meta)


def desk(cfg: Mapping[str, Any], seed: int) -> Episode:
    """The agent as it is now: mended when `BREAK_TEST_MENDED=1`."""
    _note("desk", cfg, seed)
    return _act(cfg, seed, mended=os.environ.get("BREAK_TEST_MENDED") == "1")


def old_desk(cfg: Mapping[str, Any], seed: int) -> Episode:
    """The agent before it was mended, for `recheck --old`."""
    _note("old_desk", cfg, seed)
    return _act(cfg, seed, mended=False)


def unresolved(run: Any) -> str | None:
    """A user's own check: it fails the runs that report `unresolved`."""
    return "unresolved" if run.outcome == FAILING else None


NOT_CALLABLE = 3
