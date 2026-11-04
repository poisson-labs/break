# Changelog

## Unreleased

The first two modules of Poisson Break: the repository, the package and its command, the record
every stored run carries, the four extension points, and the catalogue of what Break varies with
the ten launch faults. Nothing hunts yet.

- `poisson_break.changes`: changes and conditions by name (`parse`, `name`), canonical and
  round-tripping, with a bad name refused and the nearest valid name offered when one is within
  two edits; whether a change applies to a call (`applies`): a schedule by the call number alone,
  a rate by a keyed draw of the seed, the tool and the call; the five input operators and the four
  conversation moves as pure functions of a case and a seed; the catalogue (`CATALOG`) of the ten
  tool faults, five input operators, four conversation moves and five model faults, each with a
  one-line description and its defaults (`delay` 5 s, `wait` 30 s, `length` 200 characters,
  `typos` share 5%); the ten launch faults, each a `Fault` that is given a frozen `CallContext`
  and returns a `Result` or a `ToolError`; `register` for a fault written outside the package;
  `run_fault`, which counts the real tool's calls against the fault's declaration and turns a
  fault's mistake into an `InstrumentError`; `check_capabilities`, which refuses before any run a
  condition that asks of a way in something it cannot do (`NeedsAdapter`); and `marker`, the
  planted word derived from the hunt and the case.
- The package `poisson-break`, importing as `poisson_break`, with the command `poisson-break`
  (`python -m poisson_break` is the same). `--version` prints one line with the versions of
  Break, Prove, Trace and Python; `--help` gives a description and an example; a mistake on the
  command line is one `error:` line on stderr and exit 2, and abbreviated options are refused.
- `poisson_break.records`: the record each stored run carries under the key `poisson_break` in
  the run's extra facts, in the published shape `poisson_break.run/1`: the hunt, the stage, the
  arm, the case, the condition with each of its changes and whether and where it applied, the
  failure kind and the three signals, the strategy and the probability it gave the condition,
  every tool call, who judged the run and the target's own outcome. Frozen types that round-trip
  through JSON and refuse a field the shape does not name or a value outside its closed set.
- `poisson_break.interfaces`: the four extension points, each at version 1: a fault, a way in,
  a strategy and your own failure check.
- Prove pinned to the exact version Trace pins (0.1.2). Trace is not yet on PyPI; its pin is
  declared the day it is.
- CI: lint, type check and the tests on Python 3.11 to 3.13, under a guard that fails any
  connection and a check that no statistic is computed locally; a clean install of the built
  wheel into a fresh environment outside the checkout that runs the command.
