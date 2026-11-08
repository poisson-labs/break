"""`init`'s dialogue: the nine questions under scripted answers, in both renderings.

Taylor's rulings on BK8's open points (2026-11-07) settle what the spec left to `init`'s form, and these tests hold them:

- point 1: one prompt per question in §9.3's order, each skipped when its flag was given. Question 1 a menu of the six
  kinds, `rollout` the default and named "a function Break can call"; question 2 text with no default, and `init`
  refused in one line naming `--entry` when it cannot be asked; question 3 text, default `cases.jsonl`, then a `[y/N]` to
  write the starter file when that file is not there; question 4 a menu `read`, `write`, `off` per tool, default `read`,
  and for each `write` a menu `repeatable` or `stand-in`, then the stand-in's path as text; question 5 the outcomes and
  the own check as text, each empty by default; question 6 a `[y/N]` per surface with §9.3's defaults (tool behaviour
  yes, inputs yes, the conversation asked only when a case has turns, model calls no, settings of one's own no);
  question 7 text, default 400; question 8 the two prices as text, empty by default; question 9 text, default 5.00, asked
  only when both prices were given;
- point 2: for a `rollout` target, `init` lists exactly the tools `poisson_break.apply.wrapped_while` says were wrapped
  while the target's module was imported (BK8.5);
- point 3: `init` writes `break.toml`, and `cases.jsonl` only when the starter file was asked for; nothing else;
- point 4: a kind whose extra is missing still gets `break.toml`, `wrote`, exit 0, and the install command as its first
  `next:` (BK8.12);
- point 5: "at most nine questions" counts the numbered questions; no prompt belongs to a question past nine.

Taylor's rulings on points 31 to 40 (2026-11-07) settle the rest of the form, and these tests hold them too:

- point 31: under `init --yes` each question takes its own default, the `[y/N]` ones as no, and the look is asked
  nothing;
- point 32: each line of question 1's menu starts with the kind as `break.toml` writes it, so a script chooses any of the
  six, in either rendering;
- point 33: with no tool found, question 4 is one text prompt for the names, comma-separated, empty by default meaning
  none, then each name's `read`/`write`/`off` menu as for a tool found;
- point 34: question 2 given an entry that does not import, or nothing, says why in one `note:` line and asks again; a
  stdin that ends first is the look's refusal;
- point 35: a yes to model calls is `vary.model` set to every model fault of the catalogue; a yes to settings of one's
  own is a text prompt per setting in `--env`'s form, until an empty answer;
- point 36: the conversation question is `[Y/n]`;
- point 43: a yes to the conversation is `vary.conversation` set to every conversation move of the catalogue, in the
  catalogue's order, and a no writes none;
- point 40: the install command is the one `poisson_break.settings.install_command` hands back.

Invariants held here (Break — Plan, the commands module): BK8.3 (the dialogue under scripted answers and the equivalent
command produce byte-identical files, under both renderings), BK8.5 and BK8.12 (the menus use the look's question and
run under scripted answers in both renderings).

Every dialogue runs on three pseudo-terminals (`tests/commands_dialogue.py`). Plain is the terminals with `NO_COLOR`;
pretty is the terminals with the switch holding, where a menu is questionary's and is answered with the arrow keys.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

import pytest

from tests.commands_dialogue import Asked, converse, orders, scripted
from tests.commands_spies import INSTALL_COMMAND, NOTHING_TO_INSTALL, spied, spying
from tests.commands_support import (
    CODES,
    PROG,
    REAL,
    cli,
    child_env,
    errors,
    files_under,
    json_document,
    nexts,
    project,
    refused_once,
    verdict,
)
from tests.look_support import strip

ENTRY = "tests.commands_targets:desk"
STAND_IN = "tests.commands_targets:old_desk"
# The tools `tests/commands_targets.py` wraps at import, in the order it wraps them.
WRAPPED = ("lookup_order", "check_policy")
# Each kind whose way in is an optional extra, and that extra (the settings module's own table).
EXTRAS = {"openai-agents": "openai-agents", "langgraph": "langgraph", "crewai": "crewai", "mcp": "mcp",
          "command": "mcp"}
# The six kinds, as `break.toml` writes them (BK4.7).
KINDS = ("openai-agents", "langgraph", "crewai", "mcp", "command", "rollout")


def empty(tmp_path: Path, *, with_cases: bool = True, turns: bool = False) -> Any:
    proj = project(tmp_path, write=False)
    if with_cases:
        case = {"id": "k1", "input": "Where is order 1?"}
        if turns:
            case = {"id": "k1", "turns": ["Where is order 1?", "And order 2?"]}
        proj.write(case_list=[case])
    return proj


def expected(words: list[str]) -> str:
    from poisson_break.settings import dump, settings_from_init_args

    return str(dump(settings_from_init_args(words)))


# The answers of one whole dialogue, each with the flags that write the same file. Question 4's per-tool menus are
# answered by the tool the question names, so the order the tools are asked in is the build's.
CLASSES = {"lookup_order": ["read"], "check_policy": ["write", "stand-in", STAND_IN]}


def answering(classes: dict[str, list[str]], rest: list[str]) -> Any:
    """Questions 1 to 3 from `rest`'s head, question 4's menus by the tool each names from `classes`, and every other
    question from `rest` in turn."""
    queue = list(rest)
    pending: list[str] = []

    def answer(asked: Asked) -> str:
        if pending:
            return pending.pop(0)
        tools = [t for t in classes if t in asked.question]
        if asked.is_menu and tools and set(asked.menu) == {"read", "write", "off"}:
            first, *more = classes[tools[0]]
            pending.extend(more)
            return first
        assert queue, f"a question the script did not expect: {asked.text!r}"
        return queue.pop(0)

    return answer


# Question 1 takes the default (Enter), 2 the entry, 3 the default file, the starter file not asked (the file is
# there); 5 an outcome and the own check; 6 the defaults of the four surfaces asked; 7 123 runs; 8 two prices; 9 $2.50.
WHOLE = ["", ENTRY, "", "unresolved", "tests.commands_targets:unresolved", "", "", "", "", "123", "0.4", "0.4", "2.5"]
WHOLE_FLAGS = ["--kind", "rollout", "--entry", ENTRY, "--cases", "cases.jsonl",
               "--tool", 'lookup_order = "read"',
               "--tool", f'check_policy = {{ class = "write", stand_in = "{STAND_IN}" }}',
               "--outcomes", "unresolved", "--own-check", "tests.commands_targets:unresolved",
               "--runs", "123", "--input-per-million", "0.4", "--output-per-million", "0.4", "--dollars", "2.5"]


def kinds_of_prompt(asked: list[Asked]) -> list[str]:
    """Each prompt as what it is: `menu`, `yes/no` with its bracket, or `text` with its bracket."""
    shown = []
    for one in asked:
        if one.is_menu:
            shown.append("menu")
        elif one.yes_no:
            shown.append(one.bracket or "")
        else:
            shown.append("text")
    return shown


@pytest.fixture(scope="module")
def plain(tmp_path_factory: pytest.TempPathFactory) -> tuple[Any, Any, list[Asked]]:
    proj = empty(tmp_path_factory.mktemp("plain"))
    ran, asked = converse(proj, ["init"], answering(dict(CLASSES), list(WHOLE)))
    return proj, ran, asked


@pytest.fixture(scope="module")
def pretty(plain: tuple[Any, Any, list[Asked]],
           tmp_path_factory: pytest.TempPathFactory) -> tuple[Any, Any, list[Asked]]:
    proj = empty(tmp_path_factory.mktemp("pretty"))
    ran, asked = converse(proj, ["init"], answering(dict(CLASSES), list(WHOLE)), pretty=True,
                          order=orders(plain[2]))
    return proj, ran, asked


# ---------------------------------------------------------------------------
# BK8.3: the dialogue under scripted answers writes what the same flags write
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rendering", ["plain", "pretty"])
def test_the_dialogue_writes_the_file_its_answers_flags_write(rendering: str, request: pytest.FixtureRequest) -> None:
    proj, ran, asked = request.getfixturevalue(rendering)
    assert ran.exit == CODES["done"], (ran, asked)
    assert proj.settings.read_text(encoding="utf-8") == expected(WHOLE_FLAGS)


@pytest.mark.parametrize("rendering", ["plain", "pretty"])
def test_the_dialogue_ends_with_wrote_and_the_command_that_writes_the_same_file(
        rendering: str, request: pytest.FixtureRequest, tmp_path: Path) -> None:
    """BK8.3, §9.3: the command printed, run in another folder with every default taken (`--yes`, as BK8.3's other
    tests run it), writes a byte-identical file."""
    from poisson_break.settings import equivalent_init_command, settings_from_init_args

    proj, ran, asked = request.getfixturevalue(rendering)
    assert strip(ran.out).splitlines()[0].split("  ")[0] == "wrote", ran
    want = equivalent_init_command(settings_from_init_args(WHOLE_FLAGS), prog=PROG)
    assert want in [n.strip() for n in nexts(ran)] or want in strip(ran.out + ran.err), ran
    other = empty(tmp_path)
    again = cli(other, *shlex.split(want)[1:], "--yes")
    assert again.exit == CODES["done"], again
    assert other.settings.read_bytes() == proj.settings.read_bytes()


def test_the_two_renderings_ask_the_same_questions_in_the_same_order(
        plain: tuple[Any, Any, list[Asked]], pretty: tuple[Any, Any, list[Asked]]) -> None:
    assert plain[1].exit == pretty[1].exit == CODES["done"], (plain[1], pretty[1])
    assert len(plain[2]) == 17
    assert [a.question for a in pretty[2]] == [a.question for a in plain[2]]
    assert [a.answer for a in pretty[2]] == [a.answer for a in plain[2]]


def test_the_dialogue_says_break_calls_your_tools_for_real(plain: tuple[Any, Any, list[Asked]]) -> None:
    assert REAL in strip(plain[1].out + plain[1].err)


# ---------------------------------------------------------------------------
# point 1: the form and order of the questions; point 5: at most nine
# ---------------------------------------------------------------------------


def test_the_prompts_come_in_section_9_3_s_order_one_per_question(plain: tuple[Any, Any, list[Asked]]) -> None:
    """With the cases file there, two tools found, one of them `write` with a stand-in, both prices given: question 1
    a menu, 2 text, 3 text, 4 a menu per tool and for the write tool a menu and a text, 5 two texts, 6 four yes/nos
    (no turns, so no conversation), 7 text, 8 two texts, 9 text."""
    _, _, asked = plain
    assert kinds_of_prompt(asked) == [
        "menu", "text", "text",
        "menu", "menu", "menu", "text",
        "text", "text",
        "[Y/n]", "[Y/n]", "[y/N]", "[y/N]",
        "text", "text", "text", "text",
    ], [a.text for a in asked]


def test_question_1_is_a_menu_of_the_six_kinds_opening_on_a_function_break_can_call(
        plain: tuple[Any, Any, list[Asked]]) -> None:
    first = plain[2][0]
    assert len(first.menu) == 6, first.text
    assert first.bracket is not None
    default = first.bracket[1:-1]
    marked = [c for c in first.menu if "a function Break can call" in c]
    assert marked == [default], first.text
    assert "rollout" in plain[0].settings.read_text(encoding="utf-8")


def test_the_defaults_are_section_9_3_s(plain: tuple[Any, Any, list[Asked]]) -> None:
    """Question 3's default is `cases.jsonl`, question 4's `read`, question 7's 400 and question 9's 5.00."""
    _, _, asked = plain
    brackets = [a.bracket for a in asked]
    assert brackets[2] == "[cases.jsonl]"
    tool_menus = [a for a in asked if set(a.menu) == {"read", "write", "off"}]
    assert [a.bracket for a in tool_menus] == ["[read]"] * len(tool_menus)
    assert brackets[13] == "[400]"
    assert brackets[16] == "[5.00]"


def test_question_4_is_a_menu_read_write_off_per_tool_found_naming_the_tool(
        plain: tuple[Any, Any, list[Asked]]) -> None:
    """BK8.5, point 2: one menu for each tool the target's module wrapped on import, and no other."""
    menus = [a for a in plain[2] if a.menu == ["read", "write", "off"]]
    named = sorted(t for a in menus for t in WRAPPED if t in a.question)
    assert named == sorted(WRAPPED), [a.text for a in menus]
    assert len(menus) == len(WRAPPED)


