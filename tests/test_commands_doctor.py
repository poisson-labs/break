"""`doctor`: the settings checked, the target loaded and its tools listed, from the command.

Invariants held here (Break — Plan, the commands module; spec §9.1):
- BK8.6   `doctor` exits 4 on the first settings or target problem, among them what BK5.17 refuses and a strategy
          `load_strategy` cannot find, with one line and a `next:`.
- BK8.9   "Break calls your tools for real" is in `doctor`'s output.
- §9.1    `doctor`'s verdicts are `ready` and `not ready`; it lists the target's tools.

Taylor's rulings on BK8's open points (2026-11-07), held here: `doctor --run` asks `[y/N]` (`--yes` answers), runs
the first case once with no change, stores nothing, and adds its outcome as a detail line; `doctor` alone runs nothing
and asks nothing (point 23, and point 26 (a)); the run is `poisson_break.hunt.run_once`'s (point 39); the schema
`poisson_break.doctor-result/1` (point 11). A tool nobody classed, met in that run, is `not ready`, exit 4, in one line
naming the tool, with a `next:` that is an `init` command whose `--tool` line classes it (point 42). That `next:`, run
as printed in the project, writes a `break.toml` that reads back as the settings it was printed from with that one
tool added, classed `off`, and nothing else changed (point 44, Taylor's yes, 2026-11-08).

The `next:` carries `--yes` and `--force` and runs exactly as printed: with no terminal, and with `break.toml` already
there (point 45, Taylor's yes, 2026-11-08). When a case has turns it states the conversation's setting, even when
empty, so that `--yes`, whose conversation default is yes (point 43), changes nothing else (point 46, Taylor's yes,
2026-11-08): held with no move set and with one.
"""

from __future__ import annotations

import dataclasses
import shlex
from pathlib import Path
from typing import Any

import pytest

from tests.commands_support import (
    CODES,
    PROG,
    REAL,
    cases,
    cli,
    detail,
    errors,
    files_under,
    paths_under,
    json_document,
    nexts,
    on,
    prepared,
    project,
    refused_once,
    result_of,
    settings_text,
    verdict,
)
from tests.commands_lines import classing_nexts, states_the_conversation, the_next_writes_the_tool_in_as_off
from tests.commands_spies import CAPABILITIES_TAKEN, RUN_ONCE, RUN_ONCE_REFUSED, spied, spying
from tests.look_support import Streams, strip


def not_ready(ran: Any) -> str:
    """A doctor's `not ready`: exit 4, the verdict line first on stdout, a `next:` command, and no traceback. Hands back
    everything printed, as one text, for the facts it must carry."""
    assert ran.exit == CODES["check"], ran
    assert verdict(ran)[0] == "not ready", ran
    assert nexts(ran), ran
    assert all(shlex.split(c)[0] == PROG for c in nexts(ran)), ran
    assert "Traceback" not in ran.err
    return strip(ran.out + ran.err)


def test_a_project_that_is_ready_says_ready_lists_its_tools_and_exits_0(tmp_path: Path) -> None:
    proj = project(tmp_path)
    ran = cli(proj, "doctor")
    assert ran.exit == CODES["done"], ran
    assert verdict(ran)[0] == "ready"
    text = strip(ran.out)
    assert "lookup_order" in text and "check_policy" in text


def test_ready_says_break_calls_your_tools_for_real(tmp_path: Path) -> None:
    ran = cli(project(tmp_path), "doctor")
    assert REAL in strip(ran.out + ran.err)


def test_doctor_asked_for_nothing_more_runs_nothing_and_asks_nothing(tmp_path: Path) -> None:
    """Point 23: with stdin not a terminal and no `--yes`, `doctor` alone is ready: it asked nothing, and ran nothing."""
    proj = project(tmp_path)
    before = files_under(proj.folder)
    ran = cli(proj, "doctor", PYTHONDONTWRITEBYTECODE="1")
    assert ran.exit == CODES["done"] and verdict(ran)[0] == "ready", ran
    assert proj.runs() == []
    assert not proj.hunts.exists()
    assert files_under(proj.folder) == before
    assert errors(ran) == [] and "[y/N]" not in ran.err


