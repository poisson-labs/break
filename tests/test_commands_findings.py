"""`findings` and `replay`: a hunt's findings listed and shown, and one run again, from the command.

Invariants held here (Break — Plan, the commands module; spec §9.1, §5.5 "What a finding carries", §6.1):
- BK8.7   `findings` and `replay` work with no hunt named, and `--hunt NAME` picks another; findings are numbers; the
          runs a finding names are named after their hunt and arm; nothing printed names a hash.
- BK0.2   Every command printed is rendered from the name the command was run under, the replay command among them.
- §9.1    `findings` lists the latest hunt's findings and `findings 2` shows one, verdict `ok`; `replay` runs one
          finding once and shows what the agent did, call by call, verdict `failed` or `did not fail`.
- §5.5    A finding shown carries what the spec says it carries, each number as the look prints it.
- §6.1    `replay` stores nothing.
- Point A (`evidence/bk7/rulings-build.md`): `findings` lists what `read_findings` hands back, a gap passed over and a
          file that cannot be read refused in one line.

Taylor's rulings on BK8's open points (2026-11-07), held here: `findings`, listing, adds under a `control` heading each
case that failed in the control, with its failed runs of its runs and its kinds, the cases set aside marked so (point
15); `replay --case ID` replays another of the finding's cases (point 16); `replay` asks nothing before its one run and
shows no plan, but prints the "Break calls your tools for real" note on stderr (point 17, with Taylor's addition); a
replay whose run was not counted says `stopped` with the run's one line of error as the sentence, and exits 3 (point
18); the schemas `poisson_break.findings-result/1` and `poisson_break.replay-result/1` (point 11).
"""

from __future__ import annotations

import contextlib
import dataclasses
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
    Project,
    cli,
    detail,
    files_under,
    findings_of,
    hashes,
    holds_number,
    json_document,
    nexts,
    notes,
    opened,
    prepared,
    project,
    refused_once,
    result_of,
    results,
    store_runs,
    stored,
    verdict,
)
from tests.look_support import strip


def confirmed(proj: Project, name: str = "desk-1") -> None:
    """The three candidates of `MIXED` confirmed through the library: one finding, `error` on the look-up."""
    from poisson_break.confirm import confirm

    prepared(proj, MIXED_CANDIDATES, name=name)
    with contextlib.chdir(proj.folder):
        confirm(opened(proj, name))


@pytest.fixture(scope="module")
def two(tmp_path_factory: pytest.TempPathFactory) -> Project:
    """A hunt with two findings: the confirmed one, and a copy of it written as finding 2 under another condition by
    `write_finding`, so `findings` has two lines to order."""
    from poisson_break.confirm import write_finding

    proj = project(tmp_path_factory.mktemp("two"), MIXED, **MIXED_SETTINGS)
    confirmed(proj)
    (one,) = findings_of(proj, "desk-1")
    with contextlib.chdir(proj.folder):
        write_finding(opened(proj, "desk-1"), dataclasses.replace(one, number=2, condition="tool:lookup_order#1=timeout"))
    return proj


def no_hash(ran: Any, proj: Project) -> None:
    assert hashes((ran.out + ran.err).replace(str(proj.folder.parent), "")) == [], ran


# ---------------------------------------------------------------------------
# findings
# ---------------------------------------------------------------------------


def test_findings_lists_each_finding_by_number_and_condition_in_order(two: Project) -> None:
    ran = cli(two, "findings")
    assert ran.exit == CODES["done"], ran
    block = result_of(ran, "ok")
    lines = detail(block)
    one = [i for i, line in enumerate(lines) if line.split()[:2] == ["1", "tool:lookup_order#1=error"]]
    two_at = [i for i, line in enumerate(lines) if line.split()[:2] == ["2", "tool:lookup_order#1=timeout"]]
    assert len(one) == 1 and len(two_at) == 1 and one[0] < two_at[0], block
    no_hash(ran, two)