def test_a_write_tool_is_asked_repeatable_or_stand_in_then_the_stand_in_s_path(
        plain: tuple[Any, Any, list[Asked]]) -> None:
    asked = plain[2]
    at = next(i for i, a in enumerate(asked) if a.menu == ["read", "write", "off"] and a.answer == "write")
    assert asked[at + 1].menu == ["repeatable", "stand-in"], asked[at + 1].text
    assert not asked[at + 2].is_menu and not asked[at + 2].yes_no
    assert asked[at + 2].answer == STAND_IN


def test_no_prompt_belongs_to_a_question_past_nine(plain: tuple[Any, Any, list[Asked]]) -> None:
    """Point 5: the prompts, read in order, fall into the nine questions and no further: after question 9's (the last,
    `[5.00]`) nothing is asked."""
    asked = plain[2]
    assert asked[-1].bracket == "[5.00]"
    numbered = numbered_questions(asked)
    assert numbered == sorted(numbered), numbered
    assert sorted(set(numbered)) == list(range(1, 10)), numbered


def numbered_questions(asked: list[Asked]) -> list[int]:
    """The number of the question each prompt belongs to, read by point 1's form: the menu of six kinds is question 1
    and the text after it 2; the text whose default is the cases file 3, with the `[y/N]` after it; a tool's menu, the
    menu after a `write` and the text after `stand-in` 4; the yes/nos 6, and a text after a yes there or after such a
    text answered (point 35's settings of one's own) 6; `[400]` 7; `[5.00]` 9; a text after 6 or 7 that is neither is
    8, and any other text 5."""
    numbers: list[int] = []
    for i, one in enumerate(asked):
        before = asked[i - 1] if i else None
        if one.is_menu and len(one.menu) == 6:
            number = 1
        elif before is not None and before.is_menu and len(before.menu) == 6:
            number = 2
        elif one.bracket == "[cases.jsonl]" or (one.yes_no and before is not None
                                                and before.bracket == "[cases.jsonl]"):
            number = 3
        elif one.is_menu or (before is not None and before.answer == "stand-in"):
            number = 4
        elif one.yes_no:
            number = 6
        elif one.bracket == "[400]":
            number = 7
        elif one.bracket == "[5.00]":
            number = 9
        elif numbers and numbers[-1] == 6 and before is not None and (
                (before.yes_no and before.answer.lower().startswith("y")) or (not before.yes_no and before.answer)):
            number = 6  # point 35: a setting of one's own, after the yes or after the setting before it
        elif numbers and numbers[-1] in (6, 7, 8):
            number = 8
        else:
            number = 5
        numbers.append(number)
    return numbers


