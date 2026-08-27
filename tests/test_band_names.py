"""Non-live tests for synthesised band names.

Several places bolt a label band onto a feature stack so a grouped reduction,
`reduceConnectedComponents` or `stratifiedSample` has something to group by.
Each had invented its own name, and two picked a leading underscore, which EE
rejects -- at getInfo time, so both got as far as a live run:

    Image.rename: Invalid band name: '_label'        (merge, adjacency.py)
    Image.rename: Invalid band name: '_unit_label'   (clustering.py)

A third, `_r2_label` in components.py, was on the same path and had simply not
been reached yet. Fixing the two that fired and leaving the third would have
meant finding it live too, which is what makes this a class of bug rather than
two typos: the name is only validated where it is evaluated, and the tests
around each call site faked EE, so none of them could see it.

These pin the rule instead of the instances.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fmu.utils.gee import LABEL_BAND, check_band_name

SRC = Path(__file__).parent.parent / "src" / "fmu"


# ---------- the rule ----------


@pytest.mark.parametrize(
    "name", ["fmu_label", "B4_median", "canopy_height", "b", "VV", "ndvi2"]
)
def test_valid_names_pass(name):
    assert check_band_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "_label",  # the one that failed the merge stage
        "_unit_label",  # the one that failed the clustering stage
        "_r2_label",  # the one waiting in the metrics stage
        "2fast",  # leading digit
        "has space",
        "has-hyphen",
        "has.dot",
        "",
    ],
)
def test_names_earth_engine_would_reject_are_refused(name):
    with pytest.raises(ValueError, match="not a band name"):
        check_band_name(name)


def test_the_error_says_where_it_came_from():
    with pytest.raises(ValueError, match="merge criteria"):
        check_band_name("_label", context="merge criteria")


def test_the_shared_label_band_is_itself_valid():
    """It would be a poor joke to centralise the name and pick an invalid one."""
    assert check_band_name(LABEL_BAND) == LABEL_BAND


# ---------- the instances ----------


def _python_sources():
    return sorted(SRC.rglob("*.py"))


def test_no_source_file_renames_a_band_to_a_leading_underscore():
    """The literal form of both live failures. A test that faked EE could not
    have caught either, because the fake accepted any string."""
    pattern = re.compile(r"""\.rename\(\s*\[?\s*["']_""")
    offenders = [
        f"{path.relative_to(SRC)}:{i}"
        for path in _python_sources()
        for i, line in enumerate(path.read_text().splitlines(), 1)
        if pattern.search(line)
    ]
    assert not offenders, f"band names EE will reject: {offenders}"


def test_every_label_band_constant_is_the_shared_one():
    """Three modules used to define their own `label_band = "..."`, with three
    different conventions and two of them broken. One name, one place."""
    pattern = re.compile(r"""^\s*label_band\s*=\s*(["'].*["'])\s*$""")
    literals = [
        f"{path.relative_to(SRC)}:{i}: {m.group(1)}"
        for path in _python_sources()
        for i, line in enumerate(path.read_text().splitlines(), 1)
        if (m := pattern.match(line))
    ]
    assert not literals, (
        f"label band assigned a string literal instead of LABEL_BAND: {literals}"
    )


def test_the_call_sites_all_reach_for_the_constant():
    """Guards the inverse of the two tests above: they would also pass if the
    call sites stopped synthesising a label band at all."""
    users = [
        path.relative_to(SRC).as_posix()
        for path in _python_sources()
        if "LABEL_BAND" in path.read_text()
    ]
    assert {
        "utils/gee.py",
        "utils/adjacency.py",
        "utils/components.py",
        "stages/clustering.py",
    } <= set(users), users
