"""Plain wraps, piped does not; commands are never broken; over-wide tables fold.

Invariants pinned here (Break — Plan, the look layer):
- BK12.6   On a terminal, plain wraps long lines at the terminal's width with a hanging indent and never inside
           a question's bracketed default; piped, every fact stays on one line; a command printed for the user
           to copy is never hard-wrapped in either rendering.
- BK12.10  Over-wide tables fold, moving a unit every cell repeats into the header, with nothing dropped.

Nothing here pins where a line breaks or how wide a column is. The tests ask whether a line passes the width,
whether the words are still there in their order, and whether what must stay whole did.

Left to its ruling: whether plain's verdict line itself wraps on a terminal.
"""

from __future__ import annotations

import re
import shlex

import pytest

from tests.look_support import (
    ELLIPSIS,
    Streams,
    cells,
    pretty_env,
    run_body,
    split_words,
    strip,
    words_of,
)

LONG = ("this value goes on and on with a great many short words in it so that no line of a narrow terminal "
        "could ever hold all of it at once and it has to be wrapped somewhere along the way")
COMMAND = "poisson-break hunt --name refund-agent-1 --settings path/to/settings/break.toml --cases path/to/cases.jsonl --max-runs 400"


def narrow(columns: int = 40) -> Streams:
    return Streams(out="pty", err="pty", columns=columns)


def _rows_body() -> str:
    return f'show(look.Result("ok", "fine", detail=(look.Row("target", {LONG!r}),)))'


def _line_body() -> str:
    return f'show(look.Result("ok", "fine", detail=(look.Line({LONG!r}),)))'


@pytest.mark.parametrize("body", [_rows_body(), _line_body()], ids=["row", "line"])
@pytest.mark.parametrize("columns", [40, 61, 90])
def test_plain_on_a_terminal_keeps_each_line_within_its_width(body: str, columns: int) -> None:
    ran = run_body(body, ["--plain"], streams=narrow(columns))
    assert ran.exit == 0, ran
    assert "\x1b" not in ran.out
    assert len(ran.out.splitlines()) > 2, f"it was not wrapped: {ran.out!r}"
    assert all(len(text) <= columns for text in ran.out.splitlines()), ran.out


@pytest.mark.parametrize("body", [_rows_body(), _line_body()], ids=["row", "line"])
def test_plain_on_a_terminal_uses_the_terminals_own_width(body: str) -> None:
    """Each width is the terminal's, read from the terminal: wider terminals hold longer lines."""
    narrowest = run_body(body, ["--plain"], streams=narrow(40))
    wider = run_body(body, ["--plain"], streams=narrow(90))
    assert max(len(text) for text in wider.out.splitlines()) > 40, wider.out
    assert len(wider.out.splitlines()) < len(narrowest.out.splitlines())


@pytest.mark.parametrize("body", [_rows_body(), _line_body()], ids=["row", "line"])
def test_a_wrapped_line_loses_no_word_and_breaks_no_word(body: str) -> None:
    piped = run_body(body)
    wrapped = run_body(body, ["--plain"], streams=narrow(40))
    assert piped.exit == wrapped.exit == 0, (piped, wrapped)
    assert split_words(wrapped.out) == split_words(piped.out)


@pytest.mark.parametrize("body", [_rows_body(), _line_body()], ids=["row", "line"])
def test_a_wrapped_line_hangs(body: str) -> None:
    """What wraps is indented deeper than the line it wraps, so it reads as one fact."""
    ran = run_body(body, ["--plain"], streams=narrow(40))
    lines = ran.out.splitlines()[1:]
    first = len(lines[0]) - len(lines[0].lstrip(" "))
    assert len(lines) > 1
    for text in lines[1:]:
        assert len(text) - len(text.lstrip(" ")) > first, ran.out


def test_a_word_longer_than_the_terminal_is_left_whole() -> None:
    word = "x" * 60
    ran = run_body(f'show(look.Result("ok", "fine", detail=(look.Row("label", "a b {word} c d"),)))', ["--plain"],
                   streams=narrow(40))
    assert ran.exit == 0, ran
    assert word in ran.out


def test_a_short_line_is_not_touched_on_a_terminal() -> None:
    piped = run_body('show(look.Result("ok", "fine", detail=(look.Row("label", "a short value"),)))')
    terminal = run_body('show(look.Result("ok", "fine", detail=(look.Row("label", "a short value"),)))', ["--plain"],
                        streams=narrow(80))
    assert piped.exit == terminal.exit == 0, (piped, terminal)
    assert terminal.out == piped.out


# ---------- piped ----------


@pytest.mark.parametrize("body", [_rows_body(), _line_body()], ids=["row", "line"])
def test_piped_every_fact_stays_on_one_line(body: str) -> None:
    ran = run_body(body)
    assert ran.exit == 0, ran
    lines = ran.out.splitlines()
    assert len(lines) == 2, ran.out
    assert LONG in lines[1]