def test_question_9_is_not_asked_without_the_prices(tmp_path: Path) -> None:
    """Question 8 answered with no price: question 9 is not asked, and the file has no prices and no cap in dollars."""
    proj = empty(tmp_path)
    rest = ["", ENTRY, "", "", "", "", "", "", "", "", "", ""]
    ran, asked = converse(proj, ["init"], answering(dict(CLASSES), rest))
    assert ran.exit == CODES["done"], (ran, asked)
    assert "[5.00]" not in [a.bracket for a in asked]
    words = ["--kind", "rollout", "--entry", ENTRY, "--cases", "cases.jsonl", "--tool", 'lookup_order = "read"',
             "--tool", f'check_policy = {{ class = "write", stand_in = "{STAND_IN}" }}']
    assert proj.settings.read_text(encoding="utf-8") == expected(words)


def every_conversation_move() -> str:
    """Point 43: every conversation move of the catalogue, in the catalogue's order, as `--vary-conversation` takes
    them."""
    from poisson_break.changes import CATALOG

    return ",".join(e.name for e in CATALOG if e.surface == "user")


def test_the_conversation_is_asked_only_when_a_case_has_turns_and_defaults_to_yes(tmp_path: Path) -> None:
    """Question 6 asks one yes/no more when a case is a conversation, third of its five, and it is `[Y/n]` (point 36);
    Enter takes it, and the file is the one `--vary-conversation` with every move of the catalogue writes, in the
    catalogue's order (point 43)."""
    from poisson_break.changes import CATALOG
    from poisson_break.settings import loads

    proj = empty(tmp_path, turns=True)
    rest = ["", ENTRY, "", "", "", "", "", "", "", "", "", "", ""]
    ran, asked = converse(proj, ["init"], answering(dict(CLASSES), rest))
    assert ran.exit == CODES["done"], (ran, asked)
    assert [a.bracket for a in asked if a.yes_no] == ["[Y/n]", "[Y/n]", "[Y/n]", "[y/N]", "[y/N]"], [a.text for a in
                                                                                                      asked]
    text = proj.settings.read_text(encoding="utf-8")
    assert loads(text).vary.conversation == tuple(e.name for e in CATALOG if e.surface == "user")
    words = ["--kind", "rollout", "--entry", ENTRY, "--cases", "cases.jsonl", "--tool", 'lookup_order = "read"',
             "--tool", f'check_policy = {{ class = "write", stand_in = "{STAND_IN}" }}',
             "--vary-conversation", every_conversation_move()]
    assert text == expected(words)


