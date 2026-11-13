"""`confirm`: the confirm and reference stages from the command.

Invariants held here (Break — Plan, the commands module; spec §9.1, §9.2, §5.5, §6.2):
- BK8.2   `--json` is one strict document, with the same exit code.
- BK8.7   `confirm` works with no hunt named, and `--hunt NAME` picks another; nothing printed names a hash; the
          next command is `findings 1`.
- BK8.9   "Break calls your tools for real" after the plan, as a `note:` on stderr.
- BK8.13  The plan is shown and asked before any run, `--dry-run` runs nothing, and a stop prints what was kept and
          exits 3.
- BK8.14  Trace missing, of another version or printing another schema is one line before any run; a candidate that
          failed less is shown with its note.
- BK7.4   The cost in the plan is `plan_confirm`'s.
- §5.5    Per candidate, its verdict; the numbers on a line are Trace's, as the look prints them; too small to tell
          carries the repeats that would decide; a finished stage asked again runs nothing and gives the same answer;
          `--repeats N` asks again about what was too small to tell.
- trace#31 (fixed in Trace 0.1.0a1, the pin): a stage whose control arm and one candidate's arm hold no failed run
          is answered, that candidate too small to tell. No answer from Trace, which the stand-in still gives, is
          reported as the confirm module refuses it, in one line with a refusal's exit code, not as a crash.

Taylor's rulings on BK8's open points (2026-11-07), held here: under `--json` only the result's document (point 6);
no answer from Trace exits 1 (point 8); "start?" answered no runs nothing, exits 0 and says `stopped  nothing was run`
(point 9); `--dry-run` writes nothing (point 10); the schema `poisson_break.confirm-result/1` (point 11); a refusal known
before the plan prints no plan (point 14); and `not after the correction` is shown on its candidate's line as `failed
less` is (point 21). `nothing to compare` is not reached through a stage that runs: an arm with no case left to compare
has every run not counted, and the hunt module stops such an arm first (BK5's tenth), so no test here holds it.

The hunts here are made through the library (`commands_support.prepared`): the control stage run and the candidates
written, as `hunt` leaves them. Every answer is the pinned Trace's own, installed beside Break; the refusals of Trace
use the stand-in of the confirm module's tests (`tests/trace_stand_in`), which answers `--version` and the probe.
"""

from __future__ import annotations

import contextlib
import os
import re
import shlex
from pathlib import Path
from typing import Any

import pytest

from tests.commands_support import (
    CODES,
    MIXED,
    MIXED_CANDIDATES,
    MIXED_SETTINGS,
    PROG,
    REAL,
    SOUND,
    detail,
    result_of,
    results,
    Project,
    cases,
    cli,
    errors,
    files_under,
    paths_under,
    findings_of,
    hashes,
    holds_number,
    json_document,
    nexts,
    no_two_alike,
    notes,
    on,
    opened,
    out_lines,
    prepared,
    project,
    refused_once,
    store_runs,
    stored,
    verdict,
    written_difference,
    written_rate,
)
from tests.conftest import GUARD, REPO
from tests.look_support import VERDICT_LINE, Streams, strip

STAND_IN = REPO / "tests" / "trace_stand_in"
RECORDED = REPO / "tests" / "trace_recorded" / "fix_check_7e6fef6.jsonl"


def stand_in(proj: Project, tmp_path: Path, **env: str) -> dict[str, str]:
    """The child's environment with the stand-in for Trace first on its import path (`tests/confirm_support.py`)."""
    log = tmp_path / "trace-calls.jsonl"
    log.touch()
    return {"PYTHONPATH": os.pathsep.join([str(STAND_IN), str(GUARD), str(REPO / "src"), str(REPO)]),
            "BREAK_TEST_TRACE_LOG": str(log), "BREAK_TEST_TRACE_RECORDED": str(RECORDED), **env}


def line_of(block: list[str], number: int) -> str:
    found = [line for line in detail(block) if line.split()[:1] == [str(number)]]
    assert len(found) == 1, f"no single line for candidate {number}: {block}"
    return found[0]


def again(proj: Project, name: str) -> Any:
    """The finished stage asked again through the library, which runs nothing: its `Confirmation`, as Trace answers."""
    from poisson_break.confirm import confirm

    with contextlib.chdir(proj.folder):
        return confirm(opened(proj, name))


