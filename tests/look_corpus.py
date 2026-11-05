"""The conformance test's corpus: every invocation the look is held to.

**A later module adds its invocations here and changes nothing else.** The test in
`test_look_conformance.py` walks `CORPUS`, and the checks in `look_conformance.py` know nothing of any
particular verb. The commands module adds each verb's `--help`, each documented example and its bad
inputs, as `Invocation`s with no `program`, which run `python -m poisson_break`.

Fields:
- `name`: unique; it names the test.
- `argv`: the words after the program.
- `kind`: `result`, a verdict line first on stdout; `help`, a description and an example on stdout, exit
  0; `version`, one line, exit 0; `bad`, one `error:` line and nothing on stdout.
- `code`: the exit code this invocation must give.
- `program`: what is run, a list of words; `()` for `python -m poisson_break`.
- `takes_plain`: whether the command line takes `--plain`, which adds the `--plain` way.
- `has_json`: whether the command line takes `--json`, which adds the JSON way.
- `setup`: called with an empty folder the invocation runs in, to write what it reads.
- `env`: the variables to set for this invocation, on top of a clean environment.
- `other_stderr`: a pattern for what else may be on stderr (progress, a question), beyond problems.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from tests.look_results import RESULTS
from tests.look_support import CHILD


@dataclass(frozen=True)
class Invocation:
    name: str
    argv: tuple[str, ...]
    kind: str = "result"
    code: int = 0
    program: tuple[str, ...] = ()
    takes_plain: bool = True
    has_json: bool = False
    setup: Callable[[Path], None] | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    other_stderr: str | None = None

    def __str__(self) -> str:
        return self.name


def _child(*argv: str) -> tuple[str, ...]:
    return (sys.executable, str(CHILD), *argv)


CORPUS: list[Invocation] = [
    # the command as it stands, before its verbs: the front door itself
    Invocation("command-help", ("--help",), kind="help"),
    Invocation("command-version", ("--version",), kind="version"),
    Invocation("command-unknown-flag", ("--bogus",), kind="bad", code=2),
    Invocation("command-unknown-verb", ("bogus",), kind="bad", code=2),
    Invocation("command-abbreviated", ("--vers",), kind="bad", code=2),
    # every result of the corpus, printed as a verb prints it
    *[Invocation(f"result-{name}", (), program=_child("result", name), has_json=True)
      for name in RESULTS],
    # problems
    Invocation("refused", (), kind="bad", code=1, program=_child("refuse")),
    Invocation("usage", (), kind="bad", code=2, program=_child("usage")),
    Invocation("warning", (), program=_child("warn")),
]