def test_the_conversation_answered_no_is_not_varied(tmp_path: Path) -> None:
    proj = empty(tmp_path, turns=True)
    rest = ["", ENTRY, "", "", "", "", "", "n", "", "", "", "", ""]
    ran, asked = converse(proj, ["init"], answering(dict(CLASSES), rest))
    assert ran.exit == CODES["done"], (ran, asked)
    assert [a.answer for a in asked if a.yes_no] == ["", "", "n", "", ""]
    words = ["--kind", "rollout", "--entry", ENTRY, "--cases", "cases.jsonl", "--tool", 'lookup_order = "read"',
             "--tool", f'check_policy = {{ class = "write", stand_in = "{STAND_IN}" }}']
    assert proj.settings.read_text(encoding="utf-8") == expected(words)


# ---------------------------------------------------------------------------
# each question skipped when its flag was given
# ---------------------------------------------------------------------------


EVERY_QUESTION_FLAGGED = [*WHOLE_FLAGS, "--vary-tools", "error,timeout", "--vary-inputs", "typos",
                          "--vary-model", "error", "--env", 'inventory = ["full", "empty"]']


def test_with_every_question_s_flag_given_nothing_is_asked(tmp_path: Path) -> None:
    """Every question answered by a flag: `init` asks nothing, so it needs no terminal and no `--yes`."""
    proj = empty(tmp_path)
    ran = cli(proj, "init", *EVERY_QUESTION_FLAGGED)
    assert ran.exit == CODES["done"], ran
    assert proj.settings.read_text(encoding="utf-8") == expected(EVERY_QUESTION_FLAGGED)


def test_a_flag_given_skips_its_question_and_only_its_own(tmp_path: Path) -> None:
    """`--kind` and `--runs` given: question 1's menu and question 7's `[400]` are not asked; the rest are."""
    proj = empty(tmp_path)
    rest = [ENTRY, "", "", "", "", "", "", "", "", ""]
    ran, asked = converse(proj, ["init", "--kind", "rollout", "--runs", "77"], answering(dict(CLASSES), rest))
    assert ran.exit == CODES["done"], (ran, asked)
    assert not any(a.is_menu and len(a.menu) == 6 for a in asked)
    assert "[400]" not in [a.bracket for a in asked]
    assert sum(a.yes_no for a in asked) == 4
    words = ["--kind", "rollout", "--entry", ENTRY, "--cases", "cases.jsonl", "--tool", 'lookup_order = "read"',
             "--tool", f'check_policy = {{ class = "write", stand_in = "{STAND_IN}" }}', "--runs", "77"]
    assert proj.settings.read_text(encoding="utf-8") == expected(words)


