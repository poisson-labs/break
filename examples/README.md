# The examples

These are five small agents to try Break on. Each has a scripted model in place of a real one: a function
that decides what the agent does next from the request and from what its tools returned. So
each runs with no key and no network, and does the same thing every time.

The examples ride in the installed package. `poisson-break init --example NAME` writes one into
the folder you are in: the agent, its cases and `break.toml`. `init` will not write over a file
that is already there, so each example below is made in a new folder of its own.

Every result on this page is the output of the commands above it.

| Example | Shows |
|---|---|
| [`desk`](#desk) | a first hunt and confirm |
| [`full-loop`](#full-loop) | hunt, confirm, put a fix in, recheck |
| [`stand-in`](#stand-in) | an agent with a tool that changes something, hunted without that tool ever running |
| [`own-check`](#own-check) | a failure only a rule of your own can see |
| [`own-fault`](#own-fault) | a fault Break's catalogue does not have, added from your own module |

## desk

This is a help desk for an online shop. It looks an order up, and for a refund request it also reads
the refund policy. When the look-up fails it gives up; when the policy cannot be read it
answers without it.

```sh
mkdir desk
cd desk
poisson-break init --example desk
poisson-break hunt --yes
poisson-break confirm --yes
cd ..
```

```text
found  3 candidates in 42 runs
  control  12 runs · 0 failed (0.000)
  search   30 runs · 10 conditions tried on 3 cases each
     condition                         failed         kind
  1  tool:lookup_order#1=timeout       3 of 3 failed  failed
  2  tool:lookup_order#1=rate_limited  3 of 3 failed  failed
  3  tool:lookup_order#1=error         3 of 3 failed  failed
  not looked at: faults turned off: slow, cut_off, malformed, stale, lost_reply, planted_instruction; 0 single changes and 33 pairs of them untried
  these are candidates, not findings: a few runs each, chosen for having failed
next: poisson-break confirm
```

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

There are three findings, all on the order look-up: a timeout, a rate limit and an error each
end the request. The faults on the policy tool, an empty look-up result and the two changes to the
request were tried too, and none made the desk fail.

## full-loop

`agent.py` is an order desk that looks an order up once, and `agent_fixed.py` is the same desk
with a failed look-up tried again. The example goes round the whole loop.

```sh
mkdir full-loop
cd full-loop
poisson-break init --example full-loop
poisson-break hunt --yes
poisson-break confirm --yes
cp agent_fixed.py agent.py
poisson-break recheck --yes --check
cd ..
```

`confirm` ends with three findings, as the help desk's does. After the fix is copied in,
`recheck` runs each finding's condition again:

```text
rechecked  3 of 3 findings now fail less
     condition                         verdict     numbers
  1  tool:lookup_order#1=error         fails less  1.000 before · 0.000 now
  2  tool:lookup_order#1=timeout       fails less  1.000 before · 0.000 now
  3  tool:lookup_order#1=rate_limited  fails less  1.000 before · 0.000 now
  gap  0.0 days since the reference runs
```

Each finding failed in every run of its reference run and in none now.
[Checking a fix](https://github.com/poisson-labs/break/blob/main/docs/recheck.md) explains each part.

## stand-in

This is a refund desk. Its `issue_refund` tool asks a payments service to pay a customer back, which
must not happen in a test. `break.toml` classes the tool `write` and names a stand-in,
`payments_fake:issue_refund`, and Break calls the stand-in in the tool's place in every run.

```sh
mkdir stand-in
cd stand-in
poisson-break init --example stand-in
poisson-break hunt --yes
poisson-break confirm --yes
poisson-break replay 1
cd ..
```

```text
found  1 candidate in 27 runs
  control  12 runs · 0 failed (0.000)
  search   15 runs · 5 conditions tried on 3 cases each
     condition                       failed         kind
  1  tool:issue_refund#1=lost_reply  3 of 3 failed  duplicate_write
  not looked at: faults turned off: slow, rate_limited, empty, cut_off, malformed, stale, planted_instruction; 0 single changes and 6 pairs of them untried
  these are candidates, not findings: a few runs each, chosen for having failed
next: poisson-break confirm
```

```text
confirmed  1 of 1 candidate fails more than the control (0.000)
     condition                       verdict    numbers
  1  tool:issue_refund#1=lost_reply  confirmed  1.000   +1.000
  wrote      break-runs/refund-desk-1/findings/1.toml
  reference  18 runs
next: poisson-break findings 1
```

There is one finding. `lost_reply` lets the refund go through and then reports an error. The desk
answers an error by sending the refund again, so the customer is paid twice, and Break's
`duplicate_write` check sees the second call. An `error` or a `timeout` on the same call does
no harm, because under those the tool never acted. The replay shows the two refund calls:

```text
failed  finding 1 on case damaged-4821, seed 32408516: duplicate_write
     tool          call  change                          real tool ran
  1  lookup_order  1     none                            yes
  2  issue_refund  1     tool:issue_refund#1=lost_reply  yes
  3  issue_refund  2     none                            yes
```

## own-check

This order desk always answers. When its look-up fails it sends a confident reply anyway and
reports `resolved`, so none of Break's own checks sees anything wrong. The folder's `checks.py`
holds the team's own rule, named in `break.toml` as `[fails] own`: a reply that says where the
order is, sent after every look-up failed, is made up.

```sh
mkdir own-check
cd own-check
poisson-break init --example own-check
poisson-break hunt --yes
poisson-break confirm --yes
poisson-break findings 1
cd ..
```

```text
found  3 candidates in 24 runs
  control  12 runs · 0 failed (0.000)
  search   12 runs · 4 conditions tried on 3 cases each
     condition                         failed         kind
  1  tool:lookup_order#1=error         3 of 3 failed  own:made_up
  2  tool:lookup_order#1=timeout       3 of 3 failed  own:made_up
  3  tool:lookup_order#1=rate_limited  3 of 3 failed  own:made_up
  not looked at: faults turned off: slow, cut_off, malformed, stale, lost_reply, planted_instruction; 0 single changes and 0 pairs of them untried
  these are candidates, not findings: a few runs each, chosen for having failed
next: poisson-break confirm
```

The kind `own:made_up` is the word the check returned. `findings 1` marks the finding as resting
on that check:

```text
ok  finding 1: tool:lookup_order#1=error
  fails       1.000 under it, 0.000 under the control
  difference  +1.000
  p           3.1e-08, adjusted 3.1e-08, q 0.050
  kinds       own:made_up 18
  signals     gave_up 18, retry_storm 0, over_budget 0
  judged by   your check
  flagged     none
  left out    not re-run on the old version 0, not re-run on the new version 0, no outcome on the old version 0, no outcome on the new version 0
  cases       6 cases × 3 repeats, in confirm stage 1
  arms        order-desk-1-confirm-1 against order-desk-1-confirm-control
  reference   order-desk-1-reference-1
next: poisson-break replay 1 --hunt order-desk-1
```

## own-fault

This is an order desk, with a fault the team wrote in `faults.py`: `error_page`, under which a
tool returns a page of HTML with no error raised. The agent's module imports `faults.py`, which
registers the fault, and `break.toml` names it in `[vary] tools` beside three of Break's own.

```sh
mkdir own-fault
cd own-fault
poisson-break init --example own-fault
poisson-break hunt --yes
poisson-break confirm --yes
poisson-break replay 1
cd ..
```

```text
found  1 candidate in 24 runs
  control  12 runs · 0 failed (0.000)
  search   12 runs · 4 conditions tried on 3 cases each
     condition                       failed         kind
  1  tool:lookup_order#1=error_page  3 of 3 failed  crashed
  not looked at: faults turned off: slow, empty, cut_off, malformed, stale, lost_reply, planted_instruction; 0 single changes and 0 pairs of them untried
  these are candidates, not findings: a few runs each, chosen for having failed
next: poisson-break confirm
```

```text
confirmed  1 of 1 candidate fails more than the control (0.000)
     condition                       verdict    numbers
  1  tool:lookup_order#1=error_page  confirmed  1.000   +1.000
  wrote      break-runs/order-desk-1/findings/1.toml
  reference  18 runs
next: poisson-break findings 1
```

There is one finding, and it names the team's fault. The desk tries a look-up again when it raises an
error, so Break's `error`, `timeout` and `rate_limited` do it no harm. An error page raises
nothing; the desk reads it as an order record and falls over. The replay shows the call:

```text
failed  finding 1 on case status-4821, seed 56661626: crashed
     tool          call  change                          real tool ran
  1  lookup_order  1     tool:lookup_order#1=error_page  no
```

[Adding a fault](https://github.com/poisson-labs/break/blob/main/docs/extending/fault.md) explains how a fault is written.
