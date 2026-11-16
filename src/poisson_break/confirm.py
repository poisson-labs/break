"""Confirming findings: the confirm stage, the findings it leaves, replaying one, and rechecking
a fix.

A hunt ends with **candidates**: conditions that failed more than the control in the few runs a
search gave them. A candidate is not a finding. ``write_candidates`` keeps a hunt's candidates,
best first, in its ``candidates.json``, and ``confirm`` tests them.

**The design is fixed before the first run.** One control arm, every case the control did not
set aside, each a number of times with no change; one arm for each candidate, the same cases the
same number of times under that candidate; all on seeds no earlier stage used. Every case is in
every arm, so no case is chosen for having failed, and the candidates share the one control arm.
``design`` works it out and runs nothing. ``confirm`` writes it to the hunt's ``confirm.json``
before the stage's first run, and a stage that stopped is taken up again under what was written,
whatever the settings say by then. ``read_stages`` reads the stages written, each a ``Stage``
with the rows the store holds of each of its arms, and runs nothing.

**Break computes none of the numbers.** The arms are Prove runs in the hunt's store. Each
candidate's arm is put to Trace once, against the control arm, as a command::

    python -m poisson_trace fix-check OLD NEW --store STORE --event failed --inputs all \\
        --max-mde X --json

run with the Python Break runs on, in the hunt's folder, and what is read is the JSON document
it prints: never its exit code. The difference, its interval, the p-value, the verdict, the
direction and the count of repeats that would decide are Trace's. The candidates are tested
together, so their p-values are adjusted together with Prove's ``bh``. A failure share is two of
Trace's counts, divided, and that is all the arithmetic here. ``ask_trace`` is the one place
Trace's test is asked for and its document read.

**The verdicts,** one for each candidate, in a ``Tested``: ``confirmed`` when Trace says
*different*, the candidate's arm failed more, and the adjusted p-value is at or under ``q``;
``too small to tell`` when Trace says so, with Trace's count of repeats; and ``not confirmed``
otherwise, with a note where there is something to say: ``failed less``, ``not after the
correction``, or ``nothing to compare`` when no case is left with an outcome in both arms.
``confirm(hunt, repeats=N)`` asks again about the candidates the latest stage called *too small
to tell*: a new stage with its own control arm, on new seeds, read on its own.
``finished_stage`` gives the latest stage's answer when nothing of it is left to run or write,
and runs nothing.

**A finding** is a confirmed candidate, numbered within the hunt from 1 in the order confirmed,
written to ``findings/<n>.toml`` and read back equal (``write_finding``, ``read_finding``). Each
gets a **reference arm**: the unchanged agent under the finding's condition, every case again,
on fresh seeds, run at the end of ``confirm``. A finding's file is written before its reference
arm runs, and ``reference`` runs whatever is missing of them.

``replay`` runs one finding once, on the case that failed most in its confirm arm and on a seed
it failed on, and stores nothing. ``recheck`` runs every finding on the agent as it is now, over
the cases and repeats of its reference arm, puts the reference arm and the new one to Trace, and
reads Trace's verdict and direction as one of four phrases: ``fails less``, ``fails more``,
``no significant difference``, ``too small to tell``. With ``old``, a second way in, the old and
the new agent are both run now and compared with each other.

**Trace is required, at one version.** Before any run of ``confirm`` or ``recheck``, Trace is
asked for its version, which must be ``TRACE_VERSION``, and then for a check of two runs of one
row each that Break writes in a temporary folder, whose document must carry the schema this
module reads. Trace missing, at another version or printing another schema is refused there,
with nothing run and nothing stored.

A refusal of this module's own is a ``ConfirmError``: one line, with ``reason``, one of
``REASONS``. All but ``trace answer`` are raised before any run; ``trace answer`` is a document
Break could not read after the arms ran, and the arms are kept. What the runs module raises
(``HuntStopped``, ``HuntError``) and Ctrl-C pass through as they are, with every finished run
stored: the same call again runs what is missing.
"""

from __future__ import annotations

import datetime
import json
import os
import shlex
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from poisson_prove import Episode
from poisson_prove.diff import bh
from poisson_prove.store import EpisodeRecord, RunManifest, Store

from poisson_break import records
from poisson_break.changes import ChangeError, Condition, parse
from poisson_break.changes import name as _name_of
from poisson_break.hunt import (
    ControlSummary,
    Hunt,
    HuntError,
    Target,
    _run_unstored,
    control,
    open_hunt,
    run_arm,
)
from poisson_break.settings import Settings, _key_text, _quoted, plan_confirm

__all__ = [
    "TRACE_VERSION",
    "ConfirmError",
    "write_candidates",
    "read_candidates",
    "design",
    "Design",
    "confirm",
    "finished_stage",
    "Confirmation",
    "read_stages",
    "Stage",
    "Tested",
    "Finding",
    "write_finding",
    "read_finding",
    "read_findings",
    "reference",
    "replay",
    "Replayed",
    "recheck",
    "Rechecked",
    "ask_trace",
]

TRACE_VERSION: Final = "0.1.0a1"
"""The one version of Trace this module reads: the version the pinned Trace declares."""

FIX_CHECK_SCHEMA: Final = "poisson-trace.fix-check/2"
"""The name of the document Trace's ``fix-check --json`` prints, as this module reads it."""

CANDIDATES_SCHEMA: Final = "poisson_break.candidates/1"
"""The name of the shape of ``candidates.json``; its first key."""

CONFIRM_SCHEMA: Final = "poisson_break.confirm/1"
"""The name of the shape of ``confirm.json``; its first key."""

FINDING_SCHEMA: Final = "poisson_break.finding/1"
"""The name of the shape of a finding's file; its first key."""

REASONS: Final = ("trace missing", "trace version", "trace schema", "trace answer",
                  "no candidates", "no control", "nothing to ask again", "unfinished",
                  "unknown finding")
"""Why this module refused, as ``ConfirmError.reason`` says it."""

VERDICTS: Final = ("confirmed", "not confirmed", "too small to tell")
"""What the confirm stage says of a candidate."""

NOTES: Final = ("failed less", "not after the correction", "nothing to compare")
"""What a candidate that is not confirmed may carry beside its verdict."""

PHRASES: Final = ("fails less", "fails more", "no significant difference", "too small to tell")
"""What a recheck says of a finding."""

_TRACE = "poisson_trace"
_TRACE_VERDICTS = ("different", "no significant difference", "too small to tell")
_TRACE_DIRECTIONS = ("failed less in new", "failed more in new", "no direction")
_DIFFERENT, _NOT_DIFFERENT, _TOO_SMALL = _TRACE_VERDICTS
_LESS, _MORE, _NO_DIRECTION = _TRACE_DIRECTIONS
_CANDIDATES_FILE = "candidates.json"
_CONFIRM_FILE = "confirm.json"
_FINDINGS_FOLDER = "findings"
_HUNT_FILE = "hunt.json"
_DAY = 86_400
_YOUR_CHECK = "your check"


# ---------------------------------------------------------------------------
# the refusal
# ---------------------------------------------------------------------------


class ConfirmError(ValueError):
    """This module's refusal: one plain line, and ``reason``, one of ``REASONS``.

    ``trace missing``, ``trace version`` and ``trace schema`` say Trace cannot be used as it
    is; ``no candidates`` and ``no control`` that there is nothing to confirm yet;
    ``nothing to ask again`` and ``unfinished`` that a stage cannot be begun now; and
    ``unknown finding`` that a finding is not there to be read. Each of those is raised before
    any run. ``trace answer`` is an answer from Trace that Break could not read, and can come
    after the arms ran, which are kept."""

    def __init__(self, message: str, *, reason: str) -> None:
        if reason not in REASONS:
            raise ValueError(f"a refusal's reason is one of {', '.join(REASONS)}, not {reason!r}")
        super().__init__(" ".join(str(message).split()))
        self.reason = reason


# ---------------------------------------------------------------------------
# what the module hands back
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Design:
    """A confirm stage before it runs: who is run on what, and what it costs.

    ``cases`` are the case ids every arm holds, and ``repeats`` how many times each. ``arms``
    is each arm's own word with its condition by name, the control arm first with no condition:
    ``("confirm-control", "")``, then ``("confirm-1", <name>)`` for the first candidate.
    ``confirm_runs`` is the stage's runs, ``reference_per_finding`` the runs of one finding's
    reference arm, ``reference_runs`` those of all of them were every candidate confirmed, and
    ``runs`` the sum: the counts ``plan_confirm`` gives. ``dollars`` and ``reference_dollars``
    price ``confirm_runs`` and ``reference_runs`` at what one control run cost, and are ``None``
    when the settings give no prices."""

    cases: tuple[str, ...]
    repeats: int
    arms: tuple[tuple[str, str], ...]
    confirm_runs: int
    reference_per_finding: int
    reference_runs: int
    runs: int
    dollars: float | None
    reference_dollars: float | None