def test_tools_given_as_flags_skip_question_4(tmp_path: Path) -> None:
    proj = empty(tmp_path)
    rest = ["", ENTRY, "", "", "", "", "", "", "", "", "", ""]
    ran, asked = converse(proj, ["init", "--tool", 'lookup_order = "read"', "--tool", 'check_policy = "off"'],
                          scripted(rest))
    assert ran.exit == CODES["done"], (ran, asked)
    assert not any(a.menu == ["read", "write", "off"] for a in asked)


# ---------------------------------------------------------------------------
# question 2: the entry, which has no default
# ---------------------------------------------------------------------------


def test_with_no_terminal_and_no_entry_init_is_refused_naming_entry(tmp_path: Path) -> None:
    """Question 2 cannot be asked (stdin is not a terminal) and `--entry` was not given: one line naming `--entry`,
    exit 1, nothing written."""
    proj = empty(tmp_path)
    before = files_under(proj.folder)
    ran = cli(proj, "init", "--kind", "rollout")
    line = refused_once(ran, CODES["refused"])
    assert "--entry" in line, line
    assert files_under(proj.folder) == before


def test_under_yes_with_no_entry_init_is_refused_naming_entry(tmp_path: Path) -> None:
    """`--yes` takes each default, and question 2 has none."""
    proj = empty(tmp_path)
    ran = cli(proj, "init", "--yes", "--kind", "rollout", "--tool", 'lookup_order = "read"')
    line = refused_once(ran, CODES["refused"])
    assert "--entry" in line, line
    assert not proj.settings.exists()
    assert cli(proj, "init", "--yes", "--kind", "rollout", "--entry", ENTRY, "--tool",
               'lookup_order = "read"').exit == CODES["done"], "the same with --entry is taken"


# ---------------------------------------------------------------------------
# point 3: the starter cases file
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def starter(tmp_path_factory: pytest.TempPathFactory) -> tuple[Any, Any, list[Asked]]:
    proj = empty(tmp_path_factory.mktemp("starter"), with_cases=False)
    rest = ["", ENTRY, "", "y", "", "", "", "", "", "", "", "", ""]
    ran, asked = converse(proj, ["init"], answering(dict(CLASSES), rest), PYTHONDONTWRITEBYTECODE="1")
    return proj, ran, asked


def test_the_starter_file_is_offered_as_a_yes_no_when_the_cases_file_is_not_there(
        starter: tuple[Any, Any, list[Asked]]) -> None:
    _, ran, asked = starter
    assert ran.exit == CODES["done"], (ran, asked)
    assert asked[2].bracket == "[cases.jsonl]"
    assert asked[3].bracket == "[y/N]", asked[3].text


def test_the_starter_file_asked_for_is_three_cases_and_the_only_other_file(
        starter: tuple[Any, Any, list[Asked]]) -> None:
    from poisson_break.settings import read_cases

    proj, ran, _ = starter
    assert set(files_under(proj.folder)) == {"break.toml", "cases.jsonl"}
    assert len(read_cases(proj.folder / "cases.jsonl")) == 3
    assert 'cases = "cases.jsonl"' in proj.settings.read_text(encoding="utf-8")


def test_with_the_cases_file_there_the_starter_file_is_not_offered(plain: tuple[Any, Any, list[Asked]]) -> None:
    asked = plain[2]
    assert asked[2].bracket == "[cases.jsonl]"
    assert not asked[3].yes_no, asked[3].text
    assert set(files_under(plain[0].folder)) - {"cases.jsonl"} <= {"break.toml"}


# ---------------------------------------------------------------------------
# point 4: a kind whose extra is missing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(EXTRAS))
def test_a_kind_whose_extra_is_missing_is_written_and_ends_with_the_install_command(tmp_path: Path,
                                                                                   kind: str) -> None:
    """BK8.12, point 4: `break.toml` written, `wrote`, exit 0, and the first `next:` is `pip install` of the extra."""
    proj = empty(tmp_path)
    words = ["--kind", kind, "--entry", ENTRY, "--cases", "cases.jsonl", "--tool", 'lookup_order = "read"']
    ran = cli(proj, "init", "--yes", *words)
    assert ran.exit == CODES["done"], ran
    assert verdict(ran)[0] == "wrote"
    assert errors(ran) == []
    assert proj.settings.read_text(encoding="utf-8") == expected(words)
    first = shlex.split(nexts(ran)[0])
    assert first == ["pip", "install", f"poisson-break[{EXTRAS[kind]}]"], nexts(ran)


# ---------------------------------------------------------------------------
# point 2 through the command: the tools found are the module's wrapped ones
# ---------------------------------------------------------------------------


def test_the_tools_listed_are_those_the_target_s_module_wrapped_on_import(tmp_path: Path) -> None:
    """BK8.5: a module that wraps three tools on import, one of them never called: question 4 asks of exactly those
    three, by name; the agent is never run."""
    proj = empty(tmp_path)
    (proj.folder / "three_tools.py").write_text(
        "from poisson_break.apply import wrap\n"
        "def _a(q): return q\n"
        "find_order = wrap('find_order', _a)\n"
        "send_mail = wrap('send_mail', _a)\n"
        "never_called = wrap('never_called', _a)\n"
        "def agent(cfg, seed):\n"
        "    raise SystemExit('the agent was run')\n", encoding="utf-8")
    classes = {"find_order": ["read"], "send_mail": ["off"], "never_called": ["read"]}
    rest = ["", "three_tools:agent", "", "", "", "", "", "", "", "", "", ""]
    ran, asked = converse(proj, ["init"], answering(classes, rest),
                          PYTHONPATH=f"{proj.folder}:" + child_env(proj)["PYTHONPATH"])
    assert ran.exit == CODES["done"], (ran, asked)
    menus = [a for a in asked if a.menu == ["read", "write", "off"]]
    assert sorted(t for a in menus for t in classes if t in a.question) == sorted(classes)
    assert len(menus) == 3
    assert proj.runs() == []
    text = proj.settings.read_text(encoding="utf-8")
    for tool in classes:
        assert tool in text


