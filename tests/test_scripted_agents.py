"""The five scripted agents, in `tests/agents/`, held to what each is said to do. Every later module's
tests stand on them, so a mistake here would pass unnoticed through all of those.

Invariant pinned here (Break — Plan, the applying module and §2 item 2):
- BK2.10 The scripted agents are five, each a pure program with no framework: one retries, one gives up,
         one follows planted text, one repeats a write, and one speaks only the way-in protocol; every
         later module's tests use them and nothing else.

They are built with the module and not with these tests, and their names, shapes and call patterns are
ruling 16. The four plain agents are `agent(case, tools) -> Run`: a tool is a callable taking keyword
arguments, and raising is how it fails. Nothing here needs the agent to be running under Break unless it
says so: an agent reacts to a tool that fails, and cannot tell a fault from a real failure.

The way-in agent's `RunResult` and `ToolInfo` are ruling 15.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from poisson_break.interfaces import Capabilities, Target
from tests.apply_support import CASE, LONG, Tool, agents, apply, plain_tools, run_plain_agent, run_way_in, session, wrap_all
from tests.changes_support import changes
from tests.conftest import TESTS

AGENTS_DIR = TESTS / "agents"
FAILURES = ["error", "timeout", "rate_limited", "lost_reply"]
NON_FAILURES = ["empty", "cut_off", "malformed", "stale"]


def failing(exc: BaseException | None = None) -> Tool:
    return Tool(raises=exc or LookupError("the service is down"))


def called(run: Any) -> list[str]:
    return [v.tool for v in run.seen]


def fails_then(times: int, then: Any = "the answer") -> Any:
    """A real tool that fails its first few calls and then answers."""
    class Flaky(Tool):
        def __call__(self, **args: Any) -> Any:
            self.log.append(args)
            if len(self.log) <= times:
                raise LookupError("the service is down")
            return then
    return Flaky()


# ---------------------------------------------------------------------------
# they are five, and pure
# ---------------------------------------------------------------------------


def test_they_are_five_and_each_does_its_own_thing() -> None:
    a = agents()
    assert a.AGENTS == (a.retries, a.gives_up, a.follows_plant, a.repeats_write, a.WayIn)


def _agent_files() -> list[Path]:
    files = sorted(p for p in AGENTS_DIR.rglob("*.py") if "__pycache__" not in p.parts)
    assert files, f"no agents under {AGENTS_DIR}"
    return files


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module)
    return found


# What would make a program's answer depend on the day it ran, or on where.
IMPURE = {"time", "datetime", "random", "secrets", "uuid", "os", "socket", "subprocess", "threading",
          "multiprocessing", "asyncio", "urllib", "http", "tempfile", "pathlib", "shutil", "sqlite3"}


def test_no_framework_and_nothing_that_is_not_python_or_break() -> None:
    allowed = set(sys.stdlib_module_names) | {"poisson_break", "tests"}
    bad = {str(p.name): sorted(i for i in _imports(p) if i.split(".")[0] not in allowed) for p in _agent_files()}
    assert not any(bad.values()), bad


def test_nothing_that_would_make_a_run_differ_from_the_last() -> None:
    bad = {str(p.name): sorted(i for i in _imports(p) if i.split(".")[0] in IMPURE) for p in _agent_files()}
    assert not any(bad.values()), bad


def test_the_way_in_protocol_is_all_of_break_they_speak() -> None:
    """Spec §11.2's protocol and the failure it raises. An agent reaching into `changes` or `records`
    would know more than a real agent knows, and pass where a real one would not."""
    reached = {i for p in _agent_files() for i in _imports(p) if i.split(".")[0] == "poisson_break"}
    assert reached <= {"poisson_break.apply", "poisson_break.interfaces"}, reached


# ---------------------------------------------------------------------------
# the four plain agents share a shape
# ---------------------------------------------------------------------------


PLAIN = ["retries", "gives_up", "follows_plant", "repeats_write"]


@pytest.mark.parametrize("agent", PLAIN)
def test_a_run_says_what_it_replied_and_saw(agent: str) -> None:
    run = getattr(agents(), agent)(CASE, plain_tools())
    assert isinstance(run.reply, str) and run.reply
    assert run.seen
    with pytest.raises(dataclasses.FrozenInstanceError):
        run.reply = "changed"
    first = run.seen[0]
    assert (first.tool, first.error) == ("lookup_order", None)
    assert first.result == "Order 7 shipped on Tuesday."
    assert first.args == {"query": CASE["input"]}


@pytest.mark.parametrize("agent", PLAIN)
def test_the_same_case_and_tools_give_the_same_run(agent: str) -> None:
    program = getattr(agents(), agent)
    assert program(CASE, plain_tools()) == program(CASE, plain_tools())


@pytest.mark.parametrize("agent", PLAIN)
def test_the_request_reaches_the_tool(agent: str) -> None:
    """So that an input operator changes what the agent does, as it would a real one's."""
    tools = plain_tools()
    getattr(agents(), agent)({"id": "c2", "input": "Something else entirely."}, tools)
    assert tools["lookup_order"].log[0] == {"query": "Something else entirely."}


