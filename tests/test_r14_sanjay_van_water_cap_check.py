"""odisha_script/r14_sanjay_van_water_cap_check.py, offline: the cap of a band's stand means, the most
stands below the cap with the lower quartile still at it, the types matched by overlap, and the
refusal to write over a file. No real run is read."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "odisha_script"))

import r14_sanjay_van_water_cap_check as W  # noqa: E402, N812

from fmu.utils import stand_table as st  # noqa: E402


def test_the_cap_touches_the_band_alone():
    table = st.StandTable(labels=np.array([1, 2, 3]), bands=["a", "distance_to_water"],
                          values=np.array([[20000.0, 9000.0], [5.0, 12000.0], [7.0, 10000.0]]),
                          in_fit=np.array([True, True, False]))
    out = W.capped(table, "distance_to_water", 10000.0)
    assert out.values[:, 1].tolist() == [9000.0, 10000.0, 10000.0]
    assert out.values[:, 0].tolist() == [20000.0, 5.0, 7.0]
    assert table.values[1, 1] == 12000.0  # the table itself is not changed


@pytest.mark.parametrize("n", [5, 8, 101, 490])
def test_the_most_below_the_cap_with_the_lower_quartile_at_it_is_numpys(n: int):
    most = W.most_below_with_quartile_at_cap(n)
    for m in range(n):
        values = np.r_[np.full(m, 9000.0), np.full(n - m, 10000.0)]
        assert (st.exact_quartiles(values)[0] == 10000.0) == (m <= most), (n, m)
    assert W.most_below_with_quartile_at_cap(490) == 122


def test_the_band_numbers():
    b = W.band_numbers(np.array([9000.0, 10000.0, 10050.0, 10150.0, 11000.0]), 10000.0)
    assert (b["below_cap"], b["at_or_past_cap"]) == (1, 4)
    assert (b["from_cap_to_cap_plus_100_m"], b["from_cap_to_cap_plus_200_m"]) == (2, 3)


def test_types_are_matched_by_overlap():
    a = np.array([0, 0, 1, 1, 2, 2])
    assert W.changed_after_matching(a, np.array([2, 2, 0, 0, 1, 1]), 3) == 0  # the same, renamed
    assert W.changed_after_matching(a, np.array([2, 2, 0, 1, 1, 1]), 3) == 1


def test_it_refuses_to_write_over_a_file(tmp_path: Path):
    (tmp_path / "x.md").write_text("old")
    with pytest.raises(SystemExit, match="refusing to write over"):
        W.main(["--records", str(tmp_path), "--out-dir", str(tmp_path), "--stem", "x"])
    assert (tmp_path / "x.md").read_text() == "old"
