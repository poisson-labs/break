"""Point 11: every field of every verb's `--json` document, and each schema's name.

Ruled 2026-11-08 (Break — Decisions; `evidence/bk8f/field-tables.md`, marked ruled): the tables are the documents'
fields, with F1, F2, F4 to F10, F13 and F14 changed as recommended, F11 and F12 as they are. What changed:

- F1  `init`'s case file is `cases_file`, not `cases`.
- F2  In every plan `runs` is what the plan may make from here; no plan has `left`.
- F3  (R3, its own file) a dry run of `hunt --hunt NAME` plans the hunt taken up, so its document names the hunt.
- F4  `confirm --repeats`'s plan counts as `candidates` the candidates it asks about again.
- F5  Each tested candidate and each rechecked finding carries `no_outcome` (the cases with no outcome in an arm, in
      the cases' order) and `left_out` (Trace's counts).
- F6  Taken back (R7, 2026-11-08): `gap_days` stays rounded as the screen prints it, since Trace's gap moves between
      two readings of one recheck and two frozen tests hold those two documents byte for byte the same.
- F7  The listing's `control` is null while the control is not finished.
- F8  A Ctrl-C document carries the stop's keys: `reason` `interrupted`, `arm`, `kept`, `unclassed`. For `confirm` and
      `recheck` (R5, 2026-11-08) `kept` is the rows the interrupted stage's own arms hold (the recheck's both sides
      under `--old`), `arm` the arm whose run was interrupted, and the stop's sentence names the number, as `hunt`'s.
- F9  Every `not ready` document carries `key`, `line` and `unclassed`, null or empty where they do not apply.
- F10 Each plan has its verb's schema: `poisson_break.<verb>-plan/1`.
- F13 `confirm` names the finding files it wrote, as `wrote`, from the project folder.
- F14 Each plan carries `dollars` beside its estimate, null without prices or before the control has run. A hunt
      taken up after its control has run, with prices (R6, 2026-11-08), plans its runs left at the control's cost of
      one, as `confirm` does, and `dollars` is that number.

**What is held for each document.** Its first keys `schema`, `verdict`, `sentence` (BK8.2), a plan's `estimate` and
`source` next, `next` last when there is one; its other keys, exactly the table's; and each value against a fact read
for itself: the store, the hunt's files, the settings module's plan, the library's own answer. Every document is the
command's own, made by running it under `--json` on pipes.

R5, R6 and R7 were found writing these and ruled yes as recommended (2026-11-08, `open-points.md`); their tests are
here.
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from tests import commands_hunts as hunts
from tests.commands_spies import RUN_ONCE_REFUSED, spying
from tests.commands_support import (
    CODES,
    MIXED,
    MIXED_SETTINGS,
    Project,
    cases,
    child_env,
    cli,
    holds_number,
    json_document,
    on,
    opened,
    prepared,
    project,
)

PLAN_FIRST = ["schema", "verdict", "sentence", "estimate", "source"]
RESULT_FIRST = ["schema", "verdict", "sentence"]


def doc(ran: Any, code: int = CODES["done"]) -> dict[str, Any]:
    assert ran.exit == code, ran
    return json_document(ran)


def data_keys(document: dict[str, Any]) -> set[str]:
    """The document's own fields: everything but the first keys and `next`."""
    first = PLAN_FIRST if document.get("verdict") == "plan" else RESULT_FIRST
    keys = list(document)
    assert keys[:len(first)] == first, keys
    if "next" in keys:
        assert keys[-1] == "next", keys
    return set(keys[len(first):]) - {"next"}


def settings_of(proj: Project) -> Any:
    from poisson_break.settings import load

    return load(proj.settings)


def control_summary(proj: Project) -> Any:
    from poisson_break.hunt import control

    with contextlib.chdir(proj.folder):
        return control(opened(proj, "desk-1"))


def stored_rows(proj: Project, arm: str) -> list[dict[str, Any]]:
    from poisson_prove.store import Store

    return list(Store(proj.hunt("desk-1") / "store").read(f"desk-1-{arm}").to_dict("records"))


