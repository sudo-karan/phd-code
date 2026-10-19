"""REHEARSAL of the chance test of the Odisha kept-land field check (PHASE_KEPTLAND_PREDECLARED.md).

    python odisha_script/odisha_keptland_chance.py [--rotations 1999] [--out-dir odisha_script/keptland_scores]

Offline; no Earth Engine. Every random stream is seeded from a fixed string.

WHY A REHEARSAL. The declaration defers the chance test (Jaskaran, 15 Oct). The stands scored here
are those of the four `_keptland_s1desc` runs as they stand, from before the cache fix of round 9
(roadmap 1, #44 items 1 and 2). They are re-run after the fix and re-scored then; that run, not
this one, is the declared test's result. This file shows that the test can be built on kept land,
what it costs, and what it gives on the stands we have now. Its pass/fail lines are what the
declared rule would say on these stands, and nothing more.

WHAT IS DECLARED, AND FOLLOWED. The rotation null of odisha_phase3_3_significance.py, as declared
for the boxes (PHASE_SQUARES_PREDECLARED.md): within each box the plot cloud is rotated and moved
rigidly to a random position with every plot inside the box; 1,999 realisations; the unconditional
null for the three drawing scores and the conditional (typed-stand) null for the two labelling
scores; the seed strings of that script with this arm's name; Holm over the five tests; a test
passes at a Holm-corrected p of at most 0.05. The kept-land declaration's two changes:
  * each placed plot joins a stand by the declared rule: the stand that covers it (several: the
    lowest stand id), else the nearest stand whose edge lies within 30 m (ties: the lowest id);
  * a placed plot with no stand within 30 m is left out of that one realisation; no plot is forced
    to land on a stand, so a draw is accepted as soon as every plot lies inside its box.
The five scores are odisha_keptland_score.five_scores', computed on arrays with the functions of
odisha_phase3_3_significance (multi_ari, pair_precision, lab_wmean); the observed values must
match the committed keptland_s1desc_scores.json to 1e-12 or the script stops.

WHERE THE DECLARATION IS SILENT, the village-outline test's rule (odisha_phase3_3_significance.py,
odisha_phase2_5_stats.rotation_null) is used. Each point but Q3 and Q5 is asked under "Questions" in
docs/handoff/2026-10-17-round9-chat.md, under its own numbers: Q1 is its question 1, Q2 its 4, Q4
its 5, Q6 its 6, Q7 its 2 and Q8 its 7 (review C7, 20 Oct 2026: this said each point is listed
there, and the report cited "Q1-Q6" in both places):
  Q1  which plots are scored in a realisation: the plots the observed join scores (264), each left
      out of a realisation in which it has no stand within 30 m. The 3 plots with no stand within
      30 m at their real position move with their box's cloud but are never scored, as plots
      without a stand were never scored in the village test;
  Q2  the conditional labelling null: each box's layer limited to typed stands, its own seed. On
      kept land every stand has a type (D3), so this null differs from the unconditional one only
      in its random stream. Were some stands untyped, a placed plot's 30 m search would run over
      typed stands only and could reach past an untyped stand, which the observed join never does;
  Q3  the far-apart pairs: fixed from the plots' real positions (same district, over 2 km), each
      pair used in a realisation when both plots are typed there;
  Q4  S1 and S2 with the chance test: the same realisations, scored with field type 0 masked out
      (S1) or with the four-type typology (S2), as the village test's sensitivity runs did; Holm
      within each. The declaration's other two checks (covered plots only; beside the box runs)
      are descriptive in keptland_s1desc_scores.txt and get no chance test here;
  Q5  the box declaration's check "how far the null moves the plots", reported here too;
  Q6  the arm name in the seed strings: v120_3ha_squares_keptland_s1desc. The seeds do not take
      the run suffix, and with no forced landing the placements no longer depend on the stands, so
      the declared run on the re-run stands draws the same placements as this rehearsal;
  Q7  what the labelling mean averages over: without forced landing a district can drop out of
      the plot-weighted mean in a realisation (it needs 2 plots and 2 field types there), and the
      stands holding 2 or more plots change too. Each realisation is scored as it falls, as the
      village test scores whatever its realisation gives; how often the mean covers fewer
      districts than the observed one is reported;
  Q8  Holm when a test is not estimable: over the estimable tests only, m their number (the
      village test's rule).
CHECK C1 (odisha_script/PHASE_KEPTLAND_AMENDMENT_chance_checks.md, amending the declaration by
reference): score 4 without Kendujhar on both sides, the observed value and every realisation of
the conditional null, reported beside score 4, outside the Holm correction, with no pass or fail.

Boxes are named as odisha_phase2_5_stats.load names AOI parts (the mode of the plots' site polygon,
else of their habitation), which is what the acceptance estimate's seed string is built from.
Sampler, draw cap and unbuildable-null rule are rotation_null's (geometric acceptance below 0.02
-> the feasible-region sampler; a part that cannot place its realisations within the cap makes the
whole null unbuilt, and every test NOT ESTIMABLE).

INPUTS. The stands: by default as the explorer holds them, ui_data/by_run/<run>/stands.json
(polyline6 at 1e-6 degrees, every merged stand of the run, unsimplified). That is close but not
bit-identical to the merged layers: the observed join is the same for all 267 plots, but in a
review over 1,999 realisations for angul, dhenkanal and kendujhar the stand chosen differed in 107
of 243,878 placed plots, all near a stand edge or the 30 m limit (koraput's layer is off git and
was not compared). Good enough for a rehearsal; the declared run reads the merged layers. With
--stands-from geojson,
the merged stand layers <run>_stands_merged.geojson (docs/reproducibility/keptland_runs/ or where a
run's off-git record says, SHA-256 checked), which is how re-run stands are read (--run-suffix _r9;
ui_data is not updated in round 9). The output is labelled a rehearsal unless --declared is given;
--declared needs the merged layers and stops if any of them is a pre-fix run's file. Either way the declared join on them is checked plot by plot
against the field check's <scored-stem>_joined.csv before any null is drawn, and the observed scores
against <scored-stem>_scores.json. Also: the box outlines aois/odisha_squares_<district>.geojson, and
the plots and field types (odisha_phase3_0_field_types.csv, _k4.csv).

OTHER RUNS, ANOTHER ARM (round 10, 18 Oct 2026). --runs names the runs scored by a pattern with
{district}, as odisha_keptland_score.py's --runs does, for runs that are not the default name plus
a --run-suffix: the AlphaEarth arm's odisha_alphaearth_3ha_squares_{district}_keptland_r9. --arm
names the arm in the seed strings; by default it is the runs' own name without "odisha_", the
district or the run suffixes: a round's (_r9, _r13 and so on, and _r9_check) and _repro, numbered
or not (CLAUDE.md's from-scratch copy, so a _repro re-run, or a later round's re-run, draws its
source's placements; review of 19 Oct 2026, B22, and a check of its fix in round 13), which for
the default runs, with or without _r9, is v120_3ha_squares_keptland_s1desc as before (Q6), and for the
AlphaEarth arm alphaearth_3ha_squares_keptland: each arm its own seeds, as the village test seeds
each arm.

WRITES, in --out-dir: keptland_s1desc_chance_rehearsal.txt and .json for the pre-fix runs, or
<scored-stem>_chance.txt and .json for runs with a suffix; results only (no dates, no run times; the
inputs' SHA-256 in the JSON); <same stem>_run.json, the run's record (command, date, git commit,
dirty tree); run times in a .log beside them (ignored). A run with other than 1,999 rotations gets
the suffix _rot<n>, so a short run cannot land on either file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import shapely
import shapely.ops
from shapely import STRtree
from shapely.geometry import shape
from sklearn.metrics import adjusted_rand_score as ari

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

import odisha_keptland_score as K  # noqa: E402, N812
import odisha_phase2_5_stats as S  # noqa: E402, N812
import odisha_phase3_3_significance as G  # noqa: E402, N812
from odisha_phase2_0_aois import load_plot_points, utm_transformers  # noqa: E402

ARM = "v120_3ha_squares_keptland_s1desc"
SEED_UNCOND = G.SEED_UNCOND.format(arm=ARM)
SEED_LABELLED = G.SEED_LABELLED.format(arm=ARM)
N_ROT = 1999
ALPHA = 0.05
REACH_M = K.REACH_M
DISTANT_M = K.DISTANT_M
UI_DATA = REPO / "ui_data" / "by_run"
AOI_DIR = REPO / "aois"
SCORES_DIR = HERE / "keptland_scores"
STATS = K.STATS
DELIN = ("delin_all", "delin_multi", "prec")    # against the unconditional null
LABEL = ("lab_wmean", "far_gap")                # against the conditional null
#: check C1 (PHASE_KEPTLAND_AMENDMENT_chance_checks.md): score 4 without this district, on both sides
C1_LEFT_OUT = "kendujhar"
ANALYSES = (("primary", "the primary field types, every plot the join scores"),
            ("S1", "field type 0 (no trees) left out, same realisations"),
            ("S2", "four field types (odisha_phase3_0_field_types_k4.csv), same realisations"))

#: a run suffix the seed strings do not take (Q6): a round's (_r9, _r13, ..., and _r9_check), and
#: _repro, numbered or not, CLAUDE.md's from-scratch copy of a config (review of 19 Oct 2026, B22;
#: until a check of its fix in round 13 only _repro, _r9_check and _r9)
RUN_SUFFIX = re.compile(r"(_r\d+(_check)?|_repro\d*)$")

_lines: list[str] = []
_timings: list[str] = []


def arm_from_runs(pattern: str) -> str:
    """The arm's name in the seed strings, from the runs' name pattern: without "odisha_", the
    district and the trailing run suffixes (RUN_SUFFIX, as many as there are: _r9_repro, a
    from-scratch copy of an _r9 run, is seeded as the _r9 run, and _r13 as well). The default runs
    give ARM, with or without a run suffix."""
    arm = pattern.removeprefix("odisha_").replace("{district}_", "").replace("_{district}", "")
    while m := RUN_SUFFIX.search(arm):
        arm = arm[: m.start()]
    return arm


def say(s: str = "") -> None:
    print(s, flush=True)
    _lines.append(s)


def note_time(s: str) -> None:
    print(s, flush=True)
    _timings.append(s)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------- inputs
def decode_polyline6(s: str) -> list[list[float]]:
    """Google's encoded polyline at 6 decimals, latitude first, back to [lon, lat] pairs: the
    inverse of scripts/build_ui_early_data.polyline6."""
    out, i, lat, lon = [], 0, 0, 0
    while i < len(s):
        vals = []
        for _ in range(2):
            shift = res = 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                res |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            vals.append(~(res >> 1) if res & 1 else res >> 1)
        lat += vals[0]
        lon += vals[1]
        out.append([lon / 1e6, lat / 1e6])
    return out


def ui_stands(path: Path) -> pd.DataFrame:
    """One row per stand polygon of a run's stands.json: sid (stand_lbl), cluster (rounded
    cluster_id or NaN) and the geometry in lon/lat."""
    d = json.loads(path.read_text())
    if d.get("encoding") != "polyline6":
        raise SystemExit(f"{path}: expected polyline6 encoding, got {d.get('encoding')!r}")
    rows = []
    for f in d["features"]:
        p = f["properties"]
        polys = [[decode_polyline6(r) for r in poly] for poly in f["polygons"]]
        ct = p["stand_type"]
        rows.append({"sid": int(p["stand_id"]), "cluster": np.nan if ct is None else float(ct),
                     "geom_ll": shape({"type": "MultiPolygon", "coordinates": polys})})
    return pd.DataFrame(rows)


class Layer:
    """A run's stand polygons in one UTM zone: prepared geometries, their tree, the stand key (one
    code per (district, stand id), ordered as the ids are) and the stand type."""

    def __init__(self, stands: pd.DataFrame, district: str, epsg: int, code: dict, typed_only: bool):
        fwd = utm_transformers_epsg(epsg)
        st = stands[stands.cluster.notna()] if typed_only else stands
        self.geoms = np.array([shapely.ops.transform(fwd, g) for g in st.geom_ll])
        shapely.prepare(self.geoms)
        self.tree = STRtree(self.geoms)
        self.key = np.array([code[(district, int(s))] for s in st.sid], float)
        self.cluster = st.cluster.to_numpy(float)


def utm_transformers_epsg(epsg: int):
    from pyproj import Transformer
    return Transformer.from_crs(4326, int(epsg), always_xy=True).transform


def box_parts(aoi_dir: Path = AOI_DIR) -> list[dict[str, Any]]:
    """The 20 boxes in district order, each in the UTM zone of its centroid (as the join)."""
    parts = []
    for district in K.DISTRICTS:
        feat = json.loads((aoi_dir / f"odisha_squares_{district}.geojson").read_text())["features"][0]
        for k, g in enumerate(shape(feat["geometry"]).geoms):
            c = g.centroid
            epsg, fwd, _ = utm_transformers(c.x, c.y)
            props = feat["properties"]["parts"][k]
            parts.append({"district": district, "k": k, "epsg": int(epsg), "geom_ll": g,
                          "geom": shapely.ops.transform(fwd, g), "props": props,
                          "name": f"{district}:{'/'.join(props.get('habitations') or [f'part{k}'])}"})
            shapely.prepare(parts[-1]["geom"])
    return parts


def load_plots(parts: list[dict[str, Any]]) -> pd.DataFrame:
    """The plots inside the boxes, sorted by plot_key: field types (primary and four-type), box
    index, district and UTM x/y in their box's zone."""
    pts = load_plot_points()
    ft = pd.read_csv(K.FIELD_TYPES)[["plot_key", "field_type"]]
    k4 = pd.read_csv(K.FIELD_TYPES_K4)[["plot_key", "field_type"]].rename(columns={"field_type": "ft_k4"})
    pts = pts.merge(ft, on="plot_key", how="left", validate="1:1").merge(k4, on="plot_key", how="left",
                                                                         validate="1:1")
    ll = shapely.points(pts.lon6.to_numpy(float), pts.lat6.to_numpy(float))
    part = np.full(len(pts), -1)
    for q, p in enumerate(parts):
        part[shapely.covers(p["geom_ll"], ll) & (part < 0)] = q
    pts["aoi_part"] = part
    plots = pts[pts.aoi_part >= 0].sort_values("plot_key").reset_index(drop=True)
    plots["box_district"] = [parts[q]["district"] for q in plots.aoi_part]
    x, y = np.empty(len(plots)), np.empty(len(plots))
    for q, p in enumerate(parts):
        m = plots.aoi_part.to_numpy() == q
        if m.any():
            x[m], y[m] = utm_transformers_epsg(p["epsg"])(plots.lon6.to_numpy(float)[m],
                                                          plots.lat6.to_numpy(float)[m])
    plots["x"], plots["y"] = x, y
    if plots.field_type.isna().any() or plots.ft_k4.isna().any():
        raise SystemExit("a plot inside the boxes has no field type")
    name_parts(parts, plots)
    return plots


