"""Reading the case file, and what it hands over.

Invariant pinned here (Break — Plan, the settings module):
- BK4.5 Cases: a line without `input` is refused with its line number; ids are unique, and a case without one is
        numbered; an `expect` key not offered is refused. `read_cases` hands a case over as a mapping, which is all
        `Session.case` takes (BK2.13). The catalogue's ruling 9 left this open; plan BK4.5 closed it.

Open and held by no test here, each brought as a ruling: how a numbered id is spelt, a case carrying keys the spec
does not list, blank lines, an empty file, and an `input` that is not text.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from poisson_break.interfaces import Capabilities
from tests.apply_support import ALL_CAPABILITIES, apply
from tests.changes_support import changes
from tests.settings_support import assert_one_line, settings, write_cases


def read(tmp_path: Path, lines: list[str]) -> list[Any]:
    return list(settings().read_cases(write_cases(tmp_path, lines)))


def refused_line(tmp_path: Path, lines: list[str], line: int) -> Any:
    s = settings()
    with pytest.raises(s.SettingsError) as caught:
        list(s.read_cases(write_cases(tmp_path, lines)))
    assert_one_line(caught.value)
    assert caught.value.line == line, f"line {caught.value.line}, not {line}"
    return caught.value


GOOD = json.dumps({"input": "Where is order 7?"})


def session(condition: str = "", **over: Any) -> Any:
    return apply().Session(changes().parse(condition), seed=1, tools={}, **over)


# ---------------------------------------------------------------------------
# what a case is
# ---------------------------------------------------------------------------


def test_a_case_needs_only_its_input(tmp_path: Path) -> None:
    [case] = read(tmp_path, [GOOD])
    assert case["input"] == "Where is order 7?"


def test_each_line_is_one_case_in_the_files_order(tmp_path: Path) -> None:
    got = read(tmp_path, [json.dumps({"input": f"question {n}"}) for n in range(5)])
    assert [c["input"] for c in got] == [f"question {n}" for n in range(5)]


def test_a_case_is_handed_over_as_a_mapping(tmp_path: Path) -> None:
    assert all(isinstance(c, Mapping) for c in read(tmp_path, [GOOD, GOOD]))


@pytest.mark.parametrize("field, value", [
    ("id", "refund-1"),
    ("expect", {"reply_contains": "shipped", "calls": ["lookup_order"], "never_calls": ["issue_refund"]}),
    ("variants", ["Where is it?", "Order 7, where?"]),
    ("turns", ["Hi", "Where is order 7?", "Thanks"]),
])
def test_every_field_the_spec_lists_comes_through_as_written(tmp_path: Path, field: str, value: Any) -> None:
    [case] = read(tmp_path, [json.dumps({"input": "x", field: value})])
    assert case[field] == value
    assert case["input"] == "x"


def test_text_beyond_plain_ascii_comes_through(tmp_path: Path) -> None:
    [case] = read(tmp_path, [json.dumps({"input": "Où est ma commande? 注文"}, ensure_ascii=False)])
    assert case["input"] == "Où est ma commande? 注文"


# ---------------------------------------------------------------------------
# what it is handed to: the applier takes it as it stands
# ---------------------------------------------------------------------------


def test_the_applier_takes_a_case_as_it_comes_under_the_control(tmp_path: Path) -> None:
    [case] = read(tmp_path, [json.dumps({"input": "Where is order 7? Please refund it.", "id": "c"})])
    seen = session().case(case)
    assert seen["input"] == "Where is order 7? Please refund it."
    assert seen["id"] == "c"


def test_an_operator_changes_a_case_as_it_comes_and_the_record_says_so(tmp_path: Path) -> None:
    [case] = read(tmp_path, [json.dumps({"input": "Where is order 7? Please refund it right now, thanks a lot."})])
    s = session("input:typos")
    assert s.case(case)["input"] != case["input"]
    assert s.applied[0].applied is True


def test_a_variant_comes_from_the_cases_own_list(tmp_path: Path) -> None:
    [case] = read(tmp_path, [json.dumps({"input": "x", "variants": ["the other way of asking"]})])
    assert session("input:variant").case(case)["input"] == "the other way of asking"


def test_a_scripted_conversation_comes_from_the_cases_own_turns(tmp_path: Path) -> None:
    [case] = read(tmp_path, [json.dumps({"input": "x", "turns": ["one", "two", "three"]})])
    s = session("user:repeats@2", capabilities=Capabilities(**ALL_CAPABILITIES))
    assert s.case(case)["turns"] == ["one", "one", "three"]


def test_the_catalogues_own_functions_take_a_case_as_it_comes(tmp_path: Path) -> None:
    """The catalogue's ruling 9: operators and moves take the mapping of the JSON line."""
    [case] = read(tmp_path, [json.dumps({"input": "One sentence here. Another sentence there.", "turns": ["a", "b"]})])
    c = changes()
    assert sorted(c.reordered(case, seed=1).replace(".", "").split(" ")) == sorted(case["input"].replace(".", "").split(" "))
    assert c.repeats(case, turn=2, seed=1) == ["a", "a"]


