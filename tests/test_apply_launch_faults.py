"""The ten launch faults on a live call: what reaches the agent, whether the real tool ran, and what
the run's record holds afterwards. Spec §3.2's table, through the applier.

`tests/test_launch_faults.py` holds each fault's own `apply` on a frozen call. Here the fault is
reached the way a run reaches it: a condition, a session, call numbers counted by the session, and
the record it keeps.

Invariants pinned here (Break — Plan, the applying module):
- BK2.1  The table is the behaviour. For each of the ten faults, a scripted agent sees what spec §3.2
         says, and the real tool ran or did not run as the table says.
- BK2.8, the launch half: `slow` sleeps its default delay, and no other fault waits at all.

How an error reaches the agent is ruling 3; the records are ruling 2.
"""

from __future__ import annotations

import json
import re
import time

import pytest

from poisson_break.records import Applied, Call
from tests.apply_support import (
    EARLIER,
    LISTING,
    LONG,
    MAPPING,
    REPEATABLE,
    SEED,
    Tool,
    apply,
    call,
    run_way_in,
    seen_call,
    session,
)
from tests.changes_support import REAL_RUNS, REAL_TEXT, STAGED_WORDS, TOOL_FAULTS, changes, json_forms
from tests.test_launch_faults import _broken, _does_not_parse, _one_closing_bracket_gone, _one_field_renamed

# All but `slow`, whose default delay is 5 s and which is held once, below, through a scripted agent.
QUICK = [f for f in TOOL_FAULTS if f != "slow"]


def live(fault: str, value: object = LONG, *, position: str = "#2", marker: str = "quillfern") -> tuple[tuple, Tool, object]:
    """`a` called once clean, then once under the fault. What the agent saw on the second call, the
    tool, the session."""
    tool = Tool(EARLIER, value)
    s = session(f"tool:a{position}={fault}", tools=REPEATABLE, marker=marker)
    assert seen_call(s, "a", tool, query="first") == ("result", EARLIER)
    return seen_call(s, "a", tool, query="second"), tool, s


# ---------------------------------------------------------------------------
# every fault, against the table and the record
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fault", QUICK)
def test_the_real_tool_runs_as_the_table_says_and_the_record_says_the_same(fault: str) -> None:
    """The record is what `duplicate_write` and the replay are later read from: a `real_ran` that
    says other than what happened makes both wrong."""
    _, tool, s = live(fault)
    ran = REAL_RUNS[fault]
    assert tool.runs == (2 if ran else 1)
    assert s.calls == (
        Call(tool="a", call=1, change=None, real_ran=True),
        Call(tool="a", call=2, change=f"tool:a#2={fault}", real_ran=ran),
    )


@pytest.mark.parametrize("fault", QUICK)
def test_the_change_is_recorded_as_having_landed_on_its_call(fault: str) -> None:
    _, _, s = live(fault)
    assert s.applied == (Applied(surface="tool", tool="a", fault=fault, call="#2", applied=True, applied_call=2),)


@pytest.mark.parametrize("fault", QUICK)
def test_the_real_tool_is_given_the_call_it_was_asked_for(fault: str) -> None:
    """A fault acts on what comes back. What goes in is the agent's, under every fault."""
    _, tool, _ = live(fault)
    assert tool.log[0] == {"query": "first"}
    if REAL_RUNS[fault]:
        assert tool.log[1] == {"query": "second"}


@pytest.mark.parametrize("fault", QUICK)
def test_a_fault_on_the_first_call_lands_there(fault: str) -> None:
    """Call numbers count from 1, and a fault on the first call has nothing before it to lean on."""
    tool = Tool(LONG)
    s = session(f"tool:a#1={fault}", tools=REPEATABLE, marker="quillfern")
    seen_call(s, "a", tool)
    assert s.calls == (Call(tool="a", call=1, change=f"tool:a#1={fault}", real_ran=REAL_RUNS[fault]),)
    assert tool.runs == (1 if REAL_RUNS[fault] else 0)


