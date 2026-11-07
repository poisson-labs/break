"""`hunt`: the control, search and shrink stages from the command, in both renderings.

Invariants held here (Break — Plan, the commands module; spec §9.1, §9.2, §5.2 to §5.5):
- BK8.1   A stage's `control` and `search` lines are progress on stderr, gone from a terminal when the stage ends; what
          matters of them is a detail line under the verdict.
- BK8.2   `--json` is one strict document, `schema`, `verdict`, `sentence` first, with the same exit code.
- BK8.7   No line names a hash; `confirm` is the next command, with no hunt to type.
- BK8.9   "Break calls your tools for real" after every plan, as a `note:` on stderr, unindented.
- BK8.10  The candidates are never called findings: the stated line says they are candidates.
- BK8.11  A hunt that finds nothing prints coverage before anything else after the verdict.
- BK8.13  The plan is shown and asked before any run; a non-terminal stdin without `--yes` prints the plan and refuses;
          `--dry-run` runs nothing; a `HuntStopped` prints what was kept and exits 3; Ctrl-C prints what was kept and
          the resume command and exits 130.
- §9.1    Names, never hashes: `--name` used as given, a name not safe or taken refused in one line; hunts numbered
          from the target's name; the plan's run counts are `plan_hunt`'s.
- §5.2    A case that fails every control run is set aside and named.
- §5.5    The candidates are the conditions that fail more than the control, best first, at most `candidates`.
- BK5.17, BK6.11, BK5.18  What a way in cannot do, a strategy that cannot be found and a check that cannot be loaded
          are each refused in one line before any run.

Taylor's rulings on BK8's open points (2026-11-07), held here: under `--json` only the result's document is printed,
and the plan's only when it is the result (point 6); `hunt --hunt NAME` goes on with that hunt, and is the command a
Ctrl-C and a cap's stop print (point 7); "start?" answered no runs nothing, exits 0 and says `stopped  nothing was run`
(point 9); `--dry-run` writes nothing (point 10); the result's schema is `poisson_break.hunt-result/1` (point 11); the
high base rate is a `note:` on stderr carrying the control's rate (point 12); and a candidate's line carries "k of n
failed" from the rows of the stage that last ran it, and the kind most of its failed rows have (point 13).

The scripted desk (`tests/commands_targets.py`) fails every run in which its look-up raised `error`, and no other run,
unless a case says otherwise. Every run it makes is counted from its log, in the child.
"""

from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from tests.commands_support import (
    CODES,
    PROG,
    SOUND,
    Project,
    candidates,
    cases,
    child_env,
    cli,
    err_lines,
    errors,
    files_under,
    paths_under,
    opened,
    hashes,
    holds_number,
    hunt_names,
    json_document,
    nexts,
    notes,
    on,
    project,
    REAL,
    detail,
    result_of,
    results,
    row,
    refused_once,
    store_runs,
    stored,
    verdict,
)
from tests.look_support import VERDICT_LINE, Streams, screen, strip

def no_hash(ran: Any, proj: Project) -> None:
    text = (ran.out + ran.err).replace(str(proj.folder.parent), "")
    assert hashes(text) == [], f"a hash in what was printed:\n{ran}"


# ---------------------------------------------------------------------------
# one hunt that finds the planted weakness, read by many tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def found(tmp_path_factory: pytest.TempPathFactory) -> tuple[Project, Any]:
    proj = project(tmp_path_factory.mktemp("found"))
    return proj, cli(proj, "hunt", "--yes")


def test_a_hunt_that_finds_the_planted_weakness_says_found_and_exits_0(found: tuple[Project, Any]) -> None:
    proj, ran = found
    assert ran.exit == CODES["done"], ran
    word, sentence = VERDICT_LINE.match(result_of(ran, "found")[0]).groups()  # type: ignore[union-attr]
    assert word == "found"
    assert "finding" not in sentence


def test_the_one_condition_that_fails_more_than_the_control_is_the_one_candidate(found: tuple[Project, Any]) -> None:
    """Only `error` on the look-up fails; every other condition fails as often as the control, which is never."""
    proj, ran = found
    (name,) = hunt_names(proj)
    assert candidates(proj, name) == [on("error")]


def test_the_candidates_are_shown_by_number_and_name_in_the_file_s_order(found: tuple[Project, Any]) -> None:
    proj, ran = found
    block = result_of(ran, "found")
    (name,) = hunt_names(proj)
    listed = candidates(proj, name)
    for number, condition in enumerate(listed, start=1):
        assert [line for line in detail(block) if line.split()[:2] == [str(number), condition]], block


