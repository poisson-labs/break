"""A fault of the team's own: the tool answers with an error page where its result should be.

Some services fail this way: no error is raised, and the caller gets a page of HTML as if it
were the result. Break's catalogue has no such fault, so this module adds one. Importing it
registers `error_page`, which `break.toml` then names in `[vary] tools` beside Break's own.
"""

from poisson_break.changes import Result, register

PAGE = "<html><body><h1>503 Service Unavailable</h1><p>Try again later.</p></body></html>"


class ErrorPage:
    name = "error_page"
    surface = "tool"
    description = ("an HTML error page as the result, with no error raised; the real tool "
                   "does not run")
    parameters = {}
    real_runs = False

    def apply(self, call, *, real, params, rng):
        return Result(value=PAGE)


register(ErrorPage())
