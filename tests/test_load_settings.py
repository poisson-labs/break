"""The settings file's `at`: where a tool is, for Break to wrap it when it loads the agent (spec §12.3, §12.7 ways 8
and 9, §9.4).

Invariants held here (Break — Plan, the module that wraps tools at load; spec §12.8):
- BK15.20 A file with `at` lines reads, with an `at` whose module does not exist among them, since reading imports
          nothing; `dump` writes it back byte for byte; `--tool` carries an `at`; no flag is added (`INIT_FLAGS` is as
          on `main`); a `Session` made from a line with `at` behaves as one made from the line without.
- BK15.17, ways 8 and 9: `at` on an `off` line, and an `at` that is not a place Break can use, are the settings file's
          own refusals, on the tool's line.

Ruled 2026-11-19 (spec §12.11): the key is `at`, on the tool's own line, and no command gains a flag (question 2);
a name inside a class or an object is refused (question 5). Ruled 2026-11-20 (this module's Session A): a refusal's
test pins its kind, the tool and the facts it carries, never its words.

Nothing here loads an agent, so it runs in the test process: `at` is read and written, never followed.
"""

from __future__ import annotations

import importlib
import shlex
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.commands_support import settings_text
from tests.load_support import SPEC_ENTRY, SPEC_TOOLS, spec_settings


def settings() -> ModuleType:
    return importlib.import_module("poisson_break.settings")


def refused(text: str) -> Any:
    with pytest.raises(settings().SettingsError) as refusal:
        settings().loads(text)
    return refusal.value


def line_of(text: str, start: str) -> int:
    """The number of the file's one line that starts with `start`, counted from 1."""
    found = [n for n, row in enumerate(text.splitlines(), 1) if row.startswith(start)]
    assert len(found) == 1, (start, text)
    return found[0]


def tools_of(text: str) -> dict[str, Any]:
    return dict(tomllib.loads(text)["tools"])


# ---------------------------------------------------------------------------
# BK15.20: the file reads, imports nothing, and writes back byte for byte
# ---------------------------------------------------------------------------


def test_a_file_with_at_lines_reads_and_each_line_holds_its_at() -> None:
    """Spec §12.3's `[tools]`, word for word: the `at` of each line is its own, and a line with none holds none."""
    held = {tool.name: tool for tool in settings().loads(spec_settings()).tools}
    assert held["lookup_order"].at == "my_app.tools:lookup_order"
    assert held["check_policy"].at == "my_app.tools:check_policy"
    assert held["issue_refund"].at == "my_app.tools:issue_refund"
    assert held["issue_refund"].stand_in == "my_app.fakes:refund"
    assert held["send_email"].at is None
    plain = settings().loads(settings_text())
    assert [tool.at for tool in plain.tools] == [None, None]


def test_reading_imports_nothing_so_an_at_whose_module_is_nowhere_is_read() -> None:
    """Plan BK4.6, spec §12.3: reading checks the form only. A module that exists nowhere is read, and is not
    imported."""
    tools = {"lookup_order": {"class": "read", "at": "no_such_package_for_at.tools:lookup_order"}}
    held = settings().loads(spec_settings(tools))
    assert held.tools[0].at == "no_such_package_for_at.tools:lookup_order"
    assert not [name for name in sys.modules if name.startswith("no_such_package_for_at")]


