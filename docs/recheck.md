# Checking a fix

A finding names a condition under which your agent fails. After you change the agent, `recheck`
runs every finding's condition again on the agent as it is now, and says for each whether it
fails less than it did. This page goes round the whole loop on an example that runs with no key
and no network: hunt, confirm, put a fix in, recheck.

## Find something to fix

```sh
poisson-break init --example full-loop
poisson-break hunt --yes
poisson-break confirm --yes
```

The example is an order desk in `agent.py` that looks an order up once and gives up when the
look-up fails. The confirm stage ends with three findings, one for each way the look-up was
made to fail:

```text
confirmed  3 of 3 candidates fail more than the control (0.000)
     condition                         verdict    numbers
  1  tool:lookup_order#1=error         confirmed  1.000   +1.000
  2  tool:lookup_order#1=timeout       confirmed  1.000   +1.000
  3  tool:lookup_order#1=rate_limited  confirmed  1.000   +1.000
  wrote      break-runs/order-desk-1/findings/1.toml, 2.toml, 3.toml
  reference  54 runs
next: poisson-break findings 1
```

## Put the fix in

The folder also holds `agent_fixed.py`: the same desk, except that a failed look-up is tried
again, twice at most. Copy it over the agent.

```sh
cp agent_fixed.py agent.py
```

With your own agent this step is your own change, however you make it. `recheck` runs whatever
`[target] entry` in `break.toml` names, as it is now.

## Recheck

```sh
poisson-break recheck --yes --check
```

```text
plan  recheck 3 findings on the agent as it is now
  findings  1 tool:lookup_order#1=error, 2 tool:lookup_order#1=timeout, 3 tool:lookup_order#1=rate_limited
  runs      54: each finding over the cases and repeats of its reference run
  cap       120 runs, 2 hours
  estimate  54 runs, about 0 s; no prices, so no dollars, from the control stage's 0 s a run
note: Break calls your tools for real: run it against a test environment, never against anything that matters
rechecked  3 of 3 findings now fail less
  1  tool:lookup_order#1=error  fails less  1.000 before · 0.000 now
  2  tool:lookup_order#1=timeout  fails less  1.000 before · 0.000 now
  3  tool:lookup_order#1=rate_limited  fails less  1.000 before · 0.000 now
  gap  0.0 days since the reference runs
```

Three more `next:` lines follow, left out here because each holds a full path on the machine it
ran on: the `poisson-trace fix-check` command for each finding's whole report.

The plan comes first, as it does before anything that spends runs. Each finding is run over the
cases and repeats of its reference run, here 6 cases × 3 repeats, 18 runs a finding. Each line
of the result is one finding: its condition, a phrase, and the share of runs that failed before
and now.

| Phrase | What it means |
|---|---|
| `fails less` | Trace found the two shares different, and the new one lower |
| `fails more` | Trace found them different, and the new one higher |
| `no significant difference` | Trace had the runs to see the difference you asked about and did not see one |
| `too small to tell` | there were too few runs to decide; the line says how many repeats would |

A difference stands only after the p-values are adjusted across the findings rechecked
together, at the `q` in `[confirm]`.

## What the "before" is

A finding is chosen for having failed often in the confirm stage, so its share there runs high.
For that reason `confirm` gives every finding a second set of runs on fresh seeds, its
reference run, and `recheck` compares the agent as it is now with that.

The reference run was made when you confirmed, and the recheck is made now. `gap` says how many
days lie between them. If your agent calls a hosted model, the model may have changed in that
time, and a difference may be the model's and not your fix's. To rule that out, keep the old
agent importable and name it with `--old MODULE:NAME`, as in `recheck --old
agent_before:order_desk`. Break then runs the old agent and the new one now, on the same cases,
and compares those two sets of runs.

## In CI

`--check` makes the exit code carry the answer.

| Command | Exits 4 when |
|---|---|
| `poisson-break recheck --yes --check` | a finding fails more than it did |
| `poisson-break recheck --yes --check --strict` | a finding fails more, or is too small to tell |

Without `--check` a recheck that ran exits 0 whatever it found. Under `--json` the document's
`passed` says the same as the exit code.

## What a recheck does not show

`fails less` is about one condition on your cases. It does not show that the agent now handles
conditions no finding names, and a fix can make a new failure elsewhere. A new hunt on the
changed agent is the way to look for that. See [What Break does not claim](claims.md).
