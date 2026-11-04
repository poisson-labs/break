"""One run's applier: what it leaves alone, what it touches, what it writes down, and that it replays.

Invariants pinned here (Break — Plan, the applying module):
- BK2.2  The control changes nothing. Under the empty condition, a run's tool results and order are
         identical to a run without Break.
- BK2.3  Only the named call is touched. A change on `tool:a#2` leaves every other call of the run as
         the control's.
- BK2.4  Every call leaves a record: the tool, the call number, the change applied or none, whether it
         applied and on which call, and whether the real tool ran.
- BK2.9  Replay. Two runs of a scripted agent with the same case, condition and seed produce identical
         records.
- BK2.13, the context half: `previous` and `marker` are filled in. Which "previous" a call gets once an
         earlier call was faulted is an open point, brought to Taylor, and no test here rests on it:
         every earlier call in these tests is clean, so what the tool returned and what the agent saw
         are the same thing.

The shape of the two records is ruling 2. `Session(...)` is ruling 1. A snapshot of the previous result
is ruling 14.
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
import time
from collections.abc import Iterator
from types import ModuleType
from typing import Any

import pytest

from poisson_break.interfaces import Capabilities
from poisson_break.records import Applied, Call, Condition, Failure, RunRecord, Selection, Signals
from tests.apply_support import (
    ALL_CAPABILITIES,
    CASE,
    EARLIER,
    LONG,
    REPEATABLE,
    SEED,
    Tool,
    agents,
    apply,
    call,
    plain_tools,
    records,
    run_plain_agent,
    seen_call,
    session,
)
from tests.changes_support import REAL_TEXT, TOOL_FAULTS, changes, one
from tests.conftest import REPO, guarded_env
from tests.test_apply_adding_a_fault import watching

QUICK = [f for f in TOOL_FAULTS if f != "slow"]
PLAIN = ("retries", "gives_up", "follows_plant", "repeats_write")


# ---------------------------------------------------------------------------
# the public names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["Session", "wrap", "Applied", "InstrumentError", "ToolFailure", "ToolRefused",
                                  "RunOutOfTime", "ToolInfo", "RunResult"])
def test_the_public_names_are_declared(name: str) -> None:
    assert name in apply().__all__
    assert hasattr(apply(), name)


def test_the_re_exported_names_are_the_same_objects() -> None:
    """A second `InstrumentError` here would not be caught by whoever catches the catalogue's, and a
    second `Applied` would not fit a `RunRecord`."""
    assert apply().InstrumentError is changes().InstrumentError
    assert apply().Applied is records().Applied


def test_the_three_ways_a_run_stops_cannot_be_taken_for_each_other_or_for_a_tool_failure() -> None:
    """Rulings 3, 5, 9 and 10. A tool failure is what the hunt measures. A refusal stops the hunt, an
    instrument error is not counted, and running out of time is `hung`: four different things to
    whatever reads them."""
    a = apply()
    kinds = [a.ToolFailure, a.ToolRefused, a.InstrumentError, a.RunOutOfTime]
    for one_kind in kinds:
        for other in kinds:
            if one_kind is not other:
                assert not issubclass(one_kind, other), (one_kind, other)


# ---------------------------------------------------------------------------
# BK2.2  the control changes nothing
# ---------------------------------------------------------------------------


def test_under_the_control_the_results_and_order_are_those_of_a_run_without_break() -> None:
    """The same stateful tools, driven by the same program, once bare and once through the applier."""
    def program(step: Any) -> list[Any]:
        return [step("a", query="one"), step("b", query="two"), step("a", query="three"), step("b", query="four")]

    def world() -> tuple[dict[str, Tool], list[str]]:
        order: list[str] = []

        class Logged(Tool):
            def __init__(self, name: str, *values: Any) -> None:
                super().__init__(*values)
                self.name = name

            def __call__(self, **args: Any) -> Any:
                order.append(self.name)
                return super().__call__(**args)
        return {"a": Logged("a", "a1", {"n": 2}), "b": Logged("b", ["b1"], 4)}, order

    bare_tools, bare_order = world()
    bare = program(lambda name, **args: bare_tools[name](**args))

    tools, order = world()
    s = session("")
    through = program(lambda name, **args: call(s, name, tools[name], **args))

    assert through == bare
    assert order == bare_order
    assert {n: t.log for n, t in tools.items()} == {n: t.log for n, t in bare_tools.items()}


def test_under_the_control_the_agent_gets_the_tools_own_object() -> None:
    """Not a copy: a tool may hand back a handle, a stream or anything else that a copy would break,
    and a run without Break gets the object itself."""
    handle = object()
    assert call(session(""), "a", Tool(handle)) is handle


def test_under_the_control_a_tools_own_exception_is_the_tools_own() -> None:
    wrong = LookupError("no such order")
    with pytest.raises(LookupError) as raised:
        call(session(""), "a", Tool(raises=wrong))
    assert raised.value is wrong


def test_under_the_control_a_call_takes_no_longer_than_the_tool() -> None:
    """A run's clock is the agent's, and a wait of Break's own would change what the wall-clock limit
    cuts off. The first call and the later ones."""
    s = session("")
    for _ in range(3):
        started = time.monotonic()
        call(s, "a", Tool())
        assert time.monotonic() - started < 1


def test_under_the_control_the_tool_runs_once_per_call() -> None:
    tool = Tool()
    s = session("")
    for _ in range(3):
        call(s, "a", tool)
    assert tool.runs == 3


def test_under_the_control_the_record_says_no_change_on_any_call_and_holds_no_change() -> None:
    s = session("")
    call(s, "a", Tool())
    call(s, "b", Tool())
    assert s.calls == (Call(tool="a", call=1, change=None, real_ran=True),
                       Call(tool="b", call=1, change=None, real_ran=True))
    assert s.applied == ()


@pytest.mark.parametrize("agent", PLAIN)
def test_a_plain_scripted_agent_does_the_same_with_break_and_without(agent: str) -> None:
    """BK2.2 through every scripted agent: what it saw, what it called and its reply."""
    program = getattr(agents(), agent)
    bare_tools = plain_tools()
    bare = program(CASE, bare_tools)
    run, _, tools = run_plain_agent(program)
    assert run == bare
    assert {n: t.log for n, t in tools.items()} == {n: t.log for n, t in bare_tools.items()}


# ---------------------------------------------------------------------------
# BK2.3  only the named call is touched
# ---------------------------------------------------------------------------


class Answers(Tool):
    """A tool whose answer depends on what it was asked and on nothing that happened before, so that a
    call number the applier skipped cannot change a later answer by itself."""

    def __call__(self, **args: Any) -> Any:
        self.log.append(args)
        return f"the answer to {args['query']}. {LONG}"


def _trace(text: str, **over: Any) -> tuple[list[tuple], Any, dict[str, Tool]]:
    """The run a,b,a,b,a with a different answer on every call: what the agent saw on each."""
    tools = {"a": Answers(), "b": Answers()}
    s = session(text, tools=REPEATABLE, marker="quillfern", **over)
    out = [seen_call(s, name, tools[name], query=f"{name}{i}") for i, name in enumerate("ababa")]
    return out, s, tools


@pytest.mark.parametrize("fault", QUICK)
def test_a_change_on_one_call_leaves_every_other_call_as_the_controls(fault: str) -> None:
    """`b`'s second call is the same number on another tool, and `a`'s first and third are the same
    tool at other numbers: each is the mistake one wrong count would make. `malformed` leaves plain
    text alone, so it is the one fault whose own call shows no difference here."""
    control, _, control_tools = _trace("")
    faulted, s, tools = _trace(f"tool:a#2={fault}")
    named = 2  # the run's third call is a's second
    assert [v for i, v in enumerate(faulted) if i != named] == [v for i, v in enumerate(control) if i != named]
    if fault != "malformed":
        assert faulted[named] != control[named]
    assert [c.change for c in s.calls] == [None, None, f"tool:a#2={fault}", None, None]
    assert tools["b"].log == control_tools["b"].log


@pytest.mark.parametrize("position, lands", [
    ("#1", [1]), ("#3", [3]), ("#2-3", [2, 3]), ("#2-9", [2, 3, 4]), ("#*", [1, 2, 3, 4]), ("#9", []),
])
def test_a_schedule_lands_on_exactly_the_calls_it_names(position: str, lands: list[int]) -> None:
    s = session(f"tool:a{position}=empty")
    tool = Tool("answer")
    got = [seen_call(s, "a", tool)[1] for _ in range(4)]
    assert got == ["" if n in lands else "answer" for n in (1, 2, 3, 4)]
    assert [c.call for c in s.calls if c.change is not None] == lands
    assert all(c.change == f"tool:a{position}=empty" for c in s.calls if c.change is not None)


@pytest.mark.parametrize("seed", range(12))
def test_a_rate_lands_where_the_catalogue_says_it_does_for_this_seed(seed: int) -> None:
    """The same draw `applies` makes: the run's seed, the tool and the call. A session that made a
    draw of its own, or counted differently, would land elsewhere."""
    text = "tool:a~0.5=empty"
    change = one(text)
    s = session(text, seed=seed)
    got = [seen_call(s, "a", Tool("answer"))[1] for _ in range(12)]
    expected = [changes().applies(change, seed=seed, tool="a", call=n) for n in range(1, 13)]
    assert got == ["" if fires else "answer" for fires in expected]


def test_the_rate_is_drawn_on_the_runs_own_seed() -> None:
    def landed(seed: int) -> list[bool]:
        s = session("tool:a~0.5=empty", seed=seed)
        for _ in range(12):
            call(s, "a", Tool())
        return [c.change is not None for c in s.calls]
    assert len({tuple(landed(seed)) for seed in range(8)}) > 1


def test_a_faulted_call_still_counts_whether_or_not_the_tool_ran() -> None:
    """The number is the agent's calling, not the tool's running: `error` on the first call and on the
    third leaves the second clean, though the tool has by then run only once."""
    tool = Tool("answer")
    s = session("tool:a#1=error + tool:a#3=error")
    assert [seen_call(s, "a", tool)[0] for _ in range(3)] == ["failure", "result", "failure"]
    assert tool.runs == 1
    assert [c.call for c in s.calls] == [1, 2, 3]


def test_a_tools_own_exception_still_counts_as_a_call() -> None:
    wrong = LookupError("no")
    s = session("tool:a#2=empty")
    with pytest.raises(LookupError):
        call(s, "a", Tool(raises=wrong))
    assert seen_call(s, "a", Tool("answer")) == ("result", "")


def test_changes_on_different_calls_each_land_on_their_own() -> None:
    s = session("tool:a#1=error + tool:a#2=empty + tool:b#2=cut_off")
    long = Tool(LONG)
    assert seen_call(s, "a", long)[0] == "failure"
    assert seen_call(s, "b", long) == ("result", LONG)
    assert seen_call(s, "a", long) == ("result", "")
    assert seen_call(s, "b", long) == ("result", LONG[:200])


def test_the_call_counts_belong_to_the_run() -> None:
    """A count kept on the class or the module would put the second run's first call past the change
    meant for it."""
    for _ in range(2):
        s = session("tool:a#1=empty")
        assert seen_call(s, "a", Tool("answer")) == ("result", "")
        assert s.calls[0].call == 1


# ---------------------------------------------------------------------------
# BK2.4  every call leaves a record
# ---------------------------------------------------------------------------


def test_a_mixed_run_leaves_exactly_this_record() -> None:
    s = session("tool:a#2-3=empty + tool:b#1=error + tool:b#7=timeout")
    tool = Tool("answer")
    for name in ("a", "b", "a", "b", "a", "a"):
        seen_call(s, name, tool)
    assert s.calls == (
        Call(tool="a", call=1, change=None, real_ran=True),
        Call(tool="b", call=1, change="tool:b#1=error", real_ran=False),
        Call(tool="a", call=2, change="tool:a#2-3=empty", real_ran=True),
        Call(tool="b", call=2, change=None, real_ran=True),
        Call(tool="a", call=3, change="tool:a#2-3=empty", real_ran=True),
        Call(tool="a", call=4, change=None, real_ran=True),
    )
    assert s.applied == (
        Applied(surface="tool", tool="a", fault="empty", call="#2-3", applied=True, applied_call=2),
        Applied(surface="tool", tool="b", fault="error", call="#1", applied=True, applied_call=1),
        Applied(surface="tool", tool="b", fault="timeout", call="#7", applied=False, applied_call=None),
    )


def test_a_change_never_reached_says_so() -> None:
    s = session("tool:a#5=error")
    call(s, "a", Tool())
    assert s.applied[0].applied is False
    assert s.applied[0].applied_call is None


def test_a_change_on_a_tool_never_called_says_so() -> None:
    s = session("tool:b#1=error")
    call(s, "a", Tool())
    assert s.applied[0].applied is False
    assert s.applied[0].applied_call is None


def test_a_rate_that_never_fired_says_so() -> None:
    change = one("tool:a~0.1=error")
    seed = next(n for n in range(1000) if not any(changes().applies(change, seed=n, tool="a", call=c) for c in (1, 2, 3)))
    s = session("tool:a~0.1=error", seed=seed)
    for _ in range(3):
        call(s, "a", Tool())
    assert s.applied[0].applied is False
    assert s.applied[0].applied_call is None
    assert all(c.change is None for c in s.calls)


def test_a_rate_that_fired_gives_the_first_call_it_landed_on() -> None:
    change = one("tool:a~0.5=empty")
    seed, first = next((n, c) for n in range(1000) for c in (2, 3)
                       if changes().applies(change, seed=n, tool="a", call=c)
                       and not any(changes().applies(change, seed=n, tool="a", call=k) for k in range(1, c)))
    s = session("tool:a~0.5=empty", seed=seed)
    for _ in range(4):
        call(s, "a", Tool())
    assert s.applied[0].applied is True
    assert s.applied[0].applied_call == first


def test_a_record_of_a_change_holds_its_fields_as_the_condition_writes_them() -> None:
    """Every surface: the stored shape of §6.4, one entry per change, in the condition's order. Whether
    a surroundings change applied is the runs module's to say (BK5.8), so that one bool is left out."""
    env = {"inventory": ["full", "empty"]}
    condition = changes().parse("env:inventory=empty + input:typos + model:cut_off#2 + tool:a~0.3=error + user:repeats@3",
                                env=env)
    s = apply().Session(condition, seed=SEED, tools={"a": "read"}, capabilities=Capabilities(**ALL_CAPABILITIES))
    assert [(x.surface, x.tool, x.fault, x.call) for x in s.applied] == [
        (c.surface, c.tool, c.fault, c.call) for c in condition.changes]


