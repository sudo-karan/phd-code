"""Does Earth Engine do what segmentation.mask_before_snic counts on? A small check, run first.

    python scripts/check_snic_on_kept_land.py --config configs/<name>.yaml
        [--keep-small-patches] [--as-config configs/<name>_keptland.yaml] [--out <file.json>]

READ-ONLY on Earth Engine: it reads the config's cached assets and runs small reductions. It
submits no task and writes no asset (scripts/ee_read_only.py makes any such call raise). Run it
from the repo root (fmu reads .env from there).

Why this exists. The kept-land path of segmentation (src/fmu/utils/kept_land.py, register
entry spec-segmentation-mask-before-snic) was written and tested offline. It rests on things
the Earth Engine algorithm reference does not say, and it should not meet them for the first
time in a paid batch run. `--config` names a config that has run with the setting OFF, so its
land-cover mask and features are cached; this script reads them, turns the setting on in
memory (with small patches left out unless `--keep-small-patches`), and runs the
segmentation stage on its ROI, keeping SNIC's own output before the stage masks it. Then it
measures:

  1. masked_pixels_labelled: pixels SNIC gave a superpixel although they were masked.
     Expected 0: SNIC leaves a masked pixel without a label.
  2. kept_pixels_unlabelled: kept pixels SNIC gave no superpixel. Expected 0: the seeds reach
     every kept patch.
  3. superpixels_in_pieces: superpixels whose pixels fall in more than one piece (labels
     against connected pieces of the same label). Expected 0: no superpixel grows across
     masked land, and none is cut by the clip to the ROI.
     snic_pixels_outside_roi: pixels SNIC's own label covers outside the ROI (those the
     stage's clip removes), within OUTSIDE_BUFFER_PX of it. Expected 0: kept land, so SNIC's
     input, is clipped to the ROI before SNIC (the fix of 15 Oct 2026; before it, SNIC grew
     three superpixels on Kendujhar's box into a strip of kept land just outside the ROI,
     docs/reproducibility/snic_split_superpixels_kendujhar.json).
     largest_superpixel_pixels: the largest superpixel, against the component cap of the
     merge that would read it (Config.max_component_pixels() of --as-config, else of --config
     with the setting on). Expected at most the cap: a larger one is deleted downstream.
  4. patches_without_grid_point and their superpixels: kept patches no grid point falls in,
     and the superpixels on them. Expected equal: touching seed pixels are one seed.
  5. seed_grid_is_snics_own_grid: SNIC with its own seeds against SNIC given
     seedGrid(size), on the same stack with nothing masked. Expected no pixel to differ.
  6. size_matters_with_seeds: SNIC given seeds, at size and at twice size. If no pixel
     differs, `size` does not change SNIC's result once it is given seeds. With check 5 this
     says that `size` places the seed grid. It does not say how SNIC weights its spatial term
     when the seeds are not its own grid, as kept-land seeds are not. Corrected 20 Oct 2026
     (review C18): this said that then "its spatial term is not scaled the way it is without
     seeds", which does not follow from checks 5 and 6. Check 5 (SNIC given seedGrid(size)
     gives SNIC's own result) rules out a spatial term scaled by `size` only when SNIC places
     its own seeds; a constant normaliser and one derived from the seeds present both pass
     checks 5 and 6, and they weight kept-land seeds differently (the review's toy SNIC, not
     run here). What compactness means with segmentation.mask_before_snic on is still open
     (docs/handoff/2026-10-14-round3.md, question 13).
  7. connected_components_max_size: two squares of 15 x 15 and 9 x 9 pixels, labelled with
     maxSize 128. If the big one (225 pixels, 15 wide) is labelled, maxSize is an extent;
     if not, it is a number of pixels.
  8. connected_pixel_count: the same squares counted with maxSize 100: what a pixel of each
     holds.

The counts of checks 3 and 4 are distinct labels of a histogram over the ROI. A histogram can
also hold a key "null" (pixels the reducer saw with no value): it is not counted as a label, and
its pixels are given apart (null_key_pixels). The run of 14 Oct 2026 counted it, so its counts
there are each one too high where the key was present (docs/handoff/2026-10-14-round3.md). Check
3's count outside the ROI has two controls: how many pixels outside the ROI it looked at, and the
same count for SNIC on check 5's stack, unclipped, which has nothing masked outside the ROI where
the cached features reach past it, and so is expected above 0 there.

The answers go into the brief before any batch run with the setting on. `--out` writes the
result, which holds results only, and beside it `<name>_run.json` with the command, the date
and the git commit it ran from.

Kept land, and from it the seeds and the patches of check 4, are made here as the stage makes
them: on the analysis grid, clipped to the ROI (`fmu.utils.kept_land.kept_land_in_roi`, the fix
of 15 Oct 2026). The run of 14 Oct 2026 (docs/reproducibility/snic_on_kept_land_kendujhar.json)
was before the fix, of the stage and of this script.

`--as-config` names the kept-land config whose segmentation this stands for (one of the six of
round 3, which have no cached assets of their own yet): the script refuses unless that config's
segmentation block, ROI, analysis scale and smallest kept patch are those --config gets with the
setting on, so that the check is of that config's segmentation, and it takes the merge's
component cap from it.
"""

