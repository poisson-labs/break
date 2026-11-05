"""What a stage stores: each arm a Prove run, each run a row Break decided, each row carrying its record.

Plan BK5.1 (an arm is a Prove run, read by Prove's own `Store`), BK5.3 (Break decides the outcome), BK5.4 (what a run
records, and where), BK5.5 (arms line up by case), BK5.8 (a bare Prove target's own `cfg`), BK5.14 (seeds), BK5.16 (the
stage in every row and in `hunt.json`), and search's BK6.13 from this side (the selection reaches the record), with the
shapes of rulings 2, 3, 5, 10, 11 and 16 to 22 of 2026-11-05 (`evidence/bk5/open-points.md`, all ruled yes).

Every row here is read back through `poisson_prove.store.Store`, never through the runs module, so what is held is
what another tool would find on disk.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from poisson_prove.executor import derive_seed
from poisson_prove.store import config_hash

from tests.hunt_support import (
    AGENT_NAMES,
    apply_module,
    arms,
    by_case,
    case,
    changes,
    condition,
    desk,
    entry,
    hunt,
    hunt_json,
    name_of,
    open_new,
    record,
    records,
    rollout,
    rows,
    settings_for,
    some_cases,
    store_of,
    targets,
    told,
)

OK = ("ok", None)
NOT_COUNTED = (None, None)


@pytest.fixture(autouse=True)
def _fresh() -> None:
    targets().reset()


def root(tmp_path: Path) -> Path:
    return tmp_path / "break-runs"


def failed(kind: str) -> tuple[str, str]:
    return ("failed", kind)


def arm(h: Any, word: str = "control", cases: Any = None, text: str = "", *, repeats: int = 1, **more: Any) -> Any:
    ids = [c["id"] for c in h.cases] if cases is None else list(cases)
    return hunt().run_arm(h, word, ids, condition(text), repeats=repeats, **more)


# ---------------------------------------------------------------------------
# BK5.1: an arm is a Prove run, named `<hunt>-<arm>`
# ---------------------------------------------------------------------------


def test_an_arm_is_a_prove_run_in_the_hunts_store_read_by_proves_own_store(tmp_path: Path) -> None:
    """BK5.1, spec §6.1. One run, in `store/`, under the readable name, holding one row per case and repeat, each
    with an outcome, as Prove's own tally counts them."""
    h = open_new(root(tmp_path), name="refund-agent-1")
    arm(h, repeats=2)
    assert arms(h) == ["refund-agent-1-control"]
    assert (h.store / "refund-agent-1-control").is_dir()
    tally = store_of(h).tally("refund-agent-1-control")
    assert (tally.rows, tally.with_outcome, tally.no_outcome) == (6, 6, 0)
    assert {row["run_id"] for row in rows(h, "control")} == {"refund-agent-1-control"}


@pytest.mark.parametrize(("word", "stage"), [("control", "control"), ("confirm-control", "confirm"),
                                             ("confirm-1", "confirm"), ("reference-2", "reference"),
                                             ("recheck-1-2", "recheck")])
def test_an_arm_is_named_for_the_hunt_and_its_word_and_its_stage_is_the_words_first_part(tmp_path: Path, word: str,
                                                                                         stage: str) -> None:
    """BK5.1: "named `<hunt>-<arm>`"; spec §6.1's list of arms. Ruling 3: the stage is the arm's first word, so
    `confirm-control` is the confirm stage's arm with no change."""
    h = open_new(root(tmp_path), name="nightly")
    arm(h, word, ["c1"])
    assert arms(h) == [f"nightly-{word}"]
    found = record(rows(h, word)[0])
    assert (found.arm, found.stage, found.hunt) == (f"nightly-{word}", stage, "nightly")


@pytest.mark.parametrize("word", ["search", "shrink", "warmup", "controls", "", "Control", "1-control"])
def test_an_arm_whose_first_word_is_no_stage_of_an_arm_is_refused_before_any_run(tmp_path: Path, word: str) -> None:
    """Ruling 3: `control`, `confirm`, `reference` and `recheck` name an arm. `search` and `shrink` are stages
    `run_search` stores, and a word that is no stage would leave a row with no stage to carry."""
    target = desk()
    h = open_new(root(tmp_path), target=target)
    with pytest.raises(hunt().HuntError):
        arm(h, word, ["c1"])
    assert arms(h) == [] and target.runs == 0


def test_a_case_the_hunt_does_not_have_is_refused_before_any_run(tmp_path: Path) -> None:
    """Ruling 3: `cases` is case ids, and one the hunt was not opened with is refused, the known ones beside it unrun."""
    target = desk()
    h = open_new(root(tmp_path), target=target)
    with pytest.raises(hunt().HuntError):
        arm(h, "control", ["c1", "nobody"])
    with pytest.raises(hunt().HuntError):
        hunt().run_search(h, [entry("tool:lookup_order#1=error", ["c1"]), entry("input:typos", ["nobody"])])
    assert target.runs == 0 and all(store_of(h).count(run) == 0 for run in arms(h))


# ---------------------------------------------------------------------------
# what `run_arm` and `run_search` hand back (rulings 2, 3, 5)
# ---------------------------------------------------------------------------


def test_run_arm_hands_back_one_row_per_run_in_the_order_run(tmp_path: Path) -> None:
    """Ruling 3. Case by case in the order given, each its repeats, and each row says what the stored row says."""
    h = open_new(root(tmp_path), cases=[case("a"), case("b", does="crash"), case("c")])
    handed = arm(h, "control", ["c", "b", "a"], repeats=2)
    assert isinstance(handed, list)
    assert [r.case for r in handed] == ["c", "c", "b", "b", "a", "a"]
    assert [(r.outcome, r.kind) for r in handed] == [OK, OK, failed("crashed"), failed("crashed"), OK, OK]
    assert all(r.condition == condition("") for r in handed)
    stored = by_case(rows(h, "control"))
    assert {ident: sorted(r["seed"] for r in found) for ident, found in stored.items()} == {
        ident: sorted(r.seed for r in handed if r.case == ident) for ident in "abc"}
    assert len({r.seed for r in handed}) == 6


def test_a_row_handed_back_is_frozen_and_made_by_keyword(tmp_path: Path) -> None:
    """Ruling 2: `RunRow` is frozen and keyword-only, with the five fields."""
    made = hunt().RunRow(condition=condition("input:typos"), case="c1", seed=7, outcome="failed", kind="wrong")
    assert (made.case, made.seed, made.outcome, made.kind) == ("c1", 7, "failed", "wrong")
    with pytest.raises(TypeError):
        hunt().RunRow(condition(""), "c1", 7, "ok", None)
    with pytest.raises(Exception):  # noqa: B017 - which exception a frozen object raises is the build's
        made.outcome = "ok"
    assert made.outcome == "failed"
    h = open_new(root(tmp_path))
    assert type(arm(h, "control", ["c1"])[0]) is hunt().RunRow


