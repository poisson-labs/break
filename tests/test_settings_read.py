"""Reading `break.toml`: every setting, its default as ruled, and the file coming back as it went out.

Invariants pinned here (Break — Plan, the settings module):
- BK4.1 Round trip over every key: `loads(dump(s)) == s`, for every key of spec §9.4. The half of BK4.1 that goes
        through `init`'s flags, and BK4.4, are in `test_settings_init.py`.

And the defaults of plan ruling 19 and spec §9.4, and "the frozen settings types".

A value is read through the file, never through a field (`tests/settings_support.py`).
"""

from __future__ import annotations

import dataclasses
import tomllib
from collections.abc import MutableMapping, MutableSequence, MutableSet
from pathlib import Path
from typing import Any

import pytest

from tests.apply_support import apply
from tests.changes_support import changes
from tests.settings_support import DEFAULTS, ON_DEMAND_KINDS, OPTIONAL, PRICES, SAMPLE, doc, settings, written

STAND_IN = "tests.apply_support_standin:refund"


# ---------------------------------------------------------------------------
# the defaults as ruled
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table, key, default, other, other_read", DEFAULTS, ids=[f"{t}.{k}" for t, k, *_ in DEFAULTS])
def test_leaving_a_key_out_reads_as_its_default_and_any_other_value_does_not(table: str, key: str, default: str, other: str, other_read: Any) -> None:
    s = settings()
    bare = s.loads(doc())
    assert s.loads(doc(**{table: f"{key} = {default}"})) == bare
    assert s.loads(doc(**{table: f"{key} = {other}"})) != bare


@pytest.mark.parametrize("table, key, default, other, other_read", DEFAULTS, ids=[f"{t}.{k}" for t, k, *_ in DEFAULTS])
def test_a_value_set_in_a_key_comes_back_under_that_key(table: str, key: str, default: str, other: str, other_read: Any) -> None:
    assert written(doc(**{table: f"{key} = {other}"}))[table][key] == other_read


def test_leaving_every_table_out_reads_as_the_file_the_spec_prints() -> None:
    """§9.4 printed whole, its target and tools given, and the same with the rest left out."""
    s = settings()
    tools = 'lookup_order = "read"\ncheck_policy = "read"\nissue_refund = { class = "write", stand_in = "my_app.fakes:refund" }'
    assert s.loads(SAMPLE) == s.loads(doc(kind="openai-agents", tools=tools))


def test_a_table_left_out_and_a_table_left_empty_read_the_same() -> None:
    s = settings()
    assert s.loads(doc()) == s.loads(doc(search="", confirm="", vary="", fails="", limits="", output=""))


def test_what_the_target_table_holds_counts_in_the_settings_value() -> None:
    """Its three keys are not in the table of defaults, so a reader that dropped one would otherwise pass."""
    s = settings()
    base = doc()
    for old, new in (('"rollout"', '"langgraph"'), ("refund_agent", "other_agent"), ("cases.jsonl", "other.jsonl")):
        assert s.loads(base.replace(old, new)) != s.loads(base)


@pytest.mark.parametrize("key", ["tools", "inputs"])
def test_an_empty_list_turns_the_list_off_and_does_not_read_as_the_default(key: str) -> None:
    """§5.3 counts "faults turned off", and §9.3 question 6 lets the user say no to inputs. `x or default` would hand
    the whole list back to someone who had just turned it off."""
    s = settings()
    text = doc(vary=f"{key} = []")
    assert s.loads(text) != s.loads(doc())
    assert written(text)["vary"][key] == []


@pytest.mark.parametrize("table, key", [("fails", "outcomes"), ("fails", "own"), ("fails", "also"), ("fails", "never_call"),
                                        ("fails", "max_tool_calls"), ("fails", "max_tokens"),
                                        ("vary", "conversation"), ("vary", "model"), ("limits", "dollars"),
                                        ("limits", "input_per_million"), ("limits", "output_per_million")])
def test_what_the_spec_prints_commented_out_is_off_unless_asked_for(table: str, key: str) -> None:
    """§9.3 question 6 says model calls no and the conversation only if asked; §9.3 question 8 says without prices
    Break shows no dollars. How `dump` writes "nothing" is its own."""
    assert not written(doc()).get(table, {}).get(key)


@pytest.mark.parametrize("table, key, toml_value, read", OPTIONAL, ids=[f"{t}.{k}" for t, k, *_ in OPTIONAL])
def test_an_optional_key_set_comes_back_and_differs_from_leaving_it_out(table: str, key: str, toml_value: str, read: Any) -> None:
    s = settings()
    text = doc(kind="langgraph", **{table: f"{key} = {toml_value}"})
    assert written(text)[table][key] == read
    assert s.loads(text) != s.loads(doc(kind="langgraph"))


