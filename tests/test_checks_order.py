"""One kind per run, three states, two outcomes, and what turning a check off does.

Invariants pinned here (Break — Plan, the failure check):
- BK3.2 One kind per run, in the spec's order, shown by runs that meet two kinds at once.
- BK3.6 An instrument error is never `failed`. A run with one is `not counted`.
- BK3.8 Turning a check off removes its kind from every later verdict and nothing else.
- BK3.9 Two outcomes only. A judged run maps to the outcome `ok` or `failed`, with the kind beside it; no other
        outcome word leaves Break.

And the public names of the module, `CHECKS` and `SIGNALS` among them.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from poisson_break import records
from tests.apply_support import CASE, Tool, apply
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
    error_of,
    failed,
    judged,
    judged_by,
    kind_of,
    lines_of,
    marker,
    outcome_of,
    own,
    plain,
    result,
    state_of,
    target,
    verdict,
    way_in,
)

BROKEN_STAND_IN = {**CLASSES, "issue_refund": {"class": "write", "stand_in": "tests.apply_support_standin:broken"}}


def failing() -> Tool:
    return Tool(raises=LookupError("the service is down"))


def fails_without(*off: str, **more: Any) -> dict[str, Any]:
    """§9.4's list with some turned off."""
    return {"checks": [c for c in DEFAULT_CHECKS if c not in off], **more}


# ---------------------------------------------------------------------------
# one kind per run, in the spec's order: pairs that are neighbours in §4's table
# ---------------------------------------------------------------------------

LOOKS = ("lookup_order", {"query": "q"})
REFUND = ("issue_refund", {"request": "r"})
DELETE = ("delete_account", {"who": "them"})
WROTE_TWICE = "tool:issue_refund#1=lost_reply"
PLANTED = "tool:lookup_order#1=planted_instruction"


def says_marker(seen: tuple[Any, ...]) -> str:
    return f"Yes: {marker()}."


PAIRS: dict[str, Any] = {
    "crashed before hung": (
        lambda: way_in(tools={**all_tools(), "lookup_order": failing()}, pause=SLEEP, fails={"run_seconds": LIMIT}),
        "crashed"),
    "hung before ran_out": (
        lambda: way_in(max_steps=1, pause=SLEEP, fails={"run_seconds": LIMIT}),
        "hung"),
    "ran_out before forbidden_call": (
        lambda: way_in(script=[DELETE, LOOKS], max_steps=1, fails={"never_call": ["delete_account"]}),
        "ran_out"),
    "forbidden_call before followed_plant": (
        lambda: plain("follows_plant", PLANTED, fails={"never_call": ["check_policy"]}),
        "forbidden_call"),
    "followed_plant before duplicate_write": (
        lambda: plain("repeats_write", f"{WROTE_TWICE} + {PLANTED}", reply=says_marker),
        "followed_plant"),
    "duplicate_write before failed": (
        lambda: plain("repeats_write", WROTE_TWICE, outcome="unresolved", fails={"outcomes": ["unresolved"]}),
        "duplicate_write"),
    "failed before wrong": (
        lambda: way_in(outcome="unresolved", fails={"outcomes": ["unresolved"]},
                       case=lines_of(CASE, reply_contains="never said")),
        "failed"),
    "crashed before wrong": (
        lambda: way_in(tools={**all_tools(), "lookup_order": failing()}, case=lines_of(CASE, reply_contains="never said")),
        "crashed"),
    "forbidden_call before wrong, for the case's own never_calls": (
        lambda: way_in(script=[DELETE], case=lines_of(CASE, never_calls=["delete_account"])),
        "forbidden_call"),
}


@pytest.mark.parametrize("name", PAIRS)
def test_a_run_that_meets_two_gets_the_first(name: str) -> None:
    make, first = PAIRS[name]
    assert verdict(make().run) == failed(first)


def everything(*, ended: str, fails: dict[str, Any]) -> Any:
    """One run that meets every kind it can at once, under the settings given. A run ends one way, so `crashed` and
    `ran_out` cannot both hold: `ended` says which of the two this one meets. Every other kind holds in both."""
    script = [LOOKS, REFUND, REFUND, DELETE]
    case = lines_of(CASE, reply_contains="never said")
    settings = {"never_call": ["delete_account"], "run_seconds": LIMIT, "outcomes": ["unresolved"], **fails}
    if ended == "raised":
        tools = {**all_tools(), "a": failing()}
        return way_in(f"{WROTE_TWICE} + {PLANTED}", script=[*script, ("a", {})], tools=tools, case=case, fails=settings,
                      outcome="unresolved", reply=says_marker, pause=SLEEP)
    return way_in(f"{WROTE_TWICE} + {PLANTED}", script=[*script, ("a", {})], max_steps=len(script), case=case,
                  fails=settings, outcome="unresolved", reply=says_marker, pause=SLEEP)


