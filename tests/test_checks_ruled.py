"""The failure check's rulings (Taylor, 2026-11-04, yes to all thirty). Each test gives its ruling's number; the rulings
are in full in the evidence folder's `open-points.md`, with rulings 31 to 34, yes to the four the same day. Ruling 34 is
the settings module's to hold.

Rulings 1 to 6 are the shape the other test files already go through, and what is held here is only what those files
have no reason to read. Ruling 26 is the runs module's to hold, and ruling 30 was what those files already held.
"""

from __future__ import annotations

import dataclasses
import inspect
import sys
from collections.abc import Iterator
from types import ModuleType
from typing import Any

import pytest

from poisson_break import records
from tests.apply_support import CASE, Tool, apply, wrap_all
from tests.checks_support import (
    CLASSES,
    DEFAULT_CHECKS,
    LIMIT,
    NOT_COUNTED,
    OK,
    SLEEP,
    all_tools,
    budget,
    checks,
    failed,
    judged,
    judged_by,
    kind_of,
    lines_of,
    marker,
    own,
    own_module,
    plain,
    reply_of,
    result,
    state_of,
    target,
    verdict,
    way_in,
    with_fails,
)

PLANTED = "tool:lookup_order#1=planted_instruction"
WROTE_TWICE = "tool:issue_refund#1=lost_reply"
BROKEN_STAND_IN = {**CLASSES, "issue_refund": {"class": "write", "stand_in": "tests.apply_support_standin:broken"}}


@pytest.fixture(autouse=True)
def fresh_checks() -> Iterator[ModuleType]:
    module = own_module()
    module.reset()
    yield module
    module.reset()


def asked(check: str = "configured", **fails: Any) -> dict[str, Any]:
    return {"own": own(check), **fails}


def calls(tool: str, n: int) -> list[tuple[str, dict[str, Any]]]:
    return [(tool, {}) for _ in range(n)]


def failing() -> Tool:
    return Tool(raises=LookupError("the service is down"))


# ---------------------------------------------------------------------------
# rulings 1 to 6: the shape
# ---------------------------------------------------------------------------


def test_judge_and_signals_take_the_one_run() -> None:
    """Ruling 1. The plan's one argument stays, and settings arrive on the run."""
    for fn in (checks().judge, checks().signals):
        assert len(inspect.signature(fn).parameters) == 1


def test_watch_takes_what_ruling_1_says() -> None:
    parameters = inspect.signature(checks().watch).parameters
    assert list(parameters) == ["run_agent", "case", "session", "fails"]
    assert parameters["run_agent"].kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    assert all(parameters[n].kind is inspect.Parameter.KEYWORD_ONLY for n in ("case", "session", "fails"))
    assert parameters["fails"].default is None


def test_a_finished_run_is_frozen_and_public() -> None:
    """Ruling 1."""
    c = checks()
    assert "watch" in c.__all__ and "FinishedRun" in c.__all__
    run = way_in().run
    assert isinstance(run, c.FinishedRun)
    with pytest.raises(dataclasses.FrozenInstanceError):
        run.reply = "changed"


def test_watch_hands_back_the_runs_facts_without_judging_them() -> None:
    """Ruling 1: the verdict is `judge`'s. A check named is not yet run, and a kind met raises nothing here."""
    assert isinstance(way_in(max_steps=1, fails=asked("fails_it")).run, checks().FinishedRun)
    assert own_module().CALLS == []


def test_the_session_keeps_one_entry_of_content_per_call() -> None:
    """Ruling 2, and it is apart from the two records, which still hold no content (§6.4)."""
    scene = way_in("tool:check_policy#1=error")
    assert len(scene.session.seen) == len(scene.session.calls) == 3
    assert {f.name for f in dataclasses.fields(records.Call)} == {"tool", "call", "change", "real_ran"}


def test_the_session_keeps_a_call_it_stopped_on_too() -> None:
    """Ruling 2: a call the view lists is one the content can be read for, the one an instrument error stopped on
    among them."""
    scene = way_in(script=[("issue_refund", {"request": "r"})], classes=BROKEN_STAND_IN)
    assert len(scene.session.seen) == len(scene.session.calls) == 1


