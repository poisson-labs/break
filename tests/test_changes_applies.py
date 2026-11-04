"""Whether a change applies to a call: spec §3.1, through `applies(change, *, seed, tool, call)`.

Invariants pinned here (Break — Plan, the catalogue module):
- BK1.3  A schedule involves no chance. `applies` for `#n`, `#n-m` and `#*` depends only on the
         call number.
- BK1.4  A rate is a keyed draw. `applies` for `~r` is equal across processes for the same seed,
         tool and call; over many seeds its share is within a stated band of `r`; changing the
         tool or the call changes the draw.

The stated band is ±0.02 over 20,000 draws, more than five standard deviations at any `r`, so a
sound keyed hash cannot flake here, and the verdict is the same on every run because nothing is
random. Agreement between two draws at `r = 0.5` is 0.5 when they are independent and 1 when one
input has been ignored; the band there is the same ±0.02 at 20,000 and ±0.03 at 5,000.
"""

from __future__ import annotations

import json
import random

import pytest

from tests.changes_support import MODEL_FAULTS, changes, one, under_hash_seed

SEEDS = (0, 1, 2, 7, 20261005, 2**31, 2**63)
CALLS = range(1, 13)
N = 20_000


def fires(text: str, *, seed: int = 1, tool: str = "a") -> set[int]:
    """The call numbers, of 1 to 12, on which a change applies."""
    change = one(text)
    return {call for call in CALLS if changes().applies(change, seed=seed, tool=tool, call=call)}


def share(text: str, *, tool: str = "a", call: int = 1) -> float:
    change = one(text)
    hits = sum(changes().applies(change, seed=s, tool=tool, call=call) for s in range(N))
    return hits / N


def agreement(left, right, n: int = N) -> float:
    """The share of `n` seeds on which two draws, each given a seed, come out the same."""
    return sum(left(s) == right(s) for s in range(n)) / n


# ---------------------------------------------------------------------------
# BK1.3  a schedule involves no chance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("position, expected", [
    ("#1", {1}),
    ("#2", {2}),
    ("#12", {12}),
    ("#2-4", {2, 3, 4}),
    ("#1-1", {1}),
    ("#*", set(CALLS)),
])
def test_a_schedule_fires_on_exactly_its_calls_under_any_seed(position: str, expected: set[int],
                                                              seed: int) -> None:
    """Calls count from 1 (§3.1), both ends of a range included, and the seed changes nothing."""
    assert fires(f"tool:a{position}=error", seed=seed) == expected


def test_a_range_past_what_was_tried_still_answers_by_the_number() -> None:
    """A call number is an ordinary number: not bounded by the default limit of three, nor by a
    table the module built."""
    change = one("tool:a#*=error")
    assert changes().applies(change, seed=1, tool="a", call=10_000) is True
    assert changes().applies(one("tool:a#9999-10001=error"), seed=1, tool="a", call=10_000) is True
    assert changes().applies(one("tool:a#9999-10001=error"), seed=1, tool="a", call=9_998) is False


@pytest.mark.parametrize("position", ["#2", "#2-4", "#*", "~1"])
def test_a_change_on_one_tool_does_not_apply_to_another(position: str) -> None:
    """Ruling 8. `tool:a#2` leaves the second call of `b` alone. The rate of 1 is here because it
    fires on every call of its own tool, so a miss cannot be the draw."""
    assert fires(f"tool:a{position}=error", tool="a") != set()
    assert fires(f"tool:a{position}=error", tool="b") == set()


def test_the_answer_is_a_real_bool() -> None:
    """The signature says `-> bool`, and a stored record holds `applied` as one (§6.4). A truthy
    number or a matched-text object would be refused there."""
    c = changes()
    for text in ("tool:a#2=error", "tool:a~0.5=error", "tool:a#*=error"):
        change = one(text)
        for call in (1, 2):
            assert type(c.applies(change, seed=1, tool="a", call=call)) is bool


@pytest.mark.parametrize("text, tool, call", [
    ("input:typos", "a", 1),
    ("user:repeats@2", "a", 2),
    ("env:inventory=empty", "a", 1),
    *[(f"model:{fault}#2", "a", 2) for fault in MODEL_FAULTS],
])
def test_a_change_that_is_not_on_a_tool_never_fires_on_a_tool_call(text: str, tool: str,
                                                                   call: int) -> None:
    """A `model:` change on its second call is not the second call of a tool: if this were true the
    applier would fault the tool in the model's place. It may answer False or refuse, and no test
    decides which; it may not answer True."""
    c = changes()
    change = one(text, env={"inventory": ["empty"]})
    try:
        answer = c.applies(change, seed=1, tool=tool, call=call)
    except c.ChangeError:
        return
    assert answer is False


# ---------------------------------------------------------------------------
# BK1.4  a rate is a keyed draw
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rate", [0.1, 0.3, 0.5, 0.9])
def test_over_many_seeds_the_share_is_within_the_band(rate: float) -> None:
    assert abs(share(f"tool:a~{rate}=error") - rate) <= 0.02


