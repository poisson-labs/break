"""What `break.toml` refuses, and how: one line, naming the key by its path and its line, and the nearest known key.

Invariants pinned here (Break — Plan, the settings module):
- BK4.2 Unknown keys and tables are refused with the key's path, its line, and the nearest known key within two
        edits; each with an accepted control.
- BK4.3 Bad values are refused, one control per clause.

And spec §9.2: errors are one line. No test reads what a message says, only that it is one line and what it carries
(plan §2 item 3).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import run_python
from tests.settings_support import (
    ON_DEMAND_KINDS,
    SAMPLE,
    SHIPPED_KIND,
    assert_one_line,
    doc,
    line_of,
    refused,
    refused_at,
    settings,
    suggests,
)

STAND_IN = "my_app.fakes:refund"

# ---------------------------------------------------------------------------
# BK4.2  unknown keys and tables
# ---------------------------------------------------------------------------

# (the table, the misspelt key, the key it should have been)
MISSPELT = [
    ("target", "knd", "kind"), ("target", "entri", "entry"), ("target", "case", "cases"),
    ("fails", "check", "checks"), ("fails", "outcome", "outcomes"), ("fails", "owne", "own"), ("fails", "als", "also"),
    ("fails", "never_cal", "never_call"), ("fails", "run_second", "run_seconds"),
    ("vary", "tool", "tools"), ("vary", "input", "inputs"), ("vary", "conversations", "conversation"),
    ("vary", "modle", "model"), ("vary", "max_calls", "max_call"),
    ("search", "strategie", "strategy"), ("search", "runz", "runs"), ("search", "control_repeat", "control_repeats"),
    ("search", "cases_per_conditions", "cases_per_condition"), ("search", "seeds", "seed"),
    ("confirm", "candidate", "candidates"), ("confirm", "repeat", "repeats"), ("confirm", "max_diference", "max_difference"),
    ("confirm", "qq", "q"),
    ("limits", "dolars", "dollars"), ("limits", "input_per_milion", "input_per_million"),
    ("limits", "output_per_milion", "output_per_million"), ("limits", "hour", "hours"),
    ("output", "foldr", "folder"),
]


@pytest.mark.parametrize("table, wrong, right", MISSPELT, ids=[f"{t}.{w}" for t, w, _ in MISSPELT])
def test_a_misspelt_key_is_refused_with_its_path_its_line_and_the_nearest_key(table: str, wrong: str, right: str) -> None:
    text = doc(**{table: f"{wrong} = 1"}) if table != "target" else doc().replace("[tools]", f"{wrong} = 1\n\n[tools]")
    suggests(refused_at(text, f"{table}.{wrong}", f"{wrong} = 1"), table, right)


@pytest.mark.parametrize("wrong, right", [("serach", "search"), ("confrim", "confirm"), ("limit", "limits"), ("outpt", "output"),
                                          ("fail", "fails"), ("vari", "vary"), ("targets", "target"), ("tool", "tools")])
def test_a_misspelt_table_is_refused_with_its_name_its_line_and_the_nearest_table(wrong: str, right: str) -> None:
    text = doc() + f"\n[{wrong}]\nruns = 1\n"
    suggests(refused_at(text, wrong, f"[{wrong}]"), right)


def test_a_misspelt_key_at_the_top_is_refused_with_the_nearest_key() -> None:
    text = doc(head="version = 1\nversoin = 1")
    suggests(refused_at(text, "versoin", "versoin ="), "version")


def test_a_misspelt_table_under_another_is_refused_with_its_whole_path() -> None:
    text = doc() + '\n[vary.envv]\na = ["b"]\n'
    assert refused_at(text, "vary.envv", "[vary.envv]").suggestion in ("vary.env", "env")


@pytest.mark.parametrize("wrong, right", [("standin", "stand_in"), ("clas", "class"), ("repeatabl", "repeatable")])
def test_a_misspelt_key_in_a_tools_line_is_refused_with_its_whole_path(wrong: str, right: str) -> None:
    """Spec §3.6 refuses such a line at the session too; here it is a typo in a strict file, so it gets its line."""
    values = {"class": '"write"', "repeatable": "true", "stand_in": f'"{STAND_IN}"'}
    held = dict(values, **{wrong: values[right]})
    del held[right]
    fields = ", ".join(f"{k} = {v}" for k, v in held.items())
    text = doc(tools=f"issue_refund = {{ {fields} }}")
    error = refused_at(text, f"tools.issue_refund.{wrong}", "issue_refund =")
    assert error.suggestion is not None and error.suggestion.split(".")[-1] == right


@pytest.mark.parametrize("wrong, right", [("fools", "tools"), ("tails", "fails")])
def test_between_two_known_tables_the_nearer_is_the_one_suggested(wrong: str, right: str) -> None:
    """Each of these is one edit from the one and two from the other, and the two ways about, so neither the order of
    the list nor the last one found gets it right by luck."""
    suggests(refused(doc() + f"\n[{wrong}]\na = 1\n"), right)


@pytest.mark.parametrize("table, key", [("search", "rxxs"), ("confirm", "candidatxx"), ("vary", "max_caxx")])
def test_two_edits_away_is_near_enough(table: str, key: str) -> None:
    assert refused(doc(**{table: f"{key} = 1"})).suggestion is not None


@pytest.mark.parametrize("table, key", [("search", "xxxs"), ("search", "completely_different"), ("confirm", "zzzzzzzz"),
                                        ("output", "fxxxer"), ("limits", "xxxxs")])
def test_past_two_edits_nothing_is_suggested(table: str, key: str) -> None:
    assert refused_at(doc(**{table: f"{key} = 1"}), f"{table}.{key}", f"{key} = 1").suggestion is None


@pytest.mark.parametrize("name", ["nothing_like_it", "zzzzzzzz"])
def test_a_table_past_two_edits_gets_no_suggestion(name: str) -> None:
    assert refused_at(doc() + f"\n[{name}]\na = 1\n", name, f"[{name}]").suggestion is None


def test_what_is_suggested_is_never_the_key_that_was_refused_or_from_another_table() -> None:
    """`seeds` in `[confirm]` is one edit from `seed`, in `[search]`, and past two from all of `[confirm]`. `seed` here
    would be refused too, so the bare word is wrong; whether to point across tables at the whole path is left open."""
    error = refused(doc(confirm="seeds = 1"))
    assert error.key == "confirm.seeds"
    assert error.suggestion in (None, "search.seed")


@pytest.mark.parametrize("table, key, value", [
    ("target", "kind", '"rollout"'), ("fails", "run_seconds", "60"), ("vary", "max_call", "2"), ("search", "runs", "401"),
    ("confirm", "q", "0.1"), ("limits", "hours", "3"), ("output", "folder", '"x"'),
])
def test_the_key_spelt_right_in_the_same_place_is_taken(table: str, key: str, value: str) -> None:
    """The accepted control for the refusals above."""
    text = doc() if table == "target" else doc(**{table: f"{key} = {value}"})
    settings().loads(text)


@pytest.mark.parametrize("name", ["searches", "runz", "rnus", "anything_at_all", "tools", "version", "search"])
def test_any_name_at_all_is_a_tools_name(name: str) -> None:
    """`[tools]` is keyed by the user's own tools, so nothing in it is a misspelling, however close to a known key."""
    settings().loads(doc(tools=f'{name} = "read"'))


