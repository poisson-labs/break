"""The package as a whole: what importing it does, what the wheel carries, and the two checks
the plan asks of CI (no statistic computed locally; nothing leaves the machine).

Invariants pinned here (Break — Plan, the repo module and §2):
- BK0.4  The clean-install job fails if the wheel lacks any file a command reads at run time.
         Here: the wheel built from this tree carries every file under the package, its
         licence files and its console script; the job in CI installs that wheel in a fresh
         environment outside the checkout and runs the command (`scripts/clean_install.py`).
- BK0.5  Importing `poisson_break` imports no framework, opens no socket and reads no key.
- §2.5   Break computes no statistic: no import of `scipy.stats` or `statsmodels`, and none of
         the names of a test or interval computed locally, anywhere in the package's source.
- §2.6   Nothing leaves the machine: the suite runs under a guard that fails any connection
         (tests/conftest.py); here, the guard is shown to be on.
"""

from __future__ import annotations

import ast
import json
import socket
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from tests.conftest import REPO, NetworkGuard, run_python

SRC = REPO / "src" / "poisson_break"

# The frameworks and SDKs Break must not import on its own: each is an optional extra of an
# on-demand module, loaded only by name from the settings.
FRAMEWORKS = ("openai", "agents", "langchain", "langchain_core", "langgraph", "crewai", "mcp",
              "anthropic")

# Modules and names that compute a test or an interval. Break reads Trace's answer and calls
# Prove's adjustment; it computes none of these itself.
STATISTICS_MODULES = ("scipy", "statsmodels", "sklearn", "pingouin")
STATISTICS_NAMES = frozenset({
    "fisher_exact", "binomtest", "binom_test", "chi2_contingency", "chisquare", "mannwhitneyu",
    "ttest_ind", "ttest_rel", "ttest_1samp", "wilcoxon", "kruskal", "proportion_confint",
    "proportions_ztest", "clopper_pearson", "wilson", "mantelhaenszel", "cmh_test",
    "StratifiedTable", "Table2x2", "bootstrap", "hypergeom", "betainc", "ppf", "cdf", "sf", "isf",
    "erf", "erfc", "erfinv", "norm", "binom", "beta",
})


def _source_files() -> list[Path]:
    files = sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)
    assert files, f"no source under {SRC}"
    return files


# ---------------------------------------------------------------------------
# BK0.5  importing the package
# ---------------------------------------------------------------------------

IMPORT_PROBE = r'''
import json, os, sys

socket_events = []
def hook(event, args):
    if event.startswith("socket."):
        socket_events.append(event)
sys.addaudithook(hook)

read = []
_getitem, _contains = os._Environ.__getitem__, os._Environ.__contains__
def getitem(self, key):
    read.append(str(key)); return _getitem(self, key)
def contains(self, key):
    read.append(str(key)); return _contains(self, key)
os._Environ.__getitem__ = getitem
os._Environ.__contains__ = contains

before = set(sys.modules)
import importlib, pkgutil
import poisson_break
for info in pkgutil.walk_packages(poisson_break.__path__, "poisson_break."):
    if not info.name.endswith("__main__"):
        importlib.import_module(info.name)
import poisson_break.cli
from poisson_break.cli import build_parser
build_parser("poisson-break")
loaded = sorted(set(sys.modules) - before)
print(json.dumps({"sockets": socket_events, "env": sorted(set(read)), "loaded": loaded}))
'''


@pytest.fixture(scope="module")
def imported() -> dict[str, list[str]]:
    ran = run_python(IMPORT_PROBE)
    assert ran.exit == 0, ran.stderr
    result: dict[str, list[str]] = json.loads(ran.stdout.strip().splitlines()[-1])
    return result


def test_importing_the_package_imports_no_framework(imported: dict[str, list[str]]) -> None:
    tops = {name.split(".")[0] for name in imported["loaded"]}
    assert tops.isdisjoint(FRAMEWORKS), sorted(tops & set(FRAMEWORKS))


def test_importing_the_package_opens_no_socket(imported: dict[str, list[str]]) -> None:
    assert imported["sockets"] == []


def test_importing_the_package_reads_no_key(imported: dict[str, list[str]]) -> None:
    """No environment variable whose name says key, token, secret or password is read while the
    package and its command are loaded."""
    suspicious = [name for name in imported["env"]
                  if any(w in name.upper() for w in ("KEY", "TOKEN", "SECRET", "PASSWORD"))]
    assert suspicious == []


# ---------------------------------------------------------------------------
# §2.5  no statistic computed locally
# ---------------------------------------------------------------------------


def _imports_and_names(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return imports, names


def test_no_module_imports_a_statistics_library() -> None:
    hits = []
    for path in _source_files():
        imports, _ = _imports_and_names(path)
        bad = sorted(i for i in imports if i.split(".")[0] in STATISTICS_MODULES)
        if bad:
            hits.append(f"{path.relative_to(REPO)}: {', '.join(bad)}")
    assert hits == []


def test_no_module_names_a_test_or_interval_computed_locally() -> None:
    hits = []
    for path in _source_files():
        _, names = _imports_and_names(path)
        bad = sorted(names & STATISTICS_NAMES)
        if bad:
            hits.append(f"{path.relative_to(REPO)}: {', '.join(bad)}")
    assert hits == []


# ---------------------------------------------------------------------------
# §2.6  the guard is on
# ---------------------------------------------------------------------------


def test_the_network_guard_is_on_in_the_test_process() -> None:
    with pytest.raises(NetworkGuard):
        socket.create_connection(("127.0.0.1", 9))
    with pytest.raises(NetworkGuard):
        socket.socket().connect(("127.0.0.1", 9))


def test_the_network_guard_is_on_in_child_processes() -> None:
    ran = run_python("import socket\nsocket.create_connection(('127.0.0.1', 9))")
    assert ran.exit != 0
    assert "the network guard" in ran.stderr


# ---------------------------------------------------------------------------
# BK0.4  the wheel
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The wheel built from this tree with hatchling, as the clean-install job builds it."""
    out = tmp_path_factory.mktemp("wheel")
    done = subprocess.run([sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(out)],
                          cwd=REPO, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stdout + done.stderr
    wheels = list(out.glob("*.whl"))
    assert len(wheels) == 1, wheels
    return wheels[0]


def test_the_wheel_carries_every_file_under_the_package(wheel: Path) -> None:
    """Every file under `src/poisson_break` that is not bytecode is in the wheel, by the same
    relative path: a module, a data file or `py.typed` left out of the build config is found
    here, before the clean-install job."""
    with zipfile.ZipFile(wheel) as z:
        shipped = set(z.namelist())
    expected = {str(p.relative_to(SRC.parent)) for p in SRC.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    assert expected, "nothing under the package"
    missing = sorted(expected - shipped)
    assert missing == []


def test_the_wheel_carries_the_licence_files_and_the_console_script(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()
        dist_info = [n.split("/")[0] for n in names if n.endswith("/METADATA")][0]
        assert f"{dist_info}/licenses/LICENSE" in names
        assert f"{dist_info}/licenses/NOTICE" in names
        entry_points = z.read(f"{dist_info}/entry_points.txt").decode()
    assert "[console_scripts]" in entry_points
    assert "poisson-break = poisson_break.cli:main" in entry_points


def test_the_wheel_is_named_poisson_break_and_versioned_like_the_package(wheel: Path) -> None:
    import poisson_break

    assert wheel.name.startswith(f"poisson_break-{poisson_break.__version__}-")
    assert wheel.name.endswith("py3-none-any.whl")
