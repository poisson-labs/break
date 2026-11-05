"""The plan shown before spending: the run counts it states.

Owned by the settings module (Break — Plan, BK4: "the plan a spending command shows"). Its shape is yes/no 4 (Taylor, 2026-11-04,
`evidence/bk4/open-points.md`): `plan_hunt(settings, *, cases)` and `plan_confirm(settings, *, cases, candidates=None)`, each giving a
frozen result. Yes/no 5 is what happens when the control stage does not fit. Every figure here is worked by hand from spec §5.2, §5.5 and
§9.2, and from plan ruling 19, and none is read from the module.

Words on screen are the commands module's, and dollars need a control stage's measured cost, so neither is here. That nothing is
spent until the plan has been shown and accepted is an order of events, and stays BK5.13's and BK8's: this module has nothing that runs.
What is held here is that working out a plan runs nothing (`test_settings_pure.py`).
"""

from __future__ import annotations

import pytest

from tests.settings_support import assert_one_line, doc, settings


def plan_hunt(text: str = "", *, cases: int = 12, **tables: str) -> object:
    s = settings()
    return s.plan_hunt(s.loads(text or doc(**tables)), cases=cases)


def plan_confirm(*, cases: int = 12, candidates: int | None = None, **tables: str) -> object:
    s = settings()
    read = s.loads(doc(**tables))
    return s.plan_confirm(read, cases=cases) if candidates is None else s.plan_confirm(read, cases=cases, candidates=candidates)


# ---------------------------------------------------------------------------
# the defaults, as ruled, on 12 cases
# ---------------------------------------------------------------------------


def test_a_hunt_on_12_cases_with_the_defaults() -> None:
    """§9.2's first example: control 60 runs, search and shrink up to 340, at most 400."""
    plan = plan_hunt()
    assert (plan.control_runs, plan.search_runs, plan.runs) == (60, 340, 400)


def test_confirming_on_12_cases_with_the_defaults() -> None:
    """Ruling 19 and §5.5: 540 runs, and up to 480 for reference, 60 for each finding."""
    plan = plan_confirm()
    assert (plan.confirm_runs, plan.reference_runs, plan.reference_per_finding, plan.runs) == (540, 480, 60, 1020)


def test_confirming_plus_reference_costs_more_than_the_hunt() -> None:
    """The thing Taylor accepted knowingly in ruling 19, and the reason the plan has to say it: 540 alone is more than the 400 of the hunt."""
    hunt, confirm = plan_hunt(), plan_confirm()
    assert confirm.confirm_runs > hunt.runs
    assert confirm.runs == 1020 and hunt.runs == 400


def test_the_second_example_the_spec_prints() -> None:
    """§9.2: 4 candidates on 11 cases, 275 runs, up to 220 more, 55 for each candidate confirmed."""
    plan = plan_confirm(cases=11, candidates=4)
    assert (plan.confirm_runs, plan.reference_runs, plan.reference_per_finding, plan.runs) == (275, 220, 55, 495)


# ---------------------------------------------------------------------------
# each setting moves its own figure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tables, cases, control, search, runs", [
    ({"search": "control_repeats = 7"}, 12, 84, 316, 400),
    ({"search": "runs = 500"}, 12, 60, 440, 500),
    ({"search": "runs = 100"}, 12, 60, 40, 100),
    ({}, 3, 15, 385, 400),
    ({"search": "control_repeats = 1\nruns = 50"}, 5, 5, 45, 50),
    ({"search": "cases_per_condition = 2"}, 12, 60, 340, 400),
    ({"confirm": "candidates = 3\nrepeats = 2"}, 12, 60, 340, 400),
])
def test_a_hunts_figures_follow_its_own_settings_and_no_others(tables: dict[str, str], cases: int, control: int, search: int, runs: int) -> None:
    plan = plan_hunt(cases=cases, **tables)
    assert (plan.control_runs, plan.search_runs, plan.runs) == (control, search, runs)


@pytest.mark.parametrize("tables, cases, confirm, reference, per, runs", [
    ({"confirm": "candidates = 3"}, 12, 240, 180, 60, 420),
    ({"confirm": "repeats = 3"}, 12, 324, 288, 36, 612),
    ({"confirm": "candidates = 1\nrepeats = 1"}, 2, 4, 2, 2, 6),
    ({}, 7, 315, 280, 35, 595),
    ({"search": "control_repeats = 9\nruns = 900\ncases_per_condition = 2"}, 12, 540, 480, 60, 1020),
])
def test_confirmings_figures_follow_its_own_settings_and_no_others(tables: dict[str, str], cases: int, confirm: int, reference: int, per: int, runs: int) -> None:
    """(1 + candidates) × cases × repeats, and cases × repeats per finding (§5.5). The two kinds of repeats are not one number."""
    plan = plan_confirm(cases=cases, **tables)
    assert (plan.confirm_runs, plan.reference_runs, plan.reference_per_finding, plan.runs) == (confirm, reference, per, runs)