@pytest.mark.parametrize("name", ["searches", "runz", "tools", "version", "search"])
def test_any_name_at_all_is_a_setting_of_ones_own(name: str) -> None:
    settings().loads(doc(vary__env=f'{name} = ["a"]'))


# Where the line comes from: TOML hands back no lines, so the module finds them itself. Each of these is a place a
# search of the text for the key's name finds the wrong line.
LINE_TRAPS = {
    "a comment above holds the key": ("# runz = 1 was tried here\n[search]\n# runz = 2\nrunz = 3\n", "search.runz", 4),
    "the same word in another table": ('[output]\nfolder = "x"\n\n[search]\nrunz = 1\n', "search.runz", 5),
    "the word in a value above": ('[output]\nfolder = "runz = 1"\n\n[search]\nrunz = 1\n', "search.runz", 5),
    "a multi-line string above holds it": ('[vary.env]\nnote = ["""\nrunz = 1\n"""]\n\n[search]\nrunz = 1\n', "search.runz", 7),
    "a known key sharing its start": ('[search]\nruns = 1\nruns_extra = 2\n', "search.runs_extra", 3),
    "a known key on the line above": ('[confirm]\nq = 0.1\nqq = 0.2\n', "confirm.qq", 3),
    "after a multi-line array": ('[vary]\ntools = [\n  "error",\n  "slow",\n]\nmax_callz = 1\n', "vary.max_callz", 6),
    "a quoted key": ('[search]\n"runz" = 1\n', "search.runz", 2),
    "a comment above holds an open quote": ('# "runz" = 1 was tried\n[search]\n# \'runz\nrunz = 1\n', "search.runz", 4),
    "a dotted key under the table's own header": ('[vary]\nmax_call = 1\nenvv.a = ["b"]\n', "vary.envv", 3),
    "the same word twice, once known": ('[search]\nruns = 1\n\n[confirm]\nruns = 1\n', "confirm.runs", 5),
}


