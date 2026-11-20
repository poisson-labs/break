"""Every command the README and the docs show runs in CI, from the installed wheel, outside the
checkout.

Invariant held here (Break — Plan, the release pass):
- BK11.1  Every command the README and docs show runs in CI from the installed wheel, outside
          the checkout.

How a command is marked, and how the clean-install job takes the marked commands, is written in
`tests/release_docs.py` (rules 1 to 7, and 9 for a file a page writes). Here: every page a user
reads marks its commands by those rules; the clean-install script lists exactly the commands
the pages mark, with the wheel put in place of the requirement in an install; and a shell block
that is not marked, in each form it can take, is refused by the script, naming the file and the
line of its fence. That the listed commands then run, and pass, is the clean-install job's own
run in CI, whose results name each command by its file and line.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import REPO, guarded_env
from tests.release_docs import (
    blocks,
    commands_of,
    exit_of,
    file_of,
    marked,
    problems,
    runs,
)

SCRIPT = REPO / "scripts" / "clean_install.py"
LISTED_KEYS = {"file", "line", "kind", "command", "runs", "exit"}


def list_commands(root: Path, wheel: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    """`python scripts/clean_install.py --list-commands --wheel WHEEL`, the script of `root`."""
    return subprocess.run([sys.executable, str(root / "scripts" / "clean_install.py"),
                           "--list-commands", "--wheel", str(wheel)],
                          cwd=cwd, env=guarded_env(), stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=120)


@pytest.fixture
def wheel(tmp_path: Path) -> Path:
    """A stand-in for the wheel: the listing reads its path, never the file."""
    path = tmp_path / "dist" / "poisson_break-0.1.0-py3-none-any.whl"
    path.parent.mkdir()
    path.write_bytes(b"")
    return path


def planted_tree(tmp_path: Path, readme: str, pages: dict[str, str]) -> Path:
    """A tree of its own with the clean-install script, the package's version file, a README
    and the pages given, so a page can be planted without touching the checkout."""
    root = tmp_path / "tree"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts" / "clean_install.py")
    (root / "src" / "poisson_break").mkdir(parents=True)
    shutil.copy(REPO / "src" / "poisson_break" / "__init__.py",
                root / "src" / "poisson_break" / "__init__.py")
    (root / "README.md").write_text(readme, encoding="utf-8")
    for name, text in pages.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return root


GOOD_README = "# Poisson Break\n\n```sh\npip install poisson-break\npoisson-break catalog\n```\n"


# ---------------------------------------------------------------------------
# the pages
# ---------------------------------------------------------------------------


def test_every_page_a_user_reads_marks_its_commands_by_the_rules() -> None:
    """No fence without an info string, no shell block spelt other than `sh`, no prompt in a
    marked block, and no command shown in a block of another kind, in the README or in any page
    under `docs/` or `examples/`."""
    _, refused = marked()
    assert refused == []


# ---------------------------------------------------------------------------
# the clean-install script's listing
# ---------------------------------------------------------------------------


def test_the_clean_install_script_lists_exactly_the_marked_commands(wheel: Path,
                                                                    tmp_path: Path) -> None:
    """The commands the job runs are the commands the pages mark, by file and line, as
    written, in the pages' order, each with what is run in its place: none left out, none added,
    none reordered. The listing runs nothing and writes nothing where it is run."""
    expected, refused = marked()
    assert refused == [], "the pages refuse; the listing cannot be compared"
    folder = tmp_path / "empty"
    folder.mkdir()
    done = list_commands(REPO, wheel, folder)
    assert done.returncode == 0, done.stderr
    assert done.stderr == ""
    assert list(folder.iterdir()) == []
    listed = json.loads(done.stdout)
    assert isinstance(listed, list)
    assert all(isinstance(entry, dict) and set(entry) == LISTED_KEYS for entry in listed), listed
    assert [(e["file"], e["line"], e["kind"], e["command"]) for e in listed] == \
        [(c.file, c.line, c.kind, c.command) for c in expected]
    assert [e["runs"] for e in listed] == [runs(c, str(wheel)) for c in expected]
    assert [e["exit"] for e in listed] == [exit_of(c) for c in expected]


INSTALL_FORMS = """# Installing