@dataclass(frozen=True, kw_only=True)
class Tested:
    """One candidate, tested: a candidate, never a finding.

    ``number`` is the candidate's own, from 1 as written, ``condition`` its name, and ``arm``
    the Prove run it ran in. ``verdict`` is one of ``VERDICTS`` and ``note`` one of ``NOTES`` or
    ``None``. ``rate`` and ``control_rate`` are the failure shares of its arm and of the control
    arm over the cases Trace compared; ``difference``, ``lo`` and ``hi`` Trace's difference and
    its interval; ``p`` Trace's p-value and ``adjusted_p`` Prove's adjustment of it across the
    stage's candidates. ``repeats_needed`` and ``inputs_needed`` are Trace's counts of what
    would decide, there when the verdict is ``too small to tell``. ``left_out`` is Trace's count
    of the cases it left out, by why; ``flagged`` the cases Trace flagged as changed on their
    own; ``no_outcome`` the cases with no run that has an outcome in one of the two arms, read
    from the stored rows. A candidate with ``nothing to compare`` has no numbers."""

    number: int
    condition: str
    arm: str
    verdict: str
    note: str | None
    rate: float | None
    control_rate: float | None
    difference: float | None
    lo: float | None
    hi: float | None
    p: float | None
    adjusted_p: float | None
    repeats_needed: int | None
    inputs_needed: int | None
    left_out: Mapping[str, int]
    flagged: tuple[str, ...]
    no_outcome: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class Finding:
    """A confirmed candidate, as its file holds it.

    ``number`` is the finding's, within the hunt from 1 in the order confirmed; ``hunt`` the
    hunt's name; ``condition`` the condition by name. ``cases``, ``repeats`` and ``stage`` are
    the confirm stage it was confirmed in, and ``arm`` and ``control_arm`` its two Prove runs.
    ``rate``, ``control_rate``, ``difference``, ``lo``, ``hi``, ``p`` and ``adjusted_p`` are the
    tested candidate's, and ``q`` the level it was held to. ``kinds`` counts the failure kinds
    seen in its arm and ``signals`` the three signals over it; ``judged_by`` is ``your check``
    when a failed run of its arm was judged by the user's own check, and ``break`` otherwise.
    ``flagged`` and ``left_out`` are Trace's. ``reference`` names its reference arm, ``replay``
    is the command that replays it, and ``trace`` the Trace command for its full report."""

    number: int
    hunt: str
    condition: str
    cases: tuple[str, ...]
    repeats: int
    stage: int
    arm: str
    control_arm: str
    rate: float | None
    control_rate: float | None
    difference: float | None
    lo: float | None
    hi: float | None
    p: float | None
    adjusted_p: float | None
    q: float
    kinds: Mapping[str, int]
    signals: Mapping[str, int]
    judged_by: str
    flagged: tuple[str, ...]
    left_out: Mapping[str, int]
    reference: str
    replay: str
    trace: str


@dataclass(frozen=True, kw_only=True)
class Confirmation:
    """What a confirm stage came to: its number, its ``design``, every candidate ``tested``, in
    the candidates' order, and the ``findings``: one for each candidate confirmed, and none for
    any other."""

    stage: int
    design: Design
    tested: tuple[Tested, ...]
    findings: tuple[Finding, ...]


@dataclass(frozen=True, kw_only=True)
class Replayed:
    """One finding, run once and stored nowhere: the ``finding``'s number, the ``case`` and the
    ``seed`` it ran on, its ``outcome`` (``ok``, ``failed`` or ``not counted``), the failure
    ``kind`` or ``None``, and its ``calls`` in order, each with the change applied to it."""

    finding: int
    case: str
    seed: int
    outcome: str
    kind: str | None
    calls: tuple[records.Call, ...]
    error: str | None = None
    """For a run that was not counted, its one line of error, the line a stored row of it
    carries; ``None`` for a run that was counted."""


@dataclass(frozen=True, kw_only=True)
class Rechecked:
    """One finding, rechecked on the agent as it is now.

    ``finding`` is its number and ``condition`` its condition by name. ``phrase`` is one of
    ``PHRASES``. ``before`` and ``now`` are the two Prove runs Trace compared: the finding's
    reference arm, or the old agent's arm when one was given, and the arm run now.
    ``rate_before`` and ``rate_now`` are their failure shares over the cases Trace compared;
    ``difference``, ``lo``, ``hi`` and ``p`` are Trace's, and ``adjusted_p`` Prove's adjustment
    across the findings rechecked. ``repeats_needed`` is Trace's count when the phrase is
    ``too small to tell``. ``left_out`` is Trace's count of the cases it left out and
    ``no_outcome`` the cases with no run that has an outcome in one of the two arms.
    ``gap_days`` is how far apart Trace says the two runs started, in days: ``None`` when both
    were run now, side by side, and when Trace could not read a start. ``trace`` is the Trace
    command for the full report."""

    finding: int
    condition: str
    phrase: str
    before: str
    now: str
    rate_before: float
    rate_now: float
    difference: float
    lo: float | None
    hi: float | None
    p: float
    adjusted_p: float
    repeats_needed: int | None
    left_out: Mapping[str, int]
    no_outcome: tuple[str, ...]
    gap_days: float | None
    trace: str


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _of(hunt: object) -> Hunt:
    if not isinstance(hunt, Hunt):
        raise TypeError(f"this runs in a hunt that is open, not in {type(hunt).__name__}")
    return hunt


def _check_progress(on_progress: object) -> None:
    if on_progress is not None and not callable(on_progress):
        raise HuntError("on_progress is not something that can be called with the runs done "
                        "and the runs asked for")