# ---------------------------------------------------------------------------
# the documents, made once
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def road(tmp_path_factory: pytest.TempPathFactory) -> tuple[Project, dict[str, Any]]:
    """`MIXED` from the start: catalog, doctor, doctor --run, the hunt's plan, the hunt."""
    proj = project(tmp_path_factory.mktemp("road"), MIXED, **MIXED_SETTINGS)
    docs = {
        "catalog": doc(cli(proj, "catalog", "--json")),
        "doctor": doc(cli(proj, "doctor", "--json")),
        "doctor --run": doc(cli(proj, "doctor", "--run", "--yes", "--json")),
        "hunt plan": doc(cli(proj, "hunt", "--dry-run", "--json")),
        "hunt": doc(cli(proj, "hunt", "--yes", "--json", timeout=1200)),
    }
    return proj, docs


@pytest.fixture(scope="module")
def confirmed(tmp_path_factory: pytest.TempPathFactory) -> tuple[Project, dict[str, Any]]:
    """`MIXED`'s three candidates written: confirm's plan, confirm, asking again's plan, the listing, finding 1, its
    replay, recheck's plan and the recheck."""
    proj = hunts.fresh(tmp_path_factory.mktemp("confirmed"))
    docs: dict[str, Any] = {"confirm plan": doc(cli(proj, "confirm", "--dry-run", "--json"))}
    docs["confirm"] = doc(cli(proj, "confirm", "--yes", "--json", timeout=1200))
    docs["confirm --repeats plan"] = doc(cli(proj, "confirm", "--repeats", "6", "--dry-run", "--json"))
    docs["findings"] = doc(cli(proj, "findings", "--json"))
    docs["findings 1"] = doc(cli(proj, "findings", "1", "--json"))
    docs["replay 1"] = doc(cli(proj, "replay", "1", "--json"))
    docs["recheck plan"] = doc(cli(proj, "recheck", "--dry-run", "--json"))
    docs["recheck"] = doc(cli(proj, "recheck", "--yes", "--json", timeout=1200))
    return proj, docs


@pytest.fixture(scope="module")
def capped(tmp_path_factory: pytest.TempPathFactory) -> tuple[Project, dict[str, Any]]:
    """A hunt of three cases the dollar cap stops after one run: the stop, the dry run of its resume, the listing."""
    proj = project(tmp_path_factory.mktemp("capped"), cases(3, weak_to=["error"], tokens=[1000, 0]),
                   limits={"dollars": 0.0015, **hunts.PRICES})
    docs = {"hunt stopped": doc(cli(proj, "hunt", "--yes", "--json"), CODES["stopped"])}
    docs["hunt --hunt plan"] = doc(cli(proj, "hunt", "--hunt", "desk-1", "--dry-run", "--json"))
    docs["findings, control not finished"] = doc(cli(proj, "findings", "--json"))
    return proj, docs


@pytest.fixture(scope="module")
def stopped_confirm(tmp_path_factory: pytest.TempPathFactory) -> tuple[Project, dict[str, Any]]:
    proj = hunts.stopped_confirm(tmp_path_factory.mktemp("stopped-confirm"))
    return proj, {"confirm plan, taken up": doc(cli(proj, "confirm", "--dry-run", "--json"))}


@pytest.fixture(scope="module")
def stopped_recheck(tmp_path_factory: pytest.TempPathFactory) -> tuple[Project, dict[str, Any]]:
    proj = hunts.stopped_recheck(tmp_path_factory.mktemp("stopped-recheck"))
    return proj, {"recheck plan, taken up": doc(cli(proj, "recheck", "--dry-run", "--json"))}


def interrupted_json(proj: Project, words: list[str], after_runs: int) -> dict[str, Any]:
    """The command on pipes under `--json`, sent Ctrl-C once its target has started `after_runs` runs."""
    process = subprocess.Popen([sys.executable, "-m", "poisson_break", *words], cwd=proj.folder,
                               env=child_env(proj), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True,
                               preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))  # noqa: PLW1509
    deadline = time.monotonic() + 120
    while len(proj.runs()) < after_runs:
        assert process.poll() is None, process.communicate()
        assert time.monotonic() < deadline, "the runs did not start"
        time.sleep(0.05)
    os.killpg(process.pid, signal.SIGINT)
    out, err = process.communicate(timeout=120)
    assert process.returncode == CODES["interrupted"], (process.returncode, out, err)
    from tests.look_support import Ran

    return json_document(Ran(process.returncode, out.decode(), err.decode()))


