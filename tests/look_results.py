"""The look's corpus of results: what Break's verbs print, built through the look's public names.

Each is a small function, called at run time, so a tree without the look fails test by test. The words
and shapes follow the spec's command table and examples. The figures are invented, as the spec's are.
Every `render` test and every run of the conformance test walks these.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any


def _look() -> Any:
    return importlib.import_module("poisson_break.look")


def plan_hunt() -> Any:
    k = _look()
    return k.Plan(
        "a hunt of refund-agent on 12 cases, at most 400 runs",
        estimate="not known until the control stage has run; the cap is $5.00",
        source="the control stage",
        detail=(
            k.Row("target", "my_app.agents:refund_agent (openai-agents)"),
            k.Row("tools", "lookup_order (read), check_policy (read), issue_refund (write, stand-in)"),
            k.Row("may change", "tool behaviour (10 faults), inputs (5 operators)"),
            k.Row("strategy", "screen"),
            k.Row("stages", "control 60 runs, search and shrink up to 340"),
        ),
    )


def plan_confirm() -> Any:
    k = _look()
    return k.Plan(
        "confirm 4 candidates against a control",
        estimate=f"about {k.fmt_dollars(1.10)}, then up to {k.fmt_dollars(0.88)}",
        source="the control stage's cost per run",
        detail=(k.Row("design", "11 cases × 5 repeats · 275 runs"),
                k.Row("reference", "up to 220 more runs, 55 for each candidate that is confirmed")),
    )


def found() -> Any:
    k = _look()
    return k.Result(
        "found",
        f"4 candidates in {k.fmt_count(4200)} runs ({k.fmt_dollars(1.60)})",
        detail=(
            k.Table(("", "condition", "failed", "kind"), (
                ("1", "tool:lookup_order#1=timeout", "4 of 4", "ran_out"),
                ("2", "tool:check_policy#1=planted_instruction", "3 of 4", "followed_plant"),
                ("3", "tool:issue_refund#1=lost_reply", "3 of 4", "duplicate_write"),
                ("4", "input:cut_short", "2 of 4", "wrong"),
            )),
            k.Line("not looked at: call numbers past 3; every pair of changes; 1 case set aside"),
            k.Line("these are candidates, not findings: a few runs each, chosen for having failed"),
        ),
        nexts=(k.command("poisson-break", "confirm"),),
    )


def nothing_found() -> Any:
    k = _look()
    return k.Result(
        "nothing found",
        f"no condition failed more than the control in {k.fmt_count(400)} runs",
        detail=(k.Line("not looked at: call numbers past 3; every pair of changes"),),
    )


def confirmed() -> Any:
    k = _look()
    return k.Result(
        "confirmed",
        f"3 of 4 candidates fail more than the control ({k.fmt_rate(0.073)})",
        detail=(
            k.Table(("", "condition", "verdict", "rate"), (
                ("1", "tool:lookup_order#1=timeout", "confirmed", k.fmt_rate(0.945)),
                ("2", "tool:check_policy#1=planted_instruction", "confirmed", k.fmt_rate(0.618)),
                ("3", "input:cut_short", "too small to tell", k.fmt_rate(0.164)),
            )),
            k.Row("wrote", "break-runs/refund-agent-1/findings/1.toml, 2.toml, 3.toml"),
        ),
        nexts=(k.command("poisson-break", "findings", "1"),),
    )


def catalogue() -> Any:
    k = _look()
    return k.Result(
        "ok",
        "15 changes Break knows",
        detail=(
            k.Table(("name", "what it does"), (
                ("timeout", "the tool never answers within the wait"),
                ("cut_off", "the answer is cut part way through"),
                ("input:typos", "typos in what the user asks"),
            )),
        ),
    )


def ready() -> Any:
    k = _look()
    return k.Result("ready", "the settings and the target are fine",
                    detail=(k.Row("settings", "break.toml"),
                            k.Row("target", "my_app.agents:refund_agent, 3 tools")),
                    nexts=(k.command("poisson-break", "hunt"),))


def not_ready() -> Any:
    k = _look()
    return k.Result("not ready", "the tool issue_refund changes things outside and has no stand-in",
                    detail=(k.Row("settings", "break.toml"),),
                    nexts=(k.command("poisson-break", "doctor"),))


def stopped() -> Any:
    k = _look()
    return k.Result("stopped", f"at the cap of {k.fmt_dollars(5.0)} after {k.fmt_duration(100)}",
                    detail=(k.Row("kept", "312 runs in break-runs/refund-agent-1"),),
                    nexts=(k.command("poisson-break", "hunt", "--resume"),))


def too_small() -> Any:
    k = _look()
    return k.Result("too small to tell", f"14 repeats would decide; p {k.fmt_p(0.164)}",
                    detail=(k.Row("difference", k.fmt_rate(0.07)),))


def rechecked() -> Any:
    k = _look()
    return k.Result(
        "rechecked", "1 of 2 findings fails less on the changed agent",
        detail=(k.Table(("", "condition", "verdict", "p"), (
            ("1", "tool:lookup_order#1=timeout", "fails less", k.fmt_p(2.3e-08)),
            ("2", "input:cut_short", "no significant difference", k.fmt_p(0.412)),
        )),),
    )


def replayed() -> Any:
    k = _look()
    return k.Result(
        "failed", "the agent ran out of turns under this condition",
        detail=(k.Row("condition", "tool:lookup_order#1=timeout"),
                k.Row("took", k.fmt_duration(5760)),
                k.Row("at", "2 calls · 1 retried – none written")),
    )


def wrote() -> Any:
    k = _look()
    return k.Result("wrote", "break.toml", nexts=(k.command("poisson-break", "doctor"),))


def verdict_only() -> Any:
    return _look().Result("ok", "no findings yet")


RESULTS: dict[str, Callable[[], Any]] = {
    "plan-hunt": plan_hunt,
    "plan-confirm": plan_confirm,
    "found": found,
    "nothing-found": nothing_found,
    "confirmed": confirmed,
    "catalogue": catalogue,
    "ready": ready,
    "not-ready": not_ready,
    "stopped": stopped,
    "too-small": too_small,
    "rechecked": rechecked,
    "replayed": replayed,
    "wrote": wrote,
    "verdict-only": verdict_only,
}
