"""Each export recipe's conversion is run on a stored export and writes the stored sample.

Invariant held here (Break — Plan, the release pass; spec §7.2), as Taylor ruled it (2026-11-09,
`evidence/bk11/open-points.md`):
- 11A-12  each recipe page's Python, run on a stored sample of the tool's own export, writes the
          stored case-file sample: a recipe whose own code is wrong does not pass.
- 11A-13  a recipe's call to LangSmith, Langfuse or Phoenix is Python, not a shell command.
- 11A-23  the call to the service is a block tagged `python service`, shown and not run, since it
          needs a key; the conversion is the page's `python` blocks, which read
          `<tool>-export.<ext>` from the folder they run in and write `<tool>.jsonl`; run with the
          stored export (`docs/export/samples/<tool>-export.<ext>`) copied in, the file written
          equals the stored case-file sample byte for byte.

How a recipe page is read is `tests/release_docs.py`, rule 8; that the clean-install job's
listing carries each recipe's program is held with the listing, in
`tests/test_release_commands.py`. Here each conversion is run against this tree, in a fresh
folder holding the stored export and nothing else, under the network guard, with no key-like
variable and the probe logging any connection attempted.
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import REPO, guarded_env
from tests.release_docs import (
    RECIPE_TOOLS,
    SERVICE,
    blocks,
    marked,
    python_program,
    recipe_pages,
    rel,
    service_blocks,
)

PROBE = REPO / "tests" / "release_probe"
SAMPLES = REPO / "docs" / "export" / "samples"


def page_of(tool: str) -> Path:
    (page,) = recipe_pages()[tool]
    return page


def stored_export(tool: str) -> Path:
    """The one stored export of a tool: `docs/export/samples/<tool>-export.<ext>`."""
    found = sorted(SAMPLES.glob(f"{tool.lower()}-export.*")) if SAMPLES.exists() else []
    assert len(found) == 1, f"not one stored export for {tool}: {[p.name for p in found]}"
    return found[0]


def stored_sample(tool: str) -> Path:
    return SAMPLES / f"{tool.lower()}.jsonl"


def converted(tool: str, folder: Path, export: Path) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """The page's conversion run in `folder`, which holds a copy of `export` under the stored
    export's name and the program; and the connections it attempted."""
    program = python_program(page_of(tool))
    assert program is not None, f"{rel(page_of(tool))} has no python block"
    folder.mkdir(parents=True)
    shutil.copyfile(export, folder / stored_export(tool).name)
    (folder / "recipe.py").write_text(program.command + "\n", encoding="utf-8")
    network = folder.parent / f"{folder.name}-network.log"
    env = guarded_env()
    env["PYTHONPATH"] = str(PROBE)
    env["HOME"] = str(folder.parent)
    env["BREAK_TEST_NETWORK_LOG"] = str(network)
    done = subprocess.run([sys.executable, "recipe.py"], cwd=folder, env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=300)
    attempts = network.read_text(encoding="utf-8").splitlines() if network.exists() else []
    return done, attempts


@pytest.mark.parametrize("tool", RECIPE_TOOLS)
def test_the_page_shows_its_call_to_the_service_and_its_conversion_apart(tool: str) -> None:
    """A `python service` block for the call, shown and not run; `python` blocks for the conversion;
    no other Python on the page; and the service block is Python that parses, naming the tool's own
    package, which the conversion does not import."""
    page = page_of(tool)
    found = blocks(page.read_text(encoding="utf-8"), rel(page))
    service = service_blocks(page)
    assert service, f"{rel(page)} has no block tagged {SERVICE!r}"
    assert [b for b in found if b.language == "python" and b.info not in ("python", SERVICE)] == []
    program = python_program(page)
    assert program is not None
    for block in service:
        text = "\n".join(block.lines)
        ast.parse(text)
        assert text.strip() and text not in program.command
    package = {"LangSmith": "langsmith", "Langfuse": "langfuse", "Phoenix": "phoenix"}[tool]
    imported = set()
    for node in ast.walk(ast.parse(program.command)):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert package not in imported, f"the conversion imports {package}, which needs the service's package"
    called = "\n".join("\n".join(b.lines) for b in service)
    assert package in called, f"the service block does not name {package}"


@pytest.mark.parametrize("tool", RECIPE_TOOLS)
def test_the_stored_export_and_the_stored_sample_are_there(tool: str) -> None:
    export, sample = stored_export(tool), stored_sample(tool)
    assert export.is_file() and export.read_bytes().strip(), export
    assert sample.is_file() and sample.read_bytes().strip(), sample
    page = page_of(tool).read_text(encoding="utf-8")
    assert f"samples/{export.name}" in page, f"the page does not link its stored export, {export.name}"
    assert f"samples/{sample.name}" in page, f"the page does not link its stored sample, {sample.name}"


@pytest.mark.parametrize("tool", RECIPE_TOOLS)
def test_the_conversion_writes_the_stored_sample_byte_for_byte(tool: str, tmp_path: Path) -> None:
    folder = tmp_path / "recipe"
    done, attempts = converted(tool, folder, stored_export(tool))
    assert done.returncode == 0, done.stdout + done.stderr
    assert attempts == []
    out = folder / f"{tool.lower()}.jsonl"
    assert out.is_file(), sorted(p.name for p in folder.iterdir())
    assert out.read_bytes() == stored_sample(tool).read_bytes()
    assert sorted(p.name for p in folder.iterdir()) == sorted({stored_export(tool).name, "recipe.py", out.name})


@pytest.mark.parametrize("tool", RECIPE_TOOLS)
def test_the_conversion_reads_the_export_it_is_given(tool: str, tmp_path: Path) -> None:
    """The cases come from the export, not from the page: no input of the stored sample is written
    in the program, each is in the stored export, and an export with a record changed gives a file
    that differs from the stored sample."""
    program = python_program(page_of(tool))
    assert program is not None
    inputs = [json.loads(line)["input"] for line in stored_sample(tool).read_text(encoding="utf-8").splitlines()
              if line.strip()]
    assert len(inputs) >= 2
    export_text = stored_export(tool).read_text(encoding="utf-8")
    marker_text = inputs[0]
    for text in inputs:
        assert text not in program.command, f"the program holds the sample's input {text!r}"
        assert text in export_text or json.dumps(text)[1:-1] in export_text, \
            f"the stored export does not hold the sample's input {text!r}"
    assert export_text.count(marker_text) >= 1
    changed = tmp_path / "changed-export"
    changed.write_text(export_text.replace(marker_text, "Where is order 77?"), encoding="utf-8")
    done, _ = converted(tool, tmp_path / "changed", changed)
    assert done.returncode == 0, done.stdout + done.stderr
    written = (tmp_path / "changed" / f"{tool.lower()}.jsonl").read_text(encoding="utf-8")
    assert "Where is order 77?" in written and written != stored_sample(tool).read_text(encoding="utf-8")


def test_the_listing_s_rules_carry_each_recipe_s_program() -> None:
    """Rule 8: the marked commands hold each recipe page's conversion as one `python` program, at the
    first line of its first `python` block, and nothing of its `python service` blocks."""
    commands, refused = marked()
    assert refused == []
    for tool in RECIPE_TOOLS:
        page = page_of(tool)
        mine = [c for c in commands if c.file == rel(page) and c.kind == "python"]
        assert len(mine) == 1, (tool, mine)
        first = next(b for b in blocks(page.read_text(encoding="utf-8"), rel(page)) if b.info == "python")
        assert mine[0].line == first.first_line
        for block in service_blocks(page):
            assert "\n".join(block.lines) not in mine[0].command
