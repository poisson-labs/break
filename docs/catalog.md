# The catalogue

The catalogue is every change Break can make to a run. A hunt tries changes from it, one at a
time and in pairs, and keeps the ones under which your agent fails more often than it does with
no change. This page lists the changes, says how each is named, and shows how to choose which
ones a hunt may use.

```sh
poisson-break catalog
```

```text
ok  24 changes Break knows
  tool:error                the tool raises an error; the real tool does not run
  tool:timeout              the tool raises a timeout at once; the real tool does not run
  tool:slow                 the real result, after a stated delay (default 5 s, at most 30 s)
  tool:rate_limited         an error saying to wait a stated number of seconds (default 30); the real tool does not run
  tool:empty                an empty result of the real result's own kind; the real tool runs
  tool:cut_off              the real result cut to a stated length (default 200 characters); a mapping or a list is written out as JSON text first
  tool:malformed            the real result with its structure broken: a closing bracket dropped, or one field renamed; plain text is left as it is
  tool:stale                the result of the previous call to the same tool; on a first call, an empty result
  tool:lost_reply           an error after the tool has already acted, so a retry repeats the action; the result is discarded
  tool:planted_instruction  the real result with one added sentence telling the agent to repeat a marker word; a mapping or a list is written out as JSON text first
  input:typos               a fixed share of the request's characters swapped or dropped (5%)
  input:reordered           the request's sentences in a different order
  input:padded              an unrelated paragraph from a fixed list added before the request
  input:cut_short           only the first sentence of the request
  input:variant             the next entry of the variants the case lists; left as written when it lists none
  user:repeats              the user sends the message before this turn again (needs an adapter: a way in that can make it)
  user:interrupts           an off-topic message from a fixed list at this turn (needs an adapter: a way in that can make it)
  user:goes_quiet           a one-character message at this turn (needs an adapter: a way in that can make it)
  user:presses              a line from a fixed list asking the agent to skip its checks and hurry (needs an adapter: a way in that can make it)
  model:error               the model call fails with an error (needs an adapter: a way in that can make it)
  model:timeout             the model call times out (needs an adapter: a way in that can make it)
  model:rate_limited        the model call is refused with a rate limit saying to wait a stated number of seconds (default 30) (needs an adapter: a way in that can make it)
  model:empty               the model call returns an empty reply (needs an adapter: a way in that can make it)
  model:cut_off             the model's reply is cut to a stated length (default 200 characters) (needs an adapter: a way in that can make it)
```

## How a change is named

Every change has a name you can read, type and paste. A condition is one change, or several
joined with ` + `. The condition with no change is the control.

| Where it acts | Name | Example |
|---|---|---|
| A tool's behaviour, on one call | `tool:<tool>#<call>=<fault>` | `tool:lookup_order#2=timeout` |
| A tool's behaviour, on a share of calls | `tool:<tool>~<rate>=<fault>` | `tool:search~0.3=error` |
| The request | `input:<operator>` | `input:typos` |
| The conversation | `user:<move>@<turn>` | `user:repeats@3` |
| The model's own calls | `model:<fault>#<call>` | `model:cut_off#2` |
| A setting your agent reads | `env:<name>=<value>` | `env:inventory=empty` |

`#2` is the second call your agent makes to that tool within one run. `#2-4` is a range of
calls and `#*` is every call. A rate is above 0 and at most 1, and whether it lands on a given
call is decided from the run's seed, so a run replays exactly. Two spellings of one condition
have one name: Break sorts a condition's changes before it names it. A name that is not a
change is refused, with the nearest name when one is within two edits.

## The ten tool faults

A tool fault changes what your agent gets back from one of its tools. Each says whether the
real tool still runs, which matters for a tool that changes something.

| Fault | What the agent sees | Real tool runs |
|---|---|---|
| `error` | an error | no |
| `timeout` | a timeout, raised at once | no |
| `slow` | the real result, after a stated delay (5 s unless stated, 30 s at most) | yes |
| `rate_limited` | an error that says to wait a stated number of seconds (30 unless stated) | no |
| `empty` | an empty result of the real result's own kind | yes |
| `cut_off` | the real result cut to a stated length (200 characters unless stated) | yes |
| `malformed` | the real result with its structure broken | yes |
| `stale` | the result of the previous call to the same tool; on a first call, an empty result | yes |
| `lost_reply` | an error after the tool has already acted, so a retry repeats the action | yes |
| `planted_instruction` | the real result with one added sentence telling the agent to repeat a marker word | yes |

A fault enters where the tool's own failure would. Your agent's code, and the framework around
it, handle it as they handle a real error or a real result. `lost_reply` is taken only on a
tool that is safe to repeat: a read tool, a write tool marked `repeatable`, or one with a
stand-in. `planted_instruction` plants a word made for that hunt and case, and a run fails as
`followed_plant` when the word turns up in the agent's reply or in a later tool call.

## The five input operators

An input operator changes the request before your agent sees it. None of them uses a model.

| Operator | What it does to the request |
|---|---|
| `typos` | swaps or drops 5% of its characters |
| `reordered` | puts its sentences in a different order |
| `padded` | adds an unrelated paragraph from a fixed list before it |
| `cut_short` | keeps only its first sentence |
| `variant` | uses the next entry of the case's own `variants`; a case with none is left as written |

## What needs an adapter

The four conversation moves and the five model faults are in the catalogue, and this version
cannot make them. The one way in it ships, `rollout`, calls your agent as a function: it can
change the tools' behaviour and the request, and it does not sit between your agent and its
model or play a conversation's turns. `poisson-break catalog` marks those nine lines, and
settings that ask for one are refused before any run.

## Choosing what a hunt may change

`[vary]` in `break.toml` lists what a hunt may use. A fault or an operator left out of its list
is off, and the hunt's result names what was off under `not looked at`.

```toml
[vary]
tools = ["error", "timeout", "rate_limited", "empty"]
inputs = ["typos", "padded"]
max_call = 1                        # the latest call to a tool that a fault may land on
```

A fault lands only where your agent's calls can reach it. Break learns that from the control
stage, which records how many times each case calls each tool. With `max_call = 1` a fault is
tried on a tool's first call and no later one.

## Labels from published lists

Two published lists name ways a system built on a language model is attacked or goes wrong:
the OWASP Top 10 for LLM Applications 2025, and NIST AI 100-2 E2025. Where a change in the
catalogue is an instance of an entry in one of them, Break can show that entry's label beside
the change.

```sh
poisson-break catalog --labels
```

A label is shown only where Break's table has a row for that change, and each row quotes the
published text it rests on. `poisson-break catalog --labels --json` carries each row whole: the
list, the label, its title, where the text is published, and the quoted text. A change with no
row shows no label. Most changes have none: a tool that times out is an ordinary failure, not
an entry in a list of attacks.

## A fault of your own

The catalogue is open. A fault you write and register is named, hunted and replayed as the ten
above are. See [Adding a fault](extending/fault.md).
