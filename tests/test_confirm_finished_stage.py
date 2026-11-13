"""`finished_stage(hunt)`: the latest confirm stage's answer when nothing of it is left to run or write.

Hands-on issue 5, as Taylor ruled it (2026-11-13): a second `confirm` on a hunt whose latest stage is finished, with no
`--repeats`, runs nothing, asks nothing and leaves the finding files as they are. The command needs to know that before
it plans, and a stage whose arms are full is not always finished: a stage stopped after its last run, before Trace
answered or before its findings were written, still has findings to write and reference arms to run. This name answers
that, and runs nothing and writes nothing:

- `None` for a hunt with no stage, a stage with runs missing, a candidate the stage confirms with no finding file yet,
  or a written finding whose reference arm has runs missing: what `confirm` would go on with;
- otherwise the `Confirmation` that `confirm` gives the finished stage asked again, Trace asked again as it asks it.

On the stand-in for Trace, with no new recorded document: every stage below is one the confirm module's own tests
already run.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from tests import confirm_targets as targets
from tests.confirm_support import PLANTED, calls, confirm_module, hunt_module, ready, stand_in


@pytest.fixture
def trace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return stand_in(monkeypatch, tmp_path)


def _files(h: Any) -> dict[str, bytes]:
    folder = Path(h.folder)
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def _no_run(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    ran: list[Any] = []

    def run(self: Any, *args: Any, **kwargs: Any) -> Any:
        ran.append(args)
        raise AssertionError("the agent was run")

    monkeypatch.setattr(targets.Coin, "run", run)
    return ran


def test_finished_stage_is_a_public_name_of_the_confirm_module() -> None:
    module = confirm_module()
    assert "finished_stage" in module.__all__
    assert callable(module.finished_stage)


def test_a_hunt_with_no_stage_has_none_and_trace_is_not_asked(tmp_path: Path, trace: Path) -> None:
    h = ready(tmp_path / "hunts", PLANTED)
    before = _files(h)
    assert confirm_module().finished_stage(h) is None
    assert calls(trace) == []
    assert _files(h) == before


def test_a_stopped_stage_has_none_runs_nothing_and_trace_is_not_asked(tmp_path: Path, trace: Path,
                                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    priced = dataclasses.replace(PLANTED, name="priced", cases=tuple({**c, "tokens": [1000, 0]} for c in PLANTED.cases),
                                 limits={"dollars": 0.0155, "input_per_million": 1.0, "output_per_million": 1.0})
    h = ready(tmp_path / "hunts", priced)
    with pytest.raises(hunt_module().HuntStopped):
        confirm_module().confirm(h)
    before, asked = _files(h), len(calls(trace))
    ran = _no_run(monkeypatch)
    assert confirm_module().finished_stage(h) is None
    assert ran == [] and len(calls(trace)) == asked
    assert _files(h) == before


def test_a_finished_stage_gives_confirm_s_answer_and_runs_and_writes_nothing(tmp_path: Path, trace: Path,
                                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    h = ready(tmp_path / "hunts", PLANTED)
    done = confirm_module().confirm(h)
    assert done.findings, "the planted weakness is confirmed"
    before = _files(h)
    ran = _no_run(monkeypatch)
    again = confirm_module().finished_stage(h)
    assert isinstance(again, confirm_module().Confirmation)
    assert again == done
    assert ran == []
    assert _files(h) == before


def test_a_confirmed_candidate_with_no_finding_file_yet_has_none_and_nothing_is_written(
        tmp_path: Path, trace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """As after a stage stopped once its last run was stored and before its findings were written: `confirm` would
    write the finding and run its reference arm, so the stage is not finished."""
    h = ready(tmp_path / "hunts", PLANTED)
    done = confirm_module().confirm(h)
    (Path(h.folder) / "findings" / f"{done.findings[0].number}.toml").unlink()
    before = _files(h)
    ran = _no_run(monkeypatch)
    assert confirm_module().finished_stage(h) is None
    assert ran == []
    assert _files(h) == before