```sh
# the published package, and the same with an extra
pip install poisson-break
pip3 install 'poisson-break[mcp]'
.venv/bin/python -m pip install --upgrade \\
    poisson-break
python -m pip install "poisson-break==0.1.0"
.venv/bin/python -m pip install --quiet poisson-break
uv pip install poisson-break>=0.1
pipx install poisson-break
pip install poisson-break && poisson-break catalog
pip install rich
poisson-break doctor
python -m poisson_break catalog
```
"""


def test_each_form_of_an_install_installs_the_wheel_and_nothing_else_changes(
        wheel: Path, tmp_path: Path) -> None:
    """Every way an install of `poisson-break` can be written gets the wheel, keeping its quotes
    and extras; an install of something else, and a `poisson-break` command beside an install,
    are run as written. A comment is no command, and a command continued over two lines is one
    command, listed at its first line with both lines."""
    root = planted_tree(tmp_path, GOOD_README, {"docs/install.md": INSTALL_FORMS})
    done = list_commands(root, wheel, tmp_path)
    assert done.returncode == 0, done.stderr
    listed = [e for e in json.loads(done.stdout) if e["file"] == "docs/install.md"]
    (block,) = blocks(INSTALL_FORMS, "docs/install.md")
    expected = list(commands_of(block))
    assert [(e["line"], e["command"]) for e in listed] == [(c.line, c.command) for c in expected]
    assert [e["runs"] for e in listed] == [runs(c, str(wheel)) for c in expected]
    by_command = {e["command"]: e["runs"] for e in listed}
    w = str(wheel)
    assert ".venv/bin/python -m pip install --upgrade \\\n    poisson-break" in by_command
    assert by_command[".venv/bin/python -m pip install --upgrade \\\n    poisson-break"] == \
        f".venv/bin/python -m pip install --upgrade \\\n    {w}"
    assert not any(e["command"].startswith("#") for e in listed)
    assert by_command["pip3 install 'poisson-break[mcp]'"] == f"pip3 install '{w}[mcp]'"
    assert by_command['python -m pip install "poisson-break==0.1.0"'] == f'python -m pip install "{w}"'
    assert by_command["pip install poisson-break && poisson-break catalog"] == \
        f"pip install {w} && poisson-break catalog"
    assert by_command["pip install rich"] == "pip install rich"
    assert by_command["poisson-break doctor"] == "poisson-break doctor"
    assert by_command["python -m poisson_break catalog"] == "python -m poisson_break catalog"


EXITS = """# Refusals

