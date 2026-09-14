"""
Phase 2, step 5 — the statistics (brief Steps 6 and 7).

FULLY OFFLINE. Reads phase2_plots_joined[_districts].csv and phase2_vectors/.
Run only after PHASE2_PREDICTIONS.md is committed; that ordering is the point of it.

SETS (--set)
------------
  pilot      the six Dhenkanal village forests (60 plots). Configs and AOI as in the join.
  districts  the full set, pooled over angul, dhenkanal, kendujhar, koraput. AOI part ids are
             prefixed with the district, and stand ids are made unique by (district, id), so a
             stand id reused by another district's run is never read as the same stand.
             k-means was fitted per district, so 6.3 label agreement is computed within each
             district and reported per district plus a plot-weighted mean; distant pairs are
             pairs in the same district.
Arms whose vector files are missing are skipped with a printed note; AlphaEarth is included
automatically once its files exist.

GEOMETRY
--------
d_geo is geodesic (pyproj Geod, WGS84) everywhere: the district set spans two UTM zones, and a
planar distance across a zone edge is wrong. Rotations and boundary distances are done in the
local UTM zone of each AOI part (fmu.utils.grid.utm_epsg_code via
odisha_phase2_0_aois.utm_transformers), because a rigid rotation must be rigid in metres.

WHAT IS COMPUTED, AND FOR WHICH PARTITIONS
------------------------------------------
Primary result first: stands_merged from odisha_v120_handcrafted. The other arms and layers are
secondary and reported after it. Everything named in PHASE2_PREDICTIONS.md is computed as defined
there. Anything else is printed under a heading "SENSITIVITY (not pre-registered)" and is
reported whichever way it points.

6.1  R²_P(Y) = 1 - SS_within / SS_total, stand as the grouping factor, over
     loreys_h_m, loreys_h_tree_m, crown_cover_pct, sal_ba_frac, n_species, dbh_mean_cm, h_top5_m.
     Two forms, always labelled: ALL plots (singleton stands contribute zero within-stand
     variance, so this is inflated), and RESTRICTED to stands holding >= 2 plots with a value
     for Y (the honest one). n_stands and n_plots beside every value.

6.2  Pairwise boundary test over plot pairs inside the same AOI part.
     d_field = Bray-Curtis on RELATIVE species basal area (composition) and |delta Lorey's|
     (structure, all-habit), reported separately.
       stratified: bands 0-100, 100-200, 200-400, 400-800 m; mean d_field for same-stand vs
                   different-stand pairs, n per cell, and diff = mean(different) - mean(same)
                   (positive = stands group alike plots). A cell with <= 3 same or <= 3
                   different pairs is printed but marked uninformative and gets no percentile.
       regression: d_field ~ d_geo + same_stand over pairs < 800 m; beta_same (negative =
                   stand effect). OLS standard errors are NOT reported: pairs share plots.
     Both for all pairs and for pairs where both plots are > 30 m from a stand boundary.
     The as-run within-band label permutation p is kept, relabelled INVALID: it pools pairs
     from different sites into one exchangeable set and treats pairs sharing a plot as
     independent. A within-site shuffle is reported under SENSITIVITY.

6.3  Label agreement (typology, not delineation). Field forest type = UPGMA on Bray-Curtis of
     relative species basal area over all 274 plots, cut at 6 groups; secondary: Sal-dominant
     if sal_ba_frac > 0.5. Against the merged stand's cluster_id: ARI, NMI, Cramér's V, and the
     contingency table. ARI/NMI/V are NOT ESTIMABLE when the typed plots hold < 2 field types
     (a constant column scores ARI 0 by definition, which is not a result). Distant-pair form:
     pairs > 2 km apart, same-label vs different-label mean d_field; it depends only on the
     stand label, so it is printed once per partition.

NULL (Step 7), as fixed in PHASE2_PREDICTIONS.md
------------------------------------------------
  rotation  rigid rotation + translation of the plot configuration of each AOI part against the
            real vector stand map, --rotations realisations (default 1999). A realisation that
            puts an originally assigned plot outside every stand polygon is redrawn. For 6.3, a
            realisation that puts a typed plot on a polygon with no cluster_id is not used (its
            label statistics would be over a different plot set); the count used is printed.
  The noise-SNIC null is excluded by recorded decision: it failed its size check before any
  statistic existed (odisha_phase2_4_results.txt).

Percentile = mid-rank share of null values below the observed value, printed with n_null, the
number of realisations in which the statistic is defined. Below 100 defined realisations the
percentile is NOT ESTIMABLE. Excess = observed - null median. Raw R² is never compared across
partitions; excess over each partition's own null is.

Random numbers: one np.random.Generator per partition for the rotation null and a separate one
for permutations, each seeded from zlib.crc32 of "<arm>/<layer>", so a partition's null does not
depend on how many partitions ran before it.

Run:  python odisha_phase2_5_stats.py [--set pilot|districts] [--rotations 1999] [--vectors-dir D] [--aoi-dir D] [--out-dir D]
Writes: odisha_phase2_5_results[_districts].txt, odisha_phase2_5_summary[_districts].csv,
        odisha_phase2_5_{primary_r2_null,arms_excess,pairwise_bands}[_districts].png
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import zlib
from io import StringIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import shapely  # noqa: E402
from pyproj import Geod, Transformer  # noqa: E402
from scipy.cluster.hierarchy import fcluster, linkage  # noqa: E402
from scipy.spatial.distance import squareform  # noqa: E402
from scipy.stats import chi2_contingency, spearmanr  # noqa: E402
from shapely import STRtree  # noqa: E402
from shapely.geometry import shape  # noqa: E402
from shapely.ops import transform  # noqa: E402
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from odisha_phase2_0_aois import utm_transformers  # noqa: E402
from odisha_phase2_3_join import (ARMS, LAYERS, add_path_args, apply_path_args, arm_districts,  # noqa: E402
                                  load_layer, vector_path)

YVARS = ["loreys_h_m", "loreys_h_tree_m", "crown_cover_pct", "sal_ba_frac",
         "n_species", "dbh_mean_cm", "h_top5_m"]
BANDS = [(0, 100), (100, 200), (200, 400), (400, 800)]
BOUNDARY_M = 30.0
DISTANT_M = 2000.0
N_TYPES = 6
N_PERM = 9999
MIN_NULL = 100          # fewer defined null values than this: no percentile
MIN_CELL = 3            # n_same or n_diff <= this: 6.2 cell is uninformative
BDIST_SEARCH_M = 1000.0  # as the join
FIRST_RUN = "8d4c2ed"
GEOD = Geod(ellps="WGS84")

# reference palette (dataviz skill): ink, muted, series slots
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
NULL_FILL = "#c3c2b7"

_lines: list[str] = []
_rows: list[dict] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    _lines.append(s)


def rule(title: str) -> None:
    say("")
    say("=" * 100)
    say(title)
    say("=" * 100)


def sens(title: str) -> None:
    say(f"  SENSITIVITY (not pre-registered): {title}")


def record(**kw) -> None:
    _rows.append(kw)


def seeded(key: str) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32(key.encode()))


# ---------------------------------------------------------------------- core statistics
def r2_partition(y: np.ndarray, g: np.ndarray, restrict: bool) -> tuple[float, int, int]:
    """R² with g as grouping. Sums run over plots in index order, so two realisations that put the
    same plots together give bit-identical values whatever the stand ids are (ties stay ties)."""
    g = np.asarray(g, float)
    m = ~np.isnan(y) & ~np.isnan(g)
    y, g = y[m], g[m]
    if not len(y):
        return np.nan, 0, 0
    _, inv, cnt = np.unique(g, return_inverse=True, return_counts=True)
    if restrict:
        keep = cnt[inv] >= 2
        y, inv = y[keep], inv[keep]
        if not len(y):
            return np.nan, 0, 0
        _, inv = np.unique(inv, return_inverse=True)
    n = len(y)
    k = int(inv.max()) + 1
    if n < 2:
        return np.nan, k, n
    sst = ((y - y.mean()) ** 2).sum()
    if sst == 0:
        return np.nan, k, n
    means = np.bincount(inv, y) / np.bincount(inv)
    ssw = ((y - means[inv]) ** 2).sum()
    return 1.0 - ssw / sst, k, n


def r2_detail(y: np.ndarray, g: np.ndarray, part: np.ndarray) -> dict:
    """Restricted R² with its structure, adjusted R², and the within-part (site-demeaned) form:
    SS_total taken about AOI-part means, so between-site differences cannot count as stand signal."""
    g = np.asarray(g, float)
    m = ~np.isnan(y) & ~np.isnan(g)
    y, g, part = y[m], g[m], part[m]
    out = dict(r2=np.nan, k=0, n=0, E=np.nan, largest=0, adj=np.nan, r2_wp=np.nan)
    if not len(y):
        return out
    _, inv, cnt = np.unique(g, return_inverse=True, return_counts=True)
    keep = cnt[inv] >= 2
    y, inv, part = y[keep], inv[keep], part[keep]
    if len(y) < 2:
        return out
    _, inv, cnt = np.unique(inv, return_inverse=True, return_counts=True)
    n, k = len(y), len(cnt)
    out.update(k=k, n=n, E=(k - 1) / (n - 1), largest=int(cnt.max()))
    sst = ((y - y.mean()) ** 2).sum()
    if sst == 0:
        return out
    ssw = ((y - (np.bincount(inv, y) / cnt)[inv]) ** 2).sum()
    r2 = 1.0 - ssw / sst
    out["r2"] = r2
    out["adj"] = 1 - (1 - r2) * (n - 1) / (n - k) if n > k else np.nan
    _, pinv, pcnt = np.unique(part, return_inverse=True, return_counts=True)
    sst_wp = ((y - (np.bincount(pinv, y) / pcnt)[pinv]) ** 2).sum()
    out["r2_wp"] = 1.0 - ssw / sst_wp if sst_wp > 0 else np.nan
    return out


def pair_stats(same: np.ndarray, d_geo: np.ndarray, d_field: np.ndarray, ok: np.ndarray,
               part: np.ndarray | None = None, weights_key: np.ndarray | None = None) -> dict:
    """Stratified diffs and beta_same over the pairs selected by `ok`.
    part: add AOI-part dummies to the regression (site fixed effects).
    weights_key: stand key per pair; each same-stand pair is weighted 1/(same pairs of its stand)."""
    out = {}
    for lo, hi in BANDS:
        sel = ok & (d_geo >= lo) & (d_geo < hi) & ~np.isnan(d_field)
        s, f = same[sel], d_field[sel]
        ns, nd = int(s.sum()), int((~s).sum())
        out[f"n_same_{lo}_{hi}"], out[f"n_diff_{lo}_{hi}"] = ns, nd
        out[f"mean_same_{lo}_{hi}"] = f[s].mean() if ns else np.nan
        out[f"mean_diff_{lo}_{hi}"] = f[~s].mean() if nd else np.nan
        out[f"diff_{lo}_{hi}"] = f[~s].mean() - f[s].mean() if ns and nd else np.nan
    sel = ok & (d_geo < BANDS[-1][1]) & ~np.isnan(d_field)
    n = int(sel.sum())
    if n > 3 and same[sel].any() and (~same[sel]).any():
        cols = [np.ones(n), d_geo[sel] / 100.0, same[sel].astype(float)]
        if part is not None:
            for u in np.unique(part[sel])[1:]:
                cols.append((part[sel] == u).astype(float))
        X = np.column_stack(cols)
        y = d_field[sel]
        if weights_key is not None:
            s = same[sel]
            w = np.ones(n)
            _, inv, cnt = np.unique(weights_key[sel][s], return_inverse=True, return_counts=True)
            w[s] = 1.0 / cnt[inv]
            sw = np.sqrt(w)
            X, y = X * sw[:, None], y * sw
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        out["beta_dgeo_per100m"], out["beta_same"] = beta[1], beta[2]
    else:
        out["beta_dgeo_per100m"], out["beta_same"] = np.nan, np.nan
    out["n_pairs_reg"], out["n_same_reg"] = n, int(same[sel].sum())
    return out


def shuffle_p(same, d_geo, d_field, ok, group, rng, nperm=N_PERM) -> dict:
    """Label-shuffle p-values for each band diff (upper tail) and beta_same (lower tail).
    Labels are shuffled among pairs sharing `group` and band; group = constant gives the as-run
    pooled permutation, group = AOI part gives the within-site shuffle."""
    sel = ok & (d_geo < BANDS[-1][1]) & ~np.isnan(d_field)
    idx = np.where(sel)[0]
    s, f, g = same[idx], d_field[idx], d_geo[idx]
    band = np.digitize(g, [b[1] for b in BANDS[:-1]])
    gg = group[idx] * len(BANDS) + band
    obs = pair_stats(same, d_geo, d_field, ok)
    # a shuffle can only move labels inside a group holding both same and different pairs; with no such group
    # every shuffle reproduces the observed labels and p = 1 by construction, which tests nothing
    both = np.array([u for u in np.unique(gg) if s[gg == u].any() and (~s[gg == u]).any()], int)
    band_live = {b: bool((both % len(BANDS) == b).any()) for b in range(len(BANDS))}
    beta_live = len(both) > 0
    X2 = np.column_stack([np.ones(len(idx)), g / 100.0])
    if len(idx) > 3:
        XtXi = np.linalg.pinv(X2.T @ X2)
        r_y = f - X2 @ (XtXi @ (X2.T @ f))
    ge = {f"{lo}_{hi}": 0 for lo, hi in BANDS}
    le_beta, done = 0, 0
    chunk = max(1, min(nperm, 2_000_000 // max(1, len(idx))))
    while done < nperm:
        m = min(chunk, nperm - done)
        S = np.empty((m, len(idx)), bool)
        for u in np.unique(gg):
            loc = np.where(gg == u)[0]
            order = rng.random((m, len(loc))).argsort(axis=1)
            S[:, loc] = s[loc][order]
        for b, (lo, hi) in enumerate(BANDS):
            key = f"diff_{lo}_{hi}"
            inb = band == b
            ns, nd = int(s[inb].sum()), int((~s[inb]).sum())
            if not (ns and nd) or not np.isfinite(obs[key]):
                continue
            ssum = (S[:, inb] * f[inb]).sum(1)
            dp = (f[inb].sum() - ssum) / nd - ssum / ns
            ge[f"{lo}_{hi}"] += int((dp >= obs[key] - 1e-12).sum())
        if len(idx) > 3 and np.isfinite(obs["beta_same"]):
            Sf = S.astype(float)
            SX = Sf @ X2
            ss = Sf.sum(1) - np.einsum("ij,jk,ik->i", SX, XtXi, SX)
            with np.errstate(divide="ignore", invalid="ignore"):
                bp = (Sf @ r_y) / ss
            le_beta += int((bp <= obs["beta_same"] + 1e-12).sum())
        done += m
    out = {"degenerate": set()}
    for b, (lo, hi) in enumerate(BANDS):
        key = f"diff_{lo}_{hi}"
        out[key] = (1 + ge[f"{lo}_{hi}"]) / (nperm + 1) if np.isfinite(obs[key]) else np.nan
        if np.isfinite(obs[key]) and not band_live[b]:
            out[key] = np.nan
            out["degenerate"].add(key)
    out["beta_same"] = (1 + le_beta) / (nperm + 1) if np.isfinite(obs["beta_same"]) else np.nan
    if np.isfinite(obs["beta_same"]) and not beta_live:
        out["beta_same"] = np.nan
        out["degenerate"].add("beta_same")
    return out


DEGENERATE = "degenerate (no group holds both same and different pairs)"


def p_text(p: dict, key: str) -> str:
    return DEGENERATE if key in p["degenerate"] else fmt(p[key])


def contingency(a, b) -> tuple[float, pd.DataFrame, int, int]:
    """Cramér's V, the table, and the number of cells with expected count < 5 (of all cells)."""
    tab = pd.crosstab(pd.Series(a, name="field_type"), pd.Series(b, name="cluster_id"))
    if min(tab.shape) < 2:
        return np.nan, tab, 0, tab.size
    chi2, _, _, exp = chi2_contingency(tab.values, correction=False)
    v = float(np.sqrt(chi2 / (tab.values.sum() * (min(tab.shape) - 1))))
    return v, tab, int((exp < 5).sum()), tab.size


