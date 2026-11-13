# The rollout way in

A way in is how Break runs your agent and reaches its tools. This version has one, `rollout`:
your agent as a Python function that Break calls once for each run. If you can call your agent
from Python, you can hunt it this way, whatever it is built with.

## The function

```python
from poisson_prove import Episode

from poisson_break.apply import wrap


def _lookup_order(order: str) -> str:
    ...   # your tool, as it is


lookup_order = wrap("lookup_order", _lookup_order)


def refund_agent(cfg, seed):
    reply = run_my_agent(cfg["input"])   # your agent, calling lookup_order as it always does
    return Episode(outcome="resolved", t=1.0, horizon=1.0, meta={"reply": reply})
```

Two things make a function a rollout target.

**It takes a case and a seed and returns an `Episode`.** `cfg` is one case from your case file,
as a mapping: its `input`, and any other key you put on the line. `seed` is the run's seed; an
agent that draws random numbers should draw them from it, so that a run can be replayed.
`Episode` is Poisson Prove's record of one run. Break reads two things from it:

| Field | What Break reads |
|---|---|
| `outcome` | your agent's own word for how the run ended. List the words that mean failure in `[fails] outcomes` |
| `meta` | optional facts: `reply` (what the agent answered), `tokens_in` and `tokens_out` (for prices and caps), and `ended = "limit"` when the agent stopped at its own step limit |

`t` and `horizon` are Prove's own fields: the time at which the run ended, and the longest a
run could go. Break's verdicts do not use them, and an agent with no such measure passes
`t=1.0, horizon=1.0`.

**Each tool is wrapped once.** `wrap(name, function)` returns the tool with a hook in it. Outside
a run the wrapped tool is the tool itself, so the line can stay in your code. Inside a run,
each call goes through Break, which either passes it on or puts a fault in its place. A fault
arrives where the tool's own failure would: an `error` is an exception raised from the call,
and a `timeout` is a `TimeoutError`. Wrap a tool where it is defined, at the top of a module,
so that `init` can find it by importing that module.

An `async def` tool is refused; wrap a function that is not async.

## The settings

`init` asks where the agent is and writes `break.toml`. A flag answers its own question, and
`--yes` takes the default for every question left, so `init --entry
my_app.agents:refund_agent --yes` asks nothing. These are the lines that describe the target:

```toml
[target]
kind = "rollout"
entry = "my_app.agents:refund_agent"   # module:name, importable from the folder you run in
cases = "cases.jsonl"

[tools]
lookup_order = "read"
issue_refund = { class = "write", stand_in = "my_app.fakes:issue_refund" }
send_email = "off"
```

The command puts the folder it runs in first on the import path, so a module beside
`break.toml` is found.

## Tool classes

Break calls your tools for real, many times. So every tool your agent calls has a line in
`[tools]` that says what calling it does.

| Line | Meaning |
|---|---|
| `"read"` | calling it changes nothing; Break may call it any number of times |
| `{ class = "write", repeatable = true }` | it changes something, and your test environment absorbs repeats |
| `{ class = "write", stand_in = "module:name" }` | it changes something; Break calls the stand-in in its place in every run, with the same arguments |
| `"off"` | Break never touches it: no fault is put on it, and its calls pass straight through |

A `write` tool with neither `repeatable` nor a stand-in is refused before any run. A tool your
agent calls that has no line stops the hunt, and Break prints the `init` command that classes
it `off` so that the hunt can go on.

## A write tool with its stand-in

The `stand-in` example is a refund desk whose `issue_refund` asks a payments service to pay a
customer back. Its `break.toml` names a stand-in for that tool, so the real function never
runs.

```sh
poisson-break init --example stand-in
poisson-break hunt --yes
poisson-break confirm --yes
poisson-break replay 1
```

The hunt ends with one candidate:

```text
found  1 candidate in 27 runs
  control  12 runs · 0 failed (0.000)
  search   15 runs · 5 conditions tried on 3 cases each
     condition                       failed         kind
  1  tool:issue_refund#1=lost_reply  3 of 3 failed  duplicate_write
  not looked at: faults turned off: slow, rate_limited, empty, cut_off, malformed, stale, planted_instruction; 0 single changes and 6 pairs of them untried
  these are candidates, not findings: a few runs each, chosen for having failed
  wrote    break-runs/refund-desk-1/hunt.json, proposals.jsonl, candidates.json and every run in store/
next: poisson-break confirm
```

`lost_reply` lets the tool act and then reports an error, as a network does when a reply is
lost on the way back. This desk answers a failed refund by sending it again, so the customer is
refunded twice. Break's `duplicate_write` check sees the same write tool run again with the
same arguments after a lost reply. The replay shows the two calls:

```text
note: Break calls your tools for real: run it against a test environment, never against anything that matters
failed  finding 1 on case damaged-4821, seed 32408516: duplicate_write
     tool          call  change                          real tool ran
  1  lookup_order  1     none                            yes
  2  issue_refund  1     tool:issue_refund#1=lost_reply  yes
  3  issue_refund  2     none                            yes
```

In the last column, the tool that ran for `issue_refund` is the stand-in. The example's real
`issue_refund` would open a connection to the payments service, and in a hunt it is never
called.

## Cases

The case file is JSON Lines, one case a line. A case needs only `input`:

```json
{"input": "Where is order 7?"}
{"id": "refund-late", "input": "Refund order 9.", "expect": {"calls": ["lookup_order", "issue_refund"], "reply_contains": "refunded"}}
{"id": "gold", "input": "Where is order 12?", "customer_tier": "gold"}
```

A case with no `id` is numbered by its place in the file. `expect` adds rules for that case: a
run is `wrong` when the reply lacks `reply_contains` or when the tools in `calls` were not
called in that order, and a run that calls a tool in `never_calls` fails as `forbidden_call`. Any other key is your agent's own
and reaches it in `cfg`. To make cases from requests your users already sent, see the recipes
for [LangSmith](../export/langsmith.md), [Langfuse](../export/langfuse.md) and
[Phoenix](../export/phoenix.md).

## Check it before you hunt

```sh
poisson-break doctor
```

`doctor` reads the settings and the cases, imports the agent, lists its tools and names the
first problem it finds. `doctor --run` also runs the first case once with no change, after
asking, and stores nothing. In the example's folder it prints:

```text
note: Break calls your tools for real: run it against a test environment, never against anything that matters
ready  refund_desk:refund_desk loads, with 2 tools and 6 cases
  tools  lookup_order, issue_refund
next: poisson-break hunt
```

## What rollout cannot do

Break reaches a rollout target's tools and its request. It does not sit between the agent and
its model, and it does not play a conversation's turns. So two kinds of change in the catalogue
are refused for a rollout target before any run: the conversation moves and the model faults.
They wait for adapters that are not in this version. An agent that is not reachable as a Python
function, such as one behind an HTTP service, also needs a way in this version does not have.
[Adding a way in](../extending/way-in.md) gives the interface one is written against.
