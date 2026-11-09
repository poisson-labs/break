"""What the release tests read: the files a user reads, the fenced blocks in them, and the
commands those blocks mark. Read by the release tests (`tests/test_release_*.py`); it holds no
test itself.

**How a command is marked** (the release pass, BK11.1):

1. Every fenced block in `README.md`, in a page under `docs/` and in a page under `examples/`
   opens with an info string. A fence with none is refused, whatever it holds.
2. A block whose info string is exactly `sh` holds marked commands. Each of its lines that is
   neither blank nor a comment (`#` its first character that is not a space) is a command; a
   line that ends in a backslash goes on onto the next. A line that starts with a prompt
   (`$ `, `% `, `> `) is refused: what is marked is what runs, as written.
3. `sh` is the one spelling. A block tagged with another shell's name (`bash`, `shell`,
   `console`, `zsh` and the rest of `OTHER_SHELLS`), or `sh` followed by anything, is refused.
4. A block of any other language holding a line that starts with a command word, at its first
   character or after a prompt, is an unmarked shell block, and is refused. The command words
   are `COMMAND_WORDS`, a path before the word (`.venv/bin/poisson-break`) and settings before
   it (`NO_COLOR=1 poisson-break`) included. A comment in TOML or Python starts with `#`, so a
   command written in one is not a command shown.
5. The clean-install job runs every marked command from the installed wheel, outside the
   checkout: each file's commands in the file's order, in one shell, each command required to
   exit 0, or N when its last line ends in the comment `# exits N` (ruling 11A-14), in a fresh
   empty folder of the file's own, with a HOME of its own and no variable whose name says key,
   token, secret or password. In an install command (`pip`, `pip3`, `uv pip`, `pipx`, or
   `python -m pip`, followed by `install`), a word that names the requirement `poisson-break`
   (quoted or not, with extras or not, with a version or not) installs the wheel instead: the
   word keeps its quotes and its extras, and the name and version become the wheel's path.
6. Each extension-point page (the one page under `docs/` that names an interface's version
   constant and no other interface's) has its Python blocks, in order, as one program, which the
   same job writes to `example.py` in a fresh folder of its own and runs there with the
   environment's Python (`python example.py`), so a page that names its own module by an import
   path names it `example`.
7. `python scripts/clean_install.py --list-commands --wheel WHEEL` prints, and runs nothing, one
   JSON list on stdout: per marked command, then per extension page's program, an object with
   exactly `file` (from the checkout, with `/`), `line` (the first line of the command, or of the
   page's first Python block's content, counted from 1), `kind` (`sh` or `python`), `command`
   (its lines as written, the block's indentation taken off, joined by a newline), `runs`
   (what is run: `command` with the install words of 5 put in) and `exit` (the code it must
   exit with: N from `# exits N`, else 0; 0 for a program). `README.md` comes first, then
   every other file by its path; within a file, by line. A refused block makes it exit 1 with
   nothing on stdout and one line per refusal on stderr, each starting `FILE:LINE: `, the line
   of the block's opening fence.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from tests.conftest import REPO

#: The other names a shell block is tagged with; `sh` is the one spelling.
OTHER_SHELLS = frozenset({
    "bash", "shell", "console", "zsh", "shell-session", "sh-session", "shellsession",
    "terminal", "fish", "ksh", "csh", "tcsh", "powershell", "pwsh", "ps1", "ps", "cmd", "bat",
    "batch", "dos", "sh-",
})

#: A line that starts with one of these, after a prompt, settings or a path, is a command.
COMMAND_WORDS = frozenset({
    "poisson-break", "python", "python3", "pip", "pip3", "pipx", "uv", "uvx", "cd", "git",
    "curl", "wget", "export", "source", ".", "mkdir", "cp", "mv", "rm", "ls", "cat", "echo",
    "chmod", "touch", "tar", "unzip", "env", "sudo", "brew", "conda", "poetry", "hatch",
    "pytest",
})

_FENCE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
_PROMPT = re.compile(r"^(?:\$|%|>)\s")
_SETTING = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*$")
_PYTHON = re.compile(r"^python(?:3(?:\.\d+)?)?$")


@dataclass(frozen=True)
class Block:
    """One fenced block: where it opens, its info string, and its lines as written, the
    block's indentation taken off."""

    file: str
    fence_line: int
    info: str
    lines: tuple[str, ...]

    @property
    def language(self) -> str:
        return self.info.split()[0] if self.info.split() else ""

    @property
    def first_line(self) -> int:
        """The file's line number of the block's first line of content."""
        return self.fence_line + 1


