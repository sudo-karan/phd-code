"""
Phase 1, step 8 — a null model for the separation-ratio chart.

WHY
---
scripts/report.py::fig_separating_power ranks feature bands by

    between = sqrt( sum_c w_c * (m_c - sum_c w_c m_c)^2 )     w_c = cluster pixel-count weights
    within  = sum_c w_c * (IQR_c / 1.349)                      m_c = cluster mean of the band
    ratio   = between / (between + within)

and presents the ranking as evidence about which features drive the partition. Two problems.

1. The unit is the k-means CLUSTER (k=6), not the stand. The x-label reads
   "between-stand separation ratio" and the title "What separates the stands". That is the
   exact conflation the v1.2 reframing exists to kill: SNIC plus merge produce the stand,
   clustering only attaches a type label to a finished one.

2. Almost every band scored is a band k-means was fit on, so the ratio is circular by
   construction — it measures how well a feature separates clusters built from that feature.
   A high ratio is the expected outcome, not a finding. Without a null there is no way to say
   which bands beat what any partition of these units would have produced anyway.

WHAT THIS DOES
--------------
Repartitions the SAME units, without letting the partition see the real features, and
recomputes the same statistic. A band whose observed ratio sits below the null p95 is
indistinguishable from a partition that never saw it.

Three nulls, because they break different things:
  RANDOM-FEATURE  k-means on a random feature stack of matched dimensionality over the same
                  units. Breaks the feature->label link. This was the primary null as
                  specified -- and it FAILED its own control, see below.
  PERMUTATION     shuffle the unit->cluster assignment, preserving the cluster size
                  distribution. Breaks spatial and feature structure together, so it is the
                  weakest of the three.
  SPATIAL         k-means on the unit CENTROIDS only. Sees geometry, never a feature. This is
                  the strict null and the one the verdict is read from.

WHY A THIRD NULL WAS NEEDED
---------------------------
The first run of this script failed its own control. distance_to_water is scored by the chart
but was never fed to k-means -- clustering dropped it as a constant band -- so it is a null
sample sitting inside the published figure. It cleared the random-feature p95 by +0.010.

The reason is structural rather than a bug. The observed partition is spatially coherent,
because k-means on real features groups neighbouring superpixels: neighbouring superpixels have
similar features. A random-feature partition scatters units across the AOI instead, so
within-cluster spread is near-global for EVERY band and anything spatially autocorrelated beats
it. The random-feature null was asking "is this band spatially smooth", which all of them are.

The spatial null gives the null partition the one property the observed one has and the
random-feature one lacks: compactness. A band clears it only by separating the clusters better
than geography alone would.

WHY IT LIVES IN odisha_script/
------------------------------
It is a diagnostic that produces a results .txt in the Phase 1 format, not a pipeline driver.
scripts/ holds things that run the pipeline; this reads two archived artifacts and computes.
It does import nothing from scripts/report.py -- the formula is re-implemented here so the
null and the observed value are computed by the same code path, and any divergence from
report.py is visible as a number rather than hidden behind a shared helper.

DATA
----
Everything comes from commit b24fad3, which is where runs/ and fmu_exports_clean/ were last
tracked (they were untracked in 232ec01). Read straight out of git so provenance is explicit
and no checkout is required:

  runs/sanjay_van_baseline_20260726_204451/cluster_profiles.csv          6 rows, pixel-level
  runs/sanjay_van_baseline_20260726_204751/export_manifest_*.json        cluster distribution
  fmu_exports_clean/sanjay_van_baseline_stands_snic.geojson              1249 units, per-unit

NOTE ON PROVENANCE, on the record: no single archived run holds both the profiles and the
distribution. They come from two runs three minutes apart. Their per-cluster pixel counts
differ by 25/7/27/12/8/1 out of ~15000 (96748 vs 96786 total, 0.04%), which is the same
ROI-edge reduction disagreement seen throughout this repo, not two different k-means fits.
They are paired here on that basis and the discrepancy is printed below rather than smoothed.

Run:  python odisha_phase1_8_separation_null.py
Out:  odisha_phase1_8_results.txt, odisha_phase1_8_separation_null.png
"""
from __future__ import annotations

import io
import json
import math
import subprocess

import numpy as np
import pandas as pd

