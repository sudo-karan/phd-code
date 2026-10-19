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

The default space (--space script) was meant to mirror the clustering stage:
cyclic bands to sin/cos, skewed bands logged, then median/IQR scaling. It does
not, in five ways (review A7, 19 Oct 2026); see "Three spaces" below.

k-means is fitted PER DISTRICT in this pipeline, because each district is its
own config. So the elbow is reported per district and pooled, and one k has to
serve all four.

Three spaces (--space). The default, `script`, is this script's own
preprocessing: cyclic bands decomposed to sin/cos, skewed non-negative bands
log1p-transformed, then median/IQR scaling. Against the clustering stage: it
keeps annual_rainfall and ndvi_residual_variance, which the stage drops; it
logs only non-negative bands, by log1p, where the stage logs every band with
|skew| > 1, by log(x - min + 0.001); it keeps bands with no spread, which the
stage drops; it fits every polygon, the untyped stands and each piece of a
stand included, where the stage fits one row per typed stand; and it takes sin
and cos of the layers' mean angles. It is kept because the two committed elbow
files, odisha_phase3_2_k_elbow_<arm>.txt, are its output.

`stage` rebuilds the clustering stage's rows from the same stand layers
(stage_stands, stage_space) and gives the elbow in two geometries side by side,
naming neither as the one of record: (i) the declared one, the stage's
preprocessing then (x - median)/IQR (DEC-003); (ii) the one wekaKMeans fits
in, each band min-max normalised over the fit rows (review A2). It writes
odisha_phase3_2_k_elbow_<arm>_stage.txt. The layers hold arithmetic means of
aspect and ndvi_phase_annual (review C10), while the stage takes sin and cos per
pixel before the mean, so the last of the five departures above is one no
rebuild from the layers can remove.

`stage-rows` reads the clustering stage's own k-means rows of the _repro runs,
saved off git by scripts/remerge_demo_set.py (--demo-dir, outputs/demo by
default), gives the elbow on them in both geometries, checks the rebuild's
rules on them, and puts the `stage` rebuild of the same stands beside them. It
writes odisha_phase3_2_k_elbow_<arm>_stage_rows.txt.

Usage: python odisha_script/odisha_phase3_2_stand_k_elbow.py [--arm odisha_v120_handcrafted]
           [--space script|stage|stage-rows] [--demo-dir outputs/demo]
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.cluster import KMeans
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score

HERE = Path(__file__).parent
VEC = HERE / "phase2_vectors"
SEED = 42
K_RANGE = range(2, 13)
DROP = {"area_ha", "n_pixels", "perim_m", "centroid_lat", "centroid_lon",
        "stand_id", "stand_lbl", "cluster_id", "unit_id", "snic_label"}
CYCLIC = {"aspect", "ndvi_phase_annual", "nirv_phase_annual"}
# The clustering stage's two constants: log(x - min + LOG_EPSILON) in _apply_log_transform, and
# a band whose spread is at most SPREAD_EPSILON dropped as constant in _apply_scaling.
LOG_EPSILON = 1e-3
SPREAD_EPSILON = 1e-9
# The districts of the _repro runs whose rows --space stage-rows reads.
DISTRICTS = ("angul", "dhenkanal", "kendujhar", "koraput")
# A stand in several pieces: the stage's row is told to come from one piece when that piece is
# nearer to it than a fifth of the distance to every other piece (--space stage-rows).
TOLD_APART = 5.0
# The label column of the sweep lines the two new spaces print (the script's own keeps 14).
WIDE = 20
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
    """The script's own space (--space script). Meant to mirror the clustering stage: cyclic ->
    sin/cos, log skewed, median/IQR. It departs from it in five ways (review A7; module docstring)."""
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


