"""The three ASCII stand-ins, pinned as the look writes them.

Plan BK12.9 and the look's build, ruling 26 (`evidence/bk12/build-choices.md`, ruled 2026-11-05): on a stream that
cannot encode them, `·`, `–` and `×` are written `-`, `-` and `x`, one character each. The look's frozen tests count a
stand-in as one character and never spell it, so a build that wrote `dot`, `dash` and `times` passed all of them (the
surviving planted mistake A05, `evidence/bk12/planted-survivors.md`). This one new test spells them. No frozen test is
changed. It is green the day it lands, since the build already writes them.
"""

from __future__ import annotations

import io

from tests.look_support import PIPED, look, pretty_env, run_body


def test_the_three_glyphs_are_written_dash_dash_and_x_on_a_stream_that_cannot_encode_them() -> None:
    """In this process, on a stream of ASCII bytes; and in a child whose stdout is a pipe encoded as ASCII, the way a
    user's `PYTHONIOENCODING` or locale makes one. A row's value and a table's cell are written the same way, and the
    UTF-8 control keeps each glyph as it is."""
    sentence = "11 cases × 5 repeats · 275 runs – 3 stages"
    result = look().Result("ok", sentence, detail=(look().Row("design", "5 × 2 · 10 runs"),
                                                   look().Table(("width", "runs"), (("2 × 3", "6 – 1"),))))

    def rendered(encoding: str) -> bytes:
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding=encoding, errors="strict", newline="\n")
        look().render(result, stream=stream, mode="plain")
        stream.flush()
        return raw.getvalue()

    ascii_text = rendered("ascii").decode("ascii")
    first, *rest = ascii_text.splitlines()
    assert first == "ok  11 cases x 5 repeats - 275 runs - 3 stages"
    assert any(line.split() == ["design", "5", "x", "2", "-", "10", "runs"] for line in rest), ascii_text
    assert any(line.split() == ["2", "x", "3", "6", "-", "1"] for line in rest), ascii_text
    utf8_text = rendered("utf-8").decode("utf-8")
    assert utf8_text.splitlines()[0] == f"ok  {sentence}"
    assert ascii_text == utf8_text.replace("×", "x").replace("·", "-").replace("–", "-")

    body = (f"look.render(look.Result('ok', {sentence!r}), stream=sys.stdout, mode='plain')")
    ran = run_body(body, streams=PIPED, env=pretty_env(PYTHONIOENCODING="ascii"))
    assert ran.exit == 0, ran
    assert ran.out == "ok  11 cases x 5 repeats - 275 runs - 3 stages\n", ran
