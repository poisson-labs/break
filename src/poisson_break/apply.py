"""Applying a condition to one run: what each tool call of the agent comes back as, and the
record of what was done.

A ``Session`` is one run's applier. It holds the run's condition, its seed, the planted marker
word, each tool's class, a count of the calls made to each tool and the record of what was
applied. A way in routes every tool call of the agent through ``session.call(tool, args, real)``,
where ``args`` is the mapping of the call's arguments and ``real`` runs the real tool once and
takes no arguments. ``call`` returns what the agent should see, or raises ``ToolFailure`` for an
error the agent should see, which a way in catches to present in its own form. Under the control
the agent gets the tool's own object and the tool's own exception, once per call, with no wait.

**Which change lands.** A call is numbered among the calls of its own tool, from 1, whether or
not the tool then runs. The first change in the condition's order that applies to that call
lands on it; the condition's order is the plain text order of the changes' names, so it is the
same in every process. Any other change that would have applied to the same call does nothing
to it and is not run.

**The record.** ``session.calls`` is a tuple of ``Call``, one per tool call in the order the
agent made them: the tool, the call number, the change that landed by its whole name or
``None``, and whether the real tool ran. ``session.applied`` is a tuple of ``Applied``, one per
change in the condition's order: whether it applied, and the first call it landed on. Nothing in
either is content: no argument, no result, no marker.

**What the run saw.** ``session.seen`` is a tuple of ``Seen``, one per tool call the record
holds, in the same order and apart from the two records: the tool, the call number, the call's
arguments as they were when it was made, and what the agent was handed back, a result or a
failure. Each is a copy, or the object itself when it cannot be copied. It is what deciding
whether a run failed reads, and what a user's own check is shown, and it never reaches a stored
record. ``session.tools`` is each tool's line as the session was given it.

**What a fault is given.** The frozen call context of ``poisson_break.changes``: the tool, its
arguments, the call number, the condition, the seed, the marker, and ``previous``, the result the
real tool or its stand-in last handed back on an earlier call of the same tool. A call on which
it did not run, or raised, leaves ``previous`` as it was. It is held as a copy taken when the
tool returned, or as the object itself when it cannot be copied, while the agent gets the tool's
own object. A fault's generator is seeded from the run's seed, the tool, the call number and the
change's name, and its parameters are the ones its catalogue line declares.

**Tool classes.** ``tools`` gives each tool's line as the settings file writes it: ``"read"``,
``"off"``, ``{"class": "write", "repeatable": True}`` or ``{"class": "write", "stand_in":
"my_app.fakes:refund"}``. A ``write`` tool whose line does not say how it is made safe, a line
that is no class, a stand-in that cannot be loaded, ``lost_reply`` on a tool that is not safe to
repeat and a change that names an ``off`` tool or a tool with no line are each refused when the
session is made, with ``ToolRefused``. A call of a tool with no line is refused on the call,
before the tool runs. An ``off`` tool is never touched: its calls pass straight through, with no
count and no record. A stand-in replaces its tool in every run, the control included; it is
called ``stand_in(**args)``, it is what a fault's ``real`` runs, and its run reads as the tool's.

**When a run stops.** Break's own failure, a fault's or a stand-in's is an ``InstrumentError``,
never a tool failure the agent sees. An agent's own ``except Exception`` would catch it, so the
session holds the first instrument error, refusal or running out of time in ``session.stopped``
and raises that same object on every later call, running nothing. The real tool's own exception
is neither: it passes to the agent untouched, with no fault's work done on top, and the call is
recorded with the change that was on it.

**Time.** A fault states a delay in its result and the session does the sleeping, for that long
and no longer. ``run_seconds`` is the run's wall-clock limit, counted from when the session is
made. Past it, during a sleep or on the next call, the session raises ``RunOutOfTime``, which is
not an ``Exception``, so an agent that catches every exception does not catch it.

**The case.** ``session.case(case)`` returns the case as the run should see it, with the
condition's input operators applied and, for a way in that drives a conversation, its moves, each
in the condition's order on what the last left, and each recorded as applied when it changed
something. The case it is handed is left as it was.

**A target's own tools.** ``wrap(tool_name, fn)`` is the one call a Prove target adds per tool,
and ``with session:`` opens the run around the agent. A wrapped tool with no run open is the tool
itself. It keeps the tool's name and signature, calls the tool as the agent called it and names
positional arguments for ``args``. A call from a thread the agent started reaches the one open
run; when it cannot be told which of two open runs a call belongs to, that is an instrument
error naming the tool. A tool that is ``async def`` is refused.

``ToolInfo`` and ``RunResult`` are the two frozen objects a way in hands the core: a tool by
name, and how one run ended.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import importlib
import inspect
import math
import random
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType, TracebackType
from typing import Any, TypeVar, cast

from poisson_break import changes as _catalogue
from poisson_break.changes import (
    CATALOG,
    CallContext,
    Change,
    Condition,
    InstrumentError,
    NeedsAdapter,
    Result,
    ToolError,
    applies,
    check_capabilities,
    parse,
    run_fault,
)
from poisson_break.changes import name as _name_of
from poisson_break.interfaces import Capabilities, Fault
from poisson_break.records import Applied, Call

__all__ = [
    "Session",
    "wrap",
    "ToolFailure",
    "ToolRefused",
    "RunOutOfTime",
    "ToolInfo",
    "RunResult",
    "Seen",
    "Applied",
    "InstrumentError",
]

ENDED = ("returned", "raised", "limit")
"""How a run ended, as a way in reports it: the agent returned, an exception escaped it, or it
hit its own step or turn limit."""

_T = TypeVar("_T")

# The fault that reports an error after the tool has already acted: a retry repeats the action,
# so it is taken only on a tool that is safe to repeat.
_REPEATS_AN_ACTION = "lost_reply"

_OPERATORS: Mapping[str, Callable[..., str]] = {
    "typos": _catalogue.typos,
    "reordered": _catalogue.reordered,
    "padded": _catalogue.padded,
    "cut_short": _catalogue.cut_short,
    "variant": _catalogue.variant,
}

_MOVES: Mapping[str, Callable[..., list[str]]] = {
    "repeats": _catalogue.repeats,
    "interrupts": _catalogue.interrupts,
    "goes_quiet": _catalogue.goes_quiet,
    "presses": _catalogue.presses,
}


# ---------------------------------------------------------------------------
# what a call can end in, other than a result
# ---------------------------------------------------------------------------


class ToolFailure(Exception):
    """An error the agent should see, raised where the tool's own failure would be. ``kind`` is
    the fault's word for it (``error``, ``timeout`` or ``rate_limited`` at launch) and
    ``message`` its one line, which is also the exception's text. A ``kind`` of ``timeout`` is a
    ``TimeoutError`` too, so an agent's own ``except TimeoutError`` takes the path a real timeout
    takes."""

    kind: str
    message: str

    def __new__(cls, kind: str, message: str) -> ToolFailure:
        if cls is ToolFailure and kind == "timeout":
            cls = ToolTimeout
        return super().__new__(cls, message)

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message

    def __str__(self) -> str:
        return self.message

    def __reduce__(self) -> tuple[Any, ...]:
        return (type(self), (self.kind, self.message))


class ToolTimeout(ToolFailure, TimeoutError):
    """A ``ToolFailure`` whose kind is ``timeout``."""


class ToolRefused(ValueError):
    """A tool Break may not run this way: one plain sentence. ``tool`` names the tool, and
    ``change`` the change that is the trouble, by its whole name, or ``None`` when the trouble is
    the tool's own line."""

    def __init__(self, message: str, *, tool: str, change: str | None = None) -> None:
        super().__init__(message)
        self.tool = tool
        self.change = change

    def __reduce__(self) -> tuple[Any, ...]:
        return (_refused, (str(self), self.tool, self.change))


