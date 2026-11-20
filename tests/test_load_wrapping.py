"""What loading the agent does to the tools `[tools]` places (spec §12.4), through the library.

Invariants held here (Break — Plan, the module that wraps tools at load; spec §12.8):
- BK15.1  With no `at` in `[tools]`, loading replaces nothing: every loaded module holds, under every name, the object a
          plain import left there.
- BK15.9  Every module-level holder gets the one wrapper: after loading the holders module, the defining module's
          name, the second module's name, the package's name, the dict's value and the list's item are one object; a
          call through each, inside a run, reaches the run and takes one call number; `Reached.places` lists exactly
          those five, in text order.
- BK15.10 What cannot be replaced is named: for the holders module, `held_elsewhere` holds one `Held` each for the
          closure, the partial, the tuple and the object's attribute, with `kind` and `where` as §12.4 says; for a tool
          with no such holder it is empty; none of them refuses anything.
- BK15.11 Only what is named is touched: across a load, the differences in every loaded module's names, dicts and lists
          are exactly the places of BK15.9 for the tools that have an `at`; a function with no line, a tool with no
          `at` and an `off` tool are the objects they were.
- BK15.12 Outside a run the tool is itself: the same result, the same exception, the function run once; its name,
          docstring and signature.
- BK15.14 Loading twice is loading once.
- BK15.15 Threads and nested runs are `wrap`'s.
- BK15.18 Async is refused by `wrap`'s own check.
- BK15.19 `wrap` refuses a wrapper Break made at load, naming the tool; `wrap` on anything else is as on `main`.

And spec §12.4's names and the rules at its edges: `wrap_at_load`, `Reached`, `Held`, `RolloutTarget.reached` and
`ToolLine.at`; identity, not the name, says what is the tool; a module imported later takes the wrapper; `how` is `wrap`
for a tool a `wrap` line reached and `not seen` for one nothing did; `held_elsewhere` is `None` where the interpreter
cannot list what refers to the function (§12.11, question 4).

Each load is made in a child (`tests/load_support.py` says why). A child keeps nothing of a tool's function under a
name of its own while it loads, since its own script is a loaded module too: it holds `id`s, and reads the modules.

Ruled 2026-11-19 (spec §12.11): A2 (questions 1 and 3), holders named as a note and never refused (4), a class refused
(6), nothing of async built (18), the originals never put back (20).
"""

from __future__ import annotations

import dataclasses
import importlib
from pathlib import Path
from typing import Any

import pytest

from tests.load_support import (
    CHECK_PLACES,
    HOLDERS,
    HOLDERS_ENTRY,
    HOLDERS_TOOLS,
    LOOKUP_PLACES,
    child,
    spec_project,
    spec_settings,
)
from tests.commands_support import settings_text

#: The holders module's settings, as a child script reads them.
HOLDERS_TEXT = settings_text(entry=HOLDERS_ENTRY, tools=HOLDERS_TOOLS)

#: What a child script for the holders module does first: import the package as a plain import leaves it, and keep
#: the `id` of each of its five functions, holding none of them.
HOLDERS_IMPORTED = f'''
import {HOLDERS}.agent
tools_module = sys.modules["{HOLDERS}.tools"]
agent_module = sys.modules["{HOLDERS}.agent"]
package = sys.modules["{HOLDERS}"]
original = {{name: id(getattr(tools_module, name))
            for name in ("lookup_order", "check_policy", "issue_refund", "send_email", "cancel_order")}}
'''


# ---------------------------------------------------------------------------
# the names spec §12.4 adds
# ---------------------------------------------------------------------------


def test_the_names_are_there_and_reached_and_held_are_frozen() -> None:
    apply = importlib.import_module("poisson_break.apply")
    hunt = importlib.import_module("poisson_break.hunt")
    settings = importlib.import_module("poisson_break.settings")
    assert callable(apply.wrap_at_load)
    assert {f.name for f in dataclasses.fields(apply.Reached)} == {"tool", "how", "at", "places", "held_elsewhere"}
    assert {f.name for f in dataclasses.fields(apply.Held)} == {"kind", "where"}
    held = apply.Held(kind="partial", where="my_app.agents:FIND")
    reached = apply.Reached(tool="lookup_order", how="at load", at="my_app.tools:lookup_order",
                            places=("my_app.tools:lookup_order",), held_elsewhere=(held,))
    for thing, field in ((held, "kind"), (reached, "how")):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(thing, field, "changed")
    made = hunt.RolloutTarget(lambda cfg, seed: None, tools=[])
    assert isinstance(getattr(made, "reached"), tuple)
    assert "at" in {f.name for f in dataclasses.fields(settings.ToolLine)}


