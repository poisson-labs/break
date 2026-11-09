"""Hunts in a project folder, made through the library as the verbs leave them, for the BK8 follow-up's command tests,
and an audit hook for the command's child that names who opened what.

Each builder takes a fresh folder and hands back the project. Every run costs $0.001 where the builder says priced
(1,000 input tokens at $1 a million), so a dollar cap stops a stage after a known number of runs.

`opening_audit(pattern)` is a `sitecustomize` body for `commands_spies.spying`: for every `open`, `os.listdir` and
`os.scandir` of a path matching `pattern`, it walks the stack to the nearest frame of the package and logs that module,
`library` true for one of the library's own modules. Prove's store reads a run's `manifest.json` through Python's
`open` before it counts or reads the run, so any read of the store from the command's frames is seen; a bare `stat` is
not an audit event.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from tests.commands_support import MIXED, MIXED_CANDIDATES, MIXED_SETTINGS, Project, cases, opened, prepared, project
from tests.conftest import REPO

PRICES = {"input_per_million": 1.0, "output_per_million": 1.0}
PRICED = [{**case, "tokens": [1000, 0]} for case in MIXED]
LIBRARY = ("look", "_pretty", "settings", "hunt", "search", "confirm", "changes", "checks", "apply", "records",
           "interfaces")


def _confirm(proj: Project) -> Any:
    from poisson_break.confirm import confirm

    with contextlib.chdir(proj.folder):
        return confirm(opened(proj, "desk-1"))


def _set_cap(proj: Project, dollars: float) -> None:
    text = proj.settings.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.startswith('"dollars" = ')]
    assert len(lines) == 1, text
    proj.settings.write_text(text.replace(lines[0], f'"dollars" = {dollars!r}'), encoding="utf-8")


def fresh(folder: Path) -> Project:
    """The control run and `MIXED`'s three candidates written; no confirm stage."""
    proj = project(folder, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    return proj


def finished(folder: Path) -> Project:
    """Confirm stage 1 finished: candidate 1 confirmed (finding 1), 2 too small to tell, 3 not confirmed with the note
    `failed less`; 11 cases (k9 set aside), 4 repeats; the reference arm of finding 1 run."""
    proj = fresh(folder)
    _confirm(proj)
    return proj


def stopped_confirm(folder: Path) -> Project:
    """Priced; confirm stage 1 stopped by a cap of $0.0375 after one run of its control arm (the control's 36 runs
    spend $0.036)."""
    from poisson_break.hunt import HuntStopped

    proj = project(folder, PRICED, confirm={"repeats": 4}, search={"control_repeats": 3, "runs": 400},
                   limits={"dollars": 0.0375, **PRICES})
    prepared(proj, MIXED_CANDIDATES)
    try:
        _confirm(proj)
    except HuntStopped:
        return proj
    raise AssertionError("the confirm stage was not stopped")


def stopped_recheck(folder: Path) -> Project:
    """Priced; confirmed under a cap of $100 (finding 1), then the cap lowered to five runs past what is spent and a
    recheck begun through the library, which the cap stops part way."""
    from poisson_break.confirm import recheck
    from poisson_break.hunt import HuntStopped

    proj = project(folder, PRICED, confirm={"repeats": 4}, search={"control_repeats": 3, "runs": 400},
                   limits={"dollars": 100.0, **PRICES})
    prepared(proj, MIXED_CANDIDATES)
    _confirm(proj)
    spent = sum(stored_counts(proj).values())
    _set_cap(proj, (spent + 5) * 0.001)
    try:
        with contextlib.chdir(proj.folder):
            recheck(opened(proj, "desk-1"))
    except HuntStopped:
        return proj
    raise AssertionError("the recheck was not stopped")


def stopped_control(folder: Path) -> Project:
    """Priced; a hunt opened and its control stopped by a cap of $0.0015 after one run, through the library, and one
    candidate written, so `confirm` gets as far as asking about the control."""
    from poisson_break.changes import parse
    from poisson_break.confirm import write_candidates
    from poisson_break.hunt import HuntStopped, control, load_target, open_hunt
    from poisson_break.settings import load, read_cases

    proj = project(folder, cases(3, weak_to=["error"], tokens=[1000, 0]), limits={"dollars": 0.0015, **PRICES})
    with contextlib.chdir(proj.folder):
        settings = load(proj.settings)
        made = open_hunt(settings, target=load_target(settings), cases=read_cases(Path(settings.target.cases)),
                         name="desk-1")
        try:
            control(made)
        except HuntStopped:
            write_candidates(made, [parse("tool:lookup_order#1=error")])
            return proj
    raise AssertionError("the control was not stopped")


def stored_counts(proj: Project, name: str = "desk-1") -> dict[str, int]:
    """Every arm of the hunt's store, by its word, with Prove's count of its rows."""
    from poisson_prove.store import Store

    path = proj.hunt(name) / "store"
    if not path.exists():
        return {}
    store = Store(path)
    return {run[len(name) + 1:]: store.count(run) for run in store.runs()}


def opening_audit(pattern: str) -> str:
    """A `sitecustomize` body logging every opening of a path that matches the regular expression `pattern`."""
    source = REPO / "src" / "poisson_break"
    return f'''
import os as _aos
import re as _are
import sys as _asys

_SOURCE = {str(source)!r}
_LIBRARY = {list(LIBRARY)!r}
_WATCHED = _are.compile({pattern!r})
_busy = [False]


def _audit(event, args):
    if _busy[0] or event not in ("open", "os.listdir", "os.scandir") or not args:
        return
    try:
        path = _aos.fsdecode(args[0])
    except TypeError:
        return
    if not _WATCHED.search(path):
        return
    frame, who = _asys._getframe(1), None
    while frame is not None:
        name = frame.f_code.co_filename
        if name.startswith(_SOURCE + _aos.sep):
            who = _aos.path.relpath(name, _SOURCE).split(_aos.sep)[0].removesuffix(".py")
            break
        frame = frame.f_back
    if who is None:
        return
    _busy[0] = True
    try:
        _log(name="opened", by=who, path=path, event=event, library=who in _LIBRARY)
    finally:
        _busy[0] = False


_asys.addaudithook(_audit)
'''


__all__ = ["LIBRARY", "PRICED", "PRICES", "finished", "fresh", "opening_audit", "stopped_confirm", "stopped_control",
           "stopped_recheck", "stored_counts"]
