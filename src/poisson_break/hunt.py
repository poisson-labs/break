"""Runs stored on Prove: a hunt's folder, its arms, the control stage, the caps, and resuming.

A **hunt** is a folder, ``<output folder>/<name>``, holding ``hunt.json``, the proposals file a
search writes, and a Prove store. ``open_hunt`` makes one, or opens one that is there, and runs
nothing: every refusal a hunt can meet before its first run is met here. ``latest_hunt`` names
the hunt made last.

**Every run is a row in a Prove run, and Break decides its outcome.** An arm is one Prove run
in the hunt's store, named ``<hunt>-<arm>``, which Prove's own ``Store`` reads. ``run_arm``
runs one condition on its cases, each a number of times; ``run_search`` runs what a search
hands it, each condition on its own cases, into the one run of the search stage or of the
shrink stage; ``control`` runs the control arm and says what it measured. Each run goes through
the applier and the failure check, and its row's outcome is ``ok`` or ``failed``: an agent that
raises and a run past its limit are failed rows with their kind. Only a run that is not counted
has no outcome, and it carries one line saying why.

**What a row holds.** Its cell is the case, ``{"case": <id>}``, so arms line up case for case;
a search or shrink row's is the case and the condition by name. Its extra facts hold the run's
record under ``poisson_break`` and ``case_id``, and nothing of the target's own. Its seed is
Prove's, from the arm's salt and the cell, and the salt is the settings' seed and the arm's own
word, so no two arms share a seed and the same settings give the same seeds under any name.

**A run is stored the moment it finishes,** so a stop of any kind loses nothing finished, and a
cell is run once in an arm: asked for again, its stored row is handed back. That is the whole
of resuming. Open the hunt again, make the same calls, and exactly what is missing runs.

**How a stage stops short.** ``HuntStopped`` says why (``reason``), in which arm, and how many
rows the arm keeps: the run cap (``runs``), the dollar cap (``dollars``), the time cap
(``hours``), more than a tenth of the arm's runs not counted (``not counted``), a tool nobody
classed (``refused``), or a tool the control saw that the way in did not list (``tools``).
The tenth is judged over the runs this opening of the hunt has stored in the arm, once it has
stored ten, so a hunt opened again after the cause is mended goes on from where it stopped.
Ctrl-C passes through as it is. ``HuntError`` is this module's own refusal, before any run.

**A way in** is any object with the shape of ``Target``. ``RolloutTarget`` is the first: a plain
Prove target, ``(cfg, seed) -> Episode``, whose tools are wrapped with
``poisson_break.apply.wrap``. ``load_target`` makes one from the settings.

Prove's planner gives the seeds and Prove's store takes the rows. Prove's own runner is not
used: it stores a run that raised with none of its extra facts, and it finishes a run that a
search must keep adding to.
"""

from __future__ import annotations

import datetime
import importlib
import json
import math
import os
import platform
import re
import signal
import sys
import threading
import time
import tomllib
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from types import FrameType, MappingProxyType, TracebackType
from typing import Any, Final

from poisson_prove import Episode
from poisson_prove.executor import plan as _plan_run
from poisson_prove.sampler import SweepSpec
from poisson_prove.store import EpisodeRecord, RunManifest, Store, StoreError, config_hash

from poisson_break import __version__, records
from poisson_break.apply import RunOutOfTime, RunResult, Session, ToolInfo, ToolRefused
from poisson_break.changes import Change, ChangeError, Condition, InstrumentError, marker, parse
from poisson_break.changes import check_capabilities as _check_capabilities
from poisson_break.changes import name as _name_of
from poisson_break.checks import _check as _load_check
from poisson_break.checks import judge, signals, watch
from poisson_break.interfaces import TARGET_INTERFACE_VERSION, Capabilities, Target
from poisson_break.settings import HuntPlan, Settings, dump, plan_hunt

__all__ = [
    "Hunt",
    "open_hunt",
    "latest_hunt",
    "run_arm",
    "run_search",
    "control",
    "ControlSummary",
    "Budget",
    "RunRow",
    "HuntStopped",
    "HuntError",
    "Target",
    "RolloutTarget",
    "load_target",
    "Limits",
    "ToolInfo",
    "RunResult",
    "TARGET_INTERFACE_VERSION",
]

HUNT_SCHEMA: Final = "poisson_break.hunt/1"
"""The name of the shape of ``hunt.json``; its first key."""

ARM_STAGES: Final = ("control", "confirm", "reference", "recheck")
"""The stages an arm can belong to: the first word of the arm's own name."""

SEARCH_STAGES: Final = ("search", "shrink")
"""The two stages ``run_search`` stores, each one Prove run of its own."""

REASONS: Final = ("runs", "dollars", "hours", "not counted", "refused", "tools")
"""Why a stage stopped short, as ``HuntStopped.reason`` says it."""

_BUDGETED = ("control", "search", "shrink")
_HUNT_FILE = "hunt.json"
_TIME_UNIT = "seconds"
_BACKEND = "poisson-break"
_NOT_COUNTED = "not counted"
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_NAME_ROOM = 48
_MILLION = 1_000_000
_HOUR = 3600.0
# The two things Prove's own tally reads in a row's error line: a run its runner cut off, and a
# fault of its backend. A row Break did not count is neither, whatever its line happens to say.
_PROVES_MARKS = ("timeout", "infra: ")


# ---------------------------------------------------------------------------
# the two refusals
# ---------------------------------------------------------------------------


class HuntError(ValueError):
    """The runs module's own refusal, before any run: one plain line. A name that is not safe
    or is taken, a hunt that is not there, an arm whose first word is no stage, a case the hunt
    does not have, a check or a target that cannot be loaded, a listed tool with no line."""

    def __init__(self, message: str) -> None:
        super().__init__(" ".join(str(message).split()))


class HuntStopped(Exception):
    """A stage that stopped short after work started, with every finished run stored.

    ``reason`` is one of ``REASONS``. ``arm`` is the Prove run the stage was writing,
    ``<hunt>-<arm>``, and ``kept`` the rows that run holds. ``count`` is, for the reason
    ``not counted``, how many of the rows this opening of the hunt stored in that run were not
    counted: all of the run's, in a hunt opened once. ``cause`` is the refusal itself, for the
    reason ``refused``. ``tools`` names the tools the control saw called that the way in did
    not list, for the reason ``tools``."""

    def __init__(self, message: str, *, reason: str, arm: str, kept: int,
                 count: int | None = None, cause: BaseException | None = None,
                 tools: Sequence[str] = ()) -> None:
        super().__init__(" ".join(str(message).split()))
        self.reason = reason
        self.arm = arm
        self.kept = kept
        self.count = count
        self.cause = cause
        self.tools = tuple(tools)


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _shown(value: object) -> str:
    """A value in a sentence, without a Python repr of a list or a mapping."""
    if isinstance(value, str):
        return f'"{value}"'
    if value is None or isinstance(value, bool | int | float):
        return str(value)
    return f"a {type(value).__name__}"


def _one_line(wrong: BaseException) -> str:
    text = " ".join(str(wrong).split())
    return f"{type(wrong).__name__}: {text}" if text else type(wrong).__name__


