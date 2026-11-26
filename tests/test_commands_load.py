"""Wrapping at load, from the command: `init`, `doctor`, `hunt` and the rest on an agent whose code holds no Break line
(spec §12.5 to §12.7).

Invariants held here (Break — Plan, the module that wraps tools at load; spec §12.8):
- BK15.4  The same replay, and the same words on screen: a hunt, a confirm, `findings`, a `replay` and a `recheck` of
          the twins, each in a folder of its own under one hunt name and one seed, print the same bytes and the same
          `--json` documents, and write the same finding files but for the store's path. `hunt.json` differs in
          `reached` and in `settings`' `[tools]` lines and nowhere else.
- BK15.8  No Break line is needed: `init`, `doctor`, `hunt`, `confirm`, `replay` and `recheck` run on the second twin
          end to end. (That its source holds no `poisson_break` is `tests/test_load_twins.py`'s.)
- BK15.17, the commands' half: for each way of §12.7, `doctor` is `not ready` with exit 4, `hunt` exits 1 with one
          `error:` line and a `next:`, and no hunt folder is made. For ways 1 to 7 the `next:` lines of `hunt`,
          `confirm`, `replay` and `recheck` hold `doctor`.
- BK15.21 `init`: with no wrapped tool found, a typed name the entry's module holds gets its `at`, a name it does not
          hold gets the one further question, and an empty answer writes the line with no `at`. The command `init`
          prints, run as printed, writes the same file. With wrapped tools found, the questions and the file are as on
          `main`. Every file of the user's module has the same bytes before and after.
- BK15.22 `doctor` says how each tool is reached: `reached` in `--json` has one object for each tool not `off`, with
          `how` one of `at load`, `wrap` and `not seen`; the plain and pretty renderings carry the same facts; `tools`
          is the list it is on `main`; a holder of BK15.10 and a tool `not seen` each give one note on stderr and exit 0.
- BK15.23 `hunt.json` holds `reached`, equal to what `doctor` reported, and a hunt opened again under a different
          answer adds one entry to `later_reached` when its first run starts and none before.
- BK15.24 The copy holds: the pattern test of plan BK11.3 passes over every sentence this module prints, and no line it
          prints holds a module id, a ruling number or a session name.

Ruled 2026-11-19 (spec §12.11): `init` writes an `at` for each name typed that the entry's module holds (question 9),
and asks nothing new when it finds wrapped tools (10); `doctor` gains the `reached` row, its `--json` key and its notes
(11); `hunt.json` gains `reached` and `later_reached` under `/1` (12). Ruled 2026-11-20 (this module's Session A): a
refusal's test pins its kind, the tool and its facts, never its words.

What is read back is structure and facts, as in every commands test (`tests/commands_support.py`).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from tests.commands_dialogue import Asked, converse
from tests.commands_support import (
    CODES,
    PROG,
    Project,
    cli,
    errors,
    json_document,
    nexts,
    project,
    verdict,
)
from tests.conftest import GUARD, REPO
from tests.load_support import (
    BARE_TWIN,
    CHECK_PLACES,
    HOLDERS,
    HOLDERS_ENTRY,
    HOLDERS_TOOLS,
    LOOKUP_PLACES,
    SPEC_TOOLS,
    TOOLS_PY,
    WRAPPED_TWIN,
    spec_project,
    spec_settings,
)
from tests.look_support import TERMINALS, strip
from tests.test_load_refusals import WAYS as LIBRARY_WAYS


def on_path(proj: Project, *folders: Path) -> Project:
    """The project's child processes import from `folders` first, then as every command test does."""
    proj.env["PYTHONPATH"] = os.pathsep.join([*(str(f) for f in folders), str(GUARD), str(REPO / "src"), str(REPO)])
    return proj


def spec_proj(tmp_path: Path, lines: Mapping[str, Any] | None = None, **files: str | None) -> Project:
    """A project holding the spec's `my_app`, with `break.toml` for it giving `lines` as `[tools]`: its folder is where
    the command runs, so the package is imported from there. `files` are `spec_project`'s."""
    proj = project(tmp_path, write=False)
    spec_project(proj.folder, **files)
    proj.write(spec_settings(lines), [{"id": f"k{i}", "input": str(i)} for i in (1, 2, 3)])
    return proj


def reached_by_tool(found: Any) -> dict[str, dict[str, Any]]:
    """`reached` as `doctor --json` or `hunt.json` holds it, by tool: a list of objects that each name their tool, or
    an object keyed by the tool's name."""
    if isinstance(found, list):
        return {item["tool"]: {k: v for k, v in item.items() if k != "tool"} for item in found}
    assert isinstance(found, dict), found
    return {tool: {k: v for k, v in item.items() if k != "tool"} for tool, item in found.items()}


def note_texts(ran: Any) -> list[str]:
    """Each `note:` on stderr with the lines that carry it on, as one line of text."""
    found: list[str] = []
    open_note = False
    for line in strip(ran.err).splitlines():
        if line.startswith("note: "):
            found.append(line[len("note: "):])
            open_note = True
        elif open_note and line.startswith(" ") and not line.strip().startswith("next:"):
            found[-1] += " " + line.strip()
        else:
            open_note = False
    return [" ".join(n.split()) for n in found]


def said_on(stream: str) -> str:
    """A stream as one line of text, escapes gone, so that a fact a wrapped line split is found whole."""
    return " ".join(strip(stream).split())


