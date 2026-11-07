"""`catalog`: every change Break knows, one line each.

Invariants held here (Break — Plan, the commands module and BK1.6; spec §9.1, §3):
- §9.1    `catalog` lists every change Break knows, with one line each; verdict `ok`; spends nothing.
- BK1.6   The conversation moves and the model faults are names the core does not apply: `catalog` says so on their
          lines, and on no other.
- BK8.2   `--json` is one strict document.

What is pinned is the catalogue's own data, read through `poisson_break.changes.CATALOG`: each line's surface and name,
and its description. How a line is laid out is not.

Taylor's rulings on BK8's open points (2026-11-07), held here: `catalog` needs no `break.toml`, and lists in the
catalogue's order (point 25); the schema `poisson_break.catalog-result/1` (point 11).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from tests.commands_support import CODES, cli, detail, json_document, project, result_of, verdict


def entries() -> list[Any]:
    from poisson_break.changes import CATALOG

    return list(CATALOG)


@pytest.fixture(scope="module")
def listed(tmp_path_factory: pytest.TempPathFactory) -> tuple[Any, list[str]]:
    proj = project(tmp_path_factory.mktemp("catalog"))
    ran = cli(proj, "catalog")
    return ran, detail(result_of(ran, "ok"))


def lines_for(lines: list[str], entry: Any) -> list[str]:
    """The lines that name this change: its surface and its name, as one word or as two beside each other."""
    pattern = re.compile(rf"(?<![\w:]){re.escape(entry.surface)}(?::|\s+){re.escape(entry.name)}(?![\w])")
    return [line for line in lines if pattern.search(line)]


def test_catalog_says_ok_exits_0_and_spends_nothing(tmp_path: Path) -> None:
    proj = project(tmp_path)
    ran = cli(proj, "catalog")
    assert ran.exit == CODES["done"], ran
    assert verdict(ran)[0] == "ok"
    assert proj.runs() == [] and not proj.hunts.exists()


def test_every_change_has_exactly_one_line(listed: tuple[Any, list[str]]) -> None:
    ran, lines = listed
    assert len(entries()) == 24
    for entry in entries():
        assert len(lines_for(lines, entry)) == 1, (entry.surface, entry.name, lines)


def test_each_line_carries_its_change_s_description(listed: tuple[Any, list[str]]) -> None:
    ran, lines = listed
    for entry in entries():
        (line,) = lines_for(lines, entry)
        assert " ".join(entry.description.split()) in " ".join(line.split()), (entry.name, line)


def test_the_lines_of_changes_that_need_an_adapter_say_so_and_no_others_do(listed: tuple[Any, list[str]]) -> None:
    """BK1.6: a word or mark every `needs_adapter` line carries and no other line does, outside the change's own name
    and description."""
    ran, lines = listed

    def rest(entry: Any) -> set[str]:
        (line,) = lines_for(lines, entry)
        line = line.replace(" ".join(entry.description.split()), " ")
        line = " ".join(line.split()).replace(" ".join(entry.description.split()), " ")
        line = re.sub(rf"{re.escape(entry.surface)}(?::|\s+){re.escape(entry.name)}", " ", line)
        return set(re.findall(r"[^\s()\[\],;:·–-]+", line))

    needing = [e for e in entries() if e.needs_adapter]
    others = [e for e in entries() if not e.needs_adapter]
    assert {e.surface for e in needing} == {"user", "model"} and len(needing) == 9
    shared = set.intersection(*(rest(e) for e in needing))
    marks = shared - set.union(*(rest(e) for e in others))
    assert marks, "no word on every line of a change that needs an adapter that is on no other line"


def test_catalog_under_json_is_one_strict_document(tmp_path: Path) -> None:
    ran = cli(project(tmp_path), "catalog", "--json")
    assert ran.exit == CODES["done"], ran
    document = json_document(ran)
    assert list(document)[:3] == ["schema", "verdict", "sentence"]
    assert document["verdict"] == "ok"
    assert document["schema"] == "poisson_break.catalog-result/1"


def test_catalog_needs_no_settings_file(tmp_path: Path) -> None:
    proj = project(tmp_path, write=False)
    ran = cli(proj, "catalog")
    assert ran.exit == CODES["done"], ran
    assert verdict(ran)[0] == "ok"
    assert len(detail(result_of(ran, "ok"))) >= len(entries())


def test_catalog_lists_in_the_catalogue_s_order(listed: tuple[Any, list[str]]) -> None:
    ran, lines = listed
    at = []
    for entry in entries():
        found = lines_for(lines, entry)
        assert len(found) == 1, (entry, lines)
        at.append(lines.index(found[0]))
    assert at == sorted(at), at

