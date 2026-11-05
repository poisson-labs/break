"""When output is pretty and when it is plain.

Invariant pinned here (Break — Plan, the look layer):
- BK12.2  Pretty runs only when stdout and stderr are both terminals, `NO_COLOR` is unset or empty, `CI` is
          unset, `TERM` is not `dumb`, stdout is UTF-8, and neither `--json` nor `--plain` was given; each
          condition alone forces plain, shown one at a time.

`mode_for` is given real streams, a pseudo-terminal, a pipe and a file, so `isatty` is the operating
system's answer. Then the same conditions end to end, in a child that prints through `mode_for`.

Two readings the copies of the standard agree on, written down because each is an easy mistake: `CI` set to
anything, empty included, is set; `TERM` unset is not `dumb`.

Two the copies disagreed on, ruled: `NO_COLOR` set and empty counts as unset, and both streams must be terminals.
And one the spec did not decide, ruled: `mode_for` stops reading flags at `--`, since a word after it is an argument.
"""

from __future__ import annotations

import os
import pty
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.look_support import (
    PIPED,
    TERMINALS,
    Streams,
    look,
    pretty_env,
    run_body,
    run_result,
    strict_json,
    strip,
)

HOLDS = {"TERM": "xterm-256color"}


class Open:
    """Opens real streams for a test and closes them after."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.opened: list[Any] = []
        self.fds: list[int] = []

    def terminal(self, encoding: str = "utf-8") -> Any:
        master, slave = pty.openpty()
        self.fds.append(master)
        stream = os.fdopen(slave, "w", encoding=encoding)
        self.opened.append(stream)
        return stream

    def pipe(self, encoding: str = "utf-8") -> Any:
        read, write = os.pipe()
        self.fds.append(read)
        stream = os.fdopen(write, "w", encoding=encoding)
        self.opened.append(stream)
        return stream

    def file(self, encoding: str = "utf-8") -> Any:
        stream = open(self.tmp_path / "out.txt", "w", encoding=encoding)  # noqa: SIM115
        self.opened.append(stream)
        return stream

    def close(self) -> None:
        for stream in self.opened:
            stream.close()
        for fd in self.fds:
            os.close(fd)


@pytest.fixture()
def streams(tmp_path: Path) -> Iterator[Open]:
    opened = Open(tmp_path)
    yield opened
    opened.close()


def test_every_condition_holding_is_pretty(streams: Open) -> None:
    assert look().mode_for(streams.terminal(), streams.terminal(), HOLDS, []) == "pretty"


@pytest.mark.parametrize("kind", ["pipe", "file"])
def test_stdout_that_is_no_terminal_is_plain(streams: Open, kind: str) -> None:
    assert look().mode_for(getattr(streams, kind)(), streams.terminal(), HOLDS, []) == "plain"


@pytest.mark.parametrize("value", ["1", "0", "false", "yes"])
def test_no_color_with_any_value_is_plain(streams: Open, value: str) -> None:
    env = {**HOLDS, "NO_COLOR": value}
    assert look().mode_for(streams.terminal(), streams.terminal(), env, []) == "plain"


@pytest.mark.parametrize("value", ["true", "1", "false", "0", ""])
def test_ci_set_to_anything_is_plain(streams: Open, value: str) -> None:
    env = {**HOLDS, "CI": value}
    assert look().mode_for(streams.terminal(), streams.terminal(), env, []) == "plain"


def test_term_dumb_is_plain(streams: Open) -> None:
    assert look().mode_for(streams.terminal(), streams.terminal(), {"TERM": "dumb"}, []) == "plain"


def test_term_unset_is_not_dumb(streams: Open) -> None:
    assert look().mode_for(streams.terminal(), streams.terminal(), {}, []) == "pretty"


@pytest.mark.parametrize("term", ["vt100", "xterm", "screen-256color", "dumb-ish"])
def test_any_other_term_is_not_dumb(streams: Open, term: str) -> None:
    assert look().mode_for(streams.terminal(), streams.terminal(), {"TERM": term}, []) == "pretty"


@pytest.mark.parametrize("encoding", ["ascii", "latin-1", "utf-16", "cp1252"])
def test_stdout_not_utf8_is_plain(streams: Open, encoding: str) -> None:
    assert look().mode_for(streams.terminal(encoding), streams.terminal(), HOLDS, []) == "plain"


@pytest.mark.parametrize("encoding", ["utf8", "UTF-8", "utf_8", "U8"])
def test_every_spelling_of_utf8_counts(streams: Open, encoding: str) -> None:
    assert look().mode_for(streams.terminal(encoding), streams.terminal(), HOLDS, []) == "pretty"


def test_only_stdout_needs_to_be_utf8(streams: Open) -> None:
    assert look().mode_for(streams.terminal(), streams.terminal("latin-1"), HOLDS, []) == "pretty"


@pytest.mark.parametrize("argv", [
    ["--plain"], ["--plain", "hunt"], ["hunt", "--plain"], ["hunt", "--name", "x", "--plain"],
    ["--json"], ["hunt", "--json"], ["--json", "hunt"], ["findings", "2", "--json"],
    ["--plain", "--json"],
], ids=" ".join)
def test_the_two_flags_force_plain_before_or_after_the_verb(streams: Open, argv: list[str]) -> None:
    assert look().mode_for(streams.terminal(), streams.terminal(), HOLDS, argv) == "plain"


@pytest.mark.parametrize("argv", [["hunt"], ["findings", "2"], ["--plainly"], ["--json-out", "x"], ["plain"], ["json"]],
                         ids=" ".join)
def test_other_words_on_the_command_line_change_nothing(streams: Open, argv: list[str]) -> None:
    assert look().mode_for(streams.terminal(), streams.terminal(), HOLDS, argv) == "pretty"


def test_the_environment_read_is_the_one_given(streams: Open, monkeypatch: pytest.MonkeyPatch) -> None:
    """The environment handed in decides, in both directions, so a command's tests can set it apart from the
    process's own."""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("TERM", "dumb")
    assert look().mode_for(streams.terminal(), streams.terminal(), HOLDS, []) == "pretty"
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.delenv("CI")
    monkeypatch.setenv("TERM", "xterm-256color")
    assert look().mode_for(streams.terminal(), streams.terminal(), {**HOLDS, "NO_COLOR": "1"}, []) == "plain"


