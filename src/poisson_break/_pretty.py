"""The pretty rendering: what ``look`` prints on a terminal, drawn with Rich, and its menus,
asked with questionary (``docs/cli-look.md``, rule 16).

The one module of this package that imports Rich, and the only one that loads questionary.
``look`` imports it the first time something is drawn pretty, and a Break that cannot import
Rich prints plain and says nothing: the ``ImportError`` raised here is caught there.

What is drawn carries the same facts in the same order as the plain rendering:

- :func:`result` draws a result: the verdict word in its meaning's colour and bold, the sentence
  as it is; each row's label dim; a table with a dim header over a rule; ``next:`` dim and the
  command bold. A long line is wrapped at the terminal's width where plain wraps it, a word is
  never broken, and the verdict line and a command are never wrapped.
- A table too wide for the terminal folds. First a unit every cell of a column repeats moves
  into the column's header (``took`` over ``1,210 ms`` becomes ``took (ms)`` over ``1,210``).
  When that is still too wide each row is printed as a record, one ``column  value`` to a line.
  No cell is cut and nothing is dropped.
- :func:`problem` draws an ``error:`` or a ``note:`` line, :func:`question` a prompt,
  :func:`menu` a menu, and :class:`Bar` the progress of work, which is removed when the work
  ends. All four are on stderr.

Colour has four meanings and no others: green, yellow and red for a verdict word, ``note:`` and
``error:``, and dim for secondary text. Only the terminal's sixteen named colours, bold and dim
are used, so the user's theme decides the shades. A number is never coloured, and what a value
holds is printed as it is: nothing in it is read as markup, an emoji code or a link.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from typing import Any, Final

from rich import box
from rich.console import Console
from rich.padding import Padding
from rich.progress import BarColumn, TaskID, TextColumn
from rich.progress import Progress as Bars
from rich.table import Table as Grid
from rich.text import Text

from poisson_break import look

__all__ = ["Bar", "listing", "menu", "problem", "question", "result"]

#: A verdict word's style, by its meaning.
_WORD: Final = {"green": "bold green", "yellow": "bold yellow", "red": "bold red", "bold": "bold"}
#: The label of a problem line.
_LABEL: Final = {"error:": "bold red", "note:": "yellow"}

#: The bars now on screen, the newest last: a problem printed while one is shown goes above it.
_shown_bars: list[Bars] = []


def _console(stream: Any, width: int) -> Console:
    """A console on ``stream`` held to the sixteen named colours, which reads nothing in a text
    as markup, an emoji code or something to highlight."""
    return Console(file=stream, force_terminal=True, force_jupyter=False, color_system="standard",
                   no_color=False, width=max(20, width), highlight=False, markup=False,
                   emoji=False, legacy_windows=False)


def _text(stream: Any, text: str) -> str:
    return look._fit(text, getattr(stream, "encoding", None))


# ---------- a result ----------


def result(res: look.Result, stream: Any, width: int) -> None:
    """Draw ``res`` on ``stream``, a terminal ``width`` columns wide."""
    console = _console(stream, width)
    lines: list[Any] = [Text.assemble((res.verdict, _WORD[look._meaning(res.verdict)]),
                                      "  " + _text(stream, look._shown(res.sentence)))]
    detail = look._detail(res)
    column = look._label_column(detail)
    for part in detail:
        if isinstance(part, look.Row):
            label = _text(stream, look._shown(part.label)).ljust(column)
            value = _text(stream, look._shown(part.value))
            line = f"  {label}  {value}".rstrip(" ")
            rows = ([line] if isinstance(part.value, look._Command)
                    else look._wrap(line, width, column + 4))
            lines.append(Text.assemble("  ", (label, "dim"), rows[0][2 + len(label):]))
            lines += [Text(row) for row in rows[1:]]
        elif isinstance(part, look.Line):
            line = "  " + _text(stream, look._shown(part.text))
            rows = [line] if isinstance(part.text, look._Command) else look._wrap(line, width, 4)
            lines += [Text(row) for row in rows]
        elif isinstance(part, look.Table):
            lines += _table(part, stream, console, width)
        else:
            raise TypeError("a detail part is a Row, a Line or a Table")
    for command in res.nexts:
        lines.append(Text.assemble(("next:", "dim"), " ",
                                   (_text(stream, look._shown(command)), "bold")))
    for line in lines:
        # soft_wrap: the line is written whole, and the terminal folds what is wider than it is
        console.print(line, soft_wrap=isinstance(line, Text))


# ---------- tables ----------

#: A cell that is a number as the look prints one: a count, a rate, a p-value, a signed
#: difference, dollars, a share of a hundred.
_NUMBER: Final = re.compile(r"[+\-]?\$?\d[\d,]*(?:\.\d+)?(?:e[+\-]?\d+)?%?")
#: A cell that is a number and then its unit: ``1,210 ms``, ``+3.2 points``.
_WITH_UNIT: Final = re.compile(r"([+\-]?\$?\d[\d,]*(?:\.\d+)?(?:e[+\-]?\d+)?) ([A-Za-z%]+)")


def _units_moved(header: Sequence[str],
                 rows: Sequence[Sequence[str]]) -> tuple[list[str], list[list[str]]] | None:
    """The table with each unit that every cell of a column repeats moved into the column's
    header, or None when no column has one. A column of mixed units, or with a cell that has
    none, is left as it is: moving a unit over a cell that does not carry it would change a
    number."""
    head, body = list(header), [list(row) for row in rows]
    moved = False
    for i in range(len(head)):
        found = [_WITH_UNIT.fullmatch(row[i]) for row in body]
        units = {match.group(2) for match in found if match is not None}
        if not body or len(units) != 1 or not all(found):
            continue
        unit = units.pop()
        head[i] = f"{head[i]} ({unit})" if head[i] else f"({unit})"
        for row in body:
            row[i] = row[i][: -len(unit) - 1]
        moved = True
    return (head, body) if moved else None


def _aligned(header: Sequence[str], rows: Sequence[Sequence[str]], verdicts: Sequence[int]) -> Grid:
    """The table in columns two spaces apart: the header dim over a dim rule, a column of
    numbers to the right, a verdict word in its meaning's colour. No cell is wrapped or cut."""
    grid = Grid(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, padding=(0, 1, 0, 0),
                header_style="dim", border_style="dim")
    for i, name in enumerate(header):
        numbers = bool(rows) and all(not row[i] or _NUMBER.fullmatch(row[i]) for row in rows)
        # the table is drawn only where it fits, so nothing is ever folded; Rich lines a column
        # up to the right only under an overflow that is not "ignore"
        grid.add_column(Text(name), justify="right" if numbers else "left", no_wrap=True,
                        overflow="fold")
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            meaning = look._meaning(cell) if i in verdicts else "bold"
            cells.append(Text(cell, style="" if meaning == "bold" else meaning))
        grid.add_row(*cells)
    return grid


