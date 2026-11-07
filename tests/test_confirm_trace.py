"""How Break calls Trace, and what it does when Trace is missing, of another version, or answers otherwise.

Plan BK7.15 (the JSON, not the exit code) and BK7.19 (Trace missing, of the wrong version, or printing a schema other
than `poisson-trace.fix-check/2` is refused before any run); spec §6.2, "How Break calls Trace". Rulings 4 (the
words, the interpreter and the folder), 5 (the version and the probe of the schema, before any run) and 6
(`ConfirmError` and its reasons) of `evidence/bk7/open-points.md`.

The stand-in answers from documents the pinned Trace printed (`tests/confirm_support.py`); where a test changes an
answer it says how, through `patch`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from tests import confirm_targets as targets
from tests.confirm_support import (
    PLANTED,
    RECORDED,
    SCHEMA,
    calls,
    confirm_module,
    fix_checks,
    hunt_module,
    ready,
    refused,
    rows,
    stand_in,
)

CANDIDATE_ARMS = ("confirm-control", "confirm-1", "confirm-2", "confirm-3")


def _arms(h: Any) -> list[str]:
    from poisson_prove.store import Store

    return sorted(Store(h.store).runs())


def _confirm_arms(h: Any) -> list[str]:
    return [a for a in _arms(h) if "-confirm" in a or "-reference" in a]


def _verdicts(done: Any) -> list[tuple[str, str | None, Any]]:
    return [(t.verdict, t.note, t.p) for t in done.tested]


def _recorded_document() -> str:
    for line in RECORDED.read_text(encoding="utf-8").splitlines():
        held = json.loads(line)
        if held["key"] != "probe" and held["stdout"].strip():
            return str(held["stdout"])
    raise AssertionError("no recorded document")


# ---------------------------------------------------------------------------
# ruling 4: the words, the interpreter, the folder
# ---------------------------------------------------------------------------


def test_each_candidate_is_put_to_trace_once_against_the_shared_control_in_the_ruled_words(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = stand_in(monkeypatch, tmp_path)
    h = ready(tmp_path / "hunts", PLANTED)
    done = confirm_module().confirm(h)
    asked = fix_checks(log)
    pairs = [(c["argv"][1], c["argv"][2]) for c in asked if "-reference" not in c["argv"][2]]
    assert pairs == [(f"{h.name}-confirm-control", f"{h.name}-confirm-{n}") for n in (1, 2, 3)]
    for call in asked:
        words = call["argv"]
        flags = dict(zip(words[3::2], words[4::2], strict=False))
        assert words[0] == "fix-check"
        assert "--json" in words[3:]
        assert Path(flags["--store"]).resolve() == Path(h.store).resolve()
        assert (flags["--event"], flags["--inputs"]) == ("failed", "all")
        assert float(flags["--max-mde"]) == h.settings.confirm.max_difference
        assert "--alpha" not in words
        assert Path(call["cwd"]).resolve() == Path(h.folder).resolve()
        assert Path(call["python"]).resolve() == Path(sys.executable).resolve()
    assert len(done.tested) == 3


def test_the_difference_asked_for_is_the_settings_max_difference(tmp_path: Path,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """`--max-mde` carries `max_difference`, not a constant: 0.25 here, every answer the recorded one. (The probe of
    the schema, on a store of Break's own, asks what it likes.)"""
    log = stand_in(monkeypatch, tmp_path, patch={"*": {"stdout": _recorded_document(), "exit": 0}})
    h = ready(tmp_path / "hunts", PLANTED, confirm={"max_difference": 0.25})
    confirm_module().confirm(h)
    asked = fix_checks(log)
    assert asked
    for call in asked:
        words = call["argv"]
        assert float(words[words.index("--max-mde") + 1]) == 0.25


def test_the_version_is_asked_before_the_first_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ruling 5: `python -m poisson_trace --version`, then the probe, then the runs."""
    log = stand_in(monkeypatch, tmp_path)
    h = ready(tmp_path / "hunts", PLANTED)
    runs_before = h.target.runs
    confirm_module().confirm(h)
    every = calls(log)
    assert every[0]["argv"] == ["--version"]
    assert every[1]["argv"][0] == "fix-check" and every[1]["probe"] is True
    probe_store = Path(every[1]["argv"][every[1]["argv"].index("--store") + 1]).resolve()
    assert Path(h.folder).resolve() not in probe_store.parents
    assert h.target.runs > runs_before


# ---------------------------------------------------------------------------
# BK7.19: missing, another version, another schema: refused before any run
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("how, reason", [
    pytest.param({"missing": True}, "trace missing", id="missing"),
    pytest.param({"version": "0.0.1"}, "trace version", id="another version"),
    pytest.param({"version": "0.1.0rc1"}, "trace version", id="the release before"),
    pytest.param({"patch": {"*": {"set": {"schema": "poisson-trace.fix-check/3"}}}}, "trace schema",
                 id="another schema"),
    pytest.param({"patch": {"*": {"set": {"schema": "poisson-trace.fix-check/1"}}}}, "trace schema",
                 id="the old schema"),
])
def test_confirm_refuses_before_any_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, how: dict[str, Any],
                                        reason: str) -> None:
    stand_in(monkeypatch, tmp_path, **how)
    h = ready(tmp_path / "hunts", PLANTED)
    runs = h.target.runs
    error = refused(confirm_module().confirm, h)
    assert error.reason == reason
    assert h.target.runs == runs
    assert _confirm_arms(h) == []
    assert not (Path(h.folder) / "confirm.json").exists()


def test_the_right_version_and_schema_are_taken(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The accepted control of the refusals above: the version is `TRACE_VERSION` and the schema is the pinned one."""
    stand_in(monkeypatch, tmp_path, version=confirm_module().TRACE_VERSION,
             patch={"*": {"set": {"schema": SCHEMA}}})
    h = ready(tmp_path / "hunts", PLANTED)
    assert len(confirm_module().confirm(h).tested) == 3


@pytest.mark.parametrize("how, reason", [
    pytest.param({"missing": True}, "trace missing", id="missing"),
    pytest.param({"version": "0.0.1"}, "trace version", id="another version"),
    pytest.param({"patch": {"*": {"set": {"schema": "poisson-trace.fix-check/3"}}}}, "trace schema",
                 id="another schema"),
])
def test_recheck_refuses_before_any_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, how: dict[str, Any],
                                        reason: str) -> None:
    stand_in(monkeypatch, tmp_path)
    h = ready(tmp_path / "hunts", PLANTED)
    assert confirm_module().confirm(h).findings
    stand_in(monkeypatch, tmp_path, **how)
    again = hunt_module().open_hunt(h.settings, target=targets.Coin(), cases=PLANTED.cases, name=h.name,
                                    existing=True)
    error = refused(confirm_module().recheck, again)
    assert error.reason == reason
    assert [a for a in _arms(h) if "-recheck" in a] == []
    assert again.target.runs == 0


