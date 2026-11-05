"""What the settings module's tests share: the spec's settings file, written out once, how a file is put
together, and the lazy import of `poisson_break.settings`.

The module is imported lazily, by `settings()`, so on a tree without it each test fails on its own and the
rest of the suite still runs.

**These tests read a settings value through the file, never through an attribute.** The plan names "the frozen
settings types" and no field of them, so a value is read by writing it out with `dump` and reading that text
with `tomllib`, and a default is shown by equality: a file that leaves a key out reads the same as one that
states the default, and differently from one that states anything else. Neither rests on a field's name.

The tables are literal on purpose. A test that read the defaults from the module could not notice one changing.
"""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.changes_support import PLAN_WORDS

# The settings file as spec §9.4 prints it, comments and all. Its target is an on-demand kind, which is the point
# of plan BK4.7: this file parses today.
SAMPLE = '''\
# Poisson Break: what to hunt, what may change, and when to stop.
# Written by `poisson-break init`. Edit it freely; `poisson-break doctor` checks it.
version = 1

[target]
kind = "openai-agents"              # rollout | openai-agents | langgraph | crewai | mcp | command
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
'''

# The kinds, and which the core ships (spec §7.1).
SHIPPED_KIND = "rollout"
ON_DEMAND_KINDS = ("openai-agents", "langgraph", "crewai", "mcp", "command")

# What each key defaults to, where §9.4 prints it on an uncommented line, as (table, key, the default as TOML,
# another value as TOML, the other value as read back).
#
# 400, 5, 4, 8, 5, 0.20, 0.05 and 3 are plan ruling 19. 120 is spec §4 and `screen` is §5.3. `retry_storm_after` is §4's 5,
# printed commented out because no line means that (the failure check's ruling 6). The rest are §9.4's.
FAULTS_TOML = ('["error", "timeout", "slow", "rate_limited", "empty", "cut_off", "malformed", "stale", '
               '"lost_reply", "planted_instruction"]')
OPERATORS_TOML = '["typos", "reordered", "padded", "cut_short", "variant"]'
CHECKS_TOML = '["crashed", "hung", "ran_out", "forbidden_call", "followed_plant", "duplicate_write", "wrong"]'
DEFAULTS = (
    ("fails", "checks", CHECKS_TOML, '["crashed"]', ["crashed"]),
    ("fails", "run_seconds", "120", "60", 60),
    ("fails", "retry_storm_after", "5", "7", 7),
    ("vary", "tools", FAULTS_TOML, '["error", "timeout"]', ["error", "timeout"]),
    ("vary", "inputs", OPERATORS_TOML, '["typos"]', ["typos"]),
    ("vary", "max_call", "3", "7", 7),
    ("search", "strategy", '"screen"', '"random"', "random"),
    ("search", "runs", "400", "401", 401),
    ("search", "control_repeats", "5", "6", 6),
    ("search", "cases_per_condition", "4", "3", 3),
    ("search", "seed", "20261005", "7", 7),
    ("confirm", "candidates", "8", "9", 9),
    ("confirm", "repeats", "5", "4", 4),
    ("confirm", "max_difference", "0.20", "0.30", 0.30),
    ("confirm", "q", "0.05", "0.1", 0.1),
    ("limits", "hours", "2", "3", 3),
    ("output", "folder", '"break-runs"', '"elsewhere"', "elsewhere"),
)

# Keys §9.4 prints commented out, each with a value to set it to. They default to nothing being on. The cap and the
# two prices are set together (yes/no 6), and are in `PRICES`.
OPTIONAL = (
    ("fails", "outcomes", '["unresolved"]', ["unresolved"]),
    ("fails", "own", '"my_app.checks:refund_ok"', "my_app.checks:refund_ok"),
    ("fails", "also", '["gave_up"]', ["gave_up"]),
    ("fails", "never_call", '["delete_account"]', ["delete_account"]),
    ("fails", "max_tool_calls", "40", 40),
    ("fails", "max_tokens", "20000", 20000),
    ("vary", "conversation", '["repeats", "interrupts", "goes_quiet", "presses"]',
     ["repeats", "interrupts", "goes_quiet", "presses"]),
    ("vary", "model", '["error", "timeout", "rate_limited", "empty", "cut_off"]',
     ["error", "timeout", "rate_limited", "empty", "cut_off"]),
)
PRICES = 'dollars = 7.5\ninput_per_million = 0.125\noutput_per_million = 0.5'

TOOL_LINES = 'lookup_order = "read"'


def settings() -> ModuleType:
    return importlib.import_module("poisson_break.settings")


def doc(*, kind: str = SHIPPED_KIND, tools: str = TOOL_LINES, head: str = "version = 1", **tables: str) -> str:
    """A settings file. `tables` holds any other table's lines by name, a double underscore standing for a dot
    (`vary__env` is `[vary.env]`). What it holds without being asked is what §9.4 gives no default for."""
    parts = [head, "", "[target]", f'kind = "{kind}"', 'entry = "my_app.agents:refund_agent"', 'cases = "cases.jsonl"',
             "", "[tools]", tools]
    for name, lines in tables.items():
        parts += ["", f"[{name.replace('__', '.')}]", lines]
    return "\n".join(parts) + "\n"


def written(text: str) -> dict[str, Any]:
    """What `dump` writes for a file, as TOML reads it."""
    s = settings()
    dumped = s.dump(s.loads(text))
    assert isinstance(dumped, str)
    return tomllib.loads(dumped)


def line_of(text: str, needle: str) -> int:
    """The line a piece of text is on, counted from 1. The piece must be there once, or the test is wrong."""
    found = [n for n, line in enumerate(text.splitlines(), 1) if needle in line]
    assert len(found) == 1, f"{needle!r} is on lines {found}"
    return found[0]


def assert_one_line(error: BaseException) -> None:
    """An error is one line and says nothing of the plan's machinery (spec §9.2, plan §2 item 7). What it says
    beyond that is not read: no refusal test matches a message's words (plan §2 item 3)."""
    message = str(error)
    assert message.strip(), "the error says nothing"
    assert "\n" not in message and "\r" not in message, f"more than one line: {message!r}"
    assert not PLAN_WORDS.search(message), message
    assert "Traceback" not in message and "<class" not in message, message


def refused(text: str) -> Any:
    """Reading the text is refused with a `SettingsError` of one line, which is handed back."""
    s = settings()
    with pytest.raises(s.SettingsError) as caught:
        s.loads(text)
    assert_one_line(caught.value)
    return caught.value


def refused_at(text: str, key: str, needle: str | None = None) -> Any:
    """Refused, naming the key by its path and, where `needle` is given, on the line that holds it."""
    error = refused(text)
    assert error.key == key, f"named {error.key!r}, not {key!r}"
    if needle is not None:
        assert error.line == line_of(text, needle), f"line {error.line}, not the line of {needle!r}"
    return error


def suggests(error: Any, *path: str) -> None:
    """The suggestion is the known key asked for: written whole or by its last part, which the spec leaves open."""
    assert error.suggestion in (".".join(path), path[-1]), f"suggested {error.suggestion!r}, not {path}"


def write_cases(folder: Path, lines: list[str], name: str = "cases.jsonl") -> Path:
    path = folder / name
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return path
