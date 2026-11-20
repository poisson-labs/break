"""What wrapping at load must leave as it was, and the pages it changes (spec §12.8, §12.9).

Invariants held here (Break — Plan, the module that wraps tools at load; spec §12.8):
- BK15.5  Nothing leaves the machine: loading an agent with `at` lines, and running it, opens no socket. (Every test of
          the module runs under the network guard of plan §2, item 6: `tests/conftest.py` for the test process, and
          `tests/_guard` for every child, which `tests/load_support.py` and the commands' tests put on its path.)
- BK15.6  Break computes no statistic: plan §2, item 5's source check passes over the source with the module in it.
- BK15.7  The extension points are as they were: the four interface version constants are 1; the `Target` protocol,
          `Session.call`'s three arguments and the run record's schema string are as on `main`; every name this module
          adds is new.
- BK15.1, `wrap`'s half: `wrap`'s own tests (plan BK2.14, `tests/test_apply_wrap.py` and the rest) are unchanged and
          hold; the examples keep their `wrap` lines and the README's first screen is as released (spec §12.9, §12.11
          question 15).

And spec §12.9, at Taylor's yes to question 15: "On your own agent" and the rollout page lead with `at`; the reference
names what the module adds; "What this version cannot test" says what Break cannot reach. Each page is held to the
facts §12.9 gives it, never to its words.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
import tomllib
from pathlib import Path

import pytest

from tests.conftest import REPO
from tests.load_support import child, spec_project, spec_settings

EXAMPLES = REPO / "examples"


# ---------------------------------------------------------------------------
# BK15.5: nothing leaves the machine
# ---------------------------------------------------------------------------


def test_loading_and_running_an_agent_with_at_lines_opens_no_socket(tmp_path: Path) -> None:
    """Every `socket.*` audit event, from before the package is imported to after a run of the agent wrapped at
    load."""
    spec_project(tmp_path)
    said = child(f'''
        events = []
        sys.addaudithook(lambda event, args: events.append(event) if event.startswith("socket.") else None)
        import my_app.agents
        target = load({spec_settings()!r})
        from poisson_break.apply import Session
        from poisson_break.changes import parse
        s = Session(parse("tool:lookup_order#1=error"), seed=0,
                    tools={{"lookup_order": "read", "check_policy": "read",
                            "issue_refund": {{"class": "write", "stand_in": "my_app.fakes:refund"}}}})
        try:
            target.run({{"input": "7"}}, s, seed=0, limits=None)
        except Exception:
            pass
        out({{"events": events, "calls": len(s.calls)}})
    ''', paths=[tmp_path])
    assert said["calls"] >= 1, "the run reached no tool"
    assert said["events"] == []


# ---------------------------------------------------------------------------
# BK15.6: Break computes no statistic
# ---------------------------------------------------------------------------


def test_the_source_with_wrapping_at_load_in_it_computes_no_statistic() -> None:
    """Plan §2, item 5, over the package's source once it holds the module: no statistics library imported and no name
    of a test or interval, by `tests/test_package.py`'s own check."""
    from tests import test_package as package

    apply = importlib.import_module("poisson_break.apply")
    assert callable(getattr(apply, "wrap_at_load", None)), "the module is not built"
    package.test_no_module_imports_a_statistics_library()
    package.test_no_module_names_a_test_or_interval_computed_locally()


# ---------------------------------------------------------------------------
# BK15.7: the extension points are as they were
# ---------------------------------------------------------------------------

#: `poisson_break.apply.__all__` on `main` at 63bd637.
APPLY_ON_MAIN = ["Session", "wrap", "ToolFailure", "ToolRefused", "RunOutOfTime", "ToolInfo", "RunResult", "Seen",
                 "Applied", "InstrumentError", "wrapped_while"]


def test_the_four_interface_versions_are_1() -> None:
    interfaces = importlib.import_module("poisson_break.interfaces")
    assert (interfaces.FAULT_INTERFACE_VERSION, interfaces.TARGET_INTERFACE_VERSION,
            interfaces.STRATEGY_INTERFACE_VERSION, interfaces.CHECK_INTERFACE_VERSION) == (1, 1, 1, 1)


