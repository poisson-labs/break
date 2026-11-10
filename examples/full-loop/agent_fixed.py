"""The order desk of `agent.py`, fixed: a failed look-up is tried again, twice at most.

Nothing else differs. Copy this file over `agent.py`, then run `poisson-break recheck`.
"""

import re

from poisson_prove import Episode

from poisson_break.apply import wrap

ORDERS = {
    "4821": "shipped on Tuesday, due Thursday",
    "4822": "delivered last Friday",
    "4823": "packed, waiting for the courier",
    "4824": "delivered on Monday",
    "4825": "shipped yesterday, due Saturday",
    "4826": "returned to the warehouse",
}


def _lookup_order(order: str) -> str:
    return ORDERS.get(order, "")


lookup_order = wrap("lookup_order", _lookup_order)


def scripted_model(request: str, status: str) -> str:
    """The reply, written from the request and the order's status."""
    order = re.search(r"\d{4}", request)
    return f"Order {order.group() if order else '?'}: {status or 'I have no record of it'}."


def order_desk(cfg, seed):
    order = re.search(r"\d{4}", cfg["input"])
    for _ in range(3):
        try:
            status = lookup_order(order.group() if order else "")
        except Exception:
            # The fix: a failed look-up is tried again before the desk gives up.
            continue
        return Episode(outcome="resolved", t=1.0, horizon=1.0,
                       meta={"reply": scripted_model(cfg["input"], status)})
    return Episode(outcome="unresolved", t=0.0, horizon=1.0,
                   meta={"reply": "Sorry, I could not look that order up."})
