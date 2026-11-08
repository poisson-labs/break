"""The commands Break prints for the user to run, run as printed: each does what it says and changes nothing else.

Taylor's rulings on BK8 points 45 and 46 (2026-11-08) ask that a printed command run exactly as printed, and that it
change nothing it should not. These tests take that to every `next:` line whose behaviour the spec and the rulings
already decide, beside the tests of `doctor`'s `next:` (`test_commands_doctor.py`, points 44 to 46) and of `init`'s
printed command (`test_commands_dialogue.py`, point 46):

- the reading verbs' lines: `confirm`'s and `findings`'s `findings N`, the replay line and Trace's line of
  `findings N` (spec §9.1: `findings` reads, `replay` runs once and stores nothing (point 17), and Trace's command is
  "the Trace command for its full report");
- a spending verb's resume line after a stop (point 7, BK8.13, BK5.10), run as printed on a terminal and answered
  yes, where the frozen tests run it with `--yes` added: `hunt --hunt NAME` and `confirm --hunt NAME` (a stopped
  confirm stage resumes under its written design, spec §5.5);
- the `--help` lines of a usage error, and `doctor`'s `doctor` line for a target problem. The `--help` lines of an
  unknown verb and an unknown option are BK0's parser's, already on `main`, so those two cases pass before the build.

"Changes nothing it should not": the project's files outside the hunts folder are as they were, the hunts folder too
where the command only reads, no target run is made where none should be, and no stored run is made twice.

The lines whose behaviour is not decided are put to Taylor in `evidence/bk8/open-points.md` (points 47 to 54), and
no test here stands on them.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.commands_support import (
    CODES,
    MIXED,
    MIXED_CANDIDATES,
    MIXED_SETTINGS,
    PROG,
    Project,
    cases,
    cli,
    files_under,
    hunt_names,
    nexts,
    prepared,
    project,
    read_json,
    store_runs,
    stored,
    verdict,
)
from tests.look_support import Streams, strip

YES_ON_A_TERMINAL = Streams(stdin="pty", keys=(b"y\r",))


def outside_hunts(proj: Project) -> dict[str, bytes]:
    return {name: data for name, data in files_under(proj.folder).items() if not name.startswith("break-runs/")}


def ours(command: str) -> list[str]:
    """A printed command of Break's, as the words after the prog."""
    words = shlex.split(command)
    assert words[0] == PROG, command
    return words[1:]


