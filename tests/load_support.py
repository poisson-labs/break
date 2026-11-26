"""What the tests of wrapping at load share (spec §12; Break — Plan, the module that wraps tools at load).

**Every load runs in a child process.** What loading does lasts for the life of the process (spec §12.4: Break does not
put the original back), and whether a tool is reached by `wrap` depends on whether a `wrap` line under its name has run
in the process (spec §12.4, `Reached.how`; §12.7, way 5). The test process has run many `wrap` lines by the time any
test here runs, `lookup_order` among them. So each load is made in a fresh interpreter, under the network guard, by a
script that prints one JSON document on a line of its own (`child`). A test that only reads the settings file loads
nothing, and runs in the test process.

**The spec's project** (`my_app`, `spec_project`) is the help desk spec §12 writes its examples about: the tools defined
in `my_app/tools.py`, taken by `from … import` into `my_app/agents.py`, whose `refund_agent(cfg, seed)` is the entry, and
a stand-in in `my_app/fakes.py`. No file of it holds a Break line. A test writes it into its own folder, changes what it
needs, and loads it from there.

**The twins and the holders module** are built with the module, in `tests/agents/`, as spec §12.8 names them (plan
§2, item 2: the build writes the scripted agents and these tests hold them to what they do). What the tests here read of
them, and so what each must be:

- `tests/agents/twins/wrapped/twin_desk.py` and `tests/agents/twins/bare/twin_desk.py`: one scripted agent written twice,
  each the module `twin_desk` when its own folder is first on the import path, so that a hunt of either has one name.
  Each defines the three tools of the scripted agents, `lookup_order(query, detail=None)`, `check_policy(topic,
  note=None)` and `issue_refund(request)`, answering as the plain agents' tools answer (`tests/apply_support.py`,
  `plain_tools`), and a stand-in `refund_stand_in(request)`; each real run of a tool or of the stand-in is added to the
  module's list `EXECUTED` as `(name, arguments)`. The entry `desk(cfg, seed)` runs the plain scripted agent
  `cfg["agent"]` (`gives_up` when the case has none) over the module's own tools by name, looked up when each call is
  made, and hands back a Prove `Episode` with the outcome `unresolved` when any call failed and `done` when none did,
  `t` 0.0, `horizon` 1.0, and `meta` holding `reply` (the agent's reply), `run` (the plain agent's `Run`) and `raised`
  (a tuple of every exception a tool call raised, in order). The wrapped twin wraps each of the three tools at its top
  with `wrap`, one line each, under the tool's own name; the bare twin's file holds no `poisson_break` anywhere, defines
  each tool under the tool's own name and holds it under no other, and its tools are reached by `at =
  "twin_desk:<tool>"` lines. Both keep to what `tests/test_scripted_agents.py` holds of a
  file under `tests/agents/`: so the `Episode` comes through a module of `tests` outside `tests/agents/` that wraps
  nothing.
- `tests/agents/holders/` (a package): `tools.py` defines `lookup_order(query, detail=None)` ("Look an order up."),
  `check_policy(topic)`, `issue_refund(request)`, `send_email(to)` and `cancel_order(order)`, each adding `(name,
  arguments)` to `tools.EXECUTED` and answering with a string. `__init__.py` re-exports `lookup_order` and nothing else of
  `tools`. `agent.py` takes all five by `from tests.agents.holders.tools import …`, and holds them in a module-level dict
  `TOOLS`, keyed by their names, and a module-level list `TOOL_LIST`, in the order `lookup_order`, `check_policy`,
  `issue_refund`, `send_email`, `cancel_order`; it also holds `lookup_order`, and nothing else of `tools`, four more
  ways: `AGENT = make_agent(lookup_order)`, a closure whose function holds the tool in its own cell; `FIND =
  functools.partial(lookup_order)`; `HELP = (lookup_order, "Look an order up.")`, a tuple; and `BOX`, an object of a
  class of the module whose attribute `lookup` is the tool. Its entry `desk(cfg, seed)` calls `TOOLS["lookup_order"]`
  once with the case's input and hands back an `Episode` with the outcome `done`. Nothing in the package holds a Break
  line.

The holders' settings (`HOLDERS_TOOLS`) give `lookup_order` and `check_policy` an `at`, `issue_refund` a `write` line
with no `at`, `send_email` an `off` line, and `cancel_order` no line at all.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tests.commands_support import settings_text
from tests.conftest import GUARD, REPO, TESTS, guarded_env

TWINS = TESTS / "agents" / "twins"
WRAPPED_TWIN = TWINS / "wrapped"
BARE_TWIN = TWINS / "bare"
TWIN_TOOLS = ("lookup_order", "check_policy", "issue_refund")

HOLDERS = "tests.agents.holders"
HOLDERS_ENTRY = f"{HOLDERS}.agent:desk"
HOLDERS_TOOLS: dict[str, Any] = {
    "lookup_order": {"class": "read", "at": f"{HOLDERS}.tools:lookup_order"},
    "check_policy": {"class": "read", "at": f"{HOLDERS}.tools:check_policy"},
    "issue_refund": {"class": "write", "repeatable": True},
    "send_email": "off",
}
#: The five places of spec §12.8 (BK15.9) for `lookup_order`, in text order.
LOOKUP_PLACES = tuple(sorted((
    f"{HOLDERS}.tools:lookup_order",
    f"{HOLDERS}.agent:lookup_order",
    f"{HOLDERS}:lookup_order",
    f"{HOLDERS}.agent:TOOLS[lookup_order]",
    f"{HOLDERS}.agent:TOOL_LIST[0]",
)))
CHECK_PLACES = tuple(sorted((
    f"{HOLDERS}.tools:check_policy",
    f"{HOLDERS}.agent:check_policy",
    f"{HOLDERS}.agent:TOOLS[check_policy]",
    f"{HOLDERS}.agent:TOOL_LIST[1]",
)))

#: The three answers of `Reached.how` (spec §12.4).
HOWS = ("at load", "wrap", "not seen")

# ---------------------------------------------------------------------------
# the spec's project
# ---------------------------------------------------------------------------

SPEC_ENTRY = "my_app.agents:refund_agent"

TOOLS_PY = '''\
"""The help desk's tools, as a user writes them: plain functions, and no line of anything else's."""

CALLS: list = []


def lookup_order(query: str, detail: str | None = None) -> str:
    """Look an order up."""
    CALLS.append(("lookup_order", query))
    if query == "missing":
        raise LookupError(f"there is no order {query}")
    return f"Order {query} shipped on Tuesday."


def check_policy(topic: str) -> str:
    """Read the refund policy."""
    CALLS.append(("check_policy", topic))
    return "Refunds within thirty days."


def issue_refund(request: str) -> str:
    """Move the money back."""
    CALLS.append(("issue_refund", request))
    return "Refund issued."


def send_email(to: str) -> str:
    CALLS.append(("send_email", to))
    return "sent"


def cancel_order(order: str) -> str:
    CALLS.append(("cancel_order", order))
    return "cancelled"
'''

AGENTS_PY = '''\
"""The help desk's agent: it takes its tools from the tools module, and holds no line of Break's."""

from poisson_prove import Episode

from my_app.tools import check_policy, issue_refund, lookup_order, send_email


def refund_agent(cfg, seed):
    found = lookup_order(cfg["input"])
    policy = check_policy("refunds")
    return Episode(outcome="done", t=0.0, horizon=1.0, meta={"reply": f"{found} {policy}"})
'''

FAKES_PY = '''\
"""The stand-in the settings name for issue_refund."""

STOOD_IN: list = []


def refund(request: str) -> str:
    STOOD_IN.append(request)
    return "Refund issued (stand-in)."
'''

#: `[tools]` as spec §12.3 writes it.
SPEC_TOOLS: dict[str, Any] = {
    "lookup_order": {"class": "read", "at": "my_app.tools:lookup_order"},
    "check_policy": {"class": "read", "at": "my_app.tools:check_policy"},
    "issue_refund": {"class": "write", "stand_in": "my_app.fakes:refund", "at": "my_app.tools:issue_refund"},
    "send_email": "off",
}


def write_files(root: Path, files: Mapping[str, str]) -> Path:
    """Each file under `root`, by its path there; hands back `root`."""
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def spec_project(root: Path, **files: str | None) -> Path:
    """The spec's `my_app` under `root`; a keyword names a file of the package to replace (`tools`, `agents`,
    `fakes`), or to leave out with `None`, and any other file it holds (`sms="..."` writes `my_app/sms.py`)."""
    held: dict[str, str | None] = {"__init__": "", "tools": TOOLS_PY, "agents": AGENTS_PY, "fakes": FAKES_PY, **files}
    write_files(root, {f"my_app/{name}.py": text for name, text in held.items() if text is not None})
    return root


def spec_settings(tools: Mapping[str, Any] | None = None, *, entry: str = SPEC_ENTRY, **more: Any) -> str:
    """A whole `break.toml` for the spec's project, `[tools]` as spec §12.3 writes it unless given."""
    return settings_text(entry=entry, tools=SPEC_TOOLS if tools is None else tools, **more)


