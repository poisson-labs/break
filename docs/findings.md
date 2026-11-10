# Reading a finding

A finding is a condition under which your agent failed more often than it does with no change,
tested on fresh runs against a control. This page reads one, line by line. It uses the help
desk example, which runs with no key and no network, so you can produce every line below
yourself.

```sh
poisson-break init --example desk
poisson-break hunt --yes
poisson-break confirm --yes
```

`hunt` ends with candidates. `confirm` tests them and writes the ones that hold as findings:

```text
confirmed  3 of 3 candidates fail more than the control (0.000)
     condition                         verdict    numbers
  1  tool:lookup_order#1=timeout       confirmed  1.000   +1.000
  2  tool:lookup_order#1=rate_limited  confirmed  1.000   +1.000
  3  tool:lookup_order#1=error         confirmed  1.000   +1.000
  wrote      break-runs/desk-1/findings/1.toml, 2.toml, 3.toml
  reference  54 runs
next: poisson-break findings 1
```

Each row is one candidate with Trace's verdict on it. The two numbers are the share of runs
that failed under the condition, and the difference between that share and the control's. The
control's own share is in the first line, in brackets.

A candidate gets one of three verdicts. `confirmed` means Trace found the two shares different,
the candidate's higher, and the result held after the correction for testing several candidates
together. `too small to tell` means the stage did not have the runs to decide, and the row says
how many repeats would. `not confirmed` is anything else. Only a confirmed candidate becomes a
finding.

## The list

```sh
poisson-break findings
```

```text
ok  3 findings in desk-1
     condition                         rate   difference
  1  tool:lookup_order#1=timeout       1.000  +1.000
  2  tool:lookup_order#1=rate_limited  1.000  +1.000
  3  tool:lookup_order#1=error         1.000  +1.000
next: poisson-break findings 1
```

A finding is a number within its hunt. `findings` reads the latest hunt, and `--hunt NAME`
reads another. If a case failed in the control stage, with no change at all, the list names it
under a `control` heading: those failures are the agent's own, and they are the first thing to
look at.

## One finding

```sh
poisson-break findings 1
```

```text
ok  finding 1: tool:lookup_order#1=timeout
  fails       1.000 under it, 0.000 under the control
  difference  +1.000
  p           3.1e-08, adjusted 3.1e-08, q 0.050
  kinds       failed 18
  signals     gave_up 18, retry_storm 0, over_budget 0
  judged by   break
  flagged     none
  left out    not re-run on the old version 0, not re-run on the new version 0, no outcome on the old version 0, no outcome on the new version 0
  cases       6 cases × 3 repeats, in confirm stage 1
  arms        desk-1-confirm-1 against desk-1-confirm-control
  reference   desk-1-reference-1
next: poisson-break replay 1 --hunt desk-1
```

The output ends with one more `next:` line, left out here because it holds a full path on the
machine it ran on: the `poisson-trace fix-check` command that prints Trace's whole report for
this finding.

| Line | What it says |
|---|---|
| `finding 1: tool:lookup_order#1=timeout` | the condition: the first call to `lookup_order` in a run raises a timeout |
| `fails` | the share of runs that failed under the condition and under the control, over the same cases and repeats |
| `difference` | the first share less the second, with Trace's interval in brackets when it gives one |
| `p` | the p-value of Trace's test, the same value adjusted across the candidates tested together, and the level `q` it was held to |
| `kinds` | why the failed runs failed, counted. `failed` is an outcome your settings list as failing; the other kinds are in the table below |
| `signals` | three things counted beside every run that are not failures on their own: `gave_up`, `retry_storm`, `over_budget` |
| `judged by` | `break` when Break's own checks decided every failed run, `your check` when a check of yours decided one |
| `flagged`, `left out` | cases Trace flagged, and Trace's count of runs it could not compare |
| `cases` | the design: every case, the same number of repeats, in both arms |
| `arms` | the two sets of runs that were compared, by name |
| `reference` | the finding's reference run, which a later fix is compared with |

Here all 18 runs under the condition failed and none of the control's 18 did. `gave_up 18`
says how: in every one of those runs the look-up failed and the agent never called it again.

