"""One confirm and one recheck end to end on the pinned Trace itself, with no stand-in (plan BK7.14's "one end-to-end
case with Trace installed": the one test here that calls the pinned Trace for real).

Like BK0's tests that read Trace, it is red while no Trace is installed: Break pins Trace at a commit on GitHub until
Trace is on PyPI (ruling 1 of `evidence/bk7/open-points.md`). Break's numbers are held to a direct call of the installed
Trace on the same two stored arms, on the same machine, which is exact (BK7.5). It also holds the recorded documents
the other tests read to what Trace prints today: the same runs give the same verdicts, and the same p-values to within
a relative 1e-9, since Trace's last digits differ between the machine the documents were recorded on and another
(2026-11-06: GitHub's Linux runners printed `test.p` and `difference.lo` a few units in the last place away from the
Mac's recording, with every verdict the same).
"""

from __future__ import annotations

import importlib.metadata
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests import confirm_targets as targets
from tests.confirm_support import PLANTED, RECORDED, confirm_module, name_of, on, open_scenario, ready


def _recorded(made_from: str) -> dict:
    for line in RECORDED.read_text(encoding="utf-8").splitlines():
        held = json.loads(line)
        if held["made_from"] == made_from:
            return json.loads(held["stdout"])
    raise AssertionError(made_from)


def _direct(h: Any, old: str, new: str) -> dict[str, Any]:
    """What the installed Trace prints for two of the hunt's arms, called directly as Break calls it."""
    command = [sys.executable, "-m", "poisson_trace", "fix-check", f"{h.name}-{old}", f"{h.name}-{new}",
               "--inputs", "all", "--event", "failed", "--max-mde", "0.2", "--store", str(h.store), "--json"]
    done = subprocess.run(command, cwd=h.folder, capture_output=True, text=True, check=False)
    assert done.stdout, done.stderr
    printed: dict[str, Any] = json.loads(done.stdout)
    return printed


def test_confirm_and_recheck_on_the_pinned_trace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTHONPATH", raising=False)
    assert importlib.metadata.version("poisson-trace") == confirm_module().TRACE_VERSION
    h = ready(tmp_path / "hunts", PLANTED)
    done = confirm_module().confirm(h)
    assert [name_of(f.condition) for f in done.findings] == [on("error")]
    assert [t.verdict for t in done.tested] == ["confirmed", "too small to tell", "too small to tell"]
    for t in done.tested:
        direct = _direct(h, "confirm-control", f"confirm-{t.number}")
        assert (t.p, t.difference, t.lo, t.hi) == (direct["test"]["p"], direct["difference"]["points"],
                                                   direct["difference"]["lo"], direct["difference"]["hi"])
        recorded = _recorded(f"planted: confirm-control against confirm-{t.number}")
        assert (direct["verdict"], direct["direction"]) == (recorded["verdict"], recorded["direction"])
        assert math.isclose(direct["test"]["p"], recorded["test"]["p"], rel_tol=1e-9)
    now = open_scenario(tmp_path / "hunts", PLANTED, weak=targets.MENDED, existing=True)
    (found,) = confirm_module().recheck(now)
    assert found.phrase == "fails less"
    assert found.gap_days is not None and 0 <= found.gap_days < 1
