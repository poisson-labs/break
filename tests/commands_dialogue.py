"""`init`'s dialogue driven by scripted answers, on pseudo-terminals, in either rendering.

`converse` runs the command with stdin, stdout and stderr each on a pseudo-terminal, so `init` asks, and answers each
question once it is on the screen: a prompt is a question and its bracket at the end of stderr (`[y/N]`, `[400]`), a
menu in plain is a numbered list then the prompt `choice [<default>]`, and a menu in pretty is questionary's, which the
look draws with the instruction `(arrow keys, then Enter)`. What it read of each is an `Asked`; the answer is the
script's.

In plain (`NO_COLOR` set) every answer is a line of text: a menu takes a choice as it is written. In pretty, a text
question takes the same line, and a menu is answered with the arrow keys from the choice it opens on: the script names
the choice, and the driver moves to it in the order the plain rendering listed (`order`).

The forms held here are the ones Taylor ruled for `init` (BK8 point 1, 2026-11-07): one prompt per question in §9.3's
order, each skipped when its flag was given; questions 1 and 4 menus; the rest text or `[y/N]`.
"""

from __future__ import annotations

import contextlib
import fcntl
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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from tests.commands_support import Project, child_env
from tests.look_support import Ran, _fold, strip

#: A prompt at the end of stderr: a bracket, then the one space the look leaves the cursor after.
PROMPT = re.compile(r"(\[[^\]\n]*\]) ?$")
#: A numbered choice of a plain menu.
CHOICE = re.compile(r"^ +(\d+)  (\S.*?)\s*$")
#: questionary's menu, as the look draws it in pretty.
ARROWS = "(arrow keys, then Enter)"
DOWN, UP = b"\x1b[B", b"\x1b[A"


@dataclass
class Asked:
    """One question as it was on the screen: `text` is stderr since the last answer, escapes gone; `question` its
    question line; `bracket` the bracketed default of a text or `[y/N]` question, `None` for a pretty menu; `menu` a
    plain menu's choices as shown, in order (empty for a question that is no menu); `pretty_menu` whether it was
    questionary's. `answer` is what the script answered."""

    text: str
    question: str
    bracket: str | None
    menu: list[str] = field(default_factory=list)
    pretty_menu: bool = False
    answer: str = ""

    @property
    def is_menu(self) -> bool:
        return bool(self.menu) or self.pretty_menu

    @property
    def yes_no(self) -> bool:
        return self.bracket in ("[y/N]", "[Y/n]")


def _read(text: str) -> Asked | None:
    """The question at the end of `text`, or `None` while none is complete."""
    shown = strip(text).replace("\r", "")
    if ARROWS in shown:
        before = shown.split(ARROWS, 1)[0].rstrip().splitlines()
        return Asked(text=shown, question=before[-1].strip() if before else "", bracket=None, pretty_menu=True)
    match = PROMPT.search(shown)
    if match is None or not shown.endswith(" "):
        return None
    lines = shown.rstrip().splitlines()
    choices = [m.group(2) for m in (CHOICE.match(line) for line in lines) if m]
    if choices and lines[-1].startswith("choice "):
        first = next(i for i, line in enumerate(lines) if CHOICE.match(line))
        return Asked(text=shown, question=lines[first - 1].strip() if first else "", bracket=match.group(1),
                     menu=choices)
    question = lines[-1][: -len(match.group(1))].strip() if lines else ""
    return Asked(text=shown, question=question, bracket=match.group(1))