def test_a_cases_id_is_what_the_record_and_the_marker_can_take(tmp_path: Path) -> None:
    """Spec §6.4: the case's id is written into the record, and the marker comes from the hunt and the case."""
    for case in read(tmp_path, [GOOD, json.dumps({"input": "x", "id": "named"})]):
        assert isinstance(case["id"], str) and case["id"]
        assert changes().marker(hunt="h", case=case["id"])


# ---------------------------------------------------------------------------
# a line without `input`, or that is no case
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lines, line", [
    (['{"id": "a"}'], 1),
    ([GOOD, '{"id": "a"}'], 2),
    ([GOOD, GOOD, GOOD, '{"expect": {"calls": ["x"]}}', GOOD], 4),
    ([GOOD, '{"Input": "x"}'], 2),
    ([GOOD, GOOD, "{}"], 3),
])
def test_a_line_without_input_is_refused_with_its_line_number(tmp_path: Path, lines: list[str], line: int) -> None:
    refused_line(tmp_path, lines, line)


def test_a_line_number_counts_every_line_of_the_file(tmp_path: Path) -> None:
    """Whether a blank line is taken is a ruling not yet made. If it is, it still counts as a line: an editor would
    otherwise be sent to the wrong one."""
    try:
        read(tmp_path, [GOOD, "", GOOD])
    except settings().SettingsError as refused_it:
        assert refused_it.line == 2
        return
    refused_line(tmp_path, [GOOD, "", "{}"], 3)


@pytest.mark.parametrize("bad", ["not json", "{", '{"input": "x"', '{"input": "x"} trailing', "'single quotes'"])
def test_a_line_that_is_not_json_is_refused_with_its_line_number(tmp_path: Path, bad: str) -> None:
    refused_line(tmp_path, [GOOD, bad, GOOD], 2)


@pytest.mark.parametrize("bad", ['["input"]', '"input"', "7", "null", "true"])
def test_a_line_that_is_no_table_is_refused_with_its_line_number(tmp_path: Path, bad: str) -> None:
    refused_line(tmp_path, [GOOD, GOOD, bad], 3)


def test_a_file_that_is_not_text_is_one_line_and_not_a_decoding_error(tmp_path: Path) -> None:
    s = settings()
    path = tmp_path / "cases.jsonl"
    path.write_bytes(GOOD.encode() + b"\n\xff\xfe\n")
    with pytest.raises(s.SettingsError) as caught:
        list(s.read_cases(path))
    assert_one_line(caught.value)


# ---------------------------------------------------------------------------
# ids
# ---------------------------------------------------------------------------


def test_an_id_given_is_the_id_kept(tmp_path: Path) -> None:
    got = read(tmp_path, [json.dumps({"input": "x", "id": i}) for i in ("b", "a", "c")])
    assert [c["id"] for c in got] == ["b", "a", "c"]


@pytest.mark.parametrize("lines, line", [
    (['{"input": "x", "id": "a"}', '{"input": "y", "id": "a"}'], 2),
    (['{"input": "x", "id": "a"}', '{"input": "y", "id": "b"}', '{"input": "z", "id": "a"}'], 3),
    (['{"input": "x", "id": "a"}', '{"input": "y"}', '{"input": "z", "id": "b"}', '{"input": "w", "id": "b"}'], 4),
])
def test_an_id_given_twice_is_refused_on_the_second(tmp_path: Path, lines: list[str], line: int) -> None:
    refused_line(tmp_path, lines, line)


