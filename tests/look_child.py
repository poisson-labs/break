"""A small program that prints through the look as a verb will, for the look's tests.

    python tests/look_child.py result NAME [--plain] [--json]   one result of `look_results`
    python tests/look_child.py refuse [--plain]                 a refusal, with a command to run next
    python tests/look_child.py usage [--plain]                  a wrong command line
    python tests/look_child.py warn [--plain]                   a result and a warning
    python tests/look_child.py crash [--plain]                  an unexpected failure

It computes nothing of its own: `mode_for`, `render` and `run` decide everything it prints.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from poisson_break import look  # noqa: E402

from tests.look_results import RESULTS  # noqa: E402

words = sys.argv[1:]


def show(result: object) -> None:
    if "--json" in words:
        sys.stdout.write(look.as_json(result))
        sys.stdout.flush()
    else:
        look.render(result, stream=sys.stdout, mode=look.mode_for(sys.stdout, sys.stderr, os.environ, words))


def body() -> None:
    scene = words[0]
    if scene == "result":
        show(RESULTS[words[1]]())
    elif scene == "refuse":
        raise look.Refused("the tool issue_refund changes things outside and has no stand-in",
                           nexts=(look.command("poisson-break", "doctor"),))
    elif scene == "usage":
        raise look.Usage("no verb named hnut; the verbs are hunt, confirm and doctor",
                         nexts=(look.command("poisson-break", "--help"),))
    elif scene == "warn":
        look.note("Break calls your tools for real.")
        show(RESULTS["ready"]())
    elif scene == "crash":
        raise ValueError("raw library text")
    else:
        raise look.Usage(f"no scene named {scene}")


if __name__ == "__main__":
    sys.exit(look.run("poisson-break", words, body))
