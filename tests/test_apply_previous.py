"""What "the previous result of the same tool" is, once an earlier call was faulted.

Invariant pinned here (Break — Plan, the applying module):
- BK2.13, the half left open until Taylor ruled, 2026-11-04: `previous` is what the real tool returned, the
         most recent result it handed back on an earlier call. A call on which it did not run, or raised,
         leaves `previous` as it was.

So `stale` stands for what it stands for, a cache serving what the server said earlier, knowing nothing of
what some other failure did to the reply on its way to the agent. `stale` then depends on the tool's own
history and on no other change, unless that change stopped the tool from running.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import ModuleType
from typing import Any

import pytest

from tests.apply_support import LONG, MAPPING, REPEATABLE, Tool, call, seen_call, session, stand_in_module
from tests.test_apply_adding_a_fault import watching

WORD = "quillfern"


def run(text: str, *values: Any, calls: int = 2, **over: Any) -> list[tuple]:
    tool = Tool(*values)
    s = session(text, tools=REPEATABLE, marker=WORD, **over)
    return [seen_call(s, "a", tool) for _ in range(calls)]


class Raises(Tool):
    """A real tool that raises on the calls named, and answers on the rest."""

    def __init__(self, *values: Any, on: tuple[int, ...]) -> None:
        super().__init__(*values)
        self.on = on

    def __call__(self, **args: Any) -> Any:
        self.log.append(args)
        if len(self.log) in self.on:
            raise LookupError("no")
        return self.values[len(self.log) - 1]


@pytest.fixture
def stand_in() -> Iterator[ModuleType]:
    yield from stand_in_module()


@pytest.fixture
def with_a_watching_fault() -> Iterator[tuple[ModuleType, ModuleType, list[Any]]]:
    yield from watching()


# ---------------------------------------------------------------------------
# a fault that ran the tool: what it returned, not what the agent saw
# ---------------------------------------------------------------------------


def test_after_cut_off_stale_is_the_whole_result() -> None:
    whole = LONG + "the end of it"
    got = run("tool:a#1=cut_off + tool:a#2=stale", whole, "fresh")
    assert got == [("result", whole[:200]), ("result", whole)]


def test_after_empty_stale_is_what_the_tool_returned() -> None:
    assert run("tool:a#1=empty + tool:a#2=stale", "one", "fresh") == [("result", ""), ("result", "one")]


def test_after_malformed_stale_is_the_result_whole() -> None:
    got = run("tool:a#1=malformed + tool:a#2=stale", MAPPING, "fresh")
    assert got[0][1] != MAPPING
    assert got[1] == ("result", MAPPING)


def test_after_a_planted_instruction_stale_carries_no_plant() -> None:
    """The word was planted once, on one call. Handing it back would plant it again, and on a call whose
    condition does not say so."""
    got = run("tool:a#1=planted_instruction + tool:a#2=stale", "one", "fresh")
    assert WORD in got[0][1]
    assert got[1] == ("result", "one")


def test_after_a_lost_reply_stale_is_the_result_the_agent_never_got() -> None:
    """The tool acted, and returned. It is an oddity a real stale cache has too."""
    got = run("tool:a#1=lost_reply + tool:a#2=stale", "the receipt", "fresh")
    assert got[0][0] == "failure"
    assert got[1] == ("result", "the receipt")


@pytest.mark.parametrize("fault", ["empty", "cut_off", "malformed", "planted_instruction", "lost_reply"])
def test_stale_is_the_same_whatever_else_was_done_to_the_call_before(fault: str) -> None:
    """Removing a change on the first call changes nothing about the second, which is what lets a shrink
    take a condition apart."""
    tools = (MAPPING, "fresh")
    alone = run("tool:a#2=stale", *tools)
    with_fault = run(f"tool:a#1={fault} + tool:a#2=stale", *tools)
    assert with_fault[1] == alone[1] == ("result", MAPPING)


# ---------------------------------------------------------------------------
# a call on which the tool did not run, or raised: previous stays as it was
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fault", ["error", "timeout", "rate_limited"])
def test_a_call_the_tool_did_not_run_for_leaves_previous_as_it_was(fault: str) -> None:
    got = run(f"tool:a#2={fault} + tool:a#3=stale", "one", "two", "three", calls=3)
    assert got[1][0] == "failure"
    assert got[2] == ("result", "one")


@pytest.mark.parametrize("fault", ["error", "timeout", "rate_limited"])
@pytest.mark.parametrize("value, nothing", [("text", ""), (MAPPING, {})], ids=["text", "mapping"])
def test_stale_after_the_tool_never_ran_behaves_as_empty(fault: str, value: Any, nothing: Any) -> None:
    """Still no result from the tool, so it is a first call's `empty`, of this call's own result."""
    got = run(f"tool:a#1={fault} + tool:a#2=stale", value)
    assert got[1] == ("result", nothing)


def test_a_call_whose_tool_raised_leaves_previous_as_it_was() -> None:
    tool = Raises("one", "unused", "three", on=(2,))
    s = session("tool:a#3=stale")
    assert seen_call(s, "a", tool) == ("result", "one")
    with pytest.raises(LookupError):
        call(s, "a", tool)
    assert seen_call(s, "a", tool) == ("result", "one")


def test_a_call_whose_tool_raised_under_a_fault_leaves_previous_as_it_was() -> None:
    tool = Raises("one", "unused", "three", on=(2,))
    s = session("tool:a#2=cut_off + tool:a#3=stale")
    seen_call(s, "a", tool)
    with pytest.raises(LookupError):
        call(s, "a", tool)
    assert seen_call(s, "a", tool) == ("result", "one")


# ---------------------------------------------------------------------------
# stale on stale
# ---------------------------------------------------------------------------


def test_stale_on_every_call_is_always_one_behind() -> None:
    """Under "what the agent saw" this would be `empty` on every call. The tool runs each time, and each
    call's own result is the next call's previous."""
    assert run("tool:a#*=stale", "one", "two", "three", "four", calls=4) == [
        ("result", ""), ("result", "one"), ("result", "two"), ("result", "three")]


def test_a_stale_calls_own_real_result_is_the_next_calls_previous() -> None:
    got = run("tool:a#2-3=stale", "one", "two", "three", calls=3)
    assert got == [("result", "one"), ("result", "one"), ("result", "two")]


# ---------------------------------------------------------------------------
# held per tool, and for a stand-in, and as a copy
# ---------------------------------------------------------------------------


def test_another_tools_faults_have_nothing_to_do_with_it() -> None:
    s = session("tool:b#1=error + tool:a#2=stale", tools=REPEATABLE)
    a = Tool("one", "two")
    seen_call(s, "a", a)
    seen_call(s, "b", Tool("b's"))
    assert seen_call(s, "a", a) == ("result", "one")


def test_for_a_stand_in_it_is_what_the_stand_in_returned(stand_in: Any) -> None:
    """It stands where the tool stood."""
    stand_in.ANSWER_NEXT = LONG
    real = Tool("the real answer")
    s = session("tool:w#1=cut_off + tool:w#2=stale", tools={"w": {"class": "write", "stand_in": "tests.apply_support_standin:refund"}})
    assert seen_call(s, "w", real) == ("result", LONG[:200])
    assert seen_call(s, "w", real) == ("result", LONG)
    assert real.runs == 0


def test_under_a_fault_too_an_agents_edit_does_not_reach_it() -> None:
    """Ruling 14 on a faulted call: a short result under `cut_off` reaches the agent as the tool's own
    object, and what the agent then does to it is not what the tool returned."""
    tool = Tool({"order": 7, "status": "shipped"}, "fresh")
    s = session("tool:a#1=cut_off + tool:a#2=stale")
    first = call(s, "a", tool)
    del first["status"]
    assert call(s, "a", tool) == {"order": 7, "status": "shipped"}


# ---------------------------------------------------------------------------
# what a fault is given
# ---------------------------------------------------------------------------


def test_the_context_holds_what_the_tool_returned(with_a_watching_fault: Any) -> None:
    c, a, watched = with_a_watching_fault
    whole = LONG + "the end of it"
    s = a.Session(c.parse("tool:a#1=cut_off + tool:a#2=watch"), seed=1, tools={"a": "read"})
    tool = Tool(whole, "fresh")
    seen_call_on(a, s, tool)
    seen_call_on(a, s, tool)
    assert watched[0].previous == whole


def test_the_context_has_none_after_a_call_the_tool_did_not_run_for(with_a_watching_fault: Any) -> None:
    c, a, watched = with_a_watching_fault
    s = a.Session(c.parse("tool:a#1=error + tool:a#2=watch"), seed=1, tools={"a": "read"})
    tool = Tool("fresh")
    seen_call_on(a, s, tool)
    seen_call_on(a, s, tool)
    assert watched[0].previous is None


def seen_call_on(a: ModuleType, s: Any, tool: Tool) -> Any:
    """One call on a catalogue of its own, whose `ToolFailure` is not the suite's."""
    try:
        return call(s, "a", tool)
    except a.ToolFailure as failure:
        return failure