def test_a_row_not_counted_is_handed_back_in_those_words(tmp_path: Path) -> None:
    """Ruling 2: the three outcome words are `ok`, `failed` and `not counted`, the words search's `SeenRun` takes."""
    h = open_new(root(tmp_path), cases=[case("a", does="instrument"), case("b")])
    assert [(r.case, r.outcome, r.kind) for r in arm(h)] == [("a", "not counted", None), ("b", "ok", None)]


def test_the_repeats_of_an_arm_are_given_by_keyword(tmp_path: Path) -> None:
    h = open_new(root(tmp_path))
    with pytest.raises(TypeError):
        hunt().run_arm(h, "control", ["c1"], condition(""), 2)
    assert arms(h) == []


def test_run_search_runs_each_entry_on_its_cases_in_order_and_stores_them_in_the_search_run(tmp_path: Path) -> None:
    """Ruling 2, spec §6.1: "the search stage is one Prove run"."""
    target = desk()
    h = open_new(root(tmp_path), target=target)
    entries = [entry("tool:lookup_order#1=error", ["c2", "c1"]), entry("input:typos", ["c3"]),
               entry("tool:check_policy#1=timeout", ["c1", "c2", "c3"])]
    handed = hunt().run_search(h, entries)
    assert isinstance(handed, list)
    assert [(name_of(r.condition), r.case) for r in handed] == [
        ("tool:lookup_order#1=error", "c2"), ("tool:lookup_order#1=error", "c1"), ("input:typos", "c3"),
        ("tool:check_policy#1=timeout", "c1"), ("tool:check_policy#1=timeout", "c2"),
        ("tool:check_policy#1=timeout", "c3")]
    assert [(name_of(t.condition), t.case["id"]) for t in target.handed] == [(name_of(r.condition), r.case)
                                                                             for r in handed]
    assert arms(h) == [f"{h.name}-search"]
    stored = {(record(r).condition.name, record(r).case): r for r in rows(h, "search")}
    assert len(stored) == 6
    for r in handed:
        assert stored[(name_of(r.condition), r.case)]["seed"] == r.seed
        assert told(stored[(name_of(r.condition), r.case)]) == (r.outcome, r.kind)
    assert {record(r).stage for r in stored.values()} == {"search"}
    assert {record(r).arm for r in stored.values()} == {f"{h.name}-search"}


def test_a_condition_given_by_its_name_runs_as_the_condition_itself(tmp_path: Path) -> None:
    """Ruling 2: an entry's `condition` is a `Condition` or its canonical name. What is handed back is the object."""
    h = open_new(root(tmp_path))
    by_text = hunt().run_search(h, [entry("tool:lookup_order#1=error", ["c1"], as_text=True)])
    assert by_text[0].condition == condition("tool:lookup_order#1=error")
    assert record(rows(h, "search")[0]).condition.name == "tool:lookup_order#1=error"


def test_each_search_runs_record_holds_the_selection_of_the_entry_that_produced_it(tmp_path: Path) -> None:
    """Search's BK6.13, and BK5.4: "the selection (the strategy and the probability it gave the condition)". Two
    entries with different strategies and probabilities, so a record that took the first entry's, or the settings'
    strategy, or 1, is caught."""
    h = open_new(root(tmp_path))
    entries = [entry("tool:lookup_order#1=error", ["c1", "c2"], strategy="random", probability=0.125),
               entry("input:typos", ["c1"], strategy="tests.strategies:Fixed", probability=0.5)]
    hunt().run_search(h, entries)
    found = {(record(r).condition.name, record(r).case): record(r).selection for r in rows(h, "search")}
    assert found == {("tool:lookup_order#1=error", "c1"): entries[0].selection,
                     ("tool:lookup_order#1=error", "c2"): entries[0].selection,
                     ("input:typos", "c1"): entries[1].selection}
    assert found[("input:typos", "c1")] == records().Selection(strategy="tests.strategies:Fixed", probability=0.5)


@pytest.mark.parametrize("strategy", ["screen", "random", "my_pkg.search:Mine"])
def test_an_arms_rows_carry_the_settings_strategy_at_probability_one(tmp_path: Path, strategy: str) -> None:
    """Spec §6.4: the probability is "1 for the control". Ruling 3: every row of an arm carries the settings' strategy
    at 1, under a condition or not, so a reader weighting by probability leaves arms out by their stage."""
    h = open_new(root(tmp_path), search={"strategy": strategy})
    arm(h, "control", ["c1"])
    arm(h, "confirm-1", ["c1"], "tool:lookup_order#1=error")
    for word in ("control", "confirm-1"):
        assert record(rows(h, word)[0]).selection == records().Selection(strategy=strategy, probability=1)


def test_shrinks_rows_go_to_a_prove_run_of_their_own_at_probability_one_of_the_candidates_strategy(tmp_path: Path) -> None:
    """Ruling 17 and search's rulings 25 and 26. Shrink may run a pair the search already ran, so its rows are a run
    of their own, `<hunt>-shrink`, with the stage `shrink` and the selection the caller hands in."""
    target = desk()
    h = open_new(root(tmp_path), target=target)
    pair = "tool:lookup_order#1=error"
    hunt().run_search(h, [entry(pair, ["c1"], strategy="random", probability=0.25)])
    handed = hunt().run_search(h, [entry(pair, ["c1"], strategy="random", probability=1)], stage="shrink")
    assert target.runs == 2, "the pair is run again for shrink, which is its own stage"
    assert arms(h) == [f"{h.name}-search", f"{h.name}-shrink"]
    again = record(rows(h, "shrink")[0])
    assert (again.stage, again.arm) == ("shrink", f"{h.name}-shrink")
    assert again.selection == records().Selection(strategy="random", probability=1)
    assert record(rows(h, "search")[0]).selection.probability == 0.25
    assert handed[0].seed == rows(h, "shrink")[0]["seed"] != rows(h, "search")[0]["seed"]


@pytest.mark.parametrize("stage", ["control", "confirm", "reference", "recheck", "Search", ""])
def test_run_search_stores_only_the_search_and_the_shrink_stage(tmp_path: Path, stage: str) -> None:
    target = desk()
    h = open_new(root(tmp_path), target=target)
    with pytest.raises(hunt().HuntError):
        hunt().run_search(h, [entry("input:typos", ["c1"])], stage=stage)
    assert target.runs == 0


def test_a_pair_the_run_already_holds_is_not_run_again_and_its_stored_row_comes_back(tmp_path: Path) -> None:
    """Ruling 18: a cell is run once in an arm. Asked again, in a later call or twice in one, it is not run, and the
    row handed back is the stored one."""
    target = desk()
    h = open_new(root(tmp_path), target=target)
    one = entry("tool:lookup_order#1=error", ["c1", "c2"])
    first = hunt().run_search(h, [one])
    second = hunt().run_search(h, [entry("input:typos", ["c1"]), one, one])
    assert target.runs == 3
    assert second[1:] == first + first
    assert store_of(h).count(f"{h.name}-search") == 3


def test_an_arm_asked_for_again_runs_nothing_and_hands_back_its_rows(tmp_path: Path) -> None:
    """Ruling 18, for an arm: the same call on a finished arm is the arm as stored."""
    target = desk()
    h = open_new(root(tmp_path), target=target, cases=[case("a"), case("b", does="crash")])
    first = arm(h, repeats=2)
    assert arm(h, repeats=2) == first and target.runs == 4
    assert store_of(h).count(f"{h.name}-control") == 4