def test_the_argv_read_is_the_one_given(streams: Open, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["poisson-break", "--plain"])
    assert look().mode_for(streams.terminal(), streams.terminal(), HOLDS, []) == "pretty"


def test_a_closed_stream_is_no_terminal(streams: Open) -> None:
    """A stream closed by the parent, or `None` under `pythonw`, is not a terminal, and is no crash."""
    closed = streams.terminal()
    closed.close()
    assert look().mode_for(closed, streams.terminal(), HOLDS, []) == "plain"
    assert look().mode_for(None, streams.terminal(), HOLDS, []) == "plain"


# ---------- end to end, one condition at a time ----------

ALL_ON_TERMINALS = "\n".join([
    'look.note("a warning 3")',
    'show(look_results.RESULTS["ready"]())',
])


def _plain_on_terminals() -> Any:
    return run_body(ALL_ON_TERMINALS, ["--plain"], streams=TERMINALS)


def test_end_to_end_every_condition_holding_is_pretty_on_both_streams() -> None:
    ran = run_body(ALL_ON_TERMINALS, streams=TERMINALS)
    assert ran.exit == 0, ran
    assert "\x1b[" in ran.out and "\x1b[" in ran.err, ran
    assert strip(ran.out) != ran.out


@pytest.mark.parametrize("name, env", [
    ("NO_COLOR", {"NO_COLOR": "1"}),
    ("CI", {"CI": "true"}),
    ("CI empty", {"CI": ""}),
    ("TERM", {"TERM": "dumb"}),
], ids=lambda v: v if isinstance(v, str) else "")
def test_end_to_end_one_condition_off_prints_plain_on_the_terminal(name: str, env: dict[str, str]) -> None:
    ran = run_body(ALL_ON_TERMINALS, streams=TERMINALS, env=pretty_env(**env))
    plain = _plain_on_terminals()
    assert ran.exit == plain.exit == 0, ran
    assert "\x1b" not in ran.out + ran.err, ran
    assert (ran.out, ran.err) == (plain.out, plain.err)


def test_end_to_end_a_stdout_not_utf8_prints_plain_on_the_terminal() -> None:
    ran = run_body(ALL_ON_TERMINALS, streams=TERMINALS, env=pretty_env(PYTHONIOENCODING="latin-1"))
    assert ran.exit == 0, ran
    assert "\x1b" not in ran.out + ran.err, ran