def sweep_numbers(x: np.ndarray) -> dict:
    """k-means for every k of K_RANGE below the number of rows (seed 42, 25 starts), the knee of
    the inertia curve and the k each of three other indices prefers."""
    rows = []
    for k in K_RANGE:
        if k >= len(x):
            break
        km = KMeans(n_clusters=k, random_state=SEED, n_init=25).fit(x)
        rows.append({"k": k, "inertia": km.inertia_,
                     "sil": silhouette_score(x, km.labels_),
                     "ch": calinski_harabasz_score(x, km.labels_),
                     "db": davies_bouldin_score(x, km.labels_)})
    r = pd.DataFrame(rows)
    ke = knee(r.k.tolist(), r.inertia.tolist())
    return {"n": len(x), "elbow": ke,
            "sil": int(r.loc[r.sil.idxmax(), "k"]), "ch": int(r.loc[r.ch.idxmax(), "k"]),
            "db": int(r.loc[r.db.idxmin(), "k"]), "table": r}


def sweep(X: np.ndarray, label: str, width: int = 14) -> dict:
    res = {"label": label, **sweep_numbers(X)}
    say(f"  {label:<{width}} n={len(X):>5}   elbow k={res['elbow']:<3} "
        f"silhouette k={res['sil']:<3} Calinski k={res['ch']:<3} Davies-B k={res['db']}")
    return res


# ---------------------------------------------------------------------------------------------
# --space stage: the clustering stage's rows, rebuilt from the stand layers
# ---------------------------------------------------------------------------------------------


def stage_bands(columns) -> list[str]:
    """The layer's columns the clustering stage clusters on, before the sin/cos split.

    Every feature band of the layer but those the stage excludes (clustering._EXCLUDE_BANDS:
    annual_rainfall, the harmonic fit's residual variance, the observation counts). Columns
    that are not features are left out: DROP, and the merge's provenance
    (region_merge.PROVENANCE_FIELDS), which later layers carry.
    """
    from fmu.stages.clustering import _EXCLUDE_BANDS
    from fmu.utils.region_merge import PROVENANCE_FIELDS

    skip = DROP | set(PROVENANCE_FIELDS) | set(_EXCLUDE_BANDS)
    return sorted(c for c in columns if c not in skip)


def is_cyclic(band: str) -> bool:
    """clustering._decompose_cyclic_bands' rule: aspect (degrees) and every *_phase_* band (radians)."""
    return "_phase_" in band or band == "aspect"


def stage_stands(layer: pd.DataFrame) -> pd.DataFrame:
    """One row per stand with a type in the layer: the stand's largest piece, in stand_id order.

    The stage averages the features over each connected piece of a stand (review B14) and takes
    one row per stand, at a pixel drawn inside the habitat mask, so a stand in several pieces
    enters with one piece's means. The largest piece (most pixels; ties to the lowest
    stand_id) is the one such a pixel most likely falls in; --space stage-rows counts which
    piece the stage's own rows came from. A stand has a type where its cluster_id is not null.
    """
    typed = layer[layer["cluster_id"].notna()]
    largest = typed.sort_values(["stand_lbl", "n_pixels", "stand_id"],
                                ascending=[True, False, True], kind="mergesort")
    return largest.drop_duplicates("stand_lbl", keep="first").sort_values("stand_id", kind="mergesort")


def decompose(stands: pd.DataFrame, bands: list[str]) -> pd.DataFrame:
    """The bands as the stage clusters them: each cyclic band replaced by its sin and its cos."""
    out: dict[str, np.ndarray] = {}
    for b in bands:
        v = pd.to_numeric(stands[b], errors="raise").to_numpy(float)
        if np.isnan(v).any():
            raise ValueError(f"{b}: a stand with a type has no value; the stage's rows have none")
        if is_cyclic(b):
            rad = np.deg2rad(v) if b == "aspect" else v
            out[f"{b}_sin"], out[f"{b}_cos"] = np.sin(rad), np.cos(rad)
        else:
            out[b] = v
    return pd.DataFrame(out, index=stands.index)


