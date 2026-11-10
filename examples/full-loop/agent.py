"""An order desk with a scripted model, as it was first written: it looks the order up once.

`agent_fixed.py` is the same desk with the fix. Copy it over this file to put the fix in:

    cp agent_fixed.py agent.py
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
    try:
        status = lookup_order(order.group() if order else "")
    except Exception:
        # One look-up, and no second try: a failed look-up ends the request.
        return Episode(outcome="unresolved", t=0.0, horizon=1.0,
                       meta={"reply": "Sorry, I could not look that order up."})
    return Episode(outcome="resolved", t=1.0, horizon=1.0,
                   meta={"reply": scripted_model(cfg["input"], status)})
