"""`init`: `break.toml` written from its flags, and the one command that writes the same file.

Invariants held here (Break — Plan, the commands module; spec §9.3, §9.4):
- BK8.3   What `init` writes is what its flags say: the file is the settings module's `dump` of what the flags read as,
          and the equivalent command it prints writes a byte-identical file, under both progs and both renderings.
- BK8.4   `init` never runs the agent, reads no key, and writes one file, refusing to overwrite without `--force`.
- BK8.9   "Break calls your tools for real" is in `init`'s output.
- BK8.2   `--json` is one strict document.
- §9.3    Every key has a flag, and a flag is written whole: an abbreviated one is a mistake on the command line.

The dialogue itself (BK8.3's scripted answers, the nine questions, BK8.5's tool question and BK8.12's menus) is held
in `tests/test_commands_dialogue.py`, on Taylor's rulings of BK8 points 1 to 5. Every test here answers no question:
`--yes` takes each default, and the flags say the rest.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.commands_support import (
    CODES,
    PROG,
    REAL,
    child_env,
    cli,
    files_under,
    json_document,
    nexts,
    project,
    refused_once,
    verdict,
)
from tests.look_support import TERMINALS, launch, strip

TARGET = ["--kind", "rollout", "--entry", "tests.commands_targets:desk", "--cases", "cases.jsonl",
          "--tool", 'lookup_order = "read"', "--tool", 'check_policy = "read"']
# Flags off their defaults, a write tool with a stand-in, a value that must be written as TOML, a float to its last
# bit, a list, a setting of one's own, and prices with a cap.
MANY = [*TARGET, "--tool", 'issue_refund = { class = "write", stand_in = "tests.commands_targets:desk" }',
        "--runs", "123", "--seed", "7", "--confirm-repeats", "6", "--max-difference", "0.1234567890123",
        "--checks", "crashed,hung,wrong", "--env", 'inventory = ["full", "empty"]', "--folder", '"--odd folder"',
        "--input-per-million", "0.05", "--output-per-million", "0.4", "--dollars", "2.5"]


def empty(tmp_path: Path) -> Any:
    """A project folder holding only the cases file: what `init` starts from."""
    proj = project(tmp_path, write=False)
    proj.write(case_list=[{"id": "k1", "input": "Where is order 1?"}])
    return proj


def expected(words: list[str]) -> str:
    from poisson_break.settings import dump, settings_from_init_args

    return str(dump(settings_from_init_args(words)))


def printed_command(ran: Any) -> list[str]:
    """The one command `init` printed that writes the same file, as words: the line, wherever it stands, that a shell
    reads as `<prog> init ...`."""
    lines = [*nexts(ran), *(line.strip() for line in strip(ran.out + ran.err).splitlines())]
    found = []
    for line in lines:
        try:
            words = shlex.split(line)
        except ValueError:
            continue
        if len(words) > 1 and words[1] == "init" and " ".join(words[:1]) in (PROG, "poisson"):
            found.append(words)
        elif words[:3] == ["poisson", "break", "init"]:
            found.append(words)
    assert found, f"no init command printed:\n{ran}"
    return found[-1]


@pytest.mark.parametrize("words", [TARGET, MANY], ids=["target", "many"])
def test_init_writes_what_its_flags_say_and_says_wrote(tmp_path: Path, words: list[str]) -> None:
    proj = empty(tmp_path)
    ran = cli(proj, "init", "--yes", *words)
    assert ran.exit == CODES["done"], ran
    assert verdict(ran)[0] == "wrote"
    assert proj.settings.read_text(encoding="utf-8") == expected(words)


@pytest.mark.parametrize("words", [TARGET, MANY], ids=["target", "many"])
def test_the_printed_command_is_the_settings_module_s_equivalent_command(tmp_path: Path, words: list[str]) -> None:
    from poisson_break.settings import equivalent_init_command, settings_from_init_args

    proj = empty(tmp_path)
    ran = cli(proj, "init", "--yes", *words)
    want = equivalent_init_command(settings_from_init_args(words), prog=PROG)
    assert printed_command(ran) in (shlex.split(want), [*shlex.split(want), "--yes"])  # point 47: one trailing --yes
    assert any(want == line.strip() or want in line for line in strip(ran.out + ran.err).splitlines()), \
        "the command is printed whole, on one line"


@pytest.mark.parametrize("prog", [PROG, "poisson break"])
@pytest.mark.parametrize("terminal", [False, True], ids=["piped", "terminal"])
def test_the_printed_command_run_again_writes_a_byte_identical_file(tmp_path: Path, prog: str, terminal: bool) -> None:
    """BK8.3, BK4.4: under both progs and both renderings, run through a real shell in another folder."""
    first = empty(tmp_path / "first")
    words = ["init", "--yes", *MANY]
    if terminal:
        code = f"import sys; from poisson_break.cli import main; sys.exit(main(sys.argv[1:], prog={prog!r}))"
        ran = launch([sys.executable, "-c", code, *words], child_env(first), TERMINALS, cwd=first.folder)
    else:
        ran = cli(first, *words, prog=prog)
    assert ran.exit == CODES["done"], ran
    command = printed_command(ran)
    assert command[: len(shlex.split(prog))] == shlex.split(prog)
    second = empty(tmp_path / "second")
    runner = "import sys; from poisson_break.cli import main; sys.exit(main(sys.argv[1:], prog=sys.argv[0]))"
    tail = command[len(shlex.split(prog)):]
    line = shlex.join([sys.executable, "-c", runner.replace("prog=sys.argv[0]", f"prog={prog!r}"), *tail, "--yes"])
    again = launch(["/bin/sh", "-c", line], child_env(second), cwd=second.folder)
    assert again.exit == CODES["done"], again
    assert second.settings.read_bytes() == first.settings.read_bytes()


def test_init_says_break_calls_your_tools_for_real(tmp_path: Path) -> None:
    ran = cli(empty(tmp_path), "init", "--yes", *TARGET)
    assert REAL in strip(ran.out + ran.err)


def test_init_under_json_is_one_strict_document(tmp_path: Path) -> None:
    proj = empty(tmp_path)
    ran = cli(proj, "init", "--yes", "--json", *TARGET)
    assert ran.exit == CODES["done"], ran
    document = json_document(ran)
    assert list(document)[:3] == ["schema", "verdict", "sentence"]
    assert document["verdict"] == "wrote"
    assert proj.settings.read_text(encoding="utf-8") == expected(TARGET)


# ---------------------------------------------------------------------------
# BK8.4: no run, no key, one file, no overwrite
# ---------------------------------------------------------------------------


def test_init_writes_one_file_in_its_folder_and_nothing_anywhere_else(tmp_path: Path) -> None:
    """The folder gains `break.toml` and nothing else; the home folder gains nothing; the target is never run. Byte code
    is turned off in the child so Python's own caches are not counted as files `init` wrote."""
    proj = empty(tmp_path)
    before, home = files_under(proj.folder), files_under(proj.home)
    ran = cli(proj, "init", "--yes", *MANY, PYTHONDONTWRITEBYTECODE="1")
    assert ran.exit == CODES["done"], ran
    after = files_under(proj.folder)
    assert set(after) - set(before) == {"break.toml"}
    assert {k: v for k, v in after.items() if k != "break.toml"} == before
    assert files_under(proj.home) == home
    assert proj.runs() == []