@pytest.mark.parametrize("tail, key, line", LINE_TRAPS.values(), ids=LINE_TRAPS.keys())
def test_the_line_is_the_keys_own(tail: str, key: str, line: int) -> None:
    head = doc()
    error = refused(head + tail)
    assert error.key == key
    assert error.line == head.count("\n") + line


@pytest.mark.parametrize("line", ["search.runz = 1", "search = { runz = 1 }"])
def test_the_line_of_a_key_written_at_the_top_in_another_form(line: str) -> None:
    text = doc(head=f"version = 1\n{line}")
    error = refused(text)
    assert error.key == "search.runz"
    assert error.line == line_of(text, line)


def test_the_line_counts_the_same_with_windows_line_endings() -> None:
    text = doc(search="runz = 1")
    error = refused(text.replace("\n", "\r\n"))
    assert error.line == line_of(text, "runz = 1")


def test_a_key_with_a_line_break_in_its_name_still_makes_one_line() -> None:
    assert refused(doc(search='"run\\nz" = 1')).line is not None


def test_a_value_with_a_line_break_in_it_still_makes_one_line() -> None:
    refused(doc(head='version = 1').replace('"rollout"', '"roll\\nout"'))


# ---------------------------------------------------------------------------
# a file that is not TOML at all
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tail, needle", [
    ("[search\nruns = 1\n", "[search"),
    ("[search]\nruns = \n", "runs ="),
    ("[search]\nruns = 1 2\n", "runs = 1 2"),
    ('[output]\nfolder = "unclosed\n', "unclosed"),
    ("just some words\n", "just some words"),
])
def test_what_is_not_toml_is_one_line_with_its_line_and_not_a_toml_error(tail: str, needle: str) -> None:
    text = doc() + tail
    assert refused(text).line == line_of(text, needle)


@pytest.mark.parametrize("tail", ["[search]\nruns = 1\nruns = 2\n", "[search]\nruns = 1\n[search]\nseed = 1\n"])
def test_a_key_or_a_table_given_twice_is_refused(tail: str) -> None:
    refused(doc() + tail)


# ---------------------------------------------------------------------------
# what the file must hold
# ---------------------------------------------------------------------------


def test_an_empty_file_is_refused_naming_the_target() -> None:
    assert refused("version = 1\n").key.startswith("target")