def _refused(message: str, tool: str, change: str | None) -> ToolRefused:
    return ToolRefused(message, tool=tool, change=change)


class RunOutOfTime(BaseException):
    """The run passed its wall-clock limit. Not an ``Exception``, so an agent that catches every
    exception does not catch it."""


# ---------------------------------------------------------------------------
# the two frozen objects a way in hands the core
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ToolInfo:
    """One of the agent's tools, by name, as a way in lists it before any run."""

    name: str


@dataclass(frozen=True, kw_only=True)
class RunResult:
    """How one run ended, as a way in reports it: the agent's reply, the outcome the target
    itself reports or ``None``, tokens in and out where the way in can see them, and ``ended``:
    ``returned``, ``raised``, or ``limit`` for the agent's own step or turn limit. A way in
    decides nothing, so no other word is taken."""

    reply: Any
    outcome: str | None
    tokens_in: int | None
    tokens_out: int | None
    ended: str

    def __post_init__(self) -> None:
        if not isinstance(self.ended, str) or self.ended not in ENDED:
            raise ValueError(f"ended is {_shown(self.ended)}, not one of returned, raised or "
                             "limit")


# ---------------------------------------------------------------------------
# the content of one call, kept apart from the records
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Seen:
    """One tool call's content, as the run holds it: the tool, its call number, the arguments as
    they were when the call was made, and what the agent was handed back. ``saw`` is the result,
    and ``error`` is ``None``; or ``error`` is the failure, a kind and one line, and ``saw`` is
    ``None``. The kind is the fault's word for a failure Break made (``error``, ``timeout`` or
    ``rate_limited`` at launch) and the exception's type name for anything else the call raised:
    the tool's own exception, or what stopped the run on that call. The arguments and the result
    are copies taken at the call, or the objects themselves when they cannot be copied."""

    tool: str
    call: int
    args: Mapping[str, Any]
    saw: Any
    error: ToolError | None


