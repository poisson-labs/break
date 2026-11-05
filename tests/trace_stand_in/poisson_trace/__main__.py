"""`python -m poisson_trace`, as the stand-in answers it: `--version`, and `fix-check` from recorded documents.

Only the call Break is ruled to make is taken (ruling 4 of `evidence/bk7/open-points.md`):

    fix-check OLD NEW --store STORE --event failed --inputs all --max-mde X --json

each flag once, in any order, and nothing else; anything else is an exit of 2 and an `error:` line, as Trace's own
command line refuses a word it does not know. The answer is the document the pinned Trace printed for two runs with
the same counts: for each case, its failed runs, its runs with an outcome and its runs with none, in each run. Counts
with no recorded document are an exit of 99, so a wrong design fails loudly. Two runs of at most two rows each, which
no scenario has, are Break's probe of the schema (ruling 5), and get the recorded probe's document.

The environment says the rest, each set by `tests/confirm_support.py`:

- `BREAK_TEST_TRACE_LOG`: a file each call is added to as one JSON line: its words, its folder, the interpreter it
  ran under, and whether it was the probe;
- `BREAK_TEST_TRACE_RECORDED`: the recorded documents, one JSON line each: `key`, `exit`, `stdout`, `stderr`;
- `BREAK_TEST_TRACE_VERSION`: what `--version` says; else `poisson_break.confirm.TRACE_VERSION`;
- `BREAK_TEST_TRACE_PATCH`: changes to the answer, a JSON object from the new run's arm word (`confirm-1`, which
  never matches the probe, or `*` for every call, the probe's among them) to `{"set": {"dotted.key": value}, "drop": ["dotted.key"], "exit": code, "stdout": text}`.
"""

from __future__ import annotations

import importlib
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

FLAGS = ("--store", "--event", "--inputs", "--max-mde")
PROBE = "probe"


def _log(entry: dict[str, Any]) -> None:
    path = os.environ.get("BREAK_TEST_TRACE_LOG")
    entry = {**entry, "python": sys.executable}
    if path:
        with open(path, "a", encoding="utf-8") as out:
            out.write(json.dumps(entry) + "\n")


def _version() -> str:
    given = os.environ.get("BREAK_TEST_TRACE_VERSION")
    if given is not None:
        return given
    return str(importlib.import_module("poisson_break.confirm").TRACE_VERSION)


def _counts(store: Path, run: str) -> dict[str, list[int]]:
    from poisson_prove.store import Store

    frame = Store(store).read(run)
    out: dict[str, list[int]] = {}
    for row in frame.to_dict("records"):
        case = str(row["meta"]["poisson_break"]["case"])
        held = out.setdefault(case, [0, 0, 0])
        outcome = row["outcome"]
        if outcome is None or (isinstance(outcome, float) and outcome != outcome):
            held[2] += 1
        else:
            held[1] += 1
            held[0] += outcome == "failed"
    return out


def key_of(old: dict[str, list[int]], new: dict[str, list[int]], max_mde: float) -> str:
    return json.dumps({"old": old, "new": new, "max_mde": max_mde}, sort_keys=True)


def _recorded() -> dict[str, dict[str, Any]]:
    path = Path(os.environ.get("BREAK_TEST_TRACE_RECORDED")
                or Path(__file__).resolve().parents[2] / "trace_recorded" / "fix_check_7e6fef6.jsonl")
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            held = json.loads(line)
            found[held["key"]] = held
    return found


def answer(store: Path, old: str, new: str, max_mde: float) -> dict[str, Any]:
    """The recorded answer for two runs of a store, and whether it is the probe's."""
    a, b = _counts(store, old), _counts(store, new)
    recorded = _recorded()
    if sum(map(sum, a.values())) <= 2 and sum(map(sum, b.values())) <= 2:
        return {**recorded[PROBE], "probe": True}
    found = recorded.get(key_of(a, b, max_mde))
    if found is None:
        return {"exit": 99, "stdout": "", "stderr": f"stand-in: no recorded document for {key_of(a, b, max_mde)}\n",
                "probe": False}
    return {**found, "probe": False}


def _set(doc: dict[str, Any], dotted: str, value: Any) -> None:
    *path, last = dotted.split(".")
    for part in path:
        doc = doc[part]
    doc[last] = value


def _drop(doc: dict[str, Any], dotted: str) -> None:
    *path, last = dotted.split(".")
    for part in path:
        doc = doc[part]
    del doc[last]


def _patched(found: dict[str, Any], new: str) -> dict[str, Any]:
    patch = json.loads(os.environ.get("BREAK_TEST_TRACE_PATCH") or "{}")
    for word, change in patch.items():
        if word != "*" and (found["probe"] or not new.endswith("-" + word)):
            continue
        if "stdout" in change:
            found = {**found, "stdout": change["stdout"]}
        elif change.get("set") or change.get("drop"):
            doc = json.loads(found["stdout"])
            for dotted, value in change.get("set", {}).items():
                _set(doc, dotted, value)
            for dotted in change.get("drop", []):
                _drop(doc, dotted)
            found = {**found, "stdout": json.dumps(doc, indent=2) + "\n"}
        if "exit" in change:
            found = {**found, "exit": change["exit"]}
    return found


def main(argv: list[str]) -> int:
    if argv == ["--version"]:
        _log({"argv": argv, "cwd": os.getcwd()})
        print(f"poisson-trace {_version()} (poisson-prove 0.1.3, Python {platform.python_version()})")
        return 0
    if len(argv) < 3 or argv[0] != "fix-check":
        _log({"argv": argv, "cwd": os.getcwd()})
        print(f"error: the stand-in answers fix-check and --version, not {argv!r}", file=sys.stderr)
        return 2
    old, new, rest = argv[1], argv[2], argv[3:]
    given: dict[str, str] = {}
    json_flag = 0
    i = 0
    while i < len(rest):
        word = rest[i]
        if word == "--json":
            json_flag += 1
            i += 1
        elif word in FLAGS and i + 1 < len(rest) and word not in given:
            given[word] = rest[i + 1]
            i += 2
        else:
            _log({"argv": argv, "cwd": os.getcwd()})
            print(f"error: unrecognized arguments: {word}", file=sys.stderr)
            return 2
    if (json_flag != 1 or set(given) != set(FLAGS) or given["--event"] != "failed" or given["--inputs"] != "all"):
        _log({"argv": argv, "cwd": os.getcwd()})
        print("error: the stand-in takes exactly --store, --event failed, --inputs all, --max-mde and --json",
              file=sys.stderr)
        return 2
    found = answer(Path(given["--store"]), old, new, float(given["--max-mde"]))
    _log({"argv": argv, "cwd": os.getcwd(), "probe": found["probe"]})
    found = _patched(found, new)
    sys.stdout.write(found["stdout"])
    sys.stderr.write(found.get("stderr", ""))
    return int(found["exit"])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
