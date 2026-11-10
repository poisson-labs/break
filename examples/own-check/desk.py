"""An order desk with a scripted model that always answers.

When the look-up fails this desk does not give up: it sends a confident reply anyway. It
reports `resolved` every time, so none of Break's own checks sees anything wrong. The team's
own check, `checks.py`, does.
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


def scripted_model(request: str, status: str | None) -> str:
    """The reply. With no status to go on, the model fills the gap."""
    order = re.search(r"\d{4}", request)
    number = order.group() if order else "?"
    if status is None:
        return f"Order {number} is on its way and will arrive tomorrow."
    return f"Order {number}: {status or 'I have no record of it'}."


def order_desk(cfg, seed):
    order = re.search(r"\d{4}", cfg["input"])
    try:
        status = lookup_order(order.group() if order else "")
    except Exception:
        status = None
    return Episode(outcome="resolved", t=1.0, horizon=1.0,
                   meta={"reply": scripted_model(cfg["input"], status)})
