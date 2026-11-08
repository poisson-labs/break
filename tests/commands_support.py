"""What the commands' tests share: a project folder, the command run in a child on real streams, and reading back what
it printed and what it left on disk.

**A project** is a folder holding `break.toml` and `cases.jsonl`, the folder the command runs in, as a user has it
after `init`. Its target is a plain Prove target from `tests/commands_targets.py`, which writes each run it makes to
`runs.jsonl` beside the project, so a test counts what a command spent. `home` is the child's own home folder, so the
errors log of an unexpected failure lands where a test can see it.

**The command** is `python -m poisson_break` in a child process, on pipes unless a test asks for terminals, with the
look's switch holding (`look_support.pretty_env`) and the repository's `src` first on the import path, so the child
runs the tree the tests are in. Nothing is mocked: the child reads `break.toml` from its own folder, as a user's does.

**What is read back is structure and facts, never prose** (spec §0): the verdict line's word and sentence, which
stream a line is on, a `next:` line's command, the numbers and names a line carries, the exit code, and the files
under `break-runs/`. Where a test looks for a number it looks for it as the look prints it (`fmt_rate`, `fmt_count`).
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tests.conftest import GUARD, REPO
from tests.look_support import PIPED, VERDICT_LINE, Ran, Streams, launch, pretty_env, strip

PROG = "poisson-break"
SEED = 20261106

CODES = {"done": 0, "refused": 1, "usage": 2, "stopped": 3, "check": 4, "interrupted": 130}

#: A run of hex that reads as a hash: eight or more characters, holding a digit and a letter (BK8.7).
HEX = re.compile(r"(?<![0-9A-Za-z])(?=[0-9a-fA-F]*[0-9])(?=[0-9a-fA-F]*[a-fA-F])[0-9a-fA-F]{8,}(?![0-9A-Za-z])")

#: The faults the commands' scenarios allow: each raises where the tool's own failure would be, so the desk sees it,
#: and none sleeps (`slow` holds a call for thirty seconds).
FAULTS = ("error", "timeout", "rate_limited")

#: The eight verbs of spec §9.1.
VERBS = ("init", "doctor", "hunt", "confirm", "findings", "replay", "recheck", "catalog")


# ---------------------------------------------------------------------------
# settings and cases, as a user writes them
# ---------------------------------------------------------------------------


def toml(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, float) and math.isinf(value):
        return "inf"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, Mapping):
        return "{ " + ", ".join(f"{json.dumps(k)} = {toml(v)}" for k, v in value.items()) + " }"
    return "[" + ", ".join(toml(v) for v in value) + "]"


def settings_text(*, entry: str = "tests.commands_targets:desk", tools: Mapping[str, Any] | None = None,
                  fails: Mapping[str, Any] | None = None, vary: Mapping[str, Any] | None = None,
                  search: Mapping[str, Any] | None = None, confirm: Mapping[str, Any] | None = None,
                  limits: Mapping[str, Any] | None = None, env: Mapping[str, Sequence[str]] | None = None,
                  folder: str = "break-runs") -> str:
    """A `break.toml` for the desk: its two tools read, a run failing when the desk reports `unresolved`, the three
    faults of `FAULTS` allowed and no input operator, small numbers everywhere, and hunts kept under `folder`."""
    tables: dict[str, Mapping[str, Any]] = {
        "target": {"kind": "rollout", "entry": entry, "cases": "cases.jsonl"},
        "tools": dict(tools) if tools is not None else {"lookup_order": "read", "check_policy": "read"},
        "fails": {"outcomes": ["unresolved"], "run_seconds": 30, **(fails or {})},
        "vary": {"tools": list(FAULTS), "inputs": [], "max_call": 1, **(vary or {})},
        "search": {"strategy": "screen", "runs": 60, "control_repeats": 2, "cases_per_condition": 2, "seed": SEED,
                   **(search or {})},
        "confirm": {"candidates": 8, "repeats": 3, "max_difference": 0.2, "q": 0.05, **(confirm or {})},
        "limits": {"hours": 2, **(limits or {})},
        "output": {"folder": folder},
    }
    lines = ["version = 1"]
    for table, keys in tables.items():
        lines += ["", f"[{table}]"] + [f"{json.dumps(key)} = {toml(value)}" for key, value in keys.items()]
    if env:
        lines += ["", "[vary.env]"] + [f"{json.dumps(key)} = {toml(list(v))}" for key, v in env.items()]
    return "\n".join(lines) + "\n"


def cases(n: int, *, first: int = 1, **keys: Any) -> list[dict[str, Any]]:
    """`n` cases, `k<first>` on, each with `keys`."""
    return [{"id": f"k{i}", "input": f"Where is order {i}?", **keys} for i in range(first, first + n)]


# A desk weak to `error` on its one lookup and to nothing else: every run under `error` fails, no other runs do.
WEAK_TO_ERROR = cases(3, weak_to=["error"])
# A desk no fault moves: nothing fails, under any condition.
SOUND = cases(3)


# ---------------------------------------------------------------------------
# a project, and the command run in it
# ---------------------------------------------------------------------------


@dataclass
class Project:
    folder: Path
    home: Path
    runs_log: Path
    env: dict[str, str] = field(default_factory=dict)

    @property
    def settings(self) -> Path:
        return self.folder / "break.toml"

    @property
    def hunts(self) -> Path:
        return self.folder / "break-runs"

    def hunt(self, name: str) -> Path:
        return self.hunts / name

    def runs(self) -> list[dict[str, Any]]:
        """Every run a target made, in order, read from the log the targets write."""
        if not self.runs_log.exists():
            return []
        return [json.loads(text) for text in self.runs_log.read_text(encoding="utf-8").splitlines() if text]

    def write(self, settings: str | None = None, case_list: Iterable[Mapping[str, Any]] | None = None) -> None:
        if settings is not None:
            self.settings.write_text(settings, encoding="utf-8")
        if case_list is not None:
            (self.folder / "cases.jsonl").write_text("".join(json.dumps(c) + "\n" for c in case_list),
                                                     encoding="utf-8")


def project(tmp_path: Path, case_list: Iterable[Mapping[str, Any]] | None = None, *, write: bool = True,
            **settings: Any) -> Project:
    """A project folder under `tmp_path`, with `break.toml` from `settings_text(**settings)` and the cases, unless
    `write` is false."""
    folder = tmp_path / "project"
    home = tmp_path / "home"
    folder.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    made = Project(folder=folder, home=home, runs_log=tmp_path / "runs.jsonl")
    if write:
        made.write(settings_text(**settings), WEAK_TO_ERROR if case_list is None else case_list)
    return made


def child_env(proj: Project, **changes: str | None) -> dict[str, str]:
    """The child's environment: the look's switch holding, its home the project's, the tree's `src` first on the
    import path, and the targets' run log named."""
    env = pretty_env(HOME=str(proj.home))
    env["PYTHONPATH"] = os.pathsep.join([str(GUARD), str(REPO / "src"), str(REPO)])
    env["BREAK_TEST_RUNS_LOG"] = str(proj.runs_log)
    env.update(proj.env)
    for name, value in changes.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    return env