# ---------------------------------------------------------------------------
# BK15.1: with no at, loading replaces nothing
# ---------------------------------------------------------------------------

NO_AT = {"lookup_order": "read", "check_policy": "read",
         "issue_refund": {"class": "write", "stand_in": "my_app.fakes:refund"}, "send_email": "off"}


def test_with_no_at_loading_replaces_nothing_anywhere(tmp_path: Path) -> None:
    """BK15.1. Every module loaded before the load holds, under every name and at every value of its dicts and lists,
    what a plain import left there; and every line is `not seen`, with no place."""
    spec_project(tmp_path)
    said = child(f'''
        import my_app.agents
        import poisson_break.hunt
        before = snapshot(["my_app"])
        target = load({spec_settings(NO_AT)!r})
        out({{"changed": changed(before, snapshot(["my_app"])), "reached": [reached(r) for r in target.reached]}})
    ''', paths=[tmp_path])
    assert said["changed"] == []
    assert said["reached"] == [
        {"tool": tool, "how": "not seen", "at": None, "places": [], "held_elsewhere": said["reached"][n]["held_elsewhere"]}
        for n, tool in enumerate(("lookup_order", "check_policy", "issue_refund"))]


def test_wrap_at_load_of_no_place_does_nothing(tmp_path: Path) -> None:
    spec_project(tmp_path)
    said = child('''
        import my_app.agents
        from poisson_break.apply import wrap_at_load
        before = snapshot(["my_app"])
        got = wrap_at_load({})
        out({"got": list(got), "changed": changed(before, snapshot(["my_app"]))})
    ''', paths=[tmp_path])
    assert said == {"got": [], "changed": []}


# ---------------------------------------------------------------------------
# BK15.9: every module-level holder gets the one wrapper
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def holders_loaded() -> dict[str, Any]:
    """The holders module loaded once in a child: the `id` at every place before and after, what `reached` says, and a
    run that calls `lookup_order` through each of its five places."""
    return child(HOLDERS_IMPORTED + f'''
before = slots(["{HOLDERS}"])
target = load({HOLDERS_TEXT!r})
after = slots(["{HOLDERS}"])
from poisson_break.apply import Session
from poisson_break.changes import Condition
tools_module.EXECUTED.clear()
s = Session(Condition(changes=()), seed=0, tools={{"lookup_order": "read", "check_policy": "read"}})
with s:
    tools_module.lookup_order("q1")
    agent_module.lookup_order("q2")
    package.lookup_order("q3")
    agent_module.TOOLS["lookup_order"]("q4")
    agent_module.TOOL_LIST[0]("q5")
out({{"before": before, "after": after, "original": original,
      "reached": {{r.tool: reached(r) for r in target.reached}},
      "calls": [[c.tool, c.call, c.real_ran] for c in s.calls],
      "executed": [list(e) for e in tools_module.EXECUTED]}})
''')


def test_the_five_holders_of_a_tool_hold_one_and_the_same_new_object(holders_loaded: dict[str, Any]) -> None:
    after, original = holders_loaded["after"], holders_loaded["original"]
    held = {after[place] for place in LOOKUP_PLACES}
    assert len(held) == 1, {place: after[place] for place in LOOKUP_PLACES}
    assert held != {original["lookup_order"]}, "nothing was replaced"
    checked = {after[place] for place in CHECK_PLACES}
    assert len(checked) == 1 and checked != {original["check_policy"]}
    assert held != checked


def test_a_call_through_each_holder_reaches_the_run_and_takes_one_call_number(holders_loaded: dict[str, Any]) -> None:
    assert holders_loaded["calls"] == [["lookup_order", n, True] for n in range(1, 6)]
    assert [e[0] for e in holders_loaded["executed"]] == ["lookup_order"] * 5


