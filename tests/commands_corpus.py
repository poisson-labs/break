"""The eight verbs' part of the look's conformance corpus (`tests/look_corpus.py`): each verb's help, each documented
example and the bad inputs, run every way the conformance test runs an invocation (plan BK8.1, BK12.11).

**Setups.** Each invocation runs in a folder of its own, which its setup fills once: a project as `init` leaves it, a
hunt with its candidates written, or one with a finding confirmed. The hunts are made once per process, through the
library and the pinned Trace, and copied into each folder that wants one, so the corpus pays for each kind once.

**Verbs that write.** A hunt, a recheck and `init` change the folder, and the conformance test runs one invocation many
ways in the same folder and compares what each printed. Their setups keep a copy in `pristine/`, and they run through
`tests/commands_child.py`, which puts the folder back from it before running the command.
"""

from __future__ import annotations

import contextlib
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tests.commands_support import (
    MIXED,
    MIXED_CANDIDATES,
    MIXED_SETTINGS,
    SOUND,
    WEAK_TO_ERROR,
    Project,
    opened,
    prepared,
    settings_text,
)

CHILD = Path(__file__).with_name("commands_child.py")
INIT = ("--kind", "rollout", "--entry", "tests.commands_targets:desk", "--cases", "cases.jsonl",
        "--tool", 'lookup_order = "read"', "--tool", 'check_policy = "read"')

_built: dict[str, Path] = {}


def _write(folder: Path, case_list: Any, **settings: Any) -> Project:
    import json

    folder.mkdir(parents=True, exist_ok=True)
    (folder / "break.toml").write_text(settings_text(**settings), encoding="utf-8")
    (folder / "cases.jsonl").write_text("".join(json.dumps(c) + "\n" for c in case_list), encoding="utf-8")
    return Project(folder=folder, home=folder / "home", runs_log=folder.parent / "runs.jsonl")


def _make(kind: str, folder: Path) -> None:
    if kind == "weak":
        _write(folder, WEAK_TO_ERROR)
    elif kind == "sound":
        _write(folder, SOUND)
    elif kind == "no-strategy":
        _write(folder, WEAK_TO_ERROR, search={"strategy": "tests.nowhere_at_all:Strategy"})
    elif kind == "cases-only":
        _write(folder, WEAK_TO_ERROR)
        (folder / "break.toml").unlink()
    elif kind in ("candidates", "confirmed"):
        proj = _write(folder, MIXED, **MIXED_SETTINGS)
        prepared(proj, MIXED_CANDIDATES)
        if kind == "confirmed":
            from poisson_break.confirm import confirm

            with contextlib.chdir(folder):
                confirm(opened(proj, "desk-1"))
    else:
        raise AssertionError(f"no setup named {kind}")


def _template(kind: str) -> Path:
    if kind not in _built:
        root = Path(tempfile.mkdtemp(prefix="commands-corpus-"))
        _make(kind, root / "project")
        _built[kind] = root / "project"
    return _built[kind]


def setup(kind: str, *, pristine: bool = False) -> Callable[[Path], None]:
    """Fill an invocation's folder with the project `kind` names; with `pristine`, keep a copy to restore from. The hunt
    folder's absolute path is the invocation's own, so every way of one invocation prints the same."""

    def fill(folder: Path) -> None:
        source = _template(kind)
        for path in source.iterdir():
            if path.is_dir():
                shutil.copytree(path, folder / path.name)
            else:
                shutil.copy2(path, folder / path.name)
        if kind in ("candidates", "confirmed"):
            _repoint(folder, source)
        if pristine:
            (folder / "pristine").mkdir()
            for path in folder.iterdir():
                if path.name in ("pristine", "home"):
                    continue
                if path.is_dir():
                    shutil.copytree(path, folder / "pristine" / path.name)
                else:
                    shutil.copy2(path, folder / "pristine" / path.name)

    return fill


def _repoint(folder: Path, source: Path) -> None:
    """A finding file names its hunt's store by its absolute path: the copy's own, as if it had been made here."""
    for toml in folder.glob("break-runs/*/findings/*.toml"):
        toml.write_text(toml.read_text(encoding="utf-8").replace(str(source), str(folder)), encoding="utf-8")


def writing() -> tuple[str, ...]:
    """The program for a verb that writes: the child that restores the folder first."""
    return (sys.executable, str(CHILD))