# ---------------------------------------------------------------------------
# point 22: a bad value given to a flag
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("flag", "value", "key"), [("--runs", "0", "runs"), ("--dollars", "-1", "dollars")])
def test_a_bad_value_given_to_a_flag_is_a_mistake_on_the_command_line_naming_its_key(
        tmp_path: Path, flag: str, value: str, key: str) -> None:
    proj = empty(tmp_path)
    line = refused_once(cli(proj, "init", "--yes", "--kind", "rollout", "--entry", ENTRY, "--tool",
                            'lookup_order = "read"', flag, value), CODES["usage"])
    assert key in line, line
    assert not proj.settings.exists()


# ---------------------------------------------------------------------------
# point 11: the schema
# ---------------------------------------------------------------------------


def test_init_s_document_is_named_init_result(tmp_path: Path) -> None:
    proj = empty(tmp_path)
    ran = cli(proj, "init", "--yes", "--json", "--kind", "rollout", "--entry", ENTRY, "--tool", 'lookup_order = "read"')
    assert ran.exit == CODES["done"], ran
    assert json_document(ran)["schema"] == "poisson_break.init-result/1"


# ---------------------------------------------------------------------------
# point 40: the install command is settings.install_command's
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["rollout", "langgraph"])
def test_the_install_command_is_the_one_settings_install_command_hands_back(tmp_path: Path, kind: str) -> None:
    """With `install_command` stood in for, handing back a line for every kind, the core's own too: that line is the
    first `next:`, and `init` asked it of the kind written."""
    proj = empty(tmp_path / "proj")
    env = spying(proj, tmp_path / "spy", INSTALL_COMMAND)
    ran = cli(proj, "init", "--yes", "--kind", kind, "--entry", ENTRY, "--tool", 'lookup_order = "read"', **env)
    assert ran.exit == CODES["done"], ran
    assert nexts(ran)[0] == f"pip install spied-extra-for-{kind}", nexts(ran)
    assert {"name": "install_command", "kind": kind} in spied(env)


def test_with_nothing_to_install_init_names_no_install_command(tmp_path: Path) -> None:
    """With `install_command` handing back `None` for every kind, a kind whose extra is missing gets no `pip install`."""
    proj = empty(tmp_path / "proj")
    env = spying(proj, tmp_path / "spy", NOTHING_TO_INSTALL)
    ran = cli(proj, "init", "--yes", "--kind", "langgraph", "--entry", ENTRY, "--tool", 'lookup_order = "read"', **env)
    assert ran.exit == CODES["done"], ran
    assert nexts(ran) and not any(shlex.split(n)[0] == "pip" for n in nexts(ran)), nexts(ran)
    assert {"name": "install_command", "kind": "langgraph"} in spied(env)


# ---------------------------------------------------------------------------
# point 31: init --yes takes every default, the [y/N] ones as no
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("streams", ["terminals", "piped"])
def test_init_yes_takes_every_default_the_yes_no_ones_as_no(tmp_path: Path, streams: str) -> None:
    """No cases file, so the starter file would be offered: under `--yes` it is not written, model calls and settings of
    one's own stay off, each tool found is `read`, and nothing is asked, on terminals or not."""
    from poisson_break.settings import loads

    proj = empty(tmp_path, with_cases=False)
    if streams == "terminals":
        ran, asked = converse(proj, ["init", "--yes", "--entry", ENTRY], scripted([]))
        assert asked == []
    else:
        ran = cli(proj, "init", "--yes", "--entry", ENTRY)
    assert ran.exit == CODES["done"], ran
    assert "[y/N]" not in strip(ran.err) and "[Y/n]" not in strip(ran.err)
    assert set(files_under(proj.folder)) == {"break.toml"}
    words = ["--kind", "rollout", "--entry", ENTRY, "--cases", "cases.jsonl",
             *[w for tool in WRAPPED for w in ("--tool", f'{tool} = "read"')]]
    text = proj.settings.read_text(encoding="utf-8")
    assert text == expected(words)
    vary = loads(text).vary
    assert (vary.model, vary.env, vary.conversation) == ((), (), ())


def test_init_yes_with_conversations_takes_the_conversation_s_default_yes(tmp_path: Path) -> None:
    """Points 31, 36 and 43: the conversation's default is yes, so `--yes` turns it on with every conversation move of
    the catalogue, in the catalogue's order, and nothing else."""
    from poisson_break.changes import CATALOG
    from poisson_break.settings import loads

    proj = empty(tmp_path, turns=True)
    ran = cli(proj, "init", "--yes", "--entry", ENTRY)
    assert ran.exit == CODES["done"], ran
    vary = loads(proj.settings.read_text(encoding="utf-8")).vary
    assert vary.conversation == tuple(e.name for e in CATALOG if e.surface == "user")
    assert (vary.model, vary.env) == ((), ())