# ---------------------------------------------------------------------------
# F10: each schema's name
# ---------------------------------------------------------------------------


def test_each_document_has_its_schema_name(road: Any, confirmed: Any, capped: Any, stopped_confirm: Any,
                                           stopped_recheck: Any) -> None:
    """A result is `poisson_break.<verb>-result/1`, a stop the verb's result schema, a plan its verb's plan schema."""
    every = {**road[1], **confirmed[1], **capped[1], **stopped_confirm[1], **stopped_recheck[1]}
    want = {"catalog": "catalog-result", "doctor": "doctor-result", "doctor --run": "doctor-result",
            "hunt plan": "hunt-plan", "hunt": "hunt-result", "hunt stopped": "hunt-result",
            "hunt --hunt plan": "hunt-plan", "confirm plan": "confirm-plan", "confirm plan, taken up": "confirm-plan",
            "confirm": "confirm-result", "confirm --repeats plan": "confirm-plan", "findings": "findings-result",
            "findings, control not finished": "findings-result", "findings 1": "findings-result",
            "replay 1": "replay-result", "recheck plan": "recheck-plan", "recheck plan, taken up": "recheck-plan",
            "recheck": "recheck-result"}
    assert set(want) == set(every)
    assert {name: document["schema"] for name, document in every.items()} == {
        name: f"poisson_break.{schema}/1" for name, schema in want.items()}


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def test_init(tmp_path: Path) -> None:
    from poisson_break.settings import equivalent_init_command

    proj = project(tmp_path, write=False)
    proj.write(None, cases(3))
    document = doc(cli(proj, "init", "--yes", "--entry", "tests.commands_targets:desk", "--json"))
    assert document["schema"] == "poisson_break.init-result/1" and document["verdict"] == "wrote"
    assert data_keys(document) == {"file", "kind", "entry", "cases_file", "tools", "install"}
    written = settings_of(proj)
    assert document["file"] == "break.toml"
    assert (document["kind"], document["entry"]) == ("rollout", "tests.commands_targets:desk")
    assert document["cases_file"] == written.target.cases == "cases.jsonl"
    assert document["tools"] == [{"name": t.name, "class": t.tool_class} for t in written.tools]
    assert document["tools"] and document["install"] is None
    assert document["next"][-1].startswith(equivalent_init_command(written, prog="poisson-break"))


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


def test_doctor_ready(road: Any) -> None:
    from poisson_break.hunt import load_target
    from poisson_break.settings import read_cases

    proj, docs = road
    settings = settings_of(proj)
    with contextlib.chdir(proj.folder):
        tools = [t.name for t in load_target(settings).tools()]
        count = len(read_cases(Path(settings.target.cases)))
    for name in ("doctor", "doctor --run"):
        document = docs[name]
        assert document["verdict"] == "ready"
        assert data_keys(document) == {"settings", "target", "kind", "tools", "cases", "run"}
        assert document["settings"] == "break.toml"
        assert (document["target"], document["kind"]) == (settings.target.entry, settings.target.kind)
        assert (document["tools"], document["cases"]) == (tools, count)
    assert docs["doctor"]["run"] is None
    run = docs["doctor --run"]["run"]
    assert set(run) == {"case", "outcome", "kind"}
    assert run["case"] == "k1" and run["outcome"] in ("ok", "failed")
    assert run["kind"] is None if run["outcome"] == "ok" else isinstance(run["kind"], str)


def _not_ready(document: dict[str, Any]) -> dict[str, Any]:
    assert document["schema"] == "poisson_break.doctor-result/1" and document["verdict"] == "not ready"
    assert data_keys(document) == {"settings", "key", "line", "unclassed"}
    assert document["settings"] == "break.toml"
    return document


