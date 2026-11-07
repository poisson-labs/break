"""`recheck`: the findings run on the agent as it is now, and Trace's answer for each, from the command.

Invariants held here (Break — Plan, the commands module; spec §6.2, §6.3, §9.1):
- BK8.14  `recheck --check` exits 4 when any finding fails more, and `--strict` adds too small to tell; Trace missing is
          one line before any run.
- BK8.13  The plan is shown and asked before any run, and `--dry-run` runs nothing.
- BK8.9   "Break calls your tools for real" after the plan, as a `note:` on stderr.
- BK8.2   `--json` is one strict document, with the same exit code (4 included).
- BK8.7   `recheck` works with no hunt named; the full report's command names runs, never a hash.
- §6.2    Per finding, one of the four phrases, with the rates before and now as the look prints them, and the Trace
          command for its full report; `--old ENTRY` runs the old and the new agent side by side.

One finding, `error` on the look-up, confirmed through the library on a desk failing a tenth of its control runs and
six tenths of its runs under `error`. The agent changed is the environment's: `BREAK_TEST_MENDED=1` mends it (it fails
less), `BREAK_TEST_WEAK=1.0` makes it worse (it fails more), and nothing set leaves it as it was, where the pinned
Trace says the first recheck is too small to tell.
"""

from __future__ import annotations

import contextlib
import re
import shlex
from pathlib import Path
from typing import Any

import pytest

from tests.commands_support import (
    CODES,
    PROG,
    REAL,
    Project,
    cases,
    cli,
    detail,
    errors,
    hashes,
    holds_number,
    json_document,
    notes,
    on,
    opened,
    prepared,
    project,
    result_of,
    results,
    store_runs,
    stored,
    verdict,
)
from tests.test_commands_confirm import stand_in

RECHECK = cases(12, rate=0.1, weak=0.6, weak_to=["error"])
SETTINGS: dict[str, Any] = {"confirm": {"repeats": 4}, "search": {"control_repeats": 3, "runs": 400}}


def with_a_finding(tmp_path: Path) -> Project:
    from poisson_break.confirm import confirm

    proj = project(tmp_path, RECHECK, **SETTINGS)
    prepared(proj, (on("error"),))
    with contextlib.chdir(proj.folder):
        done = confirm(opened(proj, "desk-1"))
    assert [f.number for f in done.findings] == [1]
    return proj


def line_of(ran: Any) -> str:
    block = result_of(ran, "rechecked")
    found = [line for line in detail(block) if line.split()[:2] == ["1", on("error")]]
    assert len(found) == 1, block
    return found[0]


def recheck_runs(proj: Project) -> list[str]:
    return [r for r in store_runs(proj, "desk-1") if "-recheck-" in r]


@pytest.fixture(scope="module")
def finding(tmp_path_factory: pytest.TempPathFactory) -> Project:
    return with_a_finding(tmp_path_factory.mktemp("recheck"))


# ---------------------------------------------------------------------------
# the four phrases and --check
# ---------------------------------------------------------------------------


def test_the_agent_mended_fails_less_and_the_numbers_are_trace_s(finding: Project) -> None:
    from poisson_break.look import fmt_rate

    made = recheck_runs(finding)
    ran = cli(finding, "recheck", "--yes", BREAK_TEST_MENDED="1")
    assert ran.exit == CODES["done"], ran
    final = results(ran.out)[-1]
    assert final[0].startswith("rechecked  "), ran
    text = line_of(ran)
    assert "fails less" in text
    (latest,) = [r for r in recheck_runs(finding) if r not in made]
    before = stored(finding, "desk-1", "reference-1")
    now = stored(finding, "desk-1", latest[len("desk-1-"):])

    def share(rows: list[dict[str, Any]]) -> float:
        return sum(r["outcome"] == "failed" for r in rows) / len(rows)

    assert holds_number(text, fmt_rate(share(before))) and holds_number(text, fmt_rate(share(now))), text


def test_with_check_the_agent_mended_exits_0(finding: Project) -> None:
    ran = cli(finding, "recheck", "--yes", "--check", BREAK_TEST_MENDED="1")
    assert ran.exit == CODES["done"], ran
    assert "fails less" in line_of(ran)


def test_with_check_a_finding_that_fails_more_exits_4(finding: Project) -> None:
    """BK8.14: the check asked for did not pass. The result is still printed, with the phrase on the finding's line."""
    ran = cli(finding, "recheck", "--yes", "--check", BREAK_TEST_WEAK="1.0")
    assert ran.exit == CODES["check"], ran
    assert "fails more" in line_of(ran)
    assert "Traceback" not in ran.err


def test_without_check_a_finding_that_fails_more_exits_0(finding: Project) -> None:
    ran = cli(finding, "recheck", "--yes", BREAK_TEST_WEAK="1.0")
    assert ran.exit == CODES["done"], ran
    assert "fails more" in line_of(ran)


def test_under_json_a_failed_check_is_one_document_and_still_exits_4(finding: Project) -> None:
    ran = cli(finding, "recheck", "--yes", "--check", "--json", BREAK_TEST_WEAK="1.0")
    assert ran.exit == CODES["check"], ran
    document = json_document(ran)
    assert list(document)[:3] == ["schema", "verdict", "sentence"]
    assert document["verdict"] == "rechecked"


