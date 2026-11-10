"""S3: a Ctrl-C document of `confirm` counts the reference arms of the findings the stage confirmed as the stage's own.

Ruled 2026-11-09 (Break — Decisions; `evidence/bk8f/README.md` S3): `confirm` runs each confirmed finding's reference
arm as its last step, and its plan counts those runs, so a stop during one keeps them among the stage's. Held here:
Ctrl-C during the reference arm of the finding stage 1 confirmed gives `kept` as the rows of the stage's two arms and
of that reference arm, and `arm` as the reference arm. And the other side: a stage asked again that confirmed nothing
yet does not count the reference arm of a finding an earlier stage confirmed.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from tests import commands_hunts as hunts
from tests.commands_support import (
    CODES,
    MIXED,
    Project,
    cases,
    child_env,
    findings_of,
    holds_number,
    json_document,
    on,
    prepared,
    project,
    stored,
)
from tests.look_support import Ran


def interrupted_json(proj: Project, words: list[str], after_runs: int) -> dict[str, Any]:
    """The command on pipes under `--json`, sent Ctrl-C once its target has started `after_runs` runs."""
    process = subprocess.Popen([sys.executable, "-m", "poisson_break", *words], cwd=proj.folder,
                               env=child_env(proj), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True,
                               preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))  # noqa: PLW1509
    deadline = time.monotonic() + 180
    while len(proj.runs()) < after_runs:
        assert process.poll() is None, process.communicate()
        assert time.monotonic() < deadline, "the runs did not start"
        time.sleep(0.05)
    os.killpg(process.pid, signal.SIGINT)
    out, err = process.communicate(timeout=120)
    assert process.returncode == CODES["interrupted"], (process.returncode, out, err)
    return json_document(Ran(process.returncode, out.decode(), err.decode()))


def interrupted_in_run(proj: Project, words: list[str], run: int, tmp_path: Path) -> dict[str, Any]:
    """The command on pipes under `--json`, sent Ctrl-C while the run that is line `run` of the runs log is held where
    it starts. That run says it has begun by writing a file, and waits; nothing here is timed. The command is waited
    on to end by itself, so a file that never comes is a command that ended, which fails."""
    marker = tmp_path / "held"
    process = subprocess.Popen([sys.executable, "-m", "poisson_break", *words], cwd=proj.folder,
                               env=child_env(proj, BREAK_TEST_HOLD_AT=str(run), BREAK_TEST_HOLD_FILE=str(marker)),
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True,
                               preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))  # noqa: PLW1509
    while not marker.exists():
        assert process.poll() is None, ("the command ended before the run was held", process.communicate())
        time.sleep(0.01)
    assert len(proj.runs()) == run, "the held run is the last one started"
    os.killpg(process.pid, signal.SIGINT)
    out, err = process.communicate(timeout=120)
    assert process.returncode == CODES["interrupted"], (process.returncode, out, err)
    assert len(proj.runs()) == run, "no run started after the one interrupted"
    return json_document(Ran(process.returncode, out.decode(), err.decode()))


def test_ctrl_c_during_a_reference_arm_keeps_it_among_the_stage_s_own(tmp_path: Path) -> None:
    """Three cases at four repeats: the stage's control arm and its candidate's arm are twelve runs each, the
    candidate is confirmed and finding 1 written, and its reference arm is twelve more. Ctrl-C comes once the
    reference arm's second run has begun, which the run itself says: the command's 26th run is held where it starts.
    So the reference arm holds its first run and no other, and `kept` is the stage's two arms and that one row: 25."""
    proj = project(tmp_path, cases(3, weak_to=["error"]), confirm={"repeats": 4}, search={"control_repeats": 1})
    prepared(proj, (on("error"),))
    assert proj.runs() == [], "the hunt was prepared in this process: the log counts the command's runs alone"
    document = interrupted_in_run(proj, ["confirm", "--yes", "--json"], 12 + 12 + 2, tmp_path)
    assert document["schema"] == "poisson_break.confirm-result/1" and document["verdict"] == "stopped"
    assert (document["hunt"], document["reason"], document["unclassed"]) == ("desk-1", "interrupted", [])
    counts = hunts.stored_counts(proj)
    assert [finding.number for finding in findings_of(proj, "desk-1")] == [1]
    assert (counts["confirm-control"], counts["confirm-1"], counts["reference-1"]) == (12, 12, 1), counts
    assert document["kept"] == 25
    assert document["arm"] == "desk-1-reference-1"
    assert holds_number(document["sentence"], "25"), document["sentence"]
    held = proj.runs()
    reference = stored(proj, "desk-1", "reference-1")
    assert [int(row["seed"]) for row in reference] == [held[24]["seed"]], "the row kept is the arm's first run"
    assert held[25]["seed"] not in {int(row["seed"]) for arm in ("confirm-control", "confirm-1", "reference-1")
                                    for row in stored(proj, "desk-1", arm)}, "the run interrupted left no row"


def test_ctrl_c_in_a_stage_asked_again_leaves_out_an_earlier_stage_s_reference_arm(tmp_path: Path) -> None:
    """Stage 1 confirmed finding 1 and ran its reference arm whole. Asking again about the candidate too small to
    tell is stage 2, and Ctrl-C during its second run keeps stage 2's rows alone: not stage 1's, not finding 1's
    reference arm's, not the hunt's control's."""
    proj = hunts.finished(tmp_path)
    before = hunts.stored_counts(proj)
    assert before["reference-1"] > 0, before
    proj.write(case_list=[{**case, "nap": 0.25} for case in MIXED])  # the same ids: the hunt opens as it was
    made = len(proj.runs())
    document = interrupted_json(proj, ["confirm", "--repeats", "6", "--yes", "--json"], after_runs=made + 2)
    assert document["verdict"] == "stopped" and document["reason"] == "interrupted", document
    counts = hunts.stored_counts(proj)
    assert {arm: rows for arm, rows in counts.items() if arm in before} == before, "nothing of stage 1 moved"
    new = {arm: rows for arm, rows in counts.items() if arm not in before}
    assert new and sum(new.values()) >= 1, counts
    assert document["kept"] == sum(new.values())
    assert document["kept"] < before["reference-1"]
    assert document["arm"] in {f"desk-1-{arm}" for arm in new}, (document, new)
