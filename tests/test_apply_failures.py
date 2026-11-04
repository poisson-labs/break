"""When something other than the tool goes wrong, and when time runs out.

Invariants pinned here (Break — Plan, the applying module):
- BK2.7  Break's own failure is an instrument error. An exception inside Break's applier, inside a
         fault's `apply` or inside a stand-in surfaces as `InstrumentError`, never as a tool fault the
         agent sees, and never as an agent failure.
- BK2.8  `slow` is bounded: the applier sleeps the delay `Result.delay` states and never past it, and a
         run's wall-clock limit still applies.

And what the catalogue's ruling 18 left this module: the real tool's own exception passes to the agent
untouched, and a stand-in's failure is an instrument error.

That a run once stopped stays stopped, however the agent reacts, is ruling 9. The limit's name and what
it raises are ruling 10.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from types import ModuleType
from typing import Any

import pytest

from poisson_break.changes import Change, Condition
from tests.apply_support import Tool, agents, apply, call, fresh, plain_tools, seen_call, session, stand_in_module, wrap_all
from tests.test_apply_tool_classes import BROKEN_STAND_IN, INTERRUPTED_STAND_IN


@pytest.fixture
def c() -> Iterator[tuple[ModuleType, ModuleType]]:
    yield from fresh()


@pytest.fixture
def stand_in() -> Iterator[ModuleType]:
    yield from stand_in_module()


def outside(c_module: ModuleType, apply_fn: Any, *, name: str = "own", real_runs: bool = True) -> Any:
    """A fault written outside the core, registered on a catalogue of its own."""
    fault = type("Own", (), {"name": name, "surface": "tool", "description": "a fault of its author's",
                             "parameters": {}, "real_runs": real_runs, "apply": apply_fn})()
    c_module.register(fault)
    return fault


def own_session(pair: tuple[ModuleType, ModuleType], text: str = "tool:a#1=own", **over: Any) -> Any:
    c_module, a = pair
    over.setdefault("seed", 1)
    over.setdefault("tools", {"a": "read", "b": "read"})
    return a.Session(c_module.parse(text), **over)


def raising_fault(self: Any, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
    real()
    raise ZeroDivisionError("the fault's own mistake")


# ---------------------------------------------------------------------------
# BK2.7  a fault's mistake
# ---------------------------------------------------------------------------


def test_a_faults_exception_is_an_instrument_error(c: Any) -> None:
    outside(c[0], raising_fault)
    with pytest.raises(c[1].InstrumentError):
        call(own_session(c), "a", Tool())


@pytest.mark.parametrize("outcome", ["just a string", None, 7, ("a", "pair")], ids=["text", "none", "number", "pair"])
def test_an_outcome_of_the_wrong_shape_is_an_instrument_error(c: Any, outcome: Any) -> None:
    def apply_fn(self: Any, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
        real()
        return outcome
    outside(c[0], apply_fn)
    with pytest.raises(c[1].InstrumentError):
        call(own_session(c), "a", Tool())


@pytest.mark.parametrize("calls, declared", [(0, True), (2, True), (1, False)])
def test_a_fault_that_breaks_its_word_on_the_real_tool_is_an_instrument_error(c: Any, calls: int, declared: bool) -> None:
    """Through the applier the count still holds: a session that called `apply` itself, around the
    core's count, would let this through as a result."""
    def apply_fn(self: Any, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
        for _ in range(calls):
            real()
        return c[0].Result(value="anything")
    outside(c[0], apply_fn, real_runs=declared)
    with pytest.raises(c[1].InstrumentError):
        call(own_session(c), "a", Tool())


def test_a_faults_mistake_is_not_a_failure_the_agent_is_shown(c: Any) -> None:
    """Never a tool fault the agent sees: not a `ToolFailure` by another path."""
    outside(c[0], raising_fault)
    with pytest.raises(c[1].InstrumentError) as raised:
        call(own_session(c), "a", Tool())
    assert not isinstance(raised.value, c[1].ToolFailure)


def test_a_faults_mistake_after_the_tool_ran_is_on_the_record_as_having_run(c: Any) -> None:
    """BK2.4: every call. The real tool did act, and a write that happened is a write that happened."""
    outside(c[0], raising_fault)
    s = own_session(c)
    with pytest.raises(c[1].InstrumentError):
        call(s, "a", Tool())
    assert [(x.tool, x.call, x.change, x.real_ran) for x in s.calls] == [("a", 1, "tool:a#1=own", True)]


def test_planted_instruction_given_no_marker_is_an_instrument_error() -> None:
    """The word is the core's to give, and a session with none cannot plant one."""
    with pytest.raises(apply().InstrumentError):
        call(session("tool:a#1=planted_instruction"), "a", Tool())


# ---------------------------------------------------------------------------
# BK2.7  the applier's own mistake
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("args", ["not a mapping", 7, None, ["a", "list"]], ids=["text", "number", "none", "list"])
def test_a_call_the_way_in_got_wrong_is_an_instrument_error(args: Any) -> None:
    """A way in's mistake is Break's side of the line. A bare `TypeError` here would reach the agent
    as if its tool had raised it, and `crashed` would be recorded against the agent."""
    tool = Tool()
    with pytest.raises(apply().InstrumentError):
        session("").call("a", args, tool)
    assert tool.runs == 0


@pytest.mark.parametrize("change", [
    Change(surface="tool", tool="a", fault="no_such_fault", call="#1"),
    Change(surface="tool", tool="a", fault="error", call="#not-a-number"),
    Change(surface="tool", tool="a", fault="error", call="~not-a-rate"),
], ids=["unknown-fault", "bad-call", "bad-rate"])
def test_a_condition_the_catalogue_could_not_have_written_is_an_instrument_error(change: Change) -> None:
    """`parse` cannot make these, so only a mistake inside Break can. It may be caught when the session
    is made or on the call, and it may not come out as a `KeyError` or a `ValueError`."""
    tool = Tool()
    with pytest.raises(apply().InstrumentError):
        s = apply().Session(Condition(changes=(change,)), seed=1, tools={"a": "read"})
        s.call("a", {}, tool)
    assert tool.runs == 0


# ---------------------------------------------------------------------------
# BK2.7  a stand-in's failure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "tool:w#1=empty", "tool:w#1=lost_reply"], ids=["control", "empty", "lost-reply"])
def test_a_stand_ins_exception_is_an_instrument_error(stand_in: Any, text: str) -> None:
    """§3.2 and §4: the real tool's exception is what tools do, and a stand-in's is the user's
    instrument going wrong, in the control as under a fault."""
    s = session(text, tools={"w": {"class": "write", "stand_in": BROKEN_STAND_IN}})
    with pytest.raises(apply().InstrumentError) as raised:
        call(s, "w", Tool(), order=7)
    assert raised.value is not stand_in.WRONG
    assert len(stand_in.LOG) == 1
    assert s.stopped is raised.value


def test_a_stand_in_interrupted_by_the_user_is_an_interruption(stand_in: Any) -> None:
    """Ctrl-C has to end the hunt (BK5.11), not be counted as an instrument error."""
    s = session("", tools={"w": {"class": "write", "stand_in": INTERRUPTED_STAND_IN}})
    with pytest.raises(KeyboardInterrupt) as raised:
        call(s, "w", Tool())
    assert raised.value is stand_in.INTERRUPT


# ---------------------------------------------------------------------------
# the real tool's own exception
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fault", ["empty", "cut_off", "malformed", "stale", "lost_reply", "planted_instruction"])
def test_the_real_tools_own_exception_reaches_the_agent_untouched_under_a_fault(fault: str) -> None:
    """§3.2: with no fault's work done on top. It is what tools do, so it is no instrument error."""
    wrong = LookupError("no such order")
    s = session(f"tool:a#1={fault}", tools={"a": {"class": "write", "repeatable": True}}, marker="quillfern")
    with pytest.raises(LookupError) as raised:
        call(s, "a", Tool(raises=wrong))
    assert raised.value is wrong
    assert s.stopped is None


def test_the_real_tools_own_exception_under_slow_comes_with_no_delay() -> None:
    """No fault's work on top: its delay is part of its work. A tool that failed does not then wait."""
    wrong = LookupError("no such order")
    started = time.monotonic()
    with pytest.raises(LookupError):
        call(session("tool:a#1=slow"), "a", Tool(raises=wrong))
    assert time.monotonic() - started < 2


@pytest.mark.parametrize("wrong", [KeyboardInterrupt(), SystemExit(3)], ids=["interrupt", "exit"])
@pytest.mark.parametrize("text", ["", "tool:a#1=empty"], ids=["control", "fault"])
def test_an_interruption_in_the_real_tool_is_an_interruption(wrong: BaseException, text: str) -> None:
    """Not an `Exception`, and not Break's to catch. An applier with a bare `except` would turn the
    user's Ctrl-C into something a hunt counts."""
    s = session(text)
    with pytest.raises(type(wrong)) as raised:
        call(s, "a", Tool(raises=wrong))
    assert raised.value is wrong


# ---------------------------------------------------------------------------
# what `stopped` holds (ruling 9)
# ---------------------------------------------------------------------------


def test_a_healthy_run_is_not_stopped_whatever_the_tools_did() -> None:
    """A tool failure the agent sees and a tool's own exception are the run's business, not a stop."""
    s = session("tool:a#1=error")
    assert seen_call(s, "a", Tool())[0] == "failure"
    with pytest.raises(LookupError):
        call(s, "a", Tool(raises=LookupError("no")))
    assert s.stopped is None


def test_a_failure_the_agent_itself_raises_is_the_agents_and_is_not_held_against_the_run() -> None:
    """Never an agent failure, and the other way about: an agent's crash is `crashed`, and it does not
    become Break's. It passes out of the session as itself."""
    s = session("")
    wrong = ValueError("the agent's own mistake")
    with pytest.raises(ValueError) as raised:
        with s:
            raise wrong
    assert raised.value is wrong
    assert s.stopped is None


def test_an_agent_that_catches_everything_cannot_hide_an_instrument_error(c: Any) -> None:
    """The agent that retries catches every `Exception`, as real agents do, and would otherwise read
    Break's failure as a tool failure and go on to finish a run that would then be counted."""
    outside(c[0], raising_fault, name="own")
    tool = Tool("answer")
    s = own_session(c, "tool:lookup_order#1=own", tools={"lookup_order": "read"})
    with s:
        run = agents().retries({"id": "c1", "input": "hello"}, {"lookup_order": c[1].wrap("lookup_order", tool)})
    assert isinstance(s.stopped, c[1].InstrumentError)
    assert tool.runs == 1, "the first call ran the tool, and the stopped run runs it no more"
    assert len(run.seen) > 1, "the agent did try again"
    assert len(s.calls) == 1


def test_once_stopped_every_call_raises_the_same_error_and_runs_nothing(c: Any) -> None:
    outside(c[0], raising_fault)
    s = own_session(c)
    with pytest.raises(c[1].InstrumentError) as first:
        call(s, "a", Tool())
    tool = Tool()
    for name in ("a", "b"):
        with pytest.raises(c[1].InstrumentError) as again:
            call(s, name, tool)
        assert again.value is first.value
    assert tool.runs == 0
    assert s.stopped is first.value


# ---------------------------------------------------------------------------
# BK2.8  the applier does the sleeping, and only as long as it is told
# ---------------------------------------------------------------------------


def delaying(c_module: ModuleType, delay: float, value: Any = "answer") -> None:
    def apply_fn(self: Any, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
        real()
        return c_module.Result(value=value, delay=delay)
    outside(c_module, apply_fn)


def test_the_applier_sleeps_the_delay_a_result_states(c: Any) -> None:
    delaying(c[0], 2.0)
    s = own_session(c)
    started = time.monotonic()
    assert call(s, "a", Tool()) == "answer"
    took = time.monotonic() - started
    assert 1.98 <= took < 3.5, took


def test_a_result_with_no_delay_is_handed_over_at_once(c: Any) -> None:
    delaying(c[0], 0)
    started = time.monotonic()
    call(own_session(c), "a", Tool())
    assert time.monotonic() - started < 0.5


def test_the_tool_has_run_before_the_wait_and_is_recorded_during_it(c: Any) -> None:
    """A run stopped during the sleep has to have the call on its record: the tool did act."""
    delaying(c[0], 2.0)
    s = own_session(c)
    seen_during: list[Any] = []
    tool = Tool()

    def looker() -> None:
        stop = time.monotonic() + 1.5
        while tool.runs == 0 and time.monotonic() < stop:
            time.sleep(0.01)
        time.sleep(0.2)
        seen_during.extend(s.calls)

    thread = threading.Thread(target=looker)
    thread.start()
    call(s, "a", tool)
    thread.join()
    assert tool.runs == 1
    assert len(seen_during) == 1
    assert seen_during[0].real_ran is True


def test_a_wait_in_one_run_does_not_hold_up_another(c: Any) -> None:
    """A lock kept across the sleep, or one sleep shared between sessions, shows here. A way in may run
    a run on a thread of its own."""
    delaying(c[0], 2.0)
    got: list[Any] = []
    started = time.monotonic()
    threads = [threading.Thread(target=lambda: got.append(call(own_session(c), "a", Tool()))) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert time.monotonic() - started < 4.5
    assert got == ["answer"] * 3


# ---------------------------------------------------------------------------
# BK2.8  the wall-clock limit still applies
# ---------------------------------------------------------------------------


def test_the_limit_cuts_the_sleep_short() -> None:
    """The launch `slow`, asking for its 5 s, under a limit of one second: the agent is not kept past
    the limit, and the wait stops where the limit is."""
    s = session("tool:a#1=slow", run_seconds=1.0)
    tool = Tool()
    started = time.monotonic()
    with pytest.raises(apply().RunOutOfTime) as raised:
        call(s, "a", tool)
    took = time.monotonic() - started
    assert 0.5 <= took < 3, took
    assert tool.runs == 1
    assert s.stopped is raised.value
    assert s.calls[0].real_ran is True
    assert s.calls[0].change == "tool:a#1=slow"
    assert s.applied[0].applied_call == 1


def test_a_delay_inside_the_limit_is_slept_in_full(c: Any) -> None:
    delaying(c[0], 0.5)
    s = own_session(c, run_seconds=30)
    started = time.monotonic()
    assert call(s, "a", Tool()) == "answer"
    assert time.monotonic() - started >= 0.49
    assert s.stopped is None


def test_a_call_after_the_limit_runs_nothing() -> None:
    s = session("", run_seconds=1.0)
    call(s, "a", Tool())
    time.sleep(1.1)
    tool = Tool()
    with pytest.raises(apply().RunOutOfTime):
        call(s, "a", tool)
    assert tool.runs == 0


def test_an_agent_that_catches_every_exception_does_not_catch_the_limit() -> None:
    """Ruling 10. `hung` is what the record will say, and an agent whose `except Exception` swallowed
    the limit would keep running for as long as it liked, past a limit whose job is to stop it."""
    s = session("tool:a#1=slow", run_seconds=0.2)
    swallowed = False
    with pytest.raises(apply().RunOutOfTime):
        try:
            call(s, "a", Tool())
        except Exception:
            swallowed = True
    assert not swallowed


def test_the_scripted_agent_that_retries_does_not_retry_past_the_limit() -> None:
    """The same, from the agent's side: this one catches every failure and goes again."""
    s = session("tool:lookup_order#*=slow", run_seconds=1.0)
    tools = plain_tools()
    with s, pytest.raises(apply().RunOutOfTime):
        agents().retries({"id": "c1", "input": "hello"}, wrap_all(tools))
    assert tools["lookup_order"].runs == 1


def test_once_past_the_limit_every_call_raises_the_same_and_runs_nothing() -> None:
    s = session("tool:a#1=slow", run_seconds=0.2)
    with pytest.raises(apply().RunOutOfTime) as first:
        call(s, "a", Tool())
    tool = Tool()
    with pytest.raises(apply().RunOutOfTime) as again:
        call(s, "b", tool)
    assert again.value is first.value
    assert tool.runs == 0
