"""The record types of `poisson_break.records`: the shape of spec §6.4, fixed as data.

Invariant pinned here (Break — Plan, the repo module):
- BK0.6  The record types round-trip: every type in `poisson_break.records` serialises to JSON
         and back equal, carries `schema = "poisson_break.run/1"` at the top of a `RunRecord`,
         and refuses construction with a field the spec does not name.

And the binding facts of spec §6.4 the four side-by-side modules build against: the key, the
schema string, every field name in the spec's order, and the closed sets of `stage`, `kind`
and the signals.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest

from poisson_break import records
from poisson_break.records import (
    Applied,
    Call,
    Condition,
    Failure,
    RecordError,
    RunRecord,
    Selection,
    Signals,
)

# ---------------------------------------------------------------------------
# fixtures: one full record, every field carrying a value
# ---------------------------------------------------------------------------


def full_record(**overrides: Any) -> RunRecord:
    changes = (
        Applied(surface="tool", tool="lookup_order", fault="timeout", call="#2",
                applied=True, applied_call=2),
        Applied(surface="input", tool=None, fault="typos", call=None,
                applied=True, applied_call=None),
    )
    fields: dict[str, Any] = dict(
        hunt="refund-agent-1",
        stage="search",
        arm="refund-agent-1-search",
        case="case-7",
        condition=Condition(name="input:typos + tool:lookup_order#2=timeout", changes=changes),
        failure=Failure(kind="ran_out", signals=Signals(gave_up=1, retry_storm=0, over_budget=0)),
        selection=Selection(strategy="screen", probability=1.0),
        calls=(
            Call(tool="lookup_order", call=1, change=None, real_ran=True),
            Call(tool="lookup_order", call=2, change="tool:lookup_order#2=timeout", real_ran=False),
            Call(tool="check_policy", call=1, change=None, real_ran=True),
        ),
        judged_by="break",
        target_outcome=None,
    )
    fields.update(overrides)
    return RunRecord(**fields)


def control_record() -> RunRecord:
    return full_record(
        stage="control",
        arm="refund-agent-1-control",
        condition=Condition(name="", changes=()),
        failure=Failure(kind=None, signals=Signals(gave_up=0, retry_storm=0, over_budget=0)),
        selection=Selection(strategy="screen", probability=1.0),
        calls=(Call(tool="lookup_order", call=1, change=None, real_ran=True),),
        judged_by="your check",
        target_outcome="resolved",
    )


# ---------------------------------------------------------------------------
# the binding names
# ---------------------------------------------------------------------------


def test_key_and_schema_are_the_published_ones() -> None:
    assert records.META_KEY == "poisson_break"
    assert records.SCHEMA == "poisson_break.run/1"


def test_run_record_fields_are_the_spec_table_in_its_order() -> None:
    """Spec §6.4, top level, in order. A field added here is a new field in the spec; a field
    removed or renamed is `poisson_break.run/2`."""
    names = [f.name for f in dataclasses.fields(RunRecord)]
    assert names == ["schema", "hunt", "stage", "arm", "case", "condition", "failure",
                     "selection", "calls", "judged_by", "target_outcome"]


def test_nested_fields_are_the_spec_table() -> None:
    names = lambda t: [f.name for f in dataclasses.fields(t)]
    assert names(Condition) == ["name", "changes"]
    assert names(Applied) == ["surface", "tool", "fault", "call", "applied", "applied_call"]
    assert names(Failure) == ["kind", "signals"]
    assert names(Signals) == ["gave_up", "retry_storm", "over_budget"]
    assert names(Selection) == ["strategy", "probability"]
    assert names(Call) == ["tool", "call", "change", "real_ran"]


def test_closed_sets_are_the_spec_lists() -> None:
    """Spec §6.4's binding closed sets: the stages, §4's failure kinds (with `own:<name>` as the
    open-ended one), the three signals, §3.1's surfaces and the two judges."""
    assert records.STAGES == ("control", "search", "shrink", "confirm", "reference", "recheck")
    assert records.KINDS == ("crashed", "hung", "ran_out", "forbidden_call", "followed_plant",
                             "duplicate_write", "failed", "wrong")
    assert records.OWN_PREFIX == "own:"
    assert records.SIGNALS == ("gave_up", "retry_storm", "over_budget")
    assert records.SURFACES == ("tool", "input", "user", "model", "env")
    assert records.JUDGED_BY == ("break", "your check")


# ---------------------------------------------------------------------------
# BK0.6  round trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("record", [full_record(), control_record()], ids=["searched", "control"])
def test_run_record_round_trips_through_json(record: RunRecord) -> None:
    text = record.to_json()
    back = RunRecord.from_json(text)
    assert back == record
    assert json.loads(text) == record.to_dict()
    assert RunRecord.from_dict(json.loads(text)) == record


