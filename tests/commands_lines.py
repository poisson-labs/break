"""What the tests of printed lines share: finding the `init` line that classes a tool, and running it as printed.

Point 44 (Taylor's yes, 2026-11-08): for a tool nobody classed, the line is the settings' own equivalent `init` command
plus that tool classed `off`; point 45: it runs exactly as printed; point 46: it states the conversation when a case has
turns. `doctor --run` prints it (`test_commands_doctor.py`), and so does a stage a tool nobody classed stopped (point
51, `test_commands_printed.py`).
"""

from __future__ import annotations

import json
import shlex
import tomllib
from dataclasses import fields
from typing import Any

from tests.commands_support import CODES, PROG, cli, files_under, nexts


def classing_nexts(ran: Any, tool: str, commands: list[str] | None = None) -> list[str]:
    """The `next:` commands that are `init` with a `--tool` line whose key is `tool`; `commands` in place of the printed
    `next:` lines, for a document under `--json`."""
    found = []
    for command in nexts(ran) if commands is None else commands:
        words = shlex.split(command)
        if words[:2] != [PROG, "init"]:
            continue
        lines = [words[i + 1] for i, w in enumerate(words[:-1]) if w == "--tool"]
        if any(list(tomllib.loads(line)) == [tool] for line in lines):
            found.append(command)
    return found


def the_next_writes_the_tool_in_as_off(proj: Any, command: str, tool: str) -> None:
    """Point 44: `command`, run as printed in the project, exits 0 and writes a `break.toml` that reads back equal to the
    settings that were there with one more line in `[tools]`, `tool` classed `off`: every other table and key as it was,
    every other tool's line as it was. Every other file of the project is as it was, and no file is added. The order of
    `[tools]`'s lines is not held."""
    from poisson_break.settings import loads

    text = proj.settings.read_text(encoding="utf-8")
    assert "\n[tools]\n" in text
    wanted = loads(text.replace("\n[tools]\n", f'\n[tools]\n{json.dumps(tool)} = "off"\n', 1))
    others = {name: data for name, data in files_under(proj.folder).items() if name != "break.toml"}
    words = shlex.split(command)
    assert words[:2] == [PROG, "init"], command
    ran = cli(proj, *words[1:])
    assert ran.exit == CODES["done"], ran
    written = loads(proj.settings.read_text(encoding="utf-8"))
    assert {t.name: t for t in written.tools} == {t.name: t for t in wanted.tools}
    for field in fields(wanted):
        if field.name != "tools":
            assert getattr(written, field.name) == getattr(wanted, field.name), field.name
    assert {name: data for name, data in files_under(proj.folder).items() if name != "break.toml"} == others


def states_the_conversation(command: str) -> bool:
    """Point 46: the command says the conversation's setting itself, `--vary-conversation` with a value."""
    words = shlex.split(command)
    return any(w == "--vary-conversation" for w in words[:-1]) or any(w.startswith("--vary-conversation=")
                                                                      for w in words)


__all__ = ["classing_nexts", "states_the_conversation", "the_next_writes_the_tool_in_as_off"]
