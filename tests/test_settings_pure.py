"""What reading settings does not do, and what a settings file for a way in not yet installed does.

Invariants pinned here (Break — Plan, the settings module):
- BK4.6 Pure: reading, checking or dumping settings imports no framework and does not import the target or the
        strategy. How this module asks about what a way in can do is brought as a ruling, so no test here reads it.
- BK4.7 A `kind` the core does not ship (`openai-agents`, `langgraph`, `crewai`, `mcp`, `command`) is accepted by the
        schema and refused at load with one line naming the extra to install, so a settings file written for an
        on-demand module parses today.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import run_python
from tests.settings_support import ON_DEMAND_KINDS, SAMPLE, SHIPPED_KIND, assert_one_line, doc, line_of, settings

FRAMEWORKS = ("openai", "agents", "langchain", "langchain_core", "langgraph", "crewai", "mcp", "anthropic")

# Each of these writes a file when imported, so that an import shows even if the module then cleans up after itself.
USER_MODULES = ("planted_target", "planted_strategy", "planted_check", "planted_stand_in")

PROBE = r'''
import json, sys
before = set(sys.modules)
from pathlib import Path
from poisson_break import settings as s

out = {"read": None}
folder = Path(".")
read = s.load(folder / "break.toml")
out["read"] = s.dump(read)
s.loads(out["read"])
out["cases"] = len(list(s.read_cases(folder / "cases.jsonl")))
out["bad"] = []
for text in (Path("bad.toml").read_text(encoding="utf-8"), "not toml ["):
    try:
        s.loads(text)
    except s.SettingsError as wrong:
        out["bad"].append(wrong.key)
out["loaded"] = sorted(set(sys.modules) - before)
print(json.dumps(out))
'''

TEXT = doc(
    tools='lookup_order = "read"\nissue_refund = { class = "write", stand_in = "planted_stand_in:refund" }',
    fails='own = "planted_check:refund_ok"',
    search='strategy = "planted_strategy:Mine"',
    output='folder = "made-if-anything-makes-it"',
).replace("my_app.agents:refund_agent", "planted_target:agent")


def plant(folder: Path) -> None:
    for name in USER_MODULES:
        (folder / f"{name}.py").write_text(f"from pathlib import Path\nPath({name + '.imported'!r}).write_text('yes')\n")
    # What a framework would be, if something looked for one by importing it.
    for name in FRAMEWORKS:
        (folder / f"{name}.py").write_text(f"from pathlib import Path\nPath({name + '.imported'!r}).write_text('yes')\n")
    (folder / "break.toml").write_text(TEXT, encoding="utf-8")
    (folder / "bad.toml").write_text(TEXT.replace('kind = "rollout"', 'kind = "nothing_like_it"'), encoding="utf-8")
    (folder / "cases.jsonl").write_text('{"input": "x"}\n', encoding="utf-8")


@pytest.fixture
def probed(tmp_path: Path) -> tuple[dict[str, object], Path]:
    plant(tmp_path)
    ran = run_python(PROBE, cwd=tmp_path)
    assert ran.exit == 0, ran.stderr
    return json.loads(ran.stdout.strip().splitlines()[-1]), tmp_path


def test_the_probe_read_what_it_set_out_to(probed: tuple[dict[str, object], Path]) -> None:
    """Or the two tests below would pass on a file nobody read."""
    out, _ = probed
    assert "planted_target:agent" in str(out["read"])
    assert "planted_strategy:Mine" in str(out["read"])
    assert out["cases"] == 1
    assert len(out["bad"]) == 2 and out["bad"][0] == "target.kind"  # type: ignore[arg-type,index]


def test_no_framework_is_imported(probed: tuple[dict[str, object], Path]) -> None:
    out, folder = probed
    tops = {name.split(".")[0] for name in out["loaded"]}  # type: ignore[attr-defined]
    assert not tops & set(FRAMEWORKS)
    assert not [p.name for p in folder.glob("*.imported") if p.stem in FRAMEWORKS]


def test_neither_the_target_nor_the_strategy_nor_any_other_code_of_the_users_is_imported(probed: tuple[dict[str, object], Path]) -> None:
    """Two tell-tales each: the module in `sys.modules`, and the file it writes on import, for an import that was
    made and undone. The own check and the stand-in are in the list because the invariant is headed Pure: the module
    reads a file and runs nobody's code."""
    out, folder = probed
    tops = {name.split(".")[0] for name in out["loaded"]}  # type: ignore[attr-defined]
    assert not tops & set(USER_MODULES)
    assert not [p.name for p in folder.glob("*.imported")]


