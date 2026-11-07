"""The empty front door: `poisson-break --version`, `--help`, `python -m poisson_break`, the
command's name rendered from `prog`, and mistakes on the command line.

Invariants pinned here (Break — Plan, the repo module):
- BK0.1  `--version` is one line with Break's, Prove's, Trace's and Python's versions, exit 0;
         `--help` exits 0 with a description and an example; `python -m poisson_break` is the
         same command.
- BK0.2  `main(argv, prog=P)` renders every command it names from `P`; the suite runs under
         `poisson-break` and `poisson break`.
- BK0.3  An unknown verb or flag is one `error:` line on stderr and exit 2; an abbreviated flag
         is refused.
"""

from __future__ import annotations

import importlib.metadata
import platform
import re

import pytest

from tests.conftest import PROGS, run_command, run_module

VERSION_LINE = re.compile(
    r"^poisson-break (?P<break>\S+) \(poisson-prove (?P<prove>[^,)]+), "
    r"poisson-trace (?P<trace>[^,)]+), Python (?P<python>\d+\.\d+\.\d+)\)$"
)


def _main(words: list[str], prog: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    from poisson_break.cli import main

    code = main(words, prog=prog)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _version_of(distribution: str) -> str:
    return importlib.metadata.version(distribution)


# ---------------------------------------------------------------------------
# BK0.1  --version
# ---------------------------------------------------------------------------


def test_version_is_one_line_with_break_prove_and_python() -> None:
    """One line, exit 0, nothing on stderr; Break's version is the installed distribution's,
    Prove's is the installed `poisson-prove`'s, Python's is the running interpreter's."""
    ran = run_command(["--version"])
    assert ran.exit == 0
    assert ran.stderr == ""
    lines = ran.stdout.splitlines()
    assert len(lines) == 1, ran.stdout
    match = VERSION_LINE.match(lines[0])
    assert match, lines[0]
    assert match["break"] == _version_of("poisson-break")
    assert match["prove"] == _version_of("poisson-prove")
    assert match["python"] == platform.python_version()


def test_version_names_the_installed_trace() -> None:
    """The fourth version on the line is the installed `poisson-trace`'s. Trace is a
    dependency of Break (an exact pin, test_dependencies.py); this fails while it is absent."""
    ran = run_command(["--version"])
    match = VERSION_LINE.match(ran.stdout.strip())
    assert match, ran.stdout
    assert match["trace"] == _version_of("poisson-trace")


def test_version_line_is_the_same_from_the_library() -> None:
    """`poisson_break.__version__` is the version the metadata and the line carry: one version,
    declared once."""
    import poisson_break

    assert poisson_break.__version__ == _version_of("poisson-break")
    ran = run_command(["--version"])
    assert f"poisson-break {poisson_break.__version__} (" in ran.stdout


# ---------------------------------------------------------------------------
# BK0.1  --help
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_exits_0_with_a_description_and_an_example(flag: str) -> None:
    ran = run_command([flag])
    assert ran.exit == 0
    assert ran.stderr == ""
    out = ran.stdout
    assert out.startswith("usage: poisson-break"), out.splitlines()[0]
    # A description paragraph: a line of prose after the usage block, before the options.
    body = out.split("\n\n")
    assert len(body) >= 3, "the help has a usage block, a description and the options"
    description = body[1]
    assert not description.lstrip().startswith(("usage:", "options:", "positional")), description
    assert len(description.split()) >= 8, "the description is a sentence, not a label"
    # At least one example command, starting with the command's name.
    assert "examples:" in out
    examples = out.split("examples:", 1)[1]
    assert re.search(r"^\s+poisson-break( \S+)*$", examples, re.MULTILINE), examples


def test_help_gives_every_argument_help_text() -> None:
    """Every argument the parser knows has help text (rule L2 of the shared look)."""
    import argparse

    from poisson_break.cli import build_parser

    parser = build_parser("poisson-break")
    missing = [action.option_strings or [action.dest] for action in parser._actions
               if not action.help or action.help is argparse.SUPPRESS]
    assert missing == [], f"arguments without help text: {missing}"


def test_bare_command_runs_and_exits_cleanly() -> None:
    """`poisson-break` alone, off a terminal: exit 0, the help on stdout, nothing on stderr,
    nothing written to the folder it runs in."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as folder:
        ran = run_command([], cwd=Path(folder))
        assert ran.exit == 0
        assert ran.stderr == ""
        assert ran.stdout.startswith("usage: poisson-break"), ran.stdout
        assert list(Path(folder).iterdir()) == []


# ---------------------------------------------------------------------------
# BK0.1  python -m poisson_break is the same command
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("words", [["--version"], ["--help"], [], ["--bogus"], ["hunt"]])
def test_python_m_is_the_same_command(words: list[str]) -> None:
    """Same stdout, same stderr, same exit code, whichever way it is started."""
    a = run_command(words)
    b = run_module(words)
    assert (a.exit, a.stdout, a.stderr) == (b.exit, b.stdout, b.stderr)


# ---------------------------------------------------------------------------
# BK0.2  every command named is rendered from prog
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prog", PROGS)
def test_help_is_rendered_from_prog(prog: str, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _main(["--help"], prog, capsys)
    assert code == 0
    assert err == ""
    assert out.startswith(f"usage: {prog}")
    examples = out.split("examples:", 1)[1]
    assert re.search(rf"^\s+{re.escape(prog)}( \S+)*$", examples, re.MULTILINE), examples
    other = [p for p in PROGS if p != prog][0]
    assert other not in out, f"the help names {other!r} while running as {prog!r}"


@pytest.mark.parametrize("prog", PROGS)
def test_error_next_line_is_rendered_from_prog(prog: str, capsys: pytest.CaptureFixture[str]) -> None:
    """A usage error's `next:` command is the command as typed."""
    code, out, err = _main(["bogus"], prog, capsys)
    assert code == 2
    assert out == ""
    assert prog in err, err
    other = [p for p in PROGS if p != prog][0]
    assert other not in err, f"the error names {other!r} while running as {prog!r}"


@pytest.mark.parametrize("prog", PROGS)
def test_version_runs_under_both_names(prog: str, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _main(["--version"], prog, capsys)
    assert code == 0
    assert err == ""
    assert VERSION_LINE.match(out.strip()), out


def test_main_takes_argv_and_defaults_prog_to_the_command() -> None:
    """`main(argv=None, *, prog=None)`: argv defaults to the process's, prog to `poisson-break`,
    and prog is keyword-only, so `poisson break` can pass it later without touching Break."""
    import inspect

    from poisson_break.cli import main

    params = inspect.signature(main).parameters
    assert list(params) == ["argv", "prog"]
    assert params["argv"].default is None
    assert params["prog"].default is None
    assert params["prog"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["argv"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD


# ---------------------------------------------------------------------------
# BK0.3  mistakes on the command line
# ---------------------------------------------------------------------------


def _one_error_line(stderr: str) -> None:
    lines = stderr.splitlines()
    assert lines, "nothing on stderr"
    assert lines[0].startswith("error: "), lines[0]
    assert sum(line.startswith("error:") for line in lines) == 1, stderr
    for line in lines[1:]:
        assert line.startswith("  "), f"a stderr line that is neither the error nor indented: {line!r}"
    assert "Traceback" not in stderr
    assert "argparse" not in stderr.lower()


@pytest.mark.parametrize("words", [["bogus"], ["findings2"], ["--bogus"], ["--version=1"]])
def test_unknown_verb_or_flag_is_one_error_line_and_exit_2(words: list[str]) -> None:
    ran = run_command(words)
    assert ran.exit == 2, (ran.stdout, ran.stderr)
    assert ran.stdout == ""
    _one_error_line(ran.stderr)


@pytest.mark.parametrize("abbreviated", ["--vers", "--ver", "--v"])
def test_abbreviated_flag_is_refused(abbreviated: str) -> None:
    """An abbreviation of `--version` is not `--version`: exit 2, nothing on stdout."""
    ran = run_command([abbreviated])
    assert ran.exit == 2, (ran.stdout, ran.stderr)
    assert ran.stdout == ""
    _one_error_line(ran.stderr)


def test_error_carries_no_python_repr() -> None:
    """The error line is plain words: no quoted list, no tuple, no exception name."""
    ran = run_command(["hunt"])
    first = ran.stderr.splitlines()[0]
    assert not re.search(r"\[.*'.*'\]|\(.*,.*\)|Error\b|Exception\b", first), first