def test_the_record_fits_the_stored_shape_and_reads_back() -> None:
    s = session("tool:a#2=error + tool:b#3=empty")
    call(s, "a", Tool())
    with pytest.raises(apply().ToolFailure):
        call(s, "a", Tool())
    record = RunRecord(
        hunt="h", stage="search", arm="h-search", case="c1",
        condition=Condition(name=changes().name(s.condition), changes=s.applied),
        failure=Failure(kind=None, signals=Signals(gave_up=0, retry_storm=0, over_budget=0)),
        selection=Selection(strategy="screen", probability=1),
        calls=s.calls, judged_by="break", target_outcome=None)
    assert RunRecord.from_json(record.to_json()) == record


def test_a_call_that_ended_in_the_tools_own_exception_leaves_its_record() -> None:
    """Ruling 8. The tool ran, and the change was on. `real_ran` is what `duplicate_write` reads."""
    s = session("tool:a#1=empty")
    with pytest.raises(LookupError):
        call(s, "a", Tool(raises=LookupError("no")))
    assert s.calls == (Call(tool="a", call=1, change="tool:a#1=empty", real_ran=True),)
    assert s.applied[0].applied is True
    assert s.applied[0].applied_call == 1


def test_the_record_read_before_a_later_call_is_what_it_was() -> None:
    s = session("")
    call(s, "a", Tool())
    earlier = s.calls
    call(s, "a", Tool())
    assert len(earlier) == 1
    assert len(s.calls) == 2


