# Adding a strategy

After the control stage, a hunt asks a strategy which conditions to try next. Break ships two,
`screen` and `random`, and neither learns from what it sees. A strategy of your own is the
place to put a search that does.

The interface is versioned as `STRATEGY_INTERFACE_VERSION`, which is 1.

## What a strategy is

A strategy is any object with one method:

```text
propose(seen, budget, *, rng) -> list of Proposal
```

`seen` is everything a strategy is shown, and it is read-only:

| Field | What it holds |
|---|---|
| `seen.control` | for each case, each tool it called in the control and how many times |
| `seen.runs` | every run so far: its `condition`, `case`, `seed` and `outcome` (`ok`, `failed` or `not counted`) |
| `seen.proposals` | every proposal so far, with what became of it |
| `seen.budget` | the runs left |
| `seen.catalogue` | what the settings allow: the tools, the faults each can take, the input operators, `max_call` |
| `seen.set_aside` | the cases that failed every control run |
| `seen.cases_per_condition` | how many cases a condition is run on |

`budget` is the number of runs the stage may still spend. `rng` is a generator seeded from
`[search] seed`. A `Proposal` is a condition, a one-line reason, and the probability the
strategy gave that condition, above 0 and at most 1.

Break holds every strategy to the same rules, and does not trust a strategy to hold them
itself:

- No condition is run twice by the search. A proposal that repeats one is dropped, logged, and
  costs no run. The shrink stage, which follows the search, may run a condition again.
- Every proposal is logged before it runs, with its reason and its probability. The
  probability goes into each run's record. A search picks its runs, so they are not a random
  sample, and the probability is what lets a rate be worked out from them later.
- A proposal with no probability, a reason that is not one line, or a change the settings do
  not allow refuses its whole batch before any of it runs, and the stage stops with what it
  has.
- A strategy that raises stops the stage with what it has. It is Break's failure to report, not
  the agent's.
- A strategy keeps nothing from one hunt to the next through Break.

`propose` may return fewer proposals than the budget would pay for. The stage calls it again
until it returns nothing new or the runs are spent.

For `random` and for a strategy of your own, Break holds some runs back for the shrink stage,
and the budget a strategy is shown has them taken out: `[confirm] candidates` × 2 × `[search]
cases_per_condition` runs. With a small `[search] runs` that can leave a strategy nothing to
spend, and then the hunt tries no condition.

## An example

This strategy tries one thing: an `error` on the first call of each tool the control saw. The
program is an agent, the strategy, and a small hunt that uses it.

```python
import json
from pathlib import Path

from poisson_prove import Episode

from poisson_break.apply import wrap
from poisson_break.changes import parse
from poisson_break.interfaces import STRATEGY_INTERFACE_VERSION
from poisson_break.search import Proposal

lookup_order = wrap("lookup_order", lambda order: f"Order {order} shipped on Tuesday.")
check_policy = wrap("check_policy", lambda topic: "Refunds within thirty days.")


def agent(cfg, seed):
    try:
        status = lookup_order("4821")
    except Exception:
        return Episode(outcome="unresolved", t=0.0, horizon=1.0)
    try:
        status += " " + check_policy("refunds")
    except Exception:
        pass
    return Episode(outcome="resolved", t=1.0, horizon=1.0, meta={"reply": status})


class FirstCalls:
    def propose(self, seen, budget, *, rng):
        if seen.proposals:
            return []
        tools = sorted({tool for calls in seen.control.values() for tool in calls})
        return [Proposal(condition=parse(f"tool:{tool}#1=error"),
                         reason="an error on the first call of each tool", probability=1.0)
                for tool in tools]


SETTINGS = """
version = 1

[target]
kind = "rollout"
entry = "example:agent"
cases = "cases.jsonl"

[tools]
lookup_order = "read"
check_policy = "read"

[fails]
outcomes = ["unresolved"]

[vary]
tools = ["error"]
inputs = []
max_call = 1

[search]
strategy = "example:FirstCalls"
runs = 24
control_repeats = 1
cases_per_condition = 3

[confirm]
candidates = 1
"""

if __name__ == "__main__":
    from poisson_break.cli import main

    assert STRATEGY_INTERFACE_VERSION == 1
    cases = [{"id": f"order-{n}", "input": f"Where is order {n}?"} for n in (4821, 4822, 4823)]
    Path("cases.jsonl").write_text("".join(json.dumps(case) + "\n" for case in cases))
    Path("break.toml").write_text(SETTINGS)
    raise SystemExit(main(["--plain", "hunt", "--yes"]))
```

Saved as `example.py` and run with `python example.py`, it hunts with the two conditions the
strategy proposed:

```text
plan  a hunt of agent on 3 cases, at most 24 runs
  target      example:agent (rollout)
  tools       lookup_order (read), check_policy (read)
  may change  tool behaviour (1 fault), inputs (0 operators)
  strategy    example:FirstCalls
  stages      control 3 runs, search and shrink up to 21
  cap         24 runs, 2 hours
  estimate    at most 24 runs and 2 hours, with no prices to put in dollars, from the settings' limits
found  1 candidate in 9 runs
  control  3 runs · 0 failed (0.000)
  search   6 runs · 2 conditions tried on 3 cases each
     condition                  failed         kind
  1  tool:lookup_order#1=error  3 of 3 failed  failed
  not looked at: faults turned off: timeout, slow, rate_limited, empty, cut_off, malformed, stale, lost_reply, planted_instruction; 0 single changes and 1 pair of them untried
  these are candidates, not findings: a few runs each, chosen for having failed
next: poisson-break confirm
```

## Using it in a hunt

Name the class in `break.toml` by its import path. Break makes one with no arguments.

```toml
[search]
strategy = "my_app.search:FirstCalls"
```

`doctor` and `hunt` load it before any run. A path that cannot be loaded, a class that needs
arguments and a thing with no `propose` are each refused in one line. The proposals a hunt
logged are in the hunt's folder, in `proposals.jsonl`, one a line.
