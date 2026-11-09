"""The catalogue's labels: a checked table, and `catalog --labels`, which shows a label only where
the table has one.

Invariant held here (Break — Plan, the release pass; spec §10's labels item):
- BK11.5  A label is shown only where the checked table has one; a change with no label shows
          none.

**The table** is `src/poisson_break/labels.toml`, in the package so the wheel carries it and
the command reads it where it is installed. It holds one array of tables, `label`, and nothing
else. Each row is one label on one change of the catalogue:

    [[label]]
    change = "tool:planted_instruction"   # a catalogue line, surface:name
    scheme = "..."                        # the published list the label comes from
    id = "..."                            # the label as that list writes it
    title = "..."                         # its name in that list
    source = "https://..."                # where the published text is
    text = "..."                          # the published text the label rests on, quoted

A change may have no row, one, or several; rows are shown in the table's order.

**`catalog --labels`** lists the catalogue as `catalog` does, one line a change, and on the line
of each change the table labels, each label's `id`; the line of a change with no label is the
line `catalog` prints for it, spaces aside. Under `--json`, each change carries `labels`: its
rows, in the table's order, each without `change`; `[]` for none. Plain `catalog` shows no label.

That each row was checked by a second reader against the published text is a reading by a
person, not something a test can do; it is owed, and its record is the vault's.
"""

from __future__ import annotations

import re
import shutil
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from tests.commands_support import CODES, cli, detail, json_document, project, result_of, verdict
from tests.conftest import GUARD, REPO

TABLE = REPO / "src" / "poisson_break" / "labels.toml"
ROW_KEYS = {"change", "scheme", "id", "title", "source", "text"}
ONE_LINE = ("change", "scheme", "id", "title", "source")


def catalogue() -> list[Any]:
    from poisson_break.changes import CATALOG

    return list(CATALOG)


def read_table(path: Path = TABLE) -> list[dict[str, Any]]:
    with path.open("rb") as f:
        table = tomllib.load(f)
    assert set(table) == {"label"}, sorted(table)
    rows = table["label"]
    assert isinstance(rows, list)
    return rows


def of(rows: Sequence[dict[str, Any]], change: Any) -> list[dict[str, Any]]:
    return [r for r in rows if r["change"] == f"{change.surface}:{change.name}"]


def lines_for(lines: list[str], change: Any) -> list[str]:
    """The lines that name this change, as one word `surface:name` or as two words."""
    pattern = re.compile(rf"(?<![\w:]){re.escape(change.surface)}(?::|\s+){re.escape(change.name)}(?![\w])")
    return [line for line in lines if pattern.search(line)]


def shows(line: str, label_id: str) -> bool:
    return re.search(rf"(?<![\w:-]){re.escape(label_id)}(?![\w-])", line) is not None


def squeezed(line: str) -> str:
    return " ".join(line.split())


# ---------------------------------------------------------------------------
# the table
# ---------------------------------------------------------------------------


def test_the_table_is_one_array_of_rows_with_at_least_one_label() -> None:
    rows = read_table()
    assert rows, "the table labels nothing"
    assert all(isinstance(r, dict) for r in rows)


def test_each_row_has_the_six_keys_each_text() -> None:
    for n, row in enumerate(read_table(), 1):
        assert set(row) == ROW_KEYS, (n, sorted(row))
        for key in ROW_KEYS:
            assert isinstance(row[key], str) and row[key].strip() == row[key] and row[key], (n, key)
        for key in ONE_LINE:
            assert "\n" not in row[key], (n, key)


def test_each_row_labels_a_change_of_the_catalogue() -> None:
    known = {f"{c.surface}:{c.name}" for c in catalogue()}
    assert [r["change"] for r in read_table() if r["change"] not in known] == []


def test_no_label_is_given_twice_to_one_change() -> None:
    seen = [(r["change"], r["scheme"], r["id"]) for r in read_table()]
    assert len(seen) == len(set(seen)), seen


def test_each_row_names_its_source_text() -> None:
    """Where the published text is, as an address that can be opened, and the words of it the
    label rests on: a sentence, not the label's own title or id again."""
    for n, row in enumerate(read_table(), 1):
        assert re.fullmatch(r"https://[A-Za-z0-9.-]+\.[A-Za-z]{2,}/\S*", row["source"]), (n, row["source"])
        words = re.findall(r"[A-Za-z]+", row["text"])
        assert len(words) >= 6, (n, row["text"])
        assert squeezed(row["text"]).lower() not in {squeezed(row["title"]).lower(),
                                                      squeezed(row["id"]).lower()}, n