def converse(proj: Project, words: Sequence[str], answer: Callable[[Asked], str], *, pretty: bool = False,
             order: Mapping[str, Sequence[str]] | None = None, prog: str | None = None, columns: int = 160,
             timeout: float = 120.0, **env: str | None) -> tuple[Ran, list[Asked]]:
    """`init` (or any verb) run on three pseudo-terminals in the project's folder, each question answered by
    `answer(asked)`. In pretty, a menu's answer is a choice: `order[question]` lists its choices as plain lists them,
    and `asked.menu` is filled from it so a script reads both renderings alike."""
    changes: dict[str, str | None] = {"NO_COLOR": None if pretty else "1", **env}
    environment = child_env(proj, **changes)
    if prog is None:
        argv = [sys.executable, "-m", "poisson_break", *words]
    else:
        code = f"import sys; from poisson_break.cli import main; sys.exit(main(sys.argv[1:], prog={prog!r}))"
        argv = [sys.executable, "-c", code, *words]
    masters: dict[str, int] = {}
    slaves: dict[str, int] = {}
    for name in ("in", "out", "err"):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, columns, 0, 0))
        masters[name], slaves[name] = master, slave
    process = subprocess.Popen(argv, cwd=proj.folder, env=environment, stdin=slaves["in"], stdout=slaves["out"],
                               stderr=slaves["err"], start_new_session=True,
                               preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))  # noqa: PLW1509
    for slave in slaves.values():
        os.close(slave)
    got = {"out": b"", "err": b""}
    since = 0  # where stderr stood at the last answer
    asked: list[Asked] = []
    quiet = time.monotonic()
    deadline = time.monotonic() + timeout
    fds = {masters["out"]: "out", masters["err"]: "err"}
    closed: set[int] = set()
    try:
        while time.monotonic() < deadline:
            waiting = [fd for fd in fds if fd not in closed]
            ready, _, _ = select.select(waiting, [], [], 0.05) if waiting else ([], [], [])
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
            if process.poll() is not None and not ready:
                break
            if time.monotonic() - quiet < 0.3:
                continue
            now = _read(got["err"][since:].decode("utf-8", "replace"))
            if now is None:
                continue
            if now.pretty_menu and order is not None:
                now.menu = [choice.lstrip("*") for choice in order.get(now.question, ())]
            now.answer = answer(now)
            asked.append(now)
            if now.pretty_menu:
                keys = _arrows(now, order)
            else:
                keys = now.answer.encode() + b"\r"
            for key in keys if isinstance(keys, list) else [keys]:
                os.write(masters["in"], key)
                time.sleep(0.05)
            since = len(got["err"])
            quiet = time.monotonic()
        else:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            raise AssertionError(f"the dialogue did not end in {timeout} s: {argv}\nasked: {asked}\n{got}")
        process.wait(10)
    finally:
        if process.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(10)
        for master in masters.values():
            with contextlib.suppress(OSError):
                os.close(master)
    return Ran(process.returncode, _fold(got["out"]), _fold(got["err"]), 0.0, columns, got["err"]), asked


def _arrows(asked: Asked, order: Mapping[str, Sequence[str]] | None) -> list[bytes]:
    """The keys that move questionary's menu from the choice it opens on to the one answered, then Enter. The menu
    opens on its default, which is where the plain rendering's bracket pointed: `order` holds, for each question,
    its choices in order with the default first marked by `*`."""
    if not asked.answer:  # Enter takes the choice the menu opens on, its default
        return [b"\r"]
    assert order is not None and asked.question in order, f"no order for the menu {asked.question!r}: {asked.text}"
    listed = [c.lstrip("*") for c in order[asked.question]]
    opens = next(i for i, c in enumerate(order[asked.question]) if c.startswith("*"))
    to = listed.index(asked.answer)
    step = DOWN if to > opens else UP
    return [step] * abs(to - opens) + [b"\r"]


def orders(asked: Sequence[Asked]) -> dict[str, list[str]]:
    """From a plain run, each menu's choices in order, the default marked with a leading `*`: what `_arrows` needs to
    answer the same menus in pretty."""
    found: dict[str, list[str]] = {}
    for one in asked:
        if one.menu and one.bracket is not None:
            default = one.bracket[1:-1]
            found[one.question] = [("*" if choice == default else "") + choice for choice in one.menu]
    return found


def scripted(answers: Sequence[str]) -> Callable[[Asked], str]:
    """Answer the questions in turn with `answers`; a question past the last is a failure of the test."""
    queue = list(answers)

    def answer(asked: Asked) -> str:
        assert queue, f"a question the script did not expect: {asked.text!r}"
        return queue.pop(0)

    return answer


__all__ = ["ARROWS", "Asked", "converse", "orders", "scripted"]
