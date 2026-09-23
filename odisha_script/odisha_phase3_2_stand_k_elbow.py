"""Phase 3, step 2: choose k for the stand types by elbow, from the stands alone.

The pipeline currently fixes k=6. This picks it instead, the way the supervisor
asked, using the same evidence k-means itself sees: the per-stand feature
vectors that the export stage already writes onto every stand polygon, so no
Earth Engine call is needed.

INTEGRITY RULE. k is chosen from the SATELLITE FEATURES ALONE. No field
measurement and no field type is read anywhere in this file. The field side
chose its own k the same way, from field data alone (step 0). Neither side is
allowed to see how well it agrees with the other, because choosing k by
whichever value maximises agreement would manufacture the result.

Preprocessing mirrors the clustering stage so the elbow describes the space
k-means actually works in: cyclic bands decomposed to sin/cos, skewed bands
log-transformed, then median/IQR scaling (DEC-003, DEC-004).

k-means is fitted PER DISTRICT in this pipeline, because each district is its
own config. So the elbow is reported per district and pooled, and one k has to
serve all four.

Usage: python odisha_script/odisha_phase3_2_stand_k_elbow.py [--arm odisha_v120_handcrafted]
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score

HERE = Path(__file__).parent
VEC = HERE / "phase2_vectors"
SEED = 42
K_RANGE = range(2, 13)
DROP = {"area_ha", "n_pixels", "perim_m", "centroid_lat", "centroid_lon",
        "stand_id", "stand_lbl", "cluster_id", "unit_id", "snic_label"}
CYCLIC = {"aspect", "ndvi_phase_annual", "nirv_phase_annual"}
_lines: list[str] = []


def say(s: str = "") -> None:
    print(s)
    _lines.append(s)


def knee(ks, inertia) -> int:
    x = np.array(ks, float); y = np.array(inertia, float)
    x = (x - x.min()) / (x.max() - x.min()); y = (y - y.min()) / (y.max() - y.min())
    num = np.abs((y[-1] - y[0]) * x - (x[-1] - x[0]) * y + x[-1] * y[0] - y[-1] * x[0])
    return ks[int(np.argmax(num / np.hypot(y[-1] - y[0], x[-1] - x[0])))]


def prep(df: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """Mirror the clustering stage: cyclic -> sin/cos, log skewed, median/IQR."""
    out = {}
    for c in df.columns:
        v = pd.to_numeric(df[c], errors="coerce")
        if v.isna().all():
            continue
        if c in CYCLIC:
            rad = np.deg2rad(v) if v.abs().max() > 7 else v
            out[f"{c}_sin"], out[f"{c}_cos"] = np.sin(rad), np.cos(rad)
        else:
            if v.min() >= 0 and abs(float(pd.Series(v).skew(skipna=True) or 0)) > 1.0:
                v = np.log1p(v)
            out[c] = v
    X = pd.DataFrame(out).replace([np.inf, -np.inf], np.nan)
    X = X.fillna(X.median())
    med, iqr = X.median(), (X.quantile(.75) - X.quantile(.25)).replace(0, np.nan)
    iqr = iqr.fillna(X.std().replace(0, 1.0))
    return ((X - med) / iqr).to_numpy(float), list(X.columns)


def load(arm: str) -> dict[str, pd.DataFrame]:
    out = {}
    for f in sorted(glob.glob(str(VEC / f"{arm}_*_stands_merged.geojson"))):
        d = f.split(f"{arm}_")[1].split("_stands")[0]
        g = json.load(open(f))
        rows = [ft["properties"] for ft in g["features"]]
        if rows:
            out[d] = pd.DataFrame(rows)
    return out


def sweep(X: np.ndarray, label: str) -> dict:
    rows = []
    for k in K_RANGE:
        if k >= len(X):
            break
        km = KMeans(n_clusters=k, random_state=SEED, n_init=25).fit(X)
        rows.append({"k": k, "inertia": km.inertia_,
                     "sil": silhouette_score(X, km.labels_),
                     "ch": calinski_harabasz_score(X, km.labels_),
                     "db": davies_bouldin_score(X, km.labels_)})
    r = pd.DataFrame(rows)
    ke = knee(r.k.tolist(), r.inertia.tolist())
    res = {"label": label, "n": len(X), "elbow": ke,
           "sil": int(r.loc[r.sil.idxmax(), "k"]), "ch": int(r.loc[r.ch.idxmax(), "k"]),
           "db": int(r.loc[r.db.idxmin(), "k"]), "table": r}
    say(f"  {label:<14} n={len(X):>5}   elbow k={ke:<3} "
        f"silhouette k={res['sil']:<3} Calinski k={res['ch']:<3} Davies-B k={res['db']}")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="odisha_v120_handcrafted")
    args = ap.parse_args()

    per = load(args.arm)
    say("=" * 100)
    say(f"PHASE 3 STEP 2 -- k for the stand types by elbow, arm={args.arm}")
    say("=" * 100)
    if not per:
        say(f"  no stands_merged vectors for {args.arm} in {VEC}")
        return 2
    say(f"  districts: {', '.join(per)}   stands: "
        f"{ {d: len(v) for d, v in per.items()} }")
    say("")

    feats = sorted(set.intersection(*[set(v.columns) for v in per.values()]) - DROP)
    say(f"  feature bands used ({len(feats)}): {', '.join(feats)}")
    say("  no field measurement is read in this file.")
    say("")
    say("-" * 100)
    say("ELBOW, PER DISTRICT (k-means is fitted per district: one config each)")
    say("-" * 100)
    results = []
    for d, df in per.items():
        X, _ = prep(df[feats])
        results.append(sweep(X, d))

    say("")
    say("-" * 100)
    say("ELBOW, POOLED (all districts together, for a single k to set in the configs)")
    say("-" * 100)
    Xall, cols = prep(pd.concat([v[feats] for v in per.values()], ignore_index=True))
    pooled = sweep(Xall, "pooled")
    say("")
    say(f"  {'k':>3}  {'inertia':>12}  {'silhouette':>11}  {'Calinski-H':>11}  {'Davies-B':>10}")
    for _, r in pooled["table"].iterrows():
        say(f"  {int(r.k):>3}  {r.inertia:>12.1f}  {r.sil:>11.3f}  {r.ch:>11.1f}  {r.db:>10.3f}")

    elbows = [r["elbow"] for r in results]
    say("")
    say("-" * 100)
    say("RECOMMENDATION")
    say("-" * 100)
    say(f"  per-district elbows: { {r['label']: r['elbow'] for r in results} }")
    say(f"  pooled elbow:        {pooled['elbow']}")
    rec = int(round(float(np.median(elbows + [pooled["elbow"]]))))
    say(f"  -> median across district and pooled elbows: k = {rec}")
    say(f"  (the pipeline currently uses k = 6)")
    if rec != 6:
        say(f"  Changing k changes clustering, which is in the cache fingerprint, so it")
        say(f"  means re-running clustering and export for every district.")

    out = HERE / f"odisha_phase3_2_k_elbow_{args.arm}.txt"
    out.write_text("\n".join(_lines) + "\n")
    say("")
    say(f"  wrote {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
