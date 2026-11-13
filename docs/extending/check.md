# Adding a check of your own

Break decides that a run failed from what the agent did: it crashed, it ran past its time, it
called a tool it must never call, it reported an outcome you listed as failing. Some failures
only you can name: a refund issued without a look-up, or a reply that states a delivery date
the agent never read. For those you give Break one function.

The interface is versioned as `CHECK_INTERFACE_VERSION`, which is 1.

## What a check is

A check is a function that takes one run and returns `None` when the run is fine, or one word
that names the failure. Break records the word as the failure kind `own:<word>`. The word is ASCII
letters, digits, `_` and `-`.

The run it is given is a read-only view:

| Field | What it holds |
|---|---|
| `run.case` | the case as the run saw it: `id`, `input`, `turns` |
| `run.condition` | the condition's `name`, and its `changes` with whether each applied |
| `run.calls` | every tool call in order: `tool`, `call` (its number for that tool), `args`, `saw` (what the agent got back), `error` (the error it got, if any), `real_ran` |
| `run.reply` | the agent's reply |
| `run.outcome` | the outcome the agent itself reported, if it reports one |
| `run.tokens_in`, `run.tokens_out`, `run.seconds` | where known |
| `run.kinds` | the kinds Break's own checks give this run, including any you turned off |

A field your way in cannot fill is `None`.

Break calls the check once for each run, after the run, and only when its own checks found the
run ok. The check cannot change the run. If it raises, or returns anything but `None` or a
word, the run is not counted, and Break says why. A check may call a model. Break does not pay
for that and does not prevent it, and every finding that rests on your check says so where it
is printed: its `judged by` line reads `your check`.

## An example

The program below is an agent, a check, and a small hunt on both. The agent answers even when
its look-up failed. The check fails a run whose reply was sent after every look-up had failed.

```python
import json
from pathlib import Path

from poisson_prove import Episode

from poisson_break.apply import wrap
from poisson_break.interfaces import CHECK_INTERFACE_VERSION

lookup_order = wrap("lookup_order", lambda order: f"Order {order} shipped on Tuesday.")


def agent(cfg, seed):
    try:
        reply = lookup_order("4821")
    except Exception:
        reply = "Your order is on its way."
    return Episode(outcome="resolved", t=1.0, horizon=1.0, meta={"reply": reply})


def made_up_answer(run):
    lookups = [call for call in run.calls if call.tool == "lookup_order"]
    if lookups and all(call.error for call in lookups) and run.reply:
        return "made_up"
    return None


SETTINGS = """
version = 1

[target]
kind = "rollout"
entry = "example:agent"
cases = "cases.jsonl"

[tools]
lookup_order = "read"

[fails]
own = "example:made_up_answer"

[vary]
tools = ["error"]
inputs = []
max_call = 1

[search]
runs = 12
control_repeats = 1
cases_per_condition = 3
"""

if __name__ == "__main__":
    from poisson_break.cli import main

    assert CHECK_INTERFACE_VERSION == 1
    cases = [{"id": f"order-{n}", "input": f"Where is order {n}?"} for n in (4821, 4822, 4823)]
    Path("cases.jsonl").write_text("".join(json.dumps(case) + "\n" for case in cases))
    Path("break.toml").write_text(SETTINGS)
    raise SystemExit(main(["--plain", "hunt", "--yes"]))
```

Saved as `example.py` and run with `python example.py`, it writes the two files and hunts.
The candidate's kind is the check's word:

```text
plan  a hunt of agent on 3 cases, at most 12 runs
  target      example:agent (rollout)
  tools       lookup_order (read)
  may change  tool behaviour (1 fault), inputs (0 operators)
  strategy    screen
  stages      control 3 runs, search and shrink up to 9
  cap         12 runs, 2 hours
  estimate    at most 12 runs and 2 hours, with no prices to put in dollars, from the settings' limits
found  1 candidate in 6 runs
  control  3 runs · 0 failed (0.000)
  search   3 runs · 1 condition tried on 3 cases each
     condition                  failed         kind
  1  tool:lookup_order#1=error  3 of 3 failed  own:made_up
  not looked at: faults turned off: timeout, slow, rate_limited, empty, cut_off, malformed, stale, lost_reply, planted_instruction; 0 single changes and 0 pairs of them untried
  these are candidates, not findings: a few runs each, chosen for having failed
  wrote    break-runs/agent-1/hunt.json, proposals.jsonl, candidates.json and every run in store/
next: poisson-break confirm
```

## Using it in a hunt

Name the function in `break.toml` by its import path:

```toml
[fails]
own = "my_app.checks:made_up_answer"
```

`doctor` loads it and refuses a path that cannot be imported or called. The `own-check` example
is a hunt and a confirm stage on a check like this one:

```sh
poisson-break init --example own-check
poisson-break hunt --yes
poisson-break confirm --yes
poisson-break findings 1
```