def test_doctor_not_ready_has_one_shape_for_every_problem(tmp_path: Path) -> None:
    """F9: no settings file, a setting out of range, a target that cannot load, a tool nobody classed met by `--run`."""
    none = project(tmp_path / "none", write=False)
    missing = _not_ready(doc(cli(none, "doctor", "--json"), CODES["check"]))
    assert (missing["key"], missing["line"], missing["unclassed"]) == (None, None, [])

    bad = project(tmp_path / "bad", limits={"dollars": 5.0})
    text = bad.settings.read_text(encoding="utf-8")
    bad.settings.write_text(text.replace('"dollars" = 5.0', '"dollars" = -1.0'), encoding="utf-8")
    line = next(n for n, row in enumerate(bad.settings.read_text().splitlines(), 1) if row.startswith('"dollars"'))
    setting = _not_ready(doc(cli(bad, "doctor", "--json"), CODES["check"]))
    assert (setting["key"], setting["line"], setting["unclassed"]) == ("limits.dollars", line, [])

    gone = project(tmp_path / "gone", entry="tests.no_such_module:desk")
    target = _not_ready(doc(cli(gone, "doctor", "--json"), CODES["check"]))
    assert (target["key"], target["line"], target["unclassed"]) == (None, None, [])

    spied = project(tmp_path / "spied")
    env = spying(spied, tmp_path / "spy", RUN_ONCE_REFUSED)
    tool = _not_ready(doc(cli(spied, "doctor", "--run", "--yes", "--json", **env), CODES["check"]))
    assert (tool["key"], tool["line"], tool["unclassed"]) == (None, None, ["spied_tool"])


# ---------------------------------------------------------------------------
# hunt
# ---------------------------------------------------------------------------


def test_hunt_plan(road: Any) -> None:
    from poisson_break.settings import plan_hunt

    proj, docs = road
    document = docs["hunt plan"]
    settings = settings_of(proj)
    planned = plan_hunt(settings, cases=len(MIXED))
    assert data_keys(document) == {"dollars", "target", "kind", "cases", "runs", "control_runs", "search_runs"}
    assert document["dollars"] is None
    assert (document["target"], document["kind"], document["cases"]) == (settings.target.entry, "rollout", 12)
    assert (document["runs"], document["control_runs"], document["search_runs"]) == (
        planned.runs, planned.control_runs, planned.search_runs)


def test_hunt_plan_of_a_hunt_taken_up(capped: Any) -> None:
    """F2 and F3: the dry run names the hunt, and `runs` is what is left: 60 less the one run kept."""
    _, docs = capped
    document = docs["hunt --hunt plan"]
    assert data_keys(document) == {"dollars", "hunt", "target", "kind", "cases", "runs", "control_runs",
                                   "search_runs"}
    assert (document["hunt"], document["runs"], document["cases"]) == ("desk-1", 59, 3)
    assert (document["control_runs"], document["search_runs"]) == (6, 54)
    assert document["dollars"] is None


def test_hunt_plan_of_a_hunt_taken_up_after_its_control_is_priced_at_the_control_s_cost(tmp_path: Path) -> None:
    """R6: priced, a hunt the cap stopped in its search plans the runs it has left at the control's cost of one run,
    as `confirm` plans a stage: `dollars` is that number, the estimate says it and the source names the control's."""
    from poisson_break.look import fmt_dollars

    proj = project(tmp_path, cases(3, weak_to=["error"], tokens=[1000, 0]), limits={"dollars": 0.0085, **hunts.PRICES})
    stopped = doc(cli(proj, "hunt", "--yes", "--json"), CODES["stopped"])
    counts = hunts.stored_counts(proj)
    assert (stopped["reason"], counts["control"]) == ("dollars", 6), (stopped, counts)
    left = 60 - sum(counts.values())
    assert 0 < left < 54, counts
    document = doc(cli(proj, "hunt", "--hunt", "desk-1", "--dry-run", "--json"))
    assert data_keys(document) == {"dollars", "hunt", "target", "kind", "cases", "runs", "control_runs",
                                   "search_runs"}
    assert (document["hunt"], document["runs"]) == ("desk-1", left)
    per_run = control_summary(proj).dollars_per_run
    assert per_run == pytest.approx(0.001)
    assert document["dollars"] == pytest.approx(left * per_run)
    assert fmt_dollars(left * per_run) in document["estimate"], document["estimate"]
    assert fmt_dollars(per_run) in document["source"], document["source"]


