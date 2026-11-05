"""What the confirm module's tests share: the settings, the scenarios, and the stand-in for Trace's command.

`poisson_break.confirm` is imported lazily, so on a tree without it each test fails on its own and the rest of the
suite still runs.

**The stand-in for Trace** (rulings 4 and 5 of `evidence/bk7/open-points.md`). Break runs Trace as
`python -m poisson_trace fix-check OLD NEW --store STORE --event failed --inputs all --max-mde X --json`, in the hunt's
folder. `trace_stand_in/poisson_trace` is a package of that name; `stand_in(monkeypatch)` puts it first on
`PYTHONPATH`, so the child Break starts finds it before any Trace that is installed. It answers `fix-check` with the
document the pinned Trace printed for the same two runs: it reads the two runs from the store through Prove's own
`Store`, counts each case's failed runs, runs with an outcome and runs with none, and looks those counts up in
`trace_recorded/fix_check_7e6fef6.jsonl`. It computes nothing. Counts it has no document for are an exit of 99 and a
line on stderr, so a design the recording did not foresee fails loudly instead of reading a wrong document.

The recorded documents were made by the pinned Trace, `7e6fef6`, on the stores the scenarios below make, by
`evidence/bk7/scripts/record_trace_bk7.py` in the vault: the same settings, cases, conditions and arm words, so the
same seeds and the same counts. What a test changes in a document it says, through `patch`.
"""

from __future__ import annotations

import importlib
import json
import math
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from tests import confirm_targets as targets

TESTS = Path(__file__).resolve().parent
STAND_IN = TESTS / "trace_stand_in"
RECORDED = TESTS / "trace_recorded" / "fix_check_7e6fef6.jsonl"

TRACE_COMMIT = "7e6fef64d067ecd2654bb5d4fda74d5aac03503c"
SCHEMA = "poisson-trace.fix-check/2"
VERDICTS = ("different", "no significant difference", "too small to tell")
DIRECTIONS = ("failed less in new", "failed more in new", "no direction")
LEFT_OUT = ("not re-run on the old version", "not re-run on the new version", "no outcome on the old version",
            "no outcome on the new version")

# Plan BK7, "Public names (`poisson_break.confirm`)", with the names rulings 5 to 9, 14, 16 and 17 add.
PUBLIC_NAMES = ("design", "Design", "confirm", "Confirmation", "Tested", "Finding", "write_finding", "read_finding",
                "write_candidates", "read_candidates", "reference", "replay", "Replayed", "recheck", "Rechecked",
                "ask_trace", "ConfirmError", "TRACE_VERSION")
REASONS = ("trace missing", "trace version", "trace schema", "trace answer", "no candidates", "no control",
           "nothing to ask again", "unfinished", "unknown finding")
PHRASES = ("fails less", "fails more", "no significant difference", "too small to tell")
NOTES = (None, "failed less", "not after the correction", "nothing to compare")

SEED = 20261105
FAULTS = ("error", "timeout", "rate_limited", "empty", "cut_off", "malformed", "stale", "planted_instruction")


def confirm_module() -> ModuleType:
    return importlib.import_module("poisson_break.confirm")


def hunt_module() -> ModuleType:
    return importlib.import_module("poisson_break.hunt")


def records() -> ModuleType:
    return importlib.import_module("poisson_break.records")


def changes() -> ModuleType:
    return importlib.import_module("poisson_break.changes")


def settings_module() -> ModuleType:
    return importlib.import_module("poisson_break.settings")


# ---------------------------------------------------------------------------
# settings and scenarios
# ---------------------------------------------------------------------------


def _toml(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, float) and math.isinf(value):
        return "inf"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, Mapping):
        return "{ " + ", ".join(f"{json.dumps(k)} = {_toml(v)}" for k, v in value.items()) + " }"
    return "[" + ", ".join(_toml(v) for v in value) + "]"