def test_the_found_sentence_counts_the_candidates_and_the_runs_spent(found: tuple[Project, Any]) -> None:
    """"found 4 candidates in 400 runs": the runs are every run the target made, control, search and shrink, and
    the stored rows of those stages say the same."""
    proj, ran = found
    (name,) = hunt_names(proj)
    sentence = VERDICT_LINE.match(result_of(ran, "found")[0]).group(2)  # type: ignore[union-attr]
    made = len(proj.runs())
    rows = sum(len(stored(proj, name, arm)) for arm in ("control", "search", "shrink")
               if f"{name}-{arm}" in store_runs(proj, name))
    assert made == rows
    assert holds_number(sentence, str(made)), sentence
    assert holds_number(sentence, str(len(candidates(proj, name)))), sentence
    assert "$" not in ran.out, "no prices, so no dollars (spec §9.3, question 8)"


def test_the_control_and_search_stages_are_detail_lines_with_their_runs(found: tuple[Project, Any]) -> None:
    """BK8.1: what matters of a stage is a detail line under the verdict. The control ran 3 cases twice: 6 runs, none
    failed; the search's runs are the search arm's stored rows."""
    proj, ran = found
    (name,) = hunt_names(proj)
    block = result_of(ran, "found")
    control = row(block, "control")
    assert holds_number(control, "6")
    assert holds_number(control, "0.000")
    search = row(block, "search")
    assert holds_number(search, str(len(stored(proj, name, "search"))))


def test_piped_no_stage_progress_reaches_stderr(found: tuple[Project, Any]) -> None:
    """Progress shows only where stderr is a terminal: piped, stderr holds problems and notes and nothing else."""
    proj, ran = found
    assert ran.exit == CODES["done"] and proj.runs(), ran
    assert all(re.match(r"(note: |error: |  )", line) for line in err_lines(ran)), ran.err


def test_the_candidates_are_never_called_findings(found: tuple[Project, Any]) -> None:
    """BK8.10: a line says they are candidates and not findings, and no other line calls anything a finding."""
    proj, ran = found
    block = result_of(ran, "found")
    stated = [line for line in detail(block) if "candidates" in line and "not findings" in line]
    assert len(stated) == 1, block
    others = [line for line in block if re.search(r"\bfindings?\b", line) and line not in stated]
    assert others == [], others


def test_confirm_is_the_next_command_with_no_hunt_to_type(found: tuple[Project, Any]) -> None:
    """BK8.7: the next command is `confirm`, which defaults to the latest hunt; if it names the hunt, by its name."""
    proj, ran = found
    (name,) = hunt_names(proj)
    commands = [shlex.split(c) for c in nexts(ran)]
    confirms = [c for c in commands if c[:2] == [PROG, "confirm"]]
    assert confirms, ran
    for words in confirms:
        assert words[2:] in ([], ["--hunt", name]), words
    no_hash(ran, proj)


def test_the_note_after_the_plan_is_on_stderr_unindented(found: tuple[Project, Any]) -> None:
    proj, ran = found
    assert [n for n in notes(ran) if REAL in n], ran.err
    assert results(ran.out)[0][0].startswith("plan  "), "the plan is shown before the hunt runs"


def test_the_coverage_is_printed_after_a_hunt_that_found_something_too(found: tuple[Project, Any]) -> None:
    """Spec §5.3: every hunt ends with what it did not look at. Seven faults are off in these settings, and each is
    named."""
    proj, ran = found
    text = "\n".join(result_of(ran, "found"))
    for fault in ("slow", "empty", "cut_off", "malformed", "stale", "lost_reply", "planted_instruction"):
        assert re.search(rf"\b{fault}\b", text), (fault, text)


def test_the_candidates_are_written_best_first(tmp_path: Path) -> None:
    """Spec §5.5. Six cases, each condition run on all six: `error` fails all six, `timeout` only the three cases weak to
    it. Both fail more than the control, which never fails, and `error` is the better: it comes first, in the file and
    on the screen."""
    proj = project(tmp_path, [*cases(3, weak_to=["error", "timeout"]), *cases(3, first=4, weak_to=["error"])],
                   search={"cases_per_condition": 6, "runs": 60})
    ran = cli(proj, "hunt", "--yes")
    assert ran.exit == CODES["done"], ran
    (name,) = hunt_names(proj)
    assert candidates(proj, name) == [on("error"), on("timeout")]
    lines = detail(result_of(ran, "found"))
    first = next(i for i, line in enumerate(lines) if line.split()[:2] == ["1", on("error")])
    second = next(i for i, line in enumerate(lines) if line.split()[:2] == ["2", on("timeout")])
    assert first < second


