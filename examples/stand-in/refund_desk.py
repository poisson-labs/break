"""A refund desk with a scripted model and a tool that moves money.

`issue_refund` is a write tool: its own function asks the payments service to pay the customer
back. `break.toml` classes it `write` and names a stand-in, `payments_fake:issue_refund`, so in
every run Break calls the stand-in in its place and the function below never runs.
"""

import json
import re
import urllib.request

from poisson_prove import Episode

from poisson_break.apply import wrap

ORDERS = {
    "4821": ("delivered damaged", 39.00),
    "4822": ("delivered damaged", 12.50),
    "4823": ("lost by the courier", 85.00),
    "4824": ("delivered damaged", 7.25),
    "4825": ("lost by the courier", 149.00),
    "4826": ("delivered damaged", 22.00),
}


def _lookup_order(order: str) -> dict:
    state, paid = ORDERS.get(order, ("unknown", 0.0))
    return {"order": order, "state": state, "paid": paid}


def _issue_refund(order: str, amount: float) -> str:
    """The real refund: a request to the payments service. Break never calls this."""
    body = json.dumps({"order": order, "amount": amount}).encode()
    request = urllib.request.Request("https://payments.example.com/refunds", data=body)
    with urllib.request.urlopen(request, timeout=10) as reply:
        return json.load(reply)["id"]


lookup_order = wrap("lookup_order", _lookup_order)
issue_refund = wrap("issue_refund", _issue_refund)


def scripted_model(request: str, order: dict) -> str:
    """What to do about a refund request: `refund` or `decline`."""
    return "refund" if order["state"] in ("delivered damaged", "lost by the courier") else "decline"


def refund_desk(cfg, seed):
    number = re.search(r"\d{4}", cfg["input"])
    try:
        order = lookup_order(number.group() if number else "")
    except Exception:
        order = lookup_order(number.group() if number else "")   # a read: trying again is free
    if scripted_model(cfg["input"], order) == "decline":
        return Episode(outcome="resolved", t=1.0, horizon=1.0,
                       meta={"reply": "That order does not qualify for a refund."})
    try:
        receipt = issue_refund(order["order"], order["paid"])
    except Exception:
        # The refund call failed, so the desk sends it again. If the first call did go through
        # and only its reply was lost, the customer is now paid twice.
        receipt = issue_refund(order["order"], order["paid"])
    return Episode(outcome="resolved", t=1.0, horizon=1.0,
                   meta={"reply": f"Refunded {order['paid']:.2f}. Receipt {receipt}."})
