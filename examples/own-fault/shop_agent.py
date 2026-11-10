"""An order desk with a scripted model, and a fault of the team's own to hunt it with.

Importing `faults` registers `error_page`. Break imports this module when it loads the agent,
so the fault is in the catalogue before any run.
"""

import re

import faults  # noqa: F401  (registers error_page)
from poisson_prove import Episode

from poisson_break.apply import wrap

ORDERS = {
    "4821": "state: shipped; due: Thursday",
    "4822": "state: delivered; due: last Friday",
    "4823": "state: packed; due: next week",
    "4824": "state: delivered; due: Monday",
    "4825": "state: shipped; due: Saturday",
    "4826": "state: returned; due: never",
}


def _lookup_order(order: str) -> str:
    return ORDERS.get(order, "state: unknown; due: unknown")


lookup_order = wrap("lookup_order", _lookup_order)


def scripted_model(request: str, state: str, due: str) -> str:
    """The reply, written from the order's two fields."""
    order = re.search(r"\d{4}", request)
    return f"Order {order.group() if order else '?'} is {state}, due {due}."


def order_desk(cfg, seed):
    order = re.search(r"\d{4}", cfg["input"])
    for _ in range(3):
        try:
            record = lookup_order(order.group() if order else "")
        except Exception:
            continue   # a raised error is tried again
        # The desk trusts whatever comes back to be a record. An error page is not one, and
        # the line below falls over on it.
        state, due = (field.split(": ", 1)[1] for field in record.split("; "))
        return Episode(outcome="resolved", t=1.0, horizon=1.0,
                       meta={"reply": scripted_model(cfg["input"], state, due)})
    return Episode(outcome="unresolved", t=0.0, horizon=1.0,
                   meta={"reply": "Sorry, I could not look that order up."})
