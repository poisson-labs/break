"""`show(result)`: a result printed the way the current run prints one.

Plan BK12's public names and the look's build, ruling 27 (`evidence/bk12/build-choices.md`, ruled 2026-11-05): "it
prints a result the way the current run prints one, the document under `--json`, else `render` in the run's mode". The
build that follows these tests adds the name to the look; the verbs print with it (plan BK8). Until then every test
here is red on `show` missing, and nothing else.

Each child runs `body` under `look.run`, as a verb does, and compares what `show` wrote with what the look's own
public names write for the same result in the same process: `as_json` under `--json`, and `render` on the same
stream in the mode the run chose otherwise. Nothing is mocked; which mode a run is in is what the operating system
and the environment say. Outside a run is not held here: the ruling does not say what `show` does there.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.look_support import PIPED, TERMINALS, look, pretty_env, run_body, strip, words_of

# A result with every kind of detail and a command to run next, and a plan, built in the child.
BUILD = """\
k = look
result = k.Result("found", "2 candidates in 40 runs", detail=(
    k.Row("control", "12 runs · 3 failed (0.250)"),
    k.Line("these are candidates, not findings"),
    k.Table(("#", "condition", "verdict"), (("1", "tool:lookup_order#1=error", "confirmed"),
                                           ("2", "tool:check_policy#1=timeout", "not confirmed")))),
    nexts=(k.command("poisson-break", "confirm"),), schema="poisson_break.example/1")
plan = k.Plan("a hunt of desk on 3 cases, at most 60 runs", estimate="about $0.10", source="the control stage",
              detail=(k.Row("stages", "control 6 runs, search and shrink up to 54"),))
"""

SPLIT = "=====SPLIT=====\n"


def _both(what: str, words: tuple[str, ...] = (), *, streams: Any = PIPED, env: Any = None, before: str = "") -> Any:
    """A child that writes `show(<what>)`, a line of its own, then what the look's own names write for the same
    result: `as_json` when `--json` is on the command line, else `render` on stdout in the mode `mode_for` gives."""
    body = BUILD + before + f"""
look.show({what})
sys.stdout.write({SPLIT!r})
sys.stdout.flush()
if "--json" in words:
    sys.stdout.write(look.as_json({what}))
else:
    look.render({what}, stream=sys.stdout, mode=look.mode_for(sys.stdout, sys.stderr, os.environ, words))
sys.stdout.flush()
"""
    ran = run_body(body, list(words), streams=streams, env=pretty_env() if env is None else env)
    assert ran.exit == 0, ran
    assert SPLIT.strip() in ran.out, ran
    shown, written = ran.out.split(SPLIT.strip() + "\n", 1)
    return ran, shown, written


def test_show_is_a_public_name_of_the_look() -> None:
    assert "show" in look().__all__
    assert callable(look().show)


@pytest.mark.parametrize("what", ["result", "plan"])
def test_under_json_show_writes_the_document_and_nothing_else(what: str) -> None:
    ran, shown, written = _both(what, ("--json",))
    assert shown == written
    assert shown.lstrip().startswith("{")
    assert "\x1b" not in shown
    assert ran.err == ""


@pytest.mark.parametrize("what", ["result", "plan"])
def test_under_json_on_a_terminal_show_still_writes_the_document(what: str) -> None:
    ran, shown, written = _both(what, ("--json",), streams=TERMINALS)
    assert shown == written
    assert "\x1b" not in shown


@pytest.mark.parametrize("what", ["result", "plan"])
def test_piped_show_writes_plain_byte_for_byte_as_render_does(what: str) -> None:
    ran, shown, written = _both(what)
    assert shown == written
    assert "\x1b" not in shown
    assert shown.splitlines()[0].startswith("found  " if what == "result" else "plan  ")


def test_on_terminals_show_draws_pretty_as_render_does() -> None:
    """Every condition of the switch holds: `show` draws what `render` draws pretty, escapes and all, and carries the
    same words as plain."""
    ran, shown, written = _both("result", streams=TERMINALS)
    assert shown == written
    assert "\x1b[" in shown
    _, plain, _ = _both("result")
    assert words_of(shown) == words_of(plain)


@pytest.mark.parametrize("change", [{"words": ("--plain",)}, {"env": {"NO_COLOR": "1"}}, {"env": {"TERM": "dumb"}},
                                    {"env": {"CI": "true"}}])
def test_on_terminals_with_the_switch_off_show_writes_plain(change: dict[str, Any]) -> None:
    words = change.get("words", ())
    env = pretty_env(**change.get("env", {}))
    ran, shown, written = _both("result", words, streams=TERMINALS, env=env)
    assert shown == written
    assert "\x1b" not in shown
    assert strip(shown) == shown


def test_show_prints_in_the_mode_the_run_chose_not_one_chosen_again() -> None:
    """The run chose pretty when it began; the body then sets `NO_COLOR`, which a new choice would read as plain.
    `show` still draws pretty: "the way the current run prints one"."""
    body = BUILD + """
os.environ["NO_COLOR"] = "1"
look.show(result)
"""
    ran = run_body(body, [], streams=TERMINALS)
    assert ran.exit == 0, ran
    assert "\x1b[" in ran.out


def test_show_under_json_in_a_run_whose_json_comes_after_a_double_dash_is_not_json() -> None:
    """The run reads `--json` from its command line as `mode_for` reads `--plain`, and stops at `--`: a `--json` after
    it is a word, not the flag, and `show` renders."""
    ran, shown, written = _both("result", ("--", "--json"))
    assert not shown.lstrip().startswith("{")
    assert shown.splitlines()[0].startswith("found  ")


def test_show_writes_to_stdout_and_nothing_to_stderr_and_returns_nothing() -> None:
    body = BUILD + """
returned = look.show(result)
sys.stderr.write(f"returned={returned!r}\\n")
"""
    ran = run_body(body, [], streams=PIPED)
    assert ran.exit == 0, ran
    assert ran.out.startswith("found  ")
    assert ran.err == "returned=None\n"


def test_two_shows_in_one_run_write_two_results_in_order() -> None:
    body = BUILD + """
look.show(plan)
look.show(result)
"""
    ran = run_body(body, [], streams=PIPED)
    lines = ran.out.splitlines()
    assert lines[0].startswith("plan  ")
    assert [i for i, text in enumerate(lines) if text.startswith("found  ")], ran
