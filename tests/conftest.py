"""Shared fixtures: the network guard, and how the tests run the command.

**The network guard.** Open-source Break opens no socket of its own and sends nothing anywhere.
The whole suite runs under a guard that fails any connection attempted from the test process,
and every child process the tests start gets the same guard through `PYTHONPATH`
(`tests/_guard/sitecustomize.py`). A test that needs the network does not belong here.

**Running the command.** `run_command(words)` runs the installed console script `poisson-break`;
`run_module(words)` runs `python -m poisson_break`. Both run with the guard, a clean environment
and no terminal. The in-process entry point is `poisson_break.cli.main(argv, prog=...)`, which
the tests call directly where the command's name must be rendered from `prog`.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

TESTS = Path(__file__).resolve().parent
GUARD = TESTS / "_guard"
REPO = TESTS.parent

# The two names the command is typed as. Every output a test reads must be rendered from the
# name given, and from no literal.
PROGS = ("poisson-break", "poisson break")


class NetworkGuard(RuntimeError):
    """Raised when something under test tries to open a connection."""


def _refuse(*args: Any, **kwargs: Any) -> Any:
    raise NetworkGuard(f"the network guard: a connection was attempted ({args!r})")


@pytest.fixture(autouse=True, scope="session")
def network_guard() -> Iterator[None]:
    """Every connection from the test process fails, for the whole session."""
    saved = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection,
             socket.getaddrinfo)
    socket.socket.connect = _refuse  # type: ignore[method-assign]
    socket.socket.connect_ex = _refuse  # type: ignore[method-assign]
    socket.create_connection = _refuse  # type: ignore[assignment]
    socket.getaddrinfo = _refuse  # type: ignore[assignment]
    try:
        yield
    finally:
        (socket.socket.connect, socket.socket.connect_ex, socket.create_connection,  # type: ignore[method-assign]
         socket.getaddrinfo) = saved


def guarded_env() -> dict[str, str]:
    """A clean environment for a child process: the guard on `PYTHONPATH`, no key-like variable,
    no terminal hints, UTF-8."""
    env = {k: v for k, v in os.environ.items()
           if not any(w in k.upper() for w in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
           and k not in ("PYTHONPATH", "CI", "NO_COLOR", "FORCE_COLOR", "TERM", "COLUMNS")}
    env["PYTHONPATH"] = str(GUARD)
    env["PYTHONIOENCODING"] = "utf-8"
    env["LC_ALL"] = "C.UTF-8"
    env["LANG"] = "C.UTF-8"
    return env


@dataclass(frozen=True)
class Ran:
    exit: int
    stdout: str
    stderr: str


def _run(argv: Sequence[str], cwd: Path | None = None) -> Ran:
    done = subprocess.run(list(argv), capture_output=True, text=True, timeout=120,
                          env=guarded_env(), stdin=subprocess.DEVNULL, cwd=cwd)
    return Ran(done.returncode, done.stdout, done.stderr)


def console_script() -> Path:
    """The installed `poisson-break` beside the test interpreter. Missing means the package is
    not installed with its script, which is a real mistake, so the test fails."""
    script = Path(sys.executable).parent / "poisson-break"
    if not script.exists():
        raise AssertionError(f"the console script is not installed beside the interpreter: {script}")
    return script


def run_command(words: Sequence[str], cwd: Path | None = None) -> Ran:
    """`poisson-break WORDS`, as a user types it."""
    return _run([str(console_script()), *words], cwd=cwd)


def run_module(words: Sequence[str], cwd: Path | None = None) -> Ran:
    """`python -m poisson_break WORDS`."""
    return _run([sys.executable, "-m", "poisson_break", *words], cwd=cwd)


def run_python(code: str, cwd: Path | None = None) -> Ran:
    """A fresh interpreter running `code`, under the guard."""
    return _run([sys.executable, "-c", code], cwd=cwd)
