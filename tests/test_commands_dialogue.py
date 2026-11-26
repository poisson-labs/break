"""`init`'s dialogue: the questions Break cannot answer for itself, under scripted answers, in both renderings.

Taylor's yes on issue 13 (2026-11-13) settles what `init` asks, and these tests hold it. It asks only:

1. where the agent is, as `module:name`: text with no default, asked again with one `note:` line when the answer is
   not an import path whose module is there; `init` is refused in one line naming `--entry` when it cannot be asked;
2. where the test cases are: text, default `cases.jsonl`, then a `[y/N]` to write a starter file of three cases when
   that file is not there;
3. for each tool found, one `[y/N]`: does calling it change anything, even in a test environment. A no is `read`. A yes
   is followed by a `[y/N]` on whether it is safe to repeat (`repeatable`), and a no to that by the place of its stand-in
   as text, asked again like the agent's place. Given none, `init` writes nothing and refuses, naming the stand-in it
   needs, since `off` would let Break call the real tool in every run.

Everything else (the kind, what fails a run, what Break may change, the runs, the prices and the cap) takes its default
and is not asked. Every flag still sets its value and skips its question, and `--yes` takes every default. `init` then
says what it chose and that `break.toml` is where to change it, and prints the one command that writes the same file.

Earlier rulings still held here (BK8's open points, 2026-11-07 and 2026-11-08):

- point 2: for a `rollout` target, `init` asks about exactly the tools `poisson_break.apply.wrapped_while` says were
  wrapped while the target's module was imported (BK8.5); with none found, one text prompt for the names,
  comma-separated, empty by default meaning none (point 33);
- point 3: `init` writes `break.toml`, and `cases.jsonl` only when the starter file was asked for; nothing else;
- point 4 is withdrawn by Taylor's yes on hands-on issue 17 (2026-11-13): a kind whose way in is not there is refused
  before anything is written (held in `tests/test_commands_init.py`); point 40: the install command `init` prints is
  the one `poisson_break.settings.install_command` hands back, which is none for every kind in this release;
- point 31: under `init --yes` each question takes its own default, the `[y/N]` ones as no, and the look is asked
  nothing;
- point 34: a stdin that ends before the agent's place is given is the look's refusal;
- points 46 and 47: when a case has turns, the command `init` prints states the conversation's setting, even when
  empty, and that command runs exactly as printed, with or without a terminal, and writes the same file.

Taylor's yes on issue 12 (2026-11-13): `init` turns on nothing the chosen way in cannot do, read from the way in's own
capabilities, so a rollout target's conversation and model calls are never varied by default.

Invariants held here (Break — Plan, the commands module): BK8.3 (the dialogue under scripted answers and the equivalent
command produce byte-identical files, under both renderings) and BK8.5.

Every dialogue runs on three pseudo-terminals (`tests/commands_dialogue.py`). Plain is the terminals with `NO_COLOR`;
pretty is the terminals with the switch holding.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

import pytest

from tests.commands_dialogue import Asked, converse, scripted
from tests.commands_spies import INSTALL_COMMAND, NOTHING_TO_INSTALL, spied, spying
from tests.commands_support import (
    CODES,
    PROG,
    REAL,
    cli,
    child_env,
    files_under,
    json_document,
    nexts,
    project,
    refused_once,
)
from tests.look_support import strip

ENTRY = "tests.commands_targets:desk"
STAND_IN = "tests.commands_targets:old_desk"
# The tools `tests/commands_targets.py` wraps at import, in the order it wraps them.
WRAPPED = ("lookup_order", "check_policy")
AGENT = "Where is your agent"
CASES = "Where are your test cases"
STARTER = "There is no such file"
NAMES = "No tool was found"


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


# How each tool is answered, by the tool the question names: whether calling it changes anything, then whether it is
# safe to repeat, then its stand-in's place. The order the tools are asked in is the build's.
CLASSES = {"lookup_order": ["n"], "check_policy": ["y", "n", STAND_IN]}


def answering(classes: dict[str, list[str]], *, entry: str = ENTRY, cases: str = "", starter: str = "",
              names: str = "") -> Any:
    """Each question answered by what it asks: the agent's place with `entry`, the cases' with `cases`, the starter
    file with `starter`, the tools' names with `names`, and each tool's questions from `classes` in turn. A question
    none of these is a failure of the test."""
    left = {tool: list(said) for tool, said in classes.items()}

    def answer(asked: Asked) -> str:
        if asked.question.startswith(AGENT):
            return entry
        if asked.question.startswith(CASES):
            return cases
        if asked.question.startswith(STARTER):
            return starter
        if asked.question.startswith(NAMES):
            return names
        tools = [tool for tool in left if f" {tool}" in asked.question or f"{tool} " in asked.question]
        assert tools and left[tools[0]], f"a question the script did not expect: {asked.text!r}"
        return left[tools[0]].pop(0)

    return answer


WHOLE_FLAGS = ["--kind", "rollout", "--entry", ENTRY, "--cases", "cases.jsonl",
               "--tool", 'lookup_order = "read"',
               "--tool", f'check_policy = {{ class = "write", stand_in = "{STAND_IN}" }}']


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
    ran, asked = converse(proj, ["init"], answering(CLASSES))
    return proj, ran, asked


@pytest.fixture(scope="module")
def pretty(tmp_path_factory: pytest.TempPathFactory) -> tuple[Any, Any, list[Asked]]:
    proj = empty(tmp_path_factory.mktemp("pretty"))
    ran, asked = converse(proj, ["init"], answering(CLASSES), pretty=True)
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
    assert len(plain[2]) == 6
    assert [a.question for a in pretty[2]] == [a.question for a in plain[2]]
    assert [a.answer for a in pretty[2]] == [a.answer for a in plain[2]]


def test_the_dialogue_says_break_calls_your_tools_for_real(plain: tuple[Any, Any, list[Asked]]) -> None:
    assert REAL in strip(plain[1].out + plain[1].err)


# ---------------------------------------------------------------------------
# the form and order of the questions
# ---------------------------------------------------------------------------


def test_the_prompts_come_in_order_one_per_question_and_no_menu(plain: tuple[Any, Any, list[Asked]]) -> None:
    """With the cases file there and two tools found, one of them changing things with a stand-in: the agent's place,
    the cases' place, a yes/no for each tool, the yes/no on repeating, and the stand-in's place. No menu."""
    _, _, asked = plain
    assert kinds_of_prompt(asked) == ["text", "text", "[y/N]", "[y/N]", "[y/N]", "text"], [a.text for a in asked]
    assert asked[0].question.startswith(AGENT) and asked[0].bracket == "[]"
    assert asked[1].question.startswith(CASES) and asked[1].bracket == "[cases.jsonl]"


def test_nothing_but_the_agent_the_cases_and_the_tools_is_asked(plain: tuple[Any, Any, list[Asked]]) -> None:
    """No kind, no outcome, no check, no surface, no runs, no price and no cap is asked."""
    for one in plain[2]:
        words = one.question.lower()
        for word in ("built with", "outcome", "your own check", "may break", "how many runs", "cost", "dollars",
                     "spend"):
            assert word not in words, one.question
    assert 'kind = "rollout"' in plain[0].settings.read_text(encoding="utf-8")


def test_each_tool_found_is_asked_one_yes_no_naming_it(plain: tuple[Any, Any, list[Asked]]) -> None:
    """BK8.5, point 2: one yes/no for each tool the target's module wrapped on import, and no other."""
    asked = [a for a in plain[2] if a.question.startswith("Does calling")]
    assert [a.question for a in asked] == [
        f"Does calling {tool} change anything, even in a test environment?" for tool in WRAPPED]
    assert [a.bracket for a in asked] == ["[y/N]"] * len(WRAPPED)


