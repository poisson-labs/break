"""S2: a hunt taken up without prices estimates over the runs it has left.

Ruled 2026-11-09 (Break — Decisions; `evidence/bk8f/README.md` S2): R6 ruled the priced case. Without prices the plan
of a hunt taken up still said "at most 60 runs" beside `runs` 59. Held here: the estimate counts what is left, not
the whole plan; and once the hunt's control has run, the estimate times those runs at what one control run took, as
`confirm` does, and its source names the control's seconds a run. `dollars` stays null.

Each hunt is stopped by a dollar cap, then taken up under the same settings with the prices and the cap taken out:
the settings handed in apply from then on, so the hunt taken up has no prices.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from tests import commands_hunts as hunts
from tests.commands_support import (
    CODES,
    Project,
    cases,
    cli,
    holds_number,
    json_document,
    opened,
    project,
    result_of,
    row,
    settings_text,
)

PLAN_RUNS = 60


def stopped_then_unpriced(tmp_path: Path, dollars: float) -> tuple[Project, int]:
    """A hunt of three cases the cap stops, its settings then written again with no price and no cap; and the runs
    it has left of the plan's 60."""
    proj = project(tmp_path, cases(3, weak_to=["error"], tokens=[1000, 0]), limits={"dollars": dollars, **hunts.PRICES})
    assert cli(proj, "hunt", "--yes", "--json").exit == CODES["stopped"]
    proj.write(settings_text())
    kept = sum(hunts.stored_counts(proj).values())
    assert 0 < kept < PLAN_RUNS
    return proj, PLAN_RUNS - kept


def plan_document(proj: Project) -> dict[str, Any]:
    ran = cli(proj, "hunt", "--hunt", "desk-1", "--dry-run", "--json")
    assert ran.exit == CODES["done"], ran
    document = json_document(ran)
    assert document["verdict"] == "plan" and document["hunt"] == "desk-1", document
    return document


def test_before_its_control_has_run_the_estimate_counts_the_runs_left(tmp_path: Path) -> None:
    """Stopped after one run of its control's six: 59 runs are left, and the estimate says 59, not 60."""
    proj, left = stopped_then_unpriced(tmp_path, 0.0015)
    assert hunts.stored_counts(proj) == {"control": 1} and left == 59
    document = plan_document(proj)
    assert (document["runs"], document["dollars"]) == (left, None)
    assert holds_number(document["estimate"], str(left)), document
    assert not holds_number(document["estimate"], str(PLAN_RUNS)), document


def test_after_its_control_has_run_the_estimate_is_timed_from_the_control(tmp_path: Path) -> None:
    """Stopped in its search, the control's six runs made: the estimate holds the runs left and the time they take at
    the control's seconds a run, and the source names those seconds."""
    from poisson_break.hunt import control
    from poisson_break.look import fmt_duration

    proj, left = stopped_then_unpriced(tmp_path, 0.0085)
    counts = hunts.stored_counts(proj)
    assert counts["control"] == 6 and left == PLAN_RUNS - sum(counts.values()) < 54, counts
    with contextlib.chdir(proj.folder):
        per_run = control(opened(proj, "desk-1")).seconds_per_run
    assert per_run is not None and per_run > 0
    document = plan_document(proj)
    assert (document["runs"], document["dollars"]) == (left, None)
    assert holds_number(document["estimate"], str(left)), document
    assert not holds_number(document["estimate"], str(PLAN_RUNS)), document
    assert fmt_duration(left * per_run) in document["estimate"], (document, per_run)
    assert fmt_duration(per_run) in document["source"], (document, per_run)
    assert "$" not in document["estimate"] and "$" not in document["source"], document


def test_the_plan_on_screen_says_the_same_estimate(tmp_path: Path) -> None:
    proj, left = stopped_then_unpriced(tmp_path, 0.0015)
    document = plan_document(proj)
    ran = cli(proj, "hunt", "--hunt", "desk-1", "--dry-run")
    assert ran.exit == CODES["done"], ran
    estimate = row(result_of(ran, "plan"), "estimate")
    assert document["estimate"] in estimate and holds_number(estimate, str(left)), estimate


def test_a_new_hunt_s_estimate_still_counts_the_whole_plan(tmp_path: Path) -> None:
    """The control for the three above: a hunt not yet begun plans all 60."""
    proj = project(tmp_path, cases(3, weak_to=["error"]))
    ran = cli(proj, "hunt", "--dry-run", "--json")
    assert ran.exit == CODES["done"], ran
    document = json_document(ran)
    assert document["runs"] == PLAN_RUNS and holds_number(document["estimate"], str(PLAN_RUNS)), document