def test_an_arm_asked_for_again_under_something_else_is_refused(tmp_path: Path) -> None:
    """Ruling 18's other side: an arm is one condition on its cases, and a second call cannot make it two."""
    target = desk()
    h = open_new(root(tmp_path), target=target)
    arm(h, "confirm-1", ["c1", "c2"], "tool:lookup_order#1=error")
    for cases, text, repeats in ((["c1", "c2"], "input:typos", 1), (["c1"], "tool:lookup_order#1=error", 1),
                                 (["c1", "c2"], "tool:lookup_order#1=error", 2)):
        with pytest.raises(hunt().HuntError):
            arm(h, "confirm-1", cases, text, repeats=repeats)
    assert target.runs == 2 and store_of(h).count(f"{h.name}-confirm-1") == 2


def test_no_entries_is_no_run(tmp_path: Path) -> None:
    target = desk()
    h = open_new(root(tmp_path), target=target)
    assert hunt().run_search(h, []) == [] and target.runs == 0


def test_progress_is_told_after_each_run_with_how_many_are_done_of_how_many(tmp_path: Path) -> None:
    """Ruling 5: `on_progress(done, total)`, after each run, of the runs asked for in this call."""
    target = desk()
    h = open_new(root(tmp_path), target=target)
    seen: list[tuple[int, int, int]] = []
    arm(h, repeats=2, on_progress=lambda done, total: seen.append((done, total, target.runs)))
    assert seen == [(i, 6, i) for i in range(1, 7)]
    seen.clear()
    hunt().run_search(h, [entry("input:typos", ["c1", "c2"]), entry("tool:lookup_order#1=error", ["c3"])],
                      on_progress=lambda done, total: seen.append((done, total, target.runs - 6)))
    assert seen == [(1, 3, 1), (2, 3, 2), (3, 3, 3)]


# ---------------------------------------------------------------------------
# what is refused before any run of a call (BK5.17, ruling 30; spec §3.6)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "kind", "fact"), [
    ("user:repeats@1", "NeedsAdapter", ("change", "user:repeats@1")),
    ("model:error#1", "NeedsAdapter", ("change", "model:error#1")),
    ("tool:lookup_order#1=lost_reply", "ToolRefused", ("tool", "lookup_order")),
    ("tool:send_email#1=error", "ToolRefused", ("tool", "send_email")),
    ("tool:unknown_tool#1=error", "ToolRefused", ("tool", "unknown_tool")),
])
def test_a_condition_the_way_in_or_a_session_refuses_is_refused_before_any_run_of_the_call(
        tmp_path: Path, text: str, kind: str, fact: tuple[str, str]) -> None:
    """BK5.17: "refused ... in one line, never mid-hunt", and ruling 30: each condition handed to a stage is asked
    before any run of that call, so nothing of the call is stored. The refusals are the catalogue's and the
    session's own, with their facts (ruling 8): a change the way in cannot make, `lost_reply` on a read, a tool that
    is off, a tool with no line."""
    wanted = getattr(changes() if kind == "NeedsAdapter" else apply_module(), kind)
    tools = {"lookup_order": "read", "check_policy": "read", "issue_refund": {"class": "write", "repeatable": True},
             "send_email": "off"}
    target = desk()
    h = open_new(root(tmp_path), target=target, tools=tools)
    with pytest.raises(wanted) as refused:
        arm(h, "confirm-1", ["c1", "c2"], text)
    assert getattr(refused.value, fact[0]) == fact[1]
    with pytest.raises(wanted):
        hunt().run_search(h, [entry("input:typos", ["c1", "c2"]), entry(text, ["c1"])])
    assert target.runs == 0, "the entry before the refused one did not run either"
    assert all(store_of(h).count(run) == 0 for run in arms(h))


# ---------------------------------------------------------------------------
# BK5.3: Break decides the outcome
# ---------------------------------------------------------------------------

DECIDED = [
    ("returns", {}, {}, OK),
    ("raises", {"does": "crash"}, {}, failed("crashed")),
    ("exits", {"does": "exit"}, {}, failed("crashed")),
    ("hits its own step limit", {"does": "limit"}, {}, failed("ran_out")),
    ("comes back past the limit", {"nap": 0.25}, {"run_seconds": 0.1}, failed("hung")),
    ("lingers past the limit after its last call", {"linger": 0.25}, {"run_seconds": 0.1}, failed("hung")),
    ("reports an outcome the settings list", {"outcome": "unresolved"}, {"outcomes": ["unresolved"]},
     failed("failed")),
    ("reports an outcome the settings do not list", {"outcome": "unresolved"}, {}, OK),
    ("misses what the case expects", {"expect": {"reply_contains": "zebra"}}, {}, failed("wrong")),
    ("calls a tool the settings forbid", {}, {"never_call": ["check_policy"]}, failed("forbidden_call")),
    ("raises with every check off", {"does": "crash"}, {"checks": []}, OK),
    ("the way in breaks", {"does": "instrument"}, {}, NOT_COUNTED),
]


@pytest.mark.parametrize(("keys", "fails", "expected"), [d[1:] for d in DECIDED], ids=[d[0] for d in DECIDED])
def test_break_decides_each_rows_outcome_from_what_the_run_did(tmp_path: Path, keys: dict[str, Any],
                                                              fails: dict[str, Any], expected: Any) -> None:
    """BK5.3: every run that reaches the store is `ok` or `failed` with its kind; an exception from the agent and a
    run past the wall-clock limit are `failed` rows, never rows with no outcome; only an instrument error is. The
    `[fails]` table reaches the failure check as the settings state it (BK5.8)."""
    h = open_new(root(tmp_path), cases=[case("plain"), case("odd", **keys)], fails=fails)
    arm(h)
    found = by_case(rows(h, "control"))
    assert told(found["odd"][0]) == expected
    assert told(found["plain"][0]) == (OK if "never_call" not in fails else failed("forbidden_call"))


def test_no_outcome_word_but_ok_and_failed_reaches_proves_outcome_column(tmp_path: Path) -> None:
    """BK3.9 through this module, spec §6.1: "the outcome Prove sees is only `ok` or `failed`". The target's own words
    stay in the record."""
    cases = [case("a", outcome="resolved"), case("b", outcome="unresolved"), case("c", outcome="escalated"),
             case("d", does="crash")]
    h = open_new(root(tmp_path), cases=cases, fails={"outcomes": ["unresolved", "escalated"]})
    arm(h)
    found = {ident: got[0] for ident, got in by_case(rows(h, "control")).items()}
    assert {ident: row["outcome"] for ident, row in found.items()} == {"a": "ok", "b": "failed", "c": "failed",
                                                                         "d": "failed"}
    assert {ident: record(row).target_outcome for ident, row in found.items()} == {
        "a": "resolved", "b": "unresolved", "c": "escalated", "d": None}