def test_a_check_named_by_anything_but_a_path_cannot_be_loaded() -> None:
    """Ruling 3: an import path only. So a function handed straight in is not a check, and with ruling 24 not counted."""
    assert verdict(way_in(fails={"own": own_module().passes}).run) == NOT_COUNTED


def test_a_verdict_holds_what_ruling_4_says() -> None:
    assert {f.name for f in dataclasses.fields(checks().Verdict)} == {"state", "kind", "outcome", "judged_by", "error"}


@pytest.mark.parametrize("make, state", [
    (lambda: way_in(), "ok"),
    (lambda: way_in(max_steps=1), "failed"),
    (lambda: plain("repeats_write", classes=BROKEN_STAND_IN), "not counted"),
], ids=["ok", "failed", "not-counted"])
def test_only_a_run_not_counted_has_an_error(make: Any, state: str) -> None:
    """Ruling 4. A not-counted run's Prove row carries it, and a counted run's row must not have one."""
    v = judged(make().run)
    assert state_of(v) == state
    assert (v.error is not None) == (state == "not counted")


def test_a_view_holds_what_ruling_5_says(fresh_checks: ModuleType) -> None:
    judged(way_in("tool:lookup_order#1=empty", fails=asked("passes")).run)
    view = fresh_checks.LAST
    assert {f.name for f in dataclasses.fields(view)} == {
        "case", "condition", "calls", "reply", "outcome", "tokens_in", "tokens_out", "seconds", "kinds"}
    assert {f.name for f in dataclasses.fields(view.case)} == {"id", "input", "turns"}
    assert {f.name for f in dataclasses.fields(view.condition)} == {"name", "changes"}
    assert {f.name for f in dataclasses.fields(view.calls[0])} == {"tool", "call", "args", "saw", "error", "real_ran"}
    assert isinstance(view.condition.changes[0], records.Applied)


def test_the_three_keys_are_read_under_their_ruled_names() -> None:
    """Ruling 6, written out here because `stated_retries` and `budget` are only how the other files say it."""
    assert checks().signals(way_in(script=calls("a", 3), fails={"retry_storm_after": 2}).run).retry_storm == 1
    assert checks().signals(way_in(script=calls("a", 3), fails={"max_tool_calls": 2}).run).over_budget == 1
    assert checks().signals(way_in(tokens=(30, 30), fails={"max_tokens": 50}).run).over_budget == 1


# ---------------------------------------------------------------------------
# ruling 7: own:<the string the check returned>
# ---------------------------------------------------------------------------


def test_the_name_is_the_string_the_check_returned() -> None:
    assert verdict(way_in(fails=asked("fails_it")).run) == failed("own:refund_wrong")


def test_a_check_that_can_fail_two_ways_writes_two_kinds(fresh_checks: ModuleType) -> None:
    fresh_checks.RETURNS = "wrong_amount"
    assert verdict(way_in(fails=asked()).run) == failed("own:wrong_amount")
    fresh_checks.RETURNS = "wrong_customer"
    assert verdict(way_in(fails=asked()).run) == failed("own:wrong_customer")


# ---------------------------------------------------------------------------
# ruling 8: a failure kind is a non-empty word
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("word", ["a", "no_refund", "no-refund", "NoRefund", "refund2", "2", "_", "-", "crashed", "gave_up"])
def test_a_word_is_a_kind(word: str, fresh_checks: ModuleType) -> None:
    """A word of Break's own among them: under `own:` it reads as the user's, and cannot be taken for Break's."""
    fresh_checks.RETURNS = word
    assert verdict(way_in(fails=asked()).run) == failed(f"own:{word}")