def _records(header: Sequence[str], rows: Sequence[Sequence[str]], width: int) -> list[Text]:
    """One record per row, for a table no fold makes narrow enough: the row's first cell, then
    every other cell on a line of its own under it, ``column  value``, the column's name dim.
    A value is wrapped at ``width`` where its words allow, and no word is broken."""
    lines: list[Text] = []
    names = [name for name in header[1:]]
    column = max((len(name) for name in names), default=0)
    for row in rows:
        head = f"  {header[0]}  {row[0]}" if header[0] else f"  {row[0]}"
        first, *more = look._wrap(head.rstrip(" "), width, 6)
        at = 2 + len(header[0])
        lines.append(Text.assemble("  ", (header[0], "dim"), first[at:]))
        lines += [Text(text) for text in more]
        for name, cell in zip(names, row[1:], strict=True):
            line = f"    {name.ljust(column)}  {cell}".rstrip(" ")
            first, *more = look._wrap(line, width, column + 6)
            lines.append(Text.assemble("    ", (name.ljust(column), "dim"),
                                       first[4 + column:]))
            lines += [Text(text) for text in more]
    return lines


def _table(table: look.Table, stream: Any, console: Console, width: int) -> list[Any]:
    """A table for a terminal ``width`` wide, indented two: in columns when it fits; with its
    repeated units in the header when that makes it fit; else one record per row, each cell as
    it was written."""
    header = [_text(stream, look._shown(cell)) for cell in table.header]
    rows = [[_text(stream, look._shown(cell)) for cell in row] for row in table.rows]
    if not header:
        return []
    verdicts = [i for i, name in enumerate(header) if name == "verdict"]
    room = width - 2
    drawn = _aligned(header, rows, verdicts)
    if console.measure(drawn).maximum <= room:
        return [Padding(drawn, (0, 0, 0, 2), expand=False)]
    moved = _units_moved(header, rows)
    if moved is not None:
        drawn = _aligned(*moved, verdicts)
        if console.measure(drawn).maximum <= room:
            return [Padding(drawn, (0, 0, 0, 2), expand=False)]
    return list(_records(header, rows, width))


