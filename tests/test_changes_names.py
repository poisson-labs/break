"""Changes and conditions, by name: spec §3.1, through `parse` and `name`.

Invariants pinned here (Break — Plan, the catalogue module):
- BK1.1  Names round-trip. For every condition the catalogue can express, `parse(name(c)) == c`,
         and `name` is the same across processes. Two spellings of one condition have one name.
- BK1.2  Bad names are refused with the nearest valid name when one is within two edits, each with
         an accepted control.
- BK1.6, the `env` half: `env:<name>=<value>` parses for any name and value the settings list, and
         for no other.

And spec §6.4 as ruled on 2026-11-04: a stored change holds the position as the name writes it, and
for a setting its name and value, so every parsed change must fill an `Applied` record.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Iterator

import pytest

from poisson_break.records import Applied
from tests.changes_support import (
    CONVERSATION_MOVES,
    INPUT_OPERATORS,
    MODEL_FAULTS,
    TOOL_FAULTS,
    changes,
    fresh_changes,
    one,
    under_hash_seed,
)

ENV = {"inventory": ["full", "empty"], "date": ["2026-01-01"]}


def single_changes() -> Iterator[str]:
    """Every kind of change the catalogue can express, by the name forms of spec §3.1."""
    for tool, position, fault in itertools.product(
            ("lookup_order", "search"), ("#1", "#3", "#2-4", "#*", "~0.3", "~1"), TOOL_FAULTS):
        yield f"tool:{tool}{position}={fault}"
    for operator in INPUT_OPERATORS:
        yield f"input:{operator}"
    for move, turn in itertools.product(CONVERSATION_MOVES, (1, 3)):
        yield f"user:{move}@{turn}"
    for fault, position in itertools.product(MODEL_FAULTS, ("#1", "#2-4", "#*")):
        yield f"model:{fault}{position}"
    for setting, values in ENV.items():
        for value in values:
            yield f"env:{setting}={value}"


# ---------------------------------------------------------------------------
# BK1.1  names round-trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "tool:lookup_order#2=timeout",
    "tool:search~0.3=error",
    "input:typos",
    "user:repeats@3",
    "model:cut_off#2",
    "env:inventory=empty",
    "tool:a#2-4=slow",
    "tool:a#*=stale",
])
def test_the_specs_name_forms_are_their_own_canonical_names(text: str) -> None:
    """The name is the text of §3.1, not some other form that happens to round-trip."""
    assert changes().name(changes().parse(text, env=ENV)) == text


def test_the_empty_name_is_the_control() -> None:
    """§6.4: the control's condition name is the empty string, and it has no changes."""
    control = changes().parse("")
    assert control.changes == ()
    assert changes().name(control) == ""


def test_every_single_change_round_trips() -> None:
    c = changes()
    for text in single_changes():
        condition = c.parse(text, env=ENV)
        assert c.name(condition) == text
        assert c.parse(c.name(condition), env=ENV) == condition


def test_every_pair_round_trips() -> None:
    """§3.1: a condition is its changes joined with ` + `."""
    c = changes()
    for left, right in itertools.combinations(single_changes(), 2):
        condition = c.parse(f"{left} + {right}", env=ENV)
        assert len(condition.changes) == 2
        assert c.parse(c.name(condition), env=ENV) == condition
        assert sorted(c.name(condition).split(" + ")) == sorted((left, right))


def test_the_order_written_does_not_change_the_condition() -> None:
    """§3.1: a condition is canonical, its changes sorted. All six orders of three changes are one
    condition with one name, and one element of a set: the search's no-repeats rule leans on it."""
    c = changes()
    parts = ("tool:b#1=error", "input:typos", "tool:a~0.3=slow")
    orders = [c.parse(" + ".join(p)) for p in itertools.permutations(parts)]
    assert len({c.name(o) for o in orders}) == 1
    assert len(set(orders)) == 1
    assert all(o == orders[0] for o in orders)
    assert tuple(c.name(ch) for ch in orders[0].changes) == tuple(c.name(orders[0]).split(" + "))


@pytest.mark.parametrize("spelling, canonical", [
    ("tool:a~0.30=error", "tool:a~0.3=error"),
    ("tool:a~1.0=error", "tool:a~1=error"),
    ("tool:a#2-2=error", "tool:a#2=error"),
    ("model:cut_off#2-2", "model:cut_off#2"),
    ("tool:a#2=error + tool:a#2=error", "tool:a#2=error"),
])
def test_two_spellings_of_one_condition_have_one_name(spelling: str, canonical: str) -> None:
    """Ruling 6. Each pair behaves identically on every call, so each is one condition."""
    c = changes()
    assert c.parse(spelling) == c.parse(canonical)
    assert c.name(c.parse(spelling)) == canonical


