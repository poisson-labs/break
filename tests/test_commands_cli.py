"""What holds for every verb: the command line, the names the command imports, and its help.

Invariants held here (Break — Plan, the commands module and BK0; spec §9.1):
- BK8.8   The CLI imports only public names, checked by reading its source: every name it takes from a module of Break
          is in that module's `__all__`, it reaches no name that starts with an underscore on a module of Break, Prove or
          Trace, and it imports no private module. The source read is `cli.py` and every module of the package that
          `cli.py` reaches and that is not one of the library's own modules, so the check follows the command wherever
          the build puts it.
- §9.1    A verb's own options follow the verb, and only the tool's own (`--plain`, `--debug`) may come first; no
          abbreviated flag; an unknown verb or flag is one `error:` line and exit 2.
- BK0.2   `main(argv, prog=P)` renders every command it names from `P`: each verb's help.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from tests.commands_support import CODES, PROG, VERBS, cli, nexts, project, refused_once, verdict
from tests.conftest import REPO
from tests.look_support import strip

PACKAGE = REPO / "src" / "poisson_break"
#: The library's own modules, each built and tested by its own module's sessions; the command is everything else.
LIBRARY = {"look", "_pretty", "settings", "hunt", "search", "confirm", "changes", "checks", "apply", "records",
           "interfaces"}
OURS = ("poisson_break", "poisson_prove", "poisson_trace")


def _command_modules() -> list[Path]:
    """`cli.py`, and each module of the package it imports, at any depth, that is not one of the library's."""
    seen: list[Path] = []
    todo = [PACKAGE / "cli.py"]
    while todo:
        path = todo.pop()
        if path in seen or not path.exists():
            continue
        seen.append(path)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("poisson_break"):
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names if a.name.startswith("poisson_break")]
            for name in names:
                parts = name.split(".")[1:]
                if not parts or parts[0] in LIBRARY:
                    continue
                for candidate in (PACKAGE.joinpath(*parts).with_suffix(".py"), PACKAGE.joinpath(*parts, "__init__.py")):
                    if candidate.exists():
                        todo.append(candidate)
    return seen