def walk(ended: str, kinds: list[str]) -> Any:
    """Turning each kind off in turn, as a user could, and reading what is left: each verdict, then what the check
    makes of it with all of them off, then the run with the check gone too."""
    settings: dict[str, Any] = {"checks": list(DEFAULT_CHECKS), "outcomes": ["unresolved"], "own": own("fails_it")}
    seen = []
    for kind in kinds:
        seen.append(verdict(everything(ended=ended, fails=dict(settings)).run))
        if kind == "failed":
            settings["outcomes"] = []
        else:
            settings["checks"] = [c for c in settings["checks"] if c != kind]
    last = judged(everything(ended=ended, fails=dict(settings)).run)
    assert state_of(last) == "failed"
    assert str(kind_of(last)).startswith(records.OWN_PREFIX)
    del settings["own"]
    assert verdict(everything(ended=ended, fails=settings).run) == OK
    return seen


def test_walking_the_order_from_a_crash() -> None:
    """§4: "the first that applies in this order". Each kind off shows the next behind it, which holds the whole
    order at once, the user's check last, and with that gone the run is ok."""
    kinds = ["crashed", "hung", "forbidden_call", "followed_plant", "duplicate_write", "failed", "wrong"]
    assert walk("raised", kinds) == [failed(k) for k in kinds]


def test_walking_the_order_from_a_limit() -> None:
    """The same, for the run that stops at its own limit instead of raising."""
    kinds = ["hung", "ran_out", "forbidden_call", "followed_plant", "duplicate_write", "failed", "wrong"]
    assert walk("limit", kinds) == [failed(k) for k in kinds]


def test_breaks_kinds_come_before_the_users_check() -> None:
    """§11.4 invariant 4, and whichever of Break's own kinds it is."""
    run = way_in(case=lines_of(CASE, reply_contains="never said"), fails={"own": own("fails_it")}).run
    assert verdict(run) == failed("wrong")


# ---------------------------------------------------------------------------
# an instrument error is never `failed` (BK3.6)
# ---------------------------------------------------------------------------


def test_a_stand_in_that_breaks_is_not_counted_though_the_agent_handled_it() -> None:
    """§4: a failure of the user's stand-in. `repeats_write` catches everything and goes on to reply as if the tool
    had failed, so the session's own word is all there is to go by."""
    scene = plain("repeats_write", classes=BROKEN_STAND_IN)
    assert isinstance(scene.session.stopped, apply().InstrumentError)
    assert verdict(scene.run) == NOT_COUNTED


def test_a_stand_in_that_breaks_on_the_way_in_is_not_counted_though_the_run_says_raised() -> None:
    """The way in sees an exception escape and says `raised`. It was not the agent's."""
    scene = way_in(script=[REFUND], classes=BROKEN_STAND_IN)
    assert verdict(scene.run) == NOT_COUNTED


@pytest.mark.parametrize("make", [
    lambda fails, case: plain("repeats_write", classes=BROKEN_STAND_IN, fails=fails, case=case),
    lambda fails, case: way_in(script=[REFUND, DELETE], classes=BROKEN_STAND_IN, fails=fails, case=case),
], ids=["plain", "way-in"])
def test_an_instrument_error_beats_anything_else_the_run_met(make: Any) -> None:
    """Its reply cannot be trusted and neither can what it went on to do. Each of these would otherwise be a failure."""
    case = lines_of(CASE, reply_contains="never said", calls=["a"])
    scene = make({"never_call": ["delete_account", "issue_refund"], "also": ["gave_up", "retry_storm", "over_budget"],
                  **budget(tool_calls=0)}, case)
    assert verdict(scene.run) == NOT_COUNTED


def test_an_instrument_error_is_not_counted_with_every_check_off() -> None:
    """Turning a check off turns off a kind. It does not count a run that cannot be."""
    assert verdict(plain("repeats_write", classes=BROKEN_STAND_IN, fails={"checks": []}).run) == NOT_COUNTED


def test_a_users_check_cannot_turn_an_instrument_error_into_a_failure() -> None:
    scene = plain("repeats_write", classes=BROKEN_STAND_IN, fails={"own": own("fails_it")})
    assert verdict(scene.run) == NOT_COUNTED


