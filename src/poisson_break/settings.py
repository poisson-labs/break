"""The settings file, the case file, ``init``'s flags, and the plan shown before spending.

``break.toml`` says what to hunt, what may change, and when to stop. ``loads`` reads its text and
``load`` reads a file into a frozen ``Settings``; ``dump`` writes one back as the file ``init``
writes, with every setting that has a value on a line of its own and the ones that are off shown
commented out. ``loads(dump(s)) == s`` for every settings value, and writing again what was read
back gives the same text.

**The file is strict.** A key or a table Break does not know is refused, naming the key by its
dotted path, the line it is on and the nearest known key within two edits. A value that could
not mean anything is refused the same way: a kind, a fault, an operator, a move, a check or a
signal that is not one; a count below 1 or not a whole number; a share outside 0 to 1; a
``write`` tool whose line does not say how it is made safe; a cap in dollars without both
prices; no finite limit at all; a file with no ``version``, or one from a newer Break. Every
refusal is a ``SettingsError``: one line, with ``key`` (the dotted path), ``line`` (counted
from 1, or ``None`` where there is no line to point at) and ``suggestion``.

**Reading runs nobody's code.** Reading, checking and writing settings, reading cases, and
working out a plan or a command import no framework and none of the user's modules: not the
target, the strategy, a stand-in or the user's own check. An import path is checked for its
form, ``module:name``, and whether the module is there is asked by what loads it, before any
run. Nothing here asks what a way in can do either: a conversation move for a kind that cannot
play one reads, and is refused before any run by what holds the target.

**What is not installed yet.** A ``kind`` whose way in is an optional extra parses, so a file
written for it reads today; ``load`` refuses it in one line naming the install command, by
looking for the way in's module without importing it, so the refusal lifts the day the module
is there. The ``adaptive`` strategy is treated the same way.

**Cases.** ``read_cases`` reads a file of JSON Lines into a tuple of cases, each the mapping of
its line with an ``id`` filled in. A case needs only ``input``, non-empty text. It may carry an
``id`` (non-empty text, unique), an ``expect`` table (``reply_contains``, one string;
``calls`` and ``never_calls``, lists of strings), ``variants`` and ``turns`` (lists of
strings); any other key is kept and handed over. A case with no ``id`` takes its place among
the cases, counted from 1, as text. A blank line is skipped and still counted in line numbers.
A refusal carries the line.

**``init``'s flags.** ``INIT_FLAGS`` maps each flag to the key it sets, with one flag that
repeats for a line of ``[tools]`` and one for a setting of ``[vary.env]``.
``settings_from_init_args`` reads the words after ``init`` and ``equivalent_init_command``
writes one line a shell can run that gives the same file, byte for byte. A flag's value is
written plainly where that is safe (``--kind rollout``, ``--checks crashed,hung``) and as TOML
where it is not (``--folder '"--odd"'``, ``--outcomes '["a, b"]'``); a tool's line and a
setting of one's own are written as the file writes them.

**The plan.** ``plan_hunt`` and ``plan_confirm`` work out the run counts a spending command
shows before it starts, as frozen ``HuntPlan`` and ``ConfirmPlan``. They hold counts only: the
words on screen are the command's, and dollars wait for a control stage's measured cost. A
control stage that leaves no room for one condition is refused on ``search.runs``, naming the
smallest number that fits.
"""

from __future__ import annotations

import bisect
import importlib.util
import json
import math
import os
import re
import shlex
import tomllib
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from poisson_break.changes import CATALOG
from poisson_break.checks import CHECKS, RETRY_STORM_AFTER, RUN_SECONDS, SIGNALS

__all__ = [
    "SCHEMA_VERSION",
    "Settings",
    "TargetTable",
    "ToolLine",
    "FailsTable",
    "VaryTable",
    "EnvSetting",
    "SearchTable",
    "ConfirmTable",
    "LimitsTable",
    "OutputTable",
    "SettingsError",
    "load",
    "loads",
    "dump",
    "read_cases",
    "INIT_FLAGS",
    "settings_from_init_args",
    "equivalent_init_command",
    "install_command",
    "HuntPlan",
    "ConfirmPlan",
    "plan_hunt",
    "plan_confirm",
]

SCHEMA_VERSION = 1
"""The number ``init`` writes as ``version``. A file with a larger one is from a newer Break."""

# The six kinds of target. The core ships the first; each of the rest is an optional extra,
# found by the module its way in is built as and installed under the extra beside it.
_KINDS = ("rollout", "openai-agents", "langgraph", "crewai", "mcp", "command")
_WAYS_IN: Mapping[str, tuple[str, str]] = MappingProxyType({
    "openai-agents": ("poisson_break.adapters.openai_agents", "openai-agents"),
    "langgraph": ("poisson_break.adapters.langgraph", "langgraph"),
    "crewai": ("poisson_break.adapters.crewai", "crewai"),
    "mcp": ("poisson_break.mcp", "mcp"),
    "command": ("poisson_break.mcp", "mcp"),
})

# The strategies named by a word. `adaptive` is offered by the settings file and not built yet.
_STRATEGIES = ("screen", "random", "adaptive")
_NOT_BUILT = ("adaptive",)

_CLASSES = ("read", "write", "off")
_LINE_KEYS = ("class", "repeatable", "stand_in")
_EXPECTATIONS = ("reply_contains", "calls", "never_calls")

# What the settings file prints for the two lists that are on unless turned off. A fault added
# to the catalogue later is asked for by name; the lists themselves are checked against the live
# catalogue, so such a fault is taken once it is registered.
_FAULTS = ("error", "timeout", "slow", "rate_limited", "empty", "cut_off", "malformed", "stale",
           "lost_reply", "planted_instruction")
_OPERATORS = ("typos", "reordered", "padded", "cut_short", "variant")

_CASES = "cases.jsonl"
_MAX_CALL = 3
_STRATEGY = "screen"
_RUNS = 400
_CONTROL_REPEATS = 5
_CASES_PER_CONDITION = 4
_SEED = 20261005
_CANDIDATES = 8
_CONFIRM_REPEATS = 5
_MAX_DIFFERENCE = 0.20
_Q = 0.05
_DOLLARS = 5.00
_HOURS = 2.0
_FOLDER = "break-runs"

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_TOML_PLACE = re.compile(r"\(at line (\d+), column \d+\)\s*$")
_SHOWN = 60
_WIDTH = 104
_COMMENT_COLUMN = 36


# ---------------------------------------------------------------------------
# the refusal
# ---------------------------------------------------------------------------


class SettingsError(ValueError):
    """A settings file, a case file, a flag or a plan that is refused: one plain line.

    ``key`` is the dotted path of the setting at fault (``search.runs``), or ``None`` where no
    one setting is. ``line`` is the line it is written on, counted from 1, or ``None`` where
    there is no file or no line to point at. ``suggestion`` is the nearest known key within two
    edits of an unknown one, by its whole path, or ``None``."""

    def __init__(self, message: str, *, key: str | None = None, line: int | None = None,
                 suggestion: str | None = None) -> None:
        super().__init__(" ".join(message.split()))
        self.key = key
        self.line = line
        self.suggestion = suggestion


# ---------------------------------------------------------------------------
# the frozen settings types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TargetTable:
    """``[target]``: what to hunt."""

    kind: str
    entry: str
    cases: str


@dataclass(frozen=True)
class ToolLine:
    """One line of ``[tools]``: a tool's name, its class (``read``, ``write`` or ``off``),
    whether the test environment absorbs a repeat of it, and the stand-in called in its place,
    as an import path."""

    name: str
    tool_class: str
    repeatable: bool
    stand_in: str | None