# ---------------------------------------------------------------------------
# BK2.9  replay
# ---------------------------------------------------------------------------

REPLAYED = ["", "tool:lookup_order#1=error", "tool:lookup_order~0.5=error", "tool:lookup_order#*=malformed",
            "tool:lookup_order#1=planted_instruction", "tool:check_policy~0.7=empty + tool:lookup_order#1=cut_off",
            "tool:lookup_order#2=stale", "input:typos"]
JSON_TOOLS = {"lookup_order": ('{"order": 7, "status": "shipped", "carrier": "usual"}',), "check_policy": ("policy",)}


def _way_in_once(text: str, seed: int) -> tuple:
    tools = {n: Tool(*v) for n, v in JSON_TOOLS.items()}
    s = session(text, seed=seed, marker="quillfern")
    agent = agents().WayIn(tools)
    with s:
        result = agent.run(s.case(CASE), s, seed=seed, limits=None)
    return result, s.calls, s.applied, [(v.tool, v.args, v.result, repr(v.error)) for v in agent.seen]


@pytest.mark.parametrize("text", REPLAYED)
@pytest.mark.parametrize("seed", [1, 20261104])
def test_two_runs_give_identical_records_and_what_the_agent_saw(text: str, seed: int) -> None:
    assert _way_in_once(text, seed) == _way_in_once(text, seed)


