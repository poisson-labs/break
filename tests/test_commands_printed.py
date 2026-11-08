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

Taylor's rulings on points 47 to 56 (2026-11-08) decide the rest, and the second half of this file holds them:

- point 48: `init`'s `--force` line is the user's own command with `--force` added, and runs as printed;
- point 49: `init`'s `--entry` line is a template: the user's own words, `--entry`, and one placeholder in capitals,
  which a test fills before it runs the line;
- point 50: `doctor`'s line for a settings problem is `init` only when there is no `break.toml`, and `doctor` when
  there is;
- point 51: a stage a tool nobody classed stopped prints point 44's line, then the resume line;
- point 52: `recheck`'s resume line carries `--old ENTRY`, `--check` and `--strict` as they were given;
- point 53: a resume line never carries `--yes`; run as printed with no terminal, it is refused and changes nothing;
- point 54: the plan shown before a resumed stage is that stage's: its repeats as written and the runs it has left,
  for `hunt`, `confirm` and `recheck`;
- point 56: a refusal over a finding file that cannot be read names the file by a path that leads to it, and prints no
  `next:`.

Point 47 is held in `test_commands_dialogue.py`, point 55 in `test_commands_findings.py`.
"""

from __future__ import annotations

import os
import re
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
    holds_number,
    hunt_names,
    nexts,
    results,
    prepared,
    project,
    read_json,
    store_runs,
    stored,
    verdict,
)
from tests.commands_lines import classing_nexts, the_next_writes_the_tool_in_as_off
from tests.look_support import Streams, strip

ENTRY = "tests.commands_targets:desk"
OLD = "tests.commands_targets:old_desk"
BOTH_TOOLS = ["--tool", 'lookup_order = "read"', "--tool", 'check_policy = "read"']
PRICED = [{**c, "tokens": [1000, 0]} for c in MIXED]
PRICES = {"input_per_million": 1.0, "output_per_million": 1.0}

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


# ---------------------------------------------------------------------------
# points 48 and 49: init's refusal lines
# ---------------------------------------------------------------------------


def written_by(flags: list[str]) -> str:
    from poisson_break.settings import dump, settings_from_init_args

    return str(dump(settings_from_init_args(flags)))


def test_init_s_force_line_is_the_user_s_own_command_and_runs_as_printed(tmp_path: Path) -> None:
    """Point 48: `break.toml` is there. The line is the user's own words with `--force` added once; run as printed,
    with no terminal, it writes the file those words write, and leaves the cases file as it was."""
    proj = project(tmp_path)
    flags = ["--kind", "rollout", "--entry", ENTRY, "--runs", "77", *BOTH_TOOLS]
    words = ["init", "--yes", *flags]
    before = files_under(proj.folder)
    ran = cli(proj, *words)
    assert ran.exit == CODES["refused"], ran
    assert files_under(proj.folder) == before
    (line,) = nexts(ran)
    got = shlex.split(line)
    assert got.count("--force") == 1, line
    assert [w for w in got if w != "--force"] == [PROG, *words], line
    again = cli(proj, *got[1:])
    assert again.exit == CODES["done"], again
    assert proj.settings.read_text(encoding="utf-8") == written_by(flags)
    assert set(files_under(proj.folder)) == {"break.toml", "cases.jsonl"}
    assert files_under(proj.folder)["cases.jsonl"] == before["cases.jsonl"]


def placeholders(words: list[str]) -> list[str]:
    """Point 49: a placeholder is a word in capitals, with no lower-case letter and at least one letter."""
    return [w for w in words if any(c.isalpha() for c in w) and w == w.upper()]


def test_init_s_entry_line_is_a_template_holding_the_user_s_words(tmp_path: Path) -> None:
    """Point 49: question 2 cannot be asked (`--yes`, and no entry given). The line is the user's own words, then
    `--entry` and one placeholder in capitals; nothing is written. Filled with the entry and run, with no terminal, it
    writes the file those words write."""
    proj = project(tmp_path, write=False)
    proj.write(case_list=cases(1))
    flags = ["--kind", "rollout", "--runs", "77", *BOTH_TOOLS]
    words = ["init", "--yes", *flags]
    ran = cli(proj, *words)
    assert ran.exit == CODES["refused"], ran
    assert not proj.settings.exists()
    (line,) = nexts(ran)
    got = shlex.split(line)
    (held,) = placeholders(got)
    at = got.index(held)
    assert got[at - 1] == "--entry", line
    assert got[:at - 1] + got[at + 1:] == [PROG, *words], line
    filled = [*got[:at], ENTRY, *got[at + 1:]]
    again = cli(proj, *filled[1:])
    assert again.exit == CODES["done"], again
    assert proj.settings.read_text(encoding="utf-8") == written_by([*flags, "--entry", ENTRY])


# ---------------------------------------------------------------------------
# point 50: doctor's line for a settings problem
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("problem", ["an unknown key", "a bad value", "no cases file"])
def test_a_settings_problem_in_a_file_that_is_there_gives_doctor_s_line(tmp_path: Path, problem: str) -> None:
    """Point 50: the line is `doctor`; run as printed it says the same and changes nothing, and once the problem is
    put right it says `ready`."""
    proj = project(tmp_path)
    good = proj.settings.read_text(encoding="utf-8")
    if problem == "an unknown key":
        proj.settings.write_text(good.replace('"runs" = 60', '"rnus" = 60'), encoding="utf-8")
    elif problem == "a bad value":
        proj.settings.write_text(good.replace('"q" = 0.05', '"q" = 1.5'), encoding="utf-8")
    kept_cases = (proj.folder / "cases.jsonl").read_bytes()
    if problem == "no cases file":
        (proj.folder / "cases.jsonl").unlink()
    ran = cli(proj, "doctor")
    assert ran.exit == CODES["check"], ran
    assert verdict(ran)[0] == "not ready", ran
    (line,) = nexts(ran)
    assert shlex.split(line) == [PROG, "doctor"], line
    before = files_under(proj.folder)
    again = cli(proj, *ours(line))
    assert (again.exit, verdict(again)) == (ran.exit, verdict(ran)), again
    assert files_under(proj.folder) == before
    proj.settings.write_text(good, encoding="utf-8")
    (proj.folder / "cases.jsonl").write_bytes(kept_cases)
    mended = cli(proj, *ours(line))
    assert (mended.exit, verdict(mended)[0]) == (CODES["done"], "ready"), mended


def test_with_no_settings_file_doctor_s_line_is_init(tmp_path: Path) -> None:
    proj = project(tmp_path, write=False)
    ran = cli(proj, "doctor")
    assert ran.exit == CODES["check"], ran
    assert [shlex.split(line) for line in nexts(ran)] == [[PROG, "init"]], ran


# ---------------------------------------------------------------------------
# point 51: a stage stopped by a tool nobody classed
# ---------------------------------------------------------------------------


def without_check_policy(proj: Project) -> None:
    text = proj.settings.read_text(encoding="utf-8")
    assert text.count('"check_policy" = "read"\n') == 1
    proj.settings.write_text(text.replace('"check_policy" = "read"\n', ""), encoding="utf-8")


def confirmed_by_the_library(proj: Project) -> None:
    import contextlib

    from poisson_break.confirm import confirm

    from tests.commands_support import opened

    prepared(proj, MIXED_CANDIDATES)
    with contextlib.chdir(proj.folder):
        confirm(opened(proj, "desk-1"))


@pytest.mark.parametrize("verb", ["hunt", "confirm", "recheck"])
def test_a_stage_a_tool_nobody_classed_stopped_prints_point_44_s_line_then_the_resume(tmp_path: Path,
                                                                                         verb: str) -> None:
    """Point 51: `check_policy` loses its line in `[tools]` before the stage, and the desk calls it on every run. The
    stage stops, and its lines are point 44's `init` line that classes the tool, then the resume line, in that order.
    The first, run as printed, writes the settings back with the tool `off`; the second, run as printed on a
    terminal and answered `y`, then goes on with the same hunt and ends."""
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    if verb == "confirm":
        prepared(proj, MIXED_CANDIDATES)
    elif verb == "recheck":
        confirmed_by_the_library(proj)
    without_check_policy(proj)
    ran = cli(proj, verb, "--yes")
    assert ran.exit not in (CODES["done"], CODES["usage"]), ran
    stop = [line for line in strip(ran.out).splitlines() if line.startswith("stopped  ")]
    assert len(stop) == 1 and "check_policy" in stop[0], ran  # spec §3.6: one line naming it
    lines = nexts(ran)
    assert len(lines) == 2, lines
    assert classing_nexts(ran, "check_policy", lines[:1]) == lines[:1], lines
    (name,) = hunt_names(proj)
    assert shlex.split(lines[1]) == [PROG, verb, "--hunt", name], lines
    the_next_writes_the_tool_in_as_off(proj, lines[0], "check_policy")
    again = cli(proj, *ours(lines[1]), streams=YES_ON_A_TERMINAL)
    assert again.exit == CODES["done"], again
    assert hunt_names(proj) == [name]


# ---------------------------------------------------------------------------
# points 52 and 53: what a resume line carries
# ---------------------------------------------------------------------------


def priced_and_confirmed(tmp_path: Path) -> Project:
    proj = project(tmp_path, PRICED, confirm={"repeats": 4}, search={"control_repeats": 3, "runs": 400},
                   limits={"dollars": 100.0, **PRICES})
    confirmed_by_the_library(proj)
    return proj


def capped(proj: Project, dollars: str) -> str:
    """Puts a dollar cap of `dollars` in place of 100, and hands back the file as it was."""
    text = proj.settings.read_text(encoding="utf-8")
    assert text.count('"dollars" = 100.0') == 1
    proj.settings.write_text(text.replace('"dollars" = 100.0', f'"dollars" = {dollars}'), encoding="utf-8")
    return text


@pytest.mark.parametrize("flags", [[], ["--old", OLD], ["--check", "--strict"], ["--old", OLD, "--check", "--strict"]],
                         ids=["none", "old", "check and strict", "all three"])
def test_recheck_s_resume_line_carries_old_check_and_strict_as_given(tmp_path: Path, flags: list[str]) -> None:
    """Point 52: a recheck its dollar cap stopped. The resume line is `recheck --hunt NAME` with `--old ENTRY`,
    `--check` and `--strict` each as given and nothing else, no `--yes` (point 53). Run as printed on a terminal,
    answered `y`, with the cap raised, it rechecks with the old agent's arm exactly when `--old` was given."""
    proj = priced_and_confirmed(tmp_path)
    before_arms = set(store_runs(proj, "desk-1"))
    text = capped(proj, "0.15")
    ran = cli(proj, "recheck", "--yes", *flags)
    assert ran.exit == CODES["stopped"], ran
    (line,) = nexts(ran)
    got = shlex.split(line)
    assert got[:4] == [PROG, "recheck", "--hunt", "desk-1"], line
    rest = got[4:]
    assert "--yes" not in rest, line
    if "--old" in flags:
        at = rest.index("--old")
        assert rest[at + 1] == OLD, line
        rest = rest[:at] + rest[at + 2:]
    assert sorted(rest) == sorted(f for f in flags if f in ("--check", "--strict")), line
    proj.settings.write_text(text, encoding="utf-8")
    again = cli(proj, *ours(line), streams=YES_ON_A_TERMINAL)
    assert again.exit in (CODES["done"], CODES["check"]), again
    made = set(store_runs(proj, "desk-1")) - before_arms
    assert made, again
    assert any(run.endswith("-old") for run in made) == ("--old" in flags), sorted(made)


