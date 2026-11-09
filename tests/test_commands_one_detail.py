"""S1: one is said in the singular in the detail rows and the estimate lines too.

Ruled 2026-11-09 (Break — Decisions; `evidence/bk8f/README.md` S1): R4 held the verdict sentences; the rows under
them and a plan's estimate could still say "left 1 runs" or "1 cases × 3 repeats". Held here over every line a
command prints on stdout, and over a plan's `estimate` and `source` under `--json`, on roads where the counts those
lines carry are one: one case, one repeat, one fault allowed, one hour, one condition tried, one run left of a hunt,
of a confirm stage and of a recheck. A count of one is never followed by a plural noun; each test's control is that
the row holds the count of one followed by the singular, so a row that dropped the count would not pass.
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import Any

import pytest

from tests import commands_hunts as hunts
from tests.commands_support import (
    CODES,
    Project,
    cases,
    cli,
    json_document,
    on,
    opened,
    out_lines,
    prepared,
    project,
    result_of,
    row,
)

NOUNS = ("case", "candidate", "finding", "run", "tool", "change", "repeat", "condition", "time", "fault", "operator",
         "move", "hour", "call", "pair", "setting")
PLURAL_AFTER_ONE = re.compile(r"(?<![\d.,$])1 (?:more )?(?:" + "|".join(f"{noun}s" for noun in NOUNS) + r")\b")

ONES: dict[str, Any] = {
    "tools": {"lookup_order": "read", "check_policy": "off"},
    "vary": {"tools": ["error"]},
    "search": {"control_repeats": 1, "runs": 2, "cases_per_condition": 1},
    "confirm": {"candidates": 1, "repeats": 1},
    "limits": {"hours": 1},
}


def one(text: str, noun: str) -> bool:
    """Whether `text` holds a count of one followed by `noun` in the singular."""
    return re.search(rf"(?<![\d.,$])1 (?:more )?{noun}\b(?!s)", text) is not None


def plurals(lines: list[str]) -> list[str]:
    return [line for line in lines if PLURAL_AFTER_ONE.search(line)]


def said(ran: Any, code: int = CODES["done"]) -> list[str]:
    assert ran.exit == code, ran
    lines = out_lines(ran)
    assert lines, ran
    return lines


def set_cap(proj: Project, dollars: float) -> None:
    text = proj.settings.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.startswith('"dollars" = ')]
    assert len(lines) == 1, text
    proj.settings.write_text(text.replace(lines[0], f'"dollars" = {dollars!r}'), encoding="utf-8")


# ---------------------------------------------------------------------------
# the patterns
# ---------------------------------------------------------------------------


def test_the_pattern_catches_a_plural_after_one_and_lets_the_rest_through() -> None:
    for text in ("left  1 runs", "1 cases × 3 repeats", "3 cases × 1 repeats", "up to 1 more runs", "cap 60 runs, 1 hours",
                 "tool behaviour (1 faults)", "about $0.0010 for 1 runs", "1 conditions tried on 2 cases each"):
        assert PLURAL_AFTER_ONE.search(text), text
    for text in ("left  1 run", "11 runs", "21 cases × 31 repeats", "$1 runs deep", "0.1 runs", "1,001 runs",
                 "1 case × 1 repeat", "up to 1 more run", "1 hour", "2.1 hours", "finding 1 runs here"[:9]):
        assert not PLURAL_AFTER_ONE.search(text), text
    assert one("left 1 run of 9", "run") and one("up to 1 more run", "run")
    assert not one("left 1 runs of 9", "run") and not one("left 11 run", "run") and not one("0.1 run", "run")


# ---------------------------------------------------------------------------
# a hunt where every count is one
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ones(tmp_path_factory: pytest.TempPathFactory) -> tuple[Project, dict[str, Any]]:
    """One case, one tool Break may touch, one control repeat, one fault allowed, one case a condition, two runs at
    most, one candidate at most, one confirm repeat, a cap of one hour: the hunt's plan, the hunt, and confirm's
    plan."""
    proj = project(tmp_path_factory.mktemp("ones"), cases(1, weak_to=["error"]), **ONES)
    printed = {"hunt plan": cli(proj, "hunt", "--dry-run"), "hunt": cli(proj, "hunt", "--yes")}
    printed["confirm plan"] = cli(proj, "confirm", "--dry-run")
    return proj, printed


@pytest.mark.parametrize("which", ["hunt plan", "hunt", "confirm plan"])
def test_no_line_of_a_road_of_ones_says_a_plural_after_one(ones: Any, which: str) -> None:
    _, printed = ones
    assert plurals(said(printed[which])) == []


def test_the_hunt_plan_rows_say_one_in_the_singular(ones: Any) -> None:
    _, printed = ones
    plan = result_of(printed["hunt plan"], "plan")
    assert one(row(plan, "stages"), "run"), plan
    assert one(row(plan, "may"), "fault"), plan
    assert one(row(plan, "cap"), "hour"), plan


def test_the_hunt_result_rows_say_one_in_the_singular(ones: Any) -> None:
    _, printed = ones
    result = result_of(printed["hunt"], "found")
    assert one(row(result, "control"), "run"), result
    search = row(result, "search")
    assert one(search, "run") and one(search, "condition") and one(search, "case"), result


def test_the_confirm_plan_rows_say_one_in_the_singular(ones: Any) -> None:
    _, printed = ones
    plan = result_of(printed["confirm plan"], "plan")
    assert one(row(plan, "design"), "case") and one(row(plan, "design"), "repeat"), plan
    assert one(row(plan, "reference"), "run"), plan


# ---------------------------------------------------------------------------
# one run left
# ---------------------------------------------------------------------------


def test_a_hunt_with_one_run_left_says_so_in_its_row_and_its_estimate(tmp_path: Path) -> None:
    """Priced, a hunt the cap stops after eight runs, its control's six among them; the settings then allow nine
    runs, which apply from then on: the dry run of taking it up has one run left, in its `left` row and in its
    estimate, on screen and under `--json`."""
    proj = project(tmp_path, cases(3, weak_to=["error"], tokens=[1000, 0]), limits={"dollars": 0.0085, **hunts.PRICES})
    assert cli(proj, "hunt", "--yes").exit == CODES["stopped"]
    assert sum(hunts.stored_counts(proj).values()) == 8
    text = proj.settings.read_text(encoding="utf-8")
    assert text.count('"runs" = 60') == 1
    proj.settings.write_text(text.replace('"runs" = 60', '"runs" = 9'), encoding="utf-8")
    ran = cli(proj, "hunt", "--hunt", "desk-1", "--dry-run")
    lines = said(ran)
    assert plurals(lines) == [], lines
    plan = result_of(ran, "plan")
    assert one(row(plan, "left"), "run"), plan
    assert one(row(plan, "estimate"), "run"), plan
    document = json_document(cli(proj, "hunt", "--hunt", "desk-1", "--dry-run", "--json"))
    assert document["runs"] == 1
    assert not PLURAL_AFTER_ONE.search(document["estimate"]) and one(document["estimate"], "run"), document


def test_a_confirm_stage_with_one_run_left_says_so_in_its_row_and_its_estimate(tmp_path: Path) -> None:
    """Priced, one case and two repeats: the stage is four runs, and the cap stops it after three."""
    proj = project(tmp_path, cases(1, weak_to=["error"], tokens=[1000, 0]), search={"control_repeats": 1},
                   confirm={"repeats": 2}, limits={"dollars": 0.0045, **hunts.PRICES})
    prepared(proj, (on("error"),))
    assert cli(proj, "confirm", "--yes").exit == CODES["stopped"]
    counts = hunts.stored_counts(proj)
    assert sum(rows for arm, rows in counts.items() if arm.startswith("confirm-")) == 3, counts
    ran = cli(proj, "confirm", "--dry-run")
    lines = said(ran)
    assert plurals(lines) == [], lines
    plan = result_of(ran, "plan")
    assert one(row(plan, "left"), "run"), plan
    assert one(row(plan, "design"), "case"), plan
    assert one(row(plan, "estimate"), "run"), plan


def test_a_recheck_with_one_run_left_says_so_in_its_row_and_its_estimate(tmp_path: Path) -> None:
    """Priced; finding 1 confirmed, then the cap lowered so a recheck begun through the library stops one run short
    of its end."""
    from poisson_break.confirm import read_findings, recheck
    from poisson_break.hunt import HuntStopped

    proj = hunts.stopped_recheck(tmp_path)  # stopped after five of its runs; taken up below to one short
    with contextlib.chdir(proj.folder):
        (finding,) = read_findings(opened(proj, "desk-1"))
    cells = len(finding.cases) * finding.repeats
    spent = sum(rows for arm, rows in hunts.stored_counts(proj).items() if not arm.startswith("recheck-"))
    set_cap(proj, (spent + cells - 1) * 0.001 + 0.0005)
    with contextlib.chdir(proj.folder), pytest.raises(HuntStopped):
        recheck(opened(proj, "desk-1"))
    assert hunts.stored_counts(proj)["recheck-1-1"] == cells - 1
    ran = cli(proj, "recheck", "--dry-run")
    lines = said(ran)
    assert plurals(lines) == [], lines
    plan = result_of(ran, "plan")
    assert one(row(plan, "left"), "run"), plan
    assert one(row(plan, "estimate"), "run"), plan
