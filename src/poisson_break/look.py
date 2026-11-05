"""How everything Break prints reads: one result, two renderings (``docs/cli-look.md``).

A verb builds one :class:`Result`: a verdict word, its sentence, the detail (:class:`Row`,
:class:`Line`, :class:`Table`) and the commands to run next. :func:`render` prints it one of two
ways, and :func:`mode_for` says which.

- **Plain** is the contract: text only, no escape sequence and no box character, written with the
  standard library alone. On a pipe or in a file every fact is one line. On a terminal a long line
  is wrapped at the terminal's width with a hanging indent, a word is never broken, and the
  verdict line and a command to copy are never wrapped. A stream that cannot encode ``·``, ``–``
  or ``×`` gets ``-``, ``-`` and ``x``; any other character it cannot encode is written as its
  escape, so a name never reads as another name.
- **Pretty** carries the same facts in the same order, drawn with Rich by ``_pretty``, the one
  module here that imports Rich and questionary. It runs only when stdout and stderr are both
  terminals, ``NO_COLOR`` is unset or empty, ``CI`` is unset, ``TERM`` is not ``dumb``, stdout is
  UTF-8 and neither ``--json`` nor ``--plain`` was given. Anywhere else, and wherever Rich cannot
  be imported, plain runs, byte for byte, and nothing is said about it.

:func:`run` is how a command goes through the look. It chooses the rendering for the process,
runs the command's body, and turns what the body raises into the shared lines and exit codes
(:data:`EXIT`): :class:`Refused` and :class:`Usage` are one ``error:`` line on stderr with their
``next:`` commands under it; :class:`Stopped` prints the result it carries; Ctrl-C is a
``stopped`` line and exit 130; anything unexpected is one line naming the log the traceback went
to (:func:`errors_log_path`), with the traceback on stderr as well under ``--debug``.

Problems (:func:`error`, :func:`note`), questions (:func:`ask`) and progress (:class:`Progress`)
stay on stderr, so stdout holds the result and nothing else. A question needs a terminal to be
answered on, or ``--yes``; progress is removed from the screen when the work ends. The ``fmt_``
functions print a number the same way everywhere, and :func:`word` and :func:`command` build a
command line a shell reads back exactly.

Colour has four meanings and no others: green, the command did what was asked; yellow, it stopped
short or cannot say; red, an error or a failed check; dim, secondary text. Which verdict word
takes which is the table in this module, and a word on no list is bold with no colour.
"""

from __future__ import annotations

import codecs
import contextlib
import json
import math
import os
import re
import shlex
import sys
import time
import traceback
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Final, Literal, overload

__all__ = [
    "EXIT",
    "Line",
    "Plan",
    "Progress",
    "Refused",
    "Result",
    "Row",
    "Stopped",
    "Table",
    "Usage",
    "as_json",
    "ask",
    "command",
    "err",
    "error",
    "errors_log_path",
    "fmt_count",
    "fmt_dollars",
    "fmt_duration",
    "fmt_hash",
    "fmt_p",
    "fmt_rate",
    "fmt_time",
    "mode_for",
    "note",
    "out",
    "render",
    "run",
    "word",
]

#: The exit codes every Poisson Labs command shares.
EXIT: Final[Mapping[str, int]] = MappingProxyType({
    "done": 0,         # the result is printed, whatever it says
    "refused": 1,      # nothing was spent or written
    "usage": 2,        # the command line is wrong
    "stopped": 3,      # stopped or failed after work started, or an unexpected failure
    "check": 4,        # a check the user asked for did not pass
    "interrupted": 130,
})

# The colour of a verdict word, by its meaning. A word on no list is bold with no colour, as
# `plan` and `different` are: a result that is neither good nor bad.
_GREEN: Final = ("ok", "done", "passed", "wrote", "ready", "found", "confirmed", "rechecked",
                 "fails less")
_YELLOW: Final = ("stopped", "refused", "too small to tell", "nothing found", "nothing confirmed",
                  "not confirmed", "no significant difference", "did not fail")
_RED: Final = ("not ready", "fail", "failed", "fails more")
_MEANING: Final[Mapping[str, str]] = MappingProxyType({
    **dict.fromkeys(_GREEN, "green"),
    **dict.fromkeys(_YELLOW, "yellow"),
    **dict.fromkeys(_RED, "red"),
})

#: The schema of the one result the look itself makes: the stop Ctrl-C prints.
_STOPPED_SCHEMA: Final = "poisson_break.stopped/1"

_VERDICT: Final = re.compile(r"[a-z]+(?: [a-z]+)*")
_RESERVED: Final = ("schema", "verdict", "sentence", "next")


