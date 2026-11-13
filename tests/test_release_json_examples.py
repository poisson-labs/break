"""The `--json` documents the README and the docs show hold the ruled fields, so no example goes
stale.

Taylor's ruling 11A-18 (2026-11-09, `evidence/bk11/open-points.md`): every `json` block whose
`schema` is `poisson_break.*` holds exactly the keys `evidence/bk8f/field-tables.md` gives its
document, as ruled 2026-11-08 (F1 to F14; F6 taken back). Read here:

- Every block tagged `json` in the README or a page under `docs/` or `examples/` parses: as one
  JSON document, or as JSON Lines, a document a line (a case file). A block that cannot be read
  cannot be checked, so a shortened example (`...`) is refused.
- A document whose `schema` starts `poisson_break.` names one of the ruled documents; its first
  keys are `schema`, `verdict`, `sentence` (a plan's then `estimate`, `source`); `next`, when it is
  there, is last; every other key is one the table gives that document, under one verdict or
  another; and every item of the lists the tables spell out holds exactly the table's fields.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import REPO
from tests.release_docs import blocks

STOP = {"reason", "arm", "kept", "unclassed"}

#: Each ruled document: the keys it may hold beside the first ones and `next`.
DOCUMENTS: dict[str, set[str]] = {
    "poisson_break.init-result/1": {"file", "kind", "entry", "cases_file", "tools", "install"},
    "poisson_break.doctor-result/1": {"settings", "target", "kind", "tools", "cases", "run", "key",
                                      "line", "unclassed"},
    "poisson_break.hunt-plan/1": {"dollars", "target", "kind", "cases", "runs", "control_runs",
                                  "search_runs", "hunt"},
    "poisson_break.confirm-plan/1": {"dollars", "hunt", "candidates", "stage", "repeats", "runs",
                                     "asked_again"},
    "poisson_break.recheck-plan/1": {"dollars", "hunt", "findings", "runs", "old", "recheck"},
    "poisson_break.hunt-result/1": {"hunt", "runs", "dollars", "control", "search", "candidates",
                                    "not_looked_at", "wrote"} | STOP,
    "poisson_break.confirm-result/1": {"hunt", "stage", "candidates", "findings", "wrote",
                                       "reference_runs"} | STOP,
    "poisson_break.findings-result/1": {"hunt", "findings", "control", "finding"},
    "poisson_break.replay-result/1": {"hunt", "finding", "case", "seed", "outcome", "kind", "error",
                                      "calls"},
    "poisson_break.recheck-result/1": {"hunt", "findings", "old", "check", "strict", "passed"} | STOP,
    "poisson_break.catalog-result/1": {"changes"},
}
PLANS = {name for name in DOCUMENTS if name.endswith("-plan/1")}

#: The items of the lists the tables spell out, field for field, by document and key.
ITEMS: dict[tuple[str, str], tuple[set[str], ...]] = {
    ("poisson_break.hunt-result/1", "candidates"): ({"number", "condition", "failed", "runs", "kind"},),
    ("poisson_break.confirm-result/1", "candidates"): (
        {"number", "condition", "verdict", "note", "rate", "control_rate", "difference", "lo", "hi",
         "p", "adjusted_p", "repeats_needed", "no_outcome", "left_out"},),
    ("poisson_break.findings-result/1", "findings"): ({"number", "condition", "rate", "difference"},),
    ("poisson_break.findings-result/1", "control"): ({"case", "failed", "runs", "kinds", "set_aside"},),
    ("poisson_break.replay-result/1", "calls"): ({"tool", "call", "change", "real_ran"},),
    ("poisson_break.recheck-result/1", "findings"): (
        {"number", "condition", "phrase", "rate_before", "rate_now", "difference", "lo", "hi", "p",
         "adjusted_p", "repeats_needed", "gap_days", "before", "now", "trace", "no_outcome",
         "left_out"},),
    ("poisson_break.catalog-result/1", "changes"): (
        {"surface", "name", "description", "needs_adapter"},
        {"surface", "name", "description", "needs_adapter", "labels"}),
}
#: The objects the tables spell out, field for field.
OBJECTS: dict[tuple[str, str], set[str]] = {
    ("poisson_break.hunt-result/1", "control"): {"runs", "failed", "rate", "set_aside"},
    ("poisson_break.hunt-result/1", "search"): {"runs", "conditions"},
}


def pages() -> list[Path]:
    found = [REPO / "README.md"]
    for top in ("docs", "examples"):
        if (REPO / top).exists():
            found += sorted((REPO / top).rglob("*.md"))
    return found


def json_blocks() -> list[tuple[str, int, list[Any]]]:
    """Each `json` block: where it is, and what it holds, a list of documents (one, or one a
    line); a block that cannot be read holds `None`."""
    found = []
    for page in pages():
        rel = page.relative_to(REPO).as_posix()
        for block in blocks(page.read_text(encoding="utf-8"), rel):
            if block.language != "json":
                continue
            text = "\n".join(block.lines)
            try:
                held = [json.loads(text)]
            except ValueError:
                try:
                    held = [json.loads(line) for line in block.lines if line.strip()]
                except ValueError:
                    held = [None]
            found.append((rel, block.fence_line, held))
    return found


def ours() -> list[tuple[str, int, dict[str, Any]]]:
    return [(rel, line, d) for rel, line, held in json_blocks() for d in held
            if isinstance(d, dict) and str(d.get("schema", "")).startswith("poisson_break.")]


def test_every_json_block_can_be_read() -> None:
    assert [f"{rel}:{line}" for rel, line, held in json_blocks() if None in held] == []


def test_the_docs_show_documents_to_check() -> None:
    """The docs show what `--json` writes (reading a finding, checking a fix); with no document
    shown, the test below holds nothing."""
    assert ours()


def problems(document: dict[str, Any]) -> list[str]:
    schema = document["schema"]
    if schema not in DOCUMENTS:
        return [f"{schema} is no document the tables give"]
    keys = list(document)
    wrong = []
    first = ["schema", "verdict", "sentence"] + (["estimate", "source"] if schema in PLANS else [])
    if keys[:len(first)] != first:
        wrong.append(f"first keys {keys[:len(first)]}")
    if "next" in keys and keys[-1] != "next":
        wrong.append("next is not last")
    extra = set(keys) - set(first) - {"next"} - DOCUMENTS[schema]
    if extra:
        wrong.append(f"keys the table does not give: {sorted(extra)}")
    for (name, key), shapes in ITEMS.items():
        if name == schema and isinstance(document.get(key), list):
            for item in document[key]:
                if not isinstance(item, dict) or set(item) not in shapes:
                    wrong.append(f"{key} item {sorted(item) if isinstance(item, dict) else item}")
    for (name, key), shape in OBJECTS.items():
        if name == schema and isinstance(document.get(key), dict) and set(document[key]) != shape:
            wrong.append(f"{key} {sorted(document[key])}")
    return wrong


def test_every_document_shown_holds_the_ruled_fields() -> None:
    found = {f"{rel}:{line}": problems(d) for rel, line, d in ours() if problems(d)}
    assert found == {}


STALE = [
    ("init's cases, before F1", {"schema": "poisson_break.init-result/1", "verdict": "wrote",
                                  "sentence": "s", "file": "break.toml", "cases": "cases.jsonl"}),
    ("a plan's left, before F2", {"schema": "poisson_break.hunt-plan/1", "verdict": "plan",
                                   "sentence": "s", "estimate": "e", "source": "s", "left": 3}),
    ("the one plan schema, before F10", {"schema": "poisson_break.plan/1", "verdict": "plan",
                                          "sentence": "s", "estimate": "e", "source": "s"}),
    ("a tested candidate without no_outcome, before F5",
     {"schema": "poisson_break.confirm-result/1", "verdict": "confirmed", "sentence": "s",
      "candidates": [{"number": 1, "condition": "c", "verdict": "v", "note": None, "rate": 1.0,
                      "control_rate": 0.0, "difference": 1.0, "lo": 0.5, "hi": 1.0, "p": 0.01,
                      "adjusted_p": 0.01, "repeats_needed": None}]}),
    ("next before the fields", {"schema": "poisson_break.catalog-result/1", "verdict": "ok",
                                "sentence": "s", "next": [], "changes": []}),
    ("a plan without its estimate first", {"schema": "poisson_break.confirm-plan/1", "verdict": "plan",
                                           "sentence": "s", "hunt": "h", "estimate": "e", "source": "s"}),
]


@pytest.mark.parametrize("what, document", STALE, ids=[w for w, _ in STALE])
def test_a_stale_document_is_found(what: str, document: dict[str, Any]) -> None:
    """The check is a real one: a document written to the fields as they were before the ruling
    is caught."""
    assert problems(document), what
