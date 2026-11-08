"""The command for the conformance corpus's verbs that change what is on disk (`tests/look_corpus.py`).

The conformance test runs one invocation many ways in one folder, and compares what each way printed. A verb that
writes (a hunt, a recheck, `init`) would find the folder changed by the way before it, and print something else. So
this program first puts the folder back as the invocation's setup left it, from the copy the setup kept in `pristine/`,
and then runs `poisson_break.cli.main` on its own command line, exactly as `python -m poisson_break` would.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def restore(folder: Path) -> None:
    kept = folder / "pristine"
    if not kept.is_dir():
        return
    for path in folder.iterdir():
        if path.name in ("pristine", "home"):
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    for path in kept.iterdir():
        if path.is_dir():
            shutil.copytree(path, folder / path.name)
        else:
            shutil.copy2(path, folder / path.name)


if __name__ == "__main__":
    restore(Path.cwd())
    from poisson_break.cli import main

    sys.exit(main(sys.argv[1:]))
