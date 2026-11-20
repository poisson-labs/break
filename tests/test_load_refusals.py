"""The ways loading can fail, through the library: each refused before any run, with nothing replaced (spec §12.7, ways 1
to 7).

Invariants held here (Break — Plan, the module that wraps tools at load; spec §12.8):
- BK15.13 All or nothing: with two `at` lines of which the second is refused, for each of ways 1 to 7, no name anywhere
          is replaced.
- BK15.17, the library's half: ways 1 to 7 raise `ToolRefused` whose `.tool` is the tool (the second line's, for way
          4), from `load_target` and from `wrap_at_load`. Ways 8 and 9 are the settings file's (`tests/test_load_settings.py`),
          and what each command prints is `tests/test_commands_load.py`'s.

Each case is spec §12.7's own example: the same tools, the same modules, the same names. A test pins the refusal's kind,
the tool and the facts the spec's line carries (the place, the module, the nearest name, the other tool, what the place
holds), never its words (plan §2, item 3; ruled 2026-11-20 in this module's Session A, at Taylor's yes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from tests.load_support import AGENTS_PY, TOOLS_PY, child, spec_project, spec_settings

#: An agent that holds its own `check_policy` and imports nothing of `my_app.tools`, for the ways in which that module
#: is not there or does not hold the tool.
AGENTS_INLINE = '''\
from poisson_prove import Episode


def check_policy(topic: str) -> str:
    return "Refunds within thirty days."


def refund_agent(cfg, seed):
    return Episode(outcome="done", t=0.0, horizon=1.0, meta={"reply": check_policy("refunds")})
'''

WRAPPED_IN_TOOLS = TOOLS_PY + '''
from poisson_break.apply import wrap

lookup_order = wrap("lookup_order", lookup_order)
'''

FIRST_IN_TOOLS = {"check_policy": {"class": "read", "at": "my_app.tools:check_policy"}}
FIRST_IN_AGENTS = {"check_policy": {"class": "read", "at": "my_app.agents:check_policy"}}


def at(place: str) -> dict[str, str]:
    return {"class": "read", "at": place}


@dataclass(frozen=True)
class Way:
    """One of spec §12.7's ways: the project's files that differ from the spec's, the `[tools]` lines (a good one first,
    the refused one second), the tool the refusal names, and the facts its line carries."""

    files: dict[str, str | None]
    lines: dict[str, Any]
    tool: str
    facts: tuple[str, ...]
    modules: tuple[str, ...] = ("my_app.agents", "my_app.tools", "my_app.fakes")
    absent: tuple[str, ...] = field(default=())


WAYS: dict[str, Way] = {
    # error: the tool lookup_order is to be wrapped at my_app.tools:lookup_order, and my_app.tools could not be
    # imported (No module named 'my_app.tools')
    "1, the module cannot be imported": Way(
        files={"agents": AGENTS_INLINE, "tools": None},
        lines={**FIRST_IN_AGENTS, "lookup_order": at("my_app.tools:lookup_order")},
        tool="lookup_order", facts=("lookup_order", "my_app.tools:lookup_order", "No module named 'my_app.tools'"),
        modules=("my_app.agents", "my_app.fakes")),
    # error: the tool lookup_order is to be wrapped at my_app.tools:lookup_order, and my_app.tools has no
    # lookup_order; it has lookup_orders
    "1, the module has no such name": Way(
        files={"agents": AGENTS_INLINE, "tools": "def lookup_orders(query):\n    return query\n"},
        lines={**FIRST_IN_AGENTS, "lookup_order": at("my_app.tools:lookup_order")},
        tool="lookup_order", facts=("my_app.tools:lookup_order", "lookup_orders")),
    "1, the module has no such name and none near it": Way(
        files={"agents": AGENTS_INLINE, "tools": "def unrelated_entirely(query):\n    return query\n"},
        lines={**FIRST_IN_AGENTS, "lookup_order": at("my_app.tools:lookup_order")},
        tool="lookup_order", facts=("my_app.tools:lookup_order",), absent=("unrelated_entirely",)),
    # error: the tool lookup_order is to be wrapped at my_app.tools:lookup_order, which is a dict, not something
    # that can be called
    "2, not callable": Way(
        files={"tools": TOOLS_PY + '\nlookup_order = {"by": "id"}\n'},
        lines={**FIRST_IN_TOOLS, "lookup_order": at("my_app.tools:lookup_order")},
        tool="lookup_order", facts=("my_app.tools:lookup_order", "dict")),
    # error: the tool lookup_order is to be wrapped at my_app.tools:LookupOrder, which is a class; Break wraps a
    # function
    "3, a class": Way(
        files={"tools": TOOLS_PY + "\n\nclass LookupOrder:\n    def __call__(self, query):\n        return query\n"},
        lines={**FIRST_IN_TOOLS, "lookup_order": at("my_app.tools:LookupOrder")},
        tool="lookup_order", facts=("my_app.tools:LookupOrder",)),
    # error: the tools lookup_order and find_order are both to be wrapped at one function,
    # my_app.tools:lookup_order; one function is one tool
    "4, two lines name one place": Way(
        files={},
        lines={"lookup_order": at("my_app.tools:lookup_order"), "find_order": at("my_app.tools:lookup_order")},
        tool="find_order", facts=("lookup_order", "find_order", "my_app.tools:lookup_order")),
    "4, two lines name one function by two places": Way(
        files={},
        lines={"lookup_order": at("my_app.tools:lookup_order"), "find_order": at("my_app.agents:lookup_order")},
        tool="find_order", facts=("lookup_order", "find_order")),
    # error: the tool lookup_order has a wrap line in your code and  at  in break.toml; one of the two reaches it
    "5, a wrap line ran under its name": Way(
        files={"agents": AGENTS_PY + '\nfrom poisson_break.apply import wrap\n\n_kept = wrap("lookup_order", len)\n'},
        lines={**FIRST_IN_TOOLS, "lookup_order": at("my_app.tools:lookup_order")},
        tool="lookup_order", facts=("lookup_order",)),
    "5, the place holds what wrap made under its name": Way(
        files={"tools": WRAPPED_IN_TOOLS},
        lines={**FIRST_IN_TOOLS, "lookup_order": at("my_app.tools:lookup_order")},
        tool="lookup_order", facts=("lookup_order",)),
    # error: the tool find_order is to be wrapped at my_app.tools:lookup_order, which your code already wraps as
    # lookup_order
    "6, already wrapped under another name": Way(
        files={"tools": WRAPPED_IN_TOOLS},
        lines={**FIRST_IN_TOOLS, "find_order": at("my_app.tools:lookup_order")},
        tool="find_order", facts=("find_order", "my_app.tools:lookup_order", "lookup_order")),
    # error: the tool lookup_order, at my_app.tools:lookup_order, is async, and Break calls a tool and reads what it
    # returns
    "7, async": Way(
        files={"tools": TOOLS_PY + "\n\nasync def lookup_order(query: str) -> str:\n    return query\n"},
        lines={**FIRST_IN_TOOLS, "lookup_order": at("my_app.tools:lookup_order")},
        tool="lookup_order", facts=("lookup_order", "my_app.tools:lookup_order")),
}

_SEEN: dict[str, Any] = {}


@pytest.fixture
def refused(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Any:
    """What one way does, made once in a child: the refusal `load_target` raised, the one `wrap_at_load` raised for the
    same places, and every place that changed across each, among the user's modules' names, dicts and lists and every
    loaded module's functions."""
    name = request.param
    if name not in _SEEN:
        way = WAYS[name]
        root = spec_project(tmp_path_factory.mktemp("way"), **way.files)
        places = {tool: line["at"] for tool, line in way.lines.items()}
        _SEEN[name] = child(f'''
            for module in {list(way.modules)!r}:
                importlib.import_module(module)
            import poisson_break.hunt
            from poisson_break.apply import wrap_at_load
            before = snapshot(["my_app"])
            by_load = refusal(lambda: load({spec_settings(way.lines)!r}))
            between = snapshot(["my_app"])
            by_call = refusal(lambda: wrap_at_load({places!r}))
            after = snapshot(["my_app"])
            out({{"load": by_load, "call": by_call, "changed by load": changed(before, between),
                  "changed by call": changed(between, after)}})
        ''', paths=[root])
    return WAYS[name], _SEEN[name]