# ---------------------------------------------------------------------------
# one confirm stage with three answers, read by many tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mixed(tmp_path_factory: pytest.TempPathFactory) -> tuple[Project, Any, Any]:
    proj = project(tmp_path_factory.mktemp("mixed"), MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    ran = cli(proj, "confirm", "--yes")
    return proj, ran, again(proj, "desk-1")


def test_a_stage_with_a_finding_says_confirmed_and_exits_0(mixed: tuple[Project, Any, Any]) -> None:
    proj, ran, done = mixed
    assert ran.exit == CODES["done"], ran
    word, sentence = VERDICT_LINE.match(result_of(ran, "confirmed")[0]).groups()  # type: ignore[union-attr]
    assert [t.verdict for t in done.tested] == ["confirmed", "too small to tell", "not confirmed"]
    assert holds_number(sentence, "1") and holds_number(sentence, "3"), sentence


def test_each_candidate_s_line_carries_its_number_condition_and_verdict(mixed: tuple[Project, Any, Any]) -> None:
    proj, ran, done = mixed
    block = result_of(ran, "confirmed")
    for t in done.tested:
        text = line_of(block, t.number)
        assert t.condition in text
        assert re.search(rf"(?<![a-z]){re.escape(t.verdict)}(?![a-z])", text), text
    assert "not confirmed" not in line_of(block, 1)


def numbers_of(block: list[str], t: Any) -> str:
    """The numbers cell of a candidate's line: the line is its number, its condition, its verdict with its note, and
    then the numbers, and nothing else."""
    said = t.verdict + (f", {t.note}" if t.note else "")
    match = re.fullmatch(rf" +{t.number} +{re.escape(t.condition)} +{re.escape(said)} {{2,}}(\S.*)",
                         line_of(block, t.number))
    assert match is not None, line_of(block, t.number)
    return match.group(1)


def test_the_confirmed_candidate_s_numbers_are_trace_s_as_the_look_prints_them(mixed: tuple[Project, Any, Any]) -> None:
    """Spec §9.2: the rate under the candidate, then the difference with its sign, then Trace's interval in brackets,
    low end before high, each end with its sign. Each number is held to its exact written form and to its own place on
    the line. No two of the fixture's numbers print alike, the control's rate among them, so one printed in another's
    place, a pair swapped, or the interval's ends turned round cannot read the same; and each is written here apart
    from the look's own formatting, so a sign the look dropped is seen."""
    proj, ran, done = mixed
    t = done.tested[0]
    assert t.verdict == "confirmed"
    shown = {"rate": written_rate(t.rate), "difference": written_difference(t.difference),
             "lo": written_difference(t.lo), "hi": written_difference(t.hi),
             "control rate": written_rate(t.control_rate)}
    no_two_alike(shown)
    assert t.lo < t.difference < t.hi
    block = result_of(ran, "confirmed")
    assert numbers_of(block, t) == (f"{shown['rate']}   {shown['difference']} "
                                    f"({shown['lo']} to {shown['hi']})"), line_of(block, 1)
    word, sentence = VERDICT_LINE.match(block[0]).groups()  # type: ignore[union-attr]
    assert sentence.endswith(f" ({shown['control rate']})"), sentence
    assert len(re.findall(r"\d\.\d{3}", sentence)) == 1, sentence


def test_a_candidate_that_failed_less_prints_each_number_with_its_minus_sign(mixed: tuple[Project, Any, Any]) -> None:
    """The same line for the candidate that failed less: its difference and both ends of its interval are below
    zero, and each is printed with its minus sign, low end before high."""
    proj, ran, done = mixed
    t = done.tested[2]
    assert t.note == "failed less" and t.lo < t.difference < t.hi < 0
    shown = {"rate": written_rate(t.rate), "difference": written_difference(t.difference),
             "lo": written_difference(t.lo), "hi": written_difference(t.hi)}
    no_two_alike(shown)
    assert all(shown[name].startswith("-") for name in ("difference", "lo", "hi")), shown
    assert numbers_of(result_of(ran, "confirmed"), t) == (f"{shown['rate']}   {shown['difference']} "
                                                          f"({shown['lo']} to {shown['hi']})")


def test_too_small_to_tell_carries_trace_s_repeats_that_would_decide(mixed: tuple[Project, Any, Any]) -> None:
    proj, ran, done = mixed
    t = done.tested[1]
    assert t.repeats_needed
    assert holds_number(line_of(result_of(ran, "confirmed"), 2), str(t.repeats_needed))


def test_a_candidate_that_failed_less_is_shown_with_its_note(mixed: tuple[Project, Any, Any]) -> None:
    """BK8.14, BK7.9."""
    proj, ran, done = mixed
    assert done.tested[2].note == "failed less"
    assert "failed less" in line_of(result_of(ran, "confirmed"), 3)
    assert "failed less" not in line_of(result_of(ran, "confirmed"), 1)


def test_a_candidate_not_confirmed_after_the_correction_is_shown_with_its_note(tmp_path: Path) -> None:
    """Point 21. The mixed stage with q at 1e-12: `error` fails more by Trace (its p is about 1e-8) but not after
    Prove's correction at that q, so it is not confirmed, with the note `not after the correction`; the others keep
    their own notes."""
    proj = project(tmp_path, MIXED, confirm={"repeats": 4, "q": 1e-12}, search={"control_repeats": 3, "runs": 400})
    prepared(proj, MIXED_CANDIDATES)
    ran = cli(proj, "confirm", "--yes")
    assert ran.exit == CODES["done"], ran
    done = again(proj, "desk-1")
    assert [t.note for t in done.tested] == ["not after the correction", None, "failed less"]
    block = result_of(ran, "nothing confirmed")
    assert "not after the correction" in line_of(block, 1)
    assert "not confirmed" in line_of(block, 1)
    assert "not after the correction" not in line_of(block, 2) + line_of(block, 3)
    assert "failed less" in line_of(block, 3)


def test_the_finding_file_written_is_named_and_there(mixed: tuple[Project, Any, Any]) -> None:
    proj, ran, done = mixed
    (finding,) = findings_of(proj, "desk-1")
    assert finding.condition == on("error")
    block = "\n".join(result_of(ran, "confirmed"))
    assert "break-runs/desk-1/findings/1.toml" in block or "findings/1.toml" in block, block


def test_the_reference_stage_is_a_detail_line_with_its_runs(mixed: tuple[Project, Any, Any]) -> None:
    """BK8.1: one finding, 11 cases at 4 repeats: 44 reference runs, which the store holds."""
    proj, ran, done = mixed
    assert len(stored(proj, "desk-1", "reference-1")) == 44
    reference = [line for line in detail(result_of(ran, "confirmed")) if line.split()[:1] == ["reference"]]
    assert len(reference) == 1 and holds_number(reference[0], "44"), reference


def test_findings_1_is_the_next_command(mixed: tuple[Project, Any, Any]) -> None:
    proj, ran, done = mixed
    commands = [shlex.split(c) for c in nexts(ran)]
    assert [c for c in commands if c[:3] == [PROG, "findings", "1"] and c[3:] in ([], ["--hunt", "desk-1"])], ran


def test_the_plan_is_shown_first_with_plan_confirm_s_counts(mixed: tuple[Project, Any, Any]) -> None:
    """BK7.4: (1 + 3) × 11 × 4 = 176 runs, then up to 132, 44 for each finding; and Trace's largest difference."""
    from poisson_break.settings import load, plan_confirm

    proj, ran, done = mixed
    plan = results(ran.out)[0]
    assert plan[0].startswith("plan  ")
    counts = plan_confirm(load(proj.settings), cases=11, candidates=3)
    text = "\n".join(plan)
    for number in (counts.confirm_runs, counts.reference_runs, counts.reference_per_finding):
        assert holds_number(text, f"{number:,}"), (number, text)
    assert holds_number(text, "0.200"), text


def test_the_note_follows_the_plan(mixed: tuple[Project, Any, Any]) -> None:
    proj, ran, done = mixed
    assert [n for n in notes(ran) if REAL in n], ran.err


def test_nothing_printed_names_a_hash(mixed: tuple[Project, Any, Any]) -> None:
    proj, ran, done = mixed
    assert ran.exit == CODES["done"] and result_of(ran, "confirmed"), ran
    assert hashes((ran.out + ran.err).replace(str(proj.folder.parent), "")) == []


def test_a_finished_stage_asked_again_runs_nothing_and_gives_the_same_answer(mixed: tuple[Project, Any, Any]) -> None:
    proj, ran, done = mixed
    rows = {arm: len(stored(proj, "desk-1", arm)) for arm in ("confirm-control", "confirm-1", "reference-1")}
    made = len(proj.runs())
    second = cli(proj, "confirm", "--yes")
    assert second.exit == CODES["done"], second
    assert result_of(second, "confirmed") == result_of(ran, "confirmed")
    assert {arm: len(stored(proj, "desk-1", arm)) for arm in rows} == rows
    assert len(proj.runs()) == made


# ---------------------------------------------------------------------------
# asking again with --repeats
# ---------------------------------------------------------------------------


def test_repeats_asks_again_about_what_was_too_small_to_tell(tmp_path: Path) -> None:
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    assert cli(proj, "confirm", "--yes").exit == CODES["done"]
    ran = cli(proj, "confirm", "--repeats", "6", "--yes")
    assert ran.exit == CODES["done"], ran
    runs = store_runs(proj, "desk-1")
    assert "desk-1-confirm-2-control" in runs and "desk-1-confirm-2-2" in runs
    assert "desk-1-confirm-2-1" not in runs and "desk-1-confirm-2-3" not in runs
    assert len(stored(proj, "desk-1", "confirm-2-2")) == 11 * 6
    final = [b for b in results(ran.out) if not b[0].startswith("plan  ")]
    assert len(final) == 1
    assert [line for line in detail(final[0]) if on("timeout") in line], final


def test_repeats_with_no_stage_is_refused_before_any_plan_and_runs_nothing(tmp_path: Path) -> None:
    """Point 14: known before any plan, so no plan is printed: one `error:` line and nothing on stdout."""
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    ran = cli(proj, "confirm", "--repeats", "6", "--yes")
    refused_once(ran, CODES["refused"])
    assert "desk-1-confirm-control" not in store_runs(proj, "desk-1")


def test_repeats_with_nothing_too_small_to_tell_is_refused_before_any_plan(tmp_path: Path) -> None:
    """Point 14: a finished stage with nothing left to ask again about."""
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, (on("error"),))
    assert cli(proj, "confirm", "--yes").exit == CODES["done"]
    runs = store_runs(proj, "desk-1")
    ran = cli(proj, "confirm", "--repeats", "6", "--yes")
    refused_once(ran, CODES["refused"])
    assert store_runs(proj, "desk-1") == runs