@dataclass(frozen=True)
class FailsTable:
    """``[fails]``: what counts as a failure."""

    checks: tuple[str, ...]
    outcomes: tuple[str, ...]
    own: str | None
    also: tuple[str, ...]
    never_call: tuple[str, ...]
    retry_storm_after: int
    max_tool_calls: int | None
    max_tokens: int | None
    run_seconds: float


@dataclass(frozen=True, eq=False)
class EnvSetting:
    """One setting of ``[vary.env]``: its name and the values Break may choose from, each text,
    a number, or true or false. Two are equal when they hold the same values of the same
    types, so ``1``, ``1.0`` and ``true`` are three different values."""

    name: str
    values: tuple[str | int | float | bool, ...]

    def _held(self) -> tuple[str, tuple[tuple[str, str], ...]]:
        return self.name, tuple((type(value).__name__, repr(value)) for value in self.values)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EnvSetting):
            return NotImplemented
        return self._held() == other._held()

    def __hash__(self) -> int:
        return hash(self._held())


@dataclass(frozen=True)
class VaryTable:
    """``[vary]``: what Break may change."""

    tools: tuple[str, ...]
    inputs: tuple[str, ...]
    conversation: tuple[str, ...]
    model: tuple[str, ...]
    max_call: int
    env: tuple[EnvSetting, ...]


@dataclass(frozen=True)
class SearchTable:
    """``[search]``: how a hunt searches, and how many runs it may use."""

    strategy: str
    runs: int
    control_repeats: int
    cases_per_condition: int
    seed: int


@dataclass(frozen=True)
class ConfirmTable:
    """``[confirm]``: how candidates are confirmed."""

    candidates: int
    repeats: int
    max_difference: float
    q: float


@dataclass(frozen=True)
class LimitsTable:
    """``[limits]``: when to stop. ``dollars`` and the two prices are there together or not at
    all; ``hours`` may be ``inf`` only beside a cap in dollars."""

    dollars: float | None
    input_per_million: float | None
    output_per_million: float | None
    hours: float


@dataclass(frozen=True)
class OutputTable:
    """``[output]``: where a hunt writes."""

    folder: str


@dataclass(frozen=True)
class Settings:
    """A settings file, read and checked. Frozen all the way down, and compared by what it
    holds."""

    version: int
    target: TargetTable
    tools: tuple[ToolLine, ...]
    fails: FailsTable
    vary: VaryTable
    search: SearchTable
    confirm: ConfirmTable
    limits: LimitsTable
    output: OutputTable


@dataclass(frozen=True)
class HuntPlan:
    """The run counts of a hunt: the control stage, what is left for search and shrink, and
    the most the hunt may use."""

    control_runs: int
    search_runs: int
    runs: int


@dataclass(frozen=True)
class ConfirmPlan:
    """The run counts of confirming: the confirm stage, the most the reference stage may add,
    what it adds for each finding, and the two together."""

    confirm_runs: int
    reference_runs: int
    reference_per_finding: int
    runs: int


# ---------------------------------------------------------------------------
# the keys, in the order the file writes them
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Key:
    """One key with a fixed name: where it is, the flag that sets it, how its value is written,
    the comment the file prints beside it, and the example the file prints for it when it is
    off."""

    table: str
    name: str
    flag: str
    form: str
    comment: str = ""
    example: str = ""

    @property
    def path(self) -> str:
        return f"{self.table}.{self.name}"


# Forms: "text" (a string), "words" (a list of strings), "whole" (a whole number), "time" (a
# number of seconds or hours), "decimal" (a share, a price or a cap).
_KEYS: tuple[_Key, ...] = (
    _Key("target", "kind", "--kind", "text", comment=" | ".join(_KINDS)),
    _Key("target", "entry", "--entry", "text"),
    _Key("target", "cases", "--cases", "text"),
    _Key("fails", "checks", "--checks", "words"),
    _Key("fails", "outcomes", "--outcomes", "words",
         comment="outcomes your agent reports that count as failures",
         example='["unresolved"]'),
    _Key("fails", "own", "--own-check", "text", comment="your own check",
         example='"my_app.checks:refund_ok"'),
    _Key("fails", "also", "--also", "words", comment="promote a signal to a failure",
         example='["gave_up"]'),
    _Key("fails", "never_call", "--never-call", "words", example='["delete_account"]'),
    _Key("fails", "retry_storm_after", "--retry-storm-after", "whole",
         comment="how many calls of one tool in a row are not yet a retry storm",
         example=str(RETRY_STORM_AFTER)),
    _Key("fails", "max_tool_calls", "--max-tool-calls", "whole",
         comment="over this, a run is counted as over budget", example="40"),
    _Key("fails", "max_tokens", "--max-tokens", "whole", example="200000"),
    _Key("fails", "run_seconds", "--run-seconds", "time"),
    _Key("vary", "tools", "--vary-tools", "words"),
    _Key("vary", "inputs", "--vary-inputs", "words"),
    _Key("vary", "conversation", "--vary-conversation", "words",
         example='["repeats", "interrupts", "goes_quiet", "presses"]'),
    _Key("vary", "model", "--vary-model", "words",
         example='["error", "timeout", "rate_limited", "empty", "cut_off"]'),
    _Key("vary", "max_call", "--max-call", "whole",
         comment="the latest call to a tool that a fault may land on"),
    _Key("search", "strategy", "--strategy", "text",
         comment="screen | random | adaptive | module:Name (a strategy of your own)"),
    _Key("search", "runs", "--runs", "whole"),
    _Key("search", "control_repeats", "--control-repeats", "whole"),
    _Key("search", "cases_per_condition", "--cases-per-condition", "whole"),
    _Key("search", "seed", "--seed", "whole"),
    _Key("confirm", "candidates", "--candidates", "whole"),
    _Key("confirm", "repeats", "--confirm-repeats", "whole",
         comment="runs of each case in each arm"),
    _Key("confirm", "max_difference", "--max-difference", "decimal",
         comment="the difference Trace is asked whether it could have seen"),
    _Key("confirm", "q", "--q", "decimal"),
    _Key("limits", "dollars", "--dollars", "decimal", example="5.00"),
    _Key("limits", "input_per_million", "--input-per-million", "decimal", example="0.05"),
    _Key("limits", "output_per_million", "--output-per-million", "decimal", example="0.40"),
    _Key("limits", "hours", "--hours", "time"),
    _Key("output", "folder", "--folder", "text"),
)

_TABLES = ("target", "tools", "fails", "vary", "search", "confirm", "limits", "output")
_TOP = ("version", *_TABLES)
_ENV = "env"
_TOOL_FLAG = "--tool"
_ENV_FLAG = "--env"


def _keys_of(table: str) -> tuple[str, ...]:
    names = tuple(key.name for key in _KEYS if key.table == table)
    return (*names, _ENV) if table == "vary" else names


def _flags() -> Mapping[str, str]:
    flags: dict[str, str] = {}
    for key in _KEYS:
        flags[key.flag] = key.path
        if key.path == "target.cases":
            flags[_TOOL_FLAG] = "tools"
        if key.path == "vary.max_call":
            flags[_ENV_FLAG] = "vary.env"
    return MappingProxyType(flags)


INIT_FLAGS: Final[Mapping[str, str]] = _flags()
"""Each of ``init``'s flags and the key of the settings file it sets, in the file's order.
``--tool`` repeats, once for each line of ``[tools]``, and ``--env`` repeats, once for each
setting of ``[vary.env]``. ``version`` has no flag: ``init`` writes this module's own."""

_BY_PATH: Mapping[str, _Key] = MappingProxyType({key.path: key for key in _KEYS})
_BY_FLAG: Mapping[str, _Key] = MappingProxyType({key.flag: key for key in _KEYS})


# ---------------------------------------------------------------------------
# writing TOML
# ---------------------------------------------------------------------------