@pytest.mark.parametrize("key", ["kind", "entry"])
def test_a_target_with_no_kind_or_no_entry_is_refused_naming_it(key: str) -> None:
    """§9.4 gives neither a default, and nothing else could say what to hunt."""
    text = "\n".join(line for line in doc().splitlines() if not line.startswith(key))
    assert refused(text).key == f"target.{key}"


# ---------------------------------------------------------------------------
# BK4.3  bad values: a kind not offered
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["autogen", "Rollout", "open-agents", ""])
def test_a_kind_not_offered_is_refused_on_its_line(kind: str) -> None:
    text = doc(kind=kind)
    refused_at(text, "target.kind", "kind =")


def test_a_kind_that_is_not_text_is_refused() -> None:
    refused_at(doc().replace('kind = "rollout"', "kind = 7"), "target.kind", "kind =")


@pytest.mark.parametrize("kind", (SHIPPED_KIND, *ON_DEMAND_KINDS))
def test_each_kind_the_spec_offers_is_taken(kind: str) -> None:
    settings().loads(doc(kind=kind))


# ---------------------------------------------------------------------------
# a fault, operator, move or check not in the catalogue
# ---------------------------------------------------------------------------

# (the key, a name from another list or misspelt, the right list).
NOT_IN_CATALOGUE = [
    ("vary", "tools", "Error"), ("vary", "tools", "erorr"), ("vary", "tools", "typos"), ("vary", "tools", "repeats"), ("vary", "tools", ""),
    ("vary", "inputs", "typo"), ("vary", "inputs", "error"), ("vary", "inputs", "presses"),
    ("vary", "conversation", "repeat"), ("vary", "conversation", "typos"), ("vary", "conversation", "error"),
    ("vary", "model", "errors"), ("vary", "model", "slow"), ("vary", "model", "stale"), ("vary", "model", "typos"),
    ("fails", "checks", "crashd"), ("fails", "checks", "error"), ("fails", "also", "gave_upp"), ("fails", "also", "crashd"),
]


@pytest.mark.parametrize("table, key, word", NOT_IN_CATALOGUE, ids=[f"{t}.{k}={w}" for t, k, w in NOT_IN_CATALOGUE])
def test_a_name_not_in_its_own_list_is_refused(table: str, key: str, word: str) -> None:
    refused_at(doc(kind="langgraph", **{table: f'{key} = ["{word}"]'}), f"{table}.{key}", f"{key} =")


@pytest.mark.parametrize("key, word", [("tools", "stale"), ("inputs", "variant")])
def test_one_bad_name_after_good_ones_is_refused(key: str, word: str) -> None:
    refused_at(doc(vary=f'{key} = ["{word}", "nothing_like_it"]'), f"vary.{key}", f"{key} =")


GOOD_NAMES = [
    ("vary", "tools", ["error", "timeout", "slow", "rate_limited", "empty", "cut_off", "malformed", "stale", "lost_reply", "planted_instruction"]),
    ("vary", "inputs", ["typos", "reordered", "padded", "cut_short", "variant"]),
    ("vary", "conversation", ["repeats", "interrupts", "goes_quiet", "presses"]),
    ("vary", "model", ["error", "timeout", "rate_limited", "empty", "cut_off"]),
    ("fails", "checks", ["crashed", "hung", "ran_out", "forbidden_call", "followed_plant", "duplicate_write", "wrong"]),
    ("fails", "also", ["gave_up", "retry_storm", "over_budget"]),
]


@pytest.mark.parametrize("table, key, words", GOOD_NAMES, ids=[f"{t}.{k}" for t, k, _ in GOOD_NAMES])
def test_every_name_in_its_own_list_is_taken_one_at_a_time(table: str, key: str, words: list[str]) -> None:
    for word in words:
        settings().loads(doc(kind="langgraph", **{table: f'{key} = ["{word}"]'}))


