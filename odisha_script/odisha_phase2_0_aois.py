"""
Phase 2, step 0 — build the Odisha AOIs the pipeline runs over.

FULLY OFFLINE. No Earth Engine.

WHY
---
Only aois/sanjay_van.geojson existed, so the pipeline had never produced a stand in Odisha:
Phase 1 sampled rasters at plot points. Phase 2 runs the real method, which needs an ROI.

WHAT
----
  PILOT   the six Dhenkanal village-forest polygons in Odisha_sites.csv, each buffered by
          200 m and dissolved. The buffer is there so stands are not truncated at the village
          boundary; without it the stands touching the edge are cut, and every geometry
          statistic about them is an artefact of the clip.
            -> aois/odisha_dhenkanal_sites.geojson
  FULL    per habitation with >= 5 plots: convex hull of its plot cloud + 300 m buffer,
          overlapping hulls dissolved.
            -> aois/odisha_habitations.geojson
  DISTRICT  the full set split by district, one AOI each, because the whole set's bounding box
          (298 x 342 km) exceeds Earth Engine's 1 bn-pixel export cap. The pipeline runs per district.
            -> aois/odisha_habitations_{angul,dhenkanal,kendujhar,koraput}.geojson

Buffers are computed in the local UTM zone (fmu.utils.grid.utm_epsg_code, the same zone rule
the pipeline's analysis grid uses), per part, then brought back to EPSG:4326. The polygon
parsing (`.geo` is a LinearRing, not a Polygon) is imported from odisha_phase1_0_clean.py.

Each file is ONE Feature with a MultiPolygon geometry, because fmu.utils.gee.load_roi_geometry
turns a multi-feature collection into a MultiPolygon by assuming every feature is a Polygon.

Plot coordinates come from `plot_key` (6 dp), not from the lat/lon columns of
odisha_plots_clean.csv, which that script rounds to 4 dp (~11 m).

EXIT CONDITION
--------------
Each AOI is a valid (multi)polygon, and a point-in-polygon check over all 274 plots returns
the expected counts: 60 (pilot) and 261 (full). A mismatch is printed and the script exits
non-zero; it is not silently accepted.

Run:  python odisha_phase2_0_aois.py
Writes: ../aois/odisha_dhenkanal_sites.geojson, ../aois/odisha_habitations.geojson,
        odisha_phase2_0_results.txt
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from pyproj import Transformer
from shapely.geometry import MultiPoint, MultiPolygon, Point, mapping
from shapely.ops import transform, unary_union

from fmu.utils.grid import utm_epsg_code

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from odisha_phase1_0_clean import site_polygons  # noqa: E402

PLOTS_CSV = HERE / "odisha_plots_clean.csv"
SITES_CSV = HERE / "Odisha_sites.csv"
PILOT_OUT = REPO / "aois" / "odisha_dhenkanal_sites.geojson"
FULL_OUT = REPO / "aois" / "odisha_habitations.geojson"
RESULTS = HERE / "odisha_phase2_0_results.txt"

PILOT_BUFFER_M = 200
FULL_BUFFER_M = 300
MIN_PLOTS_PER_HABITATION = 5
EXPECTED_PILOT_PLOTS = 60
# The brief expected 261 (the plots of the 21 habitations). The dissolved hulls also contain 6 plots
# from habitations with < 5 plots; decision (Jaskaran, 2026-09-14): include them, so 267.
EXPECTED_FULL_PLOTS = 267
DISTRICT_OUT = REPO / "aois" / "odisha_habitations_{district}.geojson"

_lines: list[str] = []


def say(s: str = "") -> None:
    print(s)
    _lines.append(s)


def rule(title: str) -> None:
    say("")
    say("=" * 90)
    say(title)
    say("=" * 90)


# ---------------------------------------------------------------------- shared helpers
def load_plot_points(path: Path = PLOTS_CSV) -> pd.DataFrame:
    """The 274 plots with full-precision lon/lat parsed from plot_key."""
    df = pd.read_csv(path)
    ll = df.plot_key.str.split("_", expand=True).astype(float)
    df["lat6"], df["lon6"] = ll[0], ll[1]
    return df


def utm_transformers(lon: float, lat: float) -> tuple[int, object, object]:
    epsg = utm_epsg_code(lon, lat)
    fwd = Transformer.from_crs(4326, epsg, always_xy=True).transform
    inv = Transformer.from_crs(epsg, 4326, always_xy=True).transform
    return epsg, fwd, inv


def area_ha(geom_ll) -> float:
    c = geom_ll.centroid
    _, fwd, _ = utm_transformers(c.x, c.y)
    return transform(fwd, geom_ll).area / 10_000.0


def as_multipolygon(geom) -> MultiPolygon:
    if geom.geom_type == "Polygon":
        return MultiPolygon([geom])
    if geom.geom_type == "MultiPolygon":
        return geom
    raise ValueError(f"expected a polygonal geometry, got {geom.geom_type}")


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
                           "generated_by": "odisha_script/odisha_phase2_0_aois.py"},
            "geometry": _round(mapping(geom)),
        }],
    }
    path.write_text(json.dumps(fc, indent=1) + "\n")


def count_inside(geom, df: pd.DataFrame) -> pd.Series:
    return pd.Series([geom.covers(Point(lo, la)) for lo, la in zip(df.lon6, df.lat6)], index=df.index)


# ---------------------------------------------------------------------- pilot
def build_pilot(df: pd.DataFrame) -> tuple[MultiPolygon, bool]:
    rule(f"PILOT — six Dhenkanal site polygons, buffered {PILOT_BUFFER_M} m, dissolved")
    polys = site_polygons(SITES_CSV)
    buffered = []
    say(f"  {'site':<10} {'valid':>5} {'area_ha':>9} {'buffered_ha':>12} {'plots_in_polygon':>17}")
    for name, p in polys.items():
        c = p.centroid
        _, fwd, inv = utm_transformers(c.x, c.y)
        b = transform(inv, transform(fwd, p).buffer(PILOT_BUFFER_M))
        buffered.append(b)
        n_in = int(count_inside(p, df).sum())
        say(f"  {name:<10} {str(p.is_valid):>5} {area_ha(p):>9.1f} {area_ha(b):>12.1f} {n_in:>17}")
    total = sum(area_ha(p) for p in polys.values())
    say(f"  {'total':<10} {'':>5} {total:>9.1f}")

    aoi = as_multipolygon(unary_union(buffered))
    parts = []
    for part in aoi.geoms:
        names = [n for n, p in polys.items() if part.intersects(p)]
        parts.append({"sites": names, "area_ha": round(area_ha(part), 2)})
    say("")
    say(f"  dissolved AOI: {len(aoi.geoms)} part(s), {area_ha(aoi):.1f} ha, valid={aoi.is_valid}")
    for pt in parts:
        say(f"    part {pt['sites']}: {pt['area_ha']} ha")

    in_poly = pd.Series(False, index=df.index)
    for p in polys.values():
        in_poly |= count_inside(p, df)
    in_aoi = count_inside(aoi, df)
    say("")
    say(f"  plots inside the unbuffered polygons : {int(in_poly.sum())} (expected {EXPECTED_PILOT_PLOTS})")
    say(f"  plots inside the buffered AOI        : {int(in_aoi.sum())}")
    extra = df[in_aoi & ~in_poly]
    if len(extra):
        say(f"  {len(extra)} plot(s) fall in the 200 m buffer but outside every village polygon:")
        for r in extra.itertuples():
            say(f"    {r.plot_key}  {r.district}/{r.habitation}")
    ok = aoi.is_valid and int(in_poly.sum()) == EXPECTED_PILOT_PLOTS

    write_aoi(PILOT_OUT, aoi, "odisha_dhenkanal_sites",
              "Six FES Dhenkanal village-forest polygons (Odisha_sites.csv), each buffered 200 m "
              "in local UTM and dissolved. Pilot AOI for Phase 2 stand-level validation.",
              parts)
    say(f"  wrote {PILOT_OUT.relative_to(REPO)}")
    return aoi, ok


# ---------------------------------------------------------------------- full set
def build_full(df: pd.DataFrame) -> tuple[MultiPolygon, bool, list]:
    rule(f"FULL — habitations with >= {MIN_PLOTS_PER_HABITATION} plots: convex hull + {FULL_BUFFER_M} m, dissolved")
    counts = df.habitation.value_counts()
    keep = counts[counts >= MIN_PLOTS_PER_HABITATION].index
    say(f"  habitations: {len(counts)} total, {len(keep)} with >= {MIN_PLOTS_PER_HABITATION} plots, "
        f"holding {int(counts[keep].sum())} of {len(df)} plots")

    hulls = []
    say(f"  {'habitation':<22} {'district':<10} {'n':>3} {'hull+buffer_ha':>15}")
    for hab in sorted(keep):
        g = df[df.habitation == hab]
        lon, lat = g.lon6.mean(), g.lat6.mean()
        _, fwd, inv = utm_transformers(lon, lat)
        pts = MultiPoint([fwd(lo, la) for lo, la in zip(g.lon6, g.lat6)])
        h = transform(inv, pts.convex_hull.buffer(FULL_BUFFER_M))
        hulls.append((hab, h))
        say(f"  {hab:<22} {g.district.iloc[0]:<10} {len(g):>3} {area_ha(h):>15.1f}")

    aoi = as_multipolygon(unary_union([h for _, h in hulls]))
    parts = []
    for part in aoi.geoms:
        habs = [hab for hab, h in hulls if part.intersects(h)]
        parts.append({"habitations": habs, "area_ha": round(area_ha(part), 2)})
    say("")
    say(f"  dissolved AOI: {len(aoi.geoms)} part(s) from {len(hulls)} hulls, "
        f"{sum(p['area_ha'] for p in parts):.1f} ha, valid={aoi.is_valid}")
    for pt in parts:
        if len(pt["habitations"]) > 1:
            say(f"    merged part {pt['habitations']}: {pt['area_ha']} ha")

    in_aoi = count_inside(aoi, df)
    in_keep = df.habitation.isin(keep)
    say("")
    say(f"  plots inside the AOI                    : {int(in_aoi.sum())} (expected {EXPECTED_FULL_PLOTS})")
    say(f"  of which from a >=5-plot habitation     : {int((in_aoi & in_keep).sum())}")
    stray = df[in_aoi & ~in_keep]
    if len(stray):
        say(f"  {len(stray)} plot(s) from a <5-plot habitation fall inside a dissolved hull:")
        for r in stray.itertuples():
            say(f"    {r.plot_key}  {r.district}/{r.habitation}")
    missing = df[in_keep & ~in_aoi]
    if len(missing):
        say(f"  {len(missing)} plot(s) from a kept habitation fall OUTSIDE the AOI (should be 0)")
    ok = aoi.is_valid and int(in_aoi.sum()) == EXPECTED_FULL_PLOTS and not len(missing)

    write_aoi(FULL_OUT, aoi, "odisha_habitations",
              "Per FES habitation with >= 5 field plots: convex hull of the plot cloud plus a 300 m "
              "buffer in local UTM, overlapping hulls dissolved. Full Phase 2 AOI set.",
              parts)
    say(f"  wrote {FULL_OUT.relative_to(REPO)}")
    return aoi, ok, hulls


# ---------------------------------------------------------------------- per district
def build_districts(df: pd.DataFrame, full_aoi: MultiPolygon, hulls: list) -> bool:
    rule("PER DISTRICT — the full set split into one AOI per district")
    say("  Why: an Earth Engine export is sized by its region's bounding box. The full AOI's 20 parts")
    say("  span four districts, a 298 x 342 km box = 1.02 bn pixels at 10 m, over the 1.00 bn cap, so")
    say("  every cache export failed. Decision (Jaskaran, 2026-09-14): run the pipeline once per")
    say("  district. Same hulls, same buffer; only the grouping into files changes.")
    by_district: dict[str, list] = {}
    for hab, h in hulls:
        district = df.loc[df.habitation == hab, "district"].iloc[0]
        by_district.setdefault(district, []).append((hab, h))

    times_covered = pd.Series(0, index=df.index)
    total = 0
    say(f"  {'district':<10} {'parts':>5} {'area_ha':>8} {'plots':>5} {'bbox km':>13} {'bbox px (M)':>12}")
    for district in sorted(by_district):
        members = by_district[district]
        aoi = as_multipolygon(unary_union([h for _, h in members]))
        inside = count_inside(aoi, df)
        times_covered += inside.astype(int)
        n = int(inside.sum())
        total += n
        c = aoi.centroid
        _, fwd, _ = utm_transformers(c.x, c.y)
        minx, miny, maxx, maxy = transform(fwd, aoi).bounds
        w_km, h_km = (maxx - minx) / 1000, (maxy - miny) / 1000
        px_m = (maxx - minx) / 10 * (maxy - miny) / 10 / 1e6
        parts = [{"habitations": [hab for hab, h in members if part.intersects(h)],
                  "area_ha": round(area_ha(part), 2)} for part in aoi.geoms]
        name = f"odisha_habitations_{district.lower()}"
        write_aoi(Path(str(DISTRICT_OUT).format(district=district.lower())), aoi, name,
                  f"The {district} part of the Phase 2 full habitation set (per-habitation convex hull + "
                  f"300 m, dissolved). One of four per-district AOIs; see odisha_phase2_0_aois.py.", parts)
        say(f"  {district:<10} {len(aoi.geoms):>5} {sum(p['area_ha'] for p in parts):>8.1f} {n:>5} "
            f"{f'{w_km:.1f} x {h_km:.1f}':>13} {px_m:>12.1f}   valid={aoi.is_valid}")

    full_n = int(count_inside(full_aoi, df).sum())
    overlap = int((times_covered > 1).sum())
    say("")
    say(f"  plots over the four district AOIs: {total}; in the full AOI: {full_n}; plots in more than one "
        f"district AOI: {overlap}")
    return total == full_n and overlap == 0


def main() -> int:
    df = load_plot_points()
    say(f"plots: {len(df)} (from {PLOTS_CSV.name}; coordinates parsed from plot_key)")
    _, pilot_ok = build_pilot(df)
    full_aoi, full_ok, hulls = build_full(df)
    district_ok = build_districts(df, full_aoi, hulls)

    rule("EXIT CONDITION")
    say(f"  pilot     : {'PASS' if pilot_ok else 'FAIL'}")
    say(f"  full      : {'PASS' if full_ok else 'FAIL'}")
    say(f"  districts : {'PASS' if district_ok else 'FAIL'}")
    RESULTS.write_text("\n".join(_lines) + "\n")
    return 0 if (pilot_ok and full_ok and district_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
