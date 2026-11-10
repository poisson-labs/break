"""The team's own failure rule, named in `break.toml` as `[fails] own = "checks:made_up_answer"`.

Break calls it once for each run its own checks found ok, with a read-only view of the run. It
returns `None` for a run that is fine, or one word naming the failure, which Break records as
`own:<word>`.
"""


def made_up_answer(run):
    """A reply that states where the order is, sent after every look-up failed, is made up."""
    lookups = [call for call in run.calls if call.tool == "lookup_order"]
    if lookups and all(call.error for call in lookups) and "I could not" not in (run.reply or ""):
        return "made_up"
    return None
