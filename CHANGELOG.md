# Changelog

## 0.1.0 (2026-11-13)

The first release, an alpha. Break runs an agent many times while changing how its tools behave
and what the user asks, keeps the conditions that fail more than a control, confirms them on
fresh runs with Poisson Trace's test, and checks a fix against them later. This version has one
way in, `rollout` (an agent Break calls as a Python function), ten tool faults, five input
operators, two search strategies that do not learn, and eight commands.

What a first user gets:

- `pip install poisson-break`, then `poisson-break init --example desk`, `hunt --yes` and
  `confirm --yes` end with three findings on a help desk agent, with no key and no network.
- Five examples, each written into a folder by `init --example NAME` and each run offline
  against a scripted model: `desk`, `full-loop` (hunt, confirm, a fix, recheck), `stand-in` (a
  write tool that is never really called), `own-check` (a failure rule of your own) and
  `own-fault` (a fault of your own). They ride in the wheel.
- The docs: the catalogue, reading a finding, checking a fix, the rollout way in, recipes for
  making cases from LangSmith, Langfuse and Phoenix exports, what Break does not claim, and one
  page for each of the four extension points, and a reference for the commands, the settings
  file, the stored runs and the library. Every command the README and the docs show is
  run in CI from the installed wheel, and every program they show is run there too.
- `catalog --labels` shows, beside a change, the labels it carries from the OWASP Top 10 for
  LLM Applications 2025 and NIST AI 100-2 E2025, where the table has a row for it. Each row
  quotes the published text it rests on.

Changed since the last development build:

- The installed `poisson-break` puts the folder it runs in first on the import path, as
  `python -m poisson_break` does, so an agent, a stand-in, a check or a strategy in a module
  beside `break.toml` loads under both.
- A tool fault of your own can be named in `[vary] tools`. Reading `break.toml` takes a name
  the catalogue does not hold; `doctor`, `hunt` and `open_hunt` refuse one that is still
  unknown once the agent's module is loaded, before any run, naming it
  (`changes.check_registered`, `changes.UnknownFault`).
