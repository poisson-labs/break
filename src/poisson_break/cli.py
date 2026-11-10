"""The command a user types: ``poisson-break``, and its eight verbs.

``init`` asks the questions of the settings file and writes ``break.toml``; ``doctor`` checks
the settings, loads the target and lists its tools, and runs one case once if asked; ``hunt``
runs the control, search and shrink stages and writes the candidates; ``confirm`` tests them
against a control on fresh runs and keeps what holds as findings; ``findings`` lists them or
shows one; ``replay`` runs one finding once and shows what the agent did, call by call;
``recheck`` runs the findings on the agent as it is now and prints Trace's answer for each;
``catalog`` lists every change Break knows. ``python -m poisson_break`` is the same command.

**The command computes nothing.** Every number it prints is the library's: the settings module
reads and writes ``break.toml`` and works out a plan's counts, the runs module runs and stores
the arms, the search module proposes and scores, the confirm module asks Trace and writes the
findings. What is here is the command line, the words on screen, and the order of the calls.

**Everything printed goes through the look** (``poisson_break.look``): one result a verb,
pretty on a terminal and plain anywhere else, problems as one ``error:`` line on stderr with the
command to run next under it, questions on stderr, progress on stderr only where that is a
terminal, and ``--json`` as one strict document. ``--plain`` and ``--debug`` are the tool's own
options and may come before or after the verb; a verb's own options follow it. A mistake on the
command line is exit 2, a refusal before anything was spent exit 1, a stop after work started
exit 3, a check asked for that did not pass exit 4, Ctrl-C exit 130.

**Before anything is spent** a verb shows its plan and asks ``start?``; ``--yes`` answers,
``--dry-run`` shows the plan and runs nothing, and a stdin that is not a terminal without
``--yes`` prints the plan and refuses. The note that Break calls your tools for real follows
every plan, and is in ``init``'s and ``doctor``'s output. A stage that stops short says what was
kept and prints the command that goes on with the same hunt, and no command printed here asks
anyone to paste a hash: hunts and arms are named, findings numbered.

``main(argv=None, *, prog=None)`` runs the command on ``argv`` (the process's own arguments by
default) and returns its exit code. ``prog`` is the command's name as the user typed it, and
every command named in any output is rendered from it, never from a literal, so the same code
runs as ``poisson break`` without a change here. The command reaches the library through public
names only, which a test holds by reading this file. It reads no key and opens no socket.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import random
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from poisson_break import look
from poisson_break.apply import ToolRefused, wrapped_while
from poisson_break.changes import (
    CATALOG,
    ChangeError,
    Condition,
    InstrumentError,
    check_capabilities,
    check_registered,
    parse,
)
from poisson_break.changes import name as condition_name
from poisson_break.settings import (
    INIT_FLAGS,
    Settings,
    SettingsError,
    dump,
    equivalent_init_command,
    install_command,
    load,
    plan_confirm,
    plan_hunt,
    read_cases,
    settings_from_init_args,
)

__all__ = ["main", "build_parser", "version_line"]

DEFAULT_PROG = "poisson-break"
SETTINGS_FILE = "break.toml"

EXIT_DONE = look.EXIT["done"]
EXIT_USAGE = look.EXIT["usage"]
EXIT_STOPPED = look.EXIT["stopped"]
EXIT_CHECK = look.EXIT["check"]
EXIT_INTERRUPTED = look.EXIT["interrupted"]

#: The sentence every plan is followed by, and ``init`` and ``doctor`` end with.
REAL = ("Break calls your tools for real: run it against a test environment, never against "
        "anything that matters")

#: The look's own two options, which the lines `init` prints back leave out.
_LOOKS_OWN = ("--plain", "--debug")
#: The one placeholder a printed command may hold, where only the user knows the value.
_ENTRY_PLACEHOLDER = "MODULE:NAME"
#: The six kinds of target as `break.toml` writes them, each with a few words for the menu;
#: the core's own kind last, where the menu opens.
_KINDS = (
    ("openai-agents", "an agent built with the OpenAI Agents SDK"),
    ("langgraph", "a LangGraph graph"),
    ("crewai", "a CrewAI crew"),
    ("mcp", "an MCP server"),
    ("command", "a program on its standard input and output"),
    ("rollout", "a function Break can call"),
)
_DEFAULT_KIND = "rollout"
_STARTER_CASES = (
    {"id": "order-status", "input": "Where is my order 4821?"},
    {"id": "refund", "input": "I want a refund for order 4821, it arrived broken."},
    {"id": "address", "input": "Change the delivery address of order 4821 to 12 Elm Street."},
)

_DESCRIPTION = (
    "Poisson Break finds where an AI agent fails. It runs the agent you already have, many "
    "times, while changing what the user asks, how the tools behave and how the conversation "
    "goes, and keeps the conditions that fail more than a control. Break calls your tools for "
    "real: run it against a test environment."
)

#: Each verb, with the one line its help opens with.
_VERBS: Mapping[str, str] = {
    "init": "ask a few questions and write break.toml, the settings every other command reads",
    "doctor": ("check break.toml, load the target and list its tools; with --run, run one case "
               "once, asked first"),
    "hunt": "run the control, search and shrink stages, and write the candidates",
    "confirm": ("test the candidates against a control on fresh runs, and keep the ones that "
                "fail more as findings"),
    "findings": "list the latest hunt's findings, or show one",
    "replay": "run one finding once and show what the agent did, call by call",
    "recheck": ("run the findings on the agent as it is now, and say for each whether it fails "
                "less, with Trace's full report"),
    "catalog": "list every change Break knows, one line each",
}


def _schema(verb: str) -> str:
    """The name of the document ``--json`` writes for a verb's result."""
    return f"poisson_break.{verb}-result/1"


def _ours(prog: str, *words: str) -> str:
    """A command of ours for the user to run: ``prog`` as the user typed it, then each word
    quoted as a shell needs it."""
    return look.command(prog, *(look.word(word) for word in words))


def _n(count: int, noun: str) -> str:
    """A count and its noun, as every line says it: the noun singular for one."""
    return f"{look.fmt_count(count)} {noun if count == 1 else noun + 's'}"


def _hours(hours: float) -> str:
    """A cap in hours, the word singular for one."""
    return f"{hours:g} {'hour' if hours == 1 else 'hours'}"


def _plan_schema(verb: str) -> str:
    """The name of the document ``--json`` writes for a verb's plan: one name a verb, since
    each verb's plan has its own fields."""
    return f"poisson_break.{verb}-plan/1"


# ---------------------------------------------------------------------------
# the command line
# ---------------------------------------------------------------------------


class _Usage(Exception):
    """A mistake on the command line, in plain words."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class _Exit(Exception):
    """The command is to leave with a code: the help was printed, or a question was answered
    no and the result that says so is on stdout."""

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
    ``sys.exit``, so ``main`` always returns a code. What argparse prints goes through the look."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _Usage(_plain_words(message))

    def exit(self, status: int = 0, message: str | None = None) -> None:  # type: ignore[override]
        if message:
            look.err(message)
        raise _Exit(status)

    def _print_message(self, message: str, file: object = None) -> None:
        if message:
            (look.err if file is sys.stderr else look.out)(message)


def _plain_words(message: str) -> str:
    """argparse's message as one plain sentence, with no Python value in it."""
    prefix = "unrecognized arguments: "
    if message.startswith(prefix):
        words = message[len(prefix):].split()
        first = words[0] if words else ""
        what = "an option" if first.startswith("-") else "a command"
        return f'"{first}" is not {what} this command knows'
    head, _, rest = message.partition(": ")
    if head.startswith("argument ") and rest.startswith("invalid choice: "):
        chosen = rest[len("invalid choice: "):].split(" (", 1)[0].strip("'\"")
        return f'"{chosen}" is not a command this command knows'
    if head.startswith("argument ") and rest.startswith("invalid int value: "):
        given = rest[len("invalid int value: "):].strip("'\"")
        return f'{head[len("argument "):]} takes a whole number, and "{given}" is not one'
    if head.startswith("argument ") and rest.startswith("ignored explicit argument"):
        return f"{head[len('argument '):]} takes no value"
    if head.startswith("argument ") and rest.startswith("expected one argument"):
        return f"{head[len('argument '):]} needs a value after it"
    if message.startswith("the following arguments are required: "):
        return f"{message[len('the following arguments are required: '):]} is needed"
    return message.replace("'", "")


def _examples(prog: str, *lines: str) -> str:
    return "examples:\n" + "\n".join(f"  {prog} {line}".rstrip() for line in lines)


def _common(parser: argparse.ArgumentParser) -> None:
    """What every verb takes: the look's two options, which may also come before the verb, and
    ``--json``."""
    parser.add_argument("--plain", action="store_true", default=argparse.SUPPRESS,
                        help="print plain text, with no colour, on a terminal too")
    parser.add_argument("--debug", action="store_true", default=argparse.SUPPRESS,
                        help="print the details of an unexpected failure as well as writing "
                             "them to the log")
    parser.add_argument("--json", action="store_true",
                        help="print the result as one JSON document instead of text")


def _spending(parser: argparse.ArgumentParser, what: str) -> None:
    """What a verb that spends takes: the answer to its question, and the plan alone."""
    parser.add_argument("--yes", action="store_true",
                        help=f"answer yes to the question before {what}, so nothing is asked")
    parser.add_argument("--dry-run", action="store_true",
                        help="show the plan and run nothing")


def _hunt_option(parser: argparse.ArgumentParser, what: str) -> None:
    parser.add_argument("--hunt", metavar="NAME",
                        help=f"the hunt to {what}, by its name; the latest hunt when left out")


