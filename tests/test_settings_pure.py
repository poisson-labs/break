"""What reading settings does not do, and what a settings file for a way in not yet installed does.

Invariants pinned here (Break — Plan, the settings module):
- BK4.6 Pure: reading, checking or dumping settings imports no framework and does not import the target or the
        strategy. Nor does working out a plan or a command. This module asks nothing about what a way in can do (yes/no 1), and
        BK5.17 refuses that before any run; whether a strategy's module is there is `load_strategy`'s (yes/no 2).
- BK4.7 A `kind` the core does not ship (`openai-agents`, `langgraph`, `crewai`, `mcp`, `command`) is accepted by the
        schema, so a settings file written for an on-demand module parses, and refused at load in one line. Taylor's yes
        on hands-on issue 17 (2026-11-13): that line says this version has only the rollout way in and names no extra
        to install, since this release publishes none. The refusal still lifts when the adapter's module is there (yes/no
        12), the day a later version ships it. The strategy not yet built is refused at load too (yes/no 11).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import run_python
from tests.settings_support import ON_DEMAND_KINDS, SAMPLE, SHIPPED_KIND, assert_one_line, doc, line_of, refused, settings

FRAMEWORKS = ("openai", "agents", "langchain", "langchain_core", "langgraph", "crewai", "mcp", "anthropic")

# Each of these writes a file when imported, so that an import shows even if the module then cleans up after itself.
USER_MODULES = ("planted_target", "planted_strategy", "planted_check", "planted_stand_in")

PROBE = r'''
import json, shlex, sys
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
words = shlex.split(s.equivalent_init_command(read, prog="poisson-break"))[2:]
out["again"] = s.dump(s.settings_from_init_args(words)) == out["read"]
out["hunt"] = s.plan_hunt(read, cases=12).runs
out["confirm"] = s.plan_confirm(read, cases=12).runs
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
    assert out["again"] is True
    assert out["hunt"] == 400 and out["confirm"] == 1020
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
    """`load` must find out about the extra with no import."""
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


@pytest.mark.parametrize("kind", ON_DEMAND_KINDS)
def test_the_refusal_says_this_version_has_only_the_rollout_way_in_and_names_no_extra(tmp_path: Path,
                                                                                    kind: str) -> None:
    s = settings()
    with pytest.raises(s.SettingsError) as caught:
        s.load(write(tmp_path, doc(kind=kind)))
    said = str(caught.value)
    assert "only the rollout way in" in said and 'kind = "rollout"' in said, said
    assert "pip" not in said and "poisson-break[" not in said, said


# ---------------------------------------------------------------------------
# what lifts the refusal (yes/no 12)
# ---------------------------------------------------------------------------

ADAPTERS = {"openai-agents": "adapters/openai_agents.py", "langgraph": "adapters/langgraph.py", "crewai": "adapters/crewai.py",
            "mcp": "mcp.py", "command": "mcp.py"}

LIFT_PROBE = r'''
import json, sys
from pathlib import Path
import poisson_break
poisson_break.__path__.append(str(Path("planted_package").resolve()))
from poisson_break import settings as s
try:
    s.load(Path("break.toml"))
    print(json.dumps(["taken", sorted(n for n in sys.modules if "adapters." in n or n == "poisson_break.mcp")]))
except s.SettingsError as wrong:
    print(json.dumps(["refused", wrong.key]))
'''


def lifted(tmp_path: Path, kind: str, adapter: str | None) -> list[object]:
    """What `load` says, with the way in's module added to the package, as an installed extra adds it. The module writes a file if imported."""
    plant(tmp_path)
    (tmp_path / "break.toml").write_text(TEXT.replace('kind = "rollout"', f'kind = "{kind}"'), encoding="utf-8")
    package = tmp_path / "planted_package"
    (package / "adapters").mkdir(parents=True)
    (package / "adapters" / "__init__.py").write_text("")
    if adapter is not None:
        (package / adapter).write_text("from pathlib import Path\nPath('adapter.imported').write_text('yes')\n")
    ran = run_python(LIFT_PROBE, cwd=tmp_path)
    assert ran.exit == 0, ran.stderr
    assert not (tmp_path / "adapter.imported").exists(), "looking for the module imported it"
    return json.loads(ran.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("kind", ON_DEMAND_KINDS)
def test_with_the_adapters_module_there_the_refusal_lifts_and_nothing_is_imported(tmp_path: Path, kind: str) -> None:
    assert lifted(tmp_path, kind, ADAPTERS[kind]) == ["taken", []]


@pytest.mark.parametrize("kind, other", [("langgraph", "adapters/crewai.py"), ("openai-agents", "mcp.py"), ("mcp", "adapters/langgraph.py")])
def test_another_kinds_module_does_not_lift_it(tmp_path: Path, kind: str, other: str) -> None:
    assert lifted(tmp_path, kind, other) == ["refused", "target.kind"]


@pytest.mark.parametrize("kind", ["langgraph", "crewai", "openai-agents"])
def test_the_framework_alone_does_not_lift_it(tmp_path: Path, kind: str) -> None:
    """The extra is the adapter, not the framework: `plant` puts a module named like each framework in the folder."""
    assert lifted(tmp_path, kind, None) == ["refused", "target.kind"]


def test_the_kind_the_core_ships_is_not_refused_at_load(tmp_path: Path) -> None:
    s = settings()
    text = doc(kind=SHIPPED_KIND)
    assert s.load(write(tmp_path, text)) == s.loads(text)


def test_the_file_the_spec_prints_is_refused_at_load_saying_only_rollout(tmp_path: Path) -> None:
    s = settings()
    with pytest.raises(s.SettingsError) as caught:
        s.load(write(tmp_path, SAMPLE))
    assert "only the rollout way in" in str(caught.value)


# ---------------------------------------------------------------------------
# what this module leaves to the modules that hold the target (yes/nos 1 and 2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("line", ['conversation = ["repeats"]', 'model = ["error"]', 'conversation = ["presses"]\nmodel = ["cut_off"]'])
def test_reading_asks_nothing_about_what_a_way_in_can_do(tmp_path: Path, line: str) -> None:
    """Yes/no 1. A `rollout` target can do neither of these, and BK5.17 refuses them before any run. Here it reads, from text and from a file."""
    s = settings()
    text = doc(kind=SHIPPED_KIND, vary=line)
    assert s.load(write(tmp_path, text)) == s.loads(text)
    assert s.loads(s.dump(s.loads(text))) == s.loads(text)


def test_a_strategy_whose_module_is_not_there_is_read_by_its_form_alone(tmp_path: Path) -> None:
    """Yes/no 2: that it is absent is `load_strategy`'s to say, before any run."""
    s = settings()
    text = doc(search='strategy = "no_such_module_anywhere:Mine"')
    assert s.load(write(tmp_path, text)) == s.loads(text)


# ---------------------------------------------------------------------------
# the strategy not yet built (yes/no 11)
# ---------------------------------------------------------------------------


def test_the_strategy_not_yet_built_parses() -> None:
    settings().loads(doc(search='strategy = "adaptive"'))


def test_the_strategy_not_yet_built_is_refused_at_load_in_one_line_on_its_key(tmp_path: Path) -> None:
    s = settings()
    text = doc(search='strategy = "adaptive"')
    with pytest.raises(s.SettingsError) as caught:
        s.load(write(tmp_path, text))
    assert_one_line(caught.value)
    assert caught.value.key == "search.strategy"
    assert caught.value.line == line_of(text, "strategy =")


@pytest.mark.parametrize("name", ["screen", "random", "my_app.search:Mine"])
def test_the_strategies_there_are_not_refused_at_load(tmp_path: Path, name: str) -> None:
    settings().load(write(tmp_path, doc(search=f'strategy = "{name}"')))


def test_a_misspelling_of_it_is_still_refused_when_read() -> None:
    assert refused(doc(search='strategy = "adaptiv"')).key == "search.strategy"