def skewness(values, *, adjusted: bool = True) -> float:
    """Sample skewness of a band over the rows; 0 for a band with no spread.

    adjusted=True gives the adjusted Fisher-Pearson coefficient G1 (pandas' skew), False the
    moment coefficient g1. Which of the two Earth Engine's Reducer.skew computes is not
    documented; --space stage-rows checks both against the stage's own log decisions.
    """
    x = np.asarray(values, float)
    n = len(x)
    if n < 3 or np.all(x == x[0]):
        return 0.0
    d = x - x.mean()
    m2 = float(np.mean(d ** 2))
    if m2 <= 0:
        return 0.0
    g1 = float(np.mean(d ** 3)) / m2 ** 1.5
    return g1 * float(np.sqrt(n * (n - 1))) / (n - 2) if adjusted else g1


def log_skewed(table: pd.DataFrame, threshold: float, *,
               adjusted: bool = True) -> tuple[pd.DataFrame, list[str], dict[str, float]]:
    """clustering._identify_skewed_bands and _apply_log_transform on the rows: every band whose
    |skew| (G1, or g1 with adjusted=False) exceeds the threshold becomes log(x - min + 0.001),
    min over the same rows."""
    out = table.copy()
    logged: list[str] = []
    offsets: dict[str, float] = {}
    for c in table.columns:
        v = table[c].to_numpy(float)
        if abs(skewness(v, adjusted=adjusted)) > threshold:
            offsets[c] = -float(v.min()) + LOG_EPSILON
            out[c] = np.log(v + offsets[c])
            logged.append(c)
    return out, logged, offsets


def stage_space(stands: pd.DataFrame, bands: list[str], *, threshold: float,
                fit: np.ndarray | None = None, adjusted: bool = True) -> dict:
    """The stage's preprocessing on one set of rows, and its fit rows in the two geometries.

    `stands` holds one row per stand (stage_stands), `bands` the stage's bands (stage_bands),
    `fit` which rows k-means is trained on (every row when None), `adjusted` which skewness
    decides the log (G1; g1 when False). As in the stage, the skew, the log offsets and the
    median and IQR are taken over every row; only the fit leaves rows out
    (clustering.fit_excludes_stands_below_min_area).

    (i)  "declared": (x - median) / IQR, both exact over the rows (the stage took them from
         Earth Engine's percentile reducer, review B16). A band whose IQR is at most 1e-9 is
         dropped, as the stage drops a band with no spread.
    (ii) "fit_geometry": the same post-log bands, each min-max normalised over the fit rows,
         which is what wekaKMeans' distance does to its training rows (review A2). It does not
         depend on any per-band scaling before it. A band with no range over the fit rows is 0.

    What a layer cannot give exactly, so that these rows approximate the stage's:
      - the stage takes sin and cos of aspect and of the phase per pixel and then the mean;
        the layer holds the arithmetic mean of each angle (review C10);
      - a layer's values are the export's mean over each polygon, by pixel share; on the legacy
        cache layout (the runs before round 9) the features lay on another grid than the
        polygons, so a polygon's mean takes in slivers of its neighbours;
      - a stand typed in a layer of the legacy layout need not have had a row in the fit: the
        export's vote could give a stand with no pixel in the habitat mask a neighbour's type
        (docs/demo/remerge/README.md, section 4), and the layer does not say which;
      - the stage's median and IQR are Earth Engine's percentiles (review B16) and its skewness
        estimator is not documented.
    --space stage-rows measures what these do to the elbow on stands where both exist.
    """
    decomposed = decompose(stands, bands)
    post, logged, offsets = log_skewed(decomposed, threshold, adjusted=adjusted)
    q = post.quantile([0.25, 0.5, 0.75])
    centre, spread = q.loc[0.5], q.loc[0.75] - q.loc[0.25]
    active = [c for c in post.columns if spread[c] > SPREAD_EPSILON]
    rows = np.ones(len(post), bool) if fit is None else np.asarray(fit, bool)
    fitted = post[active][rows]
    lo, hi = fitted.min(), fitted.max()
    width = hi - lo
    disagree = [c for c in decomposed.columns
                if (abs(skewness(decomposed[c], adjusted=True)) > threshold)
                != (abs(skewness(decomposed[c], adjusted=False)) > threshold)]
    return {
        "n_rows": len(post), "n_fit": int(rows.sum()), "bands": active,
        "logged": logged, "offsets": offsets,
        "dropped": [c for c in post.columns if c not in active],
        "skew_estimators_disagree": disagree,
        "declared": ((fitted - centre[active]) / spread[active]).to_numpy(float),
        "fit_geometry": ((fitted - lo) / width.where(width > 0, 1.0)).to_numpy(float),
    }