def test_doctor_under_json_is_one_strict_document_with_the_same_exit_code(tmp_path: Path) -> None:
    ran = cli(project(tmp_path), "doctor", "--json")
    assert ran.exit == CODES["done"], ran
    document = json_document(ran)
    assert list(document)[:3] == ["schema", "verdict", "sentence"]
    assert document["verdict"] == "ready"
    assert document["schema"] == "poisson_break.doctor-result/1"


def test_a_problem_under_json_is_one_document_and_still_exits_4(tmp_path: Path) -> None:
    proj = project(tmp_path, search={"strategy": "tests.nowhere_at_all:Strategy"})
    ran = cli(proj, "doctor", "--json")
    assert ran.exit == CODES["check"], ran
    assert json_document(ran)["verdict"] == "not ready"


# ---------------------------------------------------------------------------
# each problem: not ready, exit 4, one line naming it, and a next command
# ---------------------------------------------------------------------------


def test_no_settings_file_is_not_ready(tmp_path: Path) -> None:
    not_ready(cli(project(tmp_path, write=False), "doctor"))


def test_an_unknown_key_is_not_ready_naming_the_key_and_the_nearest_known_one(tmp_path: Path) -> None:
    proj = project(tmp_path)
    proj.settings.write_text(proj.settings.read_text().replace('"runs" = 60', '"rnus" = 60'), encoding="utf-8")
    text = not_ready(cli(proj, "doctor"))
    assert "search.rnus" in text and "search.runs" in text, text


def test_a_bad_value_is_not_ready_naming_its_key(tmp_path: Path) -> None:
    text = not_ready(cli(project(tmp_path, confirm={"q": 1.5}), "doctor"))
    assert "confirm.q" in text, text


def test_a_case_file_that_is_not_there_is_not_ready(tmp_path: Path) -> None:
    proj = project(tmp_path)
    (proj.folder / "cases.jsonl").unlink()
    not_ready(cli(proj, "doctor"))


def test_a_target_that_cannot_be_imported_is_not_ready_naming_it(tmp_path: Path) -> None:
    text = not_ready(cli(project(tmp_path, entry="tests.nowhere_at_all:desk"), "doctor"))
    assert "tests.nowhere_at_all:desk" in text, text


def test_a_change_the_way_in_cannot_make_is_not_ready_naming_the_change(tmp_path: Path) -> None:
    """BK5.17, BK8.6: `[vary] conversation = ["repeats"]` on the `rollout` kind, asked as `user:repeats@1`."""
    text = not_ready(cli(project(tmp_path, vary={"conversation": ["repeats"]}), "doctor"))
    assert "user:repeats@1" in text, text


def test_a_model_fault_the_way_in_cannot_make_is_not_ready_naming_the_change(tmp_path: Path) -> None:
    text = not_ready(cli(project(tmp_path, vary={"model": ["error"]}), "doctor"))
    assert "model:error#1" in text, text


def test_a_strategy_that_cannot_be_found_is_not_ready(tmp_path: Path) -> None:
    """BK6.11, BK8.6."""
    text = not_ready(cli(project(tmp_path, search={"strategy": "tests.nowhere_at_all:Strategy"}), "doctor"))
    assert "tests.nowhere_at_all" in text, text


def test_the_adaptive_strategy_is_not_ready(tmp_path: Path) -> None:
    """BK4.7: `adaptive` parses and is refused when loaded, as not in this version."""
    not_ready(cli(project(tmp_path, search={"strategy": "adaptive"}), "doctor"))


@pytest.mark.parametrize("verb", ["doctor", "hunt", "confirm", "recheck"])
@pytest.mark.parametrize("kind", ["openai-agents", "langgraph", "crewai", "mcp", "command"])
def test_a_kind_this_version_has_no_way_in_for_is_refused_saying_only_rollout(tmp_path: Path, kind: str,
                                                                              verb: str) -> None:
    """Taylor's yes on hands-on issue 17 (2026-11-13): `kind` in `break.toml` naming any kind but rollout is refused
    before anything runs, in one line saying this version has only the rollout way in, and with no `pip install` line
    for an extra that does not exist."""
    proj = _kind(tmp_path, kind)
    ran = cli(proj, verb, "--yes") if verb != "doctor" else cli(proj, verb)
    if verb == "doctor":
        not_ready(ran)
        problem = verdict(ran)[1]
    else:
        problem = refused_once(ran, CODES["refused"])
    assert "only the rollout way in" in problem and kind in problem and 'kind = "rollout"' in problem, problem
    assert "pip" not in ran.out + ran.err, ran
    assert proj.runs() == []