def name_parts(parts: list[dict[str, Any]], plots: pd.DataFrame) -> None:
    """Each box's name by odisha_phase2_5_stats.load's rule: the mode of the site polygon of the
    plots inside it, else of their habitation, else the box's own habitations; prefixed by the
    district. The rotation null builds its acceptance estimate's seed from this name."""
    for q, p in enumerate(parts):
        inside = plots[plots.aoi_part == q]
        sp = inside.site_polygon.dropna() if "site_polygon" in inside else pd.Series([], dtype=object)
        if len(sp):
            nm = sp.mode().iat[0]
        elif len(inside) and inside.habitation.notna().any():
            nm = inside.habitation.dropna().mode().iat[0]
        else:
            nm = "/".join(p["props"].get("sites") or p["props"].get("habitations") or [f"part{p['k']}"])
        p["name"] = f"{p['district']}:{nm}"


# ---------------------------------------------------------------------- the declared join, on arrays
def assign(xy: np.ndarray, lay: Layer, reach_m: float = REACH_M) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Each point's stand by the declared rule. Returns (key, cluster, distance): the stand covering
    it (distance 0; several: the lowest stand id), else the nearest stand whose edge lies within
    reach_m (ties: the lowest stand id), else NaN, NaN, inf. A stand in pieces is as near as its
    nearest piece, and the point takes that piece's type."""
    n = len(xy)
    key, cl, dist = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.inf)
    if not n or not len(lay.geoms):
        return key, cl, dist
    pts = shapely.points(xy[:, 0], xy[:, 1])
    i, j = lay.tree.query(pts, predicate="dwithin", distance=reach_m)
    if not len(i):
        return key, cl, dist
    d = shapely.distance(pts[i], lay.geoms[j])
    order = np.lexsort((lay.key[j], d, i))          # per point: nearest first, then the lowest stand id
    i, j, d = i[order], j[order], d[order]
    first = np.unique(i, return_index=True)[1]
    i, j, d = i[first], j[first], d[first]
    keep = d <= reach_m
    i, j, d = i[keep], j[keep], d[keep]
    key[i], cl[i], dist[i] = lay.key[j], lay.cluster[j], d
    return key, cl, dist