def test_a_row_not_counted_is_the_only_row_with_no_outcome_and_proves_timeout_marks_none(tmp_path: Path) -> None:
    """BK5.3: "only an instrument error is a Prove error row", and Prove's own timeout is not used, so no row is
    marked timed out, a run past its limit included. The error is one line, not a traceback (ruling 20)."""
    cases = [case("fine"), case("crash", does="crash"), case("late", nap=0.25), case("broken", does="instrument")]
    h = open_new(root(tmp_path), cases=cases, fails={"run_seconds": 0.1})
    arm(h)
    tally = store_of(h).tally(f"{h.name}-control")
    assert (tally.rows, tally.with_outcome, tally.no_outcome, tally.timed_out) == (4, 3, 1, 0)
    found = {ident: got[0] for ident, got in by_case(rows(h, "control")).items()}
    assert [ident for ident, row in found.items() if row["outcome"] is None] == ["broken"]
    assert all(row["error"] is None for ident, row in found.items() if ident != "broken")
    error = found["broken"]["error"]
    assert isinstance(error, str) and error.strip() and "\n" not in error


def test_the_users_check_is_asked_once_for_each_run_it_may_judge(tmp_path: Path) -> None:
    """BK5.3: "calls `judge` once per run"; spec §11.4 invariant 5: the check "is run once per run". It may be a paid
    model call, and it is not run on a run Break already failed."""
    cases = [case("a"), case("b", does="crash"), case("c")]
    h = open_new(root(tmp_path), cases=cases, fails={"own": "tests.hunt_targets:counting_check"})
    arm(h, repeats=2)
    assert sorted(targets().CHECKED) == ["a", "a", "c", "c"]
    judged = {ident: {record(r).judged_by for r in got} for ident, got in by_case(rows(h, "control")).items()}
    assert judged == {"a": {"your check"}, "b": {"break"}, "c": {"your check"}}


def test_the_session_the_limits_and_the_failure_check_get_one_run_time(tmp_path: Path) -> None:
    """Failure check's build note and ruling 11: the session, the `Limits` a way in is handed and `[fails]` hold the
    same number of seconds. A run that naps past it and makes no further call is `hung` by the clock alone, which
    only holds if the check was given the number too."""
    target = desk("retries")
    h = open_new(root(tmp_path), target=target, cases=[case("a")], fails={"run_seconds": 45})
    arm(h)
    handed = target.handed[0]
    assert handed.run_seconds == 45
    assert isinstance(handed.limits, hunt().Limits) and handed.limits.run_seconds == 45
    with pytest.raises(TypeError):
        hunt().Limits(45)


def test_the_session_is_told_what_the_way_in_can_do(tmp_path: Path) -> None:
    """Spec §11.2: a session with no capabilities given is "a plain Prove target's, tool calls only", and refuses a
    conversation move when it is made. A way in that can drive a conversation has said so, and the runs module hands
    that to each run's session, so the move is run and recorded and not refused."""
    target = desk(can={"conversation": True})
    one = {"id": "a", "input": "Where is order 7?", "turns": ["Where is order 7?", "And when does it arrive?"]}
    h = open_new(root(tmp_path), target=target, cases=[one], vary={"conversation": ["repeats"]})
    arm(h, "confirm-1", ["a"], "user:repeats@2")
    assert target.runs == 1
    row = rows(h, "confirm-1")[0]
    assert row["outcome"] == "ok"
    assert [(c.surface, c.fault, c.call) for c in record(row).condition.changes] == [("user", "repeats", "@2")]


def test_the_way_in_the_check_and_the_record_see_the_case_as_the_run_saw_it(tmp_path: Path) -> None:
    """BK5.8: `watch` is handed "the case as `Session.case` gave it, since that is what a user's check is shown". An
    input operator's work reaches the way in and the check alike, and the record says it applied."""
    target = desk()
    question = "Where is order 7 and when will it arrive? Please refund it if it is late."
    h = open_new(root(tmp_path), target=target, cases=[{"id": "a", "input": question}],
                 fails={"own": "tests.hunt_targets:counting_check"}, vary={"inputs": ["cut_short"]})
    arm(h, "confirm-1", ["a"], "input:cut_short")
    seen = target.handed[0].case["input"]
    assert seen != question and question.startswith(seen)
    assert targets().CHECKED_INPUTS == [seen]
    change = record(rows(h, "confirm-1")[0]).condition.changes[0]
    assert (change.surface, change.fault, change.applied) == ("input", "cut_short", True)
    assert h.cases[0]["input"] == question, "the hunt's own case is left as it was"


def test_the_planted_word_is_the_hunts_and_the_cases_and_reaches_the_failure_check(tmp_path: Path) -> None:
    """Spec §6.4: the marker is "recoverable from `hunt` and `case`, by `marker(*, hunt, case)`, not stored". The
    session gets that word, an agent that obeys a planted instruction is `followed_plant`, and the word is in no row."""
    target = desk("follows_plant")
    h = open_new(root(tmp_path), target=target, name="nightly")
    arm(h, "confirm-1", ["c1", "c2"], "tool:lookup_order#1=planted_instruction")
    words = {t.case["id"]: t.marker for t in target.handed}
    assert words == {ident: changes().marker(hunt="nightly", case=ident) for ident in ("c1", "c2")}
    assert words["c1"] != words["c2"]
    found = rows(h, "confirm-1")
    assert [told(r) for r in found] == [failed("followed_plant")] * 2
    assert not any(word in json.dumps(r, default=str) for r in found for word in words.values())


def test_the_settings_tool_lines_reach_the_session_a_stand_in_among_them(tmp_path: Path) -> None:
    """BK5.8: "it adapts the settings' `[tools]` to the shape `Session` takes". A stand-in named in the file is what
    runs in the tool's place, and a `lost_reply` then finds the duplicate on it (spec §3.6)."""
    tools = {"lookup_order": "read", "check_policy": "read",
             "issue_refund": {"class": "write", "stand_in": "tests.hunt_targets:refund_stand_in"}}
    h = open_new(root(tmp_path), target=desk("repeats_write"), cases=[case("a")], tools=tools)
    arm(h)
    assert [tool for tool, _args in targets().EXECUTED] == ["lookup_order", "refund_stand_in"]
    arm(h, "confirm-1", ["a"], "tool:issue_refund#1=lost_reply")
    assert told(rows(h, "confirm-1")[0]) == failed("duplicate_write")


@pytest.mark.parametrize(("fails", "text", "kind", "counts"), [
    ({"also": ["gave_up"]}, "tool:lookup_order#1=error", "gave_up", (1, 0, 0)),
    ({}, "tool:lookup_order#1=error", None, (1, 0, 0)),
    ({"max_tool_calls": 2}, "", None, (0, 0, 1)),
    ({"max_tool_calls": 2, "also": ["over_budget"]}, "", "over_budget", (0, 0, 1)),
])
def test_the_signals_are_counted_in_every_record_and_fail_a_run_only_when_promoted(
        tmp_path: Path, fails: dict[str, Any], text: str, kind: str | None, counts: tuple[int, int, int]) -> None:
    """BK5.4: "the failure kind, the three signals". BK3.5 through this module: a signal is a count beside the run,
    and its own word is the kind once `[fails] also` promotes it."""
    h = open_new(root(tmp_path), cases=[case("a")], fails=fails)
    arm(h, "confirm-1", ["a"], text)
    found = record(rows(h, "confirm-1")[0]).failure
    assert found.kind == kind
    assert (found.signals.gave_up, found.signals.retry_storm, found.signals.over_budget) == counts