def test_reached_names_each_place_replaced_in_text_order(holders_loaded: dict[str, Any]) -> None:
    lookup, check = holders_loaded["reached"]["lookup_order"], holders_loaded["reached"]["check_policy"]
    assert (lookup["how"], lookup["at"]) == ("at load", f"{HOLDERS}.tools:lookup_order")
    assert lookup["places"] == list(LOOKUP_PLACES)
    assert (check["how"], check["at"]) == ("at load", f"{HOLDERS}.tools:check_policy")
    assert check["places"] == list(CHECK_PLACES)


def test_reached_has_a_line_for_each_tool_that_is_not_off_in_the_file_s_order(holders_loaded: dict[str, Any]) -> None:
    """Spec §12.4: `RolloutTarget.reached` is one `Reached` for each `[tools]` line that is not `off`, in the file's
    order. `issue_refund` has no `at` and no `wrap` line ran for it: `not seen`."""
    assert list(holders_loaded["reached"]) == ["lookup_order", "check_policy", "issue_refund"]
    refund = holders_loaded["reached"]["issue_refund"]
    assert (refund["how"], refund["at"], refund["places"]) == ("not seen", None, [])


# ---------------------------------------------------------------------------
# BK15.10: what cannot be replaced is named
# ---------------------------------------------------------------------------


def test_the_closure_the_partial_the_tuple_and_the_object_are_each_named(holders_loaded: dict[str, Any]) -> None:
    """Spec §12.4: `kind` is `closure`, `partial`, `container` or `object`; `where` is the function a closure belongs to
    as `module:qualified.name`, the module-level name that holds a partial or a container, or none. The closure's
    function is `make_agent`'s inner one, so its `where` is `make_agent`'s, as `doctor`'s note names it, or the inner
    function's qualified name under it."""
    held = holders_loaded["reached"]["lookup_order"]["held_elsewhere"]
    assert held is not None
    assert sorted(h["kind"] for h in held) == ["closure", "container", "object", "partial"], held
    where = {h["kind"]: h["where"] for h in held}
    assert where["partial"] == f"{HOLDERS}.agent:FIND"
    assert where["container"] == f"{HOLDERS}.agent:HELP"
    assert where["object"] is None
    assert where["closure"] == f"{HOLDERS}.agent:make_agent" or where["closure"].startswith(
        f"{HOLDERS}.agent:make_agent."), where["closure"]


def test_a_tool_with_no_such_holder_has_none(holders_loaded: dict[str, Any]) -> None:
    assert holders_loaded["reached"]["check_policy"]["held_elsewhere"] == []


def test_a_holder_that_cannot_be_replaced_still_holds_the_function_and_refuses_nothing(
        holders_loaded: dict[str, Any]) -> None:
    """The load went through (BK15.10: none of them refuses anything), and the four holders were left as they were:
    a call through one of them does not pass through Break, which is why `doctor` names them."""
    said = child(HOLDERS_IMPORTED + f'''
def in_cells():
    return [id(cell.cell_contents) for cell in agent_module.AGENT.__closure__ or ()]
closure_before = in_cells()
target = load({HOLDERS_TEXT!r})
out({{"original": original["lookup_order"], "partial": id(agent_module.FIND.func), "tuple": id(agent_module.HELP[0]),
      "object": id(agent_module.BOX.lookup), "closure": in_cells(), "closure_before": closure_before}})
''')
    assert said["original"] in said["closure_before"]
    assert said["original"] in said["closure"]
    assert {said[k] for k in ("partial", "tuple", "object")} == {said["original"]}


def test_where_the_interpreter_cannot_list_what_refers_to_a_function_held_elsewhere_is_none() -> None:
    """Spec §12.11, question 4: Python's own list of what refers to a function, `gc.get_referrers`. Where there is none
    to ask, `held_elsewhere` is `None` (the check was not made), not empty (nothing found), and the load still goes."""
    said = child(HOLDERS_IMPORTED + f'''
del gc.get_referrers
target = load({HOLDERS_TEXT!r})
out({{r.tool: reached(r) for r in target.reached}})
''')
    assert said["lookup_order"]["held_elsewhere"] is None
    assert said["lookup_order"]["places"] == list(LOOKUP_PLACES)