def test_hunt_result(road: Any) -> None:
    from poisson_break.confirm import read_candidates
    from poisson_break.changes import name

    proj, docs = road
    document = docs["hunt"]
    assert document["verdict"] == "found"
    assert data_keys(document) == {"hunt", "runs", "dollars", "control", "search", "candidates", "not_looked_at"}
    counts = hunts.stored_counts(proj)
    assert document["hunt"] == "desk-1"
    assert document["runs"] == sum(counts.get(arm, 0) for arm in ("control", "search", "shrink"))
    assert document["dollars"] is None
    control = stored_rows(proj, "control")
    summary = control_summary(proj)
    assert document["control"] == {"runs": len(control), "failed": sum(r["outcome"] == "failed" for r in control),
                                   "rate": summary.rate, "set_aside": list(summary.set_aside)}
    assert document["search"]["runs"] == counts["search"] and set(document["search"]) == {"runs", "conditions"}
    assert isinstance(document["search"]["conditions"], int) and document["search"]["conditions"] > 0
    with contextlib.chdir(proj.folder):
        written = [name(c) for c in read_candidates(opened(proj, "desk-1"))]
    assert [c["condition"] for c in document["candidates"]] == written
    for number, candidate in enumerate(document["candidates"], start=1):
        assert set(candidate) == {"number", "condition", "failed", "runs", "kind"}
        assert candidate["number"] == number and 0 < candidate["failed"] <= candidate["runs"]
        assert candidate["kind"] is None or isinstance(candidate["kind"], str)
    cover = document["not_looked_at"]
    assert set(cover) == {"faults_off", "never_called", "past_limit", "set_aside", "singles_untried",
                          "pairs_untried"}
    assert cover["set_aside"] == list(summary.set_aside)
    assert all(isinstance(cover[k], list) for k in ("faults_off", "never_called", "set_aside"))
    assert isinstance(cover["past_limit"], dict)
    assert all(isinstance(cover[k], int) for k in ("singles_untried", "pairs_untried"))


def test_hunt_stopped(capped: Any) -> None:
    proj, docs = capped
    document = docs["hunt stopped"]
    assert document["verdict"] == "stopped"
    assert data_keys(document) == {"hunt", "reason", "arm", "kept", "unclassed"}
    assert (document["hunt"], document["reason"], document["arm"]) == ("desk-1", "dollars", "desk-1-control")
    assert document["kept"] == len(stored_rows(proj, "control")) == 1
    assert document["unclassed"] == []


def test_hunt_ctrl_c_carries_the_stop_s_keys(tmp_path: Path) -> None:
    """F8: each run naps 0.4 s; Ctrl-C after the second has started. `kept` is what the store holds."""
    proj = project(tmp_path, cases(3, weak_to=["error"], nap=0.4))
    document = interrupted_json(proj, ["hunt", "--yes", "--json"], after_runs=2)
    assert document["schema"] == "poisson_break.hunt-result/1" and document["verdict"] == "stopped"
    assert data_keys(document) == {"hunt", "reason", "arm", "kept", "unclassed"}
    assert (document["hunt"], document["reason"], document["unclassed"]) == ("desk-1", "interrupted", [])
    assert document["kept"] == sum(hunts.stored_counts(proj).values())
    assert document["arm"] is None or document["arm"] == "desk-1-control"