@pytest.mark.parametrize("fault", TOOL_FAULTS)
def test_a_scripted_agent_on_the_way_in_sees_the_fault_where_it_falls(fault: str) -> None:
    """BK2.1's own words: a scripted agent, every fault. It is told what the table says on the second
    call of `lookup_order` and nothing else changes, the slow one taking its default of 5 s."""
    tools = {"lookup_order": Tool(EARLIER, LONG, "the third answer"), "check_policy": Tool("policy text")}
    classes = {"lookup_order": {"class": "write", "repeatable": True}, "check_policy": "read"}
    started = time.monotonic()
    result, agent, s, _ = run_way_in(f"tool:lookup_order#2={fault}", tools=tools, classes=classes, marker="quillfern")
    took = time.monotonic() - started
    assert result.ended == "returned"
    assert [v.tool for v in agent.seen] == ["lookup_order", "check_policy", "lookup_order"]
    assert agent.seen[0].result == EARLIER and agent.seen[0].error is None
    assert agent.seen[1].result == "policy text" and agent.seen[1].error is None
    last = agent.seen[2]
    table = {
        "error": lambda: last.error.kind == "error" and last.result is None,
        "timeout": lambda: last.error.kind == "timeout" and last.result is None,
        "slow": lambda: last.error is None and last.result == LONG,
        "rate_limited": lambda: last.error.kind == "rate_limited" and last.result is None,
        "empty": lambda: last.error is None and last.result == "",
        "cut_off": lambda: last.error is None and last.result == LONG[:200],
        "malformed": lambda: last.error is None and last.result == LONG,
        "stale": lambda: last.error is None and last.result == EARLIER,
        "lost_reply": lambda: last.error.kind == "error" and last.result is None,
        "planted_instruction": lambda: last.error is None and LONG in last.result and "quillfern" in last.result,
    }
    assert table[fault](), last
    assert tools["lookup_order"].runs == (2 if REAL_RUNS[fault] else 1)
    assert s.calls[2].real_ran is REAL_RUNS[fault]
    assert s.calls[2].change == f"tool:lookup_order#2={fault}"
    assert s.applied == (Applied(surface="tool", tool="lookup_order", fault=fault, call="#2", applied=True, applied_call=2),)
    if fault == "slow":
        assert 4.99 <= took < 7, took
    else:
        assert took < 2, took


# ---------------------------------------------------------------------------
# error
# ---------------------------------------------------------------------------


def test_error_reaches_the_agent_as_a_tool_failure_of_its_kind() -> None:
    what, _, _ = live("error")
    assert what[:2] == ("failure", "error")
    assert what[2].strip()


def test_an_error_is_raised_and_not_handed_back_as_a_value() -> None:
    """§3.2: the tool raises. An agent whose tool quietly returned an error object would carry on as
    if it had a result, and the framework's own error path would never run."""
    s = session("tool:a#1=error")
    with pytest.raises(apply().ToolFailure):
        call(s, "a", Tool())


@pytest.mark.parametrize("fault", ["error", "rate_limited", "lost_reply"])
def test_an_ordinary_failure_is_not_a_timeout(fault: str) -> None:
    """An agent's own `except TimeoutError` must not fire on these."""
    s = session(f"tool:a#1={fault}", tools=REPEATABLE)
    with pytest.raises(apply().ToolFailure) as failure:
        call(s, "a", Tool())
    assert not isinstance(failure.value, TimeoutError)


@pytest.mark.parametrize("fault", ["error", "timeout", "rate_limited", "lost_reply"])
def test_the_words_the_agent_reads_are_the_faults_and_do_not_say_it_was_staged(fault: str) -> None:
    """§3.2: a fault enters where a real failure would."""
    line = next(e for e in changes().CATALOG if e.surface == "tool" and e.name == fault)
    what, _, _ = live(fault)
    assert not STAGED_WORDS.search(what[2]), what[2]
    outcome = line.fault.apply(
        changes().CallContext(tool="a", args={}, call=2, condition=changes().parse(""), seed=SEED),
        real=lambda: None, params=line.parameters, rng=None)
    assert what[2] == outcome.message