# ---------------------------------------------------------------------------
# tool classes
# ---------------------------------------------------------------------------

_LINE_KEYS = ("class", "repeatable", "stand_in")


@dataclass(frozen=True)
class _ToolClass:
    """One tool's line, read: its class, whether a repeat of its action is safe, and the stand-in
    that is called in its place."""

    kind: str
    safe_to_repeat: bool
    stand_in: Callable[..., Any] | None


def _shown(value: object) -> str:
    if isinstance(value, str):
        return f'"{value}"'
    if value is None or isinstance(value, bool | int | float):
        return str(value)
    return type(value).__name__


def _one_line(wrong: BaseException) -> str:
    text = " ".join(str(wrong).split())
    return f"{type(wrong).__name__}: {text}" if text else type(wrong).__name__


def _is_async(fn: Callable[..., Any]) -> bool:
    """Whether calling ``fn`` hands back something to await rather than a result: an ``async
    def``, or an object whose own ``__call__`` is one."""
    return (inspect.iscoroutinefunction(fn) or inspect.isasyncgenfunction(fn)
            or inspect.iscoroutinefunction(type(fn).__call__))


def _stand_in(tool: str, path: object) -> Callable[..., Any]:
    """The stand-in a line names by its import path, ``module:name``."""
    if not isinstance(path, str) or not path:
        raise ToolRefused(f'the stand-in for "{tool}" is {_shown(path)}, not an import path '
                          "written module:name", tool=tool)
    module_name, colon, attribute = path.partition(":")
    if not colon or not module_name or not attribute:
        raise ToolRefused(f'the stand-in for "{tool}" is "{path}", not an import path written '
                          "module:name", tool=tool)
    try:
        found: Any = importlib.import_module(module_name)
        for part in attribute.split("."):
            found = getattr(found, part)
    except Exception as wrong:
        raise ToolRefused(f'the stand-in for "{tool}", "{path}", could not be loaded '
                          f"({_one_line(wrong)})", tool=tool) from wrong
    if not callable(found):
        raise ToolRefused(f'the stand-in for "{tool}", "{path}", is {_shown(found)}, not '
                          "something that can be called", tool=tool)
    if _is_async(found):
        raise ToolRefused(f'the stand-in for "{tool}", "{path}", is async, and Break calls a '
                          "tool and reads what it returns", tool=tool)
    return cast(Callable[..., Any], found)


def _classed(tool: str, line: object) -> _ToolClass:
    """One tool's line as the settings file writes it, read or refused."""
    if isinstance(line, str):
        fields: Mapping[Any, Any] = {"class": line}
    elif isinstance(line, Mapping):
        fields = line
    else:
        raise ToolRefused(f'"{tool}" is classed {_shown(line)}, not read, write or off',
                          tool=tool)
    extra = [key for key in fields if key not in _LINE_KEYS]
    if extra:
        raise ToolRefused(f'the line for "{tool}" has {_shown(extra[0])}, and a tool\'s line '
                          "holds class, repeatable and stand_in", tool=tool)
    kind = fields.get("class")
    if kind not in ("read", "write", "off"):
        raise ToolRefused(f'"{tool}" is classed {_shown(kind)}, not read, write or off',
                          tool=tool)
    repeatable = fields.get("repeatable", False)
    if not isinstance(repeatable, bool):
        raise ToolRefused(f'repeatable is true or false, and the line for "{tool}" gives '
                          f"{_shown(repeatable)}", tool=tool)
    named = "stand_in" in fields
    if kind == "off":
        if named:
            raise ToolRefused(f'"{tool}" is off, so Break never touches it, and its line names '
                              "a stand-in to call in its place", tool=tool)
        return _ToolClass("off", False, None)
    stand_in = _stand_in(tool, fields["stand_in"]) if named else None
    if kind == "read":
        return _ToolClass("read", False, stand_in)
    if not repeatable and stand_in is None:
        raise ToolRefused(f'"{tool}" is a write tool, and its line does not say how it is made '
                          "safe: repeatable = true, or a stand_in to call in its place",
                          tool=tool)
    return _ToolClass("write", True, stand_in)


