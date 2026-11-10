"""A target whose module registers a fault of its own, for `tests/test_release_own_fault.py`.

It is loaded only by the command's child process, as `[target] entry`; no test imports it, since importing it
changes the catalogue for the whole process. Importing this module registers the tool fault `garbled` through `poisson_break.changes.register`, as spec §11.1
says a user's module does; the desk is the commands' own (`tests/commands_targets.py`), so a case's `weak_to` names
the fault kinds it fails under. `garbled` hands the agent an error of the kind `error`, after the real tool has run.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping
from typing import Any

from poisson_break.changes import CATALOG, CallContext, Result, ToolError, register
from tests.commands_targets import desk as _desk

NAME = "garbled"


class Garbled:
    name = NAME
    surface = "tool"
    description = "the real tool runs, and the agent gets an error in place of its result"
    parameters: Mapping[str, object] = {}
    real_runs = True

    def apply(self, call: CallContext, *, real: Callable[[], Any], params: Mapping[str, object],
              rng: random.Random) -> Result | ToolError:
        real()
        return ToolError(kind="error", message="the reply could not be read")


if not any(line.surface == "tool" and line.name == NAME for line in CATALOG):
    register(Garbled())


def desk(cfg: Mapping[str, Any], seed: int) -> Any:
    return _desk(cfg, seed)
