"""`poisson-break` and `python -m poisson_break` are the same command, also for an agent that
lives in the folder the command runs in.

Spec §9.1: "`python -m poisson_break` is the same command." What the README's first screen runs
is the installed `poisson-break` (BK11.1): `init` names an agent in the folder (`--entry
desk_agent:agent`), and `hunt` and `confirm` then load it. `python -m` puts the folder it runs in
first on the import path; the installed script is a program in the environment's `bin` and does
not, so the two load different agents, or one loads none: on main, `init` (which puts the folder on
the path itself, to find the agent's tools) writes the settings, and the installed
`poisson-break doctor` then refuses the agent it was just told, while `python -m poisson_break
doctor` is ready. Held here: in a folder holding the agent, its settings and its cases, both
forms of `doctor` and of `hunt --dry-run` print the same result and exit alike, and `doctor` is
ready.

The tests' own way of running the command (`tests/commands_support.cli`) is `python -m`, which is
why no test of the commands met this.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.commands_support import CODES
from tests.conftest import run_command, run_module

AGENT = '''
from poisson_prove import Episode

from poisson_break.apply import wrap


def _lookup_order(order):
    return f"Order {order} shipped on Tuesday."


lookup_order = wrap("lookup_order", _lookup_order)


def agent(cfg, seed):
    lookup_order("4821")
    return Episode(outcome="resolved", t=1.0, horizon=1.0)
'''

SETTINGS = '''version = 1

[target]
kind = "rollout"
entry = "folder_agent:agent"
cases = "cases.jsonl"

[tools]
lookup_order = "read"

[vary]
tools = ["error"]
inputs = []
max_call = 1

[search]
runs = 20
control_repeats = 1
cases_per_condition = 2
'''


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    here = tmp_path / "project"
    here.mkdir()
    (here / "folder_agent.py").write_text(AGENT, encoding="utf-8")
    (here / "break.toml").write_text(SETTINGS, encoding="utf-8")
    (here / "cases.jsonl").write_text('{"id": "1", "input": "Where is order 4821?"}\n'
                                      '{"id": "2", "input": "Where is order 4822?"}\n',
                                      encoding="utf-8")
    return here


@pytest.mark.parametrize("words", [["--plain", "doctor"], ["--plain", "hunt", "--dry-run"]],
                         ids=["doctor", "hunt --dry-run"])
def test_the_installed_command_loads_the_agent_in_its_folder_as_python_m_does(
        words: list[str], folder: Path) -> None:
    by_module = run_module(words, cwd=folder)
    by_script = run_command(words, cwd=folder)
    assert by_module.exit == CODES["done"], by_module
    assert (by_script.exit, by_script.stdout, by_script.stderr) == \
        (by_module.exit, by_module.stdout, by_module.stderr)


def test_doctor_is_ready_for_the_agent_init_was_given(folder: Path) -> None:
    """`init` takes an agent in the folder; the `doctor` it names next must load the same one."""
    (folder / "break.toml").unlink()
    made = run_command(["--plain", "init", "--yes", "--kind", "rollout", "--entry",
                        "folder_agent:agent", "--cases", "cases.jsonl", "--tool",
                        'lookup_order = "read"'], cwd=folder)
    assert made.exit == CODES["done"], made
    ran = run_command(["--plain", "doctor"], cwd=folder)
    assert ran.exit == CODES["done"], ran
    assert ran.stdout.startswith("ready  "), ran