@pytest.mark.parametrize("refused", list(WAYS), indirect=True)
def test_each_way_is_tool_refused_naming_the_tool(refused: Any) -> None:
    """Spec §12.7: ways 1 to 7 are `ToolRefused` naming the tool, raised while the agent is loaded, and `wrap_at_load`
    raises the same (§12.4). For way 4 the tool is the second line's."""
    way, said = refused
    for how in ("load", "call"):
        got = said[how]
        assert got is not None, f"{how}: nothing was refused"
        assert "ToolRefused" in got["bases"] and "ValueError" in got["bases"], got
        assert got["tool"] == way.tool, got


@pytest.mark.parametrize("refused", list(WAYS), indirect=True)
def test_each_way_carries_the_facts_of_its_line(refused: Any) -> None:
    way, said = refused
    for how in ("load", "call"):
        message = said[how]["message"]
        for fact in way.facts:
            assert fact in message, (how, fact, message)
        for fact in way.absent:
            assert fact not in message, (how, fact, message)


@pytest.mark.parametrize("refused", list(WAYS), indirect=True)
def test_a_refusal_replaces_nothing_anywhere(refused: Any) -> None:
    """BK15.13: the first line was a place Break could use, and still nothing was replaced, by the load or by
    `wrap_at_load`: every module is as a plain import left it."""
    _, said = refused
    assert said["changed by load"] == []
    assert said["changed by call"] == []


def test_the_first_line_alone_would_have_been_replaced(tmp_path: Path) -> None:
    """The control to the cases above: the good line of each, loaded on its own, does replace its tool, so a refusal
    that replaced nothing is the refusal's doing."""
    root = spec_project(tmp_path)
    said = child(f'''
        import my_app.agents
        before = slots(["my_app"])
        load({spec_settings(FIRST_IN_TOOLS)!r})
        after = slots(["my_app"])
        out(sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k)))
    ''', paths=[root])
    assert said == ["my_app.agents:check_policy", "my_app.tools:check_policy"]