def build_parser(prog: str) -> argparse.ArgumentParser:
    """The command's parser, every usage line and command it names starting with ``prog``."""
    parser = _Parser(
        prog=prog,
        description=_DESCRIPTION + " Each command's own help says what it does and takes.",
        epilog=(_examples(prog, "init", "doctor", "hunt", "confirm", "findings 1", "--version")
                + "\n\nexit codes:\n"
                "  0  done\n"
                "  1  refused: nothing was spent or written\n"
                "  2  the command line is wrong\n"
                "  3  stopped after work started, or an unexpected failure\n"
                "  4  a check you asked for did not pass\n"
                "  130  interrupted"),
        formatter_class=_Formatter,
        allow_abbrev=False,
    )
    parser.add_argument("--version", action="store_true",
                        help="print the versions of Break, Prove, Trace and Python on one line, "
                             "and exit")
    parser.add_argument("--plain", action="store_true",
                        help="print plain text, with no colour, on a terminal too")
    parser.add_argument("--debug", action="store_true",
                        help="print the details of an unexpected failure as well as writing "
                             "them to the log")
    verbs = parser.add_subparsers(dest="verb", metavar="command", parser_class=_Parser,
                                  help="one of the eight commands below; each has its own --help")
    made: dict[str, argparse.ArgumentParser] = {}
    for verb, what in _VERBS.items():
        made[verb] = verbs.add_parser(
            verb, help=what, formatter_class=_Formatter, allow_abbrev=False,
            description=(f"{prog} {verb}: {what}. The settings are read from {SETTINGS_FILE} "
                         "in the folder the command runs in, and hunts are kept under the "
                         "folder those settings name."),
            epilog=_examples(prog, *_VERB_EXAMPLES[verb]))
        _common(made[verb])

    init = made["init"]
    for flag, key in INIT_FLAGS.items():
        if flag in ("--tool", "--env"):
            init.add_argument(flag, action="append", metavar="LINE",
                              help=(f"one line of [{key}] as the settings file writes it, such "
                                    + ("as 'lookup_order = \"read\"'; repeat it for each tool"
                                       if flag == "--tool" else
                                       "as 'inventory = [\"full\", \"empty\"]'; repeat it for "
                                       "each setting of your own")))
        else:
            init.add_argument(flag, metavar="VALUE",
                              help=f"sets {key}; left out, that question is asked, or takes its "
                                   "default under --yes")
    init.add_argument("--yes", action="store_true",
                      help="take every question's default without asking; the yes/no questions "
                           "as no")
    init.add_argument("--example", metavar="NAME",
                      help="write the example of this name into the folder, with its agent, its "
                           "cases and its settings, and ask nothing: "
                           + ", ".join(_example_names()) + "; each runs with no key")
    init.add_argument("--force", action="store_true",
                      help=f"write over a {SETTINGS_FILE}, or an example's file, that is already "
                           "here")

    doctor = made["doctor"]
    doctor.add_argument("--run", action="store_true",
                        help="also run the first case once, with no change, asked first; "
                             "nothing is stored")
    doctor.add_argument("--yes", action="store_true",
                        help="answer yes to the question --run asks, so nothing is asked")

    made["catalog"].add_argument("--labels", action="store_true",
                                 help="show, on the line of each change that has one, the labels "
                                      "it carries from two published lists: the OWASP Top 10 for "
                                      "LLM Applications 2025 and NIST AI 100-2 E2025")

    hunt = made["hunt"]
    _spending(hunt, "the first run")
    hunt.add_argument("--name", metavar="NAME",
                      help="the new hunt's name: letters, digits, dots, dashes and underscores, "
                           "at most 64; left out, the hunt is numbered from the target's name")
    hunt.add_argument("--hunt", metavar="NAME",
                      help="go on with the hunt of this name where it stopped, instead of "
                           "starting a new one")

    confirm = made["confirm"]
    _spending(confirm, "the first run")
    _hunt_option(confirm, "confirm the candidates of")
    confirm.add_argument("--repeats", type=int, metavar="N",
                         help="ask again about the candidates the latest stage called too small "
                              "to tell, each N times on fresh runs; left out, the stage runs or "
                              "is finished as it was written")

    findings = made["findings"]
    findings.add_argument("number", nargs="?", type=int, metavar="N",
                          help="the finding to show whole; left out, every finding is listed")
    _hunt_option(findings, "read")

    replay = made["replay"]
    replay.add_argument("number", type=int, metavar="N", help="the finding to run once")
    _hunt_option(replay, "read")
    replay.add_argument("--case", metavar="ID",
                        help="the case to run it on, one of the finding's; left out, the case "
                             "that failed most under it")

    recheck = made["recheck"]
    _spending(recheck, "the first run")
    _hunt_option(recheck, "recheck the findings of")
    recheck.add_argument("--old", metavar="MODULE:NAME",
                         help="the agent as it was, to run beside the agent as it is now, so the "
                              "two are compared on runs made at the same time; left out, the "
                              "findings' own reference runs are the before")
    recheck.add_argument("--check", action="store_true",
                         help="exit 4 when any finding fails more than it did")
    recheck.add_argument("--strict", action="store_true",
                         help="with --check, a finding too small to tell fails the check too")
    return parser


_VERB_EXAMPLES: Mapping[str, tuple[str, ...]] = {
    "init": ("init", "init --example desk",
             "init --kind rollout --entry my_app.agents:refund_agent", "init --yes"),
    "doctor": ("doctor", "doctor --run"),
    "hunt": ("hunt", "hunt --name nightly", "hunt --dry-run", "hunt --hunt refund-agent-1"),
    "confirm": ("confirm", "confirm --repeats 10", "confirm --hunt refund-agent-1 --yes"),
    "findings": ("findings", "findings 2", "findings --hunt refund-agent-1"),
    "replay": ("replay 2", "replay 2 --case refund-7"),
    "recheck": ("recheck", "recheck --check", "recheck --old my_app.agents:refund_agent_v1"),
    "catalog": ("catalog", "catalog --labels", "catalog --json"),
}


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


def main(argv: Sequence[str] | None = None, *, prog: str | None = None) -> int:
    """Run the command on ``argv`` and return its exit code; ``prog`` is the command's name as
    the user typed it."""
    prog = prog or DEFAULT_PROG
    words = list(sys.argv[1:] if argv is None else argv)
    _folder_first()
    return look.run(prog, words, lambda: _command(prog, words))


def _folder_first() -> None:
    """Put the folder the command runs in first on the import path, before any verb loads an
    agent, a stand-in, a check or a strategy by its import path. ``python -m poisson_break``
    starts with it there; the installed script starts with its own folder there instead, and
    would not find a module that sits beside ``break.toml``."""
    here = os.getcwd()
    if sys.path[:1] not in ([""], [here]):
        sys.path.insert(0, "")


@dataclass(frozen=True)
class _Call:
    """One run of the command: its name, the words after it, and what the parser read."""

    prog: str
    words: tuple[str, ...]
    args: Any

    @property
    def own_words(self) -> tuple[str, ...]:
        """The user's own words, less the look's two options, which a line printed back for the
        user to run leaves out so that the plain and the pretty run print the same line."""
        return tuple(word for word in self.words if word not in _LOOKS_OWN)


def _command(prog: str, words: Sequence[str]) -> int:
    """What the command does, under the look: a mistake on the command line is the look's
    ``Usage``, and anything unexpected is the look's one line."""
    parser = build_parser(prog)
    try:
        args = parser.parse_args(list(words))
    except _Usage as wrong:
        raise look.Usage(wrong.message, nexts=(_ours(prog, "--help"),)) from None
    except _Exit as left:
        return left.code
    if args.version:
        look.out(version_line() + "\n")
        return EXIT_DONE
    if args.verb is None:
        look.out(parser.format_help())
        return EXIT_DONE
    try:
        return _RUN[args.verb](_Call(prog, tuple(words), args))
    except _Exit as left:
        return left.code


# ---------------------------------------------------------------------------
# what the verbs share
# ---------------------------------------------------------------------------


def _refusals() -> tuple[type[Exception], ...]:
    """What the library refuses with, before any run or after: each is one plain line."""
    from poisson_break.confirm import ConfirmError
    from poisson_break.hunt import HuntError
    from poisson_break.search import SearchError

    return (SettingsError, HuntError, ChangeError, ToolRefused, SearchError, ConfirmError,
            InstrumentError)


def _one_line(wrong: BaseException) -> str:
    text = " ".join(str(wrong).split())
    return text or type(wrong).__name__


def _settings(call: _Call) -> Settings:
    """The settings of the folder the command runs in, or a refusal naming ``doctor``; with
    no settings file, naming ``init``."""
    path = Path(SETTINGS_FILE)
    try:
        return load(path)
    except SettingsError as wrong:
        verb = "doctor" if path.exists() else "init"
        raise look.Refused(_one_line(wrong), nexts=(_ours(call.prog, verb),)) from None


def _cases(call: _Call, settings: Settings) -> tuple[dict[str, Any], ...]:
    try:
        return read_cases(Path(settings.target.cases))
    except SettingsError as wrong:
        raise look.Refused(_one_line(wrong), nexts=(_ours(call.prog, "doctor"),)) from None


def _target(call: _Call, settings: Settings) -> Any:
    from poisson_break.hunt import load_target

    try:
        return load_target(settings)
    except _refusals() as wrong:
        raise look.Refused(_one_line(wrong), nexts=(_ours(call.prog, "doctor"),)) from None


def _which(call: _Call, settings: Settings) -> str:
    """The hunt a reading or confirming verb works on: the one named with ``--hunt``, else the
    latest; with no hunt yet, a refusal naming ``hunt``."""
    from poisson_break.hunt import latest_hunt

    if call.args.hunt is not None:
        return str(call.args.hunt)
    latest = latest_hunt(settings)
    if latest is None:
        raise look.Refused("there is no hunt yet", nexts=(_ours(call.prog, "hunt"),))
    return latest


def _open(call: _Call, settings: Settings, *, name: str | None, existing: bool,
          target: Any = None) -> Any:
    """A hunt opened, or made: every refusal the runs module has before any run, as one line
    naming ``doctor``, or ``hunt`` for a hunt that is not there."""
    from poisson_break.hunt import HuntError, open_hunt

    cases = _cases(call, settings)
    made = _target(call, settings) if target is None else target
    try:
        return open_hunt(settings, target=made, cases=cases, name=name, existing=existing)
    except HuntError as wrong:
        verb = "hunt" if existing and "no hunt named" in str(wrong) else "doctor"
        raise look.Refused(_one_line(wrong), nexts=(_ours(call.prog, verb),)) from None
    except _refusals() as wrong:
        raise look.Refused(_one_line(wrong), nexts=(_ours(call.prog, "doctor"),)) from None


def _has_turns(cases: Iterable[Mapping[str, Any]]) -> bool:
    return any("turns" in case for case in cases)


def _init_line(call: _Call, settings: Settings, cases: Iterable[Mapping[str, Any]],
               *more: str) -> str:
    """The one ``init`` command that writes these settings back as they are, with ``more`` words
    added: the settings module's own equivalent command, stating the conversation when a case
    has turns and the settings leave it empty (so that ``--yes``, whose conversation default is
    yes, changes nothing), then ``more``, then ``--yes --force`` so it runs as printed where
    ``break.toml`` already is and no terminal is there to ask on."""
    words = [equivalent_init_command(settings, prog=call.prog)]
    if _has_turns(cases) and not settings.vary.conversation:
        words += ["--vary-conversation", look.word("[]")]
    words += [look.word(word) for word in more]
    words += ["--yes", "--force"]
    return " ".join(words)


def _classing_line(call: _Call, settings: Settings, cases: Iterable[Mapping[str, Any]],
                   tools: Sequence[str]) -> str:
    """The ``init`` command that classes each of ``tools`` off, every other choice kept: off,
    since that is the one class under which Break does nothing new to a tool it knows nothing
    about, so the hunt can start; the user reclasses it read or write to have Break vary it."""
    lines: list[str] = []
    for tool in tools:
        lines += ["--tool", f'{tool} = "off"']
    return _init_line(call, settings, cases, *lines)


def _unclassed(stop: Any) -> list[str]:
    """The tools a stop names as classed by nobody: every tool the control saw that the way in
    did not list, or the one tool a run called that the settings do not class."""
    tools = list(getattr(stop, "tools", ()) or ())
    cause = getattr(stop, "cause", None)
    if not tools and isinstance(cause, ToolRefused) and cause.tool and cause.change is None:
        tools = [cause.tool]
    return tools


