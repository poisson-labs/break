"""A module that cannot be imported: it raises as it loads. For the tests of what the runs module refuses before any run."""

raise RuntimeError("this module breaks when it is imported")
