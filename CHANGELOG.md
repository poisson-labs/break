# Changelog

## Unreleased

The first seven modules of Poisson Break: the repository, the package and its command, the
record every stored run carries, the four extension points, the catalogue of what Break varies
with the ten launch faults, the applier that puts a condition on one run's tool calls, the
failure check that decides whether a run failed, the settings file with the plan shown before
spending, the look everything Break prints goes through, and the runs themselves, stored on
Prove. A hunt's stages run from Python; the search, the confirm stage and the `hunt` command
come next.

- `poisson_break.hunt`: runs stored on Prove. `open_hunt(settings, target=, cases=, name=None,
  existing=False)` makes a hunt's folder and its `hunt.json`, or opens one that is there, and
  runs nothing. A `Hunt` is read-only: `name`, `folder`, `store`, `proposals`, `settings`,
  `cases`, `target`, `plan`, `reserve` and `budget()`. `latest_hunt(settings)` names the hunt
  made last.
- A hunt is named as given, if the name is letters, digits, `.`, `_` and `-`, starts with a
  letter or a digit and is at most 64 characters; one that is not, or is taken, is refused and
  never swapped for a number. With no name it is numbered from the last part of the target's
  entry, one above the highest number there.
- Refused when a hunt is opened, before anything is made: a control stage that does not fit
  (`SettingsError`), a tool the way in lists with no line in `[tools]` and a check that cannot be
  loaded or called (`HuntError`), a `[vary]` entry the way in cannot make (`NeedsAdapter`,
  naming the change), a stand-in that cannot be loaded (`ToolRefused`).
- `run_arm(hunt, arm, cases, condition, repeats=)` runs one condition on its cases as the Prove
  run `<hunt>-<arm>`; the arm's first word is its stage (`control`, `confirm`, `reference`,
  `recheck`). `run_search(hunt, entries, stage="search")` runs what a search hands over, each
  entry's condition on its own cases, into `<hunt>-search` or, for `stage="shrink"`,
  `<hunt>-shrink`. Each hands back one `RunRow` per run: `condition`, `case`, `seed`, `outcome`
  (`ok`, `failed`, `not counted`) and `kind`. `on_progress(done, total)` is told after each run.
- `control(hunt)` runs every case `control_repeats` times with no change and returns a
  `ControlSummary` read from the store: `runs`, `failed`, `not_counted`, `rate`, `per_case`,
  `calls` (for each case, each tool with the most calls of it in one run), `set_aside` (the
  cases that fail every counted run), `high_base_rate`, `dollars_per_run`, `seconds_per_run` and
  `rows`.
- Break decides every row. A row's outcome is `ok` or `failed`; an agent that raises and a run
  past its limit are `failed` rows with their kind, and only a run that could not be counted has
  no outcome, with one line of error. Every row carries its record under `poisson_break`, a run
  not counted included, beside `case_id` and nothing of the target's own. A tool that never
  returns is cut off at `run_seconds`, on the main thread of a program on macOS or Linux.
- An arm's cell is `{"case": <id>}`, so arms line up case for case; a search or shrink row's is
  the case and the condition's name. Seeds are Prove's, from a salt of `[search] seed` and the
  arm's own word: no two arms share one, and the same settings give the same seeds under any
  hunt name. An arm's rows carry the settings' strategy at probability 1, a search row the
  selection of the entry that produced it, and a shrink row the entry's strategy at
  probability 1.
- `Budget` (`runs`, `runs_spent`, `runs_left`, `dollars`, `dollars_spent`, `hours`,
  `seconds_spent`) is read from the store. `runs` counts the control, search and shrink rows.
  With prices, the next run is priced at the dearest run stored and a stage stops before a run
  that could pass `dollars`; the first run of a hunt always runs. `hours` is the stored runs'
  seconds, summed. `Hunt.reserve` is the number of runs a search leaves unspent for shrinking.
