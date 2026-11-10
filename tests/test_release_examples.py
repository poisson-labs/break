"""The examples: small agents with scripted models, each written out by `init --example NAME`, each
run offline from the installed command with no key, each finding and confirming something.

Invariant held here (Break — Plan, the release pass):
- BK11.2  The examples are in the wheel or fetched by a documented command, and run with no key.

Taylor's rulings (2026-11-09, `evidence/bk11/open-points.md`): 11A-2, the examples ride in the
wheel and `init --example NAME` writes one into the folder (its own tests are in
`test_release_init_example.py`); 11A-3, each example's hunt is `found` and its `confirm` is
`confirmed`. And five more examples in the release, each offline with no key against a scripted
model, written out the same way, each finding and confirming something. Three of the five are
held here; the other two cannot be built on this core as it stands and are owed as open points,
with no test (11A-21: the conversation moves need a way in that can play turns, and `rollout`
cannot; 11A-22: a fault of the user's own cannot be named in `[vary] tools`, which is checked
against the catalogue before the module that registers the fault is imported).

| Example | `init --example` | Ends as |
|---|---|---|
| the help desk, the README's first screen | `desk` | found, confirmed |
| the full loop | `full-loop` | found, confirmed; the fix put in; `recheck --check` passes and every finding reads `fails less` |
| a write tool with its stand-in | `stand-in` | found, confirmed; the write tool is routed through Break and its real function never runs |
| the user's own check | `own-check` | found, confirmed; a confirmed finding's kinds hold the check's `own:<word>` |

**An example** is a folder directly under `examples/` holding `break.toml`, its cases and its
agent; its `init --example` word is the folder's name; its way in is `[target] kind`. **A way in
that exists** is one of spec §7.1's six kinds whose way in this Break has (`install_command` is
`None`). **The full loop's fix** (definition D6, `evidence/bk11/open-points.md`): the folder holds,
beside the agent's module `<module>.py` (the module `[target] entry` names), `<module>_fixed.py`,
the agent as fixed, and the fix is copying it over `<module>.py`.

Every example, in an empty folder outside the checkout: `init --example NAME` writes it; the
installed `doctor` is ready; `hunt --yes` is `found`; no control run crashed; `confirm --yes` is
`confirmed`; the network guard is on, no variable in the environment says key, token, secret or
password, and no connection is attempted, not even one the agent catches. With no key and no
network, the model the agent calls can only be a scripted one.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest

from tests.commands_support import CODES, results
from tests.conftest import REPO, Ran, console_script, guarded_env

EXAMPLES = REPO / "examples"
PROBE = REPO / "tests" / "release_probe"
#: Spec §7.1's six kinds of target.
KINDS = ("rollout", "openai-agents", "langgraph", "crewai", "mcp", "command")
#: The examples the rulings name that this core can carry, by their `init --example` word.
NAMED = ("desk", "full-loop", "stand-in", "own-check")


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


def ways_in() -> list[str]:
    from poisson_break.settings import install_command

    return [kind for kind in KINDS if install_command(kind) is None]


class Folder:
    """An empty folder outside the checkout, the installed command run in it under the probe."""

    def __init__(self, tmp_path: Path) -> None:
        self.path = tmp_path / "project"
        self.path.mkdir()
        self.network = tmp_path / "network.log"
        self.tools = tmp_path / "tools.log"
        self.home = tmp_path / "home"
        self.home.mkdir()

    def run(self, *words: str) -> Ran:
        env = guarded_env()
        env["PYTHONPATH"] = str(PROBE)
        env["BREAK_TEST_NETWORK_LOG"] = str(self.network)
        env["BREAK_TEST_TOOL_LOG"] = str(self.tools)
        env["HOME"] = str(self.home)
        done = subprocess.run([str(console_script()), *words], cwd=self.path, env=env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
        return Ran(done.returncode, done.stdout, done.stderr)

    def attempts(self) -> list[str]:
        return self.network.read_text(encoding="utf-8").splitlines() if self.network.exists() else []

    def tool_log(self) -> list[dict[str, str]]:
        if not self.tools.exists():
            return []
        return [json.loads(line) for line in self.tools.read_text(encoding="utf-8").splitlines() if line]

    def settings(self) -> dict[str, Any]:
        with (self.path / "break.toml").open("rb") as f:
            return tomllib.load(f)


def verdict(ran: Ran) -> str:
    """The verdict word of the last result on stdout: a verb that asks first prints its plan,
    then its result."""
    found = results(ran.stdout)
    assert found, ran
    return found[-1][0].split("  ", 1)[0]


def json_of(ran: Ran) -> dict[str, Any]:
    assert ran.stdout.strip(), ran
    document: dict[str, Any] = json.loads(ran.stdout)
    return document


def hunted_and_confirmed(folder: Folder, name: str) -> None:
    """`init --example NAME`, `doctor`, `hunt`, the control's crashes, `confirm`, as every example
    is held."""
    ran = folder.run("--plain", "init", "--example", name)
    assert ran.exit == CODES["done"], ran
    assert (folder.path / "break.toml").is_file()

    ran = folder.run("--plain", "doctor")
    assert ran.exit == CODES["done"], ran
    assert verdict(ran) == "ready", ran

    ran = folder.run("--plain", "hunt", "--yes")
    assert ran.exit == CODES["done"], ran
    assert verdict(ran) == "found", ran

    listed = folder.run("findings", "--json")
    assert listed.exit == CODES["done"], listed
    crashed = [c["case"] for c in json_of(listed)["control"] if "crashed" in c["kinds"]]
    assert crashed == [], "the agent falls over with no change on these cases"

    ran = folder.run("--plain", "confirm", "--yes")
    assert ran.exit == CODES["done"], ran
    assert verdict(ran) == "confirmed", ran


# ---------------------------------------------------------------------------
# which examples there are
# ---------------------------------------------------------------------------


def test_every_way_in_that_exists_has_an_example_and_no_other_does() -> None:
    assert "rollout" in ways_in(), "the core's own way in is always there"
    kinds = set(examples().values())
    assert set(ways_in()) <= kinds, {"missing": sorted(set(ways_in()) - kinds)}
    assert kinds <= set(ways_in()), {"for a way in this Break lacks": sorted(kinds - set(ways_in()))}


def test_the_examples_the_rulings_name_are_there() -> None:
    assert set(NAMED) <= set(examples()), sorted(set(NAMED) - set(examples()))


# ---------------------------------------------------------------------------
# each example runs, finds and confirms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(examples()) or ["(no example)"])
def test_each_example_finds_and_confirms_offline_with_no_key(name: str, tmp_path: Path) -> None:
    assert name in examples(), "no example under examples/"
    folder = Folder(tmp_path)
    hunted_and_confirmed(folder, name)
    assert folder.attempts() == []


def test_the_full_loop_reads_its_fix_as_holding(tmp_path: Path) -> None:
    """Hunt, confirm, the fix put in, then `recheck`: every finding fails less than it did, and
    `recheck --check` passes, from the installed command, offline, with no key."""
    folder = Folder(tmp_path)
    hunted_and_confirmed(folder, "full-loop")
    module = folder.settings()["target"]["entry"].split(":", 1)[0]
    assert "." not in module, "the agent's module is a file in the folder"
    fixed = folder.path / f"{module}_fixed.py"
    assert fixed.is_file(), f"init --example full-loop wrote no {fixed.name}"
    before = (folder.path / f"{module}.py").read_bytes()
    assert fixed.read_bytes() != before, "the fix changes nothing"
    shutil.copyfile(fixed, folder.path / f"{module}.py")

    ran = folder.run("recheck", "--yes", "--check", "--json")
    assert ran.exit == CODES["done"], ran
    document = json_of(ran)
    assert document["verdict"] == "rechecked" and document["passed"] is True, document
    phrases = [f["phrase"] for f in document["findings"]]
    assert phrases and set(phrases) == {"fails less"}, phrases
    assert folder.attempts() == []


def test_the_stand_in_example_never_runs_the_real_write_tool(tmp_path: Path) -> None:
    """The write tool is classed `write` with a stand-in; Break routes the agent's calls of it in
    every stage, and the tool's own function never runs: not in the control, the search, the
    shrink or the confirm stage."""
    folder = Folder(tmp_path)
    hunted_and_confirmed(folder, "stand-in")
    lines = folder.settings()["tools"]
    written = [tool for tool, line in lines.items()
               if isinstance(line, dict) and line.get("class") == "write" and line.get("stand_in")]
    assert written, f"no tool classed write with a stand-in: {lines}"
    log = folder.tool_log()
    for tool in written:
        assert {"routed": tool} in log, f"the agent never called {tool}"
        assert {"real": tool} not in log, f"the real {tool} ran"
    assert folder.attempts() == []


def test_the_own_check_example_confirms_a_finding_its_check_judged(tmp_path: Path) -> None:
    """The failure rule is the user's own, plugged in through `[fails] own`, and a confirmed
    finding rests on it: its kinds hold `own:<word>`, the word the check returned."""
    folder = Folder(tmp_path)
    hunted_and_confirmed(folder, "own-check")
    own = folder.settings().get("fails", {}).get("own")
    assert isinstance(own, str) and ":" in own, own
    listed = json_of(folder.run("findings", "--json"))
    numbers = [f["number"] for f in listed["findings"]]
    assert numbers
    kinds: set[str] = set()
    for number in numbers:
        finding = json_of(folder.run("findings", str(number), "--json"))["finding"]
        kinds |= set(finding["kinds"])
    assert any(kind.startswith("own:") for kind in kinds), kinds
    assert folder.attempts() == []