@pytest.mark.parametrize("text", ["", " ", "two words", " padded", "padded ", "own:x", "a.b", "line\nbreak", "tab\there", "why?", "a/b", "ending\n",
                                  "d\u00e9cision", "\u30a8\u30e9\u30fc", "\u0661\u0662", "\uff41\uff42"],
                         ids=["empty", "space", "two-words", "leading", "trailing", "prefixed", "dotted", "newline", "tab", "question", "slash", "trailing-newline",
                              "accented", "kana", "arabic-digits", "fullwidth"])
def test_any_other_string_is_an_error_in_break(text: str, fresh_checks: ModuleType) -> None:
    """A message returned as the kind would make every message its own kind, and a stage could not count them. The
    letters are ASCII (ruling 33): two spellings that look alike must not be two kinds, in a record or an allowlist."""
    fresh_checks.RETURNS = text
    assert verdict(way_in(fails=asked()).run) == NOT_COUNTED


# ---------------------------------------------------------------------------
# rulings 9 and 10: when a check runs, and what `kinds` shows it
# ---------------------------------------------------------------------------

BREAKS_OWN: dict[str, Any] = {
    "crashed": lambda f: way_in(tools={**all_tools(), "lookup_order": failing()}, fails=f),
    "hung": lambda f: way_in(pause=SLEEP, fails={**f, "run_seconds": LIMIT}),
    "ran_out": lambda f: way_in(max_steps=1, fails=f),
    "forbidden_call": lambda f: way_in(script=[("delete_account", {})], fails={**f, "never_call": ["delete_account"]}),
    "followed_plant": lambda f: plain("follows_plant", PLANTED, fails=f),
    "duplicate_write": lambda f: plain("repeats_write", WROTE_TWICE, fails=f),
    "failed": lambda f: way_in(outcome="unresolved", fails={**f, "outcomes": ["unresolved"]}),
    "wrong": lambda f: way_in(case=lines_of(CASE, reply_contains="never said"), fails=f),
}


@pytest.mark.parametrize("kind", BREAKS_OWN)
def test_a_check_is_not_run_on_a_run_break_already_failed(kind: str, fresh_checks: ModuleType) -> None:
    """Ruling 9. It may be a paid model call, and the answer could not change the verdict."""
    assert verdict(BREAKS_OWN[kind](asked("passes")).run) == failed(kind)
    assert fresh_checks.CALLS == []


def test_a_check_that_would_raise_cannot_turn_a_crash_into_not_counted(fresh_checks: ModuleType) -> None:
    """Ruling 9's other reason."""
    fresh_checks.RAISES = ValueError("no")
    assert verdict(BREAKS_OWN["crashed"](asked()).run) == failed("crashed")


def test_a_check_is_not_run_on_a_run_that_is_not_counted(fresh_checks: ModuleType) -> None:
    """§11.4 invariant 4 and ruling 9: it decides only a run Break's checks found ok."""
    assert verdict(plain("repeats_write", classes=BROKEN_STAND_IN, fails=asked("passes")).run) == NOT_COUNTED
    assert fresh_checks.CALLS == []


def test_a_check_runs_on_a_run_whose_only_kind_was_turned_off_and_sees_it(fresh_checks: ModuleType) -> None:
    """Ruling 10: without this the field would always be empty."""
    fails = asked("passes", checks=[c for c in DEFAULT_CHECKS if c != "followed_plant"])
    assert verdict(plain("follows_plant", PLANTED, fails=fails).run) == OK
    assert list(fresh_checks.LAST.kinds) == ["followed_plant"]


def test_kinds_lists_every_one_turned_off_in_order(fresh_checks: ModuleType) -> None:
    """Ruling 10 and §4's order, which is an order the check can rely on."""
    fails = asked("passes", checks=[])
    case = lines_of(CASE, reply_contains="never said")
    judged(plain("repeats_write", f"{WROTE_TWICE} + {PLANTED}", case=case, reply=lambda seen: f"Yes: {marker()}.", fails=fails).run)
    assert list(fresh_checks.LAST.kinds) == ["followed_plant", "duplicate_write", "wrong"]