def test_the_same_input_under_different_ids_is_taken(tmp_path: Path) -> None:
    assert len(read(tmp_path, ['{"input": "x", "id": "a"}', '{"input": "x", "id": "b"}'])) == 2


def test_cases_without_ids_are_numbered_so_that_every_id_differs(tmp_path: Path) -> None:
    got = read(tmp_path, [GOOD] * 12)
    ids = [c["id"] for c in got]
    assert len(set(ids)) == 12


def test_the_numbering_is_the_same_on_every_read(tmp_path: Path) -> None:
    """Arms line up by case (plan BK5.5): an id that moved between two reads would line up nothing."""
    lines = [GOOD, '{"input": "x", "id": "named"}', GOOD]
    assert [c["id"] for c in read(tmp_path, lines)] == [c["id"] for c in read(tmp_path, lines)]


def test_a_number_given_to_one_case_does_not_land_on_another(tmp_path: Path) -> None:
    """A case may be given by name the very word another would be numbered with. Either refuse it or keep them apart:
    two cases must not share an id. The names are read from the numbering itself, so this holds however it is spelt."""
    numbered = [c["id"] for c in read(tmp_path, [GOOD] * 4)]
    for name in numbered:
        lines = [json.dumps({"input": "x", "id": name}), GOOD, GOOD, GOOD]
        try:
            got = read(tmp_path, lines)
        except settings().SettingsError:
            continue
        ids = [c["id"] for c in got]
        assert len(set(ids)) == 4, ids
        assert ids[0] == name


def test_an_id_kept_is_kept_whatever_is_numbered_around_it(tmp_path: Path) -> None:
    got = read(tmp_path, [GOOD, '{"input": "x", "id": "named"}', GOOD])
    assert got[1]["id"] == "named"
    assert len({c["id"] for c in got}) == 3


@pytest.mark.parametrize("value", ['""', "[1]", '{"a": 1}', "true"])
def test_an_id_that_could_not_name_a_case_is_refused(tmp_path: Path, value: str) -> None:
    refused_line(tmp_path, [GOOD, f'{{"input": "x", "id": {value}}}'], 2)


# ---------------------------------------------------------------------------
# expect, variants and turns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["reply_contain", "reply", "call", "never_call", "calls_", "anything"])
def test_an_expect_key_not_offered_is_refused_with_its_line_number(tmp_path: Path, key: str) -> None:
    refused_line(tmp_path, [GOOD, json.dumps({"input": "x", "expect": {key: "y"}})], 2)


@pytest.mark.parametrize("expect", [{"reply_contains": "y"}, {"calls": ["a"]}, {"never_calls": ["a"]}, {},
                                    {"reply_contains": "y", "calls": ["a"], "never_calls": ["b"]}])
def test_an_expect_with_only_the_keys_offered_is_taken(tmp_path: Path, expect: dict[str, Any]) -> None:
    [case] = read(tmp_path, [json.dumps({"input": "x", "expect": expect})])
    assert case["expect"] == expect


def test_a_bad_expect_key_beside_good_ones_is_refused(tmp_path: Path) -> None:
    refused_line(tmp_path, [json.dumps({"input": "x", "expect": {"calls": ["a"], "nope": 1}})], 1)


@pytest.mark.parametrize("value", ['"calls"', "7", '["calls"]', "true"])
def test_an_expect_that_is_no_table_is_refused_with_its_line_number(tmp_path: Path, value: str) -> None:
    refused_line(tmp_path, [GOOD, f'{{"input": "x", "expect": {value}}}'], 2)


@pytest.mark.parametrize("field", ["variants", "turns"])
@pytest.mark.parametrize("value", ['"not a list"', "7", '{"a": 1}', "[1, 2]", "true"])
def test_variants_or_turns_that_are_no_list_of_text_are_refused_with_the_line_number(tmp_path: Path, field: str, value: str) -> None:
    """§9.4: "a `variants` list, and `turns` for a scripted conversation". The operators read them as text, so any
    other shape would first be seen by a run."""
    refused_line(tmp_path, [GOOD, f'{{"input": "x", "{field}": {value}}}'], 2)


def test_a_case_is_read_the_same_from_either_end_of_a_file_with_windows_line_endings(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_bytes(b'{"input": "a"}\r\n{"input": "b"}\r\n')
    assert [c["input"] for c in settings().read_cases(path)] == ["a", "b"]
