# Reference

The commands, the settings file, how runs are stored, and the library under the command.

## The command

| Verb | What it does | Spends | Verdict words |
|---|---|---|---|
| `init` | asks where the agent is, where the cases are and, for each tool, whether calling it changes anything; chooses every other setting, says what it chose, and writes `break.toml`; ends with the one command that writes the same file. `init --example NAME` asks nothing and writes an example's agent, cases and settings | nothing | `wrote` |
| `doctor` | reads the settings and the cases, loads the target and lists its tools, finds the first problem; `--run` runs the first case once, asked first, and stores nothing | one run, if asked | `ready`, `not ready` |
| `hunt` | the control stage, the search and the shrink stage; writes the candidates, best first | yes | `found`, `nothing found`, `stopped` |
| `confirm` | the confirm stage against one shared control on fresh runs, Trace's test for each candidate, the findings written and their reference runs; `--repeats N` asks again about what was too small to tell | yes | `confirmed`, `nothing confirmed`, `stopped` |
| `findings` | lists the latest hunt's findings, and each case that failed in the control under its own heading; `findings 2` shows one finding whole | nothing | `ok` |
| `replay` | runs one finding once, on the case that failed most under it, and shows each call with the change applied to it; `--case ID` picks another | one run | `failed`, `did not fail`, `stopped` |
| `recheck` | runs every finding on the agent as it is now, over the cases and repeats of its reference run, and reads Trace's answer; `--old MODULE:NAME` runs the old agent beside it; `--check` exits 4 when a finding fails more, `--strict` adds too small to tell | yes | `rechecked`, `stopped` |
| `catalog` | lists every change Break knows, the ones that need an adapter marked; `--labels` adds the labels a change carries from two published lists, where it has one | nothing | `ok` |

Every verb follows the shared look: the verdict line first on stdout, problems on stderr as one
`error:` line with the command to run next under it, `--json` as one strict document whose
first keys are `schema`, `verdict` and `sentence` (named `poisson_break.<verb>-result/1`, and a
plan `poisson_break.<verb>-plan/1`, with `dollars` beside its estimate, null without prices or
before the control has run), and the shared exit codes: 0 done, 1 refused before anything was spent or written, 2 a mistake on
the command line, 3 stopped after work started, 4 a check you asked for did not pass, 130
interrupted. Two documents carry another name: Ctrl-C before a verb's work starts prints one
named `poisson_break.stopped/1`, and a no to `start?` prints `stopped`, nothing was run, under
the plan's name. A verb's own options follow the verb; `--plain` and `--debug` are the tool's own
and may come first. No abbreviated flag is taken.

**Before a hunt, a confirm stage or a recheck spends anything** it shows its plan and asks
`start? [y/N]` on stderr. `doctor --run` asks its own question before its one run, and `replay`
runs its one run without asking. `--yes`
answers, `--dry-run` shows the plan and runs nothing (for `hunt --hunt NAME`, the plan of what
the hunt has left, its estimate counted over those runs), and a stdin that is not a terminal without `--yes` prints the plan and
refuses in one line. After every plan, before a replay, and in `init`'s output and `doctor`'s
when it is ready, Break says that it calls your tools for real: run it against a test
environment. A stage that stops short, at a cap or on Ctrl-C, says how many runs were kept (on
Ctrl-C, the runs the stage's own arms hold, a confirm stage's among them the reference runs of
the findings it confirmed; under `--json`, with the reason and the run it stopped in) and prints the command that goes on with the same hunt (`hunt --hunt NAME`, `confirm --hunt NAME`,
`recheck --hunt NAME`, with `--old`, `--check` and `--strict` as they were given), and that
command, run at a terminal, asks before it spends again. `confirm` without `--repeats` on a hunt
whose latest confirm stage is finished runs nothing and asks nothing: it says the stage is
already finished, shows its result again and leaves the finding files as they are. A tool the agent called that the
settings do not class stops the stage naming it, and prints first the `init` command that
writes the settings back as they are with that tool classed `off`, so the hunt can go on, and
then the command that goes on with it.

