"""One result, two renderings, and the verdict line first.

Invariants pinned here (Break — Plan, the look layer):
- BK12.1  For every result in the corpus, the plain and the pretty rendering carry the same facts in the same
          order; piped, the two are byte-identical.
- BK12.4  The verdict line is first on stdout, `^[a-z][a-z ]*  \\S`, in both renderings and in `--json`'s
          `verdict` and `sentence`.

Facts are compared as words and numbers in their order, so a border, a padding or a column's width can change
with nothing wrong. Plain's own shape is pinned where the standard writes it: a verdict line, `label  value`
lines indented two spaces, `next:` commands last.
"""

from __future__ import annotations

import io
import re
from typing import Any

import pytest

from tests.look_results import RESULTS
from tests.look_support import (
    BOX,
    TERMINALS,
    VERDICT_LINE,
    Streams,
    line,
    look,
    plan,
    result,
    row,
    run_body,
    run_result,
    strict_json,
    strip,
    table,
    words_of,
)

NAMES = list(RESULTS)


def plain_of(res: Any) -> str:
    stream = io.StringIO()
    look().render(res, stream=stream, mode="plain")
    return stream.getvalue()


# ---------- the same facts in the same order ----------


@pytest.mark.parametrize("name", NAMES)
def test_pretty_on_a_terminal_carries_plains_facts_in_plains_order(name: str) -> None:
    """Wide enough that nothing folds."""
    plain = run_result(name, streams=Streams(columns=160))
    pretty = run_result(name, streams=Streams(out="pty", err="pty", columns=160))
    assert plain.exit == pretty.exit == 0, pretty
    assert "\x1b[" in pretty.out, "this is not the pretty rendering"
    assert words_of(pretty.out) == words_of(plain.out)


@pytest.mark.parametrize("name", NAMES)
def test_a_rendering_given_a_pipe_is_plain_byte_for_byte(name: str) -> None:
    """Piped, the two renderings are byte-identical, whichever one is asked for."""
    plain = io.StringIO()
    pretty = io.StringIO()
    res = RESULTS[name]()
    look().render(res, stream=plain, mode="plain")
    look().render(res, stream=pretty, mode="pretty")
    assert plain.getvalue()
    assert pretty.getvalue() == plain.getvalue()


@pytest.mark.parametrize("name", NAMES)
def test_plain_is_text_with_no_escape_and_no_box(name: str) -> None:
    text = plain_of(RESULTS[name]())
    assert "\x1b" not in text
    assert not BOX.search(text)
    assert text.endswith("\n") and not text.endswith("\n\n")


@pytest.mark.parametrize("name", NAMES)
def test_plain_on_a_terminal_has_no_escape_and_no_box(name: str) -> None:
    ran = run_result(name, ["--plain"], streams=TERMINALS)
    assert ran.exit == 0, ran
    assert "\x1b" not in ran.out and not BOX.search(ran.out), ran
    assert words_of(ran.out) == words_of(run_result(name).out)


def test_rendering_twice_prints_the_same_thing() -> None:
    """A result is data: rendering it does not use it up, on either side of the switch."""
    res = RESULTS["found"]()
    assert plain_of(res) == plain_of(res)


def test_a_result_can_be_rendered_to_any_stream_it_is_given(capsys: pytest.CaptureFixture[str]) -> None:
    stream = io.StringIO()
    look().render(result("ok", "fine 3"), stream=stream, mode="plain")
    out, err = capsys.readouterr()
    assert stream.getvalue() == "ok  fine 3\n"
    assert (out, err) == ("", "")


def test_a_wrong_mode_is_refused() -> None:
    """A mode that is neither of the two is a mistake in the caller and must not pass for one of them."""
    with pytest.raises(ValueError):
        look().render(result("ok", "fine"), stream=io.StringIO(), mode="fancy")


# ---------- what plain's lines are ----------