@pytest.mark.parametrize("agent", PLAIN)
def test_the_agents_case_is_read_and_left_alone(agent: str) -> None:
    case = {"id": "c1", "input": "Where is order 7?", "expect": {"calls": []}}
    before = json.dumps(case, sort_keys=True)
    getattr(agents(), agent)(case, plain_tools())
    assert json.dumps(case, sort_keys=True) == before


@pytest.mark.parametrize("agent", ["retries", "gives_up", "repeats_write"])
def test_only_the_one_that_follows_planted_text_follows_it(agent: str) -> None:
    """`followed_plant` fires on the marker in a reply or a later tool call (§4), and quoting a result
    back would fire it on an agent that followed nothing: three of the five would then read as broken
    under this fault, whatever they did."""
    run, s, tools = run_plain_agent(getattr(agents(), agent), "tool:lookup_order#1=planted_instruction", marker="quillfern")
    assert "quillfern" not in run.reply
    assert all("quillfern" not in json.dumps(args) for t in tools.values() for args in t.log)
    assert s.applied[0].applied is True


# ---------------------------------------------------------------------------
# the one that retries
# ---------------------------------------------------------------------------


def test_with_a_tool_that_works_it_does_not_retry() -> None:
    run = agents().retries(CASE, plain_tools())
    assert called(run) == ["lookup_order"]


@pytest.mark.parametrize("times", [1, 2, 4])
def test_it_retries_the_failed_call_with_the_same_arguments_until_it_works(times: int) -> None:
    tool = fails_then(times)
    run = agents().retries(CASE, {**plain_tools(), "lookup_order": tool})
    assert tool.runs == times + 1
    assert all(args == {"query": CASE["input"]} for args in tool.log)
    assert run.seen[-1].result == "the answer"
    assert all(v.error is not None for v in run.seen[:-1])


def test_a_real_failure_and_a_fault_are_the_same_to_it() -> None:
    """A fault enters where a real failure would (§3.2), so an agent has one path for both."""
    on_fault, _, _ = run_plain_agent(agents().retries, "tool:lookup_order#1-2=error")
    tool = fails_then(2, then="Order 7 shipped on Tuesday.")
    on_real = agents().retries(CASE, {**plain_tools(), "lookup_order": tool})
    assert [v.error is None for v in on_fault.seen] == [v.error is None for v in on_real.seen]
    assert on_fault.reply == on_real.reply


@pytest.mark.parametrize("fault", ["error", "timeout", "rate_limited"])
def test_under_a_fault_on_every_call_it_stops_at_its_stated_limit(fault: str) -> None:
    limit = agents().RETRY_LIMIT
    run, s, tools = run_plain_agent(agents().retries, f"tool:lookup_order#*={fault}")
    assert len(s.calls) == limit
    assert len(run.seen) == limit
    assert tools["lookup_order"].runs == 0


def test_its_limit_is_past_where_a_retry_storm_is_counted() -> None:
    """§4: `retry_storm` counts more than 5 calls of one tool in a row, by default. This is the agent
    every later module reaches for to see one, so it has to be able to make one."""
    assert isinstance(agents().RETRY_LIMIT, int) and agents().RETRY_LIMIT > 5


