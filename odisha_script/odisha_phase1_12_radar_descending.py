"""Phase 1, step 12: Test 5 (Sentinel-1 against field structure) on the DESCENDING orbit.

Declared in odisha_script/PHASE1_RADAR_DESCENDING_PREDECLARED.md before any value was sampled
(round 9, task E, 17 Oct 2026); that file says what is sampled and computed, and why.

    python odisha_script/odisha_phase1_12_radar_descending.py            # sample, then analyse
    python odisha_script/odisha_phase1_12_radar_descending.py --offline  # analyse the saved sample

Sampling is READ-ONLY on Earth Engine: one sampleRegions over the 274 plots and one small count
per district; no task. It writes odisha_plots_sampled_s1desc.csv. The analysis reads that file
and Phase 1's own ascending sample (odisha_plots_sampled_v2.csv), and writes
odisha_phase1_12_radar_descending_results.txt (results only: no date, no run time) and, beside
it, odisha_phase1_12_radar_descending_run.json (the command, the date, the commit).

Run from the repo root (fmu reads .env from the working directory).
"""

from __future__ import annotations

import argparse
import datetime
import json
import shlex
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
PLOTS = HERE / "odisha_plots_sampled.csv"            # Phase 1's input: the 274 plots, field columns
ASCENDING = HERE / "odisha_plots_sampled_v2.csv"     # Phase 1's own sample (ascending orbit)
SAMPLE = HERE / "odisha_plots_sampled_s1desc.csv"
RESULTS = HERE / "odisha_phase1_12_radar_descending_results.txt"
RUN = HERE / "odisha_phase1_12_radar_descending_run.json"

FEAT_START, FEAT_END = "2017-01-01", "2023-01-01"     # Phase 1 step 3's window (end exclusive)
BANDS = ["vv_p10", "vv_p50", "vv_p90", "vv_iqr", "vh_p10", "vh_p50", "vh_p90", "vh_iqr"]
FIELD = [("loreys_h_m", "Lorey's height (m)"), ("crown_cover_pct", "crown cover (%)"),
         ("basal_area_cm2", "basal area (cm2 per plot)")]
DISTRICTS = ["ANGUL", "DHENKANAL", "KENDUJHAR", "KORAPUT"]


# ---------------------------------------------------------------------------
# Earth Engine: the sample (read-only)
# ---------------------------------------------------------------------------


def sample() -> tuple[pd.DataFrame, dict[str, int]]:
    """The eight bands and the image count at each plot, and the images per district."""
    import ee

    from fmu.utils.gee import init_gee

    init_gee()
    plots = pd.read_csv(PLOTS)

    def points(df: pd.DataFrame) -> ee.FeatureCollection:
        return ee.FeatureCollection([
            ee.Feature(ee.Geometry.Point([float(r.lon), float(r.lat)]), {"plot_key": str(r.plot_key)})
            for r in df.itertuples()
        ])

    def s1_over(region: ee.Geometry) -> ee.ImageCollection:
        # Phase 1 step 3's Test 5 collection, with the orbit the one change.
        return (ee.ImageCollection("COPERNICUS/S1_GRD")
                .filterBounds(region).filterDate(FEAT_START, FEAT_END)
                .filter(ee.Filter.eq("instrumentMode", "IW"))
                .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING"))
                .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
                .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
                .select(["VV", "VH"]))

    fc = points(plots)
    s1 = s1_over(fc.geometry().bounds().buffer(1000))
    pct = s1.reduce(ee.Reducer.percentile([10, 50, 90]))
    radar = pct.rename(["vv_p10", "vv_p50", "vv_p90", "vh_p10", "vh_p50", "vh_p90"])
    radar = (radar
             .addBands(radar.select("vv_p90").subtract(radar.select("vv_p10")).rename("vv_iqr"))
             .addBands(radar.select("vh_p90").subtract(radar.select("vh_p10")).rename("vh_iqr"))
             .addBands(s1.select("VV").count().rename("n_images")))
    rows = radar.toFloat().sampleRegions(collection=fc, scale=10, geometries=False,
                                         tileScale=4).getInfo()["features"]
    got = pd.DataFrame([f["properties"] for f in rows])
    per_district = ee.Dictionary({
        d: s1_over(points(plots[plots.district == d]).geometry().bounds().buffer(1000)).size()
        for d in DISTRICTS
    }).getInfo()
    out = plots[["plot_key", "district"]].merge(got, on="plot_key", how="left")
    return out[["plot_key", "district", *BANDS, "n_images"]], {k: int(v) for k, v in per_district.items()}


