"""A way in added without editing the core, and what the `rollout` kind reads from a plain Prove target.

Plan BK5.15 and spec §11.2 invariants 4 and 5: a test-only `Target` written outside the package runs a hunt's control
stage end to end; its outcome, its exception and its step limit map to the kinds the failure check names; and its
records equal the `rollout` kind's for the same scripted agent. Ruling 10 of 2026-11-05 says what the `rollout` kind
reads from the `Episode` a plain Prove target hands back (`evidence/bk5/open-points.md`, all ruled yes).

`tests.hunt_targets.Desk` is that way in, and `tests.agents.WayIn`, the fifth scripted agent, is another.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.hunt_support import (
    AGENT_NAMES,
    case,
    condition,
    desk,
    entry,
    hunt,
    interfaces,
    open_new,
    package_sources,
    record,
    rollout,
    rows,
    settings_for,
    some_cases,
    targets,
    told,
)

OK = ("ok", None)


@pytest.fixture(autouse=True)
def _fresh() -> None:
    targets().reset()


def failed(kind: str) -> tuple[str, str]:
    return ("failed", kind)


def plain_hunt(folder: Path, cases: Any, *, name: str | None = "nightly", **over: Any) -> Any:
    settings = settings_for(folder, **over)
    return hunt().open_hunt(settings, target=rollout(settings), cases=tuple(cases), name=name)


def whole(h: Any, word: str, *, but: tuple[str, ...] = ()) -> list[tuple[Any, ...]]:
    """An arm's rows as two ways in must share them: cell, repeat, seed, outcome, error or not, and the record, less
    any field named in `but`."""
    out = []
    for r in rows(h, word):
        found = {key: value for key, value in record(r).to_dict().items() if key not in but}
        out.append((r["config_hash"], r["replicate_index"], r["seed"], r["outcome"], r["error"] is None, found))
    return sorted(out, key=lambda row: row[:3])


# ---------------------------------------------------------------------------
# BK5.15: a way in from outside the package
# ---------------------------------------------------------------------------


def test_the_way_in_is_written_outside_the_package_and_the_package_does_not_know_it() -> None:
    """Spec §11: "the core never imports an implementation it did not load by name from the settings". The desk is the
    tests' own, it has the protocol's shape, and no module of the package names it."""
    assert targets().Desk.__module__ == "tests.hunt_targets"
    assert isinstance(desk(), interfaces().Target)
    sources = package_sources()
    assert "hunt.py" in sources
    assert not any("hunt_targets" in text or "Desk" in text for text in sources.values())


def test_a_way_in_from_outside_runs_a_control_stage_end_to_end(tmp_path: Path) -> None:
    """BK5.15: "its tools are listed, each call goes through `Session.call`". The way in is asked for its tools and
    for what it can do before any run; then every call the agent made is in a record, in the order the real tools
    ran, and the summary's map is the agent's own."""
    target = desk("repeats_write")
    h = open_new(tmp_path / "runs", target=target, cases=some_cases(2))
    assert target.asked_tools >= 1 and target.asked_capabilities >= 1 and target.runs == 0
    summary = hunt().control(h)
    assert (summary.runs, summary.failed, target.runs) == (4, 0, 4)
    assert {ident: dict(found) for ident, found in summary.calls.items()} == {
        ident: {"lookup_order": 1, "issue_refund": 1} for ident in ("c1", "c2")}
    recorded = [c.tool for r in rows(h, "control") for c in record(r).calls]
    assert sorted(recorded) == sorted(tool for tool, _args in targets().EXECUTED) and len(recorded) == 8
    assert all(c.real_ran and c.change is None for r in rows(h, "control") for c in record(r).calls)


WAYS = [
    ("it returns", {}, {}, OK, "done"),
    ("it raises", {"does": "crash"}, {}, failed("crashed"), None),
    ("it hits its step limit", {"does": "limit"}, {}, failed("ran_out"), "done"),
    ("it reports a failing outcome", {"outcome": "unresolved"}, {"outcomes": ["unresolved"]}, failed("failed"),
     "unresolved"),
    ("it reports a passing outcome", {"outcome": "resolved"}, {"outcomes": ["unresolved"]}, OK, "resolved"),
]


@pytest.mark.parametrize(("keys", "fails", "expected", "outcome"), [w[1:] for w in WAYS], ids=[w[0] for w in WAYS])
def test_a_way_ins_outcome_exception_and_step_limit_map_to_the_kinds(tmp_path: Path, keys: dict[str, Any],
                                                                     fails: dict[str, Any], expected: Any,
                                                                     outcome: str | None) -> None:
    """BK5.15 and spec §11.2 invariant 4: "the way in's own exception path and step limit map to `crashed` and
    `ran_out` through `RunResult`; the way in never returns an outcome word of its own". Its own outcome word is kept
    beside the kind."""
    h = open_new(tmp_path / "runs", cases=[case("a", **keys)], fails=fails)
    hunt().control(h)
    for row in rows(h, "control"):
        assert told(row) == expected
        assert record(row).target_outcome == outcome


SAME = [case("plain"), case("crashes", does="crash"), case("limited", does="limit"),
        case("unresolved", outcome="unresolved"), case("wrong", expect={"reply_contains": "zebra"}),
        case("forbidden", expect={"never_calls": ["lookup_order"]}), case("tokens", tokens=[900, 100])]
CONDITIONS = ["tool:lookup_order#1=error", "tool:lookup_order#1=planted_instruction", "tool:check_policy#1=timeout",
              "tool:issue_refund#1=lost_reply", "input:typos + tool:lookup_order#2=empty", "tool:lookup_order#*=error",
              "env:inventory=empty"]
ENV = {"inventory": ["full", "empty"]}


@pytest.mark.parametrize("agent", AGENT_NAMES)
def test_a_way_ins_records_equal_the_rollout_kinds_for_the_same_scripted_agent(tmp_path: Path, agent: str) -> None:
    """BK5.15 and spec §11.2 invariant 5: "the record a way in produces for a scripted agent equals the `rollout`
    kind's for the same agent". The same desk, reached as a way in and as a plain Prove target, over a control and
    seven conditions on seven cases: every stored row agrees, cell, repeat, seed, outcome and the whole record."""
    cases = [{**one, "agent": agent} for one in SAME]
    over: dict[str, Any] = {"fails": {"outcomes": ["unresolved"], "max_tokens": 500}, "env": ENV}
    ids = [one["id"] for one in cases]
    entries = [entry(text, ids, env=ENV) for text in CONDITIONS]
    through = open_new(tmp_path / "way-in", target=desk(agent), cases=cases, name="nightly", **over)
    plain = plain_hunt(tmp_path / "rollout", cases, **over)
    for h in (through, plain):
        hunt().control(h)
        hunt().run_search(h, entries)
        hunt().run_arm(h, "confirm-1", ids, condition(CONDITIONS[0]), repeats=2)
    for word, count in (("control", 14), ("search", 49), ("confirm-1", 14)):
        assert whole(through, word) == whole(plain, word), word
        assert len(whole(through, word)) == count
    kinds = {record(r).failure.kind for word in ("control", "search") for r in rows(through, word)}
    assert {"crashed", "ran_out", "failed", "wrong", "forbidden_call"} <= kinds, "the comparison saw real failures"


# ---------------------------------------------------------------------------
# the fifth scripted agent: `tests.agents.WayIn`
# ---------------------------------------------------------------------------


def way_in(**over: Any) -> Any:
    from tests.agents import WayIn

    return WayIn(targets().REAL, **over)


def test_the_scripted_way_in_runs_a_control_and_reports_no_outcome_of_its_own(tmp_path: Path) -> None:
    """Plan §2: one scripted agent "speaks only the way-in protocol of spec §11.2". Its three calls are in each
    record, its runs are `ok`, and a way in that reports no outcome leaves `target_outcome` empty (spec §6.4)."""
    h = open_new(tmp_path / "runs", target=way_in())
    summary = hunt().control(h)
    assert (summary.runs, summary.failed) == (6, 0)
    assert {ident: dict(found) for ident, found in summary.calls.items()} == {
        ident: {"lookup_order": 2, "check_policy": 1} for ident in ("c1", "c2", "c3")}
    assert {record(r).target_outcome for r in rows(h, "control")} == {None}


def test_the_scripted_way_ins_step_limit_is_ran_out_and_its_exception_path_is_crashed(tmp_path: Path) -> None:
    """Spec §11.2 invariant 4, on a way in that is not the desk. With a step limit of two its run ends as `limit`.
    A real tool that raises its own exception escapes its agent, and its run ends as `raised`."""
    limited = open_new(tmp_path / "limited", target=way_in(max_steps=2))
    hunt().control(limited)
    assert {told(r) for r in rows(limited, "control")} == {failed("ran_out")}

    def down(**_args: Any) -> str:
        raise LookupError("the service is down")

    from tests.agents import WayIn

    raising = open_new(tmp_path / "raising", target=WayIn({**targets().REAL, "check_policy": down}))
    hunt().control(raising)
    assert {told(r) for r in rows(raising, "control")} == {failed("crashed")}


def test_the_scripted_way_ins_records_equal_the_rollout_kinds_but_for_the_outcome_it_does_not_report(
        tmp_path: Path) -> None:
    """Spec §11.2 invariant 5 again. `gives_up` makes the scripted way in's three calls with the same arguments, so
    where no call fails the two do the same thing; a plain Prove target always reports an outcome and this way in
    reports none, which is the one field left out."""
    entries = [entry(text, ["c1", "c2", "c3"]) for text in ("tool:check_policy#1=empty", "tool:lookup_order#2=cut_off",
                                                           "input:typos", "tool:issue_refund#1=error")]
    through = open_new(tmp_path / "way-in", target=way_in(), name="nightly")
    plain = plain_hunt(tmp_path / "rollout", some_cases())
    for h in (through, plain):
        hunt().control(h)
        hunt().run_search(h, entries)
    for word, count in (("control", 6), ("search", 12)):
        assert whole(through, word, but=("target_outcome",)) == whole(plain, word, but=("target_outcome",))
        assert len(whole(through, word)) == count
    assert {record(r).target_outcome for r in rows(plain, "search")} == {"done"}
    assert any(c.applied for r in rows(through, "search") for c in record(r).condition.changes)


# ---------------------------------------------------------------------------
# what the `rollout` kind reads from the target's `Episode` (ruling 10)
# ---------------------------------------------------------------------------

BARE = "tests.hunt_targets:bare_agent"


@pytest.mark.parametrize(("entry_path", "expect", "expected"), [
    ("tests.hunt_targets:refund_agent", "refund policy", OK),
    ("tests.hunt_targets:refund_agent", "zebra", failed("wrong")),
    (BARE, "refund policy", failed("wrong")),
    (BARE, None, OK),
], ids=["a reply that holds it", "a reply that does not", "no reply handed over", "no reply and nothing expected"])
def test_a_plain_targets_reply_is_what_its_episodes_meta_says(tmp_path: Path, entry_path: str, expect: str | None,
                                                             expected: Any) -> None:
    """Ruling 10: an `Episode` has no reply, so a plain Prove target hands it over as `meta["reply"]`. `gives_up`
    replies "I looked up your order and checked the refund policy."; a target that puts nothing in `meta` has no
    reply for `reply_contains` to find."""
    one = case("a", **({"expect": {"reply_contains": expect}} if expect else {}))
    h = plain_hunt(tmp_path / "runs", [one], entry=entry_path)
    hunt().control(h)
    assert {told(r) for r in rows(h, "control")} == {expected}


@pytest.mark.parametrize(("entry_path", "expected"), [("tests.hunt_targets:refund_agent", failed("followed_plant")),
                                                      (BARE, OK)], ids=["a reply handed over", "no reply handed over"])
def test_a_planted_word_in_a_plain_targets_reply_is_seen_only_if_the_reply_is_handed_over(tmp_path: Path,
                                                                                         entry_path: str,
                                                                                         expected: Any) -> None:
    """Ruling 10: "without this a plain Prove target can never be `followed_plant` in its reply". Planted on the
    agent's last call, the word can only reach its reply."""
    h = plain_hunt(tmp_path / "runs", some_cases(1, agent="follows_plant"), entry=entry_path)
    hunt().run_search(h, [entry("tool:check_policy#1=planted_instruction", ["c1"])])
    assert told(rows(h, "search")[0]) == expected