**Names, never hashes.** A hunt is named with `--name` or numbered from the target's name
(`refund-agent-1`); `findings`, `replay`, `confirm` and `recheck` take the latest hunt, and
`--hunt NAME` another. A finding is a number within its hunt. Nothing any verb prints asks you
to paste a hash.

`init` asks only what Break cannot find out for itself, in this order: where the agent is
(`module:name`, imported to find its tools, never run, and asked again until it imports); where
the cases are (and, when there is no such file, whether to write a starter file of three); and,
for each tool it finds, whether calling it changes anything, even in a test environment. A tool
that changes nothing is `read`. For one that does, it asks whether it is safe to repeat in your
test environment, and if not, where its stand-in is: a function with the same arguments that
changes nothing. Given none, `init` writes nothing and refuses, printing the `init` command with
the answers so far and that tool's stand-in left to fill in, since Break never calls such a tool
for real. Every other setting takes its default without a question: the kind `rollout`,
Break's own checks for what fails a run, tool behaviour and inputs varied (the conversation too
when a case has turns and the way in can play one; the model's calls and settings of your own
not), 400 runs and 2 hours a hunt, and no prices. `init` then lists what it chose and says that
`break.toml` is where to change it. `--yes` takes every default and asks nothing: each tool is
`read` and no starter file is written. Where the agent is has no default, so `--yes` needs
`--entry`. Every setting has a flag, listed under `init`'s flags below, which skips its question
or sets what would otherwise be chosen, and `init` ends with the one command that writes the
same file. It runs as printed with no terminal in a folder that has no `break.toml`; where one
is already there, add `--force`.

`--version` prints one line with the versions of Break, Prove, Trace and Python. A failure
inside the command is one line that names the log its details went to, and exit 3; `--debug`
prints the details as well. The look every Poisson Labs command shares is written down in
`docs/cli-look.md` in the repository, and How Break prints, below, is Break's build of it.

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
`poisson_break.changes.register`. From then on nothing tells it from a launch fault. Reading
`break.toml` takes a tool fault's name it does not know, since reading imports none of your
modules; `doctor` and `hunt` load the agent, and refuse a name still unknown before any run.

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
# wrapped_while("my_app.agents") imports the module and names the tools wrapped while it loads:
# how `init` lists an agent's tools without running it.

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

**Wrapping at load.** A tool whose line in `[tools]` has an `at` needs no `wrap` line:
`load_target` puts the same wrapper in when it loads the agent. The `at` setting needs
Poisson Break 0.2.0 or later. Version 0.1.x uses a `wrap` line for each tool.

```python
from poisson_break.apply import wrap_at_load

reached = wrap_at_load({"lookup_order": "my_app.tools:lookup_order"})   # tool name -> its at
reached[0].how              # "at load"
reached[0].places           # ("my_app.agents:TOOLS[lookup_order]", "my_app.agents:lookup_order",
                            #  "my_app.tools:lookup_order")
reached[0].held_elsewhere   # (Held(kind="closure", where="my_app.agents:make_agent"),)
```

`wrap_at_load(places)` imports each module, finds each function and checks every line before it
replaces anything. Then it puts one wrapper for each tool in every loaded module but Break's own,
under every name that holds the function, and at every value of a dict and item of a list that a
module holds under a name. What is the function is told by identity, not by its name. One level
is gone into: a dict inside a dict is left, and a key is never replaced. Loading twice replaces
nothing more, and the original is not put back while the process lives.

- `Reached` is frozen: `tool`; `how`, one of `at load`, `wrap` and `not seen`; `at`, the line's
  `at` or `None`; `places`, each holder replaced, as text in text order; and `held_elsewhere`.
- `Held` is frozen: something that took hold of the function before Break loaded the agent and
  that Break cannot replace. `kind` is `closure`, `partial`, `container` (a tuple, a set, or a
  dict or list no module holds by name) or `object` (an attribute of an object or a class).
  `where` is the function a closure belongs to or the name a module holds a partial or a
  container under, as `module:name`, or `None`. `held_elsewhere` is `None` where Python cannot
  list what refers to a function, and empty for a tool Break did not wrap at load.