def test_end_to_end_stdout_piped_with_stderr_on_a_terminal_is_plain_on_both() -> None:
    both_piped = run_body(ALL_ON_TERMINALS, streams=PIPED)
    ran = run_body(ALL_ON_TERMINALS, streams=Streams(out="pipe", err="pty"))
    assert ran.exit == 0, ran
    assert "\x1b" not in ran.out + ran.err, ran
    assert ran.out == both_piped.out
    assert ran.err == both_piped.err


def test_end_to_end_stdout_to_a_file_is_plain(tmp_path: Path) -> None:
    path = tmp_path / "held.txt"
    ran = run_body(ALL_ON_TERMINALS, streams=Streams(out=path, err="pty"))
    piped = run_body(ALL_ON_TERMINALS, streams=PIPED)
    assert ran.exit == 0, ran
    assert path.read_text(encoding="utf-8") == piped.out


@pytest.mark.parametrize("words", [["--plain"], ["--plain", "hunt"], ["hunt", "--plain"]], ids=" ".join)
def test_end_to_end_the_plain_flag_turns_off_the_whole_rendering_on_a_terminal(words: list[str]) -> None:
    ran = run_body(ALL_ON_TERMINALS, words, streams=TERMINALS)
    assert ran.exit == 0, ran
    assert "\x1b" not in ran.out + ran.err, ran


def test_end_to_end_json_is_one_document_on_a_terminal() -> None:
    ran = run_result("found", ["--json"], streams=TERMINALS)
    assert ran.exit == 0, ran
    document = strict_json(ran.out)
    assert document["verdict"] == "found"
    assert "\x1b" not in ran.out


@pytest.mark.parametrize("name, env", [("NO_COLOR", {"NO_COLOR": "1"}), ("TERM", {"TERM": "dumb"}), ("CI", {"CI": "1"})],
                         ids=lambda v: v if isinstance(v, str) else "")
def test_no_color_is_the_whole_rendering_not_only_its_colour(name: str, env: dict[str, str]) -> None:
    """A rendering with its colours off could still draw bold, dim or a table's rules. Plain has none."""
    ran = run_result("found", streams=TERMINALS, env=pretty_env(**env))
    plain = run_result("found", ["--plain"], streams=TERMINALS)
    assert (ran.exit, ran.out, ran.err) == (0, plain.out, plain.err), ran


# ---------- as ruled ----------


def test_no_color_set_and_empty_counts_as_unset(streams: Open) -> None:
    assert look().mode_for(streams.terminal(), streams.terminal(), {**HOLDS, "NO_COLOR": ""}, []) == "pretty"


def test_end_to_end_no_color_set_and_empty_is_pretty() -> None:
    ran = run_result("found", streams=TERMINALS, env=pretty_env(NO_COLOR=""))
    assert ran.exit == 0, ran
    assert "\x1b[" in ran.out, ran


@pytest.mark.parametrize("kind", ["pipe", "file"])
def test_stderr_that_is_no_terminal_is_plain(streams: Open, kind: str) -> None:
    assert look().mode_for(streams.terminal(), getattr(streams, kind)(), HOLDS, []) == "plain"


def test_end_to_end_stderr_piped_with_stdout_on_a_terminal_is_plain_on_both() -> None:
    body = 'show(look_results.RESULTS["found"]())\nlook.note("a warning")'
    ran = run_body(body, streams=Streams(out="pty", err="pipe"))
    assert ran.exit == 0, ran
    assert "\x1b" not in ran.out + ran.err, ran
    assert ran.out == run_body(body, ["--plain"], streams=Streams(out="pty", err="pty")).out


@pytest.mark.parametrize("flag", ["--plain", "--json"])
def test_a_flag_after_two_dashes_is_an_argument(streams: Open, flag: str) -> None:
    assert look().mode_for(streams.terminal(), streams.terminal(), HOLDS, ["hunt", "--", flag]) == "pretty"


@pytest.mark.parametrize("flag", ["--plain", "--json"])
def test_a_flag_before_two_dashes_still_counts(streams: Open, flag: str) -> None:
    assert look().mode_for(streams.terminal(), streams.terminal(), HOLDS, [flag, "--", "hunt"]) == "plain"
