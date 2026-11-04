"""The network guard for processes the tests start.

Put on `PYTHONPATH` by `tests/conftest.py`, Python imports this at start-up, before the
command under test runs. Every way of opening a connection then raises, so a command that
reaches out fails loudly instead of quietly. The guard in `conftest.py` does the same for the
test process itself.
"""

from __future__ import annotations

import socket
from typing import Any


class NetworkGuard(RuntimeError):
    """Raised when something under test tries to open a connection."""


def _refuse(*args: Any, **kwargs: Any) -> Any:
    raise NetworkGuard(
        f"the network guard: a connection was attempted ({args!r}); "
        "open-source Break opens no socket of its own"
    )


socket.socket.connect = _refuse  # type: ignore[method-assign]
socket.socket.connect_ex = _refuse  # type: ignore[method-assign]
socket.create_connection = _refuse  # type: ignore[assignment]
socket.getaddrinfo = _refuse  # type: ignore[assignment]