def _stopped(call: _Call, settings: Settings, hunt: Any, stop: Any, verb: str,
             resume: str) -> look.Stopped:
    """A stage that stopped short, as a result: the runs module's own line, then, for a tool
    nobody classed, the ``init`` command that classes it off, then the command that goes on
    with the same hunt; exit 3."""
    nexts: list[str] = []
    tools = _unclassed(stop)
    if tools:
        nexts.append(_classing_line(call, settings, hunt.cases, tools))
    nexts.append(resume)
    data = {"hunt": hunt.name, "reason": str(getattr(stop, "reason", "")),
            "arm": str(getattr(stop, "arm", "")), "kept": int(getattr(stop, "kept", 0)),
            "unclassed": tools}
    return look.Stopped(look.Result("stopped", _one_line(stop), nexts=tuple(nexts),
                                    schema=_schema(verb), data=data), code=EXIT_STOPPED)


def _interrupted(call: _Call, hunt: Any, verb: str, resume: str, *, kept: int,
                 arm: str | None) -> look.Stopped:
    """Ctrl-C after work started: the runs kept, and how to go on; exit 130. The document
    carries a stop's keys: the reason ``interrupted``, the Prove run whose run was interrupted
    (``None`` between two), and ``kept``, the runs the stage's own arms hold."""
    data = {"hunt": hunt.name, "reason": "interrupted",
            "arm": None if arm is None else f"{hunt.name}-{arm}", "kept": kept, "unclassed": []}
    return look.Stopped(look.Result("stopped", f"interrupted: kept {_n(kept, 'run')}",
                                    nexts=(resume,), schema=_schema(verb), data=data),
                        code=EXIT_INTERRUPTED)


def _arm_running(order: Sequence[tuple[str, int]], held: Mapping[str, int]) -> str | None:
    """Of arms run one after another, in ``order`` with the runs each is made for, the one whose
    run was under way: the first the store holds with runs missing. ``None`` between two arms,
    when the next has not begun."""
    for word, cells in order:
        if word in held and held[word] < cells:
            return word
        if word not in held:
            return None
    return None


def _confirm_kept(hunt: Any, number: int) -> tuple[int, str | None]:
    """What a confirm stage stopped by Ctrl-C keeps: the rows its own arms hold (its arms, and
    the reference arms of the findings it confirmed), and the arm whose run was under way, in
    the order the confirm module runs them, the reference arms of every finding written last.
    Read through the confirm module and the runs module, after the stop."""
    from poisson_break.confirm import read_findings, read_stages

    try:
        stage = next((one for one in read_stages(hunt) if one.number == number), None)
        findings = read_findings(hunt)
    except _refusals():
        return 0, None
    if stage is None:  # stopped before the stage was written: none of its runs were made
        return 0, None
    held = hunt.stored()
    cells = len(stage.cases) * stage.repeats
    own = [word for word, _ in stage.arms]
    order = [(word, cells) for word in own]
    for finding in findings:
        reference = finding.reference[len(hunt.name) + 1:]
        order.append((reference, len(finding.cases) * finding.repeats))
        if finding.stage == number:
            own.append(reference)
    return sum(held.get(word, 0) for word in own), _arm_running(order, held)


def _recheck_kept(hunt: Any, findings: Sequence[Any], number: int,
                  with_old: bool) -> tuple[int, str | None]:
    """What a recheck stopped by Ctrl-C keeps: the rows its arms hold, both sides beside the old
    agent, and the arm whose run was under way, in the order the confirm module runs them.
    ``number`` is the recheck the plan began or took up; one numbered past it is the one the
    confirm module began instead. Read through the runs module, after the stop."""
    held = hunt.stored()
    number = max([number, *_recheck_numbers(held)])
    prefix = f"recheck-{number}-"
    order = []
    for finding in findings:
        cells = len(finding.cases) * finding.repeats
        if with_old:
            order.append((f"{prefix}{finding.number}-old", cells))
        order.append((f"{prefix}{finding.number}", cells))
    kept = sum(rows for word, rows in held.items() if word.startswith(prefix))
    return kept, _arm_running(order, held)


def _start(call: _Call, plan: look.Plan) -> bool:
    """Show the plan, say that the tools are called for real, and ask ``start?``: whether to go
    on. ``--dry-run`` shows the plan and does not. Under ``--json`` the plan is written only when
    it is the result: on a dry run, and when the question cannot be asked, where the document is
    the plan and the refusal is one line on stderr. A no is the result ``stopped  nothing was
    run``, exit 0."""
    args = call.args
    shown = not args.json or args.dry_run
    if shown:
        look.show(plan)
    look.note(REAL)
    if args.dry_run:
        return False
    try:
        go = look.ask("start?", False)
    except look.Refused:
        if not shown:
            look.show(plan)
        raise
    if not go:
        look.show(look.Result("stopped", "nothing was run", schema=plan.schema))
        raise _Exit(EXIT_DONE)
    return True


def _cap(settings: Settings) -> str:
    limits = settings.limits
    if limits.dollars is not None:
        return (f"{look.fmt_dollars(limits.dollars)}, {_n(settings.search.runs, 'run')}, "
                f"{_hours(limits.hours)}")
    return f"{_n(settings.search.runs, 'run')}, {_hours(limits.hours)}"


def _priced(settings: Settings) -> bool:
    return settings.limits.input_per_million is not None and settings.limits.dollars is not None


def _tools_text(settings: Settings) -> str:
    said = []
    for tool in settings.tools:
        how = tool.tool_class
        if tool.stand_in:
            how += ", stand-in"
        elif tool.repeatable:
            how += ", repeatable"
        said.append(f"{tool.name} ({how})")
    return ", ".join(said) or "none"


def _tool_lines(settings: Settings) -> dict[str, Any]:
    """Each tool's line as the settings file writes it, the shape the applier and the search
    read."""
    lines: dict[str, Any] = {}
    for tool in settings.tools:
        if tool.stand_in is None and not tool.repeatable:
            lines[tool.name] = tool.tool_class
            continue
        line: dict[str, Any] = {"class": tool.tool_class}
        if tool.repeatable:
            line["repeatable"] = True
        if tool.stand_in is not None:
            line["stand_in"] = tool.stand_in
        lines[tool.name] = line
    return lines


def _rate(value: float | None) -> str:
    return "no rate" if value is None else look.fmt_rate(value)


def _days(days: float) -> str:
    """A gap in days: to one decimal below ten days, whole from ten."""
    return f"{days:.1f}" if days < 10 else f"{round(days)}"


def _control_complete(hunt: Any) -> bool:
    """Whether the hunt's control arm holds every run it was made for, as the runs module reads
    its store, so that asking it for the control runs nothing."""
    cells = int(len(hunt.cases)) * int(hunt.settings.search.control_repeats)
    return bool(hunt.stored().get("control", 0) >= cells)


def _progress(label: str, total: int) -> tuple[look.Progress, Callable[[int, int], None]]:
    """Progress on stderr for a stage, and the callback that moves it to what the library has
    done so far."""
    bar = look.Progress(label, total)

    def tell(done: int, _total: int) -> None:
        if done > bar.done:
            bar.advance(done - bar.done)

    return bar, tell


# ---------------------------------------------------------------------------
# hunt
# ---------------------------------------------------------------------------


def _hunt(call: _Call) -> int:
    from poisson_break.hunt import HuntStopped, control
    from poisson_break.search import load_strategy

    args = call.args
    if args.name is not None and args.hunt is not None:
        raise look.Usage("give --name for a new hunt, or --hunt to go on with one, not both",
                         nexts=(_ours(call.prog, "hunt", "--help"),))
    settings = _settings(call)
    cases = _cases(call, settings)
    try:
        strategy = load_strategy(settings.search.strategy)
        plan = plan_hunt(settings, cases=len(cases))
    except _refusals() as wrong:
        raise look.Refused(_one_line(wrong), nexts=(_ours(call.prog, "doctor"),)) from None
    target = _target(call, settings)
    try:
        # the target's module is imported now, and with it any fault of the user's own
        check_registered(settings.vary.tools)
    except ChangeError as wrong:
        raise look.Refused(_one_line(wrong), nexts=(_ours(call.prog, "doctor"),)) from None
    word = settings.target.entry.rsplit(":", 1)[-1].split(".")[-1]
    rows: list[look.Row | look.Line | look.Table] = [
        look.Row("target", f"{settings.target.entry} ({settings.target.kind})"),
        look.Row("tools", _tools_text(settings)),
        look.Row("may change", _may_change(settings)),
        look.Row("strategy", settings.search.strategy),
        look.Row("stages", f"control {_n(plan.control_runs, 'run')}, search and "
                           f"shrink up to {look.fmt_count(plan.search_runs)}"),
        look.Row("cap", _cap(settings)),
    ]
    sentence = f"a hunt of {word} on {_n(len(cases), 'case')}, at most {_n(plan.runs, 'run')}"
    estimate, source = _hunt_estimate(settings, plan.runs)
    data: dict[str, Any] = {"dollars": None, "target": settings.target.entry,
                            "kind": settings.target.kind, "cases": len(cases), "runs": plan.runs,
                            "control_runs": plan.control_runs, "search_runs": plan.search_runs}
    resumed = args.hunt is not None
    if args.dry_run and not resumed:
        # a new hunt's dry run opens none, since opening one makes its folder
        _start(call, look.Plan(sentence, estimate=estimate, source=source, detail=tuple(rows),
                               schema=_plan_schema("hunt"), data=data))
        return EXIT_DONE

    # a hunt taken up is opened even for a dry run, so its plan is what is left: opening one
    # that is there writes nothing, and a name that is not a hunt is refused
    hunt = _open(call, settings, name=args.hunt if resumed else args.name, existing=resumed,
                 target=target)
    if resumed:
        left = max(plan.runs - hunt.budget().runs_spent, 0)
        rows.append(look.Row("left", f"{_n(left, 'run')} of {look.fmt_count(plan.runs)}"))
        data["runs"] = left
        measured = (_control_summary(call, settings, hunt, "hunt")
                    if _control_complete(hunt) else None)
        if _priced(settings):
            # its control has run, so what is left is priced at what one control run cost, as
            # confirm prices a stage
            if measured is not None and measured.dollars_per_run is not None:
                estimate, source = _spend_estimate(settings, measured, left)
                data["dollars"] = _spend_dollars(settings, measured, left)
        elif measured is not None and measured.seconds_per_run is not None:
            # no prices: the runs left, timed at what one control run took
            estimate, source = _spend_estimate(settings, measured, left)
        else:
            estimate, source = _hunt_estimate(settings, left)
    data = {"dollars": data.pop("dollars"), "hunt": hunt.name, **data}
    try:
        if not _start(call, look.Plan(sentence, estimate=estimate, source=source,
                                      detail=tuple(rows), schema=_plan_schema("hunt"),
                                      data=data)):
            return EXIT_DONE
    except (look.Refused, _Exit):
        if not resumed:
            _discard_unused(hunt)
        raise
    resume = _ours(call.prog, "hunt", "--hunt", hunt.name)

    search_rows: list[Any] = []
    shrink_rows: list[Any] = []
    arm = "control"  # the stage under way, and the arm its runs are stored in
    try:
        bar, tell = _progress("control", plan.control_runs)
        with bar:
            summary = control(hunt, on_progress=tell)
        if summary.high_base_rate and summary.rate is not None:
            look.note(f"the agent fails {look.fmt_rate(summary.rate)} of its control runs: a "
                      "search can at best find failures about twice as fast as chance here, "
                      "and those failures are the first thing to fix")
        arm = "search"
        stage = _search(hunt, settings, strategy, summary, plan, search_rows)
        arm = "shrink"
        found = _candidates(hunt, settings, stage.seen, summary, shrink_rows)
    except HuntStopped as stop:
        raise _stopped(call, settings, hunt, stop, "hunt", resume) from None
    except KeyboardInterrupt:
        raise _interrupted(call, hunt, "hunt", resume, kept=hunt.budget().runs_spent,
                           arm=arm if arm in hunt.stored() else None) from None
    except _refusals() as wrong:
        raise look.Refused(_one_line(wrong), nexts=(resume,)) from None

    if found:
        from poisson_break.confirm import write_candidates

        write_candidates(hunt, found)
    look.show(_hunt_result(call, settings, hunt, summary, stage, found, search_rows,
                           shrink_rows))
    return EXIT_DONE