_SHORT_ESCAPES = {"\\": "\\\\", '"': '\\"', "\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f",
                  "\r": "\\r"}


def _quoted(text: str) -> str:
    """Text as a TOML string on one line: everything that is not a printable character is
    written as an escape, a line break among them."""
    out = ['"']
    for char in text:
        if char in _SHORT_ESCAPES:
            out.append(_SHORT_ESCAPES[char])
        elif char.isprintable():
            out.append(char)
        elif ord(char) <= 0xFFFF:
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(f"\\U{ord(char):08X}")
    out.append('"')
    return "".join(out)


def _key_text(name: str) -> str:
    """A key as TOML writes it: bare where it can be, quoted where a dot, a space or anything
    else would change what it names."""
    return name if _BARE_KEY.fullmatch(name) else _quoted(name)


def _dotted(path: Sequence[str]) -> str:
    return ".".join(_key_text(part) for part in path)


def _decimal(number: float) -> str:
    """A share, a price or a cap, to the last bit, with two places where it has fewer."""
    text = repr(float(number))
    if "." not in text or "e" in text or "n" in text:
        return text
    whole, _, places = text.partition(".")
    return f"{whole}.{places.ljust(2, '0')}"


def _time_text(number: float) -> str:
    """A number of seconds or hours: whole where it is whole."""
    if math.isfinite(number) and number == int(number):
        return str(int(number))
    return repr(float(number))


def _plain_value(value: object) -> str:
    """One value of a setting of the user's own."""
    if isinstance(value, str):
        return _quoted(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return repr(value)


def _array(items: Iterable[str]) -> str:
    return "[" + ", ".join(items) + "]"


def _line_text(name: str, value: str) -> str:
    """One line of a table as a flag carries it. A name that starts with a dash is quoted, so
    that the word never reads as a flag."""
    return f"{_quoted(name) if name.startswith('-') else _key_text(name)} = {value}"


def _tool_text(tool: ToolLine) -> str:
    """A tool's line: the class as a word where that says it all, a table where it does not."""
    if not tool.repeatable and tool.stand_in is None:
        return _quoted(tool.tool_class)
    fields = [f"class = {_quoted(tool.tool_class)}"]
    if tool.repeatable:
        fields.append("repeatable = true")
    if tool.stand_in is not None:
        fields.append(f"stand_in = {_quoted(tool.stand_in)}")
    return "{ " + ", ".join(fields) + " }"


def _value_of(settings: Settings, key: _Key) -> object:
    """A key's value, or ``None`` where the setting is off and the file prints it commented
    out."""
    value: object = getattr(getattr(settings, key.table), key.name)
    if key.example and key.form == "words" and not value:
        return None
    if key.path == "fails.retry_storm_after" and value == RETRY_STORM_AFTER:
        return None
    return value


def _value_text(key: _Key, value: object) -> str:
    if key.form == "words":
        assert isinstance(value, tuple)
        return _array(_quoted(word) for word in value)
    if key.form == "text":
        assert isinstance(value, str)
        return _quoted(value)
    if key.form == "whole":
        assert isinstance(value, int)
        return str(value)
    assert isinstance(value, int | float)
    return _time_text(value) if key.form == "time" else _decimal(value)


def _commented(text: str, comment: str) -> str:
    if not comment:
        return text
    return text.ljust(max(_COMMENT_COLUMN, len(text) + 3)) + "# " + comment


def _wrapped(name: str, items: Sequence[str]) -> list[str]:
    """A list on one line where it fits, and on several, lined up under its first entry, where
    it does not."""
    start = f"{name} = ["
    whole = start + ", ".join(items) + "]"
    if len(whole) <= _WIDTH or len(items) < 2:
        return [whole]
    lines: list[str] = []
    line = start
    for at, item in enumerate(items):
        piece = item + ("]" if at == len(items) - 1 else ",")
        if line == start:
            line += piece
        elif len(line) + 1 + len(piece) > _WIDTH:
            lines.append(line)
            line = " " * len(start) + piece
        else:
            line = f"{line} {piece}"
    lines.append(line)
    return lines


_HEAD = (
    "# Poisson Break: what to hunt, what may change, and when to stop.",
    "# Written by `poisson-break init`. Edit it freely; `poisson-break doctor` checks it.",
)
_TOOL_EXAMPLES = (
    ("update_notes", '{ class = "write", repeatable = true }',
     "the test environment absorbs repeats"),
    ("send_email", '"off"', "Break never touches it"),
)
_ENV_EXAMPLE = ("# [vary.env]", '# inventory = ["full", "empty"]')


def _key_lines(settings: Settings, key: _Key) -> list[str]:
    value = _value_of(settings, key)
    if value is None:
        return [_commented(f"# {key.name} = {key.example}", key.comment)]
    if key.form == "words":
        assert isinstance(value, tuple)
        lines = _wrapped(key.name, [_quoted(word) for word in value])
        if key.comment:
            lines[-1] = (_commented(lines[-1], key.comment) if len(lines) == 1
                         else f"{lines[-1]}   # {key.comment}")
        return lines
    return [_commented(f"{key.name} = {_value_text(key, value)}", key.comment)]


def dump(settings: Settings) -> str:
    """The settings as the text of ``break.toml``, as ``init`` writes it: every setting that
    has a value on its own line, in the file's order, and each one that is off commented out
    with an example. ``loads(dump(s)) == s``."""
    if not isinstance(settings, Settings):
        raise TypeError(f"dump takes settings, not {type(settings).__name__}")
    out: list[str] = [*_HEAD, f"version = {settings.version}"]
    for table in _TABLES:
        out += ["", f"[{table}]"]
        if table == "tools":
            named = {tool.name for tool in settings.tools}
            out += [f"{_key_text(tool.name)} = {_tool_text(tool)}" for tool in settings.tools]
            out += [_commented(f"# {name} = {line}", comment)
                    for name, line, comment in _TOOL_EXAMPLES if name not in named]
            continue
        for key in _KEYS:
            if key.table == table:
                out += _key_lines(settings, key)
        if table == "vary":
            out.append("")
            if settings.vary.env:
                out.append("[vary.env]")
                for setting in settings.vary.env:
                    out += _wrapped(_key_text(setting.name),
                                    [_plain_value(value) for value in setting.values])
            else:
                out += _ENV_EXAMPLE
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# what a refusal shows
# ---------------------------------------------------------------------------


def _shown(value: object) -> str:
    """A value as a refusal shows it: on one line, cut where it runs long."""
    if isinstance(value, str):
        return _quoted(value if len(value) <= _SHOWN else value[:_SHOWN] + "…")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list | tuple):
        return "a list"
    if isinstance(value, Mapping):
        return "a table"
    if isinstance(value, date | time):
        return "a date or a time"
    if value is None:
        return "nothing"
    return "a value TOML does not write"


def _listed(words: Sequence[str]) -> str:
    if len(words) < 2:
        return "".join(words)
    return ", ".join(words[:-1]) + " or " + words[-1]