@dataclass(frozen=True)
class Command:
    file: str
    line: int
    kind: str
    command: str


class Unclosed(ValueError):
    pass


def user_docs() -> list[Path]:
    """The pages a user reads, in the order the clean-install job takes them: `README.md` first,
    then every page under `docs/` and `examples/` by its path."""
    pages = [REPO / "README.md"]
    for top in ("docs", "examples"):
        root = REPO / top
        if root.exists():
            pages += sorted(p for p in root.rglob("*.md") if p.is_file())
    return [pages[0]] + sorted(pages[1:], key=lambda p: p.relative_to(REPO).as_posix())


def rel(path: Path, root: Path = REPO) -> str:
    return path.relative_to(root).as_posix()


def blocks(text: str, file: str) -> list[Block]:
    """Every fenced block in a Markdown text, in order. A fence that is never closed is
    refused, since what follows it would be read as code."""
    found: list[Block] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        opening = _FENCE.match(lines[i])
        if not opening or (opening["fence"][0] == "`" and "`" in opening["info"]):
            i += 1
            continue
        indent, fence, info = opening["indent"], opening["fence"], opening["info"].strip()
        body: list[str] = []
        j = i + 1
        while j < len(lines):
            closing = _FENCE.match(lines[j])
            if (closing and closing["fence"][0] == fence[0] and len(closing["fence"]) >= len(fence)
                    and not closing["info"].strip()):
                break
            line = lines[j]
            body.append(line[len(indent):] if line.startswith(indent) else line.lstrip())
            j += 1
        else:
            raise Unclosed(f"{file}:{i + 1}: a fence that is never closed")
        found.append(Block(file, i + 1, info, tuple(body)))
        i = j + 1
    return found


def looks_like_a_command(line: str) -> bool:
    """Whether a line, as written at the start of a block's line, starts with a command word:
    after a prompt, after settings such as `NO_COLOR=1`, with a path before the word or not."""
    if not line or line[0].isspace():
        return False
    rest = _PROMPT.sub("", line, count=1)
    try:
        words = shlex.split(rest, comments=False, posix=True)
    except ValueError:
        words = rest.split()
    while words and _SETTING.match(words[0]):
        words = words[1:]
    if not words:
        return False
    word = words[0]
    base = word.rsplit("/", 1)[-1] if word not in (".",) else word
    return base in COMMAND_WORDS or bool(_PYTHON.match(base))


def problems(block: Block) -> list[str]:
    """Why a block is refused under the marking rules, each as `FILE:LINE: what`; empty for a
    block the rules take."""
    at = f"{block.file}:{block.fence_line}: "
    if not block.info:
        return [at + "a fenced block with no info string"]
    if block.info == "sh":
        bad = [n for n, line in enumerate(block.lines) if _PROMPT.match(line.lstrip())]
        return [at + f"a prompt in a marked block, its line {n + 1}" for n in bad]
    if block.language == "sh" or block.language.lower() in OTHER_SHELLS:
        return [at + f"a shell block tagged {block.info!r}, not sh"]
    shown = [n for n, line in enumerate(block.lines) if looks_like_a_command(line)]
    return [at + f"an unmarked shell block: its line {n + 1} is a command" for n in shown]


def commands_of(block: Block) -> Iterator[Command]:
    """The marked commands of an `sh` block, each at the file's line it starts on."""
    pending: list[str] = []
    start = 0
    for n, line in enumerate(block.lines):
        stripped = line.strip()
        if not pending and (not stripped or stripped.startswith("#")):
            continue
        if not pending:
            start = block.first_line + n
        pending.append(line)
        if not line.rstrip().endswith("\\"):
            yield Command(block.file, start, "sh", "\n".join(pending))
            pending = []
    if pending:
        yield Command(block.file, start, "sh", "\n".join(pending))


#: The four interfaces' version constants, each named by the one page that documents it.
INTERFACE_CONSTANTS = ("FAULT_INTERFACE_VERSION", "TARGET_INTERFACE_VERSION",
                       "STRATEGY_INTERFACE_VERSION", "CHECK_INTERFACE_VERSION")


def extension_pages(root: Path = REPO) -> dict[str, list[Path]]:
    """For each interface's version constant, the pages under `docs/` that name it and no other
    interface's constant (a page naming several is an overview, not an interface's page)."""
    pages = sorted((root / "docs").rglob("*.md")) if (root / "docs").exists() else []
    named = {p: {c for c in INTERFACE_CONSTANTS if c in p.read_text(encoding="utf-8")}
             for p in pages}
    return {name: [p for p in pages if named[p] == {name}] for name in INTERFACE_CONSTANTS}


