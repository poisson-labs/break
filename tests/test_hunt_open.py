"""Opening a hunt: its folder and names, what is refused before any run, and that opening runs nothing.

Plan BK5.2 (hunt names), BK5.13 (nothing is spent before the plan is accepted; a control that does not fit stops the hunt
before any run), BK5.17 (what a way in cannot do), BK5.18 (a check that cannot be loaded), with the shapes of rulings 1,
8, 9, 12 to 16 and 29 to 31 of 2026-11-05 (`evidence/bk5/open-points.md`, all ruled yes).

No refusal test reads a message's words. Each holds that the refusal happened, its kind, the facts it carries, and that
nothing was made and nothing ran.
"""

from __future__ import annotations

import datetime
import shutil
import tomllib
from pathlib import Path
from typing import Any

import pytest

from tests.hunt_support import (
    apply_module,
    arms,
    case,
    changes,
    condition,
    desk,
    hunt,
    hunt_json,
    interfaces,
    open_new,
    rollout,
    settings_for,
    settings_module,
    some_cases,
    targets,
)


@pytest.fixture(autouse=True)
def _fresh() -> None:
    targets().reset()


def root(tmp_path: Path) -> Path:
    return tmp_path / "break-runs"


def hunts_in(folder: Path) -> list[str]:
    """Every folder under the output folder, by name: what a refusal must leave empty."""
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


def one_line(wrong: BaseException) -> bool:
    text = str(wrong)
    return bool(text.strip()) and "\n" not in text


# ---------------------------------------------------------------------------
# what a hunt is (ruling 1)
# ---------------------------------------------------------------------------


def test_a_new_hunt_has_its_folder_its_file_and_its_paths(tmp_path: Path) -> None:
    """Ruling 1, spec §6.1: `<output folder>/<name>`, with `hunt.json` written, the Prove store at `store` and the
    proposals file at `proposals.jsonl`."""
    h = open_new(root(tmp_path), name="refund-agent-1")
    assert h.name == "refund-agent-1"
    assert h.folder == root(tmp_path) / "refund-agent-1"
    assert h.folder.is_dir() and (h.folder / "hunt.json").is_file()
    assert h.store == h.folder / "store"
    assert h.proposals == h.folder / "proposals.jsonl"
    assert all(isinstance(p, Path) for p in (h.folder, h.store, h.proposals))


def test_a_hunt_holds_what_it_was_opened_with_and_its_plan(tmp_path: Path) -> None:
    """Ruling 1. The plan is `plan_hunt`'s for these cases (BK5.13: "the run counts are `plan_hunt`'s")."""
    settings = settings_for(root(tmp_path), search={"control_repeats": 3, "runs": 50})
    target, cases = desk(), some_cases(4)
    h = hunt().open_hunt(settings, target=target, cases=cases, name="held")
    assert h.settings == settings
    assert h.target is target
    assert h.cases == cases and isinstance(h.cases, tuple)
    assert h.plan == settings_module().plan_hunt(settings, cases=4)
    assert (h.plan.control_runs, h.plan.search_runs, h.plan.runs) == (12, 38, 50)


@pytest.mark.parametrize("field", ["name", "folder", "store", "proposals", "settings", "cases", "target", "plan"])
def test_a_hunt_is_read_only(tmp_path: Path, field: str) -> None:
    h = open_new(root(tmp_path))
    before = getattr(h, field)
    with pytest.raises(Exception):  # noqa: B017 - which exception a frozen object raises is the build's
        setattr(h, field, "something else")
    assert getattr(h, field) is before


def test_the_target_and_the_cases_are_given_by_keyword(tmp_path: Path) -> None:
    """§11's shared rule: keyword-only, so a parameter can be added without breaking a caller."""
    settings = settings_for(root(tmp_path))
    with pytest.raises(TypeError):
        hunt().open_hunt(settings, desk(), some_cases())
    assert hunts_in(root(tmp_path)) == []


