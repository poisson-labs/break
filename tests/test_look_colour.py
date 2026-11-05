"""Four colours and no others.

Invariant pinned here (Break — Plan, the look layer):
- BK12.3  Green for done words, yellow for stopped-short words and `note:`, red for `error:` and failed checks,
          dim for secondary text; a neutral verdict word is bold with no colour; a number is never coloured;
          only the terminal's 16 named colours, bold and dim appear.

Each test reads a real pseudo-terminal's bytes and walks the escape sequences to learn each character's colour,
so the tests do not care how a build spells them. Normal and bright count as the same colour: the user's theme
decides the shade.

The words the standard names, then Break's own as ruled: `found` is green because the command did what was asked, and
`failed` is red because it reports a failed run. A word on no list is bold with no colour.
"""

from __future__ import annotations

import pytest

from tests.look_results import RESULTS
from tests.look_support import (
    ALLOWED_SGR,
    GREEN,
    MEANINGS,
    RED,
    SGR,
    TERMINALS,
    YELLOW,
    Streams,
    cells,
    cells_of,
    run_body,
    run_result,
    sgr_codes,
    strip,
)

SENTENCE = "12 of 40 runs for $1.00 at 0.150 in 1 min 40 s"


def _verdict(word: str) -> str:
    ran = run_body(f'show(look.Result({word!r}, {SENTENCE!r}))', streams=TERMINALS)
    assert ran.exit == 0, ran
    return ran.out


@pytest.mark.parametrize("word", ["ok", "done", "passed"])
def test_a_word_for_done_is_green(word: str) -> None:
    for cell in cells_of(_verdict(word), word):
        assert cell.fg in GREEN, (word, cell)


@pytest.mark.parametrize("word", ["stopped", "refused", "too small to tell"])
def test_a_word_for_stopped_short_is_yellow(word: str) -> None:
    for cell in cells_of(_verdict(word), word):
        assert cell.fg in YELLOW, (word, cell)


@pytest.mark.parametrize("word", ["not ready", "fail"])
def test_a_word_for_a_failed_check_is_red(word: str) -> None:
    for cell in cells_of(_verdict(word), word):
        assert cell.fg in RED, (word, cell)


@pytest.mark.parametrize("word", ["plan", "different"])
def test_a_word_neither_good_nor_bad_is_bold_with_no_colour(word: str) -> None:
    for cell in cells_of(_verdict(word), word):
        assert cell.fg is None and cell.bold, (word, cell)


@pytest.mark.parametrize("word", ["ok", "stopped", "not ready", "plan"])
def test_the_sentence_after_a_verdict_is_not_coloured(word: str) -> None:
    for cell in cells_of(_verdict(word), SENTENCE):
        assert cell.fg is None, (word, cell)


def test_the_plan_result_type_is_bold_with_no_colour() -> None:
    ran = run_body('show(look.Plan("a hunt", estimate="about 12", source="a table", detail=()))', streams=TERMINALS)
    assert ran.exit == 0, ran
    for cell in cells_of(ran.out, "plan"):
        assert cell.fg is None and cell.bold, cell


def test_error_is_red_and_its_numbers_are_not_coloured() -> None:
    ran = run_body('look.error("3 of 12 tools failed at 0.150", ["tool next 4"])', streams=TERMINALS)
    assert ran.exit == 0, ran
    for cell in cells_of(ran.err, "error"):
        assert cell.fg in RED, cell
    assert all(cell.fg is None for cell in cells(ran.err) if cell.char.isdigit()), repr(ran.err)


def test_note_is_yellow_and_its_numbers_are_not_coloured() -> None:
    ran = run_body('look.note("3 of 12 tools at 0.150")', streams=TERMINALS)
    assert ran.exit == 0, ran
    for cell in cells_of(ran.err, "note"):
        assert cell.fg in YELLOW, cell
    assert all(cell.fg is None for cell in cells(ran.err) if cell.char.isdigit()), repr(ran.err)


def test_a_refusal_through_the_runner_is_red() -> None:
    ran = run_body('raise look.Refused("no such run 3")', streams=TERMINALS)
    assert ran.exit == 1, ran
    for cell in cells_of(ran.err, "error"):
        assert cell.fg in RED, cell