def test_repeats_on_an_unfinished_stage_is_refused_before_any_plan(tmp_path: Path) -> None:
    """Point 14: a stage its cap stopped is not finished, so there is nothing to ask again yet."""
    priced = [{**c, "tokens": [1000, 0]} for c in MIXED]
    proj = project(tmp_path, priced, confirm={"repeats": 4}, search={"control_repeats": 3, "runs": 400},
                   limits={"dollars": 0.0375, "input_per_million": 1.0, "output_per_million": 1.0})
    prepared(proj, MIXED_CANDIDATES)
    assert cli(proj, "confirm", "--yes").exit == CODES["stopped"]
    rows = len(stored(proj, "desk-1", "confirm-control"))
    ran = cli(proj, "confirm", "--repeats", "6", "--yes")
    refused_once(ran, CODES["refused"])
    assert len(stored(proj, "desk-1", "confirm-control")) == rows


# ---------------------------------------------------------------------------
# the plan, --dry-run, --json, and which hunt
# ---------------------------------------------------------------------------


def test_a_dry_run_shows_the_plan_and_runs_nothing(tmp_path: Path) -> None:
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    ran = cli(proj, "confirm", "--dry-run")
    assert ran.exit == CODES["done"], ran
    assert verdict(ran)[0] == "plan"
    assert holds_number(strip(ran.out), "176")
    assert proj.runs() == []
    assert not [r for r in store_runs(proj, "desk-1") if "confirm" in r]
    assert [n for n in notes(ran) if REAL in n]


