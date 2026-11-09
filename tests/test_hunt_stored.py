"""`Hunt.stored()`: every arm the hunt's store holds, by its word, with the rows it holds.

Ruled 2026-11-08 (Break — Decisions: R2, option A of `evidence/bk8f/open-points.md`): one more public name, in the runs
module, that gives an arm's stored count, so the command reaches no Prove store at all: it asks whether the control is
finished, and how much a stopped recheck has left, through this name, and `fb0bf64`'s check holds. The name and its
signature are the follow-up's proposal (`evidence/bk8f/mapping.md`, "R2"):

- `Hunt.stored() -> Mapping[str, int]`, a method of the public `Hunt`;
- each Prove run in the hunt's store, by its arm's word (the run's name less `<hunt>-`: `control`, `search`, `shrink`,
  `confirm-1`, `reference-1`, `recheck-1-1`, `recheck-1-1-old`), to the rows the store holds of it, runs not counted
  included, as Prove's own count gives them;
- empty for a hunt with no store; read from the store each time it is asked; not to be changed; runs nothing, asks
  Trace nothing and writes nothing.

A mapping of every arm, not one arm's count: the command must find the recheck last begun and whether it ran beside an
old agent, which only the names of the arms the store holds can tell.
"""

from __future__ import annotations

import contextlib
import dataclasses
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
    on,
    open_scenario,
    ready,
    rows,
    stand_in,
)


@pytest.fixture
def trace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return stand_in(monkeypatch, tmp_path)


def _store_counts(h: Any) -> dict[str, int]:
    """What Prove's own store says, by arm word: the answer `stored` must give."""
    from poisson_prove.store import Store

    if not Path(h.store).exists():
        return {}
    store = Store(h.store)
    prefix = f"{h.name}-"
    return {run[len(prefix):]: store.count(run) for run in store.runs()}


def _files(h: Any) -> dict[str, bytes]:
    folder = Path(h.folder)
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def _priced(name: str = "priced") -> Any:
    """Planted, every run costing $0.001, under a cap that stops the confirm stage after its first run."""
    return dataclasses.replace(PLANTED, name=name, cases=tuple({**c, "tokens": [1000, 0]} for c in PLANTED.cases),
                               limits={"dollars": 0.0155, "input_per_million": 1.0, "output_per_million": 1.0})


def test_stored_is_a_method_of_the_public_hunt() -> None:
    module = hunt_module()
    assert "Hunt" in module.__all__
    assert callable(getattr(module.Hunt, "stored", None))


def test_a_hunt_with_no_store_has_no_arm_and_asking_makes_none(tmp_path: Path) -> None:
    h = open_scenario(tmp_path / "hunts", PLANTED)
    assert not Path(h.store).exists()
    found = h.stored()
    assert dict(found) == {}
    assert not Path(h.store).exists()


def test_after_the_control_it_is_the_control_s_rows_by_the_arm_s_word(tmp_path: Path) -> None:
    h = open_scenario(tmp_path / "hunts", PLANTED)
    hunt_module().control(h)
    cells = len(PLANTED.cases) * h.settings.search.control_repeats
    assert dict(h.stored()) == {"control": cells}


class _Entry:
    """One proposed condition on some cases, as the search hands `run_search` its entries."""

    def __init__(self, text: str, case_ids: tuple[str, ...]) -> None:
        from tests.confirm_support import condition, records

        self.condition, self.cases = condition(text), case_ids
        self.selection = records().Selection(strategy="screen", probability=1)


def test_the_search_and_shrink_runs_are_there_by_their_words(tmp_path: Path) -> None:
    """The search and shrink stages are one Prove run each, `search` and `shrink`: in the store, so in the answer."""
    h = open_scenario(tmp_path / "hunts", PLANTED)
    hunt_module().control(h)
    hunt_module().run_search(h, [_Entry(on("error"), ("k1", "k2"))])
    hunt_module().run_search(h, [_Entry(on("timeout"), ("k1",))], stage="shrink")
    found = dict(h.stored())
    assert found == _store_counts(h)
    assert (found["search"], found["shrink"]) == (2, 1)