def test_a_relative_folder_is_taken_from_the_current_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ruling 1, spec §9.4's default `folder = "break-runs"`."""
    monkeypatch.chdir(tmp_path)
    h = open_new("break-runs", name="here")
    assert h.folder.resolve() == (tmp_path / "break-runs" / "here").resolve()
    assert (tmp_path / "break-runs" / "here" / "hunt.json").is_file()


def test_a_way_in_from_outside_opens_a_hunt_whatever_kind_the_settings_name(tmp_path: Path) -> None:
    """Ruling 1, BK5.15. The settings file refuses a `kind` it does not offer, so a way in written outside the package
    can only arrive as an object, and it is not compared with `settings.target.kind`."""
    target = desk()
    assert target.kind == "desk"
    h = open_new(root(tmp_path), target=target, kind="rollout")
    assert h.target is target


# ---------------------------------------------------------------------------
# BK5.13: opening runs nothing
# ---------------------------------------------------------------------------


def test_opening_a_hunt_runs_nothing_through_a_way_in(tmp_path: Path) -> None:
    """BK5.13: nothing is spent before the plan is shown and accepted. A plan can only be shown once the hunt is open,
    so opening one makes no run, calls no tool and stores nothing."""
    target = desk()
    h = open_new(root(tmp_path), target=target)
    assert target.runs == 0
    assert targets().EXECUTED == []
    assert arms(h) == []
    assert not h.proposals.exists()


def test_opening_a_hunt_runs_nothing_of_a_plain_prove_target(tmp_path: Path) -> None:
    """The same for the `rollout` kind: loading the target and opening the hunt never call it."""
    settings = settings_for(root(tmp_path))
    h = hunt().open_hunt(settings, target=rollout(settings), cases=some_cases(), name=None)
    assert targets().ROLLOUTS == [] and targets().EXECUTED == []
    assert arms(h) == []


def test_a_control_that_does_not_fit_is_refused_before_any_run(tmp_path: Path) -> None:
    """BK5.13 and BK4.9: `plan_hunt`'s refusal stops the hunt before any run. 3 cases at 2 repeats is 6, and one
    condition on 2 cases makes 8 the smallest `runs`. The refusal is `plan_hunt`'s own, with its key (ruling 8)."""
    target = desk()
    with pytest.raises(settings_module().SettingsError) as refused:
        open_new(root(tmp_path), target=target, search={"runs": 7})
    assert refused.value.key == "search.runs"
    assert not isinstance(refused.value, hunt().HuntError)
    assert hunts_in(root(tmp_path)) == [] and target.runs == 0
    assert open_new(root(tmp_path), target=target, search={"runs": 8}).plan.search_runs == 2


# ---------------------------------------------------------------------------
# BK5.2: a numbered name (ruling 13)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("entry", "name"), [
    ("my_app.agents:refund_agent", "refund-agent-1"),
    ("tests.hunt_targets:bare_agent", "bare-agent-1"),
    ("my_app.agents:RefundAgent", "refundagent-1"),
    ("my_app.agents:refund__agent_v2", "refund-agent-v2-1"),
    ("my_app.agents:_private_agent_", "private-agent-1"),
    ("pkg.module.run", "run-1"),
    ("agent", "agent-1"),
    ("my_app.agents:___", "hunt-1"),
])
def test_a_hunt_with_no_name_is_numbered_from_the_targets_name(tmp_path: Path, entry: str, name: str) -> None:
    """BK5.2, ruling 13: the part of the entry after its last `:` or `.`, lower-cased, each run of anything but ASCII
    letters and digits one dash; nothing left reads `hunt`. Spec §9.1's example is `refund-agent-1`."""
    assert open_new(root(tmp_path), name=None, entry=entry).name == name


def test_each_new_hunt_takes_the_next_number(tmp_path: Path) -> None:
    """BK5.2: "a name is never reused"."""
    names = [open_new(root(tmp_path), name=None).name for _ in range(3)]
    assert names == ["refund-agent-1", "refund-agent-2", "refund-agent-3"]
    assert hunts_in(root(tmp_path)) == names


