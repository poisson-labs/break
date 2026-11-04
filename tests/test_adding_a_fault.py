"""Adding a fault: spec §11.1, the extension point. A fault written outside the core is registered,
and from then on nothing tells it from a launch fault.

Invariant pinned here (Break — Plan, the catalogue module):
- BK1.8  A fault is added without editing the core. A test-only fault that implements the `Fault`
         protocol and is registered from outside the package appears in `CATALOG`, parses in a
         condition name, applies through the applying module and is recorded like a launch fault;
         registering a name already taken is refused; a fault whose `apply` returns a result of the
         wrong shape is an instrument error, never a tool fault the agent sees.

And §11.1's invariants 1, 3, 5 and 7, and the version constant. The applying module does not exist
yet: `run_fault` (ruling 16) is the part of it that §11.1 asks of the core, and that the applying
module will call. Going all the way through `Session.call` is that module's test (ruling 17).

Every test that registers runs on a catalogue of its own (`fresh_changes`), except the first, which
runs a module on disk in its own interpreter, as a fault's author would.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from poisson_break import interfaces
from poisson_break.records import Applied
from tests.changes_support import (
    LAUNCH,
    REAL_RUNS,
    REAL_TEXT,
    Real,
    context,
    entry,
    fresh_changes,
    one,
    rng,
)
from tests.conftest import guarded_env


@pytest.fixture
def c() -> Iterator[ModuleType]:
    yield from fresh_changes()


def outside(c: ModuleType, **over: Any) -> Any:
    """A fault written with the members of §11.1 and no base class. It imports nothing from Break
    but the result it returns."""
    members = {
        "name": "flip",
        "surface": "tool",
        "description": "the real result, written backwards",
        "parameters": {"times": 1},
        "real_runs": True,
        "apply": lambda self, call, *, real, params, rng: c.Result(value=str(real())[::-1]),
    }
    members.update(over)
    return type("Outside", (), members)()


def behaves(c: ModuleType, returns: Any = None, *, real_calls: int = 1, raises: Exception | None = None,
            **over: Any) -> Any:
    """An outside fault that calls the real tool a stated number of times, then returns or raises
    what it is told to."""
    def apply(self: Any, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
        for _ in range(real_calls):
            real()
        if raises is not None:
            raise raises
        return returns
    return outside(c, apply=apply, **over)


def run(c: ModuleType, fault: Any, real: Real | None = None, **over: Any) -> Any:
    return c.run_fault(fault, context(c, **over), real=real if real is not None else Real(),
                       params=dict(fault.parameters), rng=rng())


# ---------------------------------------------------------------------------
# a module on disk, in its own interpreter, with no core file touched
# ---------------------------------------------------------------------------


AUTHOR = textwrap.dedent('''\
    """A fault its author wrote: this file is outside the package, and is all there is."""
    from poisson_break.changes import Result, register


    class Flip:
        name = "flip"
        surface = "tool"
        description = "the real result, written backwards"
        parameters = {"times": 1}
        real_runs = True

        def apply(self, call, *, real, params, rng):
            return Result(value=str(real())[::-1] * params["times"])


    register(Flip())
''')

DRIVER = textwrap.dedent('''\
    import json, random
    from poisson_break import changes as c

    out = {"before": sorted(f"{e.surface}:{e.name}" for e in c.CATALOG)}
    out["refused_before"] = False
    try:
        c.parse("tool:a#2=flip")
    except c.ChangeError:
        out["refused_before"] = True

    import flip_fault

    out["author_outside"] = not flip_fault.__file__.startswith(c.__file__.rsplit("/", 1)[0])
    line = [e for e in c.CATALOG if e.surface == "tool" and e.name == "flip"]
    out["lines"] = len(line)
    line = line[0]
    out["facts"] = [line.description, dict(line.parameters), line.real_runs, line.needs_adapter]
    condition = c.parse("tool:b#1=error + tool:a#2=flip")
    out["name"] = c.name(condition)
    out["round_trip"] = c.parse(c.name(condition)) == condition
    change = c.parse("tool:a#2=flip").changes[0]
    out["fields"] = [change.surface, change.tool, change.fault, change.call]
    out["fires"] = [c.applies(change, seed=1, tool="a", call=n) for n in (1, 2, 3)]
    ctx = c.CallContext(tool="a", args={}, call=2, condition=c.parse("tool:a#2=flip"), seed=1)
    outcome = c.run_fault(line.fault, ctx, real=lambda: "abc", params={"times": 2},
                          rng=random.Random(1))
    out["outcome"] = outcome.value
    print(json.dumps(out))
''')


def test_a_module_on_disk_registers_a_fault_with_no_core_file_changed(tmp_path: Path) -> None:
    (tmp_path / "flip_fault.py").write_text(AUTHOR)
    env = guarded_env()
    env["PYTHONPATH"] = f"{tmp_path}:{env['PYTHONPATH']}"
    done = subprocess.run([sys.executable, "-c", DRIVER], capture_output=True, text=True, timeout=120,
                          env=env, stdin=subprocess.DEVNULL, cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    # §11: the core never imports an implementation it did not load by name. On the path is not loaded.
    assert out["before"] == sorted(f"{s}:{n}" for s, n in LAUNCH)
    assert out["refused_before"] is True
    assert out["author_outside"] is True
    assert out["lines"] == 1
    assert out["facts"] == ["the real result, written backwards", {"times": 1}, True, False]
    assert sorted(out["name"].split(" + ")) == ["tool:a#2=flip", "tool:b#1=error"]
    assert out["round_trip"] is True
    assert out["fields"] == ["tool", "a", "flip", "#2"]
    assert out["fires"] == [False, True, False]
    assert out["outcome"] == "cbacba"


# ---------------------------------------------------------------------------
# the catalogue, once it is registered
# ---------------------------------------------------------------------------


def test_the_line_appears_and_a_catalogue_already_held_shows_it(c: ModuleType) -> None:
    held = c.CATALOG
    c.register(outside(c))
    line = entry("tool", "flip", c)
    assert (line.description, dict(line.parameters), line.real_runs) == (
        "the real result, written backwards", {"times": 1}, True)
    assert line.needs_adapter is False
    assert any(e.name == "flip" for e in held), "a module that imported CATALOG earlier sees it too"


def test_registering_leaves_the_launch_lines_as_they_were(c: ModuleType) -> None:
    before = {(e.surface, e.name): e for e in c.CATALOG}
    c.register(outside(c))
    after = {(e.surface, e.name): e for e in c.CATALOG}
    assert set(after) - set(before) == {("tool", "flip")}
    assert all(after[key] == before[key] for key in before)


def test_a_registered_line_is_read_like_a_launch_line(c: ModuleType) -> None:
    """Everything the catalogue says of `cut_off`, it says of the new one, by the same names: this
    is what `catalog` prints from."""
    c.register(outside(c))
    for attribute in ("surface", "name", "description", "parameters", "real_runs", "needs_adapter",
                      "fault"):
        assert hasattr(entry("tool", "flip", c), attribute)
        assert hasattr(entry("tool", "cut_off", c), attribute)
    assert isinstance(entry("tool", "flip", c).fault, interfaces.Fault)


def test_a_registered_model_fault_needs_an_adapter_too(c: ModuleType) -> None:
    """The surface decides, not who wrote it. It parses in the model's form and is refused without
    the capability, exactly as `model:cut_off#2` is."""
    from poisson_break.interfaces import Capabilities

    c.register(outside(c, name="garbled", surface="model", real_runs=False,
                       apply=lambda self, call, *, real, params, rng: c.Result(value="?")))
    assert entry("model", "garbled", c).needs_adapter is True
    condition = c.parse("model:garbled#2")
    assert c.name(condition) == "model:garbled#2"
    with pytest.raises(c.NeedsAdapter):
        c.check_capabilities(condition, Capabilities(tool_calls=True, model_calls=False,
                                                     conversation=False))
    assert c.check_capabilities(condition, Capabilities(tool_calls=True, model_calls=True,
                                                        conversation=True)) is None
    with pytest.raises(c.ChangeError):
        c.parse("tool:a#2=garbled")


# ---------------------------------------------------------------------------
# names, once it is registered: the same as a launch fault's
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("position", ["#1", "#2-4", "#*", "~0.3"])
def test_the_new_name_parses_in_every_position_a_launch_fault_takes(c: ModuleType,
                                                                    position: str) -> None:
    c.register(outside(c))
    text = f"tool:a{position}=flip"
    assert c.name(c.parse(text)) == text


def test_the_new_name_is_refused_on_a_surface_it_is_not_on(c: ModuleType) -> None:
    c.register(outside(c))
    with pytest.raises(c.ChangeError):
        c.parse("model:flip#2")
    with pytest.raises(c.ChangeError):
        c.parse("input:flip")


@pytest.mark.parametrize("position", ["#2", "#2-4", "#*", "~0.3", "~0.7"])
def test_the_new_fault_lands_on_the_same_calls_as_a_launch_fault(c: ModuleType, position: str) -> None:
    """Whether a change applies does not depend on the fault (§3.1), so a new fault takes over a
    launch fault's calls exactly, seed by seed."""
    c.register(outside(c))
    new, launch = one(f"tool:a{position}=flip", c), one(f"tool:a{position}=error", c)
    for seed in range(300):
        for call in (1, 2, 3, 4, 5):
            assert (c.applies(new, seed=seed, tool="a", call=call)
                    == c.applies(launch, seed=seed, tool="a", call=call))