def python_program(page: Path, root: Path = REPO) -> Command | None:
    """An extension page's Python blocks, in order, as one program."""
    found = [b for b in blocks(page.read_text(encoding="utf-8"), rel(page, root))
             if b.info == "python"]
    if not found:
        return None
    return Command(rel(page, root), found[0].first_line, "python",
                   "\n".join("\n".join(b.lines) for b in found))


def marked(root: Path = REPO) -> tuple[list[Command], list[str]]:
    """Every marked command and every extension page's program, in the order of rule 7, and
    every refusal."""
    commands: list[Command] = []
    refused: list[str] = []
    pages = user_docs() if root == REPO else _docs_under(root)
    constants = {p for named in extension_pages(root).values() for p in named}
    for page in pages:
        name = rel(page, root)
        try:
            found = blocks(page.read_text(encoding="utf-8"), name)
        except Unclosed as wrong:
            refused.append(str(wrong))
            continue
        for block in found:
            refused += problems(block)
            if block.info == "sh":
                commands += commands_of(block)
        if page in constants:
            program = python_program(page, root)
            if program is not None:
                commands.append(program)
    commands.sort(key=lambda c: (c.file != "README.md", c.file, c.line))
    return commands, refused


def _docs_under(root: Path) -> list[Path]:
    pages = [root / "README.md"]
    for top in ("docs", "examples"):
        if (root / top).exists():
            pages += sorted(p for p in (root / top).rglob("*.md") if p.is_file())
    return pages


_EXITS = re.compile(r"#\s*exits\s+(\d+)\s*$")


def exit_of(command: Command) -> int:
    """The code a marked command must exit with (rule 5): N from a last line that ends in
    `# exits N`, else 0."""
    if command.kind != "sh":
        return 0
    found = _EXITS.search(command.command.split("\n")[-1])
    return int(found.group(1)) if found else 0


_INSTALLER = re.compile(r"^(?:pip3?|pipx)$")
_REQUIREMENT = re.compile(
    r"""^(?P<q>['"]?)poisson-break(?P<extras>\[[^\]]*\])?(?:\s*(?:===|==|>=|<=|~=|!=|<|>)[^'"\s]+)?(?P=q)$""")


def install_words(words: list[str]) -> bool:
    """Whether a command's words, settings taken off, are an install: `pip install`,
    `pip3 install`, `pipx install`, `uv pip install`, `python -m pip install`, a path before the
    program or not."""
    while words and _SETTING.match(words[0]):
        words = words[1:]
    if not words:
        return False
    head = words[0].rsplit("/", 1)[-1]
    if _INSTALLER.match(head):
        return len(words) > 1 and words[1] == "install"
    if head == "uv":
        return words[1:3] == ["pip", "install"]
    if _PYTHON.match(head):
        return words[1:4] == ["-m", "pip", "install"]
    return False


def runs(command: Command, wheel: str) -> str:
    """What the clean-install job runs for a marked command (rule 5)."""
    if command.kind != "sh":
        return command.command
    out = []
    for piece in re.split(r"(&&|\|\||;|\|)", command.command):
        try:
            words = shlex.split(piece.replace("\\\n", " "))
        except ValueError:
            out.append(piece)
            continue
        if not install_words(list(words)):
            out.append(piece)
            continue
        tokens = re.split(r"(\s+)", piece)
        replaced = []
        for token in tokens:
            match = _REQUIREMENT.match(token)
            if match:
                token = f"{match['q']}{wheel}{match['extras'] or ''}{match['q']}"
            replaced.append(token)
        out.append("".join(replaced))
    return "".join(out)


def is_break_install(command: Command) -> bool:
    """Whether a marked command installs the requirement `poisson-break`."""
    if command.kind != "sh":
        return False
    joined = command.command.replace("\\\n", " ")
    for piece in re.split(r"&&|\|\||;|\|", joined):
        try:
            words = shlex.split(piece)
        except ValueError:
            continue
        if install_words(list(words)) and any(_REQUIREMENT.match(t) for t in piece.split()):
            return True
    return False


def break_verb(command: Command) -> str | None:
    """The verb of a marked `poisson-break VERB ...` command, or None."""
    if command.kind != "sh":
        return None
    try:
        words = shlex.split(command.command.replace("\\\n", " "))
    except ValueError:
        return None
    while words and _SETTING.match(words[0]):
        words = words[1:]
    if not words or words[0].rsplit("/", 1)[-1] != "poisson-break":
        return None
    rest = [w for w in words[1:] if w not in ("--plain", "--debug")]
    return rest[0] if rest and not rest[0].startswith("-") else None