def _may_change(settings: Settings) -> str:
    vary = settings.vary
    parts = [f"tool behaviour ({_n(len(vary.tools), 'fault')})",
             f"inputs ({_n(len(vary.inputs), 'operator')})"]
    if vary.conversation:
        parts.append(f"the conversation ({_n(len(vary.conversation), 'move')})")
    if vary.model:
        parts.append(f"model calls ({_n(len(vary.model), 'fault')})")
    if vary.env:
        parts.append(f"settings of your own ({look.fmt_count(len(vary.env))})")
    return ", ".join(parts)


def _hunt_estimate(settings: Settings, runs: int) -> tuple[str, str]:
    if _priced(settings):
        return (f"not known until the control stage has run; the cap is "
                f"{look.fmt_dollars(settings.limits.dollars or 0.0)}",
                "the control stage's measured cost a run, once it has run")
    return (f"at most {_n(runs, 'run')} and {_hours(settings.limits.hours)}, "
            "with no prices to put in dollars", "the settings' limits")


def _discard_unused(hunt: Any) -> None:
    """Take away a hunt that was made for this run and never used: nothing was run, so nothing
    is lost, and the next hunt takes its number."""
    import shutil

    if hunt.budget().runs_spent == 0 and not hunt.store.exists():
        shutil.rmtree(hunt.folder, ignore_errors=True)


def _search(hunt: Any, settings: Settings, strategy: Any, summary: Any, plan: Any,
            search_rows: list[Any]) -> Any:
    """The search stage, run through the search module on the hunt's budget, with every row
    the runs module made or found stored kept for the result's lines."""
    from poisson_break.hunt import run_search
    from poisson_break.search import Seen, SeenRun, allowed, read_log, search_stage

    vary = {"tools": settings.vary.tools, "inputs": settings.vary.inputs,
            "max_call": settings.vary.max_call,
            "env": {one.name: one.values for one in settings.vary.env}}
    catalogue = allowed(vary=vary, tools=_tool_lines(settings),
                        capabilities=hunt.target.capabilities())
    seen = Seen(control=summary.calls,
                runs=tuple(SeenRun(condition=row.condition, case=row.case, seed=row.seed,
                                   outcome=row.outcome) for row in summary.rows),
                proposals=read_log(hunt.proposals), budget=hunt.budget().runs_left,
                catalogue=catalogue, set_aside=summary.set_aside,
                cases_per_condition=settings.search.cases_per_condition)
    bar, tell = _progress("search", plan.search_runs)

    def run(entries: Sequence[Any]) -> list[Any]:
        rows = run_search(hunt, entries)
        search_rows.extend(rows)
        tell(len(search_rows), plan.search_runs)
        return [SeenRun(condition=row.condition, case=row.case, seed=row.seed,
                        outcome=row.outcome) for row in rows]

    with bar:
        stage = search_stage(strategy, name=settings.search.strategy, seen=seen,
                             rng=random.Random(settings.search.seed), run=run,
                             log=hunt.proposals, reserve=hunt.reserve)
    if stage.stopped is not None:
        raise stage.stopped
    return stage


def _candidates(hunt: Any, settings: Settings, seen: Any, summary: Any,
                shrink_rows: list[Any]) -> list[Condition]:
    """The candidates: the conditions that failed more than the control, best first, at most
    the settings' number, each shrunk to the smallest change that still fails as often."""
    from poisson_break.hunt import run_search
    from poisson_break.search import LogEntry, SearchError, score, shrink

    first_seen: dict[Condition, int] = {}
    for at, row in enumerate(seen.runs):
        if row.condition.changes and row.condition not in first_seen:
            first_seen[row.condition] = at
    scored: list[tuple[float, int, int, Condition]] = []
    for condition, at in first_seen.items():
        try:
            value = score(seen, condition)
        except SearchError:
            continue
        if value > 0:
            scored.append((-value, len(condition.changes), at, condition))
    scored.sort()
    reach: dict[str, int] = {}
    for per_case in summary.calls.values():
        for tool, count in per_case.items():
            reach[tool] = max(reach.get(tool, 0), count)
    found: list[Condition] = []
    bar, tell = _progress("shrink", len(scored[:settings.confirm.candidates]))
    with bar:
        for _, _, _, condition in scored[:settings.confirm.candidates]:
            cases = tuple(dict.fromkeys(row.case for row in seen.runs
                                        if row.condition == condition))

            def failures(smaller: Condition, cases: tuple[str, ...] = cases) -> int:
                entry = LogEntry(strategy=settings.search.strategy, condition=smaller,
                                 reason="shrinking a candidate", probability=1.0, state="run",
                                 cases=cases)
                rows = run_search(hunt, [entry], stage="shrink")
                shrink_rows.extend(rows)
                return sum(row.outcome == "failed" for row in rows)

            kept = shrink(condition, failures=failures, calls=reach)
            if kept not in found:
                found.append(kept)
            tell(len(found), len(scored))
    return found


def _main_kind(rows: Sequence[Any]) -> str:
    """The kind most of the failed rows have; ties go to the earlier kind in the order the
    record types list them."""
    from poisson_break.records import KINDS, SIGNALS

    order = [*KINDS, *SIGNALS]
    kinds = [row.kind for row in rows if row.outcome == "failed" and row.kind]
    if not kinds:
        return "none"
    most = max(kinds.count(kind) for kind in kinds)
    return str(min((kind for kind in kinds if kinds.count(kind) == most),
                   key=lambda kind: order.index(kind) if kind in order else len(order)))


def _coverage_line(settings: Settings, cover: Any) -> look.Line:
    bits = []
    if cover.faults_off:
        bits.append("faults turned off: " + ", ".join(cover.faults_off))
    if cover.never_called:
        bits.append("tools never called: " + ", ".join(cover.never_called))
    if cover.past_limit:
        bits.append(f"call numbers past {settings.vary.max_call}: "
                    + ", ".join(f"{tool} ({_n(count, 'call')})"
                                for tool, count in cover.past_limit.items()))
    if cover.set_aside:
        bits.append("cases set aside: " + ", ".join(cover.set_aside))
    bits.append(f"{_n(cover.singles_untried, 'single change')} and "
                f"{_n(cover.pairs_untried, 'pair')} of them untried")
    return look.Line("not looked at: " + "; ".join(bits))


def _hunt_result(call: _Call, settings: Settings, hunt: Any, summary: Any, stage: Any,
                 found: Sequence[Condition], search_rows: Sequence[Any],
                 shrink_rows: Sequence[Any]) -> look.Result:
    from poisson_break.search import coverage

    spent = hunt.budget()
    money = (f" ({look.fmt_dollars(spent.dollars_spent)})"
             if _priced(settings) and spent.dollars_spent is not None else "")
    control_text = (f"{_n(summary.runs, 'run')} · {look.fmt_count(summary.failed)} "
                    f"failed ({_rate(summary.rate)})")
    if summary.dollars_per_run is not None and _priced(settings):
        control_text += f" · {look.fmt_dollars(summary.dollars_per_run)} a run"
    if summary.set_aside:
        count = len(summary.set_aside)
        fails = "case fails" if count == 1 else "cases fail"
        control_text += (f" · {look.fmt_count(count)} {fails} every time, set aside: "
                         f"{', '.join(summary.set_aside)}")
    conditions = {row.condition for row in search_rows if row.condition.changes}
    search_text = (f"{_n(len(search_rows), 'run')} · "
                   f"{_n(len(conditions), 'condition')} tried on "
                   f"{_n(settings.search.cases_per_condition, 'case')} each")
    cover = coverage(stage.seen)
    cover_line = _coverage_line(settings, cover)
    detail: list[look.Row | look.Line | look.Table] = []
    listed: list[dict[str, Any]] = []
    if not found:
        detail.append(cover_line)
    detail += [look.Row("control", control_text), look.Row("search", search_text)]
    if found:
        table = []
        for number, condition in enumerate(found, start=1):
            rows = [row for row in shrink_rows if row.condition == condition] or \
                   [row for row in search_rows if row.condition == condition]
            failed = sum(row.outcome == "failed" for row in rows)
            kind = _main_kind(rows)
            text = condition_name(condition)
            table.append((str(number), text,
                          f"{look.fmt_count(failed)} of {look.fmt_count(len(rows))} failed", kind))
            listed.append({"number": number, "condition": text, "failed": failed,
                           "runs": len(rows), "kind": None if kind == "none" else kind})
        detail.append(look.Table(("", "condition", "failed", "kind"), tuple(table)))
        detail.append(cover_line)
        detail.append(look.Line("these are candidates, not findings: a few runs each, chosen "
                                "for having failed"))
    data: dict[str, Any] = {
        "hunt": hunt.name, "runs": spent.runs_spent,
        "dollars": spent.dollars_spent if _priced(settings) else None,
        "control": {"runs": summary.runs, "failed": summary.failed, "rate": summary.rate,
                    "set_aside": list(summary.set_aside)},
        "search": {"runs": len(search_rows), "conditions": len(conditions)},
        "candidates": listed,
        "not_looked_at": {"faults_off": list(cover.faults_off),
                          "never_called": list(cover.never_called),
                          "past_limit": dict(cover.past_limit),
                          "set_aside": list(cover.set_aside),
                          "singles_untried": cover.singles_untried,
                          "pairs_untried": cover.pairs_untried},
    }
    if found:
        return look.Result("found", f"{_n(len(found), 'candidate')} in "
                                    f"{_n(spent.runs_spent, 'run')}{money}",
                           detail=tuple(detail), nexts=(_ours(call.prog, "confirm"),),
                           schema=_schema("hunt"), data=data)
    return look.Result("nothing found", f"no condition failed more than the control in "
                                        f"{_n(spent.runs_spent, 'run')}{money}",
                       detail=tuple(detail), schema=_schema("hunt"), data=data)


# ---------------------------------------------------------------------------
# confirm
# ---------------------------------------------------------------------------


def _stage_left(stage: Any) -> int:
    """How many runs a confirm stage has left: each arm's runs less the rows the confirm module
    read in it."""
    cells = len(stage.cases) * stage.repeats
    return sum(max(cells - count, 0) for count in stage.counts.values())


