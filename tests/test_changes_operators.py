"""Input operators and conversation moves, as pure functions: spec §3.3.

Invariant pinned here (Break — Plan, the catalogue module):
- BK1.5  Input operators and conversation moves are pure: the same case and seed give the same
         output, byte for byte, and `typos` changes a stated share of characters.

And what each one does, operator by operator and move by move. The functions' names, their
signatures and the shape of a case are ruling 9; what a move does to the script and what an
operator does when it cannot act are ruling 10.
"""

from __future__ import annotations

import copy
import json
import random
import re
from collections import Counter

import pytest

from tests.changes_support import CONVERSATION_MOVES, INPUT_OPERATORS, changes, entry, under_hash_seed

# Four sentences, and no character twice running, so that swapping two neighbours always changes
# the text.
INPUT = "Where is my order now? Send it to the new place. Give me the date. Stop if it is late."
SENTENCES = ["Where is my order now?", "Send it to the new place.", "Give me the date.",
             "Stop if it is late."]
TURNS = ["first thing I said", "second thing I said", "third thing I said", "last thing I said"]


def case(**over):
    fields = {"id": "c1", "input": INPUT, "variants": ["one way to ask", "another way to ask",
                                                       "a third way to ask"], "turns": list(TURNS)}
    fields.update(over)
    return fields


def operator(name: str):
    return getattr(changes(), name)


def move(name: str):
    return getattr(changes(), name)