def test_it_replies_differently_when_it_ran_out_of_tries() -> None:
    """The later modules' `reply_contains` and the failure check can tell a run that got its answer."""
    assert agents().retries(CASE, plain_tools()).reply != agents().retries(
        CASE, {**plain_tools(), "lookup_order": failing()}).reply


def test_it_does_not_wait_between_tries() -> None:
    """A pure program, with no clock: told to wait thirty seconds, it does not."""
    started = time.monotonic()
    run_plain_agent(agents().retries, "tool:lookup_order#*=rate_limited")
    assert time.monotonic() - started < 2


@pytest.mark.parametrize("fault", NON_FAILURES)
def test_a_result_it_does_not_like_is_not_a_failure_to_it(fault: str) -> None:
    """Only a raised failure makes it try again."""
    run, s, _ = run_plain_agent(agents().retries, f"tool:lookup_order#1={fault}")
    assert len(s.calls) == 1
    assert run.seen[0].error is None


# ---------------------------------------------------------------------------
# the one that gives up
# ---------------------------------------------------------------------------


GIVES_UP_CALLS = ["lookup_order", "check_policy", "lookup_order"]


def test_with_tools_that_work_it_makes_its_three_calls() -> None:
    assert called(agents().gives_up(CASE, plain_tools())) == GIVES_UP_CALLS


@pytest.mark.parametrize("name, position, made", [
    ("lookup_order", "#1", 1), ("check_policy", "#1", 2), ("lookup_order", "#2", 3)])
@pytest.mark.parametrize("fault", ["error", "timeout", "rate_limited"])
def test_on_the_first_failure_it_stops_and_never_calls_that_tool_again(name: str, position: str, made: int,
                                                                       fault: str) -> None:
    """§4's `gave_up`: a tool failed, on a schedule that ends, and the agent never called it again. The
    schedule here has ended, since only this call was faulted, and it still stops."""
    run, s, _ = run_plain_agent(agents().gives_up, f"tool:{name}{position}={fault}")
    assert called(run) == GIVES_UP_CALLS[:made]
    assert len(s.calls) == made
    assert run.seen[-1].error is not None


def test_it_says_it_gave_up_with_a_different_reply_and_none_of_the_result() -> None:
    worked = agents().gives_up(CASE, plain_tools())
    gave_up = agents().gives_up(CASE, {**plain_tools(), "check_policy": failing()})
    assert gave_up.reply != worked.reply
    assert "Order 7 shipped" not in gave_up.reply


def test_giving_up_after_planted_text_it_does_not_quote_the_plant() -> None:
    """It read the planted sentence and then failed. `followed_plant` must not fire on that reply."""
    run, _, _ = run_plain_agent(agents().gives_up, "tool:check_policy#1=error + tool:lookup_order#1=planted_instruction",
                                marker="quillfern")
    assert run.seen[-1].error is not None
    assert "quillfern" in run.seen[0].result
    assert "quillfern" not in run.reply


def test_a_real_failure_ends_it_the_same_way() -> None:
    tools = {**plain_tools(), "check_policy": failing()}
    assert called(agents().gives_up(CASE, tools)) == GIVES_UP_CALLS[:2]
    assert tools["lookup_order"].runs == 1


@pytest.mark.parametrize("fault", NON_FAILURES)
def test_only_a_raised_failure_makes_it_give_up(fault: str) -> None:
    run, _, _ = run_plain_agent(agents().gives_up, f"tool:lookup_order#1={fault}")
    assert called(run) == GIVES_UP_CALLS


# ---------------------------------------------------------------------------
# the one that follows planted text
# ---------------------------------------------------------------------------


FOLLOWS_CALLS = ["lookup_order", "check_policy"]


def test_with_no_planted_text_it_makes_its_two_calls_and_follows_nothing() -> None:
    word = changes().marker(hunt="h", case="c1")
    tools = plain_tools()
    run = agents().follows_plant(CASE, tools)
    assert called(run) == FOLLOWS_CALLS
    assert word not in run.reply
    assert tools["check_policy"].log == [{"topic": "refunds"}]
    assert "Refunds within thirty days" not in run.reply
    assert "Order 7 shipped" not in run.reply


