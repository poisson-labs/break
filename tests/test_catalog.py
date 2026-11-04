"""The catalogue as a whole: spec §3.2 to §3.4, and what happens to a change the core cannot apply.

Invariants pinned here (Break — Plan, the catalogue module):
- BK1.6  The catalogue is closed and complete at launch: exactly the ten tool faults, five input
         operators, four conversation moves and five model faults of the spec, each with a
         description that contains no module id. Conversation moves and model faults are names in
         the catalogue; the core applies neither (they need an adapter), and `catalog` says so on
         their lines.
- BK1.9  Each of the ten faults declares whether the real tool runs, and the declaration equals
         spec §3.2's table.

The shape of `CATALOG` is ruling 3. The refusal is ruling 11: spec §11.2 invariant 6 says a way in
that cannot do something says so in `capabilities()`, and settings that ask for it are refused at
load with one line, never mid-hunt. The printed `catalog` line is the commands module's; what it
prints from is held here.
"""

from __future__ import annotations

import inspect
import json

import pytest

from poisson_break import interfaces
from poisson_break.interfaces import Capabilities
from tests.changes_support import (
    CONVERSATION_MOVES,
    INPUT_OPERATORS,
    LAUNCH,
    MODEL_FAULTS,
    PLAN_WORDS,
    REAL_RUNS,
    TOOL_FAULTS,
    changes,
    entry,
    under_hash_seed,
)

ROLLOUT = Capabilities(tool_calls=True, model_calls=False, conversation=False)
ADAPTER = Capabilities(tool_calls=True, model_calls=True, conversation=True)
NOTHING = Capabilities(tool_calls=False, model_calls=False, conversation=False)


# ---------------------------------------------------------------------------
# BK1.6  closed and complete
# ---------------------------------------------------------------------------


def test_the_catalogue_is_exactly_the_specs_lists() -> None:
    lines = [(e.surface, e.name) for e in changes().CATALOG]
    assert len(lines) == len(set(lines)), "a change is listed twice"
    assert set(lines) == set(LAUNCH)


def test_the_catalogue_is_the_same_in_every_process_and_at_every_import() -> None:
    """Closed means nothing joins it on its own, and the order `catalog` prints is one order."""
    code = ("import json; from poisson_break.changes import CATALOG\n"
            "print(json.dumps([[e.surface, e.name] for e in CATALOG]))\n")
    first = json.loads(under_hash_seed(code, 1))
    assert first == json.loads(under_hash_seed(code, 2))
    assert {tuple(line) for line in first} == set(LAUNCH)


def test_nothing_is_added_to_it_except_by_register() -> None:
    """Ruling 3. `register` is what holds the invariants of §11.1, so it is the only way in, and a
    line cannot be taken out."""
    catalog = changes().CATALOG
    with pytest.raises((TypeError, AttributeError)):
        catalog.append(object())
    with pytest.raises((TypeError, AttributeError)):
        catalog.clear()
    with pytest.raises((TypeError, AttributeError)):
        del catalog[0]
    assert {(e.surface, e.name) for e in changes().CATALOG} == set(LAUNCH)


def test_a_line_refuses_assignment_and_its_defaults_cannot_be_edited() -> None:
    """A default edited through the catalogue would change every later run in the process and be
    written down nowhere."""
    line = entry("tool", "slow")
    with pytest.raises(AttributeError):
        line.real_runs = False
    with pytest.raises(TypeError):
        line.parameters["delay"] = 29
    assert line.parameters["delay"] == 5


@pytest.mark.parametrize("surface, name", sorted(LAUNCH))
def test_every_line_has_a_plain_one_line_description(surface: str, name: str) -> None:
    """BK1.6 and §11.1 invariant 7: no module id, ruling number or session name."""
    description = entry(surface, name).description
    assert description.strip() == description
    assert description
    assert "\n" not in description
    assert not PLAN_WORDS.search(description), description


