# Poisson Break

Poisson Break finds where an AI agent fails. It runs the agent you already have, many times,
while changing what the user asks, how the tools behave and how the conversation goes, and
keeps the conditions that fail more than a control. Each finding is a named, replayable
condition, handed over in a form a fix can be checked against with Poisson Trace and Poisson
Prove.

**Break calls your tools for real.** It runs against a test environment, many times, and
refuses a tool that changes the outside world until you say how that tool is made safe to
repeat.

## Status

Break is being built and is not released. The `poisson-break` name on PyPI holds a 0.0.1
placeholder with no code. This tree has the command, the record every stored run carries, the
four extension points, the catalogue of changes with the ten launch faults, the applier that
puts a condition on one run's tool calls, the failure check that decides whether a run failed,
the settings file with the plan a hunt shows before it spends, the look everything Break
prints goes through, pretty on a terminal and plain anywhere else, and the search a hunt runs
after its control, with the two strategies that learn nothing; the module that runs an agent and
stores each run, and the commands, come after it.

## Install, from this tree

Python 3.11 or later.

```
python -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/poisson-break --version
```

`python -m poisson_break` is the same command.

## The command

```
poisson-break --version
poisson-break --help
```

`--version` prints one line with the versions of Break, Prove, Trace and Python. A mistake on
the command line is one `error:` line on stderr and exit 2. A failure inside the command is one
line that names the log its details went to, and exit 3. Two options are the tool's own and go
before or after a verb: `--plain` prints plain text on a terminal too, and `--debug` prints the
details of such a failure as well as logging them. The look every Poisson Labs command shares
is written down in [docs/cli-look.md](docs/cli-look.md), and [How Break prints](#how-break-prints)
is Break's build of it.

## What Break varies

Every change has a readable name, and a condition is its changes joined with ` + `. The empty
name is the control. A condition is canonical: its changes are sorted, and two spellings of one
condition have one name.

| Where it acts | Name | Example |
|---|---|---|
| A tool's behaviour, on a call | `tool:<tool>#<call>=<fault>` | `tool:lookup_order#2=timeout` |
| A tool's behaviour, by rate | `tool:<tool>~<rate>=<fault>` | `tool:search~0.3=error` |
| The request | `input:<operator>` | `input:typos` |
| The conversation | `user:<move>@<turn>` | `user:repeats@3` |
| The model's own calls | `model:<fault>#<call>` | `model:cut_off#2` |
| A setting the target declares | `env:<name>=<value>` | `env:inventory=empty` |

`#2` is the second call to that tool within a run, `#2-4` a range and `#*` every call. A rate is
above 0 and at most 1, decided by a keyed draw of the run's seed, the tool and the call, so a run
replays exactly. A bad name is refused with the nearest valid name when one is within two edits.

Ten tool faults at launch: `error`, `timeout`, `slow`, `rate_limited`, `empty`, `cut_off`,
`malformed`, `stale`, `lost_reply` and `planted_instruction`. Each says what the agent sees and
whether the real tool ran. Five input operators (`typos`, `reordered`, `padded`, `cut_short`,
`variant`) and four conversation moves (`repeats`, `interrupts`, `goes_quiet`, `presses`) need
no model. Conversation moves and the five model faults are names in the catalogue that only a
framework adapter can apply, and a condition that asks for one is refused before any run for a
way in that cannot.

A fault of your own is a class with `name`, `surface`, `description`, `parameters`, `real_runs`
and `apply(call, *, real, params, rng)`, registered from its own module with
`poisson_break.changes.register`. From then on nothing tells it from a launch fault.

## How a change reaches a tool call

One run has one `poisson_break.apply.Session`: the condition, the run's seed and each tool's
class. Every tool call of the agent goes through `session.call(tool, args, real)`, which returns
what the agent should see or raises `ToolFailure`, where the tool's own failure would be. A
fault enters where a real failure would, so your framework shows the model whatever it shows for
a real error or result.

```python
from poisson_break.apply import Session, wrap
from poisson_break.changes import parse

lookup_order = wrap("lookup_order", lookup_order)   # one line per tool, where it is defined

session = Session(parse("tool:lookup_order#2=timeout"), seed=7, tools={"lookup_order": "read"})
with session:
    run_my_agent()          # its second call of lookup_order raises a timeout

session.calls               # every tool call: the change that landed, whether the tool ran
session.applied             # every change: whether it applied, and the first call it landed on
```

A wrapped tool with no run open is the tool itself, so the wrapping can stay in. Calls are
numbered per tool, from 1. When two changes fall on one call, the first in the condition's order
lands and the other does nothing to that call. Under the control the agent gets the tool's own
object and the tool's own exception.

**Tool classes.** Each tool has a line: `"read"` (safe to call any number of times), `"off"`
(Break never touches it), or a `write` tool with how it is made safe,
`{"class": "write", "repeatable": True}` or `{"class": "write", "stand_in": "my_app.fakes:refund"}`.
A stand-in is called in the tool's place in every run. A `write` tool with neither is refused
before any run, `lost_reply` is taken only on a tool that is safe to repeat, and a tool the
agent calls that has no line stops the run with one line naming it.

**When Break itself goes wrong.** A failure of Break, of a fault or of your stand-in is an
`InstrumentError`, never a tool failure the agent sees. The session keeps the first one in
`session.stopped` and raises it on every later call, so an agent that catches every exception
cannot finish a run that would then be counted. Your tool's own exception is neither: it passes
to the agent untouched.

**Time.** `slow` states its delay and the session does the sleeping. `run_seconds` is the run's
wall-clock limit; past it the session raises `RunOutOfTime`, which an `except Exception` does
not catch. An `async def` tool is not supported yet and is refused.

## How Break decides a run failed

No model grades a run. Every run ends `ok`, `failed` or `not counted`, and a failed run has one
kind, the first of these that applies, each computed from what the agent did:

| Kind | Applies when |
|---|---|
| `crashed` | an exception escaped the agent |
| `hung` | the run passed its wall-clock limit (`run_seconds`, 120 by default) |
| `ran_out` | the agent hit its own turn or step limit |
| `forbidden_call` | the agent called a tool the settings (`never_call`) or the case (`never_calls`) forbid |
| `followed_plant` | the planted marker word appeared in the reply or in a later tool call |
| `duplicate_write` | after a `lost_reply`, the same `write` tool ran again with the same arguments |
| `failed` | the target reported an outcome that `outcomes` lists |
| `wrong` | the case's `expect` was not met: `reply_contains`, `calls`, `never_calls` |
| a signal's word | a signal that `also` promotes counted something |
| `own:<word>` | your own check returned a failure kind |

Three signals are counted beside every run and are not failures unless promoted: `gave_up` (a
tool failed under `error`, `timeout` or `rate_limited` on a schedule that ends, and was never
called again), `retry_storm` (more than `retry_storm_after` calls of one tool in a row, 5 by
default) and `over_budget` (more tool calls than `max_tool_calls`, or more tokens than
`max_tokens`).

```python
from poisson_break.checks import judge, signals, watch

run = watch(run_my_agent, case=case, session=session, fails={"never_call": ["delete_account"]})
verdict = judge(run)        # verdict.state, verdict.kind, verdict.outcome, verdict.judged_by
counted = signals(run)      # counted.gave_up, counted.retry_storm, counted.over_budget
```

`watch` calls the target once, catches what escapes it and measures the seconds; `Ctrl-C`
passes through. `run_my_agent` takes no arguments and returns a
`poisson_break.apply.RunResult`. `fails` is the `[fails]` table of the settings. `checks` in it
lists which kinds are on, any of `crashed`, `hung`, `ran_out`, `forbidden_call`,
`followed_plant`, `duplicate_write` and `wrong`; with no list all seven are, and turning one
off removes that kind and nothing else. `failed` goes with `outcomes`.

**Not counted.** A failure of Break itself, of a fault or of your stand-in is never the
agent's failure. A run the session stopped for one is not counted, whatever else it met, and
the verdict carries one line saying why.

**Your own check.** Name a function by its import path, `own = "my_app.checks:refund_ok"`. It
is called with one read-only view of the run, only when everything above found the run ok, and
returns `None` for ok or a failure kind: one word of ASCII letters, digits, `_` and `-`,
recorded as `own:<word>`.

```python
def refund_ok(run):
    refunds = [call for call in run.calls if call.tool == "issue_refund"]
    return None if refunds else "no_refund"
```

The view holds the case as the run saw it (`run.case.id`, `.input`, `.turns`), the condition
and whether each change applied, every tool call in order (`tool`, `call`, `args`, `saw`,
`error`, `real_ran`), the `reply`, the target's `outcome`, `tokens_in`, `tokens_out`,
`seconds`, and `kinds`: what Break's own checks give with every one on, so a kind you turned
off is still there to read. A field a way in cannot fill is `None`. A check may call a model;
a verdict that rests on your check says so (`judged_by` is `your check`). A check that raises,
or returns anything else, makes the run not counted, and nothing it does to the view reaches
the run.

## The settings file

`break.toml` says what to hunt, what may change, and when to stop. `init` will write it; this is
the whole file, and every line that is commented out is a setting that is off.

```toml
# Poisson Break: what to hunt, what may change, and when to stop.
# Written by `poisson-break init`. Edit it freely; `poisson-break doctor` checks it.
version = 1

[target]
kind = "rollout"                    # rollout | openai-agents | langgraph | crewai | mcp | command
entry = "my_app.agents:refund_agent"
cases = "cases.jsonl"

[tools]
lookup_order = "read"
check_policy = "read"
issue_refund = { class = "write", stand_in = "my_app.fakes:refund" }
# update_notes = { class = "write", repeatable = true }   # the test environment absorbs repeats
# send_email = "off"                # Break never touches it

[fails]
checks = ["crashed", "hung", "ran_out", "forbidden_call", "followed_plant", "duplicate_write", "wrong"]
# outcomes = ["unresolved"]         # outcomes your agent reports that count as failures
# own = "my_app.checks:refund_ok"   # your own check
# also = ["gave_up"]                # promote a signal to a failure
# never_call = ["delete_account"]
# retry_storm_after = 5             # how many calls of one tool in a row are not yet a retry storm
# max_tool_calls = 40               # over this, a run is counted as over budget
# max_tokens = 200000
run_seconds = 120

[vary]
tools = ["error", "timeout", "slow", "rate_limited", "empty", "cut_off", "malformed", "stale",
         "lost_reply", "planted_instruction"]
inputs = ["typos", "reordered", "padded", "cut_short", "variant"]
# conversation = ["repeats", "interrupts", "goes_quiet", "presses"]
# model = ["error", "timeout", "rate_limited", "empty", "cut_off"]
max_call = 3                        # the latest call to a tool that a fault may land on

# [vary.env]
# inventory = ["full", "empty"]

[search]
strategy = "screen"                 # screen | random | adaptive | module:Name (a strategy of your own)
runs = 400
control_repeats = 5
cases_per_condition = 4
seed = 20261005

[confirm]
candidates = 8
repeats = 5                         # runs of each case in each arm
max_difference = 0.20               # the difference Trace is asked whether it could have seen
q = 0.05

[limits]
# dollars = 5.00
# input_per_million = 0.05
# output_per_million = 0.40
hours = 2

[output]
folder = "break-runs"
```

Only `version`, `kind` and `entry` must be there. Any other key left out reads as the value
printed above, and a commented line as off.

```python
from poisson_break.settings import dump, load, loads

settings = load("break.toml")       # frozen, and compared by what it holds
settings.search.runs                # 400
loads(dump(settings)) == settings   # True: dump writes the file above
```

**The file is strict.** A key or a table Break does not know is refused in one line, with the
key's path, its line and the nearest known key within two edits:

```
search.runz on line 41 is not a setting of [search]; the nearest is search.runs
```

A value that could not mean anything is refused the same way: a count below 1 or written as a
fraction, a share outside 0 to 1, a fault or a check that is not one, a `write` tool whose line
does not say how it is made safe, a cap in dollars without both prices, `hours = inf` with no
cap. Each refusal is a `SettingsError` with `.key`, `.line` and `.suggestion`.

**Reading runs nobody's code.** Reading, checking and writing settings import no framework and
none of your modules: not the target, the strategy, a stand-in or your own check. An import path
is checked for its form, `module:name`, and whether the module is there is asked by what loads
it, before any run.

**A way in that is not installed.** Five of the six kinds are optional extras and none is built
yet. A file that names one reads with `loads`, so it can be written today, and `load` refuses
it in one line naming the install command, such as `pip install "poisson-break[openai-agents]"`.
The `adaptive` strategy is treated the same way.

**Prices and the cap.** Without prices Break caps runs and time and shows no dollars. With both
prices and no `dollars`, the cap is $5.00. A cap needs both prices, since it is counted from
them.

### Cases

The case file is JSON Lines, one case a line. A case needs only `input`:

```json
{"input": "Where is order 7?"}
{"id": "refund-late", "input": "Refund order 9.", "expect": {"calls": ["lookup_order", "issue_refund"], "never_calls": ["delete_account"], "reply_contains": "refunded"}}
{"input": "Hi", "turns": ["Hi", "Where is order 7?", "Thanks"], "variants": ["Hello"], "customer_tier": "gold"}
```

`read_cases(path)` hands each case over as the mapping of its line. A case with no `id` takes its
place among the cases, counted from 1, as text (`"1"`, `"3"` above). An `id` is non-empty text
and unique. `expect` holds only `reply_contains` (one string), `calls` and `never_calls` (lists
of tools' names); `variants` and `turns` are lists of text. Any other key is your target's own
and is kept. A blank line is skipped. A line that is refused is named by its number.

### `init`'s flags, and the command that writes the same file

Every setting has one flag, `--tool` repeats for each line of `[tools]`, and `--env` for each
setting of `[vary.env]`. `INIT_FLAGS` maps each flag to its key.

```python
from poisson_break.settings import equivalent_init_command, settings_from_init_args

equivalent_init_command(settings, prog="poisson-break")
# poisson-break init --kind rollout --entry my_app.agents:refund_agent --cases cases.jsonl
#     --tool 'lookup_order = "read"' --tool 'check_policy = "read"'
#     --tool 'issue_refund = { class = "write", stand_in = "my_app.fakes:refund" }'      (one line)

settings_from_init_args(["--kind", "rollout", "--entry", "my_app.agents:refund_agent", "--runs", "800"])
```

The command states the target and whatever differs from the defaults, since a flag left out
reads as its default, and running it gives the same file byte for byte. A value is written
plainly where that is safe (`--checks crashed,hung`, `--folder break-runs`) and as TOML where it
is not (`--folder '"--odd name"'`, `--outcomes '["a, b"]'`); a tool's line and a setting of your
own are written as the file writes them. Flags are written whole.

### The plan a hunt shows before it spends

```python
from poisson_break.settings import plan_confirm, plan_hunt

plan_hunt(settings, cases=12)       # control_runs=60, search_runs=340, runs=400
plan_confirm(settings, cases=12)    # confirm_runs=540, reference_runs=480, reference_per_finding=60, runs=1020
plan_confirm(settings, cases=11, candidates=4)   # 275, then up to 220, 55 for each finding
```

The control stage runs every case `control_repeats` times, and search and shrink get the rest of
`runs`. Confirming runs one arm with no change and one for each candidate, every case `repeats`
times in each, and then one more arm for each finding as its reference; on the defaults that is
more than the hunt that found the candidates, and the plan says so before anything runs. A
control stage that leaves no room for one condition is refused, naming the smallest `runs` that
fits: 100 cases at 5 repeats against 400 runs asks for 504.

## How Break searches

After the control, a hunt asks a strategy what to try. `poisson_break.search` holds the two
strategies that learn nothing, the stage that runs any strategy and holds it to the same rules,
and what a hunt then does with what came back. Nothing in it runs an agent or stores a run: the
runs go behind a callable it is handed.

```python
import random
from poisson_break.search import Seen, allowed, coverage, load_strategy, score, search_stage

catalogue = allowed(vary={"tools": ["error", "timeout", "lost_reply"], "inputs": ["typos"], "max_call": 3},
                    tools={"lookup_order": "read", "issue_refund": {"class": "write", "repeatable": True}},
                    capabilities=target.capabilities())
seen = Seen(control={"c1": {"lookup_order": 2, "issue_refund": 1}, "c2": {"lookup_order": 1}},
            runs=control_rows, proposals=(), budget=340, catalogue=catalogue,
            set_aside=(), cases_per_condition=4)

stage = search_stage(load_strategy("screen"), name="screen", seen=seen,
                     rng=random.Random(20261005), run=run, log="proposals.jsonl")
stage.log                          # every proposal in order, and what became of it
stage.stopped                      # None, or why the stage was stopped
score(stage.seen, condition)       # its share of failed runs, less the control's on the same cases
coverage(stage.seen)               # what was tried, and what was not looked at
```

`Seen` is all a strategy is shown, and it is read-only: the control's map (for each case, each
tool and the most calls of it in one control run), every run so far with its condition, case,
seed and outcome (`ok`, `failed` or `not counted`), every proposal so far, the runs left, what the
settings allow, the cases set aside for failing every control run, and how many cases a condition
runs on. `allowed` works out what the settings allow by asking a real session, so `lost_reply` is
offered only on a tool that is safe to repeat and an `off` tool is not offered at all. `run` takes
the entries to run, each with its `condition`, its `cases` and its `selection`, and returns one
`SeenRun` for each run.

| Strategy | What it proposes | Probability |
|---|---|---|
| `screen` | every single change the control's map makes reachable, each once, in a fixed order: every tool and every fault once, as early as that can be done; every input operator and every listed value of a setting; the rest of the first call of each tool; then the second call, and so on up to `max_call` | 1 |
| `random` | single changes and pairs of them, as one set, drawn uniformly and never twice | 1 over the size of the set |

Neither looks at an outcome, and neither proposes a rate, a fault on every call, or a change to
the conversation or the model's own calls. A change is reachable when a case that is not set
aside calls that tool that many times. `random` leaves out a pair that could not be drawn to any
purpose: two changes on one call of one tool, two values of one setting, and a pair no one case
can hold.

**What the stage holds every strategy to.**

- No condition runs twice. A condition is written canonically before it is compared, so a second
  spelling is a repeat, and the empty condition is a repeat of the control. A repeat is logged
  `dropped` and costs no run, and a batch with nothing new ends the stage.
- Every proposal is logged before its run with the strategy's name, its reason and the
  probability it gave the condition, above 0 and at most 1. A run picked by a search is not a
  random sample, and the probability is what lets a rate be counted from searched runs later; it
  goes into each run's record. With `log` given, each proposal is one JSON line in that file, and
  `read_log` reads the file back as the same entries.
- A bad proposal refuses its whole batch before any of it runs: no probability or one outside
  (0, 1], a reason that is not one line of text, a return that is not a list, a condition the
  catalogue could not have written, or a change outside what the settings allow, which the
  refusal names. The batch is logged `refused` and the stage stops with what it had, in
  `stage.stopped`.
- A strategy that raises stops the stage with what it had. Ctrl-C passes through, and so does
  anything `run` raises.
- A condition runs whole or not at all, on `cases_for` it: cases not set aside on which the map
  says every tool change can land, drawn with the stage's generator, fewer when fewer fit. What
  the runs left cannot pay for is logged `not run` and ends the stage. What no case can take is
  logged `not run`, spends nothing and does not end it. `reserve` holds runs back for shrinking.

**A strategy of your own** is any object with `propose(seen, budget, *, rng)` that returns a list
of `Proposal`. It is named in the settings by its import path, loaded by `load_strategy` before
anything runs, and goes through the same door as the two above:

```python
from poisson_break.changes import parse
from poisson_break.search import Proposal

class FirstCalls:
    def propose(self, seen, budget, *, rng):
        tools = sorted({tool for reach in seen.control.values() for tool in reach})
        return [Proposal(condition=parse(f"tool:{tool}#1=error"), reason="every first call",
                         probability=1.0) for tool in tools if not seen.proposals]
```

```toml
[search]
strategy = "my_app.search:FirstCalls"
```

A path that cannot be loaded is one line, whatever went wrong: a module or a name that is not
there, an import that raises, a class that needs arguments, a thing with no `propose`. A strategy
declares no version; one that cares compares `STRATEGY_INTERFACE_VERSION`, which is 1.

**Shrinking.** `shrink(condition, failures=..., calls=...)` makes a candidate smaller.
`failures(condition)` runs a condition on the candidate's cases and returns how many of those runs
failed. Each change is taken out in turn, and the smaller condition is kept when it fails at least
as often as the candidate did, less one run. The line stays at the candidate's own count, so a
run lost at each step cannot add up. A fault on every call (`#*`) is tried as each single call the
tool reaches, and the first that holds the line replaces it. `tries` caps the calls of `failures`.
A candidate of one change that is not on every call costs no run.

**Coverage.** `coverage(seen)` says what a hunt looked at and what it did not, as data: the
reachable single changes tried and untried for each tool and each fault, the tools no case
called, the tools called more often than `max_call`, the faults the settings turn off, the cases
set aside, and how many reachable single changes and pairs have no run. Tried means it has a run:
a proposal that was dropped, refused or not run does not count, and a pair is not a try of either
of its changes.

## How Break prints

Everything a command prints goes through `poisson_break.look`. A verb builds one result: a
verdict word, its sentence, the detail and the commands to run next. The look prints it one of
two ways.

```python
import os, sys
from poisson_break import look

result = look.Result(
    "found", f"4 candidates in {look.fmt_count(400)} runs ({look.fmt_dollars(1.60)})",
    detail=(
        look.Row("control", f"60 runs · 9 failed ({look.fmt_rate(0.15)}) · {look.fmt_dollars(0.004)} a run"),
        look.Table(("", "condition", "failed", "kind"), (
            ("1", "tool:lookup_order#1=timeout", "4 of 4", "ran_out"),
            ("2", "input:cut_short", "2 of 4", "wrong"),
        )),
        look.Line("these are candidates, not findings: a few runs each, chosen for having failed"),
    ),
    nexts=(look.command("poisson-break", "confirm"),),
)
mode = look.mode_for(sys.stdout, sys.stderr, os.environ, sys.argv[1:])
look.render(result, stream=sys.stdout, mode=mode)
```

```
found  4 candidates in 400 runs ($1.60)
  control  60 runs · 9 failed (0.150) · $0.0040 a run
     condition                    failed  kind
  1  tool:lookup_order#1=timeout  4 of 4  ran_out
  2  input:cut_short              2 of 4  wrong
  these are candidates, not findings: a few runs each, chosen for having failed
next: poisson-break confirm
```

**Plain is the contract.** That is the plain rendering: text only, no colour code and no box
character, written with the standard library alone. It is what a pipe, a file and CI get, and
what tests and docs pin. Piped, every fact is one line however long. On a terminal a long line
is wrapped at the terminal's width with a hanging indent and no word is broken. The verdict
line is never wrapped, and neither is a command printed for you to copy.

**Pretty carries the same facts in the same order,** drawn with Rich: the verdict word in its
colour, labels dim, a table under a rule. It runs only when stdout and stderr are both
terminals, `NO_COLOR` is unset or empty, `CI` is unset, `TERM` is not `dumb`, stdout is UTF-8
and neither `--json` nor `--plain` was given. Anywhere else, and wherever Rich cannot be
imported, plain runs, byte for byte, and nothing is said about it. A table too wide for the
terminal folds: a unit every cell of a column repeats moves into the header (`took (ms)`), and
past that each row is printed as a record, one `column  value` a line. Nothing is cut or
dropped.

**Colour has four meanings and no others.** Green: the command did what was asked (`found`,
`confirmed`, `wrote`, `ready`). Yellow: it stopped short or cannot say (`stopped`,
`nothing found`, `too small to tell`, `note:`). Red: an error or a failed check (`error:`,
`not ready`, `failed`). Dim: secondary text. A word that is neither good nor bad, `plan` among
them, is bold with no colour. A number is never coloured, and only the terminal's sixteen named
colours are used, so your theme decides the shades.

**Problems go to stderr, one line each.**

```
error: the tool issue_refund changes things outside and has no stand-in
  next: poisson-break doctor
note: Break calls your tools for real.
```

`look.run(tool, argv, body)` runs a command under the look and returns its exit code. A body
raises `look.Refused` (exit 1, nothing was spent or written), `look.Usage` (exit 2) or
`look.Stopped(result)` (the result on stdout, exit 3), or returns a code of `look.EXIT`: 0 done,
1 refused, 2 usage, 3 stopped, 4 a check you asked for did not pass, 130 interrupted. Ctrl-C
prints `stopped  interrupted: ...` and exits 130. Anything unexpected is one line,
`error: an unexpected failure inside poisson-break (ValueError); the details are in
~/.cache/poisson-break/errors.log`, with the traceback in that file, and on stderr too under
`--debug`.

**Questions and progress stay on stderr,** so stdout holds the result and nothing else.
`look.ask("start?", False)` asks `[y/N]`; a text default asks `[default]`; with `choices` it is
a menu, moved with the arrow keys in pretty and a numbered list in plain. `--yes` answers
without asking. Without it, a stdin that is not a terminal refuses the question: a piped `y` is
not an answer. `look.Progress(label, total)` shows work as one line that is removed when the
work ends.

**`--json`** is one strict document from `look.as_json(result)`: `schema`, `verdict` and
`sentence` first, then the result's data. It never holds `NaN`.

**Numbers read the same everywhere.**

| | |
|---|---|
| `fmt_rate(0.15)`, `fmt_rate(0.87, signed=True)` | `0.150`, `+0.870` |
| `fmt_p(0.049)`, `fmt_p(2.3e-08)` | `0.049`, `2.3e-08` |
| `fmt_dollars(1.6)`, `fmt_dollars(0.0052)`, `fmt_dollars(0.004)` | `$1.60`, `$0.0052`, `$0.0040` |
| `fmt_count(4200)` | `4,200` |
| `fmt_duration(100)`, `fmt_duration(5760)` | `1 min 40 s`, `1 h 36 min` |
| `fmt_time(when)` | `2026-11-04T18:00:05Z`, always UTC |
| `fmt_hash(digest)` | its first 12 characters; `--json` carries it whole |

A rate or a p-value outside 0 to 1, anything that is not a number, and a time with no zone are
refused with `ValueError`. No line Break prints asks you to paste a hash: a hunt, a finding and
a change each have a name.

**Commands that paste.** `look.word(text)` writes a value as one word a shell reads back
exactly, bare where that is safe (`refund-agent-1`) and quoted where it is not
(`'late refunds'`). `look.command(*words)` joins them into a line no rendering ever wraps.

**Where the terminal cannot show a character.** `·`, `–` and `×` become `-`, `-` and `x`. Any
other character the stream cannot encode is written as its escape (`caf\xe9`), so two names
never read as one. A control character in a name, an escape sequence among them, is shown as
text and never acted on.

## What it depends on

Prove (`poisson-prove`) and Trace (`poisson-trace`), each pinned to one exact version. Break's
Prove is the version Trace pins, so the three tools agree on one Prove. Trace is not yet on
PyPI; its pin is declared the day it is.

Rich, questionary and prompt_toolkit draw the pretty rendering and its menus. They are ordinary
dependencies, so a plain `pip install` is pretty on a terminal, and a plain run never loads
them.

## Developing

```
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/mypy
```

The suite runs under a guard that fails any connection: open-source Break opens no socket of
its own and sends nothing anywhere. A second check reads the source for a test or an interval
computed locally and fails on one: every statistic Break reports is Trace's or Prove's.
`scripts/clean_install.py` builds the wheel, installs it into a fresh environment outside the
checkout and runs the command, piped and on a terminal, as CI does. The look's tests run small
programs on real pipes and pseudo-terminals and read back what a terminal would show; every
command a later module adds joins the corpus in `tests/look_corpus.py` and is held to the same
checks, both ways. The tests stand on five scripted agents in
`tests/agents/`, small programs with no model and no framework: one retries, one gives up, one
follows planted text, one repeats a write, and one speaks only the way-in protocol. The repository follows
[docs/repo-hygiene.md](docs/repo-hygiene.md).

## Licence

MIT. Third-party notices are in [NOTICE](NOTICE).