def test_no_more_candidates_are_written_than_the_settings_allow(tmp_path: Path) -> None:
    """`[confirm] candidates = 1`: of the two conditions that fail more than the control, the better alone."""
    proj = project(tmp_path, [*cases(3, weak_to=["error", "timeout"]), *cases(3, first=4, weak_to=["error"])],
                   search={"cases_per_condition": 6, "runs": 60}, confirm={"candidates": 1})
    assert cli(proj, "hunt", "--yes").exit == CODES["done"]
    (name,) = hunt_names(proj)
    assert candidates(proj, name) == [on("error")]


# ---------------------------------------------------------------------------
# a hunt that finds nothing
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def nothing(tmp_path_factory: pytest.TempPathFactory) -> tuple[Project, Any]:
    """A desk no fault moves, whose cases look the order up twice where `max_call` is 1, with three faults off."""
    proj = project(tmp_path_factory.mktemp("nothing"), cases(3, lookups=2),
                   vary={"tools": ["error", "timeout"], "max_call": 1})
    return proj, cli(proj, "hunt", "--yes")


def test_a_hunt_that_finds_nothing_says_so_exits_0_and_writes_no_candidates(nothing: tuple[Project, Any]) -> None:
    proj, ran = nothing
    assert ran.exit == CODES["done"], ran
    result_of(ran, "nothing found")
    (name,) = hunt_names(proj)
    assert not (proj.hunt(name) / "candidates.json").exists()


def test_a_hunt_that_finds_nothing_prints_coverage_before_anything_else(nothing: tuple[Project, Any]) -> None:
    """BK8.11. The coverage's facts here: the faults turned off (`rate_limited` among them) and the call numbers past
    the limit of 1 on `lookup_order`, called twice. The first detail line carries coverage, and every line that
    carries a coverage fact comes before the control stage's line."""
    proj, ran = nothing
    block = result_of(ran, "nothing found")
    lines = detail(block)
    assert lines, block
    facts = (r"\brate_limited\b", r"\bplanted_instruction\b")
    assert any(re.search(f, lines[0]) for f in facts), lines
    control_at = next(i for i, line in enumerate(lines) if line.split()[:1] == ["control"])
    carrying = [i for i, line in enumerate(lines) if any(re.search(f, line) for f in facts)]
    assert carrying and max(carrying) < control_at, lines


def test_a_hunt_that_finds_nothing_names_the_tool_called_past_the_limit(nothing: tuple[Project, Any]) -> None:
    proj, ran = nothing
    lines = detail(result_of(ran, "nothing found"))
    control_at = next(i for i, line in enumerate(lines) if line.split()[:1] == ["control"])
    assert any(re.search(r"\blookup_order\b", line) for line in lines[:control_at]), lines


def test_confirm_is_not_offered_after_a_hunt_that_found_nothing(nothing: tuple[Project, Any]) -> None:
    proj, ran = nothing
    result_of(ran, "nothing found")
    assert not [c for c in nexts(ran) if shlex.split(c)[1:2] == ["confirm"]], ran


# ---------------------------------------------------------------------------
# the plan, the question, --yes and --dry-run
# ---------------------------------------------------------------------------


def test_a_dry_run_shows_the_plan_s_run_counts_and_runs_nothing(tmp_path: Path) -> None:
    """BK8.13, BK4.8: 3 cases, 2 control repeats, 60 runs: a control of 6, search and shrink up to 54, at most 60."""
    proj = project(tmp_path)
    ran = cli(proj, "hunt", "--dry-run")
    assert ran.exit == CODES["done"], ran
    word, sentence = verdict(ran)
    assert word == "plan"
    text = strip(ran.out)
    for number in ("6", "54", "60"):
        assert holds_number(text, number), (number, text)
    assert proj.runs() == []
    assert [n for n in notes(ran) if REAL in n], ran.err


def test_a_dry_run_shows_the_target_its_tools_and_the_strategy(tmp_path: Path) -> None:
    proj = project(tmp_path, search={"strategy": "random"})
    text = strip(cli(proj, "hunt", "--dry-run").out)
    for fact in ("tests.commands_targets:desk", "lookup_order", "check_policy", "random"):
        assert fact in text, (fact, text)


