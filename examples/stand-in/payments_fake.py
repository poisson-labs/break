"""The stand-in for the payments service: it hands back a receipt and moves no money.

Break calls `issue_refund` here wherever the agent calls its own `issue_refund`, with the same
arguments.
"""


def issue_refund(order: str, amount: float) -> str:
    return f"test-{order}"
