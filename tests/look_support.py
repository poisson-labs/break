"""What the look's tests share: the module reached at call time, the shapes in one place, a child
process on real pipes and pseudo-terminals, the escape sequences read back, and the words of a text.

**The module is reached when a test runs** (`look()`), so a tree without it fails test by test
instead of stopping collection.

**The shapes live here and in `look_results.py`, and nowhere else.** The plan names `Result`, `Plan`,
`render(result, *, stream, mode)`, `mode_for(stdout, stderr, env, argv)`, `error(sentence, nexts)` and
`ask(question, default)`, and leaves the rest of the shape to be ruled. Every test builds what it needs
through the helpers below, so a different ruling on a name is one line here.

**How a run is reached.** A child process with a stream of its own for each of stdout, stderr and
stdin: a pipe, a file or a pseudo-terminal of a given width. Nothing is mocked: `isatty` is what the
operating system says about the descriptor. The child's environment is `conftest.guarded_env()` with
every condition of the switch holding, and a test changes one thing on top.

**How a terminal is read.** Each stream's bytes are kept as written, escapes included. `screen()`
hands them to a terminal emulator, so what stays on screen can be asked about.

**What is never pinned here:** a border, a column's width, a padding, the spelling of a glyph's ASCII
form. Tests compare words and numbers in their order (`words_of`), and which colour a character has.
"""

from __future__ import annotations

import contextlib
import fcntl
import importlib
import json
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tests.conftest import GUARD, REPO, guarded_env

CHILD = Path(__file__).with_name("look_child.py")

#: The six exit codes of the shared look, written out so that the tests do not read them from the
#: module they test.
CODES = {"done": 0, "refused": 1, "usage": 2, "stopped": 3, "check": 4, "interrupted": 130}

VERDICT_LINE = re.compile(r"^([a-z][a-z ]*?)  (\S.*)$")
"""The verdict line, with the word and the sentence as groups: `^[a-z][a-z ]*  \\S`."""

ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][0-9A-Za-z]|\x1b[@-Z\\-_=>]")
SGR = re.compile(r"\x1b\[([0-9;:]*)m")
#: Reset, bold, dim, normal intensity, the sixteen named foreground colours and the terminal's own.
ALLOWED_SGR = frozenset({0, 1, 2, 22, 39, *range(30, 38), *range(90, 98)})
#: What a user can be asked to read as a box: box drawing and block elements.
BOX = re.compile(r"[─-▟]")
ELLIPSIS = re.compile(r"…|\.\.\.")

GREEN = frozenset({2, 10})
YELLOW = frozenset({3, 11})
RED = frozenset({1, 9})
MEANINGS = GREEN | YELLOW | RED


def look() -> Any:
    """`poisson_break.look`, reached at call time."""
    return importlib.import_module("poisson_break.look")


# ---------- the shapes, in one place ----------


def row(label: str, value: Any) -> Any:
    return look().Row(label, value)


def line(text: str) -> Any:
    return look().Line(text)


def table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> Any:
    return look().Table(tuple(header), tuple(tuple(r) for r in rows))


def result(verdict: str, sentence: str, detail: Sequence[Any] = (), nexts: Sequence[Any] = (),
           **more: Any) -> Any:
    return look().Result(verdict, sentence, detail=tuple(detail), nexts=tuple(nexts), **more)


def plan(sentence: str, estimate: str, source: str, detail: Sequence[Any] = (),
         nexts: Sequence[Any] = ()) -> Any:
    return look().Plan(sentence, estimate=estimate, source=source, detail=tuple(detail),
                       nexts=tuple(nexts))


#: What every look-using child starts with. `body` runs under the look's `run`, whose first argument
#: is the tool's name as the unexpected-failure line writes it. `show` renders a result in the mode
#: the switch chose for this process, or writes it as one document under `--json`.
PRELUDE = """\
import json, os, sys
from poisson_break import look
from tests import look_results
words = sys.argv[1:]
def show(result):
    if "--json" in words:
        sys.stdout.write(look.as_json(result))
        sys.stdout.flush()
    else:
        look.render(result, stream=sys.stdout, mode=look.mode_for(sys.stdout, sys.stderr, os.environ, words))
def body():
{body}
sys.exit(look.run("poisson-break", words, body))
"""


def snippet(body: str) -> str:
    """A child program: `body`, indented into the prelude's `body()`."""
    indented = "\n".join("    " + text for text in body.splitlines()) or "    pass"
    return PRELUDE.format(body=indented)


# ---------- a child on real streams ----------


def pretty_env(**changes: str | None) -> dict[str, str]:
    """A child's environment in which every condition of the switch holds, changed as asked: a value
    of None removes the variable."""
    env = guarded_env()
    for name in ("FORCE_COLOR", "TTY_COMPATIBLE", "TTY_INTERACTIVE", "COLORTERM", "CLICOLOR",
                 "CLICOLOR_FORCE", "LINES", "COLUMNS", "NO_COLOR", "CI", "JUPYTER_COLUMNS",
                 "JUPYTER_LINES", "PYTHONWARNINGS"):
        env.pop(name, None)
    env["TERM"] = "xterm-256color"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.pathsep.join([str(GUARD), str(REPO)])
    env["PROMPT_TOOLKIT_NO_CPR"] = "1"
    for name, value in changes.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    return env


