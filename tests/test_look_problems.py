"""Problems go to stderr, one line each, and the exit codes.

Invariants pinned here (Break — Plan, the look layer):
- BK12.5  Problems go to stderr, one line each: `error:` with optional `next:` lines indented two spaces, or
          `note:`; never a traceback, a Python repr, a hash that another command takes, or a module id; an
          unexpected failure is one line and a log path.

And the rules of the shared look a problem rests on: the six exit codes, `Refused`, `Usage` and `Stopped`,
Ctrl-C as a stop, and `--json`'s errors staying on stderr in text.

What each problem says is the caller's sentence, so no test here reads a refusal's words beyond the shape the
standard writes. The one line whose words the standard fixes is the unexpected failure's, and it is pinned as
written there.
"""

from __future__ import annotations

import re
import select
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.look_support import (
    CODES,
    ESCAPE,
    PIPED,
    TERMINALS,
    Streams,
    launch,
    look,
    pretty_env,
    run_body,
    snippet,
    strict_json,
    strip,
)

BOTH = [pytest.param(PIPED, id="piped"), pytest.param(TERMINALS, id="terminal")]
FAILING = 'raise ValueError("raw library text (1, 2) \'quoted\'")'
LINE = re.compile(r"^error: an unexpected failure inside (?P<tool>\S+) \((?P<kind>\w+)\); the details are in (?P<path>\S.*)$")


def home_env(tmp_path: Path, **more: str | None) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return pretty_env(HOME=str(home), **more)


# ---------- the exit codes ----------


def test_exit_holds_the_six_codes() -> None:
    assert dict(look().EXIT) == CODES


@pytest.mark.parametrize("code", sorted(CODES.values()))
def test_a_body_that_returns_a_code_exits_with_it(code: int) -> None:
    ran = run_body(f"return {code}")
    assert ran.exit == code, ran
    assert "Traceback" not in ran.err, ran


def test_a_body_that_returns_nothing_exits_zero() -> None:
    assert run_body("pass").exit == 0


# ---------- error ----------


@pytest.mark.parametrize("streams", BOTH)
def test_an_error_is_one_line_and_its_commands_under_it(streams: Streams) -> None:
    ran = run_body('look.error("the tool has no stand-in", ["tool doctor", "tool init --force"])', streams=streams)
    assert ran.exit == 0, ran
    assert strip(ran.err) == "error: the tool has no stand-in\n  next: tool doctor\n  next: tool init --force\n"
    assert ran.out == ""


@pytest.mark.parametrize("streams", BOTH)
def test_an_error_needs_no_commands(streams: Streams) -> None:
    ran = run_body('look.error("the tool has no stand-in", [])', streams=streams)
    assert strip(ran.err) == "error: the tool has no stand-in\n"


@pytest.mark.parametrize("streams", BOTH)
def test_a_line_break_in_a_sentence_does_not_make_a_second_line(streams: Streams) -> None:
    """A path with a line break in it, or a library's two-line message, is still one line for the user."""
    ran = run_body(r'look.error("first part\nsecond part\r\nthird part", [])', streams=streams)
    text = strip(ran.err)
    assert len(text.splitlines()) == 1, repr(text)
    assert text.startswith("error: ")
    assert all(part in text for part in ("first part", "second part", "third part"))


@pytest.mark.parametrize("streams", BOTH)
def test_a_note_is_one_line_on_stderr(streams: Streams) -> None:
    ran = run_body('look.note("Break calls your tools for real")', streams=streams)
    assert ran.exit == 0, ran
    assert strip(ran.err) == "note: Break calls your tools for real\n"
    assert ran.out == ""


def test_a_note_with_a_line_break_is_one_line() -> None:
    ran = run_body(r'look.note("one\ntwo")')
    assert len(ran.err.splitlines()) == 1, repr(ran.err)


@pytest.mark.parametrize("columns", [30, 200])
def test_an_error_is_not_wrapped_on_any_terminal(columns: int) -> None:
    sentence = "a problem that goes on for well past the width of a narrow terminal and has more to say"
    ran = run_body(f'look.error({sentence!r}, [])', streams=Streams(out="pty", err="pty", columns=columns))
    assert strip(ran.err) == f"error: {sentence}\n"


@pytest.mark.parametrize("words", [[], ["--plain"]], ids=["pretty", "plain"])
def test_an_error_prints_a_value_as_it_is(words: list[str]) -> None:
    sentence = "no run named [red]a[/red] in :warning: 'x'"
    ran = run_body(f'look.error({sentence!r}, ["tool [bold]b[/bold]"])', words, streams=TERMINALS)
    assert strip(ran.err) == f"error: {sentence}\n  next: tool [bold]b[/bold]\n", repr(ran.err)