def test_the_prices_and_the_cap_come_back_each_under_its_own_key() -> None:
    limits = written(doc(limits=PRICES))["limits"]
    assert limits["dollars"] == 7.5
    assert limits["input_per_million"] == 0.125
    assert limits["output_per_million"] == 0.5


def test_two_prices_with_no_cap_read_as_a_cap_of_five_dollars() -> None:
    """Yes/no 6, from §9.3 question 9's default: a cap exists whenever prices do."""
    s = settings()
    prices = "input_per_million = 0.125\noutput_per_million = 0.5"
    assert written(doc(limits=prices))["limits"]["dollars"] == 5.0
    assert s.loads(doc(limits=prices)) == s.loads(doc(limits=f"{prices}\ndollars = 5.00"))
    assert s.loads(doc(limits=prices)) != s.loads(doc(limits=f"{prices}\ndollars = 6.00"))


def test_settings_of_ones_own_come_back_under_their_names() -> None:
    env = written(doc(vary__env='inventory = ["full", "empty"]\nretries = [3, 5]'))["vary"]["env"]
    assert env == {"inventory": ["full", "empty"], "retries": [3, 5]}


# ---------------------------------------------------------------------------
# every key at once, none of them holding its default
# ---------------------------------------------------------------------------


EVERYTHING = doc(
    kind="langgraph",
    tools=f'lookup_order = "read"\ncheck_policy = "off"\nissue_refund = {{ class = "write", stand_in = "{STAND_IN}" }}\nupdate_notes = {{ class = "write", repeatable = true }}',
    fails='checks = ["hung", "wrong"]\noutcomes = ["unresolved", "escalated"]\nown = "my_app.checks:refund_ok"\nalso = ["retry_storm"]\nnever_call = ["delete_account"]\nrun_seconds = 61\nretry_storm_after = 8\nmax_tool_calls = 41\nmax_tokens = 20001',
    vary='tools = ["slow", "stale"]\ninputs = ["padded"]\nconversation = ["presses"]\nmodel = ["cut_off"]\nmax_call = 2',
    vary__env='inventory = ["full", "empty"]\nretries = [3, 5]',
    search='strategy = "my_app.search:Mine"\nruns = 402\ncontrol_repeats = 7\ncases_per_condition = 2\nseed = 11',
    confirm='candidates = 10\nrepeats = 3\nmax_difference = 0.35\nq = 0.15',
    limits=PRICES + "\nhours = 4",
    output='folder = "runs-here"',
)


def test_every_key_set_at_once_comes_back_under_its_own_key() -> None:
    """A swap of two keys of the same type shows here: no two of these hold the same value."""
    got = written(EVERYTHING)
    assert got["version"] == 1
    assert got["target"] == {"kind": "langgraph", "entry": "my_app.agents:refund_agent", "cases": "cases.jsonl"}
    tools = got["tools"]
    assert tool_class(tools["lookup_order"]) == "read"
    assert tool_class(tools["check_policy"]) == "off"
    assert tools["issue_refund"]["class"] == "write" and tools["issue_refund"]["stand_in"] == STAND_IN
    assert tools["update_notes"]["class"] == "write" and tools["update_notes"]["repeatable"] is True
    assert got["fails"] == {"checks": ["hung", "wrong"], "outcomes": ["unresolved", "escalated"], "own": "my_app.checks:refund_ok",
                            "also": ["retry_storm"], "never_call": ["delete_account"], "run_seconds": 61,
                            "retry_storm_after": 8, "max_tool_calls": 41, "max_tokens": 20001}
    assert got["vary"] == {"tools": ["slow", "stale"], "inputs": ["padded"], "conversation": ["presses"], "model": ["cut_off"],
                           "max_call": 2, "env": {"inventory": ["full", "empty"], "retries": [3, 5]}}
    assert got["search"] == {"strategy": "my_app.search:Mine", "runs": 402, "control_repeats": 7, "cases_per_condition": 2, "seed": 11}
    assert got["confirm"] == {"candidates": 10, "repeats": 3, "max_difference": 0.35, "q": 0.15}
    assert got["limits"] == {"dollars": 7.5, "input_per_million": 0.125, "output_per_million": 0.5, "hours": 4}
    assert got["output"] == {"folder": "runs-here"}


def tool_class(line: Any) -> Any:
    """A tool's line says its class as a word or as `class` in a table; §9.4 writes both."""
    return line if isinstance(line, str) else line["class"]