def settings_text(folder: Path | str, *, confirm: Mapping[str, Any] | None = None,
                  search: Mapping[str, Any] | None = None, limits: Mapping[str, Any] | None = None,
                  fails: Mapping[str, Any] | None = None) -> str:
    """A settings file for the desk: `lookup_order` a read tool, a run failing when the desk reports `unresolved`,
    every fault the scenarios use allowed, and hunts kept under `folder`."""
    tables: dict[str, Mapping[str, Any]] = {
        "target": {"kind": "rollout", "entry": "tests.confirm_targets:Coin", "cases": "cases.jsonl"},
        "tools": {targets.TOOL: "read"},
        "fails": {"outcomes": [targets.FAILING], "run_seconds": 120, **(fails or {})},
        "vary": {"tools": list(FAULTS), "inputs": [], "max_call": 3},
        "search": {"strategy": "screen", "runs": 400, "control_repeats": 2, "cases_per_condition": 2, "seed": SEED,
                   **(search or {})},
        "confirm": {"candidates": 8, "repeats": 5, "max_difference": 0.2, "q": 0.05, **(confirm or {})},
        "limits": {"hours": 2, **(limits or {})},
        "output": {"folder": str(folder)},
    }
    lines = ["version = 1"]
    for table, keys in tables.items():
        lines += ["", f"[{table}]"] + [f"{json.dumps(key)} = {_toml(value)}" for key, value in keys.items()]
    return "\n".join(lines) + "\n"


def cases(n: int, *, first: int = 1, **keys: Any) -> tuple[dict[str, Any], ...]:
    """`n` cases, `k<first>` on, each with `keys`, as the case reader hands them over."""
    return tuple({"id": f"k{i}", "input": f"Where is order {i}?", **keys} for i in range(first, first + n))


def on(fault: str, call: int = 1) -> str:
    """The condition of one fault on the desk's one tool."""
    return f"tool:{targets.TOOL}#{call}={fault}"


@dataclass(frozen=True)
class Scenario:
    """One hunt the tests confirm: its cases, its candidates best first, and the settings it is opened under. Its
    name is the hunt's name. `weak` is the desk's override, as `Coin(weak=...)` takes it."""

    name: str
    cases: tuple[dict[str, Any], ...]
    candidates: tuple[str, ...]
    confirm: Mapping[str, Any] = field(default_factory=dict)
    search: Mapping[str, Any] = field(default_factory=dict)
    limits: Mapping[str, Any] = field(default_factory=dict)

    def settings(self, folder: Path | str, **over: Any) -> Any:
        tables = {"confirm": self.confirm, "search": self.search, "limits": self.limits}
        for table, keys in over.items():
            tables[table] = {**tables.get(table, {}), **keys}
        return settings_module().loads(settings_text(folder, **tables))


# A weakness to `error` on six cases, a seventh that fails every control run and is set aside, and two candidates
# with no effect. Five repeats.
PLANTED = Scenario(
    name="planted",
    cases=cases(6, rate=0.1, weak=0.9, weak_to=["error"]) + cases(1, first=7, rate=1.0),
    candidates=(on("error"), on("timeout"), on("empty")),
)

# Two cases, two repeats, no effect: a design Trace says could not have seen a difference of 0.2.
SMALL = Scenario(
    name="small",
    cases=cases(2, rate=0.3),
    candidates=(on("timeout"),),
    confirm={"repeats": 2},
)

# Thirty cases failing 0.05 of their runs, five repeats, no effect: a design Trace says could have seen one. (Cases
# that never fail would not do: Trace refuses `--event failed` when neither run has a failed outcome.)
STEADY = Scenario(
    name="steady",
    cases=cases(30, rate=0.05),
    candidates=(on("timeout"),),
)

# A condition that makes the desk fail less: `error` brings a case failing 0.8 of its runs down to none.
LESS = Scenario(
    name="less",
    cases=cases(6, rate=0.8, weak=0.0, weak_to=["error"]),
    candidates=(on("error"), on("timeout")),
)