def test_a_tool_that_changes_things_is_asked_whether_it_is_safe_to_repeat_then_its_stand_in(
        plain: tuple[Any, Any, list[Asked]]) -> None:
    asked = plain[2]
    at = next(i for i, a in enumerate(asked) if a.question.startswith("Does calling check_policy"))
    assert asked[at].answer == "y"
    assert asked[at + 1].yes_no and "safe to repeat" in asked[at + 1].question, asked[at + 1].text
    assert not asked[at + 2].is_menu and not asked[at + 2].yes_no
    assert "stand-in" in asked[at + 2].question and asked[at + 2].answer == STAND_IN


def test_init_says_what_it_chose_and_where_to_change_it(plain: tuple[Any, Any, list[Asked]]) -> None:
    """After `wrote`, plain lines: what fails a run, what Break may change, the runs and the prices it chose, and that
    `break.toml` is where to change any of it; then the one `init` command."""
    out = strip(plain[1].out)
    lines = out.splitlines()
    assert lines[0] == "wrote  break.toml", out
    said = [line.strip() for line in lines[1:] if line.startswith("  ")]
    for label in ("fails on", "may change", "runs", "prices"):
        assert [line for line in said if line.startswith(label + " ")], (label, out)
    assert said[-1] == ("Break chose what it did not ask. Change any of it in break.toml, and doctor checks the "
                        "file."), out
    assert lines[-1].startswith(f"next: {PROG} init "), out