# ---------------------------------------------------------------------------
# the condition, checked
# ---------------------------------------------------------------------------


def _checked(condition: object) -> tuple[str, ...]:
    """The whole name of each change of a condition the catalogue could have written, in the
    condition's order. Anything else is Break's own mistake: ``parse`` cannot make it."""
    if not isinstance(condition, Condition) or not isinstance(condition.changes, tuple):
        raise InstrumentError(f"a run is given a condition, not {_shown(condition)}")
    names: list[str] = []
    for change in condition.changes:
        try:
            if not isinstance(change, Change):
                raise TypeError(f"{_shown(change)} is not a change")
            text = _name_of(change)
            if change.surface == "env":
                written = (isinstance(change.tool, str) and isinstance(change.fault, str)
                           and change.call is None)
            else:
                written = parse(text).changes == (change,)
        except Exception as wrong:
            raise InstrumentError("the condition holds a change the catalogue could not have "
                                  f"written ({_one_line(wrong)})") from wrong
        if not written:
            raise InstrumentError("the condition holds a change the catalogue could not have "
                                  f'written, "{text}"')
        names.append(text)
    if names != sorted(set(names)):
        raise InstrumentError("the condition's changes are not sorted with each one once, as "
                              "every condition read from a name is")
    return tuple(names)