# ---------------------------------------------------------------------- the null
def draw_null(plots: pd.DataFrame, parts: list[dict[str, Any]], layers: dict[int, Layer], n: int,
              rng: np.random.Generator, tag: str, cap_scale: float = 1.0) -> dict[str, Any]:
    """n realisations: per box, the plot cloud rotated and moved rigidly to a random position with
    every plot inside the box (rotation_null's scheme, samplers and draw cap); then each plot joins
    by the declared rule. No plot is forced onto a stand. Returns key and cluster arrays (n, plots;
    NaN where a plot has no stand within 30 m), each plot's displacement, the draws per box, and the
    boxes that could not be placed (a non-empty list means the null is not built)."""
    n_plots = len(plots)
    key, cl, moved = (np.full((n, n_plots), np.nan) for _ in range(3))
    xy = plots[["x", "y"]].to_numpy()
    draws: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    for q, part in enumerate(parts):
        idx = np.where(plots.aoi_part.to_numpy() == q)[0]
        if not len(idx):
            continue
        lay, poly = layers[q], part["geom"]
        c0 = xy[idx].mean(0)
        rel = xy[idx] - c0
        minx, miny, maxx, maxy = poly.bounds
        if part.get("_rel") is None or not np.array_equal(part["_rel"], rel):
            acc = S.geometric_acceptance(poly, rel, S.seeded(f"accept/{part['name']}"))
            part.update(_rel=rel, _accept=acc, _sampler=None, _no_angle=False)
            if acc < S.PLAIN_MIN_ACCEPT:
                try:
                    part["_sampler"] = S.FeasibleRegionSampler(poly, rel)
                except RuntimeError as e:
                    if str(e) != S.NO_FEASIBLE_ANGLE:
                        raise
                    part["_no_angle"] = True
        sampler = part["_sampler"]
        kind = "plain" if sampler is None else "feasible-region"
        cap = S.null_draw_cap(n, cap_scale)
        if part["_no_angle"]:
            failures.append({"part": part["name"], "accepted": 0, "cap": cap, "sampler": S.NO_ANGLE_SAMPLER})
            continue
        tries, failed, accepted = 0, False, 0
        t0 = time.time()
        for r in range(n):
            while True:
                tries += 1
                if tries > cap:
                    failed = True
                    break
                if sampler is None:
                    th = rng.uniform(0, 2 * np.pi)
                    c1 = np.array([rng.uniform(minx, maxx), rng.uniform(miny, maxy)])
                else:
                    th, c1, _ = sampler.draw(rng)
                rot = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
                new = rel @ rot.T + c1
                if shapely.intersects_xy(poly, new[:, 0], new[:, 1]).all():
                    break
            if failed:
                break
            accepted = r + 1
            k_, c_, _ = assign(new, lay)
            key[r, idx], cl[r, idx] = k_, c_
            moved[r, idx] = np.hypot(*(new - xy[idx]).T)
        if failed:
            failures.append({"part": part["name"], "accepted": accepted, "cap": cap, "sampler": kind,
                             "geometric_acceptance": part["_accept"]})
            continue
        draws[part["name"]] = {"draws_per_realisation": tries / n, "sampler": kind,
                               "geometric_acceptance": part["_accept"]}
        note_time(f"    [{tag}] {part['name']}: {n} realisations, {tries} draws ({kind}), {time.time() - t0:.1f} s")
    return {"key": key, "cluster": cl, "moved": moved, "draws": draws, "failures": failures}