def test_the_plan_s_counts_follow_the_settings(tmp_path: Path) -> None:
    """5 cases, 3 control repeats, 100 runs: 15, 85, 100."""
    proj = project(tmp_path, cases(5), search={"control_repeats": 3, "runs": 100})
    text = strip(cli(proj, "hunt", "--dry-run").out)
    for number in ("15", "85", "100"):
        assert holds_number(text, number), (number, text)


def test_a_dry_run_under_json_is_one_document_of_the_plan(tmp_path: Path) -> None:
    proj = project(tmp_path)
    ran = cli(proj, "hunt", "--dry-run", "--json")
    assert ran.exit == CODES["done"], ran
    document = json_document(ran)
    assert list(document)[:3] == ["schema", "verdict", "sentence"]
    assert document["verdict"] == "plan"
    assert {"estimate", "source"} <= set(document)
    assert proj.runs() == []


def test_without_a_terminal_and_without_yes_the_plan_is_shown_and_refused(tmp_path: Path) -> None:
    """BK8.13, BK12.7: stdin is not a terminal and nobody gave `--yes`: the plan on stdout, one `error:` line naming
    `--yes`, exit 1, and no run."""
    proj = project(tmp_path)
    ran = cli(proj, "hunt")
    assert ran.exit == CODES["refused"], ran
    assert verdict(ran)[0] == "plan"
    assert len(errors(ran)) == 1
    assert "--yes" in errors(ran)[0]
    assert proj.runs() == []


def test_a_question_answered_no_runs_nothing(tmp_path: Path) -> None:
    """Point 9: nothing run, exit 0, and after the plan the result `stopped  nothing was run`."""
    proj = project(tmp_path)
    ran = cli(proj, "hunt", streams=Streams(stdin="pty", keys=(b"n\r",)))
    assert verdict(ran)[0] == "plan"
    assert proj.runs() == []
    assert "Traceback" not in ran.err
    assert ran.exit == CODES["done"], ran
    assert [b[0] for b in results(ran.out)] == [results(ran.out)[0][0], "stopped  nothing was run"], ran
    assert errors(ran) == []


def test_a_question_answered_yes_runs_the_hunt(tmp_path: Path) -> None:
    proj = project(tmp_path)
    ran = cli(proj, "hunt", streams=Streams(stdin="pty", keys=(b"y\r",)))
    assert ran.exit == CODES["done"], ran
    result_of(ran, "found")
    assert proj.runs()


def test_on_one_terminal_the_note_comes_after_the_plan_and_before_the_result(tmp_path: Path) -> None:
    """As a user sees it, stdout and stderr on one terminal: the plan, then the note, then the hunt's result."""
    proj = project(tmp_path)
    ran = cli(proj, "hunt", "--yes", streams=Streams(together=True, columns=200))
    shown = strip(ran.out)
    plan_at = shown.index("plan  ")
    note_at = shown.index(REAL)
    found_at = shown.index("found  ")
    assert plan_at < note_at < found_at, shown


def test_on_terminals_no_stage_progress_is_left_on_the_screen(tmp_path: Path) -> None:
    """BK8.1: while a stage runs its progress is on stderr; when it ends it is gone, and what stays is the result."""
    proj = project(tmp_path, cases(3, weak_to=["error"], nap=0.05))
    ran = cli(proj, "hunt", "--yes", streams=Streams(together=True, columns=120))
    assert ran.exit == CODES["done"], ran
    lines, _ = screen(ran.out, columns=120, rows=200)
    left = [line for line in lines if re.match(r"\s*(control|search|shrink)\s+\d[\d,]*/\d", line)]
    assert left == [], lines


# ---------------------------------------------------------------------------
# --json
# ---------------------------------------------------------------------------


def test_a_hunt_under_json_is_one_strict_document_with_the_same_exit_code(tmp_path: Path) -> None:
    """Points 6 and 11: the hunt goes on to run, so only its result's document is printed, `hunt-result`."""
    proj = project(tmp_path)
    ran = cli(proj, "hunt", "--yes", "--json")
    assert ran.exit == CODES["done"], ran
    document = json_document(ran)
    assert list(document)[:3] == ["schema", "verdict", "sentence"]
    assert document["verdict"] == "found"
    assert document["schema"] == "poisson_break.hunt-result/1"
    assert "\x1b" not in ran.out


def test_under_json_without_a_terminal_the_plan_is_the_document_and_the_refusal_on_stderr(tmp_path: Path) -> None:
    """Point 6: the plan is the result when the question cannot be asked: its document on stdout, the refusal's one
    line on stderr naming `--yes`, exit 1, no run."""
    proj = project(tmp_path)
    ran = cli(proj, "hunt", "--json")
    assert ran.exit == CODES["refused"], ran
    assert json_document(ran)["verdict"] == "plan"
    assert len(errors(ran)) == 1 and "--yes" in errors(ran)[0], ran.err
    assert proj.runs() == []


