"""
Phase 2, step 4 — the size-matched spatial null: SNIC on pure noise, then the same merge.

NEEDS LIVE EARTH ENGINE. ~14 small getInfo calls per realisation, no exports, no assets.
Resumable: realisations already in the output file are skipped.

WHY THIS NULL AND NOT A RANDOM-FEATURE ONE
------------------------------------------
Every Phase 2 statistic is positive by chance. Small stands plus spatially autocorrelated forest
give a positive R²_stand from nothing, because nearby plots are alike and small stands hold
nearby plots. The random-feature null has already failed once in this repo
(odisha_phase1_8_separation_null.py): a random-feature partition is spatially incoherent, so any
spatially coherent partition beats it. The null has to be as spatially coherent as the real
partition, and matched in size, or it measures coherence rather than delineation.

CONSTRUCTION (fixed in PHASE2_PREDICTIONS.md before any statistic was computed)
------------------------------------------------------------------------------
Per realisation r:

  1. SNIC  -- fmu.stages.segmentation.SegmentationStage itself (z-score, RMS-distance scale,
     UTM grid pin), with size/compactness/connectivity/neighbourhood from the arm config, run
     on 6 bands of iid N(0,1) noise. One noise SNIC per realisation is SHARED by all three
     arms (common random numbers), since the distance normaliser makes band count irrelevant to
     compactness. That makes arm-vs-arm comparisons paired.
  2. MERGE -- fmu.utils.adjacency + fmu.utils.region_merge.merge_superpixels itself, with each
     arm's relax_factor, min/max area, min_defined_criteria, min_frac_valid and iteration cap.
     It merges on NOISE criteria: one extra iid N(0,1) band per real criterion. Each noise
     tolerance is the quantile of this realisation's own adjacent-superpixel noise differences
     at the `percentile_of_threshold` the real tolerance reached in the OBSERVED run
     (calibrate_thresholds, recorded by the merge stage). That fixes the merge rate to the
     observed one by construction, and involves no tuning to any field outcome. Real ETH/NDVI
     criteria are NOT used: they would carry real spatial signal into the null.
  3. SAMPLE at the plot pixels (one reduceRegions): the null stand id per arm, the noise
     superpixel id (the null for the stands_snic layer), and for each the distance to the
     nearest pixel of a different unit (fastDistanceTransform on a 4-neighbour boundary image;
     the ROI edge is not a boundary).

The OBSERVED partitions go through exactly the same sampling code (realisation "obs"): each
arm's cached SNIC plus a fresh MergeStage run. So the observed value and the null values in
odisha_phase2_5_stats.py are computed from one code path. The vector join in
odisha_phase2_3_join.py is the headline assignment; this raster assignment is checked against it
there.

Run from the repo root (fmu reads .env from the working directory):
      python odisha_script/odisha_phase2_4_noise_null.py --n 199 --workers 6
Writes: phase2_nulls/noise_null_plots.csv     one row per (realisation, plot)
        phase2_nulls/noise_null_summary.csv   one row per (realisation, arm): stand count, area
                                              quantiles, tolerances used, merge diagnostics
        phase2_nulls/noise_null_observed.csv  the observed partitions, same sampler
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import ee
import numpy as np
import pandas as pd
from shapely.geometry import Point, shape

import fmu.stages.data_load  # noqa: F401  (registers the stage)
import fmu.stages.features_embedding  # noqa: F401
import fmu.stages.features_optical  # noqa: F401
import fmu.stages.features_radar  # noqa: F401
import fmu.stages.features_static  # noqa: F401
import fmu.stages.features_structure  # noqa: F401
import fmu.stages.masking  # noqa: F401
import fmu.stages.merge  # noqa: F401
import fmu.stages.segmentation  # noqa: F401
from fmu.config import Config, SnicInputBand, load_config
from fmu.pipeline import Pipeline, default_stage_names
from fmu.stages.base import PipelineContext
from fmu.stages.segmentation import SegmentationStage
from fmu.utils.adjacency import extract_superpixel_attributes, extract_superpixel_graph
from fmu.utils.gee import init_gee, load_roi_geometry, safe_get_info
from fmu.utils.grid import analysis_grid
from fmu.utils.region_merge import merge_superpixels

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from odisha_phase2_0_aois import load_plot_points  # noqa: E402
from odisha_phase2_2_run_pipeline import missing_cache  # noqa: E402
from odisha_phase2_3_join import ARMS  # noqa: E402

NULL_DIR = HERE / "phase2_nulls"
PLOTS_OUT = NULL_DIR / "noise_null_plots.csv"
SUMMARY_OUT = NULL_DIR / "noise_null_summary.csv"
OBS_OUT = NULL_DIR / "noise_null_observed.csv"
VECTOR_DIR = HERE / "phase2_vectors"

N_SNIC_NOISE_BANDS = 6
N_CRIT_NOISE_BANDS = 3          # the most criteria any arm uses
DIST_NEIGHBOURHOOD_PX = 100     # distances beyond 1 km are reported as 1 km
_write_lock = threading.Lock()


# ---------------------------------------------------------------------- shared sampler
def boundary_distance_m(labels: ee.Image, proj: ee.Projection, scale: int, name: str) -> ee.Image:
    """Distance (m, pixel centre to pixel centre) to the nearest pixel of a different unit."""
    pinned = labels.reproject(proj)
    edge = ee.Image.constant(0)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nb = pinned.translate(x=dx, y=dy, units="pixels", proj=proj)
        # unmask(0): a missing neighbour is the ROI edge, which is not a stand boundary
        edge = edge.Or(pinned.neq(nb).unmask(0))
    d2 = (edge.reproject(proj).selfMask()
          .fastDistanceTransform(DIST_NEIGHBOURHOOD_PX, "pixels", "squared_euclidean")
          .reproject(proj))
    return (d2.sqrt().multiply(scale).unmask(DIST_NEIGHBOURHOOD_PX * scale)
            .updateMask(pinned.mask()).rename(name))


def sample_at_plots(bands: dict[str, ee.Image], plots_fc: ee.FeatureCollection,
                    proj: ee.Projection, scale: int, context: str) -> pd.DataFrame:
    stack = None
    for name, img in bands.items():
        layer = img.rename(name)
        dist = boundary_distance_m(img, proj, scale, f"bd_{name}")
        stack = layer.addBands(dist) if stack is None else stack.addBands(layer).addBands(dist)
    got = safe_get_info(
        stack.reduceRegions(collection=plots_fc, reducer=ee.Reducer.first(), scale=scale,
                            crs=proj.crs()),
        context=context,
    )
    return pd.DataFrame([f["properties"] for f in got["features"]])


# ---------------------------------------------------------------------- setup
def pilot_plots(roi_file: Path) -> pd.DataFrame:
    gj = json.loads(roi_file.read_text())
    aoi = shape(gj["features"][0]["geometry"])
    df = load_plot_points()
    return df[[aoi.covers(Point(lo, la)) for lo, la in zip(df.lon6, df.lat6)]].reset_index(drop=True)


def plots_fc(df: pd.DataFrame) -> ee.FeatureCollection:
    return ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([float(lo), float(la)]), {"plot_key": k})
        for k, lo, la in zip(df.plot_key, df.lon6, df.lat6)
    ])


def observed_context(cfg: Config, roi: ee.Geometry) -> PipelineContext:
    """Cached assets through segmentation, plus a fresh MergeStage run on the cached SNIC."""
    names = default_stage_names(cfg, through="clustering")
    names = names[: names.index("merge") + 1]
    gaps = missing_cache(cfg, names)
    if gaps:
        raise SystemExit(f"{cfg.name}: {len(gaps)} cache asset(s) missing; run odisha_phase2_2 first: {gaps[:3]}")
    ctx = PipelineContext()
    ctx.set("roi", roi)
    run_dir = NULL_DIR / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    Pipeline(stage_names=names, use_cache=True).run(config=cfg, run_dir=run_dir, initial_context=ctx)
    return ctx


# ---------------------------------------------------------------------- one realisation
def noise_image(seed_base: int, n: int, prefix: str, grid: ee.Projection) -> ee.Image:
    return ee.Image.cat([
        ee.Image.random(seed_base + b, "normal").rename(f"{prefix}{b}") for b in range(n)
    ]).reproject(grid)


def realisation(r: int, ref_cfg: Config, arm_cfgs: dict[str, Config], calib: dict[str, dict],
                roi: ee.Geometry, grid: ee.Projection, fc: ee.FeatureCollection) -> tuple[pd.DataFrame, list[dict]]:
    scale = ref_cfg.export.analysis_scale_m
    snic_noise = noise_image(1_000_003 * (r + 1), N_SNIC_NOISE_BANDS, "n", grid)
    crit_noise = noise_image(7_000_001 * (r + 1), N_CRIT_NOISE_BANDS, "c", grid)

    seg_cfg = ref_cfg.model_copy(update={"segmentation": ref_cfg.segmentation.model_copy(update={
        "input_bands": [SnicInputBand(source="static_features", band=f"n{b}")
                        for b in range(N_SNIC_NOISE_BANDS)]})})
    ctx = PipelineContext()
    ctx.set("roi", roi)
    ctx.set("static_features", snic_noise)
    snic = SegmentationStage().run(ctx, seg_cfg).outputs["snic_clusters"]

    graph = extract_superpixel_graph(snic, roi, scale, max_superpixels=ref_cfg.merge.max_superpixels,
                                     context=f"null {r} adjacency")
    means, counts = extract_superpixel_attributes(
        crit_noise.addBands(ee.Image.pixelLonLat()), snic, graph, roi, scale, context=f"null {r} criteria")
    centroids = {i: (float(m.get("longitude") or 0.0), float(m.get("latitude") or 0.0))
                 for i, m in means.items()}
    edge_diffs = {}
    for b in range(N_CRIT_NOISE_BANDS):
        band = f"c{b}"
        edge_diffs[band] = np.array([abs(means[i][band] - means[j][band]) for i, j in graph.edges
                                     if means.get(i, {}).get(band) is not None
                                     and means.get(j, {}).get(band) is not None])

    bands = {"snic": snic}
    summaries = []
    for arm, cfg in arm_cfgs.items():
        mp = cfg.merge
        real_bands = sorted(mp.tolerances())            # calibrate/merge iterate in sorted order
        tols = {}
        for b, real in enumerate(real_bands):
            pct = calib[arm][real]["percentile_of_threshold"]
            tols[f"c{b}"] = float(np.quantile(edge_diffs[f"c{b}"], pct / 100.0, method="inverted_cdf"))
        res = merge_superpixels(
            graph, means, counts, criteria=tols, relax_factor=mp.relax_factor,
            min_area_ha=mp.min_area_ha, max_area_ha=mp.max_area_ha,
            min_defined_criteria=mp.min_defined_criteria, min_frac_valid=mp.min_frac_valid,
            max_pass2_iterations=mp.max_pass2_iterations, centroids=centroids)
        bands[f"stand_{arm}"] = snic.remap(graph.raw_labels, res.assignment).toInt32().clip(roi)
        areas = np.array([a["area_ha"] for a in res.stand_attributes.values()])
        d = res.diagnostics
        summaries.append({
            "realisation": r, "arm": arm, "n_superpixels": graph.n_regions, "n_stands": res.n_stands,
            "area_p10": np.quantile(areas, .1), "area_median": np.median(areas), "area_p90": np.quantile(areas, .9),
            "snic_area_median": np.median(np.array(graph.n_pixels) * scale * scale / 1e4),
            "tolerances": json.dumps({real_bands[b]: round(tols[f"c{b}"], 6) for b in range(len(real_bands))}),
            "pass2_fallback_merges": d["pass2_fallback_merges"],
            "stands_below_min_area": d["stands_below_min_area"],
        })

    s = sample_at_plots(bands, fc, grid, scale, f"null {r} sample")
    s.insert(0, "realisation", r)
    return s, summaries


def size_check(ref: Config, arm_cfgs: dict[str, Config], roi: ee.Geometry, grid: ee.Projection,
               n_seeds: int) -> int:
    """Is the noise SNIC size-matched to the observed SNIC? Geometry only; no field data.

    The brief's premise for this null is that SNIC on noise at the same size and compactness gives
    a spatially coherent partition with a matched size distribution. This measures whether it
    does, before any statistic is computed against it.
    """
    from fmu.utils.caching import asset_exists, cached_asset_path, config_fingerprint

    lines: list[str] = []

    def out(s: str = "") -> None:
        print(s, flush=True)
        lines.append(s)

    def row(label: str, px: np.ndarray, extra: str = "") -> None:
        q = np.percentile(px, [10, 25, 50, 75, 90])
        out(f"  {label:<26} n {len(px):>5} | px p10 {q[0]:>5.0f} p25 {q[1]:>5.0f} median {q[2]:>5.0f} "
            f"p75 {q[3]:>5.0f} p90 {q[4]:>5.0f} | <= 4 px {np.mean(px <= 4):>5.1%} | >= 50 px "
            f"{np.mean(px >= 50):>5.1%}{extra}")

    out("=" * 100)
    out("SIZE CHECK — noise SNIC vs observed SNIC superpixel sizes (pixels at 10 m; 100 px = 1 ha)")
    out("=" * 100)
    out(f"  SNIC params: size {ref.segmentation.size}, compactness {ref.segmentation.compactness}, "
        f"connectivity {ref.segmentation.connectivity}, neighbourhood {ref.segmentation.neighborhood_size}")
    for arm, cfg in arm_cfgs.items():
        path = cached_asset_path(cfg.name, "segmentation", "snic_clusters", config_fingerprint(cfg))
        if not asset_exists(path):
            out(f"  observed {arm:<17} (SNIC not cached yet)")
            continue
        g = extract_superpixel_graph(ee.Image(path), roi, cfg.export.analysis_scale_m, context=f"observed {arm}")
        row(f"observed {arm}", np.array(g.n_pixels))

    seg_cfg = ref.model_copy(update={"segmentation": ref.segmentation.model_copy(update={
        "input_bands": [SnicInputBand(source="static_features", band=f"n{b}")
                        for b in range(N_SNIC_NOISE_BANDS)]})})
    for r in range(n_seeds):
        ctx = PipelineContext()
        ctx.set("roi", roi)
        ctx.set("static_features", noise_image(1_000_003 * (r + 1), N_SNIC_NOISE_BANDS, "n", grid))
        snic = SegmentationStage().run(ctx, seg_cfg).outputs["snic_clusters"]
        g = extract_superpixel_graph(snic, roi, ref.export.analysis_scale_m, context=f"noise {r}")
        # labels with a pixel whose 4-neighbour is outside the ROI: separates clip slivers from fragmentation
        edge = ee.Image.constant(0)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            edge = edge.Or(snic.reproject(grid).translate(dx, dy, "pixels", grid).mask().Not())
        hist = safe_get_info(snic.updateMask(edge.reproject(grid)).rename("l").reduceRegion(
            ee.Reducer.frequencyHistogram(), roi, ref.export.analysis_scale_m, maxPixels=1e9),
            context=f"noise {r} edge labels").get("l") or {}
        edge_labels = {int(float(k)) for k in hist}
        small = [lab for lab, n in zip(g.raw_labels, g.n_pixels) if n <= 4]
        row(f"noise seed {r}", np.array(g.n_pixels),
            f" | small touching ROI edge {sum(lab in edge_labels for lab in small)}/{len(small)}")
    out("")
    out("  Read: a size-matched null needs the noise rows to resemble the observed rows. If they do not,")
    out("  the null is not size-matched and excess over it is not interpretable (PHASE2_PREDICTIONS.md).")
    (HERE / "odisha_phase2_4_results.txt").write_text("\n".join(lines) + "\n")
    return 0


def append(df: pd.DataFrame, path: Path) -> None:
    with _write_lock:
        df.to_csv(path, mode="a", header=not path.exists(), index=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=199)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--skip-observed", action="store_true")
    ap.add_argument("--size-check", type=int, default=0, metavar="N_SEEDS",
                    help="only compare noise vs observed SNIC sizes over N seeds, write "
                         "odisha_phase2_4_results.txt, and exit")
    args = ap.parse_args()

    logging.getLogger("fmu").setLevel(logging.WARNING)
    init_gee()
    NULL_DIR.mkdir(exist_ok=True)

    arm_cfgs = {a: load_config(REPO / "configs" / f"{c}.yaml") for a, c in ARMS.items()}
    ref = arm_cfgs["v120"]
    for cfg in arm_cfgs.values():
        assert cfg.roi.roi_file == ref.roi.roi_file and cfg.segmentation.size == ref.segmentation.size \
            and cfg.segmentation.compactness == ref.segmentation.compactness
    roi = load_roi_geometry(ref.roi.roi_file)
    grid = analysis_grid(roi, ref.export.analysis_scale_m)
    if args.size_check:
        return size_check(ref, arm_cfgs, roi, grid, args.size_check)
    plots = pilot_plots(REPO / ref.roi.roi_file)
    fc = plots_fc(plots)
    print(f"plots inside {ref.roi.roi_file}: {len(plots)}")

    calib = {}
    for arm, cfg in arm_cfgs.items():
        run = json.loads((VECTOR_DIR / f"{cfg.name}_run.json").read_text())
        calib[arm] = run["merge_diagnostics"]["threshold_calibration"]["per_band"]
        print(f"  {arm}: observed tolerance percentiles "
              f"{ {b: v['percentile_of_threshold'] for b, v in calib[arm].items()} }")

    # ---------------------------------------------------------------- observed, same sampler
    if not args.skip_observed and not OBS_OUT.exists():
        obs = None
        for arm, cfg in arm_cfgs.items():
            ctx = observed_context(cfg, roi)
            s = sample_at_plots({f"stand_{arm}": ctx.get("stand_clusters"),
                                 f"snic_{arm}": ctx.get("snic_clusters")},
                                fc, grid, cfg.export.analysis_scale_m, f"observed {arm} sample")
            obs = s if obs is None else obs.merge(s, on="plot_key", validate="1:1")
            print(f"  observed {arm}: sampled {len(s)} plots")
        obs.to_csv(OBS_OUT, index=False)

    # ---------------------------------------------------------------- realisations
    done = set(pd.read_csv(SUMMARY_OUT).realisation.unique()) if SUMMARY_OUT.exists() else set()
    todo = [r for r in range(args.n) if r not in done]
    print(f"realisations: {len(done)} done, {len(todo)} to run, {args.workers} workers")

    def job(r: int) -> int:
        for attempt in range(4):
            try:
                s, summ = realisation(r, ref, arm_cfgs, calib, roi, grid, fc)
                append(s, PLOTS_OUT)
                append(pd.DataFrame(summ), SUMMARY_OUT)
                return r
            except Exception as e:  # noqa: BLE001 - transient EE errors are retried, then raised
                if attempt == 3:
                    raise
                print(f"  realisation {r} attempt {attempt + 1} failed: {str(e)[:160]}; retrying", flush=True)
                time.sleep(20 * (attempt + 1))
        return r

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(job, r) for r in todo]
        for k, f in enumerate(as_completed(futures), 1):
            r = f.result()
            if k % 10 == 0 or k == len(todo):
                print(f"  {k}/{len(todo)} done ({time.time() - t0:.0f} s), last r={r}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