def agreement(ft, cl) -> dict:
    if len(np.unique(ft)) < 2 or len(ft) < 2:
        return {"ari": np.nan, "nmi": np.nan, "cramers_v": np.nan}
    return {"ari": adjusted_rand_score(ft, cl), "nmi": normalized_mutual_info_score(ft, cl),
            "cramers_v": contingency(ft, cl)[0]}


def distant_stats(cl, i, j, far, d_bc, d_lo) -> dict:
    ok = far & ~np.isnan(cl[i]) & ~np.isnan(cl[j])
    same_lab = cl[i] == cl[j]
    out = {}
    for name, d in (("bc", d_bc), ("lorey", d_lo)):
        s = ok & same_lab & ~np.isnan(d)
        dd = ok & ~same_lab & ~np.isnan(d)
        out[f"n_same_{name}"], out[f"n_diff_{name}"] = int(s.sum()), int(dd.sum())
        out[f"distant_diff_{name}"] = d[dd].mean() - d[s].mean() if s.any() and dd.any() else np.nan
    return out


def percentile(obs: float, null: np.ndarray) -> tuple[float, int]:
    null = np.asarray(null, float)
    null = null[~np.isnan(null)]
    if np.isnan(obs) or len(null) < MIN_NULL:
        return np.nan, len(null)
    return 100.0 * ((null < obs).sum() + 0.5 * (null == obs).sum()) / len(null), len(null)


def pct_text(obs: float, null: np.ndarray) -> str:
    pc, nn = percentile(obs, null)
    if np.isnan(obs):
        return f"n/a (n_null {nn})"
    if nn < MIN_NULL:
        return f"NOT ESTIMABLE (n_null {nn} < {MIN_NULL})"
    return f"{pc:.1f} (n_null {nn})"


def fmt(v, nd=3) -> str:
    return "  n/a" if v is None or (isinstance(v, (float, np.floating)) and np.isnan(v)) else f"{v:.{nd}f}"


def qs(x) -> tuple[float, float, float]:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return (np.median(x), *np.percentile(x, [5, 95])) if len(x) else (np.nan, np.nan, np.nan)


# ---------------------------------------------------------------------- data
def load(spec: dict) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    df = pd.read_csv(spec["joined"])
    parts = []
    for district, path in spec["districts"]:
        feat = json.loads(path.read_text())["features"][0]
        for k, g in enumerate(shape(feat["geometry"]).geoms):
            c = g.centroid
            epsg, fwd, _ = utm_transformers(c.x, c.y)
            parts.append({"district": district, "k": k, "geom_ll": g, "epsg": epsg, "fwd": fwd,
                          "geom": transform(fwd, g), "props": feat["properties"]["parts"][k]})
    pts = shapely.points(df.lon6.to_numpy(float), df.lat6.to_numpy(float))
    part_idx = np.full(len(df), -1)
    for q, p in enumerate(parts):
        part_idx[shapely.covers(p["geom_ll"], pts) & (part_idx < 0)] = q
    df["aoi_part"] = part_idx
    plots = df[df.aoi_part >= 0].sort_values("plot_key").reset_index(drop=True)
    plots["district_set"] = [parts[q]["district"] for q in plots.aoi_part]
    x = np.empty(len(plots))
    y = np.empty(len(plots))
    for q, p in enumerate(parts):
        m = plots.aoi_part.to_numpy() == q
        if m.any():
            x[m], y[m] = p["fwd"](plots.lon6.to_numpy(float)[m], plots.lat6.to_numpy(float)[m])
        shapely.prepare(p["geom"])
    plots["x"], plots["y"] = x, y
    # a part is named by the field site polygon of the plots inside it (the unit a reader knows);
    # where the field table has none (outside Dhenkanal), by its habitation
    multi = len(spec["districts"]) > 1
    for q, p in enumerate(parts):
        inside = plots[plots.aoi_part == q]
        sp = inside.site_polygon.dropna()
        if len(sp):
            nm = sp.mode().iat[0]
        elif len(inside):
            nm = inside.habitation.dropna().mode().iat[0]
        else:
            nm = "/".join(p["props"].get("sites") or p["props"].get("habitations") or [f"part{p['k']}"])
        p["name"] = f"{p['district']}:{nm}" if multi else nm
    return df, plots, parts


def relative_ba(frame: pd.DataFrame) -> pd.DataFrame:
    rows = [json.loads(s) for s in frame.sp_ba_json]
    m = pd.DataFrame(rows, index=frame.plot_key).fillna(0.0)
    return m.div(m.sum(axis=1), axis=0)


def bray_curtis(a: np.ndarray) -> np.ndarray:
    num = np.abs(a[:, None, :] - a[None, :, :]).sum(-1)
    den = (a[:, None, :] + a[None, :, :]).sum(-1)
    return num / den