@pytest.mark.parametrize("words", [[], ["--plain"]], ids=["pretty", "plain"])
def test_an_escape_a_user_typed_acts_on_nothing_in_an_error(words: list[str]) -> None:
    ran = run_body(r'look.error("no run named \x1b[35mred\x07", [])', words, streams=TERMINALS)
    assert "\x1b[35m" not in ran.err and "\x07" not in ran.err, repr(ran.err)
    assert len(strip(ran.err).splitlines()) == 1


def test_pretty_on_stderr_alone_changes_only_the_style() -> None:
    plain = run_body('look.error("a b c", ["d e"])\nlook.note("f g")')
    pretty = run_body('look.error("a b c", ["d e"])\nlook.note("f g")', streams=TERMINALS)
    assert "\x1b[" in pretty.err
    assert strip(pretty.err) == plain.err


# ---------- the exceptions ----------


@pytest.mark.parametrize("streams", BOTH)
def test_refused_is_exit_1_and_its_lines_on_stderr(streams: Streams) -> None:
    ran = run_body('raise look.Refused("nothing was written", nexts=("tool doctor",))', streams=streams)
    assert ran.exit == CODES["refused"], ran
    assert strip(ran.err) == "error: nothing was written\n  next: tool doctor\n"
    assert ran.out == ""


@pytest.mark.parametrize("streams", BOTH)
def test_usage_is_exit_2_and_its_lines_on_stderr(streams: Streams) -> None:
    ran = run_body('raise look.Usage("no verb named hnut", nexts=("tool --help",))', streams=streams)
    assert ran.exit == CODES["usage"], ran
    assert strip(ran.err) == "error: no verb named hnut\n  next: tool --help\n"
    assert ran.out == ""


@pytest.mark.parametrize("name", ["Refused", "Usage"])
def test_a_refusal_needs_no_commands(name: str) -> None:
    ran = run_body(f'raise look.{name}("a sentence")')
    assert ran.err == "error: a sentence\n"


@pytest.mark.parametrize("name", ["Refused", "Usage"])
def test_a_refusal_carries_its_facts(name: str) -> None:
    refusal = getattr(look(), name)("a sentence", nexts=("tool one",))
    assert isinstance(refusal, Exception)
    assert refusal.sentence == "a sentence"
    assert tuple(refusal.nexts) == ("tool one",)


@pytest.mark.parametrize("streams", BOTH)
def test_stopped_prints_its_result_on_stdout_and_exits_3(streams: Streams) -> None:
    body = 'raise look.Stopped(look.Result("stopped", "at the cap", detail=(look.Row("kept", "312 runs"),), nexts=("tool hunt --resume",)))'
    ran = run_body(body, streams=streams)
    assert ran.exit == CODES["stopped"], ran
    text = strip(ran.out)
    assert text.startswith("stopped  at the cap\n")
    assert "312 runs" in text and "tool hunt --resume" in text
    assert ran.err == ""


def test_what_was_printed_before_a_refusal_stays_on_stdout() -> None:
    """A plan stays on screen when it refuses."""
    ran = run_body('show(look_results.RESULTS["plan-hunt"]())\nraise look.Refused("the cap would be passed")')
    assert ran.exit == 1, ran
    assert ran.out.startswith("plan  ")
    assert ran.err == "error: the cap would be passed\n"


@pytest.mark.parametrize("name", ["Refused", "Usage"])
def test_under_json_a_problem_stays_on_stderr_in_text(name: str) -> None:
    ran = run_body(f'raise look.{name}("a sentence")', ["--json"])
    assert ran.out == ""
    assert ran.err == "error: a sentence\n"


def test_under_json_stopped_is_one_document_and_its_exit_code() -> None:
    body = 'raise look.Stopped(look.Result("stopped", "at the cap", schema="poisson-break.test/1"))'
    ran = run_body(body, ["--json"])
    assert ran.exit == CODES["stopped"], ran
    document = strict_json(ran.out)
    assert list(document)[:3] == ["schema", "verdict", "sentence"]
    assert (document["verdict"], document["sentence"]) == ("stopped", "at the cap")