def _meaning(verdict: str) -> str:
    """``green``, ``yellow`` or ``red`` for a word that has a meaning; ``bold`` for any other."""
    return _MEANING.get(verdict, "bold")


# ---------- a command to copy ----------


class _Command(str):
    """A command line for the user to copy. It is text, and can stand wherever text can; the
    renderings never wrap the line that holds one."""

    __slots__ = ()


_BARE: Final = re.compile(r"[A-Za-z0-9_@%+:,./-][A-Za-z0-9_@%+=:,./-]*")
_IN_DOUBLE_QUOTES: Final = frozenset('"$`\\!')


def word(text: str) -> str:
    """``text`` as one word a POSIX shell (sh, bash, zsh) reads back exactly. A word a shell reads
    as itself is left bare, so commands stay readable. Anything else is quoted: in single quotes,
    where a shell reads every character as itself; in double quotes when the text holds a single
    quote and nothing a shell reads inside double quotes; else in single quotes with each single
    quote written ``'\\''``."""
    if _BARE.fullmatch(text):
        return text
    if "'" not in text:
        return f"'{text}'"
    if not _IN_DOUBLE_QUOTES.intersection(text):
        return f'"{text}"'
    return "'" + text.replace("'", "'\\''") + "'"


def command(*words: str) -> str:
    """A command line from its words, joined by spaces. Each word is written as given: pass a
    value that may need quoting through :func:`word` first. What comes back is text, marked so
    that no rendering wraps the line it stands on."""
    return _Command(" ".join(words))


# ---------- a result ----------


@dataclass(frozen=True)
class Row:
    """A detail line, ``label  value``."""

    label: str
    value: str

    def __post_init__(self) -> None:
        for name in ("label", "value"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"a row's {name} is text, already formatted for a person to read")


@dataclass(frozen=True)
class Line:
    """A detail line that is one sentence."""

    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("a line is text, already formatted for a person to read")


@dataclass(frozen=True)
class Table:
    """A detail table: the header's cells, then each row's, every cell text. Every row has as
    many cells as the header."""

    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        if isinstance(self.header, str) or any(isinstance(row, str) for row in self.rows):
            raise TypeError("a table's header and each of its rows is a sequence of cells")
        object.__setattr__(self, "header", tuple(self.header))
        object.__setattr__(self, "rows", tuple(tuple(row) for row in self.rows))
        for cells in (self.header, *self.rows):
            if not all(isinstance(cell, str) for cell in cells):
                raise TypeError("a table's cell is text, already formatted for a person to read")
            if len(cells) != len(self.header):
                raise ValueError(f"a row of {len(cells)} cells in a table of "
                                 f"{len(self.header)} columns")


@dataclass(frozen=True)
class Result:
    """What a verb prints: the verdict word and its sentence, which make the first line; the
    detail, in the order given; the commands to run next, which come last. ``schema`` names the
    shape ``--json`` writes and ``data`` is what that document carries after its first three
    keys. A result is data: rendering it changes nothing, and it can be rendered again.

    A verdict or a sentence that could not make the verdict line is refused here, when the result
    is made, with ``ValueError``: the word is lowercase letters, in words one space apart, and
    the sentence opens with something to read."""

    verdict: str
    sentence: str
    detail: tuple[Row | Line | Table, ...] = ()
    nexts: tuple[str, ...] = ()
    schema: str | None = None
    data: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.verdict, str) or _VERDICT.fullmatch(self.verdict) is None:
            raise ValueError("a verdict is lowercase letters, in words one space apart")
        if (not isinstance(self.sentence, str) or not self.sentence.strip()
                or self.sentence[0].isspace()):
            raise ValueError("a verdict's sentence opens with something to read")
        detail = tuple(self.detail)
        if not all(isinstance(part, (Row, Line, Table)) for part in detail):
            raise TypeError("a detail part is a Row, a Line or a Table")
        nexts = tuple(self.nexts)
        if isinstance(self.nexts, str) or not all(isinstance(n, str) and n.strip() for n in nexts):
            raise TypeError("the next commands are a sequence of command lines")
        if self.schema is not None and not (isinstance(self.schema, str) and self.schema):
            raise ValueError("a schema is a name, or None")
        data = dict(self.data or {})
        taken = sorted(key for key in data if not isinstance(key, str) or key in self._reserved())
        if taken:
            raise ValueError("the data cannot hold a key the document writes itself: "
                             + ", ".join(str(key) for key in taken))
        object.__setattr__(self, "detail", detail)
        object.__setattr__(self, "nexts", nexts)
        object.__setattr__(self, "data", MappingProxyType(data))

    def _reserved(self) -> tuple[str, ...]:
        return _RESERVED