def test_a_plain_targets_tokens_are_what_its_episodes_meta_says(tmp_path: Path) -> None:
    """Ruling 10: `tokens_in` and `tokens_out`. They price the run and are held to `max_tokens`; a target that hands
    none over costs nothing and is over no allowance."""
    over: dict[str, Any] = {"fails": {"max_tokens": 1000}, "limits": {"input_per_million": 1.0,
                                                                     "output_per_million": 2.0}}
    cases = some_cases(2, tokens=[1000, 500])
    said = plain_hunt(tmp_path / "said", cases, **over)
    silent = plain_hunt(tmp_path / "silent", cases, entry=BARE, **over)
    for h in (said, silent):
        hunt().control(h)
    assert said.budget().dollars_spent == pytest.approx(4 * 0.002)
    assert {record(r).failure.signals.over_budget for r in rows(said, "control")} == {1}
    assert silent.budget().dollars_spent == 0
    assert {record(r).failure.signals.over_budget for r in rows(silent, "control")} == {0}


@pytest.mark.parametrize(("entry_path", "expected"), [("tests.hunt_targets:refund_agent", failed("ran_out")),
                                                      (BARE, OK)], ids=["said", "not said"])
def test_a_plain_targets_own_step_limit_is_what_its_episodes_meta_says(tmp_path: Path, entry_path: str,
                                                                      expected: Any) -> None:
    """Ruling 10: `meta["ended"]` may say `limit`, and is `returned` otherwise."""
    h = plain_hunt(tmp_path / "runs", [case("a", does="limit")], entry=entry_path)
    hunt().control(h)
    assert {told(r) for r in rows(h, "control")} == {expected}