def test_the_descriptions_say_different_things() -> None:
    """A line each: one description pasted over a surface tells the user nothing."""
    for surface in ("tool", "input", "user", "model"):
        lines = [e.description for e in changes().CATALOG if e.surface == surface]
        assert len(set(lines)) == len(lines), surface


def test_a_description_is_not_just_the_name_again() -> None:
    for line in changes().CATALOG:
        assert line.description.replace("_", " ").lower() != line.name.replace("_", " ").lower()


# ---------------------------------------------------------------------------
# BK1.9  the declaration equals the table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fault, runs", REAL_RUNS.items())
def test_each_fault_declares_the_tables_third_column(fault: str, runs: bool) -> None:
    line = entry("tool", fault)
    assert line.real_runs is runs
    assert line.fault.real_runs is runs


@pytest.mark.parametrize("surface, names", [("input", INPUT_OPERATORS),
                                            ("user", CONVERSATION_MOVES),
                                            ("model", MODEL_FAULTS)])
def test_only_a_tool_fault_declares_whether_a_tool_runs(surface: str, names: tuple[str, ...]) -> None:
    """Ruling 3. §3.2's third column is about tools; the others have no such fact at launch."""
    for name in names:
        assert entry(surface, name).real_runs is None


# ---------------------------------------------------------------------------
# parameters: one default each (§3.2, ruling 12)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fault, parameters", [
    ("error", {}),
    ("timeout", {}),
    ("slow", {"delay": 5}),
    ("rate_limited", {"wait": 30}),
    ("empty", {}),
    ("cut_off", {"length": 200}),
    ("malformed", {}),
    ("stale", {}),
    ("lost_reply", {}),
    ("planted_instruction", {}),
])
def test_each_tool_fault_has_exactly_its_parameters_and_defaults(fault: str, parameters: dict) -> None:
    """The delay, the wait and the cut length, and nothing else: the search varies the tool, the
    call and the fault, not the parameters."""
    assert dict(entry("tool", fault).parameters) == parameters


@pytest.mark.parametrize("operator, parameters", [
    ("typos", {"share": 0.05}),
    ("reordered", {}),
    ("padded", {}),
    ("cut_short", {}),
    ("variant", {}),
])
def test_each_input_operator_has_exactly_its_parameters(operator: str, parameters: dict) -> None:
    assert dict(entry("input", operator).parameters) == parameters


# ---------------------------------------------------------------------------
# what a tool fault is
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fault", TOOL_FAULTS)
def test_a_launch_fault_is_a_fault_like_any_other(fault: str) -> None:
    """Spec §11.1: the launch ten go through the door a later fault goes through. Keyword-only
    where the protocol says, so a field can be added without breaking an implementer."""
    line = entry("tool", fault)
    assert isinstance(line.fault, interfaces.Fault)
    assert (line.fault.name, line.fault.surface) == (fault, "tool")
    assert line.fault.description == line.description
    assert line.needs_adapter is False
    declared = [(n, p.kind) for n, p in inspect.signature(interfaces.Fault.apply).parameters.items()
                if n != "self"]
    built = [(n, p.kind) for n, p in inspect.signature(line.fault.apply).parameters.items()]
    assert built == declared


@pytest.mark.parametrize("operator", INPUT_OPERATORS)
def test_an_input_operator_needs_no_adapter(operator: str) -> None:
    """§7.1: even an agent reachable only over HTTP can have its inputs varied."""
    assert entry("input", operator).needs_adapter is False


# ---------------------------------------------------------------------------
# conversation moves and model faults: names, and refused without an adapter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("surface, name", [("user", n) for n in CONVERSATION_MOVES]
                         + [("model", n) for n in MODEL_FAULTS])
def test_a_line_that_needs_an_adapter_says_so_and_holds_nothing_to_apply(surface: str,
                                                                         name: str) -> None:
    """BK1.6 and §3.4: the core's catalogue carries these as names and applies none of them, and
    `catalog` says so on their lines. Conversation moves have pure functions for an adapter to
    call; neither has a `Fault` in the core."""
    line = entry(surface, name)
    assert line.needs_adapter is True
    assert line.fault is None