```sh
poisson-break catalog
poisson-break bogus  # exits 2
poisson-break findings 9 # exits 1
poisson-break hunt \\
    --name 'a b'  # exits 1
# exits 3
echo "# exits 4 is no comment here"
```
"""


def test_a_command_shown_to_be_refused_carries_the_code_it_must_exit_with(
        wheel: Path, tmp_path: Path) -> None:
    """11A-14: a marked command whose last line ends in `# exits N` is listed with `exit` N, and
    run by the job to that code; every other command and every program, 0. A comment line alone
    is no command, and the words inside quotes are no comment."""
    root = planted_tree(tmp_path, GOOD_README, {"docs/refusals.md": EXITS})
    done = list_commands(root, wheel, tmp_path)
    assert done.returncode == 0, done.stderr
    listed = [(e["command"].split("\n")[0], e["exit"]) for e in json.loads(done.stdout)
              if e["file"] == "docs/refusals.md"]
    assert listed == [("poisson-break catalog", 0), ("poisson-break bogus  # exits 2", 2),
                      ("poisson-break findings 9 # exits 1", 1), ("poisson-break hunt \\", 1),
                      ('echo "# exits 4 is no comment here"', 0)]


# ---------------------------------------------------------------------------
# an unmarked shell block is caught
# ---------------------------------------------------------------------------

UNMARKED = {
    "a fence with no info string": "```\npoisson-break hunt --yes\n```\n",
    "a fence with no info string and no command": "```\nfound  1 candidate\n```\n",
    "a bash block": "```bash\npoisson-break hunt --yes\n```\n",
    "a console block with a prompt": "```console\n$ poisson-break hunt --yes\nfound  1 candidate\n```\n",
    "a shell block": "```shell\npip install poisson-break\n```\n",
    "a text block holding a command": "```text\npoisson-break confirm --yes\nconfirmed  1 finding\n```\n",
    "a text block holding a prompt": "```text\n$ poisson-break catalog\n```\n",
    "a python block holding an install": "```python\npip install poisson-break\n```\n",
    "a toml block holding a command by its path": "```toml\n.venv/bin/poisson-break doctor\n```\n",
    "a text block holding a command after a setting": "```text\nNO_COLOR=1 poisson-break findings\n```\n",
    "a marked block with a prompt": "```sh\n$ poisson-break hunt --yes\n```\n",
    "a marked block with words after sh": "```sh skip\npoisson-break hunt --yes\n```\n",
    "a tilde fence with no info string": "~~~\ncd examples/desk\n~~~\n",
    "an indented fence in a list": "1. Run it:\n\n   ```\n   poisson-break hunt --yes\n   ```\n",
}


@pytest.mark.parametrize("form", sorted(UNMARKED))
def test_an_unmarked_shell_block_is_refused_naming_its_file_and_line(form: str, wheel: Path,
                                                                    tmp_path: Path) -> None:
    """A page with the block is refused by the listing, with nothing on stdout and a line on
    stderr that starts with the page and the line of the block's fence; the same page with the
    block marked as `sh`, or with no command in it, is taken."""
    page = "# A page\n\nSome words first.\n\n" + UNMARKED[form]
    fence = 1 + page.split("\n").index(next(line for line in page.split("\n")
                                             if line.lstrip().startswith(("```", "~~~"))))
    assert problems(blocks(page, "docs/planted.md")[0]), "the rules in release_docs take it"
    root = planted_tree(tmp_path, GOOD_README, {"docs/planted.md": page})
    done = list_commands(root, wheel, tmp_path)
    assert done.returncode == 1, (done.stdout, done.stderr)
    assert done.stdout == ""
    lines = done.stderr.splitlines()
    assert any(line.startswith(f"docs/planted.md:{fence}: ") for line in lines), lines
    assert all(line.startswith("docs/planted.md:") for line in lines), lines


def test_the_same_page_with_its_commands_marked_is_taken(wheel: Path, tmp_path: Path) -> None:
    """The control for the refusals above: a page that shows its commands in `sh` blocks and
    their output in `text` blocks is listed, so a refusal is the block's form and not the page."""
    page = ("# A page\n\nSome words first.\n\n```sh\npoisson-break hunt --yes\n```\n\n"
            "It prints:\n\n```text\nfound  1 candidate\n  next: poisson-break confirm\n```\n\n"
            "```toml\n# poisson-break init --yes writes this\n[target]\nkind = \"rollout\"\n```\n")
    root = planted_tree(tmp_path, GOOD_README, {"docs/planted.md": page})
    done = list_commands(root, wheel, tmp_path)
    assert done.returncode == 0, done.stderr
    listed = json.loads(done.stdout)
    assert [(e["file"], e["line"], e["command"]) for e in listed] == [
        ("README.md", 4, "pip install poisson-break"),
        ("README.md", 5, "poisson-break catalog"),
        ("docs/planted.md", 6, "poisson-break hunt --yes"),
    ]


def test_a_page_under_examples_is_read_too(wheel: Path, tmp_path: Path) -> None:
    """The pages under `examples/` are pages a user reads: their commands are listed and their
    unmarked blocks refused, as the docs' are."""
    root = planted_tree(tmp_path, GOOD_README, {
        "examples/desk/README.md": "# Desk\n\n```sh\npoisson-break doctor\n```\n"})
    done = list_commands(root, wheel, tmp_path)
    assert done.returncode == 0, done.stderr
    assert ("examples/desk/README.md", 4) in {(e["file"], e["line"]) for e in json.loads(done.stdout)}
    root2 = planted_tree(tmp_path / "two", GOOD_README, {
        "examples/desk/README.md": "# Desk\n\n```\npoisson-break doctor\n```\n"})
    done = list_commands(root2, wheel, tmp_path)
    assert done.returncode == 1
    assert done.stderr.startswith("examples/desk/README.md:3: ")