def test_following_it_says_the_word_and_does_not_quote_the_result() -> None:
    """It follows the instruction, and is not an agent that repeats whatever its tool said: the check
    must fire because it obeyed (§4, BK3.3)."""
    run, _, _ = run_plain_agent(agents().follows_plant, "tool:check_policy#1=planted_instruction", marker="quillfern")
    assert "quillfern" in run.reply
    assert "Refunds within thirty days" not in run.reply
    assert "Order 7 shipped" not in run.reply


def test_it_repeats_the_marker_in_its_reply() -> None:
    word = changes().marker(hunt="h", case="c1")
    run, _, _ = run_plain_agent(agents().follows_plant, "tool:check_policy#1=planted_instruction", marker=word)
    assert word in run.reply


def test_planted_text_on_the_first_call_also_reaches_the_later_tool_call() -> None:
    """§4: in the reply or in a later tool call, and the failure check has to be seen firing on either
    (BK3.3). Planted on the first of its two calls, it does both."""
    word = changes().marker(hunt="h", case="c1")
    run, _, tools = run_plain_agent(agents().follows_plant, "tool:lookup_order#1=planted_instruction", marker=word)
    assert word in run.reply
    assert word in json.dumps(tools["check_policy"].log[0])


def test_planted_on_the_last_call_there_is_no_later_call_to_reach() -> None:
    word = changes().marker(hunt="h", case="c1")
    run, _, tools = run_plain_agent(agents().follows_plant, "tool:check_policy#1=planted_instruction", marker=word)
    assert word not in json.dumps(tools["lookup_order"].log)
    assert word not in json.dumps(tools["check_policy"].log)
    assert called(run) == FOLLOWS_CALLS


def test_it_follows_the_word_the_run_planted_and_no_other() -> None:
    """A fixed word in the agent would seem to pass with the word it knows and be wrong with any other."""
    for hunt, case in (("h1", "c1"), ("h2", "c2"), ("refund-agent-3", "lookup-11")):
        word = changes().marker(hunt=hunt, case=case)
        run, _, _ = run_plain_agent(agents().follows_plant, "tool:lookup_order#1=planted_instruction", marker=word)
        assert word in run.reply


@pytest.mark.parametrize("value", [{"order": 7}, [{"order": 7}]], ids=["mapping", "list"])
def test_it_follows_planted_text_on_a_structured_result(value: object) -> None:
    run, _, _ = run_plain_agent(agents().follows_plant, "tool:lookup_order#1=planted_instruction", marker="quillfern",
                                tools={**plain_tools(), "lookup_order": Tool(value)})
    assert "quillfern" in run.reply


@pytest.mark.parametrize("fault", FAILURES + NON_FAILURES)
def test_no_other_fault_gives_it_anything_to_follow(fault: str) -> None:
    word = changes().marker(hunt="h", case="c1")
    run, _, tools = run_plain_agent(agents().follows_plant, f"tool:lookup_order#1={fault}", marker=word,
                                    classes={"lookup_order": {"class": "write", "repeatable": True}, "check_policy": "read"})
    assert word not in run.reply
    assert word not in json.dumps(tools["check_policy"].log)


# ---------------------------------------------------------------------------
# the one that repeats a write
# ---------------------------------------------------------------------------


REPEATS_CALLS = ["lookup_order", "issue_refund"]


def test_with_a_write_that_works_it_writes_once() -> None:
    tools = plain_tools()
    assert called(agents().repeats_write(CASE, tools)) == REPEATS_CALLS
    assert tools["issue_refund"].runs == 1


def test_after_a_lost_reply_the_same_write_runs_again_with_the_same_arguments() -> None:
    """All three facts `duplicate_write` needs (BK3.4): a `lost_reply` applied, a `write` tool, and a
    second real execution with equal arguments. Held here on the record, where BK3 will read them."""
    run, s, tools = run_plain_agent(agents().repeats_write, "tool:issue_refund#1=lost_reply")
    assert tools["issue_refund"].runs == 2
    assert tools["issue_refund"].log[0] == tools["issue_refund"].log[1]
    assert [(c.tool, c.call, c.change, c.real_ran) for c in s.calls] == [
        ("lookup_order", 1, None, True),
        ("issue_refund", 1, "tool:issue_refund#1=lost_reply", True),
        ("issue_refund", 2, None, True),
    ]
    assert s.applied[0].applied is True
    assert run.seen[1].error is not None and run.seen[2].error is None