# ---------------------------------------------------------------------- the five scores on arrays
class Scoring:
    """One analysis (primary, S1 or S2): field types, the plots it may score (`base`: the plots the
    observed join scores, minus an excluded field type) and its far-apart pairs, fixed from the real
    positions (same district, over 2 km, both plots in `base`)."""

    def __init__(self, plots: pd.DataFrame, ft: np.ndarray, base: np.ndarray):
        self.ft, self.base = ft.astype(int), base
        self.dist = plots.box_district.to_numpy().astype(str)
        i, j = np.triu_indices(len(plots), 1)
        lon, lat = plots.lon6.to_numpy(float), plots.lat6.to_numpy(float)
        _, _, dm = G.GEOD.inv(lon[i], lat[i], lon[j], lat[j])
        far = (dm > DISTANT_M) & (self.dist[i] == self.dist[j]) & base[i] & base[j]
        self.fi, self.fj = i[far], j[far]
        self.alike = self.ft[self.fi] == self.ft[self.fj]

    def delin(self, key: np.ndarray) -> dict[str, float]:
        a = self.base & np.isfinite(key)
        f, s = self.ft[a], key[a]
        if a.sum() < 2:
            return {"delin_all": np.nan, "delin_multi": np.nan, "prec": np.nan}
        return {"delin_all": float(ari(f, s)), "delin_multi": float(G.multi_ari(f, s)[0]),
                "prec": float(G.pair_precision(f, s))}

    def label(self, cl: np.ndarray) -> dict[str, float]:
        lab = self.base & np.isfinite(cl)
        w, per = G.lab_wmean(self.ft[lab], cl[lab], self.dist[lab])
        ok = lab[self.fi] & lab[self.fj]
        same = cl[self.fi] == cl[self.fj]
        a, b = ok & self.alike, ok & ~self.alike
        gap = float(same[a].mean() - same[b].mean()) if a.any() and b.any() else np.nan
        return {"lab_wmean": float(w), "far_gap": gap, **{f"lab_{d}": float(v) for d, v in per.items()}}

    def all(self, key: np.ndarray, cl: np.ndarray) -> dict[str, float]:
        return {**self.delin(key), **self.label(cl)}


def holm(p: list[float]) -> list[float]:
    """Holm's step-down adjusted p-values, in the input order."""
    m = len(p)
    out = [0.0] * m
    running = 0.0
    for rank, t in enumerate(np.argsort(p, kind="stable")):
        running = max(running, min(1.0, (m - rank) * p[t]))
        out[t] = running
    return out


def summarise(obs: float, null: np.ndarray) -> dict[str, Any]:
    v = null[np.isfinite(null)]
    pc, n = S.percentile(obs, null)
    p, _ = G.p_upper(obs, null)
    med, p5, p95 = S.qs(v)
    est = n >= S.MIN_NULL and np.isfinite(obs)
    return {"observed": obs, "null_median": med if est else None, "null_p5": p5 if est else None,
            "null_p95": p95 if est else None, "pctile": pc if est else None, "p": p if est else None,
            "n_null": int(n)}


# ---------------------------------------------------------------------- main
def suffix(n_rot: int) -> str:
    return "" if n_rot == N_ROT else f"_rot{n_rot}"


def out_stem(scored_stem: str, rehearsal: bool, n_rot: int) -> str:
    """keptland_s1desc_chance_rehearsal for the pre-fix runs; <scored_stem>_chance otherwise; _rot<n>
    for any other number of rotations, so neither file can be overwritten by a short run."""
    return f"{scored_stem}_chance" + ("_rehearsal" if rehearsal else "") + suffix(n_rot)


def clean(x: Any) -> Any:
    """JSON-safe: NaN and inf to None, numpy scalars to Python."""
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    return x


def geojson_stands(path: Path) -> pd.DataFrame:
    """One row per polygon of a run's merged stand layer, as ui_stands: sid (stand_lbl), cluster
    (cluster_id rounded, as odisha_phase2_3_join.load_layer rounds it, or NaN), geometry in lon/lat."""
    rows = []
    for f in json.loads(path.read_text())["features"]:
        p = f["properties"]
        cid = p.get("cluster_id")
        rows.append({"sid": int(float(p["stand_lbl"])),
                     "cluster": np.nan if cid is None else float(np.rint(float(cid))),
                     "geom_ll": shape(f["geometry"])})
    return pd.DataFrame(rows)