def split(text: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+", text.strip())


def osa_distance(a: str, b: str) -> int:
    """Edits between two strings, a swap of two neighbours counting as one: the two things `typos`
    does are one edit each under this measure."""
    before: list[int] = []
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            cost = min(previous[j] + 1, row[j - 1] + 1, previous[j - 1] + (ca != cb))
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cost = min(cost, before[j - 2] + 1)
            row.append(cost)
        before, previous = previous, row
    return previous[-1]


# ---------------------------------------------------------------------------
# BK1.5  pure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", INPUT_OPERATORS)
def test_an_operator_gives_the_same_bytes_for_the_same_case_and_seed(name: str) -> None:
    f = operator(name)
    for seed in (0, 1, 2, 2**40):
        first, second = f(case(), seed=seed), f(case(), seed=seed)
        assert isinstance(first, str)
        assert first.encode() == second.encode()


@pytest.mark.parametrize("name", CONVERSATION_MOVES)
def test_a_move_gives_the_same_bytes_for_the_same_case_turn_and_seed(name: str) -> None:
    f = move(name)
    for seed in (0, 1, 2, 2**40):
        first, second = f(case(), turn=2, seed=seed), f(case(), turn=2, seed=seed)
        assert all(isinstance(t, str) for t in first)
        assert list(first) == list(second)


@pytest.mark.parametrize("name", INPUT_OPERATORS + CONVERSATION_MOVES)
def test_the_case_is_left_as_it_was(name: str) -> None:
    """Pure means the case is not written to. A case that one run edits is a different case for the
    next run, and replay is gone."""
    f = getattr(changes(), name)
    original = case()
    held = copy.deepcopy(original)
    f(original, seed=1) if name in INPUT_OPERATORS else f(original, turn=2, seed=1)
    assert original == held


@pytest.mark.parametrize("name", INPUT_OPERATORS + CONVERSATION_MOVES)
def test_the_global_generator_is_neither_read_nor_moved(name: str) -> None:
    """A function of the case and the seed only (§3.3): not of whatever `random` holds, and the
    search's own generator is not disturbed (§3.1)."""
    f = getattr(changes(), name)
    call = (lambda: f(case(), seed=5)) if name in INPUT_OPERATORS else (
        lambda: list(f(case(), turn=2, seed=5)))
    answers = []
    for global_seed in (1, 2):
        random.seed(global_seed)
        before = random.getstate()
        answers.append(call())
        assert random.getstate() == before
    assert answers[0] == answers[1]


def test_every_one_is_the_same_across_processes() -> None:
    """A word list walked through a set, or a pick by a built-in hash, passes in one process and
    replays nothing."""
    code = (
        "import json; from poisson_break import changes as c\n"
        f"case = {case()!r}\n"
        "out = {}\n"
        f"for n in {INPUT_OPERATORS!r}:\n"
        "    out[n] = [getattr(c, n)(case, seed=s) for s in range(20)]\n"
        f"for n in {CONVERSATION_MOVES!r}:\n"
        "    out[n] = [list(getattr(c, n)(case, turn=2, seed=s)) for s in range(20)]\n"
        "print(json.dumps(out))\n"
    )
    assert json.loads(under_hash_seed(code, 1)) == json.loads(under_hash_seed(code, 2))


# ---------------------------------------------------------------------------
# the input operators, one by one (§3.3)
# ---------------------------------------------------------------------------


def test_typos_changes_the_stated_share_of_characters() -> None:
    """BK1.5. The share is stated in the catalogue (ruling 12: 5%). Each swap or drop is one edit,
    so the edits over the text's length are the share; a mean over seeds, within a fifth of it."""
    share = entry("input", "typos").parameters["share"]
    assert share == 0.05
    text = " ".join([INPUT] * 4)
    assert all(a != b for a, b in zip(text, text[1:]))
    edits = [osa_distance(text, operator("typos")({"input": text}, seed=s)) for s in range(12)]
    measured = sum(edits) / len(edits) / len(text)
    assert abs(measured - share) <= share / 5


def test_typos_only_swaps_or_drops() -> None:
    """§3.3: characters swapped or dropped. So no character appears that was not there, or more
    often than it was, and nothing was added."""
    for seed in range(50):
        out = operator("typos")(case(), seed=seed)
        assert not Counter(out) - Counter(INPUT), seed
        assert len(out) <= len(INPUT)


def test_typos_changes_the_text_and_the_seed_changes_how() -> None:
    outs = {operator("typos")(case(), seed=s) for s in range(30)}
    assert INPUT not in outs
    assert len(outs) >= 20


def test_reordered_keeps_every_sentence_and_changes_the_order() -> None:
    """On every seed, not most of them: a plain shuffle of four leaves them as they were one time in
    24, so 400 seeds show it."""
    for seed in range(400):
        out = split(operator("reordered")(case(), seed=seed))
        assert sorted(out) == sorted(SENTENCES), seed
        assert out != SENTENCES, seed


def test_reordered_reaches_more_than_one_order() -> None:
    assert len({operator("reordered")(case(), seed=s) for s in range(50)}) >= 3


def test_reordered_with_one_sentence_has_nothing_to_change() -> None:
    assert operator("reordered")(case(input="Where is my order?"), seed=1) == "Where is my order?"


def _padding(seed: int, text: str) -> str:
    out = operator("padded")(case(input=text), seed=seed)
    assert out.endswith(text), "the request itself is unchanged, and last"
    return out[: -len(text)]


def test_padded_puts_a_paragraph_before_the_unchanged_request() -> None:
    for seed in range(30):
        assert _padding(seed, INPUT).strip()


def test_padded_comes_from_a_fixed_list_unrelated_to_the_request() -> None:
    """§3.3: an unrelated paragraph from a fixed list. So what is added is one of few, the same few
    whatever was asked, and none of it is built from the request or the seed."""
    seeds = range(300)
    first = {_padding(s, INPUT) for s in seeds}
    second = {_padding(s, "Quillfern zebra marmalade.") for s in seeds}
    assert first == second
    assert len(first) <= 50
    assert not any("Quillfern" in p for p in second)


def test_cut_short_is_only_the_first_sentence() -> None:
    assert operator("cut_short")(case(), seed=1) == "Where is my order now?"
    assert operator("cut_short")(case(input="Stop! Go on."), seed=1) == "Stop!"
    assert operator("cut_short")(case(input="Send it. Then wait."), seed=1) == "Send it."


def test_cut_short_of_one_sentence_is_the_sentence() -> None:
    assert operator("cut_short")(case(input="Where is my order?"), seed=1) == "Where is my order?"
    assert operator("cut_short")(case(input="no full stop here"), seed=1) == "no full stop here"


def test_cut_short_involves_no_chance() -> None:
    assert len({operator("cut_short")(case(), seed=s) for s in range(30)}) == 1


def test_variant_gives_an_entry_the_user_wrote_and_reaches_all_of_them() -> None:
    """§3.3: the next entry of the case's `variants`. The seed walks the list; the request as first
    written is not one of them."""
    variants = case()["variants"]
    outs = [operator("variant")(case(), seed=s) for s in range(30)]
    assert set(outs) == set(variants)


@pytest.mark.parametrize("no_variants", [{}, {"variants": []}])
def test_variant_with_none_written_leaves_the_input(no_variants: dict) -> None:
    """Ruling 10. Break writes no text of its own; the record says the change did not apply."""
    held = case()
    del held["variants"]
    held.update(no_variants)
    assert operator("variant")(held, seed=1) == INPUT


def test_an_operator_on_an_empty_input_leaves_it_empty() -> None:
    for name in ("typos", "reordered", "cut_short"):
        assert operator(name)(case(input=""), seed=1) == ""


# ---------------------------------------------------------------------------
# the conversation moves, one by one (§3.3, ruling 10)
# ---------------------------------------------------------------------------


def changed_at(name: str, turn: int, seed: int = 1) -> str:
    """The message a move leaves at its turn, having checked it touched nothing else: BK9.8 asks
    that each move changes exactly the turn it names, and the length stays the script's."""
    out = list(move(name)(case(), turn=turn, seed=seed))
    assert len(out) == len(TURNS)
    for i, message in enumerate(out, 1):
        if i != turn:
            assert message == TURNS[i - 1], f"{name} changed turn {i} as well as {turn}"
    return out[turn - 1]


@pytest.mark.parametrize("name", CONVERSATION_MOVES)
@pytest.mark.parametrize("turn", [2, 3, 4])
def test_a_move_changes_the_turn_it_names_and_no_other(name: str, turn: int) -> None:
    assert changed_at(name, turn) != TURNS[turn - 1]


@pytest.mark.parametrize("name", ["interrupts", "goes_quiet", "presses"])
def test_turns_count_from_one(name: str) -> None:
    assert changed_at(name, 1) != TURNS[0]


def test_repeats_sends_the_message_before_it_again() -> None:
    assert changed_at("repeats", 2) == TURNS[0]
    assert changed_at("repeats", 4) == TURNS[2]


def test_repeats_on_the_first_turn_has_nothing_to_repeat() -> None:
    assert list(move("repeats")(case(), turn=1, seed=1)) == TURNS


def test_goes_quiet_is_one_character() -> None:
    for seed in range(20):
        assert len(changed_at("goes_quiet", 2, seed=seed)) == 1


@pytest.mark.parametrize("name", ["interrupts", "presses"])
def test_a_listed_move_comes_from_a_fixed_list_whatever_the_script(name: str) -> None:
    """§3.3: each a line from a fixed list. So one of few, the same few for any script, and nothing
    from the script itself."""
    other_script = case(turns=["quillfern one", "quillfern two", "quillfern three"])
    seeds = range(300)
    lines = {changed_at(name, 2, seed=s) for s in seeds}
    assert lines == {list(move(name)(other_script, turn=2, seed=s))[1] for s in seeds}
    assert len(lines) <= 50
    assert not any("quillfern" in line or line in TURNS for line in lines)


def test_interrupting_and_pressing_are_different_lists() -> None:
    """An off-topic message and a line asking the agent to skip its checks are different moves, and
    a shared list would test one thing twice."""
    interrupts = {changed_at("interrupts", 2, seed=s) for s in range(300)}
    presses = {changed_at("presses", 2, seed=s) for s in range(300)}
    assert not interrupts & presses


@pytest.mark.parametrize("name", CONVERSATION_MOVES)
def test_a_move_past_the_end_of_the_script_leaves_it(name: str) -> None:
    """Ruling 10. The record's `applied` is how a hunt learns the turn never came."""
    assert list(move(name)(case(), turn=9, seed=1)) == TURNS


@pytest.mark.parametrize("name", CONVERSATION_MOVES)
def test_a_move_on_a_case_with_no_script_leaves_it_with_none(name: str) -> None:
    """§9.4: `turns` is optional."""
    held = case()
    del held["turns"]
    assert list(move(name)(held, turn=1, seed=1)) == []