# Eight candidates, one mildly weak: Trace alone says different, the correction across the eight does not. The seed
# is the first from 20261105 on which that holds (`record_trace_bk7.py --choose-seeds`): `error`'s p 0.0209, 0.167
# once adjusted across the eight, and no other candidate different.
CORRECTION = Scenario(
    name="correction",
    cases=cases(8, rate=0.2, weak=0.55, weak_to=["error"]),
    candidates=tuple(on(f) for f in ("timeout", "error", "rate_limited", "empty", "cut_off", "malformed", "stale",
                                     "planted_instruction")),
    search={"seed": 20261109},
)

# Runs with no outcome: under `error` case k12 has none. Its five runs are under a tenth of the arm's sixty, so the
# runs module's tenth (BK5.12) does not stop the arm, and Trace leaves the case out of the comparison.
GAPS = Scenario(
    name="gaps",
    cases=cases(11, rate=0.1, weak=0.9, weak_to=["error"])
    + cases(1, first=12, rate=0.1, weak=0.9, weak_to=["error"], dead_to=["error"]),
    candidates=(on("error"),),
)

# A candidate Trace cannot compare: under `timeout` no case has an outcome. An arm of more than nine runs with none
# counted is stopped by the runs module's tenth first, so this arm has four: two cases, two repeats.
DEAD = Scenario(
    name="dead",
    cases=cases(2, rate=0.5, weak=0.9, weak_to=["error"], dead_to=["timeout"]),
    candidates=(on("timeout"), on("error")),
    confirm={"repeats": 2},
)

# The recheck's hunt: two findings whose references fail about 0.6 of their runs, so the agent mended, made worse or
# left alone each moves them a different way, and a recheck adjusts across two. Twelve cases, five repeats.
RECHECK = Scenario(
    name="recheck",
    cases=cases(12, rate=0.1, weak=0.6, weak_to=["error", "timeout"]),
    candidates=(on("error"), on("timeout")),
)

# A desk with no weakness at all: the null of the false-finding simulation (BK7.8), at a setting where leaving out
# the correction confirms candidates. The seeds of the stages are in `NULL_SEEDS`.
NULL = Scenario(
    name="null",
    cases=cases(12, rate=0.5),
    candidates=tuple(on(f) for f in FAULTS),
)
# The first four seeds from 20261105 on which leaving the correction out confirms a candidate, on the design's cases
# (those the control sets aside left out). On none of the 41 seeds from 20261105 to 20261145 does the correction
# confirm one (`record_trace_bk7.py --choose-seeds`).
NULL_SEEDS: tuple[int, ...] = (20261105, 20261111, 20261134, 20261145)

SCENARIOS = (PLANTED, SMALL, STEADY, LESS, CORRECTION, GAPS, DEAD, RECHECK, NULL)


def open_scenario(folder: Path | str, scenario: Scenario, *, weak: float | str | None = None, existing: bool = False,
                  name: str | None = None, **over: Any) -> Any:
    """The scenario's hunt, opened on the desk under `folder`."""
    return hunt_module().open_hunt(scenario.settings(folder, **over), target=targets.Coin(weak=weak),
                                   cases=scenario.cases, name=name or scenario.name, existing=existing)


def condition(text: str) -> Any:
    return changes().parse(text)


def name_of(what: Any) -> str:
    return what if isinstance(what, str) else changes().name(what)


def ready(folder: Path | str, scenario: Scenario, **kwargs: Any) -> Any:
    """The scenario's hunt with its control run and its candidates written: what `confirm` starts from."""
    h = open_scenario(folder, scenario, **kwargs)
    hunt_module().control(h)
    confirm_module().write_candidates(h, [condition(c) for c in scenario.candidates])
    return h


# ---------------------------------------------------------------------------
# the stand-in, as a test sets it up
# ---------------------------------------------------------------------------


