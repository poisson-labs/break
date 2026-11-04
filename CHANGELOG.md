# Changelog

## Unreleased

The first module of Poisson Break: the repository, the package and its command, the record every
stored run carries, and the four extension points. Nothing hunts yet.

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
