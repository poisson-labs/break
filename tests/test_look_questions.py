"""Questions and progress stay on stderr.

Invariant pinned here (Break — Plan, the look layer):
- BK12.7  Questions and progress stay on stderr, a live display is removed when the work ends, a non-terminal
          stdin without `--yes` refuses a question, and `--yes` answers it.

And the rule these rest on: a question that spends money asks with `[y/N]`, and a stdin that is not a terminal,
without `--yes`, refuses. `ask` is on a terminal driven by key presses, through a pseudo-terminal of its own, in
both renderings; the menus the settings dialogue asks are questionary's in the pretty rendering.

Left to their rulings: what other answers than `y`, `n` and an empty line do, how a plain menu is answered, and what
a stage's finished line leaves behind.
"""

from __future__ import annotations

import pytest

from tests.look_support import (
    ALLOWED_SGR,
    MEANINGS,
    TERMINALS,
    Streams,
    cells,
    pretty_env,
    run_body,
    screen,
    sgr_codes,
    strip,
)

MODES = [pytest.param([], id="pretty"), pytest.param(["--plain"], id="plain")]
ASK_YES_NO = 'print("answer", repr(look.ask("start?", False)))'
ASK_LINE = 'print("answer", repr(look.ask("how many runs?", "400")))'
MENU = 'print("answer", repr(look.ask("built with?", "langgraph", choices=("openai-agents", "langgraph", "crewai"))))'


def on_terminal(*keys: bytes, columns: int = 100) -> Streams:
    return Streams(out="pty", err="pty", stdin="pty", columns=columns, keys=keys)


# ---------- the question ----------


@pytest.mark.parametrize("words", MODES)
@pytest.mark.parametrize("keys, wanted", [((b"y\r",), True), ((b"n\r",), False), ((b"\r",), False)],
                         ids=["y", "n", "enter"])
def test_a_yes_no_question_defaults_to_no(words: list[str], keys: tuple[bytes, ...], wanted: bool) -> None:
    ran = run_body(ASK_YES_NO, words, streams=on_terminal(*keys))
    assert ran.exit == 0, ran
    assert f"answer {wanted!r}" in strip(ran.out), ran


@pytest.mark.parametrize("words", MODES)
def test_a_yes_no_question_shows_its_choice_on_stderr(words: list[str]) -> None:
    ran = run_body(ASK_YES_NO, words, streams=on_terminal(b"\r"))
    assert "[y/N]" in strip(ran.err), repr(ran.err)
    assert "start?" in strip(ran.err)
    assert "start?" not in strip(ran.out) and "[y/N]" not in strip(ran.out), repr(ran.out)
    assert sgr_codes(ran.err) <= ALLOWED_SGR | {7, 27}, repr(ran.err)


@pytest.mark.parametrize("words", MODES)
def test_a_line_question_takes_what_is_typed(words: list[str]) -> None:
    ran = run_body(ASK_LINE, words, streams=on_terminal(b"250\r"))
    assert "answer '250'" in strip(ran.out), ran


@pytest.mark.parametrize("words", MODES)
def test_a_line_question_defaults_to_its_default(words: list[str]) -> None:
    ran = run_body(ASK_LINE, words, streams=on_terminal(b"\r"))
    assert "answer '400'" in strip(ran.out), ran
    assert "[400]" in strip(ran.err), repr(ran.err)
    assert "how many runs?" not in strip(ran.out)


