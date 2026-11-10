# What Break does not claim

Break reports what it ran and what it saw. This page says where that stops, so that a result is
read for what it is.

## A hunt that finds nothing

A hunt that ends `nothing found` means this: under the conditions the hunt tried, on the cases
you gave it, in the runs it had, no condition failed more than the control. It does not mean
the agent is safe, robust or reliable, and Break never says so. Three limits apply to every
hunt.

- **It tried only what was allowed and reachable.** A fault that `[vary]` leaves out was not
  tried. A tool no case calls was not touched. A call later than `max_call` was not changed.
  Every result prints these under `not looked at`, with a count of the single changes and the
  pairs that had no run.
- **It tried only your cases.** A request no case resembles was not tested.
- **It tried each condition a few times.** The search runs a condition on a few cases. A
  failure that shows up one time in fifty can pass through a hunt unseen.

## A candidate

A hunt ends with candidates. A candidate is a condition that failed more than the control in
the few runs the search gave it, and it was chosen for having failed. That choice biases its
numbers upward. Break prints this under every list of candidates, and no candidate is called a
finding until the confirm stage has tested it on fresh runs.

## A finding

A finding is a candidate that the confirm stage tested against a control on fresh runs, every
case in both arms, and that failed more by Trace's test after the correction for testing
several candidates at once. What a finding says:

- Under this named condition, this agent failed more often than under no change, on these
  cases, by this much.

What it does not say:

- **How often the condition happens.** A finding says what the agent does when its look-up
  times out. It does not say how often your look-up times out.
- **That the failure matters.** `failed` means a run met the rule you set: an outcome you
  listed, a check of Break's, a check of your own. Whether that rule marks a real problem is
  your call.
- **Anything about other conditions.** A finding on a timeout says nothing about an error.

The share a finding failed at in the confirm stage is from the stage that selected it, so it
runs high. Each finding also gets a reference run on fresh seeds, and a fix is compared with
that.

## A recheck

`recheck` runs each finding again on the agent as it is now and gives one of four phrases.
`fails less` means the finding's condition now fails less often than it did in its reference
run, by Trace's test. It does not mean the agent is fixed for conditions the finding does not
name. `no significant difference` and `too small to tell` are not passes: the first saw no
change it could stand behind, and the second did not have the runs to see one.

A recheck against old runs also spans time. If your agent calls a hosted model, that model may
have changed between the two sets of runs. Break prints the gap in days, and `recheck --old`
runs the old agent and the new one side by side instead.

## The numbers

Break computes no statistic. Every test, interval and adjusted p-value it prints comes from
Poisson Trace or Poisson Prove, and each finding prints the Trace command that gives its full
report. Break's own arithmetic is a failure share: failed runs divided by runs.

## Its own search

Break says what a hunt tried, what it found and what it did not look at. It quotes no figure
for how much faster its search finds failures than chance would. No such figure has been
measured.

## A check that calls a model

No model grades a run in Break's own checks. A check of your own may call one. Every finding
that rests on your check says `judged by  your check`, and its numbers are as good as that
check.

## Your tools

Break calls your tools for real. A stand-in keeps a write tool from acting, and Break refuses a
write tool until its line says how it is made safe to repeat. Nothing else stands between a
hunt and what your tools do. Run Break against a test environment.

## What this version cannot test

- An agent it cannot call as a Python function with wrapped tools. Adapters for agent
  frameworks and for MCP servers are not in this version.
- Changes to the conversation and to the model's own calls. They are named in the catalogue and
  need those adapters.
- `async def` tools, which are refused.
- Anything on Windows. Break runs on macOS and Linux.
