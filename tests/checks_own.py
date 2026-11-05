"""A user's own checks, for the tests of spec §11.4. They live in their own module, outside the package, because a
check is named by an import path (`tests.checks_own:fails_it`) and loaded by that name, and they are the "test-only
implementation written outside the package" of spec §11: nothing in the core knows them.

`RETURNS` and `RAISES` say what `configured` does, `CALLS` holds what every check here was handed, `LAST` the view it
saw, and `DOUBLE` stands in for a model a check might call.
"""

from __future__ import annotations

from typing import Any

RETURNS: Any = None
RAISES: BaseException | None = None
CALLS: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
LAST: Any = None
DOUBLE_CALLS: list[str] = []


def reset() -> None:
    global RETURNS, RAISES, LAST
    RETURNS = None
    RAISES = None
    LAST = None
    CALLS.clear()
    DOUBLE_CALLS.clear()


def _heard(args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    global LAST
    CALLS.append((args, kwargs))
    LAST = args[0] if args else None


def configured(*args: Any, **kwargs: Any) -> Any:
    """Hears whatever it is handed, then returns `RETURNS` or raises `RAISES`."""
    _heard(args, kwargs)
    if RAISES is not None:
        raise RAISES
    return RETURNS


def passes(*args: Any, **kwargs: Any) -> None:
    _heard(args, kwargs)
    return None


def fails_it(*args: Any, **kwargs: Any) -> str:
    _heard(args, kwargs)
    return "refund_wrong"


def fails_if_no_refund(run: Any) -> str | None:
    """A check of the kind a user writes: reads the calls off the view."""
    _heard((run,), {})
    return None if any(c.tool == "issue_refund" for c in run.calls) else "no_refund"


def fails_if_a_kind_was_met(run: Any) -> str | None:
    """A check of the kind a user writes when they have turned one of Break's off and want their own say on it."""
    _heard((run,), {})
    return "a_kind_was_met" if run.kinds else None


def tampers(run: Any) -> None:
    """Tries everything a check could try on what it is handed, by every ordinary means, and then says ok."""
    _heard((run,), {})
    for attempt in (
        lambda: setattr(run, "reply", "changed"),
        lambda: setattr(run, "kinds", ("crashed",)),
        lambda: setattr(run.calls[0], "real_ran", False),
        lambda: run.calls[0].args.__setitem__("query", "changed"),
        lambda: run.calls[0].args.clear(),
        lambda: run.calls[0].saw.__setitem__("status", "changed"),
        lambda: run.calls[0].saw.clear(),
        lambda: run.calls[0].args["nested"]["deep"].append("changed"),
        lambda: run.case.turns.append("changed"),
        lambda: object.__setattr__(run, "reply", "changed"),
        lambda: object.__setattr__(run.calls[0], "real_ran", False),
    ):
        try:
            attempt()
        except Exception:
            pass


def calls_a_model(run: Any) -> str:
    """§11.4: a check may call a model, and Break neither prevents nor pays for it."""
    _heard((run,), {})
    return DOUBLE(str(run.reply))


def DOUBLE(prompt: str) -> str:  # noqa: N802
    DOUBLE_CALLS.append(prompt)
    return "the_model_said_no"


async def is_async(run: Any) -> None:
    return None


NOT_CALLABLE = "this is not a function"