def _kind(tmp_path: Path, kind: str) -> Any:
    proj = project(tmp_path)
    proj.settings.write_text(proj.settings.read_text().replace('"kind" = "rollout"', f'"kind" = "{kind}"'),
                             encoding="utf-8")
    return proj


def test_the_first_problem_is_the_one_reported(tmp_path: Path) -> None:
    """A settings problem and a target problem at once: the settings are read first, so the unknown key is the problem
    reported, and the target, which cannot be imported, is not named."""
    proj = project(tmp_path, entry="tests.nowhere_at_all:desk")
    proj.settings.write_text(proj.settings.read_text().replace('"runs" = 60', '"rnus" = 60'), encoding="utf-8")
    text = not_ready(cli(proj, "doctor"))
    assert "search.rnus" in text
    assert "nowhere_at_all" not in text


def test_not_ready_is_one_problem_line(tmp_path: Path) -> None:
    """"With one line and a `next:`": the problem is the verdict's sentence, with no detail under it and no second
    telling of it on stderr."""
    ran = cli(project(tmp_path, search={"strategy": "tests.nowhere_at_all:Strategy"}), "doctor")
    not_ready(ran)
    assert detail(result_of(ran, "not ready")) == [], ran
    assert not [line for line in strip(ran.err).splitlines() if line.startswith("error: ")], ran


# ---------------------------------------------------------------------------
# point 23: doctor --run
# ---------------------------------------------------------------------------


def outcome_lines(ran: Any) -> list[str]:
    return detail(result_of(ran, "ready"))


@pytest.mark.parametrize(("rate", "outcome"), [(0.0, "ok"), (1.0, "failed")])
def test_doctor_run_yes_runs_the_first_case_once_and_shows_its_outcome(tmp_path: Path, rate: float,
                                                                       outcome: str) -> None:
    """The first case of three runs once: `k1`, whose runs all fail or none do. Its outcome is a detail line."""
    proj = project(tmp_path, [*cases(1, rate=rate), *cases(2, first=2, rate=1.0 - rate)])
    ran = cli(proj, "doctor", "--run", "--yes")
    assert ran.exit == CODES["done"], ran
    assert verdict(ran)[0] == "ready"
    assert [r["case"] for r in proj.runs()] == ["k1"]
    other = {"ok": "failed", "failed": "ok"}[outcome]
    words = [w for line in outcome_lines(ran) for w in line.split()]
    assert outcome in words and other not in words, outcome_lines(ran)


def test_doctor_run_makes_no_change(tmp_path: Path) -> None:
    """`k1` fails every run under `error` and no other: run with no change, it does not fail."""
    proj = project(tmp_path, cases(3, weak_to=["error"]))
    ran = cli(proj, "doctor", "--run", "--yes")
    assert ran.exit == CODES["done"], ran
    words = [w for line in outcome_lines(ran) for w in line.split()]
    assert "ok" in words and "failed" not in words, outcome_lines(ran)


def test_doctor_run_stores_nothing(tmp_path: Path) -> None:
    proj = project(tmp_path)
    before, paths = files_under(proj.folder), paths_under(proj.folder)
    ran = cli(proj, "doctor", "--run", "--yes", PYTHONDONTWRITEBYTECODE="1")
    assert ran.exit == CODES["done"] and len(proj.runs()) == 1, ran
    assert files_under(proj.folder) == before
    assert paths_under(proj.folder) == paths
    assert not proj.hunts.exists()


def test_doctor_run_is_hunt_run_once_s_one_run(tmp_path: Path) -> None:
    """Point 39: with `hunt.run_once` stood in for, the case is never run, `run_once` is asked once, for the first case
    as the case file holds it, and the outcome and kind shown are the ones it handed back."""
    proj = project(tmp_path / "proj", cases(3, rate=0.0))
    env = spying(proj, tmp_path / "spy", RUN_ONCE)
    ran = cli(proj, "doctor", "--run", "--yes", **env)
    assert ran.exit == CODES["done"], ran
    assert verdict(ran)[0] == "ready"
    assert proj.runs() == []
    calls = spied(env)
    assert [c["name"] for c in calls] == ["run_once"], calls
    assert calls[0]["case"] == cases(3, rate=0.0)[0]
    words = [w.strip("():,") for line in outcome_lines(ran) for w in line.split()]
    assert "failed" in words and "spied_kind" in words and "ok" not in words, outcome_lines(ran)


