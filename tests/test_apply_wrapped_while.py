"""`poisson_break.apply.wrapped_while`: the tools a module wraps while it is imported.

Taylor's yes to BK8 point 2 (2026-11-07): `init` never runs the agent, and the core's one kind, `rollout`, has its tools
wrapped inside the user's code with `wrap`, so the applying module records the name of each tool wrapped while a module
is imported, through one new public name, `wrapped_while(import_path) -> tuple[str, ...]`, and `init` lists exactly
those (BK8.5). A target that wraps its tools inside its own body has none listed. BK8's Session B adds the name before
the commands (plan §2, rule 10); this file holds what it hands back.

Each case runs in a child process, so a module is imported for the first time there, as `init` imports it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def wrapped(folder: Path, module: str) -> tuple[list[str] | None, str]:
    """What `wrapped_while(module)` hands back in a fresh child whose import path holds `folder`, and anything the
    child printed or raised."""
    code = ("import json, sys\n"
            "from poisson_break.apply import wrapped_while\n"
            f"found = wrapped_while({module!r})\n"
            "assert isinstance(found, tuple), type(found)\n"
            "print('FOUND=' + json.dumps(list(found)))\n")
    ran = subprocess.run([sys.executable, "-c", code], cwd=folder, capture_output=True, text=True, timeout=60,
                         env={"PYTHONPATH": f"{folder}:{REPO / 'src'}:{REPO}", "PATH": "/usr/bin:/bin",
                              "PYTHONDONTWRITEBYTECODE": "1"})
    lines = [line for line in ran.stdout.splitlines() if line.startswith("FOUND=")]
    return (json.loads(lines[0][len("FOUND="):]) if lines else None), ran.stdout + ran.stderr


def module(folder: Path, name: str, body: str) -> None:
    (folder / f"{name}.py").write_text(body, encoding="utf-8")


def test_wrapped_while_is_a_public_name_of_apply() -> None:
    import poisson_break.apply as apply

    assert "wrapped_while" in apply.__all__
    assert callable(apply.wrapped_while)


def test_the_tools_wrapped_on_import_in_the_order_wrapped(tmp_path: Path) -> None:
    module(tmp_path, "desk_a", "from poisson_break.apply import wrap\n"
                               "def _f(q): return q\n"
                               "lookup_order = wrap('lookup_order', _f)\n"
                               "check_policy = wrap('check_policy', _f)\n"
                               "issue_refund = wrap('issue_refund', _f)\n"
                               "def agent(cfg, seed): return None\n")
    found, said = wrapped(tmp_path, "desk_a")
    assert found == ["lookup_order", "check_policy", "issue_refund"], said


def test_the_scripted_targets_module_wraps_its_two_tools(tmp_path: Path) -> None:
    """The commands' own targets (`tests/commands_targets.py`) wrap `lookup_order` and `check_policy` on import."""
    found, said = wrapped(tmp_path, "tests.commands_targets")
    assert found == ["lookup_order", "check_policy"], said


def test_tools_wrapped_inside_the_agent_s_body_are_not_listed(tmp_path: Path) -> None:
    module(tmp_path, "desk_b", "from poisson_break.apply import wrap\n"
                               "def _f(q): return q\n"
                               "def agent(cfg, seed):\n"
                               "    lookup = wrap('lookup_order', _f)\n"
                               "    return lookup('1')\n")
    found, said = wrapped(tmp_path, "desk_b")
    assert found == [], said


def test_importing_runs_no_agent_and_calls_no_tool(tmp_path: Path) -> None:
    """Only the import runs: the tool wrapped is never called, and the agent never run."""
    module(tmp_path, "desk_c", "from poisson_break.apply import wrap\n"
                               "def _f(q): raise SystemExit('a tool was called')\n"
                               "lookup_order = wrap('lookup_order', _f)\n"
                               "def agent(cfg, seed): raise SystemExit('the agent was run')\n")
    found, said = wrapped(tmp_path, "desk_c")
    assert found == ["lookup_order"], said
    assert "was called" not in said and "was run" not in said


def test_a_tool_wrapped_twice_under_one_name_is_listed_once(tmp_path: Path) -> None:
    module(tmp_path, "desk_d", "from poisson_break.apply import wrap\n"
                               "def _f(q): return q\n"
                               "a = wrap('lookup_order', _f)\n"
                               "b = wrap('lookup_order', _f)\n"
                               "c = wrap('check_policy', _f)\n")
    found, said = wrapped(tmp_path, "desk_d")
    assert found == ["lookup_order", "check_policy"], said


def test_tools_wrapped_by_a_module_it_imports_are_listed(tmp_path: Path) -> None:
    """While the module is imported: what its own imports wrap is wrapped then too."""
    module(tmp_path, "tools_e", "from poisson_break.apply import wrap\n"
                                "def _f(q): return q\n"
                                "lookup_order = wrap('lookup_order', _f)\n")
    module(tmp_path, "desk_e", "from tools_e import lookup_order\n"
                               "def agent(cfg, seed): return None\n")
    found, said = wrapped(tmp_path, "desk_e")
    assert found == ["lookup_order"], said


@pytest.mark.parametrize("missing", ["no_such_module_here", "tests.no_such_module_here"])
def test_a_module_that_cannot_be_imported_raises(tmp_path: Path, missing: str) -> None:
    found, said = wrapped(tmp_path, missing)
    assert found is None
    assert "Traceback" in said
    assert "ModuleNotFoundError" in said and missing.rsplit(".", 1)[-1] in said, said
