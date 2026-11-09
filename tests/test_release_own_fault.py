"""A fault of the user's own is named in `[vary] tools`, hunted and confirmed.

Taylor's ruling (2026-11-09, `evidence/bk11/open-points.md` 11A-22): reading the settings takes a tool fault's name
the catalogue lacks and leaves it to the load step. When `doctor` or `hunt` has imported the target, whose module
registers the fault (spec §11.1), a name still unknown is refused there, before any run, naming it. Reading still
imports no target (BK4.6). And the release carries the example: `init --example own-fault`, offline, with no key,
found and confirmed, a confirmed finding naming the user's fault.

- Reading takes a name the catalogue lacks, and still refuses an entry that could be no fault's name.
- `doctor` is `not ready` for a name no module registered, and its sentence names it; `hunt`, and its dry run,
  refuse it before any run and make no hunt.
- With the module that registers it as the target, `doctor` is ready and the hunt's candidates carry the fault.
- The example: written by `init --example own-fault`; ready, found, confirmed, no connection attempted; a fault
  named in its `[vary] tools` is none of the catalogue's own, and a confirmed finding's condition names it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.commands_own_fault import NAME
from tests.commands_support import (
    CODES,
    cases,
    cli,
    errors,
    hunt_names,
    json_document,
    project,
    verdict,
)
from tests.conftest import run_python
from tests.settings_support import doc, settings, written
from tests.test_release_examples import Folder, examples, hunted_and_confirmed, json_of

EXAMPLE = "own-fault"
UNKNOWN = "shouting"


def built_in_faults() -> set[str]:
    """The tool faults of the catalogue as it stands with nothing registered, read in a process of its own."""
    ran = run_python("import json; from poisson_break.changes import CATALOG; "
                     "print(json.dumps([line.name for line in CATALOG if line.surface == 'tool']))")
    assert ran.exit == 0, ran.stderr
    names = set(json.loads(ran.stdout))
    assert "error" in names and len(names) >= 10, names
    return names


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------


def test_reading_takes_a_tool_fault_the_catalogue_lacks() -> None:
    assert UNKNOWN not in built_in_faults() and NAME not in built_in_faults()
    assert written(doc(vary=f'tools = ["error", "{UNKNOWN}"]'))["vary"]["tools"] == ["error", UNKNOWN]


@pytest.mark.parametrize("entry", ["", "two words", "a=b", "a+b", "a#1", "tool:error"])
def test_reading_still_refuses_an_entry_that_could_be_no_fault_s_name(entry: str) -> None:
    module = settings()
    with pytest.raises(module.SettingsError) as refused:
        module.loads(doc(vary=f'tools = ["{entry}"]'))
    assert refused.value.key == "vary.tools"


def test_reading_imports_no_target_to_take_it() -> None:
    ran = run_python(
        "import sys\n"
        "from poisson_break.settings import loads\n"
        "loads('version = 1\\n[target]\\nkind = \"rollout\"\\nentry = \"tests.commands_own_fault:desk\"\\n"
        "cases = \"c\"\\n[tools]\\nt = \"read\"\\n[vary]\\ntools = [\"garbled\"]\\n')\n"
        "print('tests.commands_own_fault' in sys.modules)\n")
    assert ran.exit == 0, ran.stderr
    assert ran.stdout.strip() == "False"


# ---------------------------------------------------------------------------
# the load step
# ---------------------------------------------------------------------------


def test_doctor_is_not_ready_for_a_fault_nobody_registered_and_names_it(tmp_path: Path) -> None:
    proj = project(tmp_path, cases(3, weak_to=["error"]), vary={"tools": ["error", UNKNOWN]})
    ran = cli(proj, "doctor")
    assert ran.exit == CODES["check"], ran
    word, sentence = verdict(ran)
    assert word == "not ready" and UNKNOWN in sentence, ran
    document = json_document(cli(proj, "doctor", "--json"))
    assert document["verdict"] == "not ready" and UNKNOWN in document["sentence"], document
    assert proj.runs() == []


@pytest.mark.parametrize("words", [["hunt", "--yes"], ["hunt", "--dry-run"], ["hunt", "--yes", "--json"]],
                         ids=" ".join)
def test_hunt_refuses_a_fault_nobody_registered_before_any_run(tmp_path: Path, words: list[str]) -> None:
    proj = project(tmp_path, cases(3, weak_to=["error"]), vary={"tools": ["error", UNKNOWN]})
    ran = cli(proj, *words)
    assert ran.exit == CODES["refused"], ran
    assert ran.out == "", ran
    (line,) = errors(ran)
    assert UNKNOWN in line, ran
    assert proj.runs() == [] and hunt_names(proj) == []


def test_the_fault_is_taken_once_the_target_s_module_registers_it(tmp_path: Path) -> None:
    """The same settings with the fault's name, and a target whose module registers it: ready, and the hunt's
    candidates are the fault's own conditions."""
    proj = project(tmp_path, cases(3, weak_to=["error"]), entry="tests.commands_own_fault:desk",
                   vary={"tools": [NAME]})
    ready = cli(proj, "doctor")
    assert ready.exit == CODES["done"] and verdict(ready)[0] == "ready", ready
    ran = cli(proj, "hunt", "--yes", "--json")
    assert ran.exit == CODES["done"], ran
    document = json_document(ran)
    assert document["verdict"] == "found", document
    conditions = [candidate["condition"] for candidate in document["candidates"]]
    assert conditions and all(condition.endswith(f"={NAME}") for condition in conditions), conditions


# ---------------------------------------------------------------------------
# the example
# ---------------------------------------------------------------------------


def test_the_own_fault_example_is_there() -> None:
    assert EXAMPLE in examples(), sorted(examples())


def test_the_own_fault_example_confirms_a_finding_that_names_the_user_s_fault(tmp_path: Path) -> None:
    folder = Folder(tmp_path)
    hunted_and_confirmed(folder, EXAMPLE)
    own = [fault for fault in folder.settings()["vary"]["tools"] if fault not in built_in_faults()]
    assert own, "the example's [vary] tools names no fault of its own"
    listed = json_of(folder.run("findings", "--json"))
    conditions = [finding["condition"] for finding in listed["findings"]]
    assert conditions
    named = [c for c in conditions if any(f"={fault}" in c for fault in own)]
    assert named, {"findings": conditions, "the user's faults": own}
    assert folder.attempts() == []
