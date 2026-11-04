"""The record every run Break stores carries: the shape, as data, and nothing else.

A stored run is a Prove run. Break writes one record under the key ``META_KEY``
(``poisson_break``) in the run's stored extra facts (Prove's ``meta``), in the shape published
as ``SCHEMA`` (``poisson_break.run/1``). The key, the schema string, every field name and the
closed sets of stages, failure kinds and signals are binding: a later field is additive and
keeps the number; a removal or a change of meaning is ``poisson_break.run/2``.

Every type here is a frozen dataclass with keyword-only fields. Construction refuses a field
the shape does not name, a value outside a closed set, a probability outside (0, 1], a count
that is not a whole number and a value of the wrong type, each with one plain sentence naming
the field (``RecordError``). ``to_dict`` gives plain JSON data in the published order,
``from_dict`` reads it back and refuses an unknown or a missing field, and ``to_json`` and
``from_json`` are the same through text. No type here computes anything.

The record in full::

    schema          "poisson_break.run/1"
    hunt            the hunt's name
    stage           control | search | shrink | confirm | reference | recheck
    arm             the arm's name, <hunt>-<arm>
    case            the case's id
    condition       name: the canonical condition name, "" for the control
                    changes: one Applied per change
    failure         kind: a failure kind, or None when the run is ok
                    signals: gave_up, retry_storm, over_budget, each a count
    selection       strategy: the strategy's name or import path
                    probability: the probability the strategy gave the condition, in (0, 1]
    calls           one Call per tool call, in order
    judged_by       "break" or "your check"
    target_outcome  for a bare Prove target, the target's own outcome; else None

An ``Applied`` is one change of a condition: its surface (``tool``, ``input``, ``user``,
``model`` or ``env``), the tool it names (``None`` for an input or a conversation change; for a
surroundings change, the setting's name), its fault, operator or move (for a surroundings
change, the value chosen), the call position as written in the condition name (``#2``, ``#2-4``,
``#*``, ``~0.3``, ``@3``; ``None`` where the change has no position), whether it applied, and
the call it landed on. A ``Call`` is one tool call: the tool, the call number from 1, the change
applied to it by name or ``None``, and whether the real tool ran.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from typing import Any, ClassVar, TypeVar

__all__ = [
    "META_KEY",
    "SCHEMA",
    "STAGES",
    "KINDS",
    "OWN_PREFIX",
    "SIGNALS",
    "SURFACES",
    "JUDGED_BY",
    "RecordError",
    "Applied",
    "Condition",
    "Signals",
    "Failure",
    "Selection",
    "Call",
    "RunRecord",
]

META_KEY = "poisson_break"
"""The key the record is stored under in a run's extra facts (Prove's ``meta``)."""

SCHEMA = "poisson_break.run/1"
"""The published shape's name; the first key of every record."""

STAGES = ("control", "search", "shrink", "confirm", "reference", "recheck")
"""The hunt stages, in the order they run; ``recheck`` is a later command's."""

KINDS = ("crashed", "hung", "ran_out", "forbidden_call", "followed_plant", "duplicate_write",
         "failed", "wrong")
"""The failure kinds Break itself decides, in the order the first one that applies is taken.
The user's own check adds ``own:<name>`` (``OWN_PREFIX``)."""

OWN_PREFIX = "own:"
"""A failure kind from the user's own check: the prefix and the check's name."""

SIGNALS = ("gave_up", "retry_storm", "over_budget")
"""The three signals, counted beside every run and not failures unless promoted."""

SURFACES = ("tool", "input", "user", "model", "env")
"""Where a change acts: tool behaviour, the inputs, the conversation, the model's own calls,
the surroundings a bare Prove target declares."""

JUDGED_BY = ("break", "your check")
"""Who decided the run's failure: Break's own checks, or the user's check."""


class RecordError(ValueError):
    """A record that is not in the published shape: one plain sentence naming the field."""


_T = TypeVar("_T", bound="_Record")


def _listed(words: tuple[str, ...]) -> str:
    if len(words) < 2:
        return "".join(words)
    return ", ".join(words[:-1]) + " or " + words[-1]


