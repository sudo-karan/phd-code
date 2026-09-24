"""Phase 3, step 3: is the pairwise score better than chance, and is 3 ha better than 10 ha?

Why this exists. odisha_phase3_1 prints an ARI for delineation and for labelling,
but in this design an ARI of zero is NOT the chance level. The plots sit in 20
village forests; field types cluster by village (a pair in the same village is
field-alike 43% of the time, against 29% over all pairs), and stands cluster by
village too, because a stand never crosses a village boundary. So a stand map
that knows nothing about the forest still groups plots of one village together,
and scores a positive ARI. A value is only evidence if it beats what a
meaningless map of the SAME shape, laid over the SAME villages, would score.

The chance level used here is the Phase 2 spatial rotation null
(odisha_phase2_5_stats.rotation_null, imported, not copied): within each village
the plot cloud is rotated and moved rigidly to a random position inside the
village polygon, and each moved plot takes the stand (and stand type) under it.
The plot-to-plot geometry, the field types and the real stand map are all kept;
only the registration between field and map is broken. Each observed statistic
is placed in that distribution as a percentile.

Two nulls, because labelling needs its own. The unconditional null forces every
plot that has a stand to land on a stand, which is right for delineation. But in
koraput about a fifth of the merged layer carries no stand type, so under it a
labelled plot often lands on an unlabelled polygon, and only a handful of the
1999 realisations label every labelled plot -- too few for a percentile. The
labelling null is therefore CONDITIONAL: each village's layer is limited to the
polygons that carry a type, and the labelled plots are the ones forced to land.
It asks the question labelling actually poses: given that these plots get a
type, is it the right one more often than a rotated map would give?

Statistics are the fixed scorer's, not new ones. Stands are keyed by
(district, id), because stand ids restart per district; labelling is the
plot-weighted mean of per-district ARIs (k-means is fitted per district, so
type 3 in angul is unrelated to type 3 in koraput), and far-apart pairs are
same-district pairs more than 2 km apart. The observed values are recomputed
here the scorer's way from the joined CSV and must match to machine precision,
or the script stops. The "multi-plot" delineation ARI is redefined in every
realisation (the stands holding >= 2 plots in THAT realisation), as it is in the
observed map.

Arm comparison. The 3 ha and 10 ha arms are compared on the SAME plots, so the
difference is read three ways: against the difference of the two arms'
independent rotation nulls, realisations paired by index only (does 3 ha beat
10 ha by more than their chance levels differ?). The arms' nulls use different
seeds and acceptance sets, so realisation r of one is unrelated to realisation r
of the other; a shared-rotation null would be tighter but cannot be built, since
which rotations are accepted depends on each arm's own layer. Then
by a paired village cluster bootstrap (the 20 villages resampled with
replacement, one draw applied to both arms, a village drawn twice counted as two
villages with separate stands), and by a leave-one-village-out jackknife.

What is deliberately NOT reported as a test: any plot-level permutation or
plot-level bootstrap. Plots within a village are not independent draws, so such
p-values are anti-conservative; the 20 villages are the units of independence.

Identity check. Before any null is built, the null's own assignment code is run
at the REAL plot positions and must reproduce the joined stand ids and stand
types exactly. If it does not, the null is not measuring the same thing as the
observed statistic, and the script stops.

Usage:  python odisha_script/odisha_phase3_3_significance.py [--rotations 1999] [--boot 4000] [--out-dir odisha_script/]
Input : odisha_script/phase2_plots_joined_districts.csv            (10 ha arm, v120)
        odisha_script/phase3_3ha/phase2_plots_joined_districts.csv  (3 ha arm, v120_3ha)
        odisha_script/odisha_phase3_0_field_types.csv               (field_type 0..4)
        the merged stand layers of both arms, via odisha_phase2_5_stats.Partition
Output: <out-dir>/odisha_phase3_3_results.txt
Offline; no Earth Engine. Every random stream is seeded from a fixed string.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from pyproj import Geod
from shapely import STRtree
from sklearn.metrics import adjusted_rand_score as ari

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import odisha_phase2_3_join as J  # noqa: E402
import odisha_phase2_5_stats as S  # noqa: E402

ARM_LABEL = {"v120": "10 ha", "v120_3ha": "3 ha"}
JOINED = {"v120": HERE / "phase2_plots_joined_districts.csv",
          "v120_3ha": HERE / "phase3_3ha" / "phase2_plots_joined_districts.csv"}
FIELD_TYPES = HERE / "odisha_phase3_0_field_types.csv"
LAYER = "merged"
DISTANT_M = 2000.0          # the scorer's far-apart threshold
OUT_NAME = "odisha_phase3_3_results.txt"
GEOD = Geod(ellps="WGS84")

# rotation-null seed keys: the ones the reconciled analysis used, so this file reproduces its draws
SEED_UNCOND = "{arm}/stands_merged/phase3_ari"
SEED_LABELLED = "{arm}/stands_merged/phase3_ari_labelled"
SEED_BOOT = "phase3_3/paired_village_bootstrap"

STATS = [("delin_all", "delineation ARI, all plots"),
         ("delin_multi", "delineation ARI, multi-plot stands"),
         ("prec", "same-stand pair precision"),
         ("lab_wmean", "labelling ARI, per-district wmean"),
         ("far_gap", "far-apart same-label rate, alike - differ")]
DELIN = ("delin_all", "delin_multi", "prec")     # read against the unconditional null
LABEL = ("lab_wmean", "far_gap")                 # read against the conditional (labelled-polygon) null
BOOT_STATS = ("delin_all", "delin_multi", "prec", "lab_wmean")

_lines: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    _lines.append(s)


# ---------------------------------------------------------------------- the scorer's statistics, on arrays
def multi_ari(f: np.ndarray, s: np.ndarray) -> tuple[float, int, int]:
    """ARI over plots in stands holding >= 2 of these plots; the stand set is whatever s gives."""
    v, c = np.unique(s, return_counts=True)
    m = np.isin(s, v[c >= 2])
    return (ari(f[m], s[m]) if m.sum() >= 2 else np.nan), int(m.sum()), int((c >= 2).sum())


def pair_precision(f: np.ndarray, s: np.ndarray) -> float:
    """Share of same-stand pairs that are field-alike, counted by grouping (no pair matrix)."""
    _, n_s = np.unique(s, return_counts=True)
    same = (n_s * (n_s - 1) // 2).sum()
    _, n_sf = np.unique(np.stack([s, f.astype(float)], 1), axis=0, return_counts=True)
    return float((n_sf * (n_sf - 1) // 2).sum() / same) if same else np.nan


def lab_wmean(f: np.ndarray, cl: np.ndarray, dist: np.ndarray) -> tuple[float, dict]:
    """Plot-weighted mean of per-district ARIs; a district is scored only with >= 2 plots and >= 2
    field types, exactly as the scorer does. Inputs are already limited to labelled plots."""
    per, w, out = [], [], {}
    for d in np.unique(dist):
        m = dist == d
        if m.sum() >= 2 and len(np.unique(f[m])) >= 2:
            a = ari(f[m], cl[m])
            per.append(a); w.append(int(m.sum())); out[d] = a
    return (float(np.average(per, weights=w)) if per else np.nan), out


class Plots:
    """The 267 in-AOI plots, their field types, and the far-apart pair set."""

    def __init__(self, plots: pd.DataFrame):
        self.ft = plots.field_type.to_numpy(int)
        self.dist = plots.district_set.to_numpy().astype(str)
        self.part = plots.aoi_part.to_numpy()
        self.n = len(plots)
        i, j = np.triu_indices(self.n, 1)
        lon, lat = plots.lon6.to_numpy(float), plots.lat6.to_numpy(float)
        _, _, dm = GEOD.inv(lon[i], lat[i], lon[j], lat[j])
        far = (dm > DISTANT_M) & (self.dist[i] == self.dist[j])
        self.fi, self.fj = i[far], j[far]
        self.f_alike = self.ft[self.fi] == self.ft[self.fj]

    def far_gap(self, cl: np.ndarray, L: np.ndarray) -> float:
        ok = L[self.fi] & L[self.fj]
        sl = cl[self.fi] == cl[self.fj]
        a, b = ok & self.f_alike, ok & ~self.f_alike
        return float(sl[a].mean() - sl[b].mean()) if a.any() and b.any() else np.nan

    def delin(self, sid: np.ndarray, A: np.ndarray) -> dict:
        f, s = self.ft[A], sid[A]
        return {"delin_all": ari(f, s), "delin_multi": multi_ari(f, s)[0], "prec": pair_precision(f, s)}

    def label(self, cl: np.ndarray, L: np.ndarray) -> dict:
        w, per = lab_wmean(self.ft[L], cl[L], self.dist[L])
        return {"lab_wmean": w, "far_gap": self.far_gap(cl, L), **{f"lab_{d}": v for d, v in per.items()}}


# ---------------------------------------------------------------------- data and partitions
def load_all():
    J.ARMS.clear()
    J.ARMS.update({k: J.ALL_ARMS[k] for k in ARM_LABEL})     # select the arms in place, as the join/stats expect
    spec = J.set_spec("districts")
    _, plots, parts = S.load(spec)                           # 10 ha joined CSV: plot set, AOI parts, UTM x/y
    j3 = pd.read_csv(JOINED["v120_3ha"])
    plots = plots.merge(j3[["plot_key"] + [c for c in j3.columns if c.startswith("v120_3ha_")]],
                        on="plot_key", how="left", validate="1:1")
    ft = pd.read_csv(FIELD_TYPES)[["plot_key", "field_type"]]
    plots = plots.merge(ft, on="plot_key", how="left", validate="1:1")
    if plots.field_type.isna().any():
        raise SystemExit(f"{int(plots.field_type.isna().sum())} in-AOI plot(s) have no field type")
    return spec, plots, parts


class LabelledLayers:
    """The partition as the rotation null sees it, but each village's layer limited to polygons that
    carry a stand type. rotation_null only calls part_layer, so this is all it needs; the Partition
    itself is left untouched."""

    def __init__(self, P: S.Partition):
        self.P, self._c = P, {}

    def part_layer(self, q):
        if q not in self._c:
            lay = self.P.part_layer(q)
            if lay is None:
                self._c[q] = None
            else:
                geoms, _, key, cid, gb = lay
                m = ~np.isnan(cid)
                self._c[q] = (geoms[m], STRtree(geoms[m]), key[m], cid[m], gb[m])
        return self._c[q]


def identity_check(P: S.Partition, plots: pd.DataFrame, parts: list) -> tuple[bool, bool]:
    """The null's assignment rule (covering polygons -> minimum stand key, then its type) at the real plot
    positions. Must reproduce the join, or the null and the observed statistic measure different things."""
    xy = plots[["x", "y"]].to_numpy()
    cid_ = np.full(len(plots), np.nan)
    ccl_ = np.full(len(plots), np.nan)
    for q in range(len(parts)):
        idx = np.where(plots.aoi_part.to_numpy() == q)[0]
        lay = P.part_layer(q)
        if not len(idx) or lay is None:
            continue
        geoms, tree, key, cid, _ = lay
        qi, qt = tree.query(shapely.points(xy[idx, 0], xy[idx, 1]))
        cov = shapely.intersects_xy(geoms[qt], xy[idx][qi, 0], xy[idx][qi, 1])
        qi, qt = qi[cov], qt[cov]
        o = np.lexsort((qt, key[qt], qi))
        qi, qt = qi[o], qt[o]
        first = np.unique(qi, return_index=True)[1]
        cid_[idx[qi[first]]] = key[qt[first]]
        ccl_[idx[qi[first]]] = cid[qt[first]]
    same = lambda a, b: bool(np.all((a == b) | (np.isnan(a) & np.isnan(b))))  # noqa: E731
    return same(cid_, P.ids), same(ccl_, P.cluster)


def scorer_observed(arm: str) -> dict:
    """The observed statistics computed the fixed scorer's way (odisha_phase3_1): from the arm's joined CSV,
    stand key the string 'district:id', labelling per district. Used only to prove the array path agrees."""
    d = pd.read_csv(JOINED[arm]).merge(pd.read_csv(FIELD_TYPES)[["plot_key", "field_type"]],
                                       on="plot_key", validate="1:1")
    id_col, cl_col = f"{arm}_{LAYER}_id", f"{arm}_{LAYER}_cluster"
    d = d[d[id_col].notna()].reset_index(drop=True)
    d["skey"] = d.district.astype(str) + ":" + d[id_col].round().astype(int).astype(str)
    out = {"delin_all": ari(d.skey, d.field_type)}
    multi = d.groupby("skey").skey.transform("size").to_numpy() > 1
    sub = d[multi]
    out["delin_multi"] = ari(sub.skey, sub.field_type)
    sizes = d.groupby("skey").size()
    alike = d.groupby(["skey", "field_type"]).size()
    out["prec"] = float((alike * (alike - 1) / 2).sum() / (sizes * (sizes - 1) / 2).sum())
    lab = np.rint(pd.to_numeric(d[cl_col], errors="coerce").to_numpy())
    ok = ~np.isnan(lab)
    per, wts = [], []
    for _, g in d[ok].groupby("district"):
        if len(g) >= 2 and g.field_type.nunique() >= 2:
            per.append(ari(g.field_type, np.rint(g[cl_col].astype(float))))
            wts.append(len(g))
    out["lab_wmean"] = float(np.average(per, weights=wts))
    i, j = np.triu_indices(len(d), 1)
    _, _, dm = GEOD.inv(d.lon6.to_numpy()[i], d.lat6.to_numpy()[i], d.lon6.to_numpy()[j], d.lat6.to_numpy()[j])
    far = ok[i] & ok[j] & (d.district.to_numpy()[i] == d.district.to_numpy()[j]) & (dm > DISTANT_M)
    st = d.field_type.to_numpy()[i] == d.field_type.to_numpy()[j]
    sl = lab[i] == lab[j]
    out["far_gap"] = float(sl[far & st].mean() - sl[far & ~st].mean())
    return out


# ---------------------------------------------------------------------- percentile reporting
def p_upper(obs: float, null: np.ndarray) -> tuple[float, int]:
    v = null[~np.isnan(null)]
    return ((1 + (v >= obs).sum()) / (1 + len(v)) if len(v) >= S.MIN_NULL and not np.isnan(obs) else np.nan), len(v)


def null_row(name: str, obs: float, null: np.ndarray, nd: int = 4) -> None:
    v = null[~np.isnan(null)]
    pc, n = S.percentile(obs, null)
    if n < S.MIN_NULL or np.isnan(obs):
        say(f"    {name:44} {obs:+.{nd}f} | NOT ESTIMABLE (usable realisations {n} < {S.MIN_NULL})")
        return
    med, p5, p95 = S.qs(v)
    pu, _ = p_upper(obs, null)
    say(f"    {name:44} {obs:+.{nd}f} | {med:+.{nd}f} [{p5:+.{nd}f}, {p95:+.{nd}f}]  {pc:6.1f}  {pu:6.3f}  {n:5d}")


def table_head() -> None:
    say(f"    {'statistic':44} {'observed':>7} | {'null median [p5, p95]':>28}  {'pctile':>6}  {'p(>=)':>6}  {'n':>5}")


# ---------------------------------------------------------------------- per-arm analysis
def analyse_arm(arm, spec, plots, parts, X: Plots, n_rot: int) -> dict:
    nm = ARM_LABEL[arm]
    P = S.Partition(spec, arm, LAYER, plots, parts)
    if P.missing:
        raise SystemExit(f"[{nm}] districts missing from the {LAYER} layer: {P.missing_why}")

    ok_id, ok_cl = identity_check(P, plots, parts)
    say(f"  [{nm}] identity check at the real plot positions: stand ids {'PASS' if ok_id else 'FAIL'}, "
        f"stand types {'PASS' if ok_cl else 'FAIL'}")
    if not (ok_id and ok_cl):
        raise SystemExit(f"IDENTITY CHECK FAILED for {arm}: the rotation null's assignment at the real plot positions "
                         "does not reproduce the join. The null would not measure the observed statistic. Stopping.")

    A = ~np.isnan(P.ids)                  # plots with a stand
    L = A & ~np.isnan(P.cluster)          # ... and a stand type
    obs = {**X.delin(P.ids, A), **X.label(P.cluster, L)}
    _, m_pl, m_st = multi_ari(X.ft[A], P.ids[A])

    ref = scorer_observed(arm)
    bad = {k: (obs[k], ref[k]) for k in ref if not np.isclose(obs[k], ref[k], rtol=0, atol=1e-12)}
    if bad:
        raise SystemExit(f"[{nm}] observed statistics disagree with the fixed scorer's definition: {bad}")
    say(f"  [{nm}] plots with a stand {int(A.sum())}, with a stand type {int(L.sum())}; multi-plot stands "
        f"{m_st} holding {m_pl} plots; observed statistics match the scorer's definition (|diff| < 1e-12)")

    t0 = time.time()
    rid, rcl, _, _, fails = S.rotation_null(plots, parts, P, A, n_rot, S.seeded(SEED_UNCOND.format(arm=arm)),
                                            strict=False, tag=arm)
    t1 = time.time()
    lab_layers = LabelledLayers(P)
    _, lcl, _, _, lfails = S.rotation_null(plots, parts, lab_layers, L, n_rot,
                                           S.seeded(SEED_LABELLED.format(arm=arm)), strict=False,
                                           tag=arm + "/labelled")
    t2 = time.time()
    say(f"  [{nm}] rotation nulls: unconditional {n_rot} in {t1 - t0:.0f} s, failures {len(fails)}; "
        f"conditional (labelled polygons) {n_rot} in {t2 - t1:.0f} s, failures {len(lfails)}")
    for f in fails + lfails:
        say(f"      FAILED PART {f}")

    # a null with a failed part is not built (rotation_null's contract): every realisation is unusable
    use_d = np.array([not fails and not np.isnan(rid[r, A]).any() for r in range(n_rot)])
    use_l = np.array([not lfails and not np.isnan(lcl[r, L]).any() for r in range(n_rot)])
    use_u = np.array([not fails and not np.isnan(rcl[r, L]).any() for r in range(n_rot)])

    null = {}
    for r in range(n_rot):
        sd = X.delin(rid[r], A) if use_d[r] else {}
        sl = X.label(lcl[r], L) if use_l[r] else {}
        for k in list(obs):
            null.setdefault(k, np.full(n_rot, np.nan))[r] = {**sd, **sl}.get(k, np.nan)
    # the unconditional null for labelling, for contrast only: why the conditional one is needed
    null_uncond_lab = np.array([X.label(rcl[r], L)["lab_wmean"] if use_u[r] else np.nan for r in range(n_rot)])
    return dict(obs=obs, null=null, null_uncond_lab=null_uncond_lab, ids=P.ids, cl=P.cluster, A=A, L=L,
                multi=(m_pl, m_st), use=(int(use_d.sum()), int(use_l.sum()), int(use_u.sum())))


# ---------------------------------------------------------------------- village resampling
def resample_stats(X: Plots, R: dict, ix: np.ndarray, copy: np.ndarray) -> dict:
    """Both arms' statistics on the plots ix; copy numbers the drawn copy of each village, so a village
    drawn twice contributes two sets of stands (the stand ids are made unique per copy)."""
    out = {}
    f, d = X.ft[ix], X.dist[ix]
    for arm, r in R.items():
        off = np.nanmax(r["ids"]) + 1
        sid = r["ids"][ix] + copy * off
        A, L = r["A"][ix], r["L"][ix]
        out[arm] = {"delin_all": ari(f[A], sid[A]), "delin_multi": multi_ari(f[A], sid[A])[0],
                    "prec": pair_precision(f[A], sid[A]), "lab_wmean": lab_wmean(f[L], r["cl"][ix][L], d[L])[0]}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rotations", type=int, default=1999, help="rotation-null realisations per null (default 1999)")
    ap.add_argument("--boot", type=int, default=4000, help="paired village cluster bootstrap draws (default 4000)")
    ap.add_argument("--out-dir", type=Path, default=HERE, help="where the results .txt goes (default odisha_script/)")
    ap.add_argument("--progress-every", type=int, default=0,
                    help="rotation-null progress line every N accepted realisations per village (0: off)")
    args = ap.parse_args()
    S.apply_runtime_args(args)
    t_start = time.time()

    spec, plots, parts = load_all()
    X = Plots(plots)
    upart = np.unique(X.part)
    n_vill = len(upart)

    say("=" * 110)
    say("PHASE 3 STEP 3 -- significance of the pairwise score (rotation null) and the 3 ha vs 10 ha comparison")
    say("=" * 110)
    say("  HOW TO READ THIS FILE")
    say("  * Chance-level ARI is POSITIVE in this design. Field types and stands both cluster by village, so a stand")
    say("    map with no information about the forest still scores above zero. Every statistic is therefore read")
    say("    against a spatial ROTATION NULL (odisha_phase2_5_stats.rotation_null): each village's plot cloud moved")
    say("    rigidly to a random position and angle inside its village, taking the stand under it. 'pctile' is the")
    say("    observed value's mid-rank percentile in that null (share below + half the ties, x100); 'p(>=)' is the")
    say("    one-sided (1 + #null >= observed) / (1 + n). Fewer than 100 usable realisations -> NOT ESTIMABLE.")
    say("  * Labelling uses a CONDITIONAL null: each village's layer limited to polygons that carry a stand type and")
    say("    the labelled plots forced to land on one, because under the unconditional null too few realisations")
    say("    label every labelled plot (koraput's merged layer is ~19% untyped).")
    say("  * Plot-level permutation and plot-level bootstrap p-values are ANTI-CONSERVATIVE here (plots in a")
    say("    village are not independent) and are deliberately NOT reported as tests.")
    say(f"  * The {n_vill} villages (AOI parts) are the units of independence. Arm differences get a paired village")
    say("    cluster bootstrap CI and a leave-one-village-out jackknife SE on top of the rotation null.")
    say("  * Statistics are exactly those of odisha_phase3_1_pairwise_score.py: stands keyed (district, id);")
    say("    labelling = plot-weighted mean of per-district ARIs; far-apart = same-district pairs > 2 km apart.")
    say(f"  * MULTIPLE COMPARISONS. {len(STATS)} statistics x 2 arms = {2 * len(STATS)} headline tests, plus per-district")
    say("    and arm-difference rows. At that count one p near 0.05 is expected from chance alone, so no single")
    say("    p-value below is a finding on its own. Holm-adjusted p-values over the headline tests are given at the")
    say("    end, together with a plain statement of what the file does and does not show.")
    say(f"  plots in the village AOIs: {X.n}; villages: {n_vill}; field types: "
        f"{ {int(k): int(v) for k, v in zip(*np.unique(X.ft, return_counts=True))} }; far-apart same-district pairs: "
        f"{len(X.fi)} before the labelled-plot restriction (each arm's count is in its own table)")
    say(f"  rotations per null: {args.rotations}; bootstrap draws: {args.boot}")
    say("")

    R = {arm: analyse_arm(arm, spec, plots, parts, X, args.rotations) for arm in ARM_LABEL}

    for arm, r in R.items():
        nm = ARM_LABEL[arm]
        say("")
        say("-" * 110)
        say(f"{nm.upper()} ARM ({arm}, {LAYER} layer) -- observed vs rotation null")
        say("-" * 110)
        say(f"  usable realisations: delineation {r['use'][0]}, labelling (conditional) {r['use'][1]}")
        table_head()
        for k, label in STATS:
            null_row(label, r["obs"][k], r["null"][k])
        say(f"      (multi-plot: {r['multi'][0]} plots in {r['multi'][1]} stands observed; redefined per realisation)")
        say(f"      (far-apart: {int((r['L'][X.fi] & r['L'][X.fj]).sum())} same-district pairs > 2 km with both plots typed)")
        say("  per-district labelling ARI (descriptive: each district is 1-12 villages):")
        for k in sorted(x for x in r["obs"] if x.startswith("lab_") and x != "lab_wmean"):
            null_row(f"  {k[4:]}", r["obs"][k], r["null"][k])
        say("  for contrast, labelling wmean under the UNCONDITIONAL null (why the conditional one is used):")
        null_row("  labelling ARI, unconditional null", r["obs"]["lab_wmean"], r["null_uncond_lab"])

    # ------------------------------------------------------------------ arm comparison
    a3, a10 = R["v120_3ha"], R["v120"]
    say("")
    say("-" * 110)
    say("ARM COMPARISON -- D = statistic(3 ha) - statistic(10 ha), same plots")
    say("-" * 110)
    say("  (i) against the difference of the two arms' independent rotation nulls (realisations paired by index")
    say("      only): is D larger than the difference in the arms' chance levels? 'excess' = D - null-D median.")
    say(f"    {'statistic':44} {'D':>7} | {'null-D median [p2.5, p97.5]':>28}  {'excess':>7}  {'pctile':>6}  {'n':>5}")
    d_pct: dict[str, float] = {}
    for k, label in STATS:
        d_obs = a3["obs"][k] - a10["obs"][k]
        dn = a3["null"][k] - a10["null"][k]
        v = dn[~np.isnan(dn)]
        pc, n = S.percentile(d_obs, dn)
        if n < S.MIN_NULL:
            say(f"    {label:44} {d_obs:+.4f} | NOT ESTIMABLE (usable paired realisations {n} < {S.MIN_NULL})")
            continue
        d_pct[k] = pc
        med = np.median(v)
        lo, hi = np.quantile(v, [.025, .975])
        say(f"    {label:44} {d_obs:+.4f} | {med:+.4f} [{lo:+.4f}, {hi:+.4f}]  {d_obs - med:+.4f}  {pc:6.1f}  {n:5d}")

    say("")
    say(f"  (ii) paired village cluster bootstrap: {n_vill} villages resampled with replacement, the same draw for both")
    say("       arms, stand ids unique per drawn copy; 95% percentile CI of D. (Far-apart is left out: a village")
    say("       drawn twice would pair each plot with its own copy.)")
    rng = S.seeded(SEED_BOOT)
    idx_part = {q: np.where(X.part == q)[0] for q in upart}
    boot = {k: np.empty(args.boot) for k in BOOT_STATS}
    for b in range(args.boot):
        pick = rng.choice(upart, n_vill, replace=True)
        ix = np.concatenate([idx_part[q] for q in pick])
        cp = np.concatenate([np.full(len(idx_part[q]), c) for c, q in enumerate(pick)])
        s = resample_stats(X, R, ix, cp)
        for k in BOOT_STATS:
            boot[k][b] = s["v120_3ha"][k] - s["v120"][k]
    say(f"    {'statistic':44} {'D':>7} | {'95% CI':>20}  {'share < 0':>9}  {'n':>5}")
    for k, label in STATS:
        if k not in BOOT_STATS:
            continue
        d_obs = a3["obs"][k] - a10["obs"][k]
        v = boot[k][~np.isnan(boot[k])]
        lo, hi = np.quantile(v, [.025, .975])
        say(f"    {label:44} {d_obs:+.4f} | [{lo:+.4f}, {hi:+.4f}]  {np.mean(v < 0):9.3f}  {len(v):5d}")
        # A CI that excludes 0 reads on its own as "the arms differ". If (i) puts D inside
        # the null-difference's central 95%, the gap is what the arms' chance levels already
        # differ by, and saying so on the same line stops the row being quoted alone.
        if (lo > 0 or hi < 0) and k in d_pct and 2.5 <= d_pct[k] <= 97.5:
            say(f"      ^ excludes 0, but (i) puts D at pctile {d_pct[k]:.1f} of the null difference: the gap is the")
            say("        difference in the arms' chance levels, not a difference in how well they delineate.")

    say("")
    say("  (iii) leave-one-village-out jackknife: D recomputed with each village held out.")
    say(f"    {'statistic':44} {'D':>7} | {'jackknife SE':>12}  {'D/SE':>6}  {'leave-one-out range':>21}")
    jk = {k: [] for k, _ in STATS}
    for q in upart:
        keep = X.part != q
        for k, _ in STATS:
            v = []
            for r in (a3, a10):
                A, L = r["A"] & keep, r["L"] & keep
                s = X.delin(r["ids"], A) if k in DELIN else X.label(r["cl"], L)
                v.append(s[k])
            jk[k].append(v[0] - v[1])
    for k, label in STATS:
        v = np.array(jk[k])
        d_obs = a3["obs"][k] - a10["obs"][k]
        g = len(v)
        se = float(np.sqrt((g - 1) / g * np.nansum((v - np.nanmean(v)) ** 2)))
        say(f"    {label:44} {d_obs:+.4f} | {se:12.4f}  {d_obs / se:+6.2f}  [{np.nanmin(v):+.4f}, {np.nanmax(v):+.4f}]")

    say("")
    say("  Bootstrap and jackknife say how much D moves with the choice of villages; neither is a chance-level test.")
    say("  The chance-level question for D is (i).")

    # ------------------------------------------------------------------ multiplicity
    say("")
    say("-" * 110)
    say(f"MULTIPLE COMPARISONS -- Holm over the {2 * len(STATS)} headline tests (one-sided p(>=), rotation null)")
    say("-" * 110)
    tests = []
    for arm, r in R.items():
        for k, label in STATS:
            p, n = p_upper(r["obs"][k], r["null"][k])
            if n >= S.MIN_NULL and not np.isnan(r["obs"][k]):
                tests.append((f"{ARM_LABEL[arm]}: {label}", p))
    order = np.argsort([p for _, p in tests])
    m, running, holm = len(tests), 0.0, {}
    for rank, t in enumerate(order):
        running = max(running, min(1.0, (m - rank) * tests[t][1]))
        holm[t] = running
    say(f"    {'test':58} {'p(>=)':>7}  {'Holm p':>7}")
    for t in order:
        say(f"    {tests[t][0]:58} {tests[t][1]:7.3f}  {holm[t]:7.3f}{'  <- survives' if holm[t] < .05 else ''}")
    n_surv = sum(h < .05 for h in holm.values())

    # ------------------------------------------------------------------ plain reading
    # Every sentence below is computed from the numbers above, so a rerun on other
    # data cannot leave a stale conclusion sitting under changed tables.
    say("")
    say("-" * 110)
    say("WHAT THIS SAYS")
    say("-" * 110)
    lab = {ARM_LABEL[a]: S.percentile(R[a]["obs"]["lab_wmean"], R[a]["null"]["lab_wmean"])[0] for a in R}
    dmul = {ARM_LABEL[a]: S.percentile(R[a]["obs"]["delin_multi"], R[a]["null"]["delin_multi"])[0] for a in R}
    say(f"  * {n_surv} of {m} headline tests beat chance after Holm correction at 0.05.")
    say("  * Labelling sits at pctile " + ", ".join(f"{v:.1f} ({k})" for k, v in lab.items())
        + " of its chance level: " + ("indistinguishable from a randomly placed stand map."
                                      if all(5 <= v <= 95 for v in lab.values()) else "see the tables."))
    say("  * Delineation on multi-plot stands sits at pctile " + ", ".join(f"{v:.1f} ({k})" for k, v in dmul.items())
        + ": " + ("inside the null's central 90% in both arms." if all(5 <= v <= 95 for v in dmul.values())
                  else "outside the central 90% in at least one arm."))
    inside = [lbl for k, lbl in STATS if k in d_pct and 2.5 <= d_pct[k] <= 97.5]
    say(f"  * Arm difference: {len(inside)} of {len(d_pct)} statistics differ between 3 ha and 10 ha by no more than")
    say("    their chance levels already differ ((i) inside the null's central 95%).")
    if n_surv == 0 and len(inside) == len(d_pct):
        say("  * So neither ceiling groups or labels structurally alike plots better than chance, and the data cannot")
        say(f"    tell the two ceilings apart. With {n_vill} villages as the units of independence it has little power to.")
    say("  * NOT supported by this file: 'better than chance' from ARI > 0 (chance is positive here); any single")
    say("    p-value read without the Holm column; any plot-level p-value; the bootstrap CI read without (i).")

    out = args.out_dir / OUT_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(_lines) + "\n")
    print(f"\n  wrote {out}   (runtime {time.time() - t_start:.0f} s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