@pytest.mark.parametrize("table, key", [("vary", "tools"), ("vary", "inputs"), ("vary", "conversation"), ("vary", "model"),
                                        ("fails", "checks"), ("fails", "also"), ("fails", "outcomes"), ("fails", "never_call")])
@pytest.mark.parametrize("value", ['"error"', "3", '[3]', "true", '{ a = "b" }'])
def test_a_list_of_names_that_is_not_one_is_refused(table: str, key: str, value: str) -> None:
    refused_at(doc(kind="langgraph", **{table: f"{key} = {value}"}), f"{table}.{key}", f"{key} =")


REGISTER = """
import json
from poisson_break import changes
from poisson_break.settings import SettingsError, loads

class Mine:
    name = "garbled"
    surface = "tool"
    description = "Hands the agent a garbled result."
    parameters = {}
    real_runs = True
    def apply(self, call, *, real, params, rng):
        return changes.Result(value=real())

TEXT = 'version = 1\\n[target]\\nkind = "rollout"\\nentry = "a:b"\\ncases = "c"\\n[tools]\\nt = "read"\\n[vary]\\ntools = ["garbled"]\\n'
try:
    loads(TEXT)
    before = "taken"
except SettingsError:
    before = "refused"
changes.register(Mine())
loads(TEXT)
print(json.dumps(before))
"""


def test_a_fault_added_from_outside_is_taken_once_it_is_registered_and_refused_before() -> None:
    """Spec §11.1: the catalogue is live. A list of the ten written into the module would turn away every fault
    added later, which is a core change for a thing that must need none."""
    ran = run_python(REGISTER)
    assert ran.exit == 0, ran.stderr
    assert ran.stdout.strip() == '"refused"'


# ---------------------------------------------------------------------------
# whole numbers of at least 1
# ---------------------------------------------------------------------------

AT_LEAST_ONE = [("search", "runs"), ("search", "control_repeats"), ("search", "cases_per_condition"), ("confirm", "candidates"),
                ("confirm", "repeats"), ("vary", "max_call")]
NOT_WHOLE = ["0", "-1", "-400", "1.5", "4.0", "true", '"4"', "[4]", "nan", "inf"]


@pytest.mark.parametrize("table, key", AT_LEAST_ONE, ids=[f"{t}.{k}" for t, k in AT_LEAST_ONE])
@pytest.mark.parametrize("value", NOT_WHOLE)
def test_a_count_below_one_or_not_a_whole_number_is_refused(table: str, key: str, value: str) -> None:
    refused_at(doc(**{table: f"{key} = {value}"}), f"{table}.{key}", f"{key} =")


@pytest.mark.parametrize("table, key", AT_LEAST_ONE, ids=[f"{t}.{k}" for t, k in AT_LEAST_ONE])
def test_a_count_of_one_is_taken(table: str, key: str) -> None:
    settings().loads(doc(**{table: f"{key} = 1"}))


# ---------------------------------------------------------------------------
# inside (0, 1)
# ---------------------------------------------------------------------------

SHARES = [("confirm", "max_difference"), ("confirm", "q")]


@pytest.mark.parametrize("table, key", SHARES, ids=[k for _, k in SHARES])
@pytest.mark.parametrize("value", ["0", "1", "0.0", "1.0", "-0.1", "1.5", "nan", "inf", "-inf", "true", '"0.2"', "[0.2]"])
def test_a_share_outside_zero_and_one_is_refused(table: str, key: str, value: str) -> None:
    refused_at(doc(**{table: f"{key} = {value}"}), f"{table}.{key}", f"{key} =")


@pytest.mark.parametrize("table, key", SHARES, ids=[k for _, k in SHARES])
@pytest.mark.parametrize("value", ["0.0001", "0.5", "0.9999"])
def test_a_share_inside_zero_and_one_is_taken(table: str, key: str, value: str) -> None:
    settings().loads(doc(**{table: f"{key} = {value}"}))


