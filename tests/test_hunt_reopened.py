"""A stage stopped for runs not counted, opened again: the share is judged over the runs stored since it was opened.

Plan BK5.12 with the runs module's point A, ruled yes on 2026-11-05 with its four parts (`evidence/bk5/point-a-built.md`):
A1, "since the hunt was opened" is the rows this opening stored in the arm, over every call that added to it; A2, the
ten that must be stored before the rule holds are counted over the same rows; A3, `HuntStopped.count` is the runs not
counted among those judged and `kept` every row the arm holds. A hunt opened once behaves as before, which the frozen
tests of `test_hunt_stops.py` hold; this holds what changes when it is opened again.

A case whose `does` is `instrument` breaks the way in, so its run is not counted; "mended" is the same case without it.
Every test reads the stop's facts, never its words.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.hunt_support import case, desk, hunt, open_new, rows, settings_for

ONCE = {"control_repeats": 1}


def _cases(dead: Any, of: int) -> list[dict[str, Any]]:
    return [case(f"k{i:02d}", **({"does": "instrument"} if i in dead else {})) for i in range(1, of + 1)]


def _stop(fn: Any) -> Any:
    try:
        fn()
    except hunt().HuntStopped as stop:
        return stop
    raise AssertionError("the control ran to its end and did not stop")


def _again(folder: Path, name: str, cases: list[dict[str, Any]], target: Any) -> Any:
    return hunt().open_hunt(settings_for(folder, search=ONCE), target=target, cases=cases, name=name, existing=True)


def test_a_stage_stopped_for_runs_not_counted_goes_on_once_opened_again_and_is_judged_since_then(tmp_path: Path) -> None:
    """(c) A control of fifteen whose first ten runs are not counted stops at ten; opened again with the cause mended,
    the same call finishes, with every row kept and only the missing runs made. (d) Opened again with the cause not
    mended, it stores ten more and stops: `kept` 20, `count` 10. (e) Opened again partly mended, two dead of the next
    ten stop it: `kept` 20, `count` 2; opened once more, the last ten finish it."""
    # (c) mended
    first = _cases(range(1, 11), 15)
    h = open_new(tmp_path / "c", cases=first, name="mended", search=ONCE)
    stop = _stop(lambda: hunt().control(h))
    assert (stop.reason, stop.kept, stop.count) == ("not counted", 10, 10)
    mended_desk = desk()
    summary = hunt().control(_again(tmp_path / "c", "mended", _cases((), 15), mended_desk))
    assert (summary.runs, summary.not_counted) == (15, 10)
    assert mended_desk.runs == 5
    assert len(rows(h, "control")) == 15

    # (d) still broken: ten more stored since the opening, all dead
    broken = _cases(range(1, 31), 30)
    h = open_new(tmp_path / "d", cases=broken, name="broken", search=ONCE)
    stop = _stop(lambda: hunt().control(h))
    assert (stop.reason, stop.kept, stop.count) == ("not counted", 10, 10)
    again_desk = desk()
    stop = _stop(lambda: hunt().control(_again(tmp_path / "d", "broken", broken, again_desk)))
    assert (stop.reason, stop.arm, stop.kept, stop.count) == ("not counted", "broken-control", 20, 10)
    assert again_desk.runs == 10

    # (e) partly mended: the first twelve dead; opened again, two of the next ten dead, more than a tenth of ten
    partly = _cases([*range(1, 11), 11, 12], 30)
    h = open_new(tmp_path / "e", cases=partly, name="partly", search=ONCE)
    stop = _stop(lambda: hunt().control(h))
    assert (stop.reason, stop.kept, stop.count) == ("not counted", 10, 10)
    stop = _stop(lambda: hunt().control(_again(tmp_path / "e", "partly", partly, desk())))
    assert (stop.reason, stop.kept, stop.count) == ("not counted", 20, 2)
    summary = hunt().control(_again(tmp_path / "e", "partly", partly, desk()))
    assert (summary.runs, summary.not_counted) == (30, 12)