# ---------------------------------------------------------------------------
# BK15.11: only what is named is touched
# ---------------------------------------------------------------------------


def test_across_a_load_the_only_differences_anywhere_are_the_places(holders_loaded: dict[str, Any]) -> None:
    """In the holders' own modules: every name, dict value and list item that changed is one of the places of the
    tools with an `at`, and every one of those changed."""
    before, after = holders_loaded["before"], holders_loaded["after"]
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    assert changed == set(LOOKUP_PLACES) | set(CHECK_PLACES)


def test_across_a_load_no_function_changes_in_any_other_module() -> None:
    """In every loaded module but Break's own and the child's script: no name, dict value or list item that held a
    function, or holds one now, changed, but at the places."""
    said = child(HOLDERS_IMPORTED + f'''
import poisson_break.hunt
before = snapshot()
target = load({HOLDERS_TEXT!r})
out(changed(before, snapshot()))
''')
    assert set(said) == set(LOOKUP_PLACES) | set(CHECK_PLACES)


def test_a_function_with_no_line_a_tool_with_no_at_and_an_off_tool_are_what_they_were(
        holders_loaded: dict[str, Any]) -> None:
    after, original = holders_loaded["after"], holders_loaded["original"]
    for name, places in (("issue_refund", ("TOOLS[issue_refund]", "TOOL_LIST[2]", "issue_refund")),
                         ("send_email", ("TOOLS[send_email]", "TOOL_LIST[3]", "send_email")),
                         ("cancel_order", ("TOOLS[cancel_order]", "TOOL_LIST[4]", "cancel_order"))):
        assert after[f"{HOLDERS}.tools:{name}"] == original[name], name
        for place in places:
            assert after[f"{HOLDERS}.agent:{place}"] == original[name], (name, place)


def test_the_tool_is_the_function_by_identity_not_by_its_name(tmp_path: Path) -> None:
    """Spec §12.4: "is the function" is identity. A second function named `lookup_order`, in another module, is not
    the tool, and is left as it was."""
    spec_project(tmp_path, other='def lookup_order(query):\n    return "another"\n')
    said = child(f'''
        import my_app.agents, my_app.other
        kept = id(my_app.other.lookup_order)
        load({spec_settings()!r})
        out({{"kept": kept, "now": id(my_app.other.lookup_order),
              "replaced": id(my_app.agents.lookup_order) == id(my_app.tools.lookup_order)}})
    ''', paths=[tmp_path])
    assert said["now"] == said["kept"]
    assert said["replaced"] is True


def test_a_module_imported_later_takes_the_wrapper(tmp_path: Path) -> None:
    """Spec §12.4: a module imported after the load, which takes the tool from a module Break replaced it in, holds the
    wrapper, and a call through it reaches the run."""
    spec_project(tmp_path, late="from my_app.tools import lookup_order\n")
    said = child(f'''
        import my_app.agents
        load({spec_settings()!r})
        import my_app.late
        from poisson_break.apply import Session
        from poisson_break.changes import parse
        s = Session(parse("tool:lookup_order#1=empty"), seed=0, tools={{"lookup_order": "read"}})
        with s:
            got = my_app.late.lookup_order("7")
        out({{"same": id(my_app.late.lookup_order) == id(my_app.tools.lookup_order), "got": got,
              "calls": [[c.tool, c.call, c.change] for c in s.calls]}})
    ''', paths=[tmp_path])
    assert said == {"same": True, "got": "", "calls": [["lookup_order", 1, "tool:lookup_order#1=empty"]]}


# ---------------------------------------------------------------------------
# BK15.12: outside a run the tool is itself
# ---------------------------------------------------------------------------


