"""`read_findings(hunt)`: every finding a hunt has a file for, in the order of their numbers.

Ruled 2026-11-06 and given its test 2026-11-07 (`evidence/bk7/rulings-build.md`, yes/no A, seven points); plan BK7's
public names, "*Ruled 2026-11-06 and not built, its test first*". The `findings` verb reads through it (plan BK8). Each
test names the point it holds. The frozen `PUBLIC_NAMES` of `tests/confirm_support.py` is not touched: point 1 is held
here.

On the stand-in for Trace, with no new recorded document: every stage below is one the confirm module's own tests
already run.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.confirm_support import (
    PLANTED,
    STEADY,
    calls,
    confirm_module,
    open_scenario,
    ready,
    refused,
    stand_in,
    trace_document,
)


@pytest.fixture
def trace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return stand_in(monkeypatch, tmp_path)


def read_findings(h: Any) -> Any:
    return confirm_module().read_findings(h)


def _files(h: Any) -> dict[str, bytes]:
    folder = Path(h.folder)
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def _two_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any, Any]:
    """Planted, its second candidate *too small to tell* in stage 1 and then *different, failed more* at a p that holds
    in stage 2: finding 1 from stage 1, finding 2 from stage 2. The second stage's answer is the first stage's document
    for that candidate, patched, since nothing was recorded for six repeats of the planted desk."""
    nsd = {"confirm-3": {"set": {"verdict": "no significant difference"}}}
    stand_in(monkeypatch, tmp_path, patch=nsd)
    h = ready(tmp_path / "hunts", PLANTED)
    first = confirm_module().confirm(h)
    assert [t.verdict for t in first.tested] == ["confirmed", "too small to tell", "not confirmed"]
    again = trace_document(h, "confirm-control", "confirm-2")
    again.update({"verdict": "different", "direction": "failed more in new"})
    again["test"]["p"] = 0.001
    stand_in(monkeypatch, tmp_path, patch={**nsd, "confirm-2-2": {"stdout": json.dumps(again), "exit": 0}})
    second = confirm_module().confirm(h, repeats=6)
    assert [f.number for f in second.findings] == [2]
    return h, first, second


# ---------------------------------------------------------------------------
# point 1: the name
# ---------------------------------------------------------------------------


def test_read_findings_is_a_public_name_of_the_confirm_module() -> None:
    module = confirm_module()
    assert "read_findings" in module.__all__
    assert callable(module.read_findings)


def test_read_findings_hands_back_a_tuple_of_findings(tmp_path: Path, trace: Path) -> None:
    h = ready(tmp_path / "hunts", PLANTED)
    confirm_module().confirm(h)
    found = read_findings(h)
    assert type(found) is tuple
    assert found and all(isinstance(f, confirm_module().Finding) for f in found)


# ---------------------------------------------------------------------------
# point 2: every file, in number order, across stages
# ---------------------------------------------------------------------------


def test_after_one_stage_it_is_each_file_read_and_the_stage_s_findings(tmp_path: Path, trace: Path) -> None:
    h = ready(tmp_path / "hunts", PLANTED)
    done = confirm_module().confirm(h)
    assert done.findings
    numbers = sorted(int(p.stem) for p in (Path(h.folder) / "findings").glob("*.toml"))
    assert read_findings(h) == tuple(confirm_module().read_finding(h, n) for n in numbers)
    assert read_findings(h) == tuple(done.findings)


def test_after_a_second_stage_it_holds_both_stages_findings_in_number_order(tmp_path: Path,
                                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    h, first, second = _two_stages(tmp_path, monkeypatch)
    found = read_findings(h)
    assert [f.number for f in found] == [1, 2]
    assert found == (*first.findings, *second.findings)
    assert [f.stage for f in found] == [1, 2]


def test_read_on_a_hunt_opened_again_it_is_the_same(tmp_path: Path, trace: Path) -> None:
    """What is on disk decides, not what the open hunt remembers: the same tuple from the hunt opened again."""
    h = ready(tmp_path / "hunts", PLANTED)
    confirm_module().confirm(h)
    again = open_scenario(tmp_path / "hunts", PLANTED, existing=True)
    assert read_findings(again) == read_findings(h)


# ---------------------------------------------------------------------------
# point 3: none, and nothing done
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("folder", ["missing", "empty"])
def test_a_hunt_with_no_finding_gives_an_empty_tuple_and_does_nothing(tmp_path: Path, trace: Path,
                                                                      folder: str) -> None:
    h = ready(tmp_path / "hunts", PLANTED)
    if folder == "empty":
        (Path(h.folder) / "findings").mkdir()
    before = _files(h)
    runs = h.target.runs
    assert read_findings(h) == ()
    assert h.target.runs == runs
    assert calls(trace) == []
    assert _files(h) == before


def test_a_stage_that_confirmed_nothing_gives_an_empty_tuple(tmp_path: Path, trace: Path) -> None:
    h = ready(tmp_path / "hunts", STEADY)
    done = confirm_module().confirm(h)
    assert done.findings == ()
    asked = len(calls(trace))
    assert read_findings(h) == ()
    assert len(calls(trace)) == asked


# ---------------------------------------------------------------------------
# point 4: a gap is passed over
# ---------------------------------------------------------------------------


def test_a_missing_number_is_passed_over(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With `1.toml` and `3.toml` on disk it hands back findings 1 and 3: finding 2 renumbered 3 by hand, its file
    written through `write_finding`, and `2.toml` taken away."""
    h, first, second = _two_stages(tmp_path, monkeypatch)
    folder = Path(h.folder) / "findings"
    moved = dataclasses.replace(second.findings[0], number=3)
    confirm_module().write_finding(h, moved)
    (folder / "2.toml").unlink()
    found = read_findings(h)
    assert [f.number for f in found] == [1, 3]
    assert found == (first.findings[0], moved)


