"""`poisson_break.settings.install_command`: the `pip install` line for a kind whose way in is not installed.

Taylor's yes to BK8 point 40 (2026-11-07). Which extra a kind needs, and whether it is installed, lived only in the
settings module's private `_WAYS_IN` and `_module_is_there`, and `load` says it only inside its refusal's text, so
`init`'s install command (point 4) had no public name to come from. The settings module gets one,
`install_command(kind) -> str | None`: the `pip install` line when the kind's way in is not installed, else `None`.
BK8 Session B adds it; this file holds what it hands back.

Taylor's yes on hands-on issue 17 (2026-11-13), as the coordinator's review of it settled: this release publishes no
extra, so `install_command` hands back `None` for every kind, and `load`'s refusal of a kind whose way in is not there
says this version has only the rollout way in, naming no command. The table of modules and extras stays for the
version that ships one, and the refusal still lifts when the way in's module is there.

None of the five extras is installed where the tests run; each test that rests on that says so first, through `load`.
Where a way in is installed, a child process stands in for it: an import finder put first that finds every module of
the package that is not there, as an installed extra would be found.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from tests.hunt_support import settings_module, settings_text

REPO = Path(__file__).resolve().parents[1]

# Each kind whose way in is an optional extra, and that extra: spec §9.1, BK4.7 and `load`'s refusal.
EXTRAS = {"openai-agents": "openai-agents", "langgraph": "langgraph", "crewai": "crewai", "mcp": "mcp",
          "command": "mcp"}


def refusal_of(folder: Path, kind: str) -> str | None:
    """What `load` says of a settings file of this kind, or `None` when it takes it."""
    path = folder / f"{kind}.toml"
    path.write_text(settings_text(folder, kind=kind), encoding="utf-8")
    try:
        settings_module().load(path)
    except settings_module().SettingsError as wrong:
        return str(wrong)
    return None


def test_install_command_is_a_public_name_of_the_settings_module() -> None:
    module = settings_module()
    assert "install_command" in module.__all__
    assert callable(module.install_command)


def test_the_core_s_own_kind_needs_nothing_installed() -> None:
    assert settings_module().install_command("rollout") is None


@pytest.mark.parametrize("kind", sorted(EXTRAS))
def test_this_release_publishes_no_extra_so_no_kind_gets_a_command(tmp_path: Path, kind: str) -> None:
    said = refusal_of(tmp_path, kind)
    assert said is not None and "only the rollout way in" in said, f"the way in for {kind} is installed here: {said}"
    assert settings_module().install_command(kind) is None


@pytest.mark.parametrize("kind", sorted(EXTRAS))
def test_load_s_refusal_names_no_command(tmp_path: Path, kind: str) -> None:
    """One answer in two places: `install_command` hands back none, and `load` names none."""
    said = refusal_of(tmp_path, kind)
    assert said is not None
    assert "pip" not in said and "poisson-break[" not in said, said


@pytest.mark.parametrize("kind", sorted(EXTRAS))
def test_a_version_that_publishes_the_extra_gets_pip_install_of_it(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The table stays for the version that ships the extra: once it is published, the line is `pip install` of it."""
    module = settings_module()
    monkeypatch.setattr(module, "_PUBLISHED_EXTRAS", frozenset(EXTRAS.values()))
    line = module.install_command(kind)
    assert isinstance(line, str) and "\n" not in line
    assert shlex.split(line) == ["pip", "install", f"poisson-break[{EXTRAS[kind]}]"]


def test_asking_imports_nothing() -> None:
    before = set(sys.modules)
    for kind in (*EXTRAS, "rollout"):
        settings_module().install_command(kind)
    assert {name for name in set(sys.modules) - before if name.startswith("poisson_break")} == set()


FINDER = '''
import importlib.abc, importlib.machinery, importlib.util, sys

class Installed(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Finds every module of the package that is not there, as an installed extra is found."""
    def find_spec(self, name, path=None, target=None):
        if not name.startswith("poisson_break."):
            return None
        if importlib.machinery.PathFinder.find_spec(name, path) is not None:
            return None
        return importlib.util.spec_from_loader(name, self, is_package=True)
    def create_module(self, spec):
        return None
    def exec_module(self, module):
        module.__path__ = []

sys.meta_path.insert(0, Installed())
'''


def test_a_kind_whose_way_in_is_installed_needs_no_command(tmp_path: Path) -> None:
    """With every way in found: `None` for each kind, and `load` takes a file of each kind, so the two agree."""
    for kind in EXTRAS:
        (tmp_path / f"{kind}.toml").write_text(settings_text(tmp_path, kind=kind), encoding="utf-8")
    code = FINDER + (
        "import json\n"
        "from poisson_break.settings import install_command, load\n"
        f"kinds = {sorted(EXTRAS)!r}\n"
        "said = {}\n"
        "for kind in kinds:\n"
        "    try:\n"
        "        load(kind + '.toml')\n"
        "        took = True\n"
        "    except Exception as wrong:\n"
        "        took = str(wrong)\n"
        "    said[kind] = [install_command(kind), took]\n"
        "print('SAID=' + json.dumps(said))\n")
    ran = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=60,
                         env={"PYTHONPATH": f"{REPO / 'src'}:{REPO}", "PATH": "/usr/bin:/bin",
                              "PYTHONDONTWRITEBYTECODE": "1"})
    lines = [line for line in ran.stdout.splitlines() if line.startswith("SAID=")]
    assert lines, ran.stdout + ran.stderr
    said = json.loads(lines[0][len("SAID="):])
    assert said == {kind: [None, True] for kind in sorted(EXTRAS)}, said
