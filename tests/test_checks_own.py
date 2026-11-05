"""The user's own check, spec §11.4: what it is handed, what it may return, and what it cannot do.

Invariants pinned here (Break — Plan, the failure check):
- BK3.1 `own:<name>` has a fixture that triggers it and a control that does not.
- BK3.7 A user's own check receives a `RunView` and nothing else; one that raises is an instrument error; one that
        calls out is the user's business, and findings resting on it carry the "judged by your check" mark; one that
        returns anything but `None` or a failure kind is an instrument error.
- BK3.10 `RunView` is read-only and complete: it exposes every field of spec §11.4's table, refuses assignment, and a
        check written against it on the fixtures sees the same values a run through BK5 later produces (BK5.4 pins
        the join).

And §11's rule for every extension point: a version constant, and a test-only implementation outside the package
that runs through the core with no core file changed. The checks are `tests/checks_own.py`.

Owed a ruling, so held here only as far as every answer agrees: what `<name>` is in `own:<name>`, which strings are a
failure kind, whether a check runs at all on a run Break already failed, who `judged_by` names on a run the check
passed, and what a check's `SystemExit` or `KeyboardInterrupt` comes to.
"""

from __future__ import annotations

import copy
import dataclasses
import inspect
import sys
import textwrap
from collections.abc import Iterator
from types import ModuleType
from typing import Any

import pytest

from poisson_break import interfaces, records
from tests.apply_support import CASE, MAPPING, Tool, apply
from tests.checks_support import (
    LIMIT,
    NOT_COUNTED,
    OK,
    SLEEP,
    TOP_LEVEL_FIELDS,
    VIEW_ATTRIBUTES,
    VIEW_FIELDS,
    all_tools,
    checks,
    error_of,
    failed,
    judged,
    judged_by,
    kind_of,
    lines_of,
    outcome_of,
    own,
    own_module,
    plain,
    saw_of,
    state_of,
    verdict,
    view_calls,
    view_changes,
    way_in,
    with_fails,
)
from tests.conftest import run_python


@pytest.fixture(autouse=True)
def fresh_checks() -> Iterator[ModuleType]:
    module = own_module()
    module.reset()
    yield module
    module.reset()


def asked(check: str = "configured", **fails: Any) -> dict[str, Any]:
    return {"own": own(check), **fails}


def is_own(v: Any) -> bool:
    kind = kind_of(v)
    return isinstance(kind, str) and kind.startswith(records.OWN_PREFIX) and len(kind) > len(records.OWN_PREFIX)


def view_of(scene: Any) -> Any:
    """What a check is handed for a run: judged with a check that keeps it."""
    judged(scene.run)
    assert len(own_module().CALLS) == 1
    return own_module().LAST


# ---------------------------------------------------------------------------
# returning nothing means passed, and returning a failure kind means failed
# ---------------------------------------------------------------------------


def test_returning_nothing_passes() -> None:
    assert verdict(way_in(fails=asked("passes")).run) == OK


def test_returning_a_failure_kind_fails_as_its_own_kind() -> None:
    v = judged(way_in(fails=asked("fails_it")).run)
    assert state_of(v) == "failed"
    assert is_own(v)


def test_a_check_written_on_the_view_decides_from_the_view() -> None:
    """A check of the kind a user writes: it reads what the agent did. Run on two agents, it tells them apart."""
    assert verdict(plain("repeats_write", fails=asked("fails_if_no_refund")).run) == OK
    v = judged(plain("gives_up", fails=asked("fails_if_no_refund")).run)
    assert state_of(v) == "failed" and is_own(v)


def test_its_kind_can_be_written_to_the_record() -> None:
    run = way_in(fails=asked("fails_it")).run
    assert is_own(records.Failure(kind=kind_of(judged(run)), signals=checks().signals(run)))


def test_failing_has_the_one_outcome_failed() -> None:
    """Plan BK3.9. What the check said goes in the kind and never in the outcome."""
    assert outcome_of(judged(way_in(fails=asked("fails_it")).run)) == "failed"