def test_piped_a_table_row_stays_on_one_line_however_wide() -> None:
    cell = "c" * 300
    ran = run_body(f'show(look.Result("ok", "fine", detail=(look.Table(("a", "b"), (("first", {cell!r}),)),)))')
    assert ran.exit == 0, ran
    assert any("first" in text and cell in text for text in ran.out.splitlines()), ran.out


def test_a_columns_setting_does_not_wrap_a_pipe() -> None:
    ran = run_body(_rows_body(), env=pretty_env(COLUMNS="40"))
    assert len(ran.out.splitlines()) == 2, ran.out


# ---------- commands ----------


@pytest.mark.parametrize("words", [[], ["--plain"]], ids=["pretty", "plain"])
@pytest.mark.parametrize("columns", [30, 70])
def test_a_next_command_is_never_hard_wrapped(words: list[str], columns: int) -> None:
    ran = run_body(f'show(look.Result("ok", "fine", nexts=(look.command(*{COMMAND.split()!r}),)))', words,
                   streams=narrow(columns))
    assert ran.exit == 0, ran
    assert any(COMMAND in text for text in strip(ran.out).splitlines()), repr(ran.out)


@pytest.mark.parametrize("words", [[], ["--plain"]], ids=["pretty", "plain"])
def test_a_command_in_a_row_is_never_hard_wrapped(words: list[str]) -> None:
    ran = run_body(f'show(look.Result("ok", "fine", detail=(look.Row("again", look.command(*{COMMAND.split()!r})),)))',
                   words, streams=narrow(30))
    assert ran.exit == 0, ran
    assert any(COMMAND in text for text in strip(ran.out).splitlines()), repr(ran.out)


@pytest.mark.parametrize("words", [[], ["--plain"]], ids=["pretty", "plain"])
def test_a_command_under_an_error_is_never_hard_wrapped(words: list[str]) -> None:
    ran = run_body(f'look.error("a problem", [look.command(*{COMMAND.split()!r})])', words, streams=narrow(30))
    assert ran.exit == 0, ran
    assert f"  next: {COMMAND}" in strip(ran.err).splitlines(), repr(ran.err)


def test_a_command_with_spaces_in_its_words_stays_whole_and_reads_back() -> None:
    ran = run_body('name = look.word("a name with spaces in it")\n'
                   'show(look.Result("ok", "fine", nexts=(look.command("tool", "--name", name, "--flag"),)))',
                   ["--plain"], streams=narrow(20))
    said = [text.split("next:", 1)[1] for text in ran.out.splitlines() if "next:" in text]
    assert len(said) == 1, ran.out
    assert shlex.split(said[0]) == ["tool", "--name", "a name with spaces in it", "--flag"]


# ---------- a question's bracketed default ----------


def _asked(columns: int, words: list[str] | None = None) -> str:
    default = "my_app.agents:refund agent with spaces"
    question = "where is the agent you want to hunt, as a module path and a name"
    ran = run_body(f'print(repr(look.ask({question!r}, {default!r})))', words or ["--plain"],
                   streams=Streams(out="pty", err="pty", stdin="pty", columns=columns, keys=(b"\r",)))
    assert ran.exit == 0, ran
    assert repr(default) in ran.out
    return ran.err


@pytest.mark.parametrize("columns", [20, 30, 44, 50, 60])
def test_plain_never_wraps_inside_a_bracketed_default(columns: int) -> None:
    default = "[my_app.agents:refund agent with spaces]"
    err = _asked(columns)
    assert any(default in text for text in strip(err).splitlines()), repr(err)


def test_plain_still_wraps_the_question_before_the_bracket() -> None:
    err = _asked(30)
    assert len([text for text in strip(err).splitlines() if text.strip()]) > 2, repr(err)
    for text in strip(err).splitlines():
        if "[" not in text and text.strip():
            assert len(text) <= 30, repr(err)


# ---------- over-wide tables ----------

UNIT = "ms"
HEADER = ("t1", "t2", "t3", "t4", "t5", "t6")
CELLS = [[f"1,23{i},56{j} {UNIT}" for j in range(6)] for i in range(3)]
UNIT_TABLE = (HEADER, tuple(tuple(row) for row in CELLS))
WIDE = 76
"""Twelve characters a cell, six of them: too wide for this terminal under any padding with its unit in every cell,
and narrow enough once the unit has moved, even with a border round every cell."""


def _table_body(table: tuple) -> str:
    return f'show(look.Result("ok", "fine", detail=(look.Table({table[0]!r}, {table[1]!r}),)))'


def _numbers(rows: tuple) -> list[str]:
    return [cell.split()[0] for row in rows for cell in row]