def cli(proj: Project, *words: str, streams: Streams = PIPED, timeout: float = 240.0,
        interrupt_on: str | None = None, prog: str | None = None, **env: str | None) -> Ran:
    """`python -m poisson_break <words>` in the project's folder. With `prog`, the command is run through
    `main(argv, prog=prog)`, as a shared `poisson break` would run it."""
    if prog is None:
        argv = [sys.executable, "-m", "poisson_break", *words]
    else:
        code = ("import sys; from poisson_break.cli import main; "
                f"sys.exit(main(sys.argv[1:], prog={prog!r}))")
        argv = [sys.executable, "-c", code, *words]
    return launch(argv, child_env(proj, **env), streams, cwd=proj.folder, timeout=timeout,
                  interrupt_on=interrupt_on)


# ---------------------------------------------------------------------------
# reading what was printed
# ---------------------------------------------------------------------------


def verdict(ran: Ran) -> tuple[str, str]:
    """The verdict line's word and sentence: the first line on stdout."""
    first = strip(ran.out).split("\n", 1)[0]
    match = VERDICT_LINE.match(first)
    assert match is not None, f"the first line on stdout is not a verdict line:\n{ran}"
    return match.group(1), match.group(2)


def out_lines(ran: Ran) -> list[str]:
    return strip(ran.out).splitlines()


