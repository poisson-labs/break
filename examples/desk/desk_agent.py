"""A help desk for an online shop: two tools and a scripted model.

The model is scripted. `scripted_model` picks the next step from the request and from what the
tools have returned so far, so the agent runs with no key and no network, and does the same
thing every time. Each tool is wrapped once with `wrap`; that one line a tool is all Break needs
to change how the tool behaves during a run.
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


def _check_policy(topic: str) -> str:
    return "Refunds are accepted within thirty days of delivery."


lookup_order = wrap("lookup_order", _lookup_order)
check_policy = wrap("check_policy", _check_policy)


def scripted_model(request: str, seen: dict[str, str]) -> tuple[str, str]:
    """The next step: a tool to call with its argument, or the reply to send."""
    order = re.search(r"\d{4}", request)
    if order is None:
        return "reply", "Which order is this about?"
    if "status" not in seen:
        return "lookup_order", order.group()
    if "refund" in request.lower() and "policy" not in seen:
        return "check_policy", "refunds"
    answer = f"Order {order.group()}: {seen['status']}."
    if seen.get("policy"):
        answer += " " + seen["policy"]
    return "reply", answer


def desk(cfg, seed):
    """One request, start to finish. The outcome is `resolved` when the customer got an answer
    about their order, and `unresolved` when the desk had to give up."""
    seen: dict[str, str] = {}
    for _ in range(6):
        step, value = scripted_model(cfg["input"], seen)
        if step == "reply":
            return Episode(outcome="resolved", t=1.0, horizon=1.0, meta={"reply": value})
        if step == "lookup_order":
            try:
                seen["status"] = lookup_order(value)
            except Exception:
                # The desk has no second try and no fallback: one failed look-up ends the request.
                return Episode(outcome="unresolved", t=0.0, horizon=1.0,
                               meta={"reply": "Sorry, I could not look that order up."})
            if not seen["status"]:
                seen["status"] = "I have no record of it, please check the number"
        else:
            try:
                seen["policy"] = check_policy(value)
            except Exception:
                # The policy is a courtesy: without it the desk still answers.
                seen["policy"] = ""
    return Episode(outcome="unresolved", t=0.0, horizon=1.0, meta={"ended": "limit"})