# ---------------------------------------------------------------------------
# point 5: only <n>.toml, n a plain whole number from 1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stray", ["notes.toml", "01.toml", "0.toml", "1.txt", "-1.toml", "1.5.toml", "+2.toml",
                                   "1.toml.bak", " 2.toml"])
def test_a_file_that_is_not_a_finding_s_name_is_passed_over(tmp_path: Path, trace: Path, stray: str) -> None:
    """Each stray holds a finding's own text, so only its name can keep it out: read, it would be one more finding."""
    h = ready(tmp_path / "hunts", PLANTED)
    confirm_module().confirm(h)
    folder = Path(h.folder) / "findings"
    expected = read_findings(h)
    shutil.copy(folder / "1.toml", folder / stray)
    assert read_findings(h) == expected


def test_a_finding_name_past_nine_is_read_in_number_order_not_text_order(tmp_path: Path, trace: Path) -> None:
    """Findings 2 and 10, written through `write_finding`: by number, 2 comes before 10 (as text it would not)."""
    h = ready(tmp_path / "hunts", PLANTED)
    confirm_module().confirm(h)
    (one,) = read_findings(h)
    for number in (2, 10):
        confirm_module().write_finding(h, dataclasses.replace(one, number=number))
    assert [f.number for f in read_findings(h)] == [1, 2, 10]


# ---------------------------------------------------------------------------
# point 6: one unreadable file refuses the whole call
# ---------------------------------------------------------------------------


def _damaged(h: Any, how: str) -> Path:
    folder = Path(h.folder) / "findings"
    target = folder / "2.toml"
    text = (folder / "1.toml").read_text(encoding="utf-8")
    if how == "not toml":
        target.write_text("this is = = not toml\n", encoding="utf-8")
    elif how == "other schema":
        target.write_text(text.replace("poisson_break.finding/1", "poisson_break.finding/9"), encoding="utf-8")
    elif how == "other hunt":
        target.write_text(text.replace('hunt = "planted"', 'hunt = "someone-else"').replace(
            "planted-", "someone-else-"), encoding="utf-8")
    elif how == "a field missing":
        target.write_text("\n".join(line for line in text.splitlines() if not line.startswith("condition = "))
                          + "\n", encoding="utf-8")
    return target


@pytest.mark.parametrize("how", ["not toml", "other schema", "other hunt", "a field missing"])
def test_one_file_that_cannot_be_read_refuses_the_whole_call(tmp_path: Path, trace: Path, how: str) -> None:
    """Finding 1 is good and `2.toml` is not: `unknown finding`, and nothing handed back. The control: the same hunt
    with `2.toml` a good copy of finding 1 renumbered reads as two findings."""
    h = ready(tmp_path / "hunts", PLANTED)
    confirm_module().confirm(h)
    (one,) = read_findings(h)
    confirm_module().write_finding(h, dataclasses.replace(one, number=2))
    assert [f.number for f in read_findings(h)] == [1, 2]
    _damaged(h, how)
    error = refused(read_findings, h)
    assert error.reason == "unknown finding"


def test_the_refusal_names_the_file(tmp_path: Path, trace: Path) -> None:
    """"Naming the file": finding 7's file is the bad one, and the refusal's line holds `7`, a number no other part of
    this hunt's findings has."""
    h = ready(tmp_path / "hunts", PLANTED)
    confirm_module().confirm(h)
    folder = Path(h.folder) / "findings"
    (folder / "7.toml").write_text("this is = = not toml\n", encoding="utf-8")
    error = refused(read_findings, h)
    assert error.reason == "unknown finding"
    text = str(error).replace(str(tmp_path), "")
    assert "7" in text


# ---------------------------------------------------------------------------
# point 7: a hunt of the wrong shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wrong", [None, "planted", 7, Path(".")])
def test_a_hunt_of_the_wrong_shape_is_refused_as_every_other_name_of_the_module_refuses_it(wrong: Any) -> None:
    """"As for every other name of the module": whatever `read_finding` raises for something that is not an open
    hunt, `read_findings` raises too, before reading anything."""
    with pytest.raises(Exception) as other:
        confirm_module().read_finding(wrong, 1)
    with pytest.raises(type(other.value)):
        read_findings(wrong)