# ---------------------------------------------------------------------------
# each question skipped when its flag was given
# ---------------------------------------------------------------------------


EVERY_QUESTION_FLAGGED = [*WHOLE_FLAGS, "--outcomes", "unresolved", "--own-check", "tests.commands_targets:unresolved",
                          "--vary-tools", "error,timeout", "--vary-inputs", "typos", "--vary-model", "error",
                          "--env", 'inventory = ["full", "empty"]', "--runs", "123", "--input-per-million", "0.4",
                          "--output-per-million", "0.4", "--dollars", "2.5"]


def test_with_every_question_s_flag_given_nothing_is_asked(tmp_path: Path) -> None:
    """Every question answered by a flag: `init` asks nothing, so it needs no terminal and no `--yes`; every flag still
    sets its value."""
    proj = empty(tmp_path)
    ran = cli(proj, "init", *EVERY_QUESTION_FLAGGED)
    assert ran.exit == CODES["done"], ran
    assert proj.settings.read_text(encoding="utf-8") == expected(EVERY_QUESTION_FLAGGED)


def test_a_flag_given_skips_its_question_and_only_its_own(tmp_path: Path) -> None:
    """`--cases` given: the cases' place is not asked; the agent's and the tools' are."""
    proj = empty(tmp_path)
    ran, asked = converse(proj, ["init", "--cases", "cases.jsonl"], answering(CLASSES))
    assert ran.exit == CODES["done"], (ran, asked)
    assert not [a for a in asked if a.question.startswith(CASES)]
    assert kinds_of_prompt(asked) == ["text", "[y/N]", "[y/N]", "[y/N]", "text"], [a.text for a in asked]
    assert proj.settings.read_text(encoding="utf-8") == expected(WHOLE_FLAGS)


def test_tools_given_as_flags_skip_the_tools_questions(tmp_path: Path) -> None:
    proj = empty(tmp_path)
    ran, asked = converse(proj, ["init", "--tool", 'lookup_order = "read"', "--tool", 'check_policy = "off"'],
                          answering({}))
    assert ran.exit == CODES["done"], (ran, asked)
    assert [a.question.split("?")[0] for a in asked] == [
        "Where is your agent", "Where are your test cases"], [a.text for a in asked]


# ---------------------------------------------------------------------------
# the agent's place, which has no default
# ---------------------------------------------------------------------------


def test_with_no_terminal_and_no_entry_init_is_refused_naming_entry(tmp_path: Path) -> None:
    """The agent's place cannot be asked (stdin is not a terminal) and `--entry` was not given: one line naming
    `--entry`, exit 1, nothing written."""
    proj = empty(tmp_path)
    before = files_under(proj.folder)
    ran = cli(proj, "init", "--kind", "rollout")
    line = refused_once(ran, CODES["refused"])
    assert "--entry" in line, line
    assert files_under(proj.folder) == before


def test_under_yes_with_no_entry_init_is_refused_naming_entry(tmp_path: Path) -> None:
    """`--yes` takes each default, and the agent's place has none."""
    proj = empty(tmp_path)
    ran = cli(proj, "init", "--yes", "--kind", "rollout", "--tool", 'lookup_order = "read"')
    line = refused_once(ran, CODES["refused"])
    assert "--entry" in line, line
    assert not proj.settings.exists()
    assert cli(proj, "init", "--yes", "--kind", "rollout", "--entry", ENTRY, "--tool",
               'lookup_order = "read"').exit == CODES["done"], "the same with --entry is taken"


@pytest.mark.parametrize("bad", ["no_such_module_here:agent", "", "no colon"],
                         ids=["does not import", "nothing", "not module:name"])
