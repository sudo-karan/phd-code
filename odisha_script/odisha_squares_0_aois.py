"""Squares, step 0: the box AOIs for the Odisha re-run on squares.

FULLY OFFLINE. No Earth Engine.

WHY
---
The Phase 2 AOIs are, per habitation, the convex hull of the plots plus 300 m
(odisha_phase2_0_aois.py). On a map they are irregular blobs hugging the plots, and the
stands drawn inside them stop at the blob's edge. Jaskaran's decision of 13 Oct 2026 (option
(b) in PR #43): re-run the 3 ha feature-vector arm on a box around each village's plots
instead, so the pipeline covers a whole rectangle of landscape and the stands around the
plots are not cut by an outline drawn from the plots themselves.

WHAT
----
  BOX     per habitation with >= 5 plots (the same 21 habitations as Phase 2): the smallest
          north-up rectangle holding its plots, widened by 300 m on every side (the same
          margin the Phase 2 hulls used). The 300 m is measured on the ellipsoid (pyproj
          Geod) from the plots' extreme latitudes and longitudes.
  MERGE   boxes of one district that overlap or touch are replaced by the box around both,
          repeated until no two boxes meet, so every part stays a rectangle.
  DISTRICT one AOI file per district, as in Phase 2 (one Feature, MultiPolygon geometry,
          because fmu.utils.gee.load_roi_geometry expects that).
            -> aois/odisha_squares_{angul,dhenkanal,kendujhar,koraput}.geojson

The boxes are north-up in longitude and latitude, so they are rectangles on the web map. The
pipeline's analysis grid is UTM, where they are tilted by about one degree; that changes
nothing, since the pipeline clips to the polygon either way.

EXIT CONDITION
--------------
Every plot of a kept habitation is inside its district's boxes, no plot is inside two
districts' boxes, every box is valid, and each district's bounding box stays far under Earth
Engine's 1 bn-pixel export cap. Plots from habitations with fewer than 5 plots that fall in a
box are listed by name: they are in the mapped area, and PHASE_SQUARES_PREDECLARED.md says
how they are scored.

Run:  python odisha_script/odisha_squares_0_aois.py
Writes: aois/odisha_squares_{district}.geojson, odisha_script/odisha_squares_0_results.txt
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from pyproj import Geod
from shapely.geometry import MultiPolygon, Point, box, mapping
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from odisha_phase2_0_aois import (  # noqa: E402
    MIN_PLOTS_PER_HABITATION,
    load_plot_points,
    utm_transformers,
)

MARGIN_M = 300.0
OUT = REPO / "aois" / "odisha_squares_{district}.geojson"
RESULTS = HERE / "odisha_squares_0_results.txt"
HULL_AOI = REPO / "aois" / "odisha_habitations_{district}.geojson"
EE_PIXEL_CAP = 1e9
GEOD = Geod(ellps="WGS84")

_lines: list[str] = []


def say(s: str = "") -> None:
    print(s)
    _lines.append(s)


def rule(title: str) -> None:
    say("")
    say("=" * 90)
    say(title)
    say("=" * 90)


def transform(fn, geom):
    """Apply a pyproj transform function to every coordinate of geom."""
    return shapely.transform(geom, lambda xy: np.column_stack(fn(xy[:, 0], xy[:, 1])))


def area_ha(geom_ll) -> float:
    c = geom_ll.centroid
    _, fwd, _ = utm_transformers(c.x, c.y)
    return transform(fwd, geom_ll).area / 10_000.0


def plot_box(lons: pd.Series, lats: pd.Series, margin_m: float = MARGIN_M):
    """North-up box around the points, widened by margin_m on every side (on the ellipsoid)."""
    w, e, s, n = float(lons.min()), float(lons.max()), float(lats.min()), float(lats.max())
    mid_lat = (s + n) / 2
    west, _, _ = GEOD.fwd(w, mid_lat, 270.0, margin_m)
    east, _, _ = GEOD.fwd(e, mid_lat, 90.0, margin_m)
    _, south, _ = GEOD.fwd(w, s, 180.0, margin_m)
    _, north, _ = GEOD.fwd(w, n, 0.0, margin_m)
    return box(west, south, east, north)


def merge_touching(boxes: list[tuple[list[str], object]]) -> list[tuple[list[str], object]]:
    """Replace boxes that overlap or touch by the box around both, until no two meet."""
    items = [(sorted(names), b) for names, b in boxes]
    changed = True
    while changed:
        changed = False
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                if items[i][1].intersects(items[j][1]):
                    names = sorted(items[i][0] + items[j][0])
                    merged = box(*unary_union([items[i][1], items[j][1]]).bounds)
                    items = [x for k, x in enumerate(items) if k not in (i, j)] + [(names, merged)]
                    changed = True
                    break
            if changed:
                break
    return sorted(items, key=lambda x: (x[1].bounds[1], x[1].bounds[0]))


def side_m(b) -> tuple[float, float]:
    c = b.centroid
    _, fwd, _ = utm_transformers(c.x, c.y)
    minx, miny, maxx, maxy = transform(fwd, b).bounds
    return maxx - minx, maxy - miny


def square_of(b):
    """The square (equal sides in metres) centred on box b with the side of its longer edge.
    Reported for comparison only; the AOIs are the boxes."""
    c = b.centroid
    _, fwd, inv = utm_transformers(c.x, c.y)
    minx, miny, maxx, maxy = transform(fwd, b).bounds
    side = max(maxx - minx, maxy - miny)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    return transform(inv, box(cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2))


def _round(obj, nd=7):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, (list, tuple)):
        return [_round(v, nd) for v in obj]
    if isinstance(obj, dict):
        return {k: _round(v, nd) for k, v in obj.items()}
    return obj


def write_aoi(path: Path, geom: MultiPolygon, name: str, description: str, parts: list[dict]) -> None:
    fc = {
        "type": "FeatureCollection",
        "name": name,
        "description": description,
        "features": [{
            "type": "Feature",
            "properties": {"name": name, "n_parts": len(geom.geoms), "parts": parts,
                           "generated_by": "odisha_script/odisha_squares_0_aois.py"},
            "geometry": _round(mapping(geom)),
        }],
    }
    path.write_text(json.dumps(fc, indent=1) + "\n")


def hull_area(district: str) -> float:
    g = json.loads(Path(str(HULL_AOI).format(district=district.lower())).read_text())
    from shapely.geometry import shape

    return area_ha(shape(g["features"][0]["geometry"]))


def main() -> int:
    df = load_plot_points()
    say(f"plots: {len(df)} (coordinates parsed from plot_key)")
    counts = df.habitation.value_counts()
    keep = set(counts[counts >= MIN_PLOTS_PER_HABITATION].index)
    say(f"habitations with >= {MIN_PLOTS_PER_HABITATION} plots: {len(keep)}, holding "
        f"{int(counts[list(keep)].sum())} plots")

    rule(f"BOXES: per habitation, the plots' north-up box widened by {MARGIN_M:.0f} m; "
         "boxes that meet are merged")
    ok = True
    covered_by = pd.Series(0, index=df.index)
    totals = {"box": 0.0, "square": 0.0, "hull": 0.0}
    say(f"  {'district':<10} {'boxes':>5} {'box_ha':>8} {'hull_ha':>8} {'square_ha':>9} {'plots':>5} "
        f"{'bbox km':>13} {'bbox px (M)':>12}")
    detail: list[str] = []
    for district in sorted(df.district.unique()):
        members = sorted(h for h in keep if (df.habitation == h).any()
                         and df.loc[df.habitation == h, "district"].iloc[0] == district)
        if not members:
            continue
        boxes = [([h], plot_box(df.loc[df.habitation == h, "lon6"], df.loc[df.habitation == h, "lat6"]))
                 for h in members]
        merged = merge_touching(boxes)
        geom = MultiPolygon([b for _, b in merged])
        valid = geom.is_valid and all(b.is_valid for _, b in merged)
        inside = pd.Series([geom.covers(Point(lo, la)) for lo, la in zip(df.lon6, df.lat6, strict=True)],
                           index=df.index)
        covered_by += inside.astype(int)
        own = df.habitation.isin(members)
        missing = df[own & ~inside]
        parts = []
        for names, b in merged:
            in_b = [geom_pt for geom_pt in zip(df.lon6, df.lat6, strict=True) if b.covers(Point(*geom_pt))]
            w_m, h_m = side_m(b)
            parts.append({"habitations": names, "area_ha": round(area_ha(b), 2),
                          "plots": len(in_b), "width_m": round(w_m), "height_m": round(h_m)})
        a_box = sum(p["area_ha"] for p in parts)
        a_sq = sum(area_ha(square_of(b)) for _, b in merged)
        a_hull = hull_area(district)
        totals["box"] += a_box
        totals["square"] += a_sq
        totals["hull"] += a_hull
        c = geom.centroid
        _, fwd, _ = utm_transformers(c.x, c.y)
        minx, miny, maxx, maxy = transform(fwd, geom).bounds
        px_m = (maxx - minx) / 10 * (maxy - miny) / 10 / 1e6
        say(f"  {district:<10} {len(merged):>5} {a_box:>8.1f} {a_hull:>8.1f} {a_sq:>9.1f} "
            f"{int(inside.sum()):>5} {f'{(maxx - minx) / 1000:.1f} x {(maxy - miny) / 1000:.1f}':>13} "
            f"{px_m:>12.1f}   valid={valid}")
        for p in parts:
            detail.append(f"  {district:<10} {', '.join(p['habitations']):<34} {p['width_m']:>6} x "
                          f"{p['height_m']:<6} m {p['area_ha']:>8.1f} ha {p['plots']:>4} plots")
        if len(missing):
            ok = False
            say(f"    {len(missing)} plot(s) of a kept habitation fall OUTSIDE the boxes (should be 0)")
        if not valid or px_m * 1e6 > EE_PIXEL_CAP:
            ok = False
        name = f"odisha_squares_{district.lower()}"
        write_aoi(Path(str(OUT).format(district=district.lower())), geom, name,
                  f"The {district} boxes for the Odisha re-run on squares: per habitation with >= 5 "
                  f"plots, the plots' north-up box widened by {MARGIN_M:.0f} m on every side, boxes "
                  f"that meet merged into one. See odisha_script/odisha_squares_0_aois.py.", parts)
    say(f"  {'total':<10} {'':>5} {totals['box']:>8.1f} {totals['hull']:>8.1f} {totals['square']:>9.1f} "
        f"{int((covered_by > 0).sum()):>5}")
    say("")
    say("  box_ha: the AOIs written here. hull_ha: the Phase 2 AOIs they replace. square_ha: what")
    say("  exact squares (side = the box's longer edge) would cover; reported only, not used.")

    rule("THE BOXES, ONE LINE EACH (width x height on the ground)")
    for line in detail:
        say(line)

    rule("PLOTS")
    in_any = covered_by > 0
    own_all = df.habitation.isin(keep)
    say(f"  plots inside a box: {int(in_any.sum())} of {len(df)}")
    say(f"    from a habitation with >= {MIN_PLOTS_PER_HABITATION} plots: {int((in_any & own_all).sum())}")
    stray = df[in_any & ~own_all]
    say(f"    from a habitation with fewer plots, inside a box all the same: {len(stray)}")
    for r in stray.itertuples():
        say(f"      {r.plot_key}  {r.district}/{r.habitation}")
    outside = df[~in_any]
    say(f"  plots outside every box: {len(outside)}")
    for r in outside.itertuples():
        say(f"      {r.plot_key}  {r.district}/{r.habitation}")
    twice = int((covered_by > 1).sum())
    say(f"  plots inside two districts' boxes: {twice}")
    if twice:
        ok = False

    rule("EXIT CONDITION")
    say(f"  boxes: {'PASS' if ok else 'FAIL'}")
    RESULTS.write_text("\n".join(_lines) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