def _shown(value: object) -> str:
    """A value in the error sentence, without a Python repr of a list or a tuple."""
    if isinstance(value, str):
        return f'"{value}"'
    if value is None or isinstance(value, bool | int | float):
        return str(value)
    return type(value).__name__


def _whole(name: str, value: object, *, least: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < least:
        raise RecordError(f"{name} is {_shown(value)}, not a whole number of {least} or more")


def _text(name: str, value: object, *, none: bool = False) -> None:
    if value is None and none:
        return
    if not isinstance(value, str):
        what = "a string or None" if none else "a string"
        raise RecordError(f"{name} is {_shown(value)}, not {what}")


def _flag(name: str, value: object) -> None:
    if not isinstance(value, bool):
        raise RecordError(f"{name} is {_shown(value)}, not true or false")


def _one_of(name: str, value: object, allowed: tuple[str, ...]) -> None:
    if not isinstance(value, str) or value not in allowed:
        raise RecordError(f"{name} is {_shown(value)}, not one of {_listed(allowed)}")


class _Record:
    """What every record type shares: the dict and JSON forms, in the published order, and a
    reader that refuses an unknown or a missing field."""

    _nested: ClassVar[dict[str, type[_Record]]] = {}
    _sequences: ClassVar[dict[str, type[_Record]]] = {}

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in fields(self):  # type: ignore[arg-type]
            value = getattr(self, f.name)
            if isinstance(value, _Record):
                out[f.name] = value.to_dict()
            elif isinstance(value, tuple):
                out[f.name] = [item.to_dict() if isinstance(item, _Record) else item
                               for item in value]
            else:
                out[f.name] = value
        return out

    @classmethod
    def from_dict(cls: type[_T], data: Mapping[str, Any]) -> _T:
        if not isinstance(data, Mapping):
            raise RecordError(f"a {cls.__name__} is read from a mapping, not {_shown(data)}")
        names = [f.name for f in fields(cls)]  # type: ignore[arg-type]
        unknown = sorted(set(data) - set(names))
        if unknown:
            raise RecordError(f"{cls.__name__} has no field named {_listed(tuple(unknown))}")
        missing = [name for name in names if name not in data and name != "schema"]
        if missing:
            raise RecordError(f"{cls.__name__} is missing {_listed(tuple(missing))}")
        values: dict[str, Any] = {}
        for name in names:
            if name not in data:
                continue
            value = data[name]
            if name in cls._nested:
                value = cls._nested[name].from_dict(value)
            elif name in cls._sequences:
                if not isinstance(value, list | tuple):
                    raise RecordError(f"{name} is {_shown(value)}, not a list")
                value = tuple(cls._sequences[name].from_dict(item) for item in value)
            values[name] = value
        return cls(**values)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, allow_nan=False)

    @classmethod
    def from_json(cls: type[_T], text: str) -> _T:
        try:
            data = json.loads(text, parse_constant=_no_constant)
        except ValueError as wrong:
            raise RecordError(f"not a JSON document: {wrong}") from None
        return cls.from_dict(data)


def _no_constant(name: str) -> Any:
    raise ValueError(f"{name} is not allowed in a record")


@dataclass(frozen=True, kw_only=True)
class Applied(_Record):
    """One change of a condition, with whether and where it applied in this run."""

    surface: str
    tool: str | None
    fault: str
    call: str | None
    applied: bool
    applied_call: int | None

    def __post_init__(self) -> None:
        _one_of("surface", self.surface, SURFACES)
        _text("tool", self.tool, none=True)
        _text("fault", self.fault)
        _text("call", self.call, none=True)
        _flag("applied", self.applied)
        if self.applied_call is not None:
            _whole("applied_call", self.applied_call, least=1)