def pre_fix_sha256() -> set[str]:
    """SHA-256 of the pre-fix runs' stand files: the merged layers in git, those an off-git record
    names, and the explorer's stands.json. A declared run may score none of them."""
    out = set()
    for d in K.DISTRICTS:
        run_name = K.run_id(d)
        for f in (K.STANDS_DIR / f"{run_name}_stands_merged.geojson", UI_DATA / run_name / "stands.json"):
            if f.exists():
                out.add(sha256(f))
        rec = K.STANDS_DIR / f"{run_name}_files_off_git.json"
        if rec.exists():
            out |= {e["sha256"] for e in json.loads(rec.read_text())["files"]
                    if e["file"].endswith("_stands_merged.geojson")}
    return out


def rel(p: Path) -> str:
    return str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p)


def run(n_rot: int, out_dir: Path, *, stands_from: str = "ui_data", stands_dir: Path | None = None,
        run_suffix: str = "", scored_stem: str = "keptland_s1desc", ui_data: Path = UI_DATA,
        scores_dir: Path = SCORES_DIR, cap_scale: float = 1.0, declared: bool = False,
        runs_pattern: str | None = None, arm: str | None = None) -> dict[str, Any]:
    """stands_from 'ui_data' reads ui_data/by_run/<run>/stands.json; 'geojson' reads
    <stands_dir>/<run>_stands_merged.geojson (or where its off-git record says, SHA-256 checked).
    <run> is odisha_v120_3ha_squares_<district>_keptland_s1desc<run_suffix>. The identity checks
    read <scored_stem>_joined.csv and <scored_stem>_scores.json in scores_dir. The run is a
    REHEARSAL unless declared=True, which needs geojson stands that are not the pre-fix files.
    runs_pattern names the runs by a pattern with {district} in place of the default name plus
    run_suffix; arm names the arm in the seed strings (default: arm_from_runs of the pattern)."""
    t_start = time.time()
    _lines.clear()
    _timings.clear()
    if stands_from not in ("ui_data", "geojson"):
        raise SystemExit(f"stands_from must be 'ui_data' or 'geojson', got {stands_from!r}")
    if runs_pattern is not None and run_suffix:
        raise SystemExit("give the runs by --runs or by --run-suffix, not both")
    pattern = runs_pattern if runs_pattern is not None else K.RUNS + run_suffix
    if "{district}" not in pattern:
        raise SystemExit(f"the runs' pattern must hold {{district}}: {pattern!r}")
    if stands_from == "ui_data" and pattern != K.RUNS:
        raise SystemExit("ui_data holds only the pre-fix runs; read re-run stands with stands_from='geojson'")
    arm = arm if arm is not None else arm_from_runs(pattern)
    seed_unc, seed_lab = G.SEED_UNCOND.format(arm=arm), G.SEED_LABELLED.format(arm=arm)
    if declared and stands_from != "geojson":
        raise SystemExit("the declared test reads the merged stand layers: use stands_from='geojson'")
    rehearsal = not declared
    parts = box_parts()
    plots = load_plots(parts)
    inputs: dict[str, str] = {}
    stands = {}
    runs = [pattern.format(district=d) for d in K.DISTRICTS]
    for d, run_name in zip(K.DISTRICTS, runs, strict=True):
        if stands_from == "ui_data":
            path = ui_data / run_name / "stands.json"
            stands[d] = ui_stands(path)
        else:
            path = K.stand_layer(run_name, stands_dir if stands_dir is not None else K.STANDS_DIR)
            stands[d] = geojson_stands(path)
        inputs[f"stands:{run_name}"] = sha256(path)
    if declared:
        pre = pre_fix_sha256()
        same_as_pre = [r for r in runs if inputs[f"stands:{r}"] in pre]
        if same_as_pre:
            raise SystemExit(f"declared=True, but these stand files are the pre-fix runs' files: {same_as_pre}")
    joined_csv = scores_dir / f"{scored_stem}_joined.csv"
    scores_json = scores_dir / f"{scored_stem}_scores.json"
    for p in (K.FIELD_TYPES, K.FIELD_TYPES_K4, joined_csv, scores_json,
              *[AOI_DIR / f"odisha_squares_{d}.geojson" for d in K.DISTRICTS]):
        inputs[rel(p)] = sha256(p)
    keys = sorted({(d, int(s)) for d in K.DISTRICTS for s in stands[d].sid})
    code = {kk: float(c) for c, kk in enumerate(keys)}
    full = {q: Layer(stands[p["district"]], p["district"], p["epsg"], code, typed_only=False)
            for q, p in enumerate(parts)}
    typed = {q: Layer(stands[p["district"]], p["district"], p["epsg"], code, typed_only=True)
             for q, p in enumerate(parts)}

    # identity check 1: the declared join at the real positions, as the null assigns, against the committed join
    xy = plots[["x", "y"]].to_numpy()
    key0, cl0, dist0 = (np.full(len(plots), np.nan) for _ in range(3))
    for q in range(len(parts)):
        m = plots.aoi_part.to_numpy() == q
        if m.any():
            key0[m], cl0[m], dist0[m] = assign(xy[m], full[q])
    ref = pd.read_csv(joined_csv).set_index("plot_key").loc[plots.plot_key]
    ref_key = np.array([code[(d, int(s))] if np.isfinite(s) else np.nan
                        for d, s in zip(ref.box_district, ref.sid, strict=True)])
    how0 = np.where(~np.isfinite(key0), "none", np.where(dist0 == 0, "covered", "within"))
    same = lambda a, b: bool(np.all((a == b) | (np.isnan(a) & np.isnan(b))))  # noqa: E731
    ok_id = same(key0, ref_key) and same(cl0, ref.cluster.to_numpy(float))
    ok_how = bool((how0 == ref.how.to_numpy()).all())
    if not (ok_id and ok_how and len(plots) == len(ref)):
        raise SystemExit("IDENTITY CHECK FAILED: the null's join at the real plot positions does not "
                         f"reproduce {joined_csv.name}. Stopping.")

    scored = np.isfinite(key0)
    ft_primary, ft_k4 = plots.field_type.to_numpy(int), plots.ft_k4.to_numpy(int)
    scorings = {"primary": Scoring(plots, ft_primary, scored),
                "S1": Scoring(plots, ft_primary, scored & (ft_primary != 0)),
                "S2": Scoring(plots, ft_k4, scored)}

    # identity check 2: the observed scores, against the committed field check
    committed = {a["analysis"]: a for a in json.loads(scores_json.read_text())
                 ["analyses"]}
    observed = {a: sc.all(key0, cl0) for a, sc in scorings.items()}
    for a, o in observed.items():
        bad = {k: (o[k], committed[a][k]) for k, _ in STATS
               if not np.isclose(o[k], committed[a][k], rtol=0, atol=1e-12, equal_nan=True)}
        if bad:
            raise SystemExit(f"observed {a} scores disagree with {scores_json.name}: {bad}")

    t1 = time.time()
    unc = draw_null(plots, parts, full, n_rot, S.seeded(seed_unc), "unconditional", cap_scale)
    t2 = time.time()
    con = draw_null(plots, parts, typed, n_rot, S.seeded(seed_lab), "conditional", cap_scale)
    t3 = time.time()
    note_time(f"  nulls: unconditional {t2 - t1:.0f} s, conditional {t3 - t2:.0f} s")
    built = not unc["failures"] and not con["failures"]

    result: dict[str, Any] = {
        "what": ("REHEARSAL of the chance test of PHASE_KEPTLAND_PREDECLARED.md on the _keptland_s1desc "
                 "stands from before the round 9 cache fix. Not the declared test's result: these runs are "
                 "re-run after the fix and re-scored then." if rehearsal else
                 "The chance test of PHASE_KEPTLAND_PREDECLARED.md on the runs named in 'runs'."),
        "rehearsal": rehearsal, "runs": runs, "stands_from": stands_from,
        "identity_files": [rel(joined_csv), rel(scores_json)],
        "inputs_sha256": inputs, "rotations": n_rot, "arm_seed_name": arm,
        "seeds": {"unconditional": seed_unc, "conditional": seed_lab},
        "identity_checks": {"join_at_real_positions": "PASS", "observed_scores_vs_committed": "PASS (|diff| < 1e-12)"},
        "null_built": built, "failures": {"unconditional": unc["failures"], "conditional": con["failures"]},
        "draws": {"unconditional": unc["draws"], "conditional": con["draws"]},
    }
    analyses = {}
    for a, sc in scorings.items():
        null = {k: np.full(n_rot, np.nan) for k in observed[a]}
        if built:
            for r in range(n_rot):
                for k, v in sc.delin(unc["key"][r]).items():
                    null[k][r] = v
                for k, v in sc.label(con["cluster"][r]).items():
                    if k in null:
                        null[k][r] = v
        rows = {k: summarise(observed[a][k], null[k]) for k, _ in STATS}
        # Holm over the estimable tests, m their number (the village test's rule)
        est = [k for k, _ in STATS if rows[k]["p"] is not None]
        for k, h in zip(est, holm([rows[k]["p"] for k in est]), strict=True):
            rows[k]["holm_p"] = h
            rows[k]["passes"] = bool(h <= ALPHA)
        n_dist_obs = sum(1 for k in observed[a] if k.startswith("lab_") and k != "lab_wmean")
        dist_keys = [k for k in null if k.startswith("lab_") and k != "lab_wmean"]
        n_dist_null = (np.isfinite(np.vstack([null[k] for k in dist_keys])).sum(0) if dist_keys and built
                       else np.array([], dtype=int))
        per_district = {k[4:]: summarise(observed[a][k], null[k]) for k in sorted(observed[a])
                        if k.startswith("lab_") and k != "lab_wmean"}
        # how many plots each realisation scores: the null leaves out plots that land off every stand
        n_delin = (sc.base & np.isfinite(unc["key"])).sum(1) if built else np.array([])
        n_lab = (sc.base & np.isfinite(con["cluster"])).sum(1) if built else np.array([])
        analyses[a] = {"what": dict(ANALYSES)[a], "plots_scored_observed": int(sc.base.sum()),
                       "plots_scored_per_realisation": {
                           "drawing": dict(zip(("median", "p5", "p95"), S.qs(n_delin), strict=True)),
                           "labelling": dict(zip(("median", "p5", "p95"), S.qs(n_lab), strict=True))},
                       "far_apart_pairs": int(len(sc.fi)), "scores": rows,
                       "labelling_by_district": per_district,
                       "districts_in_labelling_mean": {
                           "observed": n_dist_obs,
                           "realisations_by_count": {str(int(c)): int((n_dist_null == c).sum())
                                                     for c in np.unique(n_dist_null)}}}
    result["analyses"] = analyses
    # C1: the labelling mean without Kendujhar, observed and in the conditional null's realisations
    sc1 = Scoring(plots, ft_primary, scored & (plots.box_district.to_numpy() != C1_LEFT_OUT))
    obs_c1 = sc1.label(cl0)["lab_wmean"]
    null_c1 = np.full(n_rot, np.nan)
    if built:
        for r in range(n_rot):
            null_c1[r] = sc1.label(con["cluster"][r])["lab_wmean"]
    result["checks"] = {"C1": {
        "what": (f"score 4, the labelling mean, without {C1_LEFT_OUT} on both sides "
                 "(PHASE_KEPTLAND_AMENDMENT_chance_checks.md); beside the primary, outside Holm, no pass or fail"),
        "plots_scored_observed": int(sc1.base.sum()), **summarise(obs_c1, null_c1)}}
    if built:
        mv = {}
        for q, p in enumerate(parts):
            m = (plots.aoi_part.to_numpy() == q) & scored
            if m.any():
                v = unc["moved"][:, m].ravel()
                mv[p["name"]] = {"plots": int(m.sum()), "median_m": float(np.median(v)),
                                 "p90_m": float(np.percentile(v, 90))}
        allv = unc["moved"][:, scored].ravel()
        result["null_moves_plots"] = {"by_box": mv, "all_scored_plots_median_m": float(np.median(allv))}
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_stem(scored_stem, rehearsal, n_rot)
    (out_dir / f"{stem}.json").write_text(json.dumps(clean(result), indent=1) + "\n")
    report(result, plots, how0)
    (out_dir / f"{stem}.txt").write_text("\n".join(_lines) + "\n")
    note_time(f"  whole run {time.time() - t_start:.0f} s")
    with (out_dir / f"{stem}.log").open("a") as f:
        f.write("\n".join(_timings) + "\n")
    return result