def test_without_a_terminal_and_without_yes_the_plan_is_shown_and_refused(tmp_path: Path) -> None:
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    ran = cli(proj, "confirm")
    assert ran.exit == CODES["refused"], ran
    assert verdict(ran)[0] == "plan"
    assert len(errors(ran)) == 1 and "--yes" in errors(ran)[0]
    assert not [r for r in store_runs(proj, "desk-1") if "confirm" in r]


def test_confirm_under_json_is_one_strict_document(tmp_path: Path) -> None:
    """Points 6 and 11: the result's document only, `confirm-result`."""
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    ran = cli(proj, "confirm", "--yes", "--json")
    assert ran.exit == CODES["done"], ran
    document = json_document(ran)
    assert list(document)[:3] == ["schema", "verdict", "sentence"]
    assert document["verdict"] == "confirmed"
    assert document["schema"] == "poisson_break.confirm-result/1"


def test_under_json_without_a_terminal_the_plan_is_the_document_and_the_refusal_on_stderr(tmp_path: Path) -> None:
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    ran = cli(proj, "confirm", "--json")
    assert ran.exit == CODES["refused"], ran
    assert json_document(ran)["verdict"] == "plan"
    assert len(errors(ran)) == 1 and "--yes" in errors(ran)[0]
    assert not [r for r in store_runs(proj, "desk-1") if "confirm" in r]