def test_the_verdict_line_is_the_word_two_spaces_and_the_sentence() -> None:
    assert plain_of(result("too small to tell", "14 repeats would decide")) == "too small to tell  14 repeats would decide\n"


def test_a_row_is_indented_two_spaces_with_two_spaces_after_its_label() -> None:
    text = plain_of(result("ok", "fine", [row("target", "my_app.agents:refund_agent")]))
    assert re.fullmatch(r"ok  fine\n {2}target {2,}my_app\.agents:refund_agent\n", text), text


def test_rows_keep_their_order_and_all_are_there() -> None:
    labels = ["zeta", "alpha", "mid", "beta"]
    text = plain_of(result("ok", "fine", [row(label, f"value of {label}") for label in labels]))
    found = re.findall(r"^ {2}(\w+) {2,}value of (\w+)$", text, flags=re.M)
    assert found == [(label, label) for label in labels]


def test_a_labels_column_lines_up_without_breaking_the_two_spaces() -> None:
    """However rows align, a short label still has at least two spaces, and a long one too."""
    text = plain_of(result("ok", "fine", [row("a", "one"), row("a much longer label", "two")]))
    assert re.search(r"^ {2}a {2,}one$", text, flags=re.M), text
    assert re.search(r"^ {2}a much longer label {2,}two$", text, flags=re.M), text


def test_next_commands_come_last_each_on_its_line() -> None:
    text = plain_of(result("ok", "fine", [row("a", "b"), line("a sentence here")], nexts=["tool one", "tool two"]))
    lines = text.splitlines()
    assert re.fullmatch(r"\s*next: tool one", lines[-2]), text
    assert re.fullmatch(r"\s*next: tool two", lines[-1]), text
    assert lines.index(lines[-2]) > max(i for i, t in enumerate(lines) if "a sentence here" in t or "b" in t.split())


def test_detail_keeps_the_order_it_was_given_across_kinds() -> None:
    text = plain_of(result("ok", "fine", [
        line("first sentence"), row("second", "row"), table(("third", "col"), [("cell", "value")]), line("fourth sentence"),
    ]))
    words = words_of(text)
    assert words.index("first") < words.index("second") < words.index("third") < words.index("fourth")


def test_a_table_prints_its_header_and_each_row_on_a_line_with_its_cells_in_order() -> None:
    res = result("ok", "fine", [table(("name", "rate"), [("alpha", "0.150"), ("beta", "0.900")])])
    lines = plain_of(res).splitlines()
    assert any(re.search(r"name.*rate", text) for text in lines)
    assert any(re.search(r"alpha.*0\.150", text) for text in lines)
    assert any(re.search(r"beta.*0\.900", text) for text in lines)
    alpha = next(i for i, t in enumerate(lines) if "alpha" in t)
    beta = next(i for i, t in enumerate(lines) if "beta" in t)
    assert alpha < beta


def test_a_verdict_with_nothing_else_is_one_line() -> None:
    assert plain_of(result("ok", "no findings yet")) == "ok  no findings yet\n"


# ---------- the plan ----------


def test_a_plan_opens_with_its_word_and_names_its_estimate_and_its_source() -> None:
    res = plan("a hunt on 12 cases", "about $1.10", "the control stage's cost per run", [row("target", "my_app")])
    text = plain_of(res)
    head = VERDICT_LINE.match(text.splitlines()[0])
    assert head and head.groups() == ("plan", "a hunt on 12 cases")
    assert "about $1.10" in text
    assert "the control stage's cost per run" in text
    assert "my_app" in text


def test_a_plan_is_a_result() -> None:
    assert isinstance(plan("x", "y", "z"), look().Result)
    assert plan("x", "y", "z").verdict == "plan"
    assert plan("x", "y", "z").sentence == "x"


def test_a_plans_estimate_and_source_are_in_both_renderings_and_in_its_json() -> None:
    body = 'show(look.Plan("a hunt", estimate="about $1.10", source="the price table", detail=(), schema="x/1"))'
    ran = run_body(body, streams=TERMINALS)
    assert ran.exit == 0, ran
    text = strip(ran.out)
    assert "about $1.10" in text and "the price table" in text, ran
    document = strict_json(run_body(body, ["--json"]).out)
    assert "about $1.10" in str(document) and "the price table" in str(document), document