# ---------------------------------------------------------------------------
# a file the page writes (rule 9)
# ---------------------------------------------------------------------------

FILES = '''# A page that writes its files

```sh
mkdir shop
cd shop
```

```python file=shop.py
STOCK = {"dune": 3}


def shop(cfg, seed):
    return STOCK
```

```json file=cases.jsonl
{"id": "dune", "input": "Can you hold dune for me?"}
```

```sh
cat shop.py cases.jsonl
```
'''


def test_a_file_block_is_listed_where_it_stands_and_what_runs_writes_it(wheel: Path,
                                                                      tmp_path: Path) -> None:
    """Rule 9: a block tagged `LANGUAGE file=NAME` is a file the page writes. It is listed among
    the page's commands at the first line of its content, with `kind` `file`, its lines as
    `command`, and as `runs` the shell text that writes them to NAME; run in the page's one
    shell, that text writes the block's lines, each ended by a line break, into the folder the
    shell is in, before the next command. The listing and the rules in `release_docs` agree."""
    root = planted_tree(tmp_path, GOOD_README, {"docs/files.md": FILES})
    done = list_commands(root, wheel, tmp_path)
    assert done.returncode == 0, done.stderr
    listed = [e for e in json.loads(done.stdout) if e["file"] == "docs/files.md"]
    assert [(e["line"], e["kind"]) for e in listed] == [
        (4, "sh"), (5, "sh"), (9, "file"), (17, "file"), (21, "sh")]
    shown = blocks(FILES, "docs/files.md")
    assert [b for b in shown if problems(b)] == []
    files = [b for b in shown if b.language != "sh"]
    assert [e["command"] for e in listed if e["kind"] == "file"] == ["\n".join(b.lines) for b in files]
    expected = [c for b in shown for c in (commands_of(b) if b.info == "sh" else [file_of(b)])]
    assert [(e["line"], e["kind"], e["command"]) for e in listed] == \
        [(c.line, c.kind, c.command) for c in expected]
    assert [e["runs"] for e in listed] == [runs(c, str(wheel)) for c in expected]
    assert [e["exit"] for e in listed] == [0] * 5

    here = tmp_path / "page"
    here.mkdir()
    ran = subprocess.run(["bash", "-e", "-c", "\n".join(e["runs"] for e in listed)], cwd=here,
                         capture_output=True, text=True, timeout=60)
    assert ran.returncode == 0, ran.stderr
    for block, name in zip(files, ("shop.py", "cases.jsonl"), strict=True):
        assert (here / "shop" / name).read_text(encoding="utf-8") == "\n".join(block.lines) + "\n"
    assert ran.stdout == "".join("\n".join(b.lines) + "\n" for b in files)


@pytest.mark.parametrize("info", ["python file=", "python file=../shop.py", "python file=a/b.py",
                                  "json file=.hidden", "python file=shop.py file=two.py"])
def test_a_file_block_with_a_name_that_is_no_plain_file_name_is_refused(
        info: str, wheel: Path, tmp_path: Path) -> None:
    """A file block names one plain file in the page's folder: no folder, no `..`, no hidden
    file, one name. Any other is refused by the listing and by the rules, at the block's fence."""
    page = f"# A page\n\n```{info}\nSTOCK = 1\n```\n"
    assert problems(blocks(page, "docs/planted.md")[0]) != []
    root = planted_tree(tmp_path, GOOD_README, {"docs/planted.md": page})
    done = list_commands(root, wheel, tmp_path)
    assert done.returncode == 1, (done.stdout, done.stderr)
    assert done.stdout == ""
    assert done.stderr.splitlines() and all(
        line.startswith("docs/planted.md:3: ") for line in done.stderr.splitlines()), done.stderr


# ---------------------------------------------------------------------------
# the rollout page's whole agent
# ---------------------------------------------------------------------------

