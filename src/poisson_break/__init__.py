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
was done (``poisson_break.apply``), the failure check that decides, from what the agent did,
whether a run is ok, failed with one kind, or not counted, counts the three signals beside it,
and runs your own check on a read-only view of the run (``poisson_break.checks``), the
settings file ``break.toml``: reading and writing it, the case file, ``init``'s flags, and the
run counts of the plan a hunt shows before it spends (``poisson_break.settings``), the look
everything Break prints goes through: one result printed pretty on a terminal and plain anywhere
else, problems as one line on stderr, the exit codes, questions, progress and the way numbers
read (``poisson_break.look``), the runs themselves, stored on Prove: a hunt's folder and its
name, each arm a Prove run whose every row Break decided and wrote a record for, the control
stage and what it measures, the caps on runs, dollars and hours, resuming a stopped hunt, and
the way in for a plain Prove target (``poisson_break.hunt``), and the search a hunt runs after
its control: the two strategies that learn nothing, the stage that runs any strategy and holds
it to no condition twice and a logged probability on every proposal, the score, shrinking a
candidate to the smallest change that still fails, what a hunt did not look at, and loading a
strategy of your own by its import path (``poisson_break.search``).
"""

__version__ = "0.1.0.dev0"

__all__ = ["__version__"]