from __future__ import annotations

import argparse
import datetime
import json
import shlex
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))  # this checkout's fmu, not an editable install of another
REQUEST_DEADLINE_MS = 7 * 60 * 1000  # as scripts/snic_cached_vs_live.py
PIECES_MAX_SIZE = 256  # a superpixel at the shipped seed spacings is far narrower
SQUARE_BIG_PX, SQUARE_SMALL_PX = 15, 9
CC_MAX_SIZE, CPC_MAX_SIZE = 128, 100
OUTSIDE_BUFFER_PX = 20  # how far past the ROI edge SNIC's own label is looked for (check 3)


def run_record_path(out: Path) -> Path:
    return out.with_name(out.stem + "_run.json")


def verdicts(result: dict[str, Any]) -> list[str]:
    """Plain lines for a result. Pure Python, so it is testable offline."""
    lines: list[str] = []
    m = result.get("masked_run", {})
    if "error" in m:
        lines.append(f"the masked segmentation could not be run: {m['error']}")
    else:
        def says(ok: bool, yes: str, no: str) -> str:
            return ("as expected: " + yes) if ok else ("NOT as expected: " + no)

        lines.append(says(m["masked_pixels_labelled"] == 0,
                          "SNIC left every masked pixel without a superpixel",
                          f"SNIC gave {m['masked_pixels_labelled']} masked pixels a superpixel"))
        lines.append(says(m["kept_pixels_unlabelled"] == 0,
                          "every kept pixel has a superpixel",
                          f"{m['kept_pixels_unlabelled']} kept pixels have no superpixel"))
        lines.append(says(m["superpixels_in_pieces"] == 0,
                          "no superpixel is in more than one piece",
                          f"{m['superpixels_in_pieces']} superpixels are in more than one piece "
                          f"({m['pieces']} pieces for {m['superpixels']} superpixels)"))
        if "snic_pixels_outside_roi" in m:
            looked = m.get("pixels_outside_roi_looked_at")
            if not looked:
                lines.append("NOT as expected: no pixel outside the ROI was looked at, so the "
                             "count of SNIC's label there says nothing")
            else:
                lines.append(says(m["snic_pixels_outside_roi"] == 0,
                                  f"SNIC labelled none of the {looked} pixels just outside the ROI",
                                  f"SNIC labelled {m['snic_pixels_outside_roi']} of the {looked} "
                                  "pixels just outside the ROI, which the stage's clip removes"))
        cap = result.get("merge_component_cap") or {}
        if "largest_superpixel_pixels" in m and cap.get("pixels") is None:
            lines.append(f"NOT as expected: the largest superpixel, {m['largest_superpixel_pixels']} "
                         "px, has no merge component cap recorded to be compared with")
        elif "largest_superpixel_pixels" in m:
            lines.append(says(m["largest_superpixel_pixels"] <= cap["pixels"],
                              f"the largest superpixel, {m['largest_superpixel_pixels']} px, is "
                              f"within the merge's component cap of {cap.get('pixels')} px "
                              f"({cap.get('config')})",
                              f"the largest superpixel, {m['largest_superpixel_pixels']} px, is "
                              f"over the merge's component cap of {cap.get('pixels')} px "
                              f"({cap.get('config')})"))
        lines.append(says(m["patches_without_grid_point"] == m["superpixels_on_those_patches"],
                          f"each of the {m['patches_without_grid_point']} kept patches no grid "
                          "point falls in is one superpixel",
                          f"{m['patches_without_grid_point']} kept patches no grid point falls in "
                          f"hold {m['superpixels_on_those_patches']} superpixels"))
    ctl = result.get("outside_roi_control")
    if ctl and "error" in ctl:
        lines.append(f"check 3's control could not be run: {ctl['error']}")
    elif ctl:
        lines.append(f"check 3's control: SNIC on the unmasked stack labels "
                     f"{ctl['snic_pixels_outside_roi']} of the {ctl['pixels_outside_roi_looked_at']} "
                     "pixels just outside the ROI (above 0 where the cached features reach past it)")
    for key, text in (
        ("seed_grid_is_snics_own_grid", "SNIC given seedGrid(size) against SNIC with its own seeds"),
        ("size_matters_with_seeds", "SNIC given seeds, at size against twice size"),
    ):
        row = result.get(key, {})
        if "error" in row:
            lines.append(f"{text}: could not be run: {row['error']}")
        else:
            lines.append(f"{text}: {row['pixels_differing']} of {row['pixels']} pixels differ")
    cc = result.get("connected_components_max_size", {})
    if "error" in cc:
        lines.append(f"connectedComponents maxSize: could not be run: {cc['error']}")
    elif cc:
        big = cc["big_square_labelled"]
        kind = "an extent" if big == cc["big_square_pixels"] else (
            "a number of pixels" if big == 0 else "unclear")
        lines.append(f"connectedComponents maxSize {CC_MAX_SIZE} labelled {big} of the "
                     f"{cc['big_square_pixels']} pixels of the {SQUARE_BIG_PX}-pixel square: "
                     f"maxSize is {kind}")
    cpc = result.get("connected_pixel_count", {})
    if "error" in cpc:
        lines.append(f"connectedPixelCount: could not be run: {cpc['error']}")
    elif cpc:
        lines.append(f"connectedPixelCount maxSize {CPC_MAX_SIZE}: big square holds "
                     f"{cpc['big_square_min']} to {cpc['big_square_max']}, small square "
                     f"{cpc['small_square_min']} to {cpc['small_square_max']}")
    lines.append(f"export tasks submitted: {result.get('export_tasks_submitted')}")
    return lines