def test_the_agent_s_place_given_badly_says_why_in_one_note_and_asks_again(tmp_path: Path, bad: str) -> None:
    proj = empty(tmp_path)
    given = [bad, ENTRY]
    answer = answering(CLASSES)

    def first_bad(asked: Asked) -> str:
        return given.pop(0) if asked.question.startswith(AGENT) else answer(asked)

    ran, asked = converse(proj, ["init"], first_bad)
    assert ran.exit == CODES["done"], (ran, asked)
    assert asked[1].question == asked[0].question and asked[1].bracket == asked[0].bracket, asked[1].text
    said = [line for line in strip(asked[1].text).splitlines() if line.strip()]
    assert len([line for line in said if line.startswith("note:")]) == 1, said
    assert not [line for line in said if line.startswith("error:")], said
    if bad:
        assert bad.split(":")[0] in strip(asked[1].text), said
    assert proj.settings.read_text(encoding="utf-8") == expected(WHOLE_FLAGS)


def test_a_stdin_that_ends_at_the_agent_s_place_is_the_look_s_refusal(tmp_path: Path) -> None:
    """End of input (Ctrl-D) at the first question: the look refuses the question in one line, exit 1, nothing
    written."""
    proj = empty(tmp_path)
    before = files_under(proj.folder)
    ran, asked = converse(proj, ["init"], scripted(["\x04"]))
    assert ran.exit == CODES["refused"], (ran, asked)
    assert len([line for line in strip(ran.err).splitlines() if line.startswith("error:")]) == 1, ran
    assert "Traceback" not in ran.err
    assert files_under(proj.folder) == before


# ---------------------------------------------------------------------------
# point 3: the starter cases file
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def starter(tmp_path_factory: pytest.TempPathFactory) -> tuple[Any, Any, list[Asked]]:
    proj = empty(tmp_path_factory.mktemp("starter"), with_cases=False)
    ran, asked = converse(proj, ["init"], answering(CLASSES, starter="y"), PYTHONDONTWRITEBYTECODE="1")
    return proj, ran, asked


def test_the_starter_file_is_offered_as_a_yes_no_when_the_cases_file_is_not_there(
        starter: tuple[Any, Any, list[Asked]]) -> None:
    _, ran, asked = starter
    assert ran.exit == CODES["done"], (ran, asked)
    assert asked[1].bracket == "[cases.jsonl]"
    assert asked[2].question.startswith(STARTER) and asked[2].bracket == "[y/N]", asked[2].text


def test_the_starter_file_asked_for_is_three_cases_and_the_only_other_file(
        starter: tuple[Any, Any, list[Asked]]) -> None:
    from poisson_break.settings import read_cases

    proj, ran, _ = starter
    assert set(files_under(proj.folder)) == {"break.toml", "cases.jsonl"}
    assert len(read_cases(proj.folder / "cases.jsonl")) == 3
    assert 'cases = "cases.jsonl"' in proj.settings.read_text(encoding="utf-8")


def test_with_the_cases_file_there_the_starter_file_is_not_offered(plain: tuple[Any, Any, list[Asked]]) -> None:
    asked = plain[2]
    assert asked[1].bracket == "[cases.jsonl]"
    assert not [a for a in asked if a.question.startswith(STARTER)]
    assert set(files_under(plain[0].folder)) - {"cases.jsonl"} <= {"break.toml"}


# ---------------------------------------------------------------------------
# point 2 through the command: the tools found are the module's wrapped ones
# ---------------------------------------------------------------------------


