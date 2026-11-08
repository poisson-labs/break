"""A stop that names several tools nobody classed: one `init` line classing all of them off.

Taylor's yes to BK8 point 59 (2026-11-08). The runs module's `tools` stop carries every tool the control saw called
that `[tools]` does not class, and there can be more than one. Point 44's line classes one tool; point 51's test meets
one tool only. With several: the `stopped` line names them all (spec §3.6), and the first `next:` is one `init` line,
the settings' own equivalent command with a `--tool '<tool> = "off"'` for each named tool, in the order the stop
names them, then `--yes --force` (points 44 and 45), and the resume line comes second. The `init` line, run as
printed, writes the settings back with each of those tools `off` and nothing else changed.

The desk (`tests/commands_targets.py`) calls `lookup_order` and then `check_policy` on every run. The control stage
ran with both classed; then both lose their lines in `[tools]`, so the finished control names both when it is read
again: by `hunt --hunt NAME`, taking the hunt up again, and by `confirm`, reading the control it confirms against. A
stage that runs meets such a tool as the applier's own refusal, at the first call, one tool at a time, which point 51's
test holds.
"""

from __future__ import annotations

import json
import shlex
import tomllib
from dataclasses import fields
from pathlib import Path

import pytest

from tests.commands_lines import classing_nexts
from tests.commands_support import (
    CODES,
    MIXED,
    MIXED_CANDIDATES,
    MIXED_SETTINGS,
    PROG,
    Project,
    cli,
    files_under,
    hunt_names,
    nexts,
    prepared,
    project,
)
from tests.look_support import strip

TOOLS = ("lookup_order", "check_policy")


def without_both_tools(proj: Project) -> None:
    text = proj.settings.read_text(encoding="utf-8")
    for tool in TOOLS:
        line = f'"{tool}" = "read"\n'
        assert text.count(line) == 1, text
        text = text.replace(line, "")
    proj.settings.write_text(text, encoding="utf-8")


def tool_lines_of(command: str) -> list[str]:
    """The key of each `--tool` line of an `init` command, in the command's order."""
    words = shlex.split(command)
    assert words[:2] == [PROG, "init"], command
    keys = []
    for i, word in enumerate(words[:-1]):
        if word == "--tool":
            (key,) = tomllib.loads(words[i + 1])
            keys.append(key)
    return keys


def named_in_order(line: str, tools: tuple[str, ...]) -> list[str]:
    """`tools` as `line` names them, in the order they stand in it; a tool it does not name is left out."""
    at = {tool: line.find(tool) for tool in tools}
    return [tool for tool, where in sorted(at.items(), key=lambda item: item[1]) if where >= 0]


def the_next_writes_the_tools_in_as_off(proj: Project, command: str, tools: tuple[str, ...]) -> None:
    """Points 44 and 59: `command`, run as printed in the project, exits 0 and writes a `break.toml` that reads back
    equal to the settings that were there with one more line in `[tools]` for each of `tools`, classed `off`: every
    other table and key as it was. Every other file of the project is as it was, and no file is added."""
    from poisson_break.settings import loads

    text = proj.settings.read_text(encoding="utf-8")
    assert "\n[tools]\n" in text
    added = "".join(f'{json.dumps(tool)} = "off"\n' for tool in tools)
    wanted = loads(text.replace("\n[tools]\n", f"\n[tools]\n{added}", 1))
    others = {name: data for name, data in files_under(proj.folder).items() if name != "break.toml"}
    words = shlex.split(command)
    assert words[:2] == [PROG, "init"], command
    ran = cli(proj, *words[1:])
    assert ran.exit == CODES["done"], ran
    written = loads(proj.settings.read_text(encoding="utf-8"))
    assert {t.name: t for t in written.tools} == {t.name: t for t in wanted.tools}
    assert {t.name: t.tool_class for t in written.tools} == dict.fromkeys(tools, "off")
    for field in fields(wanted):
        if field.name != "tools":
            assert getattr(written, field.name) == getattr(wanted, field.name), field.name
    assert {name: data for name, data in files_under(proj.folder).items() if name != "break.toml"} == others


@pytest.mark.parametrize("verb", ["hunt", "confirm"])
def test_a_stop_naming_several_tools_nobody_classed_prints_one_init_line_classing_them_all_off(
        tmp_path: Path, verb: str) -> None:
    """Point 59: a hunt whose control stage ran, then both of the desk's tools lose their line in `[tools]`. Taken up
    again by `hunt --hunt NAME`, or confirmed, the stage stops, its `stopped` line names both tools, and exactly two
    `next:` lines follow: first one `init` command with a `--tool` line for each of the two, in the order the stop
    names them and no other `--tool` line, then the resume line. The `init` line, run as printed, writes the settings
    back with both tools `off` and nothing else changed."""
    proj = project(tmp_path, MIXED, **MIXED_SETTINGS)
    prepared(proj, MIXED_CANDIDATES)
    without_both_tools(proj)
    ran = cli(proj, verb, "--yes", *(["--hunt", "desk-1"] if verb == "hunt" else []))
    assert ran.exit not in (CODES["done"], CODES["usage"]), ran
    stop = [line for line in strip(ran.out).splitlines() if line.startswith("stopped  ")]
    assert len(stop) == 1, ran
    order = named_in_order(stop[0], TOOLS)
    assert sorted(order) == sorted(TOOLS), stop[0]  # spec §3.6: the one line names them all
    lines = nexts(ran)
    assert len(lines) == 2, lines
    assert classing_nexts(ran, TOOLS[0], lines[:1]) == lines[:1], lines
    assert classing_nexts(ran, TOOLS[1], lines[:1]) == lines[:1], lines
    assert tool_lines_of(lines[0]) == order, (lines[0], order)
    (name,) = hunt_names(proj)
    assert shlex.split(lines[1]) == [PROG, verb, "--hunt", name], lines
    the_next_writes_the_tools_in_as_off(proj, lines[0], tuple(order))