- `RolloutTarget.reached` is one `Reached` for each `[tools]` line that is not `off`, in the
  file's order: `wrap` where a `wrap` line under that name has run by the time the agent is
  loaded, `not seen` where the line has no `at` and no such line has run.
- `wrap` refuses the wrapper Break made at load, since its calls would pass through a run twice.

Each of these is a `ToolRefused` naming the tool, raised while the agent is loaded and before
anything is replaced. `doctor` prints it as `not ready`, and `hunt`, `confirm`, `replay` and
`recheck` as one `error:` line with `next: poisson-break doctor`:

| What is wrong | What the line says |
|---|---|
| the module in `at` cannot be imported, or does not hold the name | the tool, its `at`, the import's own error or the nearest name the module does hold |
| the name holds something that cannot be called | the tool, its `at` and what is there |
| the name holds a class | the tool and its `at`; Break wraps a function |
| two lines name one function | both tools and the function; one function is one tool |
| the tool has an `at` and a `wrap` line has run under its name | the tool; one of the two reaches it |
| the name holds what a `wrap` line made under another name | the tool, its `at` and the name your code wraps it as |
| the tool is async | the tool and its `at` |

**Tool classes.** Each tool has a line: `"read"` (calling it changes nothing), `"off"`
(Break never touches it), or a `write` tool with how it is made safe to repeat,
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

`break.toml` says what to hunt, what may change, and when to stop. `init` writes it; this is
the whole file, and every line that is commented out is a setting that is off.

```toml
# Poisson Break: what to hunt, what may change, and when to stop.
# Written by `poisson-break init`. Edit it freely; `poisson-break doctor` checks it.
version = 1

[target]
kind = "rollout"                    # rollout
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
# conversation = ["repeats", "interrupts", "goes_quiet", "presses"]   # needs a way in this version does not have
# model = ["error", "timeout", "rate_limited", "empty", "cut_off"]   # needs a way in this version does not have
max_call = 3                        # the latest call to a tool that a fault may land on

# [vary.env]
# inventory = ["full", "empty"]

[search]
strategy = "screen"                 # screen | random | module:Name (a strategy of your own)
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

```text
search.runz on line 41 is not a setting of [search]; the nearest is search.runs
```

A value that could not mean anything is refused the same way: a count below 1 or written as a
fraction, a share outside 0 to 1, an operator or a check that is not one, a `write` tool whose
line does not say how it is made safe to repeat, a cap in dollars without both prices, `hours = inf` with no
cap. Each refusal is a `SettingsError` with `.key`, `.line` and `.suggestion`.

**Reading runs nobody's code.** Reading, checking and writing settings import no framework and
none of your modules: not the target, the strategy, a stand-in or your own check. An import path
is checked for its form, `module:name`, and whether the module is there is asked by what loads
it, before any run.

**One way in.** This version has only the `rollout` way in. The other five kinds are ways in
that will come as optional extras, and this release publishes none of them. `init --kind` with
one of them is refused before anything is written, with the same command and `--kind rollout`
to run instead, and so is a `break.toml` whose `kind` is one, wherever it is read; the refusal
lifts once that way in's module is installed. `install_command(kind)` hands back `None` for
every kind in this release, and a later version that ships an extra hands back its
`pip install` line. The `adaptive` strategy is refused the same way.

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

### Where a tool is: `at`

A `read` or `write` line in `[tools]` may hold a fourth key beside `class`, `repeatable` and
`stand_in`: `at`, where the tool's function is, as `module:name`. Break wraps a tool that has
one when it loads the agent, and a tool with none is one your own code wraps.

```toml
[tools]
lookup_order = { class = "read", at = "my_app.tools:lookup_order" }
check_policy = { class = "read", at = "my_app.tools:check_policy" }
issue_refund = { class = "write", stand_in = "my_app.fakes:refund", at = "my_app.tools:issue_refund" }
send_email = "off"
```

The tool's name is the key and need not be the function's. The name after the colon is one word,
a name the module itself holds. Reading the file checks the form of `at` and imports nothing;
the file is written back with `at` last on its line. `ToolLine.at` holds it, as text or `None`,
and a `Session` takes a line that holds `at` and reads nothing from it. Two lines are refused
when the file is read, each on its own line of the file:

```text
error: tools.send_email.at on line 10 names a place to wrap a tool that is off, which Break never touches: class it read or write, or take the place out
error: tools.lookup.at on line 10 is "my_app.tools:Orders.lookup", a name inside Orders; this version wraps a function a module holds by name: for a method, use a wrap line in your code
```

An `at` of any other form is refused as not an import path written `module:name`.

`init` writes an `at` where it finds no wrapped tool: it asks which tools the agent calls, gives
each name the agent's module holds its place there, and asks where any other is; an empty answer
writes the line with no `at`. `doctor` says how each tool that is not `off` is reached, in a
`reached` row and, under `--json`, in `reached`: one object a tool with `tool`, `how`, `at`,
`places` and `held_elsewhere`, while `tools` stays the list of every tool's name. A tool that
something Break cannot replace also holds, and a tool with no `at` and no `wrap` line that ran
while the agent loaded, each get one `note:`, and `doctor` is still `ready`.

### `init`'s flags, and the command that writes the same file

Every setting has one flag, `--tool` repeats for each line of `[tools]`, and `--env` for each
setting of `[vary.env]`. `INIT_FLAGS` maps each flag to its key.

```python
from poisson_break.settings import equivalent_init_command, settings_from_init_args

