"""What an extension page's example is called by, for `tests/test_release_extending.py`.

Put first on `PYTHONPATH` for the example's process (and every process it starts), this runs
the network guard (`tests/_guard/sitecustomize.py`) and then, when `BREAK_TEST_PROBE_LOG` and
`BREAK_TEST_PROBE_PROGRAM` are set, records each call into a function written in the example's
file that comes straight from a module of Break: the function's name, the calling module, which
of the four interfaces its `self` answers to, and the type of each positional argument. One JSON
line a call, appended to the log. It changes nothing the example does.
"""

from __future__ import annotations

import json
import os
import runpy
import sys
import threading
from pathlib import Path
from typing import Any

runpy.run_path(str(Path(__file__).resolve().parent.parent / "_guard" / "sitecustomize.py"))

_LOG = os.environ.get("BREAK_TEST_PROBE_LOG")
_PROGRAM = os.environ.get("BREAK_TEST_PROBE_PROGRAM")


def _protocols(obj: Any) -> list[str]:
    if obj is None:
        return []
    from poisson_break import interfaces

    return [name for name in ("Fault", "Target", "Strategy", "Check")
            if isinstance(obj, getattr(interfaces, name))]


if _LOG and _PROGRAM:
    _names = {_PROGRAM, os.path.realpath(_PROGRAM)}

    def _profile(frame: Any, event: str, arg: Any) -> None:
        if event != "call" or frame.f_code.co_filename not in _names:
            return
        caller = frame.f_back
        module = caller.f_globals.get("__name__", "") if caller is not None else ""
        if module != "poisson_break" and not str(module).startswith("poisson_break."):
            return
        code = frame.f_code
        names = code.co_varnames[:code.co_argcount + code.co_kwonlyargcount]
        local = frame.f_locals
        record = {
            "name": code.co_name,
            "caller": module,
            "self": _protocols(local.get("self")) if "self" in names else [],
            "args": [type(local[n]).__name__ for n in names if n != "self" and n in local],
            "pid": os.getpid(),
        }
        with open(_LOG, "a", encoding="utf-8") as log:
            log.write(json.dumps(record) + "\n")

    sys.setprofile(_profile)
    threading.setprofile(_profile)
