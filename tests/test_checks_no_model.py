"""No model grades a run. Spec §4, and plan §2's items on statistics and sockets as they fall on this module.

Every kind is computed from what the agent did. A user's own check may call a model, and that is the user's; nothing in
Break's module does, can, or knows how. Held three ways, since each misses what the others catch: what the source
imports, what judging tries to load when it runs, and whether judging tries to reach anything.
"""

from __future__ import annotations

import ast
import importlib.util
import textwrap
from pathlib import Path

from tests.checks_support import checks
from tests.conftest import REPO, run_python

# What a model call has to come through: every provider client, and every way of speaking HTTP from Python.
CLIENTS = {"anthropic", "openai", "litellm", "cohere", "mistralai", "google", "vertexai", "groq", "ollama",
           "together", "replicate", "boto3", "botocore", "huggingface_hub", "transformers", "langchain",
           "langchain_core", "langchain_openai", "langchain_anthropic", "instructor", "dspy"}
WIRES = {"socket", "ssl", "http", "urllib", "urllib3", "requests", "httpx", "aiohttp", "websockets", "grpc", "subprocess"}


def _source() -> Path:
    spec = importlib.util.find_spec("poisson_break.checks")
    assert spec is not None and spec.origin is not None, "the module is not there"
    return Path(spec.origin)


def _imported(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module.split(".")[0])
    return found


def test_the_module_imports_no_model_client_and_nothing_that_speaks_to_one() -> None:
    """Read from the source, at any depth, so an import inside a function is seen too."""
    bad = _imported(_source()) & (CLIENTS | WIRES)
    assert not bad, bad


def test_the_module_ships_no_judge_by_any_name() -> None:
    """§4: "Break ships no judge". Public names that would be one: a grader, a scorer, or an endpoint or a key for one."""
    words = ("grade", "grader", "scorer", "llm", "prompt", "api_key", "endpoint", "completion")
    assert not [name for name in dir(checks()) if any(w in name.lower() for w in words)]


REFUSING = textwrap.dedent("""
    import os, sys, importlib.abc

    # Every client and wire below, tried from Break's own code by any route, one built from a string at run time
    # included, which reading the source cannot see. A library Break uses may try its own optional imports, and that
    # is not Break's doing. A key is set too: a module that graded when it could would try now.
    BANNED = set({banned!r})
    CLIENTS = set({clients!r})
    os.environ["OPENAI_API_KEY"] = "not-a-real-key"
    os.environ["ANTHROPIC_API_KEY"] = "not-a-real-key"

    class Refuses(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in BANNED:
                frame = sys._getframe(1)
                while frame is not None and "importlib" in frame.f_code.co_filename:
                    frame = frame.f_back
                if frame is not None and "poisson_break" in frame.f_code.co_filename:
                    print("TRIED", name)
                    raise ImportError(name)
            return None

    sys.meta_path.insert(0, Refuses())

    from tests.apply_support import CASE, Tool
    from tests.checks_support import all_tools, kind_of, judged, lines_of, plain, checks, way_in, LIMIT, SLEEP

    runs = [
        way_in(),
        way_in(tools=dict(all_tools(), lookup_order=Tool(raises=LookupError("down")))),
        way_in(pause=SLEEP, fails=dict(run_seconds=LIMIT)),
        way_in(max_steps=1),
        plain("gives_up", fails=dict(never_call=["check_policy"])),
        plain("follows_plant", "tool:lookup_order#1=planted_instruction"),
        plain("repeats_write", "tool:issue_refund#1=lost_reply"),
        way_in(outcome="unresolved", fails=dict(outcomes=["unresolved"])),
        way_in(case=lines_of(CASE, reply_contains="never said")),
        plain("gives_up", "tool:lookup_order#1=error", fails=dict(also=["gave_up"])),
    ]
    print("kinds", " ".join(str(kind_of(judged(scene.run))) for scene in runs[:9]))
    for scene in runs:
        checks().signals(scene.run)
    print("loaded", sorted(name for name in sys.modules if name.split(".")[0] in CLIENTS))
""")


def test_every_kind_is_decided_with_no_model_client_within_reach() -> None:
    """Run for real in a fresh interpreter. Whatever `poisson_break` tried to import from either list is printed, and
    a verdict of every kind has to be reached anyway, with no client loaded by anything at the end of it."""
    ran = run_python(REFUSING.format(banned=sorted(CLIENTS | WIRES), clients=sorted(CLIENTS)), cwd=REPO)
    assert ran.exit == 0, ran.stderr
    assert "TRIED" not in ran.stdout, ran.stdout
    lines = dict(line.split(" ", 1) for line in ran.stdout.strip().splitlines())
    assert lines["kinds"].split() == ["None", "crashed", "hung", "ran_out", "forbidden_call", "followed_plant",
                                      "duplicate_write", "failed", "wrong"]
    assert lines["loaded"] == "[]"


def test_judging_tries_to_reach_nothing() -> None:
    """The suite's own guard fails any connection, and a judge that dialled out and swallowed the failure would look
    like one that did not. So the attempt is counted here, on a run that meets a kind, a signal and a promotion."""
    code = textwrap.dedent("""
        import socket

        tried = []
        def note(name):
            def noted(*a, **k):
                tried.append(name)
                raise OSError("no")
            return noted
        socket.socket.connect = note("connect")
        socket.socket.connect_ex = note("connect_ex")
        socket.create_connection = note("create_connection")
        socket.getaddrinfo = note("getaddrinfo")

        from tests.checks_support import checks, judged, plain

        scene = plain("repeats_write", "tool:issue_refund#1=lost_reply", outcome="x",
                      fails=dict(outcomes=["x"], never_call=["issue_refund"], also=["gave_up"]))
        judged(scene.run)
        checks().signals(scene.run)
        print("tried", tried)
    """)
    ran = run_python(code, cwd=REPO)
    assert ran.exit == 0, ran.stderr
    assert ran.stdout.strip() == "tried []"