def test_a_near_miss_of_the_new_name_gets_a_suggestion(c: ModuleType) -> None:
    c.register(outside(c))
    with pytest.raises(c.ChangeError) as refused:
        c.parse("tool:a#2=flp")
    assert refused.value.suggestion == "tool:a#2=flip"


def test_the_new_fault_fills_a_stored_record_as_a_launch_fault_does(c: ModuleType) -> None:
    """The record is the core's (§11.1 invariant 6): the fields come from the parsed change, the
    same way whoever wrote the fault."""
    c.register(outside(c))
    def stored(text: str) -> dict[str, Any]:
        change = one(text, c)
        return Applied(surface=change.surface, tool=change.tool, fault=change.fault,
                       call=change.call, applied=True, applied_call=2).to_dict()
    new, launch = stored("tool:a#2=flip"), stored("tool:a#2=error")
    assert new.pop("fault") == "flip"
    assert launch.pop("fault") == "error"
    assert new == launch


# ---------------------------------------------------------------------------
# what `register` refuses (§11.1 invariant 1, and the interface's members)
# ---------------------------------------------------------------------------


def test_a_taken_name_is_refused_and_the_first_stays(c: ModuleType) -> None:
    c.register(outside(c))
    second = outside(c, description="another fault wanting the name")
    with pytest.raises(c.ChangeError):
        c.register(second)
    assert entry("tool", "flip", c).description == "the real result, written backwards"
    assert sum(e.name == "flip" for e in c.CATALOG) == 1