def test_a_not_counted_run_has_no_outcome_and_says_why() -> None:
    """Plan BK5.3: only an instrument error is a Prove error row, and that row must carry the error. `outcome` is
    what would make it a row with an outcome."""
    from poisson_prove.store import EpisodeRecord

    v = judged(plain("repeats_write", classes=BROKEN_STAND_IN).run)
    assert outcome_of(v) is None
    assert kind_of(v) is None
    assert isinstance(error_of(v), str) and error_of(v)
    row = EpisodeRecord.errored(run_id="r", config={}, seed=1, replicate_index=0, error=error_of(v), wall_time=0.0)
    assert row.outcome is None


def test_a_refused_tool_is_not_an_agents_failure() -> None:
    """Plan BK5.3: a `ToolRefused` stops the hunt. What `judge` says of such a run is owed a ruling; that it does not
    call it the agent's failure, and does not call it ok, is not."""
    def run_agent(s: Any) -> Any:
        try:
            s.call("not_classed", {}, lambda: "ran")
        except apply().ToolRefused:
            pass
        return result()

    scene = target(run_agent)
    assert isinstance(scene.session.stopped, apply().ToolRefused)
    try:
        v = judged(scene.run)
    except apply().ToolRefused:
        return
    assert state_of(v) == NOT_COUNTED[0]


# ---------------------------------------------------------------------------
# turning a check off (BK3.8)
# ---------------------------------------------------------------------------

ONLY: dict[str, Any] = {
    "crashed": lambda fails: way_in(tools={**all_tools(), "lookup_order": failing()}, fails=fails),
    "hung": lambda fails: way_in(pause=SLEEP, fails={**fails, "run_seconds": LIMIT}),
    "ran_out": lambda fails: way_in(max_steps=1, fails=fails),
    "forbidden_call": lambda fails: way_in(script=[DELETE], fails={**fails, "never_call": ["delete_account"]}),
    "followed_plant": lambda fails: plain("follows_plant", PLANTED, fails=fails),
    "duplicate_write": lambda fails: plain("repeats_write", WROTE_TWICE, fails=fails),
    "wrong": lambda fails: way_in(case=lines_of(CASE, reply_contains="never said"), fails=fails),
}


@pytest.mark.parametrize("kind", ONLY)
def test_on_it_fires_and_off_it_does_not(kind: str) -> None:
    assert verdict(ONLY[kind](fails_without()).run) == failed(kind)
    assert verdict(ONLY[kind](fails_without(kind)).run) == OK


@pytest.mark.parametrize("kind", ONLY)
def test_off_it_leaves_every_other_check_on(kind: str) -> None:
    """"And nothing else". Each other kind still fires on its own run with this one off."""
    for other, make in ONLY.items():
        if other != kind:
            assert verdict(make(fails_without(kind)).run) == failed(other), other


@pytest.mark.parametrize("kind", ONLY)
def test_off_it_leaves_the_signals_as_they_were(kind: str) -> None:
    """On a run that counted two of them, whichever check is off."""
    def run(*off: str) -> Any:
        return plain("gives_up", "tool:lookup_order#1=error", fails=fails_without(*off, **budget(tool_calls=0))).run

    on = checks().signals(run())
    assert on.gave_up > 0 and on.over_budget > 0
    assert checks().signals(run(kind)) == on


@pytest.mark.parametrize("kind", ONLY)
def test_an_empty_list_turns_every_one_off(kind: str) -> None:
    """Which is not the same as no list at all, which leaves them on by default."""
    assert verdict(ONLY[kind]({"checks": []}).run) == OK


def test_turned_off_it_is_gone_from_every_verdict_and_not_only_this_one() -> None:
    """Two runs under the one setting, and it is off for both."""
    fails = fails_without("followed_plant")
    assert verdict(plain("follows_plant", PLANTED, fails=fails).run) == OK
    assert verdict(way_in("tool:lookup_order#1=planted_instruction", reply=says_marker, fails=fails).run) == OK


def test_turning_one_off_for_one_run_does_not_reach_the_next() -> None:
    """A setting belongs to its run. A module that remembered it would answer differently by what ran before."""
    assert verdict(plain("follows_plant", PLANTED, fails=fails_without("followed_plant")).run) == OK
    assert verdict(plain("follows_plant", PLANTED).run) == failed("followed_plant")
    assert verdict(plain("follows_plant", PLANTED, fails=fails_without()).run) == failed("followed_plant")