def _edits(a: str, b: str, limit: int) -> int:
    """The edit distance (insert, delete, substitute), or ``limit + 1`` once it is past
    ``limit``."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            row.append(min(previous[j] + 1, row[j - 1] + 1, previous[j - 1] + (ca != cb)))
        if min(row) > limit:
            return limit + 1
        previous = row
    return previous[-1]


def _nearest(word: str, known: Iterable[tuple[str, str]]) -> str | None:
    """Of ``known``, pairs of a word and what to suggest for it, the suggestion whose word is
    nearest to ``word`` within two edits; between two as near, the first."""
    best: str | None = None
    best_edits = 3
    for candidate, suggestion in known:
        edits = _edits(word, candidate, 2)
        if edits < best_edits:
            best, best_edits = suggestion, edits
    return best


def _elsewhere(but: str | None = None) -> Iterator[tuple[str, str]]:
    """Every known key outside the table ``but``, as its last part and its whole path."""
    if but is not None:
        for name in _TOP:
            yield name, name
    for table in _TABLES:
        if table == but or table == "tools":
            continue
        for name in _keys_of(table):
            yield name, f"{table}.{name}"


def _is_import_path(text: str) -> bool:
    """Whether text has the form ``module:name``. Nothing is looked for or imported."""
    module, colon, attribute = text.partition(":")
    if not colon:
        return False
    return (all(part.isidentifier() for part in module.split("."))
            and all(part.isidentifier() for part in attribute.split(".")))


def _is_whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _has_surrogate(text: str) -> bool:
    return any(0xD800 <= ord(char) <= 0xDFFF for char in text)


# ---------------------------------------------------------------------------
# where each key of a file is written
# ---------------------------------------------------------------------------

_Path = tuple[str | int, ...]


def _where(text: str) -> dict[_Path, int]:
    """The line each key of a TOML document is first written on, counted from 1.

    TOML's reader hands back no lines, so this walks the same text: table names, keys written
    bare, quoted or dotted, and the keys of a table written on one line, past comments, strings
    of all four kinds and lists that run over several lines. ``text`` is a document the reader
    has taken, with its line ends as ``\\n``. If the walk ever loses its place it stops, and
    the keys after that have no line."""
    breaks = [at for at, char in enumerate(text) if char == "\n"]
    found: dict[_Path, int] = {}
    size = len(text)

    def note(path: _Path, at: int) -> None:
        line = bisect.bisect_left(breaks, at) + 1
        for length in range(1, len(path) + 1):
            found.setdefault(path[:length], line)

    def blank(at: int, lines: bool) -> int:
        while at < size:
            char = text[at]
            if char in " \t" or (lines and char == "\n"):
                at += 1
            elif lines and char == "#":
                while at < size and text[at] != "\n":
                    at += 1
            else:
                break
        return at

    def closing(at: int) -> int:
        while text[at] != '"':
            at += 2 if text[at] == "\\" else 1
        return at

    def after_long(at: int, quote: str) -> int:
        while True:
            if quote == '"' and text[at] == "\\":
                at += 2
            elif text.startswith(quote * 3, at):
                at += 3
                for _ in range(2):
                    if at < size and text[at] == quote:
                        at += 1
                return at
            else:
                at += 1

    def one_key(at: int) -> tuple[str, int]:
        if text[at] == '"':
            end = closing(at + 1)
            read = tomllib.loads(f"{text[at:end + 1]} = 0")
            return next(iter(read)), end + 1
        if text[at] == "'":
            end = text.index("'", at + 1)
            return text[at + 1:end], end + 1
        matched = _BARE_KEY.match(text, at)
        if matched is None:
            raise ValueError(at)
        return matched.group(), matched.end()

    def dotted(at: int) -> tuple[tuple[str, ...], int, int]:
        parts: list[str] = []
        start = at = blank(at, False)
        while True:
            part, at = one_key(blank(at, False))
            parts.append(part)
            at = blank(at, False)
            if at < size and text[at] == ".":
                at += 1
            else:
                return tuple(parts), start, at

    def value(at: int, path: _Path) -> int:
        if text.startswith('"""', at):
            return after_long(at + 3, '"')
        if text.startswith("'''", at):
            return after_long(at + 3, "'")
        char = text[at]
        if char == '"':
            return closing(at + 1) + 1
        if char == "'":
            return text.index("'", at + 1) + 1
        if char == "[":
            at += 1
            place = 0
            while True:
                at = blank(at, True)
                if text[at] == "]":
                    return at + 1
                at = blank(value(at, (*path, place)), True)
                place += 1
                if text[at] == ",":
                    at += 1
        if char == "{":
            at += 1
            while True:
                at = blank(at, True)
                if text[at] == "}":
                    return at + 1
                keys, start, at = dotted(at)
                note((*path, *keys), start)
                at = blank(value(blank(at + 1, False), (*path, *keys)), True)
                if text[at] == ",":
                    at += 1
        while at < size and text[at] not in ",]}#\n":
            at += 1
        return at

    try:
        table: _Path = ()
        at = 0
        while True:
            at = blank(at, True)
            if at >= size:
                break
            if text[at] == "[":
                double = text.startswith("[[", at)
                keys, _, end = dotted(at + (2 if double else 1))
                note(keys, at)
                table = keys
                at = end + (2 if double else 1)
            else:
                keys, start, at = dotted(at)
                note((*table, *keys), start)
                at = value(blank(at + 1, False), (*table, *keys))
    except (IndexError, ValueError, StopIteration, tomllib.TOMLDecodeError):
        pass
    return found


class _Source:
    """Where the settings being checked came from, for what a refusal says and carries."""

    def line(self, path: Sequence[str]) -> int | None:
        return None

    def named(self, path: Sequence[str]) -> str:
        return _dotted(path)


class _File(_Source):
    """A file's text: each key has the line it is written on."""

    def __init__(self, where: Mapping[_Path, int]) -> None:
        self._where = where

    def line(self, path: Sequence[str]) -> int | None:
        for length in range(len(path), 0, -1):
            line = self._where.get(tuple(path[:length]))
            if line is not None:
                return line
        return None

    def named(self, path: Sequence[str]) -> str:
        line = self._where.get(tuple(path))
        return _dotted(path) if line is None else f"{_dotted(path)} on line {line}"


class _Words(_Source):
    """``init``'s flags: each key has the flag that sets it, and no line."""

    def named(self, path: Sequence[str]) -> str:
        if path and path[0] == "tools":
            flag: str | None = _TOOL_FLAG
        elif tuple(path[:2]) == ("vary", _ENV):
            flag = _ENV_FLAG
        else:
            key = _BY_PATH.get(".".join(path[:2]))
            flag = None if key is None else key.flag
        return _dotted(path) if flag is None else f"{_dotted(path)} ({flag})"


# ---------------------------------------------------------------------------
# checking a document
# ---------------------------------------------------------------------------

_ABSENT: Final = object()


