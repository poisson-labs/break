"""What Break may do to which tool: the classes of spec §3.6, stand-ins, and what a way in cannot do.

Invariants pinned here (Break — Plan, the applying module):
- BK2.5  Tool classes are enforced. A `write` tool with neither `repeatable` nor a stand-in is refused
         before any run; an `off` tool is never wrapped; a tool not classed stops the run with its
         name; `lost_reply` is refused on a `read` tool and on a `write` tool that is not `repeatable`
         and has no stand-in.
- BK2.6  A stand-in replaces the tool in every run, the control included.
- Spec §11.2 invariant 6, as the catalogue's rulings left it: conversation changes and model faults
  are refused for a way in without the capability, and taken by one that has it.

The refusals' names and the moment each comes are ruling 5, an `off` tool's handling ruling 6, and a
stand-in's `real_ran` ruling 7. Each refusal is pinned by its kind and the facts it carries, never by
its words, with an accepted control beside it.
"""

from __future__ import annotations

import textwrap
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from poisson_break.interfaces import Capabilities
from poisson_break.records import Call
from tests.apply_support import (
    ALL_CAPABILITIES,
    LONG,
    Tool,
    apply,
    call,
    seen_call,
    session,
    stand_in_module,
)
from tests.changes_support import PLAN_WORDS, REAL_RUNS, changes

STAND_IN = "tests.apply_support_standin:refund"
BROKEN_STAND_IN = "tests.apply_support_standin:broken"
INTERRUPTED_STAND_IN = "tests.apply_support_standin:interrupted"
REPEATABLE_WRITE = {"class": "write", "repeatable": True}
WITH_STAND_IN = {"class": "write", "stand_in": STAND_IN}

POSITIONS = ["#1", "#2-4", "#*", "~0.5", "~1"]


@pytest.fixture
def stand_in() -> Iterator[ModuleType]:
    yield from stand_in_module()


def refused(text: str, tools: dict[str, Any]) -> Any:
    with pytest.raises(apply().ToolRefused) as refusal:
        session(text, tools=tools)
    return refusal.value


# ---------------------------------------------------------------------------
# BK2.5  a write tool must say how it is made safe
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("line", ["write", {"class": "write"}, {"class": "write", "repeatable": False}],
                         ids=["bare-word", "no-keys", "repeatable-false"])
def test_a_write_tool_with_no_way_to_be_safe_is_refused_naming_it(line: Any) -> None:
    refusal = refused("", {"lookup_order": "read", "issue_refund": line})
    assert refusal.tool == "issue_refund"
    assert refusal.change is None


@pytest.mark.parametrize("line", [REPEATABLE_WRITE, WITH_STAND_IN], ids=["repeatable", "stand-in"])
def test_a_write_tool_that_says_how_is_taken(line: Any) -> None:
    s = session("", tools={"issue_refund": line})
    assert s.stopped is None


def test_an_unsafe_write_tool_is_refused_though_the_condition_never_names_it() -> None:
    """Refused before any run, and the control is a run."""
    assert refused("tool:lookup_order#1=error", {"lookup_order": "read", "issue_refund": "write"}).tool == "issue_refund"


def test_a_line_that_is_no_class_is_refused_naming_the_tool() -> None:
    """The settings refuse it first (BK4.3). A way in that builds its own table comes here."""
    assert refused("", {"lookup_order": "sideways"}).tool == "lookup_order"


def test_a_refusal_is_one_line_with_no_word_of_the_plans_machinery() -> None:
    """Plan §2 item 7, and §3.6's one line naming the tool."""
    for text, tools in [("", {"w": "write"}), ("tool:r#1=lost_reply", {"r": "read"}), ("tool:o#1=error", {"o": "off"})]:
        words = str(refused(text, tools))
        assert words.strip()
        assert "\n" not in words
        assert not PLAN_WORDS.search(words), words


# ---------------------------------------------------------------------------
# BK2.5  lost_reply
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("position", POSITIONS)
def test_lost_reply_is_refused_on_a_read_tool_at_every_position(position: str) -> None:
    text = f"tool:a{position}=lost_reply"
    refusal = refused(text, {"a": "read"})
    assert refusal.tool == "a"
    assert refusal.change == changes().name(changes().parse(text))