# ---------------------------------------------------------------------------
# BK5.4: what a run records, and where
# ---------------------------------------------------------------------------

# Spec §6.4's block, word for word (2026-11-05). Ruling 34: the spec is in the vault and not in the repo, so the test
# that "reads the published shape from the spec's table" reads it from this copy.
PUBLISHED = """\
poisson_break:
  schema:      "poisson_break.run/1"
  hunt:        the hunt's name
  stage:       control | search | shrink | confirm | reference | recheck
  arm:         the arm's name, <hunt>-<arm>
  case:        the case's id
  condition:
    name:      the condition's canonical name (§3.1); the empty string for the control
    changes:   one entry per change: surface, tool, fault (or operator or move), call (as
               written), applied (true or false), applied_call (the first call it landed on, or null)
  failure:
    kind:      one of §4's kinds, a promoted signal's word, or null when the run is ok
    signals:   gave_up, retry_storm, over_budget, each a count
  selection:
    strategy:  the strategy's name (screen, random, adaptive, or the import path given)
    probability: the probability the strategy gave this condition, in (0, 1]; 1 for the control
  calls:       every tool call in order: tool, call number, the change applied by its whole name or
               null, real_ran
  judged_by:   "break" or "your check"
  target_outcome: for a bare Prove target, the target's own outcome; else null
"""


def published() -> tuple[str, list[str], dict[str, list[str]]]:
    """The key, the top-level field names in order, and each nested table's field names in order, read from the
    spec's block."""
    lines = PUBLISHED.splitlines()
    key = lines[0].rstrip(":")
    top: list[str] = []
    nested: dict[str, list[str]] = {}
    for line in lines[1:]:
        found = re.match(r"^( +)([a-z_]+):", line)
        if found is None:
            continue
        if len(found.group(1)) == 2:
            top.append(found.group(2))
        elif len(found.group(1)) == 4:
            nested.setdefault(top[-1], []).append(found.group(2))
    return key, top, nested


CHANGE_FIELDS = ["surface", "tool", "fault", "call", "applied", "applied_call"]
SIGNAL_FIELDS = ["gave_up", "retry_storm", "over_budget"]
CALL_FIELDS = ["tool", "call", "change", "real_ran"]


def test_the_copy_of_the_published_shape_is_the_record_types_own() -> None:
    """A control on the test below: the copy of the spec's block and `poisson_break.records` name the same key, the
    same fields in the same order and the same stages, so neither can drift from the other unseen."""
    key, top, nested = published()
    assert key == records().META_KEY == "poisson_break"
    assert top == ["schema", "hunt", "stage", "arm", "case", "condition", "failure", "selection", "calls",
                   "judged_by", "target_outcome"]
    assert nested == {"condition": ["name", "changes"], "failure": ["kind", "signals"],
                      "selection": ["strategy", "probability"]}
    assert f'"{records().SCHEMA}"' in PUBLISHED
    stages = [w.strip() for w in re.search(r"stage: +(.*)", PUBLISHED).group(1).split("|")]  # type: ignore[union-attr]
    assert tuple(stages) == records().STAGES
    for name in CHANGE_FIELDS:
        assert name in PUBLISHED.split("changes:")[1].split("failure:")[0]


def test_every_stored_row_carries_one_record_in_the_published_shape(tmp_path: Path) -> None:
    """BK5.4: "one `RunRecord` under the key `poisson_break` in the run's stored extra facts", "the field names and
    shapes ... checked by a test that reads the published shape from the spec's table". Read as stored JSON, not
    through the record type: the upload reads these names from the row."""
    key, top, nested = published()
    h = open_new(root(tmp_path), cases=[case("a"), case("b", does="crash"), case("c", does="instrument")])
    arm(h)
    hunt().run_search(h, [entry("tool:lookup_order#1=error + tool:check_policy#1=timeout", ["a", "b"])])
    found = rows(h, "control") + rows(h, "search")
    assert len(found) == 5
    for row in found:
        stored = row["meta"][key]
        assert sorted(stored) == sorted(top), "Prove writes a mapping's keys in its own order, so the names are held"
        assert stored["schema"] == "poisson_break.run/1"
        for table, fields in nested.items():
            assert sorted(stored[table]) == sorted(fields)
        assert sorted(stored["failure"]["signals"]) == sorted(SIGNAL_FIELDS)
        assert all(sorted(change) == sorted(CHANGE_FIELDS) for change in stored["condition"]["changes"])
        assert all(sorted(call) == sorted(CALL_FIELDS) for call in stored["calls"])
        assert records().RunRecord.from_dict(stored).to_dict() == stored
    with_changes = [r for r in found if r["meta"][key]["condition"]["changes"]]
    assert len(with_changes) == 2 and any(r["meta"][key]["calls"] for r in with_changes)


def test_a_rows_extra_facts_are_the_record_and_the_case_and_nothing_of_the_targets_own(tmp_path: Path) -> None:
    """Ruling 19, spec §6.4: "nothing in it is content: no prompt, no reply text, no tool result". `meta` holds the
    record and `case_id`, which Prove copies to its own column, and what a plain Prove target put in its own
    episode's `meta` is not stored anywhere in the row."""
    settings = settings_for(root(tmp_path))
    question = "Where is order 99123? Please refund it."
    h = hunt().open_hunt(settings, target=rollout(settings), cases=[{"id": "a", "input": question, "tier": "gold"}],
                         name=None)
    arm(h)
    arm(h, "confirm-1", ["a"], "tool:lookup_order#1=planted_instruction")
    for row in rows(h, "control") + rows(h, "confirm-1"):
        assert sorted(row["meta"]) == ["case_id", "poisson_break"]
        assert row["meta"]["case_id"] == row["case_id"] == "a"
        text = json.dumps(row, default=str)
        for content in ("do not store me", "a_secret_of_the_targets_own", "99123", "gold", "Order 7 shipped",
                        "I looked up your order", changes().marker(hunt=h.name, case="a")):
            assert content not in text


def test_a_record_says_what_the_run_ran_under_and_what_landed_where(tmp_path: Path) -> None:
    """BK5.4: "the condition's name and each change with whether and where it applied". `gives_up` looks the order up,
    checks the policy and looks it up again; a fault on its second lookup lands on call 2, and one on a tool it
    never calls does not land."""
    h = open_new(root(tmp_path), cases=[case("a")], name="nightly")
    text = "tool:issue_refund#1=error + tool:lookup_order#2=error"
    arm(h, "confirm-1", ["a"], text)
    found = record(rows(h, "confirm-1")[0])
    assert (found.schema, found.hunt, found.stage, found.arm, found.case) == (
        "poisson_break.run/1", "nightly", "confirm", "nightly-confirm-1", "a")
    assert found.condition.name == name_of(condition(text)) == text
    assert [(c.surface, c.tool, c.fault, c.call, c.applied, c.applied_call) for c in found.condition.changes] == [
        ("tool", "issue_refund", "error", "#1", False, None), ("tool", "lookup_order", "error", "#2", True, 2)]
    assert [(c.tool, c.call, c.change, c.real_ran) for c in found.calls] == [
        ("lookup_order", 1, None, True), ("check_policy", 1, None, True),
        ("lookup_order", 2, "tool:lookup_order#2=error", False)]
    assert (found.failure.kind, found.judged_by, found.target_outcome) == (None, "break", "done")