def test_every_key_the_spec_prints_comes_back() -> None:
    """Reads the file printed in the spec with its commented lines put back, so that a key in §9.4 that `EVERYTHING`
    forgot, or one `dump` lost, shows here by name."""
    uncommented = "\n".join(line[2:] if line.startswith("# ") and "=" in line.split("#")[1] else line for line in SAMPLE.splitlines())
    printed = tomllib.loads(uncommented.replace("# [vary.env]", "[vary.env]"))
    got = written(EVERYTHING)
    for table, keys in printed.items():
        if table in ("tools", "version"):
            continue
        for key in keys:
            assert key in got[table], f"{table}.{key} is printed in the spec and did not come back"


# ---------------------------------------------------------------------------
# the file coming back as it went out (BK4.1)
# ---------------------------------------------------------------------------


ROUND_TRIPS = {
    "the file the spec prints": SAMPLE,
    "the bare file": doc(),
    "every key": EVERYTHING,
    **{f"the kind {k}": doc(kind=k) for k in ON_DEMAND_KINDS},
    "a quote in a value": doc(output='folder = "a \\"quoted\\" folder"'),
    "a backslash in a value": doc(output='folder = "C:\\\\runs\\\\here"'),
    "a newline and a tab in a value": doc(vary__env='note = ["one\\ntwo\\tthree"]'),
    "a hash in a value": doc(output='folder = "runs #1"'),
    "a literal string with what TOML would escape": doc(output="folder = 'a\\b\"c'"),
    "text beyond plain ascii": doc(output='folder = "Lauf-Ergebnisse-日本語-é"'),
    "a control character": doc(vary__env='note = ["bell\\u0007here"]'),
    "a tool's name holding a dot": doc(tools='"billing.refund" = "read"'),
    "a tool's name holding a space": doc(tools='"look up order" = "read"'),
    "a tool's name holding a quote": doc(tools='"say \\"hi\\"" = "read"'),
    "a tool's name beyond plain ascii": doc(tools='"prüfen" = "read"'),
    "capitals, kept as they are": doc(tools='LookupOrder = { class = "write", stand_in = "My_App.Fakes:Refund" }', vary__env='Region = ["EU", "US"]', output='folder = "Runs"'),
    "a setting's name that needs quotes": doc(vary__env='"my.setting" = ["a"]'),
    "the numbers and words of a setting of one's own": doc(vary__env='mixed = [3, 2.5, true, "word"]'),
    "a value holding what looks like TOML": doc(vary__env='note = ["[search]\\nruns = 1"]'),
    "a float with every digit": doc(confirm="max_difference = 0.30000000000000004\nq = 0.1"),
    "a small float": doc(confirm="q = 1e-10"),
    "a whole number of hours as a fraction": doc(limits="hours = 1.5"),
    "a big seed": doc(search="seed = 9007199254740993"),
    "a run budget of one": doc(search="runs = 1"),
    "an own check, signals and forbidden tools": doc(fails='own = "a.b:c"\nalso = ["gave_up", "over_budget"]\nnever_call = ["x", "y"]'),
    "a tool with both a stand-in and repeatable": doc(tools=f'w = {{ class = "write", repeatable = true, stand_in = "{STAND_IN}" }}'),
    "a read tool in a table": doc(tools='r = { class = "read" }'),
    "an off tool": doc(tools='o = "off"'),
    "no faults": doc(vary="tools = []"),
    "a strategy of one's own": doc(search='strategy = "pkg.sub.mod:Strategy"'),
    "the strategy not yet built": doc(search='strategy = "adaptive"'),
}


@pytest.mark.parametrize("text", ROUND_TRIPS.values(), ids=ROUND_TRIPS.keys())
def test_what_dump_writes_reads_back_equal(text: str) -> None:
    s = settings()
    read = s.loads(text)
    assert s.loads(s.dump(read)) == read


@pytest.mark.parametrize("text", ROUND_TRIPS.values(), ids=ROUND_TRIPS.keys())
def test_writing_again_what_was_read_back_is_the_same_text(text: str) -> None:
    """The two renderings of the equivalent command must end byte for byte the same (BK4.4), which has no chance if
    the file drifts each time it goes through."""
    s = settings()
    once = s.dump(s.loads(text))
    assert s.dump(s.loads(once)) == once


def test_a_float_comes_back_to_the_last_bit() -> None:
    assert written(doc(confirm="max_difference = 0.30000000000000004"))["confirm"]["max_difference"] == 0.30000000000000004


@pytest.mark.parametrize("line, read", [
    ('folder = "a \\"quoted\\" folder"', 'a "quoted" folder'),
    ('folder = "C:\\\\runs\\\\here"', "C:\\runs\\here"),
    ('folder = "runs #1"', "runs #1"),
    ('folder = "Lauf-日本語"', "Lauf-日本語"),
])
def test_a_written_string_is_the_string_that_was_read(line: str, read: str) -> None:
    assert written(doc(output=line))["output"]["folder"] == read