def _control_summary(call: _Call, settings: Settings, hunt: Any, verb: str) -> Any:
    """What the control measured, asked of the runs module on a control that is finished, so
    nothing runs; a control with runs missing is a refusal naming the hunt to finish."""
    from poisson_break.hunt import HuntStopped, control

    if not _control_complete(hunt):
        raise look.Refused(f'the hunt "{hunt.name}" has no finished control, and candidates are '
                           "confirmed against what the control measured",
                           nexts=(_ours(call.prog, "hunt", "--hunt", hunt.name),))
    try:
        return control(hunt)
    except HuntStopped as stop:
        raise _stopped(call, settings, hunt, stop, verb,
                       _ours(call.prog, verb, "--hunt", hunt.name)) from None


def _confirm(call: _Call) -> int:
    from poisson_break.confirm import ConfirmError, confirm, design, read_candidates, read_stages
    from poisson_break.hunt import HuntStopped

    args = call.args
    settings = _settings(call)
    name = _which(call, settings)
    hunt = _open(call, settings, name=name, existing=True)
    resume = _ours(call.prog, "confirm", "--hunt", hunt.name)
    try:
        stages = read_stages(hunt)
    except _refusals() as wrong:
        # no command mends a stages file that cannot be read, and each would meet it again
        raise look.Refused(_one_line(wrong)) from None
    latest = stages[-1] if stages else None

    if args.repeats is not None:
        if args.repeats < 1:
            raise look.Usage("--repeats takes a whole number of 1 or more",
                             nexts=(_ours(call.prog, "confirm", "--help"),))
        if latest is None:
            raise look.Refused(f'the hunt "{hunt.name}" has no confirm stage yet, so nothing was '
                               "too small to tell: confirm first", nexts=(resume,))
        if _stage_left(latest):
            raise look.Refused(f"confirm stage {latest.number} of the hunt "
                               f'"{hunt.name}" has runs missing: finish it before asking again',
                               nexts=(resume,))
        try:
            judged = confirm(hunt)  # a finished stage asked again runs nothing
        except _refusals() as wrong:
            raise look.Refused(_one_line(wrong), nexts=(resume,)) from None
        small = [one for one in judged.tested if one.verdict == "too small to tell"]
        if not small:
            raise look.Refused(f"confirm stage {judged.stage} of the hunt \"{hunt.name}\" called "
                               "no candidate too small to tell, so there is nothing to ask again",
                               nexts=(_ours(call.prog, "findings", "--hunt", hunt.name),))

    try:
        candidates = read_candidates(hunt)
    except ConfirmError as wrong:
        raise look.Refused(_one_line(wrong), nexts=(_ours(call.prog, "hunt"),)) from None
    summary = _control_summary(call, settings, hunt, "confirm")
    try:
        planned = design(candidates, settings, summary)
    except ConfirmError as wrong:
        raise look.Refused(_one_line(wrong), nexts=(_ours(call.prog, "hunt"),)) from None

    rows: list[look.Row | look.Line | look.Table] = []
    data: dict[str, Any] = {"dollars": None, "hunt": hunt.name, "candidates": len(candidates)}
    left = _stage_left(latest) if latest is not None and args.repeats is None else 0
    if left:
        assert latest is not None
        arms = len(latest.arms) - 1
        sentence = (f"go on with confirm stage {latest.number} of {hunt.name}: "
                    f"{_n(arms, 'candidate')} against a control")
        rows += [look.Row("design", f"{_n(len(latest.cases), 'case')} × "
                                    f"{_n(latest.repeats, 'repeat')}, "
                                    "once with no change and once under each candidate, as "
                                    "written"),
                 look.Row("left", _n(left, "run"))]
        runs = left
        number = latest.number
        data.update(candidates=arms, stage=number, repeats=latest.repeats, runs=left)
    elif args.repeats is not None:
        assert latest is not None
        cases = len(latest.cases)
        again = plan_confirm(dataclasses.replace(
            settings, confirm=dataclasses.replace(settings.confirm, repeats=args.repeats)),
            cases=max(cases, 1), candidates=len(small))
        sentence = (f"ask again about {_n(len(small), 'candidate')} too small to tell, "
                    f"{_n(args.repeats, 'time')} each")
        rows += [look.Row("design", f"{_n(cases, 'case')} × "
                                    f"{_n(args.repeats, 'repeat')}, once with no change "
                                    f"and once under each candidate · "
                                    f"{_n(again.confirm_runs, 'run')}"),
                 look.Row("reference", f"up to {_more(again.reference_runs)}, "
                                       f"{look.fmt_count(again.reference_per_finding)} for each "
                                       "candidate that is confirmed")]
        runs = again.runs
        number = latest.number + 1
        data.update(candidates=len(small), stage=number, repeats=args.repeats,
                    asked_again=[one.condition for one in small], runs=again.runs)
    else:
        sentence = f"confirm {_n(len(candidates), 'candidate')} against a control"
        rows += [look.Row("design", f"{_n(len(planned.cases), 'case')} × "
                                    f"{_n(planned.repeats, 'repeat')}, once with no "
                                    "change and once under each candidate · "
                                    f"{_n(planned.confirm_runs, 'run')}"),
                 look.Row("reference", f"up to {_more(planned.reference_runs)}, "
                                       f"{look.fmt_count(planned.reference_per_finding)} "
                                       "for each candidate that is confirmed")]
        runs = planned.runs
        # a finished stage asked again is judged again, its references finished
        number = latest.number if latest is not None else 1
        data.update(stage=1, repeats=planned.repeats, runs=planned.runs)
    rows.append(look.Row("cap", _cap(settings)))
    rows.append(look.Line("Trace will say if this is too small to see a difference of "
                          f"{look.fmt_rate(settings.confirm.max_difference)}, and how many "
                          "repeats would be enough"))
    estimate, source = _spend_estimate(settings, summary, runs)
    data["dollars"] = _spend_dollars(settings, summary, runs)
    if not _start(call, look.Plan(sentence, estimate=estimate, source=source, detail=tuple(rows),
                                  schema=_plan_schema("confirm"), data=data)):
        return EXIT_DONE

    try:
        bar, tell = _progress("confirm", runs)
        with bar:
            done = confirm(hunt, repeats=args.repeats, on_progress=tell)
    except HuntStopped as stop:
        raise _stopped(call, settings, hunt, stop, "confirm", resume) from None
    except KeyboardInterrupt:
        kept, arm = _confirm_kept(hunt, number)
        raise _interrupted(call, hunt, "confirm", resume, kept=kept, arm=arm) from None
    except _refusals() as wrong:
        raise look.Refused(_one_line(wrong), nexts=(resume,)) from None
    look.show(_confirm_result(call, settings, hunt, done))
    return EXIT_DONE


def _spend_dollars(settings: Settings, summary: Any, runs: int) -> float | None:
    """What the estimate puts in dollars, as a number: the runs at what the control stage
    measured one to cost; ``None`` without prices or before the control has run."""
    if summary is not None and _priced(settings) and summary.dollars_per_run is not None:
        return float(runs * summary.dollars_per_run)
    return None


def _spend_estimate(settings: Settings, summary: Any, runs: int) -> tuple[str, str]:
    """A stage's estimate from what the control stage measured a run to cost."""
    if _priced(settings) and summary.dollars_per_run is not None:
        return (f"about {look.fmt_dollars(runs * summary.dollars_per_run)} for "
                f"{_n(runs, 'run')}",
                f"the control stage's {look.fmt_dollars(summary.dollars_per_run)} a run")
    if summary.seconds_per_run is not None:
        return (f"{_n(runs, 'run')}, about "
                f"{look.fmt_duration(runs * summary.seconds_per_run)}; no prices, so no dollars",
                f"the control stage's {look.fmt_duration(summary.seconds_per_run)} a run")
    return _n(runs, "run"), "the plan's counts"


def _more(runs: int) -> str:
    """A count of further runs, the noun singular for one."""
    return f"{look.fmt_count(runs)} more {'run' if runs == 1 else 'runs'}"


def _confirm_result(call: _Call, settings: Settings, hunt: Any, done: Any) -> look.Result:
    table = []
    listed = []
    control_rate = None
    for one in done.tested:
        if one.control_rate is not None:
            control_rate = one.control_rate
        verdict = one.verdict + (f", {one.note}" if one.note else "")
        if one.verdict == "too small to tell" and one.repeats_needed is not None:
            numbers = f"{_n(one.repeats_needed, 'repeat')} would decide"
        elif one.rate is None or one.difference is None:
            numbers = "no numbers"
        else:
            span = ("" if one.lo is None or one.hi is None else
                    f" ({look.fmt_rate(one.lo, signed=True)} to "
                    f"{look.fmt_rate(one.hi, signed=True)})")
            numbers = (f"{look.fmt_rate(one.rate)}   "
                       f"{look.fmt_rate(one.difference, signed=True)}{span}")
        table.append((str(one.number), one.condition, verdict, numbers))
        listed.append({"number": one.number, "condition": one.condition,
                       "verdict": one.verdict, "note": one.note, "rate": one.rate,
                       "control_rate": one.control_rate, "difference": one.difference,
                       "lo": one.lo, "hi": one.hi, "p": one.p, "adjusted_p": one.adjusted_p,
                       "repeats_needed": one.repeats_needed,
                       "no_outcome": list(one.no_outcome), "left_out": dict(one.left_out)})
    detail: list[look.Row | look.Line | look.Table] = [
        look.Table(("", "condition", "verdict", "numbers"), tuple(table))]
    folder = Path(settings.output.folder) / hunt.name / "findings"
    if done.findings:
        paths = [f"{folder.as_posix()}/{done.findings[0].number}.toml"]
        paths += [f"{finding.number}.toml" for finding in done.findings[1:]]
        detail.append(look.Row("wrote", ", ".join(paths)))
        reference_runs = len(done.findings) * done.design.reference_per_finding
        detail.append(look.Row("reference", _n(reference_runs, "run")))
    shown = "" if control_rate is None else f" ({look.fmt_rate(control_rate)})"
    verdict = "confirmed" if done.findings else "nothing confirmed"
    nexts = ((_ours(call.prog, "findings", str(done.findings[0].number)),)
             if done.findings else ())
    data = {"hunt": hunt.name, "stage": done.stage, "candidates": listed,
            "findings": [finding.number for finding in done.findings],
            "wrote": [f"{folder.as_posix()}/{finding.number}.toml" for finding in done.findings],
            "reference_runs": len(done.findings) * done.design.reference_per_finding}
    fail = "fails" if len(done.findings) == 1 else "fail"
    return look.Result(verdict, f"{look.fmt_count(len(done.findings))} of "
                                f"{_n(len(done.tested), 'candidate')} {fail} more than the "
                                f"control{shown}",
                       detail=tuple(detail), nexts=nexts, schema=_schema("confirm"), data=data)


# ---------------------------------------------------------------------------
# findings and replay
# ---------------------------------------------------------------------------


