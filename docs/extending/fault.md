# Adding a fault

A fault is one way a tool can misbehave: what the agent sees in place of the tool's result, and
whether the real tool still runs. Break's catalogue has ten. When your tools fail in a way none
of them covers, you add your own, from your own module, with no change to Break.

The interface is versioned as `FAULT_INTERFACE_VERSION`, which is 1. A change that would break
a fault written against it bumps that number.

## What a fault is

A fault is an object with five attributes and one method:

| Member | What it is |
|---|---|
| `name` | the word after `=` in a condition's name, such as `error_page` in `tool:lookup_order#1=error_page`; letters, digits and underscores; not already taken by another tool fault |
| `surface` | `"tool"` |
| `description` | one line in plain words; `poisson-break catalog` prints it |
| `parameters` | each parameter's name with its default; `{}` for none |
| `real_runs` | `True` if `apply` runs the real tool, `False` if it does not |
| `apply(call, *, real, params, rng)` | returns what the agent should see: `Result(value=...)` or `ToolError(kind=..., message=...)` |

`call` is all a fault is told about the run: the tool's name, the call's arguments, the call's
number, the condition, the run's seed, the tool's previous result if it had one, and the marker
word if one is planted. `real()` runs the real tool once and returns its result. `rng` is a
generator Break seeds, so the same run gives the same outcome every time it is replayed.

Break checks two rules on every call. `apply` calls `real` exactly as often as `real_runs`
says: once or not at all. And `apply` returns a `Result` or a `ToolError` and nothing else. A
fault that breaks either rule, or raises an error of its own, stops the run as Break's own
failure: the run is not counted, and the agent is never blamed for it. An error the real tool
raises inside `real()` is not the fault's, and it passes to the agent as it is. A third rule is
yours to keep: use no randomness but `rng`, or a replay will not repeat the run.

## An example

Some services fail without raising anything: the caller gets a page of HTML where the result
should be. This fault does that. The program registers it, then runs one tool twice inside a
session whose condition puts the fault on the first call.

```python
from poisson_break.apply import Session, wrap
from poisson_break.changes import CATALOG, Result, parse, register
from poisson_break.interfaces import FAULT_INTERFACE_VERSION

PAGE = "<html><body><h1>503 Service Unavailable</h1></body></html>"


class ErrorPage:
    name = "error_page"
    surface = "tool"
    description = "an HTML error page as the result, with no error raised; the real tool does not run"
    parameters = {}
    real_runs = False

    def apply(self, call, *, real, params, rng):
        return Result(value=PAGE)


assert FAULT_INTERFACE_VERSION == 1
register(ErrorPage())
print([line.name for line in CATALOG if line.surface == "tool"][-1])

lookup_order = wrap("lookup_order", lambda order: f"Order {order} shipped on Tuesday.")

session = Session(parse("tool:lookup_order#1=error_page"), seed=7, tools={"lookup_order": "read"})
with session:
    print(lookup_order("4821"))
    print(lookup_order("4821"))
for call in session.calls:
    print(call.tool, call.call, call.change, call.real_ran)
```

It prints the fault's name as the catalogue now lists it, what the agent saw on each call, and
Break's record of the two calls:

```text
error_page
<html><body><h1>503 Service Unavailable</h1></body></html>
Order 4821 shipped on Tuesday.
lookup_order 1 tool:lookup_order#1=error_page False
lookup_order 2 None True
```

## Using it in a hunt

Register the fault in a module your agent's module imports, and name it in `break.toml` beside
Break's own:

```toml
[vary]
tools = ["error", "timeout", "error_page"]
```

Reading `break.toml` imports none of your code, so the name is not checked there. `doctor` and
`hunt` load your agent first, which registers the fault, and refuse a name that is still
unknown before any run. The `own-fault` example is this fault in a full hunt:

```sh
poisson-break init --example own-fault
poisson-break hunt --yes
poisson-break confirm --yes
```
