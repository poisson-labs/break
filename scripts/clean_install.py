"""The clean-install check: the wheel built from this tree, installed into a fresh environment
outside the checkout, runs the command.

    python scripts/clean_install.py --wheel dist/poisson_break-*.whl --work WORK

WORK is a folder outside the checkout (CI uses the runner's temporary folder). The script makes
a fresh virtual environment there, installs the wheel into it with pip (its dependencies come
from PyPI), and checks, from an empty folder with its own HOME:

  * every file under src/poisson_break that is not bytecode is in the wheel, by the same path,
    and every file the wheel carries under the package is installed;
  * Rich, questionary and prompt_toolkit, which draw the command on a terminal, were installed
    as the wheel's own dependencies;
  * `poisson-break --version` exits 0 and prints one line that starts with the version this
    tree declares;
  * `python -m poisson_break --version` prints the same line;
  * `poisson-break --help` exits 0 and names the command;
  * `poisson-break hunt` exits 2 with one `error:` line on stderr and nothing on stdout;
  * `poisson-break --plain --version` prints the same line as `--version`;
  * on a terminal `poisson-break hunt` draws the same `error:` line with colour, and with
    `--plain` draws it as text;
  * the package is imported from the fresh environment, not from the checkout;
  * a hunt of one run is opened and stored there, and Prove's own store reads the row back, so
    what stores a run came with the wheel too;
  * none of the above writes a file into the folder it runs in.

Prints one `ok  ` or `FAIL` line per check, writes WORK/results.json, and exits 0 only when
every check held.
"""

from __future__ import annotations

import argparse
import json
import os
import pty
import re
import select
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
    ap.add_argument("--work", required=True, help="a folder outside the checkout to work in")
    args = ap.parse_args()
    wheel = Path(args.wheel).resolve()
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

    # 5. the command, from an empty folder with its own HOME
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
    done = run([str(bin_), "hunt"], folder, env)
    err = done.stderr.splitlines()
    check(done.returncode == 2 and done.stdout == "" and len(err) >= 1
          and err[0].startswith("error: ") and sum(e.startswith("error:") for e in err) == 1,
          "poisson-break hunt exits 2 with one error: line and nothing on stdout")
    said = done.stderr
    done = run([str(bin_), "--plain", "--version"], folder, env)
    check(done.returncode == 0 and done.stdout.strip() == line and done.stderr == "",
          "poisson-break --plain --version prints the same line")
    code, drawn = on_a_terminal([str(bin_), "hunt"], folder, env)
    check(code == 2 and "\x1b[" in drawn and ESCAPE.sub("", drawn) == said,
          "on a terminal poisson-break hunt draws the same error: line, with colour")
    code, drawn = on_a_terminal([str(bin_), "hunt", "--plain"], folder, env)
    check(code == 2 and drawn == said,
          "on a terminal poisson-break hunt --plain draws it as text")
    check(not any(folder.iterdir()), "nothing was written into the folder the command ran in")
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


def fresh_env(work: Path) -> dict[str, str]:
    home = work / "home"
    (home / "tmp").mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items()
           if not any(w in k.upper() for w in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
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