def test_every_record_type_round_trips() -> None:
    """Each type on its own, `from_dict(to_dict(x)) == x`, so a module that writes only a
    part (BK2 writes `Applied` and `Call`; BK3 writes `Failure`) can check its own output."""
    record = full_record()
    parts: list[Any] = [record.condition, *record.condition.changes, record.failure,
                        record.failure.signals, record.selection, *record.calls]
    for part in parts:
        assert type(part).from_dict(part.to_dict()) == part, type(part).__name__
        assert json.loads(json.dumps(part.to_dict())) == part.to_dict(), type(part).__name__


def test_schema_is_the_first_key_at_the_top() -> None:
    record = full_record()
    assert record.schema == "poisson_break.run/1"
    assert next(iter(record.to_dict())) == "schema"
    assert record.to_json().startswith('{"schema": "poisson_break.run/1"')


def test_to_dict_keeps_the_spec_order_everywhere() -> None:
    d = full_record().to_dict()
    assert list(d) == ["schema", "hunt", "stage", "arm", "case", "condition", "failure",
                       "selection", "calls", "judged_by", "target_outcome"]
    assert list(d["condition"]) == ["name", "changes"]
    assert list(d["condition"]["changes"][0]) == ["surface", "tool", "fault", "call", "applied",
                                                  "applied_call"]
    assert list(d["failure"]) == ["kind", "signals"]
    assert list(d["failure"]["signals"]) == ["gave_up", "retry_storm", "over_budget"]
    assert list(d["selection"]) == ["strategy", "probability"]
    assert list(d["calls"][0]) == ["tool", "call", "change", "real_ran"]


def test_to_dict_is_plain_json_data() -> None:
    """Only dicts, lists, strings, numbers, booleans and None: what Prove's `meta` stores and
    what the upload assembler reads. No dataclass, tuple or set leaks through."""
    def plain(value: Any) -> bool:
        if isinstance(value, dict):
            return all(isinstance(k, str) and plain(v) for k, v in value.items())
        if isinstance(value, list):
            return all(plain(v) for v in value)
        return value is None or isinstance(value, (str, int, float, bool))

    assert plain(full_record().to_dict())


def test_json_is_strict() -> None:
    """No `NaN` or `Infinity` can be written: a probability is checked before it is stored, and
    the writer refuses them anyway."""
    text = full_record().to_json()
    assert "NaN" not in text and "Infinity" not in text
    json.loads(text, parse_constant=lambda name: pytest.fail(f"non-strict JSON constant {name}"))


# ---------------------------------------------------------------------------
# BK0.6  refusing a field the spec does not name
# ---------------------------------------------------------------------------


def test_constructing_with_an_unknown_field_is_refused() -> None:
    with pytest.raises(TypeError):
        full_record(cost=0.004)
    with pytest.raises(TypeError):
        Selection(strategy="screen", probability=1.0, reason="first in order")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        Signals(gave_up=0, retry_storm=0, over_budget=0, slow=1)  # type: ignore[call-arg]


def test_reading_an_unknown_field_is_refused_at_every_level() -> None:
    d = full_record().to_dict()
    top = dict(d, cost=0.004)
    with pytest.raises(RecordError):
        RunRecord.from_dict(top)
    nested = json.loads(json.dumps(d))
    nested["selection"]["reason"] = "first in order"
    with pytest.raises(RecordError):
        RunRecord.from_dict(nested)
    deep = json.loads(json.dumps(d))
    deep["condition"]["changes"][0]["rate"] = 0.3
    with pytest.raises(RecordError):
        RunRecord.from_dict(deep)


def test_reading_with_a_field_missing_is_refused() -> None:
    """Nothing in the record can be backfilled: a document without a field is not a record."""
    d = full_record().to_dict()
    for name in ("selection", "stage", "judged_by", "calls"):
        without = {k: v for k, v in d.items() if k != name}
        with pytest.raises(RecordError):
            RunRecord.from_dict(without)
    nested = json.loads(json.dumps(d))
    del nested["selection"]["probability"]
    with pytest.raises(RecordError):
        RunRecord.from_dict(nested)


def test_positional_construction_is_refused() -> None:
    """Every field is named: a record built positionally would silently swap two strings."""
    with pytest.raises(TypeError):
        Selection("screen", 1.0)  # type: ignore[misc]
    with pytest.raises(TypeError):
        Call("lookup_order", 1, None, True)  # type: ignore[misc]


def test_records_are_frozen() -> None:
    record = full_record()
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.stage = "confirm"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.selection.probability = 0.5  # type: ignore[misc]
    assert isinstance(record.calls, tuple)
    assert isinstance(record.condition.changes, tuple)