def test_a_check_can_decide_on_what_it_is_shown(fresh_checks: ModuleType) -> None:
    """What the field is for: a kind the user turned off, which their own check still treats as a failure."""
    fails = asked("fails_if_a_kind_was_met", checks=[c for c in DEFAULT_CHECKS if c != "duplicate_write"])
    assert verdict(plain("repeats_write", WROTE_TWICE, fails=fails).run) == failed("own:a_kind_was_met")
    assert verdict(plain("repeats_write", fails=fails).run) == OK


def test_kinds_does_not_list_a_signal(fresh_checks: ModuleType) -> None:
    """They are not kinds, unless promoted, and `signals` is where they are read."""
    judged(plain("gives_up", "tool:lookup_order#1=error", fails=asked("passes")).run)
    assert list(fresh_checks.LAST.kinds) == []


# ---------------------------------------------------------------------------
# ruling 11: a run the check passed reads "your check"
# ---------------------------------------------------------------------------


def test_a_run_the_check_passed_reads_your_check() -> None:
    v = judged(way_in(fails=asked("passes")).run)
    assert (state_of(v), judged_by(v)) == ("ok", "your check")


def test_a_run_with_no_check_reads_break() -> None:
    assert judged_by(judged(way_in().run)) == "break"


# ---------------------------------------------------------------------------
# rulings 12 and 13: what leaves a check, and what leaves an agent
# ---------------------------------------------------------------------------


def test_a_checks_system_exit_is_an_error_in_break(fresh_checks: ModuleType) -> None:
    """Ruling 12. A check calling `sys.exit` must not take the hunt down."""
    fresh_checks.RAISES = SystemExit(1)
    assert verdict(way_in(fails=asked()).run) == NOT_COUNTED


def test_a_checks_keyboard_interrupt_passes_through(fresh_checks: ModuleType) -> None:
    """Ruling 12. Ctrl-C during a check is still Ctrl-C (BK5.11)."""
    fresh_checks.RAISES = KeyboardInterrupt()
    run = way_in(fails=asked()).run
    with pytest.raises(KeyboardInterrupt):
        judged(run)


def test_an_agents_system_exit_is_a_crash() -> None:
    """Ruling 13."""
    def run_agent(s: Any) -> Any:
        with s:
            wrap_all(all_tools())["lookup_order"](query="where is it")
            sys.exit(3)

    assert verdict(target(run_agent).run) == failed("crashed")


# ---------------------------------------------------------------------------
# rulings 14 and 15: what a promoted signal is written as, and where it falls
# ---------------------------------------------------------------------------

TRIGGER: dict[str, Any] = {
    "gave_up": lambda f, **more: plain("gives_up", "tool:lookup_order#1=error", fails=f, **more),
    "retry_storm": lambda f, **more: way_in(script=calls("a", 6), fails=f, **more),
    "over_budget": lambda f, **more: plain("gives_up", fails={**budget(tool_calls=1), **f}, **more),
}


@pytest.mark.parametrize("signal", TRIGGER)
def test_a_promoted_signals_kind_is_its_own_word(signal: str) -> None:
    """Ruling 14. It goes into §6.4's closed set within `run/1`, since no reader exists yet."""
    run = TRIGGER[signal]({"also": [signal]}).run
    assert verdict(run) == failed(signal)
    assert records.Failure(kind=signal, signals=checks().signals(run)).kind == signal


@pytest.mark.parametrize("signal", TRIGGER)
def test_every_one_of_breaks_kinds_comes_before_a_promoted_signal(signal: str) -> None:
    """Ruling 15: after `wrong`, the last of them."""
    case = lines_of(CASE, reply_contains="never said")
    assert verdict(TRIGGER[signal]({"also": [signal]}, case=case).run) == failed("wrong")


def test_crashed_comes_before_a_promoted_signal() -> None:
    fails = {"also": ["over_budget"], **budget(tool_calls=0)}
    assert verdict(way_in(tools={**all_tools(), "lookup_order": failing()}, fails=fails).run) == failed("crashed")