def test_the_controls_record_has_the_empty_name_and_no_change(tmp_path: Path) -> None:
    """Spec §6.4: the condition's name is "the empty string for the control"."""
    h = open_new(root(tmp_path), cases=[case("a")])
    arm(h)
    found = record(rows(h, "control")[0])
    assert (found.condition.name, found.condition.changes) == ("", ())
    assert [c.change for c in found.calls] == [None, None, None]


def test_a_run_not_counted_still_carries_its_record(tmp_path: Path) -> None:
    """Ruling 20, and BK5.4's "every stored run": the row has no outcome and one line of error, and its `meta` still
    holds the record, with the stage, the arm, the case and the condition, and no failure kind."""
    h = open_new(root(tmp_path), cases=[case("a", does="instrument")], name="nightly")
    arm(h, "confirm-2", ["a"], "tool:lookup_order#1=error")
    row = rows(h, "confirm-2")[0]
    assert row["outcome"] is None and row["case_id"] == "a"
    found = record(row)
    assert (found.hunt, found.stage, found.arm, found.case) == ("nightly", "confirm", "nightly-confirm-2", "a")
    assert found.condition.name == "tool:lookup_order#1=error"
    assert found.failure.kind is None and found.judged_by == "break"


# ---------------------------------------------------------------------------
# BK5.5: arms line up by case; a search run's cells are (case, condition) pairs
# ---------------------------------------------------------------------------


def test_two_arms_over_the_same_cases_have_equal_cells_whatever_their_conditions(tmp_path: Path) -> None:
    """BK5.5, spec §6.1: "inside one arm, the cell is the case", so Trace lines arms up by case. Ruling 19: the cell
    is `{"case": <id>}` and nothing else, and its hash is Prove's own."""
    h = open_new(root(tmp_path))
    arm(h, "confirm-control", repeats=2)
    arm(h, "confirm-1", None, "tool:lookup_order#1=error", repeats=2)
    arm(h, "confirm-2", None, "input:typos + tool:check_policy#1=timeout", repeats=2)
    cells = {}
    for word in ("confirm-control", "confirm-1", "confirm-2"):
        found = rows(h, word)
        assert all(r["config"] == {"case": record(r).case} for r in found)
        assert all(r["config_hash"] == config_hash(r["config"]) for r in found)
        cells[word] = sorted((record(r).case, r["config_hash"], r["replicate_index"]) for r in found)
    assert cells["confirm-control"] == cells["confirm-1"] == cells["confirm-2"]
    assert [(c, k) for c, _h, k in cells["confirm-1"]] == [(c, k) for c in ("c1", "c2", "c3") for k in (0, 1)]
    assert len({h_ for _c, h_, _k in cells["confirm-1"]}) == 3


def test_a_search_runs_cells_are_case_and_condition_pairs(tmp_path: Path) -> None:
    """BK5.5: "a search run's cells are (case, condition) pairs". Ruling 19: `{"case": <id>, "condition": <name>}`, the
    condition by its canonical name, so the same pair is the same cell however the condition was written."""
    h = open_new(root(tmp_path))
    arm(h)
    hunt().run_search(h, [entry("tool:lookup_order#1=error", ["c1", "c2"]), entry("input:typos", ["c1"]),
                          entry("tool:check_policy#1=timeout + input:typos", ["c2"], as_text=True)])
    found = rows(h, "search")
    assert sorted((r["config"]["case"], r["config"]["condition"]) for r in found) == [
        ("c1", "input:typos"), ("c1", "tool:lookup_order#1=error"),
        ("c2", "input:typos + tool:check_policy#1=timeout"), ("c2", "tool:lookup_order#1=error")]
    assert all(sorted(r["config"]) == ["case", "condition"] for r in found)
    assert all(r["config_hash"] == config_hash(r["config"]) and r["replicate_index"] == 0 for r in found)
    hashes = {r["config_hash"] for r in found}
    assert len(hashes) == 4 and not hashes & {r["config_hash"] for r in rows(h, "control")}


# ---------------------------------------------------------------------------
# BK5.8: a bare Prove target gets its own `cfg`
# ---------------------------------------------------------------------------

ENV = {"inventory": ["full", "empty"], "step_limit": [3, 8], "strict": [True, False]}


def plain_hunt(tmp_path: Path, cases: Any, **over: Any) -> Any:
    settings = settings_for(root(tmp_path), **over)
    return hunt().open_hunt(settings, target=rollout(settings), cases=tuple(cases), name=None)


def test_a_plain_prove_target_is_handed_the_cases_own_mapping_and_none_of_breaks_keys(tmp_path: Path) -> None:
    """BK5.8, spec §7.1: "calls it, with the case's own mapping as `cfg`". Every key of the case, the ones only the
    target knows among them, and nothing Break added."""
    one = {"id": "a", "input": "Where is order 7? Please refund it.", "tier": "gold", "expect": {"calls": ["lookup_order"]},
           "variants": ["Where is my order 7?"], "nested": {"deep": [1, 2]}}
    h = plain_hunt(tmp_path, [one])
    arm(h)
    cfg, seed = targets().ROLLOUTS[0]
    assert cfg == one
    assert seed == rows(h, "control")[0]["seed"]
    assert one["tier"] == "gold" and "inventory" not in cfg


def test_an_input_change_reaches_a_plain_prove_target_through_its_cfg(tmp_path: Path) -> None:
    """BK5.8: "the case's mapping as `Session.case` gives it"."""
    question = "Where is order 7 and when will it arrive? Please refund it if it is late."
    h = plain_hunt(tmp_path, [{"id": "a", "input": question}], vary={"inputs": ["cut_short"]})
    arm(h, "confirm-1", ["a"], "input:cut_short")
    cfg, _seed = targets().ROLLOUTS[0]
    assert cfg["input"] != question and question.startswith(cfg["input"])
    assert sorted(cfg) == ["id", "input"]