class _Check:
    """One document being checked: the tables as TOML read them, and where they came from."""

    def __init__(self, document: Mapping[str, Any], source: _Source) -> None:
        self.document = document
        self.source = source

    # --- refusing ---

    def refuse(self, path: Sequence[str], problem: str, *, suggestion: str | None = None
               ) -> SettingsError:
        return SettingsError(f"{self.source.named(path)} {problem}", key=_dotted(path),
                             line=self.source.line(path), suggestion=suggestion)

    def unknown(self, path: Sequence[str], what: str, own: Iterable[tuple[str, str]],
                elsewhere: Iterable[tuple[str, str]]) -> SettingsError:
        word = path[-1]
        suggestion = _nearest(word, own) or _nearest(word, elsewhere)
        nearest = "" if suggestion is None else f"; the nearest is {suggestion}"
        return self.refuse(path, f"is not {what}{nearest}", suggestion=suggestion)

    # --- reading ---

    def get(self, table: str, key: str) -> Any:
        held = self.document.get(table)
        return held.get(key, _ABSENT) if isinstance(held, Mapping) else _ABSENT

    def text(self, table: str, key: str, default: str | None, what: str) -> str:
        value = self.get(table, key)
        if value is _ABSENT:
            if default is None:
                raise self.refuse((table, key), f"is not given, and it is {what}")
            return default
        if not isinstance(value, str):
            raise self.refuse((table, key), f"is {_shown(value)}, not text: it is {what}")
        if not value:
            raise self.refuse((table, key), f"is empty, and it is {what}")
        return value

    def whole(self, table: str, key: str, default: int, least: int) -> int:
        value = self.get(table, key)
        if value is _ABSENT:
            return default
        if not _is_whole(value) or value < least:
            raise self.refuse((table, key),
                              f"is {_shown(value)}, not a whole number of {least} or more")
        return int(value)

    def allowance(self, key: str) -> int | None:
        value = self.get("fails", key)
        if value is _ABSENT:
            return None
        if not _is_whole(value) or value < 0:
            raise self.refuse(("fails", key),
                              f"is {_shown(value)}, not a whole number of 0 or more")
        return int(value)

    def share(self, key: str, default: float) -> float:
        value = self.get("confirm", key)
        if value is _ABSENT:
            return default
        if not _is_number(value) or not 0 < value < 1:
            raise self.refuse(("confirm", key),
                              f"is {_shown(value)}, not a number above 0 and below 1")
        return float(value)

    def amount(self, table: str, key: str, what: str, *, zero: bool = False,
               endless: bool = False) -> float | None:
        """A number of seconds, hours or dollars: above 0, or 0 too with ``zero``, and finite
        unless ``endless``."""
        value = self.get(table, key)
        if value is _ABSENT:
            return None
        allowed = (_is_number(value) and not math.isnan(value)
                   and (value > 0 or (zero and value == 0))
                   and (endless or math.isfinite(value)))
        if not allowed:
            least = "0 or more" if zero else "above 0"
            raise self.refuse((table, key), f"is {_shown(value)}, not {what} {least}")
        return float(value)

    def words(self, table: str, key: str, default: tuple[str, ...], each: str,
              known: Sequence[str] | None = None) -> tuple[str, ...]:
        value = self.get(table, key)
        if value is _ABSENT:
            return default
        path = (table, key)
        if not isinstance(value, list):
            raise self.refuse(path, f"is {_shown(value)}, not a list: each entry is {each}")
        held: list[str] = []
        for word in value:
            if not isinstance(word, str):
                raise self.refuse(path, f"holds {_shown(word)}, and each entry is {each}")
            if known is not None and word not in known:
                near = _nearest(word, ((name, name) for name in known))
                nearest = "" if near is None else f"; the nearest is {near}"
                raise self.refuse(path, f"names {_shown(word)}, which is not {each}: it takes "
                                        f"{_listed(known)}{nearest}")
            if not word:
                raise self.refuse(path, f"holds an empty entry, and each entry is {each}")
            if word in held:
                raise self.refuse(path, f"names {_shown(word)} twice")
            held.append(word)
        return tuple(held)

    # --- the version, and what is not known ---

    def version(self) -> int:
        """The file's version, checked before its keys: a file from a newer Break may well
        hold keys this one does not know, and should be told it is newer."""
        value = self.document.get("version", _ABSENT)
        if value is _ABSENT:
            return 0
        if not _is_whole(value) or value < 1:
            raise self.refuse(("version",), f"is {_shown(value)}, not the whole number "
                                            f"{SCHEMA_VERSION}")
        if value > SCHEMA_VERSION:
            raise self.refuse(("version",), f"is {value}, and this Break reads version "
                                            f"{SCHEMA_VERSION}: the file is from a newer one")
        return int(value)

    def nothing_unknown(self) -> None:
        tables = [(name, name) for name in _TOP]
        for name, held in self.document.items():
            if name not in _TOP:
                raise self.unknown((name,), "a table or a key of the settings file", tables,
                                   _elsewhere())
            if name != "version" and not isinstance(held, Mapping):
                raise self.refuse((name,), f"is {_shown(held)}, not a table: its settings go "
                                           f"under [{name}]")
        for table, held in self.document.items():
            if table == "version":
                continue
            if table == "tools":
                self.no_unknown_tool_keys(held)
                continue
            known = _keys_of(table)
            for key in held:
                if key not in known:
                    raise self.unknown((table, key), f"a setting of [{table}]",
                                       [(name, f"{table}.{name}") for name in known],
                                       _elsewhere(table))
            if table == "vary" and _ENV in held and not isinstance(held[_ENV], Mapping):
                raise self.refuse(("vary", _ENV), f"is {_shown(held[_ENV])}, not a table: "
                                                  "settings of your own go under [vary.env]")

    def no_unknown_tool_keys(self, tools: Mapping[str, Any]) -> None:
        for name, line in tools.items():
            if not isinstance(line, Mapping):
                continue
            for key in line:
                if key not in _LINE_KEYS:
                    stem = _dotted(("tools", name))
                    raise self.unknown(("tools", name, key),
                                       "part of a tool's line, which holds class, repeatable "
                                       "and stand_in",
                                       [(part, f"{stem}.{part}") for part in _LINE_KEYS], ())

    # --- the tables ---

    def target(self) -> TargetTable:
        kind = self.text("target", "kind", None, f"what your agent is built with, one of "
                                                 f"{_listed(_KINDS)}")
        if kind not in _KINDS:
            near = _nearest(kind, ((name, name) for name in _KINDS))
            nearest = "" if near is None else f"; the nearest is {near}"
            raise self.refuse(("target", "kind"), f"is {_shown(kind)}, which is not a kind of "
                                                  f"target: it takes {_listed(_KINDS)}{nearest}")
        entry = self.text("target", "entry", None, "where your agent is, such as "
                                                   "my_app.agents:refund_agent")
        cases = self.text("target", "cases", _CASES, "the file of your test cases")
        return TargetTable(kind=kind, entry=entry, cases=cases)

    def tools(self) -> tuple[ToolLine, ...]:
        held = self.document.get("tools", {})
        return tuple(self.tool(name, line) for name, line in held.items())

    def tool(self, name: str, line: object) -> ToolLine:
        path = ("tools", name)
        if not name:
            raise self.refuse(path, "is a tool with no name")
        if isinstance(line, str):
            fields: Mapping[str, Any] = {"class": line}
            at: tuple[str, ...] = path
        elif isinstance(line, Mapping):
            fields = line
            at = (*path, "class")
        else:
            raise self.refuse(path, f"is classed {_shown(line)}, not read, write or off")
        if "class" not in fields:
            raise self.refuse(path, "has no class: a tool is read, write or off")
        tool_class = fields["class"]
        if tool_class not in _CLASSES:
            raise self.refuse(at, f"is {_shown(tool_class)}, not read, write or off")
        repeatable = fields.get("repeatable", False)
        if not isinstance(repeatable, bool):
            raise self.refuse((*path, "repeatable"),
                              f"is {_shown(repeatable)}, not true or false")
        stand_in = fields.get("stand_in")
        if "stand_in" in fields:
            if not isinstance(stand_in, str) or not _is_import_path(stand_in):
                raise self.refuse((*path, "stand_in"),
                                  f"is {_shown(stand_in)}, not an import path written "
                                  "module:name")
            if tool_class == "off":
                raise self.refuse((*path, "stand_in"),
                                  "names a stand-in for a tool that is off, which Break never "
                                  "touches: class it read or write, or take the stand-in out")
        if tool_class == "write" and not repeatable and stand_in is None:
            raise self.refuse(path, "is a write tool, and its line does not say how it is "
                                    'made safe: { class = "write", repeatable = true } where '
                                    "the test environment absorbs repeats, or a stand_in to "
                                    "call in its place")
        return ToolLine(name=name, tool_class=tool_class, repeatable=repeatable,
                        stand_in=stand_in)

    def fails(self) -> FailsTable:
        checks = self.words("fails", "checks", CHECKS, "a check", CHECKS)
        outcomes = self.words("fails", "outcomes", (), "an outcome your agent reports")
        own = self.import_path("fails", "own", "your own check")
        also = self.words("fails", "also", (), "a signal", SIGNALS)
        never_call = self.words("fails", "never_call", (), "a tool's name")
        after = self.allowance("retry_storm_after")
        max_tool_calls = self.allowance("max_tool_calls")
        max_tokens = self.allowance("max_tokens")
        seconds = self.amount("fails", "run_seconds", "a number of seconds")
        return FailsTable(
            checks=checks, outcomes=outcomes, own=own, also=also, never_call=never_call,
            retry_storm_after=RETRY_STORM_AFTER if after is None else after,
            max_tool_calls=max_tool_calls, max_tokens=max_tokens,
            run_seconds=float(RUN_SECONDS) if seconds is None else seconds)

    def import_path(self, table: str, key: str, what: str) -> str | None:
        value = self.get(table, key)
        if value is _ABSENT:
            return None
        if not isinstance(value, str) or not _is_import_path(value):
            raise self.refuse((table, key), f"is {_shown(value)}, and {what} is named by an "
                                            "import path written module:name")
        return value

    def catalogue(self, surface: str) -> tuple[str, ...]:
        """The names the catalogue holds for a surface, as it stands now."""
        return tuple(line.name for line in CATALOG if line.surface == surface)

    def vary(self) -> VaryTable:
        return VaryTable(
            tools=self.words("vary", "tools", _FAULTS, "a tool fault", self.catalogue("tool")),
            inputs=self.words("vary", "inputs", _OPERATORS, "an input operator",
                              self.catalogue("input")),
            conversation=self.words("vary", "conversation", (), "a conversation move",
                                    self.catalogue("user")),
            model=self.words("vary", "model", (), "a model fault", self.catalogue("model")),
            max_call=self.whole("vary", "max_call", _MAX_CALL, 1),
            env=self.env())

    def env(self) -> tuple[EnvSetting, ...]:
        held = self.get("vary", _ENV)
        if held is _ABSENT:
            return ()
        settings: list[EnvSetting] = []
        for name, values in held.items():
            path = ("vary", _ENV, name)
            if not name:
                raise self.refuse(path, "is a setting with no name")
            if not isinstance(values, list):
                raise self.refuse(path, f"is {_shown(values)}, not a list of the values Break "
                                        "may choose from")
            texts: list[str] = []
            for value in values:
                if not isinstance(value, str | int | float):
                    raise self.refuse(path, f"holds {_shown(value)}, and each value is text, "
                                            "a number, or true or false")
                if str(value) in texts:
                    raise self.refuse(path, f"lists {_shown(value)} twice: a value is named "
                                            "by its text, and two cannot share one")
                texts.append(str(value))
            settings.append(EnvSetting(name=name, values=tuple(values)))
        return tuple(settings)

    def search(self) -> SearchTable:
        value = self.get("search", "strategy")
        if value is _ABSENT:
            strategy = _STRATEGY
        elif isinstance(value, str) and (value in _STRATEGIES or _is_import_path(value)):
            strategy = value
        else:
            raise self.refuse(("search", "strategy"),
                              f"is {_shown(value)}, which is neither {_listed(_STRATEGIES)} nor "
                              "a strategy of your own named by an import path written "
                              "module:Name")
        return SearchTable(
            strategy=strategy,
            runs=self.whole("search", "runs", _RUNS, 1),
            control_repeats=self.whole("search", "control_repeats", _CONTROL_REPEATS, 1),
            cases_per_condition=self.whole("search", "cases_per_condition",
                                           _CASES_PER_CONDITION, 1),
            seed=self.whole("search", "seed", _SEED, 0))

    def confirm(self) -> ConfirmTable:
        return ConfirmTable(
            candidates=self.whole("confirm", "candidates", _CANDIDATES, 1),
            repeats=self.whole("confirm", "repeats", _CONFIRM_REPEATS, 1),
            max_difference=self.share("max_difference", _MAX_DIFFERENCE),
            q=self.share("q", _Q))

    def limits(self) -> LimitsTable:
        dollars = self.amount("limits", "dollars", "a number of dollars")
        paid_in = self.amount("limits", "input_per_million", "a price in dollars", zero=True)
        paid_out = self.amount("limits", "output_per_million", "a price in dollars", zero=True)
        hours = self.amount("limits", "hours", "a number of hours", endless=True)
        if dollars is not None and (paid_in is None or paid_out is None):
            raise self.refuse(("limits", "dollars"),
                              "is a cap in dollars, and dollars are counted from the two "
                              "prices: give input_per_million and output_per_million too, or "
                              "take the cap out")
        if (paid_in is None) != (paid_out is None):
            given, other = (("input_per_million", "output_per_million") if paid_out is None
                            else ("output_per_million", "input_per_million"))
            raise self.refuse(("limits", given), f"is one price without the other: give "
                                                 f"{other} too, or take this one out")
        if paid_in is not None and paid_out is not None:
            if paid_in == 0 and paid_out == 0:
                raise self.refuse(("limits", "input_per_million"),
                                  "and output_per_million are both 0, so a cap in dollars "
                                  "could never stop a hunt: give a price above 0, or take "
                                  "both out")
            if dollars is None:
                dollars = _DOLLARS
        if hours is None:
            hours = _HOURS
        if math.isinf(hours) and dollars is None:
            raise self.refuse(("limits", "hours"),
                              "is inf with no cap in dollars, which leaves a hunt no limit at "
                              "all: give a number of hours, or the two prices")
        return LimitsTable(dollars=dollars, input_per_million=paid_in,
                           output_per_million=paid_out, hours=hours)

    def output(self) -> OutputTable:
        return OutputTable(folder=self.text("output", "folder", _FOLDER,
                                            "the folder a hunt writes to"))

    def settings(self) -> Settings:
        version = self.version()
        self.nothing_unknown()
        if not version:
            raise self.refuse(("version",), f"is not given: the file starts with version = "
                                            f"{SCHEMA_VERSION}")
        return Settings(version=version, target=self.target(), tools=self.tools(),
                        fails=self.fails(), vary=self.vary(), search=self.search(),
                        confirm=self.confirm(), limits=self.limits(), output=self.output())