def err_lines(ran: Ran) -> list[str]:
    return strip(ran.err).splitlines()


def errors(ran: Ran) -> list[str]:
    return [text for text in err_lines(ran) if text.startswith("error: ")]


def notes(ran: Ran) -> list[str]:
    return [text for text in err_lines(ran) if text.startswith("note: ")]


def nexts(ran: Ran) -> list[str]:
    """The commands of every `next:` line, on either stream."""
    found = []
    for text in [*out_lines(ran), *err_lines(ran)]:
        match = re.match(r"\s*next:\s+(.*\S)", text)
        if match:
            found.append(match.group(1))
    return found


def refused_once(ran: Ran, code: int) -> str:
    """The one `error:` line of a refusal with `code`: nothing on stdout, one `error:` line on stderr and the rest of
    stderr `next:` lines, and no traceback. Hands back the line."""
    assert ran.exit == code, f"exit {ran.exit}, wanted {code}:\n{ran}"
    assert ran.out == "", f"a refusal prints nothing on stdout:\n{ran}"
    lines = err_lines(ran)
    assert lines and lines[0].startswith("error: "), f"stderr does not open with error:\n{ran}"
    assert len(errors(ran)) == 1, f"not one error line:\n{ran}"
    assert all(re.match(r"\s+next:\s+\S", text) for text in lines[1:]), f"more than error and next lines:\n{ran}"
    assert "Traceback" not in ran.err
    return lines[0]


def numbers(text: str) -> list[str]:
    """Every number written in `text`, as written: `0.150`, `1,020`, `$5.00`."""
    return re.findall(r"\$?\d[\d,]*(?:\.\d+)?", text)


def holds_number(text: str, number: str) -> bool:
    """Whether `text` writes `number` as a number of its own, not inside a longer one."""
    return re.search(rf"(?<![\d.,$]){re.escape(number)}(?![\d]|[.,]\d)", text) is not None


def hashes(text: str) -> list[str]:
    return HEX.findall(strip(text))


def json_document(ran: Ran) -> dict[str, Any]:
    """Stdout as one strict JSON document."""
    def refuse(word: str) -> Any:
        raise ValueError(f"{word} is not strict JSON")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [k for k, _ in items]
        assert len(keys) == len(set(keys)), f"a key twice: {keys}"
        return dict(items)

    document = json.loads(ran.out, parse_constant=refuse, object_pairs_hook=pairs)
    assert isinstance(document, dict), ran.out
    return document


# ---------------------------------------------------------------------------
# reading what was left on disk
# ---------------------------------------------------------------------------


def hunt_names(proj: Project) -> list[str]:
    if not proj.hunts.exists():
        return []
    return sorted(p.name for p in proj.hunts.iterdir() if p.is_dir())


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def candidates(proj: Project, hunt: str) -> list[str]:
    """The conditions of a hunt's `candidates.json`, best first."""
    return [c["condition"] for c in read_json(proj.hunt(hunt) / "candidates.json")["candidates"]]


def stored(proj: Project, hunt: str, arm: str) -> list[dict[str, Any]]:
    """An arm's rows, read through Prove's own store."""
    from poisson_prove.store import Store

    frame = Store(proj.hunt(hunt) / "store").read(f"{hunt}-{arm}")
    return list(frame.to_dict("records"))


def store_runs(proj: Project, hunt: str) -> list[str]:
    from poisson_prove.store import Store

    path = proj.hunt(hunt) / "store"
    return sorted(Store(path).runs()) if path.exists() else []


