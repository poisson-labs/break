"""The output the pages show is the output their commands print, byte for byte.

Three pages show what their commands print: the examples' page (`examples/README.md`), "Reading a
finding" (`docs/findings.md`) and "Checking a fix" (`docs/recheck.md`). The clean-install job
runs every marked command and holds its exit code; nothing held what the pages say the commands
print. Here every command of each page is run and every block of output the page shows is
compared with what was printed.

**How it is run.** The wheel is built from this tree and installed, with pip and no index, into
a fresh environment outside the checkout. Break's own dependencies are not fetched: the fresh
environment reads them from the test environment's packages, through one path line, after its
own, so the package under test is the wheel's and the import is checked to be. Each page's
commands run in the page's order, in one shell, in a fresh empty folder of the page's own with a
HOME of its own, no terminal, no variable whose name says key, token, secret or password, and
the network guard on, logging: no connection is attempted. Each command must exit with the code
the page gives it (`release_docs.exit_of`).

**What a command printed** is its two streams as a terminal shows them, in the order written
(`2>&1`), less every `next:` line that holds the full path of the folder it ran in: a page cannot
print the path of the machine it was written on, and says so.

**What a block must be.** A block tagged `text` or `json` shows the output of one command of the
`sh` block before it. It must be, byte for byte, either all that the command printed or all of
it from the first line of its last result (a verb that asks first prints its plan and a note,
then its result; a page may show the result alone). Nothing else may be left out, at either
end or in the middle. The blocks after one `sh` block show its commands in the commands' order.

**The file the page shows.** "Reading a finding" shows a finding's file in a `toml` block. It
must be the bytes of the file the commands wrote, with the store's full path, which the page
cannot print, written as the page says it writes it.
"""

from __future__ import annotations

import difflib
import os
import shlex
import subprocess
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests import release_docs as docs
from tests.conftest import REPO, guarded_env
from tests.look_support import VERDICT_LINE

PROBE = REPO / "tests" / "release_probe"
#: The pages whose shown output is held, each with the blocks of output it shows.
PAGES = {"examples/README.md": 11, "docs/findings.md": 5, "docs/recheck.md": 2}
#: The languages a block of output is tagged with.
OUTPUT = ("text", "json")
#: How "Reading a finding" writes the store's path in the file it shows.
STORE_PLACEHOLDER = "<the hunt's store, as a full path>"