def test_a_dry_run_writes_nothing_and_moves_no_hunt_number(tmp_path: Path) -> None:
    """Point 10: the folder is as it was, under `--json` too; the hunt made after it is still the first."""
    proj = project(tmp_path)
    before, paths = files_under(proj.folder), paths_under(proj.folder)
    for words in (["hunt", "--dry-run"], ["hunt", "--dry-run", "--json"]):
        assert cli(proj, *words, PYTHONDONTWRITEBYTECODE="1").exit == CODES["done"]
        assert files_under(proj.folder) == before
        assert paths_under(proj.folder) == paths
    assert cli(proj, "hunt", "--yes").exit == CODES["done"]
    assert hunt_names(proj) == ["desk-1"]


# ---------------------------------------------------------------------------
# names, never hashes
# ---------------------------------------------------------------------------


def test_hunts_are_numbered_from_the_target_s_name(tmp_path: Path) -> None:
    proj = project(tmp_path, SOUND)
    for _ in range(2):
        assert cli(proj, "hunt", "--yes").exit == CODES["done"]
    assert hunt_names(proj) == ["desk-1", "desk-2"]
    assert "desk-2-control" in store_runs(proj, "desk-2")


def test_a_given_name_is_used_as_given(tmp_path: Path) -> None:
    proj = project(tmp_path, SOUND)
    ran = cli(proj, "hunt", "--yes", "--name", "Nightly.run_7")
    assert ran.exit == CODES["done"], ran
    assert hunt_names(proj) == ["Nightly.run_7"]
    assert "Nightly.run_7-control" in store_runs(proj, "Nightly.run_7")


@pytest.mark.parametrize("bad", ["a b", "../up", "-dash", ".dot", "x" * 65, "café", "a/b"])
def test_a_name_that_is_not_safe_is_refused_in_one_line_before_any_run(tmp_path: Path, bad: str) -> None:
    proj = project(tmp_path, SOUND)
    ran = cli(proj, "hunt", "--yes", f"--name={bad}")
    refused_once(ran, CODES["refused"])
    assert proj.runs() == []
    assert hunt_names(proj) == []


def test_a_name_that_is_taken_is_refused_never_swapped_for_a_number(tmp_path: Path) -> None:
    proj = project(tmp_path, SOUND)
    assert cli(proj, "hunt", "--yes", "--name", "mine").exit == CODES["done"]
    runs = len(proj.runs())
    ran = cli(proj, "hunt", "--yes", "--name", "mine")
    assert ran.exit == CODES["refused"], ran
    assert len(errors(ran)) == 1
    assert len(proj.runs()) == runs
    assert hunt_names(proj) == ["mine"]


def test_a_name_of_64_characters_is_taken(tmp_path: Path) -> None:
    proj = project(tmp_path, SOUND)
    name = "n" * 64
    assert cli(proj, "hunt", "--yes", "--name", name).exit == CODES["done"]
    assert hunt_names(proj) == [name]


# ---------------------------------------------------------------------------
# the control stage's facts
# ---------------------------------------------------------------------------


def test_a_case_that_fails_every_control_run_is_set_aside_and_named(tmp_path: Path) -> None:
    proj = project(tmp_path, [*cases(3, weak_to=["error"]), *cases(1, first=9, outcome="unresolved")])
    ran = cli(proj, "hunt", "--yes")
    assert ran.exit == CODES["done"], ran
    block = result_of(ran, "found")
    assert re.search(r"\bk9\b", "\n".join(block)), block
    assert not [line for line in block if re.search(r"\bk[1-3]\b", line)], "only the case set aside is named"


# ---------------------------------------------------------------------------
# refusals before any run
# ---------------------------------------------------------------------------


def test_a_change_the_way_in_cannot_make_is_refused_before_any_run_naming_the_change(tmp_path: Path) -> None:
    """BK5.17: the `rollout` kind plays no conversation, so `[vary] conversation = ["repeats"]` is refused, naming the
    change as it is asked, `user:repeats@1`."""
    proj = project(tmp_path, vary={"conversation": ["repeats"]})
    ran = cli(proj, "hunt", "--yes")
    line = refused_once(ran, CODES["refused"])
    assert "user:repeats@1" in line
    assert proj.runs() == []