@pytest.mark.parametrize("verb", ["hunt", "confirm", "recheck"])
def test_a_resume_line_carries_no_yes_and_run_with_no_terminal_changes_nothing(tmp_path: Path, verb: str) -> None:
    """Point 53: each spending verb run with `--yes` and stopped by its dollar cap. Its resume line has no `--yes`;
    run as printed with no terminal it is refused, makes no run and changes no file."""
    if verb == "hunt":
        proj = project(tmp_path, cases(3, weak_to=["error"], tokens=[1000, 0]), limits={"dollars": 0.0015, **PRICES})
    elif verb == "confirm":
        proj = project(tmp_path, PRICED, confirm={"repeats": 4}, search={"control_repeats": 3, "runs": 400},
                       limits={"dollars": 0.0375, **PRICES})
        prepared(proj, MIXED_CANDIDATES)
    else:
        proj = priced_and_confirmed(tmp_path)
        capped(proj, "0.15")
    ran = cli(proj, verb, "--yes")
    assert ran.exit == CODES["stopped"], ran
    (line,) = nexts(ran)
    assert "--yes" not in shlex.split(line), line
    before, runs = files_under(proj.folder), len(proj.runs())
    again = cli(proj, *ours(line))
    assert again.exit == CODES["refused"], again
    assert files_under(proj.folder) == before
    assert len(proj.runs()) == runs


