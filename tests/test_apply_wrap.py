"""`wrap(tool_name, fn)`: the one function call a `rollout` target adds per tool (spec §7.1, plan
yes/no 1), and how a wrapped tool finds its run.

Invariants pinned here (Break — Plan, the applying module):
- BK2.1 to BK2.4 hold through `wrap` as they do through `Session.call`.
- BK2.2 through `wrap`: a target with its tools wrapped runs the same under the control, and the same
  with no Break at all, so a user can leave the wrapping in.

How a wrapped tool finds its session is ruling 11; what happens to a tool that is `async def` is
ruling 12. How the agent's arguments reach a stand-in is ruling 4.
"""

from __future__ import annotations

import inspect
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from types import ModuleType
from typing import Any

import pytest

from tests.apply_support import REPEATABLE, Tool, apply, seen, session, stand_in_module
from tests.test_apply_adding_a_fault import watching
from tests.test_apply_tool_classes import STAND_IN


@pytest.fixture
def stand_in() -> Iterator[ModuleType]:
    yield from stand_in_module()


@pytest.fixture
def with_a_watching_fault() -> Iterator[tuple[ModuleType, ModuleType, list[Any]]]:
    yield from watching()


def lookup(order: int, carrier: str = "usual") -> dict[str, Any]:
    """Look up an order."""
    return {"order": order, "carrier": carrier}


def test_a_wrapped_tool_with_no_run_open_is_the_tool() -> None:
    """Ruling 11. A target's tools are wrapped where it defines them, which may be at import, and the
    target is still an ordinary program when Break is not running it."""
    tool = Tool("answer")
    assert apply().wrap("a", tool)(query="x") == "answer"
    assert tool.log == [{"query": "x"}]


def test_a_wrapped_tool_runs_inside_the_session_that_is_open() -> None:
    wrapped = apply().wrap("a", Tool("answer"))
    s = session("tool:a#2=empty")
    with s:
        assert wrapped(query="x") == "answer"
        assert wrapped(query="y") == ""
    assert [c.change for c in s.calls] == [None, "tool:a#2=empty"]


def test_the_session_closes_with_its_block() -> None:
    tool = Tool("answer")
    wrapped = apply().wrap("a", tool)
    s = session("tool:a#*=empty")
    with s:
        assert wrapped() == ""
    assert wrapped() == "answer"
    assert len(s.calls) == 1


def test_the_session_closes_when_its_block_ends_in_an_exception() -> None:
    tool = Tool("answer")
    wrapped = apply().wrap("a", tool)
    s = session("tool:a#*=empty")
    with pytest.raises(ValueError), s:
        raise ValueError("the agent crashed")
    assert wrapped() == "answer"
    assert s.calls == ()


def test_a_second_run_gets_its_own_numbers() -> None:
    wrapped = apply().wrap("a", Tool("answer"))
    for _ in range(2):
        s = session("tool:a#1=empty")
        with s:
            assert wrapped() == ""
        assert s.calls[0].call == 1


def test_a_wrapped_tool_has_the_tools_name_and_signature() -> None:
    """A framework reads a tool's parameters from its signature and its description from its docstring,
    so a wrapper that hid them would change what the model is told and so what the agent does."""
    wrapped = apply().wrap("lookup", lookup)
    assert wrapped.__name__ == "lookup"
    assert wrapped.__doc__ == lookup.__doc__
    assert inspect.signature(wrapped) == inspect.signature(lookup)


def test_the_way_the_agent_called_it_reaches_the_tool_unchanged() -> None:
    s = session("", tools={"lookup": "read"})
    with s:
        assert apply().wrap("lookup", lookup)(7, carrier="fast") == {"order": 7, "carrier": "fast"}
        assert apply().wrap("lookup", lookup)(8) == {"order": 8, "carrier": "usual"}