@pytest.mark.parametrize("surface, taken", [("tool", "error"), ("tool", "planted_instruction"),
                                            ("model", "cut_off"), ("model", "error")])
def test_a_launch_name_is_taken(c: ModuleType, surface: str, taken: str) -> None:
    with pytest.raises(c.ChangeError):
        c.register(outside(c, name=taken, surface=surface))
    assert {(e.surface, e.name) for e in c.CATALOG} == set(LAUNCH)


def test_a_name_is_taken_within_its_surface(c: ModuleType) -> None:
    """Ruling 4. §11.1 says unique in the catalogue, and the launch catalogue holds five names on
    two surfaces, so unique cannot mean across them. `slow` is free on the model, and the tool's
    `slow` is unchanged."""
    c.register(outside(c, name="slow", surface="model", real_runs=False))
    assert entry("model", "slow", c).needs_adapter is True
    assert entry("tool", "slow", c).real_runs is True


def test_a_good_fault_is_taken_by_register(c: ModuleType) -> None:
    """The control for every refusal below: each differs from this in one member."""
    c.register(outside(c))


@pytest.mark.parametrize("over", [
    {"surface": "input"},
    {"surface": "user"},
    {"surface": "env"},
    {"surface": "nowhere"},
    {"real_runs": None},
    {"real_runs": "yes"},
    {"real_runs": 1},
    {"name": ""},
    {"name": "has space"},
    {"name": "has=equals"},
    {"name": "has#hash"},
    {"name": "has~tilde"},
    {"name": "has@at"},
    {"name": "has+plus"},
    {"name": 7},
    {"description": ""},
    {"description": "two lines\nof description"},
    {"description": "built in module BK14"},
    {"description": "as ruling 13 says"},
    {"description": "from Session A of the catalogue"},
    {"parameters": None},
    {"parameters": ["times"]},
], ids=lambda over: "-".join(f"{k}={v!r}" for k, v in over.items()))
def test_a_member_outside_the_interface_is_refused(c: ModuleType, over: dict[str, Any]) -> None:
    """Ruling 16. `surface` is `tool` or `model`; a third value of `real_runs` is §11.1's own example
    of a breaking change; a name has to parse; invariant 7 for the description. Refused here, once,
    and not later on some call in a hunt."""
    bad = outside(c, **over)
    with pytest.raises(c.ChangeError):
        c.register(bad)
    assert {(e.surface, e.name) for e in c.CATALOG} == set(LAUNCH)


