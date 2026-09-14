"""
Phase 2, step 5 — the statistics (brief Steps 6 and 7).

FULLY OFFLINE. Reads phase2_plots_joined.csv, phase2_vectors/, phase2_nulls/.
Run only after PHASE2_PREDICTIONS.md is committed; that ordering is the point of it.

WHAT IS COMPUTED, AND FOR WHICH PARTITIONS
------------------------------------------
Primary result first: stands_merged from odisha_v120_handcrafted. The other arms and layers are
secondary and reported after it.

6.1  R²_P(Y) = 1 - SS_within / SS_total, stand as the grouping factor, over
     loreys_h_m, loreys_h_tree_m, crown_cover_pct, sal_ba_frac, n_species, dbh_mean_cm, h_top5_m.
     Two forms, always labelled: ALL plots (singleton stands contribute zero within-stand
     variance, so this is inflated), and RESTRICTED to stands holding >= 2 plots with a value
     for Y (the honest one). n_stands and n_plots beside every value.

6.2  Pairwise boundary test over plot pairs inside the same AOI part.
     d_field = Bray-Curtis on RELATIVE species basal area (composition) and |delta Lorey's|
     (structure, all-habit), reported separately.
       stratified: bands 0-100, 100-200, 200-400, 400-800 m; mean d_field for same-stand vs
                   different-stand pairs, n per cell, within-band label-permutation p, and
                   diff = mean(different) - mean(same) (positive = stands group alike plots).
       regression: d_field ~ d_geo + same_stand over pairs < 800 m; beta_same (negative =
                   stand effect). OLS standard errors are NOT reported: pairs share plots.
     Both for all pairs and for pairs where both plots are > 30 m from a stand boundary.

6.3  Label agreement (typology, not delineation). Field forest type = UPGMA on Bray-Curtis of
     relative species basal area over all 274 plots, cut at 6 groups; secondary: Sal-dominant
     if sal_ba_frac > 0.5. Against the merged stand's cluster_id: ARI, NMI, Cramér's V, and the
     contingency table. Distant-pair form: pairs > 2 km apart, same-label vs different-label
     mean d_field.

NULLS (Step 7), as fixed in PHASE2_PREDICTIONS.md
-------------------------------------------------
  noise     odisha_phase2_4_noise_null.py realisations: noise SNIC + the same merge. For
            stands_merged (per arm) and stands_snic (the noise superpixels). The OBSERVED value
            compared against it is computed from the same raster sampler
            (noise_null_observed.csv); the vector-join value is the headline and the two are
            checked against each other.
  rotation  rigid rotation + translation of the real vector stand map, per AOI part, 999
            realisations, offline here. For every arm x layer, and the only null for 6.3 and for
            stands_dissolved.

Percentile = mid-rank share of null values below the observed value. Excess = observed - null
median. Raw R² is never compared across partitions; excess over each partition's own null is.

Run:  python odisha_phase2_5_stats.py [--rotations 999]
Writes: odisha_phase2_5_results.txt, odisha_phase2_5_summary.csv, odisha_phase2_5_*.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import shapely  # noqa: E402
from scipy.cluster.hierarchy import fcluster, linkage  # noqa: E402
from scipy.spatial.distance import squareform  # noqa: E402
from scipy.stats import chi2_contingency  # noqa: E402
from shapely import STRtree  # noqa: E402
from shapely.geometry import shape  # noqa: E402
from shapely.ops import transform  # noqa: E402
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from odisha_phase2_0_aois import utm_transformers  # noqa: E402
from odisha_phase2_3_join import ARMS, LAYERS, load_layer  # noqa: E402

JOINED = HERE / "phase2_plots_joined.csv"
VECTOR_DIR = HERE / "phase2_vectors"
NULL_DIR = HERE / "phase2_nulls"
AOI = REPO / "aois" / "odisha_dhenkanal_sites.geojson"
RESULTS = HERE / "odisha_phase2_5_results.txt"
SUMMARY = HERE / "odisha_phase2_5_summary.csv"

YVARS = ["loreys_h_m", "loreys_h_tree_m", "crown_cover_pct", "sal_ba_frac",
         "n_species", "dbh_mean_cm", "h_top5_m"]
BANDS = [(0, 100), (100, 200), (200, 400), (400, 800)]
BOUNDARY_M = 30.0
DISTANT_M = 2000.0
N_TYPES = 6
N_PERM = 9999
RNG = np.random.default_rng(20260914)

# reference palette (dataviz skill): ink, muted, series slots
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
NULL_FILL = "#c3c2b7"

_lines: list[str] = []
_rows: list[dict] = []


def say(s: str = "") -> None:
    print(s)
    _lines.append(s)


def rule(title: str) -> None:
    say("")
    say("=" * 100)
    say(title)
    say("=" * 100)


def record(**kw) -> None:
    _rows.append(kw)


# ---------------------------------------------------------------------- core statistics
def r2_partition(y: np.ndarray, g: np.ndarray, restrict: bool) -> tuple[float, int, int]:
    m = ~np.isnan(y) & ~pd.isna(g)
    y, g = y[m], np.asarray(g)[m]
    if restrict and len(g):
        vals, counts = np.unique(g, return_counts=True)
        keep = np.isin(g, vals[counts >= 2])
        y, g = y[keep], g[keep]
    n = len(y)
    k = len(np.unique(g)) if n else 0
    if n < 2 or k < 1:
        return np.nan, k, n
    sst = ((y - y.mean()) ** 2).sum()
    if sst == 0:
        return np.nan, k, n
    ssw = sum(((y[g == v] - y[g == v].mean()) ** 2).sum() for v in np.unique(g))
    return 1.0 - ssw / sst, k, n


def pair_stats(same: np.ndarray, d_geo: np.ndarray, d_field: np.ndarray, ok: np.ndarray,
               permute: bool = False) -> dict:
    """Stratified diffs and beta_same over the pairs selected by `ok`."""
    out = {}
    for lo, hi in BANDS:
        sel = ok & (d_geo >= lo) & (d_geo < hi) & ~np.isnan(d_field)
        s, f = same[sel], d_field[sel]
        ns, nd = int(s.sum()), int((~s).sum())
        diff = f[~s].mean() - f[s].mean() if ns and nd else np.nan
        out[f"n_same_{lo}_{hi}"], out[f"n_diff_{lo}_{hi}"] = ns, nd
        out[f"mean_same_{lo}_{hi}"] = f[s].mean() if ns else np.nan
        out[f"mean_diff_{lo}_{hi}"] = f[~s].mean() if nd else np.nan
        out[f"diff_{lo}_{hi}"] = diff
        if permute:
            if ns and nd:
                perm = np.empty(N_PERM)
                for p in range(N_PERM):
                    sh = RNG.permutation(s)
                    perm[p] = f[~sh].mean() - f[sh].mean()
                out[f"perm_p_{lo}_{hi}"] = (1 + (perm >= diff).sum()) / (N_PERM + 1)
            else:
                out[f"perm_p_{lo}_{hi}"] = np.nan
    sel = ok & (d_geo < BANDS[-1][1]) & ~np.isnan(d_field)
    if sel.sum() > 3 and same[sel].any() and (~same[sel]).any():
        X = np.column_stack([np.ones(sel.sum()), d_geo[sel] / 100.0, same[sel].astype(float)])
        beta = np.linalg.lstsq(X, d_field[sel], rcond=None)[0]
        out["beta_dgeo_per100m"], out["beta_same"] = beta[1], beta[2]
    else:
        out["beta_dgeo_per100m"], out["beta_same"] = np.nan, np.nan
    out["n_pairs_reg"], out["n_same_reg"] = int(sel.sum()), int(same[sel].sum())
    return out


def cramers_v(a, b) -> tuple[float, pd.DataFrame]:
    tab = pd.crosstab(pd.Series(a, name="field_type"), pd.Series(b, name="cluster_id"))
    if min(tab.shape) < 2:
        return np.nan, tab
    chi2 = chi2_contingency(tab.values, correction=False)[0]
    return float(np.sqrt(chi2 / (tab.values.sum() * (min(tab.shape) - 1)))), tab


def label_stats(field_type, cluster, same_part_or_any_i, j, d_geo, d_bc, d_lo) -> dict:
    m = ~pd.isna(cluster)
    ft, cl = np.asarray(field_type)[m], np.asarray(cluster)[m].astype(int)
    out = {"ari": adjusted_rand_score(ft, cl) if len(ft) > 1 else np.nan,
           "nmi": normalized_mutual_info_score(ft, cl) if len(ft) > 1 else np.nan}
    out["cramers_v"], _ = cramers_v(ft, cl)
    cl_full = np.asarray(cluster, dtype=float)
    i = same_part_or_any_i
    far = (d_geo > DISTANT_M) & ~np.isnan(cl_full[i]) & ~np.isnan(cl_full[j])
    same_lab = cl_full[i] == cl_full[j]
    for name, d in (("bc", d_bc), ("lorey", d_lo)):
        s = far & same_lab & ~np.isnan(d)
        dd = far & ~same_lab & ~np.isnan(d)
        out[f"distant_n_same_{name}"], out[f"distant_n_diff_{name}"] = int(s.sum()), int(dd.sum())
        out[f"distant_diff_{name}"] = d[dd].mean() - d[s].mean() if s.any() and dd.any() else np.nan
    return out


def percentile(obs: float, null: np.ndarray) -> float:
    null = null[~np.isnan(null)]
    if np.isnan(obs) or not len(null):
        return np.nan
    return 100.0 * ((null < obs).sum() + 0.5 * (null == obs).sum()) / len(null)


def fmt(v, nd=3) -> str:
    return "  n/a" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.{nd}f}"


# ---------------------------------------------------------------------- data
def load() -> tuple[pd.DataFrame, pd.DataFrame, list, dict]:
    df = pd.read_csv(JOINED)
    aoi = shape(json.loads(AOI.read_text())["features"][0]["geometry"])
    parts = list(aoi.geoms)
    pts = shapely.points(df.lon6.to_numpy(float), df.lat6.to_numpy(float))
    part_idx = np.full(len(df), -1)
    for k, p in enumerate(parts):
        part_idx[shapely.covers(p, pts)] = k
    df["aoi_part"] = part_idx
    pilot = df[df.aoi_part >= 0].sort_values("plot_key").reset_index(drop=True)
    c = aoi.centroid
    _, fwd, _ = utm_transformers(c.x, c.y)
    x, y = fwd(pilot.lon6.to_numpy(float), pilot.lat6.to_numpy(float))
    pilot["x"], pilot["y"] = x, y
    return df, pilot, parts, {"fwd": fwd}


def relative_ba(frame: pd.DataFrame) -> pd.DataFrame:
    rows = [json.loads(s) for s in frame.sp_ba_json]
    m = pd.DataFrame(rows, index=frame.plot_key).fillna(0.0)
    return m.div(m.sum(axis=1), axis=0)


def bray_curtis(a: np.ndarray) -> np.ndarray:
    num = np.abs(a[:, None, :] - a[None, :, :]).sum(-1)
    den = (a[:, None, :] + a[None, :, :]).sum(-1)
    return num / den


# ---------------------------------------------------------------------- rotation null
def rotation_null(pilot: pd.DataFrame, parts_utm: list, layer: pd.DataFrame, observed_ok: np.ndarray,
                  n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """(ids, clusters, bdist) arrays of shape (n, n_plots) under rigid moves of the plots."""
    geoms = np.array(list(layer.geom))
    tree = STRtree(geoms)
    sid = layer.sid.to_numpy()
    cid = layer.cluster_id.astype(float).to_numpy()
    P = len(pilot)
    ids, cls, bd = (np.full((n, P), np.nan) for _ in range(3))
    xy = pilot[["x", "y"]].to_numpy()
    attempts = {}
    for k, part in enumerate(parts_utm):
        idx = np.where(pilot.aoi_part.to_numpy() == k)[0]
        if not len(idx):
            continue
        c0 = xy[idx].mean(0)
        minx, miny, maxx, maxy = part.bounds
        tries = 0
        for r in range(n):
            while True:
                tries += 1
                if tries > 200_000 * n // 999 + 50_000:
                    raise RuntimeError(f"rotation null: part {k} acceptance too low")
                th = RNG.uniform(0, 2 * np.pi)
                c1 = np.array([RNG.uniform(minx, maxx), RNG.uniform(miny, maxy)])
                rot = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
                new = (xy[idx] - c0) @ rot.T + c1
                pts = shapely.points(new[:, 0], new[:, 1])
                if not shapely.covers(part, pts).all():
                    continue
                q_in, q_tree = tree.query(pts, predicate="covered_by")
                hit = np.full(len(idx), -1)
                hit[q_in] = q_tree
                if not (hit[observed_ok[idx]] >= 0).all():
                    continue
                break
            ids[r, idx] = np.where(hit >= 0, sid[np.maximum(hit, 0)], np.nan)
            cls[r, idx] = np.where(hit >= 0, cid[np.maximum(hit, 0)], np.nan)
            q_in, q_tree = tree.query(pts, predicate="dwithin", distance=600.0)
            dist = shapely.distance(pts[q_in], geoms[q_tree])
            other = sid[q_tree] != ids[r, idx][q_in]
            b = np.full(len(idx), 600.0)
            for a, d_, o in zip(q_in, dist, other):
                if o and d_ < b[a]:
                    b[a] = d_
            bd[r, idx] = np.where(hit >= 0, b, np.nan)
        attempts[k] = tries / n
    return ids, cls, bd, attempts


# ---------------------------------------------------------------------- reporting helpers
def report_r2(label: str, obs_vec: dict, null_by_var: dict[str, np.ndarray], null_name: str,
              obs_null_path: dict | None = None) -> None:
    say(f"  {label}")
    say(f"    {'variable':<16} {'R2 all':>7} {'(k, n)':>10} {'R2 restr':>9} {'(k, n)':>9} "
        f"{'null med':>9} {'p5':>6} {'p95':>6} {'excess':>7} {'pctile':>7}")
    for v in YVARS:
        ra, ka, na, rr, kr, nr = obs_vec[v]
        base = obs_null_path[v] if obs_null_path is not None else rr
        nul = null_by_var[v]
        med = np.nanmedian(nul) if np.isfinite(nul).any() else np.nan
        p5, p95 = (np.nanpercentile(nul, [5, 95]) if np.isfinite(nul).any() else (np.nan, np.nan))
        pc = percentile(base, nul)
        say(f"    {v:<16} {fmt(ra):>7} {f'({ka},{na})':>10} {fmt(rr):>9} {f'({kr},{nr})':>9} "
            f"{fmt(med):>9} {fmt(p5, 2):>6} {fmt(p95, 2):>6} {fmt(base - med if np.isfinite(base) else np.nan):>7} "
            f"{fmt(pc, 1):>7}")
        record(section="6.1", null=null_name, partition=label, variable=v, r2_all=ra, k_all=ka, n_all=na,
               r2_restricted=rr, k_restricted=kr, n_restricted=nr, observed_vs_null=base,
               null_median=med, null_p5=p5, null_p95=p95,
               excess=base - med if np.isfinite(base) else np.nan, percentile=pc)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rotations", type=int, default=999)
    args = ap.parse_args()

    df, pilot, parts, tf = load()
    fwd = tf["fwd"]
    parts_utm = [transform(fwd, p) for p in parts]
    P = len(pilot)
    rule("DATA")
    say(f"  plots in the pilot AOI: {P} over {len(parts)} parts; all plots in the field table: {len(df)}")

    # pairs within the same AOI part (6.1/6.2) and all pairs (6.3 distant)
    iu, ju = np.triu_indices(P, 1)
    d_geo = np.hypot(pilot.x.to_numpy()[iu] - pilot.x.to_numpy()[ju], pilot.y.to_numpy()[iu] - pilot.y.to_numpy()[ju])
    same_part = pilot.aoi_part.to_numpy()[iu] == pilot.aoi_part.to_numpy()[ju]
    rel_all = relative_ba(df)
    rel = rel_all.loc[pilot.plot_key].to_numpy()
    BC = bray_curtis(rel)
    d_bc = BC[iu, ju]
    lor = pilot.loreys_h_m.to_numpy(float)
    d_lo = np.abs(lor[iu] - lor[ju])
    say(f"  pairs: {len(iu)} total, {int(same_part.sum())} within an AOI part; "
        f"within-part pairs by band: {[int(((d_geo >= a) & (d_geo < b) & same_part).sum()) for a, b in BANDS]}; "
        f"pairs > 2 km: {int((d_geo > DISTANT_M).sum())}")

    # field typology over all 274 plots
    Z = linkage(squareform(bray_curtis(rel_all.to_numpy()), checks=False), method="average")
    types_all = pd.Series(fcluster(Z, N_TYPES, criterion="maxclust"), index=rel_all.index)
    ftype = types_all.loc[pilot.plot_key].to_numpy()
    sal_rule = (pilot.sal_ba_frac.to_numpy() > 0.5).astype(int)
    say(f"  field types (UPGMA on Bray-Curtis, all 274 plots, k={N_TYPES}): sizes "
        f"{types_all.value_counts().sort_index().to_dict()}; in pilot {pd.Series(ftype).value_counts().sort_index().to_dict()}")

    # noise null inputs
    noise_ok = (NULL_DIR / "noise_null_plots.csv").exists() and (NULL_DIR / "noise_null_observed.csv").exists()
    if noise_ok:
        npl = pd.read_csv(NULL_DIR / "noise_null_plots.csv")
        nsum = pd.read_csv(NULL_DIR / "noise_null_summary.csv")
        nobs = pd.read_csv(NULL_DIR / "noise_null_observed.csv").set_index("plot_key").loc[pilot.plot_key].reset_index()
        reals = sorted(npl.realisation.unique())
        say(f"  noise null: {len(reals)} realisations")
    else:
        say("  noise null: NOT AVAILABLE (odisha_phase2_4 has not produced output)")

    summaries_for_fig = {}
    arms_present = [a for a in ARMS if f"{a}_merged_id" in pilot.columns]

    for arm in arms_present:
        run = json.loads((VECTOR_DIR / f"{ARMS[arm]}_run.json").read_text())
        for short, (layer_name, id_field) in LAYERS.items():
            label = f"{arm} / {layer_name}"
            primary = arm == "v120" and short == "merged"
            rule(("PRIMARY RESULT — " if primary else "SECONDARY — ") + label)
            ids = pilot[f"{arm}_{short}_id"].to_numpy(float)
            bdv = pilot[f"{arm}_{short}_bdist_m"].to_numpy(float)
            layer = load_layer(VECTOR_DIR / f"{ARMS[arm]}_{layer_name}.geojson", id_field, fwd)
            areas = layer.groupby("sid").area_ha.sum().astype(float)
            say(f"  partition: {areas.size} stands, area ha p10 {areas.quantile(.1):.2f} / median "
                f"{areas.median():.2f} / p90 {areas.quantile(.9):.2f}; plots assigned {int((~np.isnan(ids)).sum())} of {P}; "
                f"multi-plot stands {int((pd.Series(ids).value_counts() >= 2).sum())}")

            # ---------------- 6.1 observed (vector join)
            obs_vec = {}
            for v in YVARS:
                y = pilot[v].to_numpy(float)
                obs_vec[v] = (*r2_partition(y, ids, False), *r2_partition(y, ids, True))

            # ---------------- rotation null
            observed_ok = ~np.isnan(ids)
            rid, rcl, rbd, att = rotation_null(pilot, parts_utm, layer, observed_ok, args.rotations)
            say(f"  rotation null: {args.rotations} realisations; mean draws per accepted realisation by part "
                f"{ {k: round(v, 1) for k, v in att.items()} }")
            rot_r2 = {v: np.array([r2_partition(pilot[v].to_numpy(float), rid[r], True)[0]
                                   for r in range(args.rotations)]) for v in YVARS}
            report_r2(f"6.1 {label} vs ROTATION null (observed = vector join, restricted R2)", obs_vec, rot_r2, "rotation")

            # ---------------- 6.1 noise null (merged + snic only)
            if noise_ok and short in ("merged", "snic"):
                col = f"stand_{arm}" if short == "merged" else "snic"
                ocol = f"stand_{arm}" if short == "merged" else f"snic_{arm}"
                obs_raster = nobs[ocol].to_numpy(float)
                # agreement of the two assignments, as co-membership (raw ids differ between the vector renumbering and raster labels for snic)
                co_v = ids[iu] == ids[ju]
                co_r = obs_raster[iu] == obs_raster[ju]
                say(f"  raster sampler vs vector join: pair co-membership agrees on {int((co_v == co_r).sum())} of {len(iu)} pairs")
                obs_np = {v: r2_partition(pilot[v].to_numpy(float), obs_raster, True)[0] for v in YVARS}
                nr = {v: [] for v in YVARS}
                for r in reals:
                    part = npl[npl.realisation == r].set_index("plot_key").loc[pilot.plot_key]
                    g = part[col].to_numpy(float)
                    for v in YVARS:
                        nr[v].append(r2_partition(pilot[v].to_numpy(float), g, True)[0])
                nr = {v: np.array(x) for v, x in nr.items()}
                if short == "merged":
                    ns = nsum[nsum.arm == arm]
                    md = run["merge_diagnostics"]
                    say(f"  size match: observed {md['n_stands']} stands vs noise null median {ns.n_stands.median():.0f} "
                        f"(p5 {ns.n_stands.quantile(.05):.0f}, p95 {ns.n_stands.quantile(.95):.0f}); observed median stand "
                        f"{areas.median():.2f} ha vs null {ns.area_median.median():.2f} ha")
                    off_n = abs(ns.n_stands.median() - md["n_stands"]) / md["n_stands"]
                    off_a = abs(ns.area_median.median() - areas.median()) / areas.median()
                    if off_n > 0.25 or off_a > 0.5:
                        say("  !! SIZE MATCH FAILED by the predictions' criterion (count > 25% or median area > 50% off): "
                            "excess over the noise null is not interpretable; read the rotation null.")
                report_r2(f"6.1 {label} vs NOISE null (observed = raster sampler, restricted R2)", obs_vec, nr, "noise", obs_np)
                summaries_for_fig[(arm, short)] = (obs_np, nr)

            # ---------------- 6.2 pairwise
            say("")
            say("  6.2 pairwise boundary test (pairs within an AOI part)")
            same_v = (ids[iu] == ids[ju]) & ~np.isnan(ids[iu]) & ~np.isnan(ids[ju])
            assigned = ~np.isnan(ids[iu]) & ~np.isnan(ids[ju]) & same_part
            inner_v = assigned & (bdv[iu] > BOUNDARY_M) & (bdv[ju] > BOUNDARY_M)
            for dname, dvals in (("Bray-Curtis", d_bc), ("|dLorey| m", d_lo)):
                for sname, ok in (("all pairs", assigned), (f"both > {BOUNDARY_M:.0f} m from boundary", inner_v)):
                    o = pair_stats(same_v, d_geo, dvals, ok, permute=True)
                    rot = [pair_stats((rid[r][iu] == rid[r][ju]), d_geo, dvals,
                                      ok if "all" in sname else (assigned & (rbd[r][iu] > BOUNDARY_M) & (rbd[r][ju] > BOUNDARY_M)))
                           for r in range(args.rotations)]
                    say(f"    {dname}, {sname}:")
                    say(f"      {'band m':<9} {'n same':>6} {'n diff':>6} {'mean same':>9} {'mean diff':>9} "
                        f"{'diff':>7} {'perm p':>7} {'rot pctile':>10}")
                    for lo, hi in BANDS:
                        key = f"diff_{lo}_{hi}"
                        pc = percentile(o[key], np.array([x[key] for x in rot]))
                        say(f"      {f'{lo}-{hi}':<9} {o[f'n_same_{lo}_{hi}']:>6} {o[f'n_diff_{lo}_{hi}']:>6} "
                            f"{fmt(o[f'mean_same_{lo}_{hi}']):>9} {fmt(o[f'mean_diff_{lo}_{hi}']):>9} {fmt(o[key]):>7} "
                            f"{fmt(o[f'perm_p_{lo}_{hi}']):>7} {fmt(pc, 1):>10}")
                        record(section="6.2", null="rotation", partition=label, measure=dname, subset=sname,
                               band=f"{lo}-{hi}", n_same=o[f"n_same_{lo}_{hi}"], n_diff=o[f"n_diff_{lo}_{hi}"],
                               diff=o[key], perm_p=o[f"perm_p_{lo}_{hi}"], percentile=pc)
                    bn = np.array([x["beta_same"] for x in rot])
                    pc = percentile(-o["beta_same"], -bn)
                    say(f"      regression d_field ~ d_geo + same_stand (pairs < 800 m, n={o['n_pairs_reg']}, "
                        f"same={o['n_same_reg']}): beta_same {fmt(o['beta_same'], 4)}, beta per 100 m "
                        f"{fmt(o['beta_dgeo_per100m'], 4)}; rotation null median {fmt(np.nanmedian(bn) if np.isfinite(bn).any() else np.nan, 4)}; "
                        f"stand-effect percentile {fmt(pc, 1)} (high = more similar than null)")
                    record(section="6.2", null="rotation", partition=label, measure=dname, subset=sname, band="regression",
                           beta_same=o["beta_same"], n_pairs=o["n_pairs_reg"], n_same=o["n_same_reg"], percentile=pc)
                    if noise_ok and short in ("merged", "snic"):
                        col = f"stand_{arm}" if short == "merged" else "snic"
                        ocol = f"stand_{arm}" if short == "merged" else f"snic_{arm}"
                        g0, b0 = nobs[ocol].to_numpy(float), nobs[f"bd_{ocol}"].to_numpy(float)
                        ok0 = ok if "all" in sname else (assigned & (b0[iu] > BOUNDARY_M) & (b0[ju] > BOUNDARY_M))
                        o0 = pair_stats(g0[iu] == g0[ju], d_geo, dvals, ok0)
                        nn = []
                        for r in reals:
                            part = npl[npl.realisation == r].set_index("plot_key").loc[pilot.plot_key]
                            g, b = part[col].to_numpy(float), part[f"bd_{col}"].to_numpy(float)
                            okr = ok if "all" in sname else (assigned & (b[iu] > BOUNDARY_M) & (b[ju] > BOUNDARY_M))
                            nn.append(pair_stats(g[iu] == g[ju], d_geo, dvals, okr))
                        cells = " ".join(f"{lo}-{hi}:{fmt(percentile(o0[f'diff_{lo}_{hi}'], np.array([x[f'diff_{lo}_{hi}'] for x in nn])), 1)}"
                                         for lo, hi in BANDS)
                        bnn = np.array([x["beta_same"] for x in nn])
                        pcn = percentile(-o0["beta_same"], -bnn)
                        say(f"      NOISE null (raster sampler): band diff percentiles {cells}; "
                            f"beta_same {fmt(o0['beta_same'], 4)} percentile {fmt(pcn, 1)}")
                        record(section="6.2", null="noise", partition=label, measure=dname, subset=sname,
                               band="regression", beta_same=o0["beta_same"], percentile=pcn)

            # ---------------- 6.3 labels (merged layer's cluster_id only)
            if short == "merged":
                say("")
                say("  6.3 label agreement (typology, not delineation) — merged stand cluster_id")
                clus = pilot[f"{arm}_merged_cluster"].to_numpy(float)
                for tname, tt in (("UPGMA k=6", ftype), ("Sal-dominant rule", sal_rule)):
                    o = label_stats(tt, clus, iu, ju, d_geo, d_bc, d_lo)
                    rot = [label_stats(tt, rcl[r], iu, ju, d_geo, d_bc, d_lo) for r in range(args.rotations)]
                    n_typed = int((~np.isnan(clus)).sum())
                    say(f"    field type = {tname}; typed plots n={n_typed}")
                    for key in ("ari", "nmi", "cramers_v", "distant_diff_bc", "distant_diff_lorey"):
                        nulv = np.array([x[key] for x in rot])
                        pc = percentile(o[key], nulv)
                        extra = (f" (n same {o['distant_n_same_' + key.split('_')[-1]]}, n diff {o['distant_n_diff_' + key.split('_')[-1]]})"
                                 if key.startswith("distant") else "")
                        say(f"      {key:<20} {fmt(o[key])}{extra}; rotation null median {fmt(np.nanmedian(nulv))}, "
                            f"p95 {fmt(np.nanpercentile(nulv, 95) if np.isfinite(nulv).any() else np.nan)}, percentile {fmt(pc, 1)}")
                        record(section="6.3", null="rotation", partition=label, field_type=tname, statistic=key,
                               observed=o[key], null_median=np.nanmedian(nulv), percentile=pc, n=n_typed)
                    if tname.startswith("UPGMA"):
                        _, tab = cramers_v(tt[~np.isnan(clus)], clus[~np.isnan(clus)].astype(int))
                        say("      contingency (rows field type, columns cluster_id):")
                        for line in tab.to_string().splitlines():
                            say("        " + line)

    pd.DataFrame(_rows).to_csv(SUMMARY, index=False)
    RESULTS.write_text("\n".join(_lines) + "\n")
    if summaries_for_fig:
        figures(summaries_for_fig)
    return 0


def figures(s: dict) -> None:
    plt.rcParams.update({"font.family": "sans-serif", "font.size": 9, "axes.edgecolor": MUTED,
                         "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED})
    # Figure 1: primary result, noise null distributions per variable
    if ("v120", "merged") in s:
        obs, nul = s[("v120", "merged")]
        fig, axes = plt.subplots(2, 4, figsize=(11, 5), sharey=False)
        for ax, v in zip(axes.flat, YVARS):
            x = nul[v][np.isfinite(nul[v])]
            if len(x):
                ax.hist(x, bins=25, color=NULL_FILL, edgecolor="white", linewidth=0.5, label="noise null")
            if np.isfinite(obs[v]):
                ax.axvline(obs[v], color=SERIES[0], linewidth=2, label="observed")
            ax.set_title(v, color=INK, fontsize=9)
            ax.grid(axis="y", color=GRID, linewidth=0.5)
            ax.spines[["top", "right"]].set_visible(False)
        axes.flat[-1].axis("off")
        h, lab = axes.flat[0].get_legend_handles_labels()
        axes.flat[-1].legend(h, lab, loc="center", frameon=False)
        fig.suptitle("Primary: odisha_v120_handcrafted stands_merged — restricted R² vs size-matched noise null",
                     color=INK, fontsize=10)
        fig.supxlabel("R² (stands with ≥ 2 plots)", color=INK2)
        fig.tight_layout()
        fig.savefig(HERE / "odisha_phase2_5_primary_r2_null.png", dpi=150)
        plt.close(fig)
    # Figure 2: excess over own noise null, merged layer, arms side by side
    arms = [a for a in ARMS if (a, "merged") in s]
    if arms:
        fig, ax = plt.subplots(figsize=(8, 4))
        yy = np.arange(len(YVARS))
        for k, a in enumerate(arms):
            obs, nul = s[(a, "merged")]
            ex = [obs[v] - np.nanmedian(nul[v]) if np.isfinite(obs[v]) else np.nan for v in YVARS]
            lo = [np.nanpercentile(nul[v], 5) - np.nanmedian(nul[v]) for v in YVARS]
            hi = [np.nanpercentile(nul[v], 95) - np.nanmedian(nul[v]) for v in YVARS]
            off = (k - (len(arms) - 1) / 2) * 0.22
            ax.hlines(yy + off, lo, hi, color=SERIES[k], alpha=0.35, linewidth=4)
            ax.plot(ex, yy + off, "o", color=SERIES[k], markersize=7, markeredgecolor="white",
                    markeredgewidth=2, label=f"{a} (dot: excess; bar: null p5–p95)")
        ax.axvline(0, color=MUTED, linewidth=1)
        ax.set_yticks(yy, YVARS)
        ax.invert_yaxis()
        ax.set_xlabel("restricted R² minus own noise-null median", color=INK2)
        ax.grid(axis="x", color=GRID, linewidth=0.5)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False, fontsize=8, loc="lower right")
        ax.set_title("stands_merged: excess over each arm's size-matched null", color=INK, fontsize=10)
        fig.tight_layout()
        fig.savefig(HERE / "odisha_phase2_5_arms_excess.png", dpi=150)
        plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
