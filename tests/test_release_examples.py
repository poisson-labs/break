"""The examples: one small agent per way in that exists, each run offline against a scripted
model with no key.

Invariant held here (Break — Plan, the release pass):
- BK11.2  The examples are in the wheel or fetched by a documented command, and run with no key.

From the plan's "Builds": `examples/` with a small agent per way in, which runs offline against
a scripted model. **An example** is a folder directly under `examples/` holding a `break.toml`,
its cases and its agent, so a hunt can be run in it as it stands; its way in is the file's
`[target] kind`. **A way in that exists** is one of spec §7.1's six kinds whose way in this Break
has: `settings.install_command(kind)` is `None` for it (the core's `rollout`, and an adapter or
the proxy only once its module is installed).

Held here: every way in that exists has an example, and no example is for a way in that does
not; and each example, copied to a folder outside the checkout, is `ready` under the installed
`doctor`, and `hunt` and (when the hunt found something) `confirm` run to their verdicts, with the
network guard on and no variable in the environment whose name says key, token, secret or
password; no connection is attempted, not even one the agent catches; and no run of the control
crashed, so the agent runs and is not an agent that falls over on every case. With no key and no
network, the model the agent calls can only be a scripted one.

Whether the examples ride in the wheel or are fetched by a documented command is not settled by
the spec or the plan: it is owed as a ruling, and its test is written once it is ruled.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from tests.commands_support import CODES, results
from tests.conftest import REPO, Ran, console_script, guarded_env

PROBE = REPO / "tests" / "release_probe"

EXAMPLES = REPO / "examples"
#: Spec §7.1's six kinds of target.
KINDS = ("rollout", "openai-agents", "langgraph", "crewai", "mcp", "command")


def examples() -> dict[str, str]:
    """Each example folder's name with its way in."""
    found = {}
    if EXAMPLES.exists():
        for folder in sorted(p for p in EXAMPLES.iterdir() if p.is_dir()):
            settings = folder / "break.toml"
            if settings.is_file():
                with settings.open("rb") as f:
                    found[folder.name] = tomllib.load(f)["target"]["kind"]
    return found


def verdict(ran: Ran) -> str:
    """The verdict word of the last result on stdout: a verb that asks first prints its plan,
    then its result."""
    found = results(ran.stdout)
    assert found, ran
    return found[-1][0].split("  ", 1)[0]


def run(words: list[str], folder: Path, network: Path) -> Ran:
    """The installed `poisson-break WORDS` in `folder`, under the guard, with each connection
    attempted written to `network`."""
    env = guarded_env()
    env["PYTHONPATH"] = str(PROBE)
    env["BREAK_TEST_NETWORK_LOG"] = str(network)
    env["HOME"] = str(folder.parent)
    done = subprocess.run([str(console_script()), *words], cwd=folder, env=env,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
    return Ran(done.returncode, done.stdout, done.stderr)


def ways_in() -> list[str]:
    from poisson_break.settings import install_command

    return [kind for kind in KINDS if install_command(kind) is None]


def test_every_way_in_that_exists_has_an_example_and_no_other_does() -> None:
    assert "rollout" in ways_in(), "the core's own way in is always there"
    kinds = set(examples().values())
    assert set(ways_in()) <= kinds, {"missing": sorted(set(ways_in()) - kinds)}
    assert kinds <= set(ways_in()), {"for a way in this Break lacks": sorted(kinds - set(ways_in()))}


@pytest.mark.parametrize("name", sorted(examples()) or ["(no example)"])
def test_each_example_runs_offline_with_no_key(name: str, tmp_path: Path) -> None:
    assert name in examples(), "no example under examples/"
    folder = tmp_path / name
    shutil.copytree(EXAMPLES / name, folder, ignore=shutil.ignore_patterns("__pycache__", "break-runs"))

    network = tmp_path / "network.log"

    ran = run(["--plain", "doctor"], folder, network)
    assert ran.exit == CODES["done"], ran
    assert verdict(ran) == "ready", ran

    ran = run(["--plain", "hunt", "--yes"], folder, network)
    assert ran.exit == CODES["done"], ran
    found = verdict(ran)
    assert found in ("found", "nothing found"), ran

    listed = run(["findings", "--json"], folder, network)
    assert listed.exit == CODES["done"], listed
    crashed = [c["case"] for c in json.loads(listed.stdout)["control"] if "crashed" in c["kinds"]]
    assert crashed == [], "the agent falls over with no change on these cases"

    if found == "found":
        ran = run(["--plain", "confirm", "--yes"], folder, network)
        assert ran.exit == CODES["done"], ran
        assert verdict(ran) in ("confirmed", "nothing confirmed"), ran
    attempts = network.read_text(encoding="utf-8").splitlines() if network.exists() else []
    assert attempts == []
