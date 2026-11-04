"""The five scripted agents every module's tests stand on: small programs with no model and no
framework, each calling its tools in a known order and reacting to a failure in one known way.

- `retries` calls one tool and, when the call fails, makes the same call again, up to
  `RETRY_LIMIT` calls in all.
- `gives_up` makes three calls and stops at the first that fails, never calling that tool again.
- `follows_plant` makes two calls and does what a tool's result tells it to: a word it is told to
  include goes into its reply and into its later call.
- `repeats_write` looks an order up, then writes once, and writes once more if the write failed.
- `WayIn` speaks only the way-in protocol: it runs a script of calls through the session, goes on
  past a failure it is shown, and reports how the run ended.

The four plain agents are `agent(case, tools) -> Run`, where `tools` maps a tool's name to a
callable taking keyword arguments, and raising is how a tool fails. They know nothing of Break, so
a fault and a real failure are the same to them. None quotes a tool's result in its reply.

Their three tools are `lookup_order` and `check_policy`, which read, and `issue_refund`, which
writes.
"""

from tests.agents.plain import (
    RETRY_LIMIT,
    Failed,
    Run,
    Seen,
    follows_plant,
    gives_up,
    repeats_write,
    retries,
)
from tests.agents.way_in import WayIn

AGENTS = (retries, gives_up, follows_plant, repeats_write, WayIn)

__all__ = ["AGENTS", "RETRY_LIMIT", "Failed", "Run", "Seen", "WayIn", "follows_plant", "gives_up",
           "repeats_write", "retries"]