def _plural(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


def _env_of(hunt: Hunt) -> dict[str, tuple[Any, ...]]:
    """The settings' ``[vary.env]`` table, as reading a condition's name takes it."""
    return {one.name: tuple(one.values) for one in hunt.settings.vary.env}


def _canonical(hunt: Hunt, condition: object) -> str:
    """A condition's canonical name, from the condition or from a name of it in any spelling.
    ``ChangeError`` passes through for one the catalogue cannot read."""
    if isinstance(condition, Condition):
        condition = _name_of(condition)
    if not isinstance(condition, str):
        raise ChangeError(f"a condition is a Condition or its name, not "
                          f"{type(condition).__name__}")
    return _name_of(parse(condition, env=_env_of(hunt)))


def _write_text(path: Path, text: str) -> None:
    """Write a file whole, through a temporary one, so a reader never finds half."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    _write_text(path, json.dumps(data, indent=2, allow_nan=False) + "\n")


def _read_only(counts: Mapping[str, int]) -> Mapping[str, int]:
    return MappingProxyType(dict(counts))


# ---------------------------------------------------------------------------
# what the store holds
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Row:
    """One stored row, as far as this module reads it."""

    case: str
    seed: int
    outcome: str | None
    record: records.RunRecord


class _Stored:
    """A hunt's stored rows, read through Prove's own store, each run read once for as long as
    it holds as many rows as when it was read."""

    def __init__(self, hunt: Hunt) -> None:
        self._store = Store(hunt.store)
        self._read: dict[str, tuple[int, list[_Row]]] = {}

    def runs(self) -> list[str]:
        return list(self._store.runs())

    def count(self, run_id: str) -> int:
        return self._store.count(run_id) if run_id in self._store.runs() else 0

    def holds(self, run_id: str, cells: int) -> bool:
        """Whether the run holds every row it was made for."""
        return self.count(run_id) >= cells

    def made(self, run_id: str) -> datetime.datetime | None:
        """When the run was made, as Prove's store wrote it down; ``None`` for a run that is
        not there or whose time cannot be read."""
        if run_id not in self._store.runs():
            return None
        try:
            when = datetime.datetime.fromisoformat(
                self._store.manifest(run_id).created_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        return when if when.tzinfo is not None else when.replace(tzinfo=datetime.UTC)

    def rows(self, run_id: str) -> list[_Row]:
        count = self.count(run_id)
        if count == 0:
            return []
        known = self._read.get(run_id)
        if known is not None and known[0] == count:
            return known[1]
        rows: list[_Row] = []
        for row in self._store.read(run_id).to_dict("records"):
            try:
                record = records.RunRecord.from_dict(row["meta"][records.META_KEY])
            except (KeyError, TypeError, records.RecordError):
                raise HuntError(f'the run "{run_id}" holds a row with no record Break can '
                                "read") from None
            outcome = row["outcome"]
            rows.append(_Row(case=record.case, seed=int(row["seed"]),
                             outcome=outcome if isinstance(outcome, str) else None,
                             record=record))
        self._read[run_id] = (count, rows)
        return rows

    def no_outcome(self, runs: Sequence[str], cases: Sequence[str]) -> tuple[str, ...]:
        """The cases with no row that has an outcome in one of ``runs``, in the cases' order."""
        counted = [{row.case for row in self.rows(run_id) if row.outcome is not None}
                   for run_id in runs]
        return tuple(case for case in cases if any(case not in have for have in counted))


# ---------------------------------------------------------------------------
# Trace: the command, its document, and the check before any run
# ---------------------------------------------------------------------------


def _trace(words: Sequence[str], folder: Path) -> str:
    """Run Trace's command with the Python Break runs on, in ``folder``, and hand back what it
    printed. Its exit code is not read, here or anywhere."""
    try:
        done = subprocess.run([sys.executable, "-m", _TRACE, *words], cwd=folder,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", check=False)
    except OSError as wrong:
        raise ConfirmError(f"Trace's command could not be started ({type(wrong).__name__})",
                           reason="trace missing") from wrong
    return done.stdout


def _command(old_run: str, new_run: str, store: Path | str, max_difference: float) -> list[str]:
    """The words of Trace's test of two stored runs, as Break asks for it and as a finding
    shows it: every flag the reading rests on stated, and no level, so Trace's own is used."""
    return ["fix-check", old_run, new_run, "--inputs", "all", "--event", "failed",
            "--max-mde", repr(float(max_difference)), "--store", str(store)]


def _shown_command(old_run: str, new_run: str, store: Path | str, max_difference: float) -> str:
    return shlex.join(["poisson-trace", *_command(old_run, new_run, store, max_difference)])


def _no_answer(why: str, old_run: str, new_run: str) -> ConfirmError:
    return ConfirmError(f"Trace gave no answer Break can read for {old_run} against {new_run}: "
                        f"{why}. The runs are kept", reason="trace answer")


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _held(doc: Mapping[str, Any]) -> str | None:
    """What is wrong with a document as this module reads one, or ``None``."""
    if doc.get("schema") != FIX_CHECK_SCHEMA:
        return f"its schema is not {FIX_CHECK_SCHEMA}"
    if doc.get("verdict") not in _TRACE_VERDICTS:
        return "its verdict is a word Trace does not have"
    if doc.get("direction") not in _TRACE_DIRECTIONS:
        return "its direction is a word Trace does not have"
    if doc["verdict"] == _DIFFERENT and doc["direction"] == _NO_DIRECTION:
        return "it says the runs are different, in no direction"
    test, difference, rows = doc.get("test"), doc.get("difference"), doc.get("rows")
    if not isinstance(test, Mapping) or not _is_number(test.get("p")):
        return "it has no p-value"
    if not isinstance(difference, Mapping) or not _is_number(difference.get("points")):
        return "it has no difference"
    for bound in ("lo", "hi"):
        if bound not in difference or not (difference[bound] is None
                                           or _is_number(difference[bound])):
            return "its difference has no interval"
    if not isinstance(rows, Mapping):
        return "it does not count the runs compared"
    for side in ("old", "new"):
        counted = rows.get(side)
        if (not isinstance(counted, Mapping) or not _is_count(counted.get("failed"))
                or not _is_count(counted.get("runs")) or counted["runs"] == 0):
            return "it does not count the runs compared"
    if "guidance" not in doc or not (doc["guidance"] is None
                                     or isinstance(doc["guidance"], Mapping)):
        return "it does not say what would decide"
    guidance = doc["guidance"] or {}
    for key in ("repeats", "inputs"):
        if not (guidance.get(key) is None or _is_count(guidance.get(key))):
            return "it does not say what would decide"
    inputs = doc.get("inputs")
    left_out = inputs.get("left_out") if isinstance(inputs, Mapping) else None
    if not isinstance(left_out, Mapping) or not all(
            isinstance(key, str) and _is_count(value) for key, value in left_out.items()):
        return "it does not count the cases left out"
    changes = doc.get("changes")
    listed = changes.get("rows") if isinstance(changes, Mapping) else None
    if not isinstance(listed, list):
        return "it does not list the cases one by one"
    for row in listed:
        config = row.get("config") if isinstance(row, Mapping) else None
        if (not isinstance(config, Mapping) or not isinstance(config.get("case"), str)
                or "flag" not in row):
            return "it does not list the cases one by one"
    if "gap_seconds" not in doc or not (doc["gap_seconds"] is None
                                        or _is_number(doc["gap_seconds"])):
        return "it does not say how far apart the runs started"
    return None


def ask_trace(store: Path | str, old_run: str, new_run: str, *, max_difference: float,
              folder: Path | str | None = None) -> Mapping[str, Any] | None:
    """Ask Trace for its test of two runs of ``store``, ``old_run`` against ``new_run``, and
    hand back the document it printed: the one place Trace's test is asked for and read.

    Trace is run as ``python -m poisson_trace fix-check OLD NEW --inputs all --event failed
    --max-mde X --store STORE --json``, with the Python Break runs on, so the Trace installed
    beside Break answers and not one found on ``PATH``. ``X`` is ``max_difference``, the largest
    difference worth finding. It runs in ``folder``, by default the folder the store is in,
    which for a hunt is the hunt's own: a ``trace.toml`` anywhere else changes nothing. The
    store is handed to Trace by its whole path, so it is found from whichever folder that is.

    The document is read whatever the command's exit code. ``None`` means Trace printed
    nothing, which is how it refuses two runs it cannot compare. Anything printed that is not a
    document of ``FIX_CHECK_SCHEMA`` with the fields this module reads is a ``ConfirmError``
    with the reason ``trace answer``."""
    kept = Path(store).absolute()
    where = Path(folder) if folder is not None else kept.parent
    printed = _trace([*_command(old_run, new_run, kept, max_difference), "--json"], where)
    if not printed.strip():
        return None
    try:
        doc = json.loads(printed)
    except ValueError:
        raise _no_answer("what it printed is not JSON", old_run, new_run) from None
    if not isinstance(doc, dict):
        raise _no_answer("what it printed is not a document", old_run, new_run)
    wrong = _held(doc)
    if wrong is not None:
        raise _no_answer(wrong, old_run, new_run)
    return doc


def _installed_version(folder: Path) -> str | None:
    """What ``python -m poisson_trace --version`` says its version is, or ``None`` when no
    Trace answered."""
    words = _trace(["--version"], folder).split()
    if len(words) >= 2 and words[0] == "poisson-trace":
        return words[1]
    return None


def _write_probe(store: Store) -> tuple[str, str]:
    """Two runs of one case and one row each, ``ok`` in the first and ``failed`` in the second,
    in the shape a hunt's arms have. No agent is run."""
    names = ("probe-before", "probe-after")
    for seed, (run_id, outcome) in enumerate(zip(names, ("ok", "failed"), strict=True)):
        failed = outcome == "failed"
        record = records.RunRecord(
            hunt="probe", stage="confirm", arm=run_id, case="probe",
            condition=records.Condition(name="", changes=()),
            failure=records.Failure(
                kind="failed" if failed else None,
                signals=records.Signals(gave_up=0, retry_storm=0, over_budget=0)),
            selection=records.Selection(strategy="screen", probability=1),
            calls=(), judged_by="break", target_outcome=None)
        episode = Episode(outcome=outcome, t=0.0, horizon=1.0,
                          meta={records.META_KEY: record.to_dict(), "case_id": "probe"})
        store.create_run(RunManifest(
            run_id=run_id, target_id="poisson_break.confirm:probe", t_unit="seconds",
            run_salt="probe", axis_types={"case": "categorical"}, backend="poisson-break",
            environment={"hunt": "probe", "stage": "confirm"}))
        store.append(run_id, [EpisodeRecord.from_episode(
            episode, run_id=run_id, config={"case": "probe"}, seed=seed, replicate_index=0,
            wall_time=0.0)])
        store.mark_complete(run_id)
    return names


def _check_trace(hunt: Hunt) -> None:
    """Hold Trace to the version and the schema this module reads, before any run: its version
    first, then its answer to a check of two runs Break writes in a temporary folder."""
    found = _installed_version(hunt.folder)
    if found is None:
        raise ConfirmError("Trace is not installed beside Break, and confirming a finding and "
                           "rechecking one are Trace's test: python -m poisson_trace --version "
                           "printed no version", reason="trace missing")
    if found != TRACE_VERSION:
        raise ConfirmError(f"Trace {found} is installed, and this Break reads Trace "
                           f"{TRACE_VERSION}", reason="trace version")
    with tempfile.TemporaryDirectory(prefix="poisson-break-") as temporary:
        folder = Path(temporary)
        before, after = _write_probe(Store(folder / "store"))
        try:
            answer = ask_trace(folder / "store", before, after,
                               max_difference=hunt.settings.confirm.max_difference,
                               folder=folder)
        except ConfirmError:
            answer = None
    if answer is None:
        raise ConfirmError(f"Trace {found} answered a check of two runs with something other "
                           f"than a {FIX_CHECK_SCHEMA} document, which is what this Break "
                           "reads", reason="trace schema")


# ---------------------------------------------------------------------------
# the candidates
# ---------------------------------------------------------------------------


def write_candidates(hunt: Hunt, conditions: Iterable[Condition | str]) -> None:
    """Keep the hunt's candidates, best first, in its ``candidates.json``, for ``confirm`` to
    read: each with its number from 1 and its condition by name.

    Refused, with nothing written and the reason ``no candidates``: no condition at all, a
    condition twice (by its canonical name, so in any spelling), the empty condition, which is
    the control, more conditions than the settings' ``candidates``, and writing again once a
    confirm stage is on disk, since its design is fixed."""
    hunt = _of(hunt)
    if isinstance(conditions, str | Condition) or not isinstance(conditions, Iterable):
        raise ConfirmError("candidates are given as a list of conditions",
                           reason="no candidates")
    names: list[str] = []
    for condition in conditions:
        try:
            names.append(_canonical(hunt, condition))
        except ChangeError as wrong:
            raise ConfirmError(f"a candidate is not a condition Break can read ({wrong})",
                               reason="no candidates") from None
    most = hunt.settings.confirm.candidates
    if not names:
        raise ConfirmError("there is no candidate to write: a hunt hands over at least one",
                           reason="no candidates")
    if "" in names:
        raise ConfirmError("the empty condition is the control, not a candidate",
                           reason="no candidates")
    twice = next((name for name in names if names.count(name) > 1), None)
    if twice is not None:
        raise ConfirmError(f'the condition "{twice}" is among the candidates twice',
                           reason="no candidates")
    if len(names) > most:
        raise ConfirmError(f"{_plural(len(names), 'candidate')} were given, and the settings "
                           f"confirm at most {most} (confirm.candidates)",
                           reason="no candidates")
    if _read_stages(hunt):
        raise ConfirmError(f'the hunt "{hunt.name}" has a confirm stage on disk, whose design '
                           "is fixed: its candidates cannot be written again",
                           reason="no candidates")
    _write_json(hunt.folder / _CANDIDATES_FILE, {
        "schema": CANDIDATES_SCHEMA,
        "candidates": [{"number": number, "condition": name}
                       for number, name in enumerate(names, start=1)],
    })


def _candidate_names(hunt: Hunt) -> tuple[str, ...]:
    path = hunt.folder / _CANDIDATES_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfirmError(f'the hunt "{hunt.name}" has no candidates to confirm: a hunt writes '
                           f"them to its {_CANDIDATES_FILE}", reason="no candidates") from None
    except (OSError, ValueError):
        raise ConfirmError(f'the candidates of the hunt "{hunt.name}" could not be read from '
                           f"its {_CANDIDATES_FILE}", reason="no candidates") from None
    try:
        data = json.loads(text)
        if data["schema"] != CANDIDATES_SCHEMA:
            raise ValueError(data["schema"])
        names = []
        for number, entry in enumerate(data["candidates"], start=1):
            if entry["number"] != number:
                raise ValueError(entry["number"])
            names.append(_canonical(hunt, entry["condition"]))
    except (ValueError, KeyError, TypeError):
        raise ConfirmError(f'the candidates of the hunt "{hunt.name}" could not be read from '
                           f"its {_CANDIDATES_FILE}", reason="no candidates") from None
    if not names:
        raise ConfirmError(f'the hunt "{hunt.name}" has no candidates to confirm',
                           reason="no candidates")
    return tuple(names)


def read_candidates(hunt: Hunt) -> tuple[Condition, ...]:
    """The hunt's candidates as written, best first. With no ``candidates.json``, or one that
    cannot be read, there is nothing to confirm: ``ConfirmError``, reason ``no candidates``."""
    hunt = _of(hunt)
    env = _env_of(hunt)
    return tuple(parse(name, env=env) for name in _candidate_names(hunt))


# ---------------------------------------------------------------------------
# the design, and the stages on disk
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Stage:
    """One confirm stage as ``confirm.json`` holds it: with the ``q`` and ``max_difference`` it
    was written under, which it is judged under however the settings read later."""

    number: int
    repeats: int
    cases: tuple[str, ...]
    arms: tuple[tuple[str, str], ...]
    q: float
    max_difference: float

    @property
    def cells(self) -> int:
        """How many runs each arm of the stage holds."""
        return len(self.cases) * self.repeats


def _counts(settings: Settings, stage: _Stage, per_run: float | None) -> Design:
    """A stage as a design: its runs as ``plan_confirm`` counts them at the stage's own
    repeats, each priced at what one control run cost."""
    at_repeats = replace(settings, confirm=replace(settings.confirm, repeats=stage.repeats))
    plan = plan_confirm(at_repeats, cases=len(stage.cases), candidates=len(stage.arms) - 1)
    return Design(
        cases=stage.cases, repeats=stage.repeats, arms=stage.arms,
        confirm_runs=plan.confirm_runs, reference_per_finding=plan.reference_per_finding,
        reference_runs=plan.reference_runs, runs=plan.runs,
        dollars=None if per_run is None else plan.confirm_runs * per_run,
        reference_dollars=None if per_run is None else plan.reference_runs * per_run)


def _first_stage(names: Sequence[str], settings: Settings, summary: ControlSummary) -> _Stage:
    cases = tuple(case for case in summary.per_case if case not in summary.set_aside)
    if not cases:
        raise ConfirmError("the control set every case aside, each having failed every run "
                           "with no change, so there is no case to confirm on",
                           reason="no control")
    if not names:
        raise ConfirmError("there is no candidate to confirm", reason="no candidates")
    arms = (("confirm-control", ""),
            *((f"confirm-{number}", name) for number, name in enumerate(names, start=1)))
    return _Stage(number=1, repeats=settings.confirm.repeats, cases=cases, arms=arms,
                  q=settings.confirm.q, max_difference=settings.confirm.max_difference)


def design(candidates: Sequence[Condition | str], settings: Settings,
           control: ControlSummary) -> Design:
    """The first confirm stage's design for these candidates, worked out and nothing run.

    One control arm and one arm for each candidate, in the candidates' order, every arm on the
    cases the control did not set aside, in the cases' own order, each the settings' confirm
    ``repeats`` times. The counts are ``plan_confirm``'s for these cases and candidates, and
    the dollars the control's cost of one run times the runs, ``None`` without prices."""
    if not isinstance(settings, Settings):
        raise TypeError(f"a design is worked out from settings, not {type(settings).__name__}")
    if not isinstance(control, ControlSummary):
        raise TypeError("a design is worked out from what the control measured, not "
                        f"{type(control).__name__}")
    names = [_name_of(one) if isinstance(one, Condition) else str(one) for one in candidates]
    return _counts(settings, _first_stage(names, settings, control), control.dollars_per_run)


def _read_stages(hunt: Hunt) -> list[_Stage]:
    """The confirm stages the hunt has on disk, in order; none for a hunt with no file."""
    path = hunt.folder / _CONFIRM_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        raise HuntError(f'the confirm stages of the hunt "{hunt.name}" could not be read from '
                        f"its {_CONFIRM_FILE}") from None
    try:
        data = json.loads(text)
        if data["schema"] != CONFIRM_SCHEMA:
            raise ValueError(data["schema"])
        stages = []
        for number, held in enumerate(data["stages"], start=1):
            arms = tuple((str(arm["arm"]), str(arm["condition"])) for arm in held["arms"])
            q, most = held["q"], held["max_difference"]
            if not all(isinstance(value, float) and 0 < value < 1 for value in (q, most)):
                raise ValueError(number)
            stage = _Stage(number=int(held["number"]), repeats=int(held["repeats"]),
                           cases=tuple(str(case) for case in held["cases"]), arms=arms,
                           q=q, max_difference=most)
            if stage.number != number or stage.repeats < 1 or not stage.cases or len(arms) < 2:
                raise ValueError(number)
            stages.append(stage)
    except (ValueError, KeyError, TypeError):
        raise HuntError(f'the confirm stages of the hunt "{hunt.name}" could not be read from '
                        f"its {_CONFIRM_FILE}") from None
    return stages


@dataclass(frozen=True, kw_only=True)
class Stage:
    """One confirm stage as the hunt's ``confirm.json`` holds it, with what the store holds of
    it: ``number``, from 1; ``repeats``, ``cases`` and ``arms`` as written, the arms as
    ``Design.arms`` gives them (each arm's word and its condition's name, the control first
    with ``""``); the ``q`` and ``max_difference`` it is judged under; and ``counts``, each
    arm's word, in the arms' order, to the rows the store holds of it, runs not counted
    included and 0 for an arm with no run. A stage holds ``len(cases) * repeats`` rows an arm
    when it is finished. Nothing here can be changed."""

    number: int
    repeats: int
    cases: tuple[str, ...]
    arms: tuple[tuple[str, str], ...]
    q: float
    max_difference: float
    counts: Mapping[str, int]


def read_stages(hunt: Hunt) -> tuple[Stage, ...]:
    """The confirm stages the hunt has written, in order, each with the rows the store holds of
    its arms when asked: none for a hunt with no ``confirm.json``. A file that cannot be read is
    the runs module's ``HuntError``, as ``confirm`` refuses it. Runs nothing, asks Trace
    nothing and writes nothing."""
    hunt = _of(hunt)
    stages = _read_stages(hunt)
    held = hunt.stored() if stages else {}
    return tuple(Stage(number=stage.number, repeats=stage.repeats, cases=stage.cases,
                       arms=stage.arms, q=stage.q, max_difference=stage.max_difference,
                       counts=_read_only({word: held.get(word, 0) for word, _ in stage.arms}))
                 for stage in stages)


def _write_stages(hunt: Hunt, stages: Sequence[_Stage]) -> None:
    _write_json(hunt.folder / _CONFIRM_FILE, {
        "schema": CONFIRM_SCHEMA,
        "stages": [{"number": stage.number, "repeats": stage.repeats,
                    "cases": list(stage.cases), "q": stage.q,
                    "max_difference": stage.max_difference,
                    "arms": [{"arm": word, "condition": name} for word, name in stage.arms]}
                   for stage in stages],
    })


def _finished(hunt: Hunt, stage: _Stage, stored: _Stored) -> bool:
    return all(stored.holds(f"{hunt.name}-{word}", stage.cells) for word, _ in stage.arms)


def _need_control(hunt: Hunt, stored: _Stored) -> None:
    """Refuse a hunt whose control arm does not hold every run it was made for. Read from the
    hunt's file and its store, with nothing run."""
    run_id = f"{hunt.name}-control"
    try:
        about = json.loads((hunt.folder / _HUNT_FILE).read_text(encoding="utf-8"))
        line = about["arms"].get(run_id)
        cells = None if line is None else len(line["cases"]) * int(line["repeats"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise HuntError(f'the hunt "{hunt.name}" could not be read from its '
                        f"{_HUNT_FILE}") from None
    if cells is None or not stored.holds(run_id, cells):
        raise ConfirmError(f'the hunt "{hunt.name}" has no finished control, and candidates '
                           "are confirmed against what the control measured",
                           reason="no control")


# ---------------------------------------------------------------------------
# progress across the arms of a stage
# ---------------------------------------------------------------------------


class _Progress:
    """Counts a stage's runs across its arms for ``on_progress``: the runs done so far and the
    runs the stage holds, as the runs module counts one arm's."""

    def __init__(self, on_progress: Callable[[int, int], None] | None) -> None:
        self._tell = on_progress
        self._before = 0
        self.total = 0

    def arm(self, cells: int) -> Callable[[int, int], None] | None:
        """What to hand ``run_arm`` for the next arm, of ``cells`` runs."""
        before = self._before
        self._before += cells
        if self._tell is None:
            return None
        tell = self._tell
        return lambda done, _asked: tell(before + done, self.total)


# ---------------------------------------------------------------------------
# the confirm stage
# ---------------------------------------------------------------------------


def _rate(doc: Mapping[str, Any], side: str) -> float:
    """A failure share: two of Trace's counts, divided."""
    counted = doc["rows"][side]
    return float(counted["failed"] / counted["runs"])


def _adjusted(docs: Sequence[Mapping[str, Any]], q: float) -> list[float]:
    """Prove's adjustment of Trace's p-values, in the order given."""
    if not docs:
        return []
    # Prove's function takes anything an array can be made from; a list is handed over as it is.
    values: Any = [float(doc["test"]["p"]) for doc in docs]
    return [float(value) for value in bh(values, q)]


def _optional(value: float | None) -> float | None:
    return None if value is None else float(value)


def _flagged(doc: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(row["config"]["case"] for row in doc["changes"]["rows"]
                 if row["flag"] is not None)


def _judge(hunt: Hunt, stage: _Stage, stored: _Stored) -> tuple[Tested, ...]:
    """Put each candidate's arm to Trace once, against the stage's control arm, and read the
    verdicts off Trace's words and Prove's adjustment across the candidates Trace answered,
    under the stage's own ``q`` and ``max_difference``."""
    control_run = f"{hunt.name}-{stage.arms[0][0]}"
    asked: list[tuple[str, str, str, Mapping[str, Any] | None, tuple[str, ...]]] = []
    for word, name in stage.arms[1:]:
        run_id = f"{hunt.name}-{word}"
        doc = ask_trace(hunt.store, control_run, run_id,
                        max_difference=stage.max_difference, folder=hunt.folder)
        missing = stored.no_outcome((control_run, run_id), stage.cases)
        if doc is None and len(missing) < len(stage.cases):
            # Trace printed nothing while there are cases with an outcome in both arms.
            raise _no_answer("it printed nothing", control_run, run_id)
        asked.append((word, name, run_id, doc, missing))

    adjusted = iter(_adjusted([doc for _, _, _, doc, _ in asked if doc is not None], stage.q))
    tested: list[Tested] = []
    for word, name, run_id, doc, missing in asked:
        number = int(word.rsplit("-", 1)[1])
        if doc is None:
            tested.append(Tested(
                number=number, condition=name, arm=run_id, verdict="not confirmed",
                note="nothing to compare", rate=None, control_rate=None, difference=None,
                lo=None, hi=None, p=None, adjusted_p=None, repeats_needed=None,
                inputs_needed=None, left_out=_read_only({}), flagged=(), no_outcome=missing))
            continue
        after = next(adjusted)
        said, direction = doc["verdict"], doc["direction"]
        note: str | None = None
        if said == _TOO_SMALL:
            verdict = "too small to tell"
        elif said == _DIFFERENT and direction == _LESS:
            verdict, note = "not confirmed", "failed less"
        elif said == _DIFFERENT and after <= stage.q:
            verdict = "confirmed"
        elif said == _DIFFERENT:
            verdict, note = "not confirmed", "not after the correction"
        else:
            verdict = "not confirmed"
        guidance = doc["guidance"] or {}
        tested.append(Tested(
            number=number, condition=name, arm=run_id, verdict=verdict, note=note,
            rate=_rate(doc, "new"), control_rate=_rate(doc, "old"),
            difference=float(doc["difference"]["points"]),
            lo=_optional(doc["difference"]["lo"]), hi=_optional(doc["difference"]["hi"]),
            p=float(doc["test"]["p"]), adjusted_p=after,
            repeats_needed=guidance.get("repeats"), inputs_needed=guidance.get("inputs"),
            left_out=_read_only(doc["inputs"]["left_out"]), flagged=_flagged(doc),
            no_outcome=missing))
    return tuple(tested)


def _new_finding(hunt: Hunt, stage: _Stage, tested: Tested, number: int,
                 stored: _Stored) -> Finding:
    """A confirmed candidate as a finding: the tested candidate's numbers, and what its arm's
    stored rows say of how it failed."""
    kinds: dict[str, int] = {}
    counted = dict.fromkeys(records.SIGNALS, 0)
    judged_by = "break"
    for row in stored.rows(tested.arm):
        failure = row.record.failure
        if failure.kind is not None:
            kinds[failure.kind] = kinds.get(failure.kind, 0) + 1
        for signal in counted:
            counted[signal] += getattr(failure.signals, signal)
        if row.outcome == "failed" and row.record.judged_by == _YOUR_CHECK:
            judged_by = _YOUR_CHECK
    control_run = f"{hunt.name}-{stage.arms[0][0]}"
    return Finding(
        number=number, hunt=hunt.name, condition=tested.condition, cases=stage.cases,
        repeats=stage.repeats, stage=stage.number, arm=tested.arm, control_arm=control_run,
        rate=tested.rate, control_rate=tested.control_rate, difference=tested.difference,
        lo=tested.lo, hi=tested.hi, p=tested.p, adjusted_p=tested.adjusted_p,
        q=stage.q, kinds=_read_only(kinds), signals=_read_only(counted),
        judged_by=judged_by, flagged=tested.flagged, left_out=tested.left_out,
        reference=f"{hunt.name}-reference-{number}",
        replay=shlex.join(["poisson-break", "replay", str(number), "--hunt", hunt.name]),
        trace=_shown_command(control_run, tested.arm, hunt.store, stage.max_difference))


def _findings_of(hunt: Hunt, stage: _Stage, tested: Sequence[Tested],
                 stored: _Stored) -> tuple[Finding, ...]:
    """The stage's findings: the file of each confirmed candidate that has one, and a new
    finding, numbered on from the hunt's last and written, for each that has none."""
    written = {finding.arm: finding for finding in _written(hunt)}
    number = max((finding.number for finding in written.values()), default=0)
    findings: list[Finding] = []
    for one in tested:
        if one.verdict != "confirmed":
            continue
        finding = written.get(one.arm)
        if finding is None:
            number += 1
            finding = _new_finding(hunt, stage, one, number, stored)
            write_finding(hunt, finding)
        findings.append(finding)
    return tuple(findings)


def _run_stage(hunt: Hunt, stage: _Stage, stored: _Stored,
               on_progress: Callable[[int, int], None] | None) -> Confirmation:
    """Run what is missing of a stage's arms, put them to Trace, write the findings, and run
    what is missing of every written finding's reference arm."""
    per_run = control(hunt).dollars_per_run
    progress = _Progress(on_progress)
    progress.total = len(stage.arms) * stage.cells
    for word, name in stage.arms:
        run_arm(hunt, word, stage.cases, name, repeats=stage.repeats,
                on_progress=progress.arm(stage.cells))
    tested = _judge(hunt, stage, stored)
    findings = _findings_of(hunt, stage, tested, stored)
    _run_references(hunt, stored, progress)
    return Confirmation(stage=stage.number, design=_counts(hunt.settings, stage, per_run),
                        tested=tested, findings=findings)


def confirm(hunt: Hunt, *, repeats: int | None = None,
            on_progress: Callable[[int, int], None] | None = None) -> Confirmation:
    """Confirm the hunt's candidates: run the confirm stage, read Trace's test of each
    candidate against the shared control, write the findings and run their reference arms.

    With no confirm stage on disk, the first is designed from the candidates written and what
    the control measured, written to ``confirm.json``, and run. With one on disk, the latest is
    taken up again under its written design: what is missing of it runs, and a stage that is
    finished runs nothing and gives the same answer, Trace asked again. ``repeats=N`` asks
    again after a *too small to tell*: a new stage, numbered on, of the candidates the latest
    stage called *too small to tell*, each ``N`` times, with its own control arm
    (``confirm-<k>-control`` and ``confirm-<k>-<candidate>`` for stage ``k``), on new seeds and
    read on its own; its findings are numbered on from the hunt's last, after any the latest
    stage confirmed and had not yet written.

    ``on_progress(done, total)`` is called after each run made, with the stage's runs done and
    the runs it holds; the total grows by the reference arms once the findings are known.

    Refused before any run, each a ``ConfirmError`` by its ``reason``: ``no candidates`` and
    ``no control`` when there is nothing to confirm or nothing to confirm against;
    ``trace missing``, ``trace version`` and ``trace schema``; and, with ``repeats``,
    ``unfinished`` while the latest stage has runs missing and ``nothing to ask again`` when it
    called no candidate *too small to tell*, or when there is no stage yet. ``trace answer``
    comes after the arms ran, which are kept."""
    hunt = _of(hunt)
    _check_progress(on_progress)
    if repeats is not None and (isinstance(repeats, bool) or not isinstance(repeats, int)
                                or repeats < 1):
        raise HuntError("repeats is not a whole number of 1 or more")
    stored = _Stored(hunt)
    stages = _read_stages(hunt)

    if repeats is None and stages:
        stage = stages[-1]
        _check_trace(hunt)
    elif repeats is None:
        names = _candidate_names(hunt)
        _need_control(hunt, stored)
        _check_trace(hunt)
        stage = _first_stage(names, hunt.settings, control(hunt))
        _write_stages(hunt, [stage])
    else:
        if not stages:
            raise ConfirmError(f'the hunt "{hunt.name}" has no confirm stage yet, so nothing '
                               "was too small to tell: confirm first, at the settings' "
                               "repeats", reason="nothing to ask again")
        latest = stages[-1]
        if not _finished(hunt, latest, stored):
            raise ConfirmError(f"confirm stage {latest.number} of the hunt \"{hunt.name}\" has "
                               "runs missing: finish it before asking again",
                               reason="unfinished")
        _check_trace(hunt)
        judged = _judge(hunt, latest, stored)
        small = [one for one in judged if one.verdict == "too small to tell"]
        if not small:
            raise ConfirmError(f"confirm stage {latest.number} of the hunt \"{hunt.name}\" "
                               "called no candidate too small to tell, so there is nothing to "
                               "ask again", reason="nothing to ask again")
        # A candidate the latest stage confirmed is a finding before any later stage begins:
        # a stage that stopped after its last run, with its findings unwritten, loses none.
        _findings_of(hunt, latest, judged, stored)
        number = latest.number + 1
        stage = _Stage(number=number, repeats=repeats, cases=latest.cases,
                       arms=((f"confirm-{number}-control", ""),
                             *((f"confirm-{number}-{one.number}", one.condition)
                               for one in small)),
                       q=hunt.settings.confirm.q,
                       max_difference=hunt.settings.confirm.max_difference)
        _write_stages(hunt, [*stages, stage])
    return _run_stage(hunt, stage, stored, on_progress)


def finished_stage(hunt: Hunt) -> Confirmation | None:
    """The latest confirm stage's answer when nothing of it is left to run or write: its arms
    hold every run, each candidate it confirms has its finding written, and the reference arm of
    every finding written holds every run. It is the answer ``confirm`` gives that stage asked
    again, Trace checked and asked again as ``confirm`` asks it.

    ``None`` for a hunt with no confirm stage, and for a stage that ``confirm`` would go on with:
    runs missing from its arms, from a reference arm or from the hunt's control, or a candidate it
    confirms with no finding file yet, as after a stage stopped once its last run was stored.
    Runs nothing and writes nothing; Trace is asked only of a stage whose arms are full. Refused
    as ``confirm`` refuses Trace (``trace missing``, ``trace version``, ``trace schema``,
    ``trace answer``)."""
    hunt = _of(hunt)
    stages = _read_stages(hunt)
    if not stages:
        return None
    stage = stages[-1]
    stored = _Stored(hunt)
    written = _written(hunt)
    if not _finished(hunt, stage, stored) or not all(
            stored.holds(finding.reference, len(finding.cases) * finding.repeats)
            for finding in written):
        return None
    try:
        _need_control(hunt, stored)  # what the stage's answer reads the cost of a run from
    except ConfirmError:
        return None
    _check_trace(hunt)
    tested = _judge(hunt, stage, stored)
    by_arm = {finding.arm: finding for finding in written}
    confirmed = [one.arm for one in tested if one.verdict == "confirmed"]
    if not all(arm in by_arm for arm in confirmed):
        return None
    return Confirmation(stage=stage.number,
                        design=_counts(hunt.settings, stage, control(hunt).dollars_per_run),
                        tested=tested, findings=tuple(by_arm[arm] for arm in confirmed))


# ---------------------------------------------------------------------------
# a finding's file
# ---------------------------------------------------------------------------

_TABLES = ("kinds", "signals", "left_out")
_SHARES = ("rate", "control_rate", "difference", "lo", "hi", "p", "adjusted_p")
_TEXTS = ("hunt", "condition", "arm", "control_arm", "judged_by", "reference", "replay",
          "trace")
_WHOLE = ("number", "repeats", "stage")
_LISTS = ("cases", "flagged")


def _finding_path(hunt: Hunt, number: int) -> Path:
    return hunt.folder / _FINDINGS_FOLDER / f"{number}.toml"


def _toml(value: object) -> str:
    if isinstance(value, str):
        return _quoted(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    assert isinstance(value, tuple | list)
    return "[" + ", ".join(_toml(item) for item in value) + "]"


def _own(hunt: Hunt, finding: Finding) -> None:
    """Hold a finding to being one of this hunt's, numbered from 1."""
    if not isinstance(finding, Finding):
        raise TypeError(f"a finding is a Finding, not {type(finding).__name__}")
    if isinstance(finding.number, bool) or not isinstance(finding.number, int) \
            or finding.number < 1:
        raise ConfirmError("a finding is numbered from 1", reason="unknown finding")
    prefix = f"{hunt.name}-"
    if finding.hunt != hunt.name or not all(
            isinstance(run, str) and run.startswith(prefix)
            for run in (finding.arm, finding.control_arm, finding.reference)):
        raise ConfirmError(f'finding {finding.number} is not one of the hunt "{hunt.name}"',
                           reason="unknown finding")


def write_finding(hunt: Hunt, finding: Finding) -> Path:
    """Write a finding to the hunt's ``findings/<n>.toml`` and hand back the file's path.

    The file is plain TOML with ``schema`` first, then the finding field by field, the three
    counts as tables at its end. A value that is ``None`` is left out, since TOML has no null.
    ``read_finding`` reads it back as the same finding. A finding of another hunt is refused
    (``unknown finding``)."""
    hunt = _of(hunt)
    _own(hunt, finding)
    lines = [f"schema = {_toml(FINDING_SCHEMA)}"]
    for field in fields(finding):
        value = getattr(finding, field.name)
        if value is None or field.name in _TABLES:
            continue
        lines.append(f"{field.name} = {_toml(float(value) if field.name in _SHARES else value)}")
    for table in _TABLES:
        lines += ["", f"[{table}]"]
        lines += [f"{_key_text(key)} = {_toml(count)}"
                  for key, count in getattr(finding, table).items()]
    path = _finding_path(hunt, finding.number)
    path.parent.mkdir(exist_ok=True)
    _write_text(path, "\n".join(lines) + "\n")
    return path


def _read_finding_file(hunt: Hunt, number: int) -> Finding:
    path = _finding_path(hunt, number)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfirmError(f'the hunt "{hunt.name}" has no finding {number}',
                           reason="unknown finding") from None
    except (OSError, ValueError):
        raise ConfirmError(f'finding {number} of the hunt "{hunt.name}" could not be read from '
                           f"{path.name}", reason="unknown finding") from None
    try:
        held = tomllib.loads(text)
        if held.pop("schema") != FINDING_SCHEMA:
            raise ValueError("schema")
        values: dict[str, Any] = {}
        for field in fields(Finding):
            name = field.name
            if name in _SHARES:
                values[name] = None if name not in held else float(held.pop(name))
            elif name == "q":
                values[name] = float(held.pop(name))
            elif name in _WHOLE:
                values[name] = held.pop(name)
                if isinstance(values[name], bool) or not isinstance(values[name], int):
                    raise ValueError(name)
            elif name in _TEXTS:
                values[name] = held.pop(name)
                if not isinstance(values[name], str):
                    raise ValueError(name)
            elif name in _LISTS:
                values[name] = tuple(held.pop(name))
                if not all(isinstance(item, str) for item in values[name]):
                    raise ValueError(name)
            else:
                counts = held.pop(name)
                if not all(isinstance(count, int) and not isinstance(count, bool)
                           for count in counts.values()):
                    raise ValueError(name)
                values[name] = _read_only(counts)
        if held or values["number"] != number:
            raise ValueError("fields")
        values["condition"] = _canonical(hunt, values["condition"])
        finding = Finding(**values)
    except (ValueError, KeyError, TypeError, AttributeError):
        # tomllib's own error and the catalogue's are both ValueErrors.
        raise ConfirmError(f'finding {number} of the hunt "{hunt.name}" could not be read from '
                           f"{path.name}", reason="unknown finding") from None
    _own(hunt, finding)
    return finding


def read_finding(hunt: Hunt, number: int) -> Finding:
    """Finding ``number`` of the hunt, read from its file: equal to the finding the file was
    written from. A finding that is not there, or whose file cannot be read as one, is a
    ``ConfirmError`` with the reason ``unknown finding``."""
    hunt = _of(hunt)
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise ConfirmError("a finding is read by its number, from 1", reason="unknown finding")
    return _read_finding_file(hunt, number)


def read_findings(hunt: Hunt) -> tuple[Finding, ...]:
    """Every finding the hunt has a file for, read from its file, in the order of their
    numbers: ``findings/<n>.toml`` for each plain whole number ``n`` from 1, whatever stage
    wrote it, a missing number passed over. What is on disk decides, so a hunt opened again
    gives the same. A hunt with no finding gives an empty tuple and does nothing. One file that
    cannot be read as a finding refuses the whole call (``unknown finding``), naming it."""
    return tuple(_written(_of(hunt)))


def _written(hunt: Hunt) -> list[Finding]:
    """Every finding the hunt has a file for, in the order of their numbers."""
    folder = hunt.folder / _FINDINGS_FOLDER
    if not folder.is_dir():
        return []
    numbers = sorted(int(path.stem) for path in folder.glob("*.toml")
                     if path.stem.isascii() and path.stem.isdigit() and int(path.stem) >= 1
                     and str(int(path.stem)) == path.stem)
    return [_read_finding_file(hunt, number) for number in numbers]


def _word(hunt: Hunt, run_id: str) -> str:
    """An arm's own word, from the name of its Prove run."""
    return run_id[len(hunt.name) + 1:]


# ---------------------------------------------------------------------------
# the reference arms
# ---------------------------------------------------------------------------


def _run_references(hunt: Hunt, stored: _Stored, progress: _Progress) -> tuple[str, ...]:
    """Run what is missing of every written finding's reference arm: the finding's condition
    on every case of its stage, its repeats times, on seeds of the arm's own."""
    findings = _written(hunt)
    missing = [finding.number for finding in findings
               if not stored.holds(finding.reference, len(finding.cases) * finding.repeats)]
    progress.total += sum(len(finding.cases) * finding.repeats for finding in findings
                          if finding.number in missing)
    for finding in findings:
        # An arm that holds every run is asked for too: it runs nothing, and an arm whose last
        # run was stored just as the stage stopped is marked complete here.
        tell = (progress.arm(len(finding.cases) * finding.repeats)
                if finding.number in missing else None)
        run_arm(hunt, _word(hunt, finding.reference), finding.cases, finding.condition,
                repeats=finding.repeats, on_progress=tell)
    return tuple(finding.reference for finding in findings)


def reference(hunt: Hunt, *,
              on_progress: Callable[[int, int], None] | None = None) -> tuple[str, ...]:
    """Run what is missing of the reference arm of every finding the hunt has written, and
    hand back the arms' names, in the findings' order: none for a hunt with no finding.

    ``confirm`` runs the reference arms at its end; this takes up a reference stage that
    stopped short. The hunt must be open on the agent the findings were confirmed on, since a
    reference arm is that agent under the finding's condition. Trace is not asked."""
    hunt = _of(hunt)
    _check_progress(on_progress)
    return _run_references(hunt, _Stored(hunt), _Progress(on_progress))


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------


def _given(hunt: Hunt, finding: int | Finding) -> Finding:
    """A finding from its number, read from its file, or a finding handed in, held to being
    this hunt's."""
    if isinstance(finding, Finding):
        _own(hunt, finding)
        return finding
    return read_finding(hunt, finding)


def replay(hunt: Hunt, finding: int | Finding, *, case: str | None = None) -> Replayed:
    """Run one finding once, and store nothing: no row, no line in the hunt's file, and nothing
    a cap counts.

    ``finding`` is a number, read from its file, or a ``Finding``; the condition run is the one
    it holds. The case is the first of the finding's cases with the most failed runs in its
    confirm arm, and the seed that of the case's first failed run there, so an agent that
    decides by its seed fails the same way. ``case`` picks another of the finding's cases, on
    the seed of that case's first run in the arm. Hands back the outcome, the kind and every
    call in order with the change applied to it."""
    hunt = _of(hunt)
    found = _given(hunt, finding)
    by_case: dict[str, list[_Row]] = {ident: [] for ident in found.cases}
    for row in _Stored(hunt).rows(found.arm):
        by_case.setdefault(row.case, []).append(row)
    if case is None:
        failed = {ident: [row for row in by_case[ident] if row.outcome == "failed"]
                  for ident in found.cases}
        most = max((len(rows) for rows in failed.values()), default=0)
        chosen = next((ident for ident in found.cases if len(failed[ident]) == most), None)
        pool = [] if chosen is None else (failed[chosen] or by_case[chosen])
    else:
        if case not in found.cases:
            raise HuntError(f"finding {found.number} has no case with the id \"{case}\"")
        chosen, pool = case, by_case[case]
    if chosen is None or not pool:
        raise ConfirmError(f"finding {found.number} cannot be replayed: its confirm arm, "
                           f"{found.arm}, holds no run of the case to take a seed from",
                           reason="unknown finding")
    seed = pool[0].seed
    ran, calls, error = _run_unstored(hunt, found.arm, chosen, found.condition, seed=seed)
    return Replayed(finding=found.number, case=chosen, seed=seed, outcome=ran.outcome,
                    kind=ran.kind, calls=calls, error=error)


# ---------------------------------------------------------------------------
# recheck
# ---------------------------------------------------------------------------


def _rechecks(hunt: Hunt, stored: _Stored) -> dict[int, set[str]]:
    """Each recheck the store holds an arm of, by its number, with its arms' own words."""
    found: dict[int, set[str]] = {}
    prefix = f"{hunt.name}-recheck-"
    for run_id in stored.runs():
        if not run_id.startswith(prefix):
            continue
        number = run_id[len(prefix):].split("-", 1)[0]
        if number.isascii() and number.isdigit():
            found.setdefault(int(number), set()).add(_word(hunt, run_id))
    return found


def recheck(hunt: Hunt, *, old: Target | None = None,
            on_progress: Callable[[int, int], None] | None = None) -> list[Rechecked]:
    """Recheck every finding the hunt has written on the agent as it is now: the hunt opened
    with the agent changed. Hands back one ``Rechecked`` for each finding, in their order, and
    none for a hunt with no finding.

    Each finding's condition is run over the cases and repeats of its reference arm, in the arm
    ``recheck-<n>-<finding>``, where ``n`` is one above the highest recheck stored; a recheck
    that stopped short is finished first instead, and no new one is begun; a finding confirmed
    after a recheck began is not part of it, and does not make it unfinished. Trace is then asked
    once for each finding, the reference arm against the new one, and its p-values are adjusted
    across the findings with Prove's ``bh``. The phrase is read from Trace's verdict and
    direction: *different* at an adjusted p-value at or under ``q`` is ``fails less`` or
    ``fails more``; *different* above it is ``no significant difference``; the other two are
    Trace's own words.

    With ``old``, a way in over the agent as it was, both are run now, side by side: the old
    one in ``recheck-<n>-<finding>-old``, first, and Trace compares those two, so there is no
    gap between the runs to report. Without it, ``gap_days`` is the time between the reference
    arm and this one, as Trace gives it.

    Refused before any run: Trace missing, at another version or printing another schema; and,
    with the reason ``unfinished``, a recheck that stopped short and was begun the other way
    (with ``old`` and now without, or without and now with), and, without ``old``, a finding
    whose reference arm has runs missing, which only the agent as it was can run. ``trace
    answer`` comes after the arms ran, which are kept."""
    hunt = _of(hunt)
    _check_progress(on_progress)
    stored = _Stored(hunt)
    findings = _written(hunt)
    if not findings:
        return []
    sizes = {finding.number: len(finding.cases) * finding.repeats for finding in findings}

    held = _rechecks(hunt, stored)
    number = max(held, default=0)
    side_by_side = old is not None
    begun_with_old = any(word.endswith("-old") for word in held.get(number, ()))
    words = {finding.number: f"recheck-{number}-{finding.number}" for finding in findings}
    # The findings a stored recheck was begun for: those whose reference arm was made before
    # its first arm was. A finding confirmed since is not part of it, so a recheck that was
    # finished stays finished when a later confirm stage adds a finding.
    began = min((when for when in (stored.made(f"{hunt.name}-{word}")
                                   for word in held.get(number, ())) if when is not None),
                default=None)
    its_own = [one for one in findings
               if began is not None and (stored.made(one.reference) or began) <= began]
    unfinished = number > 0 and not all(
        stored.holds(f"{hunt.name}-{words[one.number]}", sizes[one.number])
        and (not begun_with_old
             or stored.holds(f"{hunt.name}-{words[one.number]}-old", sizes[one.number]))
        for one in its_own)
    if unfinished and begun_with_old != side_by_side:
        raise ConfirmError(
            f'recheck {number} of the hunt "{hunt.name}" stopped short, and was begun '
            + ("with the old agent beside the new one: give the old agent again to finish it"
               if begun_with_old else
               "without the old agent: finish it as it was begun before one side by side"),
            reason="unfinished")
    if not unfinished:
        number += 1
        words = {finding.number: f"recheck-{number}-{finding.number}" for finding in findings}
    if not side_by_side:
        short = [one.number for one in findings if not stored.holds(one.reference,
                                                                    sizes[one.number])]
        if short:
            raise ConfirmError(
                f"the reference run of finding {short[0]} has runs missing, and the agent as "
                "it is now cannot finish it: finish it on the agent the finding was confirmed "
                "on, or recheck with the old agent side by side", reason="unfinished")
    _check_trace(hunt)

    old_hunt = None if old is None else open_hunt(
        hunt.settings, target=old, cases=hunt.cases, name=hunt.name, existing=True)
    progress = _Progress(on_progress)
    progress.total = sum(sizes.values()) * (2 if side_by_side else 1)
    for finding in findings:
        cells = sizes[finding.number]
        if old_hunt is not None:
            run_arm(old_hunt, f"{words[finding.number]}-old", finding.cases, finding.condition,
                    repeats=finding.repeats, on_progress=progress.arm(cells))
        run_arm(hunt, words[finding.number], finding.cases, finding.condition,
                repeats=finding.repeats, on_progress=progress.arm(cells))

    settings = hunt.settings.confirm
    asked: list[tuple[Finding, str, str, Mapping[str, Any]]] = []
    for finding in findings:
        now = f"{hunt.name}-{words[finding.number]}"
        before = f"{now}-old" if side_by_side else finding.reference
        doc = ask_trace(hunt.store, before, now, max_difference=settings.max_difference,
                        folder=hunt.folder)
        if doc is None:
            raise _no_answer("it printed nothing", before, now)
        asked.append((finding, before, now, doc))

    adjusted = _adjusted([doc for _, _, _, doc in asked], settings.q)
    rechecked: list[Rechecked] = []
    for (finding, before, now, doc), after in zip(asked, adjusted, strict=True):
        said, direction = doc["verdict"], doc["direction"]
        if said == _DIFFERENT and after <= settings.q:
            phrase = "fails less" if direction == _LESS else "fails more"
        elif said == _DIFFERENT:
            phrase = "no significant difference"
        else:
            phrase = said
        gap = doc["gap_seconds"]
        rechecked.append(Rechecked(
            finding=finding.number, condition=finding.condition, phrase=phrase, before=before,
            now=now, rate_before=_rate(doc, "old"), rate_now=_rate(doc, "new"),
            difference=float(doc["difference"]["points"]),
            lo=_optional(doc["difference"]["lo"]), hi=_optional(doc["difference"]["hi"]),
            p=float(doc["test"]["p"]), adjusted_p=after,
            repeats_needed=(doc["guidance"] or {}).get("repeats"),
            left_out=_read_only(doc["inputs"]["left_out"]),
            no_outcome=stored.no_outcome((before, now), finding.cases),
            gap_days=None if side_by_side or gap is None else float(gap) / _DAY,
            trace=_shown_command(before, now, hunt.store, settings.max_difference)))
    return rechecked