# ---------------------------------------------------------------------------
# tool lines
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("line", ['issue_refund = "write"', 'issue_refund = { class = "write" }',
                                  'issue_refund = { class = "write", repeatable = false }'])
def test_a_write_tool_not_made_safe_is_refused_on_its_line(line: str) -> None:
    error = refused(doc(tools=line))
    assert error.key is not None and error.key.startswith("tools.issue_refund")
    assert error.line == line_of(doc(tools=line), "issue_refund =")


@pytest.mark.parametrize("line", ['issue_refund = { class = "write", repeatable = true }',
                                  f'issue_refund = {{ class = "write", stand_in = "{STAND_IN}" }}',
                                  f'issue_refund = {{ class = "write", repeatable = false, stand_in = "{STAND_IN}" }}'])
def test_a_write_tool_that_says_how_is_taken(line: str) -> None:
    settings().loads(doc(tools=line))


def test_an_unsafe_write_tool_among_safe_ones_is_the_one_named() -> None:
    text = doc(tools=f'lookup_order = "read"\nsafe = {{ class = "write", repeatable = true }}\nunsafe = {{ class = "write" }}\nother = {{ class = "write", stand_in = "{STAND_IN}" }}')
    assert refused(text).key.startswith("tools.unsafe")


@pytest.mark.parametrize("line", ['t = "delete"', 't = { class = "delete" }', "t = 7", "t = true", "t = []", 't = { repeatable = true }',
                                  't = { class = "write", repeatable = "yes" }', 't = { class = "write", repeatable = 1 }',
                                  f't = {{ class = "write", repeatable = "yes", stand_in = "{STAND_IN}" }}', 't = { class = "read", repeatable = "yes" }',
                                  't = { class = "write", stand_in = 7 }'])
def test_a_line_that_is_no_way_of_classing_a_tool_is_refused(line: str) -> None:
    assert refused(doc(tools=line)).key.startswith("tools.t")


@pytest.mark.parametrize("line", ['t = "read"', 't = "off"', 't = { class = "read" }', 't = { class = "off" }'])
def test_the_ways_of_classing_a_tool_are_taken(line: str) -> None:
    settings().loads(doc(tools=line))


@pytest.mark.parametrize("path", ["nope", ":name", "module:", "my app:name", "a:b:c"])
def test_a_stand_in_that_is_no_import_path_is_refused(path: str) -> None:
    assert refused(doc(tools=f't = {{ class = "write", stand_in = "{path}" }}')).key.startswith("tools.t")


def test_tools_that_are_not_a_table_are_refused() -> None:
    text = doc().replace('[tools]\nlookup_order = "read"\n', "").replace("version = 1", "version = 1\ntools = 3")
    assert refused(text).key == "tools"


# ---------------------------------------------------------------------------
# no finite limit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["inf", "+inf"])
def test_no_finite_limit_at_all_is_refused(value: str) -> None:
    assert refused(doc(limits=f"hours = {value}")).key.startswith("limits")


@pytest.mark.parametrize("value", ["2", "0.5", "1000"])
def test_a_finite_number_of_hours_is_taken(value: str) -> None:
    settings().loads(doc(limits=f"hours = {value}"))


@pytest.mark.parametrize("value", ["0", "-1", "nan", '"2"', "true"])
def test_a_number_of_hours_that_is_no_amount_is_refused(value: str) -> None:
    refused_at(doc(limits=f"hours = {value}"), "limits.hours", "hours =")


@pytest.mark.parametrize("key", ["dollars", "input_per_million", "output_per_million"])
@pytest.mark.parametrize("value", ["-1", "nan", '"5"', "true"])
def test_a_cap_or_a_price_that_is_no_amount_is_refused(key: str, value: str) -> None:
    """Beside the other two, since a cap or a price on its own is refused for another reason (yes/no 6)."""
    good = {"dollars": 5.0, "input_per_million": 0.05, "output_per_million": 0.4}
    lines = "\n".join(f"{k} = {value if k == key else v}" for k, v in good.items())
    refused_at(doc(limits=lines), f"limits.{key}", f"{key} =")


