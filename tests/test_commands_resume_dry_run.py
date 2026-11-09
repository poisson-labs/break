"""R3: a dry run of `hunt --hunt NAME` plans the hunt being taken up, and writes nothing.

Ruled 2026-11-08 (Break — Decisions; `evidence/bk8f/open-points.md` R3, F3 of the field tables). Before, a dry run
opened no hunt, so `hunt --hunt desk-1 --dry-run` printed a fresh hunt's plan (60 runs where 59 were left) and took a
name that is not there for a new hunt. Opening an existing hunt writes nothing (spec §6.1), so the dry run opens it,
plans what is left, and still writes nothing. The document's fields are held in `test_commands_json_fields.py`.
"""

from __future__ import annotations

from pathlib import Path

from tests import commands_hunts as hunts
from tests.commands_support import (
    CODES,
    cases,
    cli,
    files_under,
    holds_number,
    paths_under,
    project,
    refused_once,
    results,
    verdict,
)


def _plan(ran: object) -> str:
    plans = [block for block in results(ran.out) if block[0].startswith("plan  ")]  # type: ignore[attr-defined]
    assert len(plans) == 1, ran
    return "\n".join(plans[0])


def test_the_dry_run_of_a_hunt_taken_up_plans_what_is_left_and_writes_nothing(tmp_path: Path) -> None:
    """A hunt of at most 60 runs the dollar cap stopped after one: the dry run of its resume plans the 59 left, as the
    resume itself does on a terminal (point 54), and no file under the project changes."""
    proj = project(tmp_path, cases(3, weak_to=["error"], tokens=[1000, 0]), limits={"dollars": 0.0015, **hunts.PRICES})
    assert cli(proj, "hunt", "--yes").exit == CODES["stopped"]
    before, made = files_under(proj.folder), len(proj.runs())
    ran = cli(proj, "hunt", "--hunt", "desk-1", "--dry-run")
    assert ran.exit == CODES["done"], ran
    assert verdict(ran)[0] == "plan"
    plan = _plan(ran)
    assert holds_number(plan, "59"), plan
    assert files_under(proj.folder) == before and len(proj.runs()) == made


def test_the_dry_run_of_a_hunt_that_is_not_there_is_refused_and_makes_nothing(tmp_path: Path) -> None:
    """Taken up, the name must be a hunt there is, as without `--dry-run`: one refusal, no plan, no folder made."""
    proj = project(tmp_path)
    ran = cli(proj, "hunt", "--hunt", "desk-7", "--dry-run")
    refused_once(ran, CODES["refused"])
    assert paths_under(proj.hunts) == []