# ---------------------------------------------------------------------------
# reading break.toml
# ---------------------------------------------------------------------------

# What TOML's reader says, in the words a settings file's reader should hear. It says some of
# these with the key written as Python writes a tuple, which no user should be shown.
_NOT_TOML = (
    ("Cannot declare", "a table is given twice"),
    ("Cannot overwrite", "a key is given twice"),
    ("Cannot mutate", "a table written on one line is added to further down"),
    ("Cannot redefine", "a table or a key is given twice"),
    ("Duplicate inline table key", "a key is given twice in a table written on one line"),
    ("Expected '='", "a key has no = after it"),
    ("Expected ']]'", "a table's name has no closing ]]"),
    ("Expected ']'", "a table's name has no closing ]"),
    ("Expected newline", "there is more after a value, where the line should end"),
    ("Invalid date", "a date is not written as TOML writes one"),
    ("Invalid hex", "an escaped character in a string is not written right"),
    ("Invalid initial character", "a key starts with a character a key cannot hold"),
    ("Invalid statement", "the line is neither a key with a value nor a table's name"),
    ("Invalid value", "a value is missing, or is not written as TOML writes one"),
    ("Unclosed array", "a list has no closing ]"),
    ("Unclosed inline table", "a table written on one line has no closing }"),
    ("Unescaped", "a backslash in a string is followed by nothing TOML reads"),
    ("Unterminated string", "a string has no closing quote"),
    ("Escaped character", "an escaped character in a string is not one TOML allows"),
    ("Found invalid character", "there is a character TOML does not allow"),
    ("Illegal character", "a string holds a line break or a character TOML does not allow; a "
                          "missing closing quote does this"),
)


def _not_toml(text: str, wrong: tomllib.TOMLDecodeError) -> SettingsError:
    said = str(wrong)
    place = _TOML_PLACE.search(said)
    line = int(place.group(1)) if place else text.rstrip("\n").count("\n") + 1
    reason = next((ours for theirs, ours in _NOT_TOML if said.startswith(theirs)),
                  "it cannot be read")
    return SettingsError(f"line {line} is not TOML: {reason}", line=line)