def test_the_target_protocol_is_as_on_main() -> None:
    interfaces = importlib.import_module("poisson_break.interfaces")
    target = interfaces.Target
    assert set(target.__annotations__) == {"kind", "framework_versions"}
    members = {name for name, value in vars(target).items() if inspect.isfunction(value) and not name.startswith("__")}
    assert members == {"tools", "capabilities", "run"}
    assert list(inspect.signature(target.tools).parameters) == ["self"]
    assert list(inspect.signature(target.capabilities).parameters) == ["self"]
    run = inspect.signature(target.run).parameters
    assert [(name, p.kind.name) for name, p in run.items()] == [
        ("self", "POSITIONAL_OR_KEYWORD"), ("case", "POSITIONAL_OR_KEYWORD"), ("session", "POSITIONAL_OR_KEYWORD"),
        ("seed", "KEYWORD_ONLY"), ("limits", "KEYWORD_ONLY")]


def test_session_call_takes_its_three_arguments_and_the_record_s_schema_is_as_on_main() -> None:
    apply = importlib.import_module("poisson_break.apply")
    records = importlib.import_module("poisson_break.records")
    assert list(inspect.signature(apply.Session.call).parameters) == ["self", "tool", "args", "real"]
    assert records.SCHEMA == "poisson_break.run/1"
    hunt = importlib.import_module("poisson_break.hunt")
    assert hunt.HUNT_SCHEMA == "poisson_break.hunt/1"


def test_every_name_the_module_adds_is_new_and_none_is_taken_away() -> None:
    """`wrap_at_load`, `Reached` and `Held` are in `poisson_break.apply`, none of them a name `main` had there; and
    every name `main`'s `apply` gave is given still."""
    apply = importlib.import_module("poisson_break.apply")
    for name in APPLY_ON_MAIN:
        assert name in apply.__all__ and hasattr(apply, name), name
    for name in ("wrap_at_load", "Reached", "Held"):
        assert name not in APPLY_ON_MAIN and hasattr(apply, name), name
    assert len({id(getattr(apply, name)) for name in ("wrap_at_load", "Reached", "Held", *APPLY_ON_MAIN)}) == 14


# ---------------------------------------------------------------------------
# what a first-time user sees does not change (spec §12.9, question 15)
# ---------------------------------------------------------------------------

#: The README's first block of commands, as released in 0.1.1.
FIRST_SCREEN = """python -m venv .venv
. .venv/bin/activate
pip install poisson-break
poisson-break init --example desk
poisson-break hunt --yes
poisson-break confirm --yes"""


def test_the_readme_s_first_screen_is_as_released() -> None:
    text = (REPO / "README.md").read_text(encoding="utf-8")
    first = re.search(r"```sh\n(.*?)\n```", text, re.S)
    assert first is not None and first.group(1) == FIRST_SCREEN
    assert text.index(first.group(0)) < text.index("\n## ")


def _examples() -> list[Path]:
    return sorted(p for p in EXAMPLES.iterdir() if p.is_dir() and (p / "break.toml").is_file())


def test_the_five_examples_keep_their_wrap_lines_and_no_at() -> None:
    """Each example's settings name no place, and its agent wraps, at its top, every tool its settings do not turn
    off: what `init` finds, as released."""
    folders = _examples()
    assert [p.name for p in folders] == ["desk", "full-loop", "own-check", "own-fault", "stand-in"]
    for folder in folders:
        settings = tomllib.loads((folder / "break.toml").read_text(encoding="utf-8"))
        lines = settings["tools"]
        assert not [t for t, line in lines.items() if isinstance(line, dict) and "at" in line], folder.name
        module = settings["target"]["entry"].split(":")[0]
        said = child(f'''
            from poisson_break.apply import wrapped_while
            out(list(wrapped_while({module!r})))
        ''', paths=[folder])
        wanted = {t for t, line in lines.items() if (line if isinstance(line, str) else line.get("class")) != "off"}
        assert wanted <= set(said), (folder.name, said)
        source = (folder / f"{module}.py").read_text(encoding="utf-8")
        assert "from poisson_break.apply import wrap" in source, folder.name


