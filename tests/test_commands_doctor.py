"""`doctor`: the settings checked, the target loaded and its tools listed, from the command.

Invariants held here (Break — Plan, the commands module; spec §9.1):
- BK8.6   `doctor` exits 4 on the first settings or target problem, among them what BK5.17 refuses and a strategy
          `load_strategy` cannot find, with one line and a `next:`.
- BK8.9   "Break calls your tools for real" is in `doctor`'s output.
- §9.1    `doctor`'s verdicts are `ready` and `not ready`; it lists the target's tools.

Taylor's rulings on BK8's open points (2026-11-07), held here: `doctor --run` asks `[y/N]` (`--yes` answers), runs
the first case once with no change, stores nothing, and adds its outcome as a detail line; `doctor` alone runs nothing
and asks nothing (point 23, and point 26 (a)); the run is `poisson_break.hunt.run_once`'s (point 39); the schema
`poisson_break.doctor-result/1` (point 11).
"""

from __future__ import annotations

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
    project,
    result_of,
    verdict,
)
from tests.commands_spies import RUN_ONCE, spied, spying
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


@pytest.mark.parametrize("kind", ["langgraph", "openai-agents", "mcp"])
def test_a_kind_whose_way_in_is_not_installed_is_not_ready_naming_the_extra(tmp_path: Path, kind: str) -> None:
    """BK4.7: the refusal names the extra to install."""
    extra = {"langgraph": "langgraph", "openai-agents": "openai-agents", "mcp": "mcp"}[kind]
    text = not_ready(cli(_kind(tmp_path, kind), "doctor"))
    assert extra in text, text


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