@dataclass(frozen=True, init=False)
class Plan(Result):
    """What a command that spends shows before it starts: a result whose verdict is ``plan``,
    with an estimate and the source the estimate comes from. Both are printed, as the last detail
    line, and both are in the ``--json`` document."""

    estimate: str = field(default="", kw_only=True)
    source: str = field(default="", kw_only=True)

    def __init__(self, sentence: str, *, estimate: str, source: str,
                 detail: Sequence[Row | Line | Table] = (), nexts: Sequence[str] = (),
                 schema: str | None = None, data: Mapping[str, Any] | None = None) -> None:
        for name, value in (("estimate", estimate), ("source", source)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"a plan names its {name}")
            object.__setattr__(self, name, value)
        Result.__init__(self, "plan", sentence, tuple(detail), tuple(nexts), schema, data)

    def _reserved(self) -> tuple[str, ...]:
        return (*_RESERVED, "estimate", "source")


def _detail(result: Result) -> tuple[Row | Line | Table, ...]:
    """The detail both renderings print: a plan's estimate and its source are its last line."""
    if isinstance(result, Plan):
        return (*result.detail, Row("estimate", f"{result.estimate}, from {result.source}"))
    return result.detail


def as_json(result: Result) -> str:
    """The result as one strict JSON document, ended by a line end: ``schema``, ``verdict`` and
    ``sentence`` first, a plan's ``estimate`` and ``source``, the result's data, then ``next``
    when there are commands to run next. Everything is written in ASCII, so the document is the
    same bytes on every stream. A value that is not a number (``NaN``, an infinity) is refused
    with ``ValueError``: the document never holds one."""
    document: dict[str, Any] = {"schema": result.schema, "verdict": result.verdict,
                                "sentence": result.sentence}
    if isinstance(result, Plan):
        document.update(estimate=result.estimate, source=result.source)
    document.update(result.data or {})
    if result.nexts:
        document["next"] = [str(line) for line in result.nexts]
    return json.dumps(document, indent=2, allow_nan=False, ensure_ascii=True) + "\n"


# ---------- problems a body raises ----------


class _Said(Exception):
    """One sentence, and the commands that move the user on."""

    def __init__(self, sentence: str, nexts: Sequence[str] = ()) -> None:
        super().__init__(sentence)
        self.sentence = sentence
        self.nexts = tuple(nexts)


class Refused(_Said):
    """A refusal: nothing was spent or written. One ``error:`` line, exit 1."""


class Usage(_Said):
    """The command line is wrong. One ``error:`` line, exit 2."""


class Stopped(Exception):
    """The work stopped after it started. :func:`run` prints ``result`` on stdout and exits with
    ``code``: 3, or ``EXIT["interrupted"]`` when a verb caught Ctrl-C and says what it kept."""

    def __init__(self, result: Result, code: int = EXIT["stopped"]) -> None:
        super().__init__(result.sentence)
        self.result = result
        self.code = code


# ---------- numbers ----------


def _number(value: float, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} is a number")
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{what} is a number, and this is not one")
    return value


def fmt_rate(value: float, signed: bool = False) -> str:
    """A rate or a share to three decimals: ``0.150``. ``signed=True`` is for a difference
    between two rates, which always shows its sign: ``+0.870``, ``-0.200``. A rate outside 0 to
    1, a difference outside -1 to 1, and anything that is not a number are refused."""
    _number(value, "a rate")
    if signed:
        if not -1 <= value <= 1:
            raise ValueError("a difference between two rates lies between -1 and 1")
        return f"{value + 0.0:+.3f}" if value else "+0.000"
    if not 0 <= value <= 1:
        raise ValueError("a rate lies between 0 and 1")
    return f"{value:.3f}"


def fmt_p(value: float) -> str:
    """A p-value to three decimals, or with an exponent below 0.001 (``2.3e-08``), so that a
    small one never reads as zero. A value outside 0 to 1 is refused."""
    _number(value, "a p-value")
    if not 0 <= value <= 1:
        raise ValueError("a p-value lies between 0 and 1")
    return f"{value:.1e}" if 0 < value < 0.001 else f"{value:.3f}"