def test_confirm_ctrl_c_carries_the_stop_s_keys(tmp_path: Path) -> None:
    """F8 for `confirm`, and R5: Ctrl-C while the second run of the stage's control arm runs. `kept` is the rows the
    stage's own arms hold, not the hunt's control's; `arm` is the confirm control arm; the sentence names the number."""
    proj = project(tmp_path, cases(3, weak_to=["error"], nap=0.4), search={"control_repeats": 1})
    prepared(proj, (on("error"),))  # the candidate written through the library, as `hunt` leaves it
    made = len(proj.runs())
    document = interrupted_json(proj, ["confirm", "--yes", "--json"], after_runs=made + 2)
    assert document["schema"] == "poisson_break.confirm-result/1" and document["verdict"] == "stopped"
    assert data_keys(document) == {"hunt", "reason", "arm", "kept", "unclassed"}
    assert (document["hunt"], document["reason"], document["unclassed"]) == ("desk-1", "interrupted", [])
    counts = hunts.stored_counts(proj)
    stage = {arm: rows for arm, rows in counts.items() if arm.startswith("confirm-")}
    assert set(stage) == {"confirm-control"} and 1 <= stage["confirm-control"] < 3 * 3, counts
    assert counts["control"] == 3, counts
    assert document["kept"] == stage["confirm-control"]
    assert document["arm"] == "desk-1-confirm-control"
    assert holds_number(document["sentence"], str(document["kept"])), document["sentence"]


@pytest.mark.parametrize("old", [False, True], ids=["now", "old-beside"])
def test_recheck_ctrl_c_carries_the_stop_s_keys(tmp_path: Path, old: bool) -> None:
    """F8 for `recheck`, and R5: finding 1 confirmed through the library, then each run naps 0.4 s and the recheck is
    sent Ctrl-C during its second run of the agent as it is now. Beside the old agent that is after the old side's
    twelve, so `kept` is both sides' rows; `arm` is the arm as it is now; the sentence names the number."""
    from poisson_break.confirm import confirm

    proj = project(tmp_path, cases(3, weak_to=["error"]), confirm={"repeats": 4}, search={"control_repeats": 1})
    prepared(proj, (on("error"),))
    with contextlib.chdir(proj.folder):
        assert [f.number for f in confirm(opened(proj, "desk-1")).findings] == [1]
    proj.write(case_list=cases(3, weak_to=["error"], nap=0.4))  # the same ids: the hunt opens as it was
    before = hunts.stored_counts(proj)
    made = len(proj.runs())
    words = ["recheck", "--yes", "--json"] + (["--old", "tests.commands_targets:old_desk"] if old else [])
    document = interrupted_json(proj, words, after_runs=made + (12 if old else 0) + 2)
    assert document["schema"] == "poisson_break.recheck-result/1" and document["verdict"] == "stopped"
    assert data_keys(document) == {"hunt", "reason", "arm", "kept", "unclassed"}
    assert (document["hunt"], document["reason"], document["unclassed"]) == ("desk-1", "interrupted", [])
    counts = hunts.stored_counts(proj)
    assert {arm: rows for arm, rows in counts.items() if arm in before} == before, "nothing before the recheck moved"
    stage = {arm: rows for arm, rows in counts.items() if arm.startswith("recheck-")}
    assert set(stage) == ({"recheck-1-1-old", "recheck-1-1"} if old else {"recheck-1-1"}), counts
    assert stage.get("recheck-1-1-old", 12) == 12 and 1 <= stage["recheck-1-1"] < 12, counts
    assert document["kept"] == sum(stage.values())
    assert document["arm"] == "desk-1-recheck-1-1"
    assert holds_number(document["sentence"], str(document["kept"])), document["sentence"]


# ---------------------------------------------------------------------------
# confirm
# ---------------------------------------------------------------------------


def test_confirm_plan(confirmed: Any) -> None:
    from poisson_break.confirm import design, read_candidates

    proj, docs = confirmed
    document = docs["confirm plan"]
    assert data_keys(document) == {"dollars", "hunt", "candidates", "stage", "repeats", "runs"}
    with contextlib.chdir(proj.folder):
        h = opened(proj, "desk-1")
        planned = design(read_candidates(h), h.settings, control_summary(proj))
    assert (document["hunt"], document["candidates"], document["stage"]) == ("desk-1", 3, 1)
    assert (document["repeats"], document["runs"], document["dollars"]) == (planned.repeats, planned.runs, None)


