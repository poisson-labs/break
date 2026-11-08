"""The confirm command on `confirm.read_stages`: it reads no `confirm.json` and no arm of Prove's store for itself.

Ruled 2026-11-08 (Break — Decisions: yes to a public `confirm.read_stages(hunt)`, with the confirm command moved onto
it; BK8 Session B's build choice 4). Before the ruling the command read the hunt's `confirm.json` and asked Prove's
`Store` for each arm's count, to plan a resumed or asked-again stage (point 54) and to refuse before any plan (point
14). Held here three ways:

- **BK8.8's check, widened** (the follow-up's brief): no module of the command holds the file's name, read from its
  source. The modules read are those `test_commands_cli.py` reads: `cli.py` and whatever of the
  package it reaches that is not one of the library's own.
- **What the command opens**, watched in its child by an audit hook: no frame of the command itself opens
  `confirm.json` or anything in the store folder of a confirm arm, in each of five states, while the confirm module's
  own frames do (the hook's control).
- **A stand-in for `read_stages`** in the command's child, giving an answer no file and no store could: its stage
  reaches the plan before a resumed stage and before asking again (point 54), and its stages decide the refusals
  known before the plan (point 14).

The shape `read_stages` hands back is the follow-up's point R1 (`tests/test_confirm_read_stages.py`). The hunts are
made through the library, as `hunt` and a stopped `confirm` leave them; every answer is the pinned Trace's own.
"""

from __future__ import annotations

import ast
import contextlib
from pathlib import Path
from typing import Any

import pytest

from tests.commands_spies import spied, spying
from tests.commands_support import (
    CODES,
    MIXED,
    MIXED_CANDIDATES,
    MIXED_SETTINGS,
    Project,
    cli,
    holds_number,
    opened,
    prepared,
    project,
    refused_once,
    results,
    store_runs,
    verdict,
)
from tests.conftest import REPO
from tests.test_commands_cli import LIBRARY, _command_modules


# ---------------------------------------------------------------------------
# BK8.8's check, widened: the file's name, read from the source
# ---------------------------------------------------------------------------


def _text(node: ast.AST) -> str | None:
    """The text an expression of literals spells: a string, an f-string's literal parts, or a sum of them."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(part.value for part in node.values
                       if isinstance(part, ast.Constant) and isinstance(part.value, str))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _text(node.left), _text(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _confirm_json(source: str) -> list[str]:
    """Each place a command's source spells the name of the hunt's confirm stages file, a docstring's words aside: a
    string that is a statement of its own is read by nobody."""
    tree = ast.parse(source)
    said = {id(node.value) for node in ast.walk(tree) if isinstance(node, ast.Expr)}
    found = []
    for node in ast.walk(tree):
        if id(node) in said:
            continue
        text = _text(node)
        if text is not None and "confirm.json" in text:
            found.append(f"line {getattr(node, 'lineno', '?')} spells confirm.json")
    return sorted(set(found))


def test_no_module_of_the_command_spells_confirm_json() -> None:
    """The command reads its stages through `read_stages`, so the file's name is nowhere in it."""
    modules = _command_modules()
    assert modules and modules[0].name == "cli.py"
    wrong = [f"{path.name}: {what}" for path in modules for what in _confirm_json(path.read_text(encoding="utf-8"))]
    assert wrong == []


@pytest.mark.parametrize("source", [
    'path = hunt.folder / "confirm.json"',
    "name = 'confirm.json'",
    'name = "confirm" ".json"',
    'name = "confirm" + ".json"',
    'path = f"{hunt.folder}/confirm.json"',
    'json.loads((folder / "confirm.json").read_text())',
])
def test_the_check_finds_each_way_confirm_json_is_spelt(source: str) -> None:
    assert _confirm_json(source), source


def test_the_check_takes_a_command_on_read_stages() -> None:
    clean = ('def _confirm(call):\n    """Plans from the stages confirm.json holds, read by the confirm module."""\n'
             "from poisson_break.confirm import read_stages, confirm\nstages = read_stages(hunt)\n"
             'latest = stages[-1] if stages else None\nprint(f"confirm stage {latest.number}")\n'
             'look.Row("design", "once with no change and once under each candidate")\n')
    assert _confirm_json(clean) == []


# ---------------------------------------------------------------------------
# the hunts the command is run on
# ---------------------------------------------------------------------------


def _confirmed_by_the_library(proj: Project) -> None:
    from poisson_break.confirm import confirm

    with contextlib.chdir(proj.folder):
        confirm(opened(proj, "desk-1"))