def test_the_tools_asked_about_are_those_the_target_s_module_wrapped_on_import(tmp_path: Path) -> None:
    """BK8.5: a module that wraps three tools on import, one of them never called: each is asked about by name, and no
    other; the agent is never run."""
    proj = empty(tmp_path)
    (proj.folder / "three_tools.py").write_text(
        "from poisson_break.apply import wrap\n"
        "def _a(q): return q\n"
        "find_order = wrap('find_order', _a)\n"
        "send_mail = wrap('send_mail', _a)\n"
        "never_called = wrap('never_called', _a)\n"
        "def agent(cfg, seed):\n"
        "    raise SystemExit('the agent was run')\n", encoding="utf-8")
    classes = {"find_order": ["n"], "send_mail": ["y", "y"], "never_called": ["n"]}
    ran, asked = converse(proj, ["init"], answering(classes, entry="three_tools:agent"),
                          PYTHONPATH=f"{proj.folder}:" + child_env(proj)["PYTHONPATH"])
    assert ran.exit == CODES["done"], (ran, asked)
    named = [a for a in asked if a.question.startswith("Does calling")]
    assert sorted(t for a in named for t in classes if f" {t} " in a.question) == sorted(classes)
    assert len(named) == 3
    assert proj.runs() == []
    words = ["--kind", "rollout", "--entry", "three_tools:agent", "--cases", "cases.jsonl",
             "--tool", 'find_order = "read"', "--tool", 'send_mail = { class = "write", repeatable = true }',
             "--tool", 'never_called = "read"']
    assert proj.settings.read_text(encoding="utf-8") == expected(words)


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


@pytest.mark.parametrize("kind", ["rollout"])
def test_the_install_command_is_the_one_settings_install_command_hands_back(tmp_path: Path, kind: str) -> None:
    """With `install_command` stood in for, handing back a line for every kind, the core's own too: that line is the
    first `next:`, and `init` asked it of the kind written. A kind whose way in is not there is refused before it is
    asked (hands-on issue 17), so the kind here is the core's own."""
    proj = empty(tmp_path / "proj")
    env = spying(proj, tmp_path / "spy", INSTALL_COMMAND)
    ran = cli(proj, "init", "--yes", "--kind", kind, "--entry", ENTRY, "--tool", 'lookup_order = "read"', **env)
    assert ran.exit == CODES["done"], ran
    assert nexts(ran)[0] == f"pip install spied-extra-for-{kind}", nexts(ran)
    assert {"name": "install_command", "kind": kind} in spied(env)


def test_with_nothing_to_install_init_names_no_install_command(tmp_path: Path) -> None:
    """With `install_command` handing back `None` for every kind, as it does for each in this release, `init` names no
    `pip install`."""
    proj = empty(tmp_path / "proj")
    env = spying(proj, tmp_path / "spy", NOTHING_TO_INSTALL)
    ran = cli(proj, "init", "--yes", "--kind", "rollout", "--entry", ENTRY, "--tool", 'lookup_order = "read"', **env)
    assert ran.exit == CODES["done"], ran
    assert nexts(ran) and not any(shlex.split(n)[0] == "pip" for n in nexts(ran)), nexts(ran)
    assert {"name": "install_command", "kind": "rollout"} in spied(env)


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


def test_init_yes_with_conversations_leaves_the_conversation_alone_for_a_way_in_that_cannot_play_one(
        tmp_path: Path) -> None:
    """The conversation's default is on only where the way in can play a conversation's turns; the rollout way in
    cannot, so `--yes` with a case that has turns varies nothing of the conversation, and nothing else is turned on."""
    from poisson_break.settings import loads

    proj = empty(tmp_path, turns=True)
    ran = cli(proj, "init", "--yes", "--entry", ENTRY)
    assert ran.exit == CODES["done"], ran
    vary = loads(proj.settings.read_text(encoding="utf-8")).vary
    assert (vary.conversation, vary.model, vary.env) == ((), (), ())


def test_init_asks_nothing_the_way_in_cannot_do(tmp_path: Path) -> None:
    """The rollout way in cannot reach the model's own calls or play a conversation's turns: with a case that has turns,
    `init` asks about neither, and the file varies neither, asked or under `--yes`. What the way in can do is its own
    word, not a kind's name."""
    from poisson_break.hunt import RolloutTarget
    from poisson_break.settings import loads

    proj = empty(tmp_path, turns=True)
    ran, asked = converse(proj, ["init"], answering(CLASSES))
    assert ran.exit == CODES["done"], (ran, asked)
    questions = [a.question for a in asked]
    assert not [q for q in questions if "model" in q or "conversation" in q], questions
    vary = loads(proj.settings.read_text(encoding="utf-8")).vary
    assert (vary.model, vary.conversation) == ((), ())
    other = empty(tmp_path / "yes", turns=True)
    assert cli(other, "init", "--yes", "--entry", ENTRY).exit == CODES["done"]
    vary = loads(other.settings.read_text(encoding="utf-8")).vary
    assert (vary.model, vary.conversation) == ((), ())
    assert not RolloutTarget.CAN.model_calls and not RolloutTarget.CAN.conversation