def _finding_refused(call: _Call, settings: Settings, hunt: Any, wrong: Exception,
                     numbers: Iterable[int]) -> look.Refused:
    """A refusal over a finding: for a file that is there and cannot be read as one, the path
    that leads to it from here and no command to run next, since the listing would meet the
    same file; otherwise the confirm module's line, with the listing as the next command."""
    from poisson_break.confirm import ConfirmError, read_finding

    folder = Path(settings.output.folder) / hunt.name / "findings"
    if isinstance(wrong, ConfirmError) and wrong.reason == "unknown finding":
        for number in numbers:
            path = folder / f"{number}.toml"
            if not path.exists():
                continue
            try:
                read_finding(hunt, number)
            except ConfirmError:
                return look.Refused(f"{_one_line(wrong)}: mend or remove {path.as_posix()}")
    return look.Refused(_one_line(wrong),
                        nexts=(_ours(call.prog, "findings", "--hunt", hunt.name),))


def _numbered(settings: Settings, hunt: Any) -> list[int]:
    """The numbers of the finding files a hunt has, in order."""
    folder = Path(settings.output.folder) / hunt.name / "findings"
    if not folder.is_dir():
        return []
    return sorted(int(path.stem) for path in folder.glob("*.toml")
                  if path.stem.isascii() and path.stem.isdigit() and int(path.stem) >= 1
                  and str(int(path.stem)) == path.stem)


def _findings(call: _Call) -> int:
    from poisson_break.confirm import read_finding, read_findings

    args = call.args
    settings = _settings(call)
    hunt = _open(call, settings, name=_which(call, settings), existing=True)
    if args.number is None:
        try:
            found = read_findings(hunt)
        except _refusals() as wrong:
            raise _finding_refused(call, settings, hunt, wrong, _numbered(settings, hunt)) \
                from None
        look.show(_listing(call, settings, hunt, found))
        return EXIT_DONE
    try:
        finding = read_finding(hunt, int(args.number))
    except _refusals() as wrong:
        raise _finding_refused(call, settings, hunt, wrong, [int(args.number)]) from None
    look.show(_one_finding(call, hunt, finding))
    return EXIT_DONE


def _control_failures(
        call: _Call, settings: Settings, hunt: Any
) -> tuple[list[look.Row | look.Line | look.Table], list[dict[str, Any]] | None]:
    """Each case that failed in the control, with its failed runs of its runs and its kinds,
    the cases set aside marked so, under a ``control`` heading; nothing when the control is
    not finished, since asking for it would run it, and ``None`` for the document then."""
    if not _control_complete(hunt):
        return [], None
    summary = _control_summary(call, settings, hunt, "findings")
    by_case: dict[str, list[Any]] = {}
    for row in summary.rows:
        by_case.setdefault(row.case, []).append(row)
    lines: list[look.Row | look.Line | look.Table] = []
    listed: list[dict[str, Any]] = []
    for case, rows in by_case.items():
        failed = [row for row in rows if row.outcome == "failed"]
        if not failed:
            continue
        kinds = list(dict.fromkeys(row.kind for row in failed if row.kind))
        aside = case in summary.set_aside
        text = (f"{case}  {look.fmt_count(len(failed))} of {look.fmt_count(len(rows))} failed  "
                + ", ".join(kinds) + ("  set aside" if aside else ""))
        lines.append(look.Line(text))
        listed.append({"case": case, "failed": len(failed), "runs": len(rows), "kinds": kinds,
                       "set_aside": aside})
    if lines:
        lines.insert(0, look.Line("control"))
    return lines, listed


def _listing(call: _Call, settings: Settings, hunt: Any, found: Sequence[Any]) -> look.Result:
    rows = tuple((str(finding.number), finding.condition, _rate(finding.rate),
                  "no difference" if finding.difference is None
                  else look.fmt_rate(finding.difference, signed=True)) for finding in found)
    detail: list[look.Row | look.Line | look.Table] = []
    if rows:
        detail.append(look.Table(("", "condition", "rate", "difference"), rows))
    control_lines, control_data = _control_failures(call, settings, hunt)
    detail += control_lines
    nexts = (_ours(call.prog, "findings", str(found[0].number)),) if found else ()
    data = {"hunt": hunt.name,
            "findings": [{"number": finding.number, "condition": finding.condition,
                          "rate": finding.rate, "difference": finding.difference}
                         for finding in found],
            "control": control_data}
    return look.Result("ok", f"{_n(len(found), 'finding')} in {hunt.name}",
                       detail=tuple(detail), nexts=nexts, schema=_schema("findings"), data=data)


def _counts_text(counts: Mapping[str, int]) -> str:
    return ", ".join(f"{word} {look.fmt_count(count)}" for word, count in counts.items()) or "none"


def _one_finding(call: _Call, hunt: Any, finding: Any) -> look.Result:
    span = ("" if finding.lo is None or finding.hi is None else
            f" ({look.fmt_rate(finding.lo, signed=True)} to "
            f"{look.fmt_rate(finding.hi, signed=True)})")
    detail = (
        look.Row("fails", f"{_rate(finding.rate)} under it, {_rate(finding.control_rate)} under "
                          "the control"),
        look.Row("difference", ("no difference" if finding.difference is None
                                else look.fmt_rate(finding.difference, signed=True)) + span),
        look.Row("p", (f"{'none' if finding.p is None else look.fmt_p(finding.p)}, adjusted "
                       f"{'none' if finding.adjusted_p is None else look.fmt_p(finding.adjusted_p)}"
                       f", q {look.fmt_p(finding.q)}")),
        look.Row("kinds", _counts_text(finding.kinds)),
        look.Row("signals", _counts_text(finding.signals)),
        look.Row("judged by", finding.judged_by),
        look.Row("flagged", ", ".join(finding.flagged) or "none"),
        look.Row("left out", _counts_text(finding.left_out)),
        look.Row("cases", f"{_n(len(finding.cases), 'case')} × "
                          f"{_n(finding.repeats, 'repeat')}, in confirm stage "
                          f"{look.fmt_count(finding.stage)}"),
        look.Row("arms", f"{finding.arm} against {finding.control_arm}"),
        look.Row("reference", finding.reference),
    )
    replay = _ours(call.prog, "replay", str(finding.number), "--hunt", hunt.name)
    data = {"hunt": hunt.name,
            "finding": {field.name: _plain(getattr(finding, field.name))
                        for field in dataclasses.fields(finding)}}
    return look.Result("ok", f"finding {finding.number}: {finding.condition}", detail=detail,
                       nexts=(replay, finding.trace), schema=_schema("findings"), data=data)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(held) for key, held in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _replay(call: _Call) -> int:
    from poisson_break.confirm import read_finding, replay
    from poisson_break.hunt import HuntError

    args = call.args
    settings = _settings(call)
    hunt = _open(call, settings, name=_which(call, settings), existing=True)
    try:
        finding = read_finding(hunt, int(args.number))
    except _refusals() as wrong:
        raise _finding_refused(call, settings, hunt, wrong, [int(args.number)]) from None
    if args.case is not None and args.case not in finding.cases:
        raise look.Refused(f'finding {finding.number} has no case with the id "{args.case}"',
                           nexts=(_ours(call.prog, "findings", str(finding.number),
                                               "--hunt", hunt.name),))
    look.note(REAL)
    try:
        done = replay(hunt, finding, case=args.case)
    except HuntError as wrong:
        raise look.Refused(_one_line(wrong), nexts=(_ours(
            call.prog, "findings", str(finding.number), "--hunt", hunt.name),)) from None
    except _refusals() as wrong:
        raise look.Refused(_one_line(wrong), nexts=(_ours(
            call.prog, "findings", "--hunt", hunt.name),)) from None
    data = {"hunt": hunt.name, "finding": done.finding, "case": done.case, "seed": done.seed,
            "outcome": done.outcome, "kind": done.kind, "error": done.error,
            "calls": [{"tool": one.tool, "call": one.call, "change": one.change,
                       "real_ran": one.real_ran} for one in done.calls]}
    if done.outcome not in ("failed", "ok"):
        raise look.Stopped(look.Result("stopped", done.error or "the run was not counted",
                                       schema=_schema("replay"), data=data), code=EXIT_STOPPED)
    rows = tuple((str(at), one.tool, str(one.call), one.change or "none",
                  "yes" if one.real_ran else "no") for at, one in enumerate(done.calls, start=1))
    sentence = f"finding {done.finding} on case {done.case}, seed {done.seed}"
    if done.kind:
        sentence += f": {done.kind}"
    look.show(look.Result("failed" if done.outcome == "failed" else "did not fail", sentence,
                          detail=(look.Table(("", "tool", "call", "change", "real tool ran"),
                                             rows),),
                          schema=_schema("replay"), data=data))
    return EXIT_DONE


# ---------------------------------------------------------------------------
# recheck
# ---------------------------------------------------------------------------


def _recheck_left(hunt: Any, findings: Sequence[Any]) -> tuple[int, int, bool] | None:
    """A recheck that stopped short, if the store holds one: its number, the runs it has left
    over these findings, and whether it was begun with the old agent beside the new one, read
    from the arms the runs module says the store holds. The confirm module finishes such a
    recheck before it begins another."""
    held = hunt.stored()
    number = max(_recheck_numbers(held), default=0)
    if not number:
        return None
    prefix = f"recheck-{number}-"
    with_old = any(word.startswith(prefix) and word.endswith("-old") for word in held)
    left = 0
    for finding in findings:
        cells = len(finding.cases) * finding.repeats
        now = f"{prefix}{finding.number}"
        left += max(cells - held.get(now, 0), 0)
        if with_old:
            left += max(cells - held.get(f"{now}-old", 0), 0)
    return (number, left, with_old) if left else None


def _recheck_numbers(held: Mapping[str, int]) -> list[int]:
    """The number of every recheck an arm of the store is of, from its words."""
    numbers = []
    for word in held:
        if word.startswith("recheck-"):
            head = word[len("recheck-"):].split("-", 1)[0]
            if head.isascii() and head.isdigit():
                numbers.append(int(head))
    return numbers