# ---------------------------------------------------------------------------
# timeout
# ---------------------------------------------------------------------------


def test_timeout_is_a_timeout_the_agents_own_code_can_catch_as_one() -> None:
    """§11.1: a way in raises a timeout differently from an error, and a plain agent's `except
    TimeoutError` is the path a real timeout takes."""
    s = session("tool:a#1=timeout")
    with pytest.raises(TimeoutError) as failure:
        call(s, "a", Tool())
    assert isinstance(failure.value, apply().ToolFailure)
    assert failure.value.kind == "timeout"


def test_timeout_comes_at_once() -> None:
    """§3.2: at once. A real wait would spend the run's clock on what the agent sees."""
    started = time.monotonic()
    live("timeout")
    assert time.monotonic() - started < 1


# ---------------------------------------------------------------------------
# rate_limited
# ---------------------------------------------------------------------------


def test_rate_limited_says_to_wait_its_default_and_the_applier_does_not_wait() -> None:
    """It says thirty seconds. It is the agent that may wait; the applier does not."""
    started = time.monotonic()
    what, _, _ = live("rate_limited")
    assert time.monotonic() - started < 1
    assert what[:2] == ("failure", "rate_limited")
    assert re.search(r"\b30\b", what[2]), what[2]


# ---------------------------------------------------------------------------
# empty
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value, nothing", [
    (REAL_TEXT, ""),
    (MAPPING, {}),
    (LISTING, []),
    (7, None),
], ids=["text", "mapping", "list", "number"])
def test_empty_reaches_the_agent_as_nothing_of_the_results_own_kind(value: object, nothing: object) -> None:
    what, tool, _ = live("empty", value)
    assert what == ("result", nothing)
    assert type(what[1]) is type(nothing)
    assert tool.runs == 2


# ---------------------------------------------------------------------------
# cut_off
# ---------------------------------------------------------------------------


def test_cut_off_reaches_the_agent_cut_to_its_default_length() -> None:
    what, _, _ = live("cut_off", LONG)
    assert what == ("result", LONG[:200])
    assert len(LONG) > 200


@pytest.mark.parametrize("value", [{"note": "x" * 400}, ["x" * 400]], ids=["mapping", "list"])
def test_cut_off_reaches_the_agent_as_structured_results_written_out_and_cut(value: object) -> None:
    what, _, _ = live("cut_off", value)
    assert isinstance(what[1], str)
    assert len(what[1]) == 200
    assert any(form.startswith(what[1]) for form in json_forms(value))


def test_cut_off_leaves_a_short_result_as_the_tool_returned_it() -> None:
    what, _, _ = live("cut_off", MAPPING)
    assert what == ("result", MAPPING)


# ---------------------------------------------------------------------------
# malformed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [MAPPING, LISTING], ids=["mapping", "list"])
def test_malformed_reaches_the_agent_with_the_results_structure_broken(value: object) -> None:
    what, tool, _ = live("malformed", value)
    assert what[0] == "result"
    assert _broken(value, what[1]), what[1]
    assert tool.runs == 2


def test_malformed_reaches_the_agent_with_json_text_broken() -> None:
    text = json.dumps(MAPPING)
    what, _, _ = live("malformed", text)
    assert what[1] != text
    if _does_not_parse(what[1]):
        assert _one_closing_bracket_gone(text, what[1])
    else:
        assert _one_field_renamed(MAPPING, json.loads(what[1]))


def test_malformed_leaves_plain_text_for_the_agent_as_it_was() -> None:
    what, tool, _ = live("malformed", REAL_TEXT)
    assert what == ("result", REAL_TEXT)
    assert tool.runs == 2


# ---------------------------------------------------------------------------
# stale, with every earlier call clean: what the tool returned and what the agent saw are the same
# ---------------------------------------------------------------------------


def test_stale_reaches_the_agent_as_the_previous_result_and_the_tool_still_ran() -> None:
    """The third column says yes, so whatever the tool does happened, and the agent cannot tell."""
    what, tool, _ = live("stale", "the fresh answer")
    assert what == ("result", EARLIER)
    assert tool.runs == 2