def test_outside_a_run_the_tool_is_itself(tmp_path: Path) -> None:
    spec_project(tmp_path)
    said = child(f'''
        import my_app.agents
        tools = sys.modules["my_app.tools"]
        def described(fn):
            return {{"name": fn.__name__, "qualname": fn.__qualname__, "doc": fn.__doc__,
                     "signature": str(inspect.signature(fn))}}
        def once():
            before = described(tools.lookup_order)
            first = id(tools.lookup_order)
            load({spec_settings()!r})
            tools.CALLS.clear()
            got = sys.modules["my_app.agents"].lookup_order("7")
            ran = list(tools.CALLS)
            caught = refusal(lambda: tools.lookup_order("missing"))
            return {{"before": before, "after": described(tools.lookup_order), "got": got, "ran": ran,
                     "caught": caught, "replaced": id(tools.lookup_order) != first}}
        out(once())
    ''', paths=[tmp_path])
    assert said["replaced"] is True
    assert said["after"] == said["before"]
    assert said["got"] == "Order 7 shipped on Tuesday."
    assert said["ran"] == [["lookup_order", "7"]]
    assert said["caught"]["type"] == "LookupError" and said["caught"]["message"] == "there is no order missing"


# ---------------------------------------------------------------------------
# BK15.14: loading twice is loading once
# ---------------------------------------------------------------------------


def test_loading_twice_is_loading_once(tmp_path: Path) -> None:
    spec_project(tmp_path)
    said = child(f'''
        import my_app.agents
        first = load({spec_settings()!r})
        once = slots(["my_app"])
        again = refusal(lambda: load({spec_settings()!r}))
        second = load({spec_settings()!r})
        twice = slots(["my_app"])
        from poisson_break.apply import Session, wrap_at_load
        direct = refusal(lambda: wrap_at_load({{"lookup_order": "my_app.tools:lookup_order"}}))
        thrice = slots(["my_app"])
        from poisson_break.changes import Condition
        s = Session(Condition(changes=()), seed=0, tools={{"lookup_order": "read"}})
        with s:
            sys.modules["my_app.agents"].lookup_order("7")
        out({{"again": again, "direct": direct, "same": once == twice == thrice,
              "first": [reached(r) for r in first.reached], "second": [reached(r) for r in second.reached],
              "calls": [[c.tool, c.call] for c in s.calls]}})
    ''', paths=[tmp_path])
    assert said["again"] is None and said["direct"] is None
    assert said["same"] is True
    assert said["second"] == said["first"]
    assert said["calls"] == [["lookup_order", 1]]


# ---------------------------------------------------------------------------
# how each tool is reached
# ---------------------------------------------------------------------------

WRAPPING_AGENTS = '''\
from poisson_prove import Episode

from poisson_break.apply import wrap
from my_app.tools import check_policy, issue_refund, send_email
from my_app.tools import lookup_order as _lookup_order

lookup_order = wrap("lookup_order", _lookup_order)


def refund_agent(cfg, seed):
    return Episode(outcome="done", t=0.0, horizon=1.0, meta={"reply": lookup_order(cfg["input"])})
'''


def test_reached_says_how_each_tool_is_reached(tmp_path: Path) -> None:
    """Spec §12.4: `at load` for a line with `at`; `wrap` for a line whose name a `wrap` line ran under, in this
    process, by the time the agent is loaded, at import or before; `not seen` for a line with neither. An `off` line
    has none. A tool reached by `wrap` has no `at` and no place."""
    spec_project(tmp_path, agents=WRAPPING_AGENTS)
    tools = {"lookup_order": "read", "check_policy": "read",
             "issue_refund": {"class": "write", "stand_in": "my_app.fakes:refund", "at": "my_app.tools:issue_refund"},
             "send_email": "off", "send_sms": "read"}
    said = child(f'''
        from poisson_break.apply import wrap
        wrap("check_policy", lambda topic: topic)
        target = load({spec_settings(tools)!r})
        out([reached(r) for r in target.reached])
    ''', paths=[tmp_path])
    got = {r["tool"]: (r["how"], r["at"], r["places"]) for r in said}
    assert list(got) == ["lookup_order", "check_policy", "issue_refund", "send_sms"]
    assert got["lookup_order"] == ("wrap", None, [])
    assert got["check_policy"] == ("wrap", None, [])
    assert got["issue_refund"][:2] == ("at load", "my_app.tools:issue_refund")
    assert got["issue_refund"][2] == ["my_app.agents:issue_refund", "my_app.tools:issue_refund"]
    assert got["send_sms"] == ("not seen", None, [])


