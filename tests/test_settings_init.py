"""`init`'s flags, and the one command that writes the same file.

Invariants pinned here (Break — Plan, the settings module):
- BK4.1 For every settings value `init`'s flags can produce, `loads(dump(s)) == s`, and every key of spec §9.4 is
        reachable from a flag.
- BK4.4 The equivalent command round-trips to a byte-identical file, under both progs.

The shapes are yes/no 3 (Taylor, 2026-11-04, `evidence/bk4/open-points.md`): `settings_from_init_args(words)` takes the words
after `init`, `equivalent_init_command(settings, *, prog)` returns one line a shell can run, and `INIT_FLAGS` maps each flag to
the key of §9.4 it sets, with one flag that repeats for a `[tools]` line and one for a `[vary.env]` entry.

**No test spells a flag or a flag's value.** Flags are read from `INIT_FLAGS` and from the command itself, so the build keeps the
naming and how a value is written. `version` is not reachable from a flag and is not asked to be: `init` writes this module's own.
"""

from __future__ import annotations

import shlex
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.conftest import PROGS
from tests.settings_support import DEFAULTS, OPTIONAL, assert_one_line, doc, settings
from tests.test_settings_read import EVERYTHING, ROUND_TRIPS

# §9.4's keys with a fixed name, every one of them, and the three the failure check's ruling 6 adds to its list.
KEYS = frozenset({
    "target.kind", "target.entry", "target.cases",
    "fails.checks", "fails.outcomes", "fails.own", "fails.also", "fails.never_call", "fails.run_seconds",
    "fails.retry_storm_after", "fails.max_tool_calls", "fails.max_tokens",
    "vary.tools", "vary.inputs", "vary.conversation", "vary.model", "vary.max_call",
    "search.strategy", "search.runs", "search.control_repeats", "search.cases_per_condition", "search.seed",
    "confirm.candidates", "confirm.repeats", "confirm.max_difference", "confirm.q",
    "limits.dollars", "limits.input_per_million", "limits.output_per_million", "limits.hours",
    "output.folder",
})
# Where the names are the user's own, one repeating flag each.
FREE = frozenset({"tools", "vary.env"})

# What a shell does something with, and what must reach the flag as it is.
FOR_THE_SHELL = {
    "a dollar sign": doc(output='folder = "$HOME/runs"'),
    "a backtick": doc(output='folder = "`hostname`"'),
    "a semicolon": doc(output='folder = "a; rm b"'),
    "an ampersand and a pipe": doc(output='folder = "a & b | c"'),
    "a star": doc(output='folder = "runs*"'),
    "a tilde": doc(output='folder = "~/runs"'),
    "a single quote": doc(output='folder = "it\'s here"'),
    "a double quote": doc(output='folder = "say \\"hi\\""'),
    "a space": doc(output='folder = "my runs"'),
    "a leading dash": doc(output='folder = "--runs"'),
    "a line break in a value": doc(output='folder = "one\\ntwo"'),
    "a single quote in a tool's name": doc(tools='"it\'s" = "read"'),
    "a dollar sign in a setting of one's own": doc(vary__env='note = ["$HOME", "`x`"]'),
}
FILES = {**ROUND_TRIPS, **FOR_THE_SHELL}


def command(text: str, prog: str = PROGS[0]) -> str:
    s = settings()
    return s.equivalent_init_command(s.loads(text), prog=prog)


def words_of(line: str, prog: str = PROGS[0]) -> list[str]:
    """The words after `init`. The command must start with the name it was given and then `init`."""
    words = shlex.split(line)
    start = [*prog.split(), "init"]
    assert words[:len(start)] == start, words[:len(start)]
    return words[len(start):]


def chunks(words: list[str]) -> list[list[str]]:
    """The words split into one list per flag, however its value is attached."""
    held: list[list[str]] = []
    for word in words:
        if word.split("=", 1)[0] in settings().INIT_FLAGS:
            held.append([word])
        else:
            assert held, f"{word!r} comes before any flag"
            held[-1].append(word)
    return held


def flag_of(chunk: list[str]) -> str:
    return chunk[0].split("=", 1)[0]


def flag_for(key: str) -> str:
    found = [f for f, k in settings().INIT_FLAGS.items() if k == key]
    assert len(found) == 1, f"{key} has the flags {found}"
    return found[0]


# ---------------------------------------------------------------------------
# BK4.4  the equivalent command
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prog", PROGS)
@pytest.mark.parametrize("text", FILES.values(), ids=FILES.keys())
def test_the_command_writes_the_same_file_byte_for_byte(text: str, prog: str) -> None:
    s = settings()
    read = s.loads(text)
    assert s.dump(s.settings_from_init_args(words_of(s.equivalent_init_command(read, prog=prog), prog))) == s.dump(read)


@pytest.mark.parametrize("text", FILES.values(), ids=FILES.keys())
def test_what_the_flags_make_gives_the_same_command_again(text: str) -> None:
    """If a command drifted on each pass, what `init` prints would not be what wrote the file."""
    s = settings()
    line = command(text)
    assert s.equivalent_init_command(s.settings_from_init_args(words_of(line)), prog=PROGS[0]) == line


