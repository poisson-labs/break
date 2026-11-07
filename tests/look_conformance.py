"""The conformance test: one invocation, run both ways, and what must hold between the two.

Takes any `look_corpus.Invocation` and knows nothing of what it does, so the commands module adds its
verbs to the corpus without changing this file or the test.

**The ways.** `piped`: stdout and stderr on pipes, nothing else changed. `no_color`, `dumb` and `plain`
(`--plain` on the command line, where the invocation takes it): the same with one thing changed, each of
which must print what `piped` prints, byte for byte. `terminal`: stdout and stderr each on a
pseudo-terminal with every condition of the switch holding. `terminal_plain`: the same terminals with
`NO_COLOR` set. `no_rich`: the terminals with Rich and questionary failing to import. `json`, and
`terminal_json`: the two with `--json` on the command line.

**The checks** are the entries of `CHECKS`. Each takes an `Invocation` and returns what is wrong, as a list
of sentences, empty when it holds. The test asserts each is empty, and `test_look_conformance.py` runs each
against a program that breaks exactly that rule, so an empty list means something.

**Runs are kept** for the life of the process, so that each check reads the same run.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from tests.look_corpus import Invocation
from tests.look_support import (
    BOX,
    CODES,
    ESCAPE,
    PIPED,
    TERMINALS,
    VERDICT_LINE,
    Ran,
    launch,
    no_rich_path,
    pretty_env,
    strict_json,
    strip,
    words_of,
)

#: A Python value printed as itself, or a traceback, in text a user reads.
REPR = re.compile(
    r"Traceback \(most recent call last\)"
    r"|<[A-Za-z_][\w.]* object at 0x"
    r"|\b(?:Posix|Windows)?Path\('"
    r"|\b[A-Z]\w*(?:Error|Exception)\("
    r"|\('[^']*', "
    r"|\['[^']*'(?:, |\])"
    r"|\{'[^']*': "
    r"|\bdict_(?:keys|values|items)\("
    r"|\bmappingproxy\("
    r"|\bNone\b(?=[,)\]])"
)
#: A module id, a rule number, a ruling or a session, none of which a user reads.
INTERNAL = re.compile(r"\b(?:BK|TF|PF|FD|LST|PT|CAL)\d+\b|\bL1?\d\b|\b[Rr]uling \d|\bSession [AB]\b")
#: A run of hex that reads as a hash: eight or more characters, holding a digit and a letter.
HEX = re.compile(r"\b(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])[0-9a-f]{8,}\b")

#: A name of ours that means nothing to a user.
PROJECT = re.compile(r"\b(?:monte|proofload|momus)\b", re.I)

_kept: dict[tuple[str, str], Ran] = {}
_folders: dict[str, Path] = {}


def _folder() -> Path:
    if "root" not in _folders:
        _folders["root"] = Path(tempfile.mkdtemp(prefix="look-conformance-"))
    return _folders["root"]


def _work(inv: Invocation) -> Path:
    folder = _folder() / re.sub(r"\W", "_", inv.name)
    if not folder.exists():
        folder.mkdir(parents=True)
        (folder / "home").mkdir()
        if inv.setup is not None:
            inv.setup(folder)
    return folder


def run_way(inv: Invocation, way: str) -> Ran:
    """The invocation run one way, kept for the checks that read the same run."""
    key = (inv.name + "|" + "|".join(inv.program) + "|" + "|".join(inv.argv), way)
    if key in _kept:
        return _kept[key]
    work = _work(inv)
    env = pretty_env(HOME=str(work / "home"))
    env.update(inv.env)
    words = list(inv.argv)
    streams = PIPED
    if way == "piped":
        pass
    elif way == "no_color":
        env["NO_COLOR"] = "1"
    elif way == "dumb":
        env["TERM"] = "dumb"
    elif way == "plain":
        words = [*words, "--plain"]
    elif way == "terminal":
        streams = TERMINALS
    elif way == "terminal_plain":
        streams = TERMINALS
        env["NO_COLOR"] = "1"
    elif way == "no_rich":
        streams = TERMINALS
        blocked = no_rich_path(_folder() / "no-rich")
        env["PYTHONPATH"] = blocked + ":" + env["PYTHONPATH"]
    elif way == "json":
        words = [*words, "--json"]
    elif way == "terminal_json":
        words = [*words, "--json"]
        streams = TERMINALS
    else:
        raise AssertionError(f"no way named {way}")
    program = list(inv.program) or [sys.executable, "-m", "poisson_break"]
    ran = launch([*program, *words], env, streams, cwd=work)
    _kept[key] = ran
    return ran


def _plain_ways(inv: Invocation) -> list[str]:
    return ["no_color", "dumb", *(["plain"] if inv.takes_plain else [])]


def _first(text: str) -> str:
    return text.split("\n", 1)[0]


def _last_verdict(text: str) -> str:
    """The last result's verdict line: the last line that is a verdict line, so a plan printed before a result is not
    read as the result. With one result it is the first line."""
    found = [line for line in text.split("\n") if VERDICT_LINE.match(line)]
    return found[-1] if found else ""


def _set_aside(text: str, other: str | None) -> str:
    """Text with what the invocation declares beside its problems set aside (progress, a question): each piece of a
    line between line ends and carriage returns that matches the pattern, as a terminal draws progress in place."""
    if not other:
        return text
    pattern = re.compile(other)
    return "\n".join("\r".join(piece for piece in line.split("\r") if not pattern.search(piece))
                     for line in strip(text).split("\n"))


# ---------- the checks ----------


def piped_is_one_rendering(inv: Invocation) -> list[str]:
    """Piped, the pretty build equals the plain build byte for byte."""
    base = run_way(inv, "piped")
    wrong = []
    for way in _plain_ways(inv):
        other = run_way(inv, way)
        if (other.out, other.err) != (base.out, base.err):
            wrong.append(f"piped and piped with {way} differ:\n{base}\n{other}")
    return wrong


def exit_code_holds(inv: Invocation) -> list[str]:
    """The exit code is the one asked for, in the table, and the same in every way."""
    wrong = []
    allowed = set(CODES.values())
    ways = ["piped", *_plain_ways(inv), "terminal", "terminal_plain", "no_rich"]
    for way in ways:
        ran = run_way(inv, way)
        if ran.exit != inv.code:
            wrong.append(f"{way}: exit {ran.exit}, wanted {inv.code}")
        if ran.exit not in allowed:
            wrong.append(f"{way}: exit {ran.exit} is not in the table")
    return wrong


def verdict_comes_first(inv: Invocation) -> list[str]:
    """A verdict line first on stdout, piped; on a terminal, with escapes removed, the same word and
    sentence."""
    if inv.kind != "result":
        return []
    piped = run_way(inv, "piped")
    head = _first(piped.out)
    match = VERDICT_LINE.match(head)
    if match is None:
        return [f"the first line piped is not a verdict line: {head!r}"]
    wrong = []
    for way in ("terminal", "terminal_plain"):
        drawn = _first(strip(run_way(inv, way).out))
        again = VERDICT_LINE.match(drawn)
        if again is None:
            wrong.append(f"{way}: the first line is not a verdict line: {drawn!r}")
        elif again.groups() != match.groups() and (way == "terminal" or len(head) <= run_way(inv, way).columns):
            wrong.append(f"{way}: the first line says {drawn!r}, piped says {head!r}")
    return wrong


def plain_is_text(inv: Invocation) -> list[str]:
    """Plain holds no escape sequence and no box character, on a pipe or on a terminal."""
    wrong = []
    for way in ["piped", *_plain_ways(inv), "terminal_plain"]:
        ran = run_way(inv, way)
        for stream, text in (("stdout", ran.out), ("stderr", ran.err)):
            if "\x1b" in text:
                wrong.append(f"{way}: an escape sequence on {stream}: {text!r}")
            if BOX.search(text):
                wrong.append(f"{way}: a box character on {stream}: {text!r}")
    return wrong


def same_facts(inv: Invocation) -> list[str]:
    """Every rendering carries the same words and numbers in the same order; on stderr, with what the invocation
    declares beside its problems set aside, since a terminal shows progress a pipe never does."""
    base = run_way(inv, "piped")
    wrong = []
    for way in ("terminal", "terminal_plain", "no_rich"):
        ran = run_way(inv, way)
        for stream, ours, theirs in (("stdout", ran.out, base.out),
                                     ("stderr", _set_aside(ran.err, inv.other_stderr),
                                      _set_aside(base.err, inv.other_stderr))):
            if words_of(ours) != words_of(theirs):
                wrong.append(f"{way}: {stream} says other facts:\n{strip(ours)!r}\npiped:\n{theirs!r}")
    return wrong


def problems_read_as_problems(inv: Invocation) -> list[str]:
    """Every line on stderr is `error:`, `note:`, a two-space continuation, or what the invocation
    declares; `bad` has nothing on stdout and opens stderr with `error:`."""
    wrong = []
    other = re.compile(inv.other_stderr) if inv.other_stderr else None
    ran = run_way(inv, "piped")
    for text in ran.err.splitlines():
        if not re.match(r"(?:error: \S|note: \S|  \S)", text) and not (other and other.search(text)):
            wrong.append(f"a line on stderr that is no problem: {text!r}")
    if inv.kind == "bad":
        if ran.out:
            wrong.append(f"something on stdout: {ran.out!r}")
        if not ran.err.startswith("error: "):
            wrong.append(f"stderr does not open with error: {ran.err!r}")
        if sum(text.startswith("error:") for text in ran.err.splitlines()) != 1:
            wrong.append(f"not one error line: {ran.err!r}")
    return wrong


def no_leaks(inv: Invocation) -> list[str]:
    """No traceback, no Python value printed as itself, and no internal reference, in anything printed."""
    wrong = []
    for way in ("piped", "terminal"):
        ran = run_way(inv, way)
        text = strip(ran.out) + strip(ran.err)
        for pattern, what in ((REPR, "a Python value or a traceback"), (INTERNAL, "an internal reference"), (PROJECT, "a project name")):
            found = pattern.search(text)
            if found:
                wrong.append(f"{way}: {what}: {found.group(0)!r} in {text!r}")
    return wrong


def no_hash_to_paste(inv: Invocation) -> list[str]:
    """Nothing asks a user to paste a hash: no hash in a `next:` line, in a problem or in a command; and
    a hash that is shown, for the record, is at most 12 characters."""
    ran = run_way(inv, "piped")
    wrong = []
    for text in [*ran.out.splitlines(), *ran.err.splitlines()]:
        for found in HEX.findall(text):
            asks = re.match(r"\s*(?:next:|error:|note:)", text) or inv.kind == "bad"
            if asks:
                wrong.append(f"a hash a user is asked to act on: {text!r}")
            elif len(found) > 12:
                wrong.append(f"a hash longer than 12 characters in text: {text!r}")
    return wrong


def json_way(inv: Invocation) -> list[str]:
    """`--json` makes stdout one strict document, the same on a pipe and on a terminal, with `schema`,
    `verdict` and `sentence` first, carrying the last result's verdict line's word and sentence: a plan printed before
    the result is not the document."""
    if not inv.has_json:
        return []
    piped = run_way(inv, "json")
    terminal = run_way(inv, "terminal_json")
    plain = run_way(inv, "piped")
    wrong = []
    if piped.exit != plain.exit or terminal.exit != plain.exit:
        wrong.append(f"the exit code changes under --json: {plain.exit}, {piped.exit}, {terminal.exit}")
    if piped.out != terminal.out:
        wrong.append(f"the document differs on a terminal:\n{piped.out!r}\n{terminal.out!r}")
    try:
        document = strict_json(piped.out)
    except (ValueError, AssertionError) as why:
        return [*wrong, f"not one strict document: {why}: {piped.out!r}"]
    if not isinstance(document, dict) or list(document)[:3] != ["schema", "verdict", "sentence"]:
        return [*wrong, f"the first keys are not schema, verdict, sentence: {piped.out!r}"]
    match = VERDICT_LINE.match(_last_verdict(plain.out))
    if match is None or (document["verdict"], document["sentence"]) != match.groups():
        wrong.append(f"the document's verdict and sentence are not the last result's: {piped.out!r}")
    if "\x1b" in terminal.out:
        wrong.append("an escape sequence in the document")
    return wrong


def help_can_be_acted_on(inv: Invocation) -> list[str]:
    """Help goes to stdout, exits 0, and has a description and an example. A version is one line."""
    wrong = []
    if inv.kind == "help":
        for way in ("piped", "terminal"):
            ran = run_way(inv, way)
            text = strip(ran.out)
            if ran.exit != 0:
                wrong.append(f"{way}: help exits {ran.exit}")
            if strip(ran.err).strip():
                wrong.append(f"{way}: help writes to stderr: {ran.err!r}")
            if not re.search(r"(?i)\bexamples?\b", text):
                wrong.append(f"{way}: help has no example: {text!r}")
            if len(words_of(text)) < 20:
                wrong.append(f"{way}: help has no description: {text!r}")
    if inv.kind == "version":
        for way in ("piped", "terminal"):
            ran = run_way(inv, way)
            if ran.exit != 0 or len(strip(ran.out).strip().splitlines()) != 1:
                wrong.append(f"{way}: a version is one line and exit 0: {ran}")
    return wrong


def rich_absent_means_plain(inv: Invocation) -> list[str]:
    """With Rich and questionary failing to import, on a terminal: plain, the same exit code, and nothing
    said about it."""
    ran = run_way(inv, "no_rich")
    plain = run_way(inv, "terminal_plain")
    wrong = []
    if "\x1b" in ran.out or "\x1b" in ran.err:
        wrong.append(f"an escape sequence without Rich: {ran}")
    if (ran.out, ran.err) != (plain.out, plain.err):
        wrong.append(f"without Rich the terminal shows something other than plain:\n{ran}\n{plain}")
    return wrong


CHECKS: dict[str, Callable[[Invocation], list[str]]] = {
    "piped-one-rendering": piped_is_one_rendering,
    "exit-code": exit_code_holds,
    "verdict-first": verdict_comes_first,
    "plain-is-text": plain_is_text,
    "same-facts": same_facts,
    "problems": problems_read_as_problems,
    "no-leaks": no_leaks,
    "no-hash-to-paste": no_hash_to_paste,
    "json": json_way,
    "help": help_can_be_acted_on,
    "rich-absent": rich_absent_means_plain,
}


def forget() -> None:
    """Drop the kept runs and their folder."""
    _kept.clear()
    root = _folders.pop("root", None)
    if root is not None:
        shutil.rmtree(root, ignore_errors=True)


def as_json(wrong: list[str]) -> str:
    return json.dumps(wrong, indent=1)


__all__ = ["CHECKS", "ESCAPE", "forget", "run_way"]
