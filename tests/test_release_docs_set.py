"""The docs set by name, and links that work where they are read.

Taylor's rulings (2026-11-09, `evidence/bk11/open-points.md`):
- 11A-10: the docs set's pages are `docs/catalog.md`, `docs/findings.md` (reading a finding),
  `docs/recheck.md` (checking a fix), `docs/ways-in/rollout.md` (the way in that exists),
  `docs/export/langsmith.md`, `langfuse.md`, `phoenix.md`, `docs/claims.md` (what Break does not
  claim), `docs/extending/fault.md`, `way-in.md`, `strategy.md`, `check.md`; each exists and the
  README links each.
- 11A-11: every link in the README is absolute (`https://...`), since PyPI shows the README and a
  relative link is broken there; a link into the repository names a path that is there; every
  relative link in a page under `docs/` or `examples/` leads to a file or folder that is there.
- 11A-7b: the lab's two shared standards are left out of the docs set's index, the README, so a
  reader of Break's docs does not land on them.

And the pages the other release tests find by what they hold are these pages: each interface's
page (the one naming only its version constant) is its `docs/extending/` page, and each recipe
page (the one whose title names the tool) is its `docs/export/` page.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.conftest import REPO
from tests.release_docs import blocks, extension_pages

PAGES = (
    "docs/catalog.md", "docs/findings.md", "docs/recheck.md", "docs/ways-in/rollout.md",
    "docs/export/langsmith.md", "docs/export/langfuse.md", "docs/export/phoenix.md",
    "docs/claims.md", "docs/extending/fault.md", "docs/extending/way-in.md",
    "docs/extending/strategy.md", "docs/extending/check.md",
)
STANDARDS = ("docs/repo-hygiene.md", "docs/cli-look.md")
REPOSITORY = "https://github.com/poisson-labs/break/"
INTERFACE_PAGES = {
    "FAULT_INTERFACE_VERSION": "docs/extending/fault.md",
    "TARGET_INTERFACE_VERSION": "docs/extending/way-in.md",
    "STRATEGY_INTERFACE_VERSION": "docs/extending/strategy.md",
    "CHECK_INTERFACE_VERSION": "docs/extending/check.md",
}
RECIPE_PAGES = {"LangSmith": "docs/export/langsmith.md", "Langfuse": "docs/export/langfuse.md",
                "Phoenix": "docs/export/phoenix.md"}

_INLINE = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
_REFERENCE = re.compile(r"^ {0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s+.*)?$", re.MULTILINE)
_AUTOLINK = re.compile(r"<((?:https?|ftp|mailto):[^>\s]+)>")
_HTML = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)


def links(path: Path) -> list[str]:
    """Every link and image target in a page, its code blocks and code spans left out."""
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    for block in blocks(text, path.name):
        for n in range(block.fence_line - 1, block.fence_line + len(block.lines) + 1):
            if n < len(lines):
                lines[n] = ""
    prose = re.sub(r"`[^`\n]*`", "", "\n".join(lines))
    found: list[str] = []
    for pattern in (_INLINE, _REFERENCE, _AUTOLINK, _HTML):
        found += pattern.findall(prose)
    return found


def test_the_readme_has_links_to_read() -> None:
    """The tests below read the README's links; with none they would hold nothing."""
    assert links(REPO / "README.md")


@pytest.mark.parametrize("page", PAGES)
def test_each_page_of_the_docs_set_exists(page: str) -> None:
    assert (REPO / page).is_file(), page


@pytest.mark.parametrize("page", PAGES)
def test_the_readme_links_each_page(page: str) -> None:
    targets = {t.split("#", 1)[0] for t in links(REPO / "README.md")}
    assert f"{REPOSITORY}blob/main/{page}" in targets, page


def test_every_link_in_the_readme_is_absolute() -> None:
    assert [t for t in links(REPO / "README.md") if not t.startswith("https://")] == []


def test_every_readme_link_into_the_repository_names_a_path_that_is_there() -> None:
    wrong = []
    for target in links(REPO / "README.md"):
        target = target.split("#", 1)[0]
        for kind in ("blob/main/", "tree/main/"):
            if target.startswith(REPOSITORY + kind):
                path = REPO / target[len(REPOSITORY + kind):]
                if not (path.is_file() if kind == "blob/main/" else path.is_dir()):
                    wrong.append(target)
    assert wrong == []


def test_the_readme_does_not_link_the_lab_s_standards() -> None:
    assert [t for t in links(REPO / "README.md") if any(s in t for s in STANDARDS)] == []


def _pages() -> list[Path]:
    found = []
    for top in ("docs", "examples"):
        if (REPO / top).exists():
            found += sorted((REPO / top).rglob("*.md"))
    return found


def test_every_relative_link_in_a_page_leads_to_something_there() -> None:
    wrong = []
    for page in _pages():
        for target in links(page):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE) or target.startswith("#"):
                continue
            path = (page.parent / target.split("#", 1)[0]).resolve()
            if REPO not in path.parents or not path.exists():
                wrong.append(f"{page.relative_to(REPO)}: {target}")
    assert wrong == []


def test_each_interface_page_is_its_extending_page() -> None:
    found = {constant: [p.relative_to(REPO).as_posix() for p in pages]
             for constant, pages in extension_pages().items()}
    assert found == {constant: [page] for constant, page in INTERFACE_PAGES.items()}


def test_each_recipe_page_is_its_export_page() -> None:
    from tests.test_release_export import recipe_pages

    found = {tool: [p.relative_to(REPO).as_posix() for p in recipe_pages(tool)] for tool in RECIPE_PAGES}
    assert found == {tool: [page] for tool, page in RECIPE_PAGES.items()}
