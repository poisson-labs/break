"""The twins: one scripted agent reached by `wrap` lines and the same agent reached at load behave, record and stand in
alike (spec §12.8).

Invariants held here (Break — Plan, the module that wraps tools at load; spec §12.8):
- BK15.2  The same behaviour: for the control and for each of the ten faults, the twins, run on the same case, condition
          and seed, show the agent the same value or raise the same exception, by type, `kind` and message.
- BK15.3  The same record: for those runs the twins' `RunRecord`s are equal field for field, `calls` and each `applied`
          among them, and `Session.seen` is equal call for call, each argument under the same name.
- BK15.16 A stand-in is called in the tool's place, the function at `at` never runs, and the call reads `real_ran:
          true`, as for the wrapped twin.
- BK15.8, the source's half: the second twin's file holds no `poisson_break` anywhere. What the commands do with it end
          to end is `tests/test_commands_load.py`'s.

And the twins and the holders module themselves, held to what `tests/load_support.py` says they are, since every test
of the module stands on them (plan §2, item 2).

Each twin runs in a child of its own: both are `twin_desk`, and the wrapped twin's `wrap` lines would make the bare
twin's `at` lines a refusal in one process (spec §12.7, way 5). The two children run the same script and print the same
document, which the tests compare.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.commands_support import settings_text
from tests.load_support import BARE_TWIN, HOLDERS, TWIN_TOOLS, WRAPPED_TWIN, child

SEED = 20261120
MARKER = "TWINMARK"
FAULTS = ("error", "timeout", "slow", "rate_limited", "empty", "cut_off", "malformed", "stale", "lost_reply",
          "planted_instruction")

#: Each run both twins make: the agent, then the condition. The control for each agent, each of the ten faults where
#: the agent meets it, a fault on every call, and two faults on two tools.
RUNS: list[tuple[str, str]] = [
    ("gives_up", ""), ("retries", ""), ("follows_plant", ""), ("repeats_write", ""),
    ("gives_up", "tool:lookup_order#1=error"),
    ("gives_up", "tool:lookup_order#1=timeout"),
    ("gives_up", "tool:lookup_order#1=slow"),
    ("gives_up", "tool:lookup_order#1=rate_limited"),
    ("gives_up", "tool:lookup_order#1=empty"),
    ("gives_up", "tool:lookup_order#1=cut_off"),
    ("gives_up", "tool:lookup_order#1=malformed"),
    ("gives_up", "tool:lookup_order#2=stale"),
    ("repeats_write", "tool:issue_refund#1=lost_reply"),
    ("follows_plant", "tool:lookup_order#1=planted_instruction"),
    ("retries", "tool:lookup_order#*=error"),
    ("gives_up", "tool:check_policy#1=empty + tool:lookup_order#2=cut_off"),
]
#: Runs with `issue_refund` replaced by its stand-in.
STAND_IN_RUNS: list[tuple[str, str]] = [
    ("repeats_write", ""), ("repeats_write", "tool:issue_refund#1=lost_reply"),
    ("repeats_write", "tool:issue_refund#1=error"),
]


def lines(*, at: bool, stand_in: bool = False) -> dict[str, Any]:
    """The twins' `[tools]`: the bare twin's carry `at`, the wrapped twin's do not."""
    held: dict[str, Any] = {"lookup_order": {"class": "read"}, "check_policy": {"class": "read"},
                            "issue_refund": {"class": "write", "repeatable": True}}
    if stand_in:
        held["issue_refund"] = {"class": "write", "stand_in": "twin_desk:refund_stand_in"}
    if at:
        for tool in TWIN_TOOLS:
            held[tool] = {**held[tool], "at": f"twin_desk:{tool}"}
    return held