ROLLOUT = REPO / "docs" / "ways-in" / "rollout.md"
WHOLE = "A whole agent to start from"


def _whole() -> list:
    """The blocks of the rollout page's section that shows a whole agent, in order."""
    text = ROLLOUT.read_text(encoding="utf-8")
    lines = text.split("\n")
    start = lines.index(f"## {WHOLE}") + 1
    end = next((n for n in range(start, len(lines)) if lines[n].startswith("## ")), len(lines))
    return [b for b in blocks(text, "docs/ways-in/rollout.md") if start < b.fence_line <= end]


def test_the_rollout_page_shows_a_whole_agent_its_cases_and_the_commands_to_a_hunt() -> None:
    """The section shows two files, `shop.py` and `cases.jsonl`, and then the commands, with no
    output: the agent imports nothing but `re` and Prove's `Episode`, so it needs no model and no
    key and holds no Break line (ruling 15 of the wrapping at load spec, and Taylor's yes of
    2026-11-20 that this test changes by it), and is a function `shop(cfg, seed)`; the case file is three cases, each
    with `id`, `input` and `expect.reply_contains`; `init` is shown by its flags alone, and the
    last command is the hunt. The page links the section from its top."""
    import ast

    found = _whole()
    assert [b.info for b in found] == ["sh", "python file=shop.py", "json file=cases.jsonl", "sh"]
    agent = ast.parse("\n".join(found[1].lines))
    imported = {node.module if isinstance(node, ast.ImportFrom) else alias.name
                for node in ast.walk(agent) if isinstance(node, ast.Import | ast.ImportFrom)
                for alias in node.names}
    assert imported == {"re", "poisson_prove"}, imported
    (shop,) = [n for n in agent.body if isinstance(n, ast.FunctionDef) and n.name == "shop"]
    assert [a.arg for a in shop.args.args] == ["cfg", "seed"]
    cases = [json.loads(line) for line in found[2].lines]
    assert len(cases) == 3
    assert all(set(case) == {"id", "input", "expect"} and set(case["expect"]) == {"reply_contains"}
               for case in cases), cases
    shown = [c.command.replace("\\\n", " ") for c in commands_of(found[3])]
    assert [" ".join(c.split()[:2]) for c in shown] == \
        ["poisson-break init", "poisson-break doctor", "poisson-break hunt"]
    assert "--entry shop:shop" in shown[0] and "--cases cases.jsonl" in shown[0]
    assert shown[0].endswith("--yes") and shown[2] == "poisson-break hunt --yes"
    assert f"](#{WHOLE.lower().replace(' ', '-')})" in ROLLOUT.read_text(encoding="utf-8")


def test_the_rollout_page_s_whole_agent_runs_as_printed_to_a_hunt(tmp_path: Path) -> None:
    """What the section shows, run as the clean install runs it, in an empty folder under the
    network guard with no key: every command exits 0, `init` classes the two tools, one `read`
    and one `write`, each with the place Break wraps it at when it loads the agent (ruling 15 of
    the wrapping at load spec, and Taylor's yes of 2026-11-20 that this test changes by it), and
    the hunt stores its runs."""
    import tomllib

    from tests.conftest import console_script

    found = _whole()
    shown = [c for b in found for c in (commands_of(b) if b.info == "sh" else [file_of(b)])]
    env = guarded_env()
    env["PATH"] = f"{console_script().parent}{os.pathsep}{env.get('PATH', '')}"
    ran = subprocess.run(["bash", "-e", "-c", "\n".join(runs(c, "poisson-break") for c in shown)],
                         cwd=tmp_path, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                         text=True, timeout=600)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    folder = tmp_path / "shop"
    with (folder / "break.toml").open("rb") as f:
        tools = tomllib.load(f)["tools"]
    assert tools == {"check_stock": {"class": "read", "at": "shop:check_stock"},
                     "hold_copy": {"class": "write", "repeatable": True, "at": "shop:hold_copy"}}
    stored = list((folder / "break-runs").glob("*/store/*/episodes/*"))
    assert stored, sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*"))