@pytest.mark.parametrize("agent", PLAIN)
@pytest.mark.parametrize("text", ["tool:lookup_order~0.5=error", "tool:lookup_order#1=planted_instruction",
                                  "tool:issue_refund~0.5=lost_reply", "tool:check_policy#*=timeout"])
def test_a_plain_scripted_agent_replays(agent: str, text: str) -> None:
    def once() -> tuple:
        run, s, tools = run_plain_agent(getattr(agents(), agent), text, seed=7, marker="quillfern")
        return run, s.calls, s.applied, {n: t.log for n, t in tools.items()}
    assert once() == once()


def test_a_run_replays_whatever_ran_before_it() -> None:
    """A generator or a cache shared between sessions would make a run depend on the one before it."""
    first = _way_in_once("tool:lookup_order#*=malformed", 3)
    _way_in_once("tool:lookup_order#*=malformed", 4)
    _way_in_once("tool:check_policy~0.5=error", 5)
    assert _way_in_once("tool:lookup_order#*=malformed", 3) == first


def test_a_run_neither_reads_nor_moves_the_global_generator() -> None:
    """§3.1: the search's seed never touches a run's. The search's random choices come from one global
    place in a careless build, and a run that drew on it would change with the search, or change it."""
    random.seed(1)
    first = _way_in_once("tool:lookup_order#*=malformed", 3)
    random.seed(2)
    state = random.getstate()
    second = _way_in_once("tool:lookup_order#*=malformed", 3)
    assert random.getstate() == state
    assert first == second