def test_start_answered_no_runs_nothing_and_says_so(tmp_path: Path) -> None:
    """Point 9."""
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    ran = cli(proj, "confirm", streams=Streams(stdin="pty", keys=(b"n\r",)))
    assert ran.exit == CODES["done"], ran
    assert [b[0].split("  ")[0] for b in results(ran.out)] == ["plan", "stopped"], ran
    assert results(ran.out)[-1][0] == "stopped  nothing was run"
    assert not [r for r in store_runs(proj, "desk-1") if "confirm" in r]


def test_a_dry_run_writes_nothing(tmp_path: Path) -> None:
    """Point 10: no `confirm.json`, no arm, nothing else, under `--json` too."""
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    before, paths = files_under(proj.folder), paths_under(proj.folder)
    for words in (["confirm", "--dry-run"], ["confirm", "--dry-run", "--json"]):
        assert cli(proj, *words, PYTHONDONTWRITEBYTECODE="1").exit == CODES["done"]
        assert files_under(proj.folder) == before
        assert paths_under(proj.folder) == paths


def test_confirm_takes_the_latest_hunt_and_hunt_names_another(tmp_path: Path) -> None:
    """desk-1 has three candidates; desk-2, made after it and so the latest, has none. With no hunt named, `confirm`
    reads desk-2 and is refused; named, desk-1 is planned."""
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES, name="desk-1")
    prepared(proj, (), name="desk-2")
    latest = cli(proj, "confirm", "--yes")
    refused_once(latest, CODES["refused"])
    named = cli(proj, "confirm", "--hunt", "desk-1", "--dry-run")
    assert named.exit == CODES["done"], named
    assert holds_number(verdict(named)[1], "3"), named


def test_a_hunt_named_that_is_not_there_is_refused(tmp_path: Path) -> None:
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    refused_once(cli(proj, "confirm", "--hunt", "nowhere", "--yes"), CODES["refused"])


def test_with_no_hunt_at_all_confirm_is_refused(tmp_path: Path) -> None:
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    ran = cli(proj, "confirm", "--yes")
    refused_once(ran, CODES["refused"])
    assert proj.runs() == []


def test_every_command_confirm_names_starts_with_the_name_it_was_run_under(tmp_path: Path) -> None:
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    ran = cli(proj, "confirm", "--yes", prog="poisson break")
    assert ran.exit == CODES["done"], ran
    assert nexts(ran) and all(c.startswith("poisson break ") for c in nexts(ran)), ran


# ---------------------------------------------------------------------------
# Trace refused before any run (BK8.14, BK7.19)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("how", ["missing", "version", "schema"])
def test_trace_missing_of_another_version_or_schema_is_one_line_before_any_run(tmp_path: Path, how: str) -> None:
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    env = {"missing": {"BREAK_TEST_TRACE_MISSING": "1"},
           "version": {"BREAK_TEST_TRACE_VERSION": "0.0.1"},
           "schema": {"BREAK_TEST_TRACE_PATCH": '{"*": {"set": {"schema": "poisson-trace.fix-check/9"}}}'}}[how]
    ran = cli(proj, "confirm", "--yes", **stand_in(proj, tmp_path, **env))
    assert ran.exit == CODES["refused"], ran
    assert len(errors(ran)) == 1, ran
    assert "Traceback" not in ran.err
    assert not [r for r in store_runs(proj, "desk-1") if "confirm" in r]
    assert not (proj.hunt("desk-1") / "findings").exists()
    assert not (proj.home / ".cache" / "poisson-break" / "errors.log").exists()


