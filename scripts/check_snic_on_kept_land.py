"""Does Earth Engine do what segmentation.mask_before_snic counts on? A small check, run first.

    python scripts/check_snic_on_kept_land.py --config configs/<name>.yaml
        [--keep-small-patches] [--out <file.json>]

READ-ONLY on Earth Engine: it reads the config's cached assets and runs small reductions. It
submits no task and writes no asset. Run it from the repo root (fmu reads .env from there).

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
     masked land.
  4. patches_without_grid_point and their superpixels: kept patches no grid point falls in,
     and the superpixels on them. Expected equal: touching seed pixels are one seed.
  5. seed_grid_is_snics_own_grid: SNIC with its own seeds against SNIC given
     seedGrid(size), on the same stack with nothing masked. Expected no pixel to differ.
  6. size_matters_with_seeds: SNIC given seeds, at size and at twice size. If no pixel
     differs, SNIC ignores `size` once it has seeds, and its spatial term is not scaled the
     way it is without seeds.
  7. connected_components_max_size: two squares of 15 x 15 and 9 x 9 pixels, labelled with
     maxSize 128. If the big one (225 pixels, 15 wide) is labelled, maxSize is an extent;
     if not, it is a number of pixels.
  8. connected_pixel_count: the same squares counted with maxSize 100: what a pixel of each
     holds.

The answers go into the brief before any batch run with the setting on. `--out` writes the
result, which holds results only, and beside it `<name>_run.json` with the command, the date
and the git commit it ran from.

Kept land, and from it the seeds and the patches of check 4, are made here as the stage makes
them: on the analysis grid, clipped to the ROI (`fmu.utils.kept_land.kept_land_in_roi`, the fix
of 15 Oct 2026). The run of 14 Oct 2026 (docs/reproducibility/snic_on_kept_land_kendujhar.json)
was before the fix, of the stage and of this script.
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

REQUEST_DEADLINE_MS = 7 * 60 * 1000  # as scripts/snic_cached_vs_live.py
PIECES_MAX_SIZE = 256  # a superpixel at the shipped seed spacings is far narrower
SQUARE_BIG_PX, SQUARE_SMALL_PX = 15, 9
CC_MAX_SIZE, CPC_MAX_SIZE = 128, 100


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
        lines.append(says(m["patches_without_grid_point"] == m["superpixels_on_those_patches"],
                          f"each of the {m['patches_without_grid_point']} kept patches no grid "
                          "point falls in is one superpixel",
                          f"{m['patches_without_grid_point']} kept patches no grid point falls in "
                          f"hold {m['superpixels_on_those_patches']} superpixels"))
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


def measure_masked(ee: Any, get_info: Callable[..., Any], *, raw: Any, final: Any,
                   kept: Any, on_grid: Any, seeds: Any, roi: Any, grid: Any,
                   connectivity: int) -> dict[str, int]:
    """Checks 1 to 4 on SNIC's own labels (`raw`) and the stage's (`final`)."""
    kw = {"geometry": roi, "crs": grid, "maxPixels": int(1e10), "tileScale": 4}
    labelled = raw.mask().gt(0)
    sums = get_info(
        ee.Image.cat([
            labelled.And(kept.Not()).rename("masked_labelled"),
            kept.And(labelled.Not()).rename("kept_unlabelled"),
        ]).reduceRegion(reducer=ee.Reducer.sum().unweighted(), **kw),
        context="checks 1-2: labels against kept land",
    )
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

    def n(key: str) -> int:
        return len(counts.get(key) or {})

    return {
        "masked_pixels_labelled": int(sums.get("masked_labelled") or 0),
        "kept_pixels_unlabelled": int(sums.get("kept_unlabelled") or 0),
        "superpixels": n("superpixels"),
        "pieces": n("pieces"),
        "superpixels_in_pieces": max(0, n("pieces") - n("superpixels")),
        "patches_without_grid_point": n("extra_patches"),
        "superpixels_on_those_patches": n("labels_on_extra"),
    }


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
    ap.add_argument("--out", type=Path, default=None, help="write the result here as JSON")
    args = ap.parse_args()

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

    init_gee()
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
        raw = captured["result"].select("clusters").reproject(grid).clip(roi)
        final = stage_result.outputs["snic_clusters"]
        try:
            result["masked_run"] = {
                "distance_scale": stage_result.metadata.get("distance_scale"),
                **measure_masked(ee, get_info, raw=raw, final=final, kept=kept, on_grid=on_grid,
                                 seeds=seeds, roi=roi, grid=grid,
                                 connectivity=params.connectivity),
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
