"""The case a run is handed: inputs changed by operators, and a scripted conversation changed by moves.

Invariant pinned here (Break — Plan, the applying module):
- BK2.13, the case half: operators and moves are handed a case as a mapping, which BK4's `read_cases`
         hands over, or the applier makes one.

And spec §3.3 and §6.4: a change that cannot act leaves things as they were, and the record's `applied`
says so.

That `Session.case(case)` is the public way this is done, moves included for a way in that can, is
ruling 13; what happens with two operators, or two moves, in one condition is ruling 18. Which operators
that change nothing count as having applied is not in §3.3's list and is left open: `reordered` on one
sentence, `cut_short` on one sentence. No test reads their `applied`.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import pytest

from poisson_break.interfaces import Capabilities
from tests.apply_support import ALL_CAPABILITIES, SEED, apply, session
from tests.changes_support import changes

CASE = {"id": "c1", "input": "Where is order 7? Please refund it. Thank you very much for your help today.",
        "variants": ["Order 7, where is it?", "Refund order 7."],
        "turns": ["Hello there.", "Where is order 7?", "Refund it, please.", "Thanks."],
        "expect": {"never_calls": ["delete_account"]}}
OPERATORS = ("typos", "reordered", "padded", "cut_short", "variant")
MOVES = ("repeats", "interrupts", "goes_quiet", "presses")


def can() -> Capabilities:
    return Capabilities(**ALL_CAPABILITIES)


@pytest.mark.parametrize("operator", OPERATORS)
@pytest.mark.parametrize("seed", [1, SEED])
def test_an_operator_changes_the_input_and_nothing_else(operator: str, seed: int) -> None:
    """Its own pure function, on the run's own seed: replay rests on the same seed giving the same
    bytes, and on an operator being run on that seed and not another."""
    expected = getattr(changes(), operator)(CASE, seed=seed)
    got = session(f"input:{operator}", seed=seed).case(CASE)
    assert got["input"] == expected
    assert {k: v for k, v in got.items() if k != "input"} == {k: v for k, v in CASE.items() if k != "input"}


@pytest.mark.parametrize("operator", OPERATORS)
def test_an_operator_that_acted_is_recorded_as_applied_with_no_call(operator: str) -> None:
    s = session(f"input:{operator}")
    s.case(CASE)
    assert s.applied[0].applied is True
    assert s.applied[0].applied_call is None


def test_an_operator_is_on_the_record_as_not_applied_until_it_is() -> None:
    assert session("input:typos").applied[0].applied is False


def test_the_case_it_is_handed_is_left_as_it_was() -> None:
    """The same case goes to every repeat of every arm."""
    case = {"id": "c1", "input": "Where is order 7?", "turns": ["one", "two"], "expect": {"calls": ["a"]}}
    before = {"id": "c1", "input": "Where is order 7?", "turns": ["one", "two"], "expect": {"calls": ["a"]}}
    s = session("input:typos + user:presses@2", capabilities=can())
    s.case(case)
    assert case == before


def test_under_the_control_the_case_is_the_case() -> None:
    s = session("")
    assert s.case(CASE) == CASE
    assert s.applied == ()


def test_a_tool_change_leaves_the_case_alone() -> None:
    s = session("tool:a#1=error")
    assert s.case(CASE) == CASE
    assert s.applied[0].applied is False


def test_a_read_only_mapping_is_a_mapping() -> None:
    """A case is the mapping of its JSON line (the catalogue's ruling 9), and BK4 may hand over a frozen
    one."""
    frozen = MappingProxyType(dict(CASE))
    s = session("input:cut_short")
    assert s.case(frozen)["input"] == changes().cut_short(CASE, seed=SEED)


@pytest.mark.parametrize("case", ["just text", 7, None, ["a", "list"]], ids=["text", "number", "none", "list"])
def test_what_is_not_a_case_is_an_instrument_error(case: Any) -> None:
    """Whoever handed it over is Break's own side of the line."""
    with pytest.raises(apply().InstrumentError):
        session("input:typos").case(case)


def test_variant_with_none_written_leaves_the_input_and_says_it_did_not_apply() -> None:
    """§3.3: a change that cannot act leaves things as they were, and the record's `applied` says so."""
    case = {"id": "c1", "input": "Where is order 7?"}
    s = session("input:variant")
    assert s.case(case) == case
    assert s.applied[0].applied is False
    assert s.applied[0].applied_call is None


# ---------------------------------------------------------------------------
# moves, for a way in that can
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("move", MOVES)
def test_a_move_changes_the_turn_it_names_and_is_on_the_record(move: str) -> None:
    s = session(f"user:{move}@3", capabilities=can(), seed=9)
    got = s.case(CASE)
    assert got["turns"] == getattr(changes(), move)(CASE, turn=3, seed=9)
    assert got["turns"][:2] == CASE["turns"][:2]
    assert got["turns"][3] == CASE["turns"][3]
    assert got["input"] == CASE["input"]
    assert s.applied[0].applied is True


@pytest.mark.parametrize("text, case", [
    ("user:repeats@1", CASE),
    ("user:presses@9", CASE),
    ("user:interrupts@5", CASE),
    ("user:goes_quiet@1", {"id": "c1", "input": "No script here."}),
], ids=["repeats-on-the-first-turn", "past-the-end", "just-past-the-end", "no-script"])
def test_a_move_that_cannot_act_leaves_things_as_they_were_and_says_so(text: str, case: dict[str, Any]) -> None:
    s = session(text, capabilities=can())
    assert s.case(case) == case
    assert s.applied[0].applied is False


def test_a_move_on_the_last_turn_can_act() -> None:
    """The control to the two past the end."""
    s = session("user:presses@4", capabilities=can())
    assert s.case(CASE)["turns"][3] != CASE["turns"][3]
    assert s.applied[0].applied is True


# ---------------------------------------------------------------------------
# two changes on one case (ruling 18)
# ---------------------------------------------------------------------------


def test_two_operators_act_in_the_conditions_order_each_on_what_the_last_left() -> None:
    """`random` can draw the pair. `cut_short` sorts before `typos`, so it is the first sentence that
    gets the typos, and the record says both acted."""
    s = session("input:typos + input:cut_short", seed=5)
    first = changes().cut_short(CASE, seed=5)
    expected = changes().typos({**CASE, "input": first}, seed=5)
    assert s.case(CASE)["input"] == expected
    assert [a.applied for a in s.applied] == [True, True]


def test_two_moves_act_in_the_conditions_order_each_on_what_the_last_left() -> None:
    """`presses@2` sorts before `repeats@3`, so turn 3 repeats the line that was pressed in."""
    s = session("user:repeats@3 + user:presses@2", capabilities=can(), seed=5)
    pressed = changes().presses(CASE, turn=2, seed=5)
    expected = changes().repeats({**CASE, "turns": pressed}, turn=3, seed=5)
    assert s.case(CASE)["turns"] == expected
    assert expected[2] == pressed[1]


def test_one_that_acts_and_one_that_cannot_are_each_said_so() -> None:
    case = {"id": "c1", "input": "One. Two."}
    s = session("input:cut_short + input:variant")
    assert s.case(case)["input"] == "One."
    assert {a.fault: a.applied for a in s.applied} == {"cut_short": True, "variant": False}