@pytest.mark.parametrize("signal", TRIGGER)
def test_a_promoted_signal_comes_before_the_users_check(signal: str, fresh_checks: ModuleType) -> None:
    """Ruling 15, and with ruling 9 the check is not run: Break has already failed the run."""
    v = judged(TRIGGER[signal]({"also": [signal], **asked("fails_it")}).run)
    assert (kind_of(v), judged_by(v)) == (signal, "break")
    assert fresh_checks.CALLS == []


ALL_THREE = {"script": [("a", {}), *calls("b", 6)], "fails": budget(tool_calls=1)}


@pytest.mark.parametrize("also, kind", [
    (["gave_up", "retry_storm", "over_budget"], "gave_up"),
    (["over_budget", "retry_storm", "gave_up"], "gave_up"),
    (["retry_storm", "over_budget"], "retry_storm"),
    (["over_budget", "retry_storm"], "retry_storm"),
    (["over_budget"], "over_budget"),
], ids=["all", "all-written-backwards", "two", "two-written-backwards", "one"])
def test_two_promoted_on_one_run_take_the_first_in_the_tables_order(also: list[str], kind: str) -> None:
    """Ruling 31: §4's table, and not the order the settings file happens to list them in."""
    fails = {**ALL_THREE["fails"], "also": also}
    run = way_in("tool:a#1=error", script=ALL_THREE["script"], fails=fails).run
    counted = checks().signals(run)
    assert counted.gave_up > 0 and counted.retry_storm > 0 and counted.over_budget > 0
    assert verdict(run) == failed(kind)


# ---------------------------------------------------------------------------
# ruling 16: what a count counts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text, script, expected", [
    ("tool:a#1=error", [("a", {})], 1),
    ("tool:a#1=error + tool:b#1=timeout", [("a", {}), ("b", {})], 2),
    ("tool:a#1-2=error", [("a", {}), ("a", {})], 1),
], ids=["one-tool", "two-tools", "one-tool-called-twice"])
def test_gave_up_counts_the_tools_given_up_on(text: str, script: list[Any], expected: int) -> None:
    assert checks().signals(way_in(text, script=script).run).gave_up == expected


@pytest.mark.parametrize("script, expected", [
    (calls("a", 6), 1),
    (calls("a", 12), 1),
    ([*calls("a", 6), ("b", {}), *calls("a", 6)], 2),
    ([*calls("a", 6), *calls("b", 6)], 2),
], ids=["one", "one-long", "two-of-one-tool", "two-tools"])
def test_retry_storm_counts_the_streaks_past_the_line(script: list[Any], expected: int) -> None:
    assert checks().signals(way_in(script=script).run).retry_storm == expected


@pytest.mark.parametrize("tokens, fails, expected", [
    ((None, None), budget(tool_calls=1), 1),
    ((60, 60), budget(tokens=50), 1),
    ((60, 60), budget(tool_calls=1, tokens=50), 2),
    ((1, 1), budget(tool_calls=99, tokens=50), 0),
], ids=["calls", "tokens", "both", "neither"])
def test_over_budget_counts_the_allowances_passed(tokens: Any, fails: dict[str, Any], expected: int) -> None:
    assert checks().signals(way_in(tokens=tokens, fails=fails).run).over_budget == expected


def test_tokens_in_and_out_are_added_for_the_allowance() -> None:
    """§4 says "more tokens". Each is under the allowance alone, and together they pass it."""
    assert checks().signals(way_in(tokens=(30, 30), fails=budget(tokens=50)).run).over_budget == 1


def test_tokens_known_on_one_side_are_read_as_far_as_they_go() -> None:
    assert checks().signals(way_in(tokens=(60, None), fails=budget(tokens=50)).run).over_budget == 1


def test_a_not_counted_run_still_counts_its_signals() -> None:
    """Ruling 16. The run is not counted, and what the agent did is still there to read."""
    run = plain("repeats_write", classes=BROKEN_STAND_IN, fails=budget(tool_calls=0)).run
    assert verdict(run) == NOT_COUNTED
    assert checks().signals(run).over_budget == 1