# ---------------------------------------------------------------------------
# the wheel, installed outside the checkout
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The fresh environment's `bin`, with the wheel built from this tree installed in it."""
    out = tmp_path_factory.mktemp("wheel")
    built = subprocess.run([sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(out)],
                           cwd=REPO, capture_output=True, text=True, timeout=300)
    assert built.returncode == 0, built.stdout + built.stderr
    (wheel,) = out.glob("*.whl")
    venv = tmp_path_factory.mktemp("fresh") / "venv"
    assert REPO not in venv.parents, "the fresh environment is outside the checkout"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, timeout=300)
    python = venv / "bin" / "python"
    done = subprocess.run([str(python), "-m", "pip", "install", "--quiet", "--no-index", "--no-deps",
                           "--disable-pip-version-check", str(wheel)],
                          capture_output=True, text=True, timeout=300, env=guarded_env())
    assert done.returncode == 0, done.stdout + done.stderr
    where = subprocess.run([str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                           capture_output=True, text=True, check=True, timeout=60).stdout.strip()
    # Break's dependencies, read from the test environment's packages, after the fresh environment's own. A path
    # line adds a folder and reads none of its own path files, so the checkout's editable install does not follow.
    (Path(where) / "dependencies.pth").write_text(sysconfig.get_paths()["purelib"] + "\n", encoding="utf-8")
    found = subprocess.run([str(python), "-c", "import poisson_break; print(poisson_break.__file__)"],
                           capture_output=True, text=True, timeout=60, env=guarded_env(), cwd=venv)
    assert found.returncode == 0, found.stderr
    assert Path(found.stdout.strip()).resolve().is_relative_to(Path(where).resolve()), (
        "the package under test is not the installed wheel's", found.stdout)
    return venv / "bin"


# ---------------------------------------------------------------------------
# a page's commands, run in the page's order
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Printed:
    """One marked command, the code it exited with, and what it printed, both streams in order."""

    command: docs.Command
    exit: int
    output: str


@dataclass(frozen=True)
class Page:
    name: str
    folder: Path
    printed: dict[int, Printed]  # by the command's line in the page
    attempts: list[str]


def run_page(name: str, bin_folder: Path, work: Path) -> Page:
    """Every marked command of the page, in order, in one shell, in a fresh folder of the page's own."""
    text = (REPO / name).read_text(encoding="utf-8")
    commands = [c for block in docs.blocks(text, name) if block.info == "sh" for c in docs.commands_of(block)]
    assert commands, f"{name} marks no command"
    for command in commands:
        assert not docs.install_words(shlex.split(command.command, comments=True)), (
            f"{name}:{command.line}: an install command, which this test does not run")
    folder, home, out = work / "folder", work / "home", work / "out"
    for made in (folder, home, out):
        made.mkdir(parents=True)
    script = ["set -u"]
    for command in commands:
        log = shlex.quote(str(out / f"{command.line}"))
        # `{ ...; }` keeps a `cd` in this shell, so the commands after it run where the page says they do.
        script += [f"{{\n{command.command}\n}} >{log}.output 2>&1", f"echo $? >{log}.exit"]
    env = guarded_env()
    env.update(PYTHONPATH=str(PROBE), HOME=str(home), BREAK_TEST_NETWORK_LOG=str(work / "network.log"),
               PATH=os.pathsep.join([str(bin_folder), env.get("PATH", "")]))
    done = subprocess.run(["sh", "-c", "\n".join(script)], cwd=folder, env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=1500)
    assert done.returncode == 0, (name, done.stdout, done.stderr)
    printed = {}
    for command in commands:
        code = int((out / f"{command.line}.exit").read_text(encoding="utf-8"))
        output = (out / f"{command.line}.output").read_bytes().decode("utf-8")
        assert code == docs.exit_of(command), f"{name}:{command.line}: `{command.command}` exited {code}\n{output}"
        printed[command.line] = Printed(command, code, output)
    network = work / "network.log"
    return Page(name, folder, printed, network.read_text(encoding="utf-8").splitlines() if network.exists() else [])


@pytest.fixture(scope="module")
def pages(installed: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Page]:
    return {name: run_page(name, installed, tmp_path_factory.mktemp("page")) for name in PAGES}


# ---------------------------------------------------------------------------
# what a block must be
# ---------------------------------------------------------------------------


def without_this_machine(output: str, folder: Path) -> str:
    """The output less each `next:` line that holds the full path of the folder the command ran in."""
    here = {str(folder), str(folder.resolve())}
    kept = [line for line in output.splitlines(keepends=True)
            if not (line.startswith("next: ") and any(path in line for path in here))]
    return "".join(kept)


def readings(output: str, folder: Path) -> list[str]:
    """What a block showing this output may be: all of it, or all of it from its last result's first line."""
    whole = without_this_machine(output, folder)
    lines = whole.splitlines(keepends=True)
    starts = [n for n, line in enumerate(lines) if VERDICT_LINE.match(line.rstrip("\n"))]
    return [whole] + (["".join(lines[starts[-1]:])] if starts and starts[-1] > 0 else [])


def shown(name: str) -> list[tuple[docs.Block, list[docs.Command]]]:
    """Each block of output the page shows, with the commands of the `sh` block before it."""
    found: list[tuple[docs.Block, list[docs.Command]]] = []
    before: list[docs.Command] = []
    for block in docs.blocks((REPO / name).read_text(encoding="utf-8"), name):
        if block.info == "sh":
            before = list(docs.commands_of(block))
        elif block.info in OUTPUT:
            assert before, f"{name}:{block.fence_line}: a block of output with no command before it"
            found.append((block, before))
    return found


def body(block: docs.Block) -> str:
    return "".join(line + "\n" for line in block.lines)


def nearest(text: str, page: Page, commands: list[docs.Command]) -> str:
    """For a block that is no command's output: the difference from the reading nearest to it."""
    best = max(((difflib.SequenceMatcher(None, text, reading).ratio(), command, reading)
                for command in commands for reading in readings(page.printed[command.line].output, page.folder)),
               key=lambda found: found[0])
    diff = "".join(difflib.unified_diff(text.splitlines(keepends=True), best[2].splitlines(keepends=True),
                                        "the page shows", f"`{best[1].command}` printed"))
    return f"nearest is `{best[1].command}` ({page.name}:{best[1].line}):\n{diff}"


# ---------------------------------------------------------------------------
# the tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(PAGES))
def test_the_page_shows_the_blocks_of_output_this_test_holds(name: str) -> None:
    """A block of output added to a page, or one retagged so that it is no longer read as output, is seen here:
    each page shows the number of blocks written above, and no block of these pages is tagged for a terminal's
    output in another way."""
    blocks = docs.blocks((REPO / name).read_text(encoding="utf-8"), name)
    assert len([b for b in blocks if b.info in OUTPUT]) == PAGES[name]
    assert sorted({b.info for b in blocks} - {"sh", "toml", *OUTPUT}) == []


@pytest.mark.parametrize("name", sorted(PAGES))
def test_every_command_of_the_page_runs_offline_from_the_installed_wheel(name: str, pages: dict[str, Page]) -> None:
    page = pages[name]
    assert page.printed, name
    assert page.attempts == [], "a connection was attempted"
    assert not any(str(REPO) in p.output for p in page.printed.values()), "an output names the checkout"


@pytest.mark.parametrize("name", sorted(PAGES))
def test_every_block_of_output_is_what_its_command_printed_byte_for_byte(name: str, pages: dict[str, Page]) -> None:
    page = pages[name]
    wrong = []
    after: dict[int, int] = {}  # the `sh` block, by its first command's line: the commands already shown
    for block, commands in shown(name):
        text = body(block)
        start = after.get(commands[0].line, 0)
        match = next((n for n, command in enumerate(commands) if n >= start
                      and text in readings(page.printed[command.line].output, page.folder)), None)
        if match is None:
            wrong.append(f"{name}:{block.fence_line}: the block is not the output of a command before it, taken "
                         f"in order; {nearest(text, page, commands)}")
        else:
            after[commands[0].line] = match + 1
    assert not wrong, "\n\n".join(wrong)


def test_the_finding_s_file_the_page_shows_is_the_file_written(pages: dict[str, Page]) -> None:
    """ "Reading a finding" shows `break-runs/desk-1/findings/1.toml`: the block is the file's bytes, with the
    store's full path written as the page says it writes it."""
    page = pages["docs/findings.md"]
    (block,) = [b for b in docs.blocks((REPO / page.name).read_text(encoding="utf-8"), page.name)
                if b.info == "toml"]
    written = (page.folder / "break-runs" / "desk-1" / "findings" / "1.toml").read_bytes().decode("utf-8")
    store = [path for path in (str((page.folder / "break-runs" / "desk-1" / "store").resolve()),
                               str(page.folder / "break-runs" / "desk-1" / "store")) if path in written]
    assert store, "the file names its store by its full path"
    assert STORE_PLACEHOLDER in body(block)
    assert body(block) == written.replace(store[0], STORE_PLACEHOLDER)