def test_under_json_ctrl_c_is_one_document_and_its_exit_code(tmp_path: Path) -> None:
    code = snippet('look.err("working\\n")\nimport time\ntime.sleep(30)')
    ran = launch([sys.executable, "-c", code, "--json"], home_env(tmp_path), PIPED, interrupt_on="working")
    assert ran.exit == CODES["interrupted"], ran
    document = strict_json(ran.out)
    assert list(document)[:3] == ["schema", "verdict", "sentence"]
    assert document["verdict"] == "stopped" and document["sentence"].startswith("interrupted: ")


def test_under_json_an_unexpected_failure_stays_on_stderr_in_text(tmp_path: Path) -> None:
    ran = run_body(FAILING, ["--json"], env=home_env(tmp_path))
    assert ran.exit == CODES["stopped"], ran
    assert ran.out == ""
    assert LINE.match(ran.err.splitlines()[0]), ran


# ---------- an unexpected failure ----------




def _path_of(line_path: str, env: dict[str, str]) -> Path:
    return Path(line_path.replace("~", env["HOME"], 1))


def _log(env: dict[str, str]) -> Path:
    code = "from poisson_break import look; print(look.errors_log_path())"
    done = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    return Path(done.stdout.strip())


@pytest.mark.parametrize("streams", BOTH)
def test_an_unexpected_failure_is_one_line_a_log_path_and_exit_3(tmp_path: Path, streams: Streams) -> None:
    env = home_env(tmp_path)
    ran = run_body(FAILING, env=env, streams=streams)
    assert ran.exit == CODES["stopped"], ran
    lines = strip(ran.err).splitlines()
    assert len(lines) == 1, repr(ran.err)
    match = LINE.match(lines[0])
    assert match, lines[0]
    assert match["tool"] == "poisson-break"
    assert match["kind"] == "ValueError"
    assert _path_of(match["path"], env) == _log(env)


@pytest.mark.parametrize("streams", BOTH)
def test_an_unexpected_failure_shows_no_raw_text(tmp_path: Path, streams: Streams) -> None:
    ran = run_body(FAILING, env=home_env(tmp_path), streams=streams)
    text = ran.out + ran.err
    assert "raw library text" not in text
    assert "Traceback" not in text
    assert "(1, 2)" not in text
    assert "File " not in text


def test_the_traceback_goes_to_the_log(tmp_path: Path) -> None:
    env = home_env(tmp_path)
    run_body(FAILING, env=env)
    log = _log(env).read_text(encoding="utf-8")
    assert "Traceback (most recent call last)" in log
    assert "raw library text" in log


def test_the_log_is_appended_to_never_replaced(tmp_path: Path) -> None:
    env = home_env(tmp_path)
    run_body('raise ValueError("the first")', env=env)
    run_body('raise KeyError("the second")', env=env)
    log = _log(env).read_text(encoding="utf-8")
    assert "the first" in log and "the second" in log
    assert log.count("Traceback (most recent call last)") == 2


def test_the_log_is_outside_the_working_folder_under_the_home_folder(tmp_path: Path) -> None:
    env = home_env(tmp_path)
    path = _log(env)
    assert path.is_absolute()
    assert path.is_relative_to(env["HOME"])


def test_a_failure_in_the_look_itself_is_held_too(tmp_path: Path) -> None:
    """What a result fails on while rendering is still one line."""
    env = home_env(tmp_path)
    ran = run_body('show(look.Result("ok", "x", detail=(object(),)))', env=env)
    assert ran.exit == CODES["stopped"], ran
    assert LINE.match(ran.err.splitlines()[0]), ran
    assert "Traceback" not in ran.err


def test_what_was_printed_before_a_failure_is_kept(tmp_path: Path) -> None:
    ran = run_body('look.out("kept so far\\n")\n' + FAILING, env=home_env(tmp_path))
    assert ran.exit == 3, ran
    assert ran.out == "kept so far\n"


def test_keyboard_interrupt_is_not_an_unexpected_failure(tmp_path: Path) -> None:
    env = home_env(tmp_path)
    run_body("raise KeyboardInterrupt", env=env)
    assert not _log(env).exists(), "Ctrl-C is a stop, and is not logged as a crash"


def test_exit_from_a_body_passes_through(tmp_path: Path) -> None:
    """`sys.exit` is how argparse leaves after `--help`. It is no failure."""
    env = home_env(tmp_path)
    ran = run_body("raise SystemExit(0)", env=env)
    assert ran.exit == 0 and ran.err == "", ran
    assert not _log(env).exists()


# ---------- Ctrl-C ----------