def _recheck(call: _Call) -> int:
    from poisson_break.confirm import read_findings, recheck
    from poisson_break.hunt import HuntStopped

    args = call.args
    settings = _settings(call)
    hunt = _open(call, settings, name=_which(call, settings), existing=True)
    try:
        findings = read_findings(hunt)
    except _refusals() as wrong:
        raise _finding_refused(call, settings, hunt, wrong, _numbered(settings, hunt)) from None
    if not findings:
        raise look.Refused(f'the hunt "{hunt.name}" has no finding to recheck: confirm its '
                           "candidates first", nexts=(_ours(call.prog, "confirm"),))
    old = None
    if args.old is not None:
        old = _target(call, dataclasses.replace(
            settings, target=dataclasses.replace(settings.target, entry=str(args.old))))

    total = sum(len(finding.cases) * finding.repeats for finding in findings)
    runs = total * (2 if old is not None else 1)
    rows: list[look.Row | look.Line | look.Table] = [
        look.Row("findings", ", ".join(f"{finding.number} {finding.condition}"
                                       for finding in findings))]
    data: dict[str, Any] = {"dollars": None, "hunt": hunt.name,
                            "findings": [finding.number for finding in findings],
                            "runs": runs, "old": args.old}
    pending = _recheck_left(hunt, findings)
    number = max(_recheck_numbers(hunt.stored()), default=0) + 1
    if pending is not None:
        number, left, with_old = pending
        sentence = f"go on with recheck {look.fmt_count(number)} of {hunt.name}, as it was begun"
        rows.append(look.Row("left", _n(left, "run")))
        runs = left
        data.update(recheck=number, runs=left)
    else:
        sentence = (f"recheck {_n(len(findings), 'finding')} on the agent as it is now"
                    + (", beside the agent as it was" if old is not None else ""))
        rows.append(look.Row("runs", f"{look.fmt_count(runs)}: each finding over the cases and "
                                     "repeats of its reference run"
                                     + (", twice" if old is not None else "")))
    rows.append(look.Row("cap", _cap(settings)))
    summary = _control_summary(call, settings, hunt, "recheck") if _control_complete(hunt) \
        else None
    estimate, source = (_spend_estimate(settings, summary, runs) if summary is not None
                        else (_n(runs, "run"), "the plan's counts"))
    data["dollars"] = _spend_dollars(settings, summary, runs)
    if not _start(call, look.Plan(sentence, estimate=estimate, source=source, detail=tuple(rows),
                                  schema=_plan_schema("recheck"), data=data)):
        return EXIT_DONE

    resume_words = ["recheck", "--hunt", hunt.name]
    if args.old is not None:
        resume_words += ["--old", str(args.old)]
    if args.check:
        resume_words.append("--check")
    if args.strict:
        resume_words.append("--strict")
    resume = _ours(call.prog, *resume_words)
    try:
        bar, tell = _progress("recheck", runs)
        with bar:
            done = recheck(hunt, old=old, on_progress=tell)
    except HuntStopped as stop:
        raise _stopped(call, settings, hunt, stop, "recheck", resume) from None
    except KeyboardInterrupt:
        kept, arm = _recheck_kept(hunt, findings, number, old is not None)
        raise _interrupted(call, hunt, "recheck", resume, kept=kept, arm=arm) from None
    except _refusals() as wrong:
        raise look.Refused(_one_line(wrong), nexts=(resume,)) from None

    detail: list[look.Row | look.Line | look.Table] = []
    listed = []
    table = []
    for one in done:
        numbers = f"{look.fmt_rate(one.rate_before)} before · {look.fmt_rate(one.rate_now)} now"
        if one.phrase == "too small to tell" and one.repeats_needed is not None:
            numbers += f" · {_n(one.repeats_needed, 'repeat')} would decide"
        table.append((str(one.finding), one.condition, one.phrase, numbers))
        listed.append({"number": one.finding, "condition": one.condition, "phrase": one.phrase,
                       "rate_before": one.rate_before, "rate_now": one.rate_now,
                       "difference": one.difference, "lo": one.lo, "hi": one.hi, "p": one.p,
                       "adjusted_p": one.adjusted_p, "repeats_needed": one.repeats_needed,
                       "gap_days": None if one.gap_days is None else float(_days(one.gap_days)),
                       "before": one.before, "now": one.now, "trace": one.trace,
                       "no_outcome": list(one.no_outcome), "left_out": dict(one.left_out)})
    # one line a finding, not a table: the rates and the repeats make a row wider than a
    # terminal, and a table that folds says more words than its plain rendering
    detail += [look.Line("  ".join(row)) for row in table]
    gaps = [one.gap_days for one in done if one.gap_days is not None]
    if gaps and old is None:
        detail.append(look.Row("gap", f"{_days(max(gaps))} days since the reference runs"))
    less = sum(one.phrase == "fails less" for one in done)
    failing = {"fails more"} | ({"too small to tell"} if args.strict else set())
    code = EXIT_CHECK if args.check and any(one.phrase in failing for one in done) else EXIT_DONE
    fail = "fails" if less == 1 else "fail"
    look.show(look.Result("rechecked", f"{look.fmt_count(less)} of {_n(len(done), 'finding')} "
                                       f"now {fail} less",
                          detail=tuple(detail), nexts=tuple(one.trace for one in done),
                          schema=_schema("recheck"),
                          data={"hunt": hunt.name, "findings": listed, "old": args.old,
                                "check": bool(args.check), "strict": bool(args.strict),
                                "passed": code == EXIT_DONE}))
    return code


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


def _doctor(call: _Call) -> int:
    from poisson_break.apply import Session
    from poisson_break.hunt import run_once
    from poisson_break.search import load_strategy

    args = call.args
    path = Path(SETTINGS_FILE)

    def problem(sentence: str, nexts: Sequence[str], **data: Any) -> int:
        # one shape for every problem: each key null or empty where it does not apply
        held = {"key": None, "line": None, "unclassed": [], **data}
        look.show(look.Result("not ready", sentence, nexts=tuple(nexts), schema=_schema("doctor"),
                              data={"settings": SETTINGS_FILE, **held}))
        return EXIT_CHECK

    try:
        settings = load(path)
        cases = read_cases(Path(settings.target.cases))
    except SettingsError as wrong:
        verb = "doctor" if path.exists() else "init"
        return problem(_one_line(wrong), (_ours(call.prog, verb),),
                       key=wrong.key, line=wrong.line)
    again = (_ours(call.prog, "doctor"),)
    try:
        target = _target(call, settings)
    except look.Refused as refused:
        return problem(refused.sentence, again)
    try:
        load_strategy(settings.search.strategy)
        check_registered(settings.vary.tools)
        capabilities = target.capabilities()
        for move in settings.vary.conversation:
            check_capabilities(parse(f"user:{move}@1"), capabilities)
        for fault in settings.vary.model:
            check_capabilities(parse(f"model:{fault}#1"), capabilities)
        Session(Condition(changes=()), seed=0, tools=_tool_lines(settings),
                capabilities=capabilities)
        if settings.fails.own is not None:
            _loads_check(settings.fails.own)
    except _refusals() as wrong:
        return problem(_one_line(wrong), again)
    tools = [tool.name for tool in target.tools()]
    detail: list[look.Row | look.Line | look.Table] = [
        look.Row("tools", ", ".join(tools) or "none")]
    data: dict[str, Any] = {"settings": SETTINGS_FILE, "target": settings.target.entry,
                            "kind": settings.target.kind, "tools": tools,
                            "cases": len(cases), "run": None}
    if args.run and look.ask("run the first case once, with no change?", False):
        first = cases[0]
        try:
            row = run_once(settings, target=target, case=first)
        except ToolRefused as refused:
            return problem(_one_line(refused),
                           (_classing_line(call, settings, cases, [refused.tool]),),
                           unclassed=[refused.tool])
        said = f"{row.case}: {row.outcome}" + (f" ({row.kind})" if row.kind else "")
        detail.append(look.Row("run", said))
        data["run"] = {"case": row.case, "outcome": row.outcome, "kind": row.kind}
    look.note(REAL)
    look.show(look.Result("ready", f"{settings.target.entry} loads, with "
                                   f"{_n(len(tools), 'tool')} and {_n(len(cases), 'case')}",
                          detail=tuple(detail), nexts=(_ours(call.prog, "hunt"),),
                          schema=_schema("doctor"), data=data))
    return EXIT_DONE


def _loads_check(entry: str) -> None:
    """Load the user's own check by its import path and run nothing: what a hunt does before
    its first run, so ``doctor`` meets the same refusal first."""
    import importlib

    module_name, colon, attribute = entry.partition(":")
    if not colon or not module_name or not attribute:
        raise InstrumentError(f'your check is named "{entry}", which is not an import path '
                              "written module:name")
    try:
        found: Any = importlib.import_module(module_name)
        for part in attribute.split("."):
            found = getattr(found, part)
    except KeyboardInterrupt:
        raise
    except BaseException as wrong:
        raise InstrumentError(f'your check, "{entry}", could not be loaded '
                              f"({_one_line(wrong)})") from wrong
    if not callable(found):
        raise InstrumentError(f'your check, "{entry}", is not something that can be called')


# ---------------------------------------------------------------------------
# catalog
# ---------------------------------------------------------------------------


LABELS_FILE = "labels.toml"


def _labels() -> list[dict[str, str]]:
    """The labels table the package carries, read where it is installed: one row a label, in
    the table's order."""
    import tomllib

    with (Path(__file__).resolve().parent / LABELS_FILE).open("rb") as held:
        rows = tomllib.load(held).get("label", [])
    return [dict(row) for row in rows]


def _catalog(call: _Call) -> int:
    rows = []
    listed: list[dict[str, Any]] = []
    with_labels = bool(call.args.labels)
    table = _labels() if with_labels else []
    for entry in CATALOG:
        what = entry.description + (" (needs an adapter: a way in that can make it)"
                                    if entry.needs_adapter else "")
        change = f"{entry.surface}:{entry.name}"
        mine = [row for row in table if row.get("change") == change]
        if mine:
            what += " [" + ", ".join(row["id"] for row in mine) + "]"
        rows.append(look.Row(change, what))
        listed.append({"surface": entry.surface, "name": entry.name,
                       "description": entry.description, "needs_adapter": entry.needs_adapter})
        if with_labels:
            listed[-1]["labels"] = [{key: value for key, value in row.items() if key != "change"}
                                    for row in mine]
    look.show(look.Result("ok", f"{_n(len(rows), 'change')} Break knows",
                          detail=tuple(rows), schema=_schema("catalog"),
                          data={"changes": listed}))
    return EXIT_DONE


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def _dest(flag: str) -> str:
    return flag.lstrip("-").replace("-", "_")