@pytest.mark.parametrize("prog", PROGS)
@pytest.mark.parametrize("text", FILES.values(), ids=FILES.keys())
def test_the_command_is_one_line(text: str, prog: str) -> None:
    line = command(text, prog)
    assert "\n" not in line and "\r" not in line, line


@pytest.mark.parametrize("prog", PROGS)
def test_the_command_starts_with_the_name_it_was_given(prog: str) -> None:
    assert command(doc(), prog).startswith(f"{prog} init")


def test_the_two_names_change_nothing_but_the_name() -> None:
    first, second = PROGS
    assert command(EVERYTHING, first)[len(first):] == command(EVERYTHING, second)[len(second):]


def test_a_name_with_no_literal_behind_it_is_rendered_too() -> None:
    assert command(doc(), "some other name").startswith("some other name init")


def test_the_name_must_be_given_and_by_keyword() -> None:
    s = settings()
    read = s.loads(doc())
    with pytest.raises(TypeError):
        s.equivalent_init_command(read)
    with pytest.raises(TypeError):
        s.equivalent_init_command(read, PROGS[0])


@pytest.mark.parametrize("prog", PROGS)
@pytest.mark.parametrize("text", FOR_THE_SHELL.values(), ids=FOR_THE_SHELL.keys())
def test_a_real_shell_hands_over_the_same_words(tmp_path: Path, text: str, prog: str) -> None:
    """`shlex` is not a shell: `$HOME` means nothing to it. A stand-in for the command prints the words a real shell gave it."""
    script = tmp_path / prog.split()[0]
    script.write_text('#!/bin/sh\nfor word in "$@"; do printf \'%s\\0\' "$word"; done\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    s = settings()
    read = s.loads(text)
    done = subprocess.run(["/bin/sh", "-c", s.equivalent_init_command(read, prog=prog)], capture_output=True, timeout=30,
                          env={"PATH": f"{tmp_path}:/usr/bin:/bin", "HOME": "/nowhere"}, cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    words = [w.decode() for w in done.stdout.split(b"\0")[:-1]]
    start = [*prog.split()[1:], "init"]
    assert words[:len(start)] == start, words[:len(start)]
    assert s.dump(s.settings_from_init_args(words[len(start):])) == s.dump(read)


# ---------------------------------------------------------------------------
# BK4.1  every key reachable from a flag
# ---------------------------------------------------------------------------


def test_the_flags_are_a_mapping_of_each_flag_to_the_key_it_sets() -> None:
    flags = settings().INIT_FLAGS
    assert isinstance(flags, Mapping)
    assert all(isinstance(f, str) and f.startswith("--") for f in flags)
    assert all(isinstance(k, str) for k in flags.values())


def test_every_key_the_spec_prints_has_exactly_one_flag_and_no_flag_sets_anything_else() -> None:
    values = list(settings().INIT_FLAGS.values())
    assert sorted(values) == sorted(KEYS | FREE)


def test_a_file_with_every_key_set_uses_every_flag() -> None:
    used = {flag_of(c) for c in chunks(words_of(command(EVERYTHING)))}
    assert used == set(settings().INIT_FLAGS)


def test_a_tool_and_a_setting_of_ones_own_each_repeat_their_flag() -> None:
    held = chunks(words_of(command(doc(tools='a = "read"\nb = "off"\nc = "read"', vary__env='x = ["1"]\ny = ["2"]'))))
    used = [flag_of(c) for c in held]
    assert used.count(flag_for("tools")) == 3
    assert used.count(flag_for("vary.env")) == 2


REACHED = [(t, k, other, "rollout") for t, k, _, other, _ in DEFAULTS] + [(t, k, v, "langgraph") for t, k, v, _ in OPTIONAL]


@pytest.mark.parametrize("table, key, value, kind", REACHED, ids=[f"{t}.{k}" for t, k, *_ in REACHED])
def test_the_flag_of_a_key_is_what_carries_it(table: str, key: str, value: str, kind: str) -> None:
    """Take the key's own flag back out and the value goes with it, and nothing else does. A flag mapped to the wrong key shows here."""
    s = settings()
    wanted = flag_for(f"{table}.{key}")
    held = chunks(words_of(command(doc(kind=kind, **{table: f"{key} = {value}"}))))
    assert wanted in [flag_of(c) for c in held]
    rest = [word for c in held if flag_of(c) != wanted for word in c]
    assert s.settings_from_init_args(rest) == s.loads(doc(kind=kind))


def test_a_cap_and_the_two_prices_are_each_carried_by_their_own_flag() -> None:
    held = chunks(words_of(command(doc(limits="dollars = 7.5\ninput_per_million = 0.125\noutput_per_million = 0.5"))))
    used = {flag_of(c) for c in held}
    assert {flag_for("limits.dollars"), flag_for("limits.input_per_million"), flag_for("limits.output_per_million")} <= used


def test_flags_left_out_read_as_the_defaults() -> None:
    """Only what §9.4 gives no default for, and the settings are those of a file that says no more."""
    s = settings()
    needed = {flag_for("target.kind"), flag_for("target.entry"), flag_for("target.cases"), flag_for("tools")}
    held = chunks(words_of(command(doc())))
    words = [word for c in held if flag_of(c) in needed for word in c]
    assert s.settings_from_init_args(words) == s.loads(doc())


# ---------------------------------------------------------------------------
# BK4.1  what the flags make
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", FILES.values(), ids=FILES.keys())
def test_what_the_flags_make_round_trips_through_the_file_and_equals_the_file(text: str) -> None:
    s = settings()
    made = s.settings_from_init_args(words_of(command(text)))
    assert s.loads(s.dump(made)) == made
    assert made == s.loads(text)


def test_the_words_may_be_any_sequence() -> None:
    s = settings()
    words = words_of(command(doc()))
    assert s.settings_from_init_args(tuple(words)) == s.settings_from_init_args(words)


# ---------------------------------------------------------------------------
# what the flags refuse
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table, line, old, new, key", [
    ("search", "runs = 401", "401", "0", "search.runs"),
    ("confirm", "q = 0.15", "0.15", "1.5", "confirm.q"),
    ("vary", "max_call = 7", "7", "0", "vary.max_call"),
    ("fails", "run_seconds = 61", "61", "0", "fails.run_seconds"),
])
def test_a_bad_value_through_a_flag_is_refused_as_it_is_from_a_file(table: str, line: str, old: str, new: str, key: str) -> None:
    s = settings()
    wanted = flag_for(key)
    words: list[str] = []
    for chunk in chunks(words_of(command(doc(**{table: line})))):
        words += [w.replace(old, new) for w in chunk] if flag_of(chunk) == wanted else chunk
    with pytest.raises(s.SettingsError) as caught:
        s.settings_from_init_args(words)
    assert_one_line(caught.value)
    assert caught.value.key == key