# ---------------------------------------------------------------------------
# anything else, including raising, is an error in Break, not a failure of the agent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("returned", [True, False, 0, 1, 1.5, [], ["a_kind"], {}, {"kind": "a_kind"}, (), ("a_kind",), b"a_kind", object()],
                         ids=["true", "false", "zero", "one", "float", "empty-list", "list", "empty-dict", "dict", "empty-tuple", "tuple", "bytes", "object"])
def test_a_check_that_returns_anything_else_is_an_error_in_break(returned: Any, fresh_checks: ModuleType) -> None:
    """Ruled 2026-11-04. Among these are the ones a careless `if not answer` would read as passed, and the ones a
    careless `str(answer)` would read as failed."""
    fresh_checks.RETURNS = returned
    assert verdict(way_in(fails=asked()).run) == NOT_COUNTED


@pytest.mark.parametrize("raised", [ValueError("no"), RuntimeError("no"), LookupError("no"), TimeoutError("no"), AssertionError("no")],
                         ids=lambda e: type(e).__name__)
def test_a_check_that_raises_is_an_error_in_break(raised: Exception, fresh_checks: ModuleType) -> None:
    fresh_checks.RAISES = raised
    v = judged(way_in(fails=asked()).run)
    assert (state_of(v), kind_of(v)) == NOT_COUNTED
    assert isinstance(error_of(v), str) and error_of(v)


def test_a_check_that_raises_a_failure_of_a_tool_is_still_an_error_in_break(fresh_checks: ModuleType) -> None:
    """Not read as anything the agent did, though it is the same object a tool's failure is."""
    fresh_checks.RAISES = apply().ToolFailure("error", "the check's own")
    assert verdict(way_in(fails=asked()).run) == NOT_COUNTED


def test_a_check_that_raises_an_instrument_error_is_an_error_in_break(fresh_checks: ModuleType) -> None:
    fresh_checks.RAISES = apply().InstrumentError("the check's own")
    assert verdict(way_in(fails=asked()).run) == NOT_COUNTED


def test_an_async_check_has_returned_something_that_is_not_an_answer() -> None:
    """A coroutine is neither `None` nor a kind, and awaiting it is not in the interface."""
    assert verdict(way_in(fails=asked("is_async")).run) == NOT_COUNTED


def test_an_empty_answer_is_not_a_pass(fresh_checks: ModuleType) -> None:
    """Whether `""` is an error or a kind is owed a ruling. It is not `None`, so it is not ok."""
    fresh_checks.RETURNS = ""
    assert verdict(way_in(fails=asked()).run) != OK


@pytest.mark.parametrize("path", ["tests.checks_own:no_such_check", "tests.no_such_module:check", "tests.checks_own:NOT_CALLABLE"],
                         ids=["no-attribute", "no-module", "not-callable"])
def test_a_check_that_cannot_be_loaded_or_called_is_not_the_agents_failure(path: str) -> None:
    """When it is refused is owed a ruling: at load by the runs module, or on each run. Whenever it is, the agent did
    nothing, so the run is neither ok nor failed."""
    run = way_in(fails={"own": path}).run
    try:
        v = judged(run)
    except Exception:
        return
    assert state_of(v) == "not counted"


# ---------------------------------------------------------------------------
# the mark
# ---------------------------------------------------------------------------


def test_a_run_the_check_failed_is_judged_by_your_check() -> None:
    assert judged_by(judged(way_in(fails=asked("fails_it")).run)) == "your check"


def test_with_no_check_named_every_run_is_judged_by_break() -> None:
    assert judged_by(judged(way_in().run)) == "break"
    assert judged_by(judged(way_in(max_steps=1).run)) == "break"


def test_a_run_break_failed_is_judged_by_break_though_a_check_is_named() -> None:
    """The check did not decide it. A finding marked as resting on the check here would be wrong (§11.4 invariant 3)."""
    v = judged(way_in(max_steps=1, fails=asked("fails_it")).run)
    assert kind_of(v) == "ran_out"
    assert judged_by(v) == "break"


def test_a_check_may_call_a_model_and_break_neither_stops_it_nor_grades_for_it(fresh_checks: ModuleType) -> None:
    """§11.4 invariant 3 and BK3.7: that is the user's business. What it decided carries the mark."""
    v = judged(way_in(fails=asked("calls_a_model")).run)
    assert fresh_checks.DOUBLE_CALLS, "the check did not get to call it"
    assert state_of(v) == "failed" and is_own(v)
    assert judged_by(v) == "your check"