def test_a_tool_with_arguments_that_cannot_be_named_is_called_as_the_agent_called_it() -> None:
    """Positional-only and variable arguments: a wrapper that called the tool back with what it had
    named, rather than with what it was given, would fail here where the bare tool does not."""
    def gather(order: int, /, *rest: str, carrier: str = "usual", **more: str) -> tuple:
        return order, rest, carrier, more

    s = session("", tools={"gather": "read"})
    with s:
        wrapped = apply().wrap("gather", gather)
        assert wrapped(7, "x", "y", carrier="fast", note="n") == gather(7, "x", "y", carrier="fast", note="n")
    assert s.stopped is None
    assert s.calls[0].real_ran is True


def test_positional_arguments_reach_a_fault_by_their_names(with_a_watching_fault: Any) -> None:
    """Ruling 11. `CallContext.args` is a mapping, `duplicate_write` compares arguments, and `f(7)` and
    `f(order=7)` are the same call."""
    c, a, watched = with_a_watching_fault
    s = a.Session(c.parse("tool:lookup#*=watch"), seed=1, tools={"lookup": "read"})
    with s:
        wrapped = a.wrap("lookup", lookup)
        wrapped(7, carrier="fast")
        wrapped(order=7, carrier="fast")
    assert dict(watched[0].args) == {"order": 7, "carrier": "fast"}
    assert dict(watched[1].args) == dict(watched[0].args)


def test_a_call_the_agent_got_wrong_fails_as_it_does_on_the_tool_itself() -> None:
    """The agent's own mistake: the `TypeError` Python gives it, and no instrument error."""
    s = session("", tools={"lookup": "read"})
    with s, pytest.raises(TypeError):
        apply().wrap("lookup", lookup)(7, 8, 9)
    assert s.stopped is None


@pytest.mark.parametrize("fault, kind", [("error", "error"), ("timeout", "timeout"), ("rate_limited", "rate_limited"),
                                         ("lost_reply", "error")])
def test_a_tool_failure_reaches_the_agents_code_as_it_would_through_a_call(fault: str, kind: str) -> None:
    tool = Tool()
    s = session(f"tool:a#1={fault}", tools=REPEATABLE)
    with s:
        what = seen(apply().wrap("a", tool))
    assert what[:2] == ("failure", kind)


def test_a_wrapped_tools_own_exception_is_the_tools_own() -> None:
    wrong = LookupError("no")
    s = session("")
    with s, pytest.raises(LookupError) as raised:
        apply().wrap("a", Tool(raises=wrong))()
    assert raised.value is wrong


def test_a_stand_in_replaces_a_wrapped_tool_and_takes_the_arguments_by_name(stand_in: Any) -> None:
    """BK2.6 through `wrap`, positional arguments and all."""
    real_ran: list[int] = []

    def lookup_for_real(order: int, carrier: str = "usual") -> str:
        real_ran.append(order)
        return "the real answer"

    s = session("", tools={"lookup": {"class": "write", "stand_in": STAND_IN}})
    with s:
        assert apply().wrap("lookup", lookup_for_real)(7, carrier="fast") == stand_in.ANSWER
    assert real_ran == []
    assert stand_in.LOG == [{"order": 7, "carrier": "fast"}]


# ---------------------------------------------------------------------------
# which session a wrapped tool reaches
# ---------------------------------------------------------------------------


