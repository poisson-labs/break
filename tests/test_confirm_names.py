"""The confirm module's names, and what its source may and may not do.

Plan §2 item 5 and spec §5.5: Break computes no statistic. Any test, interval, detection limit or adjustment comes
from Trace's command or from a function of Prove. Plan BK7's public names, with what rulings 5 to 9, 14, 16 and 17
of `evidence/bk7/open-points.md` add. Ruling 4: Trace is a command, run as `python -m poisson_trace`, never imported.

The behaviour that shows the numbers are read and not computed is in `test_confirm_numbers.py`; here the source.
"""

from __future__ import annotations

import ast
import importlib.metadata
from pathlib import Path

from tests.confirm_support import PUBLIC_NAMES, confirm_module

SRC = Path(__file__).resolve().parents[1] / "src" / "poisson_break"
CONFIRM = SRC / "confirm.py"

# Names a module would reach for to compute a p-value, an interval or a correction of its own, beyond the package
# check's list (tests/test_package.py): the arithmetic of a test or a score interval, and ranking p-values.
COMPUTING = frozenset({"sqrt", "isqrt", "erf", "erfc", "lgamma", "gamma", "log1p", "expm1", "comb", "factorial",
                       "NormalDist", "argsort", "cumsum", "accumulate", "minimum", "maximum"})
STATISTICS = ("scipy", "statsmodels", "sklearn", "pingouin", "statistics")


def _tree() -> ast.Module:
    return ast.parse(CONFIRM.read_text(encoding="utf-8"), filename=str(CONFIRM))


def test_the_public_names_are_there() -> None:
    module = confirm_module()
    missing = [name for name in PUBLIC_NAMES if not hasattr(module, name)]
    assert missing == []
    assert set(PUBLIC_NAMES) <= set(module.__all__)


def test_confirm_error_is_a_value_error() -> None:
    """Ruling 6: the module's one refusal is a `ValueError`; each refusal's `.reason` is held where it is raised."""
    assert issubclass(confirm_module().ConfirmError, ValueError)


def test_trace_version_is_the_installed_trace() -> None:
    """Ruling 5: `TRACE_VERSION` is the version the pinned commit declares, held equal to the installed Trace's. Red
    while no Trace is installed, as BK0's tests that read Trace are."""
    assert confirm_module().TRACE_VERSION == importlib.metadata.version("poisson-trace")


def test_no_module_imports_trace() -> None:
    """Ruling 4 and spec §6.2: Trace declares its command and JSON as its surface; Break calls the command."""
    hits = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(a.name.split(".")[0] == "poisson_trace" for a in node.names):
                hits.append(path.name)
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "poisson_trace":
                hits.append(path.name)
    assert hits == []


def test_only_the_confirm_module_names_trace_s_command() -> None:
    """`ask_trace` is "the one place Trace's command is called" (plan BK7): no other module names it."""
    naming = sorted(p.name for p in SRC.rglob("*.py")
                    if "poisson_trace" in p.read_text(encoding="utf-8") and p.name != "confirm.py")
    assert naming == []
    assert "poisson_trace" in CONFIRM.read_text(encoding="utf-8")


def test_the_module_imports_no_statistics_library_and_nothing_that_computes_one() -> None:
    """No `scipy`, no `statistics` and none of the others: nothing here tests, ranks or transforms p-values."""
    bad = []
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            bad += [a.name for a in node.names if a.name.split(".")[0] in STATISTICS]
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in STATISTICS:
            bad.append(node.module or "")
    assert bad == []


def test_the_module_names_no_arithmetic_of_a_test_an_interval_or_a_correction() -> None:
    names: set[str] = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.alias):
            names.add(node.name.split(".")[-1])
    assert sorted(names & COMPUTING) == []


def test_the_adjustment_is_prove_s() -> None:
    """Spec §5.5: "adjusted ... with Prove's public adjustment". The module takes `bh` from `poisson_prove.diff`."""
    found = False
    for node in ast.walk(_tree()):
        if isinstance(node, ast.ImportFrom) and node.module == "poisson_prove.diff":
            found = found or any(a.name == "bh" for a in node.names)
        if isinstance(node, ast.ImportFrom) and node.module == "poisson_prove":
            found = found or any(a.name == "diff" for a in node.names)
        if isinstance(node, ast.Import):
            found = found or any(a.name == "poisson_prove.diff" for a in node.names)
    assert found