def fmt_dollars(value: float) -> str:
    """Dollars as ``$1.00``, or with two significant digits below $0.10: ``$0.021``, ``$0.0052``,
    ``$0.0040``. Nothing at all is ``$0.00``. A negative amount is refused."""
    _number(value, "an amount")
    if value < 0:
        raise ValueError("an amount of dollars is not negative")
    if value == 0:
        return "$0.00"
    digits, _, exponent = f"{value:.1e}".partition("e")
    if int(exponent) >= -1:  # ten cents or more, once it is rounded to two digits
        return f"${value:,.2f}"
    return "$0." + "0" * (-int(exponent) - 1) + digits.replace(".", "")


def fmt_count(value: float) -> str:
    """A count with thousands separators: ``4,200``. A count is a whole number."""
    _number(value, "a count")
    if value != int(value):
        raise ValueError("a count is a whole number")
    return f"{int(value):,}"


def fmt_duration(seconds: float) -> str:
    """A duration to the second below an hour and to the minute from there: ``45 s``,
    ``1 min 40 s``, ``1 h 36 min``."""
    _number(seconds, "a duration")
    if seconds < 0:
        raise ValueError("a duration is not negative")
    whole = int(seconds + 0.5)
    if whole < 60:
        return f"{whole} s"
    if whole < 3600:
        return f"{whole // 60} min {whole % 60} s"
    return f"{whole // 3600:,} h {whole % 3600 // 60} min"


def fmt_time(when: datetime) -> str:
    """A time in UTC, to the second, ending in ``Z``: ``2026-11-04T18:00:05Z``. A time with no
    zone cannot be said in UTC and is refused."""
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError("a time with no zone cannot be said in UTC")
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt_hash(value: str) -> str:
    """A hash as text shows it: its first 12 characters. ``--json`` carries it whole."""
    return value[:12]


# ---------- writing ----------

# The three glyphs Break's own lines use, for a stream that cannot encode them. One mark for one
# mark, so a line keeps its words and its numbers apart and in order.
_STAND_IN: Final[Mapping[str, str]] = MappingProxyType({"·": "-", "–": "-", "×": "x"})


def _encodes(text: str, encoding: str) -> bool:
    try:
        text.encode(encoding)
    except UnicodeEncodeError:
        return False
    except LookupError:  # an encoding Python does not know is left to the stream
        return True
    return True


def _fit(text: str, encoding: str | None) -> str:
    """The text as a stream in ``encoding`` can write it: itself where it can, else with each
    character out of the stream's reach replaced. One of Break's glyphs becomes its ASCII
    stand-in. Any other, a character of a name the user chose, becomes its escape
    (``caf\\xe9``), so two names never read as one."""
    if not encoding or text.isascii() or _encodes(text, encoding):
        return text
    return "".join(
        ch if ch.isascii() or _encodes(ch, encoding)
        else _STAND_IN.get(ch) or ch.encode("ascii", "backslashreplace").decode("ascii")
        for ch in text
    )


def _write(stream: Any, text: str) -> None:
    """Write and flush. A stream that is not there takes nothing. A reader that has gone away
    (``poisson-break findings | head -1``) ends the output quietly: the stream is pointed at the
    null device, so nothing more fails, then or when the process ends."""
    if stream is None:
        return
    try:
        stream.write(_fit(text, getattr(stream, "encoding", None)))
        stream.flush()
    except BrokenPipeError:
        with contextlib.suppress(AttributeError, OSError, ValueError):
            null = os.open(os.devnull, os.O_WRONLY)
            os.dup2(null, stream.fileno())
            os.close(null)


def out(text: str) -> None:
    """Write ``text`` to stdout as given, its line ends included."""
    _write(sys.stdout, text)


def err(text: str) -> None:
    """Write ``text`` to stderr as given, its line ends included."""
    _write(sys.stderr, text)


def _shown(text: str) -> str:
    """A value as one line a person reads: a line break inside it reads as a space, and a control
    character (an escape, a bell, a tab) is written as its escape, so it is shown and never
    acted on. Everything else is printed as it is."""
    if text.isascii() and text.isprintable():
        return text
    line = " ".join(text.splitlines())
    return "".join(
        ch.encode("unicode_escape").decode("ascii") if unicodedata.category(ch) in ("Cc", "Cs")
        else ch
        for ch in line
    )


