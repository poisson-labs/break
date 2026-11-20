"""The holders module: a scripted agent whose one tool is held every way a tool can be held.

`tools` defines five tools. `agent` takes them by `from ... import`, and holds them in a dict and a list at its top;
it also holds `lookup_order` in a closure, a `functools.partial`, a tuple and an attribute of an object. This package
gives `lookup_order` again under its own name, and nothing else of `tools`. No file here holds a line of anything but
Python and `tests`.
"""

from tests.agents.holders.tools import lookup_order

__all__ = ["lookup_order"]