def test_after_a_confirm_stage_every_arm_is_there_with_prove_s_count(tmp_path: Path, trace: Path) -> None:
    """The control, the stage's arms and the reference arm, keyed by their words, each with the rows Prove counts."""
    h = ready(tmp_path / "hunts", PLANTED)
    confirm_module().confirm(h)
    found = dict(h.stored())
    assert found == _store_counts(h)
    assert {"control", "confirm-control", "confirm-1", "confirm-2", "confirm-3", "reference-1"} <= set(found)
    assert not any(word.startswith(f"{h.name}-") for word in found)


def test_a_recheck_s_arms_are_there_by_their_words(tmp_path: Path, trace: Path) -> None:
    """A recheck beside the old agent leaves `recheck-1-<n>` and `recheck-1-<n>-old`: the names the command reads to
    find the recheck last begun and how it was begun."""
    h = ready(tmp_path / "hunts", PLANTED)
    confirm_module().confirm(h)
    with contextlib.suppress(confirm_module().ConfirmError):
        # the stand-in for Trace holds no answer for these two arms; they are kept, which is what is read here
        confirm_module().recheck(h, old=targets.Coin())
    found = dict(h.stored())
    assert found == _store_counts(h)
    assert {"recheck-1-1", "recheck-1-1-old"} <= set(found)


def test_runs_not_counted_are_rows_of_their_arm(tmp_path: Path, trace: Path) -> None:
    """Under `error` case k12 of the gaps hunt has no outcome: its runs are stored, not counted, and counted here."""
    h = ready(tmp_path / "hunts", GAPS)
    confirm_module().confirm(h)
    arm = rows(h, "confirm-1")
    assert any(r["outcome"] is None for r in arm)
    assert h.stored()["confirm-1"] == len(arm)


def test_the_counts_are_the_store_s_when_asked_and_the_same_from_the_hunt_opened_again(tmp_path: Path,
                                                                                        trace: Path) -> None:
    """Asked on a stage the cap stopped after one run, then after it was finished through the hunt opened again: the
    first hunt's second answer is the finished stage's, and both hunts answer alike."""
    h = ready(tmp_path / "hunts", _priced())
    with pytest.raises(hunt_module().HuntStopped):
        confirm_module().confirm(h)
    first = dict(h.stored())
    assert first["confirm-control"] == 1 and "confirm-1" not in first
    again = open_scenario(tmp_path / "hunts", _priced(), existing=True, limits={"dollars": 100.0})
    confirm_module().confirm(again)
    assert dict(h.stored()) == dict(again.stored()) == _store_counts(h)
    assert dict(h.stored()) != first


def test_the_answer_cannot_be_changed(tmp_path: Path) -> None:
    h = open_scenario(tmp_path / "hunts", PLANTED)
    hunt_module().control(h)
    found = h.stored()
    with pytest.raises(TypeError):
        found["control"] = 0
    assert h.stored()["control"] == len(PLANTED.cases) * h.settings.search.control_repeats


def test_asking_runs_nothing_asks_trace_nothing_and_writes_nothing(tmp_path: Path, trace: Path,
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """On a stopped stage, where running would add rows: no agent run, no Trace call, every file keeps its bytes."""
    h = ready(tmp_path / "hunts", _priced())
    with pytest.raises(hunt_module().HuntStopped):
        confirm_module().confirm(h)
    before, asked = _files(h), len(calls(trace))
    ran: list[Any] = []

    def run(self: Any, *args: Any, **kwargs: Any) -> Any:
        ran.append(args)
        raise AssertionError("the agent was run")

    monkeypatch.setattr(targets.Coin, "run", run)
    h.stored()
    open_scenario(tmp_path / "hunts", _priced(), existing=True).stored()
    assert ran == [] and len(calls(trace)) == asked and _files(h) == before