def test_init_reads_no_key(tmp_path: Path) -> None:
    """No environment variable whose name says key, token, secret or password is read while `init` runs, with such
    variables set; read the way the package's own test reads it (`tests/test_package.py`)."""
    proj = empty(tmp_path)
    probe = (
        "import json, os, sys\n"
        "read = []\n"
        "_g, _c = os._Environ.__getitem__, os._Environ.__contains__\n"
        "os._Environ.__getitem__ = lambda self, k: (read.append(str(k)), _g(self, k))[1]\n"
        "os._Environ.__contains__ = lambda self, k: (read.append(str(k)), _c(self, k))[1]\n"
        "from poisson_break.cli import main\n"
        "code = main(sys.argv[1:])\n"
        "sys.stderr.write('READ=' + json.dumps(sorted(set(read))) + '\\n')\n"
        "sys.exit(code)\n")
    env = {"OPENAI_API_KEY": "not-a-real-key", "ANTHROPIC_API_KEY": "not-a-real-key", "MY_TOKEN": "t"}
    ran = launch([sys.executable, "-c", probe, "init", "--yes", *TARGET], child_env(proj, **env), cwd=proj.folder)
    assert ran.exit == CODES["done"], ran
    read = json.loads(ran.err.rsplit("READ=", 1)[1].splitlines()[0])
    assert [k for k in read if any(w in k.upper() for w in ("KEY", "TOKEN", "SECRET", "PASSWORD"))] == []


