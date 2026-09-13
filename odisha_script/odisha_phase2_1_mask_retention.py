"""
Phase 2, step 1 — does the habitat mask keep the field plots? (brief Step 3, BLOCKING)

NEEDS LIVE EARTH ENGINE. Four getInfo calls, no exports, no assets written.

WHY
---
Every stand-level number downstream is computed over habitat pixels only: clustering does
`updateMask(habitat_mask)`, so a plot sitting on a pixel the mask drops never gets a type label,
and a stand made mostly of such pixels is not typed either. Many Odisha plots are low crown
cover. If CoRE Stack LULC_v4 (IndiaSAT classes 6 Trees / 12 Shrubs, WorldCover fallback) calls
them cropland, barren or built-up, they leave the analysis SILENTLY -- they would not show up as
a weak result, they would simply be absent from it.

So this is measured before anything else runs, and if overall retention is below 80% the phase
stops: a mask that deletes a fifth of the field data changes what every downstream number means,
and that is a decision for Jaskaran, not something to work around here.

WHAT
----
Runs fmu.stages.masking.MaskingStage itself (not a re-implementation) with the masking block of
configs/odisha_v120_handcrafted.yaml -- identical in all three Phase 2 configs -- over an ROI made
of 100 m discs around all 274 plots, and samples `habitat_mask` at each plot point at the 10 m
analysis scale.

The mask is a per-pixel rule (majority vote over the year images, WorldCover where IndiaSAT has
no data), so the ROI only decides the clip, not the value. That is checked rather than assumed:
the 60 pilot plots are re-sampled with the ROI set to aois/odisha_dhenkanal_sites.geojson and
must agree plot for plot.

Reported, as the brief asks: overall retention, by district, by crown_cover_pct quartile, and by
meta_chm == 0 (the Phase 1 zero census column, from odisha_plots_sampled_v2.csv). Plus two
diagnostics that say WHY a plot is dropped: the IndiaSAT year classes at the plot, and whether
any habitat pixel lies within 20 m (the GPS accuracy filter), since a plot dropped by one pixel
of registration is a different finding from a plot sitting in a field.

Run from the repo root (fmu reads .env from the working directory):
      python odisha_script/odisha_phase2_1_mask_retention.py
Writes: odisha_phase2_1_results.txt, odisha_phase2_1_mask_retention.csv
Exit code 2 if overall retention < 80% (STOP).
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import ee
import numpy as np
import pandas as pd

from fmu.config import load_config
from fmu.stages.base import PipelineContext
from fmu.stages.masking import MaskingStage, _load_indiasat_collection
from fmu.utils.gee import init_gee, load_roi_geometry, safe_get_info

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from odisha_phase2_0_aois import load_plot_points  # noqa: E402

CONFIG = REPO / "configs" / "odisha_v120_handcrafted.yaml"
PILOT_AOI = REPO / "aois" / "odisha_dhenkanal_sites.geojson"
V2 = HERE / "odisha_plots_sampled_v2.csv"
RESULTS = HERE / "odisha_phase2_1_results.txt"
OUT_CSV = HERE / "odisha_phase2_1_mask_retention.csv"

RETENTION_FLOOR = 0.80
SCALE = 10
ROI_DISC_M = 100
GPS_DISC_M = 20

# Legend groups as documented in fmu.config.MaskingParams. Codes not listed print as numbers.
INDIASAT_GROUP = {1: "built-up", 2: "water", 3: "water", 4: "water", 5: "crop", 6: "TREES",
                  7: "barren", 8: "crop", 9: "crop", 10: "crop", 11: "crop", 12: "SHRUBS"}

_lines: list[str] = []


def say(s: str = "") -> None:
    print(s)
    _lines.append(s)


def rule(title: str) -> None:
    say("")
    say("=" * 90)
    say(title)
    say("=" * 90)


def plot_fc(df: pd.DataFrame) -> ee.FeatureCollection:
    return ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([float(lo), float(la)]), {"plot_key": k})
        for k, lo, la in zip(df.plot_key, df.lon6, df.lat6)
    ])


def run_masking(roi: ee.Geometry, cfg) -> dict:
    ctx = PipelineContext()
    ctx.set("roi", roi)
    return MaskingStage().run(ctx, cfg).outputs


def sample_first(image: ee.Image, fc: ee.FeatureCollection, context: str) -> pd.DataFrame:
    got = safe_get_info(
        image.reduceRegions(collection=fc, reducer=ee.Reducer.first(), scale=SCALE),
        context=context,
    )
    out = pd.DataFrame([f["properties"] for f in got["features"]])
    # A single-band image comes back under the reducer's name ("first"), not the band's.
    if "first" in out.columns:
        out = out.rename(columns={"first": safe_get_info(image.bandNames(), context=context)[0]})
    return out


def table(df: pd.DataFrame, by: str, label: str) -> None:
    g = df.groupby(by, observed=True, dropna=False).habitat.agg(["size", "sum"])
    say(f"  {label:<24} {'n':>4} {'kept':>5} {'retention':>10}")
    for k, r in g.iterrows():
        say(f"  {str(k):<24} {int(r['size']):>4} {int(r['sum']):>5} {r['sum'] / r['size']:>9.1%}")


def main() -> int:
    init_gee()
    cfg = load_config(CONFIG)
    df = load_plot_points()
    v2 = pd.read_csv(V2)[["plot_key", "meta_chm"]]
    df = df.merge(v2, on="plot_key", how="left", validate="1:1")
    fc = plot_fc(df)

    rule("SETUP")
    say(f"  config          : {CONFIG.relative_to(REPO)} (masking block identical in all 3 Phase 2 configs)")
    say(f"  masking         : IndiaSAT {cfg.masking.indiasat_habitat_classes} "
        f"years {cfg.masking.indiasat_year_min}-{cfg.masking.indiasat_year_max}, "
        f"WorldCover fallback {cfg.masking.keep_worldcover_classes}")
    say(f"  plots           : {len(df)}; meta_chm == 0 at {int((df.meta_chm == 0).sum())}")
    say(f"  ROI             : union of {ROI_DISC_M} m discs around every plot; sampled at {SCALE} m")

    # ---------------------------------------------------------------- the stage itself
    roi = fc.geometry().buffer(ROI_DISC_M, 1)
    out = run_masking(roi, cfg)
    ic = _load_indiasat_collection(cfg.datasets.indiasat, cfg.masking, roi)
    years = safe_get_info(ic.aggregate_array("system:time_start"), context="indiasat years")
    year_labels = [pd.Timestamp(t, unit="ms").year for t in years]
    yearly = ic.toBands().rename([f"lulc_{y}" for y in year_labels])
    wc = ee.ImageCollection(cfg.datasets.worldcover).first().select("Map").rename("worldcover")
    stack = (out["habitat_mask"].rename("habitat")
             .addBands(yearly).addBands(wc)
             .addBands(yearly.select(0).mask().rename("indiasat_has_data")))
    s = sample_first(stack, fc, "habitat mask + yearly classes at plots")

    near = safe_get_info(
        out["habitat_mask"].rename("hab_frac").reduceRegions(
            collection=fc.map(lambda f: f.buffer(GPS_DISC_M, 1)),
            reducer=ee.Reducer.mean(), scale=SCALE),
        context="habitat fraction within GPS disc",
    )
    # A single-band reduceRegions names its output after the reducer, not the band.
    near = (pd.DataFrame([f["properties"] for f in near["features"]])[["plot_key", "mean"]]
            .rename(columns={"mean": "hab_frac"}))
    df = df.merge(s, on="plot_key", how="left", validate="1:1").merge(near, on="plot_key", validate="1:1")

    if df.habitat.isna().any():
        say(f"  WARNING: {int(df.habitat.isna().sum())} plot(s) returned no mask value (outside ROI?)")
    df["habitat"] = df.habitat.fillna(0).astype(int)

    # ---------------------------------------------------------------- ROI-independence check
    pilot_roi = load_roi_geometry(PILOT_AOI)
    pilot = df[df.site_polygon.notna()]
    out_p = run_masking(pilot_roi, cfg)
    sp = sample_first(out_p["habitat_mask"].rename("habitat_pilot_roi"), plot_fc(pilot),
                      "habitat mask at pilot plots, pilot ROI")
    chk = pilot.merge(sp, on="plot_key", validate="1:1")
    agree = int((chk.habitat == chk.habitat_pilot_roi.fillna(-1).astype(int)).sum())

    # ---------------------------------------------------------------- report
    n, kept = len(df), int(df.habitat.sum())
    overall = kept / n
    rule("RETENTION")
    say(f"  OVERALL: {kept} of {n} plots on a habitat pixel = {overall:.1%}   (floor {RETENTION_FLOOR:.0%})")
    say(f"  ROI check: pilot plots agree between plot-disc ROI and pilot AOI ROI at {agree} of {len(chk)}")
    say("")
    table(df, "district", "district")
    say("")
    df["cc_quartile"] = pd.qcut(df.crown_cover_pct, 4, duplicates="drop")
    say("  crown_cover_pct quartiles (band midpoints; ties make bins uneven):")
    table(df, "cc_quartile", "crown_cover_pct")
    say("")
    df["meta_zero"] = np.where(df.meta_chm == 0, "meta_chm == 0", "meta_chm > 0")
    table(df, "meta_zero", "Meta zero census")
    say("")
    df["pilot"] = np.where(df.site_polygon.notna(), "pilot (6 sites)", "outside pilot")
    table(df, "pilot", "pilot AOI")
    say("")
    df["source"] = np.where(df.indiasat_has_data == 1, "IndiaSAT decides", "WorldCover fallback")
    table(df, "source", "mask source")

    rule("WHY DROPPED PLOTS ARE DROPPED")
    dropped = df[df.habitat == 0]
    say(f"  {len(dropped)} dropped plot(s)")
    ycols = [c for c in df.columns if c.startswith("lulc_")]
    groups = Counter()
    for r in dropped.itertuples():
        cls = [int(getattr(r, c)) for c in ycols if pd.notna(getattr(r, c))]
        top = Counter(INDIASAT_GROUP.get(c, str(c)) for c in cls).most_common(1)
        groups[top[0][0] if top else "no IndiaSAT data"] += 1
    say("  majority IndiaSAT legend group across years at the dropped plots:")
    for k, v in groups.most_common():
        say(f"    {k:<18} {v}")
    say("")
    say(f"  dropped plots with ANY habitat pixel within {GPS_DISC_M} m: "
        f"{int((dropped.hab_frac > 0).sum())} of {len(dropped)}")
    say(f"  dropped plots with >= 50% habitat within {GPS_DISC_M} m : "
        f"{int((dropped.hab_frac >= 0.5).sum())} of {len(dropped)}")
    say("")
    say("  field description of dropped vs kept plots (medians):")
    for col in ["crown_cover_pct", "loreys_h_m", "h_top5_m", "n_trees"]:
        say(f"    {col:<16} dropped {dropped[col].median():>7.2f}   kept {df[df.habitat == 1][col].median():>7.2f}")

    keep_cols = ["plot_key", "district", "habitation", "site_polygon", "crown_cover_pct", "meta_chm",
                 "habitat", "hab_frac", "indiasat_has_data", "worldcover", *ycols]
    df[keep_cols].to_csv(OUT_CSV, index=False)

    rule("EXIT CONDITION")
    if overall < RETENTION_FLOOR:
        say(f"  STOP: overall retention {overall:.1%} is below {RETENTION_FLOOR:.0%}. Phase 2 does not proceed;")
        say("  this is a decision for Jaskaran, not a workaround.")
        code = 2
    else:
        say(f"  PASS: overall retention {overall:.1%} >= {RETENTION_FLOOR:.0%}. Proceed to the pipeline run "
            "(odisha_phase2_2_run_pipeline.py).")
        code = 0
    RESULTS.write_text("\n".join(_lines) + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