def test_a_question_asked_with_stdout_in_a_file_leaves_the_file_as_the_result(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "held.txt"
    ran = run_body('look.ask("how many runs?", "400")\nshow(look_results.RESULTS["wrote"]())',
                   streams=Streams(out=path, err="pty", stdin="pty", keys=(b"\r",)))
    assert ran.exit == 0, ran
    assert path.read_text(encoding="utf-8").startswith("wrote  ")


@pytest.mark.parametrize("words", MODES)
def test_what_is_asked_is_printed_as_it_is(words: list[str]) -> None:
    ran = run_body('look.ask("is [red]it[/red] :warning: fine?", False)', words, streams=on_terminal(b"\r"))
    assert ran.exit == 0, ran
    assert "is [red]it[/red] :warning: fine?" in strip(ran.err), repr(ran.err)


# ---------- no terminal to answer on ----------


@pytest.mark.parametrize("stdin", ["null", "y\n", ""], ids=["no-stdin", "a-piped-y", "empty"])
@pytest.mark.parametrize("ask", [ASK_YES_NO, ASK_LINE, MENU], ids=["yes-no", "line", "menu"])
def test_a_stdin_that_is_no_terminal_refuses_the_question(stdin: str, ask: str) -> None:
    ran = run_body(ask, streams=Streams(stdin=stdin))
    assert ran.exit == 1, ran
    assert "answer" not in ran.out, ran
    assert ran.err.startswith("error: "), ran
    assert "Traceback" not in ran.err


@pytest.mark.parametrize("ask, wanted", [(ASK_YES_NO, "True"), (ASK_LINE, "'400'"), (MENU, "'langgraph'")],
                         ids=["yes-no", "line", "menu"])
@pytest.mark.parametrize("stdin", ["null", "n\n"], ids=["no-stdin", "a-piped-n"])
def test_yes_answers_the_question_without_a_terminal(ask: str, wanted: str, stdin: str) -> None:
    ran = run_body(ask, ["--yes"], streams=Streams(stdin=stdin))
    assert ran.exit == 0, ran
    assert f"answer {wanted}" in ran.out, ran
    assert "[y/N]" not in ran.err and "start?" not in ran.err, ran


def test_yes_skips_the_question_on_a_terminal_too() -> None:
    ran = run_body(ASK_YES_NO, ["--yes"], streams=on_terminal())
    assert ran.exit == 0, ran
    assert "answer True" in strip(ran.out)
    assert "[y/N]" not in strip(ran.err)


@pytest.mark.parametrize("word", ["--yes-please", "yes", "-y"])
def test_only_the_flag_itself_answers(word: str) -> None:
    ran = run_body(ASK_YES_NO, [word], streams=Streams(stdin="null"))
    assert ran.exit == 1, ran
    assert ran.err.startswith("error: "), ran


def test_a_question_refused_leaves_the_plan_on_screen() -> None:
    """The plan is printed, then the question refuses: rule 7's order."""
    ran = run_body('show(look_results.RESULTS["plan-hunt"]())\nlook.ask("start?", False)\nlook.out("spent\\n")')
    assert ran.exit == 1, ran
    assert ran.out.startswith("plan  ")
    assert "spent" not in ran.out


# ---------- menus ----------


def test_a_menu_is_questionarys_in_pretty_and_takes_the_arrow_keys() -> None:
    ran = run_body(MENU + '\nprint("loaded", "questionary" in sys.modules)', streams=on_terminal(b"\x1b[B", b"\r"))
    assert ran.exit == 0, ran
    assert "answer 'crewai'" in strip(ran.out), ran
    assert "loaded True" in strip(ran.out)


def test_a_menu_opens_on_its_default_in_pretty() -> None:
    ran = run_body(MENU, streams=on_terminal(b"\r"))
    assert ran.exit == 0, ran
    assert "answer 'langgraph'" in strip(ran.out), ran


def test_a_menu_stays_on_stderr_in_pretty() -> None:
    ran = run_body(MENU, streams=on_terminal(b"\r"))
    assert "openai-agents" in strip(ran.err), repr(ran.err)
    assert "openai-agents" not in strip(ran.out), repr(ran.out)
    assert "built with?" not in strip(ran.out), repr(ran.out)


def test_a_menu_opens_on_its_default_in_plain_and_loads_nothing() -> None:
    ran = run_body(MENU + '\nprint("loaded", "questionary" in sys.modules)', ["--plain"], streams=on_terminal(b"\r"))
    assert ran.exit == 0, ran
    assert "answer 'langgraph'" in ran.out, ran
    assert "loaded False" in ran.out
    assert "\x1b" not in ran.err
    for choice in ("openai-agents", "langgraph", "crewai"):
        assert choice in ran.err, ran
    assert "openai-agents" not in ran.out


def test_a_menu_draws_only_named_colours_bold_and_dim() -> None:
    ran = run_body(MENU, streams=on_terminal(b"\r"))
    assert ran.exit == 0, ran
    assert sgr_codes(ran.err) <= ALLOWED_SGR | {7, 27}, repr(ran.err)


# ---------- progress ----------

WORK = """\
import time
with look.Progress("searching the conditions", 5) as progress:
    for number in range(5):
        time.sleep(0.15)
        progress.advance()
show(look_results.RESULTS["wrote"]())
"""


@pytest.mark.parametrize("words, streams", [([], Streams()), ([], TERMINALS), (["--plain"], TERMINALS)],
                         ids=["piped", "pretty", "plain-terminal"])
def test_progress_stays_off_stdout(words: list[str], streams: Streams) -> None:
    ran = run_body(WORK, words, streams=streams)
    assert ran.exit == 0, ran
    assert "searching" not in strip(ran.out), repr(ran.out)
    assert strip(ran.out).startswith("wrote  "), repr(ran.out)


def test_progress_is_shown_while_the_work_runs() -> None:
    """A display that never appears would pass every test of being removed."""
    ran = run_body(WORK, streams=TERMINALS)
    assert "searching the conditions" in ran.err, repr(ran.err)


@pytest.mark.parametrize("words", MODES)
def test_a_live_display_is_gone_from_the_screen_when_the_work_ends(words: list[str]) -> None:
    ran = run_body(WORK, words, streams=TERMINALS)
    assert ran.exit == 0, ran
    shown, hidden = screen(ran.err)
    assert not any(text.strip() for text in shown), f"left on screen: {shown}"
    assert not hidden, "the cursor was left hidden"


@pytest.mark.parametrize("words", MODES)
def test_on_one_terminal_what_remains_is_the_result(words: list[str]) -> None:
    """stdout and stderr on the same terminal, as a user has them."""
    ran = run_body(WORK, words, streams=Streams(together=True))
    assert ran.exit == 0, ran
    shown, hidden = screen(ran.out)
    text = "\n".join(line for line in shown if line.strip())
    assert text.startswith("wrote  "), text
    assert "searching" not in text, text
    assert not hidden


@pytest.mark.parametrize("words", MODES)
def test_a_live_display_is_removed_when_the_work_fails_too(words: list[str], tmp_path) -> None:  # type: ignore[no-untyped-def]
    body = ('with look.Progress("searching the conditions", 5) as progress:\n'
            '    progress.advance()\n'
            '    raise look.Refused("the cap would be passed")\n')
    ran = run_body(body, words, streams=Streams(together=True), env=pretty_env(HOME=str(tmp_path)))
    assert ran.exit == 1, ran
    shown, hidden = screen(ran.out)
    text = "\n".join(line for line in shown if line.strip())
    assert text == "error: the cap would be passed", text
    assert not hidden


def test_progress_draws_only_the_meanings_bold_and_dim() -> None:
    """A bar is not a meaning: Rich's own bar is magenta and blue until it is told otherwise."""
    ran = run_body(WORK, streams=TERMINALS)
    assert ran.exit == 0, ran
    assert sgr_codes(ran.err) <= ALLOWED_SGR, repr(ran.err)
    assert {cell.fg for cell in cells(ran.err) if cell.fg is not None} <= MEANINGS, repr(ran.err)


def test_progress_takes_a_total_of_nothing() -> None:
    ran = run_body('with look.Progress("nothing to do", 0) as progress:\n    pass', streams=TERMINALS)
    assert ran.exit == 0, ran
    assert "Traceback" not in ran.err


def test_progress_that_goes_past_its_total_is_no_crash() -> None:
    ran = run_body('with look.Progress("more than promised", 2) as progress:\n    progress.advance(5)', streams=TERMINALS)
    assert ran.exit == 0, ran
    assert "error:" not in strip(ran.err)
