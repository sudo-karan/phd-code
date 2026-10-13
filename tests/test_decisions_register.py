"""Keeps docs/decisions.yaml, the decision register, honest.

The register is read by a program later, so its shape is pinned here: every
entry has the same keys in the same order, a status from a fixed list, evidence
paths that exist, and papers that say plainly whether they were verified.

Two rules matter most. Every "## " section of docs/design_notes.md must be the
`design_notes_section` of at least one entry (the headings are read from the
file, not listed here, so a new section with no entry fails). And a paper marked
`verified: true` must carry a DOI, a title, a first author and a year, while one
marked `verified: false` must say why it was not verified.

The three checks that matter most (a section with no entry, an evidence path
that does not exist, a verified paper with no DOI) are written as functions, and
each is also run on a deliberately broken copy of the register, so that a check
which has stopped catching anything fails here too.

Fast tier: pyyaml and the standard library only. Nothing here checks a DOI
against Crossref; that is done when the register is assembled and reviewed.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
REGISTER = REPO / "docs" / "decisions.yaml"
DESIGN_NOTES = REPO / "docs" / "design_notes.md"

# Keys of a decision, in file order. `alternatives_note` is the one optional key:
# it is present exactly when `alternatives_considered` is empty.
DECISION_KEYS = (
    "id",
    "title",
    "decision",
    "alternatives_considered",
    "rationale",
    "evidence",
    "papers",
    "status",
    "design_notes_section",
    "source",
)
NO_ALTERNATIVES = "not recorded in the source"
PAPER_KEYS = (
    "doi",
    "title",
    "first_author",
    "year",
    "verified",
    "supports",
    "supports_what",
    "cited_in",
)
STATUSES = {"adopted", "superseded", "open", "pending"}
SUPPORTS = {"used", "recommended", "shown_better"}
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DOI = re.compile(r"^10\.\d{4,9}/\S+$")
DESIGN_NOTES_PATH = "docs/design_notes.md"
# A repo file named inside free text, such as "src/fmu/config.py lines 435-445".
FILE_IN_TEXT = re.compile(
    r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.(?:py|md|yaml|yml|txt|json|toml|sh))(?![\w/])"
)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


@pytest.fixture(scope="module")
def register() -> dict[str, Any]:
    return yaml.safe_load(REGISTER.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def decisions(register: dict[str, Any]) -> list[dict[str, Any]]:
    return register["decisions"]


@pytest.fixture(scope="module")
def papers(decisions: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    return [(d["id"], p) for d in decisions for p in d["papers"]]


def _headings() -> list[str]:
    lines = DESIGN_NOTES.read_text(encoding="utf-8").splitlines()
    return [line[3:].strip() for line in lines if line.startswith("## ")]


def uncovered_sections(decisions: list[dict[str, Any]], headings: list[str]) -> list[str]:
    """Headings that no entry covers.

    An entry covers a section only if it names the heading AND lists
    docs/design_notes.md as evidence, so a heading cannot be ticked off by an
    entry that never points at the notes.
    """
    covered = {
        d["design_notes_section"]
        for d in decisions
        if any(ev["path"] == DESIGN_NOTES_PATH for ev in d["evidence"])
    }
    return [h for h in headings if h not in covered]


def bad_evidence_paths(decisions: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """(entry id, path) for each evidence path that is not a real file in the repo.

    A path must be relative, stay inside the repo, and be an existing file or a
    directory with at least one file in it.
    """
    bad = []
    for d in decisions:
        for ev in d["evidence"]:
            path = Path(ev["path"])
            target = REPO / path
            inside = not path.is_absolute() and ".." not in path.parts
            real = target.is_file() or (
                target.is_dir() and any(p.is_file() for p in target.rglob("*"))
            )
            if not (inside and real):
                bad.append((d["id"], ev["path"]))
    return bad


def verified_paper_problems(papers: list[tuple[str, dict[str, Any]]]) -> list[str]:
    """What is wrong with each paper marked verified: true, as readable lines."""
    problems = []
    for where, p in papers:
        if p["verified"] is not True:
            continue
        if not (isinstance(p["doi"], str) and DOI.match(p["doi"])):
            problems.append(f"{where}: verified but doi is {p['doi']!r}")
        if not _text(p["title"]):
            problems.append(f"{where}: verified but no title")
        if not _text(p["first_author"]):
            problems.append(f"{where}: verified but no first author")
        year = p["year"]
        if not (isinstance(year, int) and not isinstance(year, bool) and 1900 <= year <= 2100):
            problems.append(f"{where}: verified but year is {year!r}")
        if "why_not_verified" in p:
            problems.append(f"{where}: verified but carries why_not_verified")
    return problems


def test_file_parses_and_has_the_top_level_shape(register: dict[str, Any]):
    assert list(register) == ["schema_version", "decisions"]
    assert register["schema_version"] == 1
    assert isinstance(register["decisions"], list) and register["decisions"]


def test_header_says_what_unverified_means():
    head = REGISTER.read_text(encoding="utf-8").split("schema_version:", 1)[0]
    assert head.lstrip().startswith("#")
    assert "Crossref" in head and "verified: false" in head


def test_ids_are_unique_slugs(decisions: list[dict[str, Any]]):
    ids = [d["id"] for d in decisions]
    bad = [i for i in ids if not (isinstance(i, str) and SLUG.match(i))]
    assert not bad, f"ids that are not lower-case slugs: {bad}"
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    assert not repeated, f"repeated ids: {repeated}"


def test_every_decision_has_exactly_the_required_keys_in_order(
    decisions: list[dict[str, Any]],
):
    for d in decisions:
        keys = [k for k in d if k != "alternatives_note"]
        assert tuple(keys) == DECISION_KEYS, f"{d.get('id')}: keys are {list(d)}"


def test_decision_values_have_the_right_types(decisions: list[dict[str, Any]]):
    for d in decisions:
        where = d["id"]
        for key in ("title", "decision", "rationale", "source"):
            assert _text(d[key]), f"{where}: {key} must be non-empty text"
        alts = d["alternatives_considered"]
        assert isinstance(alts, list), where
        assert all(_text(a) for a in alts), f"{where}: an alternative is empty"
        assert isinstance(d["evidence"], list) and d["evidence"], f"{where}: no evidence"
        for ev in d["evidence"]:
            assert isinstance(ev, dict) and list(ev) == ["path", "what"], f"{where}: {ev}"
            assert _text(ev["path"]) and _text(ev["what"]), f"{where}: {ev}"
        assert isinstance(d["papers"], list), where
        section = d["design_notes_section"]
        assert section is None or _text(section), where


def test_an_empty_alternatives_list_says_so_and_only_then(
    decisions: list[dict[str, Any]],
):
    for d in decisions:
        if d["alternatives_considered"]:
            assert "alternatives_note" not in d, d["id"]
        else:
            assert d.get("alternatives_note") == NO_ALTERNATIVES, d["id"]
            # the note sits right after the empty list
            assert list(d)[4] == "alternatives_note", d["id"]


def test_status_is_from_the_allowed_set(decisions: list[dict[str, Any]]):
    bad = {d["id"]: d["status"] for d in decisions if d["status"] not in STATUSES}
    assert not bad, bad


def test_every_design_notes_section_has_an_entry(decisions: list[dict[str, Any]]):
    headings = _headings()
    assert headings, "docs/design_notes.md has no '## ' headings"
    assert len(set(headings)) == len(headings), "two sections share a heading"
    uncovered = uncovered_sections(decisions, headings)
    assert not uncovered, (
        "docs/design_notes.md sections with no entry in docs/decisions.yaml: "
        f"{uncovered}"
    )


def test_a_section_with_no_entry_would_be_caught(decisions: list[dict[str, Any]]):
    headings = _headings()
    # a new section in the notes that the register has not caught up with
    assert uncovered_sections(decisions, [*headings, "A section added later"]) == [
        "A section added later"
    ]
    # the entries of one real section taken away
    gone = headings[0]
    rest = [d for d in decisions if d["design_notes_section"] != gone]
    assert uncovered_sections(rest, headings) == [gone]
    # an entry that names the heading but never points at the notes does not count
    stripped = copy.deepcopy(decisions)
    for d in stripped:
        if d["design_notes_section"] == gone:
            d["evidence"] = [ev for ev in d["evidence"] if ev["path"] != DESIGN_NOTES_PATH]
    assert uncovered_sections(stripped, headings) == [gone]


def test_an_entry_that_names_a_section_cites_the_design_notes(
    decisions: list[dict[str, Any]],
):
    missing = [
        d["id"]
        for d in decisions
        if d["design_notes_section"] is not None
        and not any(ev["path"] == DESIGN_NOTES_PATH for ev in d["evidence"])
    ]
    assert not missing, f"name a section but do not list {DESIGN_NOTES_PATH}: {missing}"


def test_no_entry_names_a_heading_that_does_not_exist(
    decisions: list[dict[str, Any]],
):
    headings = set(_headings())
    unknown = {
        d["id"]: d["design_notes_section"]
        for d in decisions
        if d["design_notes_section"] is not None
        and d["design_notes_section"] not in headings
    }
    assert not unknown, f"not a '## ' heading of docs/design_notes.md: {unknown}"


def test_every_evidence_path_exists(decisions: list[dict[str, Any]]):
    bad = bad_evidence_paths(decisions)
    assert not bad, f"evidence paths not in the repo: {bad}"


def test_no_entry_lists_the_same_evidence_path_twice(decisions: list[dict[str, Any]]):
    for d in decisions:
        paths = [ev["path"] for ev in d["evidence"]]
        assert len(set(paths)) == len(paths), f"{d['id']}: {paths}"


def test_a_dead_evidence_path_would_be_caught(decisions: list[dict[str, Any]], tmp_path: Path):
    for dead in (
        "src/fmu/no_such_module.py",  # not there
        "../outside_the_repo.md",  # leaves the repo
        str(tmp_path / "absolute.md"),  # absolute
        "docs/no_such_folder/",  # a folder that is not there
    ):
        broken = copy.deepcopy(decisions[:1])
        broken[0]["evidence"].append({"path": dead, "what": "made up for this test"})
        assert bad_evidence_paths(broken) == [(broken[0]["id"], dead)], dead


def test_files_named_in_cited_in_exist(papers: list[tuple[str, dict[str, Any]]]):
    """cited_in says where the repo cites the paper; the files it names must be real."""
    for where, p in papers:
        named = FILE_IN_TEXT.findall(p["cited_in"])
        assert named, f"{where}: cited_in names no file: {p['cited_in']!r}"
        missing = [f for f in named if not (REPO / f).is_file()]
        assert not missing, f"{where}: cited_in names files not in the repo: {missing}"


def test_every_paper_has_the_required_keys_in_order(
    papers: list[tuple[str, dict[str, Any]]],
):
    for where, p in papers:
        expected = PAPER_KEYS if p.get("verified") else (*PAPER_KEYS, "why_not_verified")
        assert tuple(p) == expected, f"{where}: paper keys are {list(p)}"
        assert isinstance(p["verified"], bool), where
        assert p["supports"] in SUPPORTS, f"{where}: supports is {p['supports']!r}"
        assert _text(p["cited_in"]), f"{where}: cited_in is empty"


def test_no_paper_has_supports_what_empty(papers: list[tuple[str, dict[str, Any]]]):
    empty = [where for where, p in papers if not _text(p["supports_what"])]
    assert not empty, empty


def test_a_verified_paper_has_doi_title_first_author_and_year(
    papers: list[tuple[str, dict[str, Any]]],
):
    problems = verified_paper_problems(papers)
    assert not problems, problems


def test_a_verified_paper_without_a_doi_would_be_caught():
    good = {
        "doi": "10.1234/example",
        "title": "A title",
        "first_author": "Author",
        "year": 2020,
        "verified": True,
        "supports": "used",
        "supports_what": "text",
        "cited_in": "README.md",
    }
    assert verified_paper_problems([("x", good)]) == []
    for key, value in (
        ("doi", None),
        ("doi", ""),
        ("doi", "https://doi.org/10.1234/example"),
        ("doi", "UNVERIFIED"),
        ("title", ""),
        ("first_author", None),
        ("year", "2020"),
        ("year", None),
    ):
        assert verified_paper_problems([("x", {**good, key: value})]), (key, value)
    # an unverified paper is not this check's business
    assert verified_paper_problems([("x", {**good, "doi": None, "verified": False})]) == []


def test_an_unverified_paper_says_why(papers: list[tuple[str, dict[str, Any]]]):
    for where, p in papers:
        if p["verified"]:
            continue
        assert _text(p["why_not_verified"]), f"{where}: no why_not_verified"
        assert p["doi"] is None or (isinstance(p["doi"], str) and DOI.match(p["doi"])), where


def test_one_doi_is_always_the_same_paper(papers: list[tuple[str, dict[str, Any]]]):
    """A paper appears in every entry that cites it, with the same identity each time."""
    seen: dict[str, tuple[Any, ...]] = {}
    for where, p in papers:
        if p["doi"] is None:
            continue
        identity = (p["title"], p["first_author"], p["year"], p["verified"])
        assert seen.setdefault(p["doi"], identity) == identity, f"{where}: {p['doi']}"
