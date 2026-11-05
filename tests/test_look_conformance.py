"""The conformance test, and that it can be reused and can fail.

Invariants pinned here (Break — Plan, the look layer):
- BK12.1   Piped, the pretty build equals the plain build byte for byte; on a pseudo-terminal, with
           escapes removed, the first line carries the same verdict word and sentence, and the exit code
           is the same; plain and pretty carry the same facts in the same order.
- BK12.4   The verdict line is first on stdout, in both renderings and in `--json`'s two fields.
- BK12.5   Problems read as problems; no traceback, no Python value printed as itself, no module id, no
           hash to paste.
- BK12.11  The test takes a corpus of invocations and runs each both ways; a later module adds to the
           corpus and changes nothing here.
- BK12.12  With Rich not importable, every command prints plain and says nothing about it.

The second half runs each check against a small program, written here, that does nothing but break the
rule: a check that cannot fail would hold every later verb to nothing. Those programs use no look, so that
half is green before the look is built, and pins the checks, not the build. So are the entries for the
command's `--help`, `--version` and bad flags, which hold what the repo module built against whatever the
look's build changes.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from tests import look_conformance as conformance
from tests.look_corpus import CORPUS, Invocation


@pytest.fixture(scope="module", autouse=True)
def _kept_runs() -> Iterator[None]:
    yield
    conformance.forget()


def _applies(check: str, inv: Invocation) -> bool:
    if check == "help":
        return inv.kind in ("help", "version")
    if check == "json":
        return inv.has_json
    if check == "verdict-first":
        return inv.kind == "result"
    return True


PAIRS = [(check, inv) for check in conformance.CHECKS for inv in CORPUS if _applies(check, inv)]


def test_the_corpus_names_are_unique() -> None:
    names = [inv.name for inv in CORPUS]
    assert len(names) == len(set(names)), names


@pytest.mark.parametrize("check, inv", PAIRS, ids=[f"{c}-{i.name}" for c, i in PAIRS])
def test_every_invocation_conforms(check: str, inv: Invocation) -> None:
    piped = conformance.run_way(inv, "piped")
    assert piped.exit == inv.code and "Traceback" not in piped.err, f"the invocation does not run as it should:\n{piped}"
    wrong = conformance.CHECKS[check](inv)
    assert not wrong, "\n".join(wrong)


# ---------- the checks can fail ----------

GOOD = '''\
import json, os, sys
words = sys.argv[1:]
plain = ("--plain" in words or not sys.stdout.isatty() or not sys.stderr.isatty()
         or bool(os.environ.get("NO_COLOR")) or os.environ.get("TERM") == "dumb")
if not plain:
    try:
        import rich
    except ImportError:
        plain = True
if "--json" in words:
    print(json.dumps({"schema": "x/1", "verdict": "ok", "sentence": "all 3 fine"}))
    sys.exit(0)
word = "ok" if plain else "\\x1b[32mok\\x1b[0m"
print(f"{word}  all 3 fine")
print("  label  value")
print("  fingerprint  abc123def456")
print("next: tool again")
print("note: this one is fine", file=sys.stderr)
sys.exit(0)
'''

GOOD_BAD = '''\
import os, sys
plain = not sys.stdout.isatty() or not sys.stderr.isatty() or bool(os.environ.get("NO_COLOR")) or os.environ.get("TERM") == "dumb"
try:
    import rich
except ImportError:
    plain = True
word = "error:" if plain else "\\x1b[31merror:\\x1b[0m"
print(f"{word} it did not work", file=sys.stderr)
print("  next: tool again", file=sys.stderr)
sys.exit(2)
'''

GOOD_HELP = '''\
print("usage: tool [--flag]")
print()
print("Tool does one thing and does it well, and this paragraph says what that thing is, for a person who has never run it before.")
print()
print("examples:")
print("  tool --flag")
'''

GOOD_VERSION = 'print("tool 1.0 (Python 3)")\n'

SAYS_OK = 'print(f"{word}  all 3 fine")'


def _program(tmp_path: Path, text: str, name: str = "tool.py") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def _inv(tmp_path: Path, text: str, **more: object) -> Invocation:
    fields: dict = {"name": f"meta-{tmp_path.name}", "argv": (), "has_json": True, **more}
    script = _program(tmp_path, text)
    return Invocation(program=(sys.executable, str(script)), **fields)


def _edit(old: str, new: str) -> str:
    assert GOOD.count(old) == 1, old
    return GOOD.replace(old, new)


def test_a_program_that_keeps_every_rule_passes_every_check(tmp_path: Path) -> None:
    inv = _inv(tmp_path, GOOD)
    for name, check in conformance.CHECKS.items():
        assert check(inv) == [], name


@pytest.mark.parametrize("text, kind, code", [(GOOD_BAD, "bad", 2), (GOOD_HELP, "help", 0), (GOOD_VERSION, "version", 0)],
                         ids=["bad", "help", "version"])
def test_the_other_kinds_of_invocation_can_pass(tmp_path: Path, text: str, kind: str, code: int) -> None:
    inv = _inv(tmp_path, text, kind=kind, code=code, has_json=False, takes_plain=False)
    for name, check in conformance.CHECKS.items():
        assert check(inv) == [], name


BROKEN = [
    # piped, one rendering
    ("piped-one-rendering", "plain flag adds a line", _edit(SAYS_OK, SAYS_OK + '\nif "--plain" in words: print("  extra  thing")')),
    ("piped-one-rendering", "NO_COLOR drops a line", _edit(SAYS_OK, SAYS_OK + '\nif not os.environ.get("NO_COLOR"): print("  extra  thing")')),
    ("piped-one-rendering", "TERM changes stderr", _edit(SAYS_OK, SAYS_OK + '\nif os.environ.get("TERM") == "dumb": print("note: dumb", file=sys.stderr)')),
    # the exit code
    ("exit-code", "not the code asked for", _edit("print(\"next: tool again\")\nprint(\"note: this one is fine\", file=sys.stderr)\nsys.exit(0)", "print(\"next: tool again\")\nprint(\"note: this one is fine\", file=sys.stderr)\nsys.exit(3)")),
    ("exit-code", "another code on a terminal", _edit("print(\"note: this one is fine\", file=sys.stderr)\nsys.exit(0)", "print(\"note: this one is fine\", file=sys.stderr)\nsys.exit(0 if plain else 3)")),
    # the verdict line
    ("verdict-first", "a capital and a colon", _edit(SAYS_OK, 'print("Done: all 3 fine")')),
    ("verdict-first", "one space", _edit(SAYS_OK, 'print(f"{word} all 3 fine")')),
    ("verdict-first", "a banner first", _edit(SAYS_OK, 'print("Poisson Break")\n' + SAYS_OK)),
    ("verdict-first", "other words on a terminal", _edit(SAYS_OK, 'print(f"{word}  all 3 fine" if plain else f"{word}  3 fine")')),
    ("verdict-first", "a mark on a terminal", _edit(SAYS_OK, 'print(f"{word}  all 3 fine" if plain else f"+ {word}  all 3 fine")')),
    # plain is text
    ("plain-is-text", "an escape on a pipe", _edit('word = "ok" if plain else', 'word = "\\x1b[32mok\\x1b[0m" if plain else')),
    ("plain-is-text", "a box on a pipe", _edit(SAYS_OK, SAYS_OK + '\nif plain: print("  ──────")')),
    ("plain-is-text", "an escape on stderr under NO_COLOR", _edit(SAYS_OK, SAYS_OK + '\nif os.environ.get("NO_COLOR"): print("note: \\x1b[33mhi\\x1b[0m", file=sys.stderr)')),
    ("plain-is-text", "colour left on under NO_COLOR", _edit('word = "ok" if plain else', 'word = "ok" if not sys.stdout.isatty() else')),
    # the same facts
    ("same-facts", "pretty drops a fact", _edit('print("  label  value")', 'if plain: print("  label  value")')),
    ("same-facts", "pretty reorders", _edit('print("  label  value")\nprint("  fingerprint  abc123def456")', 'print("  label  value") if plain else None\nprint("  fingerprint  abc123def456")\nif not plain: print("  label  value")')),
    ("same-facts", "pretty rounds a number", _edit('print("  label  value")', 'print("  label  value" if plain else "  label  other")')),
    # problems
    ("problems", "a stray line on stderr", _edit(SAYS_OK, SAYS_OK + '\nprint("warning: stray", file=sys.stderr)')),
    # leaks
    ("no-leaks", "a traceback", _edit(SAYS_OK, SAYS_OK + '\nprint("Traceback (most recent call last):", file=sys.stderr)')),
    ("no-leaks", "a tuple", _edit('print("  label  value")', 'print("  label  " + repr(("a", "b")))')),
    ("no-leaks", "a path as Python prints it", _edit('print("  label  value")', 'import pathlib\nprint("  label  " + repr(pathlib.PosixPath("a")))')),
    ("no-leaks", "a module id", _edit('print("  label  value")', 'print("  label  see BK12")')),
    ("no-leaks", "a rule number", _edit('print("  label  value")', 'print("  label  under L16")')),
    # a hash to paste
    ("no-hash-to-paste", "a hash in a next line", _edit('print("next: tool again")', 'print("next: tool show 1a2b3c4d")')),
    ("no-hash-to-paste", "a hash in a note", _edit('print("note: this one is fine", file=sys.stderr)', 'print("note: see 1a2b3c4d", file=sys.stderr)')),
    ("no-hash-to-paste", "a hash too long in a detail", _edit("abc123def456", "abc123def4567890")),
    # json
    ("json", "NaN", _edit('{"schema": "x/1", "verdict": "ok", "sentence": "all 3 fine"}', '{"schema": "x/1", "verdict": "ok", "sentence": "all 3 fine", "n": float("nan")}')),
    ("json", "the keys in another order", _edit('{"schema": "x/1", "verdict": "ok", "sentence": "all 3 fine"}', '{"verdict": "ok", "schema": "x/1", "sentence": "all 3 fine"}')),
    ("json", "another sentence", _edit('{"schema": "x/1", "verdict": "ok", "sentence": "all 3 fine"}', '{"schema": "x/1", "verdict": "ok", "sentence": "fine"}')),
    ("json", "two documents", _edit('{"schema": "x/1", "verdict": "ok", "sentence": "all 3 fine"}))', '{"schema": "x/1", "verdict": "ok", "sentence": "all 3 fine"}))\n    print("{}")')),
    ("json", "another document on a terminal", _edit('"sentence": "all 3 fine"}', '"sentence": "all 3 fine", "tty": sys.stdout.isatty()}')),
    ("json", "another exit code", _edit('"sentence": "all 3 fine"}))\n    sys.exit(0)', '"sentence": "all 3 fine"}))\n    sys.exit(3)')),
    # Rich absent
    ("rich-absent", "says it is missing", _edit("        plain = True\n", "        plain = True\n        print('note: install rich', file=sys.stderr)\n")),
    ("rich-absent", "colour without Rich", _edit("        plain = True\n", "        pass\n")),
]


@pytest.mark.parametrize("check, what, text", BROKEN, ids=[f"{c}-{w.replace(' ', '-')}" for c, w, _ in BROKEN])
def test_each_check_catches_a_program_that_breaks_it(tmp_path: Path, check: str, what: str, text: str) -> None:
    inv = _inv(tmp_path, text)
    assert conformance.CHECKS[check](inv), f"{check} did not catch: {what}"


BAD_BROKEN = [
    ("on stdout too", GOOD_BAD + "", 'print("oops")\n'),
    ("two error lines", GOOD_BAD, 'print("error: and again", file=sys.stderr)\n'),
]


@pytest.mark.parametrize("what, text, extra", BAD_BROKEN, ids=[w.replace(" ", "-") for w, _, _ in BAD_BROKEN])
def test_a_bad_input_must_open_with_one_error_line_and_nothing_on_stdout(tmp_path: Path, what: str, text: str, extra: str) -> None:
    inv = _inv(tmp_path, extra.join(["import sys\n", text]), kind="bad", code=2, has_json=False, takes_plain=False)
    assert conformance.CHECKS["problems"](inv), what


@pytest.mark.parametrize("what, text", [
    ("no example", GOOD_HELP.replace('print("examples:")\nprint("  tool --flag")\n', "")),
    ("no description", 'print("usage: tool")\nprint("example: tool")\n'),
    ("a non-zero exit", GOOD_HELP + "raise SystemExit(1)\n"),
    ("on stderr", "import sys\n" + GOOD_HELP + 'print("note: x", file=sys.stderr)\n'),
], ids=["no-example", "no-description", "non-zero", "stderr"])
def test_help_must_be_something_a_stranger_can_act_on(tmp_path: Path, what: str, text: str) -> None:
    inv = _inv(tmp_path, text, kind="help", has_json=False, takes_plain=False)
    assert conformance.CHECKS["help"](inv), what


def test_a_version_of_two_lines_is_caught(tmp_path: Path) -> None:
    inv = _inv(tmp_path, GOOD_VERSION + 'print("and more")\n', kind="version", has_json=False, takes_plain=False)
    assert conformance.CHECKS["help"](inv)


def test_a_later_module_only_adds_to_the_corpus(tmp_path: Path) -> None:
    """A new invocation, with a folder of its own and what it reads written there, runs through the same
    checks with nothing else changed: the shape the commands module will use."""
    seen: list[Path] = []

    def setup(folder: Path) -> None:
        seen.append(folder)
        (folder / "break.toml").write_text("settings\n")

    script = _program(tmp_path, 'import pathlib\nassert pathlib.Path("break.toml").read_text() == "settings\\n"\n' + GOOD)
    inv = replace(_inv(tmp_path, GOOD), program=(sys.executable, str(script)), setup=setup, name="a-later-verb")
    assert all(check(inv) == [] for check in conformance.CHECKS.values())
    assert seen, "the invocation's setup did not run"