def _is_terminal(stream: Any) -> bool:
    """Whether the stream is a terminal. One that is closed, or not there, is not."""
    try:
        return bool(stream is not None and stream.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def _utf8(stream: Any) -> bool:
    name = getattr(stream, "encoding", None)
    if not isinstance(name, str) or not name:
        return False
    try:
        return codecs.lookup(name).name == "utf-8"
    except LookupError:
        return False


def _width(stream: Any) -> int:
    """The width of the terminal the stream is, in columns; 80 when it cannot be asked."""
    try:
        return max(20, os.get_terminal_size(stream.fileno()).columns)
    except (AttributeError, ValueError, OSError):
        return 80


def _given(argv: Sequence[str], flag: str) -> bool:
    """Whether ``flag`` itself is among the command line's options: a word after ``--`` is an
    argument, and a longer word that holds the flag is another word."""
    for text in argv:
        if text == "--":
            return False
        if text == flag:
            return True
    return False


def mode_for(stdout: Any, stderr: Any, env: Mapping[str, str],
             argv: Sequence[str]) -> Literal["plain", "pretty"]:
    """Which rendering runs. ``pretty`` only when every condition holds: stdout and stderr are
    both terminals, ``NO_COLOR`` is unset or empty, ``CI`` is unset, ``TERM`` is not ``dumb``,
    stdout is UTF-8, and neither ``--json`` nor ``--plain`` is on the command line before a
    ``--``. Any one of them alone gives ``plain``. Only what is passed in is read: not the
    process's own environment, and not its own command line."""
    if _given(argv, "--json") or _given(argv, "--plain"):
        return "plain"
    if not (_is_terminal(stdout) and _is_terminal(stderr)):
        return "plain"
    if env.get("NO_COLOR") or "CI" in env or env.get("TERM") == "dumb":
        return "plain"
    return "pretty" if _utf8(stdout) else "plain"


# ---------- the plain rendering ----------


def _wrap(line: str, width: int, hang: int) -> list[str]:
    """``line`` as rows no wider than ``width`` where its words allow. It is broken only at
    spaces, a word is never broken, and the spaces inside a row are kept. The first row keeps the
    line's own indent and each row after it is indented ``hang``, deeper than the line, so the
    rows read as one fact. A line that fits is itself."""
    if len(line) <= width:
        return [line]
    indent = len(line) - len(line.lstrip(" "))
    if hang <= indent or hang > width // 2:
        hang = indent + 2
    rows: list[str] = []
    row, holds_a_word = " " * indent, False
    for piece in re.findall(r"[^ ]+ *", line[indent:]):
        if holds_a_word and len(row) + len(piece.rstrip(" ")) > width:
            rows.append(row.rstrip(" "))
            row = " " * hang
        row += piece
        holds_a_word = True
    rows.append(row.rstrip(" "))
    return rows


def _table_rows(table: Table) -> list[str]:
    """A table's lines, the header first: each column as wide as its widest cell, two spaces
    between columns."""
    rows = [[_shown(cell) for cell in cells] for cells in (table.header, *table.rows)]
    widths = [max(len(row[i]) for row in rows) for i in range(len(table.header))]
    return ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip()
            for row in rows]


def _label_column(detail: Sequence[Row | Line | Table]) -> int:
    return max((len(_shown(part.label)) for part in detail if isinstance(part, Row)), default=0)


def _plain_lines(result: Result, width: int | None) -> list[str]:
    """The plain rendering's lines. ``width`` is the terminal's, or None for a pipe or a file,
    where nothing is wrapped. The verdict line and a line that holds a command are never
    wrapped."""

    def rows_of(line: str, hang: int, held: bool) -> list[str]:
        return [line] if width is None or held else _wrap(line, width, hang)

    lines = [f"{result.verdict}  {_shown(result.sentence)}"]
    detail = _detail(result)
    column = _label_column(detail)
    for part in detail:
        if isinstance(part, Row):
            head = f"  {_shown(part.label).ljust(column)}  "
            lines += rows_of((head + _shown(part.value)).rstrip(" "), len(head),
                             isinstance(part.value, _Command))
        elif isinstance(part, Line):
            lines += rows_of("  " + _shown(part.text), 4, isinstance(part.text, _Command))
        elif isinstance(part, Table):
            held = any(isinstance(cell, _Command) for row in part.rows for cell in row)
            for row in _table_rows(part) if part.header else ():
                lines += rows_of(("  " + row).rstrip(" "), 4, held)
        else:
            raise TypeError("a detail part is a Row, a Line or a Table")
    lines += [f"next: {_shown(line)}" for line in result.nexts]
    return lines


def render(result: Result, *, stream: Any, mode: str) -> None:
    """Print ``result`` on ``stream`` in ``mode``, ``plain`` or ``pretty``; any other mode is a
    ``ValueError``. ``pretty`` is drawn only on a terminal that takes UTF-8, with Rich there to
    import. Anywhere else it prints what ``plain`` prints, byte for byte."""
    if mode not in ("plain", "pretty"):
        raise ValueError(f"the mode is plain or pretty, not {_shown(str(mode))}")
    terminal = _is_terminal(stream)
    if mode == "pretty" and terminal and _utf8(stream):
        pretty = _pretty()
        if pretty is not None:
            pretty.result(result, stream, _width(stream))
            return
    lines = _plain_lines(result, _width(stream) if terminal else None)
    _write(stream, "".join(line + "\n" for line in lines))