@pytest.mark.parametrize("position", POSITIONS)
@pytest.mark.parametrize("line", [REPEATABLE_WRITE, WITH_STAND_IN], ids=["repeatable", "stand-in"])
def test_lost_reply_is_taken_on_a_tool_safe_to_repeat(position: str, line: Any) -> None:
    assert session(f"tool:a{position}=lost_reply", tools={"a": line}).stopped is None


@pytest.mark.parametrize("fault", [f for f in REAL_RUNS if f != "lost_reply"])
def test_every_other_fault_is_taken_on_a_read_tool(fault: str) -> None:
    """Only `lost_reply` is a repeat of something done: §3.6 refuses it, and nothing else, on a read."""
    assert session(f"tool:a#1={fault}", tools={"a": "read"}).stopped is None


def test_lost_reply_on_one_tool_is_judged_by_that_tools_class() -> None:
    """A repeatable tool elsewhere in the table does not make this one safe."""
    tools = {"a": "read", "w": REPEATABLE_WRITE}
    assert refused("tool:w#1=error + tool:a#1=lost_reply", tools).tool == "a"
    assert session("tool:w#1=lost_reply + tool:a#1=error", tools=tools).stopped is None


# ---------------------------------------------------------------------------
# BK2.5  a tool that is not classed
# ---------------------------------------------------------------------------


def test_a_tool_not_classed_stops_the_run_with_its_name_before_it_runs() -> None:
    s = session("", tools={"a": "read"})
    tool = Tool()
    with pytest.raises(apply().ToolRefused) as refusal:
        call(s, "unknown_tool", tool)
    assert refusal.value.tool == "unknown_tool"
    assert tool.runs == 0
    assert s.stopped is refusal.value


def test_a_tool_not_classed_stops_the_run_for_every_later_call() -> None:
    """§3.6: it stops the hunt. An agent that catches the exception and goes on does not un-stop it,
    and what it does next is not part of any run that is counted."""
    s = session("", tools={"a": "read"})
    with pytest.raises(apply().ToolRefused):
        call(s, "unknown_tool", Tool())
    tool = Tool()
    with pytest.raises(apply().ToolRefused):
        call(s, "a", tool)
    assert tool.runs == 0


def test_a_tool_not_classed_is_not_a_tool_failure_the_agent_can_handle() -> None:
    """It is about the settings, and is not a behaviour of the agent's tool."""
    s = session("", tools={"a": "read"})
    with pytest.raises(apply().ToolRefused) as refusal:
        call(s, "unknown_tool", Tool())
    assert not isinstance(refusal.value, apply().ToolFailure)


def test_a_condition_on_a_tool_not_classed_never_runs_it() -> None:
    """Whether the session refuses such a condition when it is made or on the call is not settled by
    the spec, and no test decides it. The tool does not run under it either way."""
    tool = Tool()
    with pytest.raises(apply().ToolRefused):
        call(session("tool:unknown_tool#1=empty", tools={"a": "read"}), "unknown_tool", tool)
    assert tool.runs == 0


# ---------------------------------------------------------------------------
# BK2.5  an off tool
# ---------------------------------------------------------------------------


def test_an_off_tool_is_handed_straight_through() -> None:
    handle = object()
    tool = Tool(handle)
    s = session("", tools={"o": "off"})
    assert call(s, "o", tool, query="x") is handle
    assert tool.log == [{"query": "x"}]


def test_an_off_tool_leaves_no_record_and_is_not_counted() -> None:
    """§3.6: Break never touches it, and never counts it."""
    s = session("tool:a#2=empty", tools={"a": "read", "o": "off"})
    a = Tool("answer")
    assert seen_call(s, "a", a) == ("result", "answer")
    for _ in range(3):
        call(s, "o", Tool())
    assert seen_call(s, "a", a) == ("result", "")
    assert [c.tool for c in s.calls] == ["a", "a"]
    assert [c.call for c in s.calls] == [1, 2]