# ---------------------------------------------------------------------------
# BK7.15: the JSON, never the exit code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", [1, 3, 4, 130])
def test_a_document_read_whatever_the_exit_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    stand_in(monkeypatch, tmp_path / "plain")
    plain = _verdicts(confirm_module().confirm(ready(tmp_path / "a", PLANTED)))
    stand_in(monkeypatch, tmp_path / "exits", patch={"confirm-1": {"exit": code}, "confirm-2": {"exit": code}})
    exited = _verdicts(confirm_module().confirm(ready(tmp_path / "b", PLANTED)))
    assert exited == plain


def test_an_exit_of_nothing_wrong_with_no_document_is_no_answer(tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """Read from the JSON, so an exit of 0 with no JSON is no answer: `trace answer`, the arms kept."""
    stand_in(monkeypatch, tmp_path, patch={"confirm-2": {"stdout": "all good\n", "exit": 0}})
    h = ready(tmp_path / "hunts", PLANTED)
    error = refused(confirm_module().confirm, h)
    assert error.reason == "trace answer"
    for arm in CANDIDATE_ARMS:
        assert len(rows(h, arm)) == 30, arm


@pytest.mark.parametrize("patch", [
    pytest.param({"confirm-1": {"set": {"schema": "poisson-trace.fix-check/3"}}}, id="another schema mid-stage"),
    pytest.param({"confirm-1": {"set": {"verdict": "differs"}}}, id="a verdict word Trace does not have"),
    pytest.param({"confirm-1": {"set": {"direction": "failed more"}}}, id="a direction word Trace does not have"),
    pytest.param({"confirm-1": {"drop": ["test.p"]}}, id="no p-value"),
    pytest.param({"confirm-1": {"drop": ["difference"]}}, id="no difference"),
    pytest.param({"confirm-1": {"stdout": "", "exit": 1}}, id="no document and an exit of 1"),
    pytest.param({"confirm-1": {"stdout": "", "exit": 0}}, id="no document and an exit of 0"),
])
def test_a_document_break_cannot_read_is_no_answer_and_the_arms_are_kept(tmp_path: Path,
                                                                        monkeypatch: pytest.MonkeyPatch,
                                                                        patch: dict[str, Any]) -> None:
    """Ruling 6. With no JSON while every case has an outcome, it is no answer, not *nothing to compare* (ruling 11
    is for an arm in which no case has one)."""
    stand_in(monkeypatch, tmp_path, patch=patch)
    h = ready(tmp_path / "hunts", PLANTED)
    error = refused(confirm_module().confirm, h)
    assert error.reason == "trace answer"
    for arm in CANDIDATE_ARMS:
        assert len(rows(h, arm)) == 30, arm