equivalent_init_command(settings, prog="poisson-break")
# poisson-break init --kind rollout --entry my_app.agents:refund_agent --cases cases.jsonl
#     --tool 'lookup_order = "read"' --tool 'check_policy = "read"'
#     --tool 'issue_refund = { class = "write", stand_in = "my_app.fakes:refund" }'      (one line)
# a line with an at is carried the same way, and no flag is added for it:
#     --tool 'lookup_order = { class = "read", at = "my_app.tools:lookup_order" }'

settings_from_init_args(["--kind", "rollout", "--entry", "my_app.agents:refund_agent", "--runs", "800"])
```

The command states the target and whatever differs from the defaults, since a flag left out
reads as its default, and running it gives the same file byte for byte. A value is written
plainly where a shell reads it back as written (`--checks crashed,hung`, `--folder break-runs`)
and as TOML where it does not (`--folder '"--odd name"'`, `--outcomes '["a, b"]'`); a tool's line and a setting of your
own are written as the file writes them. Flags are written whole. `--outcomes none` and
`--own-check none` mean no outcome counts as a failure and there is no check of your own, as when
the flag is left out; an outcome your agent reports as the word itself is written
`--outcomes '["none"]'`.

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

## A hunt's runs, stored on Prove

A hunt is a folder. Every run in it is a row of a Prove run, so Prove's `report`, `diff` and
`inspect` read a hunt as they read any run, and so does Trace's `fix-check`.

```text
break-runs/
  refund-agent-1/              the hunt, named by you or numbered from the target's name
    hunt.json                  the settings as resolved, how each tool was reached, the stages run, which run is which arm
    proposals.jsonl            what a search proposed (written by the search, not here)
    candidates.json            the candidates a hunt hands to confirm, best first
    confirm.json               each confirm stage's design, written before its first run
    findings/
      1.toml                   one file for each finding
    store/                     a Prove store
      refund-agent-1-control/
      refund-agent-1-search/
      refund-agent-1-shrink/
      refund-agent-1-confirm-control/
      refund-agent-1-confirm-1/      one for each candidate
      refund-agent-1-reference-1/    one for each finding
      refund-agent-1-recheck-1-1/    recheck number, then finding
```

A hunt writes its candidates when it ends. The confirm stages, the findings and their runs are
written by the confirm stage, described under Confirming findings.

```python
from poisson_break import hunt
from poisson_break.changes import parse
from poisson_break.settings import load, read_cases