@pytest.fixture(scope="module")
def fresh(tmp_path_factory: pytest.TempPathFactory) -> Project:
    """The control run and the three candidates written; no confirm stage."""
    proj = project(tmp_path_factory.mktemp("fresh"), MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    return proj


@pytest.fixture(scope="module")
def finished(tmp_path_factory: pytest.TempPathFactory) -> Project:
    """Confirm stage 1 finished: candidate 1 confirmed, 2 too small to tell, 3 not confirmed; 11 cases, 4 repeats."""
    proj = project(tmp_path_factory.mktemp("finished"), MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    _confirmed_by_the_library(proj)
    return proj


@pytest.fixture(scope="module")
def stopped(tmp_path_factory: pytest.TempPathFactory) -> Project:
    """Confirm stage 1 stopped by the dollar cap after one run of its control arm: every run costs $0.001, the
    control's 36 spend $0.036, the cap is $0.0375."""
    from poisson_break.hunt import HuntStopped

    priced = [{**case, "tokens": [1000, 0]} for case in MIXED]
    proj = project(tmp_path_factory.mktemp("stopped"), priced, confirm={"repeats": 4},
                   search={"control_repeats": 3, "runs": 400},
                   limits={"dollars": 0.0375, "input_per_million": 1.0, "output_per_million": 1.0})
    prepared(proj, MIXED_CANDIDATES)
    with pytest.raises(HuntStopped):
        _confirmed_by_the_library(proj)
    assert "desk-1-confirm-1" not in store_runs(proj, "desk-1")
    return proj


def plan_text(ran: Any) -> str:
    plans = [block for block in results(ran.out) if block[0].startswith("plan  ")]
    assert len(plans) == 1, ran
    return "\n".join(plans[0])


# ---------------------------------------------------------------------------
# what the command opens, watched by an audit hook in its child
# ---------------------------------------------------------------------------

_SOURCE = REPO / "src" / "poisson_break"

#: Logs each opening or listing of `confirm.json` (or its temporary twin) and of anything in the store folder of a
#: confirm arm, with the module of the package whose frame is nearest the call: a frame of the command's or of the
#: library's. Frames outside the package (Python's, Prove's, pathlib's) are passed over to find it.
AUDIT = f'''
import os as _aos
import re as _are
import sys as _asys

_SOURCE = {str(_SOURCE)!r}
_LIBRARY = {sorted(LIBRARY)!r}
_CONFIRM = _are.compile(r"(^|/)confirm[.]json([.]tmp)?$")
_ARM = _are.compile(r"(^|/)store/[^/]+-confirm-[^/]+(/|$)")
_busy = [False]


def _audit(event, args):
    if _busy[0] or event not in ("open", "os.listdir", "os.scandir") or not args:
        return
    try:
        path = _aos.fsdecode(args[0])
    except TypeError:
        return
    if not (_CONFIRM.search(path) or _ARM.search(path)):
        return
    frame, who = _asys._getframe(1), None
    while frame is not None:
        name = frame.f_code.co_filename
        if name.startswith(_SOURCE + _aos.sep):
            who = _aos.path.relpath(name, _SOURCE).split(_aos.sep)[0].removesuffix(".py")
            break
        frame = frame.f_back
    if who is None:
        return
    _busy[0] = True
    try:
        _log(name="opened", by=who, path=path, event=event, library=who in _LIBRARY)
    finally:
        _busy[0] = False


_asys.addaudithook(_audit)
'''

_STATES = {
    "the first stage": ("fresh", ["confirm", "--dry-run"], CODES["done"]),
    "a stopped stage taken up": ("stopped", ["confirm", "--dry-run"], CODES["done"]),
    "asking again after a finished stage": ("finished", ["confirm", "--repeats", "6", "--dry-run"], CODES["done"]),
    "asking again with no stage": ("fresh", ["confirm", "--repeats", "6", "--dry-run"], CODES["refused"]),
    "asking again while a stage has runs missing": ("stopped", ["confirm", "--repeats", "6", "--dry-run"],
                                                    CODES["refused"]),
}


@pytest.mark.parametrize("state", list(_STATES))
def test_the_command_opens_no_confirm_json_and_no_confirm_arm_of_the_store_for_itself(
        state: str, request: pytest.FixtureRequest, tmp_path: Path) -> None:
    """Every opening of the stages file and of a confirm arm's store folder is the confirm module's own. The control:
    the confirm module does open `confirm.json` in every state (to read the stages, or to find there are none), so a
    hook that saw nothing would fail here rather than pass."""
    which, words, code = _STATES[state]
    proj: Project = request.getfixturevalue(which)
    env = spying(proj, tmp_path / "spy", AUDIT)
    ran = cli(proj, *words, **env)
    assert ran.exit == code, ran
    opened_ = [call for call in spied(env) if call["name"] == "opened"]
    assert [call for call in opened_ if not call["library"]] == []
    assert any(call["by"] == "confirm" and call["path"].endswith("confirm.json") for call in opened_), opened_


# ---------------------------------------------------------------------------
# a stand-in for read_stages: its answer reaches the plan and the refusals
# ---------------------------------------------------------------------------

_WRAPPED = '''
import dataclasses as _dataclasses
import types as _types
import poisson_break.confirm as _confirm

_real_read_stages = _confirm.read_stages


def read_stages(hunt):
    stages = _real_read_stages(hunt)
    _log(name="read_stages", hunt=hunt.name, stages=len(stages))
    return _changed(stages)


_confirm.read_stages = read_stages
'''

#: The stage on disk, then a second, the latest, on its first seven cases of eleven at 9 repeats where 4 were
#: written: each arm's 44 runs of 63, 76 left over four arms.
SECOND_STAGE = _WRAPPED + '''

def _changed(stages):
    return (*stages, _dataclasses.replace(stages[-1], number=2, repeats=9, cases=stages[-1].cases[:7]))
'''

#: The latest stage on its first five cases of eleven.
FIVE_CASES = _WRAPPED + '''

def _changed(stages):
    return (*stages[:-1], _dataclasses.replace(stages[-1], cases=stages[-1].cases[:5]))
'''

#: No stage at all, whatever the file holds.
NO_STAGE = _WRAPPED + '''

def _changed(stages):
    return ()
'''

#: The latest stage's control arm one run short of full, whatever the store holds.
ONE_SHORT = _WRAPPED + '''

def _changed(stages):
    last = stages[-1]
    control = last.arms[0][0]
    counts = _types.MappingProxyType({**last.counts, control: last.counts[control] - 1})
    return (*stages[:-1], _dataclasses.replace(last, counts=counts))
'''


def _unspent(proj: Project) -> tuple[list[str], int]:
    return store_runs(proj, "desk-1"), len(proj.runs())


def _asked(env: dict[str, str]) -> None:
    assert [(call["hunt"], call["stages"]) for call in spied(env) if call["name"] == "read_stages"][:1] == [
        ("desk-1", 1)], spied(env)


def test_the_control_without_a_stand_in_plans_a_finished_stage_afresh_and_asking_again(finished: Project) -> None:
    """What the stand-ins below change: on the finished stage `confirm --dry-run` plans the first stage's 176 runs, not
    a resume, and `--repeats 6` plans asking again over the eleven cases, 132 runs."""
    first = cli(finished, "confirm", "--dry-run")
    assert first.exit == CODES["done"], first
    assert holds_number(plan_text(first), "176") and not holds_number(plan_text(first), "76")
    again = cli(finished, "confirm", "--repeats", "6", "--dry-run")
    assert again.exit == CODES["done"], again
    assert holds_number(plan_text(again), "132") and not holds_number(plan_text(again), "60")


def test_point_54_the_plan_before_a_resumed_stage_is_the_latest_stage_read_stages_gives(finished: Project,
                                                                                         tmp_path: Path) -> None:
    """The stand-in's latest stage, a second one of seven cases at 9 repeats, has runs missing where the file and the
    store say none: the plan is that stage's, taken up as written, its 7 cases, its 9 repeats and its 76 runs left."""
    before = _unspent(finished)
    env = spying(finished, tmp_path / "spy", SECOND_STAGE)
    ran = cli(finished, "confirm", "--dry-run", **env)
    assert ran.exit == CODES["done"], ran
    assert verdict(ran)[0] == "plan"
    plan = plan_text(ran)
    assert all(holds_number(plan, number) for number in ("7", "9", "76")), plan
    assert not holds_number(plan, "176") and not holds_number(plan, "11"), plan
    _asked(env)
    assert _unspent(finished) == before


def test_point_54_the_plan_before_asking_again_is_over_the_cases_read_stages_gives(finished: Project,
                                                                                    tmp_path: Path) -> None:
    """Asking again about the one candidate too small to tell, over the stand-in's five cases: two arms of five cases
    six times, 60 runs, where the file's eleven make 132."""
    before = _unspent(finished)
    env = spying(finished, tmp_path / "spy", FIVE_CASES)
    ran = cli(finished, "confirm", "--repeats", "6", "--dry-run", **env)
    assert ran.exit == CODES["done"], ran
    plan = plan_text(ran)
    assert holds_number(plan, "60"), plan
    assert not holds_number(plan, "132"), plan
    _asked(env)
    assert _unspent(finished) == before


@pytest.mark.parametrize("body", [NO_STAGE, ONE_SHORT], ids=["no stage", "a stage one run short"])
def test_point_14_asking_again_is_refused_before_any_plan_when_read_stages_says_so(finished: Project, tmp_path: Path,
                                                                                    body: str) -> None:
    """Where the file and the store would plan asking again (the control above), the stand-in's answer, no stage or a
    latest stage with a run missing, is a refusal known before the plan: one `error:` line, nothing on stdout."""
    before = _unspent(finished)
    env = spying(finished, tmp_path / "spy", body)
    ran = cli(finished, "confirm", "--repeats", "6", "--dry-run", **env)
    refused_once(ran, CODES["refused"])
    _asked(env)
    assert _unspent(finished) == before


def test_a_confirm_json_that_cannot_be_read_is_one_refusal_line_not_a_fresh_plan(tmp_path: Path) -> None:
    """`read_stages` refuses a stages file it cannot read (R1 f); the command says so in one `error:` line, exit 1, and
    plans nothing, where reading the file for itself took such a file for no stage and planned a first one."""
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    (proj.hunt("desk-1") / "confirm.json").write_text("{ not json", encoding="utf-8")
    before = _unspent(proj)
    ran = cli(proj, "confirm", "--dry-run")
    refused_once(ran, CODES["refused"])
    assert _unspent(proj) == before