def test_a_deleted_hunts_number_is_not_handed_out_while_a_higher_one_stands(tmp_path: Path) -> None:
    """Ruling 13: one more than the highest number there, not the first free one."""
    for _ in range(3):
        open_new(root(tmp_path), name=None)
    shutil.rmtree(root(tmp_path) / "refund-agent-2")
    assert open_new(root(tmp_path), name=None).name == "refund-agent-4"


def test_a_number_counts_only_this_targets_numbered_hunts(tmp_path: Path) -> None:
    """Ruling 13: `<name>-<n>` folders of this target's name. Another target's hunts, a hunt with a name of its own and
    a name that only starts the same way do not move the number; a hunt someone named `refund-agent-10` does."""
    open_new(root(tmp_path), name=None, entry="my_app.agents:other_agent")
    open_new(root(tmp_path), name=None, entry="my_app.agents:other_agent")
    open_new(root(tmp_path), name="nightly")
    open_new(root(tmp_path), name="refund-agent-x")
    open_new(root(tmp_path), name="refund-agent-7-rerun")
    assert open_new(root(tmp_path), name=None).name == "refund-agent-1"
    open_new(root(tmp_path), name="refund-agent-10")
    assert open_new(root(tmp_path), name=None).name == "refund-agent-11"


# ---------------------------------------------------------------------------
# BK5.2: a given name (ruling 14)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["nightly", "run_2026.11.05", "A-b_c.d", "7days", "x", "n" * 64])
def test_a_safe_name_is_used_as_given(tmp_path: Path, name: str) -> None:
    """BK5.2: "`--name` is used as given if it is a safe folder name"."""
    h = open_new(root(tmp_path), name=name)
    assert h.name == name and h.folder.name == name
    assert hunts_in(root(tmp_path)) == [name]


@pytest.mark.parametrize("name", ["", "has space", "a/b", "a\\b", "..", ".", ".hidden", "-lead", "_lead", "ünï",
                                  "n" * 65, "line\nbreak", "tab\tbed", "semi;colon", "star*"])
def test_an_unsafe_name_is_refused_and_not_swapped_for_a_number(tmp_path: Path, name: str) -> None:
    """Ruling 14: ASCII letters, digits, `.`, `_` and `-`, starting with a letter or a digit, at most 64 characters.
    Anything else is refused in one line, and no hunt is made under some other name."""
    target = desk()
    with pytest.raises(hunt().HuntError) as refused:
        open_new(root(tmp_path), target=target, name=name)
    assert one_line(refused.value)
    assert hunts_in(root(tmp_path)) == [] and target.runs == 0


def test_a_name_already_taken_is_refused_and_the_first_hunt_is_left_as_it_was(tmp_path: Path) -> None:
    """BK5.2: "a name is never reused". Ruling 14: refused, not numbered instead."""
    first = open_new(root(tmp_path), name="nightly")
    before = (first.folder / "hunt.json").read_bytes()
    with pytest.raises(hunt().HuntError) as refused:
        open_new(root(tmp_path), name="nightly")
    assert one_line(refused.value)
    assert hunts_in(root(tmp_path)) == ["nightly"]
    assert (first.folder / "hunt.json").read_bytes() == before


def test_a_given_name_that_a_numbered_hunt_already_has_is_refused(tmp_path: Path) -> None:
    open_new(root(tmp_path), name=None)
    with pytest.raises(hunt().HuntError):
        open_new(root(tmp_path), name="refund-agent-1")
    assert hunts_in(root(tmp_path)) == ["refund-agent-1"]


def test_the_two_refusals_of_the_module_are_classes_of_their_own() -> None:
    """Rulings 7 and 8: `HuntError` is a `ValueError`, for what is refused before any run; `HuntStopped` is a stop
    after work started, and neither is the other, so a caller that catches one never swallows the other."""
    h = hunt()
    assert issubclass(h.HuntError, ValueError)
    assert issubclass(h.HuntStopped, Exception)
    assert not issubclass(h.HuntStopped, h.HuntError) and not issubclass(h.HuntError, h.HuntStopped)
    assert not issubclass(h.HuntStopped, ValueError)


