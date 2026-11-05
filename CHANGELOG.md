# Changelog

## Unreleased

The first four modules of Poisson Break: the repository, the package and its command, the
record every stored run carries, the four extension points, the catalogue of what Break varies
with the ten launch faults, the applier that puts a condition on one run's tool calls, and the
failure check that decides whether a run failed. Nothing hunts yet.

- `poisson_break.checks`: deciding whether a run failed, from what the agent did. No model
  grades a run. `watch(run_agent, *, case, session, fails=None)` runs the target once, catches
  what escapes it (an exception is a crash, an agent's `SystemExit` among them; running out of
  time is a timeout; `KeyboardInterrupt` passes through), measures the seconds and hands back a
  frozen `FinishedRun`. `judge(run)` returns a `Verdict`: `ok`, `failed` with one kind, or
  `not counted`, with the outcome a stored run carries (`ok` or `failed`), who judged it and,
  for a run not counted, one line saying why. The kinds, the first that applies: `crashed`,
  `hung` (120 seconds by default), `ran_out`, `forbidden_call`, `followed_plant`,
  `duplicate_write`, `failed` (an outcome of the target's that `outcomes` lists), `wrong` (the
  case's `reply_contains`, `calls`, `never_calls`), then a promoted signal's own word, then
  `own:<word>` from your check. `checks` in the settings turns any of the seven words of
  `CHECKS` off and nothing else. `signals(run)` counts `gave_up`, `retry_storm` (more than
  `retry_storm_after` calls of one tool in a row, 5 by default) and `over_budget`
  (`max_tool_calls`, `max_tokens`); a signal is a failure only when `also` names it. A run the
  session stopped for an instrument error or a refused tool is not counted, whatever else it
  met.
- Your own check, named in `own` by its import path, is called with one read-only `RunView` and
  nothing else, only on a run everything before it found ok. It returns `None` for ok or a
  failure kind, a word of ASCII letters, digits, `_` and `-`. Anything else it returns or
  raises makes the run not counted, never failed. The view shows the case as the run saw it,
  the condition and whether each change applied, every tool call with its arguments, what the
  agent saw and whether the real tool ran, the reply, the target's outcome, tokens, seconds, and
  the kinds Break's checks give with every one on. What it holds is a private copy, so a check
  cannot change a run.
- `poisson_break.apply`: `Session.seen` keeps each call's arguments and what the agent was
  handed back, apart from the two records, which still hold no content; `Session.tools` is each
  tool's line as given.
- `poisson_break.records`: a `Failure`'s kind may be a signal's own word, for one the settings
  promote.
- `poisson_break.apply`: `Session`, one run's applier. A way in routes every tool call through
  `session.call(tool, args, real)`, which returns what the agent should see or raises
  `ToolFailure` (a `TimeoutError` too when its kind is `timeout`). Calls are numbered per tool;
  the first change in the condition's order that applies to a call lands on it, and any other
  change on that call does nothing. Under the control the agent gets the tool's own object and
  the tool's own exception. `session.calls` and `session.applied` are the two records a stored
  run carries: every tool call with the change that landed and whether the real tool ran, and
  every change with whether it applied and the first call it landed on. A fault's `previous` is
  what the real tool last returned, held as a copy. Each tool is classed `read`, `write` or
  `off`: a `write` tool must be `repeatable` or have a stand-in, `lost_reply` is taken only on a
  tool safe to repeat, an `off` tool is never touched, a stand-in replaces its tool in every
  run, and each refusal is `ToolRefused` naming the tool, when the session is made or, for a
  tool with no line, on the call. Break's own failure, a fault's or a stand-in's is an
  `InstrumentError` held in `session.stopped`, after which every call raises the same error and
  runs nothing; the real tool's own exception passes to the agent untouched. The session sleeps
  the delay a result states, and `run_seconds` is the run's wall-clock limit: past it,
  `RunOutOfTime`, which an agent's `except Exception` does not catch. `session.case(case)` gives
  the case with the condition's input operators and conversation moves applied. `wrap(tool_name,
  fn)` is the one call a Prove target adds per tool, and `with session:` opens the run around
  the agent; an `async def` tool is refused. `ToolInfo` and `RunResult` are what a way in hands
  the core.
- Five scripted agents for the tests, in `tests/agents/`: one retries, one gives up, one follows
  planted text, one repeats a write, and one speaks only the way-in protocol. No model and no
  framework.
- `poisson_break.changes`: changes and conditions by name (`parse`, `name`), canonical and
  round-tripping, with a bad name refused and the nearest valid name offered when one is within
  two edits; whether a change applies to a call (`applies`): a schedule by the call number alone,
  a rate by a keyed draw of the seed, the tool and the call; the five input operators and the four
  conversation moves as pure functions of a case and a seed; the catalogue (`CATALOG`) of the ten
  tool faults, five input operators, four conversation moves and five model faults, each with a
  one-line description and its defaults (`delay` 5 s, `wait` 30 s, `length` 200 characters,
  `typos` share 5%); the ten launch faults, each a `Fault` that is given a frozen `CallContext`
  and returns a `Result` or a `ToolError`; `register` for a fault written outside the package;
  `run_fault`, which counts the real tool's calls against the fault's declaration and turns a
  fault's mistake into an `InstrumentError`; `check_capabilities`, which refuses before any run a
  condition that asks of a way in something it cannot do (`NeedsAdapter`); and `marker`, the
  planted word derived from the hunt and the case.
- The package `poisson-break`, importing as `poisson_break`, with the command `poisson-break`
  (`python -m poisson_break` is the same). `--version` prints one line with the versions of
  Break, Prove, Trace and Python; `--help` gives a description and an example; a mistake on the
  command line is one `error:` line on stderr and exit 2, and abbreviated options are refused.
- `poisson_break.records`: the record each stored run carries under the key `poisson_break` in
  the run's extra facts, in the published shape `poisson_break.run/1`: the hunt, the stage, the
  arm, the case, the condition with each of its changes and whether and where it applied, the
  failure kind and the three signals, the strategy and the probability it gave the condition,
  every tool call, who judged the run and the target's own outcome. Frozen types that round-trip
  through JSON and refuse a field the shape does not name or a value outside its closed set.
- `poisson_break.interfaces`: the four extension points, each at version 1: a fault, a way in,
  a strategy and your own failure check.
- Prove pinned to the exact version Trace pins (0.1.2). Trace is not yet on PyPI; its pin is
  declared the day it is.
- CI: lint, type check and the tests on Python 3.11 to 3.13, under a guard that fails any
  connection and a check that no statistic is computed locally; a clean install of the built
  wheel into a fresh environment outside the checkout that runs the command.