def test_confirm_plan_of_a_stage_taken_up(stopped_confirm: Any) -> None:
    """F2: `runs` is what the stage has left; F14: priced, `dollars` is those runs at the control's cost of one."""
    proj, docs = stopped_confirm
    document = docs["confirm plan, taken up"]
    assert data_keys(document) == {"dollars", "hunt", "candidates", "stage", "repeats", "runs"}
    counts = hunts.stored_counts(proj)
    arms = ["confirm-control", "confirm-1", "confirm-2", "confirm-3"]
    left = sum(11 * 4 - counts.get(arm, 0) for arm in arms)
    assert (document["hunt"], document["candidates"], document["stage"], document["repeats"]) == ("desk-1", 3, 1, 4)
    assert document["runs"] == left
    assert document["dollars"] == pytest.approx(left * control_summary(proj).dollars_per_run)


def test_confirm_plan_asking_again(confirmed: Any) -> None:
    """F4: `candidates` is the one asked about again."""
    from poisson_break.settings import plan_confirm

    proj, docs = confirmed
    document = docs["confirm --repeats plan"]
    assert data_keys(document) == {"dollars", "hunt", "candidates", "stage", "repeats", "runs", "asked_again"}
    settings = settings_of(proj)
    again = plan_confirm(dataclasses.replace(settings, confirm=dataclasses.replace(settings.confirm, repeats=6)),
                         cases=11, candidates=1)
    assert (document["candidates"], document["stage"], document["repeats"]) == (1, 2, 6)
    assert document["asked_again"] == ["tool:lookup_order#1=timeout"]
    assert (document["runs"], document["dollars"]) == (again.runs, None)


def test_confirm_result(confirmed: Any) -> None:
    from poisson_break.confirm import confirm

    proj, docs = confirmed
    document = docs["confirm"]
    assert document["verdict"] == "confirmed"
    assert data_keys(document) == {"hunt", "stage", "candidates", "findings", "wrote", "reference_runs"}
    with contextlib.chdir(proj.folder):
        done = confirm(opened(proj, "desk-1"))  # the finished stage asked again: runs nothing
    keys = ["number", "condition", "verdict", "note", "rate", "control_rate", "difference", "lo", "hi", "p",
            "adjusted_p", "repeats_needed"]
    assert document["candidates"] == [
        {**{key: getattr(t, key) for key in keys}, "no_outcome": list(t.no_outcome), "left_out": dict(t.left_out)}
        for t in done.tested]
    assert (document["hunt"], document["stage"], document["findings"]) == ("desk-1", 1, [1])
    assert document["wrote"] == ["break-runs/desk-1/findings/1.toml"]
    assert (proj.folder / document["wrote"][0]).is_file()
    assert document["reference_runs"] == len(stored_rows(proj, "reference-1")) == 44


# ---------------------------------------------------------------------------
# findings
# ---------------------------------------------------------------------------


def test_findings_listing(confirmed: Any) -> None:
    from tests.commands_support import findings_of

    proj, docs = confirmed
    document = docs["findings"]
    assert data_keys(document) == {"hunt", "findings", "control"}
    assert document["findings"] == [{"number": f.number, "condition": f.condition, "rate": f.rate,
                                     "difference": f.difference} for f in findings_of(proj, "desk-1")]
    summary = control_summary(proj)
    by_case: dict[str, list[Any]] = {}
    for row in summary.rows:
        by_case.setdefault(row.case, []).append(row)
    want = []
    for case, rows in by_case.items():
        failed = [r for r in rows if r.outcome == "failed"]
        if failed:
            want.append({"case": case, "failed": len(failed), "runs": len(rows),
                         "kinds": list(dict.fromkeys(r.kind for r in failed if r.kind)),
                         "set_aside": case in summary.set_aside})
    assert document["control"] == want and want


def test_findings_listing_while_the_control_is_not_finished(capped: Any) -> None:
    """F7: null, not an empty list, which would say no control case failed."""
    _, docs = capped
    document = docs["findings, control not finished"]
    assert data_keys(document) == {"hunt", "findings", "control"}
    assert (document["hunt"], document["findings"], document["control"]) == ("desk-1", [], None)


def test_findings_one(confirmed: Any) -> None:
    from tests.commands_support import findings_of

    proj, docs = confirmed
    document = docs["findings 1"]
    assert data_keys(document) == {"hunt", "finding"}
    (finding,) = findings_of(proj, "desk-1")

    def plain(value: Any) -> Any:
        if isinstance(value, dict) or hasattr(value, "items"):
            return {str(k): plain(v) for k, v in value.items()}
        if isinstance(value, (tuple, list)):
            return [plain(v) for v in value]
        return value

    assert document["hunt"] == "desk-1"
    assert document["finding"] == {f.name: plain(getattr(finding, f.name)) for f in dataclasses.fields(finding)}


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------


