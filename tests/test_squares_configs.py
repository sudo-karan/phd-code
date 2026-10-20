"""Offline checks of the Odisha box runs (PHASE_SQUARES_PREDECLARED.md).

The four configs must be the 3 ha `_repro` configs with only the area, the merge rule, the name
and the Drive folder changed, and the box AOIs must be rectangles that hold the same 267 plots as
the hull AOIs they replace.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from shapely.geometry import Point, shape

from fmu.config import load_config
from fmu.utils.caching import config_fingerprint

REPO = Path(__file__).resolve().parent.parent
DISTRICTS = ("angul", "dhenkanal", "kendujhar", "koraput")
ALLOWED = {
    ("name",),
    ("description",),
    ("roi", "name"),
    ("roi", "roi_file"),
    ("merge", "pass2_skip_at_min_area"),
    ("export", "drive_folder"),
}


def _flat(d: dict, prefix: tuple = ()) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flat(v, prefix + (k,)))
        else:
            out[prefix + (k,)] = v
    return out


def _plots() -> pd.DataFrame:
    df = pd.read_csv(REPO / "odisha_script" / "odisha_plots_clean.csv")
    ll = df.plot_key.str.split("_", expand=True).astype(float)
    df["lat"], df["lon"] = ll[0], ll[1]
    return df


def _geom(path: Path):
    fc = json.loads(path.read_text())
    assert len(fc["features"]) == 1, "load_roi_geometry expects one feature"
    return shape(fc["features"][0]["geometry"])


@pytest.mark.parametrize("district", DISTRICTS)
def test_box_config_changes_only_the_area_merge_rule_name_and_folder(district: str) -> None:
    src = yaml.safe_load((REPO / f"configs/odisha_v120_3ha_{district}_repro.yaml").read_text())
    new = yaml.safe_load((REPO / f"configs/odisha_v120_3ha_squares_{district}.yaml").read_text())
    a, b = _flat(src), _flat(new)
    changed = {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}
    assert changed <= ALLOWED, sorted(changed - ALLOWED)
    assert b[("roi", "roi_file")] == f"aois/odisha_squares_{district}.geojson"
    assert b[("merge", "pass2_skip_at_min_area")] is True
    assert b[("export", "drive_folder")] == "fmu_exports_odisha_squares"


@pytest.mark.parametrize("district", DISTRICTS)
def test_box_config_loads_with_its_own_fingerprint(district: str) -> None:
    new = load_config(str(REPO / f"configs/odisha_v120_3ha_squares_{district}.yaml"))
    old = load_config(str(REPO / f"configs/odisha_v120_3ha_{district}_repro.yaml"))
    assert new.merge.pass2_skip_at_min_area is True
    assert new.clustering.k == old.clustering.k == 5
    assert new.merge.max_area_ha == old.merge.max_area_ha == 3.0
    assert config_fingerprint(new) != config_fingerprint(old)


@pytest.mark.parametrize("district", DISTRICTS)
def test_boxes_are_rectangles_that_do_not_meet(district: str) -> None:
    geom = _geom(REPO / f"aois/odisha_squares_{district}.geojson")
    assert geom.geom_type == "MultiPolygon" and geom.is_valid
    parts = list(geom.geoms)
    for p in parts:
        assert len(p.interiors) == 0
        assert p.equals(p.envelope), "every part is a north-up rectangle"
    for i, p in enumerate(parts):
        for q in parts[i + 1:]:
            assert not p.intersects(q)


def test_boxes_hold_the_same_plots_as_the_hulls() -> None:
    df = _plots()
    in_box, in_hull = set(), set()
    for d in DISTRICTS:
        box = _geom(REPO / f"aois/odisha_squares_{d}.geojson")
        hull = _geom(REPO / f"aois/odisha_habitations_{d}.geojson")
        for key, lon, lat in zip(df.plot_key, df.lon, df.lat, strict=True):
            pt = Point(lon, lat)
            if box.covers(pt):
                in_box.add(key)
            if hull.covers(pt):
                in_hull.add(key)
        # The hulls were buffered in UTM and the boxes widened on the ellipsoid, so a hull's rim
        # may poke out by a sliver of well under a square metre (1e-10 square degrees is about
        # 1.15 m2 at these latitudes; the slivers are 0.18 m2 in Dhenkanal, 0.003 m2 in Kendujhar
        # and none elsewhere; corrected 20 Oct 2026, review C24, from "~120 m2").
        assert hull.difference(box).area < 1e-10, f"{d}: a box must contain its hulls"
    assert len(in_hull) == 267
    assert in_box == in_hull