# ---------------------------------------------------------------------------
# `latest_hunt` (ruling 12)
# ---------------------------------------------------------------------------


def test_with_no_hunt_made_there_is_no_latest(tmp_path: Path) -> None:
    settings = settings_for(root(tmp_path))
    assert hunt().latest_hunt(settings) is None
    root(tmp_path).mkdir()
    (root(tmp_path) / "not-a-hunt").mkdir()
    assert hunt().latest_hunt(settings) is None


def test_the_latest_hunt_is_the_one_made_last_whatever_its_name(tmp_path: Path) -> None:
    """Ruling 12: by when it was made, so neither the alphabet nor a number decides."""
    settings = settings_for(root(tmp_path))
    for name in ("zeta", "alpha", "middle"):
        open_new(root(tmp_path), name=name)
        assert hunt().latest_hunt(settings) == name
    numbered = open_new(root(tmp_path), name=None)
    assert hunt().latest_hunt(settings) == numbered.name == "refund-agent-1"
    open_new(root(tmp_path), name="a-last-one")
    assert hunt().latest_hunt(settings) == "a-last-one"


def test_working_on_an_older_hunt_does_not_make_it_the_latest(tmp_path: Path) -> None:
    """Ruling 12: the hunt made last, not the one touched last."""
    settings = settings_for(root(tmp_path))
    older = open_new(root(tmp_path), name="older")
    open_new(root(tmp_path), name="newer")
    hunt().run_arm(older, "control", ["c1", "c2"], condition(""), repeats=1)
    again = hunt().open_hunt(settings, target=desk(), cases=some_cases(), name="older", existing=True)
    hunt().run_arm(again, "confirm-control", ["c1"], condition(""), repeats=1)
    assert hunt().latest_hunt(settings) == "newer"


def test_the_latest_hunt_is_looked_for_in_the_settings_own_folder(tmp_path: Path) -> None:
    open_new(tmp_path / "elsewhere", name="over-there")
    assert hunt().latest_hunt(settings_for(root(tmp_path))) is None
    assert hunt().latest_hunt(settings_for(tmp_path / "elsewhere")) == "over-there"


# ---------------------------------------------------------------------------
# opening a hunt that is there (ruling 15)
# ---------------------------------------------------------------------------


def reopen(tmp_path: Path, name: str | None = "kept", *, target: Any = None, cases: Any = None, **over: Any) -> Any:
    return hunt().open_hunt(settings_for(root(tmp_path), **over), target=desk() if target is None else target,
                            cases=some_cases() if cases is None else cases, name=name, existing=True)


def test_a_hunt_that_is_there_is_opened_as_it_was_made(tmp_path: Path) -> None:
    """Ruling 15. The same name and folder, the file as it was written, and nothing run by the opening."""
    first = open_new(root(tmp_path), name="kept")
    before = (first.folder / "hunt.json").read_bytes()
    target = desk()
    again = reopen(tmp_path, target=target)
    assert (again.name, again.folder, again.store, again.proposals) == (first.name, first.folder, first.store,
                                                                         first.proposals)
    assert (first.folder / "hunt.json").read_bytes() == before
    assert target.runs == 0 and hunts_in(root(tmp_path)) == ["kept"]


@pytest.mark.parametrize("name", ["never-made", None])
def test_a_hunt_that_is_not_there_is_refused_and_not_made(tmp_path: Path, name: str | None) -> None:
    """Ruling 15. Opening what is there never makes a hunt, and with no name there is nothing to open."""
    open_new(root(tmp_path), name="kept")
    with pytest.raises(hunt().HuntError) as refused:
        reopen(tmp_path, name)
    assert one_line(refused.value)
    assert hunts_in(root(tmp_path)) == ["kept"]