# ---------------------------------------------------------------------------
# point 32: each kind chosen in question 1's menu, in both renderings
# ---------------------------------------------------------------------------


def test_each_line_of_question_1_starts_with_the_kind_as_break_toml_writes_it(
        plain: tuple[Any, Any, list[Asked]]) -> None:
    menu = plain[2][0].menu
    assert sorted(line.split()[0] for line in menu) == sorted(KINDS), menu
    (rollout,) = [line for line in menu if line.split()[0] == "rollout"]
    assert "a function Break can call" in rollout


def choosing(kind: str) -> Any:
    """Question 1 answered with the line of `kind`, question 2 with the entry, and every other question by Enter."""
    count = {"asked": 0}

    def answer(asked: Asked) -> str:
        count["asked"] += 1
        if count["asked"] == 1:
            assert len(asked.menu) == 6, asked.text
            (line,) = [c for c in asked.menu if c.split()[0] == kind]
            return line
        if count["asked"] == 2:
            return ENTRY
        return ""

    return answer


@pytest.mark.parametrize("rendering", ["plain", "pretty"])
@pytest.mark.parametrize("kind", KINDS)
def test_each_kind_can_be_chosen_in_question_1_s_menu(tmp_path: Path, plain: tuple[Any, Any, list[Asked]], kind: str,
                                                      rendering: str) -> None:
    """BK8.12, points 4 and 32: chosen in the menu, the kind is written; a kind whose extra is missing still gets
    `break.toml`, `wrote`, exit 0, and the install command as its first `next:`."""
    from poisson_break.settings import loads

    proj = empty(tmp_path)
    ran, asked = converse(proj, ["init"], choosing(kind), pretty=rendering == "pretty", order=orders(plain[2]))
    assert ran.exit == CODES["done"], (ran, asked)
    assert verdict(ran)[0] == "wrote"
    written = loads(proj.settings.read_text(encoding="utf-8"))
    assert (written.target.kind, written.target.entry) == (kind, ENTRY)
    if kind in EXTRAS:
        assert shlex.split(nexts(ran)[0]) == ["pip", "install", f"poisson-break[{EXTRAS[kind]}]"], nexts(ran)
    else:
        assert not any(shlex.split(n)[0] == "pip" for n in nexts(ran)), nexts(ran)


# ---------------------------------------------------------------------------
# point 33: question 4 when no tool was found
# ---------------------------------------------------------------------------

IN_BODY = ("from poisson_break.apply import wrap\n"
           "def _a(q): return q\n"
           "def agent(cfg, seed):\n"
           "    lookup = wrap('lookup_order', _a)\n"
           "    send = wrap('send_mail', _a)\n"
           "    raise SystemExit('the agent was run')\n")
IN_BODY_CLASSES = {"lookup_order": ["read"], "send_mail": ["off"]}
IN_BODY_REST = ["", "in_body:agent", "", "lookup_order, send_mail", "", "", "", "", "", "", "", "", ""]
IN_BODY_WORDS = ["--kind", "rollout", "--entry", "in_body:agent", "--cases", "cases.jsonl",
                 "--tool", 'lookup_order = "read"', "--tool", 'send_mail = "off"']


def in_body(folder: Path) -> tuple[Any, dict[str, str]]:
    proj = empty(folder)
    (proj.folder / "in_body.py").write_text(IN_BODY, encoding="utf-8")
    return proj, {"PYTHONPATH": f"{proj.folder}:" + child_env(proj)["PYTHONPATH"]}


@pytest.fixture(scope="module")
def no_tool_found(tmp_path_factory: pytest.TempPathFactory) -> dict[str, tuple[Any, Any, list[Asked]]]:
    proj, env = in_body(tmp_path_factory.mktemp("in-body-plain"))
    ran, asked = converse(proj, ["init"], answering(dict(IN_BODY_CLASSES), list(IN_BODY_REST)), **env)
    held = {"plain": (proj, ran, asked)}
    proj, env = in_body(tmp_path_factory.mktemp("in-body-pretty"))
    ran, again = converse(proj, ["init"], answering(dict(IN_BODY_CLASSES), list(IN_BODY_REST)), pretty=True,
                          order=orders(asked), **env)
    held["pretty"] = (proj, ran, again)
    return held


