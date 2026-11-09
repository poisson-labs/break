"""The words Break may not say appear in no file a user reads.

Invariant held here (Break — Plan, the release pass):
- BK11.3  The words Break may not say (spec §5.6 and the brand's list) appear in no user-facing
          file; a pattern test holds it.

The files a user reads: the README, every file under `docs/` and `examples/`, every verb's help
and the command's own, and every line the command can print, read as each string written in
the package's source that is not a docstring, and each text file the package carries beside its
modules.

The words, each a pattern below with where it comes from:
- Plan §2, item 7: no module id, ruling number or session name, and no project name (`Monte`,
  `proofload`, `momus`).
- Spec §5.6: no speed-up figure of any size, anywhere, until the search study has measured one.
- The brand's list ("Poisson Labs — Brand & Language" §2, "Words we do not use"), every word in
  it that the list bans with no qualifier: the dead names, the claims (certified, signable,
  audit-grade, compliance, verified, guaranteed, proves safe), the vendor noise, the commands
  (do not ship, safe to deploy, ship it), `engagements`, the opening it bans, and HydraDB, which
  the same page keeps out of public material.

Taylor's rulings (2026-11-09, `evidence/bk11/open-points.md`), held here too:
- 11A-5: spec §5.6's three words, as `safe`, `safety`, `safely`, `robust`, `robustness`,
  `reliable`, `reliably`, `reliability`, in every file the test reads, with two exceptions: the
  exact phrase `safe to repeat`, Break's own term for a write tool, and the one page on what Break
  does not claim (`docs/claims.md`, 11A-10), which may say the three words to disclaim them.
- 11A-6: `unchanged`, `simply`, `easy`, `easily` and `just`, outright; `adversarial` is not banned
  for Break, the tool that hunts.
- 11A-7a: the changelog (`CHANGELOG.md`) and the PyPI page's own text, the `description` and the
  `keywords` of `pyproject.toml`, are read too.
- 11A-7b: the lab's two shared standards, `docs/repo-hygiene.md` and `docs/cli-look.md`, are left
  out by name.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

from tests.conftest import REPO, run_command

SRC = REPO / "src" / "poisson_break"

#: Each banned pattern with where it comes from. Matched against text with its line breaks
#: read as spaces, so a phrase split across two lines is still found.
BANNED: dict[str, re.Pattern[str]] = {
    # plan §2.7
    "a module id": re.compile(r"\b(?:BK|TF|PF|FD|LST|PT|CAL|MT)\d+[a-c]?\b"),
    "a ruling number": re.compile(r"\b[Rr]uling(?:s)?\s+\d"),
    "a session name": re.compile(r"\bSession\s+[AB]\b"),
    "Monte": re.compile(r"\bMonte\b"),
    "proofload": re.compile(r"\bproofload\b", re.IGNORECASE),
    "momus": re.compile(r"\bmomus\b", re.IGNORECASE),
    # spec §5.6
    "a speed-up figure": re.compile(
        r"\b\d+(?:\.\d+)?\s*(?:x|×|times|%|per\s*cent|percent)\s+(?:faster|quicker|sooner|"
        r"fewer|less|cheaper|more\s+efficient|as\s+fast)\b", re.IGNORECASE),
    "a speed-up quoted": re.compile(r"\bspeed-?ups?\s+of\s+\d", re.IGNORECASE),
    # the brand's list, §2
    "certified": re.compile(r"\bcertified\b", re.IGNORECASE),
    "signable": re.compile(r"\bsignable\b", re.IGNORECASE),
    "audit-grade": re.compile(r"\baudit[- ]grade\b", re.IGNORECASE),
    "compliance": re.compile(r"\bcompliance\b", re.IGNORECASE),
    "verified": re.compile(r"\bverified\b", re.IGNORECASE),
    "guaranteed": re.compile(r"\bguarantee[ds]?\b", re.IGNORECASE),
    "proves safe": re.compile(r"\bproves?\s+(?:it\s+|that\s+it\s+is\s+)?safe\b", re.IGNORECASE),
    "AI-powered": re.compile(r"\bAI[- ]powered\b", re.IGNORECASE),
    "cutting-edge": re.compile(r"\bcutting[- ]edge\b", re.IGNORECASE),
    "revolutionary": re.compile(r"\brevolutionary\b", re.IGNORECASE),
    "vibes": re.compile(r"\bvibes\b", re.IGNORECASE),
    "magic": re.compile(r"\bmagic(?:al|ally)?\b", re.IGNORECASE),
    "secret sauce": re.compile(r"\bsecret\s+sauce\b", re.IGNORECASE),
    "Strongfloor": re.compile(r"\bstrongfloor\b", re.IGNORECASE),
    "Aplomb": re.compile(r"\baplomb\b", re.IGNORECASE),
    "Sangfroid": re.compile(r"\bsangfroid\b", re.IGNORECASE),
    "do not ship": re.compile(r"\b(?:do\s+not|don't|don’t)\s+ship\b", re.IGNORECASE),
    "safe to deploy": re.compile(r"\bsafe\s+to\s+(?:deploy|ship|release)\b", re.IGNORECASE),
    "ship it": re.compile(r"\bship\s+it\b", re.IGNORECASE),
    "engagements": re.compile(r"\bengagements?\b", re.IGNORECASE),
    "independent research group": re.compile(r"\bindependent\s+research\s+group\b", re.IGNORECASE),
    "HydraDB": re.compile(r"\bhydra\s*db\b", re.IGNORECASE),
}

#: Spec §5.6's three words (11A-5), and the brand's words of the reader's work and of a result
#: (11A-6). The §5.6 words are let through in the one page on what Break does not claim, and in
#: the phrase `safe to repeat` everywhere.
CLAIMS: dict[str, re.Pattern[str]] = {
    "safe": re.compile(r"\b(?:safe|safety|safely)\b", re.IGNORECASE),
    "robust": re.compile(r"\brobust(?:ness|ly)?\b", re.IGNORECASE),
    "reliable": re.compile(r"\breliab(?:le|ly|ility)\b", re.IGNORECASE),
}
WORDS: dict[str, re.Pattern[str]] = {
    "unchanged": re.compile(r"\bunchanged\b", re.IGNORECASE),
    "simply": re.compile(r"\bsimply\b", re.IGNORECASE),
    "easy": re.compile(r"\beas(?:y|ily|ier|iest)\b", re.IGNORECASE),
    "just": re.compile(r"\bjust\b", re.IGNORECASE),
}
SAFE_TO_REPEAT = re.compile(r"\bsafe\s+to\s+repeat\b", re.IGNORECASE)
CLAIMS_PAGE = "docs/claims.md"
STANDARDS = ("docs/repo-hygiene.md", "docs/cli-look.md")


def hits(text: str, *, claims_page: bool = False) -> list[str]:
    """Each banned pattern the text holds, with what it matched; on the claims page the three
    words of spec §5.6 are let through."""
    flat = re.sub(r"\s+", " ", text)
    found = []
    for name, pattern in {**BANNED, **WORDS}.items():
        for match in pattern.finditer(flat):
            found.append(f"{name}: {match.group(0)!r}")
    if not claims_page:
        rest = SAFE_TO_REPEAT.sub(" ", flat)
        for name, pattern in CLAIMS.items():
            for match in pattern.finditer(rest):
                found.append(f"{name}: {match.group(0)!r}")
    return found


# ---------------------------------------------------------------------------
# the patterns themselves: each catches its word and lets the plain words beside it through
# ---------------------------------------------------------------------------

CAUGHT = {
    "a module id": ["built in BK11", "see BK9a", "TF18 pages", "the PF12 pass"],
    "a ruling number": ["as ruling 5 says", "Rulings 1 to 24"],
    "a session name": ["Session A wrote it", "in Session B"],
    "Monte": ["Monte learns", "inside Monte."],
    "proofload": ["Proofload's store", "the proofload method"],
    "momus": ["Momus"],
    "a speed-up figure": ["finds failures 3x faster", "2.5 × fewer runs", "40% fewer runs",
                          "ten runs, 3 times faster", "30 percent cheaper"],
    "a speed-up quoted": ["a speed-up of 3", "speedups of 10"],
    "certified": ["Certified results"],
    "signable": ["a signable receipt"],
    "audit-grade": ["audit-grade evidence", "audit grade"],
    "compliance": ["for compliance"],
    "verified": ["a verified agent"],
    "guaranteed": ["guaranteed to find", "Break guarantees"],
    "proves safe": ["proves safe", "Break proves it safe", "prove safe"],
    "AI-powered": ["AI-powered search", "AI powered"],
    "cutting-edge": ["cutting-edge"],
    "revolutionary": ["a revolutionary tool"],
    "vibes": ["not vibes"],
    "magic": ["no magic", "magically"],
    "secret sauce": ["the secret  sauce"],
    "Strongfloor": ["Strongfloor"],
    "Aplomb": ["Aplomb"],
    "Sangfroid": ["Sangfroid hosts it"],
    "do not ship": ["do not ship this", "Don't ship", "don’t ship"],
    "safe to deploy": ["safe to deploy", "safe to\nrelease"],
    "ship it": ["ship it"],
    "engagements": ["our engagements", "an engagement"],
    "independent research group": ["an independent research group"],
    "HydraDB": ["HydraDB", "Hydra DB"],
    "safe": ["the agent is safe", "Safety first", "it runs safely", "safe to call twice",
             "made safe", "safe to repeat and safe"],
    "robust": ["a robust agent", "robustness"],
    "reliable": ["reliable", "reliably", "its reliability"],
    "unchanged": ["the unchanged agent"],
    "simply": ["simply run it"],
    "easy": ["it is easy", "easily", "easier"],
    "just": ["just run hunt", "Just add a line"],
}

PASSED = [
    "safe to repeat", "made safe to repeat", "it ships one way in", "the tool is shipped",
    "a run of 3 tools", "unsafe", "adjusted p-value", "justified", "adversarial search", "3 runs", "40% of runs failed",
    "fails more than the control", "Prove's numbers", "Poisson Prove", "Trace's test",
    "the 3x3 grid", "BK", "PT", "a pre-registration", "session", "a TK-1 ticket", "Trace 0.1.0rc3",
    "Python 3.11", "the monitor", "Montenegro", "magician", "engaged", "guard",
    "a hunt of 60 runs at most", "a timeout after 30 s", "x faster",
]


@pytest.mark.parametrize("name", sorted(CAUGHT))
def test_each_pattern_catches_its_word(name: str) -> None:
    for text in CAUGHT[name]:
        assert any(h.startswith(f"{name}: ") for h in hits(text)), (name, text)


def test_the_patterns_let_plain_words_through() -> None:
    assert {text: hits(text) for text in PASSED if hits(text)} == {}


def test_the_claims_page_may_say_the_three_words_and_nothing_else_banned() -> None:
    said = "Break does not say an agent is safe, robust or reliable."
    assert hits(said, claims_page=True) == []
    assert {h.split(":")[0] for h in hits(said)} == {"safe", "robust", "reliable"}
    assert [h.split(":")[0] for h in hits("It is simply unchanged.", claims_page=True)] == \
        ["unchanged", "simply"]


def test_every_word_of_the_brand_list_without_a_qualifier_has_a_pattern() -> None:
    """The brand's list is read from its words here, so dropping a pattern is seen: each word
    the list bans outright, and each name plan §2.7 keeps out, is a key above."""
    assert set(CAUGHT) == set(BANNED) | set(CLAIMS) | set(WORDS)
    assert {"certified", "signable", "audit-grade", "compliance", "verified", "guaranteed",
            "proves safe", "AI-powered", "cutting-edge", "revolutionary", "vibes", "magic",
            "secret sauce", "Strongfloor", "Aplomb", "Sangfroid", "Monte", "proofload", "momus",
            "do not ship", "safe to deploy", "ship it", "engagements",
            "independent research group", "HydraDB", "a module id", "a ruling number",
            "a session name", "a speed-up figure"} <= set(BANNED)
    assert {"safe", "robust", "reliable", "unchanged", "simply", "easy", "just"} <= set(CAUGHT)


# ---------------------------------------------------------------------------
# the files a user reads
# ---------------------------------------------------------------------------


def user_files() -> list[Path]:
    """The README, the changelog, and every text file under `docs/` and `examples/` but the two
    shared standards (11A-7a, 11A-7b)."""
    files = [REPO / "README.md", REPO / "CHANGELOG.md"]
    for top in ("docs", "examples"):
        root = REPO / top
        if root.exists():
            files += sorted(p for p in root.rglob("*") if p.is_file()
                            and "__pycache__" not in p.parts and p.suffix != ".pyc"
                            and p.relative_to(REPO).as_posix() not in STANDARDS)
    return files


def test_no_page_or_example_says_a_banned_word() -> None:
    found = {}
    for path in user_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        said = hits(text, claims_page=path.relative_to(REPO).as_posix() == CLAIMS_PAGE)
        if said:
            found[str(path.relative_to(REPO))] = said
    assert found == {}


def test_the_pypi_page_s_own_text_says_no_banned_word() -> None:
    """11A-7a: the summary and the keywords PyPI shows beside the README."""
    with (REPO / "pyproject.toml").open("rb") as f:
        project = tomllib.load(f)["project"]
    assert hits(project["description"]) == []
    assert {k: hits(k) for k in project.get("keywords", []) if hits(k)} == {}


def test_there_are_docs_and_examples_to_read() -> None:
    """The release pass writes both; with neither there, the test above reads the README alone
    and holds nothing of them."""
    files = [p.relative_to(REPO).parts[0] for p in user_files()]
    assert "docs" in files and "examples" in files


def _printed_strings(path: Path) -> list[str]:
    """Every string written in a module that is not a docstring: what the command can print is
    built from these."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings]


def test_no_line_the_command_can_print_says_a_banned_word() -> None:
    found = {}
    for path in sorted(SRC.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.suffix == ".py":
            text = "\n".join(_printed_strings(path))
        else:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
        if hits(text):
            found[str(path.relative_to(REPO))] = hits(text)
    assert found == {}


VERBS = ("init", "doctor", "hunt", "confirm", "findings", "replay", "recheck", "catalog")


@pytest.mark.parametrize("words", [["--help"]] + [[verb, "--help"] for verb in VERBS],
                         ids=lambda w: " ".join(w))
def test_no_help_says_a_banned_word(words: list[str], tmp_path: Path) -> None:
    ran = run_command(words, cwd=tmp_path)
    assert ran.exit == 0, ran.stderr
    assert ran.stdout.strip()
    assert hits(ran.stdout + ran.stderr) == []