def test_wrap_at_load_hands_back_one_reached_a_place_in_order(tmp_path: Path) -> None:
    spec_project(tmp_path)
    said = child('''
        import my_app.agents
        from poisson_break.apply import wrap_at_load
        got = wrap_at_load({"check_policy": "my_app.tools:check_policy", "find": "my_app.tools:lookup_order"})
        out({"got": [reached(r) for r in got], "type": type(got).__name__})
    ''', paths=[tmp_path])
    assert said["type"] == "tuple"
    assert [(r["tool"], r["how"], r["at"]) for r in said["got"]] == [
        ("check_policy", "at load", "my_app.tools:check_policy"), ("find", "at load", "my_app.tools:lookup_order")]
    assert said["got"][1]["places"] == ["my_app.agents:lookup_order", "my_app.tools:lookup_order"]


def test_a_tool_named_otherwise_than_its_function_reaches_the_run_under_its_own_name(tmp_path: Path) -> None:
    """Spec §12.3: `find = { class = "read", at = "my_app.tools:lookup_order" }` calls it `find` in every condition."""
    spec_project(tmp_path)
    tools = {"find": {"class": "read", "at": "my_app.tools:lookup_order"}, "check_policy": "read"}
    said = child(f'''
        import my_app.agents
        load({spec_settings(tools)!r})
        from poisson_break.apply import Session
        from poisson_break.changes import parse
        s = Session(parse("tool:find#1=empty"), seed=0, tools={{"find": "read", "check_policy": "read"}})
        with s:
            got = sys.modules["my_app.agents"].lookup_order("7")
        out({{"got": got, "calls": [[c.tool, c.call, c.change] for c in s.calls]}})
    ''', paths=[tmp_path])
    assert said == {"got": "", "calls": [["find", 1, "tool:find#1=empty"]]}


def test_the_replacement_lasts_and_the_original_is_not_put_back(tmp_path: Path) -> None:
    """Spec §12.11, question 20: after a run, and after the session is closed, the module still holds the wrapper."""
    spec_project(tmp_path)
    said = child(f'''
        import my_app.agents
        first = id(sys.modules["my_app.tools"].lookup_order)
        target = load({spec_settings()!r})
        wrapped = id(sys.modules["my_app.tools"].lookup_order)
        from poisson_break.apply import Session
        from poisson_break.changes import Condition
        with Session(Condition(changes=()), seed=0, tools={{"lookup_order": "read", "check_policy": "read"}}):
            sys.modules["my_app.agents"].refund_agent({{"input": "7"}}, 0)
        out({{"first": first, "wrapped": wrapped, "now": id(sys.modules["my_app.tools"].lookup_order)}})
    ''', paths=[tmp_path])
    assert said["wrapped"] != said["first"] and said["now"] == said["wrapped"]