def fit_rows(stands: pd.DataFrame, leave_out_below_min: bool) -> np.ndarray:
    """Which rows k-means is trained on: every row, or, with
    clustering.fit_excludes_stands_below_min_area on, all but the stands the merge left below
    merge.min_area_ha (below_min, the merge's own flag, which only later layers carry)."""
    if not leave_out_below_min:
        return np.ones(len(stands), bool)
    if "below_min" not in stands.columns:
        raise ValueError("clustering.fit_excludes_stands_below_min_area is on, and the layer does not "
                         "say which stands the merge left below the minimum (no below_min)")
    return pd.to_numeric(stands["below_min"]).to_numpy() != 1


def stage_settings(config_paths: list[Path]) -> tuple[float, bool]:
    """The clustering settings the stage read: the skewness threshold, and whether the stands
    below the minimum were left out of the fit. One value across the configs, robust scaling."""
    from fmu.config import load_config

    cfgs = [load_config(p) for p in config_paths]
    if any(c.normalization.method != "robust" for c in cfgs):
        raise ValueError("normalization.method is not robust in every config; only robust is mirrored")
    thresholds = {c.clustering.skewness_threshold for c in cfgs}
    leave_out = {c.clustering.fit_excludes_stands_below_min_area for c in cfgs}
    if len(thresholds) != 1 or len(leave_out) != 1:
        raise ValueError("the configs differ in clustering.skewness_threshold or "
                         "clustering.fit_excludes_stands_below_min_area")
    return thresholds.pop(), leave_out.pop()


def _configured_k(arm: str, districts) -> list[int]:
    return sorted({yaml.safe_load((HERE.parent / "configs" / f"{arm}_{d}.yaml").read_text())
                   ["clustering"]["k"] for d in districts})


def _say_side_by_side(results: dict[str, tuple], rows: list[tuple[str, int]]) -> None:
    """One line per (label, index into each results tuple), one column per district."""
    names = list(results)
    say("  " + f"{'':<28}" + "".join(f"{n:>11}" for n in names))
    for label, i in rows:
        say("  " + f"{label:<28}" + "".join(f"{results[n][i]['elbow']:>11}" for n in names))