# ---------------------------------------------------------------------------
# Break's own come first, and the check runs once and after
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("make, kind", [
    (lambda f: way_in(max_steps=1, fails=f), "ran_out"),
    (lambda f: way_in(pause=SLEEP, fails={**f, "run_seconds": LIMIT}), "hung"),
    (lambda f: plain("follows_plant", "tool:lookup_order#1=planted_instruction", fails=f), "followed_plant"),
    (lambda f: plain("repeats_write", "tool:issue_refund#1=lost_reply", fails=f), "duplicate_write"),
    (lambda f: way_in(case=lines_of(CASE, reply_contains="never said"), fails=f), "wrong"),
], ids=["ran_out", "hung", "followed_plant", "duplicate_write", "wrong"])
def test_breaks_kinds_win_whatever_the_check_says(make: Any, kind: str) -> None:
    """§11.4 invariant 4: it decides only a run Break's checks found ok."""
    assert verdict(make(asked("fails_it")).run) == failed(kind)


def test_a_check_that_passes_does_not_excuse_a_kind_of_breaks() -> None:
    assert verdict(way_in(max_steps=1, fails=asked("passes")).run) == failed("ran_out")


def test_it_runs_once_on_a_run_it_decides(fresh_checks: ModuleType) -> None:
    """§11.4 invariant 5. A check may call a model, so running it twice is paying twice."""
    scene = way_in(fails=asked("passes"))
    assert fresh_checks.CALLS == [], "a check runs after the run, not during"
    judged(scene.run)
    assert len(fresh_checks.CALLS) == 1


def test_reading_the_signals_does_not_run_it(fresh_checks: ModuleType) -> None:
    checks().signals(way_in(fails=asked("passes")).run)
    assert fresh_checks.CALLS == []


def test_with_no_check_named_none_is_loaded_or_run(fresh_checks: ModuleType) -> None:
    verdict(way_in().run)
    assert fresh_checks.CALLS == []


def test_a_check_is_not_loaded_before_it_is_named() -> None:
    """§11: "the core never imports an implementation it did not load by name from the settings". Measured in a fresh
    interpreter, since this one has imported it."""
    code = textwrap.dedent("""
        import sys
        import poisson_break.checks
        print("tests.checks_own" in sys.modules, "tests" in sys.modules)
    """)
    ran = run_python(code)
    assert ran.exit == 0, ran.stderr
    assert ran.stdout.split() == ["False", "False"]


# ---------------------------------------------------------------------------
# it gets a read-only view of the run, and nothing else
# ---------------------------------------------------------------------------


def test_it_is_handed_one_thing_and_that_is_a_view(fresh_checks: ModuleType) -> None:
    judged(way_in(fails=asked()).run)
    assert len(fresh_checks.CALLS) == 1
    args, kwargs = fresh_checks.CALLS[0]
    assert len(args) == 1
    assert kwargs == {}
    assert isinstance(args[0], checks().RunView)


def walk(value: Any, depth: int = 4) -> Iterator[Any]:
    """A view and everything it holds, by its public names and its items."""
    yield value
    if depth == 0:
        return
    if isinstance(value, dict) or (hasattr(value, "items") and hasattr(value, "keys")):
        for key, item in value.items():
            yield from walk(key, depth - 1)
            yield from walk(item, depth - 1)
    elif isinstance(value, list | tuple | set | frozenset):
        for item in value:
            yield from walk(item, depth - 1)
    elif not isinstance(value, str | bytes | int | float | bool | type(None)):
        for name in dir(value):
            if name.startswith("_"):
                continue
            item = getattr(value, name)
            if not inspect.ismethod(item):
                yield from walk(item, depth - 1)


def test_nothing_in_the_view_reaches_the_session_or_the_real_tool(fresh_checks: ModuleType) -> None:
    """"And nothing else". A check handed the session could call a tool, or read the hunt's seed; handed the agent's
    result object it could change what the record is written from."""
    scene = way_in("tool:lookup_order#1=empty", fails=asked())
    judged(scene.run)
    a = apply()
    for held in walk(fresh_checks.LAST):
        assert not isinstance(held, a.Session | a.RunResult | ModuleType), held
        assert not (callable(held) and not isinstance(held, type)), held
        assert held is not scene.run
        assert held is not scene.session