def test_findings_lists_what_read_findings_hands_back_a_gap_passed_over(tmp_path: Path) -> None:
    """Point A, point 4: with `1.toml` and `3.toml` on disk, findings 1 and 3, and no 2."""
    from poisson_break.confirm import write_finding

    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    confirmed(proj)
    (one,) = findings_of(proj, "desk-1")
    with contextlib.chdir(proj.folder):
        write_finding(opened(proj, "desk-1"), dataclasses.replace(one, number=3))
    ran = cli(proj, "findings")
    assert ran.exit == CODES["done"], ran
    firsts = [line.split()[0] for line in detail(result_of(ran, "ok")) if re.match(r"\s+\d+\s", line)]
    assert firsts == ["1", "3"], ran


def test_a_finding_file_that_cannot_be_read_refuses_findings_in_one_line(tmp_path: Path) -> None:
    """Point A, point 6: nothing partial is listed."""
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    confirmed(proj)
    (proj.hunt("desk-1") / "findings" / "2.toml").write_text("this is = = not toml\n", encoding="utf-8")
    refused_once(cli(proj, "findings"), CODES["refused"])


def test_findings_with_none_says_ok_and_exits_0(tmp_path: Path) -> None:
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    ran = cli(proj, "findings")
    assert ran.exit == CODES["done"], ran
    assert verdict(ran)[0] == "ok"
    assert not [line for line in detail(result_of(ran, "ok")) if "tool:" in line]


def test_findings_with_no_hunt_is_refused(tmp_path: Path) -> None:
    refused_once(cli(project(tmp_path), "findings"), CODES["refused"])


def test_findings_under_json_is_one_strict_document(two: Project) -> None:
    ran = cli(two, "findings", "--json")
    assert ran.exit == CODES["done"], ran
    document = json_document(ran)
    assert list(document)[:3] == ["schema", "verdict", "sentence"]
    assert document["verdict"] == "ok"


def test_findings_takes_the_latest_hunt_and_hunt_names_another(tmp_path: Path) -> None:
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    confirmed(proj, "desk-1")
    prepared(proj, MIXED_CANDIDATES, name="desk-2")
    latest = cli(proj, "findings")
    assert not [line for line in detail(result_of(latest, "ok")) if "tool:" in line], latest
    named = cli(proj, "findings", "--hunt", "desk-1")
    assert [line for line in detail(result_of(named, "ok")) if "tool:lookup_order#1=error" in line], named
    refused_once(cli(proj, "findings", "--hunt", "nowhere"), CODES["refused"])


# ---------------------------------------------------------------------------
# findings N: one finding shown
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def shown(two: Project) -> tuple[Project, Any, Any]:
    (one, _) = findings_of(two, "desk-1")
    return two, cli(two, "findings", "1"), one


def test_one_finding_shown_says_ok_and_names_its_condition(shown: tuple[Project, Any, Any]) -> None:
    proj, ran, finding = shown
    assert ran.exit == CODES["done"], ran
    word, sentence = verdict(ran)
    assert word == "ok"
    assert finding.condition in strip(ran.out)


def test_one_finding_shown_carries_its_numbers_as_the_look_prints_them(shown: tuple[Project, Any, Any]) -> None:
    """Spec §5.5: the failure share under it and under the control; the difference with Trace's interval; the p-value,
    the adjusted p-value and `q`."""
    from poisson_break.look import fmt_p, fmt_rate

    proj, ran, f = shown
    text = strip(ran.out)
    for number in (fmt_rate(f.rate), fmt_rate(f.control_rate), fmt_rate(f.difference, signed=True),
                   fmt_rate(f.lo, signed=True), fmt_rate(f.hi, signed=True), fmt_p(f.p), fmt_p(f.adjusted_p),
                   fmt_p(f.q)):
        assert number.lstrip("+") in text, (number, text)


def test_one_finding_shown_carries_its_kinds_and_signals_with_their_counts(shown: tuple[Project, Any, Any]) -> None:
    proj, ran, f = shown
    text = strip(ran.out)
    assert f.kinds, "the finding failed, so it has kinds"
    for kind, count in f.kinds.items():
        assert re.search(rf"\b{re.escape(kind)}\b\D{{0,12}}\b{count}\b", text), (kind, count, text)
    for signal, count in f.signals.items():
        assert re.search(rf"\b{re.escape(signal)}\b\D{{0,12}}\b{count}\b", text), (signal, count, text)