def test_reading_does_not_import_a_module_that_is_there(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan BK4.6, spec §12.3: a module that could be imported, and that the `at` and the stand-in both name, is still
    not imported by reading the file, nor by `dump`, nor by the command `init` would print."""
    name = f"at_probe_{tmp_path.name.replace('-', '_')}"
    (tmp_path / f"{name}.py").write_text("def lookup_order(query):\n    return query\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    tools = {"lookup_order": {"class": "write", "stand_in": f"{name}:lookup_order", "at": f"{name}:lookup_order"}}
    held = settings().loads(spec_settings(tools))
    settings().dump(held)
    settings().equivalent_init_command(held, prog="poisson-break")
    assert held.tools[0].at == f"{name}:lookup_order"
    assert name not in sys.modules


def test_the_tool_s_name_need_not_be_the_function_s() -> None:
    """Spec §12.3: `find = { class = "read", at = "my_app.tools:lookup_order" }` is the tool `find`."""
    tools = {"find": {"class": "read", "at": "my_app.tools:lookup_order"}}
    (tool,) = settings().loads(spec_settings(tools)).tools
    assert (tool.name, tool.at) == ("find", "my_app.tools:lookup_order")


@pytest.mark.parametrize(("line", "written"), [
    ({"class": "read", "at": "my_app.tools:lookup_order"},
     'lookup_order = { class = "read", at = "my_app.tools:lookup_order" }'),
    ({"at": "my_app.tools:lookup_order", "class": "read"},
     'lookup_order = { class = "read", at = "my_app.tools:lookup_order" }'),
    ({"at": "my_app.tools:lookup_order", "class": "write", "repeatable": True},
     'lookup_order = { class = "write", repeatable = true, at = "my_app.tools:lookup_order" }'),
    ({"at": "my_app.tools:lookup_order", "stand_in": "my_app.fakes:refund", "class": "write"},
     'lookup_order = { class = "write", stand_in = "my_app.fakes:refund", at = "my_app.tools:lookup_order" }'),
    ({"class": "read", "repeatable": True, "stand_in": "my_app.fakes:look", "at": "my_app.tools:lookup_order"},
     'lookup_order = { class = "read", repeatable = true, stand_in = "my_app.fakes:look", '
     'at = "my_app.tools:lookup_order" }'),
], ids=["read", "read, at first", "write, repeatable", "write, stand-in", "every key"])
def test_dump_writes_at_last_on_the_line_and_the_file_reads_back_byte_for_byte(line: dict[str, Any],
                                                                              written: str) -> None:
    """Spec §12.3: `dump` writes `at` last, after `class`, `repeatable` and `stand_in`, whatever order the line was
    written in; a line with `at` is a table, since the class alone no longer says it all; and what `dump` writes reads
    back as the same settings and writes the same bytes again."""
    first = settings().loads(spec_settings({"lookup_order": line}))
    text = settings().dump(first)
    assert written in text.splitlines(), text
    again = settings().loads(text)
    assert again == first
    assert settings().dump(again) == text


def test_a_file_with_every_kind_of_line_writes_back_byte_for_byte() -> None:
    """Spec §12.3's four lines together, through `dump` and back: the same settings and the same bytes, and each line
    as the file holds it."""
    first = settings().loads(spec_settings())
    text = settings().dump(first)
    assert settings().loads(text) == first
    assert settings().dump(settings().loads(text)) == text
    assert tools_of(text) == SPEC_TOOLS


def test_settings_that_differ_only_in_an_at_differ() -> None:
    one = settings().loads(spec_settings({"lookup_order": {"class": "read", "at": "my_app.tools:lookup_order"}}))
    other = settings().loads(spec_settings({"lookup_order": {"class": "read", "at": "my_app.agents:lookup_order"}}))
    none = settings().loads(spec_settings({"lookup_order": "read"}))
    assert one != other and one != none and other != none


def test_at_does_not_make_a_write_tool_safe() -> None:
    """A `write` line still says how it is made safe to repeat; an `at` is where the tool is, not a way to be safe."""
    error = refused(spec_settings({"issue_refund": {"class": "write", "at": "my_app.tools:issue_refund"}}))
    assert error.key is not None and error.key.startswith("tools.issue_refund")
    assert error.key != "tools.issue_refund.at", "the at is the line's own key, and is not what is refused"
    safe = {"class": "write", "repeatable": True, "at": "my_app.tools:issue_refund"}
    assert settings().loads(spec_settings({"issue_refund": safe})).tools[0].at == "my_app.tools:issue_refund"


# ---------------------------------------------------------------------------
# BK15.20: init's --tool carries an at, and no flag is added
# ---------------------------------------------------------------------------

#: `INIT_FLAGS` as it is on `main` at 63bd637.
INIT_FLAGS_ON_MAIN = {
    "--kind": "target.kind", "--entry": "target.entry", "--cases": "target.cases", "--tool": "tools",
    "--checks": "fails.checks", "--outcomes": "fails.outcomes", "--own-check": "fails.own", "--also": "fails.also",
    "--never-call": "fails.never_call", "--retry-storm-after": "fails.retry_storm_after",
    "--max-tool-calls": "fails.max_tool_calls", "--max-tokens": "fails.max_tokens",
    "--run-seconds": "fails.run_seconds", "--vary-tools": "vary.tools", "--vary-inputs": "vary.inputs",
    "--vary-conversation": "vary.conversation", "--vary-model": "vary.model", "--max-call": "vary.max_call",
    "--env": "vary.env", "--strategy": "search.strategy", "--runs": "search.runs",
    "--control-repeats": "search.control_repeats", "--cases-per-condition": "search.cases_per_condition",
    "--seed": "search.seed", "--candidates": "confirm.candidates", "--confirm-repeats": "confirm.repeats",
    "--max-difference": "confirm.max_difference", "--q": "confirm.q", "--dollars": "limits.dollars",
    "--input-per-million": "limits.input_per_million", "--output-per-million": "limits.output_per_million",
    "--hours": "limits.hours", "--folder": "output.folder",
}


def test_no_flag_is_added() -> None:
    """Spec §12.3, question 2: no command gains a flag; `init`'s flags are the ones on `main`, in the same order."""
    assert list(settings().INIT_FLAGS.items()) == list(INIT_FLAGS_ON_MAIN.items())


SPEC_TOOL_FLAG = 'lookup_order = { class = "read", at = "my_app.tools:lookup_order" }'


def test_the_tool_flag_carries_an_at_as_the_file_writes_it() -> None:
    """Spec §12.3's own example of the flag: one line as the file writes it, `at` and all."""
    words = ["--kind", "rollout", "--entry", SPEC_ENTRY, "--cases", "cases.jsonl", "--tool", SPEC_TOOL_FLAG,
             "--tool", 'issue_refund = { class = "write", stand_in = "my_app.fakes:refund", '
                       'at = "my_app.tools:issue_refund" }',
             "--tool", 'send_email = "off"']
    made = settings().settings_from_init_args(words)
    held = {tool.name: tool.at for tool in made.tools}
    assert held == {"lookup_order": "my_app.tools:lookup_order", "issue_refund": "my_app.tools:issue_refund",
                    "send_email": None}
    assert SPEC_TOOL_FLAG in settings().dump(made).splitlines()


def test_the_command_that_writes_the_same_file_carries_each_at() -> None:
    """The one `init` command for settings with `at` lines, read back as `init` reads its words, is the same settings."""
    first = settings().loads(spec_settings())
    words = shlex.split(settings().equivalent_init_command(first, prog="poisson-break"))
    assert words[:2] == ["poisson-break", "init"]
    assert settings().settings_from_init_args(words[2:]) == first


# ---------------------------------------------------------------------------
# BK15.20: a Session takes a line that holds at, and reads nothing from it
# ---------------------------------------------------------------------------


def apply() -> ModuleType:
    return importlib.import_module("poisson_break.apply")


def run_of(lines: dict[str, Any], condition: str, calls: int = 3) -> tuple[list[Any], Any, Any]:
    """What a session over `lines` hands back for `calls` calls of `lookup_order`, and its record."""
    from poisson_break.changes import parse

    s = apply().Session(parse(condition), seed=7, tools=lines)
    seen = []
    for n in range(calls):
        try:
            seen.append(("returned", s.call("lookup_order", {"query": str(n)}, lambda n=n: f"order {n}")))
        except apply().ToolFailure as failure:
            seen.append(("raised", type(failure).__name__, failure.kind, failure.message))
    return seen, s.calls, s.applied


@pytest.mark.parametrize(("line", "condition"), [
    ({"class": "read"}, "tool:lookup_order#2=error"),
    ({"class": "read"}, "tool:lookup_order#1=empty + tool:lookup_order#3=stale"),
    ({"class": "write", "repeatable": True}, "tool:lookup_order#1=lost_reply"),
    ({"class": "read"}, ""),
], ids=["read, error", "read, empty and stale", "write, lost reply", "control"])
def test_a_session_from_a_line_with_at_behaves_as_one_from_the_line_without(line: dict[str, Any],
                                                                             condition: str) -> None:
    """Spec §12.4: a `Session` takes a line that holds `at` and reads nothing from it, as it takes `repeatable` on a
    `read` line. The `at` names a module that is nowhere, so a session that tried to follow it would fail."""
    with_at = dict(line, at="no_such_package_for_at.tools:lookup_order")
    assert run_of({"lookup_order": with_at}, condition) == run_of({"lookup_order": line}, condition)
    assert not [name for name in sys.modules if name.startswith("no_such_package_for_at")]


@pytest.fixture
def stand_in() -> Iterator[ModuleType]:
    from tests.apply_support import stand_in_module

    yield from stand_in_module()


def test_a_session_from_a_stand_in_line_with_at_calls_the_stand_in(stand_in: ModuleType) -> None:
    from poisson_break.changes import parse

    line = {"class": "write", "stand_in": "tests.apply_support_standin:refund",
            "at": "no_such_package_for_at.tools:issue_refund"}
    s = apply().Session(parse(""), seed=7, tools={"issue_refund": line})
    ran: list[str] = []
    s.call("issue_refund", {"request": "r1"}, lambda: ran.append("real"))
    assert ran == []
    assert s.calls[0].real_ran is True
    assert stand_in.LOG == [{"request": "r1"}]


# ---------------------------------------------------------------------------
# BK15.17, way 8: at on an off line
# ---------------------------------------------------------------------------


def test_at_on_an_off_line_is_refused_on_its_line() -> None:
    """Spec §12.7, way 8: `error: break.toml: tools.send_email is off, so Break never touches it, and its line names a
    place to wrap it`. The settings file's own refusal, on the tool's line, naming the tool."""
    text = spec_settings({**SPEC_TOOLS, "send_email": {"class": "off", "at": "my_app.tools:send_email"}})
    error = refused(text)
    assert error.key is not None and error.key.startswith("tools.send_email")
    assert error.line == line_of(text, '"send_email"')
    assert "send_email" in str(error)


# ---------------------------------------------------------------------------
# BK15.17, way 9: an at that is not a place Break can use
# ---------------------------------------------------------------------------


def test_an_at_that_is_not_written_module_colon_name_is_refused_on_its_line() -> None:
    """Spec §12.7, way 9: `error: break.toml: tools.lookup_order.at is "my_app.tools.lookup_order", not an import path
    written module:name`. The key is the line's `at`, the line is the tool's, and the value is in the sentence."""
    text = spec_settings({"lookup_order": {"class": "read", "at": "my_app.tools.lookup_order"}})
    error = refused(text)
    assert error.key == "tools.lookup_order.at"
    assert error.line == line_of(text, '"lookup_order"')
    assert "my_app.tools.lookup_order" in str(error)


def test_an_at_inside_a_class_or_an_object_is_refused_naming_it() -> None:
    """Spec §12.7, way 9, and §12.11 question 5: `error: break.toml: tools.lookup.at is "my_app.tools:Orders.lookup", a
    name inside Orders; this version wraps a function a module holds by name`. Methods are left out of this version."""
    text = spec_settings({"lookup": {"class": "read", "at": "my_app.tools:Orders.lookup"}})
    error = refused(text)
    assert error.key == "tools.lookup.at"
    assert error.line == line_of(text, '"lookup"')
    assert "my_app.tools:Orders.lookup" in str(error) and "Orders" in str(error)


@pytest.mark.parametrize("at", ['""', '"my_app.tools:"', '":lookup_order"', '"my app.tools:lookup_order"',
                                '"my_app.tools:lookup order"', '"my_app..tools:lookup_order"', "3", "true",
                                '["my_app.tools:lookup_order"]', '{ module = "my_app.tools" }'],
                         ids=["empty", "no name", "no module", "a space in the module", "a space in the name",
                              "an empty part", "a number", "true", "a list", "a table"])
def test_an_at_of_any_other_form_is_refused_on_its_line(at: str) -> None:
    text = spec_settings({"lookup_order": {"class": "read"}}).replace(
        '"lookup_order" = { "class" = "read" }', f'"lookup_order" = {{ "class" = "read", "at" = {at} }}')
    assert f'"at" = {at}' in text
    good = text.replace(f'"at" = {at}', '"at" = "my_app.tools:lookup_order"')
    assert settings().loads(good).tools[0].at == "my_app.tools:lookup_order", "the same line with a place is read"
    error = refused(text)
    assert error.key == "tools.lookup_order.at"
    assert error.line == line_of(text, '"lookup_order"')


def test_a_misspelt_at_is_refused_as_any_misspelt_key_of_a_line_is() -> None:
    """`at` is now one of a line's keys, so the nearest key to a misspelling of it is `at`."""
    error = refused(spec_settings({"lookup_order": {"class": "read", "att": "my_app.tools:lookup_order"}}))
    assert error.key == "tools.lookup_order.att"
    assert error.suggestion is not None and error.suggestion.split(".")[-1] == "at"