def test_a_folder_that_is_no_hunt_is_not_opened(tmp_path: Path) -> None:
    (root(tmp_path) / "stray").mkdir(parents=True)
    with pytest.raises(hunt().HuntError):
        reopen(tmp_path, "stray")


def test_another_seed_is_refused_when_a_hunt_is_opened_again(tmp_path: Path) -> None:
    """Ruling 15: the seed must be the hunt's, or a resumed arm could not equal an unstopped one."""
    open_new(root(tmp_path), name="kept")
    with pytest.raises(hunt().HuntError) as refused:
        reopen(tmp_path, search={"seed": 7})
    assert one_line(refused.value)
    assert reopen(tmp_path).name == "kept"


@pytest.mark.parametrize("cases", [some_cases(2), some_cases(4), (case("c1"), case("c2"), case("other"))],
                         ids=["one fewer", "one more", "one renamed"])
def test_other_cases_are_refused_when_a_hunt_is_opened_again(tmp_path: Path, cases: Any) -> None:
    """Ruling 15: the case ids must be the hunt's."""
    open_new(root(tmp_path), name="kept")
    with pytest.raises(hunt().HuntError):
        reopen(tmp_path, cases=cases)


def test_a_raised_cap_applies_when_a_hunt_is_opened_again(tmp_path: Path) -> None:
    """Ruling 15: every other setting may differ and applies from then on, so a stopped hunt can go on under a
    raised cap."""
    open_new(root(tmp_path), name="kept", search={"runs": 20})
    again = reopen(tmp_path, search={"runs": 60}, limits={"hours": 5})
    assert again.budget().runs == 60 and again.budget().hours == 5
    assert again.plan.runs == 60


# ---------------------------------------------------------------------------
# `hunt.json` when a hunt is made (ruling 16)
# ---------------------------------------------------------------------------


def test_the_hunts_file_names_the_hunt_its_settings_and_no_stage_yet(tmp_path: Path) -> None:
    """Spec §6.1: "the settings as resolved, the stages run, which run is which arm". Ruling 16 gives the keys. The
    settings are in the file's own tables and keys, defaults included, as `dump` writes them."""
    settings = settings_for(root(tmp_path), env={"inventory": ["full", "empty"]}, fails={"outcomes": ["unresolved"]})
    h = hunt().open_hunt(settings, target=desk(), cases=some_cases(), name="filed")
    data = hunt_json(h)
    assert data["schema"] == "poisson_break.hunt/1"
    assert data["name"] == "filed"
    assert data["settings"] == tomllib.loads(settings_module().dump(settings))
    assert data["settings"]["confirm"]["repeats"] == 5, "a default the test's file did not state"
    assert data["stages"] == [] and data["arms"] == {}
    made = datetime.datetime.fromisoformat(data["created"])
    assert abs((datetime.datetime.now(datetime.UTC) - made.astimezone(datetime.UTC)).total_seconds()) < 60


# ---------------------------------------------------------------------------
# BK5.17: what a way in cannot do
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("vary", "change", "can"), [
    ({"conversation": ["repeats"]}, "user:repeats@1", "conversation"),
    ({"conversation": ["goes_quiet", "repeats"]}, "user:goes_quiet@1", "conversation"),
    ({"model": ["timeout"]}, "model:timeout#1", "model_calls"),
])
def test_a_vary_entry_the_way_in_cannot_do_is_refused_before_any_run(tmp_path: Path, vary: dict[str, Any], change: str,
                                                                      can: str) -> None:
    """BK5.17, spec §11.2 invariant 6, ruling 30. The refusal is `check_capabilities`' own `NeedsAdapter`, naming the
    entry as a change at its first position. A way in that can do it opens the same settings."""
    target = desk()
    with pytest.raises(changes().NeedsAdapter) as refused:
        open_new(root(tmp_path), target=target, vary=vary)
    assert refused.value.change == change
    assert one_line(refused.value) and not isinstance(refused.value, hunt().HuntError)
    assert hunts_in(root(tmp_path)) == [] and target.runs == 0
    able = desk(can={can: True})
    assert open_new(root(tmp_path), target=able, vary=vary).target is able