def test_over_many_calls_of_one_run_the_share_is_within_the_band() -> None:
    """One seed, one tool, many calls: a draw keyed on the seed alone gives all or nothing."""
    change = one("tool:a~0.3=error")
    hits = sum(changes().applies(change, seed=1, tool="a", call=c) for c in range(1, N + 1))
    assert abs(hits / N - 0.3) <= 0.02


def test_a_rate_of_one_always_fires() -> None:
    assert share("tool:a~1=error") == 1.0


def test_changing_the_call_changes_the_draw() -> None:
    change = one("tool:a~0.5=error")
    c = changes()
    together = agreement(lambda s: c.applies(change, seed=s, tool="a", call=1),
                         lambda s: c.applies(change, seed=s, tool="a", call=2))
    assert abs(together - 0.5) <= 0.02


def test_changing_the_tool_changes_the_draw() -> None:
    """Each change is asked about its own tool, so this holds whatever a change answers for
    another tool."""
    c = changes()
    on_a, on_b = one("tool:a~0.5=error"), one("tool:b~0.5=error")
    together = agreement(lambda s: c.applies(on_a, seed=s, tool="a", call=1),
                         lambda s: c.applies(on_b, seed=s, tool="b", call=1))
    assert abs(together - 0.5) <= 0.02


def test_changing_the_seed_changes_the_draw() -> None:
    """Neighbouring seeds are independent. A key that adds the seed to the call makes seed s on
    call 2 the same draw as seed s + 1 on call 1."""
    c = changes()
    change = one("tool:a~0.5=error")
    together = agreement(lambda s: c.applies(change, seed=s, tool="a", call=2),
                         lambda s: c.applies(change, seed=s + 1, tool="a", call=1))
    assert abs(together - 0.5) <= 0.02


@pytest.mark.parametrize("left, right", [
    (("a1", 1), ("a", 11)),
    (("a", 111), ("a1", 11)),
])
def test_the_key_keeps_tool_and_call_apart(left: tuple[str, int], right: tuple[str, int]) -> None:
    """A key written by joining text with no separator makes tool `a1` on call 1 the same draw as
    tool `a` on call 11. A 5,000 sample is enough, and the band is wider to match."""
    c = changes()
    on_left, on_right = one(f"tool:{left[0]}~0.5=error"), one(f"tool:{right[0]}~0.5=error")
    together = agreement(lambda s: c.applies(on_left, seed=s, tool=left[0], call=left[1]),
                         lambda s: c.applies(on_right, seed=s, tool=right[0], call=right[1]),
                         n=5_000)
    assert abs(together - 0.5) <= 0.03


def test_the_key_keeps_seed_and_call_apart() -> None:
    """Seed 71 on call 1 and seed 7 on call 11 are different draws, though the digits run the same
    if they are written side by side."""
    c = changes()
    change = one("tool:a~0.5=error")
    together = agreement(lambda s: c.applies(change, seed=int(f"{s + 1}1"), tool="a", call=1),
                         lambda s: c.applies(change, seed=s + 1, tool="a", call=11),
                         n=5_000)
    assert abs(together - 0.5) <= 0.03


def test_the_fault_is_not_in_the_key() -> None:
    """§3.1: the key is the seed, the tool and the call number. Two faults at one rate on one call
    make the same draw, so shrinking a condition cannot move where a change lands."""
    c = changes()
    one_fault, other = one("tool:a~0.3=error"), one("tool:a~0.3=timeout")
    for seed in range(2_000):
        assert (c.applies(one_fault, seed=seed, tool="a", call=1)
                == c.applies(other, seed=seed, tool="a", call=1))


def test_a_rate_is_equal_across_processes() -> None:
    """A built-in `hash` of the tool's name passes every test in one process and replays nothing."""
    code = (
        "import json; from poisson_break.changes import applies, parse\n"
        "c = parse('tool:lookup_order~0.5=error').changes[0]\n"
        "print(json.dumps([applies(c, seed=s, tool='lookup_order', call=1 + s % 4) "
        "for s in range(400)]))\n"
    )
    first = json.loads(under_hash_seed(code, 1))
    assert first == json.loads(under_hash_seed(code, 2))
    assert 100 < sum(first) < 300
    change = one("tool:lookup_order~0.5=error")
    assert first == [changes().applies(change, seed=s, tool="lookup_order", call=1 + s % 4)
                     for s in range(400)]


def test_a_draw_neither_reads_nor_moves_the_global_generator() -> None:
    """§3.1: the search's own random choices never touch a run's. A draw that seeds or reads
    `random` either changes with the search's state or changes the search's next choice."""
    c = changes()
    change = one("tool:a~0.5=error")
    answers = []
    for global_seed in (1, 2):
        random.seed(global_seed)
        before = random.getstate()
        answers.append([c.applies(change, seed=s, tool="a", call=1) for s in range(200)])
        assert random.getstate() == before
    assert answers[0] == answers[1]