# ---------------------------------------------------------------------------
# spec §12.9: the pages that change
# ---------------------------------------------------------------------------


def _section(text: str, heading: str) -> str:
    lines = text.split("\n")
    start = next(n for n, line in enumerate(lines) if line.lstrip("#").strip() == heading and line.startswith("#"))
    level = len(lines[start]) - len(lines[start].lstrip("#"))
    end = next((n for n in range(start + 1, len(lines))
                if lines[n].startswith("#") and len(lines[n]) - len(lines[n].lstrip("#")) <= level), len(lines))
    return "\n".join(lines[start + 1:end])


def _python_blocks(text: str) -> list[str]:
    return re.findall(r"```python[^\n]*\n(.*?)\n```", text, re.S)


def test_on_your_own_agent_leads_with_an_agent_that_holds_no_break_line() -> None:
    """Spec §12.9: the README's example loses its `poisson_break` import and its `wrap` line; the section says that
    `init` writes where each tool is into `break.toml`, names `at` and `doctor`, and keeps the `wrap` line as the
    second way."""
    section = _section((REPO / "README.md").read_text(encoding="utf-8"), "On your own agent")
    blocks = _python_blocks(section)
    assert blocks, "the section shows no agent"
    assert "poisson_break" not in blocks[0] and "wrap(" not in blocks[0]
    ast.parse(blocks[0])
    for words in ("`at`", "`break.toml`", "`doctor`", "`wrap`", "`init`"):
        assert words in section, words
    assert section.index("`at`") < section.index("`wrap`")


def test_the_rollout_page_leads_with_at() -> None:
    """Spec §12.9: "The function" shows the agent with no Break line, and "The settings" shows `at` on the lines."""
    text = (REPO / "docs" / "ways-in" / "rollout.md").read_text(encoding="utf-8")
    function = _python_blocks(_section(text, "The function"))
    assert function and "poisson_break" not in function[0] and "wrap(" not in function[0]
    settings = _section(text, "The settings")
    assert re.search(r'\bat\s*=\s*"[A-Za-z_][\w.]*:[A-Za-z_]\w*"', settings), settings


def test_the_reference_names_what_the_module_adds() -> None:
    """Spec §12.9: the `[tools]` keys gain `at`; `apply` gains `wrap_at_load`, `Reached` and `Held`; `doctor`'s
    `--json` gains `reached`; `hunt.json` gains `reached` and `later_reached`."""
    text = (REPO / "docs" / "reference.md").read_text(encoding="utf-8")
    for name in ("wrap_at_load", "Reached", "Held", "reached", "later_reached", "`at`"):
        assert name in text, name


def test_what_this_version_cannot_test_names_a_tool_it_cannot_reach() -> None:
    """Spec §12.9: the first line is an agent Break cannot call as a Python function, or a tool it cannot reach, one
    neither named in `break.toml` nor wrapped in your code; and a line says Break does not look for tools on its own."""
    section = _section((REPO / "docs" / "claims.md").read_text(encoding="utf-8"), "What this version cannot test")
    items: list[str] = []
    for line in section.splitlines():
        if line.startswith("- "):
            items.append(line[2:])
        elif items and line.startswith("  "):
            items[-1] += " " + line.strip()
    assert "`break.toml`" in items[0] and "wrap" in items[0], items[0]
    assert "with wrapped tools" not in section


@pytest.mark.parametrize("page", ["README.md", "docs/ways-in/rollout.md", "docs/reference.md", "docs/claims.md"])
def test_each_page_the_module_changes_holds_no_word_break_may_not_say(page: str) -> None:
    """BK15.24, the pages' half: plan BK11.3's patterns (`tests/test_release_words.py`, `hits`) over each page spec
    §12.9 changes, the claims page with the exception that test gives it."""
    from tests.test_release_words import CLAIMS_PAGE, hits

    assert hits((REPO / page).read_text(encoding="utf-8"), claims_page=page == CLAIMS_PAGE) == []