@pytest.mark.parametrize("text", [
    "tool:a#2=error+tool:b#1=error",
    " tool:a#2=error",
    "tool:a#2=error ",
    "tool:a#02=error",
])
def test_a_loose_spelling_is_refused_or_read_as_what_it_says(text: str) -> None:
    """Whether these are accepted is not settled, and no test decides it. What must not happen is a
    different condition: a tool named `a#2=error+tool:b`, or a fault with a space in it."""
    c = changes()
    try:
        condition = c.parse(text)
    except c.ChangeError:
        return
    expected = c.parse(text.replace("#02", "#2").replace("+", " + ").strip())
    assert condition == expected


@pytest.mark.parametrize("tool", ["lookup_order", "get-weather", "v2.search", "tool7"])
def test_tool_names_as_frameworks_write_them_round_trip(tool: str) -> None:
    c = changes()
    text = f"tool:{tool}#2=error"
    assert one(text).tool == tool
    assert c.name(c.parse(text)) == text


def test_name_gives_one_change_its_own_name() -> None:
    """Ruling 1. A stored call names the change applied to it (§6.4, `Call.change`)."""
    c = changes()
    condition = c.parse("tool:a#2=error + input:typos")
    assert sorted(c.name(ch) for ch in condition.changes) == ["input:typos", "tool:a#2=error"]


def test_names_are_the_same_across_processes() -> None:
    """A set iterated in hash order, or a sort on a built-in hash, shows up as two processes
    disagreeing. The string-hash seed is the only thing that differs between them."""
    written = ["tool:b#1=error + input:typos + tool:a~0.3=slow + user:presses@2",
               "model:empty#1 + env:inventory=full + input:padded"]
    code = (
        "import json; from poisson_break.changes import name, parse\n"
        f"ENV = {ENV!r}\n"
        f"print(json.dumps([name(parse(t, env=ENV)) for t in {written!r}]))\n"
    )
    first = json.loads(under_hash_seed(code, 1))
    assert first == json.loads(under_hash_seed(code, 2))
    assert first == [changes().name(changes().parse(t, env=ENV)) for t in written]


def test_a_condition_refuses_assignment() -> None:
    """The plan's types pass frozen objects (§11, rules all four share)."""
    condition = changes().parse("tool:a#2=error")
    with pytest.raises(AttributeError):
        condition.changes = ()
    with pytest.raises(AttributeError):
        condition.changes[0].fault = "timeout"


# ---------------------------------------------------------------------------
# what a change holds, and that it fills the stored record
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text, surface, tool, fault, call", [
    ("tool:lookup_order#2=timeout", "tool", "lookup_order", "timeout", "#2"),
    ("tool:a#2-4=slow", "tool", "a", "slow", "#2-4"),
    ("tool:a#*=stale", "tool", "a", "stale", "#*"),
    ("tool:search~0.3=error", "tool", "search", "error", "~0.3"),
    ("input:typos", "input", None, "typos", None),
    ("user:repeats@3", "user", None, "repeats", "@3"),
    ("model:cut_off#2", "model", None, "cut_off", "#2"),
    ("env:inventory=empty", "env", "inventory", "empty", None),
])
def test_a_change_holds_what_the_stored_record_names(text: str, surface: str, tool: str | None,
                                                     fault: str, call: str | None) -> None:
    """§6.4 as ruled 2026-11-04: the call as the name writes it, sigil included; a setting's name
    in `tool` and its value in `fault`. The fields fill an `Applied` as they stand, so the applier
    copies them and rewrites nothing."""
    change = one(text, env=ENV)
    assert (change.surface, change.tool, change.fault, change.call) == (surface, tool, fault, call)
    record = Applied(surface=change.surface, tool=change.tool, fault=change.fault,
                     call=change.call, applied=True, applied_call=None)
    assert Applied.from_json(record.to_json()) == record


# ---------------------------------------------------------------------------
# BK1.2  bad names are refused, with the nearest valid name within two edits
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad, control", [
    ("tool:a#2=timeuot", "tool:a#2=timeout"),
    ("tool:a#2=eror", "tool:a#2=error"),
    ("tool:a~0.3=cut_of", "tool:a~0.3=cut_off"),
    ("tol:a#2=error", "tool:a#2=error"),
    ("input:typo", "input:typos"),
    ("inptu:typos", "input:typos"),
    ("user:repeat@3", "user:repeats@3"),
    ("model:cut_of#2", "model:cut_off#2"),
    ("tol:a#2=eror", "tool:a#2=error"),
])
def test_a_near_miss_is_refused_and_names_the_valid_name(bad: str, control: str) -> None:
    """Ruling 2. The suggestion is a whole valid name, one a user can type back, with the wrong
    word mended and the rest as they wrote it. The control is what the suggestion says."""
    c = changes()
    with pytest.raises(c.ChangeError) as refused:
        c.parse(bad)
    assert refused.value.suggestion == control
    assert c.name(c.parse(control)) == control
    assert "\n" not in str(refused.value)