@pytest.mark.parametrize("streams", BOTH)
def test_ctrl_c_is_a_stop_with_exit_130(streams: Streams, tmp_path: Path) -> None:
    code = snippet('look.err("working\\n")\nimport time\ntime.sleep(30)')
    ran = launch([sys.executable, "-c", code], home_env(tmp_path), streams, interrupt_on="working")
    assert ran.exit == CODES["interrupted"], ran
    assert re.match(r"^stopped  interrupted: \S", strip(ran.out)), repr(ran.out)
    assert "Traceback" not in ran.err and "KeyboardInterrupt" not in ran.err, ran


def test_a_verb_can_say_what_it_kept_when_stopped_by_ctrl_c() -> None:
    body = ('raise look.Stopped(look.Result("stopped", "interrupted: 312 runs kept", nexts=("tool hunt --resume",)), '
            'code=look.EXIT["interrupted"])')
    ran = run_body(body)
    assert ran.exit == CODES["interrupted"], ran
    assert ran.out.startswith("stopped  interrupted: 312 runs kept\n")
    assert "tool hunt --resume" in ran.out


# ---------- a reader that has gone away ----------


def test_a_closed_pipe_is_no_traceback(tmp_path: Path) -> None:
    """`poisson-break findings | head -1`: the reader leaves, and the command says nothing about it."""
    code = snippet('for number in range(20000):\n    look.out(f"line {number}\\n")\nshow(look_results.RESULTS["found"]())')
    process = subprocess.Popen([sys.executable, "-c", code], env=home_env(tmp_path), stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                               cwd=str(Path(__file__).resolve().parent.parent))
    assert process.stdout is not None and process.stderr is not None
    if not select.select([process.stdout], [], [], 30)[0]:
        process.kill()
        process.wait(10)
        raise AssertionError("nothing reached stdout")
    process.stdout.read(10)
    process.stdout.close()
    err = process.stderr.read().decode()
    process.stderr.close()
    process.wait(30)
    assert "Traceback" not in err, err
    assert "BrokenPipe" not in err, err
    assert "Exception ignored" not in err, err


# ---------- out and err ----------


@pytest.mark.parametrize("streams", BOTH)
def test_out_writes_to_stdout_and_err_to_stderr(streams: Streams) -> None:
    ran = run_body('look.out("to the result\\n")\nlook.err("to the side\\n")', streams=streams)
    assert strip(ran.out) == "to the result\n"
    assert strip(ran.err) == "to the side\n"


def test_out_and_err_read_the_stream_when_called(capsys: pytest.CaptureFixture[str]) -> None:
    """A stream swapped after import, as a test or a caller may, is the one written to."""
    look().out("a\n")
    look().err("b\n")
    assert capsys.readouterr() == ("a\n", "b\n")


def test_outside_the_runner_the_problems_print_plain(capsys: pytest.CaptureFixture[str]) -> None:
    look().error("a problem", ["tool again"])
    look().note("a warning")
    out, err = capsys.readouterr()
    assert out == ""
    assert err == "error: a problem\n  next: tool again\nnote: a warning\n"


def _no_escape(text: str) -> bool:
    return ESCAPE.search(text) is None


def test_after_the_runner_a_terminal_is_plain_again() -> None:
    """Outside a run the problems print plain; what a run chose for itself ends with it."""
    code = ('import sys\nfrom poisson_break import look\n'
            'look.run("poisson-break", [], lambda: None)\nlook.error("after the run", [])\n')
    ran = launch([sys.executable, "-c", code], pretty_env(), TERMINALS)
    assert ran.exit == 0, ran
    assert ran.err == "error: after the run\n", repr(ran.err)


def test_a_yes_given_to_one_run_does_not_answer_after_it(capsys: pytest.CaptureFixture[str]) -> None:
    k = look()
    assert k.run("poisson-break", ["--yes"], lambda: None) == 0
    with pytest.raises(k.Refused):
        k.ask("start?", False)
    assert k.run("poisson-break", [], lambda: k.ask("start?", False)) == CODES["refused"]


def test_the_runner_leaves_the_process_as_it_found_it(capsys: pytest.CaptureFixture[str]) -> None:
    """Two commands run in one process, as tests do: the second is not printed through the first's choice."""
    code: Any = look().run("poisson-break", ["--plain"], lambda: look().note("first"))
    assert code == 0
    code = look().run("poisson-break", [], lambda: look().note("second"))
    assert code == 0
    out, err = capsys.readouterr()
    assert err == "note: first\nnote: second\n"
    assert _no_escape(err)


