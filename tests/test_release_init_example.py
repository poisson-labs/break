"""`init --example NAME`: the examples ride in the wheel, and `init` writes one into the folder.

Taylor's ruling 11A-2 (2026-11-09, `evidence/bk11/open-points.md`): the examples ride in the wheel
as package data under `poisson_break/examples/<name>/`, the same files as the repository's
`examples/<name>/`, put there by the build config; `init --example NAME` writes that example's
agent, cases and `break.toml` into the folder, refusing to write over a file without `--force`,
as `init` does. Its tests, as the ruling lists them: the wheel carries each example's files;
`init --example` writes exactly them, refuses an unknown name and an existing file without
`--force`, and is in the look's conformance and `init --help`. (The README's first screen using
it is held in `test_release_readme.py`; each example's run in `test_release_examples.py`.)

An example's name is its folder's name under `examples/`; its files are every file in that
folder but bytecode.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests import look_conformance as conformance
from tests.commands_corpus import writing
from tests.commands_support import CODES
from tests.conftest import REPO, Ran, guarded_env
from tests.look_corpus import Invocation

EXAMPLES = REPO / "examples"


def names() -> list[str]:
    if not EXAMPLES.exists():
        return []
    return sorted(p.name for p in EXAMPLES.iterdir() if p.is_dir() and (p / "break.toml").is_file())


def files_of(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def init(folder: Path, *words: str) -> Ran:
    """The command's `init` in `folder`, as `python -m poisson_break` runs it, under the guard."""
    env = guarded_env()
    env["HOME"] = str(folder.parent / "home")
    (folder.parent / "home").mkdir(exist_ok=True)
    done = subprocess.run([sys.executable, "-m", "poisson_break", "--plain", "init", *words],
                          cwd=folder, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, timeout=120)
    return Ran(done.returncode, done.stdout, done.stderr)


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    here = tmp_path / "project"
    here.mkdir()
    return here


# ---------------------------------------------------------------------------
# the wheel
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def shipped(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    out = tmp_path_factory.mktemp("wheel")
    done = subprocess.run([sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(out)],
                          cwd=REPO, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stdout + done.stderr
    (built,) = out.glob("*.whl")
    with zipfile.ZipFile(built) as z:
        return {n: z.read(n) for n in z.namelist() if n.startswith("poisson_break/examples/")}


def test_there_are_examples() -> None:
    assert names(), "no example under examples/"


def test_the_wheel_carries_each_example_s_files_and_no_others(shipped: dict[str, bytes]) -> None:
    expected = {f"poisson_break/examples/{name}/{rel}": data
                for name in names() for rel, data in files_of(EXAMPLES / name).items()}
    assert expected
    assert sorted(set(expected) - set(shipped)) == [], "files the wheel lacks"
    assert sorted(n for n in set(shipped) - set(expected) if "__pycache__" not in n) == [], \
        "files the wheel has that no example holds"
    assert [n for n in expected if shipped[n] != expected[n]] == [], "files that differ"


# ---------------------------------------------------------------------------
# what init --example writes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", names() or ["(no example)"])
def test_init_example_writes_exactly_the_example_s_files(name: str, folder: Path) -> None:
    assert name in names()
    ran = init(folder, "--example", name)
    assert ran.exit == CODES["done"], ran
    assert ran.stdout.startswith("wrote  "), ran
    written = {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*"))
               if p.is_file()}
    assert written == files_of(EXAMPLES / name), "the folder holds other files, or other bytes"


def test_an_unknown_example_is_refused_and_nothing_is_written(folder: Path) -> None:
    ran = init(folder, "--example", "no-such-example")
    assert ran.exit == CODES["refused"], ran
    assert sum(line.startswith("error: ") for line in ran.stderr.splitlines()) == 1, ran
    assert list(folder.iterdir()) == []


@pytest.mark.parametrize("taken", ["break.toml", "the first file"])
def test_init_example_will_not_write_over_a_file_without_force(taken: str, folder: Path) -> None:
    name = names()[0]
    rel = "break.toml" if taken == "break.toml" else sorted(files_of(EXAMPLES / name))[0]
    (folder / rel).parent.mkdir(parents=True, exist_ok=True)
    (folder / rel).write_bytes(b"written by the user\n")
    ran = init(folder, "--example", name)
    assert ran.exit == CODES["refused"], ran
    assert files_of(folder) == {rel: b"written by the user\n"}, "something was written"


def test_init_example_with_force_writes_over_and_leaves_other_files(folder: Path) -> None:
    name = names()[0]
    (folder / "break.toml").write_bytes(b"written by the user\n")
    (folder / "notes.txt").write_bytes(b"mine\n")
    ran = init(folder, "--example", name, "--force")
    assert ran.exit == CODES["done"], ran
    assert files_of(folder) == {**files_of(EXAMPLES / name), "notes.txt": b"mine\n"}


def test_init_help_names_example(folder: Path) -> None:
    ran = init(folder, "--help")
    assert ran.exit == CODES["done"], ran
    assert "--example" in ran.stdout


# ---------------------------------------------------------------------------
# the look's conformance
# ---------------------------------------------------------------------------


def _empty(folder: Path) -> None:
    (folder / "pristine").mkdir()


def _over_a_file(folder: Path) -> None:
    (folder / "break.toml").write_text("version = 1\n", encoding="utf-8")


def _corpus() -> list[Invocation]:
    name = names()[0] if names() else "desk"
    return [
        Invocation("init-example", ("init", "--example", name), program=writing(), has_json=True,
                   setup=_empty),
        Invocation("init-example-unknown", ("init", "--example", "no-such-example"), kind="bad",
                   code=1),
        Invocation("init-example-over-a-file", ("init", "--example", name), kind="bad", code=1,
                   setup=_over_a_file),
    ]


def _applies(check: str, inv: Invocation) -> bool:
    if check == "help":
        return inv.kind in ("help", "version")
    if check == "json":
        return inv.has_json
    if check == "verdict-first":
        return inv.kind == "result"
    return True


PAIRS = [(check, inv) for check in conformance.CHECKS for inv in _corpus() if _applies(check, inv)]


@pytest.fixture(scope="module", autouse=True)
def _kept_runs() -> Iterator[None]:
    yield
    conformance.forget()


@pytest.mark.parametrize("check, inv", PAIRS, ids=[f"{c}-{i.name}" for c, i in PAIRS])
def test_init_example_conforms_to_the_look(check: str, inv: Invocation) -> None:
    assert names(), "no example under examples/"
    piped = conformance.run_way(inv, "piped")
    assert piped.exit == inv.code and "Traceback" not in piped.err, f"it does not run as it should:\n{piped}"
    wrong = conformance.CHECKS[check](inv)
    assert not wrong, "\n".join(wrong)