# ---------------------------------------------------------------------------
# point 33: the tools' names when no tool was found
# ---------------------------------------------------------------------------

IN_BODY = ("from poisson_break.apply import wrap\n"
           "def _a(q): return q\n"
           "def agent(cfg, seed):\n"
           "    lookup = wrap('lookup_order', _a)\n"
           "    send = wrap('send_mail', _a)\n"
           "    raise SystemExit('the agent was run')\n")
IN_BODY_CLASSES = {"lookup_order": ["n"], "send_mail": ["y", "y"]}
IN_BODY_WORDS = ["--kind", "rollout", "--entry", "in_body:agent", "--cases", "cases.jsonl",
                 "--tool", 'lookup_order = "read"', "--tool", 'send_mail = { class = "write", repeatable = true }']


def placing_none(answer: Any) -> Any:
    """Ruling 9 of the wrapping at load spec (spec §12.5): a name typed that the entry's module does not hold is asked
    one more question, where that function is, as `module:name`. Answered empty, the tool's line has no place, as it
    did before the ruling; every other question goes to `answer`."""
    def answering_where(asked: Asked) -> str:
        q = asked.question
        if (not asked.yes_no and "module:name" in q and not q.startswith(AGENT) and "stand-in" not in q):
            return ""
        return str(answer(asked))

    return answering_where


def in_body(folder: Path) -> tuple[Any, dict[str, str]]:
    proj = empty(folder)
    (proj.folder / "in_body.py").write_text(IN_BODY, encoding="utf-8")
    return proj, {"PYTHONPATH": f"{proj.folder}:" + child_env(proj)["PYTHONPATH"]}


@pytest.fixture(scope="module")
def no_tool_found(tmp_path_factory: pytest.TempPathFactory) -> dict[str, tuple[Any, Any, list[Asked]]]:
    held = {}
    for rendering in ("plain", "pretty"):
        proj, env = in_body(tmp_path_factory.mktemp(f"in-body-{rendering}"))
        ran, asked = converse(proj, ["init"], placing_none(answering(IN_BODY_CLASSES, entry="in_body:agent",
                                                                     names="lookup_order, send_mail")),
                              pretty=rendering == "pretty", **env)
        held[rendering] = (proj, ran, asked)
    return held


@pytest.mark.parametrize("rendering", ["plain", "pretty"])
def test_with_no_tool_found_the_names_are_asked_then_each_tool_s_questions(
        no_tool_found: dict[str, tuple[Any, Any, list[Asked]]], rendering: str) -> None:
    """A target that wraps its tools inside its own body: one text prompt, empty by default, answered with two names;
    the module holds neither, so each is asked where it is (ruling 9 of the wrapping at load spec), answered with
    nothing; then each name's questions, in the order given; the file is what the same flags write."""
    proj, ran, asked = no_tool_found[rendering]
    assert ran.exit == CODES["done"], (ran, asked)
    names = asked[2]
    assert names.question.startswith(NAMES) and not names.yes_no and names.bracket == "[]", names.text
    assert names.answer == "lookup_order, send_mail"
    assert "lookup_order" in asked[3].question and "module:name" in asked[3].question and asked[3].answer == ""
    assert "send_mail" in asked[4].question and "module:name" in asked[4].question and asked[4].answer == ""
    assert asked[5].question.startswith("Does calling lookup_order")
    assert asked[6].question.startswith("Does calling send_mail")
    assert not any(a.is_menu for a in asked)
    assert proj.settings.read_text(encoding="utf-8") == expected(IN_BODY_WORDS)
    assert proj.runs() == []


def test_with_no_tool_found_and_no_names_given_no_tool_is_asked_of(tmp_path: Path) -> None:
    proj, env = in_body(tmp_path)
    ran, asked = converse(proj, ["init"], answering({}, entry="in_body:agent"), **env)
    assert ran.exit == CODES["done"], (ran, asked)
    assert len(asked) == 3, [a.text for a in asked]
    words = ["--kind", "rollout", "--entry", "in_body:agent", "--cases", "cases.jsonl"]
    assert proj.settings.read_text(encoding="utf-8") == expected(words)


