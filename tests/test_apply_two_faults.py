"""Two faults on one call: the first in the condition's order lands, the other leaves that call alone,
and its record says so.

Invariant pinned here (Break — Plan, the applying module):
- BK2.12 Two faults on one call. `parse` accepts `tool:a#1=error + tool:a#1=slow`, and `random`'s pairs can
         draw it. Ruled by Taylor, 2026-11-04: the first in the condition's order lands.

The condition's order is the plain text order of the changes' names (§3.1), so it is the same in every
process and needs no table: `#*` sorts before `#1`, `#1-2` before `#1`, and every schedule before a rate; at
one position, by the fault's name. A new fault changes nothing about a condition that does not name it.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from types import ModuleType
from typing import Any

import pytest

from poisson_break.records import Call
from tests.apply_support import LONG, REPEATABLE, Tool, agents, apply, call, fresh, seen_call, session
from tests.changes_support import changes, one, under_hash_seed
from tests.test_apply_adding_a_fault import own, session_on


def applied(s: Any) -> dict[str, tuple[bool, int | None]]:
    return {x.fault: (x.applied, x.applied_call) for x in s.applied}


@pytest.fixture
def c() -> Iterator[tuple[ModuleType, ModuleType]]:
    yield from fresh()


@pytest.mark.parametrize("text, winner, sees, runs", [
    ("tool:a#1=error + tool:a#1=slow", "error", "failure", 0),
    ("tool:a#1=empty + tool:a#1=error", "empty", ("result", ""), 1),
    ("tool:a#1=cut_off + tool:a#1=empty", "cut_off", ("result", LONG[:200]), 1),
    ("tool:a#1=empty + tool:a#1=slow", "empty", ("result", ""), 1),
    ("tool:a#1=empty + tool:a#1=planted_instruction", "empty", ("result", ""), 1),
    ("tool:a#1=error + tool:a#1=lost_reply", "error", "failure", 0),
    ("tool:a#1=lost_reply + tool:a#1=rate_limited", "lost_reply", "failure", 1),
], ids=["error-slow", "empty-error", "cut_off-empty", "empty-slow", "empty-planted", "error-lost_reply", "lost_reply-rate_limited"])
def test_the_first_in_the_conditions_order_lands_and_the_other_leaves_the_call_alone(
        text: str, winner: str, sees: Any, runs: int) -> None:
    """`empty` beats `error`, so it is the order and not whichever stops the tool. The loser's delay is
    not slept and its sentence not planted: it does nothing to this call."""
    tool = Tool(LONG)
    s = session(text, tools=REPEATABLE, marker="quillfern")
    started = time.monotonic()
    got = seen_call(s, "a", tool)
    assert time.monotonic() - started < 2
    if sees == "failure":
        assert got[0] == "failure"
        assert got[1] == "error"
    else:
        assert got == sees
    assert tool.runs == runs
    assert s.calls == (Call(tool="a", call=1, change=f"tool:a#1={winner}", real_ran=bool(runs)),)
    loser = next(x.fault for x in s.applied if x.fault != winner)
    assert applied(s) == {winner: (True, 1), loser: (False, None)}


def test_the_order_written_makes_no_difference() -> None:
    def run(text: str) -> tuple:
        tool = Tool(LONG)
        s = session(text, tools=REPEATABLE)
        return seen_call(s, "a", tool), s.calls, s.applied, tool.runs
    assert run("tool:a#1=error + tool:a#1=empty") == run("tool:a#1=empty + tool:a#1=error")


@pytest.mark.parametrize("text, calls, changes_landed, record", [
    ("tool:a#*=empty + tool:a#1=error", 2, ["tool:a#*=empty", "tool:a#*=empty"], {"empty": (True, 1), "error": (False, None)}),
    ("tool:a#1=error + tool:a~1=empty", 2, ["tool:a#1=error", "tool:a~1=empty"], {"error": (True, 1), "empty": (True, 2)}),
    ("tool:a#1=empty + tool:a#1-2=error", 2, ["tool:a#1-2=error", "tool:a#1-2=error"], {"error": (True, 1), "empty": (False, None)}),
    ("tool:a#10-12=error + tool:a#2-11=empty", 12,
     [None, "tool:a#2-11=empty"] + ["tool:a#2-11=empty"] * 7 + ["tool:a#10-12=error"] * 3,
     {"empty": (True, 2), "error": (True, 10)}),
], ids=["every-call-sorts-before-a-number", "a-schedule-sorts-before-a-rate", "a-range-sorts-before-its-first-call", "text-and-not-number"])
def test_the_order_is_the_plain_text_order_of_the_names(text: str, calls: int, changes_landed: list, record: dict) -> None:
    """Not the most specific, not the smallest number: `#10-12` sorts before `#2-11`. The canonical name
    of §3.1 is the one order every process agrees on."""
    s = session(text)
    for _ in range(calls):
        seen_call(s, "a", Tool("answer"))
    assert [x.change for x in s.calls] == changes_landed
    assert applied(s) == record


def test_the_loser_lands_on_a_call_where_it_is_alone_and_says_that_one() -> None:
    """Its `applied_call` is where it landed, and the first call it could have landed on is not that."""
    s = session("tool:a#1-2=empty + tool:a#2-3=error")
    assert [seen_call(s, "a", Tool("answer"))[0:2] for _ in range(2)] == [("result", ""), ("result", "")]
    assert seen_call(s, "a", Tool("answer"))[0] == "failure"
    assert s.calls[2].change == "tool:a#2-3=error"
    assert applied(s) == {"empty": (True, 1), "error": (True, 3)}


@pytest.mark.parametrize("seed", range(6))
def test_two_faults_at_one_rate_always_meet_and_the_first_always_lands(seed: int) -> None:
    """The fault is not in the draw's key (§3.1), so they fire together on every call one fires at all."""
    text = "tool:a~0.5=empty + tool:a~0.5=error"
    s = session(text, seed=seed)
    got = [seen_call(s, "a", Tool("answer")) for _ in range(10)]
    fires = [changes().applies(one("tool:a~0.5=empty"), seed=seed, tool="a", call=n) for n in range(1, 11)]
    assert got == [("result", "") if f else ("result", "answer") for f in fires]
    assert s.applied[1].applied is False