def test_a_strategy_that_cannot_be_found_is_refused_before_any_run(tmp_path: Path) -> None:
    proj = project(tmp_path, search={"strategy": "tests.nowhere_at_all:Strategy"})
    ran = cli(proj, "hunt", "--yes")
    refused_once(ran, CODES["refused"])
    assert proj.runs() == []


def test_a_check_that_cannot_be_called_is_refused_before_any_run(tmp_path: Path) -> None:
    proj = project(tmp_path, fails={"own": "tests.commands_targets:NOT_CALLABLE"})
    ran = cli(proj, "hunt", "--yes")
    refused_once(ran, CODES["refused"])
    assert proj.runs() == []


def test_a_control_that_leaves_no_room_is_refused_naming_the_runs_that_fit(tmp_path: Path) -> None:
    """Spec §5.2: 3 cases at 2 repeats need 6 runs and a condition 2 more: `runs = 7` is refused, naming 8."""
    proj = project(tmp_path, search={"runs": 7})
    ran = cli(proj, "hunt", "--yes")
    line = refused_once(ran, CODES["refused"])
    assert holds_number(line, "8"), line
    assert "search.runs" in line
    assert proj.runs() == []


def test_an_unknown_key_is_refused_naming_its_path_and_the_nearest_known_one(tmp_path: Path) -> None:
    proj = project(tmp_path)
    proj.settings.write_text(proj.settings.read_text().replace('"runs" = 60', '"rnus" = 60'), encoding="utf-8")
    ran = cli(proj, "hunt", "--yes")
    line = refused_once(ran, CODES["refused"])
    assert "search.rnus" in line and "search.runs" in line, line
    assert proj.runs() == []


def test_with_no_settings_file_the_hunt_is_refused_with_a_next_command(tmp_path: Path) -> None:
    proj = project(tmp_path, write=False)
    ran = cli(proj, "hunt", "--yes")
    refused_once(ran, CODES["refused"])
    assert nexts(ran), "an error says what to do"
    assert all(shlex.split(c)[0] == PROG for c in nexts(ran))


# ---------------------------------------------------------------------------
# a stage that stops short, and Ctrl-C
# ---------------------------------------------------------------------------


def test_a_hunt_stopped_by_its_dollar_cap_prints_what_was_kept_and_exits_3(tmp_path: Path) -> None:
    """BK8.13, BK5.9: each run costs $0.001; with a cap of $0.0015 the first run runs and the second would pass it. The
    stop is a result, `stopped`, carrying the cap's word and the one run kept, and the exit is 3."""
    proj = project(tmp_path, cases(3, weak_to=["error"], tokens=[1000, 0]),
                   limits={"dollars": 0.0015, "input_per_million": 1.0, "output_per_million": 1.0})
    ran = cli(proj, "hunt", "--yes")
    assert ran.exit == CODES["stopped"], ran
    block = result_of(ran, "stopped")
    text = "\n".join(block)
    assert len(proj.runs()) == 1
    (name,) = hunt_names(proj)
    assert len(stored(proj, name, "control")) == 1
    assert re.search(r"\bdollars?\b", text), text
    assert holds_number(text, "1"), text
    assert nexts(ran) == [f"{PROG} hunt --hunt {name}"], "point 7: a stop gives the command that goes on with it"
    assert "Traceback" not in ran.err


def _interrupted(proj: Project, words: list[str], after_runs: int) -> Any:
    """The command on pseudo-terminals, sent Ctrl-C once its target has started `after_runs` runs."""
    import pty

    from tests.look_support import Ran, _fold

    master, slave = pty.openpty()
    process = subprocess.Popen([sys.executable, "-m", "poisson_break", *words], cwd=proj.folder,
                               env=child_env(proj), stdin=subprocess.DEVNULL, stdout=slave, stderr=slave,
                               start_new_session=True,
                               preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))  # noqa: PLW1509
    os.close(slave)
    got = b""
    deadline = time.monotonic() + 120
    sent = False
    import select

    while time.monotonic() < deadline:
        ready, _, _ = select.select([master], [], [], 0.05)
        if ready:
            try:
                chunk = os.read(master, 65536)
            except OSError:
                chunk = b""
            if not chunk and process.poll() is not None:
                break
            got += chunk
        if not sent and len(proj.runs()) >= after_runs:
            os.killpg(process.pid, signal.SIGINT)
            sent = True
        if process.poll() is not None and not ready:
            break
    else:
        os.killpg(process.pid, signal.SIGKILL)
        raise AssertionError("the command did not end")
    process.wait(10)
    os.close(master)
    return Ran(process.returncode, _fold(got), "")


