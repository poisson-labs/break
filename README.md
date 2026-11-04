# Poisson Break

Poisson Break finds where an AI agent fails. It runs the agent you already have, many times,
while changing what the user asks, how the tools behave and how the conversation goes, and
keeps the conditions that fail more than a control. Each finding is a named, replayable
condition, handed over in a form a fix can be checked against with Poisson Trace and Poisson
Prove.

**Break calls your tools for real.** It runs against a test environment, many times, and
refuses a tool that changes the outside world until you say how that tool is made safe to
repeat.

## Status

Break is being built and is not released. The `poisson-break` name on PyPI holds a 0.0.1
placeholder with no code. This tree has the command, the record every stored run carries, the
four extension points and the catalogue of changes with the ten launch faults; the hunt itself
comes in the modules after it.

## Install, from this tree

Python 3.11 or later.

```
python -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/poisson-break --version
```

`python -m poisson_break` is the same command.

## The command

```
poisson-break --version
poisson-break --help
```

`--version` prints one line with the versions of Break, Prove, Trace and Python. A mistake on
the command line is one `error:` line on stderr and exit 2. The look every Poisson Labs command
shares is written down in [docs/cli-look.md](docs/cli-look.md).

## What Break varies

Every change has a readable name, and a condition is its changes joined with ` + `. The empty
name is the control. A condition is canonical: its changes are sorted, and two spellings of one
condition have one name.

| Where it acts | Name | Example |
|---|---|---|
| A tool's behaviour, on a call | `tool:<tool>#<call>=<fault>` | `tool:lookup_order#2=timeout` |
| A tool's behaviour, by rate | `tool:<tool>~<rate>=<fault>` | `tool:search~0.3=error` |
| The request | `input:<operator>` | `input:typos` |
| The conversation | `user:<move>@<turn>` | `user:repeats@3` |
| The model's own calls | `model:<fault>#<call>` | `model:cut_off#2` |
| A setting the target declares | `env:<name>=<value>` | `env:inventory=empty` |

`#2` is the second call to that tool within a run, `#2-4` a range and `#*` every call. A rate is
above 0 and at most 1, decided by a keyed draw of the run's seed, the tool and the call, so a run
replays exactly. A bad name is refused with the nearest valid name when one is within two edits.

Ten tool faults at launch: `error`, `timeout`, `slow`, `rate_limited`, `empty`, `cut_off`,
`malformed`, `stale`, `lost_reply` and `planted_instruction`. Each says what the agent sees and
whether the real tool ran. Five input operators (`typos`, `reordered`, `padded`, `cut_short`,
`variant`) and four conversation moves (`repeats`, `interrupts`, `goes_quiet`, `presses`) need
no model. Conversation moves and the five model faults are names in the catalogue that only a
framework adapter can apply, and a condition that asks for one is refused before any run for a
way in that cannot.

A fault of your own is a class with `name`, `surface`, `description`, `parameters`, `real_runs`
and `apply(call, *, real, params, rng)`, registered from its own module with
`poisson_break.changes.register`. From then on nothing tells it from a launch fault.

## What it depends on

Prove (`poisson-prove`) and Trace (`poisson-trace`), each pinned to one exact version. Break's
Prove is the version Trace pins, so the three tools agree on one Prove. Trace is not yet on
PyPI; its pin is declared the day it is.

## Developing

```
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/mypy
```

The suite runs under a guard that fails any connection: open-source Break opens no socket of
its own and sends nothing anywhere. A second check reads the source for a test or an interval
computed locally and fails on one: every statistic Break reports is Trace's or Prove's.
`scripts/clean_install.py` builds the wheel, installs it into a fresh environment outside the
checkout and runs the command, as CI does. The repository follows
[docs/repo-hygiene.md](docs/repo-hygiene.md).

## Licence

MIT. Third-party notices are in [NOTICE](NOTICE).