def test_one_finding_shown_names_its_arms_and_its_reference_by_hunt_and_arm(shown: tuple[Project, Any, Any]) -> None:
    proj, ran, f = shown
    text = strip(ran.out)
    for run in (f.arm, f.control_arm, f.reference):
        assert run.startswith("desk-1-")
        assert re.search(rf"(?<![\w-]){re.escape(run)}(?![\w-])", text), (run, text)


def test_one_finding_shown_carries_its_cases_repeats_and_who_judged_it(shown: tuple[Project, Any, Any]) -> None:
    proj, ran, f = shown
    text = strip(ran.out)
    assert holds_number(text, str(len(f.cases))) and holds_number(text, str(f.repeats)), text
    assert f.judged_by in text


def test_one_finding_shown_gives_the_command_that_replays_it_and_trace_s_full_report(
        shown: tuple[Project, Any, Any]) -> None:
    """The replay command, run as printed, replays this finding; the Trace command is the finding's own, whole on one
    line, naming runs and no hash."""
    proj, ran, f = shown
    commands = [shlex.split(c) for c in nexts(ran)] + [shlex.split(line.strip()) for line in strip(ran.out).splitlines()
                                                       if line.strip().startswith(PROG + " replay")]
    replays = [c for c in commands if c[:3] == [PROG, "replay", "1"]]
    assert replays, ran
    assert replays[0][3:] in ([], ["--hunt", "desk-1"])
    assert any(f.trace == line.strip() or f.trace in line for line in strip(ran.out).splitlines()), ran
    no_hash(ran, proj)


def test_an_unknown_finding_number_is_refused(two: Project) -> None:
    refused_once(cli(two, "findings", "9"), CODES["refused"])


def test_a_finding_shown_under_another_name_renders_every_command_from_it(two: Project) -> None:
    """BK0.2: the replay command is printed from the name the command was run under, whatever the file holds."""
    ran = cli(two, "findings", "1", prog="poisson break")
    assert ran.exit == CODES["done"], ran
    assert "poisson-break" not in ran.out + ran.err, ran
    assert [c for c in nexts(ran) if c.startswith("poisson break replay 1")], ran


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def replayed(two: Project) -> tuple[Project, Any, dict[str, bytes], list[str], int]:
    before = files_under(two.hunts)
    arms = store_runs(two, "desk-1")
    runs = len(two.runs())
    return two, cli(two, "replay", "1"), before, arms, runs


def test_replay_runs_the_finding_once_and_says_it_failed(replayed: Any) -> None:
    proj, ran, before, arms, runs = replayed
    assert ran.exit == CODES["done"], ran
    assert verdict(ran)[0] == "failed"
    assert len(proj.runs()) == runs + 1


def test_replay_stores_nothing(replayed: Any) -> None:
    proj, ran, before, arms, runs = replayed
    assert ran.exit == CODES["done"] and len(proj.runs()) == runs + 1, "the replay ran"
    assert files_under(proj.hunts) == before
    assert store_runs(proj, "desk-1") == arms


def test_replay_shows_each_call_in_order_with_the_change_applied_to_it(replayed: Any) -> None:
    """The desk looks the order up, then reads the policy. The look-up is the call the finding's change landed on, and
    the policy is not; the case and seed it ran on are the run's facts."""
    proj, ran, before, arms, runs = replayed
    lines = detail(result_of(ran, "failed"))
    calls = [line for line in lines if re.search(r"\b(lookup_order|check_policy)\b", line)]
    assert [re.search(r"\b(lookup_order|check_policy)\b", c).group(1) for c in calls] == [  # type: ignore[union-attr]
        "lookup_order", "check_policy"], lines
    assert "tool:lookup_order#1=error" in calls[0]
    assert "tool:lookup_order#1=error" not in calls[1]
    made = proj.runs()[-1]
    text = strip(ran.out)
    assert re.search(rf"\b{made['case']}\b", text) and holds_number(text, str(made["seed"])), (made, text)