def test_a_different_schema_string_is_refused() -> None:
    with pytest.raises(RecordError):
        full_record(schema="poisson_break.run/2")
    d = dict(full_record().to_dict(), schema="poisson_break.run/2")
    with pytest.raises(RecordError):
        RunRecord.from_dict(d)


# ---------------------------------------------------------------------------
# the closed sets hold at construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stage", ["shrunk", "Control", "", "recheck-1"])
def test_a_stage_outside_the_set_is_refused(stage: str) -> None:
    with pytest.raises(RecordError):
        full_record(stage=stage)


@pytest.mark.parametrize("stage", records.STAGES)
def test_every_stage_in_the_set_is_accepted(stage: str) -> None:
    assert full_record(stage=stage).stage == stage


@pytest.mark.parametrize("kind", ["exploded", "ok", "own:", "own", "Crashed", "gave_up"])
def test_a_kind_outside_the_set_is_refused(kind: str) -> None:
    """A signal is not a kind, `ok` is the absence of one (`None`), and `own:` needs a name."""
    with pytest.raises(RecordError):
        Failure(kind=kind, signals=Signals(gave_up=0, retry_storm=0, over_budget=0))


@pytest.mark.parametrize("kind", [*records.KINDS, "own:refund_ok", None])
def test_every_kind_in_the_set_and_the_users_own_are_accepted(kind: str | None) -> None:
    failure = Failure(kind=kind, signals=Signals(gave_up=0, retry_storm=0, over_budget=0))
    assert failure.kind == kind


@pytest.mark.parametrize("count", [-1, 1.5, True, "2"])
def test_a_signal_count_is_a_whole_number(count: Any) -> None:
    with pytest.raises(RecordError):
        Signals(gave_up=count, retry_storm=0, over_budget=0)


@pytest.mark.parametrize("probability", [0, 0.0, -0.1, 1.0000001, 2, True, False, "1", None,
                                         float("nan"), float("inf")])
def test_a_probability_outside_zero_one_is_refused(probability: Any) -> None:
    """The probability is in (0, 1]: 0 is not a probability a run could have been picked with,
    and a boolean or a string is not a number."""
    with pytest.raises(RecordError):
        Selection(strategy="screen", probability=probability)


@pytest.mark.parametrize("probability", [1, 1.0, 0.5, 1e-9])
def test_a_probability_in_zero_one_is_accepted(probability: float) -> None:
    assert Selection(strategy="random", probability=probability).probability == probability


@pytest.mark.parametrize("surface", ["tools", "Tool", "conversation", ""])
def test_a_surface_outside_the_set_is_refused(surface: str) -> None:
    with pytest.raises(RecordError):
        Applied(surface=surface, tool="t", fault="error", call="#1", applied=False, applied_call=None)


@pytest.mark.parametrize("judged_by", ["model", "Break", "", "trace"])
def test_a_judge_outside_the_two_is_refused(judged_by: str) -> None:
    with pytest.raises(RecordError):
        full_record(judged_by=judged_by)


@pytest.mark.parametrize("call", [0, -1, 1.0, True, "2"])
def test_a_call_number_counts_from_one(call: Any) -> None:
    with pytest.raises(RecordError):
        Call(tool="lookup_order", call=call, change=None, real_ran=True)
    with pytest.raises(RecordError):
        Applied(surface="tool", tool="t", fault="error", call="#1", applied=True, applied_call=call)


def test_the_control_is_the_empty_name_with_no_changes() -> None:
    """Spec §6.4: the condition's name is the empty string for the control, and only then."""
    with pytest.raises(RecordError):
        Condition(name="", changes=(Applied(surface="input", tool=None, fault="typos", call=None,
                                            applied=True, applied_call=None),))
    with pytest.raises(RecordError):
        Condition(name="input:typos", changes=())
    assert Condition(name="", changes=()).name == ""


@pytest.mark.parametrize("field, value", [
    ("hunt", 7), ("arm", None), ("case", 3), ("target_outcome", 0),
])
def test_a_field_of_the_wrong_type_is_refused(field: str, value: Any) -> None:
    """A record is read back by the upload assembler by these names and shapes; a number where
    a name belongs is refused when written, not discovered when read."""
    with pytest.raises(RecordError):
        full_record(**{field: value})


def test_a_record_error_is_one_plain_sentence_naming_the_field() -> None:
    """The message names the field so the module that wrote it can be found; it carries no
    Python repr of a list or a tuple."""
    with pytest.raises(RecordError) as caught:
        full_record(stage="shrunk")
    message = str(caught.value)
    assert "stage" in message
    assert "\n" not in message
    assert "[" not in message and "(" not in message, message