@pytest.mark.parametrize("name", ["billing.refund", "look up order", 'say "hi"', "prüfen"])
def test_a_tools_name_is_kept_whole_through_the_file(name: str) -> None:
    """A dot in a bare TOML key is two keys: written bare, the tool would come back as a table of another name."""
    quoted = name.replace('"', '\\"')
    assert list(written(doc(tools=f'"{quoted}" = "read"'))["tools"]) == [name]


def test_the_ways_toml_can_write_one_table_read_the_same() -> None:
    s = settings()
    plain = s.loads(doc(search="runs = 401\nseed = 7"))
    assert s.loads(doc(head='version = 1\nsearch = { runs = 401, seed = 7 }')) == plain
    assert s.loads(doc(head='version = 1\nsearch.runs = 401\nsearch.seed = 7')) == plain


def test_comments_and_line_endings_change_nothing() -> None:
    s = settings()
    text = doc(search="runs = 401")
    assert s.loads(text.replace("runs = 401", "# a comment\nruns = 401 # another")) == s.loads(text)
    assert s.loads(text.replace("\n", "\r\n")) == s.loads(text)


def test_the_version_is_written_as_the_modules_own_number() -> None:
    s = settings()
    assert s.SCHEMA_VERSION == 1
    assert written(doc())["version"] == s.SCHEMA_VERSION


def test_load_reads_a_file_as_loads_reads_its_text(tmp_path: Path) -> None:
    s = settings()
    text = doc(search="runs = 401", tools='"prüfen" = "read"')
    path = tmp_path / "break.toml"
    path.write_text(text, encoding="utf-8")
    assert s.load(path) == s.loads(text)
    assert s.load(path) != s.loads(doc())


# ---------------------------------------------------------------------------
# what the file hands to the modules that read it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("line, condition", [
    ('lookup_order = "read"', "tool:lookup_order#1=error"),
    ('lookup_order = { class = "read" }', "tool:lookup_order#1=error"),
    ('lookup_order = { class = "write", repeatable = true }', "tool:lookup_order#1=lost_reply"),
    (f'lookup_order = {{ class = "write", stand_in = "{STAND_IN}" }}', "tool:lookup_order#1=lost_reply"),
    ('lookup_order = "off"\nother = "read"', "tool:other#1=error"),
])
def test_a_tools_line_as_written_is_one_a_session_takes(line: str, condition: str) -> None:
    """Plan BK2.5: a session is given each tool's line as `[tools]` writes it. A line renamed on its way through
    this module would be refused there, on the first run of a hunt."""
    tools = written(doc(tools=line))["tools"]
    apply().Session(changes().parse(condition), seed=1, tools=tools)


def test_a_setting_of_ones_own_as_written_is_what_a_condition_reads() -> None:
    """The catalogue's ruling 5: `parse` takes the `[vary.env]` table, a listed number matched by its text."""
    env = written(doc(vary__env='inventory = ["full", "empty"]\nretries = [3, 5]'))["vary"]["env"]
    for name in ("env:inventory=empty", "env:retries=5"):
        assert changes().name(changes().parse(name, env=env)) == name
    with pytest.raises(changes().ChangeError):
        changes().parse("env:inventory=none", env=env)


# ---------------------------------------------------------------------------
# frozen
# ---------------------------------------------------------------------------


def walk(value: Any, seen: set[int] | None = None) -> list[Any]:
    """Everything a settings value holds, by reading its fields whatever they are called and however it is built."""
    seen = seen if seen is not None else set()
    if id(value) in seen:
        return []
    seen.add(id(value))
    found = [value]
    children: list[Any] = []
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        children = [getattr(value, f.name) for f in dataclasses.fields(value)]
    elif hasattr(value, "items") and callable(value.items):
        for k, v in value.items():
            children += [k, v]
    elif isinstance(value, (list, tuple, set, frozenset)):
        children = list(value)
    elif hasattr(value, "__dict__") and not isinstance(value, type):
        children = list(vars(value).values())
    for child in children:
        found += walk(child, seen)
    return found


def test_a_settings_value_cannot_be_changed_anywhere_inside_it() -> None:
    """"The frozen settings types." A top that refuses assignment over a table that takes it is not frozen."""
    s = settings()
    read = s.loads(EVERYTHING)
    held = walk(read)
    assert len(held) > 20, "the walk found almost nothing, so it shows nothing"
    for value in held:
        assert not isinstance(value, (MutableMapping, MutableSequence, MutableSet)), f"{value!r} can be changed"
        with pytest.raises((AttributeError, TypeError)):
            value.a_new_field = 1


def test_a_settings_value_is_compared_by_what_it_holds() -> None:
    """Without this, `loads(dump(s)) == s` would be a statement about one object."""
    s = settings()
    assert s.loads(doc()) is not s.loads(doc())
    assert s.loads(doc()) == s.loads(doc())