def main_stage(arm: str) -> int:
    per = load(arm)
    say("=" * 100)
    say(f"PHASE 3 STEP 2 -- k for the stand types by elbow, arm={arm}, in the clustering stage's space")
    say("=" * 100)
    if not per:
        say(f"  no stands_merged vectors for {arm} in {VEC}")
        return 2
    threshold, leave_out = stage_settings([HERE.parent / "configs" / f"{arm}_{d}.yaml" for d in per])
    bands = stage_bands(set.intersection(*[set(v.columns) for v in per.values()]))
    stands = {d: stage_stands(v) for d, v in per.items()}
    fit = {d: fit_rows(s, leave_out) for d, s in stands.items()}
    say(f"  districts: {', '.join(per)}   polygons: { {d: len(v) for d, v in per.items()} }")
    say(f"  rows, one per stand with a type (its largest piece): { {d: len(s) for d, s in stands.items()} }")
    say(f"  feature bands ({len(bands)}): {', '.join(bands)}")
    say(f"  as sin/cos pairs: {', '.join(b for b in bands if is_cyclic(b))}, from the layers' arithmetic "
        f"mean angles;")
    say("    the stage takes sin and cos per pixel, before the mean (review C10)")
    say(f"  from the configs: skewness threshold {threshold}, robust scaling, stands below the "
        f"minimum left out of the fit: {'yes' if leave_out else 'no'}")
    say("  no field measurement is read in this file.")
    say("")

    inputs = {d: (stands[d], fit[d]) for d in per}
    inputs["pooled"] = (pd.concat(list(stands.values()), ignore_index=True),
                        np.concatenate(list(fit.values())))
    spaces = {name: stage_space(rows, bands, threshold=threshold, fit=fit_mask)
              for name, (rows, fit_mask) in inputs.items()}
    say("-" * 100)
    say("PREPROCESSING, AS THE CLUSTERING STAGE (each district on its own rows; pooled on all rows)")
    say("-" * 100)
    for name, s in spaces.items():
        say(f"  {name:<10} rows {s['n_rows']}, fit rows {s['n_fit']}, bands {len(s['bands'])}")
        say(f"  {'':<10} logged ({len(s['logged'])}): {', '.join(s['logged']) or 'none'}")
        say(f"  {'':<10} dropped, IQR 0 ({len(s['dropped'])}): {', '.join(s['dropped']) or 'none'}")
        if s["skew_estimators_disagree"]:
            say(f"  {'':<10} |skew| above {threshold} by G1 or g1 only: "
                f"{', '.join(s['skew_estimators_disagree'])}")
    say("")
    say("-" * 100)
    say("ELBOW IN TWO GEOMETRIES (k-means: seed 42, 25 starts, k 2 to 12; the knee of the inertia curve)")
    say("  (i)  declared: the stage's preprocessing, then (x - median) / IQR over the rows (DEC-003)")
    say("  (ii) the fit's: the stage's preprocessing, then each band min-max normalised over the fit")
    say("       rows, as wekaKMeans does (review A2)")
    say("-" * 100)
    results = {name: (sweep(s["declared"], f"{name} (i)", WIDE),
                      sweep(s["fit_geometry"], f"{name} (ii)", WIDE))
               for name, s in spaces.items()}
    say("")
    say("  pooled, by k:")
    say(f"  {'k':>3}  {'(i) inertia':>12}  {'(ii) inertia':>12}")
    for (_, a), (_, b) in zip(results["pooled"][0]["table"].iterrows(),
                              results["pooled"][1]["table"].iterrows(), strict=True):
        say(f"  {int(a.k):>3}  {a.inertia:>12.1f}  {b.inertia:>12.3f}")
    differ = [name for name, s in spaces.items() if s["skew_estimators_disagree"]]
    if differ:
        say("")
        say("  where G1 and g1 disagree on a band's log (Earth Engine's estimator is not documented),")
        say("  the same with g1:")
        for name in differ:
            rows, fit_mask = inputs[name]
            alt = stage_space(rows, bands, threshold=threshold, fit=fit_mask, adjusted=False)
            sweep(alt["declared"], f"{name} (i) g1", WIDE)
            sweep(alt["fit_geometry"], f"{name} (ii) g1", WIDE)
    say("")
    say("-" * 100)
    say("ELBOWS SIDE BY SIDE")
    say("-" * 100)
    _say_side_by_side(results, [("(i) declared", 0), ("(ii) the fit's (min-max)", 1)])
    say(f"  k in the configs: {', '.join(str(k) for k in _configured_k(arm, per))}. No k is chosen here.")

    out = HERE / f"odisha_phase3_2_k_elbow_{arm}_stage.txt"
    out.write_text("\n".join(_lines) + "\n")
    say("")
    say(f"  wrote {out.name}")
    return 0


# ---------------------------------------------------------------------------------------------
# --space stage-rows: the clustering stage's own rows of the _repro runs (off git)
# ---------------------------------------------------------------------------------------------


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_stage_rows(path: Path) -> dict:
    """A clustering_old.json of scripts/remerge_demo_set.py: the stage's metadata, its active
    bands, and its k-means rows, each [stand label, scaled value of every active band]."""
    saved = json.loads(path.read_text())
    rows = saved["rows"]
    return {"metadata": saved["metadata"], "bands": list(saved["bands"]),
            "labels": [int(r[0]) for r in rows],
            "scaled": np.array([r[1:] for r in rows], float)}


def unscale(stage: dict) -> pd.DataFrame:
    """The rows before the stage's scaling (after its log), from its recorded centre and spread."""
    sc = stage["metadata"]["scaling"]
    return pd.DataFrame({b: stage["scaled"][:, j] * sc[b]["spread"] + sc[b]["center"]
                         for j, b in enumerate(stage["bands"])}, index=stage["labels"])