# ---------------------------------------------------------------------------
# points 46 and 47: the printed command, run as printed, when the cases have turns
# ---------------------------------------------------------------------------


def printed_init(ran: Any) -> list[str]:
    """The one `init` command among the `next:` lines, as words."""
    found = [shlex.split(n) for n in nexts(ran) if shlex.split(n)[:2] == [PROG, "init"]]
    assert len(found) == 1, nexts(ran)
    return found[0]


def taking_every_default(asked: Asked) -> str:
    return ""


HOWS = ["turns, the dialogue", "turns, init --yes", "turns, one move by flag", "no turns, init --yes"]


def first_init(tmp_path: Path, how: str) -> tuple[Any, list[str]]:
    """`init` in a project whose case has turns, through the dialogue, taken by `--yes`, or given one move by its flag;
    or, beside them, a case with no turns. Hands back the project and the command `init` printed, as words; where a
    case has turns, the command says `--vary-conversation` itself (point 46)."""
    turns = how.startswith("turns")
    proj = empty(tmp_path / "first", turns=turns)
    if how == "turns, the dialogue":
        ran, _ = converse(proj, ["init"], answering(CLASSES))
    elif how == "turns, one move by flag":
        ran = cli(proj, "init", "--yes", "--entry", ENTRY, "--vary-conversation", "interrupts")
    else:
        ran = cli(proj, "init", "--yes", "--entry", ENTRY)
    assert ran.exit == CODES["done"], ran
    words = printed_init(ran)
    if turns:
        assert "--vary-conversation" in words[:-1] or any(w.startswith("--vary-conversation=") for w in words), words
    return proj, words


def written_alike(proj: Any, other: Any, cases_before: bytes) -> None:
    assert other.settings.read_bytes() == proj.settings.read_bytes()
    assert files_under(other.folder) == {"break.toml": proj.settings.read_bytes(), "cases.jsonl": cases_before}


@pytest.mark.parametrize("how", HOWS)
def test_the_printed_command_run_as_printed_writes_the_same_file(tmp_path: Path, how: str) -> None:
    """Point 46: run as printed in another folder holding the same cases, on terminals with every question it leaves
    to a default answered with Enter, the command exits 0 and writes a byte-identical file, and that folder holds only
    the two files."""
    proj, words = first_init(tmp_path, how)
    other = empty(tmp_path / "again", turns=how.startswith("turns"))
    cases_before = (other.folder / "cases.jsonl").read_bytes()
    again, _ = converse(other, words[1:], taking_every_default)
    assert again.exit == CODES["done"], again
    written_alike(proj, other, cases_before)


@pytest.mark.parametrize("how", HOWS)
def test_the_printed_command_runs_as_printed_with_no_terminal(tmp_path: Path, how: str) -> None:
    """Point 47 (Taylor's yes, 2026-11-08): §9.3's "one non-interactive command". Run exactly as printed in another
    folder holding the same cases, its streams pipes and no terminal anywhere, it asks nothing, exits 0 and writes a
    byte-identical file, and that folder holds only the two files."""
    proj, words = first_init(tmp_path, how)
    other = empty(tmp_path / "again", turns=how.startswith("turns"))
    cases_before = (other.folder / "cases.jsonl").read_bytes()
    again = cli(other, *words[1:])
    assert again.exit == CODES["done"], again
    assert "[y/N]" not in strip(again.err) and "[Y/n]" not in strip(again.err), again
    written_alike(proj, other, cases_before)


# ---------------------------------------------------------------------------
# Taylor's yes on issue 13 (2026-11-13): init asks only what Break cannot find out for itself
# ---------------------------------------------------------------------------