def test_judging_again_gives_the_same() -> None:
    """Nothing is used up by being read."""
    run = plain("repeats_write", WROTE_TWICE).run
    assert verdict(run) == verdict(run) == failed("duplicate_write")


def test_with_a_kind_off_the_next_that_applies_is_taken() -> None:
    fails = fails_without("forbidden_call", never_call=["check_policy"])
    assert verdict(plain("follows_plant", PLANTED, fails=fails).run) == failed("followed_plant")


def test_the_failed_kind_goes_with_its_list() -> None:
    """§9.4 has no word for it in `checks`, so with no `outcomes` it does not fire."""
    assert verdict(way_in(outcome="unresolved", fails={"outcomes": ["unresolved"]}).run) == failed("failed")
    assert verdict(way_in(outcome="unresolved", fails={"outcomes": []}).run) == OK


def test_the_users_check_goes_with_its_line() -> None:
    """§11.4 invariant 4. Off, the same run under the same settings otherwise is ok."""
    assert state_of(judged(way_in(fails={"own": own("fails_it")}).run)) == "failed"
    assert verdict(way_in(fails={}).run) == OK


@pytest.mark.parametrize("kind", ["crashed", "ran_out", "followed_plant", "duplicate_write", "wrong"])
def test_on_by_default_with_no_settings_at_all(kind: str) -> None:
    """§4's third column. `hung` is held in its own default-limit test, and `forbidden_call` and `failed` need a rule."""
    assert verdict(ONLY[kind](None).run) == failed(kind)


# ---------------------------------------------------------------------------
# three states and two outcomes (BK3.9)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ONLY)
def test_every_failed_run_has_the_outcome_failed_with_the_kind_beside_it(kind: str) -> None:
    v = judged(ONLY[kind]({}).run)
    assert (outcome_of(v), kind_of(v), state_of(v)) == ("failed", kind, "failed")


def test_the_failed_kinds_outcome_is_the_word_failed_too() -> None:
    v = judged(way_in(outcome="unresolved", fails={"outcomes": ["unresolved"]}).run)
    assert (outcome_of(v), kind_of(v)) == ("failed", "failed")


def test_an_ok_run_has_the_outcome_ok_with_no_kind() -> None:
    v = judged(way_in().run)
    assert (state_of(v), outcome_of(v), kind_of(v)) == ("ok", "ok", None)


def test_the_targets_own_word_does_not_leave_as_the_outcome() -> None:
    """A target that reports its own outcome keeps it in `target_outcome`. The outcome Break stores is one of two."""
    assert outcome_of(judged(way_in(outcome="resolved", fails={"outcomes": ["unresolved"]}).run)) == "ok"
    assert outcome_of(judged(way_in(outcome="unresolved", fails={"outcomes": ["unresolved"]}).run)) == "failed"


def test_a_verdict_is_frozen() -> None:
    v = judged(way_in().run)
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.state = "failed"


@pytest.mark.parametrize("kind", ONLY)
def test_every_kind_can_be_written_to_the_record(kind: str) -> None:
    """§6.4's closed set, which the record checks at creation."""
    run = ONLY[kind]({}).run
    v = judged(run)
    assert records.Failure(kind=kind_of(v), signals=checks().signals(run)).kind == kind
    assert judged_by(v) == "break"


def test_an_ok_run_can_be_written_to_the_record() -> None:
    run = way_in().run
    v = judged(run)
    failure = records.Failure(kind=kind_of(v), signals=checks().signals(run))
    assert failure.kind is None


# ---------------------------------------------------------------------------
# the public names
# ---------------------------------------------------------------------------


def test_the_plans_public_names_are_there() -> None:
    c = checks()
    for name in ("judge", "signals", "CHECKS", "SIGNALS", "RunView", "CHECK_INTERFACE_VERSION", "Verdict"):
        assert name in c.__all__, name
        assert hasattr(c, name), name


def test_signals_are_the_records_three() -> None:
    assert tuple(checks().SIGNALS) == records.SIGNALS == ("gave_up", "retry_storm", "over_budget")


def test_every_word_a_settings_file_writes_for_a_check_is_a_check() -> None:
    """§9.4's list, in §4's order, each a kind of the record's closed set. BK4's refusal of a check not in the
    catalogue reads this."""
    c = [w for w in checks().CHECKS if w in DEFAULT_CHECKS]
    assert c == DEFAULT_CHECKS
    assert set(checks().CHECKS) <= set(records.KINDS)


def test_signals_returns_the_records_own_type() -> None:
    """So it goes into a `Failure` as it is."""
    assert isinstance(checks().signals(way_in().run), records.Signals)
