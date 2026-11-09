"""`read_stages(hunt)`: each confirm stage as `confirm.json` holds it, with each arm's count from the store.

Ruled 2026-11-08 (Break — Decisions: yes to a public `confirm.read_stages(hunt)`, with the confirm command moved onto
it; BK8 Session B's build choice 4). The command read `confirm.json` and asked Prove's store for each arm's count, to
plan a resumed or asked-again stage and to refuse before the plan (BK8 points 14 and 54); this name answers both, and
runs nothing. The shape the tests take, which the ruling leaves open, is the BK8 follow-up's point R1 (its
`open-points.md`), and the tests stand on its yes:

- `read_stages(hunt) -> tuple[Stage, ...]`, in the stages' order, empty for a hunt with no `confirm.json`;
- `Stage` frozen, with `number`, `repeats`, `cases` (the case ids, as written), `arms` (pairs of the arm's word and its
  condition's name, the control first with `""`, as `Design.arms` has them), `q` and `max_difference` (as written),
  and `counts`: each arm's word to the rows the store holds of its Prove run, `<hunt>-<word>`, 0 for a run not there,
  in the arms' order, not to be changed;
- a `confirm.json` that cannot be read is the runs module's `HuntError`, as `confirm` refuses it.

Each test names the point of `open-points.md` R1 it holds: (a) the name, (b) none, (c) as written, (d) the counts,
(e) runs nothing, (f) the refusal, (g) what is left is what runs. On the stand-in for Trace, with no new recorded
document: every stage below is one the confirm module's own tests already run.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tests import confirm_targets as targets
from tests.confirm_support import (
    GAPS,
    PLANTED,
    calls,
    confirm_module,
    hunt_module,
    open_scenario,
    read_json,
    ready,
    rows,
    stand_in,
    trace_document,
)


@pytest.fixture
def trace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return stand_in(monkeypatch, tmp_path)


def read_stages(h: Any) -> Any:
    return confirm_module().read_stages(h)


def _written(h: Any) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = read_json(Path(h.folder) / "confirm.json")["stages"]
    return stages


def _stored(h: Any, word: str) -> int:
    from poisson_prove.store import Store

    store = Store(h.store)
    run = f"{h.name}-{word}"
    return store.count(run) if run in store.runs() else 0


def _files(h: Any) -> dict[str, bytes]:
    folder = Path(h.folder)
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def _priced(name: str = "priced") -> Any:
    """Planted, every run costing $0.001, under a cap that stops the confirm stage after its first run (the control's
    fourteen runs spend $0.014, the cap is $0.0155)."""
    return dataclasses.replace(PLANTED, name=name, cases=tuple({**c, "tokens": [1000, 0]} for c in PLANTED.cases),
                               limits={"dollars": 0.0155, "input_per_million": 1.0, "output_per_million": 1.0})


def _stopped(tmp_path: Path) -> Any:
    """A planted hunt whose first confirm stage the dollar cap stopped after one run of its control arm."""
    h = ready(tmp_path / "hunts", _priced())
    with pytest.raises(hunt_module().HuntStopped):
        confirm_module().confirm(h)
    assert _stored(h, "confirm-control") == 1
    return h


def _as_written(stage: Any) -> dict[str, Any]:
    """A `Stage` as the file writes one, its counts aside."""
    return {"number": stage.number, "repeats": stage.repeats, "cases": list(stage.cases), "q": stage.q,
            "max_difference": stage.max_difference,
            "arms": [{"arm": word, "condition": name} for word, name in stage.arms]}


# ---------------------------------------------------------------------------
# (a) the name
# ---------------------------------------------------------------------------


def test_read_stages_and_stage_are_public_names_of_the_confirm_module() -> None:
    module = confirm_module()
    assert {"read_stages", "Stage"} <= set(module.__all__)
    assert callable(module.read_stages)
    assert dataclasses.is_dataclass(module.Stage)


# ---------------------------------------------------------------------------
# (b) none, and nothing done
# ---------------------------------------------------------------------------


def test_a_hunt_with_no_confirm_stage_has_none_and_nothing_is_written(tmp_path: Path, trace: Path) -> None:
    """Candidates written and the control run, no stage yet: an empty tuple, and no `confirm.json` made by asking."""
    h = ready(tmp_path / "hunts", PLANTED)
    before = _files(h)
    found = read_stages(h)
    assert found == () and type(found) is tuple
    assert _files(h) == before
    assert not (Path(h.folder) / "confirm.json").exists()
    assert calls(trace) == []


# ---------------------------------------------------------------------------
# (c) each stage as written
# ---------------------------------------------------------------------------


def test_a_finished_stage_is_the_stage_confirm_json_holds(tmp_path: Path, trace: Path) -> None:
    """Under a `q` of its own, so no default can pass for what was written (the repeats are held against settings
    that say otherwise below: the stand-in for Trace holds documents for the planted five only)."""
    h = ready(tmp_path / "hunts", PLANTED, confirm={"q": 0.04})
    confirm_module().confirm(h)
    (stage,) = read_stages(h)
    assert isinstance(stage, confirm_module().Stage)
    assert [_as_written(stage)] == _written(h)
    assert (stage.q, stage.repeats) == (0.04, 5)
    assert type(stage.cases) is tuple and all(type(case) is str for case in stage.cases)
    assert type(stage.arms) is tuple and all(type(arm) is tuple and len(arm) == 2 for arm in stage.arms)
    assert stage.arms[0] == ("confirm-control", "")


def test_the_arms_are_the_design_s(tmp_path: Path, trace: Path) -> None:
    """The arms, the cases and the repeats are those `design` worked out before the stage ran: one shape for both."""
    h = ready(tmp_path / "hunts", PLANTED)
    planned = confirm_module().design(confirm_module().read_candidates(h), h.settings, hunt_module().control(h))
    confirm_module().confirm(h)
    (stage,) = read_stages(h)
    assert (stage.arms, stage.cases, stage.repeats) == (planned.arms, planned.cases, planned.repeats)


def test_a_stage_is_read_as_written_whatever_the_settings_say_now(tmp_path: Path, trace: Path) -> None:
    """Stopped under `q = 0.05`, `max_difference = 0.2`, 5 repeats, and opened again under 0.2, 0.3 and 9: the stage
    is what the file holds, not what the settings would design."""
    h = _stopped(tmp_path)
    again = open_scenario(tmp_path / "hunts", _priced(), existing=True,
                          confirm={"q": 0.2, "max_difference": 0.3, "repeats": 9})
    (stage,) = read_stages(again)
    assert (stage.q, stage.max_difference, stage.repeats) == (0.05, 0.2, 5)
    assert [_as_written(stage)] == _written(h)


def test_two_stages_are_both_read_in_order_each_as_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The second candidate too small to tell in stage 1, asked again six times under a `q` of the settings' as they
    are then: stage 2 holds its own control arm and that one candidate's, and that `q`."""
    stand_in(monkeypatch, tmp_path, patch={"confirm-3": {"set": {"verdict": "no significant difference"}}})
    h = ready(tmp_path / "hunts", PLANTED)
    first = confirm_module().confirm(h)
    assert [t.verdict for t in first.tested] == ["confirmed", "too small to tell", "not confirmed"]
    answer = trace_document(h, "confirm-control", "confirm-2")
    patch = {"confirm-3": {"set": {"verdict": "no significant difference"}},
             "confirm-2-2": {"stdout": json.dumps(answer), "exit": 0}}
    stand_in(monkeypatch, tmp_path, patch=patch)
    looser = open_scenario(tmp_path / "hunts", PLANTED, existing=True, confirm={"q": 0.1})
    confirm_module().confirm(looser, repeats=6)
    stages = read_stages(looser)
    assert [_as_written(stage) for stage in stages] == _written(h)
    assert [stage.number for stage in stages] == [1, 2]
    assert stages[1].arms == (("confirm-2-control", ""), ("confirm-2-2", stages[0].arms[2][1]))
    assert (stages[0].q, stages[1].q, stages[1].repeats) == (0.05, 0.1, 6)


