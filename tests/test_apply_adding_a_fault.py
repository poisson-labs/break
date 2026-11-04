"""A fault added from outside the core, all the way through a live call.

Invariant pinned here (Break — Plan, the applying module):
- BK2.11 A fault added from outside applies through `Session.call` and is recorded like a launch fault
         (moved here from BK1.8, which could not reach `Session.call`).

And spec §11: a test-only implementation written outside the package runs end to end through the core
with no core file changed. The first test does that in its own interpreter, from a file on disk, as a
fault's author would. The rest run on a catalogue of their own, since there is no public way to take a
fault back out.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import time
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.apply_support import REPEATABLE, Tool, call, fresh, seen_call
from tests.conftest import guarded_env

AUTHOR = textwrap.dedent('''\
    """A fault its author wrote: this file is outside the package, and is all there is."""
    from poisson_break.changes import Result, register


    class Flip:
        name = "flip"
        surface = "tool"
        description = "the real result, written backwards"
        parameters = {"times": 2}
        real_runs = True

        def apply(self, call, *, real, params, rng):
            return Result(value=str(real())[::-1] * params["times"])


    register(Flip())
''')

DRIVER = textwrap.dedent('''\
    import json
    from poisson_break.apply import Session
    from poisson_break.changes import parse
    import flip_fault

    ran = []
    def real():
        ran.append(True)
        return "abc"

    s = Session(parse("tool:a#2=flip"), seed=1, tools={"a": "read"})
    seen = [s.call("a", {"q": 1}, real), s.call("a", {"q": 2}, real), s.call("a", {"q": 3}, real)]
    print(json.dumps({"seen": seen, "ran": len(ran), "calls": [c.to_dict() for c in s.calls],
                      "applied": [a.to_dict() for a in s.applied]}))
''')


def test_a_fault_in_a_file_outside_the_package_applies_through_a_call_and_is_recorded(tmp_path: Path) -> None:
    (tmp_path / "flip_fault.py").write_text(AUTHOR)
    env = guarded_env()
    env["PYTHONPATH"] = f"{tmp_path}:{env['PYTHONPATH']}"
    done = subprocess.run([sys.executable, "-c", DRIVER], capture_output=True, text=True, timeout=120,
                          env=env, stdin=subprocess.DEVNULL, cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    assert out["seen"] == ["abc", "cbacba", "abc"], "only its call, with its own declared default"
    assert out["ran"] == 3
    assert out["calls"] == [
        {"tool": "a", "call": 1, "change": None, "real_ran": True},
        {"tool": "a", "call": 2, "change": "tool:a#2=flip", "real_ran": True},
        {"tool": "a", "call": 3, "change": None, "real_ran": True},
    ]
    assert out["applied"] == [
        {"surface": "tool", "tool": "a", "fault": "flip", "call": "#2", "applied": True, "applied_call": 2}]


@pytest.fixture
def c() -> Iterator[tuple[ModuleType, ModuleType]]:
    yield from fresh()


def own(c_module: ModuleType, apply_fn: Any, *, name: str = "own", real_runs: bool = True,
        parameters: dict[str, object] | None = None) -> None:
    c_module.register(type("Own", (), {"name": name, "surface": "tool", "description": "a fault of its author's",
                                       "parameters": parameters or {}, "real_runs": real_runs, "apply": apply_fn})())


def watching() -> Iterator[tuple[ModuleType, ModuleType, list[Any]]]:
    """A catalogue with one more fault on it, which writes down the context it was given and passes the
    result through."""
    for c_module, a in fresh():
        yield _with_a_watcher(c_module, a)


def _with_a_watcher(c_module: ModuleType, a: ModuleType) -> tuple[ModuleType, ModuleType, list[Any]]:
    watched: list[Any] = []

    def apply_fn(self: Any, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
        watched.append(call)
        return c_module.Result(value=real())

    own(c_module, apply_fn, name="watch")
    return c_module, a, watched


def session_on(pair: tuple[ModuleType, ModuleType], text: str, **over: Any) -> Any:
    c_module, a = pair
    over.setdefault("seed", 1)
    over.setdefault("tools", REPEATABLE)
    return a.Session(c_module.parse(text), **over)


# ---------------------------------------------------------------------------
# recorded exactly like a launch fault
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("real_runs, launch", [(True, "empty"), (False, "error")], ids=["tool-runs", "tool-does-not"])
@pytest.mark.parametrize("position, lands", [("#2", [2]), ("#2-3", [2, 3]), ("#*", [1, 2, 3, 4]), ("~1", [1, 2, 3, 4])])
def test_its_record_is_a_launch_faults_but_for_its_name(c: Any, real_runs: bool, launch: str, position: str,
                                                        lands: list[int]) -> None:
    """The same run under the outside fault and under a launch fault with the same third column: every
    record field comes out the same, its own name aside."""
    def apply_fn(self: Any, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
        if real_runs:
            return c[0].Result(value=real())
        return c[0].ToolError(kind="error", message="no")
    own(c[0], apply_fn, real_runs=real_runs)

    def run(fault: str) -> tuple[list[Any], list[Any], int]:
        s = session_on(c, f"tool:a{position}={fault}")
        tool = Tool("answer")
        for _ in range(4):
            seen_call(s, "a", tool)
        calls = [c_.to_dict() for c_ in s.calls]
        applied = [a_.to_dict() for a_ in s.applied]
        return calls, applied, tool.runs

    theirs, launchs = run("own"), run(launch)
    assert json.loads(json.dumps(theirs).replace("=own", f"={launch}").replace('"own"', f'"{launch}"')) == json.loads(json.dumps(launchs))
    assert [x["call"] for x in theirs[0] if x["change"]] == lands
    assert theirs[1][0]["applied"] is True
    assert theirs[1][0]["applied_call"] == lands[0]


def test_it_lands_beside_a_launch_fault_each_on_its_own_call(c: Any) -> None:
    def apply_fn(self: Any, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
        return c[0].Result(value=str(real()).upper())
    own(c[0], apply_fn)
    s = session_on(c, "tool:a#1=error + tool:a#2=own + tool:b#1=empty")
    tool = Tool("answer")
    assert seen_call(s, "a", tool)[0] == "failure"
    assert seen_call(s, "a", tool) == ("result", "ANSWER")
    assert seen_call(s, "b", tool) == ("result", "")
    assert [x.change for x in s.calls] == ["tool:a#1=error", "tool:a#2=own", "tool:b#1=empty"]


# ---------------------------------------------------------------------------
# what reaches the agent
# ---------------------------------------------------------------------------


def test_its_result_reaches_the_agent(c: Any) -> None:
    def apply_fn(self: Any, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
        return c[0].Result(value={"from": real()})
    own(c[0], apply_fn)
    assert call(session_on(c, "tool:a#1=own"), "a", Tool("answer")) == {"from": "answer"}


def test_its_error_reaches_the_agent_with_its_own_kind_and_words(c: Any) -> None:
    """§11.1: `ToolError(kind, message)`, the launch three being what a way in must know, so a fourth
    word is taken and reaches the agent as said."""
    def apply_fn(self: Any, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
        return c[0].ToolError(kind="quota_exceeded", message="the monthly quota is used up")
    own(c[0], apply_fn, real_runs=False)
    tool = Tool()
    with pytest.raises(c[1].ToolFailure) as failure:
        call(session_on(c, "tool:a#1=own"), "a", tool)
    assert failure.value.kind == "quota_exceeded"
    assert failure.value.message == "the monthly quota is used up"
    assert str(failure.value) == "the monthly quota is used up"
    assert not isinstance(failure.value, TimeoutError)
    assert tool.runs == 0


def test_its_timeout_kind_is_a_timeout_too(c: Any) -> None:
    def apply_fn(self: Any, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
        return c[0].ToolError(kind="timeout", message="too long")
    own(c[0], apply_fn, real_runs=False)
    with pytest.raises(TimeoutError):
        call(session_on(c, "tool:a#1=own"), "a", Tool())


def test_its_delay_is_slept_like_a_launch_faults(c: Any) -> None:
    def apply_fn(self: Any, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
        return c[0].Result(value=real(), delay=0.5)
    own(c[0], apply_fn)
    started = time.monotonic()
    assert call(session_on(c, "tool:a#1=own"), "a", Tool("answer")) == "answer"
    assert time.monotonic() - started >= 0.49


# ---------------------------------------------------------------------------
# what it is given
# ---------------------------------------------------------------------------


def test_it_is_given_its_own_declared_parameters(c: Any) -> None:
    """§3.2: one default each, and nothing a run may vary."""
    got: list[Any] = []

    def apply_fn(self: Any, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
        got.append(dict(params))
        return c[0].Result(value=real())
    own(c[0], apply_fn, parameters={"times": 3, "word": "x"})
    call(session_on(c, "tool:a#1=own"), "a", Tool())
    assert got == [{"times": 3, "word": "x"}]


def test_its_generator_is_keyed_so_it_replays_and_the_seed_matters(c: Any) -> None:
    """§11.1 invariant 2: `rng` is seeded by the core so the same inputs give the same outcome."""
    def apply_fn(self: Any, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
        real()
        return c[0].Result(value=rng.random())
    own(c[0], apply_fn)

    def drawn(seed: int) -> float:
        return call(session_on(c, "tool:a#1=own", seed=seed), "a", Tool())

    assert drawn(5) == drawn(5)
    assert len({drawn(seed) for seed in range(20)}) > 1


def test_its_mistakes_are_instrument_errors_through_the_applier(c: Any) -> None:
    def apply_fn(self: Any, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
        return "not an outcome"
    own(c[0], apply_fn, real_runs=False)
    s = session_on(c, "tool:a#1=own")
    with pytest.raises(c[1].InstrumentError):
        call(s, "a", Tool())
    assert s.stopped is not None
