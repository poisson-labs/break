"""The holders module's five tools: plain functions, each adding its run to `EXECUTED` and answering with a string."""

from __future__ import annotations

from typing import Any

EXECUTED: list[tuple[str, dict[str, Any]]] = []
"""Each real run of a tool, as its name and the arguments it was given."""


def lookup_order(query: str, detail: str | None = None) -> str:
    """Look an order up."""
    EXECUTED.append(("lookup_order", {"query": query, "detail": detail}))
    return f"Order {query} shipped on Tuesday."


def check_policy(topic: str) -> str:
    """Read the refund policy."""
    EXECUTED.append(("check_policy", {"topic": topic}))
    return "Refunds within thirty days."


def issue_refund(request: str) -> str:
    """Move the money back."""
    EXECUTED.append(("issue_refund", {"request": request}))
    return "Refund issued."


def send_email(to: str) -> str:
    """Write to the customer."""
    EXECUTED.append(("send_email", {"to": to}))
    return "sent"


def cancel_order(order: str) -> str:
    """Cancel an order."""
    EXECUTED.append(("cancel_order", {"order": order}))
    return "cancelled"
