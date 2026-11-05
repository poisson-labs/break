"""What the runs module's tests share.

`poisson_break.hunt` is imported lazily, so on a tree without it each test fails on its own and the rest of the suite
still runs. The first part reads the module's names and its source; the second makes hunts and reads what they stored.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

# Plan BK5, "Public names (`poisson_break.hunt`)", word for word.
PUBLIC_NAMES = ("Hunt", "open_hunt", "latest_hunt", "run_arm", "run_search", "control", "ControlSummary", "Budget",
                "Target", "ToolInfo", "RunResult", "TARGET_INTERFACE_VERSION")

PROVE = "poisson_prove"


def hunt() -> ModuleType:
    return importlib.import_module("poisson_break.hunt")


def apply_module() -> ModuleType:
    return importlib.import_module("poisson_break.apply")


def interfaces() -> ModuleType:
    return importlib.import_module("poisson_break.interfaces")


def package_sources() -> dict[str, str]:
    """Every module of the package, by its file's name, as text."""
    spec = importlib.util.find_spec("poisson_break")
    assert spec is not None and spec.origin is not None
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(Path(spec.origin).parent.glob("*.py"))}


def hunt_source() -> str:
    """The runs module's own source. On a tree without the module this fails the test that asked."""
    sources = package_sources()
    assert "hunt.py" in sources, "there is no poisson_break/hunt.py"
    return sources["hunt.py"]