TWIN_SCRIPT = '''
import time
SLEPT = []
time.sleep = lambda seconds: SLEPT.append(seconds)

from poisson_prove.store import Store
from poisson_break.apply import Session
from poisson_break.changes import parse
from poisson_break.hunt import open_hunt, run_arm
from poisson_break.records import META_KEY, RunRecord
from poisson_break.settings import loads

ARGS = json.loads(ARGS_TEXT)
settings = loads(ARGS["settings"])
stand_in_settings = loads(ARGS["stand_in_settings"])
target = load(ARGS["settings"])
twin = sys.modules["twin_desk"]

def session_lines(chosen):
    lines = {}
    for tool in chosen.tools:
        line = {"class": tool.tool_class}
        if tool.repeatable:
            line["repeatable"] = True
        if tool.stand_in:
            line["stand_in"] = tool.stand_in
        lines[tool.name] = line
    return lines

def one(agent, condition, chosen):
    case = {"id": agent, "input": "Where is order 7? Please refund it.", "agent": agent}
    s = Session(parse(condition), seed=ARGS["seed"], tools=session_lines(chosen), marker=ARGS["marker"])
    twin.EXECUTED.clear()
    SLEPT.clear()
    with s:
        episode = twin.desk(dict(case), ARGS["seed"])
    meta = episode.meta
    return {
        "outcome": episode.outcome, "reply": meta["reply"], "saw": repr(meta["run"]),
        "raised": [[type(e).__module__ + "." + type(e).__qualname__, getattr(e, "kind", None), str(e)]
                   for e in meta["raised"]],
        "calls": [c.to_dict() for c in s.calls], "applied": [a.to_dict() for a in s.applied],
        "seen": [[x.tool, x.call, {k: repr(v) for k, v in x.args.items()}, repr(x.saw),
                  None if x.error is None else [x.error.kind, x.error.message]] for x in s.seen],
        "stopped": repr(s.stopped), "slept": list(SLEPT), "executed": [list(e) for e in twin.EXECUTED],
    }

said = {"reached": [reached(r) for r in target.reached],
        "runs": [one(agent, condition, settings) for agent, condition in ARGS["runs"]],
        "stand_in_runs": [one(agent, condition, stand_in_settings) for agent, condition in ARGS["stand_in_runs"]]}

def records(chosen, folder, runs):
    cases = [{"id": agent, "input": "Where is order 7? Please refund it.", "agent": agent}
             for agent in ("gives_up", "retries", "follows_plant", "repeats_write")]
    h = open_hunt(chosen, target=target, cases=cases, name="twins")
    run_arm(h, "control", [c["id"] for c in cases], "", repeats=1)
    for n, (agent, condition) in enumerate(runs, 1):
        run_arm(h, f"confirm-{n}", [agent], condition, repeats=1)
    store = Store(h.store)
    kept = {}
    for run in sorted(store.runs()):
        frame = store.read(run)
        kept[run] = [RunRecord.from_dict(row["meta"][META_KEY]).to_dict() for row in frame.to_dict("records")]
    return kept

said["records"] = records(settings, ARGS["folder"], ARGS["runs"])
out(said)
'''


def run_twin(folder: Path, tmp: Path, *, at: bool) -> dict[str, Any]:
    import json

    store = tmp / "hunts"
    args = {
        "settings": settings_text(entry="twin_desk:desk", tools=lines(at=at), folder=str(store),
                                  vary={"tools": list(FAULTS), "max_call": 3}),
        "stand_in_settings": settings_text(entry="twin_desk:desk", tools=lines(at=at, stand_in=True),
                                           folder=str(store), vary={"tools": list(FAULTS), "max_call": 3}),
        "seed": SEED, "marker": MARKER, "runs": RUNS, "stand_in_runs": STAND_IN_RUNS, "folder": str(store),
    }
    return child(f"ARGS_TEXT = {json.dumps(args)!r}\n" + TWIN_SCRIPT, paths=[folder])