def _read(text: str) -> tuple[Settings, _File]:
    if not isinstance(text, str):
        raise TypeError(f"loads takes the text of a settings file, not {type(text).__name__}")
    if _has_surrogate(text):
        raise SettingsError("the settings hold a character that is not text")
    text = text.replace("\r\n", "\n")
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as wrong:
        raise _not_toml(text, wrong) from None
    source = _File(_where(text))
    return _Check(document, source).settings(), source


def loads(text: str) -> Settings:
    """The settings a file's text holds, checked. Refused with ``SettingsError``. A kind or a
    strategy that is not installed yet reads here; ``load`` is what refuses it."""
    return _read(text)[0]


def _file_text(path: str | os.PathLike[str], what: str) -> tuple[str, str]:
    """A file's text and its name, or a refusal in one line."""
    name = Path(path).name or str(path)
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        raise SettingsError(f"there is no {what} at {_quoted(str(path))}") from None
    except OSError as wrong:
        reason = wrong.strerror or type(wrong).__name__
        raise SettingsError(f"{name} could not be read: {reason}") from None
    try:
        return raw.decode("utf-8-sig"), name
    except UnicodeDecodeError as wrong:
        line = raw.count(b"\n", 0, wrong.start) + 1
        raise SettingsError(f"line {line} of {name} is not text in UTF-8", line=line) from None


def _module_is_there(name: str) -> bool:
    """Whether a module of this package can be found, without importing it."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def install_command(kind: str) -> str | None:
    """The ``pip install`` line that puts the way in for ``kind`` on this machine, when it is an
    optional extra that is not installed; ``None`` for the core's own kind, and for a kind whose
    way in is there. Looking for the way in imports nothing. The line is the one ``load``'s
    refusal names, and the one ``init`` ends with for such a kind."""
    if not isinstance(kind, str):
        raise TypeError(f"a kind is a word, not {type(kind).__name__}")
    if kind not in _WAYS_IN:
        return None
    module, extra = _WAYS_IN[kind]
    if _module_is_there(module):
        return None
    return f"pip install 'poisson-break[{extra}]'"


def load(path: str | os.PathLike[str]) -> Settings:
    """The settings in a file, checked as ``loads`` checks them, and then for what is not
    installed: a ``kind`` whose way in is an optional extra that is not there is refused in one
    line naming the install command (``install_command``), and so is a strategy that is not
    built yet. Looking for a way in imports nothing."""
    text, _ = _file_text(path, "settings file")
    settings, source = _read(text)
    kind = settings.target.kind
    install = install_command(kind)
    if install is not None:
        at = ("target", "kind")
        raise SettingsError(
            f'{source.named(at)} is "{kind}", and that way in is not installed: {install}',
            key=_dotted(at), line=source.line(at))
    if settings.search.strategy in _NOT_BUILT:
        at = ("search", "strategy")
        raise SettingsError(
            f'{source.named(at)} is "{settings.search.strategy}", which is not in this version '
            f"of Break: use screen or random", key=_dotted(at), line=source.line(at))
    return settings


# ---------------------------------------------------------------------------
# the case file
# ---------------------------------------------------------------------------


def _no_constant(word: str) -> Any:
    raise ValueError(word)


def _once(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    held: dict[str, Any] = {}
    for key, value in pairs:
        if key in held:
            raise ValueError(key)
        held[key] = value
    return held


def _is_texts(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _case_problem(case: Mapping[str, Any]) -> tuple[str | None, str] | None:
    """What is wrong with one case, as the field at fault and one clause, or ``None``."""
    if "input" not in case:
        return "input", "has no input, and a case needs one"
    if not isinstance(case["input"], str) or not case["input"]:
        return "input", f"has an input that is {_shown(case['input'])}, not text"
    if case.get("id") is not None and (not isinstance(case["id"], str) or not case["id"]):
        return "id", f"has an id that is {_shown(case['id'])}, not text"
    expect = case.get("expect")
    if expect is not None:
        if not isinstance(expect, Mapping):
            return "expect", (f"has an expect that is {_shown(expect)}, not a table of "
                              f"{_listed(_EXPECTATIONS)}")
        for key in expect:
            if key not in _EXPECTATIONS:
                near = _nearest(key, ((name, name) for name in _EXPECTATIONS))
                nearest = "" if near is None else f"; the nearest is {near}"
                return f"expect.{key}", (f"expects {_shown(key)}, and an expectation is "
                                         f"{_listed(_EXPECTATIONS)}{nearest}")
        if "reply_contains" in expect and not isinstance(expect["reply_contains"], str):
            return "expect.reply_contains", (
                f"has a reply_contains that is {_shown(expect['reply_contains'])}, not one "
                "string")
        for key in ("calls", "never_calls"):
            if key in expect and not _is_texts(expect[key]):
                return f"expect.{key}", f"has {key} that are not a list of tools' names"
    for key in ("variants", "turns"):
        if case.get(key) is not None and not _is_texts(case[key]):
            return key, f"has {key} that are not a list of text"
    return None


def read_cases(path: str | os.PathLike[str]) -> tuple[dict[str, Any], ...]:
    """The cases in a file of JSON Lines, in the file's order, each the mapping of its line
    with its ``id`` filled in. The whole file is read and checked before anything is handed
    over, and a refusal is a ``SettingsError`` carrying the line."""
    text, name = _file_text(path, "file of cases")

    def refused(line: int, problem: str, key: str | None = None) -> SettingsError:
        return SettingsError(f"line {line} of {name} {problem}", key=key, line=line)

    cases: list[tuple[int, dict[str, Any]]] = []
    named: dict[str, int] = {}
    for line, written in enumerate(text.split("\n"), 1):
        if not written.strip():
            continue
        try:
            case = json.loads(written, parse_constant=_no_constant, object_pairs_hook=_once)
        except (ValueError, RecursionError):
            raise refused(line, "is not one JSON object with each key once") from None
        if not isinstance(case, dict):
            raise refused(line, f"is {_shown(case)}, not a case: a case is a JSON object "
                                "with an input")
        problem = _case_problem(case)
        if problem is not None:
            raise refused(line, problem[1], problem[0])
        given = case.get("id")
        if given is not None:
            if given in named:
                raise refused(line, f"has the id {_shown(given)}, which line {named[given]} "
                                    "has too", "id")
            named[given] = line
        cases.append((line, case))
    if not cases:
        raise SettingsError(f"{name} holds no cases: a case is one line, a JSON object with "
                            "an input")
    numbers = {str(place) for place, (_, case) in enumerate(cases, 1) if case.get("id") is None}
    for given, line in named.items():
        if given in numbers:
            raise refused(line, f"has the id {_shown(given)}, which is the number case "
                                f"{given} takes for having no id: name one of the two "
                                "otherwise", "id")
    return tuple(case if case.get("id") is not None else {**case, "id": str(place)}
                 for place, (_, case) in enumerate(cases, 1))


# ---------------------------------------------------------------------------
# init's flags, and the equivalent command
# ---------------------------------------------------------------------------


def _is_bare(text: str) -> bool:
    """Whether a flag can carry text as it stands, with nothing that reads as a flag, as TOML
    or as more than one line."""
    return bool(text) and text[0] not in '"-[' and text.isprintable()


def _toml_value(text: str) -> Any:
    """One value written as TOML, or ``ValueError``."""
    try:
        read = tomllib.loads(f"value = {text}")
    except tomllib.TOMLDecodeError:
        raise ValueError(text) from None
    if list(read) != ["value"]:
        raise ValueError(text)
    return read["value"]


def _flag_value(key: _Key, word: str) -> Any:
    """What a flag's word says, as TOML would have read it from the file."""
    if key.form == "text":
        return _toml_value(word) if word.startswith('"') else word
    if key.form == "words":
        return _toml_value(word) if word.startswith("[") else word.split(",")
    return _toml_value(word)


