"""The clean-install check: the wheel built from this tree, installed into a fresh environment
outside the checkout, runs the command.

    python scripts/clean_install.py --wheel dist/poisson_break-*.whl --work WORK

WORK is a folder outside the checkout (CI uses the runner's temporary folder). The script makes
a fresh virtual environment there, installs the wheel into it with pip (its dependencies come
from PyPI, and Trace from its repository at the commit the wheel pins, which needs git and read
access to that repository), and checks, from an empty folder with its own HOME:

  * every file under src/poisson_break that is not bytecode is in the wheel, by the same path,
    and every file the wheel carries under the package is installed;
  * Rich, questionary and prompt_toolkit, which draw the command on a terminal, were installed
    as the wheel's own dependencies;
  * `poisson-break --version` exits 0 and prints one line that starts with the version this
    tree declares;
  * `python -m poisson_break --version` prints the same line;
  * `poisson-break --help` exits 0 and names the command;
  * `poisson-break bogus`, a word that is no verb, exits 2 with one `error:` line on stderr and
    nothing on stdout;
  * `poisson-break --plain --version` prints the same line as `--version`;
  * on a terminal `poisson-break bogus` draws the same `error:` line with colour, and with
    `--plain` draws it as text;
  * the package is imported from the fresh environment, not from the checkout;
  * a hunt of one run is opened and stored there, and Prove's own store reads the row back, so
    what stores a run came with the wheel too;
  * Trace came with the wheel at the one version Break reads, and Prove at the version that
    Trace pins;
  * a confirm stage of one candidate is run there and Trace's own command answers for it, so
    what confirms a finding came with the wheel too;
  * none of the above writes a file into the folder it runs in;
  * every command the README and the pages under docs/ and examples/ show runs from that
    install and exits with the code it is shown to (below).

Prints one `ok  ` or `FAIL` line per check, writes WORK/results.json, and exits 0 only when
every check held.

**The commands the pages show.** A page marks a command by putting it in a fenced block whose
info string is exactly `sh`: each line that is neither blank nor a comment is a command, and a
line ending in a backslash goes on onto the next. Every fenced block has an info string; a shell
block spelt another way (`bash`, `console`, `sh` followed by anything), a prompt in a marked
block, and a command in a block of another kind are each refused, so no command is shown that
this job does not run. Each page's commands run in the page's order, in one shell, in a fresh
empty folder of the page's own with its own HOME and no variable that names a key, a token, a
secret or a password, the fresh environment first on PATH. A command must exit 0, or N where
its last line ends in the comment `# exits N`. An install of the requirement `poisson-break`
(`pip`, `pip3`, `pipx`, `uv pip` or `python -m pip`, then `install`) installs the wheel in its
place, keeping the word's quotes and extras. The Python blocks of each extension page (the one
page under docs/ naming an interface's version constant and no other's) are one program,
written to `example.py` in a fresh folder and run there. Each export recipe page (the page under
docs/ whose title names LangSmith, Langfuse or Phoenix) shows its call to the service in blocks
tagged `python service`, which are never run; its `python` blocks are one program, written to
`recipe.py` in a fresh folder beside a copy of the page's stored export
(`docs/export/samples/<tool>-export.<ext>`), and what it writes, `<tool>.jsonl`, must equal the
stored sample byte for byte.

    python scripts/clean_install.py --list-commands --wheel WHEEL

prints what would be run and runs nothing: one JSON list, an object for each marked command and
each page's program, with `file`, `line`, `kind` (`sh` or `python`), `command` (as written),
`runs` (as run) and `exit` (the code it must exit with); the README first, then each page by its
path. A refused block makes it exit 1 with nothing on stdout and one `FILE:LINE: ` line each on
stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import pty
import re
import select
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SRC = REPO / "src" / "poisson_break"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--wheel", required=True, help="the wheel built from this tree")
    ap.add_argument("--work", help="a folder outside the checkout to work in")
    ap.add_argument("--list-commands", action="store_true",
                    help="print the commands the pages mark, as JSON, and run nothing")
    args = ap.parse_args()
    wheel = Path(args.wheel).resolve()
    if args.list_commands:
        return list_commands(wheel)
    if not args.work:
        ap.error("--work is needed: a folder outside the checkout to work in")
    work = Path(args.work).resolve()
    if REPO in work.parents or work == REPO:
        print(f"FAIL the work folder must be outside the checkout: {work}")
        return 1
    work.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []

    def check(ok: bool, what: str) -> None:
        print(f"  {'ok  ' if ok else 'FAIL'} {what}", flush=True)
        results.append({"check": what, "ok": bool(ok)})

    version = re.search(r'^__version__ = "([^"]+)"', (SRC / "__init__.py").read_text(),
                        re.MULTILINE)
    assert version, "src/poisson_break/__init__.py declares no __version__"
    declared = version.group(1)
    print(f"wheel      {wheel.name}")
    print(f"declared   {declared}")

    # 1. the wheel carries every file under the package
    with zipfile.ZipFile(wheel) as z:
        shipped = set(z.namelist())
    expected = {str(p.relative_to(SRC.parent)) for p in SRC.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    missing = sorted(expected - shipped)
    check(not missing,
          f"the wheel carries every file under src/poisson_break ({len(expected)} files)"
          + (f"; missing: {', '.join(missing)}" if missing else ""))

    # 2. a fresh environment, the wheel installed into it
    venv = work / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    py = venv / "bin" / "python"
    done = subprocess.run([str(py), "-m", "pip", "install", "--quiet", str(wheel)],
                          capture_output=True, text=True)
    check(done.returncode == 0, "pip installs the wheel into a fresh environment"
          + ("" if done.returncode == 0 else f"\n{done.stdout}\n{done.stderr}"))
    if done.returncode != 0:
        return finish(work, results)

    # 3. the installed files are the wheel's
    done = subprocess.run([str(py), "-c",
                           "import poisson_break, pathlib, json; "
                           "p = pathlib.Path(poisson_break.__file__).parent; "
                           "print(json.dumps(sorted(str(f.relative_to(p.parent)) "
                           "for f in p.rglob('*') "
                           "if f.is_file() and '__pycache__' not in f.parts)))"],
                          capture_output=True, text=True, env=fresh_env(work))
    installed = set(json.loads(done.stdout)) if done.returncode == 0 else set()
    check(expected <= installed, "every file under the package is installed")
    done = subprocess.run([str(py), "-c", "import poisson_break, sys; "
                           "print(poisson_break.__file__); "
                           "sys.exit(0 if poisson_break.__file__.startswith(sys.prefix) else 1)"],
                          capture_output=True, text=True, env=fresh_env(work))
    check(done.returncode == 0,
          f"poisson_break is imported from the fresh environment ({done.stdout.strip()})")
    done = subprocess.run([str(py), "-c", "import importlib.metadata as m, json; "
                           "print(json.dumps({n: m.version(n) "
                           "for n in ('rich', 'questionary', 'prompt_toolkit')}))"],
                          capture_output=True, text=True, env=fresh_env(work))
    drawn_with = json.loads(done.stdout) if done.returncode == 0 else {}
    check(len(drawn_with) == 3,
          "Rich, questionary and prompt_toolkit came with the wheel"
          + (f" ({', '.join(f'{n} {v}' for n, v in drawn_with.items())})" if drawn_with
             else f"\n{done.stderr}"))

    # 4. one run, stored through Prove and read back by Prove's own store
    done = subprocess.run([str(py), "-c", ONE_RUN, str(work / "one-run")],
                          capture_output=True, text=True, env=fresh_env(work))
    check(done.returncode == 0 and done.stdout.strip() == "ok 1",
          "a hunt of one run is stored in the fresh environment and Prove's store reads it back"
          + ("" if done.returncode == 0 else f"\n{done.stdout}\n{done.stderr}"))

    # 5. Trace, at the version Break reads, and a confirm stage it answers for
    done = subprocess.run([str(py), "-c", PINS], capture_output=True, text=True,
                          env=fresh_env(work))
    check(done.returncode == 0 and done.stdout.startswith("ok "),
          "Trace came with the wheel at the version Break reads, and Prove at the one Trace pins"
          + (f" ({done.stdout.strip()[3:]})" if done.returncode == 0
             else f"\n{done.stdout}\n{done.stderr}"))
    done = subprocess.run([str(py), "-c", ONE_CONFIRM, str(work / "one-confirm")],
                          capture_output=True, text=True, env=fresh_env(work))
    check(done.returncode == 0 and done.stdout.startswith("ok "),
          "a confirm stage of one candidate is run in the fresh environment and Trace answers"
          + (f" ({done.stdout.strip()[3:]})" if done.returncode == 0
             else f"\n{done.stdout}\n{done.stderr}"))

    # 6. the command, from an empty folder with its own HOME
    bin_ = venv / "bin" / "poisson-break"
    folder, env = fresh_folder(work)
    done = run([str(bin_), "--version"], folder, env)
    line = done.stdout.strip()
    print(f"           {line}")
    check(done.returncode == 0 and done.stdout.count("\n") == 1 and done.stderr == ""
          and line.startswith(f"poisson-break {declared} (poisson-prove "),
          "poisson-break --version exits 0 with one line that starts with the declared version")
    module = run([str(py), "-m", "poisson_break", "--version"], folder, env)
    check(module.returncode == 0 and module.stdout == done.stdout,
          "python -m poisson_break --version prints the same line")
    done = run([str(bin_), "--help"], folder, env)
    check(done.returncode == 0 and done.stdout.startswith("usage: poisson-break")
          and done.stderr == "", "poisson-break --help exits 0 and names the command")
    # a word that is no verb: `hunt` is one, and in an empty folder it is refused with exit 1
    done = run([str(bin_), "bogus"], folder, env)
    err = done.stderr.splitlines()
    check(done.returncode == 2 and done.stdout == "" and len(err) >= 1
          and err[0].startswith("error: ") and sum(e.startswith("error:") for e in err) == 1,
          "poisson-break bogus exits 2 with one error: line and nothing on stdout")
    said = done.stderr
    done = run([str(bin_), "--plain", "--version"], folder, env)
    check(done.returncode == 0 and done.stdout.strip() == line and done.stderr == "",
          "poisson-break --plain --version prints the same line")
    code, drawn = on_a_terminal([str(bin_), "bogus"], folder, env)
    check(code == 2 and "\x1b[" in drawn and ESCAPE.sub("", drawn) == said,
          "on a terminal poisson-break bogus draws the same error: line, with colour")
    code, drawn = on_a_terminal([str(bin_), "bogus", "--plain"], folder, env)
    check(code == 2 and drawn == said,
          "on a terminal poisson-break bogus --plain draws it as text")
    check(not any(folder.iterdir()), "nothing was written into the folder the command ran in")

    # 7. every command the README and the pages show, and each page's program
    listed, refused = marked(REPO)
    check(not refused, "every page marks its commands by the rules"
          + ("".join(f"\n{line}" for line in refused) if refused else ""))
    if not refused:
        run_marked(listed, wheel, venv, work, check)
    return finish(work, results)


# A hunt of one case, run once, on a target that calls no tool and no model: opened, run and read
# back through Prove's own store, in a folder of its own under WORK.
ONE_RUN = r'''
import shutil, sys
from pathlib import Path

from poisson_prove import Episode
from poisson_prove.store import Store

from poisson_break import hunt
from poisson_break.settings import loads

folder = Path(sys.argv[1])
shutil.rmtree(folder, ignore_errors=True)
settings = loads(f"""
version = 1
[target]
kind = "rollout"
entry = "my_app.agents:refund_agent"
[search]
control_repeats = 1
runs = 5
[output]
folder = {str(folder)!r}
""".replace("'", '"'))
target = hunt.RolloutTarget(lambda cfg, seed: Episode(outcome="done", t=0.0, horizon=1.0), tools=[])
opened = hunt.open_hunt(settings, target=target, cases=[{"id": "1", "input": "Where is order 7?"}])
summary = hunt.control(opened)
tally = Store(opened.store).tally(f"{opened.name}-control")
print("ok" if (summary.runs, summary.failed) == (1, 0) else "wrong", tally.with_outcome)
'''


# What is installed beside Break: Trace at the one version the confirm module reads, and Prove
# at the version Trace's own metadata pins.
PINS = r'''
import importlib.metadata as m

from poisson_break import confirm

trace, prove = m.version("poisson-trace"), m.version("poisson-prove")
pins = [r.replace(" ", "") for r in (m.requires("poisson-trace") or [])]
held = trace == confirm.TRACE_VERSION and f"poisson-prove=={prove}" in pins
print("ok" if held else "wrong", f"poisson-trace {trace}, poisson-prove {prove}")
'''

# A confirm stage end to end, on a target with no tool and no model whose runs fail by their
# seed: the control, one candidate written, the stage run, and Trace's own command asked for its
# test of the candidate's arm against the control arm. Which verdict comes back does not matter
# here; that Trace answered with one does.
ONE_CONFIRM = r'''
import shutil, sys
from pathlib import Path

from poisson_prove import Episode

from poisson_break import confirm, hunt
from poisson_break.settings import loads

folder = Path(sys.argv[1])
shutil.rmtree(folder, ignore_errors=True)
settings = loads(f"""
version = 1
[target]
kind = "rollout"
entry = "my_app.agents:refund_agent"
[fails]
outcomes = ["unresolved"]
[search]
control_repeats = 2
runs = 20
[confirm]
repeats = 4
[output]
folder = {str(folder)!r}
""".replace("'", '"'))
target = hunt.RolloutTarget(
    lambda cfg, seed: Episode(outcome="unresolved" if seed % 3 == 0 else "done", t=0.0,
                              horizon=1.0),
    tools=[])
cases = [{"id": str(n), "input": f"Where is order {n}? It was due on Monday."}
         for n in range(1, 7)]
opened = hunt.open_hunt(settings, target=target, cases=cases)
hunt.control(opened)
confirm.write_candidates(opened, ["input:cut_short"])
done = confirm.confirm(opened)
(tested,) = done.tested
print("ok" if tested.verdict in confirm.VERDICTS else "wrong", tested.verdict)
'''


# ---------------------------------------------------------------------------
# the commands the pages mark
# ---------------------------------------------------------------------------

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
INTERFACE_CONSTANTS = ("FAULT_INTERFACE_VERSION", "TARGET_INTERFACE_VERSION",
                       "STRATEGY_INTERFACE_VERSION", "CHECK_INTERFACE_VERSION")
RECIPE_TOOLS = ("LangSmith", "Langfuse", "Phoenix")

_FENCE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
_PROMPT = re.compile(r"^(?:\$|%|>)\s")
_SETTING = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*$")
_PYTHON = re.compile(r"^python(?:3(?:\.\d+)?)?$")
_EXITS = re.compile(r"#\s*exits\s+(\d+)\s*$")
_INSTALLER = re.compile(r"^(?:pip3?|pipx)$")
_REQUIREMENT = re.compile(
    r"""^(?P<q>['"]?)poisson-break(?P<extras>\[[^\]]*\])?"""
    r"""(?:\s*(?:===|==|>=|<=|~=|!=|<|>)[^'"\s]+)?(?P=q)$""")


def pages_of(root: Path) -> list[Path]:
    """The pages a user reads: the README, then every page under docs/ and examples/ by path."""
    rest: list[Path] = []
    for top in ("docs", "examples"):
        if (root / top).exists():
            rest += [p for p in (root / top).rglob("*.md") if p.is_file()]
    return [root / "README.md"] + sorted(rest, key=lambda p: p.relative_to(root).as_posix())


def fenced(text: str) -> list[tuple[int, str, list[str]]] | int:
    """Every fenced block: the line of its opening fence, its info string, and its lines with
    the block's indentation taken off. A fence that is never closed gives its line alone."""
    lines = text.split("\n")
    found: list[tuple[int, str, list[str]]] = []
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
            if (closing and closing["fence"][0] == fence[0]
                    and len(closing["fence"]) >= len(fence) and not closing["info"].strip()):
                break
            line = lines[j]
            body.append(line[len(indent):] if line.startswith(indent) else line.lstrip())
            j += 1
        else:
            return i + 1
        found.append((i + 1, info, body))
        i = j + 1
    return found


def looks_like_a_command(line: str) -> bool:
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
    base = word if word == "." else word.rsplit("/", 1)[-1]
    return base in COMMAND_WORDS or bool(_PYTHON.match(base))


def install_words(words: list[str]) -> bool:
    while words and _SETTING.match(words[0]):
        words = words[1:]
    if not words:
        return False
    head = words[0].rsplit("/", 1)[-1]
    if _INSTALLER.match(head):
        return words[1:2] == ["install"]
    if head == "uv":
        return words[1:3] == ["pip", "install"]
    if _PYTHON.match(head):
        return words[1:4] == ["-m", "pip", "install"]
    return False


def with_the_wheel(command: str, wheel: Path) -> tuple[str, bool]:
    """A marked command as it is run, and whether it installs the wheel: in an install, each
    word naming the requirement `poisson-break` becomes the wheel's path, quotes and extras
    kept."""
    out: list[str] = []
    installs = False
    for piece in re.split(r"(&&|\|\||;|\|)", command):
        try:
            words = shlex.split(piece.replace("\\\n", " "))
        except ValueError:
            out.append(piece)
            continue
        if not install_words(list(words)):
            out.append(piece)
            continue
        tokens = []
        for token in re.split(r"(\s+)", piece):
            match = _REQUIREMENT.match(token)
            if match:
                token = f"{match['q']}{wheel}{match['extras'] or ''}{match['q']}"
                installs = True
            tokens.append(token)
        out.append("".join(tokens))
    return "".join(out), installs


def title_of(text: str) -> str:
    for line in text.split("\n"):
        if line.startswith("# "):
            return line[2:]
    return ""


def marked(root: Path, wheel: Path | None = None) -> tuple[list[dict[str, object]], list[str]]:
    """Every marked command and every page's program, in the order they are run, and every
    refusal as `FILE:LINE: what`."""
    wheel = wheel or Path("poisson-break")
    listed: list[dict[str, object]] = []
    refused: list[str] = []
    texts = {page: page.read_text(encoding="utf-8") for page in pages_of(root)}
    docs = [page for page in texts if page.relative_to(root).parts[0] == "docs"]
    programs = {page for page in docs
                if len({c for c in INTERFACE_CONSTANTS if c in texts[page]}) == 1}
    programs |= {page for page in docs
                 if any(re.search(rf"\b{tool}\b", title_of(texts[page])) for tool in RECIPE_TOOLS)}
    for page, text in texts.items():
        name = page.relative_to(root).as_posix()
        found = fenced(text)
        if isinstance(found, int):
            refused.append(f"{name}:{found}: a fence that is never closed")
            continue
        python: list[tuple[int, list[str]]] = []
        for at, info, body in found:
            language = info.split()[0] if info.split() else ""
            if not info:
                refused.append(f"{name}:{at}: a fenced block with no info string")
            elif info == "sh":
                refused += [f"{name}:{at}: a prompt in a marked block, its line {n + 1}"
                            for n, line in enumerate(body) if _PROMPT.match(line.lstrip())]
                pending: list[str] = []
                start = 0
                for n, line in enumerate(body):
                    stripped = line.strip()
                    if not pending and (not stripped or stripped.startswith("#")):
                        continue
                    if not pending:
                        start = at + 1 + n
                    pending.append(line)
                    if not line.rstrip().endswith("\\"):
                        listed.append(_entry(name, start, "\n".join(pending), wheel))
                        pending = []
                if pending:
                    listed.append(_entry(name, start, "\n".join(pending), wheel))
            elif language == "sh" or language.lower() in OTHER_SHELLS:
                refused.append(f"{name}:{at}: a shell block tagged {info!r}, not sh")
            else:
                refused += [f"{name}:{at}: an unmarked shell block: its line {n + 1} is a command"
                            for n, line in enumerate(body) if looks_like_a_command(line)]
                if info == "python":
                    python.append((at + 1, body))
        if page in programs and python:
            code = "\n".join("\n".join(body) for _, body in python)
            listed.append({"file": name, "line": python[0][0], "kind": "python", "command": code,
                           "runs": code, "exit": 0})
    listed.sort(key=lambda e: (e["file"] != "README.md", e["file"], e["line"]))
    return listed, refused


def _entry(name: str, line: int, command: str, wheel: Path) -> dict[str, object]:
    exits = _EXITS.search(command.split("\n")[-1])
    return {"file": name, "line": line, "kind": "sh", "command": command,
            "runs": with_the_wheel(command, wheel)[0], "exit": int(exits.group(1)) if exits else 0}


def list_commands(wheel: Path) -> int:
    listed, refused = marked(REPO, wheel)
    if refused:
        for line in refused:
            print(line, file=sys.stderr)
        return 1
    print(json.dumps(listed, indent=1))
    return 0


def run_marked(listed: list[dict[str, object]], wheel: Path, venv: Path, work: Path,
               check: object) -> None:
    """Run each page's marked commands in one shell, and each page's program, from the fresh
    environment; one check for each entry, named by its file and line."""
    assert callable(check)
    by_file: dict[str, list[dict[str, object]]] = {}
    for entry in listed:
        by_file.setdefault(str(entry["file"]), []).append(entry)
    token = {k: v for k, v in os.environ.items() if k.startswith("GIT_CONFIG_")}
    for number, (name, entries) in enumerate(by_file.items(), start=1):
        folder = work / "pages" / f"{number:02d}"
        shutil.rmtree(folder, ignore_errors=True)
        env = fresh_env(folder)
        env["PATH"] = f"{venv / 'bin'}{os.pathsep}{env.get('PATH', '')}"
        commands = [e for e in entries if e["kind"] == "sh"]
        if commands:
            here = folder / "sh"
            here.mkdir(parents=True)
            codes = _in_one_shell(commands, wheel, here, folder, env, token)
            stopped = False
            for entry in commands:
                at = f"{name}:{entry['line']}"
                first = str(entry["command"]).split("\n")[0]
                code = codes.get(at)
                if code is None:
                    check(False, f"{at}  {first}  (not run: "
                                 + ("an earlier command of the page did not exit as shown)"
                                    if stopped else "the shell stopped before it)"))
                    continue
                held = code == entry["exit"]
                stopped = stopped or not held
                check(held, f"{at}  {first}" + ("" if held else
                                                 f"  (exit {code}, shown to exit {entry['exit']})"
                                                 f"\n{_tail(folder / 'sh.log')}"))
        for entry in (e for e in entries if e["kind"] == "python"):
            at = f"{name}:{entry['line']}"
            recipe = next((tool for tool in RECIPE_TOOLS
                           if re.search(rf"\b{tool}\b", title_of((REPO / name).read_text(
                               encoding="utf-8")))), None)
            here = folder / ("recipe" if recipe else "example")
            here.mkdir(parents=True)
            program = here / ("recipe.py" if recipe else "example.py")
            program.write_text(str(entry["command"]) + "\n", encoding="utf-8")
            exports = (sorted((REPO / "docs" / "export" / "samples").glob(
                f"{recipe.lower()}-export.*")) if recipe else [])
            for export in exports:
                shutil.copyfile(export, here / export.name)
            done = subprocess.run([str(venv / "bin" / "python"), program.name], cwd=here, env=env,
                                  stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  timeout=900)
            held = done.returncode == 0
            what = f"{at}  the page's program, {program.name}"
            if recipe and held:
                sample = REPO / "docs" / "export" / "samples" / f"{recipe.lower()}.jsonl"
                wrote = here / sample.name
                held = (len(exports) == 1 and wrote.is_file() and sample.is_file()
                        and wrote.read_bytes() == sample.read_bytes())
                what += f", run on {exports[0].name if exports else 'no stored export'}"
                what += f" writes {sample.name} as stored" if held else \
                    f" does not write {sample.name} as stored"
            check(held, what + ("" if done.returncode == 0
                                else f"  (exit {done.returncode})\n{done.stdout}\n{done.stderr}"))


def _in_one_shell(commands: list[dict[str, object]], wheel: Path, here: Path, folder: Path,
                  env: dict[str, str], token: dict[str, str]) -> dict[str, int]:
    """Run a page's commands in order in one shell, in ``here``; the code each exited with, by
    `FILE:LINE`. The shell stops at the first command that does not exit as it is shown to.
    Only an install of the wheel is handed the git settings the job was given."""
    status = folder / "status"
    lines = ["cd " + shlex.quote(str(here))]
    for entry in commands:
        runs, installs = with_the_wheel(str(entry["command"]), wheel)
        if installs:
            lines += [f"export {key}={shlex.quote(value)}" for key, value in token.items()]
        lines.append(runs)
        lines.append("__code=$?")
        if installs and token:
            lines.append("unset " + " ".join(token))
        lines.append(f"echo {shlex.quote(str(entry['file']) + ':' + str(entry['line']))} "
                     f"$__code >> {shlex.quote(str(status))}")
        lines.append(f"[ $__code -eq {entry['exit']} ] || exit 97")
    script = folder / "page.sh"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (folder / "sh.log").open("w", encoding="utf-8") as log:
        try:
            subprocess.run(["bash", str(script)], cwd=here, env=env, stdin=subprocess.DEVNULL,
                           stdout=log, stderr=subprocess.STDOUT, timeout=1800)
        except subprocess.TimeoutExpired:
            log.write("\nthe page's commands did not finish in 30 minutes\n")
    codes: dict[str, int] = {}
    if status.exists():
        for line in status.read_text(encoding="utf-8").splitlines():
            at, _, code = line.rpartition(" ")
            codes[at] = int(code)
    return codes


def _tail(log: Path, lines: int = 30) -> str:
    try:
        return "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def fresh_env(work: Path) -> dict[str, str]:
    home = work / "home"
    (home / "tmp").mkdir(parents=True, exist_ok=True)
    # Nothing that holds a secret reaches what is run here, and none of the git settings the
    # install was handed: only pip's install of the wheel reads those.
    env = {k: v for k, v in os.environ.items()
           if not any(w in k.upper() for w in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
           and not k.startswith("GIT_CONFIG_")
           and k not in ("PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME", "PYTHONSTARTUP")}
    env.update(HOME=str(home), TMPDIR=str(home / "tmp"), LANG="C.UTF-8", LC_ALL="C.UTF-8",
               PYTHONIOENCODING="utf-8")
    return env


def fresh_folder(work: Path) -> tuple[Path, dict[str, str]]:
    folder = Path(tempfile.mkdtemp(prefix="run-", dir=work))
    return folder, fresh_env(work)


def run(argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, timeout=120)


ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def on_a_terminal(argv: list[str], cwd: Path, env: dict[str, str]) -> tuple[int, str]:
    """Run `argv` with stdout and stderr each on a pseudo-terminal of its own, with nothing in
    the environment that turns the pretty rendering off, and return the exit code and what
    stderr drew, its line ends read as a terminal writes them."""
    env = {k: v for k, v in env.items() if k not in ("NO_COLOR", "CI", "COLUMNS", "LINES")}
    env["TERM"] = "xterm-256color"
    out_master, out_slave = pty.openpty()
    err_master, err_slave = pty.openpty()
    drawn = b""
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=out_slave, stderr=err_slave)
        code = process.wait(timeout=120)
        # this process still holds the terminals open, so what the command wrote is all there
        # to read; a read that finds nothing for a moment has read it all
        while select.select([err_master], [], [], 0.5)[0]:
            chunk = os.read(err_master, 65536)
            if not chunk:
                break
            drawn += chunk
    finally:
        for fd in (out_master, out_slave, err_master, err_slave):
            os.close(fd)
    return code, re.sub(r"\r+\n", "\n", drawn.decode("utf-8", "replace"))


def finish(work: Path, results: list[dict[str, object]]) -> int:
    (work / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    failed = [r["check"] for r in results if not r["ok"]]
    print(f"{len(results) - len(failed)} of {len(results)} checks held"
          + (f"; failed: {'; '.join(map(str, failed))}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