@pytest.mark.parametrize("text", [f"user:{m}@2" for m in CONVERSATION_MOVES]
                         + [f"model:{f}#2" for f in MODEL_FAULTS])
def test_their_names_parse_so_settings_and_names_stay_stable(text: str) -> None:
    """Plan §7 item 14, ruled: settings files and condition names do not change the day an adapter
    lands."""
    assert changes().name(changes().parse(text)) == text


@pytest.mark.parametrize("text", [f"user:{m}@2" for m in CONVERSATION_MOVES]
                         + [f"model:{f}#2" for f in MODEL_FAULTS])
def test_a_way_in_without_the_capability_is_refused_in_one_line(text: str) -> None:
    """§11.2 invariant 6. The `rollout` kind is the way in that ships, and it can do neither. The
    refusal names the change, as a fact, not as a word in a sentence."""
    c = changes()
    condition = c.parse(text)
    with pytest.raises(c.NeedsAdapter) as refused:
        c.check_capabilities(condition, ROLLOUT)
    assert refused.value.change == text
    assert "\n" not in str(refused.value)
    assert not PLAN_WORDS.search(str(refused.value))


def test_the_refusal_is_a_refused_name_to_whoever_catches_those() -> None:
    """A settings file catches one kind of refusal when it checks a condition, not two."""
    assert issubclass(changes().NeedsAdapter, changes().ChangeError)


@pytest.mark.parametrize("text", [f"user:{m}@2" for m in CONVERSATION_MOVES]
                         + [f"model:{f}#2" for f in MODEL_FAULTS])
def test_the_same_condition_is_taken_by_a_way_in_that_can(text: str) -> None:
    """The control, and the reason the refusal asks about capabilities and not about the surface:
    an adapter lands with no change to the core (plan §2 item 10)."""
    assert changes().check_capabilities(changes().parse(text), ADAPTER) is None


@pytest.mark.parametrize("text, capabilities", [
    ("model:error#1", Capabilities(tool_calls=True, model_calls=True, conversation=False)),
    ("user:presses@1", Capabilities(tool_calls=True, model_calls=False, conversation=True)),
])
def test_each_surface_asks_for_its_own_capability(text: str, capabilities: Capabilities) -> None:
    assert changes().check_capabilities(changes().parse(text), capabilities) is None


@pytest.mark.parametrize("text, capabilities", [
    ("model:error#1", Capabilities(tool_calls=True, model_calls=False, conversation=True)),
    ("user:presses@1", Capabilities(tool_calls=True, model_calls=True, conversation=False)),
])
def test_the_other_capability_does_not_stand_in(text: str, capabilities: Capabilities) -> None:
    c = changes()
    with pytest.raises(c.NeedsAdapter):
        c.check_capabilities(c.parse(text), capabilities)


def test_a_tool_change_asks_for_routed_tool_calls() -> None:
    """§11.2 lists it as the first of the three, and §7.1 has an HTTP agent that can do none."""
    c = changes()
    condition = c.parse("tool:a#2=error")
    assert c.check_capabilities(condition, ROLLOUT) is None
    with pytest.raises(c.NeedsAdapter) as refused:
        c.check_capabilities(condition, NOTHING)
    assert refused.value.change == "tool:a#2=error"


@pytest.mark.parametrize("text", ["input:typos", "env:inventory=empty", ""])
def test_inputs_settings_and_the_control_ask_for_nothing(text: str) -> None:
    c = changes()
    condition = c.parse(text, env={"inventory": ["empty"]})
    assert c.check_capabilities(condition, NOTHING) is None


def test_one_change_a_way_in_cannot_do_refuses_the_whole_condition() -> None:
    """A condition is one thing to run: its other changes do not carry it, and the refusal names
    the change that is the trouble."""
    c = changes()
    condition = c.parse("tool:a#2=error + model:empty#1 + input:typos")
    with pytest.raises(c.NeedsAdapter) as refused:
        c.check_capabilities(condition, ROLLOUT)
    assert refused.value.change == "model:empty#1"
