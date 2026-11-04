"""The four extension points of spec §11, declared in `poisson_break.interfaces` with their
version constants: adding a fault, adding a way in, adding a strategy, the user's own check.

At version 1 each interface has exactly the members spec §11 gives, with keyword-only arguments
where the spec puts them. An additive change keeps the number; removing or renaming a member, or
changing what one means, bumps it. These tests pin the members of version 1: a later session that
removes or renames one without bumping the number fails here.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from poisson_break import interfaces
from poisson_break.interfaces import Capabilities, Check, Fault, Strategy, Target

KW = inspect.Parameter.KEYWORD_ONLY
POS = inspect.Parameter.POSITIONAL_OR_KEYWORD


def _params(method: Any) -> list[tuple[str, Any]]:
    return [(name, p.kind) for name, p in inspect.signature(method).parameters.items()
            if name != "self"]


def _members(protocol: type) -> set[str]:
    """The protocol's own members: its annotated data members and its methods."""
    own = vars(protocol)
    return set(inspect.get_annotations(protocol)) | {
        name for name, value in own.items() if callable(value) and not name.startswith("_")}


def test_the_four_version_constants_are_one() -> None:
    assert interfaces.FAULT_INTERFACE_VERSION == 1
    assert interfaces.TARGET_INTERFACE_VERSION == 1
    assert interfaces.STRATEGY_INTERFACE_VERSION == 1
    assert interfaces.CHECK_INTERFACE_VERSION == 1


def test_the_versions_are_whole_numbers_and_the_public_names_are_declared() -> None:
    for name in ("FAULT_INTERFACE_VERSION", "TARGET_INTERFACE_VERSION",
                 "STRATEGY_INTERFACE_VERSION", "CHECK_INTERFACE_VERSION",
                 "Fault", "Target", "Strategy", "Check", "Capabilities"):
        assert name in interfaces.__all__, name
        assert type(getattr(interfaces, name)) is int or inspect.isclass(getattr(interfaces, name))


# ---------------------------------------------------------------------------
# §11.1  a fault
# ---------------------------------------------------------------------------


def test_fault_interface_at_version_1() -> None:
    """`name`, `surface`, `description`, `parameters`, `real_runs` and
    `apply(call, *, real, params, rng)`."""
    members = _members(Fault)
    assert {"name", "surface", "description", "parameters", "real_runs", "apply"} <= members
    assert _params(Fault.apply) == [("call", POS), ("real", KW), ("params", KW), ("rng", KW)]


# ---------------------------------------------------------------------------
# §11.2  a way in
# ---------------------------------------------------------------------------


def test_target_interface_at_version_1() -> None:
    """`kind`, the framework versions it was checked against, `tools()`, `capabilities()` and
    `run(case, session, *, seed, limits)`."""
    members = _members(Target)
    assert {"kind", "framework_versions", "tools", "capabilities", "run"} <= members
    assert _params(Target.tools) == []
    assert _params(Target.capabilities) == []
    assert _params(Target.run) == [("case", POS), ("session", POS), ("seed", KW), ("limits", KW)]


def test_capabilities_are_the_three_of_the_spec() -> None:
    """Route tool calls, fault model calls, drive a scripted conversation; frozen; a fourth
    would be a new field with a default of cannot, never a change to these three."""
    import dataclasses

    assert [f.name for f in dataclasses.fields(Capabilities)] == ["tool_calls", "model_calls",
                                                                 "conversation"]
    caps = Capabilities(tool_calls=True, model_calls=False, conversation=False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        caps.model_calls = True  # type: ignore[misc]
    with pytest.raises(TypeError):
        Capabilities(True, False, False)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# §11.3  a strategy
# ---------------------------------------------------------------------------


def test_strategy_interface_at_version_1() -> None:
    """`propose(seen, budget, *, rng)`, the shape FSPC's Spec B1 defines."""
    members = _members(Strategy)
    assert {"propose"} <= members
    assert _params(Strategy.propose) == [("seen", POS), ("budget", POS), ("rng", KW)]


# ---------------------------------------------------------------------------
# §11.4  the user's own check
# ---------------------------------------------------------------------------


def test_check_interface_at_version_1() -> None:
    """`check(run)`: a callable of one argument, named by an import path."""
    assert _params(Check.__call__) == [("run", POS)]


# ---------------------------------------------------------------------------
# an implementation written outside the package is recognised by shape alone
# ---------------------------------------------------------------------------


class _OutsideFault:
    name = "flip"
    surface = "tool"
    description = "the real result with its first and last characters swapped"
    parameters: dict[str, object] = {}
    real_runs = True

    def apply(self, call: Any, *, real: Any, params: Any, rng: Any) -> Any:
        return real()


class _OutsideTarget:
    kind = "scripted"
    framework_versions = ()

    def tools(self) -> list[Any]:
        return []

    def capabilities(self) -> Capabilities:
        return Capabilities(tool_calls=True, model_calls=False, conversation=False)

    def run(self, case: Any, session: Any, *, seed: int, limits: Any) -> Any:
        return None


class _OutsideStrategy:
    def propose(self, seen: Any, budget: int, *, rng: Any) -> list[Any]:
        return []


def _outside_check(run: Any) -> str | None:
    return None


def test_an_implementation_outside_the_package_satisfies_the_protocol() -> None:
    """The core finds an implementation by name and checks it by shape, never by inheritance:
    none of these import anything but `Capabilities`."""
    assert isinstance(_OutsideFault(), Fault)
    assert isinstance(_OutsideTarget(), Target)
    assert isinstance(_OutsideStrategy(), Strategy)
    assert isinstance(_outside_check, Check)


def test_a_missing_member_fails_the_protocol() -> None:
    """A fault without `apply`, a way in without `capabilities`, a strategy without `propose`
    are not implementations: the core can refuse them at load with one line."""
    class NoApply:
        name, surface, description, parameters, real_runs = "x", "tool", "d", {}, True

    class NoCapabilities:
        kind, framework_versions = "k", ()

        def tools(self) -> list[Any]:
            return []

        def run(self, case: Any, session: Any, *, seed: int, limits: Any) -> Any:
            return None

    class NoPropose:
        def suggest(self, seen: Any, budget: int, *, rng: Any) -> list[Any]:
            return []

    assert not isinstance(NoApply(), Fault)
    assert not isinstance(NoCapabilities(), Target)
    assert not isinstance(NoPropose(), Strategy)