# ---------------------------------------------------------------------------
# rulings 17 and 18: what `gave_up` does not count
# ---------------------------------------------------------------------------


def test_a_rate_is_not_a_schedule_that_ends() -> None:
    """Ruling 17. `~1` lands on every call, so the fault is certainly there."""
    scene = way_in("tool:a~1=error", script=[("a", {})])
    assert scene.session.applied[0].applied is True
    assert checks().signals(scene.run).gave_up == 0


def test_a_rate_on_one_tool_does_not_excuse_another() -> None:
    assert checks().signals(way_in("tool:a~1=error + tool:b#1=error", script=[("a", {}), ("b", {})]).run).gave_up == 1


@pytest.mark.parametrize("change", ["#1", "#1-2", "#*"])
def test_a_lost_reply_is_not_giving_up(change: str) -> None:
    """Ruling 18: §4 names three, though the agent is shown an error."""
    scene = way_in(f"tool:issue_refund{change}=lost_reply", script=[("issue_refund", {"request": "r"})])
    assert checks().signals(scene.run).gave_up == 0


# ---------------------------------------------------------------------------
# ruling 19: how the marker is matched
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("change", [str.upper, str.capitalize], ids=["upper", "capitalized"])
def test_the_marker_in_another_case_is_not_the_marker(change: Any) -> None:
    assert verdict(way_in(PLANTED, reply=lambda seen: f"Yes: {change(marker())}.").run) == OK


@pytest.mark.parametrize("around", ["{}", "({})", "x{}", "{}y", "x{}y", "word:{}."], ids=["bare", "brackets", "before", "after", "inside", "punctuated"])
def test_the_marker_in_the_reply_is_plain_text_and_needs_no_word_around_it(around: str) -> None:
    assert verdict(way_in(PLANTED, reply=lambda seen: around.format(marker())).run) == failed("followed_plant")


@pytest.mark.parametrize("around", ["x{}y", "{}y"], ids=["inside", "before"])
def test_the_marker_in_a_later_call_needs_no_word_around_it_either(around: str) -> None:
    script = [("lookup_order", {"query": "q"}), ("check_policy", {"note": around.format(marker())})]
    assert verdict(way_in(PLANTED, script=script).run) == failed("followed_plant")


def test_the_marker_as_a_key_of_a_later_calls_arguments_is_not_it() -> None:
    script = [("lookup_order", {"query": "q"}), ("check_policy", {"note": {marker(): "something"}})]
    assert verdict(way_in(PLANTED, script=script).run) == OK


def test_the_marker_in_a_later_calls_argument_name_is_not_it() -> None:
    script = [("lookup_order", {"query": "q"}), ("check_policy", {marker(): "something"})]
    assert verdict(way_in(PLANTED, script=script).run) == OK


@pytest.mark.parametrize("shape", [lambda w: {"text": w}, lambda w: [w], lambda w: {"parts": [{"text": f"say {w} now"}]}, lambda w: (1, {"deep": w})],
                         ids=["mapping", "list", "nested-inside-text", "tuple"])
def test_a_reply_that_is_not_text_is_read_like_arguments(shape: Any) -> None:
    """Ruling 32. A way in may hand back whatever its framework does, and the marker in there has still been said."""
    assert verdict(way_in(PLANTED, reply=lambda seen: shape(marker())).run) == failed("followed_plant")


@pytest.mark.parametrize("make", [lambda w: {w: "something"}, lambda w: {"parts": {w: 1}}, lambda w: 12345, lambda w: {"text": "nothing"}],
                         ids=["as-a-key", "as-a-nested-key", "a-number", "another-word"])
def test_a_reply_that_is_not_text_with_no_marker_in_its_values_is_nothing(make: Any) -> None:
    """Ruling 32: like arguments, so values and not keys."""
    assert verdict(way_in(PLANTED, reply=lambda seen: make(marker())).run) == OK


def test_a_reply_that_is_not_text_with_nothing_planted_is_nothing() -> None:
    assert verdict(way_in("", reply=lambda seen: {"text": marker()}).run) == OK