def test_a_table_too_wide_moves_its_repeated_unit_into_the_header() -> None:
    ran = run_body(_table_body(UNIT_TABLE), streams=narrow(WIDE))
    assert ran.exit == 0, ran
    text = strip(ran.out)
    assert "\x1b[" in ran.out
    assert not re.search(rf"\d {UNIT}\b", text), f"a cell still repeats its unit:\n{text}"
    header = next(row for row in text.splitlines() if "t1" in row)
    for name in HEADER:
        assert re.search(rf"\b{name}\b", header), header
    assert len(re.findall(rf"\b{UNIT}\b", header)) == len(HEADER), f"the unit is not in the header:\n{text}"
    assert len(re.findall(rf"\b{UNIT}\b", text)) == len(HEADER), f"the unit is elsewhere too:\n{text}"


def test_a_folded_table_fits_the_terminal() -> None:
    ran = run_body(_table_body(UNIT_TABLE), streams=narrow(WIDE))
    assert ran.exit == 0, ran
    assert all(len(row) <= WIDE for row in strip(ran.out).splitlines()), strip(ran.out)


def test_a_folded_table_drops_nothing() -> None:
    ran = run_body(_table_body(UNIT_TABLE), streams=narrow(WIDE))
    text = strip(ran.out)
    for number in _numbers(UNIT_TABLE[1]):
        assert number in text, f"{number} was dropped:\n{text}"
    assert not ELLIPSIS.search(text), text


def test_a_folded_table_keeps_its_rows_in_order() -> None:
    ran = run_body(_table_body(UNIT_TABLE), streams=narrow(WIDE))
    numbers = re.findall(r"1,23(\d),560", strip(ran.out))
    assert numbers == ["0", "1", "2"], strip(ran.out)


def test_a_table_that_fits_keeps_its_units_in_its_cells() -> None:
    ran = run_body(_table_body(UNIT_TABLE), streams=narrow(160))
    text = strip(ran.out)
    assert re.search(rf"1,230,560 {UNIT}", text), text


def test_a_column_of_mixed_units_keeps_them() -> None:
    """A unit moves only when every cell repeats it: moving `ms` over a `s` cell would change a number."""
    rows = (
        ("alpha", "1,230,560 ms", "7,777,777,777 ms"),
        ("beta", "1,230,561 s", "8,888,888,888 ms"),
    )
    long_rows = tuple((*row, *[f"{i},000,000,000 ms" for i in range(4)]) for row in rows)
    header = ("name", "mixed", "same", "a", "b", "c", "d")
    ran = run_body(_table_body((header, long_rows)), streams=narrow(70))
    assert ran.exit == 0, ran
    text = strip(ran.out)
    assert re.search(r"1,230,561\s+s\b", text), f"the odd unit is lost:\n{text}"
    assert re.search(r"1,230,560\s+ms\b", text), f"a mixed column lost its unit:\n{text}"


def test_a_column_with_no_unit_stays_as_it_is_when_a_table_folds() -> None:
    rows = tuple((f"name-{i}", *[f"{i},000,000,00{j} ms" for j in range(5)]) for i in range(3))
    ran = run_body(_table_body((("name", "a", "b", "c", "d", "e"), rows)), streams=narrow(70))
    text = strip(ran.out)
    for i in range(3):
        assert f"name-{i}" in text, text
    assert not re.search(r"name \(", text), text


def test_a_table_still_too_wide_after_moving_its_unit_drops_nothing() -> None:
    """No width is too narrow to lose a fact: however it folds, every word is there, none cut."""
    rows = (("tool:check_policy#1=planted_instruction", "followed_plant", "0.618", "no more words"),
            ("tool:issue_refund#1=lost_reply", "duplicate_write", "0.582", "another few words"))
    ran = run_body(_table_body((("condition", "kind", "rate", "said"), rows)), streams=narrow(30))
    assert ran.exit == 0, ran
    text = strip(ran.out)
    for row in rows:
        for cell in row:
            assert all(word in words_of(text) for word in words_of(cell)), f"{cell}:\n{text}"
    for name in ("condition", "kind", "rate", "said"):
        assert name in words_of(text), f"the column {name} lost its name:\n{text}"
    assert not ELLIPSIS.search(text), text


def test_plain_never_moves_a_unit() -> None:
    """Piped, a cell is as it was written."""
    ran = run_body(_table_body(UNIT_TABLE))
    assert ran.exit == 0, ran
    assert ran.out.count(f" {UNIT}") == 18, ran.out


def test_a_folded_tables_numbers_are_not_coloured() -> None:
    ran = run_body(_table_body(UNIT_TABLE), streams=narrow(WIDE))
    assert ran.exit == 0, ran
    assert all(cell.fg is None for cell in cells(ran.out) if cell.char.isdigit()), repr(ran.out)