def files_under(folder: Path) -> dict[str, bytes]:
    """Every file under `folder`, by its path from there, with its bytes."""
    if not folder.exists():
        return {}
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def paths_under(folder: Path) -> list[str]:
    """Every path under `folder`, folders as well as files, by its path from there: an empty folder made shows."""
    if not folder.exists():
        return []
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*"))


def condition_name(text: str) -> str:
    from poisson_break.changes import name, parse

    return str(name(parse(text)))


def on(fault: str, call: int = 1, tool: str = "lookup_order") -> str:
    return f"tool:{tool}#{call}={fault}"




def prepared(proj: Project, conditions: Sequence[str], *, name: str = "desk-1") -> Any:
    """A hunt made through the library, in the project's own folder, as `hunt` would leave it for `confirm`: opened
    under the project's settings and target, its control stage run, and `conditions` written as its candidates, best
    first. The target runs in this process, so its runs are not in the project's log."""
    import contextlib

    from poisson_break.changes import parse
    from poisson_break.confirm import write_candidates
    from poisson_break.hunt import control, load_target, open_hunt
    from poisson_break.settings import load, read_cases

    with contextlib.chdir(proj.folder):
        settings = load(proj.settings)
        made = open_hunt(settings, target=load_target(settings), cases=read_cases(Path(settings.target.cases)),
                         name=name)
        control(made)
        if conditions:
            write_candidates(made, [parse(text) for text in conditions])
    return made


def opened(proj: Project, name: str) -> Any:
    """A hunt of the project's, opened again in this process to read it through the library."""
    import contextlib

    from poisson_break.hunt import load_target, open_hunt
    from poisson_break.settings import load, read_cases

    with contextlib.chdir(proj.folder):
        settings = load(proj.settings)
        return open_hunt(settings, target=load_target(settings), cases=read_cases(Path(settings.target.cases)),
                         name=name, existing=True)


def findings_of(proj: Project, name: str) -> list[Any]:
    """Each finding file of a hunt, read through the confirm module, in number order."""
    import contextlib

    from poisson_break.confirm import read_finding

    folder = proj.hunt(name) / "findings"
    numbers = sorted(int(p.stem) for p in folder.glob("*.toml")) if folder.exists() else []
    with contextlib.chdir(proj.folder):
        made = opened(proj, name)
        return [read_finding(made, n) for n in numbers]


# A desk whose control fails half its runs, weak to `error` (every run fails), made to fail less by `rate_limited` (no
# run fails), and unmoved by `timeout`: three candidates, three answers from the pinned Trace at four repeats (one case
# of the twelve fails all three control runs and is set aside): `confirmed`, `too small to tell` and `not confirmed`
# with the note `failed less`.
MIXED = cases(12, rate=0.5, weak_to=["error"], less_to=["rate_limited"])
MIXED_SETTINGS: dict[str, Any] = {"confirm": {"repeats": 4}, "search": {"control_repeats": 3, "runs": 400}}
MIXED_CANDIDATES = (on("error"), on("timeout"), on("rate_limited"))


# ---------------------------------------------------------------------------
# results on stdout
# ---------------------------------------------------------------------------

REAL = "Break calls your tools for real"


def results(text: str) -> list[list[str]]:
    """Stdout as results: each starts at an unindented verdict line and holds the lines under it."""
    blocks: list[list[str]] = []
    for line in strip(text).splitlines():
        if VERDICT_LINE.match(line):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
    return blocks


def result_of(ran: Any, word: str) -> list[str]:
    found = [b for b in results(ran.out) if VERDICT_LINE.match(b[0]).group(1) == word]  # type: ignore[union-attr]
    assert len(found) == 1, f"not one {word!r} result:\n{ran}"
    return found[0]


def detail(block: list[str]) -> list[str]:
    """A result's detail lines: indented, `next:` lines left out."""
    return [line for line in block[1:] if line.startswith(" ") and not line.strip().startswith("next:")]


def row(block: list[str], label: str) -> str:
    """The detail line whose first word is `label`."""
    found = [line for line in detail(block) if line.split()[:1] == [label]]
    assert len(found) == 1, f"no single {label!r} line in {block}"
    return found[0]


__all__ = [name for name in dir() if not name.startswith("_")]