settings = load("break.toml")
target = hunt.load_target(settings)                  # your Prove target, made and not run
h = hunt.open_hunt(settings, target=target, cases=read_cases(settings.target.cases))

h.name, h.folder, h.plan                             # refund-agent-1, where it is kept, the run counts
summary = hunt.control(h)                            # every case, control_repeats times, no change
summary.rate, summary.calls, summary.set_aside       # the base rate, where a fault can land, cases that always fail
rows = hunt.run_arm(h, "confirm-1", ["1", "2"], parse("tool:lookup_order#1=timeout"), repeats=5)
h.budget()                                           # what the hunt may spend, and what it has spent
h.stored()                                           # each arm the store holds, by its word, with its rows
```

**How each tool was reached.** For the rollout way in, `hunt.json` holds `reached`: for each tool
that is not `off`, its `tool`, `how`, `at`, `places` and `held_elsewhere`, as the agent was
loaded when the hunt was made, which is what `doctor` reports under the same key. A hunt opened
again where any of that differs adds the new answer and the time to `later_reached` when it
starts its first run under it, as `later_settings` holds settings that changed. The schema stays
`poisson_break.hunt/1`, each line's `at` is in `settings` too, and a run's record says nothing of
how a tool was reached: a tool wrapped at load writes the record a wrapped tool writes.

**Opening a hunt runs nothing, and refuses what could not work.** `open_hunt` makes the folder
and writes `hunt.json`. Before it makes anything it refuses, in one line each: a control stage
that leaves no room for one condition, a name that is not allowed or is taken, a tool your agent
has that `[tools]` does not class, a tool fault in `[vary]` that no module has registered,
something in `[vary]` your way in cannot do, a check of your
own that cannot be loaded, and a stand-in that cannot be loaded. A name is letters, digits, `.`,
`_` and `-`, starting with a letter or a digit, at most 64 characters, and is used as given. With
none, hunts are numbered from the last part of the target's entry: `refund-agent-1`, then
`refund-agent-2`. `latest_hunt(settings)` names the hunt made last. `run_once(settings,
target=, case=)` runs one case once with no change, through the same applier and failure check
as a stored run, and stores nothing: no hunt, no store, no cap; it is what `doctor --run` runs.

**Break decides every row.** Each run goes through the applier and the failure check. Its row's
outcome is `ok` or `failed`: an agent that raises is a `failed` row with the kind `crashed`, and
a run past `run_seconds` is `failed` with `hung`, so neither is lost as a row with no outcome.
Only a run Break could not count has none, and it carries one line saying why. A tool that never
returns is cut off at the run's limit, when the hunt runs on the main thread of a program on
macOS or Linux; from another thread a run past its limit is still `hung`, by its session's clock
and the measured time, once it comes back.

**What a row holds.** The cell is the case, `{"case": "<id>"}`, so two arms line up case for
case whatever their conditions; a search or shrink row's cell is the case and the condition's
name. The row's extra facts hold the run's record under `poisson_break` and `case_id`, and
nothing of your target's own: no prompt, no reply, no tool result. The seed is Prove's, from the
arm's salt and the cell. The salt is `[search] seed` and the arm's own word, so no two arms of a
hunt share a seed, and the same settings give the same seeds under any hunt name. A value of
`[vary.env]` is added to the case your target is handed, under the setting's own name.

**The three caps.** `[search] runs` counts the control, search and shrink rows, runs not counted
among them. With prices in `[limits]`, the next run is priced at the dearest run the hunt has
stored, and a stage stops before a run that could pass `dollars`; the first run of a hunt always
runs. `hours` is the stored runs' seconds, summed, so opening a hunt again does not start the
clock again. A stage that stops short raises `HuntStopped`, which says why (`runs`, `dollars`,
`hours`, `not counted`, `refused` or `tools`), in which arm, and how many rows the arm keeps.
It also stops when more than a tenth of an arm's runs could not be counted, judged after every
run once ten are stored, and when the agent calls a tool `[tools]` does not class: that run is
not stored, so that it is made once the tool has a line. The tenth is judged over the runs
stored since the hunt was opened, so once the cause is mended, opening the hunt again goes on
from where it stopped, with the runs not counted kept as they are.

**Stopping loses nothing, and the same calls go on.** A run is stored the moment it finishes, so
Ctrl-C, a cap or a killed process loses nothing finished. Open the hunt again with
`open_hunt(..., name="refund-agent-1", existing=True)` and make the same calls: a run the arm
already holds is not made again and its stored row is handed back, so exactly what is missing
runs, on the seeds it would have had. The settings handed in apply from then on, so a raised
cap lets a stopped hunt go on; the seed and the cases must be the hunt's own.

**Your agent, as a plain Prove target.** `RolloutTarget(fn, tools=[...])` drives a function
`fn(cfg, seed) -> Episode` whose tools are wrapped with `wrap`, and `load_target(settings)` makes
one from `target.entry`. `cfg` is the case's own mapping, with none of Break's keys. The
episode's `outcome` is your target's own outcome, kept beside Break's verdict, and its `meta` may
say more, each optional: `reply`, `tokens_in`, `tokens_out`, and `ended = "limit"` for the
agent's own step limit. Any other way in is an object with the same five members (`kind`,
`framework_versions`, `tools()`, `capabilities()` and `run()`), handed to `open_hunt` already
made.

## How Break searches

After the control, a hunt asks a strategy what to try. `poisson_break.search` holds the two
strategies that learn nothing, the stage that runs any strategy and holds it to the same rules,
and what a hunt then does with what came back. Nothing in it runs an agent or stores a run: the
runs go behind a callable it is handed, and `poisson_break.hunt.run_search` is the one a hunt
hands it:

```python
from poisson_break.hunt import run_search
from poisson_break.search import SeenRun