def test_init_asks_only_where_the_agent_and_the_cases_are_and_what_each_tool_changes(tmp_path: Path) -> None:
    """Where the agent is, where the cases are, and for each tool found one yes/no on whether calling it changes
    anything, a yes followed by whether it is safe to repeat: nothing else is asked. Every other setting takes its
    default, and `init` says in plain lines what it chose and that `break.toml` is where to change it, then prints the
    one command that writes the same file."""
    proj = empty(tmp_path)
    answers = {"lookup_order": "n", "check_policy": "y"}

    def answer(asked: Asked) -> str:
        if "Where is your agent" in asked.question:
            return ENTRY
        for tool, said in answers.items():
            if f"Does calling {tool} change anything" in asked.question:
                return said
        if "check_policy" in asked.question and "safe to repeat" in asked.question:
            return "y"
        return ""

    ran, asked = converse(proj, ["init"], answer)
    assert ran.exit == CODES["done"], (ran, asked)
    assert kinds_of_prompt(asked) == ["text", "text", "[y/N]", "[y/N]", "[y/N]"], [a.text for a in asked]
    assert [a.question for a in asked][2:4] == [
        f"Does calling {tool} change anything, even in a test environment?" for tool in WRAPPED]
    words = ["--kind", "rollout", "--entry", ENTRY, "--cases", "cases.jsonl", "--tool", 'lookup_order = "read"',
             "--tool", 'check_policy = { class = "write", repeatable = true }']
    assert proj.settings.read_text(encoding="utf-8") == expected(words)
    out = strip(ran.out)
    assert out.splitlines()[0] == "wrote  break.toml", out
    said = [line.strip() for line in out.splitlines()[1:] if line.startswith("  ")]
    assert any("break.toml" in line and "change" in line.lower() for line in said), out
    assert any(line.startswith("may change") for line in said), out
    assert any(line.startswith("runs") for line in said), out
    printed = [n for n in nexts(ran) if shlex.split(n)[:2] == [PROG, "init"]]
    assert len(printed) == 1, nexts(ran)


def answering_check_policy(where: str) -> Any:
    """The agent's place, then `check_policy` said to change things and not to be safe to repeat, its stand-in's place
    answered with `where`; every other question by Enter."""

    def answer(asked: Asked) -> str:
        if asked.question.startswith(AGENT):
            return ENTRY
        if "Does calling check_policy" in asked.question:
            return "y"
        if "stand-in" in asked.question and "check_policy" in asked.question and not asked.yes_no:
            return where
        return ""

    return answer


def test_a_tool_that_changes_things_and_is_not_safe_to_repeat_is_asked_for_its_stand_in(tmp_path: Path) -> None:
    """A no to whether it is safe to repeat asks where its stand-in is, as module:name, and the stand-in is written."""
    proj = empty(tmp_path)
    ran, asked = converse(proj, ["init"], answering_check_policy(STAND_IN))
    assert ran.exit == CODES["done"], (ran, asked)
    assert kinds_of_prompt(asked) == ["text", "text", "[y/N]", "[y/N]", "[y/N]", "text"], [a.text for a in asked]
    words = ["--kind", "rollout", "--entry", ENTRY, "--cases", "cases.jsonl", "--tool", 'lookup_order = "read"',
             "--tool", f'check_policy = {{ class = "write", stand_in = "{STAND_IN}" }}']
    assert proj.settings.read_text(encoding="utf-8") == expected(words)


def test_a_tool_that_changes_things_with_no_stand_in_is_refused_and_never_left_off(tmp_path: Path) -> None:
    """The coordinator's review of issue 13 (2026-11-13): a tool that changes things, is not safe to repeat and has no
    stand-in is never `off`, which would pass every call to the real tool. The stand-in question offers no empty answer;
    given none, `init` writes nothing and refuses in one line that says what is missing, a stand-in, a function with the
    same arguments that changes nothing, as module:name; its `next:` is the `init` command with the answers so far and
    that tool given a stand-in to fill in."""
    proj = empty(tmp_path)
    before = files_under(proj.folder)
    ran, asked = converse(proj, ["init"], answering_check_policy(""))
    assert ran.exit == CODES["refused"], (ran, asked)
    assert files_under(proj.folder) == before
    question = asked[-1].question
    assert "stand-in" in question and "alone" not in question and "Empty" not in question, question
    said = strip(ran.err)
    assert said.count("error: ") == 1, ran  # on the line of the last prompt, which the answer did not end
    line = said.split("error: ", 1)[1].splitlines()[0]
    for words in ("check_policy", "stand-in", "same arguments", "changes nothing", "module:name"):
        assert words in line, line
    assert len(nexts(ran)) == 1, nexts(ran)
    assert shlex.split(nexts(ran)[0]) == [
        PROG, "init", "--kind", "rollout", "--entry", ENTRY, "--cases", "cases.jsonl",
        "--tool", 'lookup_order = "read"', "--tool", 'check_policy = { class = "write", stand_in = "MODULE:NAME" }']