def fmt(v: Any, nd: int = 4, sign: bool = True) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "n/a"
    return f"{v:+.{nd}f}" if sign else f"{v:.{nd}f}"


def report(res: dict[str, Any], plots: pd.DataFrame, how0: np.ndarray) -> None:
    w = 104
    say("=" * w)
    if res["rehearsal"]:
        say("REHEARSAL -- chance test of the Odisha kept-land field check (PHASE_KEPTLAND_PREDECLARED.md)")
        say("=" * w)
        say("  NOT THE DECLARED TEST'S RESULT. The stands are the four _keptland_s1desc runs from BEFORE the round 9")
        say("  cache fix; they are re-run after it and re-scored then. Pass/fail below says what the declared rule")
        say("  would say on these stands, nothing more.")
    else:
        say("Chance test of the Odisha kept-land field check (PHASE_KEPTLAND_PREDECLARED.md)")
        say("=" * w)
        say(f"  Runs: {', '.join(res['runs'])}.")
    say("  Where the declaration is silent the village-outline test's rule is used (Q1-Q8 in the script's")
    say("  docstring). docs/handoff/2026-10-17-round9-chat.md asks them under its own numbers: Q1 is its")
    say("  question 1, Q2 its 4, Q4 its 5, Q6 its 6, Q7 its 2 and Q8 its 7; Q3 and Q5 are not asked there.")
    say("")
    say("  HOW TO READ IT. Chance is positive in this design (plots and stands both cluster by village), so each")
    say("  score is read against a rotation null: each box's plot cloud moved rigidly to a random position and")
    say("  angle with every plot inside the box, each plot then joining by the declared rule (covered, else the")
    say("  nearest stand within 30 m); a plot with no stand within 30 m is left out of that realisation only.")
    say("  'pctile' is the mid-rank percentile of the observed score in the null; 'p' is (1 + #null >= obs) /")
    say("  (1 + n), one-sided; Holm over the five tests; a test passes at Holm p <= 0.05. Fewer than 100 usable")
    say("  realisations: NOT ESTIMABLE.")
    say("")
    hw = pd.Series(how0)
    say(f"  plots in the boxes {len(plots)}: on a stand {int((hw == 'covered').sum())}, by the 30 m rule "
        f"{int((hw == 'within').sum())}, left out {int((hw == 'none').sum())}")
    say(f"  rotations per null: {res['rotations']}; seeds '{res['seeds']['unconditional']}' (drawing) and "
        f"'{res['seeds']['conditional']}' (labelling)")
    jf, sf = (Path(x).name for x in res["identity_files"])
    say(f"  identity checks: the null's join at the real positions reproduces {jf} for every plot; the")
    say(f"  observed scores equal {sf} (|diff| < 1e-12)")
    if not res["null_built"]:
        say("")
        say("  NULL NOT BUILT: a box could not place its realisations within the draw cap. Every test is NOT")
        say(f"  ESTIMABLE. Failures: {res['failures']}")
    for a, an in res["analyses"].items():
        say("")
        say("-" * w)
        say(f"{a}: {an['what']}")
        say("-" * w)
        pr = an["plots_scored_per_realisation"]
        say(f"  plots scored: observed {an['plots_scored_observed']}; per realisation, median [p5, p95]: drawing "
            f"{fmt(pr['drawing']['median'], 0, False)} [{fmt(pr['drawing']['p5'], 0, False)}, "
            f"{fmt(pr['drawing']['p95'], 0, False)}], labelling {fmt(pr['labelling']['median'], 0, False)} "
            f"[{fmt(pr['labelling']['p5'], 0, False)}, {fmt(pr['labelling']['p95'], 0, False)}]")
        say(f"  far-apart same-district pairs (> 2 km) from the real positions: {an['far_apart_pairs']}")
        say(f"    {'score':<56}{'observed':>9} | {'null median [p5, p95]':>28}{'pctile':>8}{'p':>7}"
            f"{'Holm p':>8}{'n':>6}")
        for k, label in STATS:
            r = an["scores"][k]
            if r["p"] is None:
                say(f"    {label:<56}{fmt(r['observed']):>9} | NOT ESTIMABLE (usable realisations {r['n_null']})")
                continue
            band = f"{fmt(r['null_median'])} [{fmt(r['null_p5'])}, {fmt(r['null_p95'])}]"
            say(f"    {label:<56}{fmt(r['observed']):>9} | {band:>28}{r['pctile']:>8.1f}{r['p']:>7.3f}"
                f"{fmt(r.get('holm_p'), 3, False):>8}{r['n_null']:>6}"
                + ("  <- passes" if r.get("passes") else ""))
        dl = an["districts_in_labelling_mean"]
        counts = ", ".join(f"{c} districts in {n}" for c, n in sorted(dl["realisations_by_count"].items()))
        say(f"  districts in the labelling mean: observed {dl['observed']}; realisations: {counts or 'none'}")
        say("  labelling ARI by district (descriptive, not tests; against the conditional null, over the realisations")
        say("  in which the district has 2 scored plots of 2 field types, n given):")
        for d, r in an["labelling_by_district"].items():
            if r["p"] is None:
                say(f"    {d:<56}{fmt(r['observed']):>9} | NOT ESTIMABLE (usable realisations {r['n_null']})")
            else:
                band = f"{fmt(r['null_median'])} [{fmt(r['null_p5'])}, {fmt(r['null_p95'])}]"
                say(f"    {d:<56}{fmt(r['observed']):>9} | {band:>28}{r['pctile']:>8.1f}{r['p']:>7.3f}"
                    f"{'':>8}{r['n_null']:>6}")
    c1 = res["checks"]["C1"]
    say("")
    say("-" * w)
    say(f"Check C1 (PHASE_KEPTLAND_AMENDMENT_chance_checks.md): the labelling mean without {C1_LEFT_OUT}, on both sides")
    say("-" * w)
    say("  Beside the primary's labelling mean, not replacing it: outside the Holm correction, no pass or fail.")
    say(f"  plots scored: observed {c1['plots_scored_observed']}; the conditional null's realisations, as the primary's")
    if c1["p"] is None:
        say(f"    {'labelling ARI, plot-weighted mean, ' + C1_LEFT_OUT + ' left out':<56}{fmt(c1['observed']):>9} | "
            f"NOT ESTIMABLE (usable realisations {c1['n_null']})")
    else:
        band = f"{fmt(c1['null_median'])} [{fmt(c1['null_p5'])}, {fmt(c1['null_p95'])}]"
        say(f"    {'labelling ARI, plot-weighted mean, ' + C1_LEFT_OUT + ' left out':<56}{fmt(c1['observed']):>9} | "
            f"{band:>28}{c1['pctile']:>8.1f}{c1['p']:>7.3f}{'':>8}{c1['n_null']:>6}")
    if res["null_built"]:
        say("")
        say("-" * w)
        say("How far the null moves the plots (the box declaration's check; unconditional null, the plots the join scores)")
        say("-" * w)
        say(f"    {'box':<40}{'plots':>6}{'median m':>10}{'p90 m':>9}{'draws/realisation':>19}{'sampler':>17}")
        for name, v in res["null_moves_plots"]["by_box"].items():
            dr = res["draws"]["unconditional"][name]
            say(f"    {name:<40}{v['plots']:>6}{v['median_m']:>10.0f}{v['p90_m']:>9.0f}"
                f"{dr['draws_per_realisation']:>19.2f}{dr['sampler']:>17}")
        say(f"    median over the plots the join scores: {res['null_moves_plots']['all_scored_plots_median_m']:.0f} m")
    say("")
    say("-" * w)
    say("WHAT THIS SAYS")
    say("-" * w)
    p = res["analyses"]["primary"]["scores"]
    est = [k for k, _ in STATS if "holm_p" in p[k]]
    if res["null_built"] and est:
        n_pass = sum(p[k]["passes"] for k in est)
        say(f"  * Primary: {n_pass} of {len(est)} estimable tests pass after Holm at 0.05"
            + (" on these (pre-fix) stands." if res["rehearsal"] else ".")
            + ("" if len(est) == 5 else f" {5 - len(est)} not estimable."))
        inside = [k for k in est if 5 <= p[k]["pctile"] <= 95]
        say(f"  * {len(inside)} of {len(est)} estimable primary scores sit inside the null's central 90%.")
    else:
        say("  * The primary tests are not estimable (see above).")
    pa = res["analyses"]["primary"]
    say(f"  * The null scores fewer plots than the observed join (median {fmt(pa['plots_scored_per_realisation']['drawing']['median'], 0, False)}"
        f" of {pa['plots_scored_observed']}): plots that land off every")
    say("    stand are left out of that realisation, as declared, so the null's scores rest on fewer plots.")
    dl = pa["districts_in_labelling_mean"]
    fewer = sum(n for c, n in dl["realisations_by_count"].items() if int(c) < dl["observed"])
    if fewer:
        short = [d for d, r in pa["labelling_by_district"].items() if r["n_null"] < res["rotations"]]
        say(f"  * In {fewer} of {res['rotations']} realisations the labelling mean averages fewer districts than the observed")
        say(f"    {dl['observed']}, because a district then lacks 2 scored plots of 2 field types ({', '.join(short)}).")
    say("  * NOT supported by this file: "
        + ("any claim about the declared test (it runs on the re-run stands); " if res["rehearsal"] else "")
        + "'better than chance' from a score")
    say("    above zero; a single p read without the Holm column.")