def _err(exc: BaseException) -> dict[str, str]:
    return {"error": " ".join(str(exc).split())[:300]}


def check_fmu_is_this_checkouts() -> None:
    """Refuse if fmu is not imported from this checkout's src/, so the check runs the code of
    the commit its run record names (as scripts/reuse_upstream_assets.py does)."""
    import fmu

    here = Path(fmu.__file__).resolve()
    if (REPO / "src").resolve() not in here.parents:
        raise SystemExit(f"fmu is imported from {here}, not from {REPO / 'src'}: this would check "
                         "another checkout's code")


def as_config_problems(on: Any, as_cfg: Any) -> list[str]:
    """Why `as_cfg` (a kept-land config) is not what `on` (--config with the setting on in
    memory) segments: an empty list when its segmentation is the one checked. Pure Python."""
    problems = []
    if on.segmentation != as_cfg.segmentation:
        a, b = on.segmentation.model_dump(), as_cfg.segmentation.model_dump()
        problems.append("segmentation differs in " + ", ".join(
            sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k))))
    if on.roi != as_cfg.roi:
        problems.append("the ROI differs")
    if on.export.analysis_scale_m != as_cfg.export.analysis_scale_m:
        problems.append("export.analysis_scale_m differs")
    if on.kept_patch_min_pixels() != as_cfg.kept_patch_min_pixels():
        problems.append("the smallest kept patch (kept_patch_min_pixels) differs")
    return problems