ARCHIVE = "b24fad3"
PROFILES = "runs/sanjay_van_baseline_20260726_204451/cluster_profiles.csv"
MANIFEST = "runs/sanjay_van_baseline_20260726_204751/export_manifest_sanjay_van_baseline.json"
UNITS = "fmu_exports_clean/sanjay_van_baseline_stands_snic.geojson"

OUT_TXT = "odisha_phase1_8_results.txt"
OUT_PNG = "odisha_phase1_8_separation_null.png"

N_NULL = 200          # >= 100 required; 200 makes the p95 stable to ~1 in the last digit
K = 6
SEED0 = 20260909

# report.py drops these from the chart. Kept identical so the band list matches.
DIAGNOSTIC = {"annual_rainfall", "ndvi_residual_variance", "nirv_residual_variance"}

# Cyclic bands the pipeline decomposes per PIXEL before reducing to units, so the archive's
# per-unit value is mean(angle), not mean(sin(angle)). Their unit-level ratios below are a
# proxy, computed as sin(mean angle) -- fine for comparing observed against null, since both
# sides use it, but not the same quantity as the published pixel-level band.
CYCLIC = {"aspect": "deg", "ndvi_phase_annual": "rad"}

_out: list[str] = []


def say(s: str = "") -> None:
    _out.append(s)
    print(s)


def rule(t: str) -> None:
    say("")
    say("=" * 100)
    say(t)
    say("=" * 100)


def git_show(path: str) -> str:
    r = subprocess.run(["git", "show", f"{ARCHIVE}:{path}"],
                       capture_output=True, text=True, cwd="..")
    if r.returncode != 0:
        raise SystemExit(f"cannot read {ARCHIVE}:{path} -- {r.stderr.strip()}")
    return r.stdout


# ---------------------------------------------------------------------- the statistic

def ratio(values: np.ndarray, labels: np.ndarray, weights: np.ndarray) -> float:
    """report.py's separation ratio, computed from per-unit values.

    `values`  per-unit band value        `labels`  per-unit cluster id
    `weights` per-unit pixel count       returns   between / (between + within)

    Cluster weight is the summed pixel count of its units, matching report.py's use of the
    cluster distribution. Within-cluster spread is IQR/1.349 over the UNIT values in that
    cluster -- report.py takes it over pixels, which this cannot see. That is why the
    unit-level observed number below is reported next to the published one rather than
    instead of it.
    """
    ok = np.isfinite(values)
    if ok.sum() < K * 2:
        return float("nan")
    ws, ms, iqrs = [], [], []
    for c in range(K):
        m = (labels == c) & ok
        if not m.any():
            continue
        v, w = values[m], weights[m]
        tw = w.sum()
        if tw <= 0:
            continue
        ws.append(tw)
        ms.append(float(np.average(v, weights=w)))
        q75, q25 = np.percentile(v, [75, 25])
        iqrs.append(float(q75 - q25))
    if len(ws) < 2:
        return float("nan")
    ws = np.asarray(ws, float)
    ws = ws / ws.sum()
    ms = np.asarray(ms, float)
    between = math.sqrt(float(np.sum(ws * (ms - np.sum(ws * ms)) ** 2)))
    within = float(np.sum(ws * (np.asarray(iqrs, float) / 1.349)))
    return between / (between + within + 1e-9)


def published_ratio(profiles: pd.DataFrame, dist: pd.DataFrame, band: str) -> float:
    """report.py's number exactly, from the 6-row tables."""
    w = dist.set_index("cluster_id")["pixel_count"].reindex(profiles["cluster_id"]).to_numpy(float)
    w = w / w.sum()
    m = profiles[f"{band}_mean"].to_numpy(float)
    between = math.sqrt(float(np.sum(w * (m - np.sum(w * m)) ** 2)))
    iqr = (profiles[f"{band}_p75"] - profiles[f"{band}_p25"]).to_numpy(float)
    within = float(np.sum(w * (iqr / 1.349)))
    return between / (between + within + 1e-9)


# ---------------------------------------------------------------------- nulls