def test_the_number_of_candidates_found_stands_over_the_settings() -> None:
    """A hunt that found 2 of the 8 it may hand over confirms 2."""
    plan = plan_confirm(candidates=2)
    assert (plan.confirm_runs, plan.reference_runs) == (180, 120)
    plan = plan_confirm(candidates=9, confirm="candidates = 2")
    assert (plan.confirm_runs, plan.reference_runs) == (600, 540)


def test_no_candidates_found_is_not_read_as_the_settings_number() -> None:
    """`candidates or settings` would plan 540 runs for a hunt that found nothing. Refusing or planning the control arm alone is the build's."""
    s = settings()
    try:
        plan = s.plan_confirm(s.loads(doc()), cases=12, candidates=0)
    except (s.SettingsError, ValueError):
        return
    assert plan.reference_runs == 0
    assert plan.confirm_runs < 540


# ---------------------------------------------------------------------------
# a control stage that does not fit (yes/no 5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tables, cases, smallest", [
    ({}, 100, 504),
    ({}, 80, 404),
    ({"search": "control_repeats = 10"}, 40, 404),
    ({"search": "cases_per_condition = 6"}, 80, 406),
    ({"search": "runs = 50"}, 12, 64),
])
def test_a_control_stage_that_leaves_no_room_is_refused_naming_the_smallest_runs(tables: dict[str, str], cases: int, smallest: int) -> None:
    """The one fact read from this message: the number the user is told to set. 80 cases × 5 is exactly the 400 runs, with none left to search."""
    s = settings()
    with pytest.raises(s.SettingsError) as caught:
        plan_hunt(cases=cases, **tables)
    assert_one_line(caught.value)
    assert caught.value.key == "search.runs"
    assert str(smallest) in str(caught.value)


@pytest.mark.parametrize("cases, control_repeats, cases_per_condition, smallest", [(100, 5, 4, 504), (80, 5, 4, 404), (20, 7, 3, 143)])
def test_the_number_it_names_is_the_smallest_that_works(cases: int, control_repeats: int, cases_per_condition: int, smallest: int) -> None:
    """Room for one condition on its cases: one run fewer is refused, and that number goes through with exactly that room."""
    s = settings()
    table = f"control_repeats = {control_repeats}\ncases_per_condition = {cases_per_condition}\nruns = "
    with pytest.raises(s.SettingsError):
        plan_hunt(cases=cases, search=f"{table}{smallest - 1}")
    plan = plan_hunt(cases=cases, search=f"{table}{smallest}")
    assert plan.search_runs == cases_per_condition
    assert plan.control_runs == cases * control_repeats


def test_confirming_has_no_such_limit() -> None:
    """`runs` is the hunt's budget, and §5.5's cost is shown and not capped by it."""
    assert plan_confirm(cases=100).confirm_runs == 4500


# ---------------------------------------------------------------------------
# the results
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("make, field", [(plan_hunt, "control_runs"), (plan_hunt, "search_runs"), (plan_hunt, "runs"),
                                         (plan_confirm, "confirm_runs"), (plan_confirm, "reference_runs"),
                                         (plan_confirm, "reference_per_finding"), (plan_confirm, "runs")])
def test_a_plan_cannot_be_changed(make: object, field: str) -> None:
    plan = make()
    with pytest.raises((AttributeError, TypeError)):
        setattr(plan, field, 1)


def test_two_plans_of_the_same_are_equal_and_of_different_are_not() -> None:
    assert plan_hunt() == plan_hunt()
    assert plan_hunt() != plan_hunt(cases=11)
    assert plan_confirm() == plan_confirm()
    assert plan_confirm() != plan_confirm(cases=11)


def test_the_number_of_cases_must_be_named() -> None:
    s = settings()
    read = s.loads(doc())
    for call in (s.plan_hunt, s.plan_confirm):
        with pytest.raises(TypeError):
            call(read, 12)
        with pytest.raises(TypeError):
            call(read)
    with pytest.raises(TypeError):
        s.plan_confirm(read, 12, 4)


def test_working_out_a_plan_leaves_the_settings_as_they_were() -> None:
    s = settings()
    read = s.loads(doc())
    before = s.dump(read)
    s.plan_hunt(read, cases=12)
    s.plan_confirm(read, cases=12, candidates=2)
    assert s.dump(read) == before
