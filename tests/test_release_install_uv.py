"""The uv install line, beside pip's, wherever a page a user reads says how Break installs.

Issue #21: Break pins a pre-release of Poisson Trace exactly (`poisson-trace==0.1.0a1`). pip takes
an exact pin on a pre-release as written; uv leaves pre-releases out unless told, so
`uv pip install poisson-break` does not install Break. Taylor's ruling (2026-11-16): the README
gives the uv line, `uv pip install --prerelease=allow poisson-break`, beside the pip line, until
the pin becomes a range.

Held here: the README's first screen is followed, before the first `##` heading, by that line
and a sentence saying why uv needs the flag; the README's Status and the reference's "What it
depends on", which say how pip installs the pre-release, give the same line. The line is in
prose, not in a marked block: the first screen's tests hold that nothing else runs between the
install and `confirm`, and the clean-install job runs every marked command.
"""

from __future__ import annotations

import re

from tests.conftest import REPO

UV_LINE = "`uv pip install --prerelease=allow poisson-break`"


def _section(text: str, heading: str) -> str:
    """The text of the `## heading` section, up to the next `## `."""
    found = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert found, f"no ## {heading}"
    return found.group(1)


def test_the_readme_gives_the_uv_line_after_the_first_screen_and_before_the_first_heading() -> None:
    text = (REPO / "README.md").read_text(encoding="utf-8")
    first_heading = text.index("\n## ")
    confirm = text.index("poisson-break confirm --yes\n```")
    after = text[confirm:first_heading]
    assert UV_LINE in after, "no uv line between the first screen and the first heading"
    paragraph = next(p for p in after.split("\n\n") if UV_LINE in p)
    assert "pre-release" in paragraph and "Poisson Trace" in paragraph, paragraph


def test_the_readme_status_gives_the_uv_line() -> None:
    status = _section((REPO / "README.md").read_text(encoding="utf-8"), "Status")
    assert "pre-release" in status and UV_LINE in status, status


def test_the_reference_gives_the_uv_line_where_it_says_how_pip_installs_trace() -> None:
    depends = _section((REPO / "docs" / "reference.md").read_text(encoding="utf-8"), "What it depends on")
    assert "pre-release" in depends and UV_LINE in depends, depends


def test_no_page_a_user_reads_shows_uv_installing_break_without_the_flag() -> None:
    pages = [REPO / "README.md", *sorted((REPO / "docs").rglob("*.md")),
             *sorted((REPO / "examples").rglob("*.md"))]
    bare = re.compile(r"uv (?:pip install|add)(?![^\n`]*--prerelease=allow)[^\n`]*poisson-break")
    found = [f"{p.relative_to(REPO)}:{m.group(0)}" for p in pages
             for m in bare.finditer(p.read_text(encoding="utf-8"))]
    assert found == [], found