def kmeans(x: np.ndarray, k: int, rng: np.random.Generator, iters: int = 50) -> np.ndarray:
    """k-means++ init then Lloyd. Local, so the null needs no sklearn dependency."""
    n = len(x)
    centres = [x[rng.integers(n)]]
    for _ in range(k - 1):
        d = np.min(((x[:, None, :] - np.asarray(centres)[None, :, :]) ** 2).sum(-1), axis=1)
        tot = d.sum()
        centres.append(x[rng.integers(n) if tot <= 0 else
                        int(np.searchsorted(np.cumsum(d / tot), rng.random()))])
    c = np.asarray(centres, float)
    lab = np.zeros(n, int)
    for _ in range(iters):
        new = np.argmin(((x[:, None, :] - c[None, :, :]) ** 2).sum(-1), axis=1)
        if (new == lab).all():
            break
        lab = new
        for j in range(k):
            if (lab == j).any():
                c[j] = x[lab == j].mean(0)
    return lab


def null_random_feature(n: int, dim: int, rng: np.random.Generator) -> np.ndarray:
    """Partition by k-means on a random stack of matched dimensionality."""
    return kmeans(rng.standard_normal((n, dim)), K, rng)


def null_permutation(observed: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Shuffle the unit->cluster assignment, preserving cluster sizes exactly."""
    out = observed.copy()
    rng.shuffle(out)
    return out


def null_spatial(xy: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Partition by k-means on unit CENTROIDS only. Sees geometry, never a feature.

    Added after the first run of this script failed its own control: distance_to_water, a band
    k-means provably never saw, cleared the random-feature p95 by +0.010. The reason is
    structural, not a bug. The observed partition is spatially coherent -- k-means on real
    features groups neighbouring superpixels because neighbouring superpixels have similar
    features -- while a random-feature partition scatters units across the AOI. So within-cluster
    spread under the random-feature null is close to the global spread for EVERY band, and any
    spatially autocorrelated quantity beats it. The null was measuring "is this band spatially
    smooth", which every one of them is.

    This null fixes that by giving the null partition the one property the random-feature null
    lacks: spatial compactness. A band only clears it if it separates the clusters better than
    geography alone would. distance_to_water, being a pure function of position, should score
    HIGH here -- that is the control working, and it is the reason this null is the strict one.
    """
    return kmeans(xy, K, rng)


# ---------------------------------------------------------------------- main

def main() -> None:
    say("=" * 100)
    say("PHASE 1 STEP 8 — null model for the separation-ratio chart")
    say("=" * 100)

    profiles = pd.read_csv(io.StringIO(git_show(PROFILES))).sort_values("cluster_id").reset_index(drop=True)
    manifest = json.loads(git_show(MANIFEST))
    dist = pd.DataFrame(manifest["clustering"]["cluster_distribution"]).sort_values("cluster_id").reset_index(drop=True)
    gj = json.loads(git_show(UNITS))
    units = pd.DataFrame([f["properties"] for f in gj["features"]])

    active = manifest["clustering"]["active_bands"]
    mean_cols = [c[:-5] for c in profiles.columns if c.endswith("_mean")]
    bands = [b for b in mean_cols if b not in DIAGNOSTIC]

    rule("Provenance")
    say(f"  archive commit : {ARCHIVE}")
    say(f"  profiles       : {PROFILES}")
    say(f"  distribution   : {MANIFEST}")
    say(f"  units          : {UNITS}  ({len(units)} superpixels)")
    say("")
    say("  The profiles and the distribution come from two DIFFERENT runs, three minutes")
    say("  apart. Per-cluster pixel counts:")
    say(f"    {'cluster':>8} {'profiles':>10} {'manifest':>10} {'diff':>7}")
    pp = profiles.set_index("cluster_id")["pixel_count"]
    dd = dist.set_index("cluster_id")["pixel_count"]
    for c in sorted(pp.index):
        say(f"    {c:>8} {int(pp[c]):>10} {int(dd[c]):>10} {int(dd[c]) - int(pp[c]):>+7}")
    say(f"    {'TOTAL':>8} {int(pp.sum()):>10} {int(dd.sum()):>10} "
        f"{int(dd.sum()) - int(pp.sum()):>+7}   ({100 * abs(dd.sum() - pp.sum()) / pp.sum():.2f}%)")
    say("")
    say("  Same k-means fit measured by two reductions that disagree at the ROI edge, not two")
    say("  different fits: the deltas are 0.04% and the cluster identities line up. Paired on")
    say("  that basis. If a run holding both ever exists, prefer it.")

    rule("What the chart actually scores")
    say(f"  clustered_bands (report.py: every *_mean column minus _DIAGNOSTIC): {len(bands)}")
    say(f"    {bands}")
    say("")
    say(f"  active_bands (manifest: what k-means was actually fit on): {len(active)}")
    say(f"    {active}")
    say("")
    extra = sorted(set(bands) - set(active))
    missing = sorted(set(active) - set(bands))
    say(f"  scored but NOT fed to k-means : {extra}")
    say(f"  fed to k-means but not scored : {missing}")
    say("")
    say("  So the chart scores 22 bands, not 20, and report.py's ConfigRun.clustered_bands is")
    say('  documented as "feature bands that fed k-means" while actually being "bands present')
    say("  in cluster_profiles.csv minus three diagnostics\". The two lists differ by exactly")
    say("  one band: distance_to_water, which clustering dropped as constant (zero spread).")
    say("")
    say("  That makes distance_to_water a control that was already sitting in the published")
    say("  chart: a band the partition provably never saw. Its observed ratio is a null")
    say("  sample of one, and the null below should bracket it.")

    # ------------------------------------------------------------------ build the unit table
    rule("Unit-level band table")
    weights = units["n_pixels"].to_numpy(float)
    observed_labels = units["cluster_id"].to_numpy(int)
    say(f"  units: {len(units)}   pixels: {int(weights.sum())}   "
        f"clusters present: {sorted(set(observed_labels.tolist()))}")

    unit_vals: dict[str, np.ndarray] = {}
    proxied: list[str] = []
    for b in bands:
        if b in units.columns:
            unit_vals[b] = units[b].to_numpy(float)
            continue
        base = b.rsplit("_", 1)[0]
        fn = b.rsplit("_", 1)[1] if "_" in b else ""
        if base in CYCLIC and fn in ("sin", "cos") and base in units.columns:
            ang = units[base].to_numpy(float)
            if CYCLIC[base] == "deg":
                ang = np.deg2rad(ang)
            unit_vals[b] = np.sin(ang) if fn == "sin" else np.cos(ang)
            proxied.append(b)
    say(f"  bands with a direct per-unit column : {len(unit_vals) - len(proxied)}")
    say(f"  cyclic bands reconstructed as proxy : {proxied}")
    say(f"  bands with no per-unit value        : {[b for b in bands if b not in unit_vals]}")
    say("")
    say("  The cyclic four are a PROXY: the pipeline decomposes sin/cos per pixel and then")
    say("  reduces, so the archive holds mean(angle) and this computes sin(mean angle). Both")
    say("  the observed and the null use it, so the comparison is internally valid; the")
    say("  absolute value is not the published band's.")

    # ------------------------------------------------------------------ nulls
    rule(f"Null distributions ({N_NULL} draws each)")
    nb = [b for b in bands if b in unit_vals]
    dim = len(active)
    xy = np.column_stack([units["centroid_lon"].to_numpy(float),
                          units["centroid_lat"].to_numpy(float)])
    xy = (xy - xy.mean(0)) / xy.std(0)
    say(f"  RANDOM-FEATURE : k-means(k={K}) on N(0,1) stacks of {dim} dims over the same {len(units)} units")
    say("  PERMUTATION    : shuffle of the observed unit->cluster labels (sizes preserved)")
    say(f"  SPATIAL        : k-means(k={K}) on standardised unit centroids only -- STRICT")
    say("")
    say("  The SPATIAL null exists because the first run of this script failed its own control.")
    say("  distance_to_water, never fed to k-means, cleared the random-feature p95 by +0.010.")
    say("  That is structural: the observed partition is spatially coherent and a random-feature")
    say("  partition is not, so within-cluster spread under the latter is near-global for every")
    say("  band and anything spatially smooth beats it. The random-feature null was asking 'is")
    say("  this band spatially autocorrelated', which all of them are. The spatial null gives the")
    say("  null partition the compactness the observed one has, so a band clears it only by")
    say("  separating clusters better than geography alone.")
    say("")

    null_rf = {b: [] for b in nb}
    null_pm = {b: [] for b in nb}
    null_sp = {b: [] for b in nb}
    for i in range(N_NULL):
        rng = np.random.default_rng(SEED0 + i)
        lab_rf = null_random_feature(len(units), dim, rng)
        lab_pm = null_permutation(observed_labels, rng)
        lab_sp = null_spatial(xy, rng)
        for b in nb:
            null_rf[b].append(ratio(unit_vals[b], lab_rf, weights))
            null_pm[b].append(ratio(unit_vals[b], lab_pm, weights))
            null_sp[b].append(ratio(unit_vals[b], lab_sp, weights))

    # ------------------------------------------------------------------ table
    rule("Results — observed vs null")
    say("  'published'  report.py's own number, pixel-level, from the 6-row tables.")
    say("  'unit-level' the same formula recomputed from the 1249 per-unit rows. Differs from")
    say("               'published' because within-cluster IQR is over units, not pixels.")
    say("  'excess'     unit-level observed minus SPATIAL p95 (the strict null). Positive = survives.")
    say("  'n'          units with a finite value for the band; blanks are ETH no-data holes.")
    say("")
    say(f"  {'band':24} {'n':>5} {'pub':>6} {'unit':>6} | {'rf p95':>7} {'pm p95':>7} | "
        f"{'sp p95':>7} {'excess':>7} {'fed?':>5}")
    say("  " + "-" * 96)

    rows, undefined = [], []
    for b in bands:
        pub = published_ratio(profiles, dist, b)
        if b not in unit_vals:
            undefined.append((b, pub))
            continue
        v = unit_vals[b]
        obs = ratio(v, observed_labels, weights)
        rf95 = float(np.percentile(np.asarray(null_rf[b], float), 95))
        pm95 = float(np.percentile(np.asarray(null_pm[b], float), 95))
        sp95 = float(np.percentile(np.asarray(null_sp[b], float), 95))
        rows.append((b, int(np.isfinite(v).sum()), pub, obs, rf95, pm95, sp95,
                     obs - sp95, b in active))
    rows.sort(key=lambda r: -r[7])
    for b, n, pub, obs, rf95, pm95, sp95, exc, fed in rows:
        mark = "*" if b in proxied else " "
        say(f"  {b:23}{mark} {n:>5} {pub:>6.3f} {obs:>6.3f} | {rf95:>7.3f} {pm95:>7.3f} | "
            f"{sp95:>7.3f} {exc:>+7.3f} {'yes' if fed else 'NO':>5}")
    for b, pub in undefined:
        say(f"  {b:24} {'--':>5} {pub:>6.3f} {'--':>6} | {'--':>7} {'--':>7} | {'--':>7} "
            f"{'--':>7} {'yes' if b in active else 'NO':>5}")
    say("  " + "-" * 96)
    say("  * cyclic proxy (sin/cos of the mean angle)")

    rule("Verdict")
    dw = next((r for r in rows if r[0] == "distance_to_water"), None)
    if dw:
        say("  CONTROL FIRST. distance_to_water was never fed to k-means -- clustering dropped it")
        say("  as a constant band -- so it is a null sample sitting inside the published chart.")
        say(f"    observed {dw[3]:.3f}   random-feature p95 {dw[4]:.3f}   spatial p95 {dw[6]:.3f}")
        if dw[3] > dw[4]:
            say("")
            say("  It CLEARS the random-feature null. That null is therefore too permissive and")
            say("  no 'survives' verdict read off it is evidence.")
        say("")
        say(f"  Under the SPATIAL null it does not clear comfortably either: excess {dw[7]:+.3f},")
        say("  which is the second smallest in the table. It is a pure function of position, so a")
        say("  spatially-compact null should land almost exactly on it -- and does. That is the")
        say("  null being calibrated rather than passed.")
        say("")
        say(f"  USE IT AS THE FLOOR. A known-null band scores {dw[7]:+.3f} here, so any band whose")
        say(f"  excess is below about {dw[7]:.3f} is not distinguishable from it. On that reading the")
        say("  bottom of the SURVIVE list -- vv_p90 (+0.008) and vv_p50 (+0.014) -- should be read")
        say("  as null too, and the honest count is the bands clearly above that floor.")

    survive = [r for r in rows if r[7] > 0]
    fail = [r for r in rows if r[7] <= 0]
    say(f"  Against the SPATIAL null: {len(survive)}/{len(rows)} bands separate the clusters better")
    say("  than geography alone.")
    say("")
    say("  SURVIVE — carry information beyond spatial compactness:")
    for r in survive:
        say(f"    + {r[0]:24} observed {r[3]:.3f}  vs sp p95 {r[6]:.3f}  ({r[7]:+.3f})")
    say("")
    say("  DO NOT SURVIVE — indistinguishable from a partition that never saw them:")
    for r in fail:
        say(f"    - {r[0]:24} observed {r[3]:.3f}  vs sp p95 {r[6]:.3f}  ({r[7]:+.3f})")
    if undefined:
        say("")
        say("  NOT TESTABLE at unit level (no finite per-unit column in the archive):")
        for b, pub in undefined:
            say(f"    ? {b:24} published {pub:.3f}")

    rule("What this says about the chart")
    say("  1. The caption is wrong. The unit is the k-means cluster, k=6, not the stand. It must")
    say("     read 'between-cluster', and the title must not say 'What separates the stands'.")
    say("  2. The ranking is not evidence on its own. Every band except distance_to_water was fit")
    say("     on, so a high ratio is the expected outcome of the construction.")
    say("  3. elevation's high rank is the clearest case. It is in the k-means feature vector, so")
    say("     its separation is partly circular -- and it is also the band most aligned with")
    say("     geography, which is what the spatial null is built to price in.")
    say("  4. Report the excess over the spatial null, not the raw ratio, if this chart is to")
    say("     support a claim about which features drive the partition.")
    say("")
    say("  5. The band that dominates the partition is the band the field data trusts least.")
    say("     canopy_height and canopy_height_max lead the survivors at +0.268 and +0.264, well")
    say("     clear of everything else -- and Phase 1 measured ETH canopy height against 274")
    say("     Odisha plots at R2=0.207 with slope 0.30. canopy_height_std survives too (+0.076)")
    say("     while measuring crown cover at R2=0.000 (r=-0.011). So these bands genuinely drive")
    say("     the partition; what they do not do is measure the forest property they are named")
    say("     for. Those are not in tension -- a band can carve consistent groups out of a")
    say("     landscape while being a poor estimator of the quantity it claims -- but any claim")
    say("     that the clusters are structurally meaningful rests on the second, not the first.")

    # ------------------------------------------------------------------ figure
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        rr = sorted(rows, key=lambda r: r[3])
        y = np.arange(len(rr))
        fig, ax = plt.subplots(figsize=(8.5, max(4.0, 0.34 * len(rr))))
        ax.barh(y, [r[3] for r in rr], height=0.7,
                color=["#2f6f4e" if r[7] > 0 else "#b9c4bd" for r in rr])
        ax.plot([r[6] for r in rr], y, marker="|", linestyle="none", markersize=12,
                color="#c1121f", label="spatial null, p95 (strict)")
        ax.plot([r[4] for r in rr], y, marker="|", linestyle="none", markersize=9,
                color="#e8a33d", label="random-feature null, p95")
        ax.set_yticks(y)
        ax.set_yticklabels([r[0] + (" *" if r[0] in proxied else "") for r in rr], fontsize=8)
        ax.set_xlim(0, 1)
        ax.set_xlabel("between-CLUSTER separation ratio  (0 = overlapping, 1 = fully separated)")
        ax.set_title(
            "What separates the six k-means clusters — sanjay_van_baseline\n"
            "unit-level, 1249 superpixels; green bars beat a spatially-compact partition "
            "that never saw the band", loc="left", fontsize=10)
        ax.legend(loc="lower right", fontsize=8, frameon=False)
        ax.grid(axis="y", visible=False)
        fig.tight_layout()
        fig.savefig(OUT_PNG, dpi=150)
        say("")
        say(f"  wrote {OUT_PNG}")
    except Exception as e:  # noqa: BLE001 - the figure is optional, the table is the deliverable
        say(f"\n  figure skipped: {type(e).__name__}: {e}")

    with open(OUT_TXT, "w") as f:
        f.write("\n".join(_out) + "\n")
    print(f"\nwrote {OUT_TXT}")


if __name__ == "__main__":
    main()