@pytest.mark.parametrize("lines", ["dollars = 5.0", "dollars = 5.0\ninput_per_million = 0.05", "dollars = 5.0\noutput_per_million = 0.4",
                                   "input_per_million = 0.05", "output_per_million = 0.4"])
def test_a_cap_without_both_prices_or_one_price_alone_is_refused(lines: str) -> None:
    """Yes/no 6: a cap that could never fire is worse than none, since BK5.9 can only measure dollars from prices."""
    assert refused(doc(limits=lines)).key.startswith("limits")


def test_two_prices_are_taken_without_a_cap() -> None:
    settings().loads(doc(limits="input_per_million = 0.05\noutput_per_million = 0.40"))


def test_a_cap_and_two_prices_are_taken() -> None:
    settings().loads(doc(limits="dollars = 5.00\ninput_per_million = 0.05\noutput_per_million = 0.40"))


@pytest.mark.parametrize("value", ["0", "-1", "nan", '"120"', "true", "[120]"])
def test_a_time_limit_on_a_run_that_is_no_time_is_refused(value: str) -> None:
    refused_at(doc(fails=f"run_seconds = {value}"), "fails.run_seconds", "run_seconds =")


@pytest.mark.parametrize("value", ["1", "0.5", "86400"])
def test_a_time_limit_on_a_run_is_taken(value: str) -> None:
    settings().loads(doc(fails=f"run_seconds = {value}"))


# ---------------------------------------------------------------------------
# the version
# ---------------------------------------------------------------------------


def test_a_version_above_this_modules_is_refused_on_its_line() -> None:
    s = settings()
    text = doc(head=f"version = {s.SCHEMA_VERSION + 1}")
    refused_at(text, "version", "version =")


@pytest.mark.parametrize("head", ["", "# version = 1"])
def test_a_file_with_no_version_is_refused_naming_it(head: str) -> None:
    """Yes/no 7."""
    assert refused(doc(head=head)).key == "version"


def test_this_modules_version_is_taken() -> None:
    s = settings()
    s.loads(doc(head=f"version = {s.SCHEMA_VERSION}"))


@pytest.mark.parametrize("value", ['"1"', "1.5", "1.0", "true", "[1]"])
def test_a_version_that_is_no_whole_number_is_refused(value: str) -> None:
    refused_at(doc(head=f"version = {value}"), "version", "version =")


# ---------------------------------------------------------------------------
# the strategy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ['"best"', '"Screen"', '""', '":Name"', '"module:"', '"a:b:c"', '"my app:Name"', '"mod.:Name"', '".mod:Name"', "7", "true", '["screen"]'])
def test_a_strategy_that_is_neither_a_built_in_nor_an_import_path_is_refused(value: str) -> None:
    refused_at(doc(search=f"strategy = {value}"), "search.strategy", "strategy =")


@pytest.mark.parametrize("value", ["screen", "random", "module:Name", "pkg.sub.mod:Name", "my_mod2:name_2"])
def test_a_built_in_or_an_import_path_is_taken(value: str) -> None:
    settings().loads(doc(search=f'strategy = "{value}"'))


# ---------------------------------------------------------------------------
# anything else malformed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table, key", [("search", "seed")])
@pytest.mark.parametrize("value", ["1.5", '"7"', "true", "[7]"])
def test_a_seed_that_is_no_whole_number_is_refused(table: str, key: str, value: str) -> None:
    refused_at(doc(**{table: f"{key} = {value}"}), f"{table}.{key}", f"{key} =")


@pytest.mark.parametrize("value", ['"nope"', '":name"', '"module:"', "7", "true", '["a:b"]'])
def test_an_own_check_that_is_no_import_path_is_refused(value: str) -> None:
    refused_at(doc(fails=f"own = {value}"), "fails.own", "own =")


