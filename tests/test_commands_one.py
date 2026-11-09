"""R4: a verdict sentence says one thing in the singular.

Ruled 2026-11-08 (Break — Decisions; `evidence/bk8f/open-points.md` R4): "1 finding in desk-1", not "1 findings".
Held over every verdict sentence, the plans' included, of a road where each count the sentences carry is one: a case,
a candidate, a finding. A count of one is never followed by a plural noun; each test's control is that the count of
one is there, followed by the singular, so a sentence that dropped the count would not pass.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from tests import commands_hunts as hunts
from tests.commands_support import MIXED, MIXED_SETTINGS, CODES, cases, cli, project, results

NOUNS = ("case", "candidate", "finding", "run", "tool", "change", "repeat", "condition", "time")
PLURAL_AFTER_ONE = re.compile(r"(?<![\d.,$])1 (?:" + "|".join(f"{noun}s" for noun in NOUNS) + r")\b")


def sentences(ran: Any) -> list[str]:
    """Every verdict sentence the command printed: the words after each result's verdict word."""
    return [block[0].split("  ", 1)[1].strip() for block in results(ran.out)]


def one_and_singular(text: str, noun: str) -> bool:
    return re.search(rf"(?<![\d.,$])1 {noun}\b", text) is not None


@pytest.fixture(scope="module")
def one_candidate(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """`MIXED` hunted for at most one candidate, then confirmed (one finding), listed and rechecked."""
    proj = project(tmp_path_factory.mktemp("one"), MIXED, search=MIXED_SETTINGS["search"],
                   confirm={**MIXED_SETTINGS["confirm"], "candidates": 1})
    said = {"hunt": cli(proj, "hunt", "--yes", timeout=1200)}
    said["confirm"] = cli(proj, "confirm", "--yes", timeout=1200)
    said["findings"] = cli(proj, "findings")
    said["recheck"] = cli(proj, "recheck", "--yes", timeout=1200)
    return proj, said


@pytest.mark.parametrize("verb, noun", [("hunt", "candidate"), ("confirm", "candidate"), ("findings", "finding"),
                                        ("recheck", "finding")])
def test_each_sentence_with_one_says_it_in_the_singular(one_candidate: Any, verb: str, noun: str) -> None:
    _, said = one_candidate
    ran = said[verb]
    assert ran.exit == CODES["done"], ran
    every = sentences(ran)
    assert every, ran
    assert [s for s in every if PLURAL_AFTER_ONE.search(s)] == [], every
    assert any(one_and_singular(s, noun) for s in every), every


def test_asking_again_about_one_candidate(tmp_path: Path) -> None:
    proj = hunts.finished(tmp_path)
    ran = cli(proj, "confirm", "--repeats", "6", "--dry-run")
    assert ran.exit == CODES["done"], ran
    every = sentences(ran)
    assert [s for s in every if PLURAL_AFTER_ONE.search(s)] == [], every
    assert any(one_and_singular(s, "candidate") for s in every), every


def test_one_case(tmp_path: Path) -> None:
    """`doctor` and the hunt's plan over a case file of one case."""
    proj = project(tmp_path, cases(1, weak_to=["error"]))
    for words in (["doctor"], ["hunt", "--dry-run"]):
        ran = cli(proj, *words)
        assert ran.exit == CODES["done"], ran
        every = sentences(ran)
        assert [s for s in every if PLURAL_AFTER_ONE.search(s)] == [], every
        assert any(one_and_singular(s, "case") for s in every), every