def measure_masked(ee: Any, get_info: Callable[..., Any], *, raw: Any, final: Any,
                   kept: Any, on_grid: Any, seeds: Any, roi: Any, grid: Any,
                   connectivity: int, unclipped: Any | None = None,
                   scale: int = 10) -> dict[str, Any]:
    """Checks 1 to 4 on SNIC's own labels (`raw`, clipped to the ROI; `unclipped`, not) and
    the stage's (`final`). `scale` is the analysis grid's, in metres."""
    kw = {"geometry": roi, "crs": grid, "maxPixels": int(1e10), "tileScale": 4}
    labelled = raw.mask().gt(0)
    sums = get_info(
        ee.Image.cat([
            labelled.And(kept.Not()).rename("masked_labelled"),
            kept.And(labelled.Not()).rename("kept_unlabelled"),
        ]).reduceRegion(reducer=ee.Reducer.sum().unweighted(), **kw),
        context="checks 1-2: labels against kept land",
    )
    outside = ({} if unclipped is None else
               outside_roi(ee, get_info, unclipped, roi=roi, grid=grid, scale=scale,
                           context="check 3: SNIC's own label outside the ROI"))
    kernel = ee.Kernel.square(1) if connectivity == 8 else ee.Kernel.plus(1)
    pieces = final.connectedComponents(kernel, PIECES_MAX_SIZE).select("labels")
    extra = seeds.And(on_grid.Not())
    extra_patches = extra.selfMask().connectedComponents(kernel, PIECES_MAX_SIZE).select("labels")
    hist = ee.Reducer.frequencyHistogram().unweighted()
    counts = get_info(
        ee.Dictionary({
            "superpixels": final.rename("v").reduceRegion(reducer=hist, **kw).get("v"),
            "pieces": pieces.rename("v").reduceRegion(reducer=hist, **kw).get("v"),
            "extra_patches": extra_patches.rename("v").reduceRegion(reducer=hist, **kw).get("v"),
            "labels_on_extra": raw.updateMask(extra).rename("v").reduceRegion(reducer=hist, **kw).get("v"),
        }),
        context="checks 3-4: superpixels, pieces and seedless patches",
    )

    def labels(key: str) -> dict[str, Any]:
        return {k: v for k, v in (counts.get(key) or {}).items() if k != "null"}

    def n(key: str) -> int:
        return len(labels(key))

    sizes = labels("superpixels")
    largest = max(sizes, key=lambda k: (sizes[k], k)) if sizes else None
    return {
        "masked_pixels_labelled": int(sums.get("masked_labelled") or 0),
        "kept_pixels_unlabelled": int(sums.get("kept_unlabelled") or 0),
        "superpixels": n("superpixels"),
        "pieces": n("pieces"),
        "superpixels_in_pieces": max(0, n("pieces") - n("superpixels")),
        **outside,
        "largest_superpixel_pixels": int(sizes[largest]) if largest is not None else 0,
        "largest_superpixel_label": None if largest is None else int(float(largest)),
        "patches_without_grid_point": n("extra_patches"),
        "superpixels_on_those_patches": n("labels_on_extra"),
        "null_key_pixels": {k: (counts.get(k) or {}).get("null") for k in
                            ("superpixels", "pieces", "extra_patches", "labels_on_extra")},
    }



def outside_roi(ee: Any, get_info: Callable[..., Any], unclipped: Any, *, roi: Any, grid: Any,
                scale: int, context: str) -> dict[str, int]:
    """Pixels a label image (before any clip) labels where the stage's clip removes a pixel, within
    OUTSIDE_BUFFER_PX of the ROI, and how many such pixels were looked at."""
    # 1 where the clip removes a pixel (its mask is 0 there), 0 where it keeps one, however little
    # the ROI covers it; both images written out as 0 and 1 everywhere, so that neither is masked
    # outside the ROI and a 0 cannot come from a masked pixel.
    outside_clip = ee.Image(1).clip(roi).unmask(0, False).eq(0)
    labelled_any = unclipped.mask().gt(0).unmask(0, False)
    got = get_info(
        ee.Image.cat([
            labelled_any.And(outside_clip).rename("labelled"),
            outside_clip.rename("outside"),
        ]).reduceRegion(
            reducer=ee.Reducer.sum().unweighted(),
            geometry=roi.buffer(OUTSIDE_BUFFER_PX * scale),
            crs=grid, maxPixels=int(1e10), tileScale=4),
        context=context,
    )
    return {"snic_pixels_outside_roi": int(got.get("labelled") or 0),
            "pixels_outside_roi_looked_at": int(got.get("outside") or 0)}