def test_replay_of_a_finding_that_no_longer_fails_says_did_not_fail(two: Project) -> None:
    ran = cli(two, "replay", "1", BREAK_TEST_MENDED="1")
    assert ran.exit == CODES["done"], ran
    assert verdict(ran)[0] == "did not fail"


def test_replay_of_an_unknown_finding_is_refused_and_runs_nothing(two: Project) -> None:
    runs = len(two.runs())
    refused_once(cli(two, "replay", "9"), CODES["refused"])
    assert len(two.runs()) == runs


def test_replay_under_json_is_one_strict_document(two: Project) -> None:
    ran = cli(two, "replay", "1", "--json")
    assert ran.exit == CODES["done"], ran
    document = json_document(ran)
    assert list(document)[:3] == ["schema", "verdict", "sentence"]
    assert document["verdict"] == "failed"


def test_replay_takes_the_latest_hunt_and_hunt_names_another(tmp_path: Path) -> None:
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    confirmed(proj, "desk-1")
    prepared(proj, MIXED_CANDIDATES, name="desk-2")
    refused_once(cli(proj, "replay", "1"), CODES["refused"])
    named = cli(proj, "replay", "1", "--hunt", "desk-1")
    assert named.exit == CODES["done"], named
    assert verdict(named)[0] == "failed"


# ---------------------------------------------------------------------------
# point 17: no plan and no question, and the note
# ---------------------------------------------------------------------------


def test_replay_shows_no_plan_and_asks_nothing(replayed: Any) -> None:
    """Run with stdin not a terminal and no `--yes`, it runs: nothing was asked. Its one result is the replay's."""
    proj, ran, before, arms, runs = replayed
    assert ran.exit == CODES["done"], ran
    assert [b[0].split("  ")[0] for b in results(ran.out)] == ["failed"], ran
    assert "[y/N]" not in ran.err


def test_replay_prints_break_calls_your_tools_for_real_as_a_note(replayed: Any) -> None:
    proj, ran, before, arms, runs = replayed
    assert [n for n in notes(ran) if REAL in n], ran.err


# ---------------------------------------------------------------------------
# point 16: another case
# ---------------------------------------------------------------------------


def test_replay_case_runs_the_case_named(two: Project) -> None:
    (finding, *_) = findings_of(two, "desk-1")
    default = cli(two, "replay", "1")
    chosen = two.runs()[-1]["case"]
    other = next(c for c in finding.cases if c != chosen)
    runs = len(two.runs())
    ran = cli(two, "replay", "1", "--case", other)
    assert default.exit == ran.exit == CODES["done"], ran
    assert len(two.runs()) == runs + 1
    assert two.runs()[-1]["case"] == other
    assert re.search(rf"\b{other}\b", strip(ran.out).splitlines()[0]), ran


def test_replay_of_a_case_the_finding_does_not_hold_is_refused_and_runs_nothing(two: Project) -> None:
    runs = len(two.runs())
    refused_once(cli(two, "replay", "1", "--case", "k404"), CODES["refused"])
    assert len(two.runs()) == runs


# ---------------------------------------------------------------------------
# point 18: a replay whose run was not counted
# ---------------------------------------------------------------------------


def test_a_replay_whose_run_was_not_counted_says_stopped_with_its_error_and_exits_3(two: Project) -> None:
    """The way in hands back something that is no episode: the run is Break's own failure, not counted. The result is
    `stopped`, its sentence the run's one line of error, exit 3; nothing is stored."""
    before = files_under(two.hunts)
    runs = len(two.runs())
    ran = cli(two, "replay", "1", BREAK_TEST_BROKEN="1")
    assert ran.exit == CODES["stopped"], ran
    word, sentence = verdict(ran)
    assert word == "stopped"
    assert sentence.strip() and "\n" not in sentence
    assert "Traceback" not in ran.err
    assert len(two.runs()) == runs + 1
    assert files_under(two.hunts) == before


# ---------------------------------------------------------------------------
# point 15: the control's failures in the listing
# ---------------------------------------------------------------------------