def test_init_refuses_to_write_over_break_toml_without_force(tmp_path: Path) -> None:
    proj = empty(tmp_path)
    proj.settings.write_text("# mine\n", encoding="utf-8")
    ran = cli(proj, "init", "--yes", *TARGET)
    refused_once(ran, CODES["refused"])
    assert proj.settings.read_text(encoding="utf-8") == "# mine\n"


def test_with_force_init_writes_over_break_toml(tmp_path: Path) -> None:
    proj = empty(tmp_path)
    proj.settings.write_text("# mine\n", encoding="utf-8")
    ran = cli(proj, "init", "--yes", "--force", *TARGET)
    assert ran.exit == CODES["done"], ran
    assert proj.settings.read_text(encoding="utf-8") == expected(TARGET)


# ---------------------------------------------------------------------------
# the command line
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["--ru", "--forc", "--confirm-rep"])
def test_an_abbreviated_flag_is_a_mistake_on_the_command_line(tmp_path: Path, flag: str) -> None:
    proj = empty(tmp_path)
    ran = cli(proj, "init", "--yes", *TARGET, flag, "5")
    refused_once(ran, CODES["usage"])
    assert not proj.settings.exists()
    whole = {"--ru": ["--runs", "5"], "--forc": ["--force"], "--confirm-rep": ["--confirm-repeats", "5"]}[flag]
    assert cli(proj, "init", "--yes", *TARGET, *whole).exit == CODES["done"], "the flag written whole is taken"


def test_an_unknown_flag_is_a_mistake_on_the_command_line(tmp_path: Path) -> None:
    proj = empty(tmp_path)
    refused_once(cli(proj, "init", "--yes", *TARGET, "--bogus", "1"), CODES["usage"])
    assert not proj.settings.exists()
    assert cli(proj, "init", "--yes", *TARGET).exit == CODES["done"], "the same command without it is taken"


def test_every_flag_init_flags_names_is_taken(tmp_path: Path) -> None:
    """Each flag of `INIT_FLAGS` reaches `init`: given with a value the settings module takes, the file is that value's
    file. One `init` per flag would be slow, so the flags are given together, each off its default where it can be."""
    from poisson_break.settings import INIT_FLAGS

    named = set(INIT_FLAGS)
    given = {word for word in MANY if word.startswith("--")} | {"--kind", "--entry", "--cases", "--tool"}
    rest = sorted(named - given)
    values = {"--strategy": "random", "--control-repeats": "4", "--cases-per-condition": "3", "--candidates": "5",
              "--q": "0.04", "--max-call": "2", "--hours": "3", "--run-seconds": "60", "--retry-storm-after": "6",
              "--max-tool-calls": "30", "--max-tokens": "1000", "--outcomes": "unresolved", "--also": "gave_up",
              "--never-call": "delete_account", "--own-check": "tests.commands_targets:unresolved",
              "--vary-tools": "error,timeout", "--vary-inputs": "typos", "--vary-conversation": "repeats",
              "--vary-model": "error"}
    words = list(MANY)
    for flag in rest:
        assert flag in values, f"no value chosen for {flag}"
        words += [flag, values[flag]]
    proj = empty(tmp_path)
    ran = cli(proj, "init", "--yes", *words)
    assert ran.exit == CODES["done"], ran
    assert proj.settings.read_text(encoding="utf-8") == expected(words)