# ---------------------------------------------------------------------------
# The analysis (offline)
# ---------------------------------------------------------------------------


def fit(x: pd.Series, y: pd.Series) -> dict[str, Any]:
    """n, r, R2, slope of y on x (Test 5). RMSE and bias, as odisha_phase1_9_gedi_recount.py
    computes them, are computed but not written: for radar they compare dB with metres (Jaskaran,
    18 Oct 2026, round 9 question 3 (b))."""
    m = x.notna() & y.notna()
    xs, ys = x[m].to_numpy(float), y[m].to_numpy(float)
    if len(xs) < 8:
        return {"n": len(xs), "note": "too few"}
    if np.ptp(xs) == 0 or np.ptp(ys) == 0:
        return {"n": len(xs), "note": "no variance"}
    lr = stats.linregress(xs, ys)
    return {"n": len(xs), "r": float(lr.rvalue), "r2": float(lr.rvalue) ** 2, "slope": float(lr.slope),
            "rmse": float(np.sqrt(np.mean((ys - xs) ** 2))), "bias": float(np.mean(ys - xs))}


def loo(df: pd.DataFrame) -> dict[str, Any]:
    """All eight bands, linear, left one out, against Lorey's height (Test 5's multi-band line)."""
    x = df[BANDS].to_numpy(float)
    y = df.loreys_h_m.to_numpy(float)
    m = ~np.isnan(x).any(axis=1) & ~np.isnan(y)
    x, y = x[m], y[m]
    if len(y) < 10:
        return {"n": len(y), "note": "too few"}
    design = np.column_stack([np.ones(len(x)), x])
    pred = np.empty(len(y))
    for i in range(len(y)):
        keep = np.arange(len(y)) != i
        beta, *_ = np.linalg.lstsq(design[keep], y[keep], rcond=None)
        pred[i] = design[i] @ beta
    r = float(stats.pearsonr(y, pred)[0])
    return {"n": len(y), "r": r, "r2": r * r, "rmse": float(np.sqrt(np.mean((pred - y) ** 2)))}


def zero_spread(df: pd.DataFrame) -> pd.Series:
    return (df.vv_iqr == 0) | (df.vh_iqr == 0)


def line(label: str, f: dict[str, Any], *, bias: bool = False) -> str:
    if "note" in f:
        return f"  {label:44} n={f['n']:>3}  ({f['note']})"
    out = f"  {label:44} n={f['n']:>3}  r={f['r']:+.3f}  R2={f['r2']:.3f}"
    if "slope" in f:
        out += f"  slope={f['slope']:+.2f}"
    if bias and "bias" in f:
        out += f"  RMSE={f['rmse']:.2f}  bias={f['bias']:+.2f}"
    elif "slope" not in f:
        out += f"  RMSE={f['rmse']:.2f}"
    return out


