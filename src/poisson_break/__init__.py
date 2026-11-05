"""Poisson Break finds where an AI agent fails.

It runs the agent you already have, many times, while changing what the user asks, how the
tools behave and how the conversation goes, and keeps the conditions that fail more than a
control. Break calls your tools for real: it runs against a test environment.

This package holds the command (``poisson_break.cli``), the record every stored run carries
(``poisson_break.records``), the four extension points a fault, a way in, a strategy or your
own failure check is written against (``poisson_break.interfaces``), the catalogue of what
Break varies: the changes and conditions by name, the ten launch faults, the input operators and
the conversation moves (``poisson_break.changes``), the applier that puts a condition on one
run: what each tool call comes back as, which tools it may touch and how, and the record of what
was done (``poisson_break.apply``), and the failure check that decides, from what the agent
did, whether a run is ok, failed with one kind, or not counted, counts the three signals beside
it, and runs your own check on a read-only view of the run (``poisson_break.checks``).
"""

__version__ = "0.1.0.dev0"

__all__ = ["__version__"]
