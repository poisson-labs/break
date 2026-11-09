"""What an extension page's example is called by, and what an example tries to connect to, for
`tests/test_release_extending.py` and `tests/test_release_examples.py`.

Put first on `PYTHONPATH` for the example's process (and every process it starts), this runs
the network guard (`tests/_guard/sitecustomize.py`). With `BREAK_TEST_NETWORK_LOG` set, each
connection attempted is written to that file as one line before the guard refuses it, so an
attempt the program swallows is still seen. With `BREAK_TEST_PROBE_LOG` and
`BREAK_TEST_PROBE_PROGRAM` set, it records each call into a function written in the example's
file that comes straight from a module of Break: the function's name, the calling module, which
of the four interfaces its `self` answers to, the type of each positional argument, and the type
of what it returned (`NoneType` when it raised). One JSON line a call, appended to the log when
the call ends. It changes nothing the example does.
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

_NETWORK = os.environ.get("BREAK_TEST_NETWORK_LOG")
if _NETWORK:
    import socket

    def _logged(refuse: Any) -> Any:
        def attempt(*args: Any, **kwargs: Any) -> Any:
            with open(_NETWORK, "a", encoding="utf-8") as log:
                log.write(f"{os.getpid()} {args[1:2] or args[:1]!r}\n")
            return refuse(*args, **kwargs)
        return attempt

    socket.socket.connect = _logged(socket.socket.connect)  # type: ignore[method-assign]
    socket.socket.connect_ex = _logged(socket.socket.connect_ex)  # type: ignore[method-assign]
    socket.create_connection = _logged(socket.create_connection)  # type: ignore[assignment]
    socket.getaddrinfo = _logged(socket.getaddrinfo)  # type: ignore[assignment]

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
    _open: dict[int, dict[str, Any]] = {}

    def _profile(frame: Any, event: str, arg: Any) -> None:
        if frame.f_code.co_filename not in _names:
            return
        if event == "return":
            record = _open.pop(id(frame), None)
            if record is not None:
                record["returned"] = type(arg).__name__
                with open(_LOG, "a", encoding="utf-8") as log:  # type: ignore[arg-type]
                    log.write(json.dumps(record) + "\n")
            return
        if event != "call":
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
        _open[id(frame)] = record

    sys.setprofile(_profile)
    threading.setprofile(_profile)
