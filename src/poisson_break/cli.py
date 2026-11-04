"""The command a user types: ``poisson-break``.

This build has the front door and no verbs yet: ``--version`` prints one line with the
versions of Break, Prove, Trace and Python; ``--help`` prints help a stranger can act on; a bare
``poisson-break`` prints the help. ``python -m poisson_break`` is the same command.

``main(argv=None, *, prog=None)`` runs the command on ``argv`` (the process's own arguments by
default) and returns its exit code. ``prog`` is the command's name as the user typed it, and
every command named in any output is rendered from it, never from a literal, so the same code
can run as ``poisson break`` later without a change here.

A mistake on the command line is one ``error:`` line on stderr, in plain words, with the
command to run next under it, and exit 2. Abbreviated options are refused. Nothing here reads
a key, opens a socket or imports a framework.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

__all__ = ["main", "build_parser", "version_line"]

DEFAULT_PROG = "poisson-break"

EXIT_DONE = 0
EXIT_USAGE = 2

_DESCRIPTION = (
    "Poisson Break finds where an AI agent fails. It runs the agent you already have, many "
    "times, while changing what the user asks, how the tools behave and how the conversation "
    "goes, and keeps the conditions that fail more than a control. Break calls your tools for "
    "real: run it against a test environment. This build has the command and no verbs yet."
)


class _Usage(Exception):
    """A mistake on the command line, in plain words."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class _Exit(Exception):
    """argparse asked to leave with a code: the help was printed."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


class _Formatter(argparse.HelpFormatter):
    """argparse's own formatter, except that the examples and the exit codes are kept as
    written, one per line."""

    def _fill_text(self, text: str, width: int, indent: str) -> str:
        if text.lstrip().startswith(("examples:", "exit codes:")):
            return "\n".join(indent + line for line in text.splitlines())
        return super()._fill_text(text, width, indent)


class _Parser(argparse.ArgumentParser):
    """A command-line mistake raises ``_Usage``; leaving raises ``_Exit``; nothing here calls
    ``sys.exit``, so ``main`` always returns a code."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _Usage(_plain_words(message))

    def exit(self, status: int = 0, message: str | None = None) -> None:  # type: ignore[override]
        if message:
            sys.stderr.write(message)
        raise _Exit(status)


def _plain_words(message: str) -> str:
    """argparse's message as one plain sentence."""
    prefix = "unrecognized arguments: "
    if message.startswith(prefix):
        words = message[len(prefix):].split()
        first = words[0] if words else ""
        what = "an option" if first.startswith("-") else "a command"
        return f'"{first}" is not {what} this command knows'
    if message.startswith("argument --version: ignored explicit argument"):
        return "--version takes no value"
    return message


def build_parser(prog: str) -> argparse.ArgumentParser:
    """The command's parser, every usage line and command it names starting with ``prog``."""
    parser = _Parser(
        prog=prog,
        description=_DESCRIPTION,
        epilog=(
            "examples:\n"
            f"  {prog} --version\n"
            f"  {prog} --help\n"
            "\n"
            "exit codes:\n"
            "  0  done\n"
            "  2  the command line is wrong"
        ),
        formatter_class=_Formatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--version", action="store_true",
        help="print the versions of Break, Prove, Trace and Python on one line, and exit",
    )
    return parser


def version_line() -> str:
    """``poisson-break X (poisson-prove Y, poisson-trace Z, Python P)``: what is installed."""
    import importlib.metadata
    import platform

    from poisson_break import __version__

    def installed(distribution: str) -> str:
        try:
            return importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            return "not installed"

    return (f"poisson-break {__version__} (poisson-prove {installed('poisson-prove')}, "
            f"poisson-trace {installed('poisson-trace')}, Python {platform.python_version()})")


def _error(message: str, nexts: Sequence[str]) -> None:
    sys.stderr.write(f"error: {message}\n")
    for command in nexts:
        sys.stderr.write(f"  next: {command}\n")
    sys.stderr.flush()


def main(argv: Sequence[str] | None = None, *, prog: str | None = None) -> int:
    """Run the command on ``argv`` and return its exit code; ``prog`` is the command's name as
    the user typed it."""
    prog = prog or DEFAULT_PROG
    words = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser(prog)
    try:
        args = parser.parse_args(words)
    except _Usage as wrong:
        _error(wrong.message, [f"{prog} --help"])
        return EXIT_USAGE
    except _Exit as left:
        return left.code
    if args.version:
        sys.stdout.write(version_line() + "\n")
        sys.stdout.flush()
        return EXIT_DONE
    parser.print_help()
    sys.stdout.flush()
    return EXIT_DONE
