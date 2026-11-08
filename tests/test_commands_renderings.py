"""The spending verbs end to end in both renderings: `hunt --yes`, `confirm --yes` and `recheck --yes`.

Plan BK8.1 and BK12.1 for the three verbs the conformance corpus cannot yet hold. Each prints its plan before its result
and shows progress on a terminal's stderr, and two checks of the frozen conformance test cannot take either (put to
Taylor as a ruling; `tests/look_corpus.py` says so where they would be). What this file holds of them meanwhile:

- piped, the pretty build equals the plain build byte for byte: `NO_COLOR`, `TERM=dumb` and `--plain` change nothing on
  stdout or stderr;
- on terminals the result is drawn pretty, and carries the same words and numbers in the same order as piped, with
  the same exit code; with `NO_COLOR` on the same terminals it is plain text;
- with Rich failing to import, the terminals show what they show with `NO_COLOR`, on stdout;
- under `--json`, one strict document, the same on a pipe and on a terminal, whose verdict is the result's.

Every way runs in the same folder, put back first by `tests/commands_child.py`, so each prints the same hunt names and
paths. Stdout is compared on terminals, not stderr, which holds the progress a pipe never shows.
"""

from __future__ import annotations

import contextlib
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.commands_support import (
    CODES,
    MIXED,
    MIXED_CANDIDATES,
    MIXED_SETTINGS,
    Project,
    cases,
    child_env,
    json_document,
    on,
    opened,
    prepared,
    project,
    results,
)
from tests.look_support import PIPED, TERMINALS, launch, no_rich_path, strip, words_of

CHILD = Path(__file__).with_name("commands_child.py")


def keep(proj: Project) -> None:
    """Copy the project's folder into `pristine/`, for `commands_child.py` to put back before each way."""
    kept = proj.folder / "pristine"
    kept.mkdir()
    for path in proj.folder.iterdir():
        if path.name == "pristine":
            continue
        (shutil.copytree if path.is_dir() else shutil.copy2)(path, kept / path.name)


def way(proj: Project, words: list[str], name: str, tmp_path: Path) -> Any:
    env = child_env(proj)
    streams = PIPED
    if name == "no_color":
        env["NO_COLOR"] = "1"
    elif name == "dumb":
        env["TERM"] = "dumb"
    elif name == "plain":
        words = [*words, "--plain"]
    elif name == "terminal":
        streams = TERMINALS
    elif name == "terminal_plain":
        streams, env["NO_COLOR"] = TERMINALS, "1"
    elif name == "no_rich":
        streams = TERMINALS
        env["PYTHONPATH"] = no_rich_path(tmp_path / "no-rich") + ":" + env["PYTHONPATH"]
    elif name == "json":
        words = [*words, "--json"]
    elif name == "terminal_json":
        words, streams = [*words, "--json"], TERMINALS
    return launch([sys.executable, str(CHILD), *words], env, streams, cwd=proj.folder, timeout=240)


def hunt_project(tmp_path: Path) -> Project:
    return project(tmp_path, cases(3, weak_to=["error"]))


def confirm_project(tmp_path: Path) -> Project:
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    return proj


def recheck_project(tmp_path: Path) -> Project:
    from poisson_break.confirm import confirm

    proj = project(tmp_path, cases(12, rate=0.1, weak=0.6, weak_to=["error"]),
                   confirm={"repeats": 4}, search={"control_repeats": 3, "runs": 400})
    prepared(proj, (on("error"),))
    with contextlib.chdir(proj.folder):
        confirm(opened(proj, "desk-1"))
    return proj


VERBS = {"hunt": (hunt_project, ["hunt", "--yes"], "found"),
         "confirm": (confirm_project, ["confirm", "--yes"], "confirmed"),
         "recheck": (recheck_project, ["recheck", "--yes"], "rechecked")}


@pytest.fixture(scope="module", params=list(VERBS))
def ran(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> tuple[str, dict[str, Any]]:
    make, words, _ = VERBS[request.param]
    tmp = tmp_path_factory.mktemp(request.param)
    proj = make(tmp)
    keep(proj)
    ways = ("piped", "no_color", "dumb", "plain", "terminal", "terminal_plain", "no_rich", "json", "terminal_json")
    return request.param, {name: way(proj, list(words), name, tmp) for name in ways}


def ended(by: dict[str, Any]) -> None:
    """Every comparison below stands on the command having run: each way ended as it should."""
    assert {name: r.exit for name, r in by.items()} == dict.fromkeys(by, CODES["done"]), by


def test_each_way_ends_with_the_same_exit_code(ran: tuple[str, dict[str, Any]]) -> None:
    verb, by = ran
    assert {name: r.exit for name, r in by.items()} == dict.fromkeys(by, CODES["done"]), by


def test_piped_the_pretty_build_equals_the_plain_build_byte_for_byte(ran: tuple[str, dict[str, Any]]) -> None:
    verb, by = ran
    ended(by)
    base = by["piped"]
    for name in ("no_color", "dumb", "plain"):
        assert (by[name].out, by[name].err) == (base.out, base.err), (name, by[name], base)
    assert "\x1b" not in base.out + base.err


def test_piped_the_result_follows_its_plan(ran: tuple[str, dict[str, Any]]) -> None:
    verb, by = ran
    ended(by)
    words = [block[0].split("  ")[0] for block in results(by["piped"].out)]
    assert words == ["plan", VERBS[verb][2]], by["piped"]


def test_on_terminals_the_result_is_drawn_pretty_with_the_same_facts(ran: tuple[str, dict[str, Any]]) -> None:
    verb, by = ran
    ended(by)
    drawn = by["terminal"]
    assert "\x1b[" in drawn.out, drawn
    assert words_of(drawn.out) == words_of(by["piped"].out), (drawn, by["piped"])


def test_on_terminals_with_no_color_the_result_is_plain_text(ran: tuple[str, dict[str, Any]]) -> None:
    verb, by = ran
    ended(by)
    shown = by["terminal_plain"]
    assert "\x1b" not in shown.out and strip(shown.out) == shown.out, shown
    assert words_of(shown.out) == words_of(by["piped"].out)


def test_without_rich_the_terminals_show_plain(ran: tuple[str, dict[str, Any]]) -> None:
    verb, by = ran
    ended(by)
    assert "\x1b" not in by["no_rich"].out
    assert by["no_rich"].out == by["terminal_plain"].out, (by["no_rich"], by["terminal_plain"])


def test_under_json_one_document_the_same_on_a_pipe_and_a_terminal(ran: tuple[str, dict[str, Any]]) -> None:
    verb, by = ran
    ended(by)
    assert by["json"].out == by["terminal_json"].out
    document = json_document(by["json"])
    assert list(document)[:3] == ["schema", "verdict", "sentence"]
    assert document["verdict"] == VERBS[verb][2]
    final = results(by["piped"].out)[-1][0]
    assert final == f'{document["verdict"]}  {document["sentence"]}', (final, document)