def run(entries):
    return [SeenRun(condition=row.condition, case=row.case, seed=row.seed, outcome=row.outcome)
            for row in run_search(hunt, entries)]
```

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
declares no version; one that cares compares the strategy interface's version constant, named
in [Adding a strategy](extending/strategy.md), which is 1.

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

## Confirming findings

A hunt ends with candidates: conditions that failed more than the control in the few runs a
search gave them. A candidate is not a finding. `poisson_break.confirm` tests the candidates
properly, writes the ones that hold as findings, and checks a fix against them later.

```python
from poisson_break.confirm import confirm, recheck, replay, write_candidates

write_candidates(hunt, candidates)        # best first; kept in the hunt's candidates.json
done = confirm(hunt)                      # runs the confirm stage, then the reference runs
for tested in done.tested:                # every candidate, with its verdict
    print(tested.number, tested.condition, tested.verdict, tested.note)
for finding in done.findings:             # only the confirmed ones
    print(finding.number, finding.condition, finding.rate, finding.control_rate)

replay(hunt, 1)                           # finding 1 once more, nothing stored
recheck(changed)                          # the hunt opened again on the agent as it is now
```

**The design is fixed before the first run.** One control arm runs every case the control did
not set aside, `repeats` times, with no change. One arm for each candidate runs the same cases
the same number of times under that candidate. Every case is in every arm, so no case is chosen
for having failed, and all the arms are on seeds no earlier stage used. The candidates share the
one control arm. `design(candidates, settings, control)` works the design out and runs nothing:
its cases, its arms (`confirm-control`, then `confirm-1` for the first candidate), and its cost,
which is `plan_confirm`'s: (1 + candidates) × cases × repeats, and cases × repeats more for each
finding's reference run. `confirm` writes the design to the hunt's `confirm.json` before the
stage's first run, and a stage that stopped is taken up again under what was written, whatever
the settings say by then.

**Break computes none of the numbers.** The arms are Prove runs in the hunt's store. Each
candidate's arm is put to Trace once, against the control arm:

`python -m poisson_trace fix-check OLD NEW --inputs all --event failed --max-mde X --store STORE --json`,

run with the Python Break runs on, in the hunt's folder, `X` being the settings' `max_difference`.
What Break reads is the JSON document Trace prints, never its exit code: the difference in
failure share with its interval, the p-value of its one exact test stratified by case, the
verdict, the direction, and how many repeats would decide. The candidates are tested together,
so their p-values are adjusted together with Prove's `bh`, at the settings' `q`. A failure share
is two of Trace's counts divided, and that is all the arithmetic in the module.

**The verdicts,** one for each candidate, in a `Tested`:

- `confirmed`: Trace says *different*, the candidate's arm failed more, and the adjusted p-value
  is at or under `q`;
- `too small to tell`: Trace says so, and `repeats_needed` is Trace's count of repeats that
  would decide;
- `not confirmed`: anything else, with a `note` where there is something to say: `failed less`
  when the candidate's arm failed less than the control, `not after the correction` when Trace's
  *different* did not hold across the candidates, and `nothing to compare` when no case has an
  outcome in both arms, in which case the candidate has no numbers and is left out of the
  adjustment.

`no_outcome` names the cases with no run that has an outcome in one of the two arms, read from
the stored rows, beside Trace's own count of what it left out (`left_out`). An arm in which more
than a tenth of the runs were not counted stops the stage, as it stops any arm.

**Asking again.** `confirm(hunt, repeats=N)` after a *too small to tell* is a new confirm stage
of only the candidates the latest stage called *too small to tell*, with its own control arm
(`confirm-2-control`, `confirm-2-<candidate>`), on new seeds. It is read on its own: its runs
are never pooled with the earlier stage's, because adding runs until a test passes makes the
test mean less than it says. `confirm(hunt)` on a stage that is finished runs nothing and gives
the same answer. `finished_stage(hunt)` gives that answer without running or writing anything,
and `None` while the latest stage has runs, findings or reference runs left to make.

**A finding** is a confirmed candidate, numbered within the hunt from 1 in the order confirmed
and written to `findings/<n>.toml`: the condition by name, the failure share under it and under
the control, Trace's difference and interval, the p-value, the adjusted p-value and `q`, the
failure kinds and the signals counted over its arm, whether a failed run was judged by your own
check, the cases Trace flagged and left out, the cases, the repeats and the two arms, its
reference arm, the command that replays it and the Trace command for its full report. The file
is plain TOML that can be committed, and `read_finding(hunt, n)` reads it back as the finding it
was written from; `read_findings(hunt)` reads every finding the hunt has a file for, in number
order, and one file that cannot be read as a finding refuses the whole call. A candidate that
is not confirmed never gets a file. Each confirm stage is written to `confirm.json` with the
`q` and `max_difference` it was begun under, and is judged under those however the settings
read later. `read_stages(hunt)` reads the stages written, in order, each a `Stage` with the rows
the store holds of each of its arms, and runs nothing.

**The reference run.** A finding is selected for having failed more than the control, so its
confirm-stage share overstates how often it fails. Each finding therefore gets a reference arm,
`reference-<n>`: the same agent under the finding's condition, every case again, on fresh
seeds. `confirm` runs them at its end, each finding's file written first, and `reference(hunt)`
runs whatever is missing of them after a stop.

**Replay.** `replay(hunt, 1)` runs finding 1 once and stores nothing. It runs on the first of
the finding's cases with the most failed runs in its confirm arm, on the seed of that case's
first failed run, so an agent that decides by its seed fails the same way; `case=` picks another
case, on the seed of its first run. It hands back the outcome, the kind and every call in order
with the change applied to it, and, for a run that was not counted, the run's one line of error
(`Replayed.error`).

**Recheck.** After the agent is changed, open the hunt again on it and call `recheck`. Each
finding's condition is run over the cases and repeats of its reference arm, in the arm
`recheck-<n>-<finding>`, Trace compares the reference arm with the new one, and the p-values are
adjusted across the findings as the confirm stage adjusts them. Each finding gets one of four
phrases, read from Trace's verdict and direction: `fails less`, `fails more`,
`no significant difference`, `too small to tell`. *Different* stands only at an adjusted
p-value at or under `q`. `gap_days` is the time between the two runs as Trace gives it, since a
hosted model may have changed in between; `recheck(hunt, old=target)` runs the old and the new
agent now, side by side (`recheck-<n>-<finding>-old`), and compares those two instead. A recheck
that stopped is finished before a new one is begun.

**Trace is required, at one version.** Before any run of `confirm` or `recheck`, Break asks
Trace for its version and then for a check of two small runs it writes in a temporary folder.
Trace missing, at another version, or printing a document under another schema name is refused
there, with nothing run and nothing stored. Every refusal of the module is a `ConfirmError` with
a `reason`: `trace missing`, `trace version`, `trace schema`, `no candidates`, `no control`,
`nothing to ask again`, `unfinished`, `unknown finding`, or `trace answer`, which is an answer
Break could not read after the arms ran, with the arms kept.

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
look.show(result)   # inside look.run: the way the current run prints one; outside: plain
```