def test_it_shows_no_field_outside_the_list_but_what_is_added_with_a_default(fresh_checks: ModuleType) -> None:
    """§11.4: "a new field is additive with a default of `None`". Anything else here has been let in by mistake."""
    judged(way_in(fails=asked()).run)
    fields = dataclasses.fields(fresh_checks.LAST)
    for field in fields:
        if field.name not in TOP_LEVEL_FIELDS:
            assert field.default is None, field.name


@pytest.mark.parametrize("name", sorted(TOP_LEVEL_FIELDS))
def test_every_field_of_the_list_is_on_it_with_the_interface_at_version_one(name: str, fresh_checks: ModuleType) -> None:
    """§11.4: removing a field is the breaking change. A later version has its own list, and this test is the reminder
    to write it."""
    assert checks().CHECK_INTERFACE_VERSION == 1
    judged(way_in(fails=asked()).run)
    assert name in {f.name for f in dataclasses.fields(fresh_checks.LAST)}


@pytest.mark.parametrize("place", VIEW_ATTRIBUTES, ids=[name for _, name in VIEW_ATTRIBUTES])
def test_assignment_is_refused(place: Any) -> None:
    """Plan BK3.10, on every field: the view's own, the case's, the condition's, a change's and a call's."""
    on, name = place
    view = view_of(way_in("tool:lookup_order#1=empty", fails=asked("passes")))
    holder = on(view)
    before = getattr(holder, name)
    with pytest.raises((AttributeError, TypeError)):
        setattr(holder, name, "changed")
    assert getattr(holder, name) == before


@pytest.mark.parametrize("place", VIEW_ATTRIBUTES[:9], ids=[name for _, name in VIEW_ATTRIBUTES[:9]])
def test_deleting_is_refused(place: Any) -> None:
    on, name = place
    view = view_of(way_in("tool:lookup_order#1=empty", fails=asked("passes")))
    with pytest.raises((AttributeError, TypeError)):
        delattr(on(view), name)


def test_a_new_attribute_is_refused() -> None:
    view = view_of(way_in(fails=asked("passes")))
    with pytest.raises((AttributeError, TypeError)):
        view.verdict = "ok"


def test_the_arguments_mapping_refuses_assignment() -> None:
    view = view_of(way_in(fails=asked("passes")))
    with pytest.raises(TypeError):
        view.calls[0].args["query"] = "changed"


def test_the_list_of_calls_cannot_be_added_to() -> None:
    view = view_of(way_in(fails=asked("passes")))
    with pytest.raises((AttributeError, TypeError)):
        view.calls.append("another")
    with pytest.raises((AttributeError, TypeError)):
        view.calls[0] = "another"


def test_a_check_that_tries_everything_changes_nothing(fresh_checks: ModuleType) -> None:
    """§11.4 invariant 5: it "cannot change it". Whatever it tries, on the view or inside what the view holds, by
    ordinary means or by `object.__setattr__`, the run stays what it was: read again, the verdict, the signals and a
    second view are the same, and the agent's own objects and the session are untouched."""
    nested = {"nested": {"deep": ["as it was"]}, "query": "q"}
    original = {"status": "as the tool said"}
    tools = {**all_tools(), "lookup_order": Tool(original)}
    scene = way_in(script=[("lookup_order", nested)], tools=tools, fails=asked("tampers"))
    before_args = copy.deepcopy(nested)
    before_record = scene.session.calls

    judged(scene.run)
    assert nested == before_args
    assert original == {"status": "as the tool said"}
    assert tools["lookup_order"].log == [before_args]
    assert scene.session.calls == before_record
    assert scene.seen[0].result == {"status": "as the tool said"}


