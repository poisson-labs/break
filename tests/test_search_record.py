"""BK6.13, the stored record: each search run's `RunRecord.selection` equals the proposal that produced it, strategy and
probability (spec §6.4, §11.3 invariant 2; ruling 29 of `evidence/bk6/open-points.md`).

`test_search_stage.py` holds what `run` is handed. This is the other half, end to end: a search stage whose `run` is the runs
module's `run_search`, a real way in, and the rows read back from the hunt's own Prove store. It stands on the two shapes the
runs module's tests froze for it (`evidence/bk5/interfaces-for-bk6.md`) and on nothing else of that module: `open_hunt` with
the hunt's `name`, `store` and `proposals`, and what `run_search` takes and returns.

The runs module and Prove are imported inside the test, so on a tree without the runs module this one test fails on its own
and the rest of the suite still runs.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from tests.search_support import Fixed, agents, catalogue, proposal, records, rng, search, seen, text_of

# The name the stage is given, which is not the settings' own strategy: a record that took the settings' word is caught.
NAME = "my_pkg.search:Mine"

LOOK_UP, POLICY, REQUEST = "tool:lookup_order#1=error", "tool:check_policy#1=timeout", "input:typos"
PAIR = "tool:check_policy#1=error + tool:lookup_order#2=timeout"

LINES: dict[str, Any] = {"lookup_order": "read", "check_policy": "read"}
CASES = ({"id": "c1", "input": "Where is order 1?"}, {"id": "c2", "input": "Where is order 2?"})

# What the scripted way in calls with no change: the order looked up, the policy checked, the order looked up again.
CONTROL = {case["id"]: {"lookup_order": 2, "check_policy": 1} for case in CASES}

SETTINGS = """\
version = 1

[target]
kind = "rollout"
entry = "tests.agents:WayIn"
cases = "cases.jsonl"

[tools]
lookup_order = "read"
check_policy = "read"

[vary]
tools = ["error", "timeout"]
inputs = ["typos"]

[search]
strategy = "random"
cases_per_condition = 2

[output]
folder = '{folder}'
"""


def test_each_search_runs_stored_record_holds_the_selection_of_the_proposal_that_produced_it(tmp_path: Path) -> None:
    """Four conditions over two batches, each with a probability of its own, and one of them proposed a second time with
    another: a record that took the first entry's selection, the settings' strategy, a probability of 1 or the dropped
    repeat's is caught. Each condition runs on both cases, so eight rows."""
    hunt_module = importlib.import_module("poisson_break.hunt")
    from poisson_prove.store import Store

    settings = importlib.import_module("poisson_break.settings").loads(SETTINGS.format(folder=tmp_path / "break-runs"))
    way_in = agents().WayIn({"lookup_order": lambda **_: "Order 7 shipped on Tuesday.",
                             "check_policy": lambda **_: "Refunds within thirty days."})
    hunt = hunt_module.open_hunt(settings, target=way_in, cases=CASES, name="refund-agent-1")

    def run(entries: Any) -> list[Any]:
        return [search().SeenRun(condition=r.condition, case=r.case, seed=r.seed, outcome=r.outcome)
                for r in hunt_module.run_search(hunt, entries)]

    strategy = Fixed([proposal(LOOK_UP, reason="the first look-up", probability=0.25),
                      proposal(POLICY, reason="the policy", probability=0.125)],
                     [proposal(LOOK_UP, reason="once more", probability=0.75),
                      proposal(REQUEST, reason="the request", probability=0.5),
                      proposal(PAIR, reason="both tools", probability=1 / 3)])
    start = seen(control=CONTROL, cat=catalogue(("error", "timeout"), ("typos",), tools=LINES), budget=40, cases_per_condition=2)
    result = search().search_stage(strategy, name=NAME, seen=start, rng=rng(), run=run, log=hunt.proposals)

    assert result.stopped is None
    ran = [e for e in result.log if e.state == "run"]
    assert [(text_of(e.condition), e.probability) for e in ran] == [(LOOK_UP, 0.25), (POLICY, 0.125), (REQUEST, 0.5), (PAIR, 1 / 3)]
    proposed = {(text_of(e.condition), case): e.selection for e in ran for case in e.cases}
    assert len(proposed) == 8

    frame = Store(hunt.store).read(f"{hunt.name}-search")
    stored = [records().RunRecord.from_dict(row["meta"]["poisson_break"]) for row in frame.to_dict("records")]
    assert len(stored) == 8, "one stored row for each run"
    found = {(record.condition.name, record.case): record.selection for record in stored}
    assert found == proposed
    assert {condition: selection for (condition, _case), selection in found.items()} == {
        LOOK_UP: records().Selection(strategy=NAME, probability=0.25),
        POLICY: records().Selection(strategy=NAME, probability=0.125),
        REQUEST: records().Selection(strategy=NAME, probability=0.5),
        PAIR: records().Selection(strategy=NAME, probability=1 / 3)}

    # The proposals file beside the store says the same of every run, so the two can be read together.
    on_disk = {(text_of(e.condition), case): e.selection
               for e in search().read_log(hunt.proposals) if e.state == "run" for case in e.cases}
    assert on_disk == found