# ---------- problems, questions and menus: all on stderr ----------


def _problems(stream: Any) -> Console:
    """The console a problem is printed on: the newest bar's while one is shown, so the line
    lands above the bar and the bar stays whole."""
    if _shown_bars:
        return _shown_bars[-1].console
    return _console(stream, look._width(stream))


def problem(stream: Any, label: str, sentence: str, nexts: Sequence[str]) -> None:
    """``error:`` or ``note:`` in its colour, the sentence as it is on the same line, and each
    command to run next under it. No line is wrapped."""
    console = _problems(stream)
    console.print(Text.assemble((label, _LABEL[label]), " " + _text(stream, sentence)),
                  soft_wrap=True)
    for command in nexts:
        console.print(Text.assemble("  ", ("next:", "dim"), " ",
                                    (_text(stream, command), "bold")), soft_wrap=True)


def question(stream: Any, lines: Sequence[str], bracket: str) -> None:
    """A prompt: the question bold, its bracketed default dim, the cursor left after it."""
    console = _console(stream, look._width(stream))
    text = Text()
    for number, line in enumerate(lines):
        line = _text(stream, line)
        ends = number == len(lines) - 1 and line.endswith(bracket)
        asked = line[: len(line) - len(bracket)] if ends else line
        text.append(asked, style="bold")
        if ends:
            text.append(bracket, style="dim")
        text.append("\n" if number < len(lines) - 1 else " ")
    console.print(text, end="", soft_wrap=True)


def listing(stream: Any, lines: Sequence[str]) -> None:
    """A menu written out as text: the question bold, each numbered choice under it."""
    console = _console(stream, look._width(stream))
    for number, line in enumerate(lines):
        console.print(Text(_text(stream, line), style="bold" if number == 0 else ""),
                      soft_wrap=True)


def menu(asked: str, default: str, choices: Sequence[tuple[str, str]]) -> str:
    """A menu on stderr, moved with the arrow keys and answered with Enter, opening on
    ``default``. ``choices`` are pairs: a choice as it is shown, and as it is returned. Raises
    ``ImportError`` where questionary cannot be imported, and ``KeyboardInterrupt`` on Ctrl-C."""
    import questionary
    from prompt_toolkit.output import ColorDepth, create_output

    # questionary colours its mark, the answer and the choice the pointer is on. None of those
    # colours has a meaning here, so each is set back to the terminal's own text colour.
    style = questionary.Style([
        ("qmark", "fg:default bold"), ("question", "fg:default bold"),
        ("answer", "fg:default nobold"), ("pointer", "fg:default bold"),
        ("highlighted", "fg:default bold"), ("selected", "fg:default bg:default noreverse"),
        ("instruction", "fg:default"), ("text", "fg:default"), ("disabled", "fg:default"),
    ])
    made = [questionary.Choice(title=shown, value=value) for shown, value in choices]
    opens_on = next(choice for choice in made if choice.value == default)
    answer = questionary.select(
        asked, choices=made, default=opens_on, qmark="", style=style,
        instruction="(arrow keys, then Enter)", output=create_output(stdout=sys.stderr),
        color_depth=ColorDepth.DEPTH_4_BIT,
    ).unsafe_ask()
    return str(answer)


# ---------- progress ----------


class Bar:
    """The progress of work as one line on stderr: the label, a bar and the count. It is redrawn
    while the work runs and removed when :meth:`stop` is called, so nothing of it stays on
    screen. The bar is the terminal's own text colour, dim where the work is not yet done: a bar
    is not a meaning, and takes no colour of one."""

    def __init__(self, stream: Any, label: str, total: int, width: int) -> None:
        self._bars = Bars(
            TextColumn("  {task.description}", markup=False),
            BarColumn(bar_width=30, style="dim", complete_style="none", finished_style="none",
                      pulse_style="dim"),
            TextColumn("{task.completed:,.0f}/{task.total:,.0f}", markup=False),
            console=_console(stream, width), transient=True, refresh_per_second=8,
            redirect_stdout=False, redirect_stderr=False,
        )
        self._task: TaskID = self._bars.add_task(_text(stream, label), total=total)

    def start(self) -> None:
        self._bars.start()
        _shown_bars.append(self._bars)

    def advance(self, by: int) -> None:
        self._bars.advance(self._task, by)

    def stop(self) -> None:
        if self._bars in _shown_bars:
            _shown_bars.remove(self._bars)
        self._bars.stop()
