"""Poisson Break finds where an AI agent fails.

It runs the agent you already have, many times, while changing what the user asks, how the
tools behave and how the conversation goes, and keeps the conditions that fail more than a
control. Break calls your tools for real: it runs against a test environment.

This package holds the command (``poisson_break.cli``), the record every stored run carries
(``poisson_break.records``), the four extension points a fault, a way in, a strategy or your
own failure check is written against (``poisson_break.interfaces``), and the catalogue of what
Break varies: the changes and conditions by name, the ten launch faults, the input operators and
the conversation moves (``poisson_break.changes``).
"""

__version__ = "0.1.0.dev0"

__all__ = ["__version__"]