def differing(ee: Any, get_info: Callable[..., Any], a: Any, b: Any, *, roi: Any, grid: Any,
              context: str) -> dict[str, int]:
    """Pixels where two label images disagree (checks 5 and 6)."""
    neq = a.neq(b).rename("v")
    kw = {"geometry": roi, "crs": grid, "maxPixels": int(1e10), "tileScale": 4}
    got = get_info(
        ee.Dictionary({
            "differ": neq.reduceRegion(reducer=ee.Reducer.sum().unweighted(), **kw).get("v"),
            "n": neq.reduceRegion(reducer=ee.Reducer.count().unweighted(), **kw).get("v"),
        }),
        context=context,
    )
    return {"pixels": int(got.get("n") or 0), "pixels_differing": int(got.get("differ") or 0)}


def squares(ee: Any, get_info: Callable[..., Any], *, x0: float, y0: float, epsg: int,
            scale: int) -> tuple[dict[str, int], dict[str, int]]:
    """Checks 7 and 8 on two squares drawn on the analysis grid, away from any data."""
    proj = f"EPSG:{epsg}"
    big = ee.Geometry.Rectangle(
        [x0, y0, x0 + SQUARE_BIG_PX * scale, y0 + SQUARE_BIG_PX * scale], proj, False)
    sx = x0 + 3 * SQUARE_BIG_PX * scale
    small = ee.Geometry.Rectangle(
        [sx, y0, sx + SQUARE_SMALL_PX * scale, y0 + SQUARE_SMALL_PX * scale], proj, False)
    grid = ee.Projection(proj).atScale(scale)
    ones = (
        ee.Image(0).byte()
        .paint(ee.FeatureCollection([ee.Feature(big), ee.Feature(small)]), 1)
        .reproject(grid)
        .selfMask()
    )
    labels = ones.connectedComponents(ee.Kernel.square(1), CC_MAX_SIZE).select("labels").rename("v")
    count = ones.connectedPixelCount(CPC_MAX_SIZE, True).rename("v")
    one = ones.rename("v")

    def over(image: Any, region: Any, reducer: Any) -> Any:
        return image.reduceRegion(reducer=reducer, geometry=region, crs=grid,
                                  maxPixels=int(1e8)).get("v")

    n = ee.Reducer.count().unweighted()
    got = get_info(
        ee.Dictionary({
            "big_square_pixels": over(one, big, n),
            "small_square_pixels": over(one, small, n),
            "big_square_labelled": over(labels, big, n),
            "small_square_labelled": over(labels, small, n),
            "big_min": over(count, big, ee.Reducer.min()),
            "big_max": over(count, big, ee.Reducer.max()),
            "small_min": over(count, small, ee.Reducer.min()),
            "small_max": over(count, small, ee.Reducer.max()),
        }),
        context="checks 7-8: two squares",
    )
    cc = {k: int(got.get(k) or 0) for k in (
        "big_square_pixels", "small_square_pixels", "big_square_labelled", "small_square_labelled")}
    cpc = {
        "big_square_min": got.get("big_min"), "big_square_max": got.get("big_max"),
        "small_square_min": got.get("small_min"), "small_square_max": got.get("small_max"),
    }
    return cc, cpc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, required=True,
                    help="a config that ran with mask_before_snic off, its upstream cached")
    ap.add_argument("--keep-small-patches", action="store_true",
                    help="do not leave out kept patches below merge.min_area_ha")
    ap.add_argument("--as-config", type=Path, default=None,
                    help="the kept-land config whose segmentation this checks (see the docstring)")
    ap.add_argument("--out", type=Path, default=None, help="write the result here as JSON")
    args = ap.parse_args()
    check_fmu_is_this_checkouts()

    import ee
    from pyproj import Transformer
    from shapely.geometry import shape

    import fmu.stages.data_load  # noqa: F401  (importing registers the stages)
    import fmu.stages.features_embedding  # noqa: F401
    import fmu.stages.features_optical  # noqa: F401
    import fmu.stages.features_radar  # noqa: F401
    import fmu.stages.features_static  # noqa: F401
    import fmu.stages.features_structure  # noqa: F401
    import fmu.stages.masking  # noqa: F401
    import fmu.stages.segmentation as segmentation_module
    from fmu.config import Config, load_config
    from fmu.pipeline import Pipeline, segmentation_stage_names
    from fmu.stages.base import PipelineContext
    from fmu.utils.gee import init_gee, load_roi_geometry, safe_get_info
    from fmu.utils.grid import utm_epsg_code
    from fmu.utils.kept_land import kept_land_in_roi, seeds_on_kept_land
    from fmu.utils.provenance import git_state

    cfg = load_config(args.config)
    if cfg.segmentation.mask_before_snic:
        raise SystemExit(f"{cfg.name} already has mask_before_snic on; name the config it was copied from")
    raw_cfg = cfg.model_dump(mode="json")
    raw_cfg["segmentation"]["mask_before_snic"] = True
    raw_cfg["segmentation"]["drop_kept_patches_below_min_area"] = not args.keep_small_patches
    on = Config.model_validate(raw_cfg)
    checked = on
    if args.as_config:
        checked = load_config(args.as_config)
        problems = as_config_problems(on, checked)
        if problems:
            raise SystemExit(f"{checked.name} is not what {cfg.name} segments with the setting on: "
                             + "; ".join(problems))

    init_gee()
    import ee_read_only  # scripts/: every task or asset write raises before it is sent

    ee_read_only.forbid_writes()
    ee.data.setDeadline(REQUEST_DEADLINE_MS)
    roi = load_roi_geometry(cfg.roi.roi_file)
    scale = cfg.export.analysis_scale_m
    upstream = segmentation_stage_names(cfg)[:-1]
    ctx = PipelineContext()
    ctx.set("roi", roi)
    run = Pipeline(upstream, use_cache=True, submit_exports=False, summaries=False).run(
        config=cfg, run_dir=Path(tempfile.mkdtemp(prefix="check_snic_on_kept_land_")),
        initial_context=ctx,
    )
    status = {s.name: s.cache_status for s in run.stages}
    live = sorted(f"{st}/{k}" for st, keys in status.items() for k, v in keys.items()
                  if v != "hit" and k != "mask_provenance")
    if live:
        raise SystemExit(f"{cfg.name}: not cached, so this would compute them live: {live}")
    context = run.context

    def get_info(obj: Any, context: str = "") -> Any:
        print(f"  ... {context}", file=sys.stderr, flush=True)
        return safe_get_info(obj, context=context)

    result: dict[str, Any] = {
        "config": cfg.name,
        "with_the_setting_on": {
            "mask_before_snic": True,
            "drop_kept_patches_below_min_area": not args.keep_small_patches,
            "kept_patch_min_pixels": on.kept_patch_min_pixels(),
            "size": on.segmentation.size,
            "connectivity": on.segmentation.connectivity,
            "neighborhood_size": on.segmentation.neighborhood_size,
        },
        "upstream_cache_status": status,
        "checks_the_segmentation_of": checked.name if args.as_config else None,
        "merge_component_cap": {"config": checked.name if args.as_config else f"{cfg.name}, setting on",
                                "pixels": checked.max_component_pixels()},
    }

    # The stage itself, keeping SNIC's own output before the stage masks it.
    snic = ee.Algorithms.Image.Segmentation.SNIC
    captured: dict[str, Any] = {}

    def keep(**kwargs: Any) -> Any:
        captured.update(kwargs)
        captured["result"] = snic(**kwargs)
        return captured["result"]

    grid = segmentation_module._analysis_grid(roi, scale)
    params = on.segmentation
    # Kept land as the stage makes it: on the analysis grid, clipped to the ROI.
    kept = kept_land_in_roi(context.get("habitat_mask"), roi, grid,
                            min_patch_pixels=on.kept_patch_min_pixels(),
                            connectivity=params.connectivity)
    on_grid = (ee.Algorithms.Image.Segmentation.seedGrid(params.size).unmask(0).gt(0).And(kept))
    seeds = seeds_on_kept_land(kept, size=params.size, connectivity=params.connectivity,
                               max_extent=params.neighborhood_size)
    try:
        ee.Algorithms.Image.Segmentation.SNIC = keep
        stage_result = segmentation_module.SegmentationStage().run(context, on)
    except Exception as exc:  # report it, and still run the checks that need no stage
        result["masked_run"] = _err(exc)
        stage_result = None
    finally:
        ee.Algorithms.Image.Segmentation.SNIC = snic
    if stage_result is not None:
        unclipped = captured["result"].select("clusters").reproject(grid)
        raw = unclipped.clip(roi)
        final = stage_result.outputs["snic_clusters"]
        try:
            result["masked_run"] = {
                "distance_scale": stage_result.metadata.get("distance_scale"),
                **measure_masked(ee, get_info, raw=raw, final=final, kept=kept, on_grid=on_grid,
                                 seeds=seeds, roi=roi, grid=grid,
                                 connectivity=params.connectivity, unclipped=unclipped,
                                 scale=scale),
            }
        except Exception as exc:
            result["masked_run"] = _err(exc)

    # Checks 5 and 6, on the stack SNIC was given with its masked pixels set to 0, so that
    # they say nothing about masks: both sides of each comparison see the same image.
    if "image" in captured:
        stack = captured["image"].unmask(0)
        common = {"compactness": params.compactness, "connectivity": params.connectivity,
                  "neighborhoodSize": params.neighborhood_size}
        grid_seeds = ee.Algorithms.Image.Segmentation.seedGrid(params.size)

        def labels(**kwargs: Any) -> Any:
            return snic(image=stack, **common, **kwargs).select("clusters").reproject(grid).clip(roi)

        own = labels(size=params.size)
        given = labels(size=params.size, seeds=grid_seeds)
        try:
            control = snic(image=stack, size=params.size, **common).select("clusters").reproject(grid)
            result["outside_roi_control"] = outside_roi(
                ee, get_info, control, roi=roi, grid=grid, scale=scale,
                context="check 3, control: SNIC on the unmasked stack, outside the ROI")
        except Exception as exc:
            result["outside_roi_control"] = _err(exc)
        twice = labels(size=2 * params.size, seeds=grid_seeds)
        for key, a, b in (("seed_grid_is_snics_own_grid", own, given),
                          ("size_matters_with_seeds", given, twice)):
            try:
                result[key] = differing(ee, get_info, a, b, roi=roi, grid=grid, context=f"check: {key}")
            except Exception as exc:
                result[key] = _err(exc)

    # Checks 7 and 8, on two squares by the ROI's south-west corner, on the analysis grid.
    try:
        geom = shape(json.loads(Path(cfg.roi.roi_file).read_text())["features"][0]["geometry"])
        west, south = geom.bounds[0], geom.bounds[1]
        epsg = utm_epsg_code(*geom.centroid.coords[0])
        x, y = Transformer.from_crs(4326, epsg, always_xy=True).transform(west, south)
        x0, y0 = (round(x / scale) - 200) * scale, (round(y / scale) - 200) * scale
        result["connected_components_max_size"], result["connected_pixel_count"] = squares(
            ee, get_info, x0=x0, y0=y0, epsg=epsg, scale=scale)
    except Exception as exc:
        result["connected_components_max_size"] = _err(exc)
        result["connected_pixel_count"] = _err(exc)

    result["export_tasks_submitted"] = sum(len(s.export_tasks) for s in run.stages)
    print("\n".join(verdicts(result)))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=1, default=str) + "\n")
        record = {
            "result_file": args.out.name,
            "command_line": "python " + " ".join(shlex.quote(a) for a in sys.argv),
            "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "git": {k: v for k, v in git_state().items() if k != "root"},
        }
        run_record_path(args.out).write_text(json.dumps(record, indent=1) + "\n")
        print(f"wrote {args.out} and {run_record_path(args.out).name}")


if __name__ == "__main__":
    main()