class Partition:
    """One arm x layer over every district of the set: stand keys unique across districts, and the
    layer re-projected into each AOI part's own UTM zone for the rotation null."""

    def __init__(self, spec, arm, short, plots, parts):
        layer_name, id_field = LAYERS[short]
        self.arm, self.short, self.layer_name = arm, short, layer_name
        self.label = f"{arm} / {layer_name}"
        # one presence rule with the join (every layer file present), and in addition the joined table must
        # hold an assigned plot for this layer there: a layer loaded for a district the join left unassigned
        # (files partial at join time, or vectors arriving after it) would give the null plots the
        # observed statistic never saw
        dset = plots.district_set.to_numpy()
        raw_ids0 = plots[f"{arm}_{short}_id"].to_numpy(float)
        with_files = {d for d, _ in arm_districts(spec, ARMS[arm])}
        self.districts = [d for d, _ in spec["districts"]
                          if d in with_files and np.isfinite(raw_ids0[dset == d]).any()]
        self.missing = [d for d, _ in spec["districts"] if d not in self.districts]
        self.missing_why = {d: ("not every layer file present" if d not in with_files else
                                "layer files present but no plot assigned in the joined table (rerun the join)")
                            for d in self.missing}
        self.paths = {d: vector_path(spec["config"](ARMS[arm], d), layer_name) for d in self.districts}
        self.id_field = id_field
        ll = {d: load_layer(self.paths[d], id_field, lambda a, b: (a, b)) for d in self.districts}
        keys = sorted({(d, int(s)) for d in self.districts for s in ll[d].sid})
        self.code = {kk: float(c) for c, kk in enumerate(keys)}
        self.raw = {c: kk for kk, c in self.code.items()}
        self.polys = pd.concat([ll[d].assign(district=d) for d in self.districts], ignore_index=True)
        self.polys["key"] = [self.code[(d, int(s))] for d, s in zip(self.polys.district, self.polys.sid)]
        self.polys["cluster_id"] = np.rint(self.polys.cluster_id.astype(float))
        loaded = np.isin(dset, self.districts)
        self.n_dropped_ids = int((np.isfinite(raw_ids0) & ~loaded).sum())
        self.n_in_loaded = int(loaded.sum())
        self.ids = np.array([self.code.get((d, int(v)), np.nan) if np.isfinite(v) and ok else np.nan
                             for d, v, ok in zip(plots.district_set, raw_ids0, loaded)])
        self.bdist = np.where(loaded, plots[f"{arm}_{short}_bdist_m"].to_numpy(float), np.nan)
        self.cluster = np.where(loaded, np.rint(plots[f"{arm}_{short}_cluster"].to_numpy(float)), np.nan)
        self._cache = {}
        self.parts = parts

    def part_layer(self, q):
        p = self.parts[q]
        ck = (p["district"], p["epsg"])
        if ck not in self._cache:
            if p["district"] not in self.paths:
                self._cache[ck] = None
            else:
                fwd = Transformer.from_crs(4326, p["epsg"], always_xy=True).transform
                lay = load_layer(self.paths[p["district"]], self.id_field, fwd)
                geoms = np.array(list(lay.geom))
                key = np.array([self.code[(p["district"], int(s))] for s in lay.sid])
                cid = np.rint(lay.cluster_id.astype(float).to_numpy())
                self._cache[ck] = (geoms, STRtree(geoms), key, cid)
        return self._cache[ck]


# ---------------------------------------------------------------------- rotation null
PLAIN_MIN_ACCEPT = 0.02   # below this geometric acceptance a part uses the feasible-region sampler
ANGLE_GRID = 720


def geometric_acceptance(poly, rel: np.ndarray, rng: np.random.Generator, n: int = 4000) -> float:
    """Share of plain (angle, translation) draws that keep every plot inside the part."""
    minx, miny, maxx, maxy = poly.bounds
    th = rng.uniform(0, 2 * np.pi, n)
    cx, cy = rng.uniform(minx, maxx, n), rng.uniform(miny, maxy, n)
    c, s = np.cos(th)[:, None], np.sin(th)[:, None]
    X = rel[:, 0] * c - rel[:, 1] * s + cx[:, None]
    Y = rel[:, 0] * s + rel[:, 1] * c + cy[:, None]
    return float(shapely.contains_xy(poly, X.ravel(), Y.ravel()).reshape(n, -1).all(1).mean())


class FeasibleRegionSampler:
    """Draws (angle, translation) from EXACTLY the plain scheme's accepted distribution (uniform angle,
    translation uniform over the part's bounding box, conditioned on every plot inside the part), but
    without blind rejection. Needed for the district parts (convex hull + 300 m of a plot cloud): an
    elongated cloud fits only near its own angle and position, and plain rejection there accepts one
    draw in thousands.

    For an angle th, the translations keeping the cloud's hull vertices inside the part form
    F(th) = bbox ∩ ⋂_v (part − R(th)·v). Accept th with probability area(F)/M, M ≥ max area over
    angles, then draw the translation uniformly in F. The joint proposal density is then constant
    (1/M) over {(th, c): c ∈ F(th)}, a superset of the acceptable set (hull vertices are a subset of
    the plots), so the caller's full check of every plot and of stand coverage leaves the same
    uniform distribution plain rejection gives."""

    def __init__(self, poly, rel: np.ndarray):
        hull = shapely.convex_hull(shapely.multipoints(rel))
        self.V = (np.asarray(hull.exterior.coords)[:-1] if hull.geom_type == "Polygon"
                  else shapely.get_coordinates(hull))
        self.poly = poly
        self.box = shapely.box(*poly.bounds)
        areas = [self.region(t).area for t in np.linspace(0, 2 * np.pi, ANGLE_GRID, endpoint=False)]
        # 1.25x the grid maximum: area(F) is smooth in th and the grid step is 0.5 degrees
        self.M = 1.25 * max(areas)
        if self.M <= 0:
            raise RuntimeError("rotation null: the plot cloud fits inside its part at no angle")

    def region(self, th: float):
        c, s = np.cos(th), np.sin(th)
        R = self.V @ np.array([[c, -s], [s, c]]).T
        shifted = [shapely.affinity.translate(self.poly, -rx, -ry) for rx, ry in R]
        return shapely.intersection_all(shifted + [self.box])

    def draw(self, rng: np.random.Generator) -> tuple[float, np.ndarray, int]:
        proposals = 0
        while True:
            proposals += 1
            th = rng.uniform(0, 2 * np.pi)
            F = self.region(th)
            a = F.area
            if a > self.M:
                raise RuntimeError("rotation null: feasible-region bound exceeded; refine ANGLE_GRID")
            if rng.uniform() * self.M >= a:
                continue
            minx, miny, maxx, maxy = F.bounds
            while True:
                x, y = rng.uniform(minx, maxx, 64), rng.uniform(miny, maxy, 64)
                ok = shapely.contains_xy(F, x, y)
                if ok.any():
                    i = int(np.argmax(ok))
                    return th, np.array([x[i], y[i]]), proposals