@pytest.mark.parametrize("bad, control", [
    ("tool:a#2=kaboom", "tool:a#2=error"),
    ("tool:a#2=errrrrr", "tool:a#2=error"),   # three edits from `error`
    ("tol:a#2=erorr", "tool:a#2=error"),      # one in the surface and two in the fault
    ("input:typoooos", "input:typos"),        # three edits
    ("nothing:at-all", "input:typos"),
])
def test_past_two_edits_there_is_no_suggestion(bad: str, control: str) -> None:
    c = changes()
    with pytest.raises(c.ChangeError) as refused:
        c.parse(bad)
    assert refused.value.suggestion is None
    c.parse(control)


def test_the_suggestion_is_the_nearest_not_the_first_within_two_edits(fresh_catalogue) -> None:
    """Two faults whose names lie within two edits of what was typed: the closer one is named,
    whichever was registered first."""
    c = fresh_catalogue
    for fault_name in ("spark", "sparks"):
        c.register(_named(c, fault_name))
    for typed, nearest in (("spar", "spark"), ("sparkss", "sparks")):
        with pytest.raises(c.ChangeError) as refused:
            c.parse(f"tool:a#2={typed}")
        assert refused.value.suggestion == f"tool:a#2={nearest}"


def test_the_suggestion_for_a_condition_mends_the_wrong_change_and_parses() -> None:
    c = changes()
    with pytest.raises(c.ChangeError) as refused:
        c.parse("tool:a#2=error + input:typo")
    assert c.parse(refused.value.suggestion) == c.parse("tool:a#2=error + input:typos")


BAD_WITH_CONTROL = [
    # a position the surface does not have, each beside the form it does have
    ("user:repeats", "user:repeats@3"),
    ("user:repeats#3", "user:repeats@3"),
    ("user:repeats@*", "user:repeats@3"),
    ("user:repeats@0", "user:repeats@1"),
    ("user:repeats@-1", "user:repeats@1"),
    ("input:typos#2", "input:typos"),
    ("input:typos@2", "input:typos"),
    ("model:cut_off", "model:cut_off#2"),
    ("model:cut_off@2", "model:cut_off#2"),
    ("model:cut_off~0.3", "model:cut_off#2"),
    ("model:cut_off=x#2", "model:cut_off#2"),
    # calls count from one, and a range runs upward
    ("tool:a#0=error", "tool:a#1=error"),
    ("tool:a#-1=error", "tool:a#1=error"),
    ("tool:a#0-2=error", "tool:a#1-2=error"),
    ("tool:a#4-2=error", "tool:a#2-4=error"),
    ("tool:a#2-=error", "tool:a#2-4=error"),
    ("tool:a#-2=error", "tool:a#2=error"),
    ("tool:a#1.5=error", "tool:a#1=error"),
    ("tool:a#x=error", "tool:a#1=error"),
    ("tool:a#=error", "tool:a#1=error"),
    # a rate is above 0 and at most 1 (ruling 7)
    ("tool:a~0=error", "tool:a~0.5=error"),
    ("tool:a~0.0=error", "tool:a~0.5=error"),
    ("tool:a~1.5=error", "tool:a~1=error"),
    ("tool:a~-0.1=error", "tool:a~0.1=error"),
    ("tool:a~abc=error", "tool:a~0.5=error"),
    ("tool:a~nan=error", "tool:a~0.5=error"),
    ("tool:a~inf=error", "tool:a~0.5=error"),
    ("tool:a~=error", "tool:a~0.5=error"),
    # a piece missing
    ("tool:a=error", "tool:a#1=error"),
    ("tool:a#2", "tool:a#2=error"),
    ("tool:a#2=", "tool:a#2=error"),
    ("tool:#2=error", "tool:a#2=error"),
    ("tool:", "tool:a#2=error"),
    ("typos", "input:typos"),
    # a tool name holding a character the grammar uses
    ("tool:a b#2=error", "tool:ab#2=error"),
    ("tool:a#b#2=error", "tool:ab#2=error"),
    ("tool:a=b#2=error", "tool:ab#2=error"),
    ("tool:a~b#2=error", "tool:ab#2=error"),
    # a dangling join
    ("tool:a#2=error + ", "tool:a#2=error"),
    (" + tool:a#2=error", "tool:a#2=error"),
    ("tool:a#2=error +  + input:typos", "tool:a#2=error + input:typos"),
]