def git_block(now: bool = False) -> dict[str, Any]:
    """This checkout's git state as a run record holds it: as the process found it first, or read
    again now (`now`). main() asks first, before the run writes anything (review C32)."""
    sys.path.insert(0, str(REPO / "src"))
    from fmu.utils.provenance import git_state, git_state_now

    state = git_state_now(HERE) if now else git_state(HERE)
    return {k: v for k, v in state.items() if k != "root"}


def write_run_record(out_dir: Path, stem: str, argv: list[str], git: dict[str, Any] | None = None) -> None:
    """The run record beside the results. `git` is the state the run started from (main() reads it
    first); `git_at_end` is read now, after the results were written."""
    import datetime
    import shlex

    sys.path.insert(0, str(REPO / "src"))
    from fmu.utils.provenance import environment_state

    rec = {"result_files": [f"{stem}.txt", f"{stem}.json"],
           "command_line": "python " + " ".join(shlex.quote(a) for a in
                                                ["odisha_script/odisha_keptland_chance.py", *argv]),
           "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
           "git": git if git is not None else git_block(),
           "git_at_end": git_block(now=True),
           # The Python environment, as the pipeline's manifests record it (review C37): the null
           # draws from a seeded numpy Generator and places plots with shapely.
           "environment": environment_state()}
    (out_dir / f"{stem}_run.json").write_text(json.dumps(rec, indent=1) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rotations", type=int, default=N_ROT, help=f"realisations per null (default {N_ROT})")
    ap.add_argument("--out-dir", type=Path, default=SCORES_DIR)
    ap.add_argument("--stands-from", choices=("ui_data", "geojson"), default="ui_data",
                    help="ui_data (the explorer's stands.json, pre-fix runs only) or geojson (merged stand layers)")
    ap.add_argument("--stands-dir", type=Path, default=None,
                    help=f"with --stands-from geojson: where <run>_stands_merged.geojson is (default {rel(K.STANDS_DIR)})")
    ap.add_argument("--run-suffix", default="", help="suffix of the runs scored, e.g. _r9; empty: the pre-fix runs")
    ap.add_argument("--runs", default=None,
                    help="the runs scored, a pattern with {district}, in place of the default name plus --run-suffix "
                         "(e.g. odisha_alphaearth_3ha_squares_{district}_keptland_r9)")
    ap.add_argument("--arm", default=None,
                    help="the arm's name in the seed strings (default: the runs' name without odisha_, the district "
                         "and the run suffixes: a round's, such as _r9, _r13 or _r9_check, and _repro, numbered or not)")
    ap.add_argument("--scored-stem", default="keptland_s1desc",
                    help="stem of the field check's <stem>_joined.csv and <stem>_scores.json in --scores-dir")
    ap.add_argument("--scores-dir", type=Path, default=SCORES_DIR)
    ap.add_argument("--declared", action="store_true",
                    help="the declared test, not a rehearsal: needs --stands-from geojson, and stops if any "
                         "stand file is a pre-fix run's file (by SHA-256)")
    args = ap.parse_args(argv)
    started = git_block()  # before the run writes anything (review C32)
    res = run(args.rotations, args.out_dir, stands_from=args.stands_from, stands_dir=args.stands_dir,
              run_suffix=args.run_suffix, scored_stem=args.scored_stem, scores_dir=args.scores_dir,
              declared=args.declared, runs_pattern=args.runs, arm=args.arm)
    write_run_record(args.out_dir, out_stem(args.scored_stem, res["rehearsal"], args.rotations),
                     list(sys.argv[1:] if argv is None else argv), git=started)
    return 0


if __name__ == "__main__":
    sys.exit(main())