# ---------- the run ----------


@dataclass(frozen=True)
class _Session:
    """What one run chose for itself, and what its command line said. Outside a run nothing is
    chosen: problems print plain, and no question is answered for the user."""

    tool: str = ""
    mode: str = "plain"
    json: bool = False
    yes: bool = False
    debug: bool = False


_session = _Session()
_missing: list[bool] = []
_progress_lines: list[Progress] = []


def _pretty() -> ModuleType | None:
    """The module that draws pretty, or None where Rich cannot be imported: missing, or there
    and failing as it loads. It is loaded the first time something is drawn pretty and never
    before, so a plain run loads none of it."""
    if _missing:
        return None
    try:
        from poisson_break import _pretty as module
    except Exception:  # whatever stops Rich loading, the answer is the same: plain
        _missing.append(True)
        return None
    return module


def _drawn(stream: Any) -> ModuleType | None:
    """The pretty module when this run draws ``stream`` pretty, else None."""
    if _session.mode != "pretty" or not _is_terminal(stream):
        return None
    return _pretty()


def _problem(label: str, sentence: str, nexts: Sequence[str]) -> None:
    stream = sys.stderr
    sentence = _shown(sentence)
    commands = [_shown(line) for line in nexts]
    pretty = _drawn(stream)
    if pretty is not None:
        pretty.problem(stream, label, sentence, commands)
        return
    # a line of progress now on this stream is taken off first and put back after, so the
    # problem is a line of its own
    shown = next((line for line in reversed(_progress_lines) if line._stream is stream), None)
    if shown is not None:
        shown._erase()
    _write(stream, f"{label} {sentence}\n" + "".join(f"  next: {c}\n" for c in commands))
    if shown is not None:
        shown._draw()


def error(sentence: str, nexts: Sequence[str] = ()) -> None:
    """``error: <sentence>`` on stderr, as one line however long, and each command to run next
    on its own ``  next:`` line under it."""
    _problem("error:", sentence, nexts)


def note(sentence: str) -> None:
    """``note: <sentence>`` on stderr, as one line: a warning."""
    _problem("note:", sentence, ())


def errors_log_path() -> Path:
    """Where the traceback of an unexpected failure is appended: a file under the user's home
    folder, outside the folder the command runs in."""
    return Path.home() / ".cache" / "poisson-break" / "errors.log"


def _from_home(path: Path) -> str:
    """The path as a person reads it and a shell takes it: from ``~`` when it is under the home
    folder."""
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except (ValueError, RuntimeError):
        return str(path)