@pytest.mark.parametrize("bad, control", BAD_WITH_CONTROL)
def test_a_malformed_name_is_refused(bad: str, control: str) -> None:
    """Each beside one that differs only in the clause under test, and is taken. Any suggestion
    offered must itself parse."""
    c = changes()
    with pytest.raises(c.ChangeError) as refused:
        c.parse(bad)
    assert "\n" not in str(refused.value)
    if refused.value.suggestion is not None:
        c.parse(refused.value.suggestion)
    c.parse(control)


@pytest.mark.parametrize("bad, control", [
    ("model:slow#2", "tool:a#2=slow"),
    ("model:malformed#2", "tool:a#2=malformed"),
    ("model:stale#2", "tool:a#2=stale"),
    ("model:lost_reply#2", "tool:a#2=lost_reply"),
    ("model:planted_instruction#2", "tool:a#2=planted_instruction"),
    ("tool:a#2=typos", "input:typos"),
    ("tool:a#2=repeats", "user:repeats@2"),
    ("input:error", "tool:a#2=error"),
    ("input:repeats", "user:repeats@2"),
    ("user:error@1", "tool:a#1=error"),
    ("user:typos@1", "input:typos"),
])
def test_a_word_is_only_good_on_its_own_surface(bad: str, control: str) -> None:
    """§3.2 to §3.4 give each surface its own list; a model has no `slow`, a tool no `typos`."""
    c = changes()
    with pytest.raises(c.ChangeError):
        c.parse(bad)
    c.parse(control)


# ---------------------------------------------------------------------------
# BK1.6, the `env` half
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("setting, value", [
    ("inventory", "empty"),
    ("date", "2026-01-01"),
    ("step_limit", "a value with spaces"),
    ("note", "a=b"),
    ("lang", "日本語"),
])
def test_an_env_change_parses_for_what_the_settings_list(setting: str, value: str) -> None:
    """Any name and any value the settings list (ruling 5 for how they are given). A value holding
    `=` is still one value: the name ends at the first `=`."""
    c = changes()
    text = f"env:{setting}={value}"
    env = {setting: [value]}
    change = one(text, env=env)
    assert (change.surface, change.tool, change.fault) == ("env", setting, value)
    assert c.parse(c.name(c.parse(text, env=env)), env=env) == c.parse(text, env=env)


def test_a_listed_number_is_matched_by_its_text() -> None:
    """Ruling 5. TOML can list `step_limit = [3, 5]`; the name is text, and a stored change holds
    text (§6.4)."""
    change = one("env:step_limit=5", env={"step_limit": [3, 5]})
    assert change.fault == "5"
    with pytest.raises(changes().ChangeError):
        changes().parse("env:step_limit=4", env={"step_limit": [3, 5]})


@pytest.mark.parametrize("text, env", [
    ("env:inventory=gone", {"inventory": ["full", "empty"]}),
    ("env:other=empty", {"inventory": ["full", "empty"]}),
    ("env:inventory=empty", {}),
    ("env:inventory=empty", None),
    ("env:inventory=", {"inventory": ["full", "empty"]}),
    ("env:=empty", {"inventory": ["full", "empty"]}),
    ("env:inventory", {"inventory": ["full", "empty"]}),
])
def test_an_env_change_parses_for_no_other(text: str, env: dict[str, list[str]] | None) -> None:
    """The control is the test above: the same name, listed. With nothing listed, nothing parses:
    a framework agent has no such slot (§3.4)."""
    c = changes()
    with pytest.raises(c.ChangeError):
        c.parse(text, env=env)


@pytest.mark.parametrize("bad, nearest", [
    ("env:inventry=empty", "env:inventory=empty"),
    ("env:inventory=empt", "env:inventory=empty"),
])
def test_an_env_near_miss_names_the_listed_one(bad: str, nearest: str) -> None:
    c = changes()
    with pytest.raises(c.ChangeError) as refused:
        c.parse(bad, env={"inventory": ["full", "empty"]})
    assert refused.value.suggestion == nearest


def test_an_env_value_holding_the_join_is_never_read_as_two_changes() -> None:
    """A listed value with ` + ` in it is one value or a refusal, and no test decides which. Two
    changes is the one wrong answer."""
    c = changes()
    env = {"note": ["a + input:typos"]}
    try:
        condition = c.parse("env:note=a + input:typos", env=env)
    except c.ChangeError:
        return
    assert len(condition.changes) == 1
    assert condition.changes[0].fault == "a + input:typos"


def _named(c, fault_name: str):
    """The smallest outside fault: a name and the §11.1 members."""
    return type("Named", (), {
        "name": fault_name, "surface": "tool", "description": "does nothing to the real result",
        "parameters": {}, "real_runs": True,
        "apply": lambda self, call, *, real, params, rng: c.Result(value=real()),
    })()


@pytest.fixture
def fresh_catalogue():
    yield from fresh_changes()