def unlog(stage: dict, post: pd.DataFrame) -> pd.DataFrame:
    """The rows before the stage's log, from its recorded offsets."""
    md = stage["metadata"]
    pre = post.copy()
    for b in md["log_transformed_bands"]:
        if b in pre.columns:
            pre[b] = np.exp(post[b]) - md["log_offsets"][b]
    return pre


def check_stage_rules(stage: dict, threshold: float) -> dict:
    """The rebuild's rules against the stage's own decisions, on the stage's own rows.

    Only the active bands are in the rows, so the bands the stage dropped are not checked.
    """
    md = stage["metadata"]
    post = unscale(stage)
    pre = unlog(stage, post)
    logged = set(md["log_transformed_bands"])
    out: dict = {}
    for name, adjusted in (("G1", True), ("g1", False)):
        out[name] = [b for b in pre.columns
                     if (abs(skewness(pre[b], adjusted=adjusted)) > threshold) != (b in logged)]
    out["offsets"] = [b for b in pre.columns if b in logged
                      and not np.isclose(-float(pre[b].min()) + LOG_EPSILON, md["log_offsets"][b],
                                         rtol=1e-9, atol=1e-9)]
    q = post.quantile([0.25, 0.75])
    exact_iqr = q.loc[0.75] - q.loc[0.25]
    ratio = np.array([md["scaling"][b]["spread"] / exact_iqr[b] for b in post.columns])
    out["spread_ratio"] = (float(ratio.min()), float(ratio.max()))
    return out


def which_piece(stage: dict, layer: pd.DataFrame) -> dict[str, int]:
    """For each stand in several typed pieces with a row in the stage's fit: the piece whose
    layer values are nearest the row (non-cyclic bands, the stage's pre-log values, in units of
    each band's IQR over the rows). Counted as the largest piece, another piece, or not told
    apart (TOLD_APART)."""
    pre = unlog(stage, unscale(stage))
    cols = [b for b in pre.columns if b in layer.columns and not is_cyclic(b)]
    q = pre[cols].quantile([0.25, 0.75])
    unit = (q.loc[0.75] - q.loc[0.25]).replace(0, np.nan)
    counts = {"largest": 0, "another": 0, "not_told_apart": 0}
    typed = layer[layer["cluster_id"].notna()]
    for lbl, pieces in typed.groupby("stand_lbl"):
        if len(pieces) < 2 or int(lbl) not in pre.index:
            continue
        row = pre.loc[int(lbl), cols]
        dist = [float(np.nansum(np.abs((pieces.iloc[i][cols].astype(float) - row) / unit)))
                for i in range(len(pieces))]
        order = np.argsort(dist)
        if dist[order[1]] <= TOLD_APART * dist[order[0]]:
            counts["not_told_apart"] += 1
        elif int(order[0]) == int(np.argmax(pieces["n_pixels"].to_numpy())):
            counts["largest"] += 1
        else:
            counts["another"] += 1
    return counts


def _exact_declared(post: pd.DataFrame) -> np.ndarray:
    q = post.quantile([0.25, 0.5, 0.75])
    return ((post - q.loc[0.5]) / (q.loc[0.75] - q.loc[0.25])).to_numpy(float)


def _min_max(post: pd.DataFrame) -> np.ndarray:
    lo, hi = post.min(), post.max()
    width = hi - lo
    return ((post - lo) / width.where(width > 0, 1.0)).to_numpy(float)