```text
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

**Problems go to stderr, one line each.** Here `hunt` refuses the `stand-in` example after its
`issue_refund` line in `break.toml` is changed to `"write"`, with neither `repeatable` nor a stand-in:

```text
error: tools.issue_refund on line 15 is a write tool, and its line does not say how it is made safe to repeat: { class = "write", repeatable = true } where the test environment absorbs repeats, or a stand_in to call in its place
  next: poisson-break doctor
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
exactly, bare where a shell needs no quotes (`refund-agent-1`) and quoted where it does
(`'late refunds'`). `look.command(*words)` joins them into a line no rendering ever wraps.

**Where the terminal cannot show a character.** `·`, `–` and `×` become `-`, `-` and `x`. Any
other character the stream cannot encode is written as its escape (`caf\xe9`), so two names
never read as one. A control character in a name, an escape sequence among them, is shown as
text and never acted on.

## What it depends on

Prove (`poisson-prove`) and Trace (`poisson-trace`), each pinned exactly. Break's Prove is the
version Trace pins, 0.1.3, so the three tools agree on one Prove. Trace is pinned at 0.1.0a1, a
pre-release on PyPI, which `pip` installs for an exact pin without `--pre`. uv installs a
pre-release only when told to, so with uv the line is `uv pip install --prerelease=allow poisson-break`. Break takes Prove's store, its planner and its adjustment
across tests from Prove's own modules and nothing from its private ones: the planner gives each
run its seed, the store takes each row, and `bh` adjusts the p-values. Trace is never imported:
Break runs its command and reads the JSON it prints.

