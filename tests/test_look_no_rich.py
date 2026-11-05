"""Rich absent means plain, and plain needs nothing but the standard library.

Invariant pinned here (Break — Plan, the look layer):
- BK12.12  With Rich not importable, every command prints plain and says nothing about it.

And the ruling it rests on (plan §7, item 5): the look is built on Rich and questionary, ordinary dependencies, and
Rich draws pretty. The plain rendering is standard library only, so a run that does not need them never loads them.

"Not importable" is made real: a folder first on `PYTHONPATH` holds packages of those names that fail on import, as a
machine without them does. The conformance test does the same for its whole corpus.
"""

from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path

import pytest

from tests.look_support import Streams, TERMINALS, no_rich_path, pretty_env, run_body, run_result, strip


def _without_rich(tmp_path: Path) -> dict[str, str]:
    env = pretty_env()
    env["PYTHONPATH"] = no_rich_path(tmp_path / "blocked") + ":" + env["PYTHONPATH"]
    return env


BODY = 'show(look_results.RESULTS["found"]())\nlook.note("a warning")\nlook.error("a problem", ["tool again"])'


def test_on_a_terminal_without_rich_the_look_is_plain_and_says_nothing(tmp_path: Path) -> None:
    ran = run_body(BODY, streams=TERMINALS, env=_without_rich(tmp_path))
    plain = run_body(BODY, ["--plain"], streams=TERMINALS)
    assert ran.exit == 0, ran
    assert "\x1b" not in ran.out + ran.err, ran
    assert (ran.out, ran.err) == (plain.out, plain.err)
    assert not re.search(r"(?i)\brich\b", ran.out + ran.err)


def test_without_rich_plain_still_wraps_at_the_terminals_width(tmp_path: Path) -> None:
    long = " ".join(["word"] * 40)
    body = f'show(look.Result("ok", "fine", detail=(look.Row("label", {long!r}),)))'
    narrow = Streams(out="pty", err="pty", columns=40)
    ran = run_body(body, streams=narrow, env=_without_rich(tmp_path))
    assert ran.exit == 0, ran
    assert ran.out == run_body(body, ["--plain"], streams=narrow).out
    assert len(ran.out.splitlines()) > 2


def test_without_rich_a_problem_still_exits_as_it_should(tmp_path: Path) -> None:
    ran = run_body('raise look.Refused("a sentence")', streams=TERMINALS, env=_without_rich(tmp_path))
    assert ran.exit == 1, ran
    assert ran.err == "error: a sentence\n"


def test_without_rich_progress_runs_and_a_question_is_asked(tmp_path: Path) -> None:
    body = ('with look.Progress("searching", 2) as progress:\n    progress.advance()\n    progress.advance()\n'
            'print("answer", look.ask("how many?", "400"))')
    streams = Streams(out="pty", err="pty", stdin="pty", keys=(b"\r",))
    ran = run_body(body, streams=streams, env=_without_rich(tmp_path))
    assert ran.exit == 0, ran
    assert "answer 400" in ran.out
    assert "\x1b[3" not in ran.err, repr(ran.err)
    assert "unexpected failure" not in ran.err


def test_without_questionary_alone_a_menu_is_asked(tmp_path: Path) -> None:
    folder = tmp_path / "blocked"
    no_rich_path(folder)
    import shutil
    shutil.rmtree(folder / "rich")
    env = pretty_env()
    env["PYTHONPATH"] = str(folder) + ":" + env["PYTHONPATH"]
    ran = run_body('print("answer", look.ask("built with?", "b", choices=("a", "b")))',
                   streams=Streams(out="pty", err="pty", stdin="pty", keys=(b"\r",)), env=env)
    assert ran.exit == 0, ran
    assert "answer b" in strip(ran.out)


@pytest.mark.parametrize("body", [
    "pass",
    'show(look_results.RESULTS["found"]())',
    'look.error("a", [])\nlook.note("b")',
    'with look.Progress("x", 1) as progress:\n    progress.advance()',
    'look.fmt_rate(0.5)\nlook.fmt_duration(100)\nlook.command("a", "b")',
], ids=["nothing", "a-result", "problems", "progress", "numbers"])
@pytest.mark.parametrize("words", [[], ["--plain"]], ids=["piped", "piped-plain"])
def test_plain_never_loads_rich_or_questionary(body: str, words: list[str]) -> None:
    probe = body + '\nsys.stdout.flush()\nprint("loaded", sorted(m for m in sys.modules if m.split(".")[0] in ("rich", "questionary", "prompt_toolkit")))'
    ran = run_body(probe, words)
    assert ran.exit == 0, ran
    assert "loaded []" in ran.out, ran


def test_importing_the_look_loads_neither() -> None:
    ran = run_body('print("loaded", sorted(m for m in sys.modules if m.split(".")[0] in ("rich", "questionary", "prompt_toolkit")))')
    assert "loaded []" in ran.out, ran


def test_pretty_is_drawn_with_rich() -> None:
    ran = run_body('show(look_results.RESULTS["found"]())\nprint("loaded", "rich" in sys.modules)', streams=TERMINALS)
    assert ran.exit == 0, ran
    assert "loaded True" in strip(ran.out), ran


@pytest.mark.parametrize("name", ["rich", "questionary"])
def test_they_are_ordinary_dependencies(name: str) -> None:
    declared = importlib.metadata.requires("poisson-break") or []
    ordinary = [r for r in declared if ";" not in r]
    found = [r for r in ordinary if re.split(r"[\s=<>!~\[]", r, maxsplit=1)[0].lower() == name]
    assert found, f"{name} is not an ordinary dependency: {declared}"


def test_a_result_without_rich_matches_plain_on_a_pipe_and_on_a_terminal(tmp_path: Path) -> None:
    env = _without_rich(tmp_path)
    piped = run_result("found", env=env)
    assert piped.exit == 0, piped
    assert piped.out == run_result("found").out
    assert run_result("found", streams=TERMINALS, env=env).out == run_result("found", ["--plain"], streams=TERMINALS).out