def test_an_off_tools_own_exception_passes_through_unrecorded() -> None:
    wrong = LookupError("no")
    s = session("", tools={"o": "off"})
    with pytest.raises(LookupError) as raised:
        call(s, "o", Tool(raises=wrong))
    assert raised.value is wrong
    assert s.calls == ()
    assert s.stopped is None


@pytest.mark.parametrize("position", ["#1", "#*", "~0.5"])
def test_a_condition_that_names_an_off_tool_is_refused(position: str) -> None:
    """Ruling 6. "Break never touches it", and a change that said otherwise would silently do nothing
    and be reported as a condition that did not fail."""
    text = f"tool:o{position}=error"
    refusal = refused(text, {"o": "off"})
    assert refusal.tool == "o"
    assert refusal.change == changes().name(changes().parse(text))


def test_a_wrapped_off_tool_is_the_tool() -> None:
    """Wrapped or not, it is reached as itself: no record, no count, under any condition elsewhere."""
    tool = Tool("answer")
    s = session("tool:a#1=error", tools={"a": "read", "o": "off"})
    with s:
        assert apply().wrap("o", tool)(query="x") == "answer"
    assert s.calls == ()
    assert tool.log == [{"query": "x"}]


# ---------------------------------------------------------------------------
# BK2.6  a stand-in replaces the tool in every run, the control included
# ---------------------------------------------------------------------------


def test_under_the_control_the_stand_in_runs_and_the_real_tool_does_not(stand_in: Any) -> None:
    real = Tool("the real answer")
    s = session("", tools={"issue_refund": WITH_STAND_IN})
    assert call(s, "issue_refund", real, order=7) == stand_in.ANSWER
    assert real.runs == 0
    assert stand_in.LOG == [{"order": 7}]


def test_the_stand_in_is_given_the_calls_arguments_by_name(stand_in: Any) -> None:
    """Ruling 4. It stands where the tool stood, so it takes what the tool takes."""
    s = session("", tools={"issue_refund": WITH_STAND_IN})
    call(s, "issue_refund", Tool(), order=7, reason="late")
    assert stand_in.LOG == [{"order": 7, "reason": "late"}]


def test_the_record_treats_the_stand_ins_run_as_the_tools(stand_in: Any) -> None:
    """Ruling 7. `lost_reply` is offered on stand-ins (§3.6), and `duplicate_write` needs a second real
    execution (BK3.4): a stand-in that always read as not run could never show one."""
    s = session("", tools={"issue_refund": WITH_STAND_IN})
    call(s, "issue_refund", Tool(), order=7)
    assert s.calls == (Call(tool="issue_refund", call=1, change=None, real_ran=True),)


@pytest.mark.parametrize("fault", list(REAL_RUNS))
def test_under_every_fault_the_stand_in_is_what_the_fault_runs(stand_in: Any, fault: str) -> None:
    """The fault's `real` is the stand-in. The real tool never runs in a run where it has one, or a
    fault could put a real refund through. `slow` states its delay, which this test does not wait out."""
    real = Tool("the real answer")
    s = session(f"tool:issue_refund#1={fault}", tools={"issue_refund": WITH_STAND_IN}, marker="quillfern",
                run_seconds=1.0 if fault == "slow" else None)
    try:
        seen_call(s, "issue_refund", real, order=7)
    except apply().RunOutOfTime:
        assert fault == "slow"
    assert real.runs == 0
    assert len(stand_in.LOG) == (1 if REAL_RUNS[fault] else 0)
    assert s.calls[0].real_ran is REAL_RUNS[fault]


def test_a_fault_edits_what_the_stand_in_returned(stand_in: Any) -> None:
    s = session("tool:issue_refund#1=cut_off", tools={"issue_refund": WITH_STAND_IN})
    stand_in.ANSWER_NEXT = LONG
    assert call(s, "issue_refund", Tool(), order=7) == LONG[:200]


