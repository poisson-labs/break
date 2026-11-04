"""A user's stand-ins, for the tests of spec §3.6. They live in their own module because a stand-in is
named by an import path (`tests.apply_support_standin:refund`) and loaded by that name."""

from __future__ import annotations

from typing import Any

ANSWER = "the stand-in's answer"
ANSWER_NEXT: Any = None
LOG: list[dict[str, Any]] = []
NOT_CALLABLE = "this is not a function"
WRONG = ValueError("the stand-in itself went wrong")
INTERRUPT = KeyboardInterrupt()


def reset() -> None:
    global ANSWER_NEXT
    ANSWER_NEXT = None
    LOG.clear()


def refund(**args: Any) -> Any:
    LOG.append(args)
    return ANSWER_NEXT if ANSWER_NEXT is not None else ANSWER


def broken(**args: Any) -> Any:
    LOG.append(args)
    raise WRONG


def interrupted(**args: Any) -> Any:
    LOG.append(args)
    raise INTERRUPT