def control_failures(proj: Project, name: str) -> dict[str, tuple[int, int, list[str]]]:
    """Each case that failed in the control: its failed runs, its runs, and its kinds, from the control arm's rows."""
    held: dict[str, tuple[int, int, list[str]]] = {}
    for r in stored(proj, name, "control"):
        case = r["meta"]["poisson_break"]["case"]
        failed, ran, kinds = held.get(case, (0, 0, []))
        kind = r["meta"]["poisson_break"]["failure"]["kind"]
        if r["outcome"] == "failed" and kind not in kinds:
            kinds = [*kinds, kind]
        held[case] = (failed + (r["outcome"] == "failed"), ran + 1, kinds)
    return {case: value for case, value in held.items() if value[0]}


def set_aside(proj: Project, name: str) -> tuple[str, ...]:
    from poisson_break.hunt import control

    with contextlib.chdir(proj.folder):
        return tuple(control(opened(proj, name)).set_aside)


def under_control(ran: Any) -> list[str]:
    lines = detail(result_of(ran, "ok"))
    heads = [i for i, line in enumerate(lines) if line.split()[:1] == ["control"]]
    assert heads, f"no control heading: {lines}"
    return lines[heads[0]:]


def test_findings_lists_each_case_that_failed_in_the_control_under_its_own_heading(two: Project) -> None:
    ran = cli(two, "findings")
    assert ran.exit == CODES["done"], ran
    failing = control_failures(two, "desk-1")
    assert failing, "the mixed desk fails half its control runs"
    shown = under_control(ran)
    for case, (failed, runs, kinds) in failing.items():
        lines = [line for line in shown if case in re.findall(r"[\w.-]+", line)]
        assert len(lines) == 1, (case, shown)
        assert re.search(rf"(?<!\d){failed} of {runs}(?!\d)", lines[0]), (case, failed, runs, lines[0])
        for kind in kinds:
            assert kind in lines[0], (kind, lines[0])


def test_a_case_that_never_failed_in_the_control_is_not_listed_there(two: Project) -> None:
    ran = cli(two, "findings")
    failing = control_failures(two, "desk-1")
    every = {r["meta"]["poisson_break"]["case"] for r in stored(two, "desk-1", "control")}
    shown = "\n".join(under_control(ran))
    for case in every - set(failing):
        assert case not in re.findall(r"[\w.-]+", shown), (case, shown)


def test_the_cases_set_aside_are_marked_so_and_no_others(two: Project) -> None:
    ran = cli(two, "findings")
    aside = set_aside(two, "desk-1")
    assert aside, "one case of the mixed desk fails every control run"
    shown = under_control(ran)
    for line in shown:
        words = re.findall(r"[\w.-]+", line)
        named = [case for case in control_failures(two, "desk-1") if case in words]
        if named:
            assert ("set aside" in line) == (named[0] in aside), line


def test_a_case_s_line_under_control_carries_its_kinds(tmp_path: Path) -> None:
    """The mixed desk with one case more, `k99`, that falls over on every run: its line carries the kind `crashed` (and
    it is set aside, since it fails every control run)."""
    proj = project(tmp_path, [*MIXED, {"id": "k99", "input": "Where is order 99?", "crash": True}], **MIXED_SETTINGS)
    confirmed(proj)
    ran = cli(proj, "findings")
    assert ran.exit == CODES["done"], ran
    (line,) = [text for text in under_control(ran) if "k99" in re.findall(r"[\w.-]+", text)]
    assert "crashed" in line and "set aside" in line, line
    others = [text for text in under_control(ran)[1:] if "k99" not in text]
    assert others and not any("crashed" in text for text in others), others


# ---------------------------------------------------------------------------
# point 11: the schemas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("words", "schema"), [(["findings"], "findings-result"), (["findings", "1"], "findings-result"),
                                               (["replay", "1"], "replay-result")])
def test_each_document_is_named_after_its_verb(two: Project, words: list[str], schema: str) -> None:
    ran = cli(two, *words, "--json")
    assert ran.exit == CODES["done"], ran
    assert json_document(ran)["schema"] == f"poisson_break.{schema}/1"
