"""A stand-in for Trace's command, for the confirm module's tests only (`tests/confirm_support.py`).

Put first on `PYTHONPATH`, it is what `python -m poisson_trace` finds. With `BREAK_TEST_TRACE_MISSING` set it cannot
be imported, as when no Trace is installed.
"""

import os

if os.environ.get("BREAK_TEST_TRACE_MISSING"):
    raise ModuleNotFoundError("No module named 'poisson_trace'", name="poisson_trace")