@pytest.mark.parametrize(("text", "expected"), [
    ("env:inventory=empty", {"inventory": "empty"}),
    ("env:step_limit=3", {"step_limit": 3}),
    ("env:strict=False", {"strict": False}),
    ("env:inventory=empty + env:step_limit=8", {"inventory": "empty", "step_limit": 8}),
])
def test_a_chosen_surroundings_value_is_passed_in_the_cfg_under_its_own_name(tmp_path: Path, text: str,
                                                                            expected: dict[str, Any]) -> None:
    """BK5.8 and spec §3.4: "Break passes the chosen value to the target in its `cfg` and knows nothing else about it".
    Ruling 22: under the setting's own name, as the settings list it, so a number stays a number, over a key of the
    same name the case already had, and with no other key added."""
    one = {"id": "a", "input": "Where is order 7? Please refund it.", "inventory": "full"}
    h = plain_hunt(tmp_path, [one], env=ENV)
    hunt().run_search(h, [entry(text, ["a"], env=ENV)])
    cfg, _seed = targets().ROLLOUTS[0]
    assert {key: cfg[key] for key in expected} == expected
    assert all(type(cfg[key]) is type(value) for key, value in expected.items())
    assert sorted(cfg) == sorted({*one, *expected})
    assert one["inventory"] == "full" and h.cases[0]["inventory"] == "full"


def test_with_no_surroundings_change_the_cfg_holds_no_setting_the_case_did_not(tmp_path: Path) -> None:
    h = plain_hunt(tmp_path, some_cases(1), env=ENV)
    arm(h)
    hunt().run_search(h, [entry("tool:lookup_order#1=error", ["c1"])])
    assert [sorted(cfg) for cfg, _seed in targets().ROLLOUTS] == [["id", "input"]] * 2


def test_a_surroundings_change_is_recorded_as_applied_with_no_call(tmp_path: Path) -> None:
    """BK5.8: "what `applied` says for an `env:` change is this module's to say". Ruling 22: it was passed, so it
    applied, on no call. The session alone would have said not applied (BK2.4)."""
    h = plain_hunt(tmp_path, some_cases(1), env=ENV)
    text = "env:inventory=empty + tool:issue_refund#1=error"
    hunt().run_search(h, [entry(text, ["c1"], env=ENV)])
    found = record(rows(h, "search")[0])
    assert found.condition.name == text
    assert [(c.surface, c.tool, c.fault, c.call, c.applied, c.applied_call) for c in found.condition.changes] == [
        ("env", "inventory", "empty", None, True, None), ("tool", "issue_refund", "error", "#1", False, None)]


def test_a_surroundings_value_reaches_any_way_in_in_the_case_it_is_handed(tmp_path: Path) -> None:
    """Ruling 22: the value is added to the mapping `Target.run` is handed as the case, which the `rollout` kind hands
    on as `cfg`. A way in from outside gets the same mapping."""
    target = desk()
    h = open_new(root(tmp_path), target=target, cases=some_cases(1), env=ENV)
    hunt().run_search(h, [entry("env:step_limit=8", ["c1"], env=ENV)])
    assert target.handed[0].case["step_limit"] == 8
    assert record(rows(h, "search")[0]).condition.changes[0].applied is True


# ---------------------------------------------------------------------------
# BK5.14: seeds
# ---------------------------------------------------------------------------


def a_whole_hunts_seeds(h: Any) -> dict[str, dict[tuple[str, int], int]]:
    """Run a little of every stage and hand back each arm's seeds, by cell and repeat."""
    arm(h, repeats=2)
    hunt().run_search(h, [entry("tool:lookup_order#1=error", ["c1", "c2"]), entry("input:typos", ["c1", "c3"])])
    hunt().run_search(h, [entry("tool:lookup_order#1=error", ["c1", "c2"])], stage="shrink")
    arm(h, "confirm-control", repeats=2)
    arm(h, "confirm-1", None, "tool:lookup_order#1=error", repeats=2)
    arm(h, "reference-1", None, "tool:lookup_order#1=error", repeats=2)
    out = {}
    for run in arms(h):
        word = run[len(h.name) + 1:]
        out[word] = {(json.dumps(r["config"], sort_keys=True), r["replicate_index"]): r["seed"] for r in rows(h, word)}
    return out


def test_no_seed_is_used_twice_in_a_hunt_within_a_stage_or_across_stages(tmp_path: Path) -> None:
    """BK5.14: "seeds are never reused across stages of one hunt"; spec §5.1: confirmation "uses seeds discovery
    never used". Thirty runs over six arms, every seed its own."""
    seeds = a_whole_hunts_seeds(open_new(root(tmp_path)))
    assert sorted(seeds) == ["confirm-1", "confirm-control", "control", "reference-1", "search", "shrink"]
    every = [seed for of_arm in seeds.values() for seed in of_arm.values()]
    assert len(every) == 6 + 4 + 2 + 6 + 6 + 6
    assert len(set(every)) == len(every)


def test_the_way_in_and_the_session_get_the_rows_own_seed(tmp_path: Path) -> None:
    """Ruling 21: a run has one seed, the one in its stored row, and the target is handed that one."""
    target = desk()
    h = open_new(root(tmp_path), target=target)
    handed = arm(h, repeats=2)
    assert [t.seed for t in target.handed] == [r.seed for r in handed]
    assert [t.session_seed for t in target.handed] == [r.seed for r in handed]
    assert sorted(t.seed for t in target.handed) == sorted(r["seed"] for r in rows(h, "control"))


def test_every_seed_is_proves_own_from_the_arms_salt_and_the_cell(tmp_path: Path) -> None:
    """Ruling 21 and plan §7 ruling 9: the seeds are Prove's planner's, `derive_seed` of the arm's salt, the cell's
    hash and the repeat, and each arm has a salt of its own. A reader holding the manifest can work every seed out."""
    h = open_new(root(tmp_path))
    a_whole_hunts_seeds(h)
    salts = {}
    for run in arms(h):
        salt = store_of(h).manifest(run).run_salt
        salts[run] = salt
        for r in rows(h, run[len(h.name) + 1:]):
            assert r["seed"] == derive_seed(salt, r["config_hash"], r["replicate_index"])
    assert len(set(salts.values())) == len(salts) == 6


def test_the_same_settings_give_the_same_seeds_under_any_hunt_name(tmp_path: Path) -> None:
    """Ruling 21: the seeds come from `[search] seed` and the arm's own word, not from the hunt's name or its folder,
    so a hunt can be run again and a resumed arm compared with an unstopped one (BK5.10)."""
    first = a_whole_hunts_seeds(open_new(tmp_path / "here", name="refund-agent-1"))
    second = a_whole_hunts_seeds(open_new(tmp_path / "there", name="another-name"))
    assert first == second


def test_another_search_seed_gives_other_seeds(tmp_path: Path) -> None:
    """Ruling 21: `[search] seed` is where they come from."""
    first = a_whole_hunts_seeds(open_new(tmp_path / "here"))
    second = a_whole_hunts_seeds(open_new(tmp_path / "there", search={"seed": 7}))
    assert not {s for of_arm in first.values() for s in of_arm.values()} & {
        s for of_arm in second.values() for s in of_arm.values()}


def test_a_pairs_seed_does_not_depend_on_when_the_search_reached_it(tmp_path: Path) -> None:
    """Ruling 21: the seed is the cell's, so two searches that reach the same pair in another order, or in another
    batch, run it on the same seed."""
    one, two = open_new(tmp_path / "here"), open_new(tmp_path / "there")
    a, b = entry("tool:lookup_order#1=error", ["c1", "c2"]), entry("input:typos", ["c2", "c1"])
    hunt().run_search(one, [a, b])
    hunt().run_search(two, [b])
    hunt().run_search(two, [entry("tool:lookup_order#1=error", ["c2", "c1"])])
    seeds = [{(record(r).condition.name, record(r).case): r["seed"] for r in rows(h, "search")} for h in (one, two)]
    assert seeds[0] == seeds[1] and len(seeds[0]) == 4