def _listed(words: Sequence[str]) -> str:
    if len(words) < 2:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def _plural(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


def _number(value: object) -> float | None:
    """A count of tokens as a number, or ``None`` for anything that is not one."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) and value >= 0 else None


# ---------------------------------------------------------------------------
# the frozen objects a stage hands back
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Limits:
    """What a way in is handed as a run's limits: ``run_seconds``, the run's wall-clock limit,
    the one number the run's session and the failure check hold too. A later limit is a new
    field."""

    run_seconds: float


@dataclass(frozen=True, kw_only=True)
class RunRow:
    """One run, as a stage hands it back: the ``condition`` it ran under, the ``case`` by its
    id, its ``seed``, which is the one in the stored row, its ``outcome`` (``ok``, ``failed`` or
    ``not counted``) and the failure ``kind``, or ``None``."""

    condition: Condition
    case: str
    seed: int
    outcome: str
    kind: str | None


@dataclass(frozen=True, kw_only=True)
class Budget:
    """What a hunt may spend and what it has spent, read from what is stored.

    ``runs`` is the cap, the settings' ``search.runs``; ``runs_spent`` counts the stored rows of
    the control, search and shrink stages, runs not counted among them, and ``runs_left`` is the
    rest. ``dollars`` is the cap or ``None``; ``dollars_spent`` is every stored run's tokens at
    the two prices, ``None`` when the settings give no prices. ``hours`` is the time cap, and
    ``seconds_spent`` the stored runs' seconds, summed."""

    runs: int
    runs_spent: int
    runs_left: int
    dollars: float | None
    dollars_spent: float | None
    hours: float
    seconds_spent: float


@dataclass(frozen=True, kw_only=True)
class ControlSummary:
    """What the control stage measured, read from its stored rows.

    ``runs``, ``failed`` and ``not_counted`` count the rows. ``rate`` is failed over the runs
    that counted, and ``per_case`` the same for each case by its id; a rate with no counted run
    under it is ``None``. ``calls`` is the map of where a tool fault can land: for each case,
    each tool it called with the most calls of it in one run. ``set_aside`` names the cases that
    failed every run that counted, in the cases' own order. ``high_base_rate`` says whether more
    than half the counted runs failed. ``dollars_per_run`` is the mean cost of a run, ``None``
    without prices, and ``seconds_per_run`` its mean time. ``rows`` is every control run."""

    runs: int
    failed: int
    not_counted: int
    rate: float | None
    per_case: Mapping[str, float | None]
    calls: Mapping[str, Mapping[str, int]]
    set_aside: tuple[str, ...]
    high_base_rate: bool
    dollars_per_run: float | None
    seconds_per_run: float | None
    rows: tuple[RunRow, ...]


# ---------------------------------------------------------------------------
# the `rollout` kind: a plain Prove target
# ---------------------------------------------------------------------------


class RolloutTarget:
    """The ``rollout`` way in: a plain Prove target, ``fn(cfg, seed) -> Episode``.

    ``tools`` names the tools it lists. A run opens ``with session:`` around the target, so
    that each tool the target wrapped with ``poisson_break.apply.wrap`` reaches the run, and
    hands the target the case's own mapping as ``cfg``. The target's ``Episode`` says the rest:
    its ``outcome`` is the target's own outcome, and its ``meta`` may carry ``reply``,
    ``tokens_in``, ``tokens_out`` and ``ended``, which says ``limit`` for the agent's own step
    limit. It routes tool calls and nothing more."""

    kind = "rollout"
    framework_versions: Sequence[str] = ()

    def __init__(self, fn: Callable[[Mapping[str, Any], int], Any], *,
                 tools: Iterable[str]) -> None:
        if not callable(fn):
            raise HuntError(f"a rollout target is a function of a case and a seed, not "
                            f"{_shown(fn)}")
        if isinstance(tools, str):
            raise HuntError(f"a rollout target's tools are a list of names, not {_shown(tools)}")
        names = tuple(tools)
        for tool in names:
            if not isinstance(tool, str) or not tool:
                raise HuntError(f"a rollout target lists its tools by name, not by "
                                f"{_shown(tool)}")
        self._fn = fn
        self._tools = names

    def tools(self) -> list[ToolInfo]:
        return [ToolInfo(name=tool) for tool in self._tools]

    def capabilities(self) -> Capabilities:
        return Capabilities(tool_calls=True, model_calls=False, conversation=False)

    def run(self, case: Mapping[str, Any], session: Session, *, seed: int,
            limits: Limits) -> RunResult:
        with session:
            episode = self._fn(dict(case), seed)
        if not isinstance(episode, Episode):
            raise InstrumentError(f"the target handed back {_shown(episode)}, and a Prove "
                                  "target hands back an Episode")
        said = episode.meta
        return RunResult(
            reply=said.get("reply"),
            outcome=episode.outcome,
            tokens_in=said.get("tokens_in"),
            tokens_out=said.get("tokens_out"),
            ended="limit" if said.get("ended") == "limit" else "returned",
        )


def _is_import_path(text: str) -> bool:
    module, colon, attribute = text.partition(":")
    if not colon:
        return False
    return (all(part.isidentifier() for part in module.split("."))
            and all(part.isidentifier() for part in attribute.split(".")))


def load_target(settings: Settings) -> Target:
    """The settings' own way in, made and not run: for ``kind = "rollout"``, the function
    ``target.entry`` names by its import path, ``module:name``, listing every tool ``[tools]``
    names. An entry of another form, one that cannot be imported and one that cannot be called
    are each a ``HuntError``."""
    if not isinstance(settings, Settings):
        raise TypeError(f"a target is loaded from settings, not {type(settings).__name__}")
    kind, entry = settings.target.kind, settings.target.entry
    if kind != "rollout":
        raise HuntError(f'target.kind is "{kind}", and this loads the rollout kind: a way in '
                        "of another kind is made by its own module and handed to open_hunt")
    if not _is_import_path(entry):
        raise HuntError(f'target.entry is "{entry}", and a rollout target is named by its '
                        "import path, written module:name")
    module_name, _, attribute = entry.partition(":")
    try:
        found: Any = importlib.import_module(module_name)
        for part in attribute.split("."):
            found = getattr(found, part)
    except KeyboardInterrupt:
        raise
    except BaseException as wrong:
        # A module that exits while it is imported is one that did not load.
        raise HuntError(f'the target "{entry}" could not be loaded '
                        f"({_one_line(wrong)})") from wrong
    if not callable(found):
        raise HuntError(f'the target "{entry}" is {_shown(found)}, not something that can be '
                        "called")
    return RolloutTarget(found, tools=[tool.name for tool in settings.tools])


# ---------------------------------------------------------------------------
# a hunt
# ---------------------------------------------------------------------------


class Hunt:
    """A hunt that is open: where it is kept, what it was opened with, and its plan.

    ``name`` is the hunt's name and ``folder`` where it is kept, ``<output folder>/<name>``.
    ``store`` is its Prove store, ``folder / "store"``, and ``proposals`` the file a search
    writes its proposals to, ``folder / "proposals.jsonl"``, which this module never writes.
    ``settings``, ``cases`` and ``target`` are what it was opened with, and ``plan`` the run
    counts ``plan_hunt`` gives for these cases. ``reserve`` is how many runs a search leaves
    unspent so that shrinking has some: none under ``screen``, and for any other strategy the
    settings' candidates, times two, times the cases a condition runs on. ``budget()`` reads
    what the hunt has spent. Nothing here can be assigned."""

    __slots__ = ("name", "folder", "store", "proposals", "settings", "cases", "target", "plan",
                 "reserve", "_listed", "_capabilities", "_lines", "_fails", "_env", "_read",
                 "_since")

    name: str
    folder: Path
    store: Path
    proposals: Path
    settings: Settings
    cases: tuple[Mapping[str, Any], ...]
    target: Target
    plan: HuntPlan
    reserve: int
    _listed: tuple[str, ...]
    _capabilities: Capabilities
    _lines: Mapping[str, Any]
    _fails: Mapping[str, Any]
    _env: Mapping[str, tuple[Any, ...]]
    _read: dict[str, list[_Kept]]
    _since: dict[str, list[int]]

    def __init__(self, *, name: str, folder: Path, settings: Settings,
                 cases: tuple[Mapping[str, Any], ...], target: Target, plan: HuntPlan,
                 listed: tuple[str, ...], capabilities: Capabilities) -> None:
        search = settings.search
        held: dict[str, Any] = {
            "name": name,
            "folder": folder,
            "store": folder / "store",
            "proposals": folder / "proposals.jsonl",
            "settings": settings,
            "cases": cases,
            "target": target,
            "plan": plan,
            "reserve": (0 if search.strategy == "screen"
                        else settings.confirm.candidates * 2 * search.cases_per_condition),
            "_listed": listed,
            "_capabilities": capabilities,
            "_lines": _tool_lines(settings),
            "_fails": _fails_table(settings),
            "_env": MappingProxyType({one.name: tuple(one.values) for one in settings.vary.env}),
            # Each arm's rows as last read, so a stage does not read the whole store again for
            # every call. It is checked against the store's own count before it is believed.
            "_read": {},
            # For each arm, how many runs this opening of the hunt has stored in it and how
            # many of those were not counted: what the tenth is judged over.
            "_since": {},
        }
        for field, value in held.items():
            object.__setattr__(self, field, value)

    def __setattr__(self, field: str, value: object) -> None:
        raise AttributeError(f"a hunt is read-only: {field} cannot be assigned")

    def __delattr__(self, field: str) -> None:
        raise AttributeError(f"a hunt is read-only: {field} cannot be deleted")

    def __repr__(self) -> str:
        return f'<Hunt "{self.name}" in {self.folder}>'

    def budget(self) -> Budget:
        """What the hunt may spend and what it has spent so far, read from its store."""
        return _spent(self, _read_file(self.folder)).budget(self.settings)


def _tool_lines(settings: Settings) -> Mapping[str, Any]:
    """The settings' ``[tools]`` in the shape a run's session takes: a word where the class
    says it all, and the line's own table otherwise."""
    lines: dict[str, Any] = {}
    for tool in settings.tools:
        if not tool.repeatable and tool.stand_in is None:
            lines[tool.name] = tool.tool_class
            continue
        line: dict[str, Any] = {"class": tool.tool_class}
        if tool.repeatable:
            line["repeatable"] = True
        if tool.stand_in is not None:
            line["stand_in"] = tool.stand_in
        lines[tool.name] = MappingProxyType(line)
    return MappingProxyType(lines)


def _fails_table(settings: Settings) -> Mapping[str, Any]:
    """The settings' ``[fails]`` as the mapping the failure check reads."""
    fails = settings.fails
    table: dict[str, Any] = {
        "checks": list(fails.checks),
        "outcomes": list(fails.outcomes),
        "also": list(fails.also),
        "never_call": list(fails.never_call),
        "retry_storm_after": fails.retry_storm_after,
        "run_seconds": fails.run_seconds,
    }
    for key, value in (("own", fails.own), ("max_tool_calls", fails.max_tool_calls),
                       ("max_tokens", fails.max_tokens)):
        if value is not None:
            table[key] = value
    return MappingProxyType(table)


# --- names ---------------------------------------------------------------------------------


def _output_folder(settings: Settings) -> Path:
    """Where the settings keep their hunts. A relative folder is taken from the current one."""
    folder = Path(settings.output.folder)
    return folder if folder.is_absolute() else Path.cwd() / folder


def _target_name(entry: str) -> str:
    """The word a numbered hunt is named from: the last part of the target's entry, lower-cased,
    with each run of anything but ASCII letters and digits turned into one dash."""
    last = re.split(r"[:.]", entry)[-1]
    word = re.sub(r"[^a-z0-9]+", "-", last.lower()).strip("-")[:_NAME_ROOM].strip("-")
    return word or "hunt"


def _next_number(root: Path, word: str) -> int:
    """One more than the highest number a folder ``<word>-<n>`` has there, from 1."""
    numbered = re.compile(re.escape(word) + r"-([0-9]+)")
    highest = 0
    if root.is_dir():
        for path in root.iterdir():
            found = numbered.fullmatch(path.name)
            if found is not None:
                highest = max(highest, int(found.group(1)))
    return highest + 1


def _safe(name: object, what: str) -> str:
    if not isinstance(name, str) or _SAFE_NAME.fullmatch(name) is None:
        raise HuntError(f"{what} is {_shown(name)}, and a name is letters, digits, dots, "
                        "underscores and dashes, starting with a letter or a digit, at most 64 "
                        "characters")
    return name


# --- hunt.json -----------------------------------------------------------------------------


def _plain(value: Any) -> Any:
    """Settings as JSON holds them: a number that is not finite is written as TOML writes it."""
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")
    return value


def _settings_data(settings: Settings) -> dict[str, Any]:
    """The settings as resolved, in the file's own tables and keys, defaults included."""
    data: dict[str, Any] = _plain(tomllib.loads(dump(settings)))
    return data


def _write_file(folder: Path, data: Mapping[str, Any]) -> None:
    """Write ``hunt.json`` whole, through a temporary file, so a reader never finds half."""
    path = folder / _HUNT_FILE
    text = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _read_file(folder: Path) -> dict[str, Any]:
    """A hunt's file, read and held to its shape."""
    path = folder / _HUNT_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HuntError(f'there is no hunt at "{folder}": it holds no {_HUNT_FILE}') from None
    except (OSError, ValueError) as wrong:
        raise HuntError(f'the hunt at "{folder}" could not be read '
                        f"({_one_line(wrong)})") from None
    if not isinstance(data, dict) or data.get("schema") != HUNT_SCHEMA:
        raise HuntError(f'"{path}" is not a hunt this Break reads: its schema is not '
                        f"{HUNT_SCHEMA}")
    if not isinstance(data.get("arms"), dict) or not isinstance(data.get("stages"), list):
        raise HuntError(f'"{path}" does not say which runs are which arms')
    return data


def _made(folder: Path) -> datetime.datetime | None:
    """When the hunt in ``folder`` was made, or ``None`` for a folder that is no hunt."""
    try:
        data = json.loads((folder / _HUNT_FILE).read_text(encoding="utf-8"))
        made = datetime.datetime.fromisoformat(data["created"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("schema") != HUNT_SCHEMA:
        return None
    return made if made.tzinfo is not None else made.replace(tzinfo=datetime.UTC)


def _hunts(root: Path) -> list[tuple[datetime.datetime, str]]:
    """Every hunt kept in ``root``, as when it was made and its name."""
    if not root.is_dir():
        return []
    found = []
    for path in root.iterdir():
        made = _made(path) if path.is_dir() else None
        if made is not None:
            found.append((made, path.name))
    return found


def latest_hunt(settings: Settings) -> str | None:
    """The name of the hunt made last in the settings' output folder, or ``None`` when it holds
    none. Made last, not touched last: working on an older hunt does not make it the latest."""
    if not isinstance(settings, Settings):
        raise TypeError(f"hunts are looked for by settings, not {type(settings).__name__}")
    found = _hunts(_output_folder(settings))
    return max(found)[1] if found else None


# --- what is refused before a hunt is made -------------------------------------------------


def _case_ids(cases: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    ids: list[str] = []
    for case in cases:
        if not isinstance(case, Mapping):
            raise HuntError(f"a case is the mapping of its line, not {_shown(case)}")
        ident = case.get("id")
        if not isinstance(ident, str) or not ident:
            raise HuntError(f"a case's id is {_shown(ident)}, and each case a hunt is opened "
                            "with has an id, as the case file's reader gives it")
        if ident in ids:
            raise HuntError(f'two cases have the id "{ident}"')
        ids.append(ident)
    return tuple(ids)


def _asked_of(target: Target, settings: Settings) -> tuple[tuple[str, ...], Capabilities]:
    """Ask the way in for its tools and for what it can do, and hold both to the settings: a
    listed tool with no line is refused, and so is a ``[vary]`` entry the way in cannot make."""
    try:
        listed = tuple(info.name for info in target.tools())
        capabilities = target.capabilities()
    except KeyboardInterrupt:
        raise
    except BaseException as wrong:
        raise HuntError("the way in could not say what tools it has and what it can do "
                        f"({_one_line(wrong)})") from wrong
    if not isinstance(capabilities, Capabilities):
        raise HuntError(f"the way in said it can do {_shown(capabilities)}, and a way in "
                        "answers with what it can do of tool calls, model calls and a "
                        "conversation")
    classed = {tool.name for tool in settings.tools}
    for tool in listed:
        if not isinstance(tool, str) or not tool:
            raise HuntError(f"the way in lists a tool by {_shown(tool)}, not by its name")
        if tool not in classed:
            raise HuntError(f'the agent has the tool "{tool}", and [tools] has no line for it: '
                            "class it read, write or off")
    for change in _varied(settings):
        _check_capabilities(Condition(changes=(change,)), capabilities)
    return listed, capabilities


def _varied(settings: Settings) -> Iterator[Change]:
    """Each ``[vary]`` entry that asks something of a way in, as a change at its first
    position, in the file's order. A tool fault is asked about on the first tool Break may
    touch; inputs and surroundings ask for nothing."""
    vary = settings.vary
    first = next((tool.name for tool in settings.tools if tool.tool_class != "off"), None)
    if first is not None:
        for fault in vary.tools:
            yield Change(surface="tool", tool=first, fault=fault, call="#1")
    for move in vary.conversation:
        yield Change(surface="user", tool=None, fault=move, call="@1")
    for fault in vary.model:
        yield Change(surface="model", tool=None, fault=fault, call="#1")


def _loads(settings: Settings, lines: Mapping[str, Any], capabilities: Capabilities) -> None:
    """Load the user's own check and every stand-in, and run neither."""
    own = settings.fails.own
    if own is not None:
        try:
            _load_check(own)
        except InstrumentError as wrong:
            raise HuntError(str(wrong)) from wrong
    try:
        Session(Condition(changes=()), seed=0, tools=lines, capabilities=capabilities)
    except InstrumentError as wrong:
        raise HuntError(str(wrong)) from wrong


def open_hunt(settings: Settings, *, target: Target, cases: Sequence[Mapping[str, Any]],
              name: str | None = None, existing: bool = False) -> Hunt:
    """Make a new hunt, or with ``existing=True`` open one that is there. Nothing is run.

    ``target`` is the way in, already made, and is not compared with the settings' ``kind``.
    ``cases`` is what ``read_cases`` gives. ``name`` is the hunt's name as given: letters,
    digits, ``.``, ``_`` and ``-``, starting with a letter or a digit, at most 64 characters;
    one that is not, or is taken, is refused and never swapped for a number. With no name a new
    hunt is numbered from the target's name, one above the highest number there.

    Before anything is made: ``plan_hunt`` refuses a control stage that does not fit
    (``SettingsError``); a tool the way in lists with no line in ``[tools]``, and a check that
    cannot be loaded or called, are each a ``HuntError``; a ``[vary]`` entry the way in cannot
    make is ``NeedsAdapter``, naming the change; a stand-in a session refuses is
    ``ToolRefused``. A new hunt then has its folder and its ``hunt.json``.

    A hunt that is there is opened under the settings handed in, which apply from then on, so a
    raised cap lets a stopped hunt go on. Its seed and its case ids must be the hunt's own."""
    held = tuple(cases)
    ids = _case_ids(held)
    plan = plan_hunt(settings, cases=len(held))
    root = _output_folder(settings)

    if existing:
        if name is None:
            raise HuntError("a hunt that is there is opened by its name, and none was given")
        folder = root / _safe(name, "the hunt's name")
        if not folder.is_dir():
            raise HuntError(f'there is no hunt named "{name}" in "{root}"')
        _same_hunt(_read_file(folder), settings, ids, name)
    elif name is not None:
        folder = root / _safe(name, "the hunt's name")
        if folder.exists():
            raise HuntError(f'a hunt named "{name}" is already in "{root}": give another name, '
                            "or none for a numbered one")

    listed, capabilities = _asked_of(target, settings)
    _loads(settings, _tool_lines(settings), capabilities)

    if not existing:
        folder, name = _make_folder(root, name, settings)
        made = datetime.datetime.now(datetime.UTC)
        others = [when for when, other in _hunts(root) if other != name]
        if others and made <= max(others):
            made = max(others) + datetime.timedelta(microseconds=1)
        _write_file(folder, {
            "schema": HUNT_SCHEMA,
            "name": name,
            "created": made.isoformat(),
            "settings": _settings_data(settings),
            "cases": list(ids),
            "stages": [],
            "arms": {},
        })
    assert name is not None
    return Hunt(name=name, folder=folder, settings=settings, cases=held, target=target,
                plan=plan, listed=listed, capabilities=capabilities)


def _same_hunt(data: Mapping[str, Any], settings: Settings, ids: tuple[str, ...],
               name: str) -> None:
    """Hold a hunt opened again to what must equal the hunt as made: the seed and the case
    ids. Without them a resumed arm could not equal an unstopped one."""
    made = data.get("settings")
    seed = made.get("search", {}).get("seed") if isinstance(made, dict) else None
    if seed != settings.search.seed:
        raise HuntError(f'the hunt "{name}" was made with search.seed {_shown(seed)}, and these '
                        f"settings give {settings.search.seed}: a hunt is opened again under "
                        "its own seed")
    kept = data.get("cases")
    if not isinstance(kept, list) or sorted(kept) != sorted(ids):
        raise HuntError(f'the hunt "{name}" was made with other cases than these: a hunt is '
                        "opened again with its own cases")


def _make_folder(root: Path, name: str | None, settings: Settings) -> tuple[Path, str]:
    """Make the hunt's folder, numbering it when no name was given."""
    if name is not None:
        folder = root / name
        try:
            folder.mkdir(parents=True)
        except FileExistsError:
            raise HuntError(f'a hunt named "{name}" is already in "{root}"') from None
        return folder, name
    word = _target_name(settings.target.entry)
    while True:
        numbered = f"{word}-{_next_number(root, word)}"
        try:
            (root / numbered).mkdir(parents=True)
        except FileExistsError:
            continue
        return root / numbered, numbered


# ---------------------------------------------------------------------------
# what the store holds
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Kept:
    """One stored row, as far as this module reads it back."""

    key: tuple[str, int]
    case: str
    seed: int
    outcome: str | None
    kind: str | None
    seconds: float
    tokens: tuple[float | None, float | None]
    calls: tuple[records.Call, ...]

    def row(self, condition: Condition) -> RunRow:
        return RunRow(condition=condition, case=self.case, seed=self.seed,
                      outcome=_NOT_COUNTED if self.outcome is None else self.outcome,
                      kind=self.kind)


def _rows_of(hunt: Hunt, store: Store, run_id: str) -> list[_Kept]:
    """A Prove run's rows, read by Prove's store; none for a run that is not there yet. What
    was read last is kept and used again while the store counts as many rows as it holds: a run
    only ever gains rows."""
    if run_id not in store.runs():
        return []
    known = hunt._read.get(run_id)
    if known is not None and len(known) == store.count(run_id):
        return known
    kept: list[_Kept] = []
    for row in store.read(run_id).to_dict("records"):
        try:
            record = records.RunRecord.from_dict(row["meta"][records.META_KEY])
        except (KeyError, TypeError, records.RecordError) as wrong:
            raise HuntError(f'the run "{run_id}" holds a row with no record Break can read '
                            f"({_one_line(wrong)})") from None
        spent = row["backend_meta"].get(records.META_KEY)
        spent = spent if isinstance(spent, dict) else {}
        kept.append(_Kept(
            key=(str(row["config_hash"]), int(row["replicate_index"])),
            case=record.case,
            seed=int(row["seed"]),
            outcome=row["outcome"] if isinstance(row["outcome"], str) else None,
            kind=record.failure.kind,
            seconds=float(row["wall_time"]),
            tokens=(_number(spent.get("tokens_in")), _number(spent.get("tokens_out"))),
            calls=record.calls,
        ))
    hunt._read[run_id] = kept
    return kept


def _cost(tokens: tuple[float | None, float | None], settings: Settings) -> float:
    """One run's cost: its tokens in and out at the two prices. Tokens nobody saw cost
    nothing."""
    limits = settings.limits
    paid = 0.0
    for count, price in zip(tokens, (limits.input_per_million, limits.output_per_million),
                            strict=True):
        if count is not None and price is not None:
            paid += count * price
    return paid / _MILLION


@dataclass
class _Spent:
    """What a hunt has stored, counted for its caps: the rows of the control, search and shrink
    stages, every row's tokens and seconds, and each arm's rows by the arm's name."""

    arms: dict[str, list[_Kept]]
    stages: dict[str, str]

    def budget(self, settings: Settings) -> Budget:
        every = [row for rows in self.arms.values() for row in rows]
        runs = sum(len(rows) for run_id, rows in self.arms.items()
                   if self.stages.get(run_id) in _BUDGETED)
        priced = settings.limits.input_per_million is not None
        return Budget(
            runs=settings.search.runs,
            runs_spent=runs,
            runs_left=max(0, settings.search.runs - runs),
            dollars=settings.limits.dollars,
            dollars_spent=sum(_cost(row.tokens, settings) for row in every) if priced else None,
            hours=settings.limits.hours,
            seconds_spent=sum(row.seconds for row in every),
        )


def _spent(hunt: Hunt, data: Mapping[str, Any]) -> _Spent:
    """Read what the hunt has stored, arm by arm, as its file names them."""
    store = Store(hunt.store)
    stages = {run_id: str(about.get("stage")) for run_id, about in data["arms"].items()
              if isinstance(about, dict)}
    return _Spent(arms={run_id: list(_rows_of(hunt, store, run_id)) for run_id in stages},
                  stages=stages)


# ---------------------------------------------------------------------------
# one run
# ---------------------------------------------------------------------------


class _CutOff:
    """Cuts a run off at its limit, so that a tool that never returns ends the run and not the
    hunt. It raises ``RunOutOfTime`` inside the target, which the failure check reads as a run
    past its limit. This can be done on the main thread of a program, where the system can
    interrupt what is running; anywhere else it does nothing, and a run past its limit is still
    caught by its session's clock on its next call, and by the measured time."""

    def __init__(self, seconds: float) -> None:
        self._seconds = seconds
        self._on = (hasattr(signal, "setitimer") and hasattr(signal, "SIGALRM")
                    and threading.current_thread() is threading.main_thread())
        self._armed = False
        self._due = 0.0
        self._started = 0.0
        self._before: Any = None
        self._pending: tuple[float, float] = (0.0, 0.0)

    def _fire(self, signum: int, frame: FrameType | None) -> None:
        if not self._armed:
            return
        left = self._due - time.monotonic()
        if left > 0:
            signal.setitimer(signal.ITIMER_REAL, left)
            return
        # Asked again a second later, for an agent that swallowed the first.
        signal.setitimer(signal.ITIMER_REAL, 1.0)
        raise RunOutOfTime(f"the run passed its limit of {self._seconds:g} seconds and was "
                           "cut off")

    def __enter__(self) -> _CutOff:
        if self._on:
            self._started = time.monotonic()
            self._due = self._started + self._seconds
            self._armed = True
            self._before = signal.signal(signal.SIGALRM, self._fire)
            self._pending = signal.setitimer(signal.ITIMER_REAL, self._seconds)
        return self

    def __exit__(self, kind: type[BaseException] | None, wrong: BaseException | None,
                 trace: TracebackType | None) -> None:
        if not self._on:
            return
        self._armed = False
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self._before)
        delay, interval = self._pending
        if delay > 0:
            # A timer the program had running before the run is given back what it had left.
            left = max(delay - (time.monotonic() - self._started), 0.001)
            signal.setitimer(signal.ITIMER_REAL, left, interval)


@dataclass(frozen=True)
class _Cell:
    """One run a stage was asked for: the case, the condition, the cell and the repeat."""

    case: str
    condition: Condition
    text: str
    config: Mapping[str, str]
    repeat: int
    selection: records.Selection


@dataclass(frozen=True)
class _Ran:
    """What one run came to: the row to store, and what a stage counts of it."""

    record: EpisodeRecord
    kept: _Kept


def _passed(change: Change, values: Mapping[str, tuple[Any, ...]]) -> Any:
    """The value of a surroundings change as the settings list it, so a number stays a number."""
    for value in values.get(str(change.tool), ()):
        if str(value) == change.fault:
            return value
    return change.fault


def _run_once(hunt: Hunt, cell: _Cell, *, run_id: str, stage: str, seed: int,
              key: tuple[str, int]) -> _Ran | ToolRefused:
    """Run one cell and decide it. Hands back the row to store, or the refusal of a tool nobody
    classed, in which case nothing is stored. Ctrl-C passes through."""
    case = next(one for one in hunt.cases if one.get("id") == cell.case)
    seconds = float(hunt.settings.fails.run_seconds)
    session = Session(cell.condition, seed=seed, tools=hunt._lines,
                      marker=marker(hunt=hunt.name, case=cell.case),
                      capabilities=hunt._capabilities, run_seconds=seconds)
    passed: set[int] = set()
    try:
        seen: Mapping[str, Any] = session.case(case)
    except InstrumentError as wrong:
        seen, broke = case, wrong

        def run_agent() -> Any:
            raise broke
    else:
        given = dict(seen)
        for index, change in enumerate(cell.condition.changes):
            if change.surface == "env" and change.tool is not None:
                given[change.tool] = _passed(change, hunt._env)
                passed.add(index)
        limits = Limits(run_seconds=seconds)

        def run_agent() -> Any:
            with _CutOff(seconds):
                return hunt.target.run(given, session, seed=seed, limits=limits)

    finished = watch(run_agent, case=seen, session=session, fails=hunt._fails)
    stop = session.stopped
    if isinstance(stop, ToolRefused):
        return stop

    verdict = judge(finished)
    try:
        counted = signals(finished)
    except InstrumentError:
        counted = records.Signals(gave_up=0, retry_storm=0, over_budget=0)
    # A surroundings value was passed to the target, so it applied, on no call: the session,
    # which applies nothing for one, says otherwise.
    changes = tuple(
        replace(one, applied=True) if index in passed else one
        for index, one in enumerate(finished.condition.changes))
    record = records.RunRecord(
        hunt=hunt.name,
        stage=stage,
        arm=run_id,
        case=cell.case,
        condition=records.Condition(name=cell.text, changes=changes),
        failure=records.Failure(kind=verdict.kind, signals=counted),
        selection=cell.selection,
        calls=finished.calls,
        judged_by=verdict.judged_by,
        target_outcome=finished.outcome if isinstance(finished.outcome, str) else None,
    )
    tokens = (_number(finished.tokens_in), _number(finished.tokens_out))
    meta = {records.META_KEY: record.to_dict(), "case_id": cell.case}
    backend = {records.META_KEY: {"tokens_in": tokens[0], "tokens_out": tokens[1]}}
    if verdict.outcome is None:
        line = verdict.error or "Break could not count this run"
        if line == _PROVES_MARKS[0] or line.startswith(_PROVES_MARKS[1]):
            line = f"not counted: {line}"
        row = EpisodeRecord.errored(
            run_id=run_id, config=cell.config, seed=seed, replicate_index=cell.repeat,
            error=line, wall_time=finished.seconds, backend_meta=backend, meta=meta)
    else:
        # A row's time is the run's seconds, held to its limit, which is the row's horizon.
        episode = Episode(outcome=verdict.outcome, t=min(max(finished.seconds, 0.0), seconds),
                          horizon=seconds, meta=meta)
        row = EpisodeRecord.from_episode(
            episode, run_id=run_id, config=cell.config, seed=seed, replicate_index=cell.repeat,
            wall_time=finished.seconds, backend_meta=backend)
    return _Ran(record=row, kept=_Kept(
        key=key, case=cell.case, seed=seed, outcome=verdict.outcome, kind=verdict.kind,
        seconds=finished.seconds, tokens=tokens, calls=finished.calls))


# ---------------------------------------------------------------------------
# a stage: the cells asked for, the caps, and what is stored
# ---------------------------------------------------------------------------


def _resolved(hunt: Hunt, condition: object) -> Condition:
    """A condition as a stage takes it: the object, or its canonical name read."""
    if isinstance(condition, Condition):
        return condition
    if isinstance(condition, str):
        return parse(condition, env=dict(hunt._env))
    raise HuntError(f"a condition is a Condition or its name, not {_shown(condition)}")


def _asked(hunt: Hunt, conditions: Iterable[Condition]) -> None:
    """Ask, before any run of a call, whether the way in and a session take each condition.
    ``NeedsAdapter`` and ``ToolRefused`` pass through with their facts."""
    looked: list[Condition] = []
    for condition in conditions:
        if condition in looked:
            continue
        looked.append(condition)
        try:
            Session(condition, seed=0, tools=hunt._lines, capabilities=hunt._capabilities)
        except ChangeError:
            raise
        except InstrumentError as wrong:
            raise HuntError(str(wrong)) from wrong


def _known(hunt: Hunt, cases: object) -> list[str]:
    """Case ids as a stage takes them: each one of the hunt's own."""
    if isinstance(cases, str) or not isinstance(cases, Iterable):
        raise HuntError(f"cases are given as a list of ids, not {_shown(cases)}")
    ids = list(cases)
    own = {case.get("id") for case in hunt.cases}
    for ident in ids:
        if not isinstance(ident, str) or ident not in own:
            raise HuntError(f"the hunt has no case with the id {_shown(ident)}")
    return ids


def _salt(hunt: Hunt, word: str) -> str:
    """An arm's salt: the settings' seed and the arm's own word, and nothing of the hunt's
    name, so the same settings give the same seeds wherever the hunt is kept."""
    return f"{hunt.settings.search.seed}-{word}"


def _stop(hunt: Hunt, reason: str, run_id: str, kept: int, *, count: int | None = None,
          judged: int | None = None, cause: BaseException | None = None,
          tools: Sequence[str] = ()) -> HuntStopped:
    settings = hunt.settings
    held = f"{_plural(kept, 'run')} of {run_id} {'is' if kept == 1 else 'are'} kept"
    if reason == "runs":
        why = (f"the hunt has used its {_plural(settings.search.runs, 'run')} "
               "(search.runs)")
    elif reason == "dollars":
        why = (f"the next run could pass the cap of ${settings.limits.dollars:g} "
               "(limits.dollars)")
    elif reason == "hours":
        why = (f"the hunt's runs have taken the {settings.limits.hours:g} hours it may "
               "(limits.hours)")
    elif reason == _NOT_COUNTED and judged == kept:
        why = f"{count} of the {_plural(kept, 'run')} of {run_id} could not be counted"
        held = "they are kept"
    elif reason == _NOT_COUNTED:
        why = (f"{count} of the {judged} runs stored in {run_id} since the hunt was opened "
               "could not be counted")
        held = f"all {kept} of its runs are kept"
    elif reason == "refused":
        why = str(cause)
    else:
        why = (f"the agent called {_listed([_shown(tool) for tool in tools])}, which its way in "
               "did not list")
    return HuntStopped(f"{why}: {held}", reason=reason, arm=run_id, kept=kept, count=count,
                       cause=cause, tools=tools)


def _stage(hunt: Hunt, *, word: str, stage: str, cells: Sequence[_Cell], repeats: int,
           about: Mapping[str, Any], on_progress: Callable[[int, int], None] | None
           ) -> list[RunRow]:
    """Run what is missing of the cells asked for, in the order asked, storing each run as it
    finishes, and hand back one row for each cell: the stored row for a cell the run already
    holds."""
    run_id = f"{hunt.name}-{word}"
    if not cells:
        return []
    store = Store(hunt.store)
    data = _read_file(hunt.folder)
    spent = _spent(hunt, data)
    held = {row.key: row for row in spent.arms.get(run_id, ())}

    # Seeds and the run's name are Prove's planner's: one plan for the cells of this call.
    spec = SweepSpec.build([dict(cell.config) for cell in cells], replicates=repeats,
                           target_id=hunt.settings.target.entry, t_unit=_TIME_UNIT)
    planned = replace(_plan_run(spec, store, backend=_BACKEND, run_salt=_salt(hunt, word)),
                      run_id=run_id)
    seeds = {(pair.config_hash, pair.replicate_index): pair.seed for pair in planned.pairs}

    settings = hunt.settings
    budget = spent.budget(settings)
    counts = stage in _BUDGETED
    runs_spent = budget.runs_spent
    dollars_spent = budget.dollars_spent
    seconds_spent = budget.seconds_spent
    every = [row for rows in spent.arms.values() for row in rows]
    dearest = max((_cost(row.tokens, settings) for row in every), default=0.0)
    anything = bool(every)
    stored = len(held)
    # The tenth not counted is judged over what this opening of the hunt has stored in the
    # arm, over every call that added to it. A row an earlier opening stored is kept and is
    # not judged again, so a hunt opened again after the cause is mended goes on.
    since = hunt._since.setdefault(run_id, [0, 0])
    started = False

    out: list[RunRow] = []
    total = len(cells)
    for done, cell in enumerate(cells, start=1):
        key = (config_hash(cell.config), cell.repeat)
        if key in held:
            out.append(held[key].row(cell.condition))
            continue

        if counts and runs_spent + 1 > settings.search.runs:
            raise _stop(hunt, "runs", run_id, stored)
        if (dollars_spent is not None and settings.limits.dollars is not None and anything
                and dollars_spent + dearest > settings.limits.dollars):
            raise _stop(hunt, "dollars", run_id, stored)
        if seconds_spent >= settings.limits.hours * _HOUR:
            raise _stop(hunt, "hours", run_id, stored)

        if not started:
            _begin(hunt, data, store, planned.run_id, planned.run_salt, spec, stage, about)
            started = True
        ran = _run_once(hunt, cell, run_id=run_id, stage=stage, seed=seeds[key], key=key)
        if isinstance(ran, ToolRefused):
            raise _stop(hunt, "refused", run_id, stored, cause=ran)
        store.append(run_id, [ran.record])
        hunt._read.setdefault(run_id, []).append(ran.kept)

        held[key] = ran.kept
        out.append(ran.kept.row(cell.condition))
        stored += 1
        anything = True
        runs_spent += 1 if counts else 0
        seconds_spent += ran.kept.seconds
        cost = _cost(ran.kept.tokens, settings)
        dearest = max(dearest, cost)
        if dollars_spent is not None:
            dollars_spent += cost
        since[0] += 1
        if ran.kept.outcome is None:
            since[1] += 1
        if on_progress is not None:
            on_progress(done, total)
        if since[0] >= 10 and since[1] * 10 > since[0]:
            raise _stop(hunt, _NOT_COUNTED, run_id, stored, count=since[1], judged=since[0])
    return out


def _begin(hunt: Hunt, data: dict[str, Any], store: Store, run_id: str, salt: str,
           spec: SweepSpec, stage: str, about: Mapping[str, Any]) -> None:
    """Before the first run of a call that runs anything: say in the hunt's file which run is
    which arm, and make the Prove run. The file comes first, so that no row is ever stored
    whose arm the file does not name."""
    changed = False
    if run_id not in data["arms"]:
        data["arms"][run_id] = dict(about)
        changed = True
    if stage not in data["stages"]:
        data["stages"].append(stage)
        changed = True
    now = _settings_data(hunt.settings)
    later = data.get("later_settings")
    last = later[-1].get("settings") if isinstance(later, list) and later else data.get("settings")
    if now != last:
        # The hunt was opened again under other settings: what its later runs ran under is
        # written beside what it was made with, which stays as it was.
        data["later_settings"] = [*(later if isinstance(later, list) else []),
                                  {"from": datetime.datetime.now(datetime.UTC).isoformat(),
                                   "settings": now}]
        changed = True
    if changed:
        _write_file(hunt.folder, data)
    if run_id in store.runs():
        return
    environment: dict[str, Any] = {
        "python": sys.version,
        "platform": platform.platform(),
        "poisson_break_version": __version__,
        "hunt": hunt.name,
        "stage": stage,
    }
    if stage in ARM_STAGES:
        # An arm is one condition on its cases, so the plan of its first call is the whole
        # arm's. A search grows call by call, and no one plan says what it holds.
        environment["sweep"] = spec.to_dict()
    try:
        store.create_run(RunManifest(
            run_id=run_id, target_id=spec.target_id, t_unit=spec.t_unit, run_salt=salt,
            axis_types=dict(spec.axis_types), backend=_BACKEND, environment=environment))
    except StoreError as wrong:
        raise HuntError(f'the run "{run_id}" could not be made in the hunt\'s store '
                        f"({_one_line(wrong)})") from wrong


# ---------------------------------------------------------------------------
# the stages
# ---------------------------------------------------------------------------


def _check_progress(on_progress: object) -> None:
    if on_progress is not None and not callable(on_progress):
        raise HuntError(f"on_progress is {_shown(on_progress)}, not something that can be "
                        "called with the runs done and the runs asked for")


def _of(hunt: object) -> Hunt:
    if not isinstance(hunt, Hunt):
        raise TypeError(f"a stage runs in a hunt that is open, not in {type(hunt).__name__}")
    return hunt


def run_arm(hunt: Hunt, arm: str, cases: Sequence[str], condition: Condition | str, *,
            repeats: int, on_progress: Callable[[int, int], None] | None = None
            ) -> list[RunRow]:
    """Run one arm: ``condition`` on each of ``cases``, ``repeats`` times each, stored as the
    Prove run ``<hunt>-<arm>``. Hands back one row per run, case by case in the order given.

    ``arm`` is the arm's own word, such as ``control``, ``confirm-control`` or ``confirm-1``,
    and its first word is its stage: ``control``, ``confirm``, ``reference`` or ``recheck``.
    Every row carries the settings' strategy at probability 1. A run the arm already holds is
    not made again, so the same call on a stopped arm runs what is missing, and on a finished
    arm runs nothing. An arm asked for again under another condition, other cases or another
    number of repeats is refused."""
    hunt = _of(hunt)
    _check_progress(on_progress)
    if not isinstance(arm, str) or _SAFE_NAME.fullmatch(arm) is None:
        raise HuntError(f"an arm is named by a word such as control or confirm-1, not by "
                        f"{_shown(arm)}")
    stage = arm.split("-", 1)[0]
    if stage not in ARM_STAGES:
        raise HuntError(f'the arm "{arm}" starts with "{stage}", and an arm\'s first word is '
                        f"its stage: {', '.join(ARM_STAGES[:-1])} or {ARM_STAGES[-1]}")
    if isinstance(repeats, bool) or not isinstance(repeats, int) or repeats < 1:
        raise HuntError(f"repeats is {_shown(repeats)}, not a whole number of 1 or more")
    ids = _known(hunt, cases)
    resolved = _resolved(hunt, condition)
    text = _name_of(resolved)
    if stage == "control" and text:
        raise HuntError(f'the arm "{arm}" is of the control stage, which runs with no change, '
                        f'and was asked for under "{text}"')
    _asked(hunt, [resolved])

    about = {"stage": stage, "condition": text, "cases": ids, "repeats": repeats}
    made = _read_file(hunt.folder)["arms"].get(f"{hunt.name}-{arm}")
    if made is not None and any(made.get(key) != value for key, value in about.items()):
        raise HuntError(f'the arm "{arm}" was made under another condition, other cases or '
                        "another number of repeats, and an arm is one condition on its cases")

    selection = records.Selection(strategy=hunt.settings.search.strategy, probability=1)
    cells = [_Cell(case=ident, condition=resolved, text=text, config={"case": ident},
                   repeat=repeat, selection=selection)
             for ident in ids for repeat in range(repeats)]
    rows = _stage(hunt, word=arm, stage=stage, cells=cells, repeats=repeats, about=about,
                  on_progress=on_progress)
    _finish(hunt, f"{hunt.name}-{arm}", len({(cell.case, cell.repeat) for cell in cells}))
    return rows


def _finish(hunt: Hunt, run_id: str, cells: int) -> None:
    """Mark an arm that holds every run it was made for as complete, as Prove marks its own."""
    store = Store(hunt.store)
    if run_id not in store.runs():
        return
    if store.manifest(run_id).status != "complete" and store.count(run_id) >= cells:
        store.mark_complete(run_id)


def run_search(hunt: Hunt, entries: Iterable[Any], *, stage: str = "search",
               on_progress: Callable[[int, int], None] | None = None) -> list[RunRow]:
    """Run what a search hands over: each entry's condition once on each of its cases, in the
    entries' order and each entry's cases' order, stored in the one Prove run of the stage,
    ``<hunt>-search`` or, for ``stage="shrink"``, ``<hunt>-shrink``. Hands back one row per run.

    An entry is anything with ``condition`` (a ``Condition`` or its canonical name), ``cases``
    (the ids of the cases to run it on) and ``selection`` (a ``records.Selection``: the
    strategy and the probability it gave the condition), which each of its rows' records
    carries. A shrink row carries the entry's strategy at probability 1, since no strategy
    proposed it. A pair of case and condition the run already holds is not run again."""
    hunt = _of(hunt)
    _check_progress(on_progress)
    if stage not in SEARCH_STAGES:
        raise HuntError(f"run_search stores the search stage and the shrink stage, not "
                        f"{_shown(stage)}: an arm of another stage is run_arm's")
    if isinstance(entries, str | Mapping) or not isinstance(entries, Iterable):
        raise HuntError(f"entries are a list of what a search proposed, not {_shown(entries)}")
    cells: list[_Cell] = []
    conditions: list[Condition] = []
    for entry in entries:
        try:
            condition, cases, selection = entry.condition, entry.cases, entry.selection
        except AttributeError:
            raise HuntError(f"an entry has a condition, its cases and its selection, and "
                            f"{_shown(entry)} does not") from None
        if not isinstance(selection, records.Selection):
            raise HuntError(f"an entry's selection is {_shown(selection)}, not the strategy "
                            "and the probability it gave the condition")
        if stage == "shrink":
            selection = records.Selection(strategy=selection.strategy, probability=1)
        resolved = _resolved(hunt, condition)
        text = _name_of(resolved)
        conditions.append(resolved)
        cells += [_Cell(case=ident, condition=resolved, text=text,
                        config={"case": ident, "condition": text}, repeat=0,
                        selection=selection)
                  for ident in _known(hunt, cases)]
    _asked(hunt, conditions)
    about = {"stage": stage, "condition": None, "cases": None, "repeats": 1}
    return _stage(hunt, word=stage, stage=stage, cells=cells, repeats=1, about=about,
                  on_progress=on_progress)


def control(hunt: Hunt, *, on_progress: Callable[[int, int], None] | None = None
            ) -> ControlSummary:
    """Run what is missing of the control arm, every case the settings' ``control_repeats``
    times with no change, and say what the arm measured, read from the store. On a control
    that is finished it runs nothing and says the same.

    A tool the control saw called that the way in did not list stops the hunt here
    (``HuntStopped``, reason ``tools``), with the control's runs kept."""
    hunt = _of(hunt)
    ids = [str(case.get("id")) for case in hunt.cases]
    run_arm(hunt, "control", ids, Condition(changes=()),
            repeats=hunt.settings.search.control_repeats, on_progress=on_progress)
    run_id = f"{hunt.name}-control"
    kept = _rows_of(hunt, Store(hunt.store), run_id)
    summary = _summary(hunt, ids, kept)
    unlisted = [tool for tool in dict.fromkeys(
        tool for ident in ids for tool in summary.calls[ident]) if tool not in hunt._listed]
    if unlisted:
        raise _stop(hunt, "tools", run_id, len(kept), tools=unlisted)
    return summary


def _rate(failed: int, counted: int) -> float | None:
    return failed / counted if counted else None


def _summary(hunt: Hunt, ids: Sequence[str], kept: Sequence[_Kept]) -> ControlSummary:
    """The control arm, counted: rates over the runs that counted, the map of each case's
    calls, the cases that always fail, and the cost and time of one run."""
    by_case: dict[str, list[_Kept]] = {ident: [] for ident in ids}
    for row in kept:
        by_case.setdefault(row.case, []).append(row)
    per_case: dict[str, float | None] = {}
    calls: dict[str, Mapping[str, int]] = {}
    set_aside: list[str] = []
    for ident in ids:
        rows = sorted(by_case[ident], key=lambda row: row.key[1])
        failed = sum(1 for row in rows if row.outcome == "failed")
        counted = sum(1 for row in rows if row.outcome is not None)
        per_case[ident] = _rate(failed, counted)
        if counted and failed == counted:
            set_aside.append(ident)
        most: dict[str, int] = {}
        for row in rows:
            made: dict[str, int] = {}
            for call in row.calls:
                made[call.tool] = made.get(call.tool, 0) + 1
            for tool, count in made.items():
                most[tool] = max(most.get(tool, 0), count)
        calls[ident] = MappingProxyType(most)

    failed = sum(1 for row in kept if row.outcome == "failed")
    not_counted = sum(1 for row in kept if row.outcome is None)
    counted = len(kept) - not_counted
    priced = hunt.settings.limits.input_per_million is not None
    empty = Condition(changes=())
    ordered = [row for ident in ids for row in sorted(by_case[ident], key=lambda row: row.key[1])]
    return ControlSummary(
        runs=len(kept),
        failed=failed,
        not_counted=not_counted,
        rate=_rate(failed, counted),
        per_case=MappingProxyType(per_case),
        calls=MappingProxyType(calls),
        set_aside=tuple(set_aside),
        high_base_rate=2 * failed > counted,
        dollars_per_run=(sum(_cost(row.tokens, hunt.settings) for row in kept) / len(kept)
                         if priced and kept else None),
        seconds_per_run=sum(row.seconds for row in kept) / len(kept) if kept else None,
        rows=tuple(row.row(empty) for row in ordered),
    )
