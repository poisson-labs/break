"""`Replayed.error`: the replayed run's one line of error when it was not counted, else `None`.

Taylor's yes to BK8 point 37 (2026-11-07). A replay whose run was not counted says `stopped` with the run's one line
of error as its sentence (point 18), and `confirm.replay` handed back no such line: the hunt module keeps it in the row
it makes, and `replay` dropped it. So `Replayed` gets one more field, `error: str | None`. BK8 Session B adds it in
`confirm.py`; this file holds it.

The line is the one the hunt module writes for such a run, so a replay and the stored row it replays say the same:
the gaps scenario's case k12 is not counted under `error` (`tests/confirm_support.py`).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from tests.confirm_support import GAPS, PLANTED, RECHECK, confirm_module, ready, record, rows, stand_in


@pytest.fixture
def trace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return stand_in(monkeypatch, tmp_path)


def _confirmed(tmp_path: Path, scenario: Any) -> tuple[Any, Any]:
    h = ready(tmp_path / "hunts", scenario)
    return h, confirm_module().confirm(h)


def test_replayed_has_an_error_field() -> None:
    assert "error" in [f.name for f in dataclasses.fields(confirm_module().Replayed)]


def test_a_replay_that_failed_has_no_error(tmp_path: Path, trace: Path) -> None:
    h, _ = _confirmed(tmp_path, PLANTED)
    replayed = confirm_module().replay(h, 1)
    assert replayed.outcome == "failed"
    assert replayed.error is None


def test_a_replay_that_did_not_fail_has_no_error(tmp_path: Path, trace: Path) -> None:
    h, _ = _confirmed(tmp_path, RECHECK)
    by_case: dict[str, list[dict[str, Any]]] = {}
    for row in rows(h, "confirm-1"):
        by_case.setdefault(record(row).case, []).append(row)
    case = next(c for c, held in by_case.items() if held[0]["outcome"] == "ok")
    replayed = confirm_module().replay(h, 1, case=case)
    assert replayed.outcome == "ok"
    assert replayed.error is None


def test_a_replay_that_was_not_counted_carries_the_line_the_stored_row_holds(tmp_path: Path, trace: Path) -> None:
    """k12 under `error`: the way in cannot reach it. The replay's line is the stored row's, for the row of the seed
    it replayed on."""
    h, done = _confirmed(tmp_path, GAPS)
    assert "k12" in done.findings[0].cases
    replayed = confirm_module().replay(h, 1, case="k12")
    assert replayed.outcome == "not counted"
    stored = next(r for r in rows(h, "confirm-1") if record(r).case == "k12" and int(r["seed"]) == replayed.seed)
    assert stored["outcome"] is None
    assert isinstance(replayed.error, str) and replayed.error.strip() and "\n" not in replayed.error
    assert replayed.error == stored["error"]