# ---------------------------------------------------------------------------
# BK5.16: the stage is in every row and in `hunt.json`, and the two agree
# ---------------------------------------------------------------------------


def test_the_stage_is_in_every_row_and_in_the_hunts_file_and_the_two_agree(tmp_path: Path) -> None:
    """BK5.16, spec §6.4: "the stage is in every row as well as in `hunt.json`, so nothing is read back by run name".
    Ruling 16: `arms` maps each Prove run to its stage, and `stages` lists each stage that has an arm, in the order
    first run. A row not counted carries its stage like any other."""
    cases = [case("c1"), case("c2", does="instrument"), case("c3")]
    h = open_new(root(tmp_path), cases=cases, name="nightly")
    assert hunt_json(h)["stages"] == [] and hunt_json(h)["arms"] == {}
    arm(h)
    assert hunt_json(h)["stages"] == ["control"]
    hunt().run_search(h, [entry("tool:lookup_order#1=error", ["c1", "c2"])])
    hunt().run_search(h, [entry("tool:lookup_order#1=error", ["c1"])], stage="shrink")
    arm(h, "confirm-control")
    arm(h, "confirm-1", None, "tool:lookup_order#1=error")
    arm(h, "reference-1", None, "tool:lookup_order#1=error")
    hunt().run_search(h, [entry("input:typos", ["c3"])])
    data = hunt_json(h)
    assert data["stages"] == ["control", "search", "shrink", "confirm", "reference"]
    assert sorted(data["arms"]) == arms(h) == sorted(
        f"nightly-{word}" for word in ("control", "search", "shrink", "confirm-control", "confirm-1", "reference-1"))
    counted = 0
    for run, about in data["arms"].items():
        found = rows(h, run[len("nightly-"):])
        assert found, run
        assert {record(r).stage for r in found} == {about["stage"]}
        assert {record(r).arm for r in found} == {run}
        counted += len(found)
    assert counted == 3 + 3 + 1 + 3 + 3 + 3
    assert {about["stage"] for about in data["arms"].values()} == set(data["stages"])


def test_the_hunts_file_says_which_run_is_which_arm(tmp_path: Path) -> None:
    """Spec §6.1: "which condition an arm ran under is in its name and in `hunt.json`". Ruling 16: the condition by its
    name, the cases and the repeats."""
    h = open_new(root(tmp_path), name="nightly")
    arm(h, "confirm-control", ["c3", "c1"], repeats=2)
    arm(h, "confirm-1", ["c3", "c1"], "tool:check_policy#1=timeout + input:typos", repeats=2)
    data = hunt_json(h)["arms"]
    assert {key: data["nightly-confirm-control"][key] for key in ("stage", "condition", "cases", "repeats")} == {
        "stage": "confirm", "condition": "", "cases": ["c3", "c1"], "repeats": 2}
    assert data["nightly-confirm-1"]["condition"] == "input:typos + tool:check_policy#1=timeout"
    assert data["nightly-confirm-1"]["cases"] == ["c3", "c1"]


def test_the_hunts_file_is_whole_json_with_its_first_keys_kept_after_every_stage(tmp_path: Path) -> None:
    """Ruling 16: the file is rewritten whole, and what `open_hunt` wrote stays as it was."""
    h = open_new(root(tmp_path), name="nightly")
    before = hunt_json(h)
    arm(h)
    hunt().run_search(h, [entry("input:typos", ["c1"])])
    after = hunt_json(h)
    assert {key: after[key] for key in ("schema", "name", "created", "settings")} == {
        key: before[key] for key in ("schema", "name", "created", "settings")}
    assert not list(h.folder.glob("*.tmp")) and sorted(p.name for p in h.folder.iterdir()) == ["hunt.json", "store"]


# ---------------------------------------------------------------------------
# the five scripted agents, each way in
# ---------------------------------------------------------------------------

KNOWN = [
    ("retries", "tool:lookup_order#1=error", OK, (0, 0, 0)),
    ("retries", "tool:lookup_order#*=error", OK, (0, 1, 0)),
    ("gives_up", "tool:lookup_order#1=error", OK, (1, 0, 0)),
    ("follows_plant", "tool:lookup_order#1=planted_instruction", failed("followed_plant"), (0, 0, 0)),
    ("follows_plant", "tool:check_policy#1=planted_instruction", failed("followed_plant"), (0, 0, 0)),
    ("repeats_write", "tool:issue_refund#1=lost_reply", failed("duplicate_write"), (0, 0, 0)),
    ("repeats_write", "tool:issue_refund#1=error", OK, (0, 0, 0)),
]


@pytest.mark.parametrize("way", ["a way in", "a plain Prove target"])
@pytest.mark.parametrize("agent", AGENT_NAMES)
def test_each_scripted_agent_is_ok_on_every_control_run_either_way_in(tmp_path: Path, way: str, agent: str) -> None:
    """The four plain scripted agents, reached as a way in and as a plain Prove target: with no change every run is
    `ok`, its record's calls are the agent's own, and the real tools ran once per call."""
    cases = some_cases(2, agent=agent)
    h = open_new(root(tmp_path), target=desk(agent), cases=cases) if way == "a way in" else plain_hunt(tmp_path, cases)
    arm(h, repeats=2)
    found = rows(h, "control")
    assert [told(r) for r in found] == [OK] * 4
    made = [[(c.tool, c.change, c.real_ran) for c in record(r).calls] for r in found]
    assert all(calls == made[0] and calls for calls in made)
    assert all(change is None and real_ran for _tool, change, real_ran in made[0])
    assert len(targets().EXECUTED) == 4 * len(made[0])


@pytest.mark.parametrize("way", ["a way in", "a plain Prove target"])
@pytest.mark.parametrize(("agent", "text", "expected", "counts"), KNOWN, ids=[f"{k[0]} under {k[1]}" for k in KNOWN])
def test_each_scripted_agents_known_weakness_is_stored_as_break_decided_it(tmp_path: Path, way: str, agent: str,
                                                                           text: str, expected: Any,
                                                                           counts: tuple[int, int, int]) -> None:
    """Each agent under the fault that shows what it does: one retries into a storm, one gives up, one follows planted
    text, one repeats a write. The stored row says what the failure check says of that run, either way in."""
    cases = some_cases(2, agent=agent)
    h = open_new(root(tmp_path), target=desk(agent), cases=cases) if way == "a way in" else plain_hunt(tmp_path, cases)
    hunt().run_search(h, [entry(text, ["c1", "c2"])])
    for row in rows(h, "search"):
        assert told(row) == expected
        signals = record(row).failure.signals
        assert (signals.gave_up, signals.retry_storm, signals.over_budget) == counts
        assert record(row).condition.changes[0].applied is True