@pytest.mark.parametrize("rendering", ["plain", "pretty"])
def test_with_no_tool_found_question_4_asks_for_the_names_then_a_menu_for_each(
        no_tool_found: dict[str, tuple[Any, Any, list[Asked]]], rendering: str) -> None:
    """A target that wraps its tools inside its own body: question 4 is one text prompt, empty by default, answered
    with two names; then each name's menu, in the order given; the file is what the same flags write."""
    proj, ran, asked = no_tool_found[rendering]
    assert ran.exit == CODES["done"], (ran, asked)
    names = asked[3]
    assert not names.is_menu and not names.yes_no and names.bracket == "[]", names.text
    assert names.answer == "lookup_order, send_mail"
    menus = asked[4:6]
    assert [m.is_menu for m in menus] == [True, True], [m.text for m in menus]
    assert ["lookup_order" in menus[0].question, "send_mail" in menus[1].question] == [True, True]
    if rendering == "plain":
        assert [m.menu for m in menus] == [["read", "write", "off"]] * 2
        assert [m.bracket for m in menus] == ["[read]"] * 2
    assert sum(m.is_menu for m in asked) == 3  # question 1's, and the two
    assert proj.settings.read_text(encoding="utf-8") == expected(IN_BODY_WORDS)
    assert proj.runs() == []


def test_with_no_tool_found_and_no_names_given_no_tool_is_asked_of(tmp_path: Path) -> None:
    proj, env = in_body(tmp_path)
    rest = ["", "in_body:agent", "", "", "", "", "", "", "", "", "", "", ""]
    ran, asked = converse(proj, ["init"], scripted(rest), **env)
    assert ran.exit == CODES["done"], (ran, asked)
    assert sum(a.is_menu for a in asked) == 1
    words = ["--kind", "rollout", "--entry", "in_body:agent", "--cases", "cases.jsonl"]
    assert proj.settings.read_text(encoding="utf-8") == expected(words)


# ---------------------------------------------------------------------------
# point 34: question 2 given an entry that does not import, or nothing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["no_such_module_here:agent", ""], ids=["does not import", "nothing"])
def test_question_2_given_a_bad_entry_says_why_in_one_note_and_asks_again(tmp_path: Path, bad: str) -> None:
    proj = empty(tmp_path)
    rest = ["", bad, ENTRY, "", "", "", "", "", "", "", "", "", ""]
    ran, asked = converse(proj, ["init"], answering(dict(CLASSES), rest))
    assert ran.exit == CODES["done"], (ran, asked)
    assert asked[2].question == asked[1].question and asked[2].bracket == asked[1].bracket, asked[2].text
    said = [line for line in strip(asked[2].text).splitlines() if line.strip()]
    assert [line for line in said if line.startswith("note:")] and len(
        [line for line in said if line.startswith("note:")]) == 1, said
    assert not [line for line in said if line.startswith("error:")], said
    if bad:
        assert "no_such_module_here" in strip(asked[2].text), said
    words = ["--kind", "rollout", "--entry", ENTRY, "--cases", "cases.jsonl", "--tool", 'lookup_order = "read"',
             "--tool", f'check_policy = {{ class = "write", stand_in = "{STAND_IN}" }}']
    assert proj.settings.read_text(encoding="utf-8") == expected(words)


def test_question_2_with_stdin_ending_first_is_the_look_s_refusal(tmp_path: Path) -> None:
    """End of input (Ctrl-D) at question 2: the look refuses the question in one line, exit 1, nothing written."""
    proj = empty(tmp_path)
    before = files_under(proj.folder)
    ran, asked = converse(proj, ["init"], scripted(["", "\x04"]))
    assert ran.exit == CODES["refused"], (ran, asked)
    assert len([line for line in strip(ran.err).splitlines() if line.startswith("error:")]) == 1, ran
    assert "Traceback" not in ran.err
    assert files_under(proj.folder) == before


# ---------------------------------------------------------------------------
# point 35: what a yes to model calls, or to settings of one's own, adds
# ---------------------------------------------------------------------------


def test_a_yes_to_model_calls_and_to_settings_of_one_s_own(tmp_path: Path) -> None:
    """Model calls yes: every model fault of the catalogue. Settings of one's own yes: one text prompt per setting, in
    `--env`'s form, until an empty answer; then question 7."""
    from poisson_break.changes import CATALOG

    proj = empty(tmp_path)
    inventory, region = 'inventory = ["full", "empty"]', 'region = ["eu", "us"]'
    rest = ["", ENTRY, "", "", "", "", "", "y", "y", inventory, region, "", "", "", ""]
    ran, asked = converse(proj, ["init"], answering(dict(CLASSES), rest))
    assert ran.exit == CODES["done"], (ran, asked)
    at = next(i for i, a in enumerate(asked) if a.answer == inventory)
    assert asked[at - 1].yes_no and asked[at - 1].answer == "y"
    own = asked[at:at + 3]
    assert [(a.is_menu, a.yes_no) for a in own] == [(False, False)] * 3, [a.text for a in own]
    assert [a.answer for a in own] == [inventory, region, ""]
    assert asked[at + 3].bracket == "[400]"
    numbered = numbered_questions(asked)
    assert numbered == sorted(numbered) and set(numbered) == set(range(1, 9)), numbered
    model = ",".join(e.name for e in CATALOG if e.surface == "model")
    words = ["--kind", "rollout", "--entry", ENTRY, "--cases", "cases.jsonl", "--tool", 'lookup_order = "read"',
             "--tool", f'check_policy = {{ class = "write", stand_in = "{STAND_IN}" }}',
             "--vary-model", model, "--env", inventory, "--env", region]
    assert proj.settings.read_text(encoding="utf-8") == expected(words)