def _fold(raw: bytes) -> str:
    """Bytes as text, a terminal's line ends read as `\\n`. A pseudo-terminal writes `\\r\\n` for a line
    feed, and macOS sometimes `\\r\\r\\n` at the edge of its output queue."""
    return re.sub(r"\r+\n", "\n", raw.decode("utf-8", "replace"))


@dataclass(frozen=True)
class Ran:
    exit: int
    out: str
    err: str
    took: float = 0.0
    columns: int = 100
    raw_err: bytes = b""

    def __str__(self) -> str:
        return f"exit {self.exit}\n--- stdout\n{self.out}\n--- stderr\n{self.err}"


@dataclass
class Streams:
    """Which stream is what: `pipe`, `pty` or a path, for stdout and stderr; for stdin `null`, `pty`,
    or text to pipe in. `together` puts stdout and stderr on one terminal, as a user has them."""
    out: str | Path = "pipe"
    err: str | Path = "pipe"
    stdin: str = "null"
    columns: int = 100
    together: bool = False
    keys: Sequence[bytes] = field(default_factory=tuple)


PIPED = Streams()
TERMINALS = Streams(out="pty", err="pty")


def launch(argv: Sequence[str], env: Mapping[str, str], streams: Streams = PIPED, *, cwd: Path | None = None,
           timeout: float = 60.0, interrupt_on: str | None = None) -> Ran:
    """Run `argv` on the streams asked for, and read each until the child has ended and its side is
    drained. `keys` are written to the stdin terminal one at a time, each after the output has been
    quiet for a moment. `interrupt_on` sends SIGINT once that text has reached stdout or stderr."""
    env = dict(env)
    cwd = cwd or REPO
    masters: dict[str, int] = {}
    slaves: dict[str, int] = {}
    files: list[Any] = []
    wanted = {"out": streams.out, "err": streams.err}
    if streams.together:
        wanted = {"out": "pty", "err": "pty"}
    for name, kind in wanted.items():
        if kind == "pty":
            if streams.together and name == "err":
                masters["err"], slaves["err"] = masters["out"], slaves["out"]
                continue
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, streams.columns, 0, 0))
            masters[name], slaves[name] = master, slave
    stdin_master = None
    stdin: Any
    text_in = None
    if streams.stdin == "null":
        stdin = subprocess.DEVNULL
    elif streams.stdin == "pty":
        stdin_master, stdin_slave = pty.openpty()
        fcntl.ioctl(stdin_slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, streams.columns, 0, 0))
        stdin = stdin_slave
    else:
        stdin = subprocess.PIPE
        text_in = streams.stdin.encode()

    def target(name: str) -> Any:
        kind = wanted[name]
        if name in slaves:
            return slaves[name]
        if kind == "pipe":
            return subprocess.PIPE
        handle = open(kind, "wb")  # noqa: SIM115
        files.append(handle)
        return handle

    started = time.monotonic()
    # A child of a shell that runs in the background inherits SIGINT ignored, and Ctrl-C would mean nothing.
    process = subprocess.Popen(list(argv), cwd=cwd, env=env, stdin=stdin, stdout=target("out"),
                               stderr=target("err"), start_new_session=True,
                               preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))  # noqa: PLW1509
    if text_in is not None:
        assert process.stdin is not None
        with contextlib.suppress(BrokenPipeError):
            process.stdin.write(text_in)
            process.stdin.close()
    fds: dict[int, str] = {}
    if streams.together:
        fds[masters["out"]] = "out"
    else:
        for name in ("out", "err"):
            if name in masters:
                fds[masters[name]] = name
            elif wanted[name] == "pipe":
                pipe = process.stdout if name == "out" else process.stderr
                assert pipe is not None
                fds[pipe.fileno()] = name
    got = {"out": b"", "err": b""}
    closed: set[int] = set()
    keys = list(streams.keys)
    quiet = time.monotonic()
    interrupted = False

    def drain(wait: float) -> bool:
        nonlocal quiet
        waiting = [fd for fd in fds if fd not in closed]
        if not waiting:
            time.sleep(min(wait, 0.02))
            return False
        ready, _, _ = select.select(waiting, [], [], wait)
        for fd in ready:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                chunk = b""
            if chunk:
                got[fds[fd]] += chunk
                quiet = time.monotonic()
            else:
                closed.add(fd)
        return bool(ready)

    deadline = started + timeout
    try:
        while time.monotonic() < deadline:
            drain(0.02)
            if process.poll() is not None:
                break
            if interrupt_on is not None and not interrupted and interrupt_on.encode() in got["out"] + got["err"]:
                os.killpg(process.pid, signal.SIGINT)
                interrupted = True
            asked = bool(got["out"] or got["err"]) or time.monotonic() - started > 5
            if keys and stdin_master is not None and asked and time.monotonic() - quiet > 0.3:
                os.write(stdin_master, keys.pop(0))
                quiet = time.monotonic()
        else:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(10)
            raise AssertionError(f"the child did not end in {timeout} s: {argv}\n{got}")
        for _ in range(100):
            if not drain(0.02):
                break
    finally:
        if process.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(10)
        for fd in {*masters.values(), *slaves.values()}:
            with contextlib.suppress(OSError):
                os.close(fd)
        if stdin_master is not None:
            with contextlib.suppress(OSError):
                os.close(stdin_master)
            with contextlib.suppress(OSError):
                os.close(stdin_slave)
        for pipe in (process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()
        for handle in files:
            handle.close()
    return Ran(process.returncode, _fold(got["out"]), _fold(got["err"]), time.monotonic() - started,
               streams.columns, got["err"])


def run_body(body: str, words: Sequence[str] = (), *, streams: Streams = PIPED,
             env: Mapping[str, str] | None = None, **kw: Any) -> Ran:
    """`body` in a child, under the look's `run`, with `words` as its command line."""
    return launch([sys.executable, "-c", snippet(body), *words], pretty_env() if env is None else env,
                  streams, **kw)


def run_result(name: str, words: Sequence[str] = (), *, streams: Streams = PIPED,
               env: Mapping[str, str] | None = None) -> Ran:
    """One result of the corpus, rendered in a child by `tests/look_child.py`."""
    return launch([sys.executable, str(CHILD), "result", name, *words],
                  pretty_env() if env is None else env, streams)


def no_rich_path(folder: Path) -> str:
    """A folder that, put first on `PYTHONPATH`, makes Rich and questionary fail to import, as they do
    on a machine without them."""
    for name in ("rich", "questionary"):
        package = folder / name
        package.mkdir(parents=True, exist_ok=True)
        (package / "__init__.py").write_text(
            f"raise ModuleNotFoundError(\"No module named '{name}'\", name={name!r})\n")
    return str(folder)


# ---------- reading what came back ----------


def strip(text: str) -> str:
    return ESCAPE.sub("", text)


def words_of(text: str) -> list[str]:
    """The words and numbers of a text, in order, with escapes gone and whatever joins or breaks them
    set aside: a border, a padding, a wrapped line."""
    return re.findall(r"[^\W_]+", strip(text))


def split_words(text: str) -> list[str]:
    """The text cut at white space only, so a word broken across two lines shows."""
    return strip(text).split()


def sgr_codes(text: str) -> set[int]:
    """Every SGR parameter a text holds; an empty parameter is a reset. A colon form, such as `4:3`,
    counts as a code of its own, so it can never pass for an allowed one."""
    found: set[int] = set()
    for match in SGR.finditer(text):
        body = match.group(1)
        if ":" in body:
            found.add(-1)
            continue
        found |= {int(part) if part else 0 for part in body.split(";")}
    return found


@dataclass(frozen=True)
class Cell:
    char: str
    fg: int | None
    bold: bool
    dim: bool


def cells(text: str) -> list[Cell]:
    """A text as the characters a terminal would draw, each with its foreground (one of the sixteen,
    0 to 15, or None for the terminal's own), bold and dim."""
    fg: int | None = None
    bold = dim = False
    out: list[Cell] = []
    at = 0
    while at < len(text):
        match = ESCAPE.match(text, at)
        if match is None:
            out.append(Cell(text[at], fg, bold, dim))
            at += 1
            continue
        at = match.end()
        sgr = SGR.fullmatch(match.group(0))
        if sgr is None:
            continue
        for part in (sgr.group(1).split(";") if sgr.group(1) else ["0"]):
            code = int(part) if part.isdigit() else -1
            if code == 0:
                fg, bold, dim = None, False, False
            elif code == 1:
                bold = True
            elif code == 2:
                dim = True
            elif code == 22:
                bold = dim = False
            elif code == 39:
                fg = None
            elif 30 <= code <= 37:
                fg = code - 30
            elif 90 <= code <= 97:
                fg = code - 90 + 8
    return out


def drawn(text: str, *, first_line: bool = False) -> list[Cell]:
    all_cells = cells(text)
    if first_line:
        ends = next((i for i, c in enumerate(all_cells) if c.char == "\n"), len(all_cells))
        return all_cells[:ends]
    return all_cells


def cells_of(text: str, wanted: str) -> list[Cell]:
    """The cells of the first place `wanted` is drawn."""
    all_cells = cells(text)
    plain = "".join(c.char for c in all_cells)
    at = plain.find(wanted)
    assert at >= 0, f"{wanted!r} is not drawn in {plain!r}"
    return all_cells[at:at + len(wanted)]


def screen(raw: str, columns: int = 100, rows: int = 40) -> tuple[list[str], bool]:
    """What a terminal shows once `raw` has been drawn on it, and whether the cursor is left hidden."""
    import pyte

    terminal = pyte.Screen(columns, rows)
    stream = pyte.Stream(terminal)
    stream.feed(raw.replace("\n", "\r\n"))
    return [text.rstrip() for text in terminal.display], bool(terminal.cursor.hidden)


def strict_json(document: str) -> Any:
    def refuse(constant: str) -> Any:
        raise AssertionError(f"{constant} in a strict document")
    return json.loads(document, parse_constant=refuse)