def test_a_plain_targets_outcome_is_its_episodes_and_is_kept_beside_the_kind(tmp_path: Path) -> None:
    """Spec §6.4: "for a bare Prove target, the target's own outcome". BK5.4: "beside them"."""
    cases = [case("a", outcome="resolved"), case("b", outcome="unresolved")]
    h = plain_hunt(tmp_path / "runs", cases, entry=BARE, fails={"outcomes": ["unresolved"]})
    hunt().control(h)
    assert sorted((record(r).case, r["outcome"], record(r).failure.kind, record(r).target_outcome)
                  for r in rows(h, "control")) == [("a", "ok", None, "resolved")] * 2 + [
                      ("b", "failed", "failed", "unresolved")] * 2


def test_a_plain_target_that_raises_is_a_crashed_row(tmp_path: Path) -> None:
    """Spec §5.1: Break "catches an exception from the agent ... because Prove records its own crashes ... as rows
    with no outcome"."""
    h = plain_hunt(tmp_path / "runs", [case("a", does="crash"), case("b", does="exit")])
    hunt().control(h)
    assert {told(r) for r in rows(h, "control")} == {failed("crashed")}


def test_a_plain_target_that_hands_back_no_episode_is_not_counted(tmp_path: Path) -> None:
    """Ruling 10: "something that is no `Episode` is not counted, as a way in that hands back no `RunResult` is". The
    row has no outcome and one line of error, and still carries its record."""
    h = plain_hunt(tmp_path / "runs", some_cases(1), entry="tests.hunt_targets:hands_back_text")
    summary = hunt().control(h)
    assert (summary.runs, summary.not_counted, summary.failed) == (2, 2, 0)
    for row in rows(h, "control"):
        assert row["outcome"] is None and row["error"] and "\n" not in row["error"]
        assert (record(row).stage, record(row).case, record(row).failure.kind) == ("control", "c1", None)
