"""A library name stood in for in the command's child process, so a test can see the command use it.

Taylor's yes to BK8 points 37 and 39 (2026-11-07) gave the command public names to take what it needs from:
`Replayed.error` for a replay that was not counted, and `hunt.run_once` for `doctor --run` (point 40's
`settings.install_command` went with hands-on issue 17, 2026-11-13). A test holds the command to each by standing in for it with an answer no other source
could give, and reading that answer in what the command printed.

`spying(folder, body)` writes a `sitecustomize` module into `folder` and hands back the environment that puts it first
on the child's import path. Python imports it at start-up, before the command: it runs the tests' network guard
(`tests/_guard/sitecustomize.py`, which it shadows) and then `body`, which replaces a name on its module. A stand-in
writes each call it takes to the JSON Lines file `BREAK_TEST_SPY_LOG` names; `spied(env)` reads them back.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.commands_support import Project, child_env

GUARD = Path(__file__).resolve().parent / "_guard" / "sitecustomize.py"

_HEAD = f'''
import json as _json
import os as _os
exec(compile(open({str(GUARD)!r}, encoding="utf-8").read(), {str(GUARD)!r}, "exec"))


def _log(**facts):
    with open(_os.environ["BREAK_TEST_SPY_LOG"], "a", encoding="utf-8") as handle:
        handle.write(_json.dumps(facts, default=str) + "\\n")
'''

#: `hunt.run_once` stood in for: the case is not run, and the row says it failed with a kind no check has.
RUN_ONCE = '''
import poisson_break.hunt as _hunt
from poisson_break.changes import Condition as _Condition


def run_once(settings, *, target, case):
    ident = case["id"] if hasattr(case, "keys") else case
    _log(name="run_once", case=dict(case) if hasattr(case, "keys") else case, entry=settings.target.entry)
    return _hunt.RunRow(condition=_Condition(changes=()), case=str(ident), seed=0, outcome="failed",
                        kind="spied_kind")


_hunt.run_once = run_once
'''

#: `hunt.run_once` stood in for: the case is not run, and a tool no settings file names is refused (point 42).
RUN_ONCE_REFUSED = '''
import poisson_break.hunt as _hunt
from poisson_break.apply import ToolRefused as _ToolRefused


def run_once(settings, *, target, case):
    _log(name="run_once", case=dict(case) if hasattr(case, "keys") else case)
    raise _ToolRefused('the agent called "spied_tool", which the settings do not class as read, write or off',
                       tool="spied_tool")


_hunt.run_once = run_once
'''

#: `changes.check_capabilities` stood in for: every change is one the way in can make, so `doctor` gets past the
#: conversation's moves on a `rollout` target and on to its run (point 46). Put before another body.
CAPABILITIES_TAKEN = '''
import poisson_break.changes as _changes


def check_capabilities(condition, capabilities):
    _log(name="check_capabilities", condition=str(condition))
    return None


_changes.check_capabilities = check_capabilities
'''

#: `confirm.replay` wrapped: a run that was not counted carries an error line no run wrote.
REPLAY_ERROR = '''
import dataclasses as _dataclasses
import poisson_break.confirm as _confirm

_real_replay = _confirm.replay
SPIED_ERROR = "the spied line of error, from Replayed.error"


def replay(*args, **kwargs):
    done = _real_replay(*args, **kwargs)
    _log(name="replay", outcome=done.outcome)
    if done.outcome == "not counted":
        return _dataclasses.replace(done, error=SPIED_ERROR)
    return done


_confirm.replay = replay
'''

SPIED_ERROR = "the spied line of error, from Replayed.error"


def spying(proj: Project, folder: Path, body: str) -> dict[str, str]:
    """The environment changes that run `body` in the command's child, its calls logged under `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "sitecustomize.py").write_text(_HEAD + body, encoding="utf-8")
    return {"PYTHONPATH": f"{folder}:" + child_env(proj)["PYTHONPATH"],
            "BREAK_TEST_SPY_LOG": str(folder / "calls.jsonl")}


def spied(env: dict[str, str]) -> list[dict[str, Any]]:
    log = Path(env["BREAK_TEST_SPY_LOG"])
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


__all__ = ["CAPABILITIES_TAKEN", "REPLAY_ERROR", "RUN_ONCE", "RUN_ONCE_REFUSED", "SPIED_ERROR", "spied", "spying"]