# ---------------------------------------------------------------------------
# the reading verbs' lines
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def confirmed(tmp_path_factory: pytest.TempPathFactory) -> tuple[Project, Any]:
    """`confirm` run by the command on the three candidates of `MIXED`: one finding."""
    proj = project(tmp_path_factory.mktemp("confirmed"), MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    ran = cli(proj, "confirm", "--yes")
    assert ran.exit == CODES["done"], ran
    return proj, ran


def test_confirm_s_findings_line_run_as_printed_reads_and_changes_nothing(confirmed: tuple[Project, Any]) -> None:
    proj, ran = confirmed
    assert nexts(ran), ran
    for command in nexts(ran):
        assert ours(command)[0] == "findings", command
        before, runs = files_under(proj.folder), len(proj.runs())
        again = cli(proj, *ours(command))
        assert again.exit == CODES["done"], again
        assert verdict(again)[0] == "ok", again
        assert files_under(proj.folder) == before
        assert len(proj.runs()) == runs


def test_findings_s_line_run_as_printed_reads_and_changes_nothing(confirmed: tuple[Project, Any]) -> None:
    proj, _ = confirmed
    listed = cli(proj, "findings")
    assert nexts(listed), listed
    for command in nexts(listed):
        before, runs = files_under(proj.folder), len(proj.runs())
        again = cli(proj, *ours(command))
        assert again.exit == CODES["done"], again
        assert files_under(proj.folder) == before
        assert len(proj.runs()) == runs


def test_the_replay_line_run_as_printed_replays_once_and_stores_nothing(confirmed: tuple[Project, Any]) -> None:
    """Point 17: `replay` asks nothing, so the line runs as printed with no terminal; one run, nothing stored."""
    proj, _ = confirmed
    shown = cli(proj, "findings", "1")
    (command,) = [c for c in nexts(shown) if shlex.split(c)[1:2] == ["replay"]]
    before, runs = files_under(proj.folder), len(proj.runs())
    again = cli(proj, *ours(command))
    assert again.exit == CODES["done"], again
    assert verdict(again)[0] in ("failed", "did not fail"), again
    assert len(proj.runs()) == runs + 1
    assert files_under(proj.folder) == before


def test_trace_s_line_run_as_printed_from_any_folder_reports_and_changes_nothing(
        confirmed: tuple[Project, Any], tmp_path: Path) -> None:
    """The finding's Trace command, through a shell, from the project's folder and from another: it exits 0 and
    leaves the project as it was. Trace is installed with Break, so its command is on the path beside Break's."""
    proj, _ = confirmed
    shown = cli(proj, "findings", "1")
    (command,) = [c for c in nexts(shown) if shlex.split(c)[0] != PROG]
    path = os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")])
    for where in (proj.folder, tmp_path):
        before = files_under(proj.folder)
        done = subprocess.run(command, shell=True, cwd=where, env={**os.environ, "PATH": path}, capture_output=True,
                              text=True, timeout=240)
        assert done.returncode == 0, (where, done.stdout, done.stderr)
        assert done.stdout.strip(), done
        assert files_under(proj.folder) == before


# ---------------------------------------------------------------------------
# a spending verb's resume line, run as printed on a terminal
# ---------------------------------------------------------------------------


def test_a_hunt_s_resume_line_run_as_printed_and_answered_yes_finishes_that_hunt(tmp_path: Path) -> None:
    """Point 7: a hunt stopped by its dollar cap after one run, the cap then raised. The line the stop printed, run
    as printed on a terminal and answered `y`, goes on with that hunt: no new hunt, the stored run not made again, the
    control whole, and nothing outside the hunts folder changed by it."""
    proj = project(tmp_path, cases(3, weak_to=["error"], tokens=[1000, 0]),
                   limits={"dollars": 0.0015, "input_per_million": 1.0, "output_per_million": 1.0})
    first = cli(proj, "hunt", "--yes")
    assert first.exit == CODES["stopped"], first
    (name,) = hunt_names(proj)
    (stopped_at,) = [(r["case"], r["seed"]) for r in proj.runs()]
    proj.settings.write_text(proj.settings.read_text(encoding="utf-8").replace("0.0015", "1.0"), encoding="utf-8")
    (command,) = nexts(first)
    before = outside_hunts(proj)
    again = cli(proj, *ours(command), streams=YES_ON_A_TERMINAL)
    assert again.exit == CODES["done"], again
    assert hunt_names(proj) == [name]
    assert [(r["case"], r["seed"]) for r in proj.runs()].count(stopped_at) == 1
    assert len(stored(proj, name, "control")) == 6
    assert outside_hunts(proj) == before


def test_a_confirm_stage_s_resume_line_run_as_printed_and_answered_yes_finishes_that_stage(tmp_path: Path) -> None:
    """Point 7 for `confirm`, and spec §5.5: a confirm stage stopped by its dollar cap after one run, the cap then
    raised. The line, run as printed on a terminal and answered `y`, finishes that stage under its written design: one
    stage in `confirm.json`, each of its arms 11 cases by 4 repeats, no stored run made twice, and nothing outside the
    hunts folder changed by it."""
    priced = [{**c, "tokens": [1000, 0]} for c in MIXED]
    proj = project(tmp_path, priced, confirm={"repeats": 4}, search={"control_repeats": 3, "runs": 400},
                   limits={"dollars": 0.0375, "input_per_million": 1.0, "output_per_million": 1.0})
    prepared(proj, MIXED_CANDIDATES)
    first = cli(proj, "confirm", "--yes")
    assert first.exit == CODES["stopped"], first
    (kept,) = [(r["meta"]["poisson_break"]["case"], r["seed"]) for r in stored(proj, "desk-1", "confirm-control")]
    proj.settings.write_text(proj.settings.read_text(encoding="utf-8").replace("0.0375", "100.0"), encoding="utf-8")
    (command,) = nexts(first)
    before = outside_hunts(proj)
    again = cli(proj, *ours(command), streams=YES_ON_A_TERMINAL)
    assert again.exit == CODES["done"], again
    assert hunt_names(proj) == ["desk-1"]
    assert len(read_json(proj.hunt("desk-1") / "confirm.json")["stages"]) == 1
    for arm in ("confirm-control", "confirm-1", "confirm-2", "confirm-3"):
        rows = [(r["meta"]["poisson_break"]["case"], r["seed"]) for r in stored(proj, "desk-1", arm)]
        assert len(rows) == 11 * 4 and len(set(rows)) == len(rows), arm
    control = [(r["meta"]["poisson_break"]["case"], r["seed"]) for r in stored(proj, "desk-1", "confirm-control")]
    assert kept in control
    assert not [run for run in store_runs(proj, "desk-1") if run.startswith("desk-1-confirm-2-")]
    assert outside_hunts(proj) == before


# ---------------------------------------------------------------------------
# lines that change nothing: --help after a usage error, doctor after a target problem
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("words", [["bogus"], ["hunt", "--nope"],
                                   ["init", "--yes", "--entry", "tests.commands_targets:desk", "--runs", "0"]],
                         ids=["an unknown verb", "an unknown option", "a bad value given to init"])
def test_a_usage_error_s_help_line_run_as_printed_prints_help_and_changes_nothing(tmp_path: Path,
                                                                                    words: list[str]) -> None:
    proj = project(tmp_path / "proj")
    if words[0] == "init":
        proj.settings.unlink()
    ran = cli(proj, *words)
    assert ran.exit == CODES["usage"], ran
    if words[0] == "init":
        assert "search.runs" in strip(ran.err), ran  # point 22: the key, so this is init's own refusal
    assert nexts(ran), ran
    for command in nexts(ran):
        assert ours(command)[-1] == "--help", command
        before = files_under(proj.folder)
        again = cli(proj, *ours(command))
        assert again.exit == CODES["done"], again
        assert again.out.strip(), again
        assert files_under(proj.folder) == before
    assert proj.runs() == []


def test_doctor_s_doctor_line_run_as_printed_checks_again_and_changes_nothing(tmp_path: Path) -> None:
    """A target that cannot be imported: `doctor`'s line, run as printed, says the same and changes nothing; and once
    the entry is put right, the same line says `ready`, exit 0, with no question asked and no run made (BK8.6, point
    23: `doctor` asked for nothing more runs nothing and asks nothing)."""
    proj = project(tmp_path, entry="tests.nowhere_at_all:desk")
    ran = cli(proj, "doctor")
    assert ran.exit == CODES["check"], ran
    (command,) = nexts(ran)
    before = files_under(proj.folder)
    again = cli(proj, *ours(command))
    assert (again.exit, verdict(again)) == (ran.exit, verdict(ran)), again
    assert files_under(proj.folder) == before
    proj.settings.write_text(proj.settings.read_text(encoding="utf-8").replace("tests.nowhere_at_all:desk",
                                                                               "tests.commands_targets:desk"),
                             encoding="utf-8")
    fixed = files_under(proj.folder)
    ready = cli(proj, *ours(command))
    assert ready.exit == CODES["done"], ready
    assert verdict(ready)[0] == "ready", ready
    assert "[y/N]" not in strip(ready.err), ready
    assert files_under(proj.folder) == fixed
    assert proj.runs() == []