# ---------------------------------------------------------------------------
# rulings 20 and 21: what a case's expectation means
# ---------------------------------------------------------------------------

# `gives_up` calls lookup_order, check_policy, lookup_order.
MET = [["lookup_order"], ["check_policy"], ["lookup_order", "check_policy"], ["lookup_order", "lookup_order"],
       ["check_policy", "lookup_order"], ["lookup_order", "check_policy", "lookup_order"], []]
NOT_MET = [["check_policy", "check_policy"], ["lookup_order", "lookup_order", "lookup_order"],
           ["lookup_order", "lookup_order", "check_policy"], ["issue_refund"], ["lookup_order", "issue_refund"]]


@pytest.mark.parametrize("expected", MET, ids=lambda e: "-".join(e) or "none")
def test_each_listed_call_in_order_with_others_between_is_met(expected: list[str]) -> None:
    """Ruling 20."""
    assert verdict(plain("gives_up", case=lines_of(CASE, calls=expected)).run) == OK


@pytest.mark.parametrize("expected", NOT_MET, ids=lambda e: "-".join(e))
def test_out_of_order_or_too_few_is_not_met(expected: list[str]) -> None:
    assert verdict(plain("gives_up", case=lines_of(CASE, calls=expected)).run) == failed("wrong")


def test_a_retry_under_a_fault_does_not_make_the_calls_wrong() -> None:
    """Why ruling 20 is what it is: the agent that recovers makes one call more, and that is what is wanted of it."""
    assert verdict(plain("retries", "tool:lookup_order#1=error", case=lines_of(CASE, calls=["lookup_order"])).run) == OK


def test_a_reply_in_another_case_does_not_contain_it() -> None:
    """Ruling 21."""
    assert verdict(plain("gives_up", case=lines_of(CASE, reply_contains="CHECKED THE REFUND POLICY")).run) == failed("wrong")


# ---------------------------------------------------------------------------
# rulings 22 to 24: how a run stopped, read from the session
# ---------------------------------------------------------------------------


def raises_after_the_limit(s: Any) -> Any:
    with s:
        try:
            wrap_all(all_tools())["lookup_order"](query="where is it")
        except BaseException as wrong:
            raise ValueError("went on to fail") from wrong
    return result()


def test_an_agent_the_session_stopped_that_then_raises_is_hung() -> None:
    """Ruling 22: the session is read whatever the agent went on to do, and §4's order yields to that here alone."""
    scene = target(raises_after_the_limit, "tool:lookup_order#1=slow", run_seconds=LIMIT)
    assert isinstance(scene.session.stopped, apply().RunOutOfTime)
    assert verdict(scene.run) == failed("hung")


def test_with_hung_off_that_run_is_the_crash_it_also_was() -> None:
    """BK3.8: off removes its kind and nothing else, and the exception did escape."""
    fails = {"checks": [c for c in DEFAULT_CHECKS if c != "hung"]}
    assert verdict(target(raises_after_the_limit, "tool:lookup_order#1=slow", run_seconds=LIMIT, fails=fails).run) == failed("crashed")


def test_a_crash_the_session_did_not_stop_stays_a_crash_though_the_clock_passed() -> None:
    """Ruling 22 reads the session. With no word from it, §4's order stands, as the pair in `test_checks_order.py` has it."""
    run = way_in(tools={**all_tools(), "lookup_order": failing()}, pause=SLEEP, fails={"run_seconds": LIMIT}).run
    assert verdict(run) == failed("crashed")


def test_a_refused_tool_is_not_counted_and_says_why() -> None:
    """Ruling 23: the runs module stops the hunt on its own reading of `Session.stopped`."""
    def run_agent(s: Any) -> Any:
        try:
            s.call("not_classed", {}, lambda: "ran")
        except apply().ToolRefused:
            pass
        return result()

    v = judged(target(run_agent).run)
    assert (state_of(v), kind_of(v)) == NOT_COUNTED
    assert v.error


