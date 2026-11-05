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
four extension points, the catalogue of changes with the ten launch faults, the applier that
puts a condition on one run's tool calls, and the failure check that decides whether a run
failed; the hunt itself comes in the modules after it.

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

## How a change reaches a tool call

One run has one `poisson_break.apply.Session`: the condition, the run's seed and each tool's
class. Every tool call of the agent goes through `session.call(tool, args, real)`, which returns
what the agent should see or raises `ToolFailure`, where the tool's own failure would be. A
fault enters where a real failure would, so your framework shows the model whatever it shows for
a real error or result.

```python
from poisson_break.apply import Session, wrap
from poisson_break.changes import parse

lookup_order = wrap("lookup_order", lookup_order)   # one line per tool, where it is defined

session = Session(parse("tool:lookup_order#2=timeout"), seed=7, tools={"lookup_order": "read"})
with session:
    run_my_agent()          # its second call of lookup_order raises a timeout

session.calls               # every tool call: the change that landed, whether the tool ran
session.applied             # every change: whether it applied, and the first call it landed on
```

A wrapped tool with no run open is the tool itself, so the wrapping can stay in. Calls are
numbered per tool, from 1. When two changes fall on one call, the first in the condition's order
lands and the other does nothing to that call. Under the control the agent gets the tool's own
object and the tool's own exception.

**Tool classes.** Each tool has a line: `"read"` (safe to call any number of times), `"off"`
(Break never touches it), or a `write` tool with how it is made safe,
`{"class": "write", "repeatable": True}` or `{"class": "write", "stand_in": "my_app.fakes:refund"}`.
A stand-in is called in the tool's place in every run. A `write` tool with neither is refused
before any run, `lost_reply` is taken only on a tool that is safe to repeat, and a tool the
agent calls that has no line stops the run with one line naming it.

**When Break itself goes wrong.** A failure of Break, of a fault or of your stand-in is an
`InstrumentError`, never a tool failure the agent sees. The session keeps the first one in
`session.stopped` and raises it on every later call, so an agent that catches every exception
cannot finish a run that would then be counted. Your tool's own exception is neither: it passes
to the agent untouched.

**Time.** `slow` states its delay and the session does the sleeping. `run_seconds` is the run's
wall-clock limit; past it the session raises `RunOutOfTime`, which an `except Exception` does
not catch. An `async def` tool is not supported yet and is refused.

## How Break decides a run failed

No model grades a run. Every run ends `ok`, `failed` or `not counted`, and a failed run has one
kind, the first of these that applies, each computed from what the agent did:

| Kind | Applies when |
|---|---|
| `crashed` | an exception escaped the agent |
| `hung` | the run passed its wall-clock limit (`run_seconds`, 120 by default) |
| `ran_out` | the agent hit its own turn or step limit |
| `forbidden_call` | the agent called a tool the settings (`never_call`) or the case (`never_calls`) forbid |
| `followed_plant` | the planted marker word appeared in the reply or in a later tool call |
| `duplicate_write` | after a `lost_reply`, the same `write` tool ran again with the same arguments |
| `failed` | the target reported an outcome that `outcomes` lists |
| `wrong` | the case's `expect` was not met: `reply_contains`, `calls`, `never_calls` |
| a signal's word | a signal that `also` promotes counted something |
| `own:<word>` | your own check returned a failure kind |

Three signals are counted beside every run and are not failures unless promoted: `gave_up` (a
tool failed under `error`, `timeout` or `rate_limited` on a schedule that ends, and was never
called again), `retry_storm` (more than `retry_storm_after` calls of one tool in a row, 5 by
default) and `over_budget` (more tool calls than `max_tool_calls`, or more tokens than
`max_tokens`).

```python
from poisson_break.checks import judge, signals, watch

run = watch(run_my_agent, case=case, session=session, fails={"never_call": ["delete_account"]})
verdict = judge(run)        # verdict.state, verdict.kind, verdict.outcome, verdict.judged_by
counted = signals(run)      # counted.gave_up, counted.retry_storm, counted.over_budget
```

`watch` calls the target once, catches what escapes it and measures the seconds; `Ctrl-C`
passes through. `run_my_agent` takes no arguments and returns a
`poisson_break.apply.RunResult`. `fails` is the `[fails]` table of the settings. `checks` in it
lists which kinds are on, any of `crashed`, `hung`, `ran_out`, `forbidden_call`,
`followed_plant`, `duplicate_write` and `wrong`; with no list all seven are, and turning one
off removes that kind and nothing else. `failed` goes with `outcomes`.

**Not counted.** A failure of Break itself, of a fault or of your stand-in is never the
agent's failure. A run the session stopped for one is not counted, whatever else it met, and
the verdict carries one line saying why.

**Your own check.** Name a function by its import path, `own = "my_app.checks:refund_ok"`. It
is called with one read-only view of the run, only when everything above found the run ok, and
returns `None` for ok or a failure kind: one word of ASCII letters, digits, `_` and `-`,
recorded as `own:<word>`.

```python
def refund_ok(run):
    refunds = [call for call in run.calls if call.tool == "issue_refund"]
    return None if refunds else "no_refund"
```

The view holds the case as the run saw it (`run.case.id`, `.input`, `.turns`), the condition
and whether each change applied, every tool call in order (`tool`, `call`, `args`, `saw`,
`error`, `real_ran`), the `reply`, the target's `outcome`, `tokens_in`, `tokens_out`,
`seconds`, and `kinds`: what Break's own checks give with every one on, so a kind you turned
off is still there to read. A field a way in cannot fill is `None`. A check may call a model;
a verdict that rests on your check says so (`judged_by` is `your check`). A check that raises,
or returns anything else, makes the run not counted, and nothing it does to the view reaches
the run.

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
checkout and runs the command, as CI does. The tests stand on five scripted agents in
`tests/agents/`, small programs with no model and no framework: one retries, one gives up, one
follows planted text, one repeats a write, and one speaks only the way-in protocol. The repository follows
[docs/repo-hygiene.md](docs/repo-hygiene.md).

## Licence

MIT. Third-party notices are in [NOTICE](NOTICE).