def test_replay(confirmed: Any) -> None:
    from poisson_break.confirm import replay

    proj, docs = confirmed
    document = docs["replay 1"]
    assert data_keys(document) == {"hunt", "finding", "case", "seed", "outcome", "kind", "error", "calls"}
    with contextlib.chdir(proj.folder):
        done = replay(opened(proj, "desk-1"), 1)
    assert (document["hunt"], document["finding"]) == ("desk-1", 1)
    assert (document["case"], document["seed"], document["outcome"], document["kind"], document["error"]) == (
        done.case, done.seed, done.outcome, done.kind, done.error)
    assert document["calls"] == [{"tool": c.tool, "call": c.call, "change": c.change, "real_ran": c.real_ran}
                                 for c in done.calls]


# ---------------------------------------------------------------------------
# recheck
# ---------------------------------------------------------------------------


def test_recheck_plan(confirmed: Any) -> None:
    _, docs = confirmed
    document = docs["recheck plan"]
    assert data_keys(document) == {"dollars", "hunt", "findings", "runs", "old"}
    assert (document["hunt"], document["findings"], document["runs"]) == ("desk-1", [1], 44)
    assert (document["old"], document["dollars"]) == (None, None)


def test_recheck_plan_of_a_recheck_taken_up(stopped_recheck: Any) -> None:
    """F2: `runs` is what recheck 1 has left; F14: priced, `dollars` is those runs at the control's cost of one."""
    proj, docs = stopped_recheck
    document = docs["recheck plan, taken up"]
    assert data_keys(document) == {"dollars", "hunt", "findings", "runs", "old", "recheck"}
    left = 44 - hunts.stored_counts(proj).get("recheck-1-1", 0)
    assert 0 < left < 44
    assert (document["hunt"], document["findings"], document["recheck"], document["runs"]) == ("desk-1", [1], 1, left)
    assert document["old"] is None
    assert document["dollars"] == pytest.approx(left * control_summary(proj).dollars_per_run)


def test_recheck_result(confirmed: Any) -> None:
    proj, docs = confirmed
    document = docs["recheck"]
    assert document["verdict"] == "rechecked"
    assert data_keys(document) == {"hunt", "findings", "old", "check", "strict", "passed"}
    assert (document["hunt"], document["old"], document["check"], document["strict"], document["passed"]) == (
        "desk-1", None, False, False, True)
    (one,) = document["findings"]
    assert set(one) == {"number", "condition", "phrase", "rate_before", "rate_now", "difference", "lo", "hi", "p",
                        "adjusted_p", "repeats_needed", "gap_days", "before", "now", "trace", "no_outcome",
                        "left_out"}
    assert (one["number"], one["condition"]) == (1, "tool:lookup_order#1=error")
    assert one["phrase"] in ("fails less", "fails more", "no significant difference", "too small to tell")
    assert (one["before"], one["now"]) == ("desk-1-reference-1", "desk-1-recheck-1-1")
    assert one["trace"] == document["next"][0]
    assert one["no_outcome"] == []
    assert set(one["left_out"]) == {"not re-run on the old version", "not re-run on the new version",
                                    "no outcome on the old version", "no outcome on the new version"}
    # F6 taken back (R7): the reference ran minutes before the recheck, and the days are rounded as the screen prints
    # them, one decimal under ten days: 0.0
    assert isinstance(one["gap_days"], float) and one["gap_days"] == 0.0


# ---------------------------------------------------------------------------
# catalog
# ---------------------------------------------------------------------------


def test_catalog(road: Any) -> None:
    from poisson_break.changes import CATALOG

    _, docs = road
    document = docs["catalog"]
    assert data_keys(document) == {"changes"}
    assert document["changes"] == [{"surface": e.surface, "name": e.name, "description": e.description,
                                    "needs_adapter": e.needs_adapter} for e in CATALOG]