- `HuntStopped` is a stage that stopped short with every finished run stored: `reason` (`runs`,
  `dollars`, `hours`, `not counted`, `refused`, `tools`), `arm`, `kept`, `count`, `cause` and
  `tools`. More than a tenth of an arm's runs not counted stops it, judged after every run once
  ten are stored. A tool nobody classed stops it and that run is not stored. A tool the control
  saw called that the way in did not list stops the hunt after the control. Ctrl-C passes
  through as it is. `HuntError` is the module's own refusal before any run.
- A run is stored the moment it finishes, and a cell is run once in an arm: asked for again,
  its stored row is handed back. A hunt opened again with `existing=True`, under its own seed
  and cases, runs exactly what is missing on the same calls, under the settings handed in.
- `hunt.json` holds `schema` (`poisson_break.hunt/1`), `name`, `created`, `settings` as
  resolved, `cases`, `stages` and `arms`, each arm with its `stage`, `condition`, `cases` and
  `repeats`. It is rewritten whole when an arm starts.
- `RolloutTarget(fn, tools=)` is the way in for a plain Prove target, and `load_target(settings)`
  makes one from `target.entry`. It reads `reply`, `tokens_in`, `tokens_out` and `ended` from
  the episode's `meta`, each optional. `Limits(run_seconds)` is what a way in is handed.
  `Target`, `ToolInfo`, `RunResult` and `TARGET_INTERFACE_VERSION` are re-exported.
- Prove's planner gives the seeds and its store takes the rows, one row as each run finishes.
  Prove's runner is not used, and nothing is taken from a private module of Prove.

- `poisson_break.look`: one result, two renderings. A verb builds a `Result` (a verdict word,
  its sentence, the detail as `Row`, `Line` and `Table`, the commands to run next) or a `Plan`
  (a result whose verdict is `plan`, with an estimate and its source), and `render` prints it
  plain or pretty. Plain is text only, with no colour code and no box character, and needs
  nothing but the standard library: one line per fact on a pipe, wrapped at the terminal's width
  with a hanging indent on a terminal, the verdict line and a command never wrapped. Pretty
  carries the same facts in the same order, drawn with Rich.
- `mode_for` chooses: pretty only when stdout and stderr are both terminals, `NO_COLOR` is
  unset or empty, `CI` is unset, `TERM` is not `dumb`, stdout is UTF-8, and neither `--json` nor
  `--plain` stands before a `--`. Anywhere else, and wherever Rich cannot be imported, plain
  runs, byte for byte, and nothing is said about it.
- Colour has four meanings: green for a command that did what was asked (`found`, `confirmed`,
  `wrote`, `ready`, `rechecked`, `fails less`), yellow for one that stopped short or cannot say
  (`stopped`, `nothing found`, `not confirmed`, `too small to tell`, `did not fail`, `note:`),
  red for an error or a failed check (`error:`, `not ready`, `failed`, `fails more`), dim for
  secondary text. Any other verdict word is bold with no colour. A number is never coloured,
  and only the terminal's sixteen named colours, bold and dim are used.
- A table too wide for the terminal folds in pretty: a unit every cell of a column repeats
  moves into the header, and past that each row is printed as a record. Nothing is cut.
- `run(tool, argv, body)` runs a command under the look and returns its exit code, from `EXIT`:
  0 done, 1 refused, 2 usage, 3 stopped, 4 a check did not pass, 130 interrupted. `Refused` and
  `Usage` are one `error:` line on stderr with their `next:` commands under it; `Stopped`
  prints the result it carries; Ctrl-C prints `stopped  interrupted: ...`; anything unexpected
  is one line naming `~/.cache/poisson-break/errors.log`, where the traceback is appended, and
  `--debug` prints the traceback too. `error`, `note`, `out` and `err` write the lines.