# ---------------------------------------------------------------------------
# BK15.15: threads and nested runs are wrap's
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def threads(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """The tests of plan BK2.14 on threads and nested runs (`tests/test_apply_wrap.py`), on a tool wrapped at load."""
    root = spec_project(tmp_path_factory.mktemp("threads"))
    return child(f'''
        import threading
        from concurrent.futures import ThreadPoolExecutor
        import my_app.agents
        load({spec_settings()!r})
        from poisson_break.apply import InstrumentError, Session
        from poisson_break.changes import parse
        lookup = sys.modules["my_app.agents"].lookup_order
        tools = sys.modules["my_app.tools"]
        lines = {{"lookup_order": "read", "check_policy": "read"}}
        said = {{}}

        s = Session(parse("tool:lookup_order#*=empty"), seed=0, tools=lines)
        with s, ThreadPoolExecutor(max_workers=3) as pool:
            got = list(pool.map(lambda n: lookup(str(n)), range(6)))
        said["pool"] = {{"got": got, "numbers": sorted(c.call for c in s.calls), "stopped": s.stopped is not None}}

        ready = threading.Barrier(2)
        def run(text, kept):
            one = Session(parse(text), seed=0, tools=lines)
            with one:
                ready.wait(timeout=5)
                kept.extend(lookup(str(n)) for n in range(4))
                ready.wait(timeout=5)
            kept.append([c.call for c in one.calls])
        a, b = [], []
        both = [threading.Thread(target=run, args=("tool:lookup_order#*=empty", a)),
                threading.Thread(target=run, args=("", b))]
        for t in both: t.start()
        for t in both: t.join()
        said["two threads"] = {{"a": a, "b": b}}

        opened, finish = threading.Event(), threading.Event()
        def other_run():
            with Session(parse(""), seed=0, tools=lines):
                opened.set()
                finish.wait(timeout=10)
        other = threading.Thread(target=other_run)
        other.start()
        opened.wait(timeout=10)
        caught = []
        tools.CALLS.clear()
        try:
            with Session(parse(""), seed=0, tools=lines):
                def stray():
                    try:
                        lookup("9")
                    except BaseException as wrong:
                        caught.append(wrong)
                t = threading.Thread(target=stray)
                t.start()
                t.join()
        finally:
            finish.set()
            other.join()
        said["stray"] = {{"caught": [type(w).__name__ for w in caught],
                          "instrument": all(isinstance(w, InstrumentError) for w in caught),
                          "names": all("lookup_order" in str(w) for w in caught), "ran": list(tools.CALLS)}}

        outer = Session(parse("tool:lookup_order#2=empty"), seed=0, tools=lines)
        inner = Session(parse("tool:lookup_order#1=empty"), seed=0, tools=lines)
        with outer:
            first = lookup("1")
            with inner:
                nested = lookup("2")
            last = lookup("3")
        said["nested"] = {{"got": [first, nested, last], "outer": [[c.call, c.change] for c in outer.calls],
                           "inner": [[c.call, c.change] for c in inner.calls]}}
        out(said)
    ''', paths=[root])


def test_a_call_from_a_thread_the_agent_started_reaches_its_run(threads: dict[str, Any]) -> None:
    assert threads["pool"] == {"got": [""] * 6, "numbers": [1, 2, 3, 4, 5, 6], "stopped": False}


def test_two_runs_on_two_threads_keep_their_own_calls(threads: dict[str, Any]) -> None:
    a, b = threads["two threads"]["a"], threads["two threads"]["b"]
    assert a[:4] == [""] * 4 and a[4] == [1, 2, 3, 4]
    assert b[:4] == [f"Order {n} shipped on Tuesday." for n in range(4)] and b[4] == [1, 2, 3, 4]


def test_a_call_that_cannot_be_told_from_two_open_runs_is_an_instrument_error_naming_the_tool(
        threads: dict[str, Any]) -> None:
    stray = threads["stray"]
    assert len(stray["caught"]) == 1 and stray["instrument"] and stray["names"], stray
    assert stray["ran"] == []


def test_nested_runs_reach_the_innermost_and_closing_it_gives_the_outer_back(threads: dict[str, Any]) -> None:
    nested = threads["nested"]
    assert nested["got"] == ["Order 1 shipped on Tuesday.", "", ""]
    assert nested["inner"] == [[1, "tool:lookup_order#1=empty"]]
    assert nested["outer"] == [[1, None], [2, "tool:lookup_order#2=empty"]]


# ---------------------------------------------------------------------------
# BK15.18: async is refused by wrap's own check
# ---------------------------------------------------------------------------

#: Each a module `my_app.v<n>` holding `fn`: what `wrap` refuses as async, then what it takes.
VARIANTS = {
    "an async def": "async def fn(query):\n    return query\n",
    "an async generator function": "async def fn(query):\n    yield query\n",
    "an object whose __call__ is async def": (
        "class _Lookup:\n    async def __call__(self, query):\n        return query\n\nfn = _Lookup()\n"),
    "a partial of an async def": (
        "import functools\n\nasync def _fn(query, detail):\n    return query\n\nfn = functools.partial(_fn, detail=1)\n"),
    "a def": "def fn(query):\n    return query\n",
    "a generator function": "def fn(query):\n    yield query\n",
    "a partial of a def": (
        "import functools\n\ndef _fn(query, detail):\n    return query\n\nfn = functools.partial(_fn, detail=1)\n"),
}
ASYNC = ["an async def", "an async generator function", "an object whose __call__ is async def"]
INLINE_AGENTS = '''\
from poisson_prove import Episode


def refund_agent(cfg, seed):
    return Episode(outcome="done", t=0.0, horizon=1.0, meta={"reply": "done"})
'''


@pytest.fixture(scope="module")
def async_checked(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """For each variant: what loading a line `at` it does, and what `wrap` does with a fresh copy of it."""
    root = tmp_path_factory.mktemp("async")
    files = {"agents": INLINE_AGENTS, "tools": None}
    for n, source in enumerate(VARIANTS.values()):
        files[f"v{n}"] = source
        files[f"w{n}"] = source
    spec_project(root, **files)
    texts = [spec_settings({f"tool_{n}": {"class": "read", "at": f"my_app.v{n}:fn"}}) for n in range(len(VARIANTS))]
    return child(f'''
        from poisson_break.apply import wrap
        said = []
        for n, text in enumerate({texts!r}):
            at_load = refusal(lambda: load(text))
            copy = importlib.import_module(f"my_app.w{{n}}")
            by_wrap = refusal(lambda: wrap(f"probe_{{n}}", copy.fn))
            said.append({{"at_load": at_load, "wrap": by_wrap}})
        out(said)
    ''', paths=[root])


@pytest.mark.parametrize("variant", list(VARIANTS))
def test_loading_refuses_exactly_what_wrap_refuses_as_async(async_checked: list[Any], variant: str) -> None:
    """BK15.18, spec §12.7 way 7: each thing `wrap` refuses as async is refused at load, as `ToolRefused` naming the
    tool, and what `wrap` takes is taken: the one check, so the day `wrap` takes one, a place does too."""
    n = list(VARIANTS).index(variant)
    said = async_checked[n]
    if variant in ASYNC:
        assert said["wrap"] is not None and said["wrap"]["type"] == "ToolRefused", said
    assert (said["at_load"] is None) == (said["wrap"] is None), said
    if said["at_load"] is not None:
        assert said["at_load"]["type"] == "ToolRefused" and said["at_load"]["tool"] == f"tool_{n}", said
        assert f"my_app.v{n}:fn" in said["at_load"]["message"]


# ---------------------------------------------------------------------------
# BK15.19: wrap refuses a wrapper Break made at load
# ---------------------------------------------------------------------------


def test_wrap_refuses_a_wrapper_made_at_load_naming_the_tool_and_takes_anything_else(tmp_path: Path) -> None:
    """Spec §12.4: the call would pass through the run twice and take two call numbers. Under the tool's own name and
    under another, `wrap` on the wrapper is `ToolRefused` naming the tool; on a plain function, and on what `wrap`
    itself made, it is as on `main`; and a call of the tool in a run still takes one number."""
    spec_project(tmp_path)
    said = child(f'''
        import my_app.agents
        load({spec_settings()!r})
        from poisson_break.apply import Session, wrap
        from poisson_break.changes import Condition
        tools = sys.modules["my_app.tools"]
        same = refusal(lambda: wrap("lookup_order", tools.lookup_order))
        other = refusal(lambda: wrap("find_order", tools.lookup_order))
        plain = wrap("plain_tool", lambda query: f"plain {{query}}")
        twice = refusal(lambda: wrap("outer_tool", wrap("inner_tool", lambda query: query)))
        s = Session(Condition(changes=()), seed=0, tools={{"lookup_order": "read"}})
        with s:
            sys.modules["my_app.agents"].lookup_order("7")
        out({{"same": same, "other": other, "plain": plain("7"), "twice": twice,
              "calls": [[c.tool, c.call] for c in s.calls]}})
    ''', paths=[tmp_path])
    assert said["same"]["type"] == "ToolRefused" and said["same"]["tool"] == "lookup_order", said
    assert "lookup_order" in said["same"]["message"]
    assert said["other"]["type"] == "ToolRefused" and said["other"]["tool"] in ("lookup_order", "find_order"), said
    assert said["plain"] == "plain 7"
    assert said["twice"] is None
    assert said["calls"] == [["lookup_order", 1]]