def test_two_runs_on_two_threads_keep_their_own_calls() -> None:
    """A way in may run a run on a thread of its own, to hold its wall-clock limit. One session kept in
    a plain global would take the other's calls."""
    wrapped = apply().wrap("a", Tool("answer"))
    ready = threading.Barrier(2)

    def run(text: str, out: list[Any]) -> None:
        s = session(text)
        with s:
            ready.wait(timeout=5)
            out.extend(wrapped() for _ in range(4))
            ready.wait(timeout=5)
        out.append(s.calls)

    one: list[Any] = []
    other: list[Any] = []
    threads = [threading.Thread(target=run, args=("tool:a#*=empty", one)),
               threading.Thread(target=run, args=("", other))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert one[:4] == [""] * 4
    assert other[:4] == ["answer"] * 4
    assert [c.call for c in one[4]] == [1, 2, 3, 4]
    assert [c.call for c in other[4]] == [1, 2, 3, 4]


def test_a_call_from_a_thread_the_agent_started_reaches_its_run() -> None:
    """Ruling 11. An agent that calls tools in parallel starts threads of its own, and a call there that
    missed its session would run the real tool with no fault and no record: the hunt would report a
    condition as not failing when it was never applied."""
    tool = Tool("answer")
    wrapped = apply().wrap("a", tool)
    s = session("tool:a#*=empty")
    with s, ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: wrapped(), range(6)))
    assert results == [""] * 6
    assert sorted(c.call for c in s.calls) == [1, 2, 3, 4, 5, 6]
    assert s.stopped is None


def test_a_call_that_cannot_be_told_from_two_open_runs_is_an_instrument_error() -> None:
    """Ruling 11, and §11.2 invariant 2: a call that may have bypassed its session is reported, not
    run. This takes two runs open at once and a thread neither of them started."""
    tool = Tool("answer")
    wrapped = apply().wrap("stray_tool", tool)
    opened = threading.Event()
    finish = threading.Event()

    def other_run() -> None:
        with session(""):
            opened.set()
            finish.wait(timeout=10)

    other = threading.Thread(target=other_run)
    other.start()
    opened.wait(timeout=10)
    try:
        s = session("")
        with s:
            caught: list[BaseException] = []

            def stray() -> None:
                try:
                    wrapped()
                except BaseException as wrong:  # noqa: B036
                    caught.append(wrong)

            thread = threading.Thread(target=stray)
            thread.start()
            thread.join()
    finally:
        finish.set()
        other.join()
    assert tool.runs == 0
    assert len(caught) == 1
    assert isinstance(caught[0], apply().InstrumentError)
    assert "stray_tool" in str(caught[0])


def test_parallel_calls_number_every_call_once() -> None:
    """The count taken and the number given are one step. Only the numbers are held here: which of two
    parallel calls gets which is the agent's own race, and such an agent does not replay."""
    s = session("")
    with s, ThreadPoolExecutor(max_workers=8) as pool:
        wrapped = apply().wrap("a", lambda: "answer")
        list(pool.map(lambda _: wrapped(), range(200)))
    assert sorted(c.call for c in s.calls) == list(range(1, 201))


# ---------------------------------------------------------------------------
# a tool that is async def (ruling 12)
# ---------------------------------------------------------------------------


async def async_lookup(order: int) -> str:
    return "answer"


def test_wrapping_an_async_tool_is_refused_naming_it() -> None:
    """Every fault that reads a result would read a coroutine instead: `empty` would hand back nothing,
    `cut_off` would write out its repr, and the tool would never run. Silently wrong, so refused."""
    with pytest.raises(apply().ToolRefused) as refusal:
        apply().wrap("async_lookup", async_lookup)
    assert refusal.value.tool == "async_lookup"


def test_a_real_that_hands_back_something_to_await_is_an_instrument_error() -> None:
    """The same mistake through `Session.call`, where a way in passes its own `real`."""
    s = session("tool:a#1=empty")
    coroutine = async_lookup(7)
    try:
        with pytest.raises(apply().InstrumentError):
            s.call("a", {"order": 7}, lambda: coroutine)
    finally:
        coroutine.close()
    assert s.stopped is not None


def test_a_real_that_hands_back_something_to_await_is_refused_under_the_control_too() -> None:
    s = session("")
    coroutine = async_lookup(7)
    try:
        with pytest.raises(apply().InstrumentError):
            s.call("a", {"order": 7}, lambda: coroutine)
    finally:
        coroutine.close()


def test_a_sync_tool_passed_by_a_callable_object_is_taken() -> None:
    """The control to the refusal above: only an `async def` is refused."""
    s = session("")
    with s:
        assert apply().wrap("a", Tool("answer"))() == "answer"