@dataclass(frozen=True, kw_only=True)
class Condition(_Record):
    """The condition the run ran under: its canonical name, the empty string for the control,
    and its changes, none for the control."""

    _sequences: ClassVar[dict[str, type[_Record]]] = {"changes": Applied}

    name: str
    changes: tuple[Applied, ...]

    def __post_init__(self) -> None:
        _text("name", self.name)
        if not isinstance(self.changes, tuple) or not all(
                isinstance(c, Applied) for c in self.changes):
            raise RecordError("changes is not a tuple of Applied")
        if (self.name == "") != (len(self.changes) == 0):
            raise RecordError('name is "" exactly when changes is empty: the control has no change')


@dataclass(frozen=True, kw_only=True)
class Signals(_Record):
    """The three signals, each a count."""

    gave_up: int
    retry_storm: int
    over_budget: int

    def __post_init__(self) -> None:
        for name in SIGNALS:
            _whole(name, getattr(self, name), least=0)


@dataclass(frozen=True, kw_only=True)
class Failure(_Record):
    """How the run failed, or ``None`` when it did not, and the signals counted beside it."""

    _nested: ClassVar[dict[str, type[_Record]]] = {"signals": Signals}

    kind: str | None
    signals: Signals

    def __post_init__(self) -> None:
        kind = self.kind
        if kind is not None:
            own = (isinstance(kind, str) and kind.startswith(OWN_PREFIX)
                   and len(kind) > len(OWN_PREFIX))
            if not own and (not isinstance(kind, str) or kind not in KINDS):
                raise RecordError(
                    f"kind is {_shown(kind)}, not one of {_listed(KINDS)}, "
                    f"{OWN_PREFIX}<name> or None")
        if not isinstance(self.signals, Signals):
            raise RecordError(f"signals is {_shown(self.signals)}, not Signals")


@dataclass(frozen=True, kw_only=True)
class Selection(_Record):
    """Which strategy proposed the condition and the probability it gave it, in (0, 1];
    1 for the control."""

    strategy: str
    probability: float

    def __post_init__(self) -> None:
        _text("strategy", self.strategy)
        p = self.probability
        if (isinstance(p, bool) or not isinstance(p, int | float) or not math.isfinite(p)
                or not 0 < p <= 1):
            raise RecordError(f"probability is {_shown(p)}, not a number above 0 and at most 1")


@dataclass(frozen=True, kw_only=True)
class Call(_Record):
    """One tool call: the tool, its call number from 1, the change applied to it by name or
    ``None``, and whether the real tool ran."""

    tool: str
    call: int
    change: str | None
    real_ran: bool

    def __post_init__(self) -> None:
        _text("tool", self.tool)
        _whole("call", self.call, least=1)
        _text("change", self.change, none=True)
        _flag("real_ran", self.real_ran)


@dataclass(frozen=True, kw_only=True)
class RunRecord(_Record):
    """The record of one stored run, in the published shape, ``schema`` first."""

    _nested: ClassVar[dict[str, type[_Record]]] = {
        "condition": Condition, "failure": Failure, "selection": Selection}
    _sequences: ClassVar[dict[str, type[_Record]]] = {"calls": Call}

    schema: str = field(default=SCHEMA)
    hunt: str
    stage: str
    arm: str
    case: str
    condition: Condition
    failure: Failure
    selection: Selection
    calls: tuple[Call, ...]
    judged_by: str
    target_outcome: str | None

    def __post_init__(self) -> None:
        if self.schema != SCHEMA:
            raise RecordError(f"schema is {_shown(self.schema)}, not {_shown(SCHEMA)}")
        _text("hunt", self.hunt)
        _one_of("stage", self.stage, STAGES)
        _text("arm", self.arm)
        _text("case", self.case)
        if not isinstance(self.condition, Condition):
            raise RecordError(f"condition is {_shown(self.condition)}, not Condition")
        if not isinstance(self.failure, Failure):
            raise RecordError(f"failure is {_shown(self.failure)}, not Failure")
        if not isinstance(self.selection, Selection):
            raise RecordError(f"selection is {_shown(self.selection)}, not Selection")
        if not isinstance(self.calls, tuple) or not all(isinstance(c, Call) for c in self.calls):
            raise RecordError("calls is not a tuple of Call")
        _one_of("judged_by", self.judged_by, JUDGED_BY)
        _text("target_outcome", self.target_outcome, none=True)