def stand_in(monkeypatch: Any, tmp_path: Path, *, patch: Mapping[str, Any] | None = None,
             version: str | None = None, missing: bool = False) -> Path:
    """Put the stand-in for Trace first on `PYTHONPATH` for every child Break starts, and hand back the log it writes:
    one JSON line per call, its words and the folder it ran in. `patch` changes the documents it answers with (see
    `trace_stand_in/poisson_trace/__main__.py`); `version` is what `--version` says; `missing` makes the package
    unimportable, as when no Trace is installed."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    log = tmp_path / "trace-calls.jsonl"
    log.touch()
    path = os.pathsep.join(p for p in (str(STAND_IN), str(TESTS.parent), os.environ.get("PYTHONPATH", "")) if p)
    monkeypatch.setenv("PYTHONPATH", path)
    monkeypatch.setenv("BREAK_TEST_TRACE_LOG", str(log))
    monkeypatch.setenv("BREAK_TEST_TRACE_RECORDED", str(RECORDED))
    for key, value in (("BREAK_TEST_TRACE_PATCH", None if patch is None else json.dumps(patch)),
                       ("BREAK_TEST_TRACE_VERSION", version),
                       ("BREAK_TEST_TRACE_MISSING", "1" if missing else None)):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    return log


def calls(log: Path) -> list[dict[str, Any]]:
    """The stand-in's calls, in order."""
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def fix_checks(log: Path) -> list[dict[str, Any]]:
    """The stand-in's `fix-check` calls on a hunt's own store, leaving out the probe on a store of Break's own."""
    return [c for c in calls(log) if c["argv"][:1] == ["fix-check"] and not c.get("probe")]


# ---------------------------------------------------------------------------
# a direct call of the stand-in, and of Prove's adjustment, for the numbers to be compared with
# ---------------------------------------------------------------------------


def trace_document(h: Any, old: str, new: str, *, max_mde: float = 0.2) -> dict[str, Any]:
    """What the stand-in answers for two of the hunt's arms, called directly as a test would call Trace."""
    sys.path.insert(0, str(STAND_IN))
    try:
        answer = importlib.import_module("poisson_trace.__main__").answer
    finally:
        sys.path.remove(str(STAND_IN))
    found = answer(Path(h.store), f"{h.name}-{old}", f"{h.name}-{new}", max_mde)
    return json.loads(found["stdout"])


def adjusted(ps: Sequence[float], q: float = 0.05) -> list[float]:
    """Prove's Benjamini-Hochberg adjustment of `ps`, called directly."""
    from poisson_prove.diff import bh

    return [float(x) for x in bh(list(ps), q)]


# ---------------------------------------------------------------------------
# reading what a hunt stored, through Prove's own store
# ---------------------------------------------------------------------------


def _plain(value: Any) -> Any:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return value


def rows(h: Any, arm: str) -> list[dict[str, Any]]:
    from poisson_prove.store import Store

    frame = Store(h.store).read(f"{h.name}-{arm}")
    return [{key: _plain(value) for key, value in row.items()} for row in frame.to_dict("records")]


def arms(h: Any) -> list[str]:
    from poisson_prove.store import Store

    return sorted(Store(h.store).runs())


def record(row: Mapping[str, Any]) -> Any:
    return records().RunRecord.from_dict(row["meta"][records().META_KEY])


def seeds(h: Any, arm: str) -> set[int]:
    return {int(r["seed"]) for r in rows(h, arm)}


def cases_of(h: Any, arm: str) -> list[str]:
    """Each case of an arm once, in the order first stored."""
    return list(dict.fromkeys(record(r).case for r in rows(h, arm)))


def per_case(h: Any, arm: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows(h, arm):
        out[record(r).case] = out.get(record(r).case, 0) + 1
    return out


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def refused(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Call `fn`, which must refuse with `ConfirmError`, and hand back the error."""
    try:
        fn(*args, **kwargs)
    except confirm_module().ConfirmError as error:
        return error
    raise AssertionError("no ConfirmError was raised")


def tested_by_condition(confirmation: Any) -> dict[str, Any]:
    return {name_of(t.condition): t for t in confirmation.tested}


def names(items: Iterable[Any]) -> list[str]:
    return [name_of(x) for x in items]