def test_doctor_alone_does_not_ask_run_once(tmp_path: Path) -> None:
    proj = project(tmp_path / "proj")
    env = spying(proj, tmp_path / "spy", RUN_ONCE)
    ran = cli(proj, "doctor", **env)
    assert ran.exit == CODES["done"], ran
    assert spied(env) == []


def test_doctor_run_asks_first_and_yes_runs(tmp_path: Path) -> None:
    proj = project(tmp_path)
    ran = cli(proj, "doctor", "--run", streams=Streams(stdin="pty", keys=(b"y\r",)))
    assert ran.exit == CODES["done"], ran
    assert "[y/N]" in strip(ran.err)
    assert len(proj.runs()) == 1


def test_doctor_run_answered_no_runs_nothing(tmp_path: Path) -> None:
    proj = project(tmp_path)
    ran = cli(proj, "doctor", "--run", streams=Streams(stdin="pty", keys=(b"n\r",)))
    assert "[y/N]" in strip(ran.err)
    assert proj.runs() == []
    assert "Traceback" not in ran.err


def test_doctor_run_without_a_terminal_and_without_yes_is_refused_and_runs_nothing(tmp_path: Path) -> None:
    proj = project(tmp_path)
    ran = cli(proj, "doctor", "--run")
    assert ran.exit == CODES["refused"], ran
    assert len(errors(ran)) == 1 and "--yes" in errors(ran)[0], ran
    assert proj.runs() == []


# ---------------------------------------------------------------------------
# point 42: a tool nobody classed, met by doctor --run
# ---------------------------------------------------------------------------


def test_doctor_run_meeting_a_tool_nobody_classed_is_not_ready_naming_it(tmp_path: Path) -> None:
    """Point 42: `check_policy` has no line in `[tools]`, and the desk calls it on every run. `doctor --run` meets the
    tool, says `not ready` in one line naming it, exits 4, stores nothing, and its `next:` is the `init` command that
    classes the tool: run, it writes the settings back with `check_policy` added as `off` (point 44)."""
    proj = project(tmp_path, tools={"lookup_order": "read"})
    before, paths = files_under(proj.folder), paths_under(proj.folder)
    ran = cli(proj, "doctor", "--run", "--yes", PYTHONDONTWRITEBYTECODE="1")
    not_ready(ran)
    assert "check_policy" in verdict(ran)[1], ran
    assert detail(result_of(ran, "not ready")) == [], ran
    assert not [line for line in strip(ran.err).splitlines() if line.startswith("error: ")], ran
    (command,) = classing_nexts(ran, "check_policy")
    assert files_under(proj.folder) == before
    assert paths_under(proj.folder) == paths
    assert not proj.hunts.exists()
    the_next_writes_the_tool_in_as_off(proj, command, "check_policy")


def test_a_tool_nobody_classed_under_json_is_one_document_and_still_exits_4(tmp_path: Path) -> None:
    """The same under `--json`: the document's `next` holds the one `init` command, and run it writes the same."""
    proj = project(tmp_path, tools={"lookup_order": "read"})
    ran = cli(proj, "doctor", "--run", "--yes", "--json")
    assert ran.exit == CODES["check"], ran
    document = json_document(ran)
    assert (document["schema"], document["verdict"]) == ("poisson_break.doctor-result/1", "not ready")
    assert "check_policy" in document["sentence"], document
    (command,) = classing_nexts(ran, "check_policy", list(document["next"]))
    the_next_writes_the_tool_in_as_off(proj, command, "check_policy")


def test_doctor_run_reports_the_tool_run_once_refuses(tmp_path: Path) -> None:
    """Point 42 through `hunt.run_once`: stood in for so that it refuses `spied_tool`, which no settings file names,
    without running the case. `doctor --run` is `not ready`, exit 4, naming that tool, and classes it `off` in its `next:`, every other
    setting kept."""
    proj = project(tmp_path / "proj")
    env = spying(proj, tmp_path / "spy", RUN_ONCE_REFUSED)
    ran = cli(proj, "doctor", "--run", "--yes", **env)
    not_ready(ran)
    assert "spied_tool" in verdict(ran)[1], ran
    (command,) = classing_nexts(ran, "spied_tool")
    assert [c["name"] for c in spied(env)] == ["run_once"]
    assert proj.runs() == []
    the_next_writes_the_tool_in_as_off(proj, command, "spied_tool")