def main_stage_rows(arm: str, demo_dir: Path) -> int:
    say("=" * 100)
    say(f"PHASE 3 STEP 2 -- k for the stand types by elbow, arm={arm}, on the clustering stage's own rows")
    say("=" * 100)
    runs = {d: f"{arm}_{d}_repro" for d in DISTRICTS}
    rows_files = {d: Path("remerge") / r / "clustering_old.json" for d, r in runs.items()}
    layer_files = {d: Path("vectors_old") / f"{r}_stands_merged.geojson" for d, r in runs.items()}
    missing = [str(p) for p in [*rows_files.values(), *layer_files.values()] if not (demo_dir / p).exists()]
    if missing:
        say(f"  not found under --demo-dir (off git, written by scripts/remerge_demo_set.py --all): "
            f"{', '.join(missing)}")
        return 2
    stage = {d: read_stage_rows(demo_dir / rows_files[d]) for d in DISTRICTS}
    layers = {d: pd.DataFrame([ft["properties"] for ft in
                               json.loads((demo_dir / layer_files[d]).read_text())["features"]])
              for d in DISTRICTS}
    say("  rows: the k-means rows of the clustering stage fitted again, every input read from the")
    say("    cache, on the stands of the _repro runs (scripts/remerge_demo_set.py, the old rule;")
    say("    docs/demo/remerge/README.md). Not the stands of record in phase2_vectors, nor the fit that")
    say("    typed them. Off git, in the folder the README names (outputs/demo):")
    for d in DISTRICTS:
        p = demo_dir / rows_files[d]
        say(f"    {str(rows_files[d]):<58} {len(stage[d]['labels']):>5} rows  {p.stat().st_size:>9} bytes")
        say(f"    {'':<58} sha256 {sha256(p)}")
    say("  the same runs' stand layers, for the rebuild from the layers on the same stands:")
    for d in DISTRICTS:
        p = demo_dir / layer_files[d]
        say(f"    {str(layer_files[d]):<58} {len(layers[d]):>5} polygons  {p.stat().st_size:>9} bytes")
        say(f"    {'':<58} sha256 {sha256(p)}")
    say("  no field measurement is read in this file.")
    say("")

    say("-" * 100)
    say("THE REBUILD'S RULES, CHECKED ON THE STAGE'S OWN ROWS")
    say("-" * 100)
    settings = {d: stage_settings([HERE.parent / "configs" / f"{runs[d]}.yaml"]) for d in DISTRICTS}
    for d in DISTRICTS:
        threshold, _ = settings[d]
        md = stage[d]["metadata"]
        c = check_stage_rules(stage[d], threshold)
        p = which_piece(stage[d], layers[d])
        say(f"  {d:<10} logged by the stage ({len(md['log_transformed_bands'])}): "
            f"{', '.join(md['log_transformed_bands']) or 'none'}; dropped: "
            f"{', '.join(md['dropped_constant_bands']) or 'none'}")
        say(f"  {'':<10} its log decisions on the active bands, by |G1| > {threshold}: "
            f"{'all reproduced' if not c['G1'] else 'not ' + ', '.join(c['G1'])}; by |g1|: "
            f"{'all reproduced' if not c['g1'] else 'not ' + ', '.join(c['g1'])}")
        say(f"  {'':<10} its log offsets = -min over the rows + 0.001: "
            f"{'all' if not c['offsets'] else 'not ' + ', '.join(c['offsets'])}")
        say(f"  {'':<10} its spread against the exact IQR of its own post-log rows: "
            f"{c['spread_ratio'][0]:.3f} to {c['spread_ratio'][1]:.3f} (review B16)")
        say(f"  {'':<10} stands in several typed pieces with a row: the row is the largest piece's "
            f"in {p['largest']}, another piece's in {p['another']}, not told apart in {p['not_told_apart']}")
    say("")

    say("-" * 100)
    say("ELBOW (k-means: seed 42, 25 starts, k 2 to 12; the knee of the inertia curve)")
    say("  on the stage's own rows:")
    say("    (i) as scaled:  the rows as the stage scaled them (its recorded centre and spread)")
    say("    (i) exact:      the same post-log rows, (x - median) / IQR with exact quantiles (DEC-003)")
    say("    (ii):           the same post-log rows, each band min-max normalised over the rows, as")
    say("                    wekaKMeans does (review A2)")
    say("  rebuilt from the same runs' layers by --space stage's rules: layer (i), layer (ii)")
    say("-" * 100)
    results: dict[str, tuple] = {}
    for d in DISTRICTS:
        post = unscale(stage[d])
        as_scaled = sweep(stage[d]["scaled"], f"{d} rows (i)s", WIDE)
        committed = json.loads((HERE.parent / "docs" / "demo" / "remerge" / f"{runs[d]}.json")
                               .read_text())["elbow"]["old"]
        if ([round(float(v), 6) for v in as_scaled["table"].inertia] != committed["inertia"]
                or as_scaled["elbow"] != committed["elbow_k"]):
            raise SystemExit(f"{runs[d]}: these rows do not give the elbow committed in "
                             f"docs/demo/remerge/{runs[d]}.json")
        exact = sweep(_exact_declared(post), f"{d} rows (i)x", WIDE)
        minmax = sweep(_min_max(post), f"{d} rows (ii)", WIDE)
        threshold, leave_out = settings[d]
        stands = stage_stands(layers[d])
        rebuilt = stage_space(stands, stage_bands(layers[d].columns), threshold=threshold,
                              fit=fit_rows(stands, leave_out))
        in_both = len(set(int(v) for v in stands["stand_lbl"]) & set(stage[d]["labels"]))
        say(f"  {'':<{WIDE}} rebuilt from the layer: {rebuilt['n_fit']} rows, {in_both} of them stands "
            f"with a row in the stage's fit; logged ({len(rebuilt['logged'])}): "
            f"{', '.join(rebuilt['logged']) or 'none'}"
            + (f"; G1 and g1 disagree on {', '.join(rebuilt['skew_estimators_disagree'])}"
               if rebuilt["skew_estimators_disagree"] else ""))
        layer_i = sweep(rebuilt["declared"], f"{d} layer (i)", WIDE)
        layer_ii = sweep(rebuilt["fit_geometry"], f"{d} layer (ii)", WIDE)
        results[d] = (as_scaled, exact, minmax, layer_i, layer_ii)
    say("  (i)s: as the stage scaled them; (i)x: exact quantiles. Each (i)s line gives the inertia and")
    say("  the elbow committed in docs/demo/remerge/<run>.json (elbow.old), checked to 6 decimals.")
    say("")
    say("-" * 100)
    say("ELBOWS SIDE BY SIDE (pooled: none; the stage scales each district's rows on their own)")
    say("-" * 100)
    _say_side_by_side(results, [("stage rows (i) as scaled", 0), ("stage rows (i) exact", 1),
                                ("stage rows (ii) min-max", 2), ("rebuilt from layer (i)", 3),
                                ("rebuilt from layer (ii)", 4)])
    say(f"  k in the configs: {', '.join(str(k) for k in _configured_k(arm, DISTRICTS))}. "
        f"No k is chosen here.")

    out = HERE / f"odisha_phase3_2_k_elbow_{arm}_stage_rows.txt"
    out.write_text("\n".join(_lines) + "\n")
    say("")
    say(f"  wrote {out.name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="odisha_v120_handcrafted")
    ap.add_argument("--space", choices=("script", "stage", "stage-rows"), default="script")
    ap.add_argument("--demo-dir", type=Path, default=HERE.parent / "outputs" / "demo")
    args = ap.parse_args()
    if args.space == "stage":
        return main_stage(args.arm)
    if args.space == "stage-rows":
        return main_stage_rows(args.arm, args.demo_dir)

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
    # the k the arm's configs actually carry, read rather than assumed: the two arms differ
    in_use = sorted({yaml.safe_load((HERE.parent / "configs" / f"{args.arm}_{d}.yaml").read_text())
                     ["clustering"]["k"] for d in per})
    if len(in_use) == 1:
        say(f"  (the pipeline currently uses k = {in_use[0]})")
    else:
        say(f"  (the districts' configs disagree on k: {in_use})")
    if in_use != [rec]:
        say(f"  Changing k changes clustering, which is in the cache fingerprint, so it")
        say(f"  means re-running clustering and export for every district.")

    out = HERE / f"odisha_phase3_2_k_elbow_{args.arm}.txt"
    out.write_text("\n".join(_lines) + "\n")
    say("")
    say(f"  wrote {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