# ---------------------------------------------------------------------------
# a child process that loads, and says what it found
# ---------------------------------------------------------------------------

#: What every child script can call: `out(value)` prints the one result; `reached(r)` is a `Reached` as plain data;
#: `refusal(fn)` runs `fn` and hands back the refusal it raised as plain data, or `None`; `slots(prefixes)` is every
#: module-level name, dict value and list item of the loaded modules whose names start with a prefix, by place, as the
#: `id` of what it holds; `snapshot(own)` and `changed(before, after)` say which places differ across a load;
#: `load(text)` reads a settings file's text and loads its target.
PRELUDE = '''
import gc, importlib, inspect, json, sys, types

def out(value):
    print("@@result " + json.dumps(value, default=repr), flush=True)

def reached(r):
    held = None if r.held_elsewhere is None else [{"kind": h.kind, "where": h.where} for h in r.held_elsewhere]
    return {"tool": r.tool, "how": r.how, "at": r.at, "places": list(r.places), "held_elsewhere": held}

def refusal(fn):
    try:
        fn()
    except Exception as wrong:
        return {"type": type(wrong).__name__, "bases": [c.__name__ for c in type(wrong).__mro__],
                "tool": getattr(wrong, "tool", None), "message": str(wrong),
                "key": getattr(wrong, "key", None), "line": getattr(wrong, "line", None)}
    return None

def slots(prefixes=None, *, functions_only=False):
    held = {}
    for name, module in list(sys.modules.items()):
        if module is None or name in ("__main__", "__mp_main__") or module is sys.modules.get("__main__"):
            continue
        if prefixes is not None and not any(name == p or name.startswith(p + ".") for p in prefixes):
            continue
        try:
            names = dict(vars(module))
        except TypeError:
            continue
        for key, value in names.items():
            if not functions_only or isinstance(value, types.FunctionType):
                held[f"{name}:{key}"] = id(value)
            if isinstance(value, dict):
                for k, v in list(value.items()):
                    if not functions_only or isinstance(v, types.FunctionType):
                        held[f"{name}:{key}[{k}]"] = id(v)
            elif isinstance(value, list):
                for i, v in enumerate(list(value)):
                    if not functions_only or isinstance(v, types.FunctionType):
                        held[f"{name}:{key}[{i}]"] = id(v)
    return held

def snapshot(own=()):
    """The loaded modules, and the `id` at each place: every function anywhere, and everything in `own`'s modules."""
    loaded = {n for n, m in sys.modules.items() if m is not None}
    return loaded, {**slots(functions_only=True), **(slots(list(own)) if own else {})}

def changed(before, after):
    """The places that differ between two snapshots, in modules loaded at the first, Break's own left out: a module
    imported between the two is new, not changed."""
    loaded, one = before
    _, other = after
    keys = {k for k in set(one) | set(other) if k.split(":")[0] in loaded}
    return sorted(k for k in keys if one.get(k) != other.get(k)
                  and not (k.startswith("poisson_break:") or k.startswith("poisson_break.")))

def load(text):
    from poisson_break.hunt import load_target
    from poisson_break.settings import loads
    return load_target(loads(text))
'''


def child(code: str, *, paths: Sequence[Path] = (), cwd: Path | None = None, exit_code: int = 0,
          timeout: float = 240.0) -> Any:
    """Run `code` in a fresh interpreter under the network guard, with `paths` first on the import path and then the
    tree's `src` and the repository; hand back what it gave `out`. A child that exits otherwise than `exit_code`, or
    gives nothing, fails the test with everything it printed."""
    env = guarded_env()
    env["PYTHONPATH"] = os.pathsep.join([str(GUARD), *(str(p) for p in paths), str(REPO / "src"), str(REPO)])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    done = subprocess.run([sys.executable, "-c", PRELUDE + "\n" + textwrap.dedent(code)], capture_output=True,
                          text=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL, cwd=cwd)
    said = f"exit {done.returncode}\n--- stdout\n{done.stdout}\n--- stderr\n{done.stderr}"
    assert done.returncode == exit_code, said
    found = [line[len("@@result "):] for line in done.stdout.splitlines() if line.startswith("@@result ")]
    assert len(found) == 1, said
    return json.loads(found[0])


def held_as(held: Any) -> Any:
    """`held_elsewhere` as a set of (kind, where), or `None`."""
    return None if held is None else {(h["kind"], h["where"]) for h in held}