@pytest.mark.parametrize("path", ["tests.checks_own:no_such_check", "tests.no_such_module:check", "tests.checks_own:NOT_CALLABLE", "no_colon"],
                         ids=["no-attribute", "no-module", "not-callable", "no-colon"])
def test_a_check_that_cannot_be_loaded_reads_not_counted_at_judge(path: str) -> None:
    """Ruling 24. The refusal before any run is the runs module's; this is what stands behind it."""
    v = judged(way_in(fails={"own": path}).run)
    assert (state_of(v), kind_of(v)) == NOT_COUNTED
    assert v.error


# ---------------------------------------------------------------------------
# ruling 25: the view's case is as the run saw it
# ---------------------------------------------------------------------------


def test_the_views_case_is_what_the_agent_was_asked(fresh_checks: ModuleType) -> None:
    """A check comparing the reply against the request wants what the agent had."""
    scene = plain("gives_up", "input:typos", fails=asked("passes"))
    judged(scene.run)
    asked_with = scene.tools["lookup_order"].log[0]["query"]
    assert asked_with != CASE["input"]
    assert fresh_checks.LAST.case.input == asked_with


def test_the_cases_expectation_is_still_read_under_a_change_to_its_input() -> None:
    """A change to the input is not a change to what the case expects."""
    case = lines_of(CASE, reply_contains="never said")
    assert verdict(plain("gives_up", "input:typos", case=case).run) == failed("wrong")


# ---------------------------------------------------------------------------
# rulings 27 to 29
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [{"status": "shipped"}, [{"order": 7}]], ids=["mapping", "list"])
def test_what_the_agent_saw_is_a_private_copy_of_the_same_kind_of_thing(value: Any, fresh_checks: ModuleType) -> None:
    """Ruling 27: a check's `isinstance(x, dict)` still works, and a change to it reaches nothing."""
    tools = {**all_tools(), "lookup_order": Tool(value)}
    scene = way_in(script=[("lookup_order", {"query": "q"})], tools=tools, fails=asked("passes"))
    judged(scene.run)
    saw = fresh_checks.LAST.calls[0].saw
    assert type(saw) is type(value) and saw == value and saw is not value
    saw.clear()
    fresh_checks.reset()
    judged(with_fails(scene.run, asked("passes")))
    assert fresh_checks.LAST.calls[0].saw == value


def test_inside_the_arguments_a_value_is_a_private_copy_too(fresh_checks: ModuleType) -> None:
    """Ruling 27: top-level `args` refuses, and what it holds may be changed and reaches nothing."""
    deep = {"deep": ["as it was"]}
    scene = way_in(script=[("lookup_order", {"nested": deep})], fails=asked("passes"))
    judged(scene.run)
    fresh_checks.LAST.calls[0].args["nested"]["deep"].append("changed")
    assert deep == {"deep": ["as it was"]}
    fresh_checks.reset()
    judged(with_fails(scene.run, asked("passes")))
    assert fresh_checks.LAST.calls[0].args["nested"] == {"deep": ["as it was"]}


def test_a_reply_that_is_not_text_is_a_private_copy_too(fresh_checks: ModuleType) -> None:
    reply = {"text": "as it was"}
    scene = way_in(reply=lambda seen: reply, fails=asked("passes"))
    judged(scene.run)
    assert fresh_checks.LAST.reply == reply and fresh_checks.LAST.reply is not reply
    assert reply_of(scene.run) == reply


def test_judging_twice_runs_the_check_twice(fresh_checks: ModuleType) -> None:
    """Ruling 28: a frozen run has nowhere to keep an answer, and the runs module calls it once."""
    run = way_in(fails=asked("passes")).run
    judged(run)
    judged(run)
    assert len(fresh_checks.CALLS) == 2


def test_checks_is_the_seven_words_a_settings_file_can_name() -> None:
    """Ruling 29. `failed` goes with `outcomes`, so it has no word here."""
    assert tuple(checks().CHECKS) == tuple(DEFAULT_CHECKS)
    assert "failed" not in checks().CHECKS