# ---------------------------------------------------------------------------
# point 46: the `next:` in a project whose cases have turns
# ---------------------------------------------------------------------------


def test_with_turns_and_no_move_the_next_states_the_conversation_and_keeps_it_off(tmp_path: Path) -> None:
    """Point 46: the cases are conversations and `[vary] conversation` is empty, the default. The `next:` says so, and
    run as printed under its `--yes` (whose conversation default is yes) the conversation stays off."""
    turns = [{**c, "turns": [c["input"], "And the refund?"]} for c in cases(3)]
    proj = project(tmp_path, turns, tools={"lookup_order": "read"})
    ran = cli(proj, "doctor", "--run", "--yes")
    not_ready(ran)
    (command,) = classing_nexts(ran, "check_policy")
    assert states_the_conversation(command), command
    the_next_writes_the_tool_in_as_off(proj, command, "check_policy")


def test_with_turns_and_moves_set_the_next_keeps_those_moves(tmp_path: Path) -> None:
    """Point 46 with moves set: `[vary] conversation = ["interrupts", "repeats"]`. `doctor` is let past the check of
    those moves on a `rollout` target (a stand-in takes every change) and `run_once` refuses `spied_tool` (a stand-in).
    The `next:` states the two moves, and run as printed, outside the stand-ins, keeps them, in their order."""
    turns = [{**c, "turns": [c["input"], "And the refund?"]} for c in cases(3)]
    proj = project(tmp_path / "proj", turns, vary={"conversation": ["interrupts", "repeats"]})
    env = spying(proj, tmp_path / "spy", CAPABILITIES_TAKEN + RUN_ONCE_REFUSED)
    ran = cli(proj, "doctor", "--run", "--yes", **env)
    not_ready(ran)
    (command,) = classing_nexts(ran, "spied_tool")
    assert states_the_conversation(command), command
    the_next_writes_the_tool_in_as_off(proj, command, "spied_tool")


# ---------------------------------------------------------------------------
# a [vary] line the way in cannot do: named, with what to do, wherever it is met
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verb", ["doctor", "hunt", "confirm", "recheck"])
@pytest.mark.parametrize(("key", "value", "change"), [
    ("model", ["error", "timeout"], "model:error#1"),
    ("conversation", ["repeats"], "user:repeats@1"),
])
def test_a_vary_line_the_way_in_cannot_do_is_named_with_what_to_do(tmp_path: Path, verb: str, key: str,
                                                                    value: list[str], change: str) -> None:
    """docs/cli-look.md rule 4: the problem names the line of `break.toml` to change, `[vary] model` or
    `[vary] conversation`, and says what to write there; its `next:` is a command that mends it, not `doctor` again.
    That command, run as printed, writes a `break.toml` that reads as the settings that were there with that line
    emptied, and `doctor` is then ready. `hunt`, `confirm` and `recheck` meet it as they open the hunt."""
    from poisson_break.settings import loads

    proj = project(tmp_path)
    if verb in ("confirm", "recheck"):
        prepared(proj, [on("error")])
    proj.write(settings_text(vary={key: value}))
    ran = cli(proj, verb, "--yes") if verb != "doctor" else cli(proj, verb)
    if verb == "doctor":
        text = not_ready(ran)
        problem = verdict(ran)[1]
    else:
        problem = refused_once(ran, CODES["refused"])
        text = strip(ran.out + ran.err)
    assert f"[vary] {key}" in problem and "break.toml" in problem, text
    assert f"{key} = []" in problem, text
    assert change in problem, text
    assert "rollout" in problem, text
    mends = [command for command in nexts(ran) if shlex.split(command)[:2] == [PROG, "init"]]
    assert len(mends) == 1 and nexts(ran) == mends, text
    wanted = loads(proj.settings.read_text(encoding="utf-8"))
    again = cli(proj, *shlex.split(mends[0])[1:])
    assert again.exit == CODES["done"], again
    written = loads(proj.settings.read_text(encoding="utf-8"))
    assert getattr(written.vary, key) == ()
    assert written == dataclasses.replace(wanted, vary=dataclasses.replace(wanted.vary, **{key: ()}))
    ready = cli(proj, "doctor")
    assert ready.exit == CODES["done"] and verdict(ready)[0] == "ready", ready
