"""odisha_script/odisha_keptland_score.py, offline: the declared join and the five statistics.

The statistics are checked against odisha_phase3_3_significance.scorer_observed, the scorer's own
arithmetic, on both committed Phase 3 tables and with a field type left out; the join's rules
(covered, the lowest stand id, the 30 m rule and its ties, left out past 30 m) on a small layer.
No kept-land run is scored here.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "odisha_script"))

pytest.importorskip("shapely")
import odisha_keptland_score as K  # noqa: E402, N812
import odisha_phase3_3_significance as G  # noqa: E402, N812


@pytest.mark.parametrize("arm", ["v120", "v120_3ha"])
@pytest.mark.parametrize("excluded", [(), (0,)])
def test_the_five_statistics_are_the_scorers(arm, excluded):
    joined = pd.read_csv(G.JOINED[arm]).merge(pd.read_csv(K.FIELD_TYPES)[["plot_key", "field_type"]],
                                              on="plot_key", validate="1:1")
    d = joined.rename(columns={f"{arm}_merged_id": "sid", f"{arm}_merged_cluster": "cluster"})
    d = d[~d.field_type.isin(list(excluded))]
    mine = K.five_scores(d[["district", "lat6", "lon6", "field_type", "sid", "cluster"]])
    theirs = G.scorer_observed(arm, excluded=excluded)
    for key, _ in K.STATS:
        assert math.isclose(mine[key], theirs[key], rel_tol=0, abs_tol=1e-12), (arm, excluded, key)


def _layer(tmp_path: Path) -> Path:
    """Three stands near (85.0 E, 21.0 N), in degrees: 2, and 1 overlapping its east part (a plot
    there is covered by both); 7 lies apart, east."""
    def sq(x0, x1, y0=21.0, y1=21.001):
        return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}
    feats = [{"type": "Feature", "geometry": sq(85.0, 85.001), "properties": {"stand_lbl": 2, "cluster_id": 1.0000000001, "area_ha": 1.0}},
             {"type": "Feature", "geometry": sq(85.0008, 85.002), "properties": {"stand_lbl": 1, "cluster_id": 3.9999999999, "area_ha": 1.0}},
             {"type": "Feature", "geometry": sq(85.0030, 85.004), "properties": {"stand_lbl": 7, "cluster_id": 2.0, "area_ha": 1.0}}]
    path = tmp_path / "layer.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return path


def _plots(points: dict[str, tuple[float, float]]) -> pd.DataFrame:
    rows = [{"plot_key": k, "lon6": lo, "lat6": la, "epsg": 32645} for k, (lo, la) in points.items()]
    return pd.DataFrame(rows)


def test_the_join_follows_the_declared_rule(tmp_path):
    layer = _layer(tmp_path)
    plots = _plots({
        "inside_2": (85.0005, 21.0005),      # covered by stand 2 alone
        "on_the_edge": (85.0009, 21.0005),   # covered by 2 and 1: the lowest id, 1
        "near_1": (85.0021, 21.0005),        # outside, about 10 m east of stand 1: by the 30 m rule
        "between": (85.0025, 21.0005),       # outside, about 52 m from 1 and from 7: left out
        "far": (85.0100, 21.0005),           # outside, far from all: left out
    })
    j = K.join(plots, layer, K.REACH_M).set_index("plot_key")
    assert (j.loc["inside_2", "sid"], j.loc["inside_2", "how"], j.loc["inside_2", "cluster"]) == (2, "covered", 1.0)
    assert (j.loc["on_the_edge", "sid"], j.loc["on_the_edge", "how"]) == (1, "covered")
    assert (j.loc["near_1", "sid"], j.loc["near_1", "how"], j.loc["near_1", "cluster"]) == (1, "within", 4.0)
    assert 5 < j.loc["near_1", "dist_m"] <= K.REACH_M
    for k in ("between", "far"):
        assert j.loc[k, "how"] == "none" and math.isnan(j.loc[k, "sid"])
    assert j.loc["between", "dist_m"] > K.REACH_M
    # Without the 30 m rule, the plot near stand 1 is left out too.
    j0 = K.join(plots, layer, None).set_index("plot_key")
    assert j0.loc["near_1", "how"] == "none" and j0.loc["inside_2", "sid"] == 2


def test_a_tie_within_30_m_goes_to_the_lowest_stand_id(tmp_path):
    layer = _layer(tmp_path)
    # Halfway between stand 1 (ends at 85.002) and stand 7 (starts at 85.003)? That is ~52 m from
    # each. Move stand 7 to make a tie inside the reach: a plot 10 m from both stands 1 and 7.
    g = json.loads(layer.read_text())
    g["features"][2]["geometry"]["coordinates"][0] = [[85.00219, 21.0], [85.003, 21.0], [85.003, 21.001],
                                                      [85.00219, 21.001], [85.00219, 21.0]]
    layer.write_text(json.dumps(g))
    mid = (85.002 + 85.00219) / 2
    j = K.join(_plots({"tie": (mid, 21.0005)}), layer, K.REACH_M).set_index("plot_key")
    assert (j.loc["tie", "sid"], j.loc["tie", "how"]) == (1, "within")