def test_the_stand_in_answers_the_same_stage_when_nothing_is_wrong(tmp_path: Path) -> None:
    """The control for the three refusals above: the same stand-in, unpatched, lets the stage start (it then has no
    recorded document for these counts and stops the stage as no answer, after the runs: those runs are the proof the
    refusal above came first)."""
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    cli(proj, "confirm", "--yes", **stand_in(proj, tmp_path))
    assert "desk-1-confirm-control" in store_runs(proj, "desk-1")


# ---------------------------------------------------------------------------
# trace#31: neither arm failed, and no answer from Trace
# ---------------------------------------------------------------------------


def test_a_stage_where_neither_arm_failed_is_answered_by_the_pinned_trace(tmp_path: Path) -> None:
    """A desk that never fails but under `error`: the control arm and `timeout`'s arm hold no failed run. The pinned
    Trace answers `--event failed` for them (poisson-labs/trace#31, fixed in 0.1.0a1; before it Trace refused the
    event and the stage had no answer): `timeout` is too small to tell, with the repeats that would decide, and `error`
    is confirmed and written as the one finding."""
    proj = project(tmp_path, SOUND)
    proj.write(case_list=cases(3, weak_to=["error"]))
    prepared(proj, (on("error"), on("timeout")))
    ran = cli(proj, "confirm", "--yes")
    assert ran.exit == CODES["done"], ran
    assert not errors(ran), ran
    assert "Traceback" not in ran.err
    by_condition = {line.split()[1]: line for line in out_lines(ran) if line.split()[:1] in (["1"], ["2"])}
    assert "confirmed" in by_condition[on("error")], ran
    assert "too small to tell" in by_condition[on("timeout")], ran
    assert re.search(r"\d+ repeats would decide", by_condition[on("timeout")]), ran
    assert sorted(p.name for p in (proj.hunt("desk-1") / "findings").iterdir()) == ["1.toml"]
    assert {"desk-1-confirm-control", "desk-1-confirm-1", "desk-1-confirm-2"} <= set(store_runs(proj, "desk-1"))


def test_no_answer_from_trace_is_one_refusal_line_not_a_crash(tmp_path: Path) -> None:
    """The same desk asked of the stand-in, which holds no recorded document for these counts and so prints no JSON:
    no answer from Trace. The confirm module refuses the stage as no answer from Trace, with the runs kept and no
    finding written; the command prints that refusal as one `error:` line and exits as a refusal does. No traceback,
    no errors log, and no result but the plan on stdout."""
    proj = project(tmp_path, SOUND)
    proj.write(case_list=cases(3, weak_to=["error"]))
    prepared(proj, (on("error"), on("timeout")))
    ran = cli(proj, "confirm", "--yes", **stand_in(proj, tmp_path))
    assert ran.exit == CODES["refused"], ran
    assert len(errors(ran)) == 1, ran
    assert "Traceback" not in ran.err
    assert not (proj.home / ".cache" / "poisson-break" / "errors.log").exists()
    assert [b[0].split("  ")[0] for b in results(ran.out)] == ["plan"], ran
    assert not (proj.hunt("desk-1") / "findings").exists()
    assert {"desk-1-confirm-control", "desk-1-confirm-1", "desk-1-confirm-2"} <= set(store_runs(proj, "desk-1"))


# ---------------------------------------------------------------------------
# a stage that stops short
# ---------------------------------------------------------------------------


def test_a_confirm_stage_stopped_by_the_dollar_cap_prints_what_was_kept_and_exits_3(tmp_path: Path) -> None:
    """Each run costs $0.001. The control's 36 runs spend $0.036; a cap of $0.0375 lets one confirm run through."""
    priced = [{**c, "tokens": [1000, 0]} for c in MIXED]
    proj = project(tmp_path, priced, confirm={"repeats": 4}, search={"control_repeats": 3, "runs": 400},
                   limits={"dollars": 0.0375, "input_per_million": 1.0, "output_per_million": 1.0})
    prepared(proj, MIXED_CANDIDATES)
    ran = cli(proj, "confirm", "--yes")
    assert ran.exit == CODES["stopped"], ran
    block = result_of(ran, "stopped")
    assert len(stored(proj, "desk-1", "confirm-control")) == 1
    assert holds_number("\n".join(block), "1"), block
    assert nexts(ran)
    assert out_lines(ran)