- `ask(question, default, choices=None)` asks on stderr: `[y/N]` for a yes or no, `[default]`
  for text, a menu for `choices` (questionary's in pretty, a numbered list in plain). `--yes`
  answers without asking, and without it a stdin that is not a terminal refuses the question.
  `Progress(label, total)` shows work on stderr as one line, removed when the work ends.
- `as_json(result)`: the `--json` document, `schema`, `verdict` and `sentence` first, never a
  `NaN`.
- Numbers read the same everywhere: `fmt_rate` (`0.150`, and `+0.870` for a difference),
  `fmt_p` (`0.049`, `2.3e-08`), `fmt_dollars` (`$1.60`, `$0.0052`), `fmt_count` (`4,200`),
  `fmt_duration` (`1 min 40 s`, `1 h 36 min`), `fmt_time` (UTC with `Z`) and `fmt_hash` (12
  characters). `word` quotes a value for a shell and `command` joins a line that is never
  wrapped.
- A stream that cannot encode `·`, `–` or `×` gets `-`, `-` and `x`, and any other character it
  cannot encode is written as its escape, so two names never read as one. A control character
  in a value is shown as text and never acted on.
- The command goes through the look. It takes `--plain` and `--debug`, a mistake on the command
  line is drawn in the terminal's red on a terminal, and a failure inside the command is one
  line and exit 3.
- Rich (14.2.0 or later), questionary (2.1.1 or later) and prompt_toolkit (3.0.53 or later) are
  ordinary dependencies. A plain run loads none of them.
- The clean-install check also confirms that the three came with the wheel, and runs the
  command on a terminal, with colour and with `--plain`.

- `poisson_break.settings`: the settings file `break.toml`. `loads` reads its text and `load` a
  file into a frozen `Settings`, compared by what it holds; `dump` writes the file `init` writes,
  with every setting that has a value on its own line and each one that is off commented out,
  and `loads(dump(s)) == s`. Only `version`, `target.kind` and `target.entry` must be given; the
  defaults are 400 runs, 5 control repeats, 4 cases per condition, 8 candidates, 5 confirm
  repeats, a difference of 0.20, `q` 0.05, the first 3 calls, 120 seconds a run, 2 hours, the
  ten tool faults and five input operators on, the conversation and model calls off.
- The file is strict. An unknown key or table is refused with its dotted path, its line and the
  nearest known key within two edits. So is a value that means nothing: a kind, fault, operator,
  move, check or signal that is not one, read from the live catalogue so a fault registered from
  outside is taken; a count below 1 or not a whole number; a share outside 0 to 1; a `write`
  tool whose line does not say how it is made safe; a stand-in, a check of your own or a strategy
  not written `module:name`; a cap in dollars without both prices, or one price alone; `hours =
  inf` with no cap; a file with no `version` or one from a newer Break. Every refusal is a
  `SettingsError`, one line, with `.key`, `.line` and `.suggestion`. Two prices with no cap read
  as a cap of $5.00.
- Reading, checking and writing settings run nobody's code: no framework is imported, and
  neither is the target, the strategy, a stand-in or your own check. Nothing here asks what a
  way in can do; that is refused before any run by what holds the target.
- A `kind` whose way in is an optional extra (`openai-agents`, `langgraph`, `crewai`, `mcp`,
  `command`) parses with `loads`, and `load` refuses it in one line naming the install command
  until its module is there, found without importing it. The `adaptive` strategy parses and is
  refused by `load` the same way.
- `read_cases`: the case file, JSON Lines. A case needs only `input`, non-empty text; it may
  carry an `id`, an `expect` table (`reply_contains`, `calls`, `never_calls`), `variants` and
  `turns`, and any key of your target's own, which is kept. A case with no `id` takes its place
  among the cases, counted from 1, as text. A blank line is skipped and still counted. A line
  that is refused is named by its number.
- `INIT_FLAGS`, `settings_from_init_args` and `equivalent_init_command`: every setting has one
  flag, with `--tool` and `--env` repeating for a tool's line and a setting of your own, and the
  one command a shell can run that writes the same file byte for byte. Flags are written whole.
- `plan_hunt` and `plan_confirm`: the run counts a spending command shows before it starts, as
  frozen results. A hunt on 12 cases with the defaults is 60 control runs and up to 340 for
  search and shrink; confirming is 540 runs and up to 480 more for reference. A control stage
  that leaves no room for one condition is refused, naming the smallest `runs` that fits.
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