# ---------------------------------------------------------------------------
# point 54: the plan before a resumed stage
# ---------------------------------------------------------------------------


def plan_block(ran: Any) -> str:
    plans = [block for block in results(ran.out) if block[0].startswith("plan  ")]
    assert len(plans) == 1, ran
    return "\n".join(plans[0])


def test_the_plan_before_a_resumed_hunt_counts_the_runs_it_has_left(tmp_path: Path) -> None:
    """Point 54: a hunt of at most 60 runs stopped after one; the plan before its resume counts 59 left."""
    proj = project(tmp_path, cases(3, weak_to=["error"], tokens=[1000, 0]), limits={"dollars": 0.0015, **PRICES})
    first = cli(proj, "hunt", "--yes")
    assert first.exit == CODES["stopped"], first
    assert len(proj.runs()) == 1
    proj.settings.write_text(proj.settings.read_text(encoding="utf-8").replace("0.0015", "1.0"), encoding="utf-8")
    (line,) = nexts(first)
    again = cli(proj, *ours(line), streams=YES_ON_A_TERMINAL)
    assert again.exit == CODES["done"], again
    assert holds_number(plan_block(again), "59"), plan_block(again)


def test_the_plan_before_a_resumed_confirm_stage_is_that_stage_as_written(tmp_path: Path) -> None:
    """Point 54: `confirm --repeats 6` asks again about the one candidate too small to tell, and its dollar cap stops
    it. The plan before its resume is that stage's: 6 repeats, and the runs its two arms have left; not a fresh
    stage's 176 runs of 4 repeats over three candidates."""
    import json

    proj = priced_and_confirmed(tmp_path)
    spent = sum(len(stored(proj, "desk-1", run.split("desk-1-", 1)[1])) for run in store_runs(proj, "desk-1"))
    text = capped(proj, repr((spent + 5) * 0.001))
    ran = cli(proj, "confirm", "--repeats", "6", "--yes")
    assert ran.exit == CODES["stopped"], ran
    stage = json.loads((proj.hunt("desk-1") / "confirm.json").read_text(encoding="utf-8"))["stages"][-1]
    assert stage["repeats"] == 6
    have = sum(len(stored(proj, "desk-1", arm["arm"])) for arm in stage["arms"]
               if f"desk-1-{arm['arm']}" in store_runs(proj, "desk-1"))
    left = len(stage["cases"]) * stage["repeats"] * len(stage["arms"]) - have
    assert 0 < left < len(stage["cases"]) * 6 * len(stage["arms"])
    proj.settings.write_text(text, encoding="utf-8")
    (line,) = nexts(ran)
    again = cli(proj, *ours(line), streams=YES_ON_A_TERMINAL)
    assert again.exit == CODES["done"], again
    plan = plan_block(again)
    assert holds_number(plan, "6") and holds_number(plan, str(left)), plan
    assert not holds_number(plan, "176"), plan


