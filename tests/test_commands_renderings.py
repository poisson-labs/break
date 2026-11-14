"""The spending verbs end to end in both renderings: `hunt --yes`, `confirm --yes` and `recheck --yes`.

Plan BK8.1 and BK12.1 for the three verbs the conformance corpus cannot yet hold. Each prints its plan before its result
and shows progress on a terminal's stderr, and two checks of the frozen conformance test cannot take either (put to
Taylor as a ruling; `tests/look_corpus.py` says so where they would be). What this file holds of them meanwhile:

- piped, the pretty build equals the plain build byte for byte: `NO_COLOR`, `TERM=dumb` and `--plain` change nothing on
  stdout or stderr;
- on terminals the result is drawn pretty, and carries the same words and numbers in the same order as piped, with
  the same exit code, a table's column names set aside where they stand (a table wider than the terminal is drawn one
  record per row, each line of a record opening with its column's name); with `NO_COLOR` on the same terminals it is
  plain text;
- the rows are one table lined up under its header, piped and on terminals wide enough for it, with a rule under the
  header there;
- with Rich failing to import, the terminals show what they show with `NO_COLOR`, on stdout;
- under `--json`, one strict document, the same on a pipe and on a terminal, whose verdict is the result's.

Every way runs in the same folder, put back first by `tests/commands_child.py`, so each prints the same hunt names and
paths. Stdout is compared on terminals, not stderr, which holds the progress a pipe never shows.
"""

from __future__ import annotations

import contextlib
import re
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
from tests.look_support import PIPED, TERMINALS, Streams, launch, no_rich_path, strip, words_of

CHILD = Path(__file__).with_name("commands_child.py")
#: Terminals wide enough for every table these verbs print, the recheck's widest row included.
WIDE = Streams(out="pty", err="pty", columns=160)


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
    elif name == "terminal_wide":
        streams = WIDE
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
    ways = ("piped", "no_color", "dumb", "plain", "terminal", "terminal_wide", "terminal_plain", "no_rich", "json",
            "terminal_json")
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


def without_column_names(text: str, names: list[str]) -> str:
    """The text with a table's column names taken out where they stand as names, and nowhere else: the header line
    over the rows, and the name that opens each line of a record, when a table wider than the terminal is drawn one
    record per row."""
    label = re.compile(r"^ {4}(?:" + "|".join(map(re.escape, names)) + r")  ")
    return "\n".join(label.sub("    ", line) for line in strip(text).splitlines() if line.split() != names)


def test_on_terminals_the_result_is_drawn_pretty_with_the_same_facts(ran: tuple[str, dict[str, Any]]) -> None:
    verb, by = ran
    ended(by)
    names = table_of(results(by["piped"].out)[-1])[0].split()
    for name in ("terminal", "terminal_wide"):
        drawn = by[name]
        assert "\x1b[" in drawn.out, drawn
        assert (words_of(without_column_names(drawn.out, names))
                == words_of(without_column_names(by["piped"].out, names))), (name, drawn, by["piped"])
        assert set(names) <= set(words_of(drawn.out)), (name, names, drawn)


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


def table_of(lines: list[str]) -> tuple[str, list[str]]:
    """The result's table: its header, the line whose first word is `condition`, and the numbered rows under it."""
    (at,) = [n for n, line in enumerate(lines) if line.split()[:1] == ["condition"]]
    rows = []
    for line in lines[at + 1:]:
        if re.fullmatch(r"[\s─-]+", line):
            continue
        if not re.match(r"  \d+  ", line):
            break
        rows.append(line)
    return lines[at], rows


def test_the_rows_are_a_table_lined_up_under_its_header(ran: tuple[str, dict[str, Any]]) -> None:
    """Hands-on issue 6: each verb's rows are one table, as hunt's, confirm's and findings' are: a header over the
    rows, its first cell blank, and each column's cells starting where its name does, two spaces after the cell
    before. Piped the header is the line over the rows; on terminals wide enough for the table a rule is drawn under
    it."""
    verb, by = ran
    ended(by)
    header, rows = table_of(results(by["piped"].out)[-1])
    assert header.startswith("     condition"), header
    starts = [m.start() for m in re.finditer(r"(?<!\S)\S", header)]
    assert rows, header
    for row in rows:
        for start in starts:
            assert row[start - 2:start] == "  " and row[start] != " ", (verb, header, row)
    drawn = [line.rstrip() for line in strip(by["terminal_wide"].out).splitlines()]
    (at,) = [n for n, line in enumerate(drawn) if line.split()[:1] == ["condition"]]
    assert set(drawn[at + 1].strip()) == {"─"}, drawn