# ---------------------------------------------------------------------------
# catalog --labels, on the table as it is
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def shown(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    proj = project(tmp_path_factory.mktemp("labels"))
    labelled = cli(proj, "catalog", "--labels")
    plain = cli(proj, "catalog")
    as_json = cli(proj, "catalog", "--labels", "--json")
    return {"proj": proj, "labelled": labelled, "plain": plain, "json": as_json}


def test_catalog_labels_says_ok_exits_0_and_spends_nothing(shown: dict[str, Any]) -> None:
    ran = shown["labelled"]
    assert ran.exit == CODES["done"], ran
    assert verdict(ran)[0] == "ok"
    assert shown["proj"].runs() == [] and not shown["proj"].hunts.exists()


def check_lines(labelled_lines: list[str], plain_lines: list[str], rows: list[dict[str, Any]]) -> None:
    every_id = {r["id"] for r in rows}
    for change in catalogue():
        (line,) = lines_for(labelled_lines, change) or [""]
        assert line, (change.surface, change.name, labelled_lines)
        labels = of(rows, change)
        if labels:
            for label in labels:
                assert shows(line, label["id"]), (line, label["id"])
            assert {i for i in every_id if shows(line, i)} == {r["id"] for r in labels}, line
        else:
            (before,) = lines_for(plain_lines, change)
            assert squeezed(line) == squeezed(before), (line, before)


def test_a_change_shows_its_labels_and_a_change_with_none_shows_none(shown: dict[str, Any]) -> None:
    labelled = detail(result_of(shown["labelled"], "ok"))
    plain = detail(result_of(shown["plain"], "ok"))
    assert len(labelled) == len(plain) == len(catalogue())
    check_lines(labelled, plain, read_table())


def test_plain_catalog_shows_no_label(shown: dict[str, Any]) -> None:
    out = shown["plain"].out
    assert [r["id"] for r in read_table() if shows(out, r["id"])] == []


def test_catalog_labels_json_carries_each_change_rows_in_the_table_order(shown: dict[str, Any]) -> None:
    doc = json_document(shown["json"])
    assert doc["schema"] == "poisson_break.catalog-result/1"
    rows = read_table()
    listed = doc["changes"]
    assert [(c["surface"], c["name"]) for c in listed] == [(c.surface, c.name) for c in catalogue()]
    for entry, change in zip(listed, catalogue(), strict=True):
        expected = [{k: v for k, v in r.items() if k != "change"} for r in of(rows, change)]
        assert entry["labels"] == expected, (change.surface, change.name)


# ---------------------------------------------------------------------------
# catalog --labels, on a table changed under it
# ---------------------------------------------------------------------------


def planted_package(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    """A copy of the package with `rows` as its table; returns the folder to put first on the
    import path."""
    root = tmp_path / "planted"
    shutil.copytree(REPO / "src" / "poisson_break", root / "poisson_break",
                    ignore=shutil.ignore_patterns("__pycache__"))
    out = []
    for row in rows:
        out.append("[[label]]")
        for key in ("change", "scheme", "id", "title", "source", "text"):
            value = row[key].replace("\\", "\\\\").replace('"', '\\"')
            out.append(f'{key} = "{value}"')
        out.append("")
    (root / "poisson_break" / "labels.toml").write_text("\n".join(out), encoding="utf-8")
    return root


def test_catalog_labels_shows_what_the_table_holds_when_the_table_changes(tmp_path: Path) -> None:
    """The labels are read from the table, not written into the command: with one labelled
    change's rows taken out and two rows added to a change that had none (or to the last change),
    the command shows the planted table, line by line and in `--json`, the two in the table's
    order."""
    rows = read_table()
    changes = catalogue()
    dropped = next(c for c in changes if of(rows, c))
    added = next((c for c in reversed(changes) if not of(rows, c)), changes[-1])
    planted = [r for r in rows if r["change"] != f"{dropped.surface}:{dropped.name}"]
    for n in (7, 8):
        planted.append({"change": f"{added.surface}:{added.name}", "scheme": "Planted list",
                        "id": f"PLANTED-{n}", "title": f"A planted label, number {n}",
                        "source": "https://example.org/planted",
                        "text": f"Sentence {n}, planted for this test, which no published list holds."})
    root = planted_package(tmp_path, planted)
    proj = project(tmp_path / "proj")
    path = f"{root}:{GUARD}:{REPO}"
    labelled = cli(proj, "catalog", "--labels", PYTHONPATH=path)
    plain = cli(proj, "catalog", PYTHONPATH=path)
    as_json = cli(proj, "catalog", "--labels", "--json", PYTHONPATH=path)
    assert labelled.exit == plain.exit == as_json.exit == CODES["done"], (labelled, plain, as_json)
    check_lines(detail(result_of(labelled, "ok")), detail(result_of(plain, "ok")), planted)
    doc = json_document(as_json)
    for entry, change in zip(doc["changes"], changes, strict=True):
        assert entry["labels"] == [{k: v for k, v in r.items() if k != "change"}
                                   for r in of(planted, change)], (change.surface, change.name)
    by_change = {(c["surface"], c["name"]): c["labels"] for c in doc["changes"]}
    assert by_change[(dropped.surface, dropped.name)] == []
    assert [label["id"] for label in by_change[(added.surface, added.name)]][-2:] == \
        ["PLANTED-7", "PLANTED-8"]
