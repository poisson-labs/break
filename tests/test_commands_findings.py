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
    Project,
    cli,
    detail,
    files_under,
    findings_of,
    hashes,
    holds_number,
    json_document,
    nexts,
    opened,
    prepared,
    project,
    refused_once,
    result_of,
    store_runs,
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