def analyse(df: pd.DataFrame, title: str) -> tuple[list[str], dict[str, Any]]:
    """The tables of one orbit: every plot, then without the plots of zero spread."""
    out: list[str] = []
    record: dict[str, Any] = {}
    zero = zero_spread(df)
    for subset, rows in (("all plots", df), ("without the plots whose spread is exactly zero", df[~zero])):
        out += ["", "=" * 92, f"{title}: {subset} ({len(rows)} plots)", "=" * 92]
        rec: dict[str, Any] = {}
        for col, name in FIELD:
            out.append(f"Against {name}:")
            rec[col] = {}
            for b in BANDS:
                f = fit(rows[col], rows[b])
                rec[col][b] = f
                out.append(line(b, f))
        lo = loo(rows)
        rec["all_eight_bands_loo"] = lo
        out.append("")
        out.append(line("all 8 bands, linear, leave-one-out", lo, bias=False))
        record[subset] = rec
    return out, record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--offline", action="store_true", help="analyse the saved sample; no Earth Engine")
    args = ap.parse_args()

    if args.offline:
        desc = pd.read_csv(SAMPLE)
        per_district = json.loads(RUN.read_text())["images_per_district"]
    else:
        desc, per_district = sample()
        desc.to_csv(SAMPLE, index=False)

    field = pd.read_csv(PLOTS)[["plot_key", "district", "loreys_h_m", "crown_cover_pct", "basal_area_cm2"]]
    d = field.merge(desc.drop(columns=["district"]), on="plot_key", how="left")
    a = pd.read_csv(ASCENDING)[["plot_key", "district", "loreys_h_m", "crown_cover_pct", "basal_area_cm2", *BANDS]]

    lines = ["=" * 92,
             "PHASE 1 STEP 12 -- Test 5 on the DESCENDING Sentinel-1 orbit",
             "declared before sampling: PHASE1_RADAR_DESCENDING_PREDECLARED.md",
             "=" * 92,
             f"  plots: {len(d)} (odisha_plots_sampled.csv); radar window {FEAT_START} to {FEAT_END} (end exclusive),",
             "  IW, VV and VH; percentiles 10, 50, 90 per pixel; iqr = p90 - p10, as Phase 1 defines it",
             "  per band: n, r, R2, slope (x the field measure, y the band). RMSE and bias, which for",
             "  radar compare dB with metres, are not reported (Jaskaran, 18 Oct 2026). The multi-band",
             "  line's RMSE is of predicted against measured height, in metres.",
             "", "Images per district (descending): images over the district's plots | n_images per plot"]
    record: dict[str, Any] = {"images_per_district": per_district, "plots": len(d)}
    for dist in DISTRICTS:
        n = d[d.district == dist].n_images
        lines.append(f"  {dist:10} {per_district[dist]:>4} images | plots {len(n):>3}: "
                     f"min {int(n.min())}  median {float(n.median()):g}  max {int(n.max())}")
    no_value = int(d[BANDS].isna().any(axis=1).sum())
    lines.append(f"  plots with no descending value in some band: {no_value}")
    lines.append("")
    lines.append("Plots whose spread is exactly zero (vv_iqr = 0 or vh_iqr = 0):")
    for name, df in (("descending", d), ("ascending, Phase 1's sample", a)):
        z = df[zero_spread(df)]
        by = {k: int(v) for k, v in z.district.value_counts().sort_index().items()}
        lines.append(f"  {name:28} {len(z):>3}  {by if by else ''}")

    out, rec = analyse(d, "DESCENDING")
    lines += out
    record["descending"] = rec
    out, rec = analyse(a, "ASCENDING (Phase 1's sample, odisha_plots_sampled_v2.csv)")
    lines += out
    record["ascending"] = rec
    RESULTS.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))

    from fmu.utils.provenance import git_state

    run = {
        "result_file": RESULTS.name,
        "sample_file": SAMPLE.name,
        "declaration": "odisha_script/PHASE1_RADAR_DESCENDING_PREDECLARED.md",
        "command_line": "python " + " ".join(shlex.quote(x) for x in sys.argv),
        "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "git": {k: v for k, v in git_state().items() if k != "root"},
        "images_per_district": per_district,
    }
    if args.offline and RUN.exists():
        run["sampled"] = json.loads(RUN.read_text()).get("sampled", run["date"])
    else:
        run["sampled"] = run["date"]
    RUN.write_text(json.dumps(run, indent=1) + "\n")
    print(f"\nwrote {RESULTS.name}, {SAMPLE.name if not args.offline else ''} and {RUN.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
