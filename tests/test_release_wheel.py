"""What the release's wheel must be before it is uploaded, read offline from the wheel built from
this tree.

From Break — Plan, the release pass ("Builds": a TestPyPI rehearsal) and §1 (the exact pins).
The rehearsal itself and the release smoke are the build session's; what can be held without an
index is held here, beside what the package's own tests already hold (every file under the
package shipped, the licence files, the console script, the wheel's name and version: BK0.4 in
`tests/test_package.py`; the exact pins and Prove's agreeing with Trace's: BK0.7 in
`tests/test_dependencies.py`).

- **Every requirement is one an index can serve.** PyPI and TestPyPI refuse an upload whose
  metadata carries a direct reference (`name @ url`), so a wheel that still takes Trace, or
  anything, from a repository cannot be the release, on any extra.
- **The wheel installs one package.** Nothing outside `poisson_break/` and its `.dist-info`
  folder: an `examples/` or `tests/` folder at the top of the wheel would land in every user's
  site-packages as a package of that name.

Taylor's rulings (2026-11-09, `evidence/bk11/open-points.md`):
- 11A-15: the build ends with `__version__ = "0.1.0"` and a dated 0.1.0 section in the changelog;
  the rehearsal uploads that wheel and the release the same bytes (the upload is the build's).
  Held: the version, in the package and the wheel; the changelog's first section is `0.1.0` with
  its date, and no `Unreleased` section stands above it.
- 11A-16: the classifier `Development Status :: 3 - Alpha`, and no other development status.
- 11A-17: a wheel and an sdist; the sdist carries only files git tracks, and only under `src/`,
  `tests/`, `docs/`, `examples/`, `scripts/`, with the README, LICENSE, NOTICE, CHANGELOG and
  `pyproject.toml` (and the `PKG-INFO` an sdist writes for itself).
- 11A-26: `.gitignore` is allowed in the sdist too. Hatchling puts the repository's ignore file
  in every sdist, whatever the build settings say; it is tracked, and holds no private text.
"""

from __future__ import annotations

import datetime
import email.parser
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from tests.conftest import REPO


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("wheel")
    done = subprocess.run([sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(out)],
                          cwd=REPO, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stdout + done.stderr
    (built,) = out.glob("*.whl")
    return built


def metadata(wheel: Path) -> email.message.Message:
    with zipfile.ZipFile(wheel) as z:
        name = next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))
        return email.parser.Parser().parsestr(z.read(name).decode("utf-8"))


def test_every_requirement_is_one_an_index_can_serve(wheel: Path) -> None:
    """No `Requires-Dist` is a direct reference, on the ordinary dependencies or any extra. Red
    while Trace is pinned at a commit of its repository, as BK0's exact-pin test is; green the day
    the pin names a version on PyPI."""
    requires = metadata(wheel).get_all("Requires-Dist") or []
    assert requires, "the wheel declares no requirement"
    direct = [r for r in requires if re.search(r"\s@\s|@\s*(?:git\+|https?:|file:)", r)]
    assert direct == []


def test_the_wheel_installs_one_package_and_its_metadata(wheel: Path) -> None:
    import poisson_break

    with zipfile.ZipFile(wheel) as z:
        tops = {name.split("/", 1)[0] for name in z.namelist()}
    assert tops == {"poisson_break", f"poisson_break-{poisson_break.__version__}.dist-info"}, sorted(tops)


# ---------------------------------------------------------------------------
# 11A-15, 11A-16: the version and the classifier
# ---------------------------------------------------------------------------


def test_the_release_is_version_0_1_0_in_the_package_and_the_wheel(wheel: Path) -> None:
    import poisson_break

    assert poisson_break.__version__ == "0.1.0"
    assert metadata(wheel)["Version"] == "0.1.0"


def test_the_changelog_opens_with_the_dated_0_1_0_section() -> None:
    lines = (REPO / "CHANGELOG.md").read_text(encoding="utf-8").split("\n")
    sections = [line for line in lines if line.startswith("## ")]
    assert sections, "the changelog has no section"
    first = re.fullmatch(r"## 0\.1\.0\b\D*(\d{4}-\d{2}-\d{2})\D*", sections[0])
    assert first, sections[0]
    datetime.date.fromisoformat(first.group(1))
    assert not any("unreleased" in line.lower() for line in sections), sections


def test_the_development_status_is_alpha(wheel: Path) -> None:
    statuses = [c for c in metadata(wheel).get_all("Classifier") or []
                if c.startswith("Development Status ::")]
    assert statuses == ["Development Status :: 3 - Alpha"]


# ---------------------------------------------------------------------------
# 11A-17: the sdist
# ---------------------------------------------------------------------------

SDIST_TOPS = {"src", "tests", "docs", "examples", "scripts"}
SDIST_FILES = {"README.md", "LICENSE", "NOTICE", "CHANGELOG.md", "pyproject.toml", "PKG-INFO", ".gitignore"}


@pytest.fixture(scope="module")
def sdist(tmp_path_factory: pytest.TempPathFactory) -> list[str]:
    """The paths the sdist built from this tree carries, from its own top folder."""
    out = tmp_path_factory.mktemp("sdist")
    done = subprocess.run([sys.executable, "-m", "hatchling", "build", "-t", "sdist", "-d", str(out)],
                          cwd=REPO, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stdout + done.stderr
    (built,) = out.glob("*.tar.gz")
    with tarfile.open(built) as tar:
        names = [m.name for m in tar.getmembers() if m.isfile()]
    top = names[0].split("/", 1)[0]
    assert all(n.startswith(top + "/") for n in names)
    return sorted(n.split("/", 1)[1] for n in names)


def test_the_sdist_carries_only_the_named_folders_and_files(sdist: list[str]) -> None:
    assert sdist
    outside = [n for n in sdist if n.split("/", 1)[0] not in SDIST_TOPS and n not in SDIST_FILES]
    assert outside == []


def test_the_sdist_carries_only_files_git_tracks(sdist: list[str]) -> None:
    tracked = set(subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True,
                                 check=True).stdout.splitlines())
    assert [n for n in sdist if n != "PKG-INFO" and n not in tracked] == []