def test_the_settings_read_and_the_plain_prove_target_is_what_refuses(tmp_path: Path) -> None:
    """Spec §11.2 invariant 6: "`conversation = ["repeats"]` with `kind = "rollout"` reads, and is refused at this
    point". Reading asks nothing (BK4.6); the runs module asks the target it was handed."""
    settings = settings_for(root(tmp_path), vary={"conversation": ["repeats"]})
    with pytest.raises(changes().NeedsAdapter) as refused:
        hunt().open_hunt(settings, target=rollout(settings), cases=some_cases(), name=None)
    assert refused.value.change == "user:repeats@1"
    assert hunts_in(root(tmp_path)) == [] and targets().ROLLOUTS == []


def test_the_way_in_is_asked_what_it_can_do_and_not_guessed_from_its_kind(tmp_path: Path) -> None:
    """Spec §11.2 invariant 6: "it asks of the capabilities and not of the surface, so an adapter lands with no core
    change". A way in of a kind the core has never heard of is taken at its word."""
    able = desk(can={"conversation": True, "model_calls": True})
    h = open_new(root(tmp_path), target=able, vary={"conversation": ["repeats"], "model": ["error"]})
    assert able.asked_capabilities >= 1 and h.target is able


# ---------------------------------------------------------------------------
# BK5.18 and spec §3.6: a check or a stand-in that cannot be loaded
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("own", ["tests.no_such_module:check", "tests.hunt_targets:no_such_name",
                                 "tests.hunt_targets:NOT_CALLABLE", "tests.hunt_broken_module:check"],
                         ids=["no such module", "no such name", "not something to call", "a module that breaks"])
def test_a_check_that_cannot_be_loaded_or_called_is_refused_before_any_run(tmp_path: Path, own: str) -> None:
    """BK5.18, spec §11.4 invariant 2, ruling 31: refused by the runs module, in one line, before any run."""
    target = desk()
    with pytest.raises(hunt().HuntError) as refused:
        open_new(root(tmp_path), target=target, fails={"own": own})
    assert one_line(refused.value)
    assert hunts_in(root(tmp_path)) == [] and target.runs == 0


def test_a_check_that_loads_opens_the_hunt_and_is_not_run_by_the_opening(tmp_path: Path) -> None:
    """The control for the test above. The check may be a paid model call (§11.4): loading it is not running it."""
    h = open_new(root(tmp_path), fails={"own": "tests.hunt_targets:counting_check"})
    assert h.name and targets().CHECKED == []


def test_a_stand_in_that_cannot_be_loaded_is_refused_before_any_run(tmp_path: Path) -> None:
    """Spec §3.6: a stand-in that cannot be loaded "is refused before any run". Ruling 31: the session's own
    `ToolRefused`, naming the tool, raised when the hunt is opened and not on its first run."""
    target = desk()
    tools = {"lookup_order": "read", "check_policy": "read",
             "issue_refund": {"class": "write", "stand_in": "tests.no_such_module:refund"}}
    with pytest.raises(apply_module().ToolRefused) as refused:
        open_new(root(tmp_path), target=target, tools=tools)
    assert refused.value.tool == "issue_refund"
    assert not isinstance(refused.value, hunt().HuntError)
    assert hunts_in(root(tmp_path)) == [] and target.runs == 0


def test_a_stand_in_that_loads_opens_the_hunt_and_is_not_called_by_the_opening(tmp_path: Path) -> None:
    tools = {"lookup_order": "read", "check_policy": "read",
             "issue_refund": {"class": "write", "stand_in": "tests.hunt_targets:refund_stand_in"}}
    assert open_new(root(tmp_path), tools=tools).name
    assert targets().EXECUTED == []


# ---------------------------------------------------------------------------
# the tools a way in lists (ruling 29)
# ---------------------------------------------------------------------------