def _unexpected(session: _Session, argv: Sequence[str], failure: Exception) -> None:
    """One ``error:`` line for a failure nobody planned for, naming its type and the log its
    traceback went to. The traceback is also printed under ``--debug``, and when the log cannot
    be written, since then it has nowhere else to go."""
    details = "".join(traceback.format_exception(failure))
    what = f"an unexpected failure inside {session.tool} ({type(failure).__name__})"
    shown = "~/.cache/poisson-break/errors.log"
    kept = False
    with contextlib.suppress(OSError, RuntimeError):
        path = errors_log_path()
        shown = _from_home(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        when = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        # a word the command line could not read as text is kept escaped, never refused
        with open(path, "a", encoding="utf-8", errors="backslashreplace") as log:
            log.write(f"--- {when}  {shlex.join([session.tool, *argv])}\n{details}\n")
        kept = True
    if kept:
        error(f"{what}; the details are in {shown}")
        if session.debug:
            err(details)
    else:
        error(f"{what}; its log, {shown}, could not be written, so the details follow")
        err(details)


def _show(result: Result) -> None:
    """A result on stdout as this run prints one: the document under ``--json``, else the run's
    rendering."""
    if _session.json:
        _write(sys.stdout, as_json(result))
    else:
        render(result, stream=sys.stdout, mode=_session.mode)


def run(tool: str, argv: Sequence[str], body: Callable[[], int | None]) -> int:
    """Run a command's ``body`` under the look and return its exit code.

    ``tool`` is the command's name as the user typed it, and ``argv`` the words after it. The
    rendering is chosen once, by :func:`mode_for` on the process's own streams and environment,
    and holds for :func:`error`, :func:`note`, :func:`ask` and :class:`Progress` until the body
    ends; ``--yes`` and ``--debug`` are read from ``argv`` the same way. ``body`` returns an exit
    code, or nothing for 0.

    What the body raises becomes the shared lines and codes: :class:`Refused`, its ``error:``
    line and exit 1; :class:`Usage`, the same and exit 2; :class:`Stopped`, its result on stdout
    and its code; Ctrl-C, ``stopped  interrupted: ...`` on stdout and exit 130; anything else,
    one line naming the log its traceback went to, and exit 3. ``SystemExit`` passes through.
    Under ``--json`` a stop is one document on stdout and a problem stays on stderr, in text.
    When the body ends the process is as it was found."""
    global _session
    words = [str(text) for text in argv]
    mode: str = mode_for(sys.stdout, sys.stderr, os.environ, words)
    if mode == "pretty" and _pretty() is None:
        mode = "plain"
    held = _session
    session = _Session(tool=str(tool), mode=mode, json=_given(words, "--json"),
                       yes=_given(words, "--yes"), debug=_given(words, "--debug"))
    _session = session
    try:
        try:
            try:
                code = body()
                return EXIT["done"] if code is None else int(code)
            except Refused as said:
                error(said.sentence, said.nexts)
                return EXIT["refused"]
            except Usage as said:
                error(said.sentence, said.nexts)
                return EXIT["usage"]
            except Stopped as stop:
                _show(stop.result)
                return int(stop.code)
        except KeyboardInterrupt:
            if _is_terminal(sys.stderr):
                err("\n")  # the terminal has just drawn ^C: the stop is a line of its own
            _show(Result("stopped", "interrupted: nothing was kept", schema=_STOPPED_SCHEMA))
            return EXIT["interrupted"]
        except Exception as failure:  # the one place an unplanned failure is caught
            _unexpected(session, words, failure)
            return EXIT["stopped"]
    except Exception:  # the failure's own line could not be printed: the code still says it
        return EXIT["stopped"]
    finally:
        _session = held


# ---------- questions ----------


def _prompt(question: str, bracket: str, width: int | None) -> list[str]:
    """A question and its bracketed default as the lines of a prompt. On a terminal the question
    is wrapped at ``width``; the bracket is never broken, and stands on a line of its own when
    the question's last line has no room for it."""
    line = f"{question} {bracket}"
    if width is None or len(line) <= width:
        return [line]
    rows = _wrap(question, width, 2)
    if len(rows[-1]) + 1 + len(bracket) <= width:
        rows[-1] += " " + bracket
    else:
        rows.append("  " + bracket)
    return rows


def _put_question(lines: Sequence[str], bracket: str) -> None:
    stream = sys.stderr
    pretty = _drawn(stream)
    if pretty is not None:
        pretty.question(stream, lines, bracket)
    else:
        _write(stream, "\n".join(lines) + " ")


def _answer(question: str) -> str:
    """One typed line, trimmed. A stdin that ends first is a refusal."""
    line = sys.stdin.readline() if sys.stdin is not None else ""
    if not line:  # nothing was typed, so the cursor is still on the prompt's line
        err("\n")
        raise Refused(f'the question "{question}" was not answered: '
                      "stdin ended before an answer")
    return line.strip()


def _asked(question: str, bracket: str) -> str:
    stream = sys.stderr
    _put_question(_prompt(question, bracket, _width(stream) if _is_terminal(stream) else None),
                  bracket)
    return _answer(question)


def _numbered_menu(question: str, default: str, choices: Sequence[str]) -> str:
    """A menu as text: the question, each choice on a numbered line, then a prompt that takes a
    number, a choice's own word, or Enter for the default."""
    shown = [_shown(choice) for choice in choices]
    digits = len(str(len(choices)))
    listing = [question, *(f"  {number:>{digits}}  {choice}"
                           for number, choice in enumerate(shown, 1))]
    stream = sys.stderr
    pretty = _drawn(stream)
    if pretty is not None:
        pretty.listing(stream, listing)
    else:
        _write(stream, "".join(line + "\n" for line in listing))
    bracket = f"[{_shown(default)}]"
    while True:
        answer = _asked("choice", bracket)
        if not answer:
            return default
        if answer in choices:
            return answer
        if answer in shown:
            return choices[shown.index(answer)]
        if answer.isascii() and answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1]
        note(f"answer with a number from 1 to {len(choices)}, or a choice as it is written")


def _menu(question: str, default: str, choices: Sequence[str]) -> str:
    stream = sys.stderr
    pretty = _drawn(stream)
    if pretty is not None and _utf8(stream):
        with contextlib.suppress(ImportError):  # no questionary: the menu is asked as text
            return str(pretty.menu(question, default, [(_shown(c), c) for c in choices]))
    return _numbered_menu(question, default, choices)


