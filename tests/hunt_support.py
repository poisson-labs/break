"""What the runs module's tests share.

`poisson_break.hunt` is imported lazily, so on a tree without it each test fails on its own and the rest of the suite
still runs. What is here reads the module's names and its source only: every test that makes a hunt waits on the rulings
its shapes need, and is added with them.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
from pathlib import Path
from types import ModuleType

# Plan BK5, "Public names (`poisson_break.hunt`)", word for word.
PUBLIC_NAMES = ("Hunt", "open_hunt", "latest_hunt", "run_arm", "run_search", "control", "ControlSummary", "Budget",
                "Target", "ToolInfo", "RunResult", "TARGET_INTERFACE_VERSION")

PROVE = "poisson_prove"


def hunt() -> ModuleType:
    return importlib.import_module("poisson_break.hunt")


def apply_module() -> ModuleType:
    return importlib.import_module("poisson_break.apply")


def interfaces() -> ModuleType:
    return importlib.import_module("poisson_break.interfaces")


def package_sources() -> dict[str, str]:
    """Every module of the package, by its file's name, as text."""
    spec = importlib.util.find_spec("poisson_break")
    assert spec is not None and spec.origin is not None
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(Path(spec.origin).parent.glob("*.py"))}


def hunt_source() -> str:
    """The runs module's own source. On a tree without the module this fails the test that asked."""
    sources = package_sources()
    assert "hunt.py" in sources, "there is no poisson_break/hunt.py"
    return sources["hunt.py"]


def prove_imports(source: str) -> list[tuple[str, str | None]]:
    """Everything `source` imports from Prove, as (module, name): `import poisson_prove.store` is
    (`poisson_prove.store`, None) and `from poisson_prove.store import Store` is (`poisson_prove.store`, `Store`).
    An import inside a function counts like one at the top."""
    found: list[tuple[str, str | None]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [(alias.name, None) for alias in node.names
                      if alias.name == PROVE or alias.name.startswith(PROVE + ".")]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            if node.module == PROVE or node.module.startswith(PROVE + "."):
                found += [(node.module, alias.name) for alias in node.names]
    return found


def private(imported: tuple[str, str | None]) -> bool:
    """Whether an import reaches into Prove's private side: a module whose name, or any part of it, starts with an
    underscore, or a name that does. `__version__` is the one name with underscores that is public."""
    module, name = imported
    parts = module.split(".")[1:]
    if name is not None and name != "__version__":
        parts.append(name)
    return any(part.startswith("_") for part in parts)


def keywords_passed(source: str) -> set[str]:
    """Every keyword any call in `source` passes, and every key of a `**{...}` written out beside it."""
    words: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg is not None:
                    words.add(keyword.arg)
                elif isinstance(keyword.value, ast.Dict):
                    words |= {key.value for key in keyword.value.keys
                              if isinstance(key, ast.Constant) and isinstance(key.value, str)}
    return words