class _Dialogue:
    """``init``'s questions, asked through the look, or answered by their flags and defaults.

    Each question is skipped when its flag was given. Under ``--yes`` each takes its own
    default, the yes/no ones as no, and nothing is asked; a question that cannot be asked
    otherwise (no terminal) is the look's refusal. The answers are gathered as the words of the
    one ``init`` command that writes the same file, and the settings module reads them."""

    def __init__(self, call: _Call) -> None:
        self.call = call
        self.yes = bool(call.args.yes)
        self.given: dict[str, list[str]] = {}
        for flag in INIT_FLAGS:
            value = getattr(call.args, _dest(flag), None)
            if value is not None:
                self.given[flag] = list(value) if isinstance(value, list) else [str(value)]
        self.words: list[str] = []

    def put(self, flag: str, *values: str) -> None:
        for value in values:
            self.words += [flag, value]

    def ask(self, question: str, default: str) -> str:
        return default if self.yes else look.ask(question, default)

    def ask_yes_no(self, question: str, default: bool) -> bool:
        return default if self.yes else look.ask(question, default)

    def menu(self, question: str, default: str, choices: Sequence[str]) -> str:
        return default if self.yes else look.ask(question, default, choices)

    def run(self) -> tuple[Settings, bool, str]:
        """Ask what is not given, in the file's order, and hand back the settings the answers
        read as, whether a case has turns, and the kind chosen."""
        kind = self.kind()
        entry = self.entry()
        cases_file = self.cases_file()
        self.tools(kind, entry)
        self.failures()
        turns = self.has_turns(cases_file)
        self.may_change(turns)
        self.runs()
        self.money()
        for flag, values in self.given.items():
            if flag not in self.words:
                self.put(flag, *values)
        try:
            settings = settings_from_init_args(self.words)
        except SettingsError as wrong:
            raise look.Usage(_one_line(wrong),
                             nexts=(_ours(self.call.prog, "init", "--help"),)) from None
        return settings, turns, kind

    # --- question 1: what the agent is built with

    def kind(self) -> str:
        if "--kind" in self.given:
            kind = self.given["--kind"][0]
        else:
            lines = {f"{word} ({what})": word for word, what in _KINDS}
            default = next(line for line, word in lines.items() if word == _DEFAULT_KIND)
            kind = lines[self.menu("What is your agent built with?", default, list(lines))]
        self.put("--kind", kind)
        return kind

    # --- question 2: where it is

    def entry(self) -> str:
        if "--entry" in self.given:
            entry = self.given["--entry"][0]
        else:
            if self.yes or not look_can_ask():
                raise look.Refused(
                    "init cannot ask where the agent is: give it with --entry, as module:name",
                    nexts=(_ours(self.call.prog, *self.call.own_words, "--entry",
                                    _ENTRY_PLACEHOLDER),))
            entry = self.entry_asked()
        self.put("--entry", entry)
        return entry

    def entry_asked(self) -> str:
        import importlib.util

        if "" not in sys.path:
            sys.path.insert(0, "")
        while True:
            entry = look.ask("Where is it? A module path and a name, module:name", "")
            module, colon, attribute = entry.partition(":")
            if not entry:
                look.note("no agent was named: write it as module:name")
                continue
            if not colon or not module or not attribute:
                look.note(f'"{entry}" is not written module:name')
                continue
            try:
                found = importlib.util.find_spec(module) is not None
            except (ImportError, ValueError, AttributeError):
                found = False
            if not found:
                look.note(f'"{entry}" cannot be imported: there is no module "{module}" on the '
                          "import path from this folder")
                continue
            return entry

    # --- question 3: the cases

    def cases_file(self) -> str:
        if "--cases" in self.given:
            cases_file = self.given["--cases"][0]
        else:
            cases_file = self.ask("Where are your test cases? A file of JSON lines", "cases.jsonl")
            if not Path(cases_file).exists() and self.ask_yes_no(
                    "There is no such file. Write a starter file of three cases to edit?", False):
                Path(cases_file).write_text(
                    "".join(json.dumps(case) + "\n" for case in _STARTER_CASES), encoding="utf-8")
        self.put("--cases", cases_file)
        return cases_file

    # --- question 4: the tools

    def tools(self, kind: str, entry: str) -> None:
        if "--tool" in self.given:
            self.put("--tool", *self.given["--tool"])
            return
        found: list[str] = []
        if kind == _DEFAULT_KIND:
            if "" not in sys.path:
                sys.path.insert(0, "")
            try:
                found = list(wrapped_while(entry.partition(":")[0]))
            except Exception as wrong:
                raise look.Refused(f'init could not import "{entry}" to find its tools '
                                   f"({_one_line(wrong)})",
                                   nexts=(_ours(self.call.prog, *self.call.own_words,
                                                   "--entry", _ENTRY_PLACEHOLDER),)) from None
        if not found:
            typed = self.ask("No tool was found. Which tools does it call? Names, comma-separated",
                             "")
            found = [name.strip() for name in typed.split(",") if name.strip()]
        for tool in found:
            how = self.menu(f"{tool}: does it change things outside your test environment?",
                            "read", ["read", "write", "off"])
            if how != "write":
                self.put("--tool", f'{tool} = "{how}"')
                continue
            made_safe = self.menu(f"{tool} changes things: is it safe to repeat here, or is there "
                                  "a stand-in?", "repeatable", ["repeatable", "stand-in"])
            if made_safe == "stand-in":
                where = look.ask(f"The stand-in for {tool}, module:name", "")
                self.put("--tool", f'{tool} = {{ class = "write", stand_in = "{where}" }}')
            else:
                self.put("--tool", f'{tool} = {{ class = "write", repeatable = true }}')

    # --- question 5: what counts as a failure

    def failures(self) -> None:
        for flag, question in (
                ("--outcomes", "Which outcomes your agent reports are failures? Comma-separated, "
                               "or none"),
                ("--own-check", "Your own check function, module:name, or none")):
            if flag in self.given:
                self.put(flag, *self.given[flag])
            else:
                answer = self.ask(question, "")
                if answer:
                    self.put(flag, answer)

    def has_turns(self, cases_file: str) -> bool:
        """Whether a case in the file is a conversation. The file is read line by line as JSON,
        not through the case reader, since this is asked before the settings are written and a
        file the reader would refuse still says whether its cases have turns."""
        try:
            lines = Path(cases_file).read_text(encoding="utf-8").splitlines()
        except (OSError, ValueError):
            return False
        for line in lines:
            if not line.strip():
                continue
            try:
                case = json.loads(line)
            except ValueError:
                continue
            if isinstance(case, dict) and "turns" in case:
                return True
        return False

    # --- question 6: what Break may change

    def may_change(self, turns: bool) -> None:
        moves = ",".join(entry.name for entry in CATALOG if entry.surface == "user")
        faults = ",".join(entry.name for entry in CATALOG if entry.surface == "model")
        surfaces: tuple[tuple[str, str, bool, bool], ...] = (
            ("--vary-tools", "May Break change how the tools behave?", True, True),
            ("--vary-inputs", "May Break change what the user asks?", True, True),
            ("--vary-conversation", "May Break change the conversation?", True, turns),
            ("--vary-model", "May Break change the model's calls?", False, True),
            ("--env", "May Break change settings of your own?", False, True),
        )
        for flag, question, default, asked in surfaces:
            if flag in self.given:
                self.put(flag, *self.given[flag])
                continue
            if not asked:
                continue
            answer = self.ask_yes_no(question, default)
            if flag in ("--vary-tools", "--vary-inputs"):
                if not answer:
                    self.put(flag, "[]")
            elif flag == "--vary-conversation" and answer:
                self.put(flag, moves)
            elif flag == "--vary-model" and answer:
                self.put(flag, faults)
            elif flag == "--env" and answer:
                while True:
                    line = look.ask('A setting of your own, as name = ["a", "b"]; Enter when done',
                                    "")
                    if not line:
                        break
                    self.put(flag, line)

    # --- question 7: how many runs

    def runs(self) -> None:
        if "--runs" in self.given:
            self.put("--runs", self.given["--runs"][0])
        else:
            self.put("--runs", self.ask("How many runs may a hunt use?", "400"))

    # --- questions 8 and 9: the prices and the cap

    def money(self) -> None:
        prices = []
        for flag, question in (
                ("--input-per-million", "What does a million input tokens cost, in dollars? "
                                        "Empty: no prices, and no dollars shown"),
                ("--output-per-million", "And a million output tokens, in dollars?")):
            if flag in self.given:
                price = self.given[flag][0]
            else:
                price = self.ask(question, "")
            prices.append(price)
            if price:
                self.put(flag, price)
        if "--dollars" in self.given:
            self.put("--dollars", self.given["--dollars"][0])
        elif all(prices):
            self.put("--dollars", self.ask("What is the most a hunt may spend, in dollars?",
                                           "5.00"))


def look_can_ask() -> bool:
    """Whether a question can be asked at all: stdin is a terminal."""
    try:
        return bool(sys.stdin is not None and sys.stdin.isatty())
    except (AttributeError, ValueError):
        return False


def _examples_root() -> Path:
    """Where the examples are: in the package as the wheel carries them, or, in a checkout
    installed for development, the repository's own folder."""
    packaged = Path(__file__).resolve().parent / "examples"
    return packaged if packaged.is_dir() else Path(__file__).resolve().parents[2] / "examples"


def _example_names() -> list[str]:
    root = _examples_root()
    if not root.is_dir():
        return []
    return sorted(folder.name for folder in root.iterdir()
                  if folder.is_dir() and (folder / SETTINGS_FILE).is_file())


def _init_example(call: _Call, name: str) -> int:
    """Write an example's files into the folder, every one or none: an unknown name, another
    answer given beside it, and a file already here without ``--force`` are each refused before
    anything is written."""
    given = [flag for flag in INIT_FLAGS if getattr(call.args, _dest(flag), None) is not None]
    if given:
        raise look.Usage(f"--example writes the example's own settings and takes no {given[0]}",
                         nexts=(_ours(call.prog, "init", "--example", name),))
    names = _example_names()
    if name not in names:
        raise look.Refused(f'there is no example named "{name}": the examples are '
                           + ", ".join(names),
                           nexts=tuple(_ours(call.prog, "init", "--example", one)
                                       for one in names[:1]))
    source = _examples_root() / name
    files = sorted(path.relative_to(source) for path in source.rglob("*")
                   if path.is_file() and "__pycache__" not in path.parts
                   and path.suffix != ".pyc")
    taken = [path for path in files if path.exists()]
    if taken and not call.args.force:
        raise look.Refused(f"{taken[0].as_posix()} is already here",
                           nexts=(_ours(call.prog, *call.own_words, "--force"),))
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((source / path).read_bytes())
    settings = load(Path(SETTINGS_FILE))
    look.note(REAL)
    data = {"file": SETTINGS_FILE, "kind": settings.target.kind, "entry": settings.target.entry,
            "cases_file": settings.target.cases,
            "tools": [{"name": tool.name, "class": tool.tool_class} for tool in settings.tools],
            "install": None}
    look.show(look.Result("wrote", f"the example {name}: "
                                   + ", ".join(path.as_posix() for path in files),
                          nexts=(_ours(call.prog, "hunt"),), schema=_schema("init"), data=data))
    return EXIT_DONE


def _init(call: _Call) -> int:
    if call.args.example is not None:
        return _init_example(call, str(call.args.example))
    path = Path(SETTINGS_FILE)
    if path.exists() and not call.args.force:
        raise look.Refused(f"{SETTINGS_FILE} is already here",
                           nexts=(_ours(call.prog, *call.own_words, "--force"),))
    settings, turns, kind = _Dialogue(call).run()
    path.write_text(dump(settings), encoding="utf-8")
    look.note(REAL)
    nexts = []
    install = install_command(kind)
    if install is not None:
        nexts.append(install)
    stated = [equivalent_init_command(settings, prog=call.prog)]
    if turns and not settings.vary.conversation:
        stated += ["--vary-conversation", look.word("[]")]
    nexts.append(" ".join([*stated, "--yes"]))
    data = {"file": SETTINGS_FILE, "kind": settings.target.kind, "entry": settings.target.entry,
            "cases_file": settings.target.cases,
            "tools": [{"name": tool.name, "class": tool.tool_class} for tool in settings.tools],
            "install": install}
    look.show(look.Result("wrote", SETTINGS_FILE, nexts=tuple(nexts), schema=_schema("init"),
                          data=data))
    return EXIT_DONE


_RUN: Mapping[str, Callable[[_Call], int]] = {
    "init": _init, "doctor": _doctor, "hunt": _hunt, "confirm": _confirm,
    "findings": _findings, "replay": _replay, "recheck": _recheck, "catalog": _catalog,
}