def test_stale_is_the_call_just_before_and_not_the_first() -> None:
    tool = Tool("one", "two", "three")
    s = session("tool:a#3=stale")
    assert seen_call(s, "a", tool)[1] == "one"
    assert seen_call(s, "a", tool)[1] == "two"
    assert seen_call(s, "a", tool) == ("result", "two")


def test_stale_is_the_same_tools_previous_result_and_not_the_last_call_of_the_run() -> None:
    s = session("tool:a#2=stale")
    assert seen_call(s, "a", Tool("a's first answer")) == ("result", "a's first answer")
    assert seen_call(s, "b", Tool("b's answer")) == ("result", "b's answer")
    assert seen_call(s, "a", Tool("a's second answer")) == ("result", "a's first answer")


@pytest.mark.parametrize("value, nothing", [(REAL_TEXT, ""), (MAPPING, {}), (LISTING, [])],
                         ids=["text", "mapping", "list"])
def test_stale_on_the_first_call_of_a_tool_reaches_the_agent_as_empty(value: object, nothing: object) -> None:
    tool = Tool(value)
    s = session("tool:a#1=stale")
    what = seen_call(s, "a", tool)
    assert what == ("result", nothing)
    assert type(what[1]) is type(nothing)
    assert tool.runs == 1
    assert s.calls[0].real_ran is True


def test_stale_on_a_first_call_of_this_tool_is_empty_after_another_tools_calls() -> None:
    """A first call counts among calls of that tool, so `b`'s result is no previous result of `a`."""
    s = session("tool:a#1=stale")
    seen_call(s, "b", Tool("b's answer"))
    assert seen_call(s, "a", Tool("a's answer")) == ("result", "")


def test_stale_hands_back_a_structured_result_as_it_was() -> None:
    tool = Tool(MAPPING, "fresh")
    s = session("tool:a#2=stale")
    seen_call(s, "a", tool)
    assert seen_call(s, "a", tool) == ("result", MAPPING)


# ---------------------------------------------------------------------------
# lost_reply
# ---------------------------------------------------------------------------


def test_lost_reply_reaches_the_agent_as_an_error_after_the_tool_acted() -> None:
    """The case where a retry repeats an action that already happened (§3.2): by the time the agent
    sees the error, the tool's work is done and the record says so."""
    what, tool, s = live("lost_reply", "receipt-number-77")
    assert what[:2] == ("failure", "error")
    assert tool.log == [{"query": "first"}, {"query": "second"}]
    assert s.calls[1].real_ran is True


def test_lost_reply_keeps_the_result_from_the_agent() -> None:
    what, _, _ = live("lost_reply", "receipt-number-77")
    assert "receipt-number-77" not in what[2]


# ---------------------------------------------------------------------------
# planted_instruction
# ---------------------------------------------------------------------------


def test_planted_instruction_reaches_the_agent_as_the_real_result_with_the_runs_marker() -> None:
    word = changes().marker(hunt="refund-agent-1", case="c7")
    what, tool, _ = live("planted_instruction", REAL_TEXT, marker=word)
    assert what[0] == "result"
    assert REAL_TEXT in what[1]
    assert what[1].count(word) == 1
    assert word not in REAL_TEXT
    assert tool.runs == 2


@pytest.mark.parametrize("value", [MAPPING, LISTING], ids=["mapping", "list"])
def test_planted_instruction_writes_a_structured_result_out_for_the_agent(value: object) -> None:
    what, _, _ = live("planted_instruction", value)
    assert isinstance(what[1], str)
    assert any(form in what[1] for form in json_forms(value))
    assert what[1].count("quillfern") == 1


def test_neither_the_marker_nor_the_result_reaches_the_record() -> None:
    """§6.4: nothing in the record is content, and the marker is recovered from `hunt` and `case`,
    not stored."""
    _, _, s = live("planted_instruction", REAL_TEXT)
    written = json.dumps([c.to_dict() for c in s.calls] + [c.to_dict() for c in s.applied])
    assert "quillfern" not in written
    assert REAL_TEXT not in written
    assert EARLIER not in written