# ---------- the verdict line ----------


@pytest.mark.parametrize("name", NAMES)
def test_the_first_line_is_the_verdict_line_in_every_rendering(name: str) -> None:
    res = RESULTS[name]()
    piped = run_result(name)
    terminal = run_result(name, streams=TERMINALS)
    head = piped.out.split("\n", 1)[0]
    drawn = strip(terminal.out).split("\n", 1)[0]
    assert VERDICT_LINE.fullmatch(head), head
    assert VERDICT_LINE.fullmatch(drawn), drawn
    assert VERDICT_LINE.fullmatch(head).groups() == (res.verdict, res.sentence)  # type: ignore[union-attr]
    assert VERDICT_LINE.fullmatch(drawn).groups() == (res.verdict, res.sentence)  # type: ignore[union-attr]


@pytest.mark.parametrize("name", NAMES)
def test_json_carries_the_same_word_and_sentence_first(name: str) -> None:
    res = RESULTS[name]()
    res = _with_schema(res)
    document = strict_json(look().as_json(res))
    assert list(document)[:3] == ["schema", "verdict", "sentence"]
    assert (document["verdict"], document["sentence"]) == (res.verdict, res.sentence)


def _with_schema(res: Any) -> Any:
    return look().Result(res.verdict, res.sentence, detail=res.detail, nexts=res.nexts, schema="poisson-break.test/1")


def test_a_long_sentence_stays_whole_on_the_first_line_in_pretty() -> None:
    """On a narrow terminal, with escapes removed, the first line still carries the whole sentence."""
    sentence = "a sentence far longer than the terminal is wide, so that a rendering would be tempted to break it"
    ran = run_body(f'show(look.Result("ok", {sentence!r}))', streams=Streams(out="pty", err="pty", columns=40))
    assert ran.exit == 0, ran
    assert strip(ran.out).split("\n", 1)[0] == f"ok  {sentence}"


def test_two_results_print_one_after_the_other_with_the_first_still_first() -> None:
    """`hunt` prints its plan, then what it found. Each keeps its own verdict line."""
    ran = run_body('show(look_results.RESULTS["plan-hunt"]())\nshow(look_results.RESULTS["found"]())')
    assert ran.exit == 0, ran
    lines = ran.out.splitlines()
    assert lines[0].startswith("plan  ")
    assert any(text.startswith("found  ") for text in lines[1:])


# ---------- JSON ----------