def _violations(source: str) -> list[str]:
    wrong: list[str] = []
    tree = ast.parse(source)
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in OURS:
                    if any(part.startswith("_") for part in alias.name.split(".")[1:]):
                        wrong.append(f"imports the private module {alias.name}")
                    aliases[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in OURS:
            parts = node.module.split(".")
            if any(part.startswith("_") for part in parts[1:]):
                wrong.append(f"imports from the private module {node.module}")
                continue
            for alias in node.names:
                if alias.name.startswith("__") and alias.name.endswith("__"):
                    continue  # a dunder such as __version__ is the package's own public face
                if alias.name.startswith("_"):
                    wrong.append(f"imports the private name {node.module}.{alias.name}")
                    continue
                if parts[0] == "poisson_break":
                    module = importlib.import_module(node.module)
                    submodule = f"{node.module}.{alias.name}"
                    is_module = importlib.util.find_spec(submodule) is not None if node.module == "poisson_break" else False
                    if is_module:
                        aliases[alias.asname or alias.name] = submodule
                    elif alias.name not in getattr(module, "__all__", ()):
                        wrong.append(f"imports {alias.name} from {node.module}, which is not in its __all__")
                    else:
                        value = getattr(module, alias.name, None)
                        if isinstance(value, type(importlib)):
                            aliases[alias.asname or alias.name] = value.__name__
                else:
                    aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("_") and not node.attr.startswith("__"):
            base = node.value
            if isinstance(base, ast.Name) and base.id in aliases:
                wrong.append(f"reaches {aliases[base.id]}.{node.attr}")
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases:
            target = aliases[node.value.id]
            if target.startswith("poisson_break.") and target.split(".")[1] in LIBRARY:
                module = importlib.import_module(target)
                if not node.attr.startswith("_") and node.attr not in getattr(module, "__all__", ()):
                    wrong.append(f"reaches {target}.{node.attr}, which is not in its __all__")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("getattr", "__import__"):
            for arg in node.args[1:2]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("_"):
                    wrong.append(f"reaches a private name through {node.func.id}: {arg.value}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "import_module":
            for arg in node.args[:1]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and any(
                        p.startswith("_") for p in arg.value.split(".")[1:]) and arg.value.split(".")[0] in OURS:
                    wrong.append(f"imports the private module {arg.value} at run time")
    return wrong


def test_the_command_imports_only_public_names() -> None:
    modules = _command_modules()
    assert modules and modules[0].name == "cli.py"
    wrong = [f"{path.name}: {what}" for path in modules for what in _violations(path.read_text(encoding="utf-8"))]
    assert wrong == []


def test_the_command_imports_the_library_it_drives() -> None:
    """The check above holds something: the command takes names from the modules the eight verbs are built on."""
    reached: set[str] = set()
    for path in _command_modules():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module == "poisson_break":
                reached |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("poisson_break."):
                reached.add(node.module.split(".")[1])
            elif isinstance(node, ast.Import):
                reached |= {a.name.split(".")[1] for a in node.names if a.name.startswith("poisson_break.")}
    assert {"look", "settings", "hunt", "search", "confirm", "changes"} <= reached, reached


@pytest.mark.parametrize("source, found", [
    ("from poisson_break.hunt import _run_unstored", "private name"),
    ("from poisson_break import hunt\nhunt._run_unstored()", "reaches poisson_break.hunt._run_unstored"),
    ("import poisson_break.hunt as h\nh._spent", "reaches poisson_break.hunt._spent"),
    ("from poisson_break._pretty import result", "private module"),
    ("from poisson_break.confirm import CONFIRM_SCHEMA", "not in its __all__"),
    ("from poisson_prove._store import Store", "private module"),
    ("from poisson_break import look\nlook._show(1)", "reaches poisson_break.look._show"),
    ("getattr(x, '_spent')", "through getattr"),
    ("from poisson_break import confirm\nconfirm.CONFIRM_SCHEMA", "not in its __all__"),
    # BK8 points 37, 39 and 40 (2026-11-07): the private names the three new public ones replace
    ("from poisson_break.settings import _WAYS_IN", "private name"),
    ("from poisson_break import settings\nsettings._WAYS_IN['mcp']", "reaches poisson_break.settings._WAYS_IN"),
    ("from poisson_break.settings import _module_is_there", "private name"),
    ("import poisson_break.settings as s\ns._module_is_there('x')", "reaches poisson_break.settings._module_is_there"),
    ("import poisson_break.hunt as h\nh._run_unstored()", "reaches poisson_break.hunt._run_unstored"),
    ("from poisson_break.hunt import _rows_of", "private name"),
    ("from poisson_break import confirm\nconfirm._Stored(h).rows('a')", "reaches poisson_break.confirm._Stored"),
])
def test_the_check_finds_each_way_a_private_name_is_reached(source: str, found: str) -> None:
    """The check can fail: each of these, in a command's source, is named."""
    assert any(found in what for what in _violations(source)), _violations(source)


def test_the_check_takes_the_three_public_names_the_rulings_add() -> None:
    """BK8 points 37, 39 and 40 (2026-11-07): `hunt.run_once`, `settings.install_command` and `Replayed.error` are what
    the command reaches instead, each a public name of its module."""
    clean = ("from poisson_break.hunt import run_once\nfrom poisson_break.settings import install_command\n"
             "from poisson_break.confirm import Replayed\nimport poisson_break.hunt as h\nh.run_once\n"
             "from poisson_break import settings\nsettings.install_command\n")
    assert _violations(clean) == []


def test_the_check_takes_public_names() -> None:
    clean = ("from poisson_break import look, __version__\nfrom poisson_break.hunt import open_hunt, HuntStopped\n"
             "import poisson_break.confirm as c\nc.confirm\nlook.show\n")
    assert _violations(clean) == []


# ---------------------------------------------------------------------------
# the command line
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("words", [["--json", "catalog"], ["--yes", "hunt"], ["--dry-run", "hunt"],
                                   ["--hunt", "desk-1", "findings"], ["--name", "x", "hunt"], ["--force", "init"]])
def test_a_verb_s_own_option_before_the_verb_is_a_mistake_on_the_command_line(tmp_path: Path,
                                                                             words: list[str]) -> None:
    """The control: the same words with the verb first are no mistake on the command line."""
    proj = project(tmp_path)
    refused_once(cli(proj, *words), CODES["usage"])
    assert proj.runs() == []
    verb_first = [words[-1], *words[:-1], *(["--dry-run"] if words[-1] == "hunt" else [])]
    if words[-1] == "init":
        verb_first += ["--yes", "--kind", "rollout", "--entry", "tests.commands_targets:desk"]
    assert cli(proj, *verb_first).exit != CODES["usage"], verb_first


@pytest.mark.parametrize("flag", ["--plain", "--debug"])
def test_the_tool_s_own_options_may_come_before_or_after_the_verb(tmp_path: Path, flag: str) -> None:
    proj = project(tmp_path)
    before = cli(proj, flag, "catalog")
    after = cli(proj, "catalog", flag)
    assert before.exit == after.exit == CODES["done"], (before, after)
    assert before.out == after.out
    assert verdict(before)[0] == "ok"


@pytest.mark.parametrize("words", [["hunt", "--dry"], ["catalog", "--js"], ["recheck", "--chec"], ["confirm", "--rep", "2"],
                                   ["findings", "--hu", "x"], ["hunt", "--na", "x"]])
def test_an_abbreviated_option_is_a_mistake_on_the_command_line(tmp_path: Path, words: list[str]) -> None:
    """The control: the option written whole is taken."""
    proj = project(tmp_path)
    refused_once(cli(proj, *words), CODES["usage"])
    assert proj.runs() == []
    whole = {"--dry": "--dry-run", "--js": "--json", "--chec": "--check", "--rep": "--repeats", "--hu": "--hunt",
             "--na": "--name"}
    written = [whole.get(w, w) for w in words] + (["--dry-run"] if words[0] in ("recheck", "confirm") or
                                                   (words[0] == "hunt" and "--dry-run" not in
                                                    [whole.get(w, w) for w in words]) else [])
    assert cli(proj, *written).exit != CODES["usage"], written


@pytest.mark.parametrize("words", [["hunts"], ["catalogue"], ["catalog", "--bogus"], ["findings", "one"]])
def test_an_unknown_verb_flag_or_value_is_one_line_and_exit_2(tmp_path: Path, words: list[str]) -> None:
    """The control: `catalog` and `findings` themselves are known verbs."""
    proj = project(tmp_path)
    refused_once(cli(proj, *words), CODES["usage"])
    assert cli(proj, "catalog").exit == CODES["done"]


#: A mistake in each verb's own options or arguments, which that verb's parser finds.
_VERB_MISTAKES = {
    "init": ["init", "--bogus"],
    "doctor": ["doctor", "--run=yes"],
    "hunt": ["hunt", "--name"],
    "confirm": ["confirm", "--repeats", "zero"],
    "findings": ["findings", "one"],
    "replay": ["replay"],
    "recheck": ["recheck", "--old"],
    "catalog": ["catalog", "--labels=all"],
}


@pytest.mark.parametrize("where", ["alone", "--plain first", "--debug last"])
@pytest.mark.parametrize("verb", VERBS)
def test_a_mistake_in_a_verb_s_own_words_names_that_verb_s_help(tmp_path: Path, verb: str, where: str) -> None:
    """Hands-on issue 18: the `next:` line of a mistake the verb's parser finds is that verb's `--help`, where the
    option or argument is described, with the tool's own options before or after the verb; run as printed, it
    prints that verb's help."""
    proj = project(tmp_path)
    words = _VERB_MISTAKES[verb]
    if where == "--plain first":
        words = ["--plain", *words]
    elif where == "--debug last":
        words = [*words, "--debug"]
    ran = cli(proj, *words)
    refused_once(ran, CODES["usage"])
    assert nexts(ran) == [f"{PROG} {verb} --help"], ran
    again = cli(proj, verb, "--help")
    assert again.exit == CODES["done"] and f"{PROG} {verb}" in strip(again.out), again
    assert proj.runs() == []


@pytest.mark.parametrize("words", [["hunts"], ["--bogus"], ["--bogus", "catalog"], ["--version=2"]],
                         ids=["an unknown verb", "an unknown option and no verb",
                              "an unknown option before a verb", "the tool's own option given a value"])
def test_a_mistake_before_any_verb_names_the_tool_s_help(tmp_path: Path, words: list[str]) -> None:
    """The control: with no verb named, or a verb the command does not know, the line stays the tool's `--help`."""
    proj = project(tmp_path)
    ran = cli(proj, *words)
    refused_once(ran, CODES["usage"])
    assert nexts(ran) == [f"{PROG} --help"], ran


# ---------------------------------------------------------------------------
# each verb's help
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verb", VERBS)
@pytest.mark.parametrize("prog", [PROG, "poisson break"])
def test_each_verb_s_help_names_its_commands_from_the_name_it_was_run_under(tmp_path: Path, verb: str,
                                                                           prog: str) -> None:
    ran = cli(project(tmp_path), verb, "--help", prog=prog)
    assert ran.exit == CODES["done"], ran
    text = strip(ran.out)
    assert f"{prog} {verb}" in text, text
    if prog != PROG:
        assert PROG not in text, text


def test_the_tool_s_help_names_every_verb(tmp_path: Path) -> None:
    text = strip(cli(project(tmp_path), "--help").out)
    for verb in VERBS:
        assert verb in text, verb