def test_the_plan_before_a_resumed_recheck_counts_the_runs_it_has_left(tmp_path: Path) -> None:
    """Point 54, with the spec's rule for `recheck` that an unfinished recheck is finished, the way it was begun,
    before a new one starts: a recheck its dollar cap stopped after a few runs. The plan before its resume counts the
    runs that recheck has left, not a fresh recheck's whole count."""
    from tests.commands_support import findings_of

    proj = priced_and_confirmed(tmp_path)
    total = sum(len(f.cases) * f.repeats for f in findings_of(proj, "desk-1"))
    spent = sum(len(stored(proj, "desk-1", run.split("desk-1-", 1)[1])) for run in store_runs(proj, "desk-1"))
    text = capped(proj, repr((spent + 5) * 0.001))
    ran = cli(proj, "recheck", "--yes")
    assert ran.exit == CODES["stopped"], ran
    made = [run for run in store_runs(proj, "desk-1") if "-recheck-" in run]
    have = sum(len(stored(proj, "desk-1", run.split("desk-1-", 1)[1])) for run in made)
    left = total - have
    assert 0 < left < total, (have, total)
    proj.settings.write_text(text, encoding="utf-8")
    (line,) = nexts(ran)
    again = cli(proj, *ours(line), streams=YES_ON_A_TERMINAL)
    assert again.exit == CODES["done"], again
    plan = plan_block(again)
    assert holds_number(plan, str(left)), plan
    assert not holds_number(plan, str(total)), plan


# ---------------------------------------------------------------------------
# point 56: a finding file that cannot be read
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def unreadable(tmp_path_factory: pytest.TempPathFactory) -> tuple[Project, Path]:
    proj = project(tmp_path_factory.mktemp("unreadable"), MIXED, **MIXED_SETTINGS)
    confirmed_by_the_library(proj)
    bad = proj.hunt("desk-1") / "findings" / "2.toml"
    bad.write_text("this is = = not toml\n", encoding="utf-8")
    return proj, bad


@pytest.mark.parametrize("words", [["findings", "2"], ["findings"], ["replay", "2"]],
                         ids=["findings 2", "the listing", "replay 2"])
def test_a_refusal_over_an_unreadable_finding_names_its_path_and_prints_no_next(
        unreadable: tuple[Project, Path], words: list[str]) -> None:
    """Point 56: refused, exit 1, in one `error:` line holding a path that leads to the file from the project's folder
    (or from anywhere, if absolute), and no `next:` line, so nothing sends the user round to the same refusal."""
    proj, bad = unreadable
    before = files_under(proj.folder)
    ran = cli(proj, *words)
    assert ran.exit == CODES["refused"], ran
    assert nexts(ran) == [], ran
    lines = [line for line in strip(ran.err).splitlines() if line.startswith("error: ")]
    assert len(lines) == 1, ran
    tokens = [t.strip("\"'`.,;:()") for t in re.split(r"\s+", lines[0])]
    assert any(t and (proj.folder / t).resolve() == bad.resolve() for t in tokens), lines[0]
    assert files_under(proj.folder) == before