def _generator(seed: int, tool: str, call: int, change: str) -> random.Random:
    """A fault's own generator for one call, from the run's seed, the tool, the call number and
    the change's name, by a hash that is the same in every process."""
    text = "\x1f".join(("fault", str(seed), tool, str(call), change))
    return random.Random(int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big"))


def _copied(value: Any) -> Any:
    """A copy of a result, or the result itself when it cannot be copied."""
    try:
        return copy.deepcopy(value)
    except Exception:
        return value


def _arguments(args: Mapping[str, Any]) -> Mapping[str, Any]:
    """A call's arguments as they are now, held read-only: each value a copy, or the value itself
    when it cannot be copied. A target may fill one mapping in again for its next call. A mapping
    that cannot be read through is held as it is."""
    try:
        return MappingProxyType({key: _copied(value) for key, value in args.items()})
    except Exception:
        return args


def _failure_seen(wrong: BaseException) -> ToolError:
    """What a call raised, as the content of that call keeps it: a tool failure's own kind and
    line, and for anything else the exception's type name and its text on one line."""
    if isinstance(wrong, ToolFailure):
        return ToolError(kind=wrong.kind, message=wrong.message)
    return ToolError(kind=type(wrong).__name__, message=" ".join(str(wrong).split()))


def _request(case: Mapping[str, Any]) -> str:
    """The request as the input operators read it."""
    value = case.get("input", "")
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _script(case: Mapping[str, Any]) -> list[str]:
    """The scripted conversation as the moves read it."""
    turns = case.get("turns")
    if not isinstance(turns, list | tuple):
        return []
    return [turn if isinstance(turn, str) else str(turn) for turn in turns]


# ---------------------------------------------------------------------------
# the real tool, run for one call
# ---------------------------------------------------------------------------


class _Real:
    """The real tool, or the stand-in called in its place, for one call. It counts its runs,
    remembers the tool's own exception so that it can be told from Break's, and hands what the
    tool returned to the session to hold as the tool's previous result."""

    def __init__(self, session: Session, tool: str, args: Mapping[str, Any],
                 real: Callable[[], Any], stand_in: Callable[..., Any] | None) -> None:
        self._session = session
        self._tool = tool
        self._args = args
        self._real = real
        self._stand_in = stand_in
        self.runs = 0
        self.own: BaseException | None = None

    def __call__(self) -> Any:
        self.runs += 1
        if self._stand_in is not None:
            try:
                value = self._stand_in(**self._args)
            except Exception as wrong:
                raise InstrumentError(f'the stand-in for "{self._tool}" raised '
                                      f"{_one_line(wrong)}") from wrong
        else:
            try:
                value = self._real()
            except Exception as wrong:
                self.own = wrong
                raise
        if inspect.isawaitable(value):
            raise InstrumentError(f'"{self._tool}" handed back something to await, not a '
                                  "result: Break calls a tool and reads what it returns")
        self._session._hold(self._tool, value)
        return value


# ---------------------------------------------------------------------------
# the runs that are open, for a target's own wrapped tools
# ---------------------------------------------------------------------------

_OPEN_LOCK = threading.Lock()
_OPEN: list[Session] = []
_HERE = threading.local()


def _opened_here() -> list[Session]:
    """The runs this thread opened and has not closed, the innermost last."""
    runs: list[Session] | None = getattr(_HERE, "runs", None)
    if runs is None:
        runs = []
        _HERE.runs = runs
    return runs


def _current(tool: str) -> Session | None:
    """The run a wrapped tool's call belongs to, or ``None`` with no run open. The run this
    thread opened, the innermost if it opened more than one; from a thread that opened none,
    the one run open. With more than one open it cannot be told, and the call is refused before
    the tool runs: a call that missed its run would run with no change and no record."""
    here = _opened_here()
    if here:
        return here[-1]
    with _OPEN_LOCK:
        candidates = list({id(run): run for run in _OPEN}.values())
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    wrong = InstrumentError(
        f'a call of "{tool}" came from a thread that opened no run while {len(candidates)} runs '
        "were open, so it cannot be told which run the call belongs to")
    for run in candidates:
        run._stop(wrong)
    raise wrong


# ---------------------------------------------------------------------------
# one run's applier
# ---------------------------------------------------------------------------


class Session:
    """One run's applier: the condition, the seed, the marker, each tool's class, the per-tool
    call counts, the record of what was applied and, apart from it, the content of each call.

    ``capabilities`` says what the way in can do; with none given it is a plain Prove target's,
    which routes tool calls and nothing more, and a condition that asks for more is refused with
    ``NeedsAdapter`` when the session is made. ``run_seconds`` is the run's wall-clock limit,
    counted from now; with none given there is no limit."""

    def __init__(self, condition: Condition, *, seed: int, tools: Mapping[str, object],
                 marker: str | None = None, capabilities: Capabilities | None = None,
                 run_seconds: float | None = None) -> None:
        self._started = time.monotonic()
        names = _checked(condition)
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise InstrumentError(f"a run's seed is a whole number, not {_shown(seed)}")
        if marker is not None and (not isinstance(marker, str) or not marker):
            raise InstrumentError(f"a run's marker is a word or None, not {_shown(marker)}")
        if run_seconds is not None and (
                isinstance(run_seconds, bool) or not isinstance(run_seconds, int | float)
                or not math.isfinite(run_seconds) or run_seconds <= 0):
            raise InstrumentError("a run's limit is a number of seconds above 0 or None, not "
                                  f"{_shown(run_seconds)}")
        if not isinstance(tools, Mapping) or not all(isinstance(tool, str) for tool in tools):
            raise InstrumentError("a run is given each tool's line by the tool's name, not "
                                  f"{_shown(tools)}")
        if capabilities is None:
            capabilities = Capabilities(tool_calls=True, model_calls=False, conversation=False)

        self._condition = condition
        self._names = names
        self._seed = seed
        self._marker = marker
        self._capabilities = capabilities
        self._run_seconds = run_seconds
        self._deadline = None if run_seconds is None else self._started + run_seconds
        self._tools = {tool: _classed(tool, line) for tool, line in tools.items()}
        self._lines: Mapping[str, object] = MappingProxyType(
            {tool: _copied(line) for tool, line in tools.items()})

        try:
            check_capabilities(condition, capabilities)
        except NeedsAdapter:
            raise
        except Exception as wrong:
            raise InstrumentError("a run is given what its way in can do, not "
                                  f"{_shown(capabilities)}") from wrong

        lines = {line.name: line for line in CATALOG if line.surface == "tool"}
        faults: dict[int, tuple[Fault, Mapping[str, object]]] = {}
        for index, change in enumerate(condition.changes):
            if change.surface != "tool" or change.tool is None:
                continue
            tool, text = change.tool, names[index]
            classed = self._tools.get(tool)
            if classed is None:
                raise ToolRefused(f'"{text}" names "{tool}", which the settings do not class '
                                  "as read, write or off", tool=tool, change=text)
            if classed.kind == "off":
                raise ToolRefused(f'"{text}" names "{tool}", which is off: Break never touches '
                                  "it, so the change could do nothing", tool=tool, change=text)
            if change.fault == _REPEATS_AN_ACTION and not classed.safe_to_repeat:
                raise ToolRefused(f'"{text}" reports an error after the tool has acted, so a '
                                  f'retry repeats the action, and "{tool}" is not a write tool '
                                  "marked repeatable or given a stand-in", tool=tool, change=text)
            line = lines.get(change.fault)
            if line is None or line.fault is None:
                raise InstrumentError(f'"{text}" names a fault the catalogue holds nothing to '
                                      "apply for")
            faults[index] = (line.fault, line.parameters)
        self._faults = faults
        self._faulted = frozenset(condition.changes[index].tool for index in faults)

        self._lock = threading.Lock()
        self._counts: dict[str, int] = {}
        self._calls: list[Call | None] = []
        self._seen: list[Seen | None] = []
        self._landed: list[int | None] = [None] * len(names)
        self._acted: list[bool] = [False] * len(names)
        self._previous: dict[str, Any] = {}
        self._stopped: BaseException | None = None

    def __repr__(self) -> str:
        return f'<Session "{_name_of(self._condition)}" seed={self._seed}>'

    # --- what the run holds ----------------------------------------------------------------

    @property
    def condition(self) -> Condition:
        """The run's condition; the control has no change."""
        return self._condition

    @property
    def seed(self) -> int:
        """The run's seed."""
        return self._seed

    @property
    def marker(self) -> str | None:
        """The word ``planted_instruction`` plants in this run, or ``None``."""
        return self._marker

    @property
    def capabilities(self) -> Capabilities:
        """What the run's way in can do."""
        return self._capabilities

    @property
    def run_seconds(self) -> float | None:
        """The run's wall-clock limit in seconds, counted from when the session was made."""
        return self._run_seconds

    @property
    def tools(self) -> Mapping[str, object]:
        """Each tool's line as the run was given it, by the tool's name, read-only."""
        return self._lines

    @property
    def calls(self) -> tuple[Call, ...]:
        """One ``Call`` per tool call so far, in the order the agent made them. A call still
        inside its tool is not in it yet."""
        with self._lock:
            return tuple(call for call in self._calls if call is not None)

    @property
    def seen(self) -> tuple[Seen, ...]:
        """One ``Seen`` per tool call so far, in the order the agent made them: the call's
        arguments and what the agent was handed back, apart from the two records. A call whose
        answer the agent has not yet been handed is not in it yet."""
        with self._lock:
            return tuple(one for one in self._seen if one is not None)

    @property
    def applied(self) -> tuple[Applied, ...]:
        """One ``Applied`` per change, in the condition's order: whether it has applied so far,
        and for a change on a tool the first call it landed on."""
        with self._lock:
            landed, acted = list(self._landed), list(self._acted)
        return tuple(
            Applied(surface=change.surface, tool=change.tool, fault=change.fault,
                    call=change.call, applied=acted[index] or landed[index] is not None,
                    applied_call=landed[index])
            for index, change in enumerate(self._condition.changes))

    @property
    def stopped(self) -> BaseException | None:
        """The first instrument error, refusal or running out of time of this run, or ``None``.
        Once it is set every later call raises that same object and runs nothing, so a run that
        stopped is not one to count, whatever the agent went on to do."""
        with self._lock:
            return self._stopped

    def _stop(self, wrong: BaseException) -> BaseException:
        """Hold ``wrong`` as what stopped the run, unless something already did; what is held."""
        with self._lock:
            if self._stopped is None:
                self._stopped = wrong
            return self._stopped

    # --- one tool call ---------------------------------------------------------------------

    def call(self, tool: str, args: Mapping[str, Any], real: Callable[[], Any]) -> Any:
        """One tool call of the agent: ``tool`` by name, ``args`` the mapping of its arguments,
        and ``real``, which runs the real tool once and takes no arguments. Returns what the
        agent should see, or raises ``ToolFailure`` for an error it should see. The real tool's
        own exception passes untouched."""
        classed = self._tools.get(tool) if isinstance(tool, str) else None
        if classed is not None and classed.kind == "off":
            return real()

        stopped = self.stopped
        if stopped is not None:
            raise stopped
        if not isinstance(tool, str):
            raise self._stop(InstrumentError(
                f"a tool is called by its name, not by {_shown(tool)}"))
        if not isinstance(args, Mapping):
            raise self._stop(InstrumentError(
                f'the arguments of a call of "{tool}" are {_shown(args)}, not a mapping of '
                "their names to their values"))
        if not callable(real):
            raise self._stop(InstrumentError(
                f'a call of "{tool}" came with {_shown(real)} to run the real tool, not '
                "something that can be called"))
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise self._stop(self._out_of_time())
        if classed is None:
            raise self._stop(ToolRefused(
                f'the agent called "{tool}", which the settings do not class as read, write or '
                "off", tool=tool))

        # The arguments are copied before the call takes its number, so that whatever happens
        # from here on leaves both the call's record and its content.
        given = _arguments(args)
        with self._lock:
            if self._stopped is not None:
                raise self._stopped
            number = self._counts.get(tool, 0) + 1
            self._counts[tool] = number
            slot = len(self._calls)
            self._calls.append(None)
            self._seen.append(None)

        saw: Any = None
        failure: ToolError | None = None
        try:
            index = self._landing(tool, number)
            runner = _Real(self, tool, args, real, classed.stand_in)
            try:
                outcome = self._outcome(index, runner, tool, args, number)
            finally:
                self._record(slot, index, tool, number, runner.runs > 0)

            if isinstance(outcome, ToolError):
                raise ToolFailure(outcome.kind, outcome.message)
            self._wait(outcome.delay)
            saw = _copied(outcome.value)
            return outcome.value
        except BaseException as wrong:
            failure = _failure_seen(wrong)
            raise
        finally:
            self._keep(slot, Seen(tool=tool, call=number, args=given, saw=saw, error=failure))

    def _landing(self, tool: str, number: int) -> int | None:
        """Which change lands on this call: the first in the condition's order that applies to
        it, by its place in the condition, or ``None``."""
        if tool not in self._faulted:
            return None
        for index in self._faults:
            if applies(self._condition.changes[index], seed=self._seed, tool=tool, call=number):
                return index
        return None

    def _outcome(self, index: int | None, runner: _Real, tool: str, args: Mapping[str, Any],
                 number: int) -> Result | ToolError:
        """What this call comes to: the tool's own result under no change, or the landing
        fault's outcome. Break's failure, a fault's or a stand-in's stops the run; the real
        tool's own exception passes as it is."""
        try:
            if index is None:
                return Result(value=runner())
            fault, parameters = self._faults[index]
            text = self._names[index]
            try:
                context = CallContext(
                    tool=tool, args=args, call=number, condition=self._condition,
                    seed=self._seed, previous=self._held(tool), marker=self._marker)
                generator = _generator(self._seed, tool, number, text)
            except Exception as wrong:
                raise InstrumentError(f'the call of "{tool}" could not be handed to "{text}" '
                                      f"({_one_line(wrong)})") from wrong
            return run_fault(fault, context, real=runner, params=parameters, rng=generator)
        except InstrumentError as wrong:
            if wrong is runner.own:
                raise
            broke = wrong
        raise self._stop(broke)

    def _record(self, slot: int, index: int | None, tool: str, number: int,
                real_ran: bool) -> None:
        """Write the call down, and that its change landed on it."""
        change = None if index is None else self._names[index]
        record = Call(tool=tool, call=number, change=change, real_ran=real_ran)
        with self._lock:
            self._calls[slot] = record
            if index is not None:
                first = self._landed[index]
                self._landed[index] = number if first is None else min(first, number)

    def _keep(self, slot: int, one: Seen) -> None:
        """Keep the call's content, in the call's own place."""
        with self._lock:
            self._seen[slot] = one

    def _hold(self, tool: str, value: Any) -> None:
        """Keep what the tool just returned as its previous result, as a copy. Only a fault on
        the same tool ever reads it, so nothing is kept for a tool the condition leaves alone."""
        if tool in self._faulted:
            held = _copied(value)
            with self._lock:
                self._previous[tool] = held

    def _held(self, tool: str) -> Any:
        """The tool's previous result for a fault to read: a copy of the one held, so that
        nothing done to it reaches the next call's."""
        with self._lock:
            if tool not in self._previous:
                return None
            held = self._previous[tool]
        return _copied(held)

    def _out_of_time(self) -> RunOutOfTime:
        return RunOutOfTime(f"the run passed its limit of {self._run_seconds:g} seconds")

    def _wait(self, delay: float) -> None:
        """Sleep the delay a result states, and never past the run's limit."""
        if not delay > 0:
            return
        if self._deadline is None:
            time.sleep(delay)
            return
        left = self._deadline - time.monotonic()
        if delay <= left:
            time.sleep(delay)
            return
        if left > 0:
            time.sleep(left)
        raise self._stop(self._out_of_time())

    # --- the case --------------------------------------------------------------------------

    def case(self, case: Mapping[str, Any]) -> dict[str, Any]:
        """The case as the run should see it: the condition's input operators applied to its
        ``input`` and its conversation moves to its ``turns``, each in the condition's order on
        what the last left, on the run's seed. A change is recorded as applied when it changed
        something; one that cannot act leaves things as they were. The case handed over is left
        as it was, and anything that is not a mapping is an instrument error."""
        stopped = self.stopped
        if stopped is not None:
            raise stopped
        if not isinstance(case, Mapping):
            raise self._stop(InstrumentError(
                f"a case is the mapping of its line, not {_shown(case)}"))
        try:
            seen: dict[str, Any] = copy.deepcopy(dict(case))
        except Exception:
            seen = dict(case)
        acted: dict[int, bool] = {}
        broke: InstrumentError | None = None
        for index, change in enumerate(self._condition.changes):
            try:
                if change.surface == "input":
                    request = _OPERATORS[change.fault](seen, seed=self._seed)
                    acted[index] = request != _request(seen)
                    if acted[index]:
                        seen["input"] = request
                elif change.surface == "user" and change.call is not None:
                    script = _MOVES[change.fault](seen, turn=int(change.call[1:]),
                                                  seed=self._seed)
                    acted[index] = script != _script(seen)
                    if acted[index]:
                        seen["turns"] = script
            except Exception as wrong:
                broke = InstrumentError(f'"{self._names[index]}" could not be applied to the '
                                        f"case ({_one_line(wrong)})")
                broke.__cause__ = wrong
                break
        if broke is not None:
            raise self._stop(broke)
        with self._lock:
            for index, did in acted.items():
                self._acted[index] = did
        return seen

    # --- the run open around a target's own agent --------------------------------------------

    def __enter__(self) -> Session:
        with _OPEN_LOCK:
            _OPEN.append(self)
        _opened_here().append(self)
        return self

    def __exit__(self, kind: type[BaseException] | None, wrong: BaseException | None,
                 trace: TracebackType | None) -> None:
        here = _opened_here()
        for place in range(len(here) - 1, -1, -1):
            if here[place] is self:
                del here[place]
                break
        with _OPEN_LOCK:
            for place in range(len(_OPEN) - 1, -1, -1):
                if _OPEN[place] is self:
                    del _OPEN[place]
                    break


# ---------------------------------------------------------------------------
# a target's own tools
# ---------------------------------------------------------------------------


def _signature(fn: Callable[..., Any]) -> inspect.Signature | None:
    try:
        return inspect.signature(fn)
    except (TypeError, ValueError):
        return None


def _named(signature: inspect.Signature | None, positional: tuple[Any, ...],
           named: dict[str, Any]) -> dict[str, Any]:
    """The arguments of a call by name, as the tool's own signature names them. Extra keyword
    arguments keep their own names. Where the signature cannot say (there is none, or the call
    does not fit it), a positional argument is named by its place."""
    if signature is not None:
        try:
            bound = signature.bind(*positional, **named)
        except TypeError:
            pass
        else:
            out: dict[str, Any] = {}
            for key, value in bound.arguments.items():
                if signature.parameters[key].kind is inspect.Parameter.VAR_KEYWORD:
                    for extra, given in value.items():
                        out.setdefault(extra, given)
                else:
                    out[key] = value
            return out
    out = {str(place): value for place, value in enumerate(positional)}
    out.update(named)
    return out


def wrap(tool_name: str, fn: Callable[..., _T]) -> Callable[..., _T]:
    """A target's own tool, wrapped so that Break can reach it: the one call a Prove target adds
    per tool. With no run open the wrapped tool is the tool itself. Inside ``with session:`` each
    call goes through ``session.call`` under ``tool_name``, with positional arguments named for
    ``args`` and the tool called as the agent called it. The wrapped tool keeps the tool's name,
    docstring and signature. A tool that is ``async def`` is refused."""
    if not isinstance(tool_name, str) or not tool_name:
        raise TypeError(f"a tool is wrapped under its name, not {_shown(tool_name)}")
    if not callable(fn):
        raise ToolRefused(f'"{tool_name}" is {_shown(fn)}, not something that can be called',
                          tool=tool_name)
    if _is_async(fn):
        raise ToolRefused(f'"{tool_name}" is async, and Break calls a tool and reads what it '
                          "returns: wrap a tool that is not", tool=tool_name)
    signature = _signature(fn)

    @functools.wraps(fn)
    def wrapped(*positional: Any, **named: Any) -> _T:
        run = _current(tool_name)
        if run is None:
            return fn(*positional, **named)
        return cast(_T, run.call(tool_name, _named(signature, positional, named),
                                 lambda: fn(*positional, **named)))

    return wrapped