def test_the_same_word_in_a_table_keeps_the_rule_for_numbers() -> None:
    """A verdict word in a row of a table may be coloured; the rate beside it never is."""
    ran = run_result("confirmed", streams=Streams(out="pty", err="pty", columns=160))
    assert ran.exit == 0, ran
    assert all(cell.fg is None for cell in cells(ran.out) if cell.char.isdigit()), repr(ran.out)


@pytest.mark.parametrize("name", list(RESULTS))
def test_no_number_in_any_result_is_coloured(name: str) -> None:
    ran = run_result(name, streams=Streams(out="pty", err="pty", columns=160))
    assert ran.exit == 0, ran
    wrong = [cell for cell in cells(ran.out) if cell.char.isdigit() and cell.fg is not None]
    assert not wrong, repr(ran.out)


@pytest.mark.parametrize("name", list(RESULTS))
def test_only_named_colours_bold_and_dim_appear_in_any_result(name: str) -> None:
    ran = run_result(name, streams=Streams(out="pty", err="pty", columns=160))
    assert ran.exit == 0, ran
    assert sgr_codes(ran.out) <= ALLOWED_SGR, repr(ran.out)
    assert sgr_codes(ran.out), "no style at all: this is not the pretty rendering"


@pytest.mark.parametrize("name", list(RESULTS))
def test_only_the_three_meanings_colour_anything(name: str) -> None:
    """Sixteen names may be used, for three meanings: nothing is drawn in blue, cyan, magenta, white or black."""
    ran = run_result(name, streams=Streams(out="pty", err="pty", columns=160))
    assert ran.exit == 0, ran
    colours = {cell.fg for cell in cells(ran.out) if cell.fg is not None}
    assert colours <= MEANINGS, repr(ran.out)


@pytest.mark.parametrize("name", list(RESULTS))
def test_stdout_holds_styles_and_nothing_that_moves_the_cursor(name: str) -> None:
    """What stays on stdout is the result: a live display belongs on stderr."""
    ran = run_result(name, streams=TERMINALS)
    assert ran.exit == 0, ran
    assert "\x1b" not in SGR.sub("", ran.out), repr(ran.out)


def test_problems_hold_only_named_colours_bold_and_dim() -> None:
    ran = run_body('look.note("a warning")\nlook.error("a problem", ["tool again"])', streams=TERMINALS)
    assert ran.exit == 0, ran
    assert sgr_codes(ran.err) and sgr_codes(ran.err) <= ALLOWED_SGR, repr(ran.err)
    assert strip(ran.err) == "note: a warning\nerror: a problem\n  next: tool again\n"


def test_secondary_text_is_dim_and_never_coloured() -> None:
    """A `next:` line and a detail's label are secondary: whichever a build dims, it uses dim, not a colour."""
    ran = run_body('show(look.Result("ok", "fine", detail=(look.Row("label", "value"),), nexts=("tool again",)))',
                   streams=TERMINALS)
    assert ran.exit == 0, ran
    for text in ("label", "value", "next", "tool again"):
        for cell in cells_of(ran.out, text):
            assert cell.fg is None, (text, cell)
    assert any(cell.dim for cell in cells(ran.out)), "nothing is dim: secondary text must be"


# ---------- Break's own words, as ruled ----------


@pytest.mark.parametrize("word", ["wrote", "ready", "found", "confirmed", "rechecked", "fails less"])
def test_breaks_own_word_for_done_is_green(word: str) -> None:
    for cell in cells_of(_verdict(word), word):
        assert cell.fg in GREEN, (word, cell)


@pytest.mark.parametrize("word", ["nothing found", "nothing confirmed", "not confirmed", "no significant difference", "did not fail"])
def test_breaks_own_word_for_stopped_short_is_yellow(word: str) -> None:
    for cell in cells_of(_verdict(word), word):
        assert cell.fg in YELLOW, (word, cell)


@pytest.mark.parametrize("word", ["failed", "fails more"])
def test_breaks_own_word_for_a_failure_is_red(word: str) -> None:
    for cell in cells_of(_verdict(word), word):
        assert cell.fg in RED, (word, cell)


@pytest.mark.parametrize("word", ["listed nowhere", "unheard"])
def test_a_word_on_no_list_is_bold_with_no_colour(word: str) -> None:
    for cell in cells_of(_verdict(word), word):
        assert cell.fg is None and cell.bold, (word, cell)