def test_reading_writes_nothing(probed: tuple[dict[str, object], Path]) -> None:
    """`[output] folder` is where a hunt writes. A reader that made it would write outside what `init` and `hunt`
    say they write."""
    _, folder = probed
    assert not (folder / "made-if-anything-makes-it").exists()
    assert not [p.name for p in folder.iterdir() if p.suffix not in (".py", ".toml", ".jsonl", ".imported") and p.name != "__pycache__"]


KIND_PROBE = r'''
from pathlib import Path
from poisson_break import settings as s
try:
    s.load(Path("break.toml"))
except s.SettingsError:
    pass
'''


@pytest.mark.parametrize("kind", ON_DEMAND_KINDS)
def test_looking_for_a_kinds_extra_imports_nothing(tmp_path: Path, kind: str) -> None:
    """`load` must find out about the extra with no import. Whether a thing named like the framework in the current
    folder counts as installed is its own business, and which way it goes is not read here."""
    plant(tmp_path)
    (tmp_path / "break.toml").write_text(TEXT.replace('kind = "rollout"', f'kind = "{kind}"'), encoding="utf-8")
    ran = run_python(KIND_PROBE, cwd=tmp_path)
    assert ran.exit == 0, ran.stderr
    assert not [p.name for p in tmp_path.glob("*.imported")]


# ---------------------------------------------------------------------------
# BK4.7
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ON_DEMAND_KINDS)
def test_a_kind_the_core_does_not_ship_parses(kind: str) -> None:
    """"Accepted by the schema", so that a settings file written for an on-demand module parses today."""
    s = settings()
    read = s.loads(doc(kind=kind))
    assert s.loads(s.dump(read)) == read


def test_the_file_the_spec_prints_parses_though_its_kind_is_not_shipped() -> None:
    settings().loads(SAMPLE)


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "break.toml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("kind", ON_DEMAND_KINDS)
def test_a_kind_the_core_does_not_ship_is_refused_at_load_in_one_line_on_its_key(tmp_path: Path, kind: str) -> None:
    s = settings()
    text = doc(kind=kind)
    with pytest.raises(s.SettingsError) as caught:
        s.load(write(tmp_path, text))
    assert_one_line(caught.value)
    assert caught.value.key == "target.kind"
    assert caught.value.line == line_of(text, "kind =")


@pytest.mark.parametrize("kind, extra", [("openai-agents", "openai-agents"), ("langgraph", "langgraph"), ("crewai", "crewai"), ("mcp", "mcp")])
def test_the_refusal_names_the_extra_to_install(tmp_path: Path, kind: str, extra: str) -> None:
    """The one thing read from a message here, since it is the fact the invariant says the message carries (spec §7.1
    prints `pip install "poisson-break[openai-agents]"`)."""
    s = settings()
    with pytest.raises(s.SettingsError) as caught:
        s.load(write(tmp_path, doc(kind=kind)))
    assert f"poisson-break[{extra}]" in str(caught.value)


def test_the_refusal_for_command_names_some_extra_to_install(tmp_path: Path) -> None:
    """`command` ships with the proxy's module (plan BK13) and the spec does not spell its extra."""
    s = settings()
    with pytest.raises(s.SettingsError) as caught:
        s.load(write(tmp_path, doc(kind="command")))
    assert "poisson-break[" in str(caught.value)


def test_the_kind_the_core_ships_is_not_refused_at_load(tmp_path: Path) -> None:
    s = settings()
    text = doc(kind=SHIPPED_KIND)
    assert s.load(write(tmp_path, text)) == s.loads(text)


def test_the_file_the_spec_prints_is_refused_at_load_naming_its_extra(tmp_path: Path) -> None:
    s = settings()
    with pytest.raises(s.SettingsError) as caught:
        s.load(write(tmp_path, SAMPLE))
    assert "poisson-break[openai-agents]" in str(caught.value)