def test_something_with_no_apply_is_refused(c: ModuleType) -> None:
    """BK0's protocols say the core can refuse this at load: it is not a `Fault`."""
    no_apply = type("NoApply", (), {"name": "flip", "surface": "tool", "description": "d",
                                    "parameters": {}, "real_runs": True})()
    with pytest.raises(c.ChangeError):
        c.register(no_apply)


def test_a_refusal_is_one_line_and_not_a_repr(c: ModuleType) -> None:
    with pytest.raises(c.ChangeError) as refused:
        c.register(outside(c, name="error"))
    assert "\n" not in str(refused.value)
    assert "object at 0x" not in str(refused.value)


# ---------------------------------------------------------------------------
# §11.1 invariant 3: the core counts, and a mismatch is an instrument error
# ---------------------------------------------------------------------------


def test_a_fault_that_keeps_its_word_returns_its_outcome(c: ModuleType) -> None:
    """The control for what follows, and `run_fault` hands back exactly what the fault gave."""
    result = c.Result(value="done")
    assert run(c, behaves(c, result, real_calls=1, real_runs=True)) == result
    error = c.ToolError(kind="error", message="no route to the service")
    assert run(c, behaves(c, error, real_calls=0, real_runs=False)) == error


@pytest.mark.parametrize("declared, made", [(True, 0), (True, 2), (False, 1), (False, 2)])
def test_a_fault_that_breaks_its_word_on_the_real_tool_is_an_instrument_error(c: ModuleType,
                                                                              declared: bool,
                                                                              made: int) -> None:
    """Never the outcome the fault returned: an agent cannot be shown the result of a call the
    record would describe wrongly."""
    fault = behaves(c, c.Result(value="done"), real_calls=made, real_runs=declared)
    with pytest.raises(c.InstrumentError):
        run(c, fault)


# ---------------------------------------------------------------------------
# §11.1 invariant 5: the wrong shape; §11: an exception
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("returned", [
    None,
    "a bare string",
    {"value": "a mapping"},
    ["a", "list"],
    7,
    ValueError("an exception returned, not raised"),
], ids=["none", "text", "mapping", "list", "number", "exception"])
def test_an_outcome_of_the_wrong_shape_is_an_instrument_error(c: ModuleType, returned: Any) -> None:
    """BK1.8. The fault counted its real calls right, so this is the shape alone."""
    with pytest.raises(c.InstrumentError):
        run(c, behaves(c, returned))


def test_a_pair_of_outcomes_is_the_wrong_shape(c: ModuleType) -> None:
    pair = (c.Result(value="x"), c.ToolError(kind="error", message="y"))
    with pytest.raises(c.InstrumentError):
        run(c, behaves(c, pair))


@pytest.mark.parametrize("raised", [KeyError("oops"), ValueError("oops"), ZeroDivisionError()],
                         ids=["key", "value", "arithmetic"])
def test_an_exception_in_apply_is_an_instrument_error(c: ModuleType, raised: Exception) -> None:
    """§11: never a tool fault the agent sees, never an agent failure."""
    with pytest.raises(c.InstrumentError):
        run(c, behaves(c, c.Result(value="x"), raises=raised))


