"""The ASCII fallback.

Invariant pinned here (Break — Plan, the look layer):
- BK12.9  When the stream cannot encode `·`, `–` or `×`, plain substitutes ASCII and the facts are unchanged.

The tests write to real encoded streams and ask that nothing fails, that nothing outside the stream's reach is
written, and that the words and numbers are the same. They do not pin which ASCII stands in for which glyph.

As ruled, a character of a name the user chose (`café`) is written as its escape, so it never reads as another name.
"""

from __future__ import annotations

import io

import pytest

from tests.look_results import RESULTS
from tests.look_support import Streams, look, pretty_env, result, row, run_body, run_result, table, words_of

GLYPHS = "11 cases × 5 repeats · 275 runs – 3 stages"


def assert_same_facts(written: str, whole: str) -> None:
    """Every word and number of the whole text is there in its order, and nothing else but what stands in for a glyph
    (`×` may become `x`, which reads as a word)."""
    ours, theirs = words_of(written), words_of(whole)
    glyphs = sum(whole.count(mark) for mark in "·–×")
    places = iter(ours)
    assert all(word in places for word in theirs), f"a word is lost:\n{written}\n{whole}"
    assert len(ours) - len(theirs) <= glyphs, f"words were added:\n{written}\n{whole}"


def _written(res: object, encoding: str, mode: str = "plain") -> str:
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding=encoding)
    look().render(res, stream=stream, mode=mode)
    stream.flush()
    return raw.getvalue().decode(encoding)


@pytest.mark.parametrize("encoding", ["ascii", "latin-1", "cp1252", "cp437"])
@pytest.mark.parametrize("where", ["sentence", "row", "table", "next"])
def test_each_place_a_glyph_can_be_falls_back(encoding: str, where: str) -> None:
    res = {
        "sentence": lambda: result("ok", GLYPHS),
        "row": lambda: result("ok", "x", [row("design", GLYPHS)]),
        "table": lambda: result("ok", "x", [table(("design",), [(GLYPHS,)])]),
        "next": lambda: result("ok", "x", nexts=[GLYPHS]),
    }[where]()
    assert_same_facts(_written(res, encoding), _written(res, "utf-8"))


@pytest.mark.parametrize("name", list(RESULTS))
def test_every_result_of_the_corpus_keeps_its_facts_in_ascii(name: str) -> None:
    written = _written(RESULTS[name](), "ascii")
    assert written.isascii()
    assert_same_facts(written, _written(RESULTS[name](), "utf-8"))


def test_utf8_keeps_the_glyphs() -> None:
    """The fallback is for a stream that cannot encode them, and only that."""
    assert GLYPHS in _written(result("ok", GLYPHS), "utf-8")


def test_a_stream_that_can_encode_a_glyph_keeps_it() -> None:
    """Latin-1 holds `·` and `×` and not `–`, so only the last is replaced."""
    written = _written(result("ok", GLYPHS), "latin-1")
    assert "×" in written and "·" in written and "–" not in written


def test_a_fallback_is_one_glyph_for_one_mark_so_a_line_keeps_its_shape() -> None:
    """A separator stays a separator: its neighbours do not run together."""
    written = _written(result("ok", GLYPHS), "ascii")
    assert len(written.split()) == len(f"ok {GLYPHS}".split()), written


@pytest.mark.parametrize("encoding", ["ascii", "latin-1"])
def test_end_to_end_a_result_on_such_a_stream_prints(encoding: str) -> None:
    ran = run_result("plan-confirm", env=pretty_env(PYTHONIOENCODING=encoding))
    assert ran.exit == 0, ran
    assert "Traceback" not in ran.err, ran
    assert_same_facts(ran.out, run_result("plan-confirm").out)


@pytest.mark.parametrize("encoding", ["ascii", "latin-1"])
def test_end_to_end_on_a_terminal_that_cannot_encode_them_plain_runs_and_falls_back(encoding: str) -> None:
    ran = run_result("plan-confirm", streams=Streams(out="pty", err="pty", columns=160), env=pretty_env(PYTHONIOENCODING=encoding))
    assert ran.exit == 0, ran
    assert "\x1b" not in ran.out and "Traceback" not in ran.err, ran
    assert "–" not in ran.out


@pytest.mark.parametrize("line", ['look.error("11 × 5 · 275 – 3", ["tool · again"])', 'look.note("11 × 5 · 275 – 3")',
                                  'look.out("11 × 5 · 275 – 3\\n")', 'look.err("11 × 5 · 275 – 3\\n")'],
                         ids=["error", "note", "out", "err"])
def test_problems_and_raw_text_fall_back_too(line: str) -> None:
    ran = run_body(line, env=pretty_env(PYTHONIOENCODING="ascii"))
    assert ran.exit == 0, ran
    assert "Traceback" not in ran.err, ran
    assert "unexpected failure" not in ran.err, ran
    text = ran.out + ran.err
    assert text.isascii()
    assert all(word in words_of(text) for word in ("11", "5", "275", "3")), text


def test_a_question_on_such_a_stream_is_asked_all_the_same() -> None:
    ran = run_body('look.ask("11 × 5?", "4 · 2")', streams=Streams(stdin="pty", keys=(b"\r",), out="pipe", err="pipe"),
                   env=pretty_env(PYTHONIOENCODING="ascii"))
    assert ran.exit == 0, ran
    assert ran.err.isascii()


def test_a_character_of_a_users_name_does_not_stop_the_line() -> None:
    written = _written(result("ok", "the run café has 3 cases"), "ascii")
    assert written.isascii()
    assert "the run" in written and "has 3 cases" in written


def test_a_character_of_a_users_name_is_written_as_its_escape() -> None:
    assert r"the run caf\xe9 has 3 cases" in _written(result("ok", "the run café has 3 cases"), "ascii")


def test_two_names_never_read_as_one() -> None:
    one, other = (_written(result("ok", f"the run {name}"), "ascii") for name in ("café", "cafè"))
    assert one != other