def prove_imports(source: str) -> list[tuple[str, str | None]]:
    """Everything `source` imports from Prove, as (module, name): `import poisson_prove.store` is
    (`poisson_prove.store`, None) and `from poisson_prove.store import Store` is (`poisson_prove.store`, `Store`).
    An import inside a function counts like one at the top."""
    found: list[tuple[str, str | None]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [(alias.name, None) for alias in node.names
                      if alias.name == PROVE or alias.name.startswith(PROVE + ".")]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            if node.module == PROVE or node.module.startswith(PROVE + "."):
                found += [(node.module, alias.name) for alias in node.names]
    return found


def private(imported: tuple[str, str | None]) -> bool:
    """Whether an import reaches into Prove's private side: a module whose name, or any part of it, starts with an
    underscore, or a name that does. `__version__` is the one name with underscores that is public."""
    module, name = imported
    parts = module.split(".")[1:]
    if name is not None and name != "__version__":
        parts.append(name)
    return any(part.startswith("_") for part in parts)


def keywords_passed(source: str) -> set[str]:
    """Every keyword any call in `source` passes, and every key of a `**{...}` written out beside it."""
    words: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg is not None:
                    words.add(keyword.arg)
                elif isinstance(keyword.value, ast.Dict):
                    words |= {key.value for key in keyword.value.keys
                              if isinstance(key, ast.Constant) and isinstance(key.value, str)}
    return words


# ---------------------------------------------------------------------------
# making a hunt: settings, cases, targets
# ---------------------------------------------------------------------------
#
# Everything below rests on the thirty-seven rulings of 2026-11-05 (Taylor: yes to all), which gave the runs module the
# shapes the plan leaves out. A test names the ruling it rests on.

import json  # noqa: E402
import math  # noqa: E402
from collections.abc import Callable, Iterable, Mapping, Sequence  # noqa: E402
from typing import Any  # noqa: E402

SEED = 20261105
ROLLOUT_ENTRY = "tests.hunt_targets:refund_agent"

DEFAULT_CHECKS = ["crashed", "hung", "ran_out", "forbidden_call", "followed_plant", "duplicate_write", "wrong"]

TOOLS: dict[str, Any] = {"lookup_order": "read", "check_policy": "read",
                         "issue_refund": {"class": "write", "repeatable": True}}

# What each plain scripted agent calls with no change, the most of each tool in one run: read from the agents' own
# docstrings and held by `tests/test_scripted_agents.py`, not read from the runs module.
CONTROL_CALLS: dict[str, dict[str, int]] = {
    "retries": {"lookup_order": 1},
    "gives_up": {"lookup_order": 2, "check_policy": 1},
    "follows_plant": {"lookup_order": 1, "check_policy": 1},
    "repeats_write": {"lookup_order": 1, "issue_refund": 1},
}
AGENT_NAMES = tuple(CONTROL_CALLS)


def settings_module() -> ModuleType:
    return importlib.import_module("poisson_break.settings")


def changes() -> ModuleType:
    return importlib.import_module("poisson_break.changes")


def records() -> ModuleType:
    return importlib.import_module("poisson_break.records")


def checks() -> ModuleType:
    return importlib.import_module("poisson_break.checks")


def targets() -> ModuleType:
    return importlib.import_module("tests.hunt_targets")


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


def settings_text(folder: Path | str, *, kind: str = "rollout", entry: str = ROLLOUT_ENTRY,
                  tools: Mapping[str, Any] | None = None, fails: Mapping[str, Any] | None = None,
                  vary: Mapping[str, Any] | None = None, env: Mapping[str, Sequence[Any]] | None = None,
                  search: Mapping[str, Any] | None = None, limits: Mapping[str, Any] | None = None) -> str:
    """A settings file as text. The defaults are small, so a hunt in a test is a handful of runs: two control repeats
    and two cases for a condition. `folder` is where hunts are kept, an absolute path under the test's own folder."""
    tables: dict[str, Mapping[str, Any]] = {
        "target": {"kind": kind, "entry": entry, "cases": "cases.jsonl"},
        "tools": TOOLS if tools is None else tools,
        "fails": {"checks": DEFAULT_CHECKS, "run_seconds": 120, **(fails or {})},
        "vary": {"tools": ["error", "timeout", "lost_reply", "planted_instruction"], "inputs": ["typos"], "max_call": 3,
                 **(vary or {})},
        "search": {"strategy": "screen", "runs": 400, "control_repeats": 2, "cases_per_condition": 2, "seed": SEED,
                   **(search or {})},
        "limits": {"hours": 2, **(limits or {})},
        "output": {"folder": str(folder)},
    }
    lines = ["version = 1"]
    for table, keys in tables.items():
        lines += ["", f"[{table}]"] + [f"{json.dumps(key)} = {_toml(value)}" for key, value in keys.items()]
        if table == "vary" and env:
            lines += ["", "[vary.env]"] + [f"{json.dumps(key)} = {_toml(list(value))}" for key, value in env.items()]
    return "\n".join(lines) + "\n"


def settings_for(folder: Path | str, **over: Any) -> Any:
    return settings_module().loads(settings_text(folder, **over))


def some_cases(n: int = 3, **keys: Any) -> tuple[dict[str, Any], ...]:
    """`n` cases as the case reader hands them over: plain mappings, each with its `id`. `keys` go on every case."""
    return tuple({"id": f"c{i}", "input": f"Where is order {i}? Please refund it.", **keys} for i in range(1, n + 1))


def case(ident: str, **keys: Any) -> dict[str, Any]:
    return {"id": ident, "input": f"Where is the order of {ident}? Please refund it.", **keys}


def desk(agent: str = "gives_up", **over: Any) -> Any:
    return targets().Desk(agent, **over)


def rollout(settings: Any) -> Any:
    """The settings' own `rollout` target, loaded as `doctor` and `hunt` load it (ruling 9)."""
    return hunt().load_target(settings)


def open_new(folder: Path | str, *, target: Any = None, cases: Sequence[Mapping[str, Any]] | None = None,
             name: str | None = "refund-agent-1", settings: Any = None, **over: Any) -> Any:
    """A new hunt, kept under `folder`. With no target given it is the desk as a way in."""
    made = settings_for(folder, **over) if settings is None else settings
    return hunt().open_hunt(made, target=desk() if target is None else target,
                            cases=some_cases() if cases is None else tuple(cases), name=name)


def condition(text: str, env: Mapping[str, Sequence[Any]] | None = None) -> Any:
    return changes().parse(text, env=env)


def name_of(what: Any) -> str:
    return what if isinstance(what, str) else changes().name(what)


@dataclass(frozen=True)
class Entry:
    """What `run_search` is handed for one condition: anything with these three (ruling 2). Search's `LogEntry` has
    them; this is the tests' own, so that no test here needs the search module."""

    condition: Any
    cases: tuple[str, ...]
    selection: Any


def entry(text: str, cases: Iterable[str], *, strategy: str = "screen", probability: float = 1.0,
          as_text: bool = False, env: Mapping[str, Sequence[Any]] | None = None) -> Entry:
    return Entry(condition=text if as_text else condition(text, env), cases=tuple(cases),
                 selection=records().Selection(strategy=strategy, probability=probability))


# ---------------------------------------------------------------------------
# reading what a hunt stored, through Prove's own store
# ---------------------------------------------------------------------------


def store_of(h: Any) -> Any:
    from poisson_prove.store import Store

    return Store(h.store)


def _plain(value: Any) -> Any:
    """A cell of the frame as plain data: a missing value is `None`, whatever the frame calls it."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return value


def rows(h: Any, arm: str) -> list[dict[str, Any]]:
    """An arm's stored rows, read by Prove's own `Store`, as plain mappings in the store's order."""
    frame = store_of(h).read(f"{h.name}-{arm}")
    return [{key: _plain(value) for key, value in row.items()} for row in frame.to_dict("records")]


def arms(h: Any) -> list[str]:
    """Every Prove run in the hunt's store, by name."""
    return store_of(h).runs()


def record(row: Mapping[str, Any]) -> Any:
    """The record a stored row carries under Break's one key."""
    return records().RunRecord.from_dict(row["meta"][records().META_KEY])


def by_case(found: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    out: dict[str, list[Mapping[str, Any]]] = {}
    for row in found:
        out.setdefault(record(row).case, []).append(row)
    return out


def told(row: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """A stored row as (outcome, failure kind)."""
    return (row["outcome"], record(row).failure.kind)


def hunt_json(h: Any) -> dict[str, Any]:
    return json.loads((h.folder / "hunt.json").read_text(encoding="utf-8"))


def stopped(fn: Callable[[], Any]) -> Any:
    """Run `fn`, which must stop short, and hand back the `HuntStopped` it raised."""
    try:
        fn()
    except hunt().HuntStopped as stop:
        return stop
    raise AssertionError("the stage ran to its end and did not stop")
