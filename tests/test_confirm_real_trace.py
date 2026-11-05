"""One confirm and one recheck end to end on the pinned Trace itself, with no stand-in (plan BK7.14's "one end-to-end
case with Trace installed": the one test here that calls the pinned Trace for real).

Like BK0's tests that read Trace, it is red while no Trace is installed: Break pins Trace at a commit on GitHub until
Trace is on PyPI (ruling 1 of `evidence/bk7/open-points.md`). It also holds the recorded documents the other tests
read to what Trace prints today: the same runs give the same p-values and verdicts.
"""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import pytest

from tests import confirm_targets as targets
from tests.confirm_support import PLANTED, RECORDED, confirm_module, name_of, on, open_scenario, ready


def _recorded(made_from: str) -> dict:
    for line in RECORDED.read_text(encoding="utf-8").splitlines():
        held = json.loads(line)
        if held["made_from"] == made_from:
            return json.loads(held["stdout"])
    raise AssertionError(made_from)


def test_confirm_and_recheck_on_the_pinned_trace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTHONPATH", raising=False)
    assert importlib.metadata.version("poisson-trace") == confirm_module().TRACE_VERSION
    h = ready(tmp_path / "hunts", PLANTED)
    done = confirm_module().confirm(h)
    assert [name_of(f.condition) for f in done.findings] == [on("error")]
    assert [t.verdict for t in done.tested] == ["confirmed", "too small to tell", "too small to tell"]
    for t in done.tested:
        doc = _recorded(f"planted: confirm-control against confirm-{t.number}")
        assert (t.p, t.difference, t.lo, t.hi) == (doc["test"]["p"], doc["difference"]["points"],
                                                   doc["difference"]["lo"], doc["difference"]["hi"])
    now = open_scenario(tmp_path / "hunts", PLANTED, weak=targets.MENDED, existing=True)
    (found,) = confirm_module().recheck(now)
    assert found.phrase == "fails less"
    assert found.gap_days is not None and 0 <= found.gap_days < 1