# ---------------------------------------------------------------------------
# (d) each arm's count, from the store
# ---------------------------------------------------------------------------


def test_each_arm_s_count_is_the_rows_its_run_holds_and_every_arm_of_a_finished_stage_is_full(
        tmp_path: Path, trace: Path) -> None:
    h = ready(tmp_path / "hunts", PLANTED)
    confirm_module().confirm(h)
    (stage,) = read_stages(h)
    assert list(stage.counts) == [word for word, _ in stage.arms]
    assert dict(stage.counts) == {word: len(rows(h, word)) for word, _ in stage.arms}
    assert set(stage.counts.values()) == {len(stage.cases) * stage.repeats}


def test_a_stopped_stage_counts_what_was_stored_and_0_for_an_arm_with_no_run(tmp_path: Path, trace: Path) -> None:
    h = _stopped(tmp_path)
    (stage,) = read_stages(h)
    words = [word for word, _ in stage.arms]
    assert dict(stage.counts) == {words[0]: 1, **{word: 0 for word in words[1:]}}
    from poisson_prove.store import Store

    assert f"{h.name}-{words[1]}" not in Store(h.store).runs()


def test_the_counts_are_the_store_s_when_asked_not_when_first_read(tmp_path: Path, trace: Path) -> None:
    """Asked on the stopped stage, then again on the same hunt after it was finished: the second answer is full."""
    h = _stopped(tmp_path)
    (stopped,) = read_stages(h)
    again = open_scenario(tmp_path / "hunts", _priced(), existing=True, limits={"dollars": 100.0})
    confirm_module().confirm(again)
    (finished,) = read_stages(h)
    assert dict(stopped.counts) != dict(finished.counts)
    assert set(finished.counts.values()) == {len(finished.cases) * finished.repeats}