@pytest.fixture(scope="module")
def twins(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
    return {"wrapped": run_twin(WRAPPED_TWIN, tmp_path_factory.mktemp("wrapped"), at=False),
            "bare": run_twin(BARE_TWIN, tmp_path_factory.mktemp("bare"), at=True)}


def labelled(runs: list[tuple[str, str]]) -> list[str]:
    return [f"{agent}, {condition or 'control'}" for agent, condition in runs]


# ---------------------------------------------------------------------------
# the twins are what they are said to be
# ---------------------------------------------------------------------------


def test_the_bare_twin_s_file_holds_no_poisson_break_anywhere() -> None:
    """BK15.8: no Break line, and no word of Break's, in the second twin's source."""
    source = (BARE_TWIN / "twin_desk.py").read_text(encoding="utf-8")
    assert "poisson_break" not in source


def test_the_wrapped_twin_wraps_each_tool_at_import_and_the_bare_twin_wraps_none() -> None:
    said = child('''
        from poisson_break.apply import wrapped_while
        out(list(wrapped_while("twin_desk")))
    ''', paths=[WRAPPED_TWIN])
    assert sorted(said) == sorted(TWIN_TOOLS)
    assert child('''
        from poisson_break.apply import wrapped_while
        out(list(wrapped_while("twin_desk")))
    ''', paths=[BARE_TWIN]) == []


def test_the_twins_reached_one_way_each(twins: dict[str, dict[str, Any]]) -> None:
    """The wrapped twin's tools are reached by its `wrap` lines and the bare twin's at load, each at its own place."""
    wrapped = {r["tool"]: (r["how"], r["at"]) for r in twins["wrapped"]["reached"]}
    bare = {r["tool"]: (r["how"], r["at"], r["places"]) for r in twins["bare"]["reached"]}
    assert wrapped == {tool: ("wrap", None) for tool in TWIN_TOOLS}
    assert bare == {tool: ("at load", f"twin_desk:{tool}", [f"twin_desk:{tool}"]) for tool in TWIN_TOOLS}


def test_every_run_reached_the_session_and_each_fault_was_applied(twins: dict[str, dict[str, Any]]) -> None:
    """So that the comparisons below are not of two runs Break never saw: every run's calls are recorded, and each
    fault is applied on both twins."""
    for side in ("wrapped", "bare"):
        for (agent, condition), run in zip(RUNS, twins[side]["runs"], strict=True):
            assert run["calls"], (side, agent, condition)
            if condition:
                assert any(a["applied"] for a in run["applied"]), (side, agent, condition, run["applied"])


# ---------------------------------------------------------------------------
# BK15.2: the same behaviour
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", range(len(RUNS)), ids=labelled(RUNS))
def test_the_agent_sees_the_same_value_or_the_same_exception(twins: dict[str, dict[str, Any]], n: int) -> None:
    """What the agent was handed back, call for call, its reply and outcome, and every exception a call raised by its
    type, `kind` and message; and the delays a fault asked for."""
    wrapped, bare = twins["wrapped"]["runs"][n], twins["bare"]["runs"][n]
    for key in ("saw", "raised", "reply", "outcome", "slept", "stopped"):
        assert bare[key] == wrapped[key], key


def test_the_ten_faults_are_all_among_the_runs() -> None:
    named = {part.split("=")[1] for _, condition in RUNS for part in condition.split(" + ") if condition}
    assert set(FAULTS) <= named


# ---------------------------------------------------------------------------
# BK15.3: the same record
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", range(len(RUNS)), ids=labelled(RUNS))
def test_the_session_holds_the_same_calls_applied_and_seen(twins: dict[str, dict[str, Any]], n: int) -> None:
    wrapped, bare = twins["wrapped"]["runs"][n], twins["bare"]["runs"][n]
    for key in ("calls", "applied", "seen", "executed"):
        assert bare[key] == wrapped[key], key


def test_the_stored_records_are_equal_field_for_field(twins: dict[str, dict[str, Any]]) -> None:
    """Each arm of one hunt name, made on each twin under the same seed: the `RunRecord` of every run, field for field."""
    wrapped, bare = twins["wrapped"]["records"], twins["bare"]["records"]
    assert sorted(wrapped) == sorted(bare) and len(wrapped) == len(RUNS) + 1
    for run in wrapped:
        assert bare[run] == wrapped[run], run
        assert all(record["calls"] for record in wrapped[run]), run


# ---------------------------------------------------------------------------
# BK15.16: a stand-in is called in the tool's place
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", range(len(STAND_IN_RUNS)), ids=labelled(STAND_IN_RUNS))
def test_a_stand_in_is_called_in_the_tool_s_place_as_for_the_wrapped_twin(twins: dict[str, dict[str, Any]],
                                                                          n: int) -> None:
    wrapped, bare = twins["wrapped"]["stand_in_runs"][n], twins["bare"]["stand_in_runs"][n]
    assert bare == wrapped
    refunds = [c for c in bare["calls"] if c["tool"] == "issue_refund"]
    assert refunds and all(c["real_ran"] is True for c in refunds if c["change"] is None)
    ran = [e[0] for e in bare["executed"]]
    assert "issue_refund" not in ran and "refund_stand_in" in ran


# ---------------------------------------------------------------------------
# the holders module is what it is said to be
# ---------------------------------------------------------------------------


def test_the_holders_module_holds_its_tool_every_way_it_is_said_to() -> None:
    """Before any load: the five places hold the one function, and the closure, the partial, the tuple and the object
    hold it too; the other tools are in the dict and the list; no file of the package holds `poisson_break`."""
    said = child(f'''
        import {HOLDERS}.agent
        tools = sys.modules["{HOLDERS}.tools"]
        agent = sys.modules["{HOLDERS}.agent"]
        package = sys.modules["{HOLDERS}"]
        fn = tools.lookup_order
        names = ("lookup_order", "check_policy", "issue_refund", "send_email", "cancel_order")
        out({{
            "places": [agent.lookup_order is fn, package.lookup_order is fn, agent.TOOLS["lookup_order"] is fn,
                       agent.TOOL_LIST[0] is fn],
            "dict": list(agent.TOOLS) == list(names) and all(agent.TOOLS[n] is getattr(tools, n) for n in names),
            "list": [id(x) for x in agent.TOOL_LIST] == [id(getattr(tools, n)) for n in names],
            "closure": any(cell.cell_contents is fn for cell in agent.AGENT.__closure__ or ()),
            "closure owner": agent.AGENT.__qualname__,
            "partial": agent.FIND.func is fn, "tuple": isinstance(agent.HELP, tuple) and agent.HELP[0] is fn,
            "object": agent.BOX.lookup is fn and not isinstance(agent.BOX, type),
            "package holds": sorted(n for n in names if hasattr(package, n)),
            "doc": fn.__doc__, "parameters": list(inspect.signature(fn).parameters),
        }})
    ''')
    assert said["places"] == [True] * 4
    assert said["dict"] and said["list"] and said["closure"] and said["partial"] and said["tuple"] and said["object"]
    assert said["closure owner"].startswith("make_agent.")
    assert said["package holds"] == ["lookup_order"]
    assert said["doc"] == "Look an order up." and said["parameters"] == ["query", "detail"]
    root = Path(__file__).parent / "agents" / "holders"
    assert sorted(p.name for p in root.glob("*.py")) == ["__init__.py", "agent.py", "tools.py"]
    assert not [p.name for p in root.glob("*.py") if "poisson_break" in p.read_text(encoding="utf-8")]