def test_the_seed_decides_how_a_fault_with_a_choice_makes_it() -> None:
    """`rng` is seeded by the core (§11.1), from what the run holds: a generator fixed for every run
    would give every run the same one of `malformed`'s two ways, and the seed would mean nothing."""
    def way(seed: int) -> str:
        s = session("tool:a#1=malformed", seed=seed)
        value = call(s, "a", Tool({"order": 7, "status": "shipped"}))
        return "renamed" if isinstance(value, dict) else "bracket"
    assert {way(seed) for seed in range(40)} == {"renamed", "bracket"}


REPLAY_DRIVER = """
import json
from poisson_break.apply import Session
from poisson_break.changes import parse
from tests.agents import WayIn
out = {}
for text in ('tool:lookup_order~0.5=malformed', 'tool:lookup_order#*=malformed', 'tool:check_policy~0.3=error',
             'tool:lookup_order#1=planted_instruction', 'input:typos + input:padded'):
    for seed in range(8):
        s = Session(parse(text), seed=seed, tools={'lookup_order': 'read', 'check_policy': 'read'}, marker='quillfern')
        tools = {'lookup_order': lambda **a: {'alpha': 1, 'beta': 2, 'gamma': 3, 'delta': 4}, 'check_policy': lambda **a: 'policy'}
        agent = WayIn(tools)
        agent.run(s.case({'id': 'c1', 'input': 'Where is order 7? Please refund it now.'}), s, seed=seed, limits=None)
        out[f'{text}/{seed}'] = {'calls': [c.to_dict() for c in s.calls], 'applied': [a.to_dict() for a in s.applied],
                                 'seen': [[v.tool, v.args, repr(v.result), repr(v.error)] for v in agent.seen]}
print(json.dumps(out, sort_keys=True))
"""


def test_a_run_replays_in_another_process() -> None:
    """A rename picked out of a set, a word by a built-in hash or a generator seeded from a tuple's
    hash passes in one process and does not replay."""
    def under(hash_seed: int) -> dict:
        env = guarded_env()
        env["PYTHONHASHSEED"] = str(hash_seed)
        done = subprocess.run([sys.executable, "-c", REPLAY_DRIVER], capture_output=True, text=True, timeout=120,
                              env=env, stdin=subprocess.DEVNULL, cwd=REPO)
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)
    assert under(1) == under(2)


# ---------------------------------------------------------------------------
# BK2.13  the call context is filled in, with every earlier call clean
# ---------------------------------------------------------------------------


@pytest.fixture
def with_a_watching_fault() -> Iterator[tuple[ModuleType, ModuleType, list[Any]]]:
    yield from watching()


def _session(c: Any, a: Any, text: str, **over: Any) -> Any:
    over.setdefault("seed", SEED)
    over.setdefault("tools", {"a": "read", "b": "read"})
    return a.Session(c.parse(text), **over)