def test_ctrl_c_during_a_hunt_prints_what_was_kept_and_how_to_go_on_and_exits_130(tmp_path: Path) -> None:
    """BK8.13, BK5.11. Each run naps 0.4 s; Ctrl-C after the second has started. The stop line says how many runs were
    kept, which is what the store holds; the command it gives, run as printed, finishes the hunt and runs no stored
    cell again."""
    proj = project(tmp_path, cases(3, weak_to=["error"], nap=0.4))
    ran = _interrupted(proj, ["hunt", "--yes"], after_runs=2)
    assert ran.exit == CODES["interrupted"], ran
    (name,) = hunt_names(proj)
    before = {(r["meta"]["poisson_break"]["case"], r["seed"]) for r in stored(proj, name, "control")}
    kept = len(before)
    assert 1 <= kept <= len(proj.runs())
    shown = strip(ran.out)
    stop = [line for line in shown.splitlines() if line.startswith("stopped  ")]
    assert len(stop) == 1, shown
    assert holds_number(stop[0], str(kept)), stop
    commands = [shlex.split(c) for c in re.findall(r"next:\s+(.*\S)", shown)]
    assert commands == [[PROG, "hunt", "--hunt", name]], shown
    again = cli(proj, *commands[0][1:], *([] if "--yes" in commands[0] else ["--yes"]))
    assert again.exit == CODES["done"], again
    assert hunt_names(proj) == [name]
    rows = stored(proj, name, "control")
    assert len(rows) == 6
    assert len({(r["meta"]["poisson_break"]["case"], r["seed"]) for r in rows}) == 6
    made = [(r["case"], r["seed"]) for r in proj.runs()]
    assert all(made.count(cell) == 1 for cell in before), "a cell stored before the stop is not run again"


# ---------------------------------------------------------------------------
# the command's name
# ---------------------------------------------------------------------------


def test_every_command_the_hunt_names_starts_with_the_name_it_was_run_under(tmp_path: Path) -> None:
    proj = project(tmp_path)
    ran = cli(proj, "hunt", "--yes", prog="poisson break")
    assert ran.exit == CODES["done"], ran
    commands = nexts(ran)
    assert commands and all(c.startswith("poisson break ") for c in commands), commands
    assert "poisson-break" not in ran.out + ran.err


# ---------------------------------------------------------------------------
# point 7: going on with a hunt by its name
# ---------------------------------------------------------------------------


def test_hunt_given_a_hunt_that_is_not_there_is_refused_before_any_run(tmp_path: Path) -> None:
    proj = project(tmp_path, SOUND)
    refused_once(cli(proj, "hunt", "--yes", "--hunt", "nightly"), CODES["refused"])
    assert proj.runs() == []
    assert hunt_names(proj) == []


def test_hunt_given_a_stopped_hunt_goes_on_with_it(tmp_path: Path) -> None:
    """A hunt stopped by its dollar cap after one run, the cap then raised, and the command the stop printed run: no
    hunt is made, the cell stored before the stop is not run again, and the hunt ends."""
    proj = project(tmp_path, cases(3, weak_to=["error"], tokens=[1000, 0]),
                   limits={"dollars": 0.0015, "input_per_million": 1.0, "output_per_million": 1.0})
    first = cli(proj, "hunt", "--yes")
    assert first.exit == CODES["stopped"], first
    (name,) = hunt_names(proj)
    (stopped_at,) = [(r["case"], r["seed"]) for r in proj.runs()]
    text = proj.settings.read_text(encoding="utf-8")
    assert text.count("0.0015") == 1
    proj.settings.write_text(text.replace("0.0015", "1.0"), encoding="utf-8")
    command = shlex.split(nexts(first)[0])
    again = cli(proj, *command[1:], "--yes")
    assert again.exit == CODES["done"], again
    assert hunt_names(proj) == [name]
    assert [(r["case"], r["seed"]) for r in proj.runs()].count(stopped_at) == 1
    assert len(stored(proj, name, "control")) == 6


# ---------------------------------------------------------------------------
# point 12: the high base rate
# ---------------------------------------------------------------------------


def control_rate(proj: Project, name: str) -> str:
    """The control stage's rate as the look prints it, read back through the library (the stage is stored, so asking
    for it again runs nothing)."""
    import contextlib

    from poisson_break import look
    from poisson_break.hunt import control

    with contextlib.chdir(proj.folder):
        summary = control(opened(proj, name))
    return str(look.fmt_rate(summary.rate))