def test_too_small_to_tell_fails_the_check_only_under_strict(tmp_path: Path) -> None:
    """The agent as it was, rechecked once with `--check` and once with `--check --strict`, each the first recheck of a
    fresh hunt, which the pinned Trace calls too small to tell: exit 0, then exit 4."""
    plain = with_a_finding(tmp_path / "plain")
    ran = cli(plain, "recheck", "--yes", "--check")
    assert "too small to tell" in line_of(ran), ran
    assert ran.exit == CODES["done"], ran
    strict = with_a_finding(tmp_path / "strict")
    ran = cli(strict, "recheck", "--yes", "--check", "--strict")
    assert "too small to tell" in line_of(ran), ran
    assert ran.exit == CODES["check"], ran


def test_strict_without_check_changes_no_exit_code(finding: Project) -> None:
    ran = cli(finding, "recheck", "--yes", "--strict", BREAK_TEST_WEAK="1.0")
    assert ran.exit == CODES["done"], ran


# ---------------------------------------------------------------------------
# what a recheck shows
# ---------------------------------------------------------------------------


def test_each_finding_s_full_report_is_trace_s_command_naming_runs_not_hashes(finding: Project) -> None:
    made = recheck_runs(finding)
    ran = cli(finding, "recheck", "--yes", BREAK_TEST_MENDED="1")
    (latest,) = [r for r in recheck_runs(finding) if r not in made and not r.endswith("-old")]
    shown = "\n".join(results(ran.out)[-1])
    commands = [shlex.split(m) for m in re.findall(r"(poisson-trace fix-check .*\S)", shown)]
    assert commands, shown
    words = commands[-1]
    assert words[2:4] == ["desk-1-reference-1", latest], words
    assert hashes((ran.out + ran.err).replace(str(finding.folder.parent), "")) == []


def test_old_runs_the_old_and_the_new_agent_side_by_side(finding: Project) -> None:
    """`recheck --old ENTRY`: the old agent's arm beside the new one's, under the recheck's number, and the old agent's
    own runs among what was made."""
    made = len(finding.runs())
    ran = cli(finding, "recheck", "--yes", "--old", "tests.commands_targets:old_desk", BREAK_TEST_MENDED="1")
    assert ran.exit == CODES["done"], ran
    runs = recheck_runs(finding)
    olds = [r for r in runs if r.endswith("-old")]
    assert olds, runs
    assert olds[-1][: -len("-old")] in runs
    assert {r["target"] for r in finding.runs()[made:]} == {"desk", "old_desk"}
    assert "fails less" in line_of(ran)


def test_the_note_follows_the_plan(finding: Project) -> None:
    ran = cli(finding, "recheck", "--yes", BREAK_TEST_MENDED="1")
    assert results(ran.out)[0][0].startswith("plan  ")
    assert [n for n in notes(ran) if REAL in n], ran.err


# ---------------------------------------------------------------------------
# the plan, refusals and which hunt
# ---------------------------------------------------------------------------


def test_a_dry_run_shows_the_plan_and_runs_nothing(finding: Project) -> None:
    arms = recheck_runs(finding)
    runs = len(finding.runs())
    ran = cli(finding, "recheck", "--dry-run")
    assert ran.exit == CODES["done"], ran
    assert verdict(ran)[0] == "plan"
    assert recheck_runs(finding) == arms and len(finding.runs()) == runs


def test_without_a_terminal_and_without_yes_the_plan_is_shown_and_refused(finding: Project) -> None:
    arms = recheck_runs(finding)
    ran = cli(finding, "recheck")
    assert ran.exit == CODES["refused"], ran
    assert verdict(ran)[0] == "plan"
    assert len(errors(ran)) == 1 and "--yes" in errors(ran)[0]
    assert recheck_runs(finding) == arms


def test_trace_missing_is_one_line_before_any_run(finding: Project, tmp_path: Path) -> None:
    arms = recheck_runs(finding)
    ran = cli(finding, "recheck", "--yes", **stand_in(finding, tmp_path, BREAK_TEST_TRACE_MISSING="1"))
    assert ran.exit == CODES["refused"], ran
    assert len(errors(ran)) == 1, ran
    assert recheck_runs(finding) == arms
    assert "Traceback" not in ran.err


def test_recheck_takes_the_latest_hunt_and_hunt_names_another(finding: Project) -> None:
    """A second hunt, with no finding, made after the first: named, the first is rechecked."""
    if "desk-2" not in [p.name for p in finding.hunts.iterdir()]:
        prepared(finding, (), name="desk-2")
    ran = cli(finding, "recheck", "--hunt", "desk-1", "--yes", BREAK_TEST_MENDED="1")
    assert ran.exit == CODES["done"], ran
    assert "fails less" in line_of(ran)


def test_every_command_recheck_names_starts_with_the_name_it_was_run_under(finding: Project) -> None:
    ran = cli(finding, "recheck", "--hunt", "desk-1", "--yes", prog="poisson break", BREAK_TEST_MENDED="1")
    assert ran.exit == CODES["done"], ran
    assert "poisson-break" not in ran.out + ran.err, ran
    assert PROG not in ran.out.replace("poisson-trace", "")