def test_after_a_check_that_tampers_a_second_look_sees_what_the_first_was_given(fresh_checks: ModuleType) -> None:
    nested = {"nested": {"deep": ["as it was"]}, "query": "q"}
    tools = {**all_tools(), "lookup_order": Tool({"status": "as the tool said"})}
    case = {**CASE, "turns": ["Where is it?", "Thanks."]}
    scene = way_in(script=[("lookup_order", nested)], tools=tools, case=case, reply=lambda seen: "my reply", fails=asked("tampers"))
    first = judged(scene.run)
    signals_after = checks().signals(scene.run)

    view = view_of_again(scene, fresh_checks)
    assert view.reply == "my reply"
    assert list(view.case.turns) == ["Where is it?", "Thanks."]
    assert view.calls[0].real_ran is True
    assert list(view.kinds) == []
    assert dict(view.calls[0].args) == {"nested": {"deep": ["as it was"]}, "query": "q"}
    assert view.calls[0].saw == {"status": "as the tool said"}
    assert (state_of(first), kind_of(first)) == OK
    assert signals_after == checks().signals(scene.run)


def view_of_again(scene: Any, module: ModuleType) -> Any:
    """The same run, judged once more by a check that keeps what it was handed."""
    run = with_fails(scene.run, {"own": own("passes")})
    module.reset()
    judged(run)
    return module.LAST


def test_a_check_cannot_reach_a_later_runs_view(fresh_checks: ModuleType) -> None:
    """Each run's view is its own: what one check did to its copy is not there for the next."""
    tools = {**all_tools(), "lookup_order": Tool(dict(MAPPING))}
    judged(way_in(tools=tools, fails=asked("tampers")).run)
    fresh_checks.reset()
    view = view_of(way_in(tools={**all_tools(), "lookup_order": Tool(dict(MAPPING))}, fails=asked("passes")))
    assert view.calls[0].saw == MAPPING


# ---------------------------------------------------------------------------
# it exposes every field, with what is true of the run
# ---------------------------------------------------------------------------


def test_the_view_says_what_the_run_did(fresh_checks: ModuleType) -> None:
    """Every field of §11.4's list, against a run whose every value is known. The agent is `WayIn`, which goes on past
    a failure, so a call after the fault can be read too."""
    case = {"id": "c9", "input": "Where is order 7?", "turns": ["Where is order 7?", "Thanks."]}
    script = [("lookup_order", {"query": "q"}), ("check_policy", {"topic": "refunds"}), ("lookup_order", {"query": "r"})]
    condition = "tool:check_policy#1=error + tool:lookup_order#2=empty + tool:lookup_order#9=cut_off"
    scene = way_in(condition, script=script, case=case, outcome="resolved", tokens=(120, 34), reply=lambda seen: "my reply",
                   fails=asked("passes"))
    view = view_of(scene)
    assert view.case.id == "c9"
    assert view.case.input == "Where is order 7?"
    assert list(view.case.turns) == ["Where is order 7?", "Thanks."]
    assert view.condition.name == condition
    assert view_changes(view) == [
        ("tool", "check_policy", "error", "#1", True, 1),
        ("tool", "lookup_order", "empty", "#2", True, 2),
        ("tool", "lookup_order", "cut_off", "#9", False, None),
    ]
    assert view_calls(view) == [
        ("lookup_order", 1, {"query": "q"}, ("result", "Order 7 shipped on Tuesday."), True),
        ("check_policy", 1, {"topic": "refunds"}, ("failure", "error"), False),
        ("lookup_order", 2, {"query": "r"}, ("result", ""), True),
    ]
    assert view.reply == "my reply"
    assert view.outcome == "resolved"
    assert (view.tokens_in, view.tokens_out) == (120, 34)
    assert view.seconds >= 0
    assert list(view.kinds) == []


def test_the_seconds_are_the_runs() -> None:
    """Read from the clock around the run, so a run that took a while says so."""
    assert view_of(way_in(pause=SLEEP, fails=asked("passes"))).seconds >= SLEEP


def test_what_the_agent_saw_is_what_it_saw_and_not_what_the_tool_said() -> None:
    """§11.4 says "what the agent saw". Under `cut_off` those differ, and a check written to read the tool's answer
    would be reading something the agent never had."""
    long = "Order 7 shipped on Tuesday. " * 40
    tools = {**all_tools(), "lookup_order": Tool(long)}
    view = view_of(way_in("tool:lookup_order#1=cut_off", tools=tools, fails=asked("passes")))
    assert view.calls[0].saw == long[:200]
    assert view.calls[0].real_ran is True