def test_an_own_check_named_by_an_import_path_is_taken() -> None:
    settings().loads(doc(fails='own = "my_app.checks:refund_ok"'))


@pytest.mark.parametrize("old, new, key", [
    ('entry = "my_app.agents:refund_agent"', "entry = 7", "target.entry"),
    ('cases = "cases.jsonl"', "cases = 7", "target.cases"),
    ('cases = "cases.jsonl"', 'cases = ["a"]', "target.cases"),
])
def test_a_target_value_that_is_not_text_is_refused(old: str, new: str, key: str) -> None:
    text = doc().replace(old, new)
    refused_at(text, key, new)


@pytest.mark.parametrize("value", ["7", "true", '["x"]'])
def test_a_folder_that_is_not_text_is_refused(value: str) -> None:
    refused_at(doc(output=f"folder = {value}"), "output.folder", "folder =")


@pytest.mark.parametrize("table", ["search", "confirm", "fails", "vary", "limits", "output"])
def test_a_table_given_as_a_single_value_is_refused(table: str) -> None:
    assert refused(doc(head=f"version = 1\n{table} = 3")).key == table


def test_a_target_given_as_a_single_value_is_refused() -> None:
    assert refused("version = 1\ntarget = 3\n").key == "target"


@pytest.mark.parametrize("tail", ["[[search]]\nruns = 1\n", "[[vary.env]]\na = 1\n"])
def test_a_table_given_as_a_list_of_tables_is_refused(tail: str) -> None:
    refused(doc() + tail)


@pytest.mark.parametrize("value", ["2026-11-04", "2026-11-04T10:00:00Z"])
def test_a_date_is_not_a_value_of_any_setting(value: str) -> None:
    refused_at(doc(search=f"runs = {value}"), "search.runs", "runs =")


@pytest.mark.parametrize("line", ['inventory = "full"', "inventory = 3", 'inventory = { a = "b" }', 'inventory = [["a"]]', 'inventory = [{ a = "b" }]'])
def test_a_setting_of_ones_own_that_is_no_list_of_values_is_refused(line: str) -> None:
    """§3.4: "with the values Break may choose from". `parse` reads these (the catalogue's ruling 5)."""
    assert refused(doc(vary__env=line)).key.startswith("vary.env.inventory")


# ---------------------------------------------------------------------------
# what every refusal carries, read from a file as well as from text
# ---------------------------------------------------------------------------


def test_a_refusal_carries_its_three_facts_even_when_there_is_no_suggestion() -> None:
    error = refused(doc(search="runs = 0"))
    assert error.key == "search.runs"
    assert isinstance(error.line, int)
    assert error.suggestion is None


def test_load_refuses_as_loads_does_with_the_same_key_and_line(tmp_path: Path) -> None:
    s = settings()
    text = doc(search="runz = 1")
    path = tmp_path / "break.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(s.SettingsError) as caught:
        s.load(path)
    assert_one_line(caught.value)
    assert caught.value.key == "search.runz"
    assert caught.value.line == line_of(text, "runz = 1")
    suggests(caught.value, "search", "runs")


def test_a_file_that_is_not_text_is_one_line_and_not_a_decoding_error(tmp_path: Path) -> None:
    s = settings()
    path = tmp_path / "break.toml"
    path.write_bytes(b"version = 1\n\xff\xfe\xfd\n")
    with pytest.raises(s.SettingsError) as caught:
        s.load(path)
    assert_one_line(caught.value)


def test_the_file_the_spec_prints_breaks_at_the_line_of_a_typo_put_into_it() -> None:
    """The whole file, comments and a multi-line array above, with one typo near the end."""
    text = SAMPLE.replace("hours = 2", "hoursz = 2")
    suggests(refused_at(text, "limits.hoursz", "hoursz ="), "limits", "hours")
