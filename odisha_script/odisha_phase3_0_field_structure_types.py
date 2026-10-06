"""Phase 3, step 0: group the field plots by FOREST STRUCTURE, k chosen by elbow.

Why this exists. The pre-registered field typology clustered plots on species
composition and collapsed: 259 of 274 plots fell in one group (see
explain_field_types.py). Sal averages only 12% of basal area and mango and jamun
are nearly everywhere, so composition does not carve this forest into types, and
"do alike plots get the same stand type?" had nothing to test against.

Structure does vary. Height runs 0.16-45.52 m and crown cover 0-98% across these
plots, and structure is also what the pipeline measures -- canopy height, canopy
roughness, seasonality -- so a structural grouping is the like-for-like truth to
compare stand labels against.

INTEGRITY RULE, and the reason the number of groups is chosen here rather than
later: k is selected from the FIELD DATA ALONE, by elbow and silhouette, before
any stand label is read. It is never chosen by trying values and keeping the one
that agrees best with the pipeline. That would tune the answer into existence,
which is the thing the supervisor's brief rules out.

CHANGED 2026-10-07 -- every measurement now counts the same rows.
Until this date the four structural variables did not describe the same things.
The raw sheet has one row per record, and its Habit column says what the record
is: Tree, SaplingSeedling, Shrub, Climber, Stump (and one Seedling). Height and
trunk area were taken over ALL of those rows, while the tree count took Tree rows
only. So a plot could show 0 trees and still a non-zero height and trunk area,
and 168 cut stumps were counted as standing wood.

The rule now (--rows trees, the default), fixed before any score was recomputed
and with no stand label or score read:
  height      trunk-area-weighted mean Height over Tree rows only
  trunk area  sum of pi*(DBH/2)^2 over Tree rows only (log1p before scaling)
  n_trees     number of Tree rows (as before)
  crown cover one field reading per plot (as before)
  no-tree rule: a plot with no Tree row (15 plots) gets height 0.0 and trunk
              area 0.0. It stays in the analysis -- "no trees here" is a real
              structure, and all 274 plots are kept.
Stumps, climbers, shrubs and saplings are therefore no longer counted in any
variable. Scaling, k-means (seed 42, n_init 25), the k range 2..12 and the elbow
rule are unchanged. The rule was NOT chosen by looking at what it does to any
downstream result, and the integrity rule above still holds: k is whatever the
elbow of this field data gives.

Type numbers are also made meaningful under --rows trees: types are renumbered
0..k-1 from shortest to tallest (group median tree height, ties by median trunk
area), instead of the arbitrary order k-means happens to return.

--rows all reproduces the earlier, committed behaviour exactly (features from the
joined table, original numbering) and writes to separate *_allrows files, so the
old typology stays available for comparison and cannot be mistaken for the truth.

Input : odisha_script/phase2_plots_joined_districts.csv   (274 plots)
        odisha_script/Odisha_samples.csv                  (raw records, via
        odisha_phase1_0_clean.load_trees: GPS filter + crown-cover repair)
Output: --rows trees (default; the truth used downstream)
          odisha_script/odisha_phase3_0_field_types.csv   (plot_key -> field_type)
          odisha_script/odisha_phase3_0_results.txt
        --rows all (the earlier behaviour, for comparison only)
          odisha_script/odisha_phase3_0_field_types_allrows.csv
          odisha_script/odisha_phase3_0_results_allrows.txt
Offline; no Earth Engine.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import KMeans
from sklearn.metrics import (adjusted_rand_score, calinski_harabasz_score,
                             davies_bouldin_score, silhouette_score)

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from odisha_phase1_0_clean import load_trees  # noqa: E402

SEED = 42
K_RANGE = range(2, 13)
N_NO_TREE_PLOTS = 15          # plots with no Tree row; checked, not assumed
OUTPUTS = {
    "trees": (HERE / "odisha_phase3_0_field_types.csv",
              HERE / "odisha_phase3_0_results.txt"),
    "all": (HERE / "odisha_phase3_0_field_types_allrows.csv",
            HERE / "odisha_phase3_0_results_allrows.txt"),
}

_lines: list[str] = []


def say(s: str = "") -> None:
    print(s)
    _lines.append(s)


def robust_scale(df: pd.DataFrame) -> np.ndarray:
    """Median/IQR scaling, matching the pipeline's own preprocessing (DEC-003),
    so neither side of the comparison is treated more kindly than the other."""
    med = df.median()
    iqr = (df.quantile(0.75) - df.quantile(0.25)).replace(0, np.nan)
    iqr = iqr.fillna(df.std().replace(0, 1.0))
    return ((df - med) / iqr).to_numpy(float)


def knee(ks: list[int], inertia: list[float]) -> int:
    """Elbow by maximum distance to the chord joining the first and last point."""
    x = np.array(ks, float)
    y = np.array(inertia, float)
    x = (x - x.min()) / (x.max() - x.min())
    y = (y - y.min()) / (y.max() - y.min())
    num = np.abs((y[-1] - y[0]) * x - (x[-1] - x[0]) * y + x[-1] * y[0] - y[-1] * x[0])
    return ks[int(np.argmax(num / np.hypot(y[-1] - y[0], x[-1] - x[0])))]


def tree_rows_structure(p: pd.DataFrame) -> pd.DataFrame:
    """Height, trunk area and count over Tree rows only, from the raw sheet,
    one row per plot in the order of `p`. Stops loudly if the raw sheet and the
    joined table disagree, so a silent drift between the two cannot pass."""
    s, _ = load_trees(HERE / "Odisha_samples.csv")
    if set(s.plot_key) != set(p.plot_key):
        raise SystemExit("CROSS-CHECK FAILED: raw sheet and joined table hold different plots")
    t = s[s["Habit"].astype(str).str.strip().str.lower() == "tree"]
    g = t.groupby("plot_key")
    area = g["ba_cm2"].sum()
    out = pd.DataFrame({
        "tree_height_m": (t["Height"] * t["ba_cm2"]).groupby(t["plot_key"]).sum() / area,
        "tree_trunk_area_cm2": area,
        "n_tree_rows": g.size(),
    }).reindex(p.plot_key)
    has_tree = out.n_tree_rows.fillna(0).to_numpy() > 0
    if np.isnan(out.tree_height_m.to_numpy()[has_tree]).any():
        raise SystemExit("CROSS-CHECK FAILED: a plot with Tree rows has no defined tree height")
    # the no-tree rule: no Tree row -> height 0.0, trunk area 0.0, count 0
    out = out.fillna(0.0)
    out["n_tree_rows"] = out.n_tree_rows.astype(int)
    out.index = p.index

    n_none = int((~has_tree).sum())
    if n_none != N_NO_TREE_PLOTS:
        raise SystemExit(f"CROSS-CHECK FAILED: {n_none} plots have no Tree row, "
                         f"expected {N_NO_TREE_PLOTS}")
    if not (out.n_tree_rows.to_numpy() == p.n_trees.to_numpy()).all():
        raise SystemExit("CROSS-CHECK FAILED: Tree-row count differs from the joined table's n_trees")
    ref = p.loreys_h_tree_m.to_numpy(float)
    defined = ~np.isnan(ref)
    if not (defined == has_tree).all():
        raise SystemExit("CROSS-CHECK FAILED: loreys_h_tree_m is defined for a different set "
                         "of plots than those with Tree rows")
    worst = float(np.abs(out.tree_height_m.to_numpy()[defined] - ref[defined]).max())
    if worst > 1e-6:
        raise SystemExit(f"CROSS-CHECK FAILED: trees-only height differs from the joined "
                         f"table's loreys_h_tree_m by up to {worst:.3g} m")
    say(f"  cross-check passed: trees-only height matches the joined table's loreys_h_tree_m "
        f"(max diff {worst:.1e} m, {int(defined.sum())} plots);")
    say(f"                      Tree-row count matches n_trees on all {len(p)} plots; "
        f"{n_none} plots have no Tree row.")
    return out


def scan_k(X: np.ndarray) -> pd.DataFrame:
    rows = []
    for k in K_RANGE:
        km = KMeans(n_clusters=k, random_state=SEED, n_init=25).fit(X)
        lab = km.labels_
        rows.append({
            "k": k, "inertia": km.inertia_,
            "silhouette": silhouette_score(X, lab),
            "ch": calinski_harabasz_score(X, lab),
            "db": davies_bouldin_score(X, lab),
        })
    return pd.DataFrame(rows)


def fit_labels(X: np.ndarray, k: int) -> np.ndarray:
    return KMeans(n_clusters=k, random_state=SEED, n_init=25).fit(X).labels_


def main(rows: str = "trees") -> None:
    out_csv, out_txt = OUTPUTS[rows]
    p = pd.read_csv(HERE / "phase2_plots_joined_districts.csv")
    say("=" * 100)
    say("PHASE 3 STEP 0 -- field forest types from STRUCTURE, k by elbow")
    say("=" * 100)
    say(f"  plots: {len(p)}")
    if rows == "trees":
        say("  rows counted: TREE rows only, for height, trunk area and tree count alike")
        say("                (stumps, climbers, shrubs and saplings are not counted; rule of 2026-10-07)")
    else:
        say("  rows counted: ALL rows for height and trunk area, Tree rows for the count")
        say("                (the behaviour before 2026-10-07; kept for comparison only)")

    total_ba = p.sp_ba_json.map(
        lambda s: sum(json.loads(s).values()) if isinstance(s, str) else 0.0
    )
    tr = tree_rows_structure(p)
    p["tree_height_m"] = tr.tree_height_m
    p["tree_trunk_area_cm2"] = tr.tree_trunk_area_cm2
    p["all_rows_trunk_area_cm2"] = total_ba.astype(float)

    # Four structural variables, complete for all 274 plots. dbh_mean_cm is
    # deliberately excluded from the primary set: it is missing for exactly the
    # 15 plots that recorded no trees, and imputing it would invent structure
    # for the plots whose lack of structure is the real signal. It is reported
    # as a sensitivity below.
    feat_all = pd.DataFrame({
        "loreys_h_m": p.loreys_h_m.astype(float),
        "crown_cover_pct": p.crown_cover_pct.astype(float),
        "log_basal_area": np.log1p(total_ba.astype(float)),
        "n_trees": p.n_trees.astype(float),
    })
    feat_trees = pd.DataFrame({
        "tree_height_m": p.tree_height_m.astype(float),
        "crown_cover_pct": p.crown_cover_pct.astype(float),
        "log_tree_trunk_area": np.log1p(p.tree_trunk_area_cm2.astype(float)),
        "n_trees": p.n_trees.astype(float),
    })
    feat = feat_trees if rows == "trees" else feat_all
    h_col = "tree_height_m" if rows == "trees" else "loreys_h_m"
    ba_col = "tree_trunk_area_cm2" if rows == "trees" else "all_rows_trunk_area_cm2"
    say(f"  structural variables: {', '.join(feat.columns)}")
    say("  basal area is a plot total, not per hectare: plot radius is still an open")
    say("  question with FES, so an area denominator is not available. All plots share")
    say("  the same protocol, so the total is proportional to density across plots.")
    say("")

    X = robust_scale(feat)

    say("-" * 100)
    say("CHOOSING k FROM THE FIELD DATA ALONE (no stand label is read anywhere above)")
    say("-" * 100)
    say(f"  {'k':>3}  {'inertia':>12}  {'silhouette':>11}  {'Calinski-H':>11}  {'Davies-B':>10}")
    res = scan_k(X)
    for _, r in res.iterrows():
        say(f"  {int(r['k']):>3}  {r['inertia']:>12.1f}  {r['silhouette']:>11.3f}  "
            f"{r['ch']:>11.1f}  {r['db']:>10.3f}")

    k_elbow = knee(res.k.tolist(), res.inertia.tolist())
    k_sil = int(res.loc[res.silhouette.idxmax(), "k"])
    k_ch = int(res.loc[res.ch.idxmax(), "k"])
    k_db = int(res.loc[res.db.idxmin(), "k"])
    say("")
    say(f"  elbow (knee of inertia)      k = {k_elbow}")
    say(f"  best silhouette              k = {k_sil}  ({res.silhouette.max():.3f})")
    say(f"  best Calinski-Harabasz       k = {k_ch}")
    say(f"  best Davies-Bouldin          k = {k_db}")

    k = k_elbow
    agree = [n for n, v in (("silhouette", k_sil), ("Calinski-Harabasz", k_ch),
                            ("Davies-Bouldin", k_db)) if v == k_elbow]
    say(f"  -> SELECTED k = {k} (elbow). Also preferred by: "
        f"{', '.join(agree) if agree else 'none of the other three'}.")
    if not agree:
        say("     The criteria disagree. The elbow is taken because it is the one the")
        say("     supervisor named; the others are recorded so the choice is auditable.")
    say("")

    labels = fit_labels(X, k)
    if rows == "trees":
        # Meaningful, stable numbering: 0 = shortest ... k-1 = tallest, by the
        # group's median tree height (ties by median trunk area). k-means' own
        # numbering is arbitrary. Not applied to --rows all, which must stay
        # label-for-label identical to the committed typology.
        med = p.assign(_l=labels).groupby("_l")[[h_col, ba_col]].median()
        order = med.sort_values([h_col, ba_col], kind="mergesort").index.tolist()
        remap = {old: new for new, old in enumerate(order)}
        labels = np.array([remap[v] for v in labels])
    p["field_type"] = labels

    say("-" * 100)
    say(f"THE {k} STRUCTURAL FOREST TYPES")
    say("-" * 100)
    if rows == "trees":
        say("  numbered from shortest (0) to tallest by median tree height")
    prof = p.groupby("field_type").agg(
        plots=("plot_key", "size"),
        height_m=(h_col, "median"),
        crown_pct=("crown_cover_pct", "median"),
        trees=("n_trees", "median"),
        species=("n_species", "median"),
        sal_share=("sal_ba_frac", "median"),
        basal_area=(ba_col, "median"),
    )
    h_name, ba_name = (("tree height", "tree trunk area") if rows == "trees"
                       else ("height", "BA"))
    for t, r in prof.iterrows():
        say(f"  type {t}: {int(r.plots):>3} plots | {h_name} {r.height_m:>5.1f} m | "
            f"crown {r.crown_pct:>5.1f}% | {int(r.trees):>3} trees | "
            f"{int(r.species)} spp | Sal {r.sal_share:.2f} | {ba_name} {r.basal_area:,.0f}"
            + (" cm2" if rows == "trees" else ""))
    say("")
    say(f"  sizes: {p.field_type.value_counts().sort_index().to_dict()}")
    largest = p.field_type.value_counts().max()
    say(f"  largest group holds {largest} of {len(p)} plots ({largest/len(p):.1%}) "
        f"-- compare the composition typology's 259/274 (94.5%).")
    if rows == "trees":
        nt = p[p.n_trees == 0].field_type.value_counts().sort_index().to_dict()
        say(f"  the {N_NO_TREE_PLOTS} plots with no Tree row fall in type(s): {nt}")
    say("")

    say("  by district:")
    say(pd.crosstab(p.district, p.field_type).to_string())
    say("")

    # sensitivity: does adding mean DBH change the picture?
    # (dbh_mean_cm in the joined table is already the mean over Tree rows.)
    f2 = feat.copy()
    f2["dbh_mean_cm"] = p.dbh_mean_cm.astype(float).fillna(0.0)
    X2 = robust_scale(f2)
    r2 = [(kk, KMeans(n_clusters=kk, random_state=SEED, n_init=25).fit(X2).inertia_)
          for kk in K_RANGE]
    say(f"  SENSITIVITY: adding dbh_mean_cm (0 where no trees) moves the elbow to "
        f"k = {knee([a for a, _ in r2], [b for _, b in r2])}.")
    lab2 = fit_labels(X2, k)
    say(f"               agreement with the primary grouping at k={k}: "
        f"ARI {adjusted_rand_score(labels, lab2):.3f}")

    if rows == "trees":
        compare_with_all_rows(p, feat_all, k)

    p[["plot_key", "district", "habitation", "field_type", "loreys_h_m",
       "crown_cover_pct", "n_trees", "n_species", "sal_ba_frac",
       "tree_height_m", "tree_trunk_area_cm2", "all_rows_trunk_area_cm2"]].to_csv(out_csv, index=False)
    say("")
    say(f"  wrote {out_csv.name} ({len(p)} plots) and {out_txt.name}")
    out_txt.write_text("\n".join(_lines) + "\n")


def compare_with_all_rows(p: pd.DataFrame, feat_all: pd.DataFrame, k_trees: int) -> None:
    """How far the trees-only typology moved from the earlier all-rows one.
    The all-rows typology is refitted here exactly as --rows all fits it (its
    own elbow, k-means' own numbering). Field data only; no stand label."""
    say("")
    say("-" * 100)
    say("COMPARISON WITH THE ALL-ROWS TYPOLOGY (the grouping used before 2026-10-07)")
    say("-" * 100)
    Xa = robust_scale(feat_all)
    ra = scan_k(Xa)
    k_all = knee(ra.k.tolist(), ra.inertia.tolist())
    lab_all = fit_labels(Xa, k_all)
    lab_tr = p.field_type.to_numpy()

    has = (p.n_trees > 0).to_numpy()
    d = (p.loreys_h_m - p.tree_height_m).abs().to_numpy()
    say(f"  height, all rows vs Tree rows only, differs by more than 1 m in "
        f"{int((d > 1).sum())} of {len(p)} plots:")
    say(f"    {int((d[has] > 1).sum())} of the {int(has.sum())} plots that have trees "
        f"(largest change {d[has].max():.2f} m), and")
    say(f"    {int((d[~has] > 1).sum())} of the {int((~has).sum())} plots with no Tree row, "
        f"whose height is now 0.0 (it was up to {p.loreys_h_m[~has].max():.2f} m,")
    say("    measured on shrubs, saplings, climbers or stumps).")
    share = p.tree_trunk_area_cm2.sum() / p.all_rows_trunk_area_cm2.sum()
    say(f"  Tree rows carry {share:.1%} of all recorded trunk area.")
    say("")
    if k_all == k_trees:
        say(f"  number of types: {k_trees} under both rules (each from its own elbow).")
    else:
        say(f"  THE NUMBER OF TYPES DIFFERS: the elbow gives k = {k_trees} with Tree rows only,")
        say(f"  but k = {k_all} with all rows. Nothing was forced to match.")
    say(f"  ARI between the two typologies: {adjusted_rand_score(lab_all, lab_tr):.3f} "
        f"(1 = identical grouping, 0 = no better than chance)")
    say("")
    say("  contingency table (rows: all-rows type, old numbering; columns: trees-only type):")
    ct = pd.crosstab(pd.Series(lab_all, name="all_rows"), pd.Series(lab_tr, name="trees_only"))
    say(ct.to_string())
    say("")
    r_idx, c_idx = linear_sum_assignment(-ct.to_numpy())
    kept = int(ct.to_numpy()[r_idx, c_idx].sum())
    pairs = ", ".join(f"{ct.index[r]}->{ct.columns[c]}" for r, c in zip(r_idx, c_idx))
    say(f"  best one-to-one matching of types (all-rows -> trees-only): {pairs}")
    say(f"  plots that change group under that matching: {len(p) - kept} of {len(p)} "
        f"({(len(p) - kept) / len(p):.1%}); {kept} stay.")
    if k_all != k_trees:
        say("  (with different numbers of types, at least one type has no partner, so every")
        say("   plot in it counts as changed.)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rows", choices=["trees", "all"], default="trees",
                    help="trees: height, trunk area and count all over Tree rows (default, "
                         "the truth used downstream). all: the pre-2026-10-07 behaviour, "
                         "written to *_allrows files.")
    main(ap.parse_args().rows)