def test_the_context_holds_this_call(with_a_watching_fault: Any) -> None:
    c, a, watched = with_a_watching_fault
    condition_text = "tool:a#2=watch + tool:b#9=error"
    s = _session(c, a, condition_text, seed=41, marker="quillfern")
    tool = Tool(EARLIER, REAL_TEXT)
    call(s, "a", tool, query="first")
    call(s, "b", Tool("b's answer"), query="other")
    call(s, "a", tool, query="second", page=3)
    got = watched[0]
    assert got.tool == "a"
    assert dict(got.args) == {"query": "second", "page": 3}
    assert got.call == 2
    assert got.condition == c.parse(condition_text)
    assert got.seed == 41
    assert got.marker == "quillfern"


def test_a_first_call_has_no_previous_result(with_a_watching_fault: Any) -> None:
    c, a, watched = with_a_watching_fault
    call(_session(c, a, "tool:a#1=watch"), "a", Tool())
    assert watched[0].previous is None


def test_a_later_call_has_the_previous_result_of_the_same_tool(with_a_watching_fault: Any) -> None:
    c, a, watched = with_a_watching_fault
    s = _session(c, a, "tool:a#2-3=watch")
    tool = Tool(EARLIER, {"second": True}, "third")
    call(s, "a", tool)
    call(s, "b", Tool("b's answer"))
    call(s, "a", tool)
    call(s, "b", Tool("b's other answer"))
    call(s, "a", tool)
    assert watched[0].previous == EARLIER
    assert watched[1].previous == {"second": True}


def test_another_tools_first_call_has_no_previous_result_of_its_own(with_a_watching_fault: Any) -> None:
    c, a, watched = with_a_watching_fault
    s = _session(c, a, "tool:b#1=watch")
    call(s, "a", Tool(EARLIER))
    call(s, "b", Tool())
    assert watched[0].previous is None


def test_the_marker_is_the_word_the_session_was_given_and_comes_from_the_hunt_and_the_case(
        with_a_watching_fault: Any) -> None:
    """The word reaches the fault whole, from `marker(hunt=, case=)` (BK2.13), so that what the failure
    check later recovers from the record is the word the agent was told."""
    c, a, watched = with_a_watching_fault
    word = c.marker(hunt="refund-agent-1", case="c7")
    call(_session(c, a, "tool:a#1=watch", marker=word), "a", Tool())
    assert watched[0].marker == word


def test_a_session_given_no_marker_gives_the_fault_none(with_a_watching_fault: Any) -> None:
    c, a, watched = with_a_watching_fault
    call(_session(c, a, "tool:a#1=watch"), "a", Tool())
    assert watched[0].marker is None


def test_a_fault_cannot_edit_what_the_real_tool_was_called_with(with_a_watching_fault: Any) -> None:
    c, a, watched = with_a_watching_fault
    args = {"query": "first"}
    s = _session(c, a, "tool:a#1=watch")
    s.call("a", args, lambda: "answer")
    with pytest.raises(TypeError):
        watched[0].args["query"] = "changed"
    assert args == {"query": "first"}


def test_a_previous_result_is_as_it_came_back_even_if_the_agent_then_edits_it() -> None:
    """Ruling 14. An agent that pops a key from what its tool returned has not changed what the tool
    returned, and `stale` hands back the result of the previous call."""
    tool = Tool({"order": 7, "status": "shipped", "nested": {"a": 1}}, "fresh")
    s = session("tool:a#2=stale")
    first = call(s, "a", tool)
    del first["status"]
    first["nested"]["a"] = 99
    assert call(s, "a", tool) == {"order": 7, "status": "shipped", "nested": {"a": 1}}


def test_a_result_that_cannot_be_copied_is_held_as_it_was() -> None:
    """Ruling 14. A handle or a stream cannot be copied, and is no reason to fail a run."""
    class Handle:
        def __deepcopy__(self, memo: Any) -> Any:
            raise TypeError("cannot be copied")

    handle = Handle()
    tool = Tool(handle, "fresh")
    s = session("tool:a#2=stale")
    assert call(s, "a", tool) is handle
    assert call(s, "a", tool) is handle
    assert s.stopped is None


def test_the_tools_own_exception_is_no_previous_result() -> None:
    """A call whose tool raised returned nothing. With no result yet, `stale` on the next call is a
    first call's `empty`, under either reading of "previous", since the agent saw no result either."""
    s = session("tool:a#2=stale")
    with pytest.raises(LookupError):
        call(s, "a", Tool(raises=LookupError("no")))
    assert seen_call(s, "a", Tool("fresh")) == ("result", "")