def test_the_loser_is_not_run_at_all(c: Any) -> None:
    """Its work is not done and thrown away: `apply` is not called, so a loser that would break its word
    on the real tool, or raise, does neither."""
    ran: list[str] = []

    def loser(self: Any, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
        ran.append("loser")
        raise ZeroDivisionError("never reached")

    own(c[0], loser, name="zzz_last")
    tool = Tool("answer")
    s = session_on(c, "tool:a#1=empty + tool:a#1=zzz_last")
    assert seen_call(s, "a", tool) == ("result", "")
    assert ran == []
    assert tool.runs == 1
    assert s.stopped is None


def test_a_fault_from_outside_takes_its_place_in_the_same_order(c: Any) -> None:
    """Nothing tells it from a launch fault: its name decides, and it can come first or last."""
    def first(self: Any, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
        return c[0].Result(value=str(real()).upper())

    own(c[0], first, name="aaa_first")
    s = session_on(c, "tool:a#1=aaa_first + tool:a#1=error")
    assert seen_call(s, "a", Tool("answer")) == ("result", "ANSWER")
    assert [x.fault for x in s.applied if x.applied] == ["aaa_first"]


def test_a_loser_is_still_judged_by_the_tools_class() -> None:
    """Whether it would have landed is not known before the run, so the refusal does not wait to see:
    `lost_reply` on a read tool is refused, here as alone."""
    with pytest.raises(apply().ToolRefused) as refusal:
        session("tool:a#1=error + tool:a#1=lost_reply", tools={"a": "read"})
    assert refusal.value.change == "tool:a#1=lost_reply"


def test_a_lost_reply_that_lost_is_no_lost_reply() -> None:
    """`duplicate_write` asks for a `lost_reply` applied (BK3.4), so the record has to say it was not."""
    tool = Tool("receipt")
    s = session("tool:a#1=empty + tool:a#1=lost_reply", tools=REPEATABLE)
    assert seen_call(s, "a", tool) == ("result", "")
    assert applied(s)["lost_reply"] == (False, None)


def test_the_tools_own_exception_passes_and_only_the_winner_is_on_the_record() -> None:
    wrong = LookupError("no")
    s = session("tool:a#1=empty + tool:a#1=error")
    with pytest.raises(LookupError) as raised:
        call(s, "a", Tool(raises=wrong))
    assert raised.value is wrong
    assert applied(s) == {"empty": (True, 1), "error": (False, None)}


@pytest.mark.parametrize("text", ["tool:a#1=error + tool:b#1=empty", "input:typos + tool:a#1=error"], ids=["two-tools", "another-surface"])
def test_changes_on_different_things_do_not_meet(text: str) -> None:
    """The control to all of the above: only two faults on one call of one tool are the case."""
    s = session(text)
    assert seen_call(s, "a", Tool("answer"))[0] == "failure"
    assert s.calls[0].change == "tool:a#1=error"
    if "tool:b" in text:
        assert seen_call(s, "b", Tool("answer")) == ("result", "")
        assert all(x.applied for x in s.applied)


def test_a_scripted_agent_sees_only_the_winner_through_wrap_and_the_way_in() -> None:
    text = "tool:lookup_order#1=empty + tool:lookup_order#1=error"
    tools = {"lookup_order": Tool("answer"), "check_policy": Tool("policy")}
    s = session(text)
    agent = agents().WayIn(tools)
    agent.run({"id": "c1", "input": "hello"}, s, seed=1, limits=None)
    assert agent.seen[0].result == "" and agent.seen[0].error is None

    tool = Tool("answer")
    wrapped = apply().wrap("lookup_order", tool)
    s = session(text)
    with s:
        assert wrapped(query="x") == ""
    assert s.calls[0].change == "tool:lookup_order#1=empty"


def test_it_replays_in_every_process() -> None:
    """Chosen by a set, a built-in hash or a draw, it would land differently from run to run."""
    code = (
        "import json\n"
        "from poisson_break.apply import Session\n"
        "from poisson_break.changes import parse\n"
        "out = {}\n"
        "for text in ('tool:a#1=empty + tool:a#1=error', 'tool:a#1=cut_off + tool:a#1=empty + tool:a#1=slow + tool:a#1=stale',\n"
        "             'tool:a~0.5=empty + tool:a~0.5=error + tool:a~0.5=timeout'):\n"
        "    for seed in range(12):\n"
        "        s = Session(parse(text), seed=seed, tools={'a': 'read'})\n"
        "        for _ in range(3):\n"
        "            try:\n"
        "                s.call('a', {}, lambda: 'answer')\n"
        "            except Exception:\n"
        "                pass\n"
        "        out[f'{text}/{seed}'] = [c.change for c in s.calls]\n"
        "print(json.dumps(out, sort_keys=True))\n"
    )
    first = json.loads(under_hash_seed(code, 1))
    assert first == json.loads(under_hash_seed(code, 2))
    assert all(change in (None, "tool:a#1=empty", "tool:a#1=cut_off", "tool:a~0.5=empty")
               for changes_seen in first.values() for change in changes_seen)