def rotation_null(plots: pd.DataFrame, parts: list, part_obj: Partition, observed_ok: np.ndarray,
                  n: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """(ids, clusters, bdist) arrays of shape (n, n_plots) under rigid moves of the plots.
    Assignment and boundary distance follow the join exactly: several covering stands -> minimum
    stand id; distance to the nearest different stand within 1000 m, inf if none."""
    P = len(plots)
    ids, cls, bd = (np.full((n, P), np.nan) for _ in range(3))
    xy = plots[["x", "y"]].to_numpy()
    attempts = {}
    for q, part in enumerate(parts):
        idx = np.where(plots.aoi_part.to_numpy() == q)[0]
        lay = part_obj.part_layer(q)
        if not len(idx) or lay is None:
            continue
        geoms, tree, key, cid = lay
        poly = part["geom"]
        c0 = xy[idx].mean(0)
        minx, miny, maxx, maxy = poly.bounds
        tries = 0
        must = observed_ok[idx]
        rel = xy[idx] - c0
        # the sampler depends only on the part and its plots, so it is chosen once and shared by partitions;
        # its acceptance estimate uses its own RNG, so the choice never shifts the partition's stream
        ck = rel.tobytes()
        if part.get("_sampler_key") != ck:
            acc = geometric_acceptance(poly, rel, seeded(f"accept/{part['name']}"))
            part["_sampler_key"] = ck
            part["_accept"] = acc
            part["_sampler"] = None if acc >= PLAIN_MIN_ACCEPT else FeasibleRegionSampler(poly, rel)
        sampler = part["_sampler"]
        for r in range(n):
            while True:
                tries += 1
                if tries > 200_000 * n // 999 + 50_000:
                    raise RuntimeError(f"rotation null: part {part['name']} acceptance too low")
                if sampler is None:
                    th = rng.uniform(0, 2 * np.pi)
                    c1 = np.array([rng.uniform(minx, maxx), rng.uniform(miny, maxy)])
                else:
                    th, c1, _ = sampler.draw(rng)
                rot = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
                new = (xy[idx] - c0) @ rot.T + c1
                pts = shapely.points(new[:, 0], new[:, 1])
                if not shapely.covers(poly, pts).all():
                    continue
                q_in, q_tree = tree.query(pts, predicate="covered_by")
                # minimum stand key per plot (the join's tie-break), then that polygon's cluster
                order = np.lexsort((q_tree, key[q_tree], q_in))
                q_in, q_tree = q_in[order], q_tree[order]
                first = np.unique(q_in, return_index=True)[1]
                hit = np.full(len(idx), -1)
                hit[q_in[first]] = q_tree[first]
                if not (hit[must] >= 0).all():
                    continue
                break
            got = hit >= 0
            ids[r, idx] = np.where(got, key[np.maximum(hit, 0)], np.nan)
            cls[r, idx] = np.where(got, cid[np.maximum(hit, 0)], np.nan)
            b_in, b_tree = tree.query(pts, predicate="dwithin", distance=BDIST_SEARCH_M)
            other = key[b_tree] != ids[r, idx][b_in]
            b = np.full(len(idx), np.inf)
            if other.any():
                dist = shapely.distance(pts[b_in[other]], geoms[b_tree[other]])
                np.minimum.at(b, b_in[other], dist)
            bd[r, idx] = np.where(got, b, np.nan)
        attempts[part["name"]] = (tries / n, "plain" if sampler is None else "feasible-region", part["_accept"])
    return ids, cls, bd, attempts


# ---------------------------------------------------------------------- reporting helpers
def report_r2(label, obs_vec, null_by_var) -> dict:
    say(f"  6.1 {label} vs ROTATION null (observed = vector join, restricted R2)")
    say(f"    {'variable':<16} {'R2 all':>7} {'(k, n)':>10} {'R2 restr':>9} {'(k, n)':>9} "
        f"{'null med':>9} {'p5':>6} {'p95':>6} {'excess':>7} {'pctile':>7} {'n_null':>6}")
    out = {}
    for v in YVARS:
        ra, ka, na, rr, kr, nr = obs_vec[v]
        nul = null_by_var[v]
        med, p5, p95 = qs(nul)
        pc, nn = percentile(rr, nul)
        ex = rr - med if np.isfinite(rr) else np.nan
        ptxt = fmt(pc, 1) if nn >= MIN_NULL else "NOT EST"
        say(f"    {v:<16} {fmt(ra):>7} {f'({ka},{na})':>10} {fmt(rr):>9} {f'({kr},{nr})':>9} "
            f"{fmt(med):>9} {fmt(p5, 2):>6} {fmt(p95, 2):>6} {fmt(ex):>7} {ptxt:>7} {nn:>6}")
        record(section="6.1", null="rotation", partition=label, variable=v, r2_all=ra, k_all=ka, n_all=na,
               r2_restricted=rr, k_restricted=kr, n_restricted=nr, null_median=med, null_p5=p5, null_p95=p95,
               excess=ex, percentile=pc, n_null=nn)
        out[v] = dict(obs=rr, med=med, p5=p5, p95=p95, excess=ex, pct=pc, null=np.asarray(nul, float))
    return out


# ---------------------------------------------------------------------- per-partition analysis
class Ctx:
    pass


def analyse_partition(C: Ctx, part_obj: Partition, n_rot: int, primary: bool) -> dict:
    plots, parts = C.plots, C.parts
    arm, short, label = part_obj.arm, part_obj.short, part_obj.label
    rule(("PRIMARY RESULT — " if primary else "SECONDARY — ") + label)
    P = len(plots)
    ids, bdv = part_obj.ids, part_obj.bdist
    if part_obj.missing:
        say(f"  NOTE: districts not loaded for this partition, their plots unassigned in observed and null alike: "
            f"{part_obj.missing_why}")
    if part_obj.n_dropped_ids:
        say(f"  NOTE: {part_obj.n_dropped_ids} plots carry a stand id in the joined table for a district not loaded; "
            f"set to unassigned")
    n_obs_assigned = int((~np.isnan(ids)).sum())
    if n_obs_assigned < part_obj.n_in_loaded:
        say(f"  NOTE: observed assigned plots {n_obs_assigned} < {part_obj.n_in_loaded} plots in loaded districts; the "
            f"rotation null may assign the other {part_obj.n_in_loaded - n_obs_assigned} (it forces only the observed-"
            f"assigned plots to land on a stand)")
    pol = part_obj.polys
    areas = pol.groupby("key").area_ha.sum().astype(float)
    untyped = pol.cluster_id.isna()
    say(f"  partition: {areas.size} stands, area ha p10 {areas.quantile(.1):.2f} / median "
        f"{areas.median():.2f} / p90 {areas.quantile(.9):.2f}; plots assigned {int((~np.isnan(ids)).sum())} of {P}; "
        f"multi-plot stands {int((pd.Series(ids).value_counts() >= 2).sum())}")
    say(f"  polygons with no cluster_id: {int(untyped.sum())} of {len(pol)}, {pol.area_ha[untyped].astype(float).sum():.2f} ha "
        f"of {pol.area_ha.astype(float).sum():.2f} ha")

    rng = seeded(f"{arm}/{part_obj.layer_name}")
    prng = seeded(f"{arm}/{part_obj.layer_name}/perm")
    t0 = time.time()
    observed_ok = ~np.isnan(ids)
    rid, rcl, rbd, att = rotation_null(plots, parts, part_obj, observed_ok, n_rot, rng)
    say(f"  rotation null: {n_rot} realisations (seed crc32('{arm}/{part_obj.layer_name}')); {time.time() - t0:.0f} s; "
        f"mean draws per accepted realisation by part { {k: round(v[0], 1) for k, v in att.items()} }")
    fr = {k: f"{v[2]:.3f}" for k, v in att.items() if v[1] != "plain"}
    say(f"    sampler: plain rejection in every part" if not fr else
        f"    sampler: feasible-region (exact; plain geometric acceptance < {PLAIN_MIN_ACCEPT}) in {fr}; plain elsewhere")
    res = {"label": label}

    # ---------------- 6.1
    Y = {v: plots[v].to_numpy(float) for v in YVARS}
    obs_vec = {v: (*r2_partition(Y[v], ids, False), *r2_partition(Y[v], ids, True)) for v in YVARS}
    rot_r2 = {v: np.array([r2_partition(Y[v], rid[r], True)[0] for r in range(n_rot)]) for v in YVARS}
    res["r2"] = report_r2(label, obs_vec, rot_r2)

    part_arr = plots.aoi_part.to_numpy()
    say("")
    sens("6.1 null structure — does the rotation null have the observed partition's shape?")
    od = r2_detail(Y["loreys_h_m"], ids, part_arr)
    nds = [r2_detail(Y["loreys_h_m"], rid[r], part_arr) for r in range(n_rot)]
    iu, ju, sp = C.iu, C.ju, C.same_part
    same_obs = int(((ids[iu] == ids[ju]) & sp).sum())
    same_null = np.array([int(((rid[r][iu] == rid[r][ju]) & sp).sum()) for r in range(n_rot)])
    say("    (restricted set: multi-plot stands over plots with loreys_h_m)")
    say(f"    {'quantity':<30} {'observed':>9} {'null med':>9} {'p5':>7} {'p95':>7}  pctile")
    for nm, o_, nv in (("k (multi-plot stands)", od["k"], [d["k"] for d in nds]),
                       ("n (plots in them)", od["n"], [d["n"] for d in nds]),
                       ("E = (k-1)/(n-1)", od["E"], [d["E"] for d in nds]),
                       ("largest multi-plot group", od["largest"], [d["largest"] for d in nds]),
                       ("same-stand within-part pairs", same_obs, same_null)):
        med, p5, p95 = qs(nv)
        say(f"    {nm:<30} {fmt(float(o_), 3):>9} {fmt(med):>9} {fmt(p5):>7} {fmt(p95):>7}  {pct_text(float(o_), nv)}")
    bias = []
    for v in YVARS:
        dd = [r2_detail(Y[v], rid[r], part_arr) for r in range(n_rot)]
        e = np.array([d["E"] for d in dd])
        rr = np.array([d["r2"] for d in dd])
        ok = np.isfinite(e) & np.isfinite(rr)
        eo = r2_detail(Y[v], ids, part_arr)["E"]
        if ok.sum() > 2 and np.isfinite(eo):
            slope = np.polyfit(e[ok], rr[ok], 1)[0]
            bias.append(f"{v} {slope * (eo - np.median(e[ok])):+.3f} (n {int(ok.sum())})")
        else:
            bias.append(f"{v} n/a (n {int(ok.sum())})")
    say("    E-slope bias estimate, slope(null R2 on null E) x (E_obs - E_null median), in R2 units; negative means the "
        "null's different E alone")
    say("    pushes the observed value below the null median by about that much, i.e. the percentile is biased low: "
        + "; ".join(bias))

    if short == "merged":
        say("")
        sens("6.1 alternatives to raw restricted R2 vs the same rotation null (each realisation with its own k, n)")
        say(f"    {'variable':<16} {'adj R2':>7} {'pctile (n_null)':>24} {'within-part R2':>15} {'pctile (n_null)':>24}   "
            f"leave-one-site-out restricted R2 percentile (n_null)")
        names = [p["name"] for p in parts]
        present_parts = sorted(np.unique(part_arr))
        for v in YVARS:
            od_v = r2_detail(Y[v], ids, part_arr)
            ndv = [r2_detail(Y[v], rid[r], part_arr) for r in range(n_rot)]
            null_adj, null_wp = [d["adj"] for d in ndv], [d["r2_wp"] for d in ndv]
            pa, na_ = percentile(od_v["adj"], null_adj)
            pw, nw_ = percentile(od_v["r2_wp"], null_wp)
            loso, loso_rec = [], {}
            for q in present_parts:
                m = part_arr != q
                o_ = r2_partition(Y[v][m], ids[m], True)[0]
                nl = np.array([r2_partition(Y[v][m], rid[r][m], True)[0] for r in range(n_rot)])
                pc, nn = percentile(o_, nl)
                loso.append(f"-{names[q]} {pct_text(o_, nl)}")
                loso_rec[f"loso_pct_{names[q]}"], loso_rec[f"loso_n_null_{names[q]}"] = pc, nn
            say(f"    {v:<16} {fmt(od_v['adj']):>7} {pct_text(od_v['adj'], null_adj):>24} {fmt(od_v['r2_wp']):>15} "
                f"{pct_text(od_v['r2_wp'], null_wp):>24}   " + ", ".join(loso))
            record(section="6.1-sens", partition=label, variable=v, adj_r2=od_v["adj"], adj_pct=pa, n_null_adj=na_,
                   r2_within_part=od_v["r2_wp"], within_part_pct=pw, n_null_within_part=nw_, **loso_rec)

    if short == "dissolved":
        say("")
        sens("dissolved layer vs AOI parts — is it the site partition?")
        m = ~np.isnan(ids)
        per = {parts[q]["name"]: int(len(np.unique(ids[m & (part_arr == q)]))) for q in sorted(np.unique(part_arr))}
        ari = adjusted_rand_score(part_arr[m], ids[m])
        say(f"    units holding plots, per AOI part: {per}")
        say(f"    ARI(unit id, AOI part) over {int(m.sum())} assigned plots: {ari:.3f}")
        site_r2 = {v: r2_partition(Y[v], part_arr.astype(float), True)[0] for v in YVARS}
        say("    restricted R2 of the site-only partition (AOI part as the group): "
            + "; ".join(f"{v} {fmt(site_r2[v])}" for v in YVARS))
        if ari >= 0.7:
            say("    !! ARI >= 0.7: this layer is effectively the site partition; its statistics measure between-site "
                "differences and are not a delineation test.")
        record(section="dissolved-sens", partition=label, ari_unit_part=ari, **{f"site_r2_{v}": site_r2[v] for v in YVARS})

    # ---------------- 6.2
    say("")
    say("  6.2 pairwise boundary test (pairs within an AOI part)")
    same_v = (ids[iu] == ids[ju]) & ~np.isnan(ids[iu]) & ~np.isnan(ids[ju])
    assigned = ~np.isnan(ids[iu]) & ~np.isnan(ids[ju]) & sp
    inner_v = assigned & (bdv[iu] > BOUNDARY_M) & (bdv[ju] > BOUNDARY_M)
    ppart = part_arr[iu]
    res["bands"] = {}
    for dname, dvals in (("Bray-Curtis", C.d_bc), ("|dLorey| m", C.d_lo)):
        for sname, ok in (("all pairs", assigned), (f"both > {BOUNDARY_M:.0f} m from boundary", inner_v)):
            o = pair_stats(same_v, C.d_geo, dvals, ok)
            rot = [pair_stats((rid[r][iu] == rid[r][ju]), C.d_geo, dvals,
                              ok if "all" in sname else (assigned & (rbd[r][iu] > BOUNDARY_M) & (rbd[r][ju] > BOUNDARY_M)))
                   for r in range(n_rot)]
            naive = shuffle_p(same_v, C.d_geo, dvals, ok, np.zeros(len(iu), int), prng)
            say(f"    {dname}, {sname}:")
            say(f"      {'band m':<9} {'n same':>6} {'n diff':>6} {'mean same':>9} {'mean diff':>9} "
                f"{'diff':>7} {'rot pctile':>32}   naive perm p (INVALID: pools sites, pairs dependent)")
            cells = {}
            for lo, hi in BANDS:
                key = f"diff_{lo}_{hi}"
                nul = np.array([x[key] for x in rot])
                ns_, nd_ = o[f"n_same_{lo}_{hi}"], o[f"n_diff_{lo}_{hi}"]
                unin = ns_ <= MIN_CELL or nd_ <= MIN_CELL
                pc, nn = percentile(o[key], nul)
                ptxt = "uninformative (n<=3)" if unin else pct_text(o[key], nul)
                say(f"      {f'{lo}-{hi}':<9} {ns_:>6} {nd_:>6} "
                    f"{fmt(o[f'mean_same_{lo}_{hi}']):>9} {fmt(o[f'mean_diff_{lo}_{hi}']):>9} {fmt(o[key]):>7} "
                    f"{ptxt:>32}   {p_text(naive, key)}")
                med, p5, p95 = qs(nul)
                cells[(lo, hi)] = dict(obs=o[key], p5=p5, p95=p95, med=med, unin=unin, ns=ns_, nd=nd_)
                record(section="6.2", null="rotation", partition=label, measure=dname, subset=sname,
                       band=f"{lo}-{hi}", n_same=ns_, n_diff=nd_, diff=o[key], naive_perm_p_invalid=naive[key],
                       percentile=np.nan if unin else pc, n_null=nn, uninformative=unin)
            bn = np.array([x["beta_same"] for x in rot])
            pc, nn = percentile(-o["beta_same"], -bn)
            say(f"      regression d_field ~ d_geo + same_stand (pairs < 800 m, n={o['n_pairs_reg']}, "
                f"same={o['n_same_reg']}): beta_same {fmt(o['beta_same'], 4)}, beta per 100 m "
                f"{fmt(o['beta_dgeo_per100m'], 4)}; rotation null median {fmt(qs(bn)[0], 4)}; "
                f"stand-effect percentile {pct_text(-o['beta_same'], -bn)} (high = more similar than null); "
                f"naive perm p {p_text(naive, 'beta_same')} (INVALID)")
            record(section="6.2", null="rotation", partition=label, measure=dname, subset=sname, band="regression",
                   beta_same=o["beta_same"], beta_dgeo_per100m=o["beta_dgeo_per100m"], n_pairs=o["n_pairs_reg"],
                   n_same=o["n_same_reg"], percentile=pc, n_null=nn, naive_perm_p_invalid=naive["beta_same"])
            if C.d_bc_first is not None and dname == "Bray-Curtis":
                # the same observed statistic on the first run's species keys (R15 undone, everything else as now),
                # used only to attribute changes in the corrections section
                C.first_keys[(label, dname, sname)] = pair_stats(same_v, C.d_geo, C.d_bc_first, ok)
            ws = shuffle_p(same_v, C.d_geo, dvals, ok, ppart, prng)
            sens(f"within-site shuffle p ({N_PERM} shuffles of same_stand among pairs in the same AOI part and band; "
                 "upper tail for diff, lower for beta; 'degenerate' = no AOI part x band group holds both pair "
                 "types, so no shuffle can change a label and there is no test):")
            say("      " + "; ".join(
                f"{lo}-{hi} {p_text(ws, f'diff_{lo}_{hi}')}" + (" (uninformative n<=3)" if cells[(lo, hi)]["unin"] else "")
                for lo, hi in BANDS) + f"; beta_same {p_text(ws, 'beta_same')}")
            record(section="6.2-sens", partition=label, measure=dname, subset=sname,
                   **{f"within_site_p_{lo}_{hi}": ws[f"diff_{lo}_{hi}"] for lo, hi in BANDS},
                   within_site_p_beta=ws["beta_same"], within_site_degenerate=";".join(sorted(ws["degenerate"])))
            if "all" in sname:
                res["bands"][dname] = cells

        if short == "merged":
            sens(f"6.2 robustness of beta_same, {dname}, all pairs (same rotation realisations throughout)")
            ok = assigned
            if dname == "Bray-Curtis":
                sel = same_v & ok
                names = [p["name"] for p in parts]
                say("    same-stand pairs by AOI part: observed / null median / null p95 / pctile")
                for q in sorted(np.unique(part_arr)):
                    mq = sp & (ppart == q)
                    o_ = int((sel & mq).sum())
                    nq = np.array([int(((rid[r][iu] == rid[r][ju]) & mq).sum()) for r in range(n_rot)])
                    say(f"      {names[q]:<24} {o_:>4} / {np.median(nq):>5.0f} / {np.percentile(nq, 95):>5.0f} / {pct_text(o_, nq)}")
                st = pd.DataFrame({"stand": ids[iu][sel], "part": ppart[sel]})
                npl = pd.Series(ids).value_counts()
                g = st.groupby(["part", "stand"]).size().sort_values(ascending=False)
                say("    same-stand pairs by stand (AOI part, stand id as in the layer, plots, pairs): " + "; ".join(
                    f"{names[pq]} {part_obj.raw[s][1]} {int(npl[s])}p {c}" for (pq, s), c in g.items()))
            rows = []
            for nm, kw, okx in ([("site fixed effects", {"part": ppart}, ok),
                                 ("stand-weighted (same pair weight 1/pairs in its stand)", {"weights_key": ids[iu]}, ok)]
                                + [(f"drop {parts[q]['name']}", {}, ok & (ppart != q)) for q in sorted(np.unique(part_arr))]):
                o_ = pair_stats(same_v, C.d_geo, dvals, okx, **kw)
                kwr = lambda r: ({"part": ppart} if "part" in kw else {"weights_key": rid[r][iu]} if kw else {})  # noqa: E731
                nb = np.array([pair_stats(rid[r][iu] == rid[r][ju], C.d_geo, dvals, okx, **kwr(r))["beta_same"]
                               for r in range(n_rot)])
                pc, nn = percentile(-o_["beta_same"], -nb)
                say(f"      {nm:<56} n_same {o_['n_same_reg']:>4}  beta_same {fmt(o_['beta_same'], 4)}  null median "
                    f"{fmt(qs(nb)[0], 4)}  stand-effect pctile {pct_text(-o_['beta_same'], -nb)}")
                record(section="6.2-sens", partition=label, measure=dname, subset="all pairs", variant=nm,
                       beta_same=o_["beta_same"], n_same=o_["n_same_reg"], percentile=pc, n_null=nn)

    # ---------------- 6.3
    if short == "merged":
        res["labels"] = analyse_labels(C, part_obj, rid, rcl, n_rot)
    res["rid"] = rid
    return res


def analyse_labels(C: Ctx, part_obj: Partition, rid, rcl, n_rot) -> dict:
    plots, iu, ju = C.plots, C.iu, C.ju
    clus = part_obj.cluster
    say("")
    say("  6.3 label agreement (typology, not delineation) — merged stand cluster_id")
    dist = plots.district_set.to_numpy()
    out = {}
    per_district = {}
    for d in part_obj.districts:
        m = (dist == d) & ~np.isnan(clus)
        valid = ~np.isnan(rcl[:, m]).any(axis=1)
        per_district[d] = (m, valid)
        say(f"    district {d}: typed plots {int(m.sum())} of {int((dist == d).sum())}; rotation realisations used "
            f"{int(valid.sum())} of {n_rot} (the rest put a typed plot on a polygon with no cluster_id)")
    # Set-level nulls (plot-weighted mean, distant pairs) pair the c-th valid realisation of each district.
    # Rotations of different districts are independent draws and validity depends on a district's own plots,
    # so this is a draw from the same null as requiring validity everywhere at once, without the usable count
    # shrinking as the product of the districts' validity rates. With one district it is exactly the valid rows.
    valid_rows = {d: np.where(v)[0] for d, (m, v) in per_district.items() if m.any()}
    n_comb = min((len(r) for r in valid_rows.values()), default=0)
    if len(valid_rows) > 1:
        say(f"    set-level nulls: the c-th valid realisation of each district combined index-wise; {n_comb} combined "
            f"realisations (implementation choice, not pre-registered)")
    for tname, tt in (("UPGMA k=6", C.ftype), ("Sal-dominant rule", C.sal_rule)):
        say(f"    field type = {tname}")
        stats_d = {}
        for d, (m, valid) in per_district.items():
            if not m.any():
                say(f"      {d}: no typed plots; not computed")
                continue
            ft, cl = tt[m], clus[m]
            n_types = len(np.unique(ft))
            o = agreement(ft, cl)
            if n_types < 2:
                say(f"      {d}: typed plots n={int(m.sum())} hold {n_types} field type(s) "
                    f"({pd.Series(ft).value_counts().to_dict()}): ARI, NMI, Cramér's V NOT ESTIMABLE")
                for key in ("ari", "nmi", "cramers_v"):
                    record(section="6.3", null="rotation", partition=part_obj.label, district=d, field_type=tname,
                           statistic=key, observed=np.nan, percentile=np.nan, n_null=0, n=int(m.sum()),
                           note="NOT ESTIMABLE: < 2 field types")
                _, tab, _, n_cells = contingency(ft, cl.astype(int))
                say(f"      {d}: contingency (rows field type, columns cluster_id); cells with expected count < 5: "
                    f"n/a (one row; no chi-square) of {n_cells}")
                for line in tab.to_string().splitlines():
                    say("        " + line)
                continue
            rows = np.where(valid)[0]
            nulls = {key: np.array([agreement(ft, rcl[r, m])[key] for r in rows]) for key in ("ari", "nmi", "cramers_v")}
            stats_d[d] = (o, nulls, rows, int(m.sum()))
            for key in ("ari", "nmi", "cramers_v"):
                med, p5, p95 = qs(nulls[key])
                pc, nn = percentile(o[key], nulls[key])
                say(f"      {d}: {key:<10} {fmt(o[key])} (n plots {int(m.sum())}); rotation null median {fmt(med)}, "
                    f"p95 {fmt(p95)}, percentile {pct_text(o[key], nulls[key])}")
                record(section="6.3", null="rotation", partition=part_obj.label, district=d, field_type=tname,
                       statistic=key, observed=o[key], null_median=med, percentile=pc, n_null=nn, n=int(m.sum()))
            _, tab, n_lt5, n_cells = contingency(ft, cl.astype(int))
            say(f"      {d}: contingency (rows field type, columns cluster_id); cells with expected count < 5: "
                f"{n_lt5} of {n_cells}")
            for line in tab.to_string().splitlines():
                say("        " + line)
        if len(stats_d) > 1:
            n_w = min(len(s[2]) for s in stats_d.values())
            for key in ("ari", "nmi", "cramers_v"):
                w = np.array([s[3] for s in stats_d.values()], float)
                ob = np.average([s[0][key] for s in stats_d.values()], weights=w)
                nm = np.array([np.average([s[1][key][c] for s in stats_d.values()], weights=w) for c in range(n_w)])
                pc, nn = percentile(ob, nm)
                say(f"      plot-weighted mean over {len(stats_d)} districts: {key:<10} {fmt(ob)}; percentile "
                    f"{pct_text(ob, nm)} (c-th valid realisation of each district combined)")
                record(section="6.3", null="rotation", partition=part_obj.label, district="weighted mean",
                       field_type=tname, statistic=key, observed=ob, percentile=pc, n_null=nn)
    # distant pairs: depend on the stand label only, so once per partition
    say("    distant pairs (> 2 km, same district; depend only on the stand cluster label):")
    far = (C.d_geo > DISTANT_M) & C.same_district
    typed_plot = ~np.isnan(clus)
    o = distant_stats(clus, iu, ju, far & typed_plot[iu] & typed_plot[ju], C.d_bc, C.d_lo)
    if C.d_bc_first is not None:
        C.first_keys[(part_obj.label, "distant")] = distant_stats(clus, iu, ju, far & typed_plot[iu] & typed_plot[ju],
                                                                  C.d_bc_first, C.d_lo)
    rot = []
    for c in range(n_comb):
        comb = np.full(len(plots), np.nan)
        for d, rws in valid_rows.items():
            md = dist == d
            comb[md] = rcl[rws[c], md]
        rot.append(distant_stats(comb, iu, ju, far & typed_plot[iu] & typed_plot[ju], C.d_bc, C.d_lo))
    for name in ("bc", "lorey"):
        key = f"distant_diff_{name}"
        nul = np.array([x[key] for x in rot])
        med, p5, p95 = qs(nul)
        pc, nn = percentile(o[key], nul)
        say(f"      {key:<20} {fmt(o[key])} (n same-label {o['n_same_' + name]}, n different-label {o['n_diff_' + name]}); "
            f"rotation null median {fmt(med)}, p5 {fmt(p5)}, p95 {fmt(p95)}, percentile {pct_text(o[key], nul)}")
        record(section="6.3", null="rotation", partition=part_obj.label, field_type="(label only)", statistic=key,
               observed=o[key], null_median=med, percentile=pc, n_null=nn, n_same=o["n_same_" + name])
    return out


# ---------------------------------------------------------------------- set-level sections
def dgeo_prediction(C: Ctx) -> None:
    rule("6.2 PRE-REGISTERED: d_field rises with d_geo")
    w = C.same_part & (C.d_geo < BANDS[-1][1])
    far = (C.d_geo > DISTANT_M) & C.same_district
    for nm, d in (("Bray-Curtis", C.d_bc), ("|dLorey| m", C.d_lo)):
        ok = w & ~np.isnan(d)
        slope = np.polyfit(C.d_geo[ok] / 100.0, d[ok], 1)[0]
        rho = spearmanr(C.d_geo[ok], d[ok])[0]
        say(f"  {nm:<12} within AOI parts, pairs < 800 m (n={int(ok.sum())}): OLS slope {slope:+.4f} per 100 m, "
            f"Spearman rho {rho:+.3f}")
        record(section="6.2-dgeo", measure=nm, slope_per100m=slope, spearman_rho=rho, n_pairs=int(ok.sum()))
    sp = C.same_part & ~np.isnan(C.d_lo)
    fr = far & ~np.isnan(C.d_lo)
    say(f"  mean |dLorey|: within-part pairs {C.d_lo[sp].mean():.2f} m (n={int(sp.sum())}) vs pairs > 2 km "
        f"{C.d_lo[fr].mean():.2f} m (n={int(fr.sum())}); mean Bray-Curtis {C.d_bc[C.same_part].mean():.3f} vs "
        f"{C.d_bc[far].mean():.3f}")


def arms_section(results: dict) -> dict:
    rule("ARMS (pre-registered): difference in excess over own rotation null, stands_merged")
    arms = [a for a in ARMS if (a, "merged") in results]
    out = {}
    if len(arms) < 2:
        say("  fewer than two arms present; not computed")
        return out
    say("  excess = observed restricted R2 - own null median. Null of the difference: each arm's null centred on its own")
    say("  median, differenced index-wise between the arms' independent draws. Prediction: the observed difference")
    say("  falls inside that null's p5-p95.")
    for a, b in [(arms[0], x) for x in arms[1:]]:
        ra, rb = results[(a, "merged")]["r2"], results[(b, "merged")]["r2"]
        say(f"  {a} - {b}:")
        say(f"    {'variable':<16} {'excess ' + a:>14} {'excess ' + b:>16} {'difference':>11} {'null p5':>8} {'null p95':>9}  pctile")
        for v in YVARS:
            na, nb = ra[v]["null"] - ra[v]["med"], rb[v]["null"] - rb[v]["med"]
            n = min(len(na), len(nb))
            dn = na[:n] - nb[:n]
            dv = ra[v]["excess"] - rb[v]["excess"]
            _, p5, p95 = qs(dn)
            pc, nn = percentile(dv, dn)
            inside = "inside" if p5 <= dv <= p95 else "OUTSIDE"
            say(f"    {v:<16} {fmt(ra[v]['excess']):>14} {fmt(rb[v]['excess']):>16} {fmt(dv):>11} {fmt(p5):>8} "
                f"{fmt(p95):>9}  {pct_text(dv, dn)}  {inside}")
            record(section="arms", arms=f"{a}-{b}", variable=v, excess_diff=dv, null_p5=p5, null_p95=p95,
                   percentile=pc, n_null=nn)
        say("")
        sens("literal reading of the prediction's wording, 'falls inside either arm's null spread': the difference "
             "against each arm's OWN null, centred on its median, p5-p95")
        say(f"    {'variable':<16} {'difference':>11} {a + ' centred p5..p95':>26} {'':>8} {b + ' centred p5..p95':>28} {'':>8}  verdict")
        for v in YVARS:
            dv = ra[v]["excess"] - rb[v]["excess"]
            spans, verdicts = [], []
            for r_ in (ra, rb):
                lo_, hi_ = r_[v]["p5"] - r_[v]["med"], r_[v]["p95"] - r_[v]["med"]
                ins = bool(np.isfinite(dv) and lo_ <= dv <= hi_)
                spans.append(f"[{fmt(lo_)}, {fmt(hi_)}]")
                verdicts.append("inside" if ins else "OUTSIDE")
            n_in = verdicts.count("inside")
            verdict = {2: "inside both", 1: "inside one", 0: "inside neither"}[n_in]
            say(f"    {v:<16} {fmt(dv):>11} {spans[0]:>26} {verdicts[0]:>8} {spans[1]:>28} {verdicts[1]:>8}  {verdict}")
            record(section="arms-sens", arms=f"{a}-{b}", variable=v, excess_diff=dv,
                   **{f"inside_own_null_{a}": verdicts[0] == "inside", f"inside_own_null_{b}": verdicts[1] == "inside"})
    return out


# ---------------------------------------------------------------------- corrections header
CORRECTIONS = [
    "R1  cluster_id rounded (np.rint) in the join and for rotation-null labels: GEE's mode reducer gave 4.9999999999999885 "
    "for current's class 5 (6 pilot plots). The first run truncated these ids to int for ARI/NMI/Cramér's V and the "
    "contingency table (the 6 plots counted as class 4), and compared the unrounded floats for distant pairs (splitting "
    "class 5; current distant same-label pairs 160 -> 198).",
    "R2  6.3 ARI/NMI/V printed NOT ESTIMABLE when typed plots hold < 2 field types (pilot UPGMA k=6 is constant); distant "
    "pairs printed once per partition; expected-count < 5 cells printed for every contingency table.",
    "R3  every percentile printed with n_null; NOT ESTIMABLE below 100 defined null values.",
    "R4  6.2 cells with n_same <= 3 or n_diff <= 3 marked uninformative (n<=3), no percentile.",
    "R5  dissolved layer: units per AOI part, ARI(unit, part), site-only restricted R2 (SENSITIVITY).",
    "R6  within-band label permutation p relabelled INVALID; within-site shuffle p added (SENSITIVITY).",
    "R7  6.1 null structure (k, n, E, largest group, same-stand pairs) and E-slope bias estimate (SENSITIVITY).",
    "R8  6.1 adjusted R2, within-part R2 and leave-one-site-out percentiles vs the rotation null (SENSITIVITY, merged).",
    "R9  6.2 same-stand pairs by part and stand, leave-one-site-out, site fixed effects, stand-weighted beta (SENSITIVITY, merged).",
    "R10 pre-registered ARMS prediction computed: excess difference vs index-wise differenced centred nulls.",
    "R11 pre-registered 'd_field rises with d_geo' computed: slope, Spearman rho, within-part vs > 2 km means.",
    "R12 6.3 uses only rotation realisations that keep every typed plot on a typed polygon; untyped polygons counted.",
    "R13 per-partition RNGs seeded from crc32('<arm>/<layer>') (separate permutation stream); --rotations default 1999.",
    "R14 rotation null matches the join: minimum stand id on multi-cover; boundary search 1000 m, inf beyond (was capped at 600 m).",
    "R15 species keys: trailing '.' stripped, aliases cassia fistul/lagerstroemia parviflor/zizyphus oenoplia; the "
    "join was rerun, changing sp_ba_json of 8 pilot plots and so Bray-Curtis numbers (sal_ba_frac and n_species of pilot "
    "plots unchanged; all-274 UPGMA sizes 10/260/1/1/1/1 -> 11/259/1/1/1/1, still one type in the pilot).",
    "R16 figures redrawn from the rotation null (the first run's figure code read the noise null, which was never used).",
    "R17 DATA line states the noise null's exclusion by decision; this corrections section added.",
    "R18 --set pilot|districts; d_geo geodesic (WGS84) instead of planar UTM, which moves pilot betas in the 4th decimal "
    "and changes no band count; rotations and boundary distances in each AOI part's own UTM zone.",
]


def first_run_dgeo_slopes() -> dict:
    """beta per 100 m from the first run's results text (its summary CSV did not record it)."""
    try:
        txt = subprocess.run(["git", "show", f"{FIRST_RUN}:odisha_script/odisha_phase2_5_results.txt"], cwd=REPO,
                             capture_output=True, text=True, check=True).stdout
    except Exception:  # noqa: BLE001
        return {}
    import re
    out, label, head = {}, None, None
    for line in txt.splitlines():
        m = re.match(r"^(?:PRIMARY RESULT|SECONDARY) — (.+)$", line)
        if m:
            label, head = m.group(1).strip(), None
            continue
        m = re.match(r"^    (Bray-Curtis|\|dLorey\| m), (.+):$", line)
        if m:
            head = (m.group(1), m.group(2))
            continue
        m = re.search(r"regression d_field ~ d_geo \+ same_stand .*beta per 100 m\s+(\S+);", line)
        if m and label and head and (label, *head) not in out:
            v = m.group(1)
            out[(label, *head)] = np.nan if v == "n/a" else float(v)
            head = None
    return out


def corrections_block(spec: dict, n_rot: int, C: Ctx) -> list[str]:
    lines = ["", "=" * 100, f"CORRECTIONS TO THE FIRST RUN (git {FIRST_RUN})", "=" * 100]
    if spec["name"] != "pilot":
        lines.append(f"  NOTE: set '{spec['name']}'. The first run covered the pilot only. The list below describes the code "
                     "corrections; every number and plot count in it refers to the PILOT run, not to this set.")
    lines += ["  " + c for c in CORRECTIONS]
    if spec["name"] != "pilot":
        lines.append("  (no value comparison for this set)")
        return lines
    try:
        txt = subprocess.run(["git", "show", f"{FIRST_RUN}:odisha_script/odisha_phase2_5_summary.csv"], cwd=REPO,
                             capture_output=True, text=True, check=True).stdout
        # section is read as text: "6.1" would otherwise load as a float and match nothing
        old = pd.read_csv(StringIO(txt), dtype={"section": str})
    except Exception as e:  # noqa: BLE001
        lines.append(f"  first-run summary not readable from git ({e}); value comparison skipped")
        return lines
    new = pd.DataFrame(_rows)
    old["partition"] = old.partition.str.replace(r"^6\.1 (.*) vs ROTATION null.*$", r"\1", regex=True)
    lines.append("")
    lines.append("  Pre-registered OBSERVED values that changed, first run -> corrected (Monte Carlo cannot move these):")
    changed_obs, pct_moves = [], []

    geodesic_only = []
    TOL = 1e-9

    def differs(x, y):
        return (np.isnan(x) != np.isnan(y)) or (not np.isnan(x) and abs(x - y) > TOL)

    def cmp(o_row, n_row, fields, tag, kind, arm, first=None):
        """kind: '6.1', '6.2-bc', '6.2-lorey', '6.3-label', '6.3-distant-bc', '6.3-distant-lorey'.
        first: field -> the same observed statistic recomputed now on the first run's species keys (R15 undone),
        so a change splits exactly into R15 (new vs first) and the rest (first-run value vs first)."""
        for f_ in fields:
            a, b = o_row.get(f_), n_row.get(f_)
            a = np.nan if a is None or pd.isna(a) else float(a)
            b = np.nan if b is None or pd.isna(b) else float(b)
            if differs(a, b):
                r1 = bool(C.r1_changed.get(arm)) if C.r1_changed is not None else None
                fv = None if first is None or first.get(f_) is None else float(first[f_])
                if kind == "6.3-label" and "UPGMA" in tag and np.isnan(b):
                    why = "R2 (typed plots hold one field type)"
                elif kind == "6.3-label":
                    why = ("R1 (first run truncated 4.99999 to class 4)" if r1 else "unattributed")
                elif kind == "6.3-distant-lorey":
                    why = "R1 (first run compared unrounded labels)" if r1 else "R18 (geodesic d_geo) or unattributed"
                elif kind in ("6.2-bc", "6.3-distant-bc"):
                    if fv is None:
                        why = "R15 and/or R18 (first-run species keys not available to split)"
                    else:
                        rest = ("R1 (labels)" if kind == "6.3-distant-bc" and r1 else "R18 (geodesic d_geo)")
                        parts_ = (["R15 (species keys)"] if differs(fv, b) else []) + ([rest] if differs(a, fv) else [])
                        why = " + ".join(parts_) or "unattributed"
                elif kind == "6.2-lorey":
                    why = "R18 (geodesic d_geo)"
                else:
                    why = "unattributed"
                line = f"    {tag} {f_}: {fmt(a, 4)} -> {fmt(b, 4)}   [{why}]"
                # |dLorey| does not read species keys or cluster ids: a sub-1e-3 relative move there is the
                # geodesic d_geo entering the regression (R18), not R1 or R15
                if "|dLorey|" in tag and not np.isnan(a) and abs(a - b) <= 1e-3 * max(abs(a), 1e-12):
                    geodesic_only.append(line + f" (rel {abs(a - b) / abs(a):.1e})")
                else:
                    changed_obs.append(line)

    def pct_cmp(o_row, n_row, tag):
        a, b = o_row.get("percentile"), n_row.get("percentile")
        a = np.nan if pd.isna(a) else float(a)
        b = np.nan if pd.isna(b) else float(b)
        why = ""
        if np.isnan(b):
            unin = n_row.get("uninformative")
            note = n_row.get("note")
            nn = n_row.get("n_null")
            # 6.3 rows carry no 'uninformative' field: NaN there must not read as True
            if unin is not None and not pd.isna(unin) and bool(unin):
                why = " uninformative (n<=3), R4"
            elif isinstance(note, str) and note:
                why = " NOT ESTIMABLE (< 2 field types), R2"
            elif nn is not None and not pd.isna(nn) and nn < MIN_NULL:
                why = f" NOT ESTIMABLE (n_null {int(nn)}), R3"
        pct_moves.append((tag, a, b, why))

    s61n = new[new.section == "6.1"].set_index(["partition", "variable"])
    for _, r in old[old.section == "6.1"].iterrows():
        k = (r.partition, r.variable)
        if k in s61n.index:
            n_ = s61n.loc[k]
            cmp(r, n_, ["r2_all", "k_all", "n_all", "r2_restricted", "k_restricted", "n_restricted"], f"6.1 {k[0]} {k[1]}",
                "6.1", k[0].split(" / ")[0])
            pct_cmp(r, n_, f"6.1 {k[0]} {k[1]}")
    s62n = new[new.section == "6.2"].set_index(["partition", "measure", "subset", "band"])
    old_dgeo = first_run_dgeo_slopes()
    for _, r in old[(old.section == "6.2") & (old.null == "rotation")].iterrows():
        k = (r.partition, r.measure, r.subset, r.band)
        if k in s62n.index:
            n_ = s62n.loc[k]
            fk = C.first_keys.get((r.partition, r.measure, r.subset))
            if r.band == "regression":
                fields = ["beta_same", "beta_dgeo_per100m", "n_pairs", "n_same"]
                r = r.copy()
                r["beta_dgeo_per100m"] = old_dgeo.get((r.partition, r.measure, r.subset), np.nan)
                first = None if fk is None else {"beta_same": fk["beta_same"], "beta_dgeo_per100m": fk["beta_dgeo_per100m"],
                                                 "n_pairs": fk["n_pairs_reg"], "n_same": fk["n_same_reg"]}
            else:
                fields = ["n_same", "n_diff", "diff"]
                bk = r.band.replace("-", "_")
                first = None if fk is None else {f_: fk[f"{f_}_{bk}"] for f_ in fields}
            kind = "6.2-bc" if r.measure == "Bray-Curtis" else "6.2-lorey"
            cmp(r, n_, fields, "6.2 " + " / ".join(k), kind, r.partition.split(" / ")[0], first)
            pct_cmp(r, n_, "6.2 " + " / ".join(k))
    s63n = new[new.section == "6.3"]
    for _, r in old[old.section == "6.3"].iterrows():
        if r.statistic.startswith("distant"):
            n_ = s63n[(s63n.partition == r.partition) & (s63n.statistic == r.statistic)]
        else:
            n_ = s63n[(s63n.partition == r.partition) & (s63n.statistic == r.statistic) & (s63n.field_type == r.field_type)]
        if not len(n_):
            continue
        n_ = n_.iloc[0]
        tag = f"6.3 {r.partition} {r.field_type if not r.statistic.startswith('distant') else ''} {r.statistic}"
        if r.statistic.startswith("distant") and r.field_type != "UPGMA k=6":
            continue  # the first run printed the distant pair stats twice; compare once
        arm = r.partition.split(" / ")[0]
        if r.statistic == "distant_diff_bc":
            fk = C.first_keys.get((r.partition, "distant"))
            cmp(r, n_, ["observed"], tag, "6.3-distant-bc", arm, None if fk is None else {"observed": fk["distant_diff_bc"]})
        elif r.statistic == "distant_diff_lorey":
            cmp(r, n_, ["observed"], tag, "6.3-distant-lorey", arm)
        else:
            cmp(r, n_, ["observed"], tag, "6.3-label", arm)
        pct_cmp(r, n_, tag)
    if C.d_bc_first is None:
        lines.append("    (first run's joined table not readable from git: Bray-Curtis changes are not split into R15 / R18)")
    lines.append("    (beta per 100 m is compared against the first run's results text; its summary CSV did not record it)"
                 if old_dgeo else "    (first run's results text not readable: beta per 100 m not compared)")
    lines += changed_obs or ["    none"]
    lines.append("  |dLorey| values moved only by the geodesic d_geo (R18, relative change < 1e-3):")
    lines += geodesic_only or ["    none"]
    big = [(t, a, b, w) for t, a, b, w in pct_moves
           if (np.isnan(a) != np.isnan(b)) or (not np.isnan(a) and abs(a - b) > 5)]
    small = [abs(a - b) for t, a, b, _ in pct_moves if not np.isnan(a) and not np.isnan(b) and abs(a - b) <= 5]
    lines.append("")
    lines.append(f"  Pre-registered PERCENTILES: every one is redrawn (new seeds, {n_rot} realisations, R3/R4/R12/R14 rules). "
                 f"Moves > 5 pp or a change of estimability, first run -> corrected:")
    lines += [f"    {t}: {fmt(a, 1)} -> {fmt(b, 1)}{w}" for t, a, b, w in big] or ["    none"]
    if small:
        lines.append(f"  All other percentile moves: median {np.median(small):.1f} pp, max {max(small):.1f} pp (Monte Carlo).")
    return lines


# ---------------------------------------------------------------------- figures
def figures(results: dict, suffix: str, out_dir: Path = HERE) -> None:
    plt.rcParams.update({"font.family": "sans-serif", "font.size": 9, "axes.edgecolor": MUTED,
                         "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED})
    # (a) primary result: rotation-null distributions per variable
    if ("v120", "merged") in results:
        r2 = results[("v120", "merged")]["r2"]
        fig, axes = plt.subplots(2, 4, figsize=(11.5, 5.4))
        for ax, v in zip(axes.flat, YVARS):
            x = r2[v]["null"][np.isfinite(r2[v]["null"])]
            if len(x):
                ax.hist(x, bins=30, color=NULL_FILL, edgecolor="white", linewidth=0.5, label="rotation null")
            if np.isfinite(r2[v]["obs"]):
                ax.axvline(r2[v]["obs"], color=SERIES[0], linewidth=2, label="observed")
            ax.set_title(f"{v}\nn_null {len(x)}, pctile {fmt(r2[v]['pct'], 1)}", color=INK, fontsize=9)
            ax.grid(axis="y", color=GRID, linewidth=0.5)
            ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
            ax.spines[["top", "right"]].set_visible(False)
        axes.flat[-1].axis("off")
        h, lab = axes.flat[0].get_legend_handles_labels()
        axes.flat[-1].legend(h, lab, loc="center", frameon=False)
        fig.suptitle("Primary: odisha_v120_handcrafted stands_merged — restricted R² vs rotation null", color=INK, fontsize=10)
        fig.supxlabel("R² (stands with ≥ 2 plots)", color=INK2)
        fig.supylabel("realisations", color=INK2)
        fig.tight_layout()
        fig.savefig(out_dir / f"odisha_phase2_5_primary_r2_null{suffix}.png", dpi=150)
        plt.close(fig)
    # (b) excess over own rotation null, merged layer, arms side by side
    arms = [a for a in ARMS if (a, "merged") in results]
    if arms:
        fig, ax = plt.subplots(figsize=(7.5, 5.0))
        yy = np.arange(len(YVARS))
        for k, a in enumerate(arms):
            r2 = results[(a, "merged")]["r2"]
            ex = [r2[v]["excess"] for v in YVARS]
            lo = [r2[v]["p5"] - r2[v]["med"] for v in YVARS]
            hi = [r2[v]["p95"] - r2[v]["med"] for v in YVARS]
            off = (k - (len(arms) - 1) / 2) * 0.26
            ax.hlines(yy + off, lo, hi, color=SERIES[k], alpha=0.35, linewidth=5)
            ax.plot(ex, yy + off, "o", color=SERIES[k], markersize=8, markeredgecolor="white",
                    markeredgewidth=2, label=f"{a} (dot: excess; bar: own null p5–p95)")
        ax.axvline(0, color=MUTED, linewidth=1)
        ax.set_yticks(yy, YVARS)
        ax.invert_yaxis()
        ax.set_xlabel("restricted R² minus own rotation-null median", color=INK2)
        ax.grid(axis="x", color=GRID, linewidth=0.5)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=len(arms))
        ax.set_title("stands_merged: excess over each arm's rotation null", color=INK, fontsize=10)
        fig.tight_layout()
        fig.savefig(out_dir / f"odisha_phase2_5_arms_excess{suffix}.png", dpi=150)
        plt.close(fig)
    # (c) 6.2 primary: per band observed diff vs null p5-p95
    if ("v120", "merged") in results:
        bands = results[("v120", "merged")]["bands"]
        fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
        for ax, dname in zip(axes, ["Bray-Curtis", "|dLorey| m"]):
            cells = bands[dname]
            xs = np.arange(len(BANDS))
            for x_, (lo, hi) in zip(xs, BANDS):
                c = cells[(lo, hi)]
                if np.isfinite(c["p5"]):
                    ax.vlines(x_, c["p5"], c["p95"], color=NULL_FILL, linewidth=10,
                              label="rotation null p5–p95" if x_ == 0 else None)
                if np.isfinite(c["obs"]):
                    if c["unin"]:
                        ax.plot(x_, c["obs"], "o", markerfacecolor="white", markeredgecolor=SERIES[0],
                                markeredgewidth=2, markersize=8, label="observed, uninformative (n≤3)")
                    else:
                        ax.plot(x_, c["obs"], "o", color=SERIES[0], markeredgecolor="white", markeredgewidth=2,
                                markersize=9, label="observed" if x_ == 0 or not any(
                                    not cells[b]["unin"] for b in BANDS[:x_]) else None)
                ax.annotate(f"same {c['ns']} / diff {c['nd']}", (x_, 0), xytext=(0, -30), textcoords="offset points",
                            xycoords=("data", "axes fraction"), ha="center", fontsize=7, color=INK2,
                            annotation_clip=False)
            ax.axhline(0, color=MUTED, linewidth=1)
            ax.set_xticks(xs, [f"{lo}–{hi} m" for lo, hi in BANDS])
            ax.set_title(f"{dname}", color=INK, fontsize=10)
            ax.set_ylabel("mean(different) − mean(same)", color=INK2)
            ax.grid(axis="y", color=GRID, linewidth=0.5)
            ax.spines[["top", "right"]].set_visible(False)
        h, lab = [], []
        for ax in axes:
            for hh, ll in zip(*ax.get_legend_handles_labels()):
                if ll not in lab:
                    h.append(hh)
                    lab.append(ll)
        fig.legend(h, lab, loc="lower center", ncol=3, frameon=False, fontsize=8)
        fig.suptitle("Primary 6.2: v120 stands_merged, all within-part pairs — positive = stands group alike plots",
                     color=INK, fontsize=10)
        fig.tight_layout(rect=(0, 0.1, 1, 1))
        fig.savefig(out_dir / f"odisha_phase2_5_pairwise_bands{suffix}.png", dpi=150)
        plt.close(fig)


# ---------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["pilot", "districts"], default="pilot")
    ap.add_argument("--rotations", type=int, default=1999)
    add_path_args(ap)
    args = ap.parse_args()
    spec = apply_path_args(args)
    suffix = spec["suffix"]
    out_dir = spec["out_dir"]
    t_start = time.time()

    df, plots, parts = load(spec)
    C = Ctx()
    C.plots, C.parts = plots, parts
    P = len(plots)
    rule(f"DATA (set: {spec['name']})")
    say(f"  plots in the set's AOIs: {P} over {len(parts)} parts "
        f"({sum(1 for q in range(len(parts)) if (plots.aoi_part == q).any())} holding plots); all plots in the field table: {len(df)}")
    say("  parts: " + "; ".join(f"{p['name']} {int((plots.aoi_part == q).sum())} plots (EPSG {p['epsg']})"
                                for q, p in enumerate(parts)))

    iu, ju = np.triu_indices(P, 1)
    lon, lat = plots.lon6.to_numpy(float), plots.lat6.to_numpy(float)
    _, _, d_geo = GEOD.inv(lon[iu], lat[iu], lon[ju], lat[ju])
    C.iu, C.ju, C.d_geo = iu, ju, np.asarray(d_geo)
    pa = plots.aoi_part.to_numpy()
    C.same_part = pa[iu] == pa[ju]
    dd = plots.district_set.to_numpy()
    C.same_district = dd[iu] == dd[ju]
    rel_all = relative_ba(df)
    rel = rel_all.loc[plots.plot_key].to_numpy()
    C.d_bc = bray_curtis(rel)[iu, ju]
    # first run's joined table (pilot only): its species keys and raw cluster ids, used only to attribute
    # changed values in the corrections section (R15 vs R18, R1)
    C.d_bc_first, C.r1_changed, C.first_keys = None, None, {}
    if spec["name"] == "pilot":
        try:
            txt = subprocess.run(["git", "show", f"{FIRST_RUN}:odisha_script/phase2_plots_joined.csv"], cwd=REPO,
                                 capture_output=True, text=True, check=True).stdout
            old_j = pd.read_csv(StringIO(txt))
            rel_first = relative_ba(old_j).loc[plots.plot_key].to_numpy()
            C.d_bc_first = bray_curtis(rel_first)[iu, ju]
            oj = old_j.set_index("plot_key").loc[plots.plot_key]
            C.r1_changed = {a: bool(np.any(oj[f"{a}_merged_cluster"].dropna().to_numpy(float) % 1 != 0))
                            for a in ARMS if f"{a}_merged_cluster" in oj.columns}
        except Exception as e:  # noqa: BLE001
            say(f"  (first run's joined table not readable from git: {e})")
    lor = plots.loreys_h_m.to_numpy(float)
    C.d_lo = np.abs(lor[iu] - lor[ju])
    say(f"  pairs: {len(iu)} total, {int(C.same_part.sum())} within an AOI part; "
        f"within-part pairs by band: {[int(((C.d_geo >= a) & (C.d_geo < b) & C.same_part).sum()) for a, b in BANDS]}; "
        f"pairs > 2 km (same district): {int(((C.d_geo > DISTANT_M) & C.same_district).sum())}; d_geo geodesic (WGS84)")

    Z = linkage(squareform(bray_curtis(rel_all.to_numpy()), checks=False), method="average")
    types_all = pd.Series(fcluster(Z, N_TYPES, criterion="maxclust"), index=rel_all.index)
    C.ftype = types_all.loc[plots.plot_key].to_numpy()
    C.sal_rule = (plots.sal_ba_frac.to_numpy() > 0.5).astype(int)
    say(f"  field types (UPGMA on Bray-Curtis, all {len(rel_all)} plots, k={N_TYPES}): sizes "
        f"{types_all.value_counts().sort_index().to_dict()}; in this set {pd.Series(C.ftype).value_counts().sort_index().to_dict()}")
    say("  noise-SNIC null: EXCLUDED by recorded decision (PHASE2_PREDICTIONS.md, Null models): it failed its size check "
        "before any statistic existed (odisha_phase2_4_results.txt). The rotation null is the only null.")

    dgeo_prediction(C)

    results = {}
    for arm in ARMS:
        if f"{arm}_merged_id" not in plots.columns:
            say("")
            say(f"  NOTE: arm {arm} skipped — no vector files for it in this set (no {arm}_* columns in {spec['joined'].name})")
            continue
        for short in LAYERS:
            po = Partition(spec, arm, short, plots, parts)
            if not po.districts:
                say(f"  NOTE: {arm} / {LAYERS[short][0]} skipped — vector files missing")
                continue
            results[(arm, short)] = analyse_partition(C, po, args.rotations, arm == "v120" and short == "merged")

    arms_section(results)
    say("")
    say(f"  total runtime {time.time() - t_start:.0f} s")

    header = corrections_block(spec, args.rotations, C)
    pd.DataFrame(_rows).to_csv(out_dir / f"odisha_phase2_5_summary{suffix}.csv", index=False)
    (out_dir / f"odisha_phase2_5_results{suffix}.txt").write_text("\n".join(header + _lines) + "\n")
    print("\n".join(header))
    figures(results, suffix, out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