## Why a run failed

A failed run has one kind, the first of these that applies:

| Kind | Applies when |
|---|---|
| `crashed` | an exception escaped the agent |
| `hung` | the run passed its time limit (`run_seconds`, 120 unless set) |
| `ran_out` | the agent hit its own turn or step limit |
| `forbidden_call` | the agent called a tool the settings or the case forbid |
| `followed_plant` | a planted marker word appeared in the reply or in a later tool call |
| `duplicate_write` | after a lost reply, the same write tool ran again with the same arguments |
| `failed` | the agent reported an outcome that `[fails] outcomes` lists |
| `wrong` | the case's `expect` was not met |
| a signal's word | a signal that `[fails] also` promotes counted something |
| `own:<word>` | your own check returned that word |

No model decides any of these. Each is computed from what the agent did. A run Break itself
could not complete, because a fault, a stand-in or Break went wrong, is not counted as the
agent's failure. It is left out, and Break says why.

## See it happen

```sh
poisson-break replay 1
```

```text
note: Break calls your tools for real: run it against a test environment, never against anything that matters
failed  finding 1 on case status-4821, seed 56661626: failed
     tool          call  change                       real tool ran
  1  lookup_order  1     tool:lookup_order#1=timeout  no
```

`replay` runs the finding once more and stores nothing. It picks the case that failed most
under the finding, on the seed of that case's first failed run, and lists every tool call the
agent made with the change that landed on it. `--case ID` picks another of the finding's cases.

## The file

Each finding is a file, `break-runs/<hunt>/findings/<n>.toml`, plain TOML that can be committed
and read by anything:

```toml
schema = "poisson_break.finding/1"
number = 1
hunt = "desk-1"
condition = "tool:lookup_order#1=timeout"
cases = ["status-4821", "status-4823", "status-4825", "refund-4822", "refund-4824", "refund-4826"]
repeats = 3
stage = 1
arm = "desk-1-confirm-1"
control_arm = "desk-1-confirm-control"
rate = 1.0
control_rate = 0.0
difference = 1.0
p = 3.125000000000001e-08
adjusted_p = 3.125000000000001e-08
q = 0.05
judged_by = "break"
flagged = []
reference = "desk-1-reference-1"
replay = "poisson-break replay 1 --hunt desk-1"
trace = "poisson-trace fix-check desk-1-confirm-control desk-1-confirm-1 --inputs all --event failed --max-mde 0.2 --store <the hunt's store, as a full path>"

[kinds]
failed = 18

[signals]
gave_up = 18
retry_storm = 0
over_budget = 0

[left_out]
"not re-run on the old version" = 0
"not re-run on the new version" = 0
"no outcome on the old version" = 0
"no outcome on the new version" = 0
```

The `trace` line holds the store's full path where `<...>` stands here.

## As JSON

Every command takes `--json` and prints one document, its first keys `schema`, `verdict` and
`sentence`.

```sh
poisson-break findings --json
```

```json
{
  "schema": "poisson_break.findings-result/1",
  "verdict": "ok",
  "sentence": "3 findings in desk-1",
  "hunt": "desk-1",
  "findings": [
    {
      "number": 1,
      "condition": "tool:lookup_order#1=timeout",
      "rate": 1.0,
      "difference": 1.0
    },
    {
      "number": 2,
      "condition": "tool:lookup_order#1=rate_limited",
      "rate": 1.0,
      "difference": 1.0
    },
    {
      "number": 3,
      "condition": "tool:lookup_order#1=error",
      "rate": 1.0,
      "difference": 1.0
    }
  ],
  "control": [],
  "next": [
    "poisson-break findings 1"
  ]
}
```

`control` lists each case that failed in the control stage; it is empty here because none did.
`poisson-break findings 1 --json` carries every field of the finding's file under `finding`.

## What a finding is not

A finding says the agent fails more under one named condition, on your cases. It does not say
how often that condition happens to you, or that nothing else is wrong. See
[What Break does not claim](claims.md). To test a fix against a finding, see
[Checking a fix](recheck.md).
