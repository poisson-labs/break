"""Numbers read the same everywhere, and commands read back.

Invariant pinned here (Break — Plan, the look layer):
- BK12.8  Rates and p-values to three decimals (`2.3e-08` below 0.001), dollars as `$1.00` or two significant
          digits below $0.10, counts with thousands separators, durations as `1 min 40 s`, times in UTC with `Z`,
          hashes at 12 characters in text and in full in JSON.

Every expected value is the standard's own example, or follows from it with no further choice. Where the standard is
silent (a duration of exactly one minute, no dollars at all, a time with no zone) nothing is pinned, and the answer
waits on its ruling. So does `$0.004`, which the spec's example writes against the standard's rule.

And `word` and `command`: a word as a shell reads it back, and a command line that pastes as one.
"""

from __future__ import annotations

import shlex
import subprocess
from datetime import UTC, datetime, timedelta, timezone

import pytest

from tests.look_support import look


@pytest.mark.parametrize("value, text", [(0.15, "0.150"), (0.0, "0.000"), (1.0, "1.000"), (0.945, "0.945"), (0.1234, "0.123"),
                                         (0.1239, "0.124"), (0.073, "0.073")])
def test_a_rate_has_three_decimals(value: float, text: str) -> None:
    assert look().fmt_rate(value) == text


@pytest.mark.parametrize("value, text", [(0.049, "0.049"), (0.412, "0.412"), (1.0, "1.000"), (0.001, "0.001"), (0.0012, "0.001"),
                                         (0.05, "0.050")])
def test_a_p_value_has_three_decimals(value: float, text: str) -> None:
    assert look().fmt_p(value) == text


@pytest.mark.parametrize("value, text", [(2.3e-08, "2.3e-08"), (0.00099, "9.9e-04"), (1.5e-12, "1.5e-12"), (2.3456e-05, "2.3e-05")])
def test_a_p_value_below_a_thousandth_has_an_exponent(value: float, text: str) -> None:
    assert look().fmt_p(value) == text


def test_a_p_value_never_reads_as_zero() -> None:
    assert look().fmt_p(1e-300) != "0.000"


@pytest.mark.parametrize("value, text", [(1.0, "$1.00"), (5.0, "$5.00"), (1.6, "$1.60"), (0.88, "$0.88"), (0.1, "$0.10")])
def test_dollars_from_ten_cents_have_two_decimals(value: float, text: str) -> None:
    assert look().fmt_dollars(value) == text


@pytest.mark.parametrize("value, text", [(0.021, "$0.021"), (0.0052, "$0.0052"), (0.099, "$0.099"), (0.012, "$0.012"), (0.00031, "$0.00031"), (0.0214, "$0.021"), (0.00526, "$0.0053")])
def test_dollars_below_ten_cents_have_two_significant_digits(value: float, text: str) -> None:
    assert look().fmt_dollars(value) == text


@pytest.mark.parametrize("value, text", [(4200, "4,200"), (0, "0"), (999, "999"), (1000, "1,000"), (1234567, "1,234,567"), (10496, "10,496")])
def test_a_count_has_thousands_separators(value: int, text: str) -> None:
    assert look().fmt_count(value) == text


@pytest.mark.parametrize("seconds, text", [(100, "1 min 40 s"), (5760, "1 h 36 min"), (61, "1 min 1 s"), (3599, "59 min 59 s"), (3660, "1 h 1 min"), (7380, "2 h 3 min")])
def test_a_duration_reads_as_the_standard_writes_it(seconds: float, text: str) -> None:
    assert look().fmt_duration(seconds) == text


def test_a_duration_past_an_hour_says_no_seconds() -> None:
    assert look().fmt_duration(5761) == "1 h 36 min"


@pytest.mark.parametrize("when", [
    datetime(2026, 11, 4, 18, 0, 5, tzinfo=UTC),
    datetime(2026, 11, 4, 13, 0, 5, tzinfo=timezone(timedelta(hours=-5))),
    datetime(2026, 11, 5, 3, 30, 5, tzinfo=timezone(timedelta(hours=9, minutes=30))),
], ids=["utc", "behind", "ahead"])
def test_a_time_is_in_utc_with_a_z(when: datetime) -> None:
    text = look().fmt_time(when)
    assert text.endswith("Z"), text
    assert "+" not in text and text.count("-") == 2, text
    assert datetime.fromisoformat(text.replace("Z", "+00:00")) == datetime(2026, 11, 4, 18, 0, 5, tzinfo=UTC)


def test_a_hash_is_twelve_characters() -> None:
    full = "0123456789abcdef0123456789abcdef"
    assert look().fmt_hash(full) == "0123456789ab"


# ---------- word and command ----------

ROUND_TRIPS = ["plain", "with space", "two  spaces", "it's", 'say "hi"', "$HOME", "`date`", "back\\slash", "a!b", "!", "a;b", "a|b",
               "a&b", "*", "?", "~", "", "-dash", "--flag", "=x", "a=b", "é", "tab\there", "line\nbreak", "#comment", "(x)", "tool:lookup_order#1=timeout"]


@pytest.mark.parametrize("text", ROUND_TRIPS)
def test_a_word_reads_back_as_itself_in_a_real_shell(text: str) -> None:
    """One word, whatever it holds: the shell counts one argument and reads it back."""
    script = f'set -- {look().word(text)}; printf "%s:%s" "$#" "$1"'
    done = subprocess.run(["sh", "-c", script], capture_output=True, text=True, check=True)
    assert done.stdout == f"1:{text}"


@pytest.mark.parametrize("text", ["plain", "path/to/file.toml", "a:b", "1.5", "a_b-c", "input:cut_short"])
def test_a_word_that_needs_no_quoting_is_left_bare(text: str) -> None:
    """Commands stay readable."""
    assert look().word(text) == text


def test_a_command_is_its_words_joined() -> None:
    k = look()
    assert str(k.command("poisson-break", "findings", "2")) == "poisson-break findings 2"


def test_a_command_reads_back_as_its_words() -> None:
    k = look()
    made = k.command("poisson-break", "--name", k.word("a name with spaces"), "--note", k.word('say "hi"'))
    assert shlex.split(str(made)) == ["poisson-break", "--name", "a name with spaces", "--note", 'say "hi"']


def test_a_command_can_stand_wherever_text_can() -> None:
    """A `next:` line, a row's value and an f-string all take one."""
    made = look().command("tool", "again")
    assert isinstance(made, str)
    assert f"{made}" == "tool again"
