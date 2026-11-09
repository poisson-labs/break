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

import shlex

from tests.conftest import REPO
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
