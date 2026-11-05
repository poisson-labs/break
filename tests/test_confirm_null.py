"""The false-finding rate with a shared control (plan BK7.8; spec §5.5, "The correction").

On a desk with a fixed failure rate and no weakness, every candidate a confirm stage confirms is a false finding, so
the false-discovery rate is the share of stages that confirm any (ruling 21 of `evidence/bk7/open-points.md`). The
simulation that measures it, 160,000 stages over eight settings with Trace's own test and Prove's `bh`, is in
`evidence/bk7/fdr-simulation.md`: at most 0.0143 against `q = 0.05`, so `bh` stands and `holm` is not needed.

This test runs four whole stages through `confirm`, eight candidates each against one shared control, on twelve cases
that each fail half their runs, against what the pinned Trace printed for them. The four seeds are the first from
20261105 on which leaving the correction out confirms a candidate; on none of the 41 seeds scanned does the correction
confirm one. So a confirm that skipped the correction, or read Trace's *different* alone, fails here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.confirm_support import NULL, NULL_SEEDS, confirm_module, ready, stand_in, trace_document


def test_a_desk_with_no_weakness_gives_no_finding_in_any_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stand_in(monkeypatch, tmp_path)
    assert len(NULL_SEEDS) == 4
    stages_with_a_finding = 0
    different_alone = 0
    for seed in NULL_SEEDS:
        h = ready(tmp_path / str(seed), NULL, search={"seed": seed})
        done = confirm_module().confirm(h)
        assert len(done.tested) == 8
        docs = [trace_document(h, "confirm-control", f"confirm-{t.number}") for t in done.tested]
        different_alone += any(d["verdict"] == "different" and d["direction"] == "failed more in new" for d in docs)
        stages_with_a_finding += bool(done.findings)
        assert [t.verdict for t in done.tested].count("confirmed") == 0
    assert different_alone == 4
    assert stages_with_a_finding / len(NULL_SEEDS) <= 0.05
