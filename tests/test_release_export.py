"""Each export recipe's sample output parses as a case file.

Invariant held here (Break — Plan, the release pass; spec §7.2):
- BK11.4  Each export recipe's sample output parses as a case file.

Spec §7.2: the docs give one recipe per tool (LangSmith, Langfuse, Phoenix) for exporting recent
inputs into a case file with the tool's own export, and CI checks each recipe's output format
against a stored sample; Break calls none of those services. Read here: for each tool, one page
under `docs/` whose title (its first `# ` line) names it; the page links to its stored sample, a
`.jsonl` file in the checkout; and every sample a recipe page links to is read by Break's own
reader of case files, `poisson_break.settings.read_cases`, the one `doctor` and `hunt` read
`[target] cases` with, with no refusal, each case's input text and not empty.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.conftest import REPO

TOOLS = ("LangSmith", "Langfuse", "Phoenix")
_LINK = re.compile(r"\]\(([^)\s]+)\)")


def title(page: Path) -> str:
    for line in page.read_text(encoding="utf-8").split("\n"):
        if line.startswith("# "):
            return line[2:]
    return ""


def recipe_pages(tool: str) -> list[Path]:
    docs = REPO / "docs"
    pages = sorted(docs.rglob("*.md")) if docs.exists() else []
    return [p for p in pages if re.search(rf"\b{tool}\b", title(p))]


def samples(page: Path) -> list[Path]:
    """The `.jsonl` files the page links to, read from the page's own folder."""
    found = []
    for target in _LINK.findall(page.read_text(encoding="utf-8")):
        target = target.split("#", 1)[0]
        if target.endswith(".jsonl") and "://" not in target:
            found.append((page.parent / target).resolve())
    return found


@pytest.mark.parametrize("tool", TOOLS)
def test_one_recipe_page_for_each_tool(tool: str) -> None:
    assert len(recipe_pages(tool)) == 1, [str(p.relative_to(REPO)) for p in recipe_pages(tool)]


@pytest.mark.parametrize("tool", TOOLS)
def test_each_recipe_links_a_stored_sample_in_the_checkout(tool: str) -> None:
    (page,) = recipe_pages(tool)
    linked = samples(page)
    assert linked, f"{page.relative_to(REPO)} links no .jsonl sample"
    for sample in linked:
        assert REPO in sample.parents, sample
        assert sample.is_file(), f"{page.relative_to(REPO)} links {sample}, which is not there"


@pytest.mark.parametrize("tool", TOOLS)
def test_each_recipe_sample_parses_as_a_case_file(tool: str) -> None:
    from poisson_break.settings import SettingsError, read_cases

    (page,) = recipe_pages(tool)
    for sample in samples(page):
        try:
            cases = read_cases(sample)
        except SettingsError as refused:
            pytest.fail(f"{sample.relative_to(REPO)} is refused as a case file: {refused}")
        assert cases
        for case in cases:
            assert isinstance(case["input"], str) and case["input"].strip(), case
