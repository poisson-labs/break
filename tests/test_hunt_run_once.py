"""`poisson_break.hunt.run_once`: one case run once, with no change, stored nowhere.

Taylor's yes to BK8 point 39 (2026-11-07). `doctor --run` runs the first case once with no change and stores nothing
(point 23), and the only door that did that was the hunt module's private `_run_unstored`, which needs a hunt and an
arm and which BK8.8 does not let the command reach. So the hunt module gets one public name,
`run_once(settings, *, target, case) -> RunRow`: no hunt, no store, no cap, and the same applier and failure check as a
stored run. BK8 Session B adds it; this file holds what it does.

`case` is one case as `read_cases` hands it, a mapping with its `id`: the signature has no hunt to hold the cases, and
the row names the case by its id (point 41, OWED). Every call here goes through `once`, so the other answer changes one
line.

Not held here, since point 39 does not say: which seed the run is on, and what a tool nobody classed does (point 42,
OWED).
"""

from __future__ import annotations

import inspect
import tempfile
from pathlib import Path
from typing import Any

import pytest

from tests.hunt_support import case, changes, desk, hunt, settings_for, targets


def once(settings: Any, target: Any, one: dict[str, Any]) -> Any:
    return hunt().run_once(settings, target=target, case=one)


def no_change() -> Any:
    return changes().Condition(changes=())


def everything_under(folder: Path) -> list[str]:
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*")) if folder.exists() else []


def test_run_once_is_a_public_name_of_the_hunt_module() -> None:
    module = hunt()
    assert "run_once" in module.__all__
    assert callable(module.run_once)


def test_run_once_takes_the_settings_then_target_and_case_by_keyword() -> None:
    parameters = list(inspect.signature(hunt().run_once).parameters.values())
    assert [p.name for p in parameters] == ["settings", "target", "case"]
    assert parameters[0].kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    assert [p.kind for p in parameters[1:]] == [inspect.Parameter.KEYWORD_ONLY] * 2


def test_a_case_that_passes_is_an_ok_row_with_no_change(tmp_path: Path) -> None:
    settings = settings_for(tmp_path / "hunts")
    target = desk()
    row = once(settings, target, case("c1"))
    assert isinstance(row, hunt().RunRow)
    assert (row.case, row.outcome, row.kind) == ("c1", "ok", None)
    assert row.condition == no_change()
    assert isinstance(row.seed, int)
    assert target.runs == 1
    (handed,) = target.handed
    assert handed.case == case("c1")
    assert handed.condition == no_change()


@pytest.mark.parametrize(("keys", "fails", "kind"), [
    ({"does": "crash"}, {}, "crashed"),
    ({}, {"never_call": ["check_policy"]}, "forbidden_call"),
], ids=["the agent raises", "a tool it may never call"])
def test_the_failure_check_decides_the_outcome(tmp_path: Path, keys: dict[str, Any], fails: dict[str, Any],
                                               kind: str) -> None:
    """The same failure check as a stored run: an agent that raises is a failed row of kind `crashed`, and the
    `gives_up` desk calling `check_policy` under `never_call` one of kind `forbidden_call`."""
    row = once(settings_for(tmp_path / "hunts", fails=fails), desk(), case("c1", **keys))
    assert (row.outcome, row.kind) == ("failed", kind)


def test_a_run_the_way_in_could_not_make_is_not_counted(tmp_path: Path) -> None:
    row = once(settings_for(tmp_path / "hunts"), desk(), case("c1", does="instrument"))
    assert (row.outcome, row.kind) == ("not counted", None)


def test_it_makes_no_hunt_and_stores_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The settings' output folder as it was, a file in it kept; nothing where it was called from; nothing left in the
    temporary folder; and no hunt to name."""
    here, scratch, hunts = tmp_path / "here", tmp_path / "tmp", tmp_path / "hunts"
    for folder in (here, scratch, hunts):
        folder.mkdir()
    (hunts / "kept.txt").write_text("the user's own\n", encoding="utf-8")
    monkeypatch.chdir(here)
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    settings = settings_for(hunts)
    for one in (case("c1"), case("c2", does="crash"), case("c3", does="instrument")):
        once(settings, desk(), one)
    assert everything_under(hunts) == ["kept.txt"]
    assert everything_under(here) == []
    assert everything_under(scratch) == []
    assert hunt().latest_hunt(settings) is None


def test_no_cap_holds_it_and_nothing_is_remembered(tmp_path: Path) -> None:
    """A run cap of one and a dollar cap far under one run's cost: each call still runs the case once more."""
    settings = settings_for(tmp_path / "hunts", search={"runs": 1},
                            limits={"dollars": 0.01, "input_per_million": 100.0, "output_per_million": 100.0})
    target = desk()
    rows = [once(settings, target, case("c1", tokens=(1_000_000, 1_000_000))) for _ in range(3)]
    assert [r.outcome for r in rows] == ["ok"] * 3
    assert target.runs == 3


def test_the_run_is_held_to_the_settings_run_seconds(tmp_path: Path) -> None:
    target = desk()
    once(settings_for(tmp_path / "hunts", fails={"run_seconds": 7}), target, case("c1"))
    assert target.handed[0].run_seconds == 7.0


def test_the_settings_own_rollout_target_runs_once(tmp_path: Path) -> None:
    """The way `doctor` loads the target (`load_target`): the plain Prove target is called once, on the case."""
    targets().reset()
    settings = settings_for(tmp_path / "hunts")
    row = once(settings, hunt().load_target(settings), case("c1"))
    assert (row.case, row.outcome) == ("c1", "ok")
    assert [cfg["id"] for cfg, _ in targets().ROLLOUTS] == ["c1"]