- Every detail row and estimate line says one in the singular ("1 run left", "1 case × 3
  repeats"), as the verdict sentences already did.
- A hunt taken up with no prices set estimates over the runs it has left, and once its control
  has run, from the control's seconds a run.
- `none`, given to `--outcomes` or `--own-check` or answered to their questions, means no
  outcome counts as a failure and there is no check of your own. It was written as an outcome
  named "none", and refused as a check's import path.
- `init` asks only about what the way in can reach, read from the way in itself: a `rollout`
  target is not asked whether Break may change the model's calls or the conversation, and
  `--yes` varies neither for it. `break.toml`'s comments list only the kind and the strategies
  this version runs. A `[vary]` line the way in cannot make is named, in `doctor`, `hunt`,
  `confirm` and `recheck` alike, with what to write there, and the command printed under it is
  the `init` command that writes the file with that line emptied.
- `init` asks three things where it asked up to nine: where the agent is, where the cases are,
  and for each tool one yes or no on whether calling it changes anything, even in a test
  environment, in place of a `read`, `write` or `off` menu about changes outside it. The kind,
  what fails a run, what Break may change, the runs, the prices and the cap take their defaults
  without a question; `init` lists them after `wrote` and says `break.toml` is where to change
  them. Every flag still sets its value.
- The package's version is 0.1.0, its status Alpha. An sdist is built beside the wheel and
  holds only the source, the tests, the docs, the examples, the scripts and the project's own
  files.

Everything in the release, module by module:

- The commands: `init`, `doctor`, `hunt`, `confirm`, `findings`, `replay`, `recheck` and
  `catalog`, each with its own `--help`. The command computes nothing: every number it prints
  is the settings module's, the runs module's, the search module's or the confirm module's, and
  what is in `poisson_break.cli` is the command line, the words on screen and the order of the
  calls. Every verb prints one result through the look, takes `--json` for one strict document
  named `poisson_break.<verb>-result/1`, and keeps the shared exit codes. A verb that spends
  shows its plan and asks `start?` first; `--yes` answers, `--dry-run` runs nothing and writes
  nothing, and no terminal without `--yes` is the plan and a refusal in one line. After every
  plan, and in `init`'s and `doctor`'s output, the note that Break calls your tools for real.
- `init` asks only what Break cannot find out for itself: where the agent is, where the cases
  are, and for each tool whether calling it changes anything, with a yes followed by whether it
  is safe to repeat and, if not, where its stand-in is. The tools of a `rollout` target are the
  ones its module wraps while it is imported (never run). Every other setting takes its default,
  and `init` lists what it chose and says `break.toml` is where to change it. Every setting has a
  flag; `--yes` takes every default and needs `--entry`. It writes `break.toml`, refuses to
  write over one without `--force`, writes `cases.jsonl` only when the starter file was asked
  for, and ends with the one command that writes the same file, which runs as printed with no
  terminal; a kind whose adapter is not installed is still written, with the `pip install` line
  first. A line it prints back (`--force`, `--entry MODULE:NAME`) is the user's own words.
- `doctor` finds the first problem of the settings, the cases, the target, the strategy, the
  changes the way in cannot make, each tool line and stand-in and your own check, and says
  `not ready`, exit 4, in one line with the command to run next: `init` when there is no
  settings file, `doctor` once the line it names is mended. `--run` runs the first case once
  with no change, asked first, and stores nothing; a tool the agent calls that nobody classed
  is `not ready` naming it, with the `init` command that writes the settings back with that
  tool `off`.
- `hunt` runs the control, the search and the shrink stage, writes the candidates best first,
  and shows each with how many of its runs failed and the kind most of them had; a hunt that
  finds nothing prints what it did not look at first. A cap's stop and Ctrl-C say what was
  kept and print `hunt --hunt NAME`, which goes on with the same hunt and runs no stored cell
  again. A control that fails more than half its runs is a `note:` carrying its rate.
- `confirm` plans from the control stage's measured cost, runs the stage or finishes the one on
  disk under its written design (its plan then says what is left), asks Trace about each
  candidate and writes the findings; `--repeats N` asks again about the candidates too small to
  tell, and is refused before any plan when there is nothing to ask again. `findings` lists them
  with each case that failed in the control under a `control` heading, and `findings N` shows
  one with its numbers as the look prints them, the command that replays it and Trace's
  command for its full report. `replay` asks nothing before its one run. `recheck` prints one
  of Trace's four phrases a finding with the rates before and now, the gap in days since the
  reference runs, and `--check` exits 4 on a finding that fails more, `--strict` adding too
  small to tell. `catalog` needs no settings file.
- A stage stopped by a tool nobody classed names it, and prints first the `init` command that
  writes the settings back as they are with every such tool classed `off`, then the resume.
  A refusal over a finding file that cannot be read names the file by a path that leads to it,
  and prints no `next:`.
- `poisson_break.apply`: `wrapped_while(import_path)` names the tools wrapped while a module is
  imported, in order, each once. `poisson_break.hunt`: `run_once(settings, target=, case=)`
  runs one case once with no change, stored nowhere; a tool nobody classed raises
  `ToolRefused`. `poisson_break.settings`: `install_command(kind)` is the `pip install` line
  for a kind whose way in is not installed, or `None`; `load`'s refusal names the same line.
  `poisson_break.hunt`: `Hunt.stored()` is every arm the hunt's store holds, by its word, with
  the rows Prove counts in it. `poisson_break.confirm`: `read_stages(hunt)` is each confirm
  stage written, a `Stage` with its arms' rows; `Replayed.error` carries a run not counted's
  one line of error; `read_findings(hunt)` reads every finding file in number order and
  refuses the whole call on
  one it cannot read; each confirm stage in `confirm.json` carries the `q` and
  `max_difference` it was begun under, and is judged under those. `poisson_break.look`:
  `show(result)` prints a result the way the current run prints one, and plain outside a run.
- The command reads the confirm stages through `read_stages` and the store through
  `Hunt.stored`, never `confirm.json` or Prove's store itself; a `confirm.json` that cannot be
  read is refused in one line. Each `--json` document's fields are fixed: a plan is
  `poisson_break.<verb>-plan/1` with `dollars` beside its estimate and `runs` what it may make
  from here; `init` names `cases_file`; every `not ready` carries `key`, `line` and
  `unclassed`; each tested candidate and rechecked finding carries `no_outcome` and `left_out`;
  `confirm` names the files it `wrote`; the listing's `control` is null while the control is
  not finished; a Ctrl-C document carries a stop's keys. A dry run of `hunt --hunt NAME` plans
  what the hunt has left, and a hunt taken up after its control, with prices, is priced at the
  control's cost of one run. A verdict sentence says a count of one in the singular.

- `poisson_break.confirm`: confirming findings. `write_candidates(hunt, conditions)` keeps a
  hunt's candidates, best first, in its `candidates.json`, and `read_candidates(hunt)` reads
  them back; no condition at all, a condition twice in any spelling, the empty condition, more
  than the settings' `candidates`, and writing again once a confirm stage is on disk are each
  refused. `design(candidates, settings, control)` works out the confirm stage and runs
  nothing: one control arm and one arm for each candidate, every arm on every case the control
  did not set aside, the settings' `repeats` times each, with the run counts `plan_confirm`
  gives and their cost at what one control run cost.
- `confirm(hunt)` writes the design to the hunt's `confirm.json` before the stage's first run,
  runs the arms on seeds no earlier stage used, and hands back a `Confirmation`: the stage, its
  design, a `Tested` for every candidate and a `Finding` for each one confirmed. A stage that
  stopped is taken up again under its written design, whatever the settings say by then, and a
  finished stage asked again runs nothing and gives the same answer.
- Every number is Trace's or Prove's. Each candidate's arm is put to Trace once, against the
  shared control arm, as `python -m poisson_trace fix-check OLD NEW --inputs all --event failed
  --max-mde X --store STORE --json`, run with the Python Break runs on, in the hunt's folder,
  and what is read is the JSON it prints, whatever its exit code (`ask_trace`). The candidates'
  p-values are adjusted together with Prove's `bh` at the settings' `q`. A failure share is two
  of Trace's counts divided, and the module computes nothing else.
- The verdicts: `confirmed` when Trace says *different*, the candidate's arm failed more and
  the adjusted p-value is at or under `q`; `too small to tell` when Trace says so, with its
  count of repeats that would decide; `not confirmed` otherwise, with the note `failed less`,
  `not after the correction` or `nothing to compare` where one applies. A candidate with
  nothing to compare has no numbers and is left out of the adjustment. `no_outcome` names the
  cases with no run that has an outcome in one of the two arms, beside Trace's own count of
  what it left out.
- `confirm(hunt, repeats=N)` asks again after a *too small to tell*: a new stage of only the
  candidates the latest stage called *too small to tell*, with its own control arm, on new
  seeds, read on its own and never pooled with the earlier stage. It is refused while the
  latest stage has runs missing and when nothing was too small.
- A finding is numbered within the hunt from 1 in the order confirmed and written to
  `findings/<n>.toml` (`write_finding`), plain TOML with its schema name first and a value that
  is none left out; `read_finding` reads it back equal. It holds the condition by name, the two
  failure shares, Trace's difference, interval and p-value, the adjusted p-value and `q`, the
  failure kinds and signals counted over its arm, whether a failed run was judged by your own
  check, what Trace flagged and left out, its cases, repeats, stage and arms, its reference
  arm, the command that replays it and the Trace command for its full report.
- Each finding gets a reference arm, `reference-<n>`: the same agent under the finding's
  condition, every case of its stage again, on fresh seeds, run at the end of `confirm` with
  the finding's file written first. `reference(hunt)` runs what is missing of them.
- `replay(hunt, finding)` runs one finding once and stores nothing: on the first of its cases
  with the most failed runs in its confirm arm, on the seed of that case's first failed run,
  or on the case given, on the seed of its first run. It hands back a `Replayed`: the outcome,
  the kind and every call in order with the change applied to it.
- `recheck(hunt)` runs every finding on the agent as it is now, over the cases and repeats of
  its reference arm, in arms `recheck-<n>-<finding>`, asks Trace about the reference arm and
  the new one, adjusts across the findings with `bh`, and hands back a `Rechecked` for each
  with one of four phrases read from Trace's verdict and direction: `fails less`, `fails
  more`, `no significant difference`, `too small to tell`. *Different* stands only at an
  adjusted p-value at or under `q`. `gap_days` is Trace's time between the two runs. With
  `old`, a way in over the agent as it was, both are run now (`recheck-<n>-<finding>-old`) and
  compared with each other. A recheck that stopped is finished before a new one is begun.
- Trace is required at one version, `TRACE_VERSION`. Before any run of `confirm` or `recheck`
  Break asks Trace for its version, then for a check of two runs of one row each that it
  writes in a temporary folder. Trace missing, at another version or printing another schema
  is refused there with nothing run. Every refusal is a `ConfirmError` with a `reason`:
  `trace missing`, `trace version`, `trace schema`, `trace answer`, `no candidates`,
  `no control`, `nothing to ask again`, `unfinished` or `unknown finding`. `trace answer` is an
  answer Break could not read after the arms ran, and the arms are kept.
- Break now depends on Trace, pinned at 0.1.0a1, a pre-release on PyPI, and its Prove pin
  moves to 0.1.3, the version that Trace pins.
- `poisson_break.search`: the search without learning, and the door every strategy comes
  through. A strategy is anything with `propose(seen, budget, *, rng)` that returns a list of
  `Proposal`: a condition, the reason in one line, and the probability the strategy gave that
  condition, above 0 and at most 1. `Seen` is all it is shown, read-only: the control's map, every
  run so far (`SeenRun`: condition, case, seed and an outcome of `ok`, `failed` or `not
  counted`), every proposal so far, the runs left, what the settings allow, the cases set aside
  and how many cases a condition runs on.
- `Screen` proposes every single change the control's map makes reachable, each once, in a fixed
  order, at probability 1: every tool and every fault once in as few proposals as that takes,
  then every input operator and every listed value of a setting, then the rest of the first call
  of each tool, then each later call up to `max_call`. `Random` draws single changes and pairs of
  them as one set, uniformly and never twice, at 1 over the size of the set; a pair on one call of
  one tool, two values of one setting and a pair no one case can hold are not in it. Neither reads
  an outcome, and neither proposes a rate, a fault on every call, or a change to the conversation
  or the model's own calls.
- `allowed(vary=, tools=, capabilities=)` gives what the settings allow as a frozen `Allowed`:
  each tool that is not `off` with the faults a session takes on it, the input operators, each
  setting's values, `max_call` and the faults turned off. It asks a real session, so no second
  copy of the tool-class rule exists.
- `search_stage(strategy, name=, seen=, rng=, run=, log=None, reserve=0)` runs a stage and returns
  a `Stage`: the last `Seen`, the log and why it stopped or `None`. `run` is a callable that runs
  each entry's condition on its cases and returns the rows, so the module runs no agent and
  stores nothing. No condition runs twice: a repeat, a second spelling of a condition or the
  control proposed again is logged `dropped` and costs no run, and a batch with nothing new ends
  the stage. Every proposal is logged with its strategy, reason and probability before its run,
  as a `LogEntry` whose `selection` is what a run's record carries, and with `log` given as one
  JSON line in that file, which `read_log` reads back. A proposal with no probability or one
  outside (0, 1], a reason that is not one line of text, a return that is not a list, a condition
  the catalogue could not have written, or a change outside what the settings allow (named in the
  refusal) refuses its whole batch before any of it runs. A strategy that raises stops the stage
  with what it had; Ctrl-C and anything `run` raises pass through. A condition runs whole or not
  at all: what the runs left cannot pay for is logged `not run` and ends the stage, and
  `reserve` holds runs back for shrinking.
- `cases_for(seen, condition, rng=)`: the cases a condition runs on, drawn from those not set
  aside on which the map says every tool change can land; where none fits, from those that call
  each tool named at all, so a change at a call the control never saw has somewhere to run. A
  condition no case can take is logged `not run`, spends nothing and does not end the stage.
- `score(seen, condition)`: failed runs over counted runs under the condition, less the same for
  the control on those cases, each side pooled. A condition with a run on a case set aside, or
  with no counted run, is refused.
- `shrink(condition, failures=, calls=, tries=None)`: one change taken out at a time, the smaller
  condition kept when it fails at least as often as the candidate did, less one run, the line
  staying at the candidate's own count. A fault on every call is tried as each single call the
  tool reaches. A candidate of one change that is not on every call costs no run.
- `coverage(seen)`: what was tried and what was not looked at, as a frozen `Coverage`: reachable,
  tried and untried for each tool and each fault, the tools never called, the tools called past
  `max_call`, the faults turned off, the cases set aside, and how many reachable single changes
  and pairs have no run.
- `load_strategy(name_or_path)`: `screen`, `random`, or `module:Name`, imported; a class is made
  with no arguments and anything else with a `propose` is used as it is. Whatever goes wrong is
  one `SearchError` of one line, before anything runs. `adaptive` is not in this version and is
  refused the same way.
- `poisson_break.interfaces`: a strategy's `propose` is typed as returning a list, which is what
  the stage holds it to.
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
  ten are stored, over the runs stored since the hunt was opened, so a hunt opened again after
  the cause is mended goes on. A tool nobody classed stops it and that run is not stored. A tool the control
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
  tool whose line does not say how it is made safe to repeat; a stand-in, a check of your own or a strategy
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
- Prove pinned to the exact version Trace pins, and Trace pinned exactly, both from PyPI.
- CI: lint, type check and the tests on Python 3.11 to 3.13, under a guard that fails any
  connection and a check that no statistic is computed locally; a clean install of the built
  wheel into a fresh environment outside the checkout that runs the command.
