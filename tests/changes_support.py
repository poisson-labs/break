"""What the catalogue's tests share: the spec's own tables, written out once, and the helpers that
reach `poisson_break.changes`.

The tables are literal on purpose. A test that read the names from `CATALOG` could not notice a
fault going missing from it.

The module is imported lazily, by `changes()`, so that on a tree without it each test fails on its
own and the rest of the suite still runs.

`fresh_changes()` gives a test a catalogue of its own. There is no public way to take a fault back
out once it is registered, so a test that registers one runs on a fresh import of the package, and
the suite's own import is put back afterwards.
"""

from __future__ import annotations

import importlib
import json
import random
import re
import subprocess
import sys
from collections.abc import Iterator
from types import ModuleType
from typing import Any

from tests.conftest import guarded_env

PACKAGE = "poisson_break"

# Spec §3.2: the ten tool faults, in the table's order, with its third column.
REAL_RUNS = {
    "error": False,
    "timeout": False,
    "slow": True,
    "rate_limited": False,
    "empty": True,
    "cut_off": True,
    "malformed": True,
    "stale": True,
    "lost_reply": True,
    "planted_instruction": True,
}
TOOL_FAULTS = tuple(REAL_RUNS)

# Spec §3.3 and §3.4.
INPUT_OPERATORS = ("typos", "reordered", "padded", "cut_short", "variant")
CONVERSATION_MOVES = ("repeats", "interrupts", "goes_quiet", "presses")
MODEL_FAULTS = ("error", "timeout", "rate_limited", "empty", "cut_off")

# The whole catalogue at launch, as (surface, name).
LAUNCH = frozenset(
    {("tool", n) for n in TOOL_FAULTS}
    | {("input", n) for n in INPUT_OPERATORS}
    | {("user", n) for n in CONVERSATION_MOVES}
    | {("model", n) for n in MODEL_FAULTS}
)

# Spec §11.1 invariant 7 and plan §2 item 7: nothing a user reads names the plan's machinery.
PLAN_WORDS = re.compile(r"\bBK\d|\bruling\b|\bsession\b|§", re.IGNORECASE)

# Words an error the agent sees must not carry: a fault enters where a real failure would (§3.2),
# so what the agent reads cannot say it was staged.
STAGED_WORDS = re.compile(r"poisson|\bbreak\b|inject|\bfault|simulat|\bfake\b", re.IGNORECASE)

PREVIOUS = "the answer from the call before"
REAL_TEXT = "Order 7 shipped on Tuesday and arrives on Friday by the usual carrier."


def changes() -> ModuleType:
    return importlib.import_module("poisson_break.changes")


def fresh_changes() -> Iterator[ModuleType]:
    """A fresh import of the package, with its own catalogue; the old import comes back after."""
    def ours() -> list[str]:
        return [n for n in sys.modules if n == PACKAGE or n.startswith(PACKAGE + ".")]

    saved = {n: sys.modules[n] for n in ours()}
    for n in saved:
        del sys.modules[n]
    try:
        yield importlib.import_module("poisson_break.changes")
    finally:
        for n in ours():
            del sys.modules[n]
        sys.modules.update(saved)


def one(text: str, module: ModuleType | None = None, **kwargs: Any) -> Any:
    """The one change a name holds."""
    condition = (module or changes()).parse(text, **kwargs)
    assert len(condition.changes) == 1, text
    return condition.changes[0]


def entry(surface: str, name: str, module: ModuleType | None = None) -> Any:
    """The catalogue's line for one change, found by walking `CATALOG`."""
    found = [e for e in (module or changes()).CATALOG if e.surface == surface and e.name == name]
    assert len(found) == 1, f"{surface}:{name} is listed {len(found)} times"
    return found[0]


class Real:
    """The real tool: counts its calls and returns a fixed result, or raises what it is given."""

    def __init__(self, value: Any = REAL_TEXT, raises: BaseException | None = None) -> None:
        self.value = value
        self.raises = raises
        self.calls = 0

    def __call__(self) -> Any:
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.value


def context(module: ModuleType | None = None, **over: Any) -> Any:
    """A frozen call: the second call of `lookup`, unless a test says otherwise."""
    c = module or changes()
    fields: dict[str, Any] = {
        "tool": "lookup",
        "args": {"order": 7},
        "call": 2,
        "condition": c.parse("tool:lookup#2=error"),
        "seed": 20261104,
        "previous": PREVIOUS,
        "marker": "quillfern",
    }
    fields.update(over)
    return c.CallContext(**fields)


def rng(seed: int = 20261104) -> random.Random:
    return random.Random(seed)


def apply_builtin(fault: str, real: Real | None = None, *, params: Any = None,
                  **over: Any) -> tuple[Any, Real]:
    """One launch fault's own `apply`, on a frozen call, with its declared defaults unless given."""
    line = entry("tool", fault)
    real = real if real is not None else Real()
    outcome = line.fault.apply(context(**over), real=real,
                               params=line.parameters if params is None else params, rng=rng())
    return outcome, real


def json_forms(value: Any) -> set[str]:
    """The ways a result may be written as JSON text. The spacing is not the point of any test."""
    return {json.dumps(value), json.dumps(value, ensure_ascii=False),
            json.dumps(value, separators=(",", ":")),
            json.dumps(value, ensure_ascii=False, separators=(",", ":"))}


def under_hash_seed(code: str, hash_seed: int) -> str:
    """Stdout of a fresh interpreter running `code` with the given string-hash seed, under the
    network guard. Fails the test if the interpreter fails."""
    env = guarded_env()
    env["PYTHONHASHSEED"] = str(hash_seed)
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                          env=env, stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stderr
    return done.stdout