def test_an_instrument_error_cannot_be_taken_for_a_refused_name_or_a_tool_error(c: ModuleType) -> None:
    """Three different things reach three different places: settings, the count of runs not counted,
    and the agent."""
    assert not issubclass(c.InstrumentError, c.ChangeError)
    assert not isinstance(c.ToolError(kind="error", message="x"), Exception)


def test_the_real_tools_own_exception_is_not_an_instrument_error(c: ModuleType) -> None:
    """Ruling 18. A tool that fails is what tools do, and the agent's to handle: it goes through
    `run_fault` untouched, with no fault's work done on top, and no run is lost from the count."""
    class ToolFailed(RuntimeError):
        pass

    with pytest.raises(ToolFailed):
        run(c, entry("tool", "cut_off", c).fault, Real(raises=ToolFailed("the tool itself failed")))


@pytest.mark.parametrize("fault", ["slow", "empty", "cut_off", "malformed", "stale", "lost_reply",
                                   "planted_instruction"])
def test_every_launch_fault_that_runs_the_tool_lets_its_exception_through(c: ModuleType,
                                                                          fault: str) -> None:
    class ToolFailed(RuntimeError):
        pass

    line = entry("tool", fault, c)
    real = Real(raises=ToolFailed("the tool itself failed"))
    with pytest.raises(ToolFailed):
        c.run_fault(line.fault, context(c), real=real, params=line.parameters, rng=rng())
    assert real.calls == 1


@pytest.mark.parametrize("fault, runs", REAL_RUNS.items())
def test_a_launch_fault_goes_through_run_fault_like_a_new_one(c: ModuleType, fault: str,
                                                              runs: bool) -> None:
    """One path for all ten: the outcome is whole, as its own `apply` gave it, the delay of `slow`
    included, and the real tool ran once or not at all."""
    line = entry("tool", fault, c)
    real = Real(REAL_TEXT)
    through = c.run_fault(line.fault, context(c), real=real, params=line.parameters, rng=rng())
    direct = line.fault.apply(context(c), real=Real(REAL_TEXT), params=line.parameters, rng=rng())
    assert through == direct
    assert real.calls == (1 if runs else 0)


# ---------------------------------------------------------------------------
# the version constant, and the public names
# ---------------------------------------------------------------------------


def test_the_interfaces_version_is_one_and_is_the_one_declared(c: ModuleType) -> None:
    """Spec §11: 1 at v0.1.0, and one constant, not two that can drift. A bump is a core change with
    its own session; this fails on one made by accident, or made in only one module."""
    import poisson_break.interfaces as declared

    assert c.FAULT_INTERFACE_VERSION == 1
    assert c.FAULT_INTERFACE_VERSION == declared.FAULT_INTERFACE_VERSION


def test_the_fault_protocol_is_the_one_declared(c: ModuleType) -> None:
    """Ruled 2026-11-04: the interfaces live in one module, re-exported under the plan's names."""
    import poisson_break.interfaces as declared

    assert c.Fault is declared.Fault


@pytest.mark.parametrize("public", [
    "Change", "Condition", "parse", "name", "Fault", "CATALOG", "register", "applies",
    "FAULT_INTERFACE_VERSION",
    # the input operators and the conversation moves
    "typos", "reordered", "padded", "cut_short", "variant",
    "repeats", "interrupts", "goes_quiet", "presses",
    # the names the rulings add
    "CallContext", "Result", "ToolError", "ChangeError", "NeedsAdapter", "InstrumentError",
    "check_capabilities", "run_fault", "marker",
])
def test_the_public_names_are_declared(c: ModuleType, public: str) -> None:
    """The plan's, and what the rulings add. A later module imports these and no other: BK8.8 reads
    the source to check it."""
    assert public in c.__all__
    assert hasattr(c, public)


def test_a_parsed_change_is_a_change_and_a_parsed_condition_a_condition(c: ModuleType) -> None:
    condition = c.parse("tool:a#2=error")
    assert isinstance(condition, c.Condition)
    assert isinstance(condition.changes[0], c.Change)
    assert isinstance(condition.changes, tuple)
