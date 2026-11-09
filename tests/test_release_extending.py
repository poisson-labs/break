"""The extension-point pages match the code: each page's example implements its interface and
runs through Break.

Invariant held here (Break — Plan, the release pass; spec §11):
- BK11.6  The extension-point docs match the code: each interface page's example implements the
          protocol and is run by the docs job against the installed wheel.

An interface's page is the one page under `docs/` that names its version constant
(`FAULT_INTERFACE_VERSION`, `TARGET_INTERFACE_VERSION`, `STRATEGY_INTERFACE_VERSION`,
`CHECK_INTERFACE_VERSION`) and no other interface's; its example is its Python blocks, in order,
as one program (`tests/release_docs.py`, rule 6). The clean-install job runs that program against
the installed wheel; the listing that holds the job to it is held in
`tests/test_release_commands.py`. Here the program is run against this tree, in a fresh folder,
under the network guard and with no key, and it must exit 0 having had its implementation called
by Break itself, which is what spec §11 asks of every interface's test: an implementation written
outside the package runs end to end through the core.

- A fault: its `apply` is called by `poisson_break.changes` (`run_fault`), on an object that
  answers to `interfaces.Fault`.
- A way in: its `run` is called from a module of Break, on an object that answers to
  `interfaces.Target`.
- A strategy: its `propose` is called by `poisson_break.search`, on an object that answers to
  `interfaces.Strategy`.
- A check: a function of the example is called by `poisson_break.checks` with a `RunView`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import REPO, guarded_env
from tests.release_docs import INTERFACE_CONSTANTS, extension_pages, python_program, rel

PROBE = REPO / "tests" / "release_probe"


def run_example(constant: str, tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], list[dict[str, Any]]]:
    (page,) = extension_pages()[constant]
    program = python_program(page)
    assert program is not None, f"{rel(page)} has no Python block"
    folder = tmp_path / "example"
    folder.mkdir()
    path = folder / "example.py"
    path.write_text(program.command + "\n", encoding="utf-8")
    log = tmp_path / "calls.jsonl"
    env = guarded_env()
    env["PYTHONPATH"] = str(PROBE)
    env["HOME"] = str(tmp_path)
    env["BREAK_TEST_PROBE_LOG"] = str(log)
    env["BREAK_TEST_PROBE_PROGRAM"] = str(path)
    done = subprocess.run([sys.executable, "example.py"], cwd=folder, env=env,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600)
    calls = ([json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]
             if log.exists() else [])
    return done, calls


@pytest.mark.parametrize("constant", INTERFACE_CONSTANTS)
def test_each_interface_has_one_page_with_an_example(constant: str) -> None:
    pages = extension_pages()[constant]
    assert len(pages) == 1, [rel(p) for p in pages]
    assert python_program(pages[0]) is not None


WHAT = {
    "FAULT_INTERFACE_VERSION": ("apply", ("poisson_break.changes",), "Fault"),
    "TARGET_INTERFACE_VERSION": ("run", ("poisson_break.",), "Target"),
    "STRATEGY_INTERFACE_VERSION": ("propose", ("poisson_break.search",), "Strategy"),
}


@pytest.mark.parametrize("constant", sorted(WHAT))
def test_the_example_runs_and_break_calls_its_implementation(constant: str, tmp_path: Path) -> None:
    done, calls = run_example(constant, tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    method, callers, protocol = WHAT[constant]
    called = [c for c in calls if c["name"] == method and c["caller"].startswith(callers)
              and protocol in c["self"]]
    assert called, {"calls": calls[:20]}


def test_the_check_example_runs_and_break_judges_with_it(tmp_path: Path) -> None:
    done, calls = run_example("CHECK_INTERFACE_VERSION", tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    judged = [c for c in calls if c["caller"].startswith("poisson_break.checks")
              and c["args"][:1] == ["RunView"]]
    assert judged, {"calls": calls[:20]}


def test_the_probe_sees_a_call_from_break_and_not_one_from_the_example_itself(tmp_path: Path) -> None:
    """The probe the four tests above read is a real witness: an example that calls its own
    `apply` is not counted, and Break's `run_fault` calling it is."""
    folder = tmp_path / "example"
    folder.mkdir()
    path = folder / "example.py"
    path.write_text(
        "import random\n"
        "from poisson_break.changes import CallContext, Result, parse, run_fault\n"
        "class Echo:\n"
        "    name = 'echo'; surface = 'tool'; description = 'the real result'\n"
        "    parameters = {}; real_runs = True\n"
        "    def apply(self, call, *, real, params, rng):\n"
        "        return Result(value=real())\n"
        "fault = Echo()\n"
        "call = CallContext(tool='t', args={}, call=1, condition=parse('tool:t#1=timeout'), seed=1)\n"
        "fault.apply(call, real=lambda: 1, params={}, rng=random.Random(0))\n"
        "import sys\n"
        "if sys.argv[1:] == ['through']:\n"
        "    run_fault(fault, call, real=lambda: 1, params={}, rng=random.Random(0))\n",
        encoding="utf-8")
    log = tmp_path / "calls.jsonl"
    env = guarded_env()
    env.update(PYTHONPATH=str(PROBE), BREAK_TEST_PROBE_LOG=str(log),
               BREAK_TEST_PROBE_PROGRAM=str(path))
    for words, expected in (([], 0), (["through"], 1)):
        log.unlink(missing_ok=True)
        done = subprocess.run([sys.executable, "example.py", *words], cwd=folder, env=env,
                              capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stderr
        calls = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
        seen = [c for c in calls if c["name"] == "apply" and c["caller"] == "poisson_break.changes"
                and "Fault" in c["self"]]
        assert len(seen) == expected, calls
