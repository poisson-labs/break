"""The README's first screen: install, `init`, `hunt`, `confirm`, in that order.

From Break — Plan, the release pass ("Builds"): a README whose first screen is install,
`init`, `hunt`, `confirm`. Read through the commands the README marks (`tests/release_docs.py`,
rules 1 to 4): of the README's marked commands that are Break's own (an install of the
requirement `poisson-break`, or `poisson-break VERB`), the first four are an install, `init`,
`hunt` and `confirm`, in that order, and no other marked command comes between the install and
`confirm`. The install is of the published name, so a README that still installs from the
checkout (`pip install .`) does not pass.

Taylor's rulings (2026-11-09, `evidence/bk11/open-points.md`):
- 11A-2: the first screen's `init` is `init --example NAME`, writing an example the README's
  reader has with the wheel, so the four run offline with no key.
- 11A-4: the four commands sit before the README's first `##` heading and within its first 40
  lines, and only the title, prose, and the two lines that make and enter a virtual environment
  (`python -m venv .venv`, `. .venv/bin/activate`) may come before the install.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from tests.conftest import REPO, run_command
from tests.release_docs import Command, blocks, break_verb, is_break_install, marked

SCREEN = 40
BEFORE_THE_INSTALL = ("python -m venv .venv", ". .venv/bin/activate")


def _readme_commands() -> list[Command]:
    commands, _ = marked()
    return [c for c in commands if c.file == "README.md" and c.kind == "sh"]


def _what(command: Command) -> str | None:
    if is_break_install(command):
        return "install"
    return break_verb(command)


def _screen() -> list[Command]:
    readme = _readme_commands()
    whats = [_what(c) for c in readme]
    assert "install" in whats and "confirm" in whats, whats
    return readme[whats.index("install"):whats.index("confirm") + 1]


def test_the_readme_first_four_break_commands_are_install_init_hunt_confirm() -> None:
    ours = [(c.line, _what(c)) for c in _readme_commands() if _what(c) is not None]
    assert [what for _, what in ours[:4]] == ["install", "init", "hunt", "confirm"], ours


def test_nothing_else_is_run_between_the_install_and_confirm() -> None:
    """The four read as one sequence: no `cd`, no other verb, no other install between them."""
    screen = _screen()
    assert [_what(c) or c.command for c in screen] == ["install", "init", "hunt", "confirm"]


def test_the_first_screen_init_writes_an_example_the_wheel_carries() -> None:
    """11A-2: `init --example NAME`, NAME one of the examples."""
    init = _screen()[1]
    words = shlex.split(init.command.replace("\\\n", " "))
    assert "--example" in words, init.command
    name = words[words.index("--example") + 1]
    assert (REPO / "examples" / name / "break.toml").is_file(), name


def test_the_first_screen_sits_before_the_first_heading_and_within_40_lines() -> None:
    """11A-4."""
    lines = (REPO / "README.md").read_text(encoding="utf-8").split("\n")
    headings = [n for n, line in enumerate(lines, 1) if line.startswith("## ")]
    last = _screen()[-1].line
    assert last <= SCREEN, f"confirm is on line {last}"
    assert not headings or last < headings[0], f"confirm is on line {last}, the first ## on {headings[0]}"


def test_only_the_title_prose_and_a_virtual_environment_come_before_the_install() -> None:
    """11A-4: before the install, one `#` title and prose; no other heading, and no block but the
    two lines that make and enter a virtual environment."""
    text = (REPO / "README.md").read_text(encoding="utf-8")
    install = _screen()[0]
    lines = text.split("\n")[:install.line - 1]
    assert lines and lines[0].startswith("# "), "the README opens with its title"
    assert [line for line in lines[1:] if line.startswith("#")] == [], "a heading before the install"
    before = [b for b in blocks(text, "README.md") if b.fence_line < install.line]
    for block in before:
        if block.fence_line < install.line <= block.fence_line + len(block.lines):
            shown = [line for line in block.lines[:install.line - block.fence_line - 1]
                     if line.strip() and not line.strip().startswith("#")]
        else:
            shown = [line for line in block.lines
                     if line.strip() and not line.strip().startswith("#")]
            assert block.info == "sh", f"a {block.info or 'bare'} block before the install"
        assert all(line.strip() in BEFORE_THE_INSTALL for line in shown), shown


# ---------------------------------------------------------------------------
# the sections after the first screen
# ---------------------------------------------------------------------------


def _sections() -> dict[str, str]:
    """Each `## ` section of the README by its heading, its text up to the next `## `."""
    found: dict[str, str] = {}
    heading = None
    for line in (REPO / "README.md").read_text(encoding="utf-8").split("\n"):
        if line.startswith("## "):
            heading = line[3:].strip()
            found[heading] = ""
        elif heading is not None:
            found[heading] += line + "\n"
    return found


HOW = "How Break changes a tool"


def test_how_break_changes_a_tool_comes_straight_after_the_first_screen() -> None:
    """A reader who has run the first screen with no key reads next how it ran: the first `##`
    section says how Break reaches the agent and its tools."""
    assert list(_sections())[0] == HOW, list(_sections())


def test_how_break_changes_a_tool_names_the_example_s_model_as_the_example_has_it() -> None:
    """The section says the example's model is a plain function, by its name, and the desk's
    module defines a function of that name; it names `wrap` and `break.toml`."""
    section = _sections()[HOW]
    assert "`scripted_model`" in section and "`wrap`" in section and "`break.toml`" in section
    agent = (REPO / "examples" / "desk" / "desk_agent.py").read_text(encoding="utf-8")
    assert "\ndef scripted_model(" in agent


def test_each_fault_the_section_names_is_a_tool_fault_that_runs_the_tool_as_it_says() -> None:
    """The section names a timeout, which arrives without the tool running, as a `TimeoutError`;
    and `empty`, `malformed`, `stale` and `lost_reply`, which each run the real tool. Each is a
    tool fault of the catalogue, and its catalogue line agrees on whether the real tool runs."""
    from poisson_break.apply import ToolFailure
    from poisson_break.changes import CATALOG

    section = _sections()[HOW]
    lines = {line.name: line for line in CATALOG if line.surface == "tool"}
    named = {word for word in re.findall(r"`([a-z_]+)`", section) if word in lines}
    assert {"empty", "malformed", "stale", "lost_reply"} <= named, named
    assert all(lines[word].real_runs for word in named), named
    assert "`TimeoutError`" in section
    assert lines["timeout"].real_runs is False
    assert isinstance(ToolFailure("timeout", "the request timed out"), TimeoutError)


SEE = "What you see"


def _desk_runs(tmp_path: Path) -> dict[str, int]:
    """The first screen's three commands, run in an empty folder: how many runs the hunt's store
    held after `hunt`, and after `confirm`."""
    from poisson_prove.store import Store

    stored = {}
    for words in (["init", "--example", "desk"], ["hunt", "--yes"], ["confirm", "--yes"]):
        ran = run_command(words, cwd=tmp_path)
        assert ran.exit == 0, ran.stderr
        store = tmp_path / "break-runs" / "desk-1" / "store"
        if store.is_dir():
            stored[words[0]] = sum(Store(store).count(run) for run in Store(store).runs())
    return stored


def test_what_you_see_says_what_ran_and_what_the_hunt_s_folder_holds(tmp_path: Path) -> None:
    """The section says how many times the first screen called the desk's function, each count
    the store holds; it names what `break-runs/desk-1/` holds, and the folder holds each; and it
    names `replay` as what shows what the agent did."""
    stored = _desk_runs(tmp_path)
    section = _sections()[SEE]
    hunted, confirmed = stored["hunt"], stored["confirm"] - stored["hunt"]
    assert f"{hunted} times" in section, hunted
    assert f"{confirmed} more" in section, confirmed
    folder = tmp_path / "break-runs" / "desk-1"
    assert "`break-runs/desk-1/`" in section
    for name in ("hunt.json", "candidates.json", "findings/1.toml", "store/"):
        assert f"`{name}`" in section, name
        assert (folder / name).exists(), name
    assert "`replay`" in section


def test_a_stored_run_holds_no_prompt_and_no_reply(tmp_path: Path) -> None:
    """What the section says a stored run is: Break's record, which holds the case by its id and
    none of the agent's request, reply or tool results. Every row of every arm of the desk's
    store is read, and no request of the cases, no reply the desk gives and no result its order
    look-up returns is in it."""
    from poisson_prove.store import Store

    _desk_runs(tmp_path)
    store = Store(tmp_path / "break-runs" / "desk-1" / "store")
    rows = repr([store.read(run).to_dict("records") for run in store.runs()])
    assert "status-4821" in rows
    cases = [json.loads(line) for line in
             (REPO / "examples" / "desk" / "cases.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    said = [case["input"] for case in cases] + [
        "Order 48", "could not look that order up", "shipped on Tuesday, due Thursday"]
    assert [text for text in said if text in rows] == []
    section = _sections()[SEE]
    assert "prompt" in section and "reply" in section