def _flag_line(word: str) -> tuple[str, Any]:
    """One line of a table, written as the file writes it: its name and its value."""
    try:
        read = tomllib.loads(word)
    except tomllib.TOMLDecodeError:
        raise ValueError(word) from None
    if len(read) != 1:
        raise ValueError(word)
    return next(iter(read.items()))


def settings_from_init_args(words: Sequence[str]) -> Settings:
    """The settings ``init``'s flags ask for: ``words`` are the words after ``init``.

    A flag is written whole, and its value is the next word or follows an ``=``. A flag left
    out reads as its default. Refused with ``SettingsError``: a word that is no flag, an
    abbreviated flag, a flag with no value or given twice, and any value the settings file
    would refuse, which carries the same ``key`` and no ``line``."""
    if isinstance(words, str):
        raise TypeError("the words after init are a sequence of words, not one string")
    words = list(words)
    for word in words:
        if not isinstance(word, str):
            raise TypeError(f"a word is text, not {type(word).__name__}")
        if _has_surrogate(word):
            raise SettingsError("a flag or its value holds a character that is not text")
    document: dict[str, Any] = {"version": SCHEMA_VERSION}
    at = 0
    while at < len(words):
        flag, attached, value = words[at].partition("=")
        at += 1
        if flag not in INIT_FLAGS:
            whole = [name for name in INIT_FLAGS if name.startswith(flag)]
            if flag.startswith("--") and len(flag) > 2 and whole:
                raise SettingsError(f"{_shown(flag)} is not a flag of init: a flag is written "
                                    f"whole, as {_listed(whole)}")
            near = _nearest(flag, ((name, name) for name in INIT_FLAGS))
            nearest = "" if near is None else f"; the nearest is {near}"
            raise SettingsError(f"{_shown(flag)} is not a flag of init{nearest}")
        path = INIT_FLAGS[flag]
        if not attached:
            if at >= len(words) or words[at].startswith("--"):
                raise SettingsError(f"{flag} has no value: write the value after it, or "
                                    f"{flag}=VALUE where the value starts with --", key=path)
            value = words[at]
            at += 1
        if flag in (_TOOL_FLAG, _ENV_FLAG):
            try:
                name, held = _flag_line(value)
            except ValueError:
                example = ('lookup_order = "read"' if flag == _TOOL_FLAG
                           else 'inventory = ["full", "empty"]')
                raise SettingsError(f"{flag} takes one line as the settings file writes it, "
                                    f"such as {example}, not {_shown(value)}", key=path) from None
            table = (document.setdefault("tools", {}) if flag == _TOOL_FLAG
                     else document.setdefault("vary", {}).setdefault(_ENV, {}))
            if name in table:
                raise SettingsError(f"{flag} names {_shown(name)} twice",
                                    key=_dotted((*path.split("."), name)))
            table[name] = held
            continue
        key = _BY_FLAG[flag]
        table = document.setdefault(key.table, {})
        if key.name in table:
            raise SettingsError(f"{flag} is given twice", key=path)
        try:
            table[key.name] = _flag_value(key, value)
        except ValueError:
            raise SettingsError(f"{path} ({flag}) is {_shown(value)}, which is not a value it "
                                "can take", key=path) from None
    return _Check(document, _Words()).settings()


def _flag_text(key: _Key, value: object) -> str:
    """A key's value as its flag carries it: plainly where that is safe, as TOML where it is
    not."""
    if key.form == "text":
        assert isinstance(value, str)
        return value if _is_bare(value) else _quoted(value)
    if key.form == "words":
        assert isinstance(value, tuple)
        if value and _is_bare(value[0]) and all(word and word.isprintable() and "," not in word
                                                for word in value):
            return ",".join(value)
        return _array(_quoted(word) for word in value)
    return _value_text(key, value)


def _stated(settings: Settings) -> Iterator[tuple[str, str]]:
    """The flags that say what these settings say beyond the defaults, each with its value."""
    usual = _Check({"version": SCHEMA_VERSION,
                    "target": {"kind": settings.target.kind, "entry": settings.target.entry}},
                   _Words()).settings()
    for key in _KEYS:
        value = _value_of(settings, key)
        always = key.table == "target"
        if value is not None and (always or value != _value_of(usual, key)):
            yield key.flag, _flag_text(key, value)
        if key.path == "target.cases":
            for tool in settings.tools:
                yield _TOOL_FLAG, _line_text(tool.name, _tool_text(tool))
        if key.path == "vary.max_call":
            for setting in settings.vary.env:
                values = _array(_plain_value(value) for value in setting.values)
                yield _ENV_FLAG, _line_text(setting.name, values)


def equivalent_init_command(settings: Settings, *, prog: str) -> str:
    """One line a shell can run that writes these settings: ``prog``, then ``init``, then the
    flags. The target is always stated; any other flag is there only where the settings differ
    from the default, since a flag left out reads as it."""
    if not isinstance(settings, Settings):
        raise TypeError(f"the command is worked out from settings, not "
                        f"{type(settings).__name__}")
    words = [prog, "init"]
    for flag, value in _stated(settings):
        words += [flag, shlex.quote(value)]
    return " ".join(words)


# ---------------------------------------------------------------------------
# the plan shown before spending
# ---------------------------------------------------------------------------


def _counted(number: object, what: str, least: int) -> int:
    if not _is_whole(number):
        raise TypeError(f"{what} is a whole number, not {type(number).__name__}")
    assert isinstance(number, int)
    if number < least:
        raise ValueError(f"{what} is {number}, and a plan needs at least {least}")
    return number


def _of(settings: object) -> Settings:
    if not isinstance(settings, Settings):
        raise TypeError(f"a plan is worked out from settings, not {type(settings).__name__}")
    return settings


def plan_hunt(settings: Settings, *, cases: int) -> HuntPlan:
    """The run counts of a hunt on ``cases`` cases: the control stage runs every case
    ``control_repeats`` times, and search and shrink may use the rest of ``runs``.

    A control stage that leaves no room for one condition is refused with ``SettingsError`` on
    ``search.runs``, naming the smallest ``runs`` that fits: the control's runs plus
    ``cases_per_condition``."""
    search = _of(settings).search
    cases = _counted(cases, "the number of cases", 1)
    control = cases * search.control_repeats
    smallest = control + search.cases_per_condition
    if search.runs < smallest:
        raise SettingsError(
            f"search.runs is {search.runs}, and the control stage alone takes {control} "
            f"({cases} cases, {search.control_repeats} times each): set runs to {smallest} or "
            f"more, which leaves room for one condition on {search.cases_per_condition} cases, "
            "or lower control_repeats", key="search.runs")
    return HuntPlan(control_runs=control, search_runs=search.runs - control, runs=search.runs)


def plan_confirm(settings: Settings, *, cases: int, candidates: int | None = None
                 ) -> ConfirmPlan:
    """The run counts of confirming on ``cases`` cases: one arm with no change and one for each
    candidate, every case ``repeats`` times in each, and then as many runs again as one arm for
    each finding, for reference.

    ``candidates`` is the number a hunt found; left out, it is the most the settings let a hunt
    hand over. ``runs`` is the hunt's budget and does not cap this."""
    confirm = _of(settings).confirm
    cases = _counted(cases, "the number of cases", 1)
    found = (confirm.candidates if candidates is None
             else _counted(candidates, "the number of candidates", 1))
    arm = cases * confirm.repeats
    return ConfirmPlan(confirm_runs=(1 + found) * arm, reference_runs=found * arm,
                       reference_per_finding=arm, runs=(1 + 2 * found) * arm)

