"""The runs module's public names, and what it takes from Prove (plan BK5, BK5.1, BK5.3, §7 ruling 9).

These are the tests that rest on the plan's own words. Every test that makes a hunt rests on a shape the plan does not
give, and is written once that shape is ruled.

- Public names: the twelve the plan lists are there, and are what the module says it offers.
- `ToolInfo` and `RunResult` are defined in the applying module and re-exported here; `Target` is the way-in protocol;
  `TARGET_INTERFACE_VERSION` is 1 and is the interfaces module's own.
- BK5.1: nothing from a Prove module whose name starts with an underscore is imported, by any module of the package.
- §7 ruling 9: the store and the planner come from Prove's own modules, under the exact pin.
- BK5.3: Prove's own episode timeout is not used.
"""

from __future__ import annotations

import pytest

from tests.hunt_support import (
    PUBLIC_NAMES,
    apply_module,
    hunt,
    hunt_source,
    interfaces,
    keywords_passed,
    package_sources,
    private,
    prove_imports,
)

# ---------------------------------------------------------------------------
# the names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", PUBLIC_NAMES)
def test_each_public_name_of_the_plan_is_there_and_is_offered(name: str) -> None:
    """Plan BK5's public names. Each is an attribute of the module and is in what it says it offers, so `from
    poisson_break.hunt import *` and a reader of `__all__` see the same twelve the plan lists."""
    module = hunt()
    assert hasattr(module, name), f"poisson_break.hunt has no {name}"
    assert name in module.__all__


def test_nothing_offered_is_missing_or_private() -> None:
    """What the module offers is really there, and none of it is a private name: a name in `__all__` that does not
    exist breaks `import *`, and a private one would be a promise nobody meant."""
    module = hunt()
    assert len(set(module.__all__)) == len(module.__all__)
    for name in module.__all__:
        assert hasattr(module, name), f"__all__ names {name}, which is not there"
        assert not name.startswith("_")


def test_tool_info_and_run_result_are_the_applying_modules_own() -> None:
    """Plan BK5: "`ToolInfo` and `RunResult` (defined in `poisson_break.apply`, re-exported here)". The same objects,
    not copies: a way in written against either module makes a result the other accepts."""
    assert hunt().ToolInfo is apply_module().ToolInfo
    assert hunt().RunResult is apply_module().RunResult


def test_target_is_the_way_in_protocol_and_its_version_is_one() -> None:
    """Plan BK5: "`Target` (the way-in protocol of spec §11.2)" and "`TARGET_INTERFACE_VERSION = 1`". One protocol
    and one number in the package, so a way in that checks the constant checks the one the core means."""
    assert hunt().Target is interfaces().Target
    assert hunt().TARGET_INTERFACE_VERSION == 1
    assert hunt().TARGET_INTERFACE_VERSION is interfaces().TARGET_INTERFACE_VERSION


# ---------------------------------------------------------------------------
# what is taken from Prove
# ---------------------------------------------------------------------------


def test_the_reader_of_imports_finds_each_way_of_reaching_into_prove() -> None:
    """A control on the three tests below: the reader sees an import at the top and one inside a function, of a module
    and of a name, and tells Prove's private side from its public one. It reads nothing of the runs module."""
    source = (
        "import poisson_prove._look\n"
        "import poisson_prove.store\n"
        "from poisson_prove import __version__, Episode\n"
        "from poisson_prove.store import Store, _SCHEMA\n"
        "from poisson_prove._limits import design\n"
        "from poisson_prove.core._inner import thing\n"
        "import poisson_prover\n"
        "from . import apply\n"
        "def later():\n"
        "    from poisson_prove.executor import _record, plan\n"
    )
    found = prove_imports(source)
    assert ("poisson_prover", None) not in found and len(found) == 10
    assert sorted(i for i in found if private(i)) == [
        ("poisson_prove._limits", "design"),
        ("poisson_prove._look", None),
        ("poisson_prove.core._inner", "thing"),
        ("poisson_prove.executor", "_record"),
        ("poisson_prove.store", "_SCHEMA"),
    ]
    assert not private(("poisson_prove", "__version__"))
    assert keywords_passed("run(p, f, s, episode_timeout=3)\nrun(**{'max_rollouts': 1})\n") == {
        "episode_timeout", "max_rollouts"}


def test_the_runs_module_takes_nothing_from_proves_private_side() -> None:
    """BK5.1: "nothing from a Prove module whose name starts with an underscore is imported". A private name of a public
    module is the same reach, so it is held too."""
    reached = [imported for imported in prove_imports(hunt_source()) if private(imported)]
    assert reached == []


def test_no_module_of_the_package_takes_from_proves_private_side() -> None:
    """The same for every module beside it, so the rule cannot be kept in one file by moving the import to another.
    It needs the runs module to be there, or it would hold of a package that stores no run at all."""
    sources = package_sources()
    assert "hunt.py" in sources, "there is no poisson_break/hunt.py"
    reached = {name: [i for i in prove_imports(text) if private(i)] for name, text in sources.items()}
    assert {name: found for name, found in reached.items() if found} == {}


def test_the_store_and_the_planner_are_proves_own() -> None:
    """Plan §7 ruling 9: "Break imports Prove's store, planner and adjustment from Prove's non-underscored modules". The
    store is `poisson_prove.store` and the planner is in `poisson_prove.executor`; the adjustment is the confirm
    module's to import. A runs module that wrote its own store, or drew its own seeds, would import neither."""
    modules = {module for module, _name in prove_imports(hunt_source())}
    assert "poisson_prove.store" in modules
    assert "poisson_prove.executor" in modules


def test_proves_own_episode_timeout_is_not_used() -> None:
    """BK5.3: "Prove's own episode timeout is not used". Prove stores a run it cut off as a row with no outcome, which
    its comparisons then leave out; Break enforces the limit itself so that a run past it is a `failed` row. The
    timeout is one keyword of Prove's runner, and no call in the runs module passes it."""
    assert "episode_timeout" not in keywords_passed(hunt_source())