def test_a_run_not_counted_is_a_row_its_arm_holds_so_a_finished_stage_with_one_is_full(
        tmp_path: Path, trace: Path) -> None:
    """Under `error` case k12 of the gaps hunt has no outcome: its runs are stored, not counted. They are rows of the
    arm all the same, so the finished stage's count is full, and asking it again runs nothing: a count of outcomes
    alone would show runs left on a stage with none."""
    h = ready(tmp_path / "hunts", GAPS)
    confirm_module().confirm(h)
    (stage,) = read_stages(h)
    word = stage.arms[1][0]
    assert any(r["outcome"] is None for r in rows(h, word))
    assert stage.counts[word] == len(rows(h, word)) == len(stage.cases) * stage.repeats
    before = _files(h)
    confirm_module().confirm(h)
    assert {k: v for k, v in _files(h).items() if not k.startswith("store/")} == {
        k: v for k, v in before.items() if not k.startswith("store/")}
    assert {word: _stored(h, word) for word, _ in stage.arms} == dict(stage.counts)


def test_a_stage_and_its_counts_cannot_be_changed(tmp_path: Path, trace: Path) -> None:
    h = _stopped(tmp_path)
    (stage,) = read_stages(h)
    with pytest.raises(dataclasses.FrozenInstanceError):
        stage.repeats = 99
    with pytest.raises(TypeError):
        stage.counts["confirm-control"] = 99
    (again,) = read_stages(h)
    assert again.counts["confirm-control"] == 1


# ---------------------------------------------------------------------------
# (e) runs nothing
# ---------------------------------------------------------------------------


def test_reading_a_stopped_stage_runs_nothing_asks_trace_nothing_and_writes_nothing(
        tmp_path: Path, trace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A stage with runs missing is where running would add rows: no arm grows, Trace is not asked, the agent is not
    called, and every file of the hunt keeps its bytes."""
    h = _stopped(tmp_path)
    before, asked = _files(h), len(calls(trace))
    ran: list[Any] = []

    def run(self: Any, *args: Any, **kwargs: Any) -> Any:
        ran.append(args)
        raise AssertionError("the agent was run")

    monkeypatch.setattr(targets.Coin, "run", run)
    read_stages(h)
    read_stages(open_scenario(tmp_path / "hunts", _priced(), existing=True))
    assert ran == []
    assert len(calls(trace)) == asked
    assert _files(h) == before


# ---------------------------------------------------------------------------
# (f) a file that cannot be read
# ---------------------------------------------------------------------------


def _not_json(held: dict[str, Any]) -> str:
    return "{ not json"


def _other_schema(held: dict[str, Any]) -> str:
    return json.dumps({**held, "schema": "poisson_break.confirm/2"})


def _no_q(held: dict[str, Any]) -> str:
    del held["stages"][0]["q"]
    return json.dumps(held)


def _numbered_2(held: dict[str, Any]) -> str:
    held["stages"][0]["number"] = 2
    return json.dumps(held)


def _one_arm(held: dict[str, Any]) -> str:
    held["stages"][0]["arms"] = held["stages"][0]["arms"][:1]
    return json.dumps(held)


@pytest.mark.parametrize("spoil", [_not_json, _other_schema, _no_q, _numbered_2, _one_arm])
def test_a_confirm_json_that_cannot_be_read_is_the_runs_module_s_refusal_as_confirm_s_is(
        tmp_path: Path, trace: Path, spoil: Any) -> None:
    """The file as written reads; spoiled, `read_stages` refuses it with `HuntError`, as `confirm` does the same file,
    so the command meets one refusal however it asks."""
    h = ready(tmp_path / "hunts", PLANTED)
    confirm_module().confirm(h)
    assert len(read_stages(h)) == 1
    path = Path(h.folder) / "confirm.json"
    path.write_text(spoil(read_json(path)), encoding="utf-8")
    with pytest.raises(hunt_module().HuntError):
        read_stages(h)
    with pytest.raises(hunt_module().HuntError):
        confirm_module().confirm(h)


# ---------------------------------------------------------------------------
# (g) what is left is what runs
# ---------------------------------------------------------------------------


def test_the_runs_a_stopped_stage_has_left_by_its_counts_are_the_runs_taking_it_up_makes(
        tmp_path: Path, trace: Path) -> None:
    """Point 54's number: every arm's cells less its count, summed over the arms, is how many rows the stage's arms
    gain when it is taken up again and finished."""
    h = _stopped(tmp_path)
    (stage,) = read_stages(h)
    cells = len(stage.cases) * stage.repeats
    left = sum(cells - count for count in stage.counts.values())
    again = open_scenario(tmp_path / "hunts", _priced(), existing=True, limits={"dollars": 100.0})
    confirm_module().confirm(again)
    gained = sum(_stored(h, word) for word, _ in stage.arms) - sum(stage.counts.values())
    assert 0 < left == gained