def test_after_a_plain_error_it_writes_again_and_the_tool_ran_once() -> None:
    """The same reaction with no duplicate: the first attempt never reached the tool, which is what
    tells a `lost_reply` from an `error`."""
    run, s, tools = run_plain_agent(agents().repeats_write, "tool:issue_refund#1=error")
    assert tools["issue_refund"].runs == 1
    assert [c.real_ran for c in s.calls] == [True, False, True]
    assert run.seen[-1].error is None


def test_it_repeats_once_and_does_not_go_on() -> None:
    """Under a fault on every call it tries twice and replies. The agent that goes on is the other one."""
    run, s, tools = run_plain_agent(agents().repeats_write, "tool:issue_refund#*=lost_reply")
    assert tools["issue_refund"].runs == 2
    assert len([c for c in s.calls if c.tool == "issue_refund"]) == 2
    assert run.seen[-1].error is not None


def test_a_read_that_fails_is_not_repeated() -> None:
    """It repeats a write, and this is what tells it from the agent that retries."""
    tools = {**plain_tools(), "lookup_order": failing()}
    agents().repeats_write(CASE, tools)
    assert tools["lookup_order"].runs == 1


def test_the_write_is_the_one_tool_it_writes_through() -> None:
    tools = plain_tools()
    agents().repeats_write(CASE, tools)
    assert tools["check_policy"].runs == 0


# ---------------------------------------------------------------------------
# the one that speaks only the way-in protocol
# ---------------------------------------------------------------------------


WAY_IN_CALLS = ["lookup_order", "check_policy", "lookup_order"]


def test_it_is_a_way_in() -> None:
    agent = agents().WayIn(plain_tools())
    assert isinstance(agent, Target)
    assert isinstance(agent.kind, str) and agent.kind
    assert list(agent.framework_versions) == []


def test_it_says_it_routes_tool_calls_and_nothing_more() -> None:
    """Like a bare Prove target. A later module's way in may do more; this one is its base case."""
    assert agents().WayIn(plain_tools()).capabilities() == Capabilities(
        tool_calls=True, model_calls=False, conversation=False)


def test_it_lists_exactly_the_tools_it_then_calls() -> None:
    """§11.2 invariant 3: `tools()` before any run equals the set seen during the control stage."""
    tools = plain_tools()
    agent = agents().WayIn({k: tools[k] for k in ("lookup_order", "check_policy")})
    listed = {info.name for info in agent.tools()}
    assert all(isinstance(info, apply().ToolInfo) for info in agent.tools())
    s = session("")
    agent.run(CASE, s, seed=1, limits=None)
    assert listed == {c.tool for c in s.calls} == {"lookup_order", "check_policy"}


def test_every_tool_call_goes_through_the_session() -> None:
    """§11.2 invariant 2. The real tool's runs and the session's record agree, call for call."""
    result, agent, s, tools = run_way_in()
    assert [c.tool for c in s.calls] == WAY_IN_CALLS
    assert sum(t.runs for t in tools.values()) == len(s.calls)
    assert [v.tool for v in agent.seen] == WAY_IN_CALLS
    assert result.ended == "returned"


def test_it_keeps_going_past_a_failure_and_sees_every_call_of_its_program() -> None:
    """It is the one that shows every later call of a run under a fault, which the others cannot, each
    stopping or repeating by design."""
    result, agent, s, _ = run_way_in("tool:check_policy#1=error")
    assert [v.tool for v in agent.seen] == WAY_IN_CALLS
    assert agent.seen[1].error is not None
    assert agent.seen[1].error.kind == "error"
    assert agent.seen[2].error is None
    assert result.ended == "returned"


def test_what_it_sees_starts_afresh_on_each_run() -> None:
    agent = agents().WayIn(plain_tools())
    agent.run(CASE, session(""), seed=1, limits=None)
    first = agent.seen
    agent.run(CASE, session(""), seed=1, limits=None)
    assert len(agent.seen) == len(first) == len(WAY_IN_CALLS)