# ---------------------------------------------------------------------------
# BK15.22: doctor says how each tool is reached
# ---------------------------------------------------------------------------

WRAPPING_AGENTS = '''\
from poisson_prove import Episode

from poisson_break.apply import wrap
from my_app.tools import check_policy, issue_refund, send_email
from my_app.tools import lookup_order as _lookup_order

lookup_order = wrap("lookup_order", _lookup_order)


def refund_agent(cfg, seed):
    return Episode(outcome="done", t=0.0, horizon=1.0, meta={"reply": lookup_order(cfg["input"])})
'''

MIXED_TOOLS = {"lookup_order": "read", "check_policy": {"class": "read", "at": "my_app.tools:check_policy"},
               "issue_refund": SPEC_TOOLS["issue_refund"], "send_email": "off", "send_sms": "read"}


@pytest.fixture(scope="module")
def doctor_mixed(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """`doctor`, plain, pretty on terminals, and `--json`, on a project with one tool of each `how` and one `off`."""
    proj = spec_proj(tmp_path_factory.mktemp("mixed"), MIXED_TOOLS, agents=WRAPPING_AGENTS)
    return {"plain": cli(proj, "--plain", "doctor"), "pretty": cli(proj, "doctor", streams=TERMINALS),
            "json": cli(proj, "doctor", "--json")}


@pytest.fixture(scope="module")
def doctor_holders(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """`doctor` on the holders module, with a line for a tool nothing reaches."""
    proj = project(tmp_path_factory.mktemp("holders"), entry=HOLDERS_ENTRY,
                   tools={**HOLDERS_TOOLS, "send_sms": "read"})
    return {"plain": cli(proj, "--plain", "doctor"), "json": cli(proj, "doctor", "--json"), "project": proj}


def test_doctor_s_json_says_how_each_tool_that_is_not_off_is_reached(doctor_mixed: dict[str, Any]) -> None:
    ran = doctor_mixed["json"]
    assert ran.exit == CODES["done"], ran
    document = json_document(ran)
    assert document["verdict"] == "ready"
    assert [item["tool"] for item in document["reached"]] == ["lookup_order", "check_policy", "issue_refund",
                                                               "send_sms"]
    for item in document["reached"]:
        assert set(item) == {"tool", "how", "at", "places", "held_elsewhere"}, item
        assert item["how"] in ("at load", "wrap", "not seen"), item
    got = reached_by_tool(document["reached"])
    assert (got["lookup_order"]["how"], got["lookup_order"]["at"], got["lookup_order"]["places"]) == ("wrap", None, [])
    assert (got["check_policy"]["how"], got["check_policy"]["at"]) == ("at load", "my_app.tools:check_policy")
    assert got["check_policy"]["places"] == ["my_app.agents:check_policy", "my_app.tools:check_policy"]
    assert got["check_policy"]["held_elsewhere"] == []
    assert (got["issue_refund"]["how"], got["issue_refund"]["at"]) == ("at load", "my_app.tools:issue_refund")
    assert (got["send_sms"]["how"], got["send_sms"]["at"], got["send_sms"]["places"]) == ("not seen", None, [])


def test_doctor_s_tools_is_the_list_it_is_on_main(doctor_mixed: dict[str, Any]) -> None:
    """Spec §12.5: `--json` keeps `tools` as the list of names it is today: every `[tools]` line, `off` among them, in
    the file's order."""
    document = json_document(doctor_mixed["json"])
    assert document["tools"] == ["lookup_order", "check_policy", "issue_refund", "send_email", "send_sms"]


def reached_block(ran: Any) -> str:
    """The `reached` row of a `ready`, with the lines that carry it on, up to the next row or `next:`, as one line."""
    lines = strip(ran.out).splitlines()
    start = next(n for n, line in enumerate(lines) if line.split()[:1] == ["reached"])
    indent = len(lines[start]) - len(lines[start].lstrip())
    block = [lines[start]]
    for line in lines[start + 1:]:
        if not line.strip() or line.strip().startswith("next:"):
            break
        if len(line) - len(line.lstrip()) <= indent:
            break
        block.append(line)
    return " ".join(" ".join(block).split())


@pytest.mark.parametrize("rendering", ["plain", "pretty"])
def test_doctor_s_reached_row_names_each_tool_and_where_it_was_wrapped(doctor_mixed: dict[str, Any],
                                                                       rendering: str) -> None:
    """Spec §12.5: a line for every tool that is not `off`; a tool wrapped at load names the modules it was wrapped in.
    Both renderings carry the same facts."""
    ran = doctor_mixed[rendering]
    assert ran.exit == CODES["done"], ran
    assert verdict(ran)[0] == "ready"
    block = reached_block(ran)
    for tool in ("lookup_order", "check_policy", "issue_refund", "send_sms"):
        assert len(re.findall(rf"\b{tool}\b", block)) == 1, (tool, block)
    assert "send_email" not in block
    check = block[block.index("check_policy"):block.index("issue_refund")]
    assert "my_app.tools" in check and "my_app.agents" in check, check


def test_a_tool_not_seen_is_one_note_and_doctor_is_still_ready(doctor_mixed: dict[str, Any]) -> None:
    """Spec §12.5: `send_sms has no wrap line that ran while loading and no at in break.toml; Break reaches it only if
    your code wraps it later`. A note, not a refusal: a `wrap` inside a function that has not run yet is allowed."""
    ran = doctor_mixed["plain"]
    assert ran.exit == CODES["done"] and verdict(ran)[0] == "ready", ran
    said = note_texts(ran)
    assert len([n for n in said if "send_sms" in n]) == 1, said
    assert [n for n in said if re.search(r"\bcheck_policy\b|\blookup_order\b", n)] == [], said


def test_a_holder_that_cannot_be_replaced_is_one_note_naming_each(doctor_holders: dict[str, Any]) -> None:
    """Spec §12.5 and §12.11, question 4: one note for each tool that has any such holder, naming the kind and where;
    never a refusal. `check_policy` has none, and gets no note."""
    ran = doctor_holders["plain"]
    assert ran.exit == CODES["done"] and verdict(ran)[0] == "ready", ran
    said = note_texts(ran)
    about = [n for n in said if re.search(r"\blookup_order\b", n)]
    assert len(about) == 1, said
    for where in (f"{HOLDERS}.agent:FIND", f"{HOLDERS}.agent:HELP", f"{HOLDERS}.agent:make_agent"):
        assert where in about[0], (where, about[0])
    assert [n for n in said if re.search(r"\bcheck_policy\b", n)] == [], said
    assert len([n for n in said if "send_sms" in n]) == 1, said


def test_doctor_s_json_names_the_holders(doctor_holders: dict[str, Any]) -> None:
    document = json_document(doctor_holders["json"])
    got = reached_by_tool(document["reached"])
    assert got["lookup_order"]["places"] == list(LOOKUP_PLACES)
    assert got["check_policy"]["places"] == list(CHECK_PLACES)
    held = got["lookup_order"]["held_elsewhere"]
    assert sorted(h["kind"] for h in held) == ["closure", "container", "object", "partial"], held
    assert all(set(h) == {"kind", "where"} for h in held), held
    assert got["check_policy"]["held_elsewhere"] == []


def test_where_the_interpreter_cannot_list_what_refers_doctor_says_the_check_was_not_made(tmp_path: Path) -> None:
    """Spec §12.11, question 4: `held_elsewhere` is null, and `doctor` says the check was not made, in a note: more
    notes than the same project gives where the list can be had."""
    proj = spec_proj(tmp_path)
    code = ("import gc, sys; del gc.get_referrers; from poisson_break.cli import main; "
            "sys.exit(main(sys.argv[1:], prog='poisson-break'))")
    from tests.commands_support import child_env
    from tests.look_support import PIPED, launch

    blind = launch([sys.executable, "-c", code, "doctor", "--json"], child_env(proj), PIPED,
                   cwd=proj.folder, timeout=240)
    assert blind.exit == CODES["done"], blind
    got = reached_by_tool(json_document(blind)["reached"])
    assert got["lookup_order"]["held_elsewhere"] is None
    plain = launch([sys.executable, "-c", code, "--plain", "doctor"], child_env(proj), PIPED,
                   cwd=proj.folder, timeout=240)
    seeing = cli(proj, "--plain", "doctor")
    assert plain.exit == seeing.exit == CODES["done"], (plain, seeing)
    assert len(note_texts(plain)) > len(note_texts(seeing)), (note_texts(plain), note_texts(seeing))


# ---------------------------------------------------------------------------
# BK15.17: each way of §12.7, from doctor and hunt
# ---------------------------------------------------------------------------

#: Ways 8 and 9, the settings file's own, beside the library's seven: the lines, the tool, and the same lines with the
#: one fault mended, which `doctor` finds ready.
SETTINGS_WAYS: dict[str, tuple[dict[str, Any], str, dict[str, Any]]] = {
    "8, at on an off line": ({**SPEC_TOOLS, "send_email": {"class": "off", "at": "my_app.tools:send_email"}},
                             "send_email", SPEC_TOOLS),
    "9, not module:name": ({"lookup_order": {"class": "read", "at": "my_app.tools.lookup_order"}}, "lookup_order",
                           {"lookup_order": {"class": "read", "at": "my_app.tools:lookup_order"}}),
    "9, a name inside a class": ({"lookup": {"class": "read", "at": "my_app.tools:Orders.lookup"}}, "lookup",
                                 {"lookup": {"class": "read", "at": "my_app.tools:lookup_order"}}),
}
WAY_NAMES = [*LIBRARY_WAYS, *SETTINGS_WAYS]


@pytest.fixture(scope="module")
def way_runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
    """For each way: `doctor`, `doctor --json` and `hunt --yes` in a project that meets it, and what the project
    folder holds after."""
    held: dict[str, dict[str, Any]] = {}
    for name in WAY_NAMES:
        if name in LIBRARY_WAYS:
            way = LIBRARY_WAYS[name]
            tools, tool, files = way.lines, way.tool, way.files
            mended = None
        else:
            tools, tool, mended = SETTINGS_WAYS[name]
            files = {}
        proj = spec_proj(tmp_path_factory.mktemp("way"), tools, **files)
        held[name] = {"tool": tool, "settings": proj.settings.read_text(encoding="utf-8"),
                      "mended": None if mended is None else cli(spec_proj(tmp_path_factory.mktemp("mended"), mended),
                                                                "doctor"),
                      "doctor": cli(proj, "--plain", "doctor"), "json": cli(proj, "doctor", "--json"),
                      "hunt": cli(proj, "--plain", "hunt", "--yes"), "hunts": proj.hunts.exists(),
                      "runs": proj.runs()}
    return held


@pytest.mark.parametrize("name", WAY_NAMES)
def test_doctor_is_not_ready_with_exit_4_naming_the_tool(way_runs: dict[str, dict[str, Any]], name: str) -> None:
    said = way_runs[name]
    ran = said["doctor"]
    assert ran.exit == CODES["check"], ran
    assert verdict(ran)[0] == "not ready"
    assert re.search(rf"\b{said['tool']}\b", said_on(ran.out)), ran
    assert nexts(ran), ran
    assert "Traceback" not in ran.err
    document = json_document(said["json"])
    assert document["verdict"] == "not ready"
    if name in SETTINGS_WAYS:
        mended = said["mended"]
        assert mended.exit == CODES["done"] and verdict(mended)[0] == "ready", ("the line mended", mended)
        assert document["key"] is not None and document["key"].startswith(f"tools.{said['tool']}"), document
        line = next(n for n, row in enumerate(said["settings"].splitlines(), 1) if row.startswith(f'"{said["tool"]}"'))
        assert document["line"] == line, document


@pytest.mark.parametrize("name", WAY_NAMES)
def test_hunt_exits_1_with_one_error_line_and_a_next_and_makes_no_hunt(way_runs: dict[str, dict[str, Any]],
                                                                        name: str) -> None:
    said = way_runs[name]
    ran = said["hunt"]
    assert ran.exit == CODES["refused"], ran
    assert len(errors(ran)) == 1, ran
    assert re.search(rf"\b{said['tool']}\b", said_on(ran.err)), ran
    assert nexts(ran), ran
    if name in LIBRARY_WAYS:
        assert [PROG, "doctor"] in [shlex.split(n) for n in nexts(ran)], nexts(ran)
    assert "Traceback" not in ran.err
    assert not said["hunts"]
    assert said["runs"] == []


@pytest.mark.parametrize("name", list(LIBRARY_WAYS))
def test_the_line_shown_carries_the_facts_of_its_way(way_runs: dict[str, dict[str, Any]], name: str) -> None:
    """What `hunt` shows and `doctor` says carry the facts of spec §12.7's line for the way, as the library's refusal
    does (`tests/test_load_refusals.py`)."""
    way = LIBRARY_WAYS[name]
    shown = said_on(way_runs[name]["hunt"].err)
    said = said_on(way_runs[name]["doctor"].out)
    for fact in way.facts:
        assert fact in shown, (fact, shown)
        assert fact in said, (fact, said)


FAILING_AGENTS = '''\
from poisson_prove import Episode

from my_app.tools import check_policy, lookup_order


def refund_agent(cfg, seed):
    try:
        found = lookup_order(cfg["input"])
    except Exception:
        return Episode(outcome="unresolved", t=0.0, horizon=1.0, meta={"reply": "I could not look it up."})
    return Episode(outcome="done", t=0.0, horizon=1.0, meta={"reply": found + " " + check_policy("refunds")})
'''
ASYNC_TOOLS = TOOLS_PY + "\n\nasync def lookup_order(query: str) -> str:\n    return query\n"


def test_confirm_replay_and_recheck_refuse_a_way_with_doctor_next(tmp_path: Path) -> None:
    """Spec §12.7: `hunt`, `confirm`, `replay` and `recheck` print ways 1 to 7 as `error:`, exit 1, with `next:
    poisson-break doctor`. A hunt and its findings are made with the agent as it was, and then its tool turns async
    (way 7) before each verb."""
    proj = spec_proj(tmp_path, {"lookup_order": {"class": "read", "at": "my_app.tools:lookup_order"},
                                "check_policy": "read"}, agents=FAILING_AGENTS)
    tools_file = proj.folder / "my_app" / "tools.py"
    assert cli(proj, "hunt", "--yes", PYTHONDONTWRITEBYTECODE="1").exit == CODES["done"]
    tools_file.write_text(ASYNC_TOOLS, encoding="utf-8")
    refused_confirm = cli(proj, "confirm", "--yes", PYTHONDONTWRITEBYTECODE="1")
    tools_file.write_text(TOOLS_PY, encoding="utf-8")
    done = cli(proj, "confirm", "--yes", PYTHONDONTWRITEBYTECODE="1")
    assert done.exit == CODES["done"], done
    tools_file.write_text(ASYNC_TOOLS, encoding="utf-8")
    for ran in (refused_confirm, cli(proj, "replay", "1", PYTHONDONTWRITEBYTECODE="1"),
                cli(proj, "recheck", "--yes", PYTHONDONTWRITEBYTECODE="1")):
        assert ran.exit == CODES["refused"], ran
        assert len(errors(ran)) == 1 and "lookup_order" in said_on(ran.err), ran
        assert [PROG, "doctor"] in [shlex.split(n) for n in nexts(ran)], nexts(ran)


OLD_AGENTS = '''\
from poisson_prove import Episode

from my_app.tools import lookup_order


def refund_agent(cfg, seed):
    try:
        lookup_order(cfg["input"])
    except Exception:
        return Episode(outcome="unresolved", t=0.0, horizon=1.0, meta={"reply": "I could not look it up."})
    return Episode(outcome="done", t=0.0, horizon=1.0, meta={"reply": "Found it."})
'''


def test_doctor_run_and_recheck_old_reach_a_tool_wrapped_at_load(tmp_path: Path) -> None:
    """Spec §12.5: `doctor --run` is as today, on an agent whose tools are wrapped at load. Spec §12.4 and §12.11,
    question 13: `recheck --old ENTRY` loads the old agent under the same `[tools]` lines, and reaches it where it
    calls the same functions: the old agent fails under each finding as the agent did, so no finding fails less."""
    proj = spec_proj(tmp_path, {"lookup_order": {"class": "read", "at": "my_app.tools:lookup_order"},
                                "check_policy": "read"}, agents=FAILING_AGENTS, old=OLD_AGENTS)
    run = cli(proj, "doctor", "--run", "--yes", "--json", PYTHONDONTWRITEBYTECODE="1")
    assert run.exit == CODES["done"], run
    assert json_document(run)["run"]["outcome"] == "ok", run
    for words in (["hunt", "--yes"], ["confirm", "--yes"]):
        ran = cli(proj, *words, PYTHONDONTWRITEBYTECODE="1")
        assert ran.exit == CODES["done"], ran
    old = cli(proj, "recheck", "--old", "my_app.old:refund_agent", "--yes", "--json", PYTHONDONTWRITEBYTECODE="1")
    assert old.exit == CODES["done"], old
    findings = json_document(old)["findings"]
    assert findings and all(f["phrase"] != "fails less" for f in findings), findings


# ---------------------------------------------------------------------------
# BK15.21: init
# ---------------------------------------------------------------------------

AGENT_Q = "Where is your agent"
CASES_Q = "Where are your test cases"
STARTER_Q = "There is no such file"
NAMES_Q = "No tool was found"
SMS_PY = 'def send_sms(to: str) -> str:\n    return "sent"\n'


def is_where(asked: Asked) -> bool:
    """The further question for a name the entry's module does not hold: where that function is, as `module:name`."""
    q = asked.question
    return (not asked.yes_no and "module:name" in q and not q.startswith(AGENT_Q) and "stand-in" not in q)


def answering(entry: str, names: str, where: Mapping[str, str], classes: Mapping[str, list[str]]
              ) -> Callable[[Asked], str]:
    left = {tool: list(said) for tool, said in classes.items()}

    def answer(asked: Asked) -> str:
        q = asked.question
        if q.startswith(AGENT_Q):
            return entry
        if q.startswith(CASES_Q) or q.startswith(STARTER_Q):
            return ""
        if q.startswith(NAMES_Q):
            return names
        if is_where(asked):
            tools = [t for t in where if re.search(rf"\b{t}\b", q)]
            assert len(tools) == 1, f"a question the script did not expect: {asked.text!r}"
            return where[tools[0]]
        tools = [t for t in left if re.search(rf"\b{t}\b", q)]
        assert len(tools) == 1 and left[tools[0]], f"a question the script did not expect: {asked.text!r}"
        return left[tools[0]].pop(0)

    return answer


def expected_file(*tool_lines: str) -> str:
    from poisson_break.settings import dump, settings_from_init_args

    words = ["--kind", "rollout", "--entry", "my_app.agents:refund_agent", "--cases", "cases.jsonl"]
    for line in tool_lines:
        words += ["--tool", line]
    return str(dump(settings_from_init_args(words)))


CLASSES = {"lookup_order": ["n"], "issue_refund": ["y", "n", "my_app.fakes:refund"], "send_sms": ["y", "y"]}


def init_project(tmp_path: Path) -> Project:
    proj = project(tmp_path, write=False)
    spec_project(proj.folder, sms=SMS_PY)
    proj.write(case_list=[{"id": "k1", "input": "Where is order 1?"}])
    return proj


def files_of(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


@pytest.fixture(scope="module", params=["plain", "pretty"])
def init_found(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """`init` on the spec's project, whose entry module wraps nothing: three names typed, two of which the module
    holds; the third is placed by the further question."""
    proj = init_project(tmp_path_factory.mktemp(f"init-{request.param}"))
    before = files_of(proj.folder / "my_app")
    ran, asked = converse(proj, ["init"], answering("my_app.agents:refund_agent", "lookup_order, issue_refund, send_sms",
                                                    {"send_sms": "my_app.sms:send_sms"}, CLASSES),
                          pretty=request.param == "pretty", PYTHONDONTWRITEBYTECODE="1")
    return {"project": proj, "ran": ran, "asked": asked, "before": before,
            "after": files_of(proj.folder / "my_app")}


def test_init_writes_an_at_for_each_name_the_entry_s_module_holds_and_asks_where_the_other_is(
        init_found: dict[str, Any]) -> None:
    """Spec §12.5, question 9: a name the entry's module holds gets `at = "<the entry's module>:<name>"`; a name it does
    not hold gets one more question, answered here. The class questions follow, as today."""
    ran, asked, proj = init_found["ran"], init_found["asked"], init_found["project"]
    assert ran.exit == CODES["done"], (ran, [a.text for a in asked])
    questions = [a.question for a in asked]
    names = next(n for n, q in enumerate(questions) if q.startswith(NAMES_Q))
    where = [a for a in asked if is_where(a)]
    assert len(where) == 1 and "send_sms" in where[0].question, questions
    assert not [a for a in asked if is_where(a) and re.search(r"\blookup_order\b|\bissue_refund\b", a.question)]
    assert asked.index(where[0]) == names + 1, questions
    changes = [q for q in questions[names + 2:] if q.startswith("Does calling")]
    assert len(changes) == 3, questions
    for question, tool in zip(changes, ("lookup_order", "issue_refund", "send_sms"), strict=True):
        assert re.search(rf"\b{tool}\b", question), (tool, question)
    assert not any(a.is_menu for a in asked)
    assert proj.settings.read_text(encoding="utf-8") == expected_file(
        'lookup_order = { class = "read", at = "my_app.agents:lookup_order" }',
        'issue_refund = { class = "write", stand_in = "my_app.fakes:refund", at = "my_app.agents:issue_refund" }',
        'send_sms = { class = "write", repeatable = true, at = "my_app.sms:send_sms" }')


def test_init_says_where_each_name_it_found_is(init_found: dict[str, Any]) -> None:
    """Spec §12.5: one line a tool, naming it and the entry's module, before the questions that follow. On terminals a
    question's own text is what was printed since the last answer, its prompt last."""
    lines = [line for asked in init_found["asked"] for line in asked.text.splitlines()[:-1]]
    lines += [line for line in strip(init_found["ran"].out).splitlines() if "next:" not in line]
    for tool in ("lookup_order", "issue_refund"):
        said = [line for line in lines if re.search(rf"\b{tool}\b", line) and "my_app.agents" in line]
        assert len(said) >= 1, (tool, lines)


def test_init_changes_no_file_of_the_user_s_module(init_found: dict[str, Any]) -> None:
    assert init_found["after"] == init_found["before"]


def test_init_s_printed_command_run_as_printed_writes_the_same_file(init_found: dict[str, Any],
                                                                     tmp_path: Path) -> None:
    """The command `init` prints carries each `at` in its `--tool`; run as printed in another folder holding the same
    project, with no terminal, it writes the same bytes."""
    proj = init_found["project"]
    printed = [shlex.split(n) for n in nexts(init_found["ran"]) if shlex.split(n)[:2] == [PROG, "init"]]
    assert len(printed) == 1, nexts(init_found["ran"])
    assert any("at =" in word for word in printed[0]), printed[0]
    other = init_project(tmp_path)
    again = cli(other, *printed[0][1:])
    assert again.exit == CODES["done"], again
    assert other.settings.read_bytes() == proj.settings.read_bytes()


def test_an_empty_answer_to_where_writes_the_line_with_no_at(tmp_path: Path) -> None:
    proj = init_project(tmp_path)
    ran, asked = converse(proj, ["init"], answering("my_app.agents:refund_agent", "lookup_order, send_sms",
                                                    {"send_sms": ""}, {k: CLASSES[k] for k in ("lookup_order",
                                                                                               "send_sms")}),
                          PYTHONDONTWRITEBYTECODE="1")
    assert ran.exit == CODES["done"], (ran, [a.text for a in asked])
    assert len([a for a in asked if is_where(a)]) == 1
    assert proj.settings.read_text(encoding="utf-8") == expected_file(
        'lookup_order = { class = "read", at = "my_app.agents:lookup_order" }',
        'send_sms = { class = "write", repeatable = true }')


def test_with_wrapped_tools_found_init_asks_nothing_new_and_writes_no_at(tmp_path: Path) -> None:
    """Spec §12.11, question 10: where `init` finds wrapped tools, the same questions and the same file: no name is
    asked for, no place, and no line has `at`, though the module holds a function by another tool's name."""
    proj = project(tmp_path, write=False)
    spec_project(proj.folder, agents=WRAPPING_AGENTS)
    proj.write(case_list=[{"id": "k1", "input": "Where is order 1?"}])
    ran, asked = converse(proj, ["init"], answering("my_app.agents:refund_agent", "", {}, {"lookup_order": ["n"]}),
                          PYTHONDONTWRITEBYTECODE="1")
    assert ran.exit == CODES["done"], (ran, [a.text for a in asked])
    assert not [a for a in asked if a.question.startswith(NAMES_Q) or is_where(a)]
    assert proj.settings.read_text(encoding="utf-8") == expected_file('lookup_order = "read"')


# ---------------------------------------------------------------------------
# BK15.4, BK15.8 and BK15.23: the twins from init to recheck
# ---------------------------------------------------------------------------

#: `init`'s flags for both twins: everything but the tools, so the hunts are small and the dialogue asks only of tools.
INIT_FLAGS = ["--entry", "twin_desk:desk", "--cases", "cases.jsonl", "--outcomes", "unresolved",
              "--vary-tools", "error,timeout,rate_limited", "--vary-inputs", "[]", "--max-call", "1",
              "--runs", "60", "--control-repeats", "2", "--cases-per-condition", "2", "--seed", "20261120",
              "--confirm-repeats", "3", "--run-seconds", "30"]
TWIN_CLASSES = {"lookup_order": ["n"], "check_policy": ["n"], "issue_refund": ["y", "y"]}
TWIN_CASES = [{"id": f"k{i}", "input": f"Where is order {i}? Please refund it.", "agent": agent}
              for i, agent in enumerate(("gives_up", "gives_up", "repeats_write"), 1)]
VERBS: list[list[str]] = [["hunt", "--yes"], ["confirm", "--yes"], ["findings"], ["findings", "1"], ["replay", "1"],
                          ["recheck", "--yes"]]
TIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?")


def twin_project(root: Path, twin: Path) -> Project:
    proj = on_path(project(root, write=False), twin)
    proj.write(case_list=TWIN_CASES)
    return proj


def normal(text: str, proj: Project) -> str:
    """What two folders' outputs may differ in and still be the same: the folder's own path, and the clock."""
    return TIME.sub("<time>", text.replace(str(proj.folder), "<project>").replace(str(proj.home), "<home>"))


@pytest.fixture(scope="module")
def twin_chains(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
    """Each twin from `init` to `recheck`, in a folder of its own, in plain; then again under `--json` in a second
    folder holding the `break.toml` the first `init` wrote."""
    held: dict[str, dict[str, Any]] = {}
    for side, twin in (("wrapped", WRAPPED_TWIN), ("bare", BARE_TWIN)):
        plain = twin_project(tmp_path_factory.mktemp(f"{side}-plain"), twin)
        names = "lookup_order, check_policy, issue_refund"
        init, asked = converse(plain, ["init", *INIT_FLAGS], answering("twin_desk:desk", names, {}, TWIN_CLASSES),
                               PYTHONDONTWRITEBYTECODE="1")
        doctor = cli(plain, "doctor", "--json", PYTHONDONTWRITEBYTECODE="1")
        ran = [cli(plain, "--plain", *words, PYTHONDONTWRITEBYTECODE="1") for words in VERBS]
        as_json = twin_project(tmp_path_factory.mktemp(f"{side}-json"), twin)
        if plain.settings.exists():
            shutil.copy(plain.settings, as_json.settings)
        documents = [cli(as_json, *words, "--json", PYTHONDONTWRITEBYTECODE="1") for words in VERBS]
        held[side] = {"plain": plain, "json": as_json, "init": init, "asked": asked, "doctor": doctor, "ran": ran,
                      "documents": documents}
    return held


def test_init_on_each_twin_writes_the_same_file_but_for_at(twin_chains: dict[str, dict[str, Any]]) -> None:
    """BK15.8 and BK15.21: on the bare twin `init` finds no wrapped tool, is told the three names, and writes an `at`
    for each in the entry's module; on the wrapped twin it finds the three. The two files read as the same settings
    once the `at`s are taken off."""
    import tomllib

    for side in ("wrapped", "bare"):
        assert twin_chains[side]["init"].exit == CODES["done"], twin_chains[side]["init"]
    wrapped = tomllib.loads(twin_chains["wrapped"]["plain"].settings.read_text(encoding="utf-8"))
    bare = tomllib.loads(twin_chains["bare"]["plain"].settings.read_text(encoding="utf-8"))
    ats = {tool: line.pop("at") for tool, line in bare["tools"].items() if isinstance(line, dict) and "at" in line}
    assert ats == {"lookup_order": "twin_desk:lookup_order", "check_policy": "twin_desk:check_policy",
                   "issue_refund": "twin_desk:issue_refund"}
    bare["tools"] = {tool: (line["class"] if set(line) == {"class"} else line) if isinstance(line, dict) else line
                     for tool, line in bare["tools"].items()}
    assert bare == wrapped


def test_every_command_runs_on_the_bare_twin_end_to_end(twin_chains: dict[str, dict[str, Any]]) -> None:
    """BK15.8: `init`, `doctor`, `hunt`, `confirm`, `replay` and `recheck` on an agent with no Break line: each exits as
    on the wrapped twin, `doctor` is ready with every tool wrapped at load, and the hunt finds and confirms."""
    bare = twin_chains["bare"]
    doctor = json_document(bare["doctor"])
    assert bare["doctor"].exit == CODES["done"] and doctor["verdict"] == "ready", bare["doctor"]
    assert {item["how"] for item in doctor["reached"]} == {"at load"}
    for words, ran in zip(VERBS, bare["ran"], strict=True):
        assert ran.exit == CODES["done"], (words, ran)
    assert list((bare["plain"].hunt("desk-1") / "findings").glob("*.toml")), "the hunt confirmed nothing"


@pytest.mark.parametrize("n", range(len(VERBS)), ids=[" ".join(w) for w in VERBS])
def test_the_twins_print_the_same_bytes(twin_chains: dict[str, dict[str, Any]], n: int) -> None:
    """BK15.4: the same exit, and stdout and stderr byte for byte, but for each folder's own path and the clock."""
    wrapped, bare = twin_chains["wrapped"], twin_chains["bare"]
    one, other = wrapped["ran"][n], bare["ran"][n]
    assert one.exit == other.exit == CODES["done"], (one, other)
    assert normal(other.out, bare["plain"]) == normal(one.out, wrapped["plain"])
    assert normal(other.err, bare["plain"]) == normal(one.err, wrapped["plain"])


@pytest.mark.parametrize("n", range(len(VERBS)), ids=[" ".join(w) for w in VERBS])
def test_the_twins_write_the_same_json_documents(twin_chains: dict[str, dict[str, Any]], n: int) -> None:
    wrapped, bare = twin_chains["wrapped"], twin_chains["bare"]
    one, other = wrapped["documents"][n], bare["documents"][n]
    assert one.exit == other.exit == CODES["done"], (one, other)
    assert normal(other.out, bare["json"]) == normal(one.out, wrapped["json"])


def kept_files(proj: Project) -> dict[str, str]:
    """Every file the hunt keeps but its store, as text with the folder's path and the clock taken out."""
    root = proj.hunt("desk-1")
    return {p.relative_to(root).as_posix(): normal(p.read_text(encoding="utf-8"), proj)
            for p in sorted(root.rglob("*")) if p.is_file() and "store" not in p.relative_to(root).parts}


def test_the_twins_write_the_same_files_and_hunt_json_differs_only_in_reached_and_the_tools(
        twin_chains: dict[str, dict[str, Any]]) -> None:
    for mode in ("plain", "json"):
        wrapped, bare = kept_files(twin_chains["wrapped"][mode]), kept_files(twin_chains["bare"][mode])
        assert sorted(wrapped) == sorted(bare)
        assert any(name.startswith("findings/") for name in wrapped), sorted(wrapped)
        for name in wrapped:
            if name != "hunt.json":
                assert bare[name] == wrapped[name], name
        one, other = json.loads(wrapped["hunt.json"]), json.loads(bare["hunt.json"])
        assert one["reached"] != other["reached"]
        assert one["settings"]["tools"] != other["settings"]["tools"]
        for data in (one, other):
            del data["reached"]
            del data["settings"]["tools"]
        assert other == one


def test_hunt_json_holds_reached_equal_to_what_doctor_reported(twin_chains: dict[str, dict[str, Any]]) -> None:
    """BK15.23, and spec §12.6: the hunt's file says how each tool was reached when the hunt was made, as `doctor`
    said it; the file's `settings` hold each line's `at`."""
    bare = twin_chains["bare"]
    data = json.loads((bare["plain"].hunt("desk-1") / "hunt.json").read_text(encoding="utf-8"))
    assert reached_by_tool(data["reached"]) == reached_by_tool(json_document(bare["doctor"])["reached"])
    assert data["settings"]["tools"]["lookup_order"]["at"] == "twin_desk:lookup_order"
    assert data["schema"] == "poisson_break.hunt/1"


LATER_PLACE = "\nKEPT = [lookup_order]\n"


def test_a_hunt_opened_again_under_another_answer_adds_one_later_reached_when_its_first_run_starts(
        tmp_path: Path) -> None:
    """BK15.23: the agent gains a module-level list holding its tool, so the answer differs (one more place); a dry run
    of the next stage adds nothing; its first run adds one entry, with the new answer and the time; another run under
    the same answer adds none."""
    tools = {"lookup_order": {"class": "read", "at": "my_app.tools:lookup_order"}, "check_policy": "read"}
    proj = spec_proj(tmp_path, tools, agents=FAILING_AGENTS)
    made = cli(proj, "hunt", "--yes", PYTHONDONTWRITEBYTECODE="1")
    assert made.exit == CODES["done"], made
    hunt_file = proj.hunt("refund-agent-1") / "hunt.json"
    first = json.loads(hunt_file.read_text(encoding="utf-8"))
    assert "later_reached" not in first or first["later_reached"] == []
    agents = proj.folder / "my_app" / "agents.py"
    agents.write_text(FAILING_AGENTS + LATER_PLACE, encoding="utf-8")
    dry = cli(proj, "confirm", "--dry-run", PYTHONDONTWRITEBYTECODE="1")
    assert dry.exit == CODES["done"], dry
    unrun = json.loads(hunt_file.read_text(encoding="utf-8"))
    assert unrun.get("later_reached", []) == []
    assert unrun["reached"] == first["reached"]
    ran = cli(proj, "confirm", "--yes", PYTHONDONTWRITEBYTECODE="1")
    assert ran.exit == CODES["done"], ran
    after = json.loads(hunt_file.read_text(encoding="utf-8"))
    assert after["reached"] == first["reached"], "what the hunt was made with stays as it was"
    assert len(after["later_reached"]) == 1, after["later_reached"]
    entry = after["later_reached"][0]
    text = json.dumps(entry)
    assert "my_app.agents:KEPT[0]" in text, entry
    assert TIME.search(text), entry
    again = cli(proj, "recheck", "--yes", PYTHONDONTWRITEBYTECODE="1")
    assert again.exit == CODES["done"], again
    assert len(json.loads(hunt_file.read_text(encoding="utf-8"))["later_reached"]) == 1


# ---------------------------------------------------------------------------
# BK15.24: the copy holds
# ---------------------------------------------------------------------------


def test_nothing_this_module_prints_holds_a_word_break_may_not_say(
        doctor_mixed: dict[str, Any], doctor_holders: dict[str, Any], way_runs: dict[str, dict[str, Any]],
        init_found: dict[str, Any], twin_chains: dict[str, dict[str, Any]]) -> None:
    """Plan BK11.3's patterns (`tests/test_release_words.py`), over everything the commands printed here: `doctor`'s
    rows and notes, `init`'s lines and questions, and every refusal of §12.7 from `doctor` and `hunt`."""
    from tests.test_release_words import hits

    printed = [doctor_mixed["plain"], doctor_mixed["pretty"], doctor_holders["plain"], init_found["ran"],
               twin_chains["bare"]["init"]]
    assert reached_block(doctor_mixed["plain"]) and reached_block(doctor_holders["plain"]), "nothing new was printed"
    for said in way_runs.values():
        printed += [said["doctor"], said["hunt"]]
    text = "\n".join(strip(ran.out + "\n" + ran.err) for ran in printed)
    text += "\n" + "\n".join(a.text for a in init_found["asked"])
    assert hits(text) == []
