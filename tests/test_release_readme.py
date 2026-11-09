"""The README's first screen: install, `init`, `hunt`, `confirm`, in that order.

From Break — Plan, the release pass ("Builds"): a README whose first screen is install,
`init`, `hunt`, `confirm`. Read here through the commands the README marks (`tests/release_docs.py`,
rules 1 to 4): of the README's marked commands that are Break's own (an install of the
requirement `poisson-break`, or `poisson-break VERB`), the first four are an install, `init`,
`hunt` and `confirm`, in that order, and no other marked command comes between the install and
`confirm`. The install is of the published name, so a README that still installs from the
checkout (`pip install .`) does not pass. How many lines a screen holds is not settled by the
plan, and is not held here.
"""

from __future__ import annotations

from tests.release_docs import Command, break_verb, is_break_install, marked


def _readme_commands() -> list[Command]:
    commands, _ = marked()
    return [c for c in commands if c.file == "README.md" and c.kind == "sh"]


def _what(command: Command) -> str | None:
    if is_break_install(command):
        return "install"
    return break_verb(command)


def test_the_readme_first_four_break_commands_are_install_init_hunt_confirm() -> None:
    ours = [(c.line, _what(c)) for c in _readme_commands() if _what(c) is not None]
    assert [what for _, what in ours[:4]] == ["install", "init", "hunt", "confirm"], ours


def test_nothing_else_is_run_between_the_install_and_confirm() -> None:
    """The four read as one sequence: no `cd`, no other verb, no other install between them."""
    readme = _readme_commands()
    whats = [_what(c) for c in readme]
    assert "install" in whats and "confirm" in whats, whats
    first = whats.index("install")
    last = whats.index("confirm")
    assert [(c.line, _what(c) or c.command) for c in readme[first:last + 1]] == \
        [(c.line, w) for c, w in zip(readme[first:last + 1], ["install", "init", "hunt", "confirm"])]