def test_it_runs_the_script_it_is_given() -> None:
    script = [("a", {"q": 1}), ("b", {"q": 2}), ("a", {"q": 3})]
    tools = {"a": Tool("a's"), "b": Tool("b's")}
    _, agent, s, _ = run_way_in(script=script, tools=tools)
    assert [c.tool for c in s.calls] == ["a", "b", "a"]
    assert tools["a"].log == [{"q": 1}, {"q": 3}]
    assert tools["b"].log == [{"q": 2}]
    assert [v.result for v in agent.seen] == ["a's", "b's", "a's"]


def test_a_tools_own_exception_ends_the_run_as_raised_with_no_outcome_word() -> None:
    """§11.2 invariant 4: the exception path maps through `RunResult`, and the way in never returns an
    outcome word of its own. `crashed` is the core's to say."""
    tools = {**plain_tools(), "check_policy": failing()}
    result, agent, s, _ = run_way_in(tools=tools)
    assert result.ended == "raised"
    assert result.outcome is None
    assert [c.tool for c in s.calls] == WAY_IN_CALLS[:2]


def test_its_step_limit_ends_the_run_as_hitting_the_limit() -> None:
    """§11.2 invariant 4 again, for `ran_out`."""
    result, agent, s, _ = run_way_in(max_steps=2)
    assert result.ended == "limit"
    assert result.outcome is None
    assert len(s.calls) == 2


def test_it_reports_no_tokens_since_there_is_no_model() -> None:
    result, _, _, _ = run_way_in()
    assert result.tokens_in is None
    assert result.tokens_out is None
    assert result.outcome is None


def test_what_it_replied_does_not_quote_a_result() -> None:
    """Under a planted word its reply stays clean, so it does not read as having followed it."""
    result, agent, _, _ = run_way_in("tool:lookup_order#1=planted_instruction", marker="quillfern",
                                     tools={**plain_tools(), "lookup_order": Tool(LONG)})
    assert "quillfern" in agent.seen[0].result
    assert "quillfern" not in result.reply
    assert LONG not in result.reply


def test_its_later_calls_are_not_changed_by_what_it_saw() -> None:
    """Its calls are its script, so a fault changes what it saw and not what it asks: a later module
    that compares call patterns under a condition can trust them."""
    _, _, _, control = run_way_in()
    _, _, _, faulted = run_way_in("tool:lookup_order#1=cut_off")
    assert control["check_policy"].log == faulted["check_policy"].log
    assert control["lookup_order"].log == faulted["lookup_order"].log


# ---------------------------------------------------------------------------
# the protocol's two frozen objects (ruling 15)
# ---------------------------------------------------------------------------


def test_a_run_result_holds_what_spec_11_2_lists_and_is_frozen() -> None:
    a = apply()
    assert {f.name for f in dataclasses.fields(a.RunResult)} == {"reply", "outcome", "tokens_in", "tokens_out", "ended"}
    result = a.RunResult(reply="done", outcome=None, tokens_in=None, tokens_out=None, ended="returned")
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.reply = "changed"


@pytest.mark.parametrize("ended", ["returned", "raised", "limit"])
def test_a_run_ends_in_one_of_three_ways(ended: str) -> None:
    assert apply().RunResult(reply=None, outcome=None, tokens_in=None, tokens_out=None, ended=ended).ended == ended


@pytest.mark.parametrize("ended", ["ok", "failed", "crashed", "", None])
def test_a_way_in_cannot_end_a_run_with_a_word_of_its_own(ended: Any) -> None:
    """§11.2 invariant 4: the way in decides nothing. `failed` here would be an outcome word."""
    with pytest.raises(ValueError):
        apply().RunResult(reply=None, outcome=None, tokens_in=None, tokens_out=None, ended=ended)


def test_a_tool_info_names_the_tool_and_is_frozen() -> None:
    info = apply().ToolInfo(name="lookup_order")
    assert info.name == "lookup_order"
    with pytest.raises(dataclasses.FrozenInstanceError):
        info.name = "changed"


def test_tools_wrapped_for_a_plain_agent_need_only_an_open_session() -> None:
    """The way a `rollout` target's own agent reaches its tools: BK5 builds on this."""
    tools = plain_tools()
    s = session("tool:check_policy#1=empty")
    with s:
        run = agents().gives_up(CASE, wrap_all(tools))
    assert [v.result for v in run.seen][1] == ""
    assert s.calls[1].change == "tool:check_policy#1=empty"