@overload
def ask(question: str, default: bool, choices: None = None) -> bool: ...
@overload
def ask(question: str, default: str, choices: Sequence[str] | None = None) -> str: ...


def ask(question: str, default: bool | str, choices: Sequence[str] | None = None) -> bool | str:
    """Ask on stderr, read the answer from stdin, and return it.

    A ``bool`` default asks ``[y/N]`` (or ``[Y/n]``) and returns a ``bool``: ``y``, ``yes``,
    ``n`` and ``no`` answer in any case, Enter takes the default, and anything else asks again.
    A text default asks ``[default]`` and returns what was typed, or the default on Enter. With
    ``choices`` the question is a menu, and the default is one of them: questionary's in the
    pretty rendering, moved with the arrow keys; in plain a numbered list that takes a number or
    a choice's own word.

    ``--yes`` on the command line :func:`run` was given answers without asking: yes to a
    ``[y/N]`` question, the default to any other. Without it a stdin that is not a terminal
    refuses the question (:class:`Refused`), and so does a stdin that ends before an answer."""
    if choices is not None:
        choices = list(choices)
        if isinstance(default, bool) or default not in choices:
            raise ValueError("a menu's default is one of its choices")
        if len(set(choices)) != len(choices):
            raise ValueError("a menu's choices are all different")
    elif not isinstance(default, (bool, str)):
        raise TypeError("a question's default is True, False or text")
    question = _shown(question)
    if _session.yes:
        return True if isinstance(default, bool) else default
    if not _is_terminal(sys.stdin):
        raise Refused(f'the question "{question}" was not answered: '
                      "stdin is not a terminal and --yes was not given")
    if choices is not None:
        assert isinstance(default, str)
        return _menu(question, default, choices)
    if isinstance(default, bool):
        while True:
            answer = _asked(question, "[Y/n]" if default else "[y/N]").lower()
            if not answer:
                return default
            if answer in ("y", "yes"):
                return True
            if answer in ("n", "no"):
                return False
            note("answer y or n")
    return _asked(question, f"[{_shown(default)}]") or default


# ---------- progress ----------


class Progress:
    """Progress through ``total`` steps of work, shown on stderr while the work runs and removed
    from the screen when it ends, whether it ends well or not::

        with look.Progress("searching the conditions", 340) as progress:
            for condition in conditions:
                ...
                progress.advance()

    On a terminal it is one line that is redrawn: a bar in the pretty rendering, the label and
    the count in plain. An ``error:`` or a ``note:`` printed while it is shown lands above it.
    Where stderr is no terminal nothing is shown, so a pipe or a log holds the problems and
    nothing else. A result is printed after the work ends, not while the progress is shown."""

    def __init__(self, label: str, total: int) -> None:
        self.label = label
        self.total = max(0, int(total))
        self.done = 0
        self._stream: Any = None
        self._bar: Any = None
        self._drawn = 0
        self._last = 0.0

    def __enter__(self) -> Progress:
        stream = sys.stderr
        if not _is_terminal(stream):
            return self
        self._stream = stream
        pretty = _drawn(stream)
        if pretty is not None:
            self._bar = pretty.Bar(stream, _shown(self.label), self.total, _width(stream))
            self._bar.start()
        else:
            _progress_lines.append(self)
            self._draw()
        return self

    def advance(self, by: int = 1) -> None:
        """``by`` more steps are done."""
        self.done += by
        if self._bar is not None:
            self._bar.advance(by)
        elif self._stream is not None and time.monotonic() - self._last >= 0.1:
            self._draw()

    def _draw(self) -> None:
        # one line, redrawn in place: short enough that the terminal never folds it
        room = _width(self._stream) - 1
        count = f"{self.done:,}/{self.total:,}"
        words = _shown(self.label).split(" ")
        while words and len(f"  {' '.join(words)} {count}") > room:
            words.pop()
        text = f"  {' '.join(words)} {count}" if words else f"  {count}"[:room]
        _write(self._stream, "\r" + text.ljust(self._drawn))
        self._drawn = len(text)
        self._last = time.monotonic()

    def _erase(self) -> None:
        _write(self._stream, "\r" + " " * self._drawn + "\r")
        self._drawn = 0

    def __exit__(self, *failure: object) -> None:
        if self._bar is not None:
            self._bar.stop()
        elif self._stream is not None:
            self._erase()
        if self in _progress_lines:
            _progress_lines.remove(self)
        self._stream = self._bar = None
