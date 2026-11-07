"""`q` and `max_difference` in each stage of `confirm.json`, and a stage read under what it was run under.

Ruled 2026-11-06 and given its test 2026-11-07 (`evidence/bk7/rulings-build.md`, yes/no B, nine points); spec §5.5,
"Asking again", "*Ruled 2026-11-06 and not yet built, its test first*". It takes back the first sentence of the build's
choice 15 ("a finished stage asked again is read under the settings as they are now"). Each test names the point it
holds.

On the stand-in for Trace. Its recorded documents were made at `--max-mde 0.2`, and it looks a document up by the
counts *and* that value, so a call made at any other value finds no document and exits 99: a stage asked with the
settings' value as they are now, not its own, fails loudly here. `recheck` and the probe of Trace's schema still read
the settings as they are now, on purpose (the ruling's last paragraph); the probe's document answers at any value.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tests.confirm_support import (
    CORRECTION,
    PLANTED,
    confirm_module,
    fix_checks,
    hunt_module,
    name_of,
    on,
    open_scenario,
    read_json,
    ready,
    rows,
    stand_in,
    tested_by_condition as by_condition,
    trace_document,
)


@pytest.fixture
def trace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return stand_in(monkeypatch, tmp_path)


def _stages(h: Any) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = read_json(Path(h.folder) / "confirm.json")["stages"]
    return stages


def _max_mde(call: dict[str, Any]) -> float:
    words = call["argv"]
    return float(words[words.index("--max-mde") + 1])


def _findings_files(h: Any) -> dict[str, bytes]:
    folder = Path(h.folder) / "findings"
    return {p.name: p.read_bytes() for p in sorted(folder.glob("*"))} if folder.exists() else {}


def _priced(scenario: Any = PLANTED, name: str = "priced") -> Any:
    """The scenario with every run costing $0.001 and a cap that stops the confirm stage after its first run (the
    control's fourteen runs spend $0.014, the cap is $0.0155)."""
    return dataclasses.replace(scenario, name=name, cases=tuple({**c, "tokens": [1000, 0]} for c in scenario.cases),
                               limits={"dollars": 0.0155, "input_per_million": 1.0, "output_per_million": 1.0})


# ---------------------------------------------------------------------------
# point 1: on disk, with the rest of the design, before the first run
# ---------------------------------------------------------------------------


def test_each_stage_holds_the_q_and_max_difference_it_was_written_under(tmp_path: Path, trace: Path) -> None:
    h = ready(tmp_path / "hunts", PLANTED, confirm={"q": 0.04, "max_difference": 0.2})
    confirm_module().confirm(h)
    (stage,) = _stages(h)
    assert stage["q"] == 0.04
    assert stage["max_difference"] == 0.2
    assert {"number", "repeats", "cases", "arms"} <= set(stage)


def test_the_two_values_are_on_disk_before_the_stage_s_first_run(tmp_path: Path, trace: Path) -> None:
    """Stopped by the dollar cap after its first run, the stage's `q` and `max_difference` are already written."""
    priced = _priced()
    h = ready(tmp_path / "hunts", priced, confirm={"q": 0.03})
    with pytest.raises(hunt_module().HuntStopped):
        confirm_module().confirm(h)
    assert len(rows(h, "confirm-control")) == 1
    (stage,) = _stages(h)
    assert (stage["q"], stage["max_difference"]) == (0.03, 0.2)


def test_the_values_written_are_the_settings_not_a_default(tmp_path: Path, trace: Path) -> None:
    """Two hunts under two `q`s write two `q`s: the value is read from the settings the hunt was open under."""
    one = ready(tmp_path / "a", PLANTED, confirm={"q": 0.01})
    two = ready(tmp_path / "b", PLANTED, confirm={"q": 0.10})
    confirm_module().confirm(one)
    confirm_module().confirm(two)
    assert (_stages(one)[0]["q"], _stages(two)[0]["q"]) == (0.01, 0.10)


# ---------------------------------------------------------------------------
# point 2: the schema name stays
# ---------------------------------------------------------------------------


def test_the_schema_name_stays_confirm_1(tmp_path: Path, trace: Path) -> None:
    h = ready(tmp_path / "hunts", PLANTED)
    confirm_module().confirm(h)
    assert read_json(Path(h.folder) / "confirm.json")["schema"] == "poisson_break.confirm/1"


# ---------------------------------------------------------------------------
# point 3: a looser q does not confirm what the stage's q did not
# ---------------------------------------------------------------------------


def test_a_finished_stage_asked_again_under_a_looser_q_gives_the_same_confirmation(tmp_path: Path,
                                                                                    trace: Path) -> None:
    """The correction scenario: `error` is *different* by Trace alone (p 0.0209) and 0.167 once adjusted across the
    eight, so `not after the correction` at 0.05. Opened again under `q = 0.2`, which would confirm it, it stays so,
    and no finding file is written."""
    h = ready(tmp_path / "hunts", CORRECTION)
    first = confirm_module().confirm(h)
    t = by_condition(first)[on("error")]
    assert (t.verdict, t.note) == ("not confirmed", "not after the correction")
    assert 0.05 < t.adjusted_p <= 0.2
    files = _findings_files(h)
    again = open_scenario(tmp_path / "hunts", CORRECTION, existing=True, confirm={"q": 0.2})
    second = confirm_module().confirm(again)
    assert second == first
    assert second.findings == ()
    assert _findings_files(h) == files


# ---------------------------------------------------------------------------
# point 4: a stricter q does not take back what the stage's q confirmed
# ---------------------------------------------------------------------------


def test_a_finding_confirmed_at_the_stage_s_q_stays_under_a_stricter_one(tmp_path: Path, trace: Path) -> None:
    h = ready(tmp_path / "hunts", PLANTED)
    first = confirm_module().confirm(h)
    (finding,) = first.findings
    files = _findings_files(h)
    strict = finding.adjusted_p / 10
    again = open_scenario(tmp_path / "hunts", PLANTED, existing=True, confirm={"q": strict})
    second = confirm_module().confirm(again)
    assert second == first
    assert second.findings == (finding,)
    assert _findings_files(h) == files


# ---------------------------------------------------------------------------
# point 5: asked again, Trace is asked with the stage's own max_difference
# ---------------------------------------------------------------------------


def test_a_finished_stage_asked_again_asks_trace_with_its_own_max_difference(tmp_path: Path, trace: Path) -> None:
    h = ready(tmp_path / "hunts", PLANTED)
    first = confirm_module().confirm(h)
    asked = len(fix_checks(trace))
    again = open_scenario(tmp_path / "hunts", PLANTED, existing=True, confirm={"max_difference": 0.3})
    second = confirm_module().confirm(again)
    later = fix_checks(trace)[asked:]
    assert later, "the stage asked again asked Trace nothing"
    assert {_max_mde(c) for c in later} == {0.2}
    assert second == first
    (finding,) = second.findings
    words = finding.trace.split()
    assert float(words[words.index("--max-mde") + 1]) == 0.2


# ---------------------------------------------------------------------------
# point 6: a stopped stage taken up under other settings
# ---------------------------------------------------------------------------


def test_a_stopped_stage_taken_up_under_other_settings_is_read_under_its_written_values(
        tmp_path: Path, trace: Path) -> None:
    """Stopped after its first run at `q = 0.05`, `max_difference = 0.2`; taken up with the cap lifted, `q = 0.2` and
    `max_difference = 0.3`: it finishes, Trace is asked at 0.2 throughout, and the verdicts are those the planted stage
    gives at 0.05."""
    priced = _priced()
    h = ready(tmp_path / "hunts", priced)
    with pytest.raises(hunt_module().HuntStopped):
        confirm_module().confirm(h)
    again = open_scenario(tmp_path / "hunts", priced, existing=True,
                          limits={"dollars": 100.0}, confirm={"q": 0.2, "max_difference": 0.3})
    done = confirm_module().confirm(again)
    assert {_max_mde(c) for c in fix_checks(trace)} == {0.2}
    plain = ready(tmp_path / "plain", PLANTED)
    expected = confirm_module().confirm(plain)
    assert [(name_of(t.condition), t.verdict, t.note, t.adjusted_p) for t in done.tested] == [
        (name_of(t.condition), t.verdict, t.note, t.adjusted_p) for t in expected.tested]
    assert [f.q for f in done.findings] == [0.05]
    (stage,) = _stages(h)
    assert (stage["q"], stage["max_difference"]) == (0.05, 0.2)


# ---------------------------------------------------------------------------
# point 7: a finding first written when its stage is asked again carries the stage's q
# ---------------------------------------------------------------------------


def test_a_finding_first_written_when_its_stage_is_asked_again_carries_the_stage_s_q(tmp_path: Path,
                                                                                    trace: Path) -> None:
    """The stage as if stopped just after its last run, its finding unwritten: the file is taken away. Asked again on
    the hunt opened under `q = 0.2`, the file written then holds `q = 0.05`, and its Trace command `--max-mde 0.2`."""
    h = ready(tmp_path / "hunts", PLANTED)
    first = confirm_module().confirm(h)
    (finding,) = first.findings
    (Path(h.folder) / "findings" / "1.toml").unlink()
    again = open_scenario(tmp_path / "hunts", PLANTED, existing=True, confirm={"q": 0.2, "max_difference": 0.3})
    confirm_module().confirm(again)
    written = confirm_module().read_finding(again, 1)
    assert written.q == 0.05
    assert written == finding


# ---------------------------------------------------------------------------
# point 8: asking again with repeats under other settings
# ---------------------------------------------------------------------------


def test_asking_again_judges_the_latest_stage_under_its_values_and_writes_the_new_one_under_the_settings(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Planted, its second candidate *too small to tell* at 0.2. Opened again under `max_difference = 0.3` and
    `q = 0.1`, `confirm(repeats=6)` asks Trace about stage 1 at 0.2 and runs stage 2 for the second candidate alone,
    which holds 0.3 and 0.1 and is asked at 0.3. (Stage 2's answer is stage 1's document for the candidate, given
    whatever the counts, since nothing was recorded at six repeats or at 0.3.)"""
    nsd = {"confirm-3": {"set": {"verdict": "no significant difference"}}}
    log = stand_in(monkeypatch, tmp_path, patch=nsd)
    h = ready(tmp_path / "hunts", PLANTED)
    first = confirm_module().confirm(h)
    assert [t.verdict for t in first.tested] == ["confirmed", "too small to tell", "not confirmed"]
    answer = json.dumps(trace_document(h, "confirm-control", "confirm-2"))
    log = stand_in(monkeypatch, tmp_path, patch={**nsd, "confirm-2-2": {"stdout": answer, "exit": 0}})
    asked = len(fix_checks(log))
    again = open_scenario(tmp_path / "hunts", PLANTED, existing=True, confirm={"max_difference": 0.3, "q": 0.1})
    second = confirm_module().confirm(again, repeats=6)
    assert [name_of(t.condition) for t in second.tested] == [on("timeout")]
    later = fix_checks(log)[asked:]
    by_arm = {c["argv"][2].rsplit("-confirm-", 1)[1]: _max_mde(c) for c in later}
    assert {arm: mde for arm, mde in by_arm.items() if not arm.startswith("2-")} == {"1": 0.2, "2": 0.2, "3": 0.2}
    assert by_arm["2-2"] == 0.3
    one, two = _stages(h)
    assert (one["q"], one["max_difference"]) == (0.05, 0.2)
    assert (two["q"], two["max_difference"]) == (0.1, 0.3)


# ---------------------------------------------------------------------------
# point 9: a stage without the two is a hunt file Break can no longer read
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("drop", [("q",), ("max_difference",), ("q", "max_difference")])
def test_a_stage_without_the_two_is_the_runs_module_s_refusal(tmp_path: Path, trace: Path,
                                                             drop: tuple[str, ...]) -> None:
    """The control: the file as written reads, and the stage asked again gives the same confirmation."""
    h = ready(tmp_path / "hunts", PLANTED)
    first = confirm_module().confirm(h)
    path = Path(h.folder) / "confirm.json"
    held = read_json(path)
    assert confirm_module().confirm(h) == first
    for key in drop:
        del held["stages"][0][key]
    path.write_text(json.dumps(held), encoding="utf-8")
    with pytest.raises(hunt_module().HuntError):
        confirm_module().confirm(h)

