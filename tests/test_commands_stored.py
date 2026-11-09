"""The command on `Hunt.stored()`: it asks the runs module what the store holds, and opens nothing of the store itself.

Ruled 2026-11-08 (R2, option A): the command reads whether the control is finished (`confirm`, `findings`, `recheck`)
and how much a stopped recheck has left (point 54's plan) through `Hunt.stored()` (`tests/test_hunt_stored.py`), so
that BK8.8's store-wide check (`test_commands_read_stages.py`, `fb0bf64`) holds on a build. Held two ways here:

- **What the command opens**, watched by an audit hook in its child: in six states across the three verbs no frame
  of the command opens anything in the hunt's store folder, while the library's frames do (the hook's control).
- **A stand-in for `Hunt.stored`**, giving an answer the store could not: a control one run short is a control not
  finished, for `confirm` (refused before any plan) and for the `findings` listing (no control heading); a recheck arm
  the store does not hold makes the plan the resume of that recheck, its runs left counted from the stand-in's numbers,
  beside the old agent when an `-old` arm is there.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests import commands_hunts as hunts
from tests.commands_spies import spied, spying
from tests.look_support import strip
from tests.commands_support import (
    CODES,
    Project,
    cli,
    holds_number,
    refused_once,
    results,
    store_runs,
    verdict,
)


@pytest.fixture(scope="module")
def finished(tmp_path_factory: pytest.TempPathFactory) -> Project:
    return hunts.finished(tmp_path_factory.mktemp("finished"))


@pytest.fixture(scope="module")
def stopped_recheck(tmp_path_factory: pytest.TempPathFactory) -> Project:
    return hunts.stopped_recheck(tmp_path_factory.mktemp("recheck"))


@pytest.fixture(scope="module")
def stopped_control(tmp_path_factory: pytest.TempPathFactory) -> Project:
    return hunts.stopped_control(tmp_path_factory.mktemp("control"))


def plan_text(ran: Any) -> str:
    plans = [block for block in results(ran.out) if block[0].startswith("plan  ")]
    assert len(plans) == 1, ran
    return "\n".join(plans[0])


def _unspent(proj: Project) -> tuple[list[str], int]:
    return store_runs(proj, "desk-1"), len(proj.runs())


# ---------------------------------------------------------------------------
# what the command opens
# ---------------------------------------------------------------------------

STORE = hunts.opening_audit(r"(^|/)break-runs/[^/]+/store(/|$)")

_STATES = {
    "confirm, the first stage": ("finished", ["confirm", "--dry-run"], CODES["done"]),
    "confirm, a control not finished": ("stopped_control", ["confirm", "--dry-run"], CODES["refused"]),
    "the findings listing": ("finished", ["findings"], CODES["done"]),
    "the findings listing, a control not finished": ("stopped_control", ["findings"], CODES["done"]),
    "recheck, the first": ("finished", ["recheck", "--dry-run"], CODES["done"]),
    "recheck, one taken up": ("stopped_recheck", ["recheck", "--dry-run"], CODES["done"]),
}


@pytest.mark.parametrize("state", list(_STATES))
def test_the_command_opens_nothing_of_the_store_for_itself(state: str, request: pytest.FixtureRequest,
                                                           tmp_path: Path) -> None:
    """Every opening of the hunt's store folder is the library's. The control: the library does open the store in
    every state, so a hook that saw nothing fails here rather than passes."""
    which, words, code = _STATES[state]
    proj: Project = request.getfixturevalue(which)
    env = spying(proj, tmp_path / "spy", STORE)
    ran = cli(proj, *words, **env)
    assert ran.exit == code, ran
    opened = [call for call in spied(env) if call["name"] == "opened"]
    assert [call for call in opened if not call["library"]] == []
    assert any(call["library"] for call in opened), opened


# ---------------------------------------------------------------------------
# a stand-in for Hunt.stored
# ---------------------------------------------------------------------------

_WRAPPED = '''
import types as _types
import poisson_break.hunt as _hunt

_real_stored = _hunt.Hunt.stored


def stored(self):
    found = dict(_real_stored(self))
    _log(name="stored", hunt=self.name, arms=sorted(found))
    return _types.MappingProxyType(_changed(found))


_hunt.Hunt.stored = stored
'''

#: The control one run short, whatever the store holds.
CONTROL_SHORT = _WRAPPED + '''

def _changed(found):
    return {**found, "control": found["control"] - 1}
'''

#: A first recheck begun, ten runs into finding 1's 44, that the store does not hold.
RECHECK_BEGUN = _WRAPPED + '''

def _changed(found):
    return {**found, "recheck-1-1": 10}
'''

#: The same recheck begun beside the old agent, whose arm holds five.
RECHECK_BEGUN_WITH_OLD = _WRAPPED + '''

def _changed(found):
    return {**found, "recheck-1-1": 10, "recheck-1-1-old": 5}
'''


def _asked(env: dict[str, str]) -> None:
    assert any(call["name"] == "stored" and call["hunt"] == "desk-1" for call in spied(env)), spied(env)


def test_the_control_without_a_stand_in(finished: Project) -> None:
    """What the stand-ins change: on the finished hunt `confirm --dry-run` plans and `recheck --dry-run` plans a first recheck of finding 1's 44 runs."""
    assert cli(finished, "confirm", "--dry-run").exit == CODES["done"]
    ran = cli(finished, "recheck", "--dry-run")
    assert ran.exit == CODES["done"], ran
    assert holds_number(plan_text(ran), "44") and not holds_number(plan_text(ran), "34")


def test_a_control_stored_short_is_not_finished_and_confirm_is_refused_before_any_plan(finished: Project,
                                                                                      tmp_path: Path) -> None:
    before = _unspent(finished)
    env = spying(finished, tmp_path / "spy", CONTROL_SHORT)
    refused_once(cli(finished, "confirm", "--dry-run", **env), CODES["refused"])
    _asked(env)
    assert _unspent(finished) == before


def _control_heading(ran: Any) -> list[str]:
    return [line for line in strip(ran.out).splitlines() if line.strip() == "control"]


def test_a_control_stored_short_leaves_the_control_out_of_the_listing(finished: Project, tmp_path: Path) -> None:
    """The listing asks the runs module for the control only once it is finished (build choice 5): stored short, it is
    not, so no control heading is printed, where the store's own answer prints one."""
    assert _control_heading(cli(finished, "findings")) == ["  control"]
    env = spying(finished, tmp_path / "spy", CONTROL_SHORT)
    ran = cli(finished, "findings", **env)
    assert ran.exit == CODES["done"], ran
    assert _control_heading(ran) == []
    _asked(env)


@pytest.mark.parametrize("body, left", [(RECHECK_BEGUN, "34"), (RECHECK_BEGUN_WITH_OLD, "73")],
                         ids=["the new agent alone", "beside the old agent"])
def test_point_54_a_recheck_the_stand_in_says_was_begun_is_the_plan(finished: Project, tmp_path: Path,
                                                                   body: str, left: str) -> None:
    """Finding 1's 44 runs a side: ten made leaves 34; beside the old agent, whose arm holds five, 34 and 39 leave 73.
    The plan goes on with recheck 1 as it was begun, where the store holds no recheck at all."""
    before = _unspent(finished)
    env = spying(finished, tmp_path / "spy", body)
    ran = cli(finished, "recheck", "--dry-run", **env)
    assert ran.exit == CODES["done"], ran
    assert verdict(ran)[0] == "plan"
    plan = plan_text(ran)
    assert holds_number(plan, left), plan
    assert not holds_number(plan, "44"), plan
    _asked(env)
    assert _unspent(finished) == before