def test_a_listed_tool_with_no_line_is_refused_before_any_run(tmp_path: Path) -> None:
    """Spec §3.6: "every tool the agent has is classed". Ruling 29: a tool `tools()` lists and `[tools]` has no line
    for is refused when the hunt is opened, before the first run could meet it."""
    target = desk(listed=["lookup_order", "check_policy", "issue_refund", "send_email"])
    with pytest.raises(hunt().HuntError) as refused:
        open_new(root(tmp_path), target=target)
    assert one_line(refused.value)
    assert hunts_in(root(tmp_path)) == [] and target.runs == 0 and target.asked_tools >= 1


@pytest.mark.parametrize("line", ["off", "read", {"class": "write", "repeatable": True}])
def test_a_listed_tool_with_a_line_of_any_class_opens(tmp_path: Path, line: Any) -> None:
    """The control: a line is what is asked for, and `off` is a line."""
    target = desk(listed=["lookup_order", "check_policy", "issue_refund", "send_email"])
    tools = {"lookup_order": "read", "check_policy": "read", "issue_refund": {"class": "write", "repeatable": True},
             "send_email": line}
    assert open_new(root(tmp_path), target=target, tools=tools).target is target


def test_a_classed_tool_the_way_in_does_not_list_is_no_trouble_when_opening(tmp_path: Path) -> None:
    """A line for a tool the agent turns out not to have costs nothing: only a missing line is refused."""
    assert open_new(root(tmp_path), target=desk(listed=["lookup_order"])).name


# ---------------------------------------------------------------------------
# the `rollout` kind's loader (ruling 9)
# ---------------------------------------------------------------------------


def test_load_target_makes_the_rollout_way_in_from_the_settings_entry(tmp_path: Path) -> None:
    """Ruling 9, plan BK5: "`Target` ... with the `rollout` kind as its first implementation". It lists every tool
    `[tools]` names, an `off` one too, and can route tool calls and nothing more (spec §3.4, §7.1)."""
    tools = {"lookup_order": "read", "check_policy": "read", "issue_refund": {"class": "write", "repeatable": True},
             "send_email": "off"}
    target = rollout(settings_for(root(tmp_path), tools=tools))
    assert isinstance(target, hunt().RolloutTarget) and isinstance(target, interfaces().Target)
    assert target.kind == "rollout"
    assert sorted(info.name for info in target.tools()) == sorted(tools)
    assert all(isinstance(info, hunt().ToolInfo) for info in target.tools())
    assert target.capabilities() == interfaces().Capabilities(tool_calls=True, model_calls=False, conversation=False)
    assert targets().ROLLOUTS == []


@pytest.mark.parametrize("entry", ["tests.hunt_targets", "tests.no_such_module:agent", "tests.hunt_targets:no_such_name",
                                   "tests.hunt_targets:NOT_CALLABLE", "tests.hunt_broken_module:agent",
                                   "python -m my_agent", "tests.hunt_targets:refund_agent:again"],
                         ids=["no name", "no such module", "no such name", "not something to call",
                              "a module that breaks", "a command line", "two colons"])
def test_an_entry_that_is_no_loadable_target_is_one_refusal(tmp_path: Path, entry: str) -> None:
    """Ruling 9: a `rollout` entry is `module:name`. Another form, one that cannot be imported and one that cannot be
    called are each a `HuntError` of one line, and nothing is run to find out."""
    with pytest.raises(hunt().HuntError) as refused:
        rollout(settings_for(root(tmp_path), entry=entry))
    assert one_line(refused.value)
    assert targets().ROLLOUTS == []


def test_a_rollout_target_can_be_made_from_a_function_in_hand(tmp_path: Path) -> None:
    """Ruling 9: `RolloutTarget(fn, *, tools)`, the tools by keyword."""
    made = hunt().RolloutTarget(targets().refund_agent, tools=["lookup_order"])
    assert [info.name for info in made.tools()] == ["lookup_order"]
    with pytest.raises(TypeError):
        hunt().RolloutTarget(targets().refund_agent, ["lookup_order"])
