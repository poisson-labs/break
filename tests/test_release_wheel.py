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
"""

from __future__ import annotations

import email.parser
import re
import subprocess
import sys
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