def test_a_write_tool_not_made_safe_is_refused_through_the_flag() -> None:
    s = settings()
    wanted = flag_for("tools")
    words: list[str] = []
    for chunk in chunks(words_of(command(doc(tools='w = { class = "write", repeatable = true }')))):
        words += [w.replace("true", "false") for w in chunk] if flag_of(chunk) == wanted else chunk
    with pytest.raises(s.SettingsError) as caught:
        s.settings_from_init_args(words)
    assert caught.value.key.startswith("tools.w")


def test_every_abbreviated_flag_is_refused() -> None:
    """§9.1: no abbreviated flags. Each flag's own chunk has its name cut short, with nothing else in the file changed, so the only
    thing to refuse is the abbreviation: added beside the whole flag, it would be refused for setting a key twice."""
    s = settings()
    held = chunks(words_of(command(EVERYTHING)))
    assert s.settings_from_init_args([w for c in held for w in c]) == s.loads(EVERYTHING)
    for at, chunk in enumerate(held):
        flag = flag_of(chunk)
        short = flag[:-1]
        if short in s.INIT_FLAGS:
            continue
        cut = [chunk[0].replace(flag, short, 1), *chunk[1:]]
        words = [w for c in held[:at] + [cut] + held[at + 1:] for w in c]
        with pytest.raises(s.SettingsError) as caught:
            s.settings_from_init_args(words)
        assert_one_line(caught.value)


@pytest.mark.parametrize("stray", ["--nothing-like-it", "stray", "-x"])
def test_a_word_that_is_no_flag_is_refused(stray: str) -> None:
    s = settings()
    with pytest.raises(s.SettingsError) as caught:
        s.settings_from_init_args([stray, *words_of(command(doc()))])
    assert_one_line(caught.value)


def test_a_flag_with_no_value_is_refused() -> None:
    s = settings()
    words = words_of(command(doc()))
    with pytest.raises(s.SettingsError) as caught:
        s.settings_from_init_args([*words, flag_for("search.runs")])
    assert_one_line(caught.value)


@pytest.mark.parametrize("word", ["none", "None", "NONE"])
def test_none_given_to_the_outcomes_or_the_own_check_sets_nothing(word: str) -> None:
    """The word `none`, in any case, is no outcomes and no check of your own: what leaving the flag out gives."""
    s = settings()
    words = words_of(command(doc()))
    plain = s.settings_from_init_args(words)
    for key in ("fails.outcomes", "fails.own"):
        assert s.settings_from_init_args([*words, flag_for(key), word]) == plain, key


def test_an_outcome_that_is_the_word_none_still_round_trips() -> None:
    """An outcome your agent reports as the word itself is kept: the command writes it as TOML, so it is not read
    back as no outcomes."""
    s = settings()
    text = doc(fails='outcomes = ["none"]')
    line = command(text)
    assert s.settings_from_init_args(words_of(line)) == s.loads(text), line
