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

Input : odisha_script/phase2_plots_joined_districts.csv   (274 plots)
Output: odisha_script/odisha_phase3_0_field_types.csv     (plot_key -> field_type)
        odisha_script/odisha_phase3_0_results.txt
Offline; no Earth Engine.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score

HERE = Path(__file__).parent
SEED = 42
K_RANGE = range(2, 13)
OUT_TXT = HERE / "odisha_phase3_0_results.txt"
OUT_CSV = HERE / "odisha_phase3_0_field_types.csv"

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


def main() -> None:
    p = pd.read_csv(HERE / "phase2_plots_joined_districts.csv")
    say("=" * 100)
    say("PHASE 3 STEP 0 -- field forest types from STRUCTURE, k by elbow")
    say("=" * 100)
    say(f"  plots: {len(p)}")

    total_ba = p.sp_ba_json.map(
        lambda s: sum(json.loads(s).values()) if isinstance(s, str) else 0.0
    )

    # Four structural variables, complete for all 274 plots. dbh_mean_cm is
    # deliberately excluded from the primary set: it is missing for exactly the
    # 15 plots that recorded no trees, and imputing it would invent structure
    # for the plots whose lack of structure is the real signal. It is reported
    # as a sensitivity below.
    feat = pd.DataFrame({
        "loreys_h_m": p.loreys_h_m.astype(float),
        "crown_cover_pct": p.crown_cover_pct.astype(float),
        "log_basal_area": np.log1p(total_ba.astype(float)),
        "n_trees": p.n_trees.astype(float),
    })
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
        r = rows[-1]
        say(f"  {k:>3}  {r['inertia']:>12.1f}  {r['silhouette']:>11.3f}  "
            f"{r['ch']:>11.1f}  {r['db']:>10.3f}")
    res = pd.DataFrame(rows)

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

    km = KMeans(n_clusters=k, random_state=SEED, n_init=25).fit(X)
    p["field_type"] = km.labels_

    say("-" * 100)
    say(f"THE {k} STRUCTURAL FOREST TYPES")
    say("-" * 100)
    prof = p.groupby("field_type").agg(
        plots=("plot_key", "size"),
        height_m=("loreys_h_m", "median"),
        crown_pct=("crown_cover_pct", "median"),
        trees=("n_trees", "median"),
        species=("n_species", "median"),
        sal_share=("sal_ba_frac", "median"),
    ).round(2)
    prof["basal_area"] = p.assign(ba=total_ba).groupby("field_type").ba.median().round(0)
    for t, r in prof.iterrows():
        say(f"  type {t}: {int(r.plots):>3} plots | height {r.height_m:>5.1f} m | "
            f"crown {r.crown_pct:>5.1f}% | {int(r.trees):>3} trees | "
            f"{int(r.species)} spp | Sal {r.sal_share:.2f} | BA {r.basal_area:,.0f}")
    say("")
    say(f"  sizes: {p.field_type.value_counts().sort_index().to_dict()}")
    largest = p.field_type.value_counts().max()
    say(f"  largest group holds {largest} of {len(p)} plots ({largest/len(p):.1%}) "
        f"-- compare the composition typology's 259/274 (94.5%).")
    say("")

    say("  by district:")
    say(pd.crosstab(p.district, p.field_type).to_string())
    say("")

    # sensitivity: does adding mean DBH change the picture?
    f2 = feat.copy()
    f2["dbh_mean_cm"] = p.dbh_mean_cm.astype(float).fillna(0.0)
    X2 = robust_scale(f2)
    r2 = [(kk, KMeans(n_clusters=kk, random_state=SEED, n_init=25).fit(X2).inertia_)
          for kk in K_RANGE]
    say(f"  SENSITIVITY: adding dbh_mean_cm (0 where no trees) moves the elbow to "
        f"k = {knee([a for a, _ in r2], [b for _, b in r2])}.")
    lab2 = KMeans(n_clusters=k, random_state=SEED, n_init=25).fit(X2).labels_
    from sklearn.metrics import adjusted_rand_score
    say(f"               agreement with the primary grouping at k={k}: "
        f"ARI {adjusted_rand_score(km.labels_, lab2):.3f}")

    p[["plot_key", "district", "habitation", "field_type", "loreys_h_m",
       "crown_cover_pct", "n_trees", "n_species", "sal_ba_frac"]].to_csv(OUT_CSV, index=False)
    say("")
    say(f"  wrote {OUT_CSV.name} ({len(p)} plots) and {OUT_TXT.name}")
    OUT_TXT.write_text("\n".join(_lines) + "\n")


if __name__ == "__main__":
    main()
