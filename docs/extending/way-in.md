# Adding a way in

A way in is how Break drives one kind of agent and reaches its tools. This version ships one,
`rollout`: a Python function Break calls, with each tool wrapped
([the rollout way in](../ways-in/rollout.md)). An agent built another way, on a framework or
behind a protocol, needs a way in of its own. This page is the interface one is written
against.

The interface is versioned as `TARGET_INTERFACE_VERSION`, which is 1.

## What a way in is

A way in is an object with two attributes and three methods:

| Member | What it is |
|---|---|
| `kind` | the way in's name |
| `framework_versions` | the framework versions it was checked against; empty when it needs no framework |
| `tools()` | the agent's tools, each a `ToolInfo(name=...)`, listed before any run |
| `capabilities()` | which of three things it can do: route tool calls, fault the model's own calls, play a scripted conversation |
| `run(case, session, *, seed, limits)` | runs the agent once on one case and returns a `RunResult` |

In `run`, every tool call the agent makes goes through the session:

```text
session.call(tool, args, real)
```

`tool` is the tool's name, `args` the call's arguments as a mapping, and `real` a function of
no arguments that runs the real tool once. The call returns what the agent should see, or
raises `ToolFailure` where the tool's own failure would be, which the way in shows the agent
in whatever form its framework shows a failed tool.

A `RunResult` says how the run ended and nothing more: the `reply`, the `outcome` the agent
itself reported or `None`, `tokens_in` and `tokens_out` where the way in can see them, and
`ended`, one of `returned`, `raised` or `limit` (the agent's own step or turn limit).

A way in decides nothing. Break applies the changes, enforces the time limit, decides whether
the run failed and writes its record. Break also holds a way in to these rules:

- Under the control, with no change, the agent's calls, their results and their order are what
  they are without Break.
- Every tool call goes through `session.call`.
- The tools `tools()` lists are the tools the control stage sees. A tool listed with no line in
  `[tools]` is refused before any run.
- A way in says what it cannot do in `capabilities()`, and settings that ask for it are refused
  before any run, in one line.

## An example

The program below is a way in for an agent that is one function call. It opens a hunt on it and
runs the control stage, through the library.

```python
import tempfile

from poisson_break import hunt
from poisson_break.apply import RunResult, ToolFailure, ToolInfo
from poisson_break.interfaces import TARGET_INTERFACE_VERSION, Capabilities
from poisson_break.settings import loads


def lookup_order(order):
    return f"Order {order} shipped on Tuesday."


class Desk:
    kind = "desk"
    framework_versions = ()

    def tools(self):
        return [ToolInfo(name="lookup_order")]

    def capabilities(self):
        return Capabilities(tool_calls=True, model_calls=False, conversation=False)

    def run(self, case, session, *, seed, limits):
        order = case["input"].split()[-1].rstrip("?")
        try:
            reply = session.call("lookup_order", {"order": order}, lambda: lookup_order(order))
        except ToolFailure:
            return RunResult(reply="Sorry, I could not look that up.", outcome="unresolved",
                             tokens_in=None, tokens_out=None, ended="returned")
        return RunResult(reply=reply, outcome="resolved", tokens_in=None, tokens_out=None,
                         ended="returned")


assert TARGET_INTERFACE_VERSION == 1
settings = loads(f"""
version = 1

[target]
kind = "rollout"
entry = "my_app.desk:desk"

[tools]
lookup_order = "read"

[fails]
outcomes = ["unresolved"]

[search]
runs = 12
control_repeats = 2

[output]
folder = "{tempfile.mkdtemp()}"
""")
cases = [{"id": f"order-{n}", "input": f"Where is order {n}?"} for n in (4821, 4822, 4823)]
opened = hunt.open_hunt(settings, target=Desk(), cases=cases)
summary = hunt.control(opened)
print(opened.name, summary.runs, summary.failed)
print({case: dict(calls) for case, calls in summary.calls.items()})
```

It prints the hunt's name, the control's runs and failures, and which tools each case called:

```text
desk-1 6 0
{'order-4821': {'lookup_order': 1}, 'order-4822': {'lookup_order': 1}, 'order-4823': {'lookup_order': 1}}
```

## What is not here yet

`break.toml` names six kinds of target: `rollout`, `openai-agents`, `langgraph`, `crewai`,
`mcp` and `command`. This version loads `rollout` from the settings. A way in of another kind
is made by its own code and handed to `open_hunt`, as the example does, and the command cannot
load one yet. A way in that can fault the model's own calls needs a method the session does not
have yet; it will arrive with the first way in that uses it.