def test_a_control_that_fails_more_than_half_its_runs_is_a_note_carrying_its_rate(tmp_path: Path) -> None:
    """Point 12, spec §5.2, BK5.7: a `note:` on stderr when the control stage ends, carrying the control's rate."""
    proj = project(tmp_path, cases(6, rate=0.8, weak_to=["error"]), search={"control_repeats": 3, "runs": 120})
    ran = cli(proj, "hunt", "--yes")
    assert ran.exit == CODES["done"], ran
    (name,) = hunt_names(proj)
    rate = control_rate(proj, name)
    assert [n for n in notes(ran) if REAL not in n and holds_number(n, rate)], (rate, ran.err)


def test_a_control_that_fails_seldom_has_no_such_note(found: tuple[Project, Any]) -> None:
    """The found hunt's control failed none of its runs: its one note is the one after the plan."""
    proj, ran = found
    assert ran.exit == CODES["done"] and proj.runs(), ran
    assert [n for n in notes(ran) if REAL in n], "the hunt ran and printed its one note"
    assert [n for n in notes(ran) if REAL not in n] == [], ran.err


# ---------------------------------------------------------------------------
# point 13: "k of n failed" and the kind on a candidate's line
# ---------------------------------------------------------------------------


def last_rows(proj: Project, name: str, condition: str) -> list[dict[str, Any]]:
    """The stored rows of the stage that last ran `condition`: shrink's if it ran it, else search's."""
    for arm in ("shrink", "search"):
        if f"{name}-{arm}" not in store_runs(proj, name):
            continue
        rows = [r for r in stored(proj, name, arm)
                if r["meta"]["poisson_break"]["condition"]["name"] == condition]
        if rows:
            return rows
    raise AssertionError(f"no stage ran {condition}")


def main_kind(rows: list[dict[str, Any]]) -> str:
    """The kind most of the failed rows have, ties by the order of §4 (`records.KINDS`, then the signals)."""
    from poisson_break.records import KINDS, SIGNALS

    order = [*KINDS, *SIGNALS]
    kinds = [r["meta"]["poisson_break"]["failure"]["kind"] for r in rows if r["outcome"] == "failed"]
    most = max(kinds.count(k) for k in kinds)
    return min((k for k in kinds if kinds.count(k) == most), key=lambda k: order.index(k) if k in order else len(order))


def candidate_line(ran: Any, condition: str) -> str:
    block = result_of(ran, "found")
    found = [line for line in detail(block) if condition in line.split()]
    assert len(found) == 1, (condition, block)
    return found[0]


@pytest.fixture(scope="module")
def two_kinds(tmp_path_factory: pytest.TempPathFactory) -> tuple[Project, Any]:
    """A desk that fails about half its runs under `error` and crashes on every run under `timeout`: two candidates,
    one whose rows did not all fail, and one whose kind is not the word "failed"."""
    proj = project(tmp_path_factory.mktemp("kinds"), cases(8, weak=0.5, weak_to=["error"], crash_to=["timeout"]),
                   search={"control_repeats": 2, "runs": 300, "cases_per_condition": 6})
    return proj, cli(proj, "hunt", "--yes")


@pytest.mark.parametrize("hunted", ["found", "two_kinds"])
def test_a_candidate_s_line_carries_k_of_n_failed_from_the_stage_that_last_ran_it(
        hunted: str, request: pytest.FixtureRequest) -> None:
    proj, ran = request.getfixturevalue(hunted)
    assert ran.exit == CODES["done"], ran
    (name,) = hunt_names(proj)
    counts = []
    for condition in candidates(proj, name):
        rows = last_rows(proj, name, condition)
        failed = sum(r["outcome"] == "failed" for r in rows)
        counts.append((failed, len(rows)))
        line = candidate_line(ran, condition)
        assert re.search(rf"(?<!\d){failed} of {len(rows)} failed\b", line), (line, failed, len(rows))
    if hunted == "two_kinds":
        assert any(k < n for k, n in counts), f"a candidate whose rows did not all fail: {counts}"


def test_a_candidate_s_line_carries_the_kind_most_of_its_failed_rows_have(
        two_kinds: tuple[Project, Any]) -> None:
    proj, ran = two_kinds
    assert ran.exit == CODES["done"], ran
    (name,) = hunt_names(proj)
    kinds = {condition: main_kind(last_rows(proj, name, condition)) for condition in candidates(proj, name)}
    assert "crashed" in kinds.values(), kinds
    for condition, kind in kinds.items():
        words = candidate_line(ran, condition).split()
        assert kind in words, (kind, words)
        others = {"crashed", "wrong"} - {kind}
        assert not others & set(words), (kind, words)
