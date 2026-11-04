"""What Break depends on, and at what version.

Invariant pinned here (Break — Plan, the repo module):
- BK0.7  The two dependencies are exact pins, and the pin on Prove equals the pin Trace
         declares, checked by a test that reads both packages' metadata.

And the fact the later modules rest on: at the pinned Prove, the store, the planner and the
adjustment are importable from Prove's non-underscored modules (plan §6, P4).
"""

from __future__ import annotations

import importlib
import importlib.metadata
import re

import pytest

PIN = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)\s*==\s*(?P<version>[A-Za-z0-9_.!+-]+)\s*$")


def _requirements(distribution: str) -> list[str]:
    """The distribution's declared requirements without a marker (its ordinary dependencies)."""
    try:
        declared = importlib.metadata.requires(distribution) or []
    except importlib.metadata.PackageNotFoundError:
        pytest.fail(f"{distribution} is not installed, so its metadata cannot be read")
    return [r for r in declared if ";" not in r]


def _pin_of(distribution: str, on: str) -> str:
    """The exact version `distribution` pins `on` to; fails when there is no such pin or when
    it is not exact."""
    found = [r for r in _requirements(distribution)
             if re.split(r"[\s=<>!~\[]", r, maxsplit=1)[0].lower() == on.lower()]
    assert found, f"{distribution} declares no dependency on {on}"
    assert len(found) == 1, f"{distribution} declares {on} more than once: {found}"
    match = PIN.match(found[0])
    assert match, f"{distribution} does not pin {on} exactly: {found[0]!r}"
    return match["version"]


def test_prove_is_pinned_exactly_and_installed_at_the_pin() -> None:
    pinned = _pin_of("poisson-break", "poisson-prove")
    assert importlib.metadata.version("poisson-prove") == pinned


def test_trace_is_pinned_exactly_and_installed_at_the_pin() -> None:
    pinned = _pin_of("poisson-break", "poisson-trace")
    assert importlib.metadata.version("poisson-trace") == pinned


def test_the_prove_pin_is_the_one_trace_declares() -> None:
    """Break's Prove is whatever Trace pins, so the three agree on one Prove (plan §1; ruling
    10 of the 2026-11-04 list). Read from both packages' metadata, never from a constant."""
    ours = _pin_of("poisson-break", "poisson-prove")
    traces = _pin_of("poisson-trace", "poisson-prove")
    assert ours == traces


def test_prove_is_the_only_pin_that_is_not_poisson_labs_own() -> None:
    """Every other ordinary dependency is a floor, not a pin: the exact pins are Prove's and
    Trace's, because Break reads a named JSON schema from Trace and Trace pins Prove."""
    pins = [r for r in _requirements("poisson-break") if PIN.match(r)]
    names = sorted(PIN.match(r)["name"].lower() for r in pins)  # type: ignore[index]
    assert set(names) <= {"poisson-prove", "poisson-trace"}, names


@pytest.mark.parametrize("module, names", [
    ("poisson_prove.store", ("Store",)),
    ("poisson_prove.executor", ("plan", "Plan")),
    ("poisson_prove.diff", ("bh", "holm")),
])
def test_prove_store_planner_and_adjustment_import_from_public_modules(module: str,
                                                                        names: tuple[str, ...]) -> None:
    """At the pinned Prove, the modules Break will import for storing runs, planning and the
    correction across candidates exist under non-underscored names (plan §6, P4). A Prove release
    that moves one is met here, not in a hunt."""
    assert not any(part.startswith("_") for part in module.split(".")), module
    loaded = importlib.import_module(module)
    for name in names:
        assert hasattr(loaded, name), f"{module} has no {name}"