def test_a_stand_in_written_outside_the_package_is_found_by_its_import_path(tmp_path: Path,
                                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """§3.6 and §11: named in the settings as `my_app.fakes:refund`, and loaded by that name."""
    (tmp_path / "my_own_fakes.py").write_text(textwrap.dedent("""\
        def refund(**args):
            return {"refunded": args["order"]}
    """))
    monkeypatch.syspath_prepend(tmp_path)
    s = session("", tools={"issue_refund": {"class": "write", "stand_in": "my_own_fakes:refund"}})
    assert call(s, "issue_refund", Tool(), order=7) == {"refunded": 7}


@pytest.mark.parametrize("path", ["no_such_module_anywhere:refund", "tests.apply_support_standin:no_such_name",
                                  "tests.apply_support_standin", "tests.apply_support_standin:NOT_CALLABLE", ""],
                         ids=["no-module", "no-name", "no-colon", "not-callable", "empty"])
def test_a_stand_in_that_cannot_be_loaded_is_refused_before_any_run(path: str) -> None:
    """Ruling 5. Better here than as one instrument error per run, on hundreds of runs."""
    assert refused("", {"issue_refund": {"class": "write", "stand_in": path}}).tool == "issue_refund"


# ---------------------------------------------------------------------------
# §11.2 invariant 6: what a way in cannot do
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["user:repeats@2", "user:interrupts@1", "user:goes_quiet@3", "user:presses@2"])
def test_a_conversation_change_is_refused_for_a_session_with_no_adapter(text: str) -> None:
    """A plain Prove target takes no conversation moves (§7.1). Refused when the session is made, so
    no tool has run."""
    with pytest.raises(changes().NeedsAdapter) as refusal:
        session(text)
    assert refusal.value.change == text


@pytest.mark.parametrize("fault", ["error", "timeout", "rate_limited", "empty", "cut_off"])
def test_a_model_fault_is_refused_for_a_session_with_no_adapter(fault: str) -> None:
    text = f"model:{fault}#1"
    with pytest.raises(changes().NeedsAdapter) as refusal:
        session(text)
    assert refusal.value.change == text


def test_the_refusal_names_the_change_that_is_the_trouble_in_a_longer_condition() -> None:
    with pytest.raises(changes().NeedsAdapter) as refusal:
        session("input:typos + tool:a#1=error + user:repeats@2")
    assert refusal.value.change == "user:repeats@2"


@pytest.mark.parametrize("text", ["user:repeats@2", "model:error#1"])
def test_a_way_in_that_can_do_it_is_taken(text: str) -> None:
    """Asked of the capabilities and not of the surface, so an adapter lands with no core change."""
    assert session(text, capabilities=Capabilities(**ALL_CAPABILITIES)).stopped is None


@pytest.mark.parametrize("text, capability", [("user:repeats@2", "conversation"), ("model:error#1", "model_calls"),
                                              ("tool:a#1=error", "tool_calls")])
def test_the_session_asks_of_the_capabilities_it_was_given(text: str, capability: str) -> None:
    """The one capability off, the others on: a session that decided by the surface alone, or looked
    at the wrong one, does not refuse here."""
    can = dict(ALL_CAPABILITIES)
    can[capability] = False
    with pytest.raises(changes().NeedsAdapter):
        session(text, capabilities=Capabilities(**can))


def test_with_a_capable_way_in_a_model_change_leaves_every_tool_call_alone() -> None:
    """§3.1: a change that is not on a tool never applies to a tool call, and its record says it did
    not apply, the core having no way to apply it."""
    s = session("model:error#1", tools={"error": "read"}, capabilities=Capabilities(**ALL_CAPABILITIES))
    assert seen_call(s, "error", Tool("answer")) == ("result", "answer")
    assert s.calls[0].change is None
    assert s.applied[0].applied is False
    assert s.applied[0].applied_call is None


def test_a_session_needs_no_capability_for_inputs() -> None:
    """§11.2: `input:` and `env:` ask for nothing, so the plain way in takes them."""
    can = Capabilities(tool_calls=False, model_calls=False, conversation=False)
    assert session("input:typos", capabilities=can).stopped is None