def test_json_is_one_strict_document_and_carries_the_data() -> None:
    res = result("ok", "fine", schema="poisson-break.test/1", data={"runs": 400, "rate": 0.15, "names": ["a", "b"]})
    document = strict_json(look().as_json(res))
    assert document["schema"] == "poisson-break.test/1"
    assert document["runs"] == 400 and document["rate"] == 0.15 and document["names"] == ["a", "b"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")], ids=["nan", "inf", "-inf"])
def test_json_never_writes_nan_or_infinity(value: float) -> None:
    """Refusing the document or writing `null` are both within the rule; a bare `NaN` is not."""
    res = result("ok", "fine", schema="poisson-break.test/1", data={"nested": {"value": value}, "list": [value]})
    try:
        document = look().as_json(res)
    except ValueError:
        return
    strict_json(document)


def test_a_hash_is_whole_in_json_and_twelve_characters_in_text() -> None:
    full = "0123456789abcdef" * 4
    res = result("ok", "fine", [row("stored as", look().fmt_hash(full))], schema="poisson-break.test/1", data={"hash": full})
    assert strict_json(look().as_json(res))["hash"] == full
    text = plain_of(res)
    assert full[:12] in text and full[:13] not in text


# ---------- what a value holds is printed as it is ----------

AWKWARD = "the file [red]a/b[/red].toml holds :warning: 3 of [4] at 0.150 'quoted' http://x.io/y 192.168.0.1 True None"


@pytest.mark.parametrize("where", ["sentence", "row", "line", "table", "next"])
def test_pretty_prints_a_value_as_it_is(where: str) -> None:
    """Rich reads `[red]` as markup and `:warning:` as an emoji, and paints numbers and paths, unless told
    not to. A name a user chose, or a path, is printed as written."""
    if where == "sentence":
        build = f'look.Result("ok", {AWKWARD!r})'
    elif where == "row":
        build = f'look.Result("ok", "x", detail=(look.Row("label", {AWKWARD!r}),))'
    elif where == "line":
        build = f'look.Result("ok", "x", detail=(look.Line({AWKWARD!r}),))'
    elif where == "table":
        build = f'look.Result("ok", "x", detail=(look.Table(("a", "b"), (("c", {AWKWARD!r}),)),))'
    else:
        build = f'look.Result("ok", "x", nexts=({AWKWARD!r},))'
    ran = run_body(f"show({build})", streams=Streams(out="pty", err="pty", columns=160))
    assert ran.exit == 0, ran
    assert AWKWARD in strip(ran.out), ran


def test_plain_prints_a_value_as_it_is_too() -> None:
    assert AWKWARD in plain_of(result("ok", AWKWARD))
    assert AWKWARD in plain_of(result("ok", "x", [row("label", AWKWARD)]))


@pytest.mark.parametrize("mode_words", [[], ["--plain"]], ids=["pretty", "plain"])
def test_an_escape_in_a_value_acts_on_nothing(mode_words: list[str]) -> None:
    """A name holding an escape sequence is shown, not obeyed: it must not reach the terminal as one."""
    value = "name\\x1b[35mred\\x1b]0;title\\x07"
    body = f'show(look.Result("ok", "the run {value}", detail=(look.Row("name", "{value}"),), nexts=("tool {value}",)))'
    ran = run_body(body, mode_words, streams=TERMINALS)
    assert ran.exit == 0, ran
    assert "\x1b[35m" not in ran.out and "\x1b]0" not in ran.out, repr(ran.out)
    assert "\x07" not in ran.out, repr(ran.out)


# ---------- as ruled ----------


@pytest.mark.parametrize("verdict", ["Done", "a  b", "", " ok", "ok!", "1ok", "a\nb"],
                         ids=["capital", "two-spaces", "empty", "leading-space", "mark", "digit", "line-break"])
def test_a_verdict_that_could_not_make_the_line_is_refused_when_made(verdict: str) -> None:
    with pytest.raises(ValueError):
        result(verdict, "a sentence")


@pytest.mark.parametrize("sentence", ["", "   "], ids=["empty", "blank"])
def test_a_sentence_that_could_not_make_the_line_is_refused_when_made(sentence: str) -> None:
    with pytest.raises(ValueError):
        result("ok", sentence)


def test_a_verdict_of_several_words_is_made() -> None:
    assert result("too small to tell", "a sentence").verdict == "too small to tell"


NOTED_PLAN = ('show(look.Plan("a hunt of 12 cases", estimate="400 runs", source="the settings", detail=(look.Row("cost", "not known"),)))\n'
              'look.note("Break calls your tools for real")')


@pytest.mark.parametrize("words", [[], ["--plain"]], ids=["pretty", "plain"])
def test_a_plans_note_is_unindented_and_on_stderr_after_its_detail(words: list[str]) -> None:
    ran = run_body(NOTED_PLAN, words, streams=TERMINALS)
    assert ran.exit == 0, ran
    assert "note:" not in strip(ran.out), ran
    assert strip(ran.err) == "note: Break calls your tools for real\n", ran
    together = strip(run_body(NOTED_PLAN, words, streams=Streams(together=True)).out).splitlines()
    assert together[-1] == "note: Break calls your tools for real", together
    assert any("not known" in text for text in together[:-1]), together