def test_a_lost_reply_shows_the_failure_the_agent_saw_and_that_the_tool_ran() -> None:
    script = [("issue_refund", {"request": "r"})]
    view = view_of(way_in("tool:issue_refund#1=lost_reply", script=script, fails=asked("passes")))
    assert saw_of(view.calls[0]) == ("failure", "error")
    assert view.calls[0].real_ran is True


def test_planted_text_is_in_what_the_agent_saw_and_the_view_can_read_it() -> None:
    scene = way_in("tool:lookup_order#1=planted_instruction", fails=asked("passes"))
    assert scene.marker in view_of(scene).calls[0].saw


def test_a_tool_that_was_off_was_never_touched_so_it_is_not_on_the_list() -> None:
    """§3.6: an `off` tool passes straight through with no count and no record, and the view agrees."""
    classes = {"a": "off", "lookup_order": "read"}
    script = [("a", {}), ("lookup_order", {"query": "q"})]
    view = view_of(way_in(script=script, classes=classes, fails=asked("passes")))
    assert [c.tool for c in view.calls] == ["lookup_order"]


@pytest.mark.parametrize("make", [
    lambda f: way_in(fails=f),
    lambda f: plain("gives_up", fails=f),
    lambda f: plain("retries", fails=f),
], ids=["way-in", "gives-up", "retries"])
def test_a_field_a_way_in_cannot_fill_is_none_and_never_absent(make: Any) -> None:
    """§11.4 invariant 1. Neither reports tokens or an outcome, and the case has no turns. A check written against one
    way in must not fall over on another."""
    view = view_of(make(asked("passes")))
    for read in VIEW_FIELDS.values():
        read(view)  # none of them raises
    assert view.outcome is None
    assert view.tokens_in is None
    assert view.tokens_out is None
    assert view.case.turns is None


def test_the_view_is_the_same_for_the_same_agent_through_either_way() -> None:
    """Plan BK3.10 and §11.2 invariant 5: what a check sees does not depend on the way in. The `rollout` kind and the
    way-in kind running the same calls under the same condition show the same calls and the same changes."""
    plain_view = view_of(plain("gives_up", "tool:check_policy#1=empty", fails=asked("passes")))
    own_module().reset()
    script = [("lookup_order", {"query": CASE["input"]}), ("check_policy", {"topic": "refunds"}),
              ("lookup_order", {"query": CASE["input"], "detail": "delivery"})]
    protocol_view = view_of(way_in("tool:check_policy#1=empty", script=script, fails=asked("passes")))
    assert view_calls(plain_view) == view_calls(protocol_view)
    assert view_changes(plain_view) == view_changes(protocol_view)
    assert plain_view.condition.name == protocol_view.condition.name


# ---------------------------------------------------------------------------
# the extension point, held to its version
# ---------------------------------------------------------------------------


def test_the_version_is_one_and_the_module_hands_on_the_interfaces_own() -> None:
    """§11: every interface carries one, 1 at v0.1.0. A bump is a breaking change with a session of its own, and this
    is the line that makes that visible."""
    assert interfaces.CHECK_INTERFACE_VERSION == 1
    assert checks().CHECK_INTERFACE_VERSION == 1
    assert checks().CHECK_INTERFACE_VERSION is interfaces.CHECK_INTERFACE_VERSION


def test_a_check_written_outside_the_package_runs_with_no_core_file_touched(tmp_path: Any, fresh_checks: ModuleType,
                                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """§11's test for every interface: a test-only implementation outside the package, end to end. This one is not
    even in the repository: it is written now, found by its name, and never heard of until the settings say so."""
    (tmp_path / "my_app_checks.py").write_text(textwrap.dedent("""
        def refund_ok(run):
            refunds = [c for c in run.calls if c.tool == "issue_refund"]
            return None if refunds else "no_refund"
    """))
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        assert verdict(plain("repeats_write", fails={"own": "my_app_checks:refund_ok"}).run) == OK
        v = judged(plain("gives_up", fails={"own": "my_app_checks:refund_ok"}).run)
        assert state_of(v) == "failed" and is_own(v)
        assert judged_by(v) == "your check"
    finally:
        sys.modules.pop("my_app_checks", None)