Rich, questionary and prompt_toolkit draw the pretty rendering and its menus. They are ordinary
dependencies, so a plain `pip install` is pretty on a terminal, and a plain run never loads
them.

## Developing

In a checkout, with a virtual environment in `.venv`: `.venv/bin/python -m pip install -e ".[dev]"`
installs Break with what its tests need, `.venv/bin/python -m pytest -q` runs the suite,
`.venv/bin/ruff check .` lints and `.venv/bin/mypy` checks the types.

The suite runs under a guard that fails any connection: open-source Break opens no socket of
its own and sends nothing anywhere. A second check reads the source for a test or an interval
computed locally and fails on one: every statistic Break reports is Trace's or Prove's. The
confirm stage's tests answer for Trace with a stand-in that prints what the pinned Trace printed
for the same runs, and one test runs a confirm and a recheck on the installed Trace itself.
`scripts/clean_install.py` installs the wheel into a fresh environment outside the checkout and
runs the command there, piped and on a terminal, and then every command the README and the
pages under `docs/` and `examples/` show, as CI does. The look's tests run small
programs on real pipes and pseudo-terminals and read back what a terminal would show; every
command a later module adds joins the corpus in `tests/look_corpus.py` and is held to the same
checks, both ways. The tests stand on five scripted agents in
`tests/agents/`, small programs with no model and no framework: one retries, one gives up, one
follows planted text, one repeats a write, and one speaks only the way-in protocol. The repository
follows `docs/repo-hygiene.md`.
