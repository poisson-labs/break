# Poisson Break

Break finds where an AI agent fails. It runs the agent you already have, many times,
while changing how its tools behave and what the user asks, and keeps the conditions under
which the agent fails more often than it does with no change. Each one is a finding: a named
condition you can replay, with the numbers behind it, that a fix can later be checked against.

Try it on an example agent. It needs Python 3.11 or later, on macOS or Linux, and no key and
no network once it is installed.

```sh
python -m venv .venv
. .venv/bin/activate
pip install poisson-break
poisson-break init --example desk
poisson-break hunt --yes
poisson-break confirm --yes
```

`init --example desk` writes a small help desk into the folder: an agent with two tools and a
scripted model, six requests to try it on, and `break.toml`, the settings. `hunt` looks for
conditions that make it fail. `confirm` tests what the hunt found on fresh runs. To run Break on
an agent of your own, go on to [On your own agent](https://github.com/poisson-labs/break#on-your-own-agent).

**Break calls your tools for real.** Run it against a test environment. It refuses a tool that
changes something outside until you say how that tool is made safe to repeat.

## How Break changes a tool

The desk's model is a plain Python function, `scripted_model`, that picks the next step from the
request and from what the tools have returned so far. That is why the example needs no key and
no network. Break makes no model call of its own; on your own agent, the model calls are the
ones your agent makes.

Break starts no app and no server. It imports the function `break.toml` names, `desk_agent:desk`
here, and calls it once for each run, in Break's own process. One run is one call of that
function, on one case, with one seed, under one condition. The control runs the same cases with no
change, and every condition is compared with it; each condition the desk's hunt tries is one
change.

Each tool is wrapped once with `wrap`, which puts Break between the agent and the tool. On the
call a condition names, such as the first call to `lookup_order`, Break applies the condition's
fault. A timeout, an error or a rate limit is raised where the tool's own failure would arrive,
and the tool does not run, so a timeout reaches the agent as a `TimeoutError`. Other faults run
the tool and change what comes back: `empty` hands back an empty result, `malformed` breaks its
structure, and `stale` hands back the previous call's result. `lost_reply` lets the tool act and
then reports an error. Every other call runs the real tool, as every call does in the control.

## What you see

`hunt` shows its plan, then runs the agent with no change (the control), then tries one change
at a time:

```text
plan  a hunt of desk on 6 cases, at most 120 runs
  target      desk_agent:desk (rollout)
  tools       lookup_order (read), check_policy (read)
  may change  tool behaviour (4 faults), inputs (2 operators)
  strategy    screen
  stages      control 12 runs, search and shrink up to 108
  cap         120 runs, 2 hours
  estimate    at most 120 runs and 2 hours, with no prices to put in dollars, from the settings' limits
note: Break calls your tools for real: run it against a test environment, never against anything that matters
found  3 candidates in 42 runs
  control  12 runs · 0 failed (0.000)
  search   30 runs · 10 conditions tried on 3 cases each
     condition                         failed         kind
  1  tool:lookup_order#1=timeout       3 of 3 failed  failed
  2  tool:lookup_order#1=rate_limited  3 of 3 failed  failed
  3  tool:lookup_order#1=error         3 of 3 failed  failed
  not looked at: faults turned off: slow, cut_off, malformed, stale, lost_reply, planted_instruction; 0 single changes and 33 pairs of them untried
  these are candidates, not findings: a few runs each, chosen for having failed
  wrote    break-runs/desk-1/hunt.json, proposals.jsonl, candidates.json and every run in store/
next: poisson-break confirm
```

The desk never failed in its 12 control runs. Of the 10 conditions the hunt tried, three made
it fail on every case they were tried on: a timeout, a rate limit and an error on the first
call to `lookup_order`. The other seven, among them every fault on `check_policy` and both
changes to the request, did not. The line `not looked at` says what this hunt left untried.

Those three are candidates: a few runs each, and chosen because they failed. `confirm` runs
each of them again on every case, three times, beside a control arm. The control arm is the
set of runs on the same cases with no change, and each candidate's runs are compared with it.
`confirm` then asks Trace whether the difference holds.
[Trace](https://pypi.org/project/poisson-trace/) is the Poisson Labs tool that checks whether a
fix held:

```text
plan  confirm 3 candidates against a control
  design     6 cases × 3 repeats, once with no change and once under each candidate · 72 runs
  reference  up to 54 more runs, 18 for each candidate that is confirmed
  cap        120 runs, 2 hours
  Trace will say if this is too small to see a difference of 0.200, and how many repeats would be enough
  estimate   126 runs, about 0 s; no prices, so no dollars, from the control stage's 0 s a run
note: Break calls your tools for real: run it against a test environment, never against anything that matters
confirmed  3 of 3 candidates fail more than the control (0.000)
     condition                         verdict    numbers
  1  tool:lookup_order#1=timeout       confirmed  1.000   +1.000
  2  tool:lookup_order#1=rate_limited  confirmed  1.000   +1.000
  3  tool:lookup_order#1=error         confirmed  1.000   +1.000
  wrote      break-runs/desk-1/findings/1.toml, 2.toml, 3.toml
  reference  54 runs
next: poisson-break findings 1
```

All three hold, and each is now a finding. Read one, and run it once more to see what the agent
did:

```sh
poisson-break findings 1
poisson-break replay 1
```

```text
note: Break calls your tools for real: run it against a test environment, never against anything that matters
failed  finding 1 on case status-4821, seed 56661626: failed
     tool          call  change                       real tool ran
  1  lookup_order  1     tool:lookup_order#1=timeout  no
```

The desk has no second try: one failed look-up ends the request.
[Reading a finding](https://github.com/poisson-labs/break/blob/main/docs/findings.md) goes through every line a finding prints.

The hunt called the desk's function 42 times, once for each run: 12 control runs, two on each of
the six cases, and 30 runs for the ten conditions it tried. `confirm` called it 126 more times:
72 runs with no change and under the three candidates, and 54 for the reference, the runs
`recheck` later compares a fix with.

Everything is kept in `break-runs/desk-1/`, one folder for each hunt. `hunt.json` holds the
settings as resolved and the stages run, `candidates.json` the candidates `hunt` handed to
`confirm`, `findings/1.toml` and the two beside it one finding each, and `store/` every run, as
a Prove store. [Prove](https://github.com/poisson-labs/prove) is the Poisson Labs tool that tells
you whether a difference is real, and its own commands read the store.

A stored run is Break's record of the run: the case by its id, the change, the outcome and the
kind of failure, and each tool call with whether the real tool ran. It holds none of the agent's
prompt, reply or tool results. `replay` is how you see what the agent did: it runs a finding
once more, stores nothing, and shows each tool call with the change on it.

## On your own agent

A way in is how Break runs your agent and reaches its tools. This version has one, `rollout`:
your agent as a Python function that Break calls once for each run, with each tool wrapped
once.

The function takes `cfg` and `seed` and returns an `Episode`. `cfg` is one case from your case
file, as a mapping that holds the request under `input`. `seed` is the run's seed. `Episode` is
Prove's record of one run, and Break reads the agent's own `outcome` from it.

```python
from poisson_prove import Episode

from poisson_break.apply import wrap

lookup_order = wrap("lookup_order", lookup_order)      # one line a tool, where it is defined


def refund_agent(cfg, seed):
    reply = run_my_agent(cfg["input"])                 # your agent, as it is
    return Episode(outcome="resolved", t=1.0, horizon=1.0, meta={"reply": reply})
```

The `wrap` line is what this way in asks of your code. You write it yourself, once for each
tool, where the tool is defined, at the top of its module, and not at each call. `init` does not
add it: it finds the tools already wrapped by importing your module. The line makes your module
import `poisson_break`. Outside a run the wrapped tool is the tool itself, so the line can stay
in. A tool that is `async def` is refused. Adapters for agent frameworks and MCP servers are not
in this version (see [Status](https://github.com/poisson-labs/break#status)).

Then, in the folder that holds it, `poisson-break init` asks where the agent is, where your
test cases are, and, for each tool it finds, whether calling it changes anything. It chooses
everything else, says what it chose, and writes `break.toml`, where you can change any of it.
`poisson-break doctor` checks that everything loads. `hunt` and `confirm` work as above.
[The rollout way in](https://github.com/poisson-labs/break/blob/main/docs/ways-in/rollout.md) has the details, and ends with
[a whole agent to start from](https://github.com/poisson-labs/break/blob/main/docs/ways-in/rollout.md#a-whole-agent-to-start-from):
two files to copy and the commands that take them to a hunt. The
[catalogue](https://github.com/poisson-labs/break/blob/main/docs/catalog.md) lists every change a hunt can make.

When you have changed the agent, `poisson-break recheck` runs every finding again and says
whether each now fails less: [Checking a fix](https://github.com/poisson-labs/break/blob/main/docs/recheck.md).

## The examples

Each is written into the folder by `poisson-break init --example NAME`, and each runs with no
key and no network against a scripted model.

| Example | What it is | What it ends with |
|---|---|---|
| `desk` | a help desk with two read tools | 3 findings: the desk gives up when its order look-up fails |
| `full-loop` | an order desk, and the same desk with a fix | 3 findings; after the fix is copied in, `recheck` reads all 3 as `fails less` |
| `stand-in` | a refund desk whose refund tool moves money, with a stand-in for it | 1 finding: after a lost reply the desk refunds twice (`duplicate_write`) |
| `own-check` | a desk that always answers, with a check of the team's own | 3 findings judged by that check (`own:made_up`) |
| `own-fault` | a desk, with a fault the team added to the catalogue | 1 finding: the desk falls over on an error page (`crashed`) |

[The examples page](https://github.com/poisson-labs/break/blob/main/examples/README.md) walks through each.

## The docs

These pages are also on the site, at [poissonlabs.ai/docs/break](https://poissonlabs.ai/docs/break/).

- [The catalogue](https://github.com/poisson-labs/break/blob/main/docs/catalog.md): every change Break can make, and how each is named.
- [Reading a finding](https://github.com/poisson-labs/break/blob/main/docs/findings.md): what each line and number means.
- [Checking a fix](https://github.com/poisson-labs/break/blob/main/docs/recheck.md): hunt, confirm, fix, recheck.
- [The rollout way in](https://github.com/poisson-labs/break/blob/main/docs/ways-in/rollout.md): your agent as a function, its tools and their classes.
- Cases from the requests your users already sent:
  [LangSmith](https://github.com/poisson-labs/break/blob/main/docs/export/langsmith.md), [Langfuse](https://github.com/poisson-labs/break/blob/main/docs/export/langfuse.md),
  [Phoenix](https://github.com/poisson-labs/break/blob/main/docs/export/phoenix.md).
- [What Break does not claim](https://github.com/poisson-labs/break/blob/main/docs/claims.md).
- [The reference](https://github.com/poisson-labs/break/blob/main/docs/reference.md): the commands, the settings file, the stored runs, the library.
- Extending Break: [a fault](https://github.com/poisson-labs/break/blob/main/docs/extending/fault.md), [a way in](https://github.com/poisson-labs/break/blob/main/docs/extending/way-in.md),
  [a strategy](https://github.com/poisson-labs/break/blob/main/docs/extending/strategy.md), [a check of your own](https://github.com/poisson-labs/break/blob/main/docs/extending/check.md).
- [The changelog](https://github.com/poisson-labs/break/blob/main/CHANGELOG.md): what each version changed.

## What Break does not claim

A hunt that finds nothing has shown that the conditions it tried, on the cases you gave it, did
not fail more than the control in the runs it had. It has not shown more than that, and Break
does not say it has. A finding says the agent fails more under one named condition; it does not
say how often that condition happens to you. Every test, interval and p-value Break prints
beside a finding is computed by Trace or Prove; Break itself only counts runs and divides. Each finding prints the command that gives the full report. [What Break does not claim](https://github.com/poisson-labs/break/blob/main/docs/claims.md) sets the limits out.

## Status

This is version 0.1.0, an alpha. It has one way in, `rollout`: an agent Break can call as a
Python function. It changes tool behaviour (ten faults) and the request (five operators), and
searches with two strategies that do not learn. Adapters for agent frameworks and MCP servers,
changes to the conversation and to the model's own calls, and a search that learns are not in
this version; the catalogue names what waits for them. It runs on macOS and Linux, on Python
3.11 or later.

Break is on [PyPI](https://pypi.org/project/poisson-break/) as `poisson-break`, and its page on
the site is [poissonlabs.ai/tools/break](https://poissonlabs.ai/tools/break/). It depends on Prove
and Trace, each at one exact version, and `pip` installs both from PyPI with it. Trace is a
pre-release there, 0.1.0a1.

[The reference](https://github.com/poisson-labs/break/blob/main/docs/reference.md) has the
commands, the settings file, how runs are stored, and the library under the command.

## Licence

MIT. Third-party notices are in [NOTICE](https://github.com/poisson-labs/break/blob/main/NOTICE).
