"""The superpixels A6 found in more than one piece: where they are, and what separates the pieces.

    python scripts/check_split_superpixels.py --config configs/<name>.yaml
        [--keep-small-patches] [--as-config configs/<name>_keptland.yaml] [--out <file.json>]

READ-ONLY on Earth Engine: it reads the config's cached assets and makes small requests. It
submits no task and writes no asset (scripts/ee_read_only.py makes any such call raise). Run it
from the repo root (fmu reads .env from there).

Why this exists. scripts/check_snic_on_kept_land.py (task A6 of
docs/handoff/2026-10-13-round2.md) found, on Kendujhar's box run with
segmentation.mask_before_snic on, 3 superpixels in more than one piece (2,758 pieces for 2,755
superpixels; docs/reproducibility/snic_on_kept_land_kendujhar.json). Jaskaran asked, on 14 Oct
2026, for each of them: its label, the number of pieces and the area of each piece, and what
separates the pieces: masked (not kept) pixels, a diagonal touch only, or a tile edge or the ROI
edge. This script answers that and changes nothing: it is a check, not a fix.

What it does.
  1. The segmentation A6 ran: the same config, the setting turned on in memory (small kept
     patches left out unless --keep-small-patches), the upstream read from the cache, and the
     segmentation stage itself, keeping SNIC's own output before the stage clips it to the ROI
     and masks it to kept land (as A6 does).
  2. The pieces as A6 counts them: connectedComponents on the stage's label image, with the
     kernel of SNIC's connectivity. One grouped histogram finds every superpixel with more than
     one piece, and gives the totals to compare with A6.
  3. For each of those, a window around it on the analysis grid (computePixels): the stage's
     label, SNIC's own label (no clip, no mask), kept land, the ROI, and A6's piece label. The
     rest is plain Python on those arrays (`classify`, tested offline):
       - the pieces again, 8- and 4-connected, with their pixel counts and areas;
       - where A6's count splits what is one 8-connected piece here, what the count saw between
         the parts: "diagonal touch only" (they touch at a corner and nowhere along a side) or
         "tile edge" (see below);
       - for each 8-connected piece other than the largest, what lies between it and the
         largest, as a list of what applies:
           "masked pixels"      the two can be joined through land kept land leaves out, or
                                SNIC's own label joins them through such land, which the
                                stage's mask then removes;
           "ROI edge"           the shortest way between them leaves the ROI, or SNIC's own
                                label joins them through pixels outside the ROI, which the
                                stage's clip removes;
           "tile edge"          a line of the 256-pixel tile lattice of the analysis grid runs
                                between them (the lattice is assumed to start at the grid's
                                pixel origin: Earth Engine does not document where its tiles
                                start);
           "other superpixels"  only kept land carrying other superpixels lies between them;
           "other"              none of these.
         The facts behind each (what a shortest way between the pieces crosses, whether SNIC's
         own label joins them, which tile lines lie between them) are written out with it.

`--out` writes the result, which holds results only, and beside it `<name>_run.json` with the
command, the date and the git commit it ran from. `--as-config` is as in
scripts/check_snic_on_kept_land.py: the kept-land config whose segmentation this checks, refused
unless it is what --config segments with the setting on.

Since the fix of 15 Oct 2026 (kept land clipped to the ROI before SNIC; register entry
spec-segmentation-mask-before-snic), kept land here is made as the stage makes it
(`fmu.utils.kept_land.kept_land_in_roi`), so the window's kept land is the land SNIC is given.
The result of 14 Oct 2026, before the fix, read kept land unclipped, and its windows show the
strip of kept land outside the ROI that SNIC then grew into.
"""

from __future__ import annotations

import argparse
import datetime
import json
import shlex
import sys
import tempfile
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))  # this checkout's fmu, not an editable install of another
REQUEST_DEADLINE_MS = 7 * 60 * 1000  # as scripts/check_snic_on_kept_land.py
PIECES_MAX_SIZE = 256  # as scripts/check_snic_on_kept_land.py, so the pieces are A6's
TILE_PX = 256  # Earth Engine's tile size in pixels
MARGIN_PX = 24  # pixels around a superpixel's bounding box in the window read back
NONE = -1  # stands for "no value" in the arrays read back (masked, outside the image)

EIGHT = np.ones((3, 3), dtype=int)
FOUR = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])


def run_record_path(out: Path) -> Path:
    return out.with_name(out.stem + "_run.json")


# ------------------------------------------------------------------- offline part (tested)


def _components(mask: np.ndarray, structure: np.ndarray) -> tuple[np.ndarray, int]:
    from scipy import ndimage

    labelled, n = ndimage.label(mask, structure=structure)
    return labelled, int(n)


def _touch(a: np.ndarray, b: np.ndarray) -> tuple[bool, bool]:
    """(touch along a side, touch at a corner) between two boolean masks of one shape."""
    pad_a = np.pad(a, 1)
    side = corner = False
    h, w = a.shape
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            shifted = pad_a[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
            if (shifted & b).any():
                if dy == 0 or dx == 0:
                    side = True
                else:
                    corner = True
    return side, corner


def _tile_lines_between(
    a: np.ndarray, b: np.ndarray, i0: int, j0: int, tile_px: int
) -> list[str]:
    """Tile-lattice lines that have all of one piece on one side and all of the other on the
    other side. Columns are global pixel indices i0 + c, rows j0 + r; a line `x=k` runs along
    the left edge of global column k, and k is a multiple of `tile_px`."""
    ys_a, xs_a = np.nonzero(a)
    ys_b, xs_b = np.nonzero(b)
    lines = []
    for name, ca, cb, off in (("x", xs_a, xs_b, i0), ("y", ys_a, ys_b, j0)):
        ga, gb = ca + off, cb + off
        lo, hi = (ga, gb) if ga.max() < gb.min() else (gb, ga)
        if lo.max() >= hi.min():
            continue  # they overlap along this axis: no line of it separates them
        first = (lo.max() // tile_px + 1) * tile_px  # first lattice line right of / below lo
        k = first
        while k <= hi.min():
            lines.append(f"{name}={k}")
            k += tile_px
    return lines


def _shortest_gap(a: np.ndarray, b: np.ndarray) -> list[tuple[int, int]]:
    """The pixels strictly between `a` and `b` on one shortest 8-connected path, or [] if the
    two touch (or if `b` cannot be reached inside the window)."""
    h, w = a.shape
    prev: dict[tuple[int, int], tuple[int, int] | None] = {}
    queue: deque[tuple[int, int]] = deque()
    for y, x in zip(*np.nonzero(a), strict=True):
        prev[(int(y), int(x))] = None
        queue.append((int(y), int(x)))
    while queue:
        y, x = queue.popleft()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ny, nx = y + dy, x + dx
                if (dy == 0 and dx == 0) or not (0 <= ny < h and 0 <= nx < w):
                    continue
                if (ny, nx) in prev:
                    continue
                prev[(ny, nx)] = (y, x)
                if b[ny, nx]:
                    path = []
                    step = prev[(ny, nx)]
                    while step is not None and not a[step]:
                        path.append(step)
                        step = prev[step]
                    return path[::-1]
                queue.append((ny, nx))
    return []


def _reach(a: np.ndarray, b: np.ndarray, through: np.ndarray) -> int | None:
    """Fewest pixels of `through` between `a` and `b` on an 8-connected path that steps only on
    `through` pixels, or None if there is no such path inside the window."""
    h, w = a.shape
    seen = a.copy()
    frontier: deque[tuple[int, int, int]] = deque(
        (int(y), int(x), 0) for y, x in zip(*np.nonzero(a), strict=True)
    )
    while frontier:
        y, x, d = frontier.popleft()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ny, nx = y + dy, x + dx
                if (dy == 0 and dx == 0) or not (0 <= ny < h and 0 <= nx < w) or seen[ny, nx]:
                    continue
                if b[ny, nx]:
                    return d
                seen[ny, nx] = True
                if through[ny, nx]:
                    frontier.append((ny, nx, d + 1))
    return None


def classify(
    final: np.ndarray,
    raw: np.ndarray,
    kept: np.ndarray,
    roi: np.ndarray,
    piece: np.ndarray,
    label: int,
    *,
    i0: int,
    j0: int,
    tile_px: int = TILE_PX,
    pixel_ha: float = 0.01,
) -> dict[str, Any]:
    """What one superpixel's pieces are, and what separates them, from arrays of one window.

    final  the stage's label image (NONE where masked)
    raw    SNIC's own label image, before the clip to the ROI and the mask to kept land
    kept   1 on kept land, 0 elsewhere inside the ROI; outside it NONE or 0, as kept land is
           clipped to the ROI (before the fix of 15 Oct 2026 it was read unclipped, 1 on kept
           land outside the ROI too, and NONE outside the land-cover footprint)
    roi    1 inside the ROI, 0 outside
    piece  A6's piece label (connectedComponents on `final`), NONE where masked
    i0, j0 the global pixel column and row of the window's top-left pixel

    Two kinds of gap are told apart. A6's count can split what is one 8-connected piece here
    (`split_by_the_count`); then the question is what the count saw between the parts: a
    corner only, or a tile line. Or the superpixel really is in separate 8-connected pieces
    (`between_pieces`); then the question is what lies between them: land the mask removes,
    land outside the ROI, other superpixels, and whether a tile line runs between them.
    """
    mine = final == label
    lab8, n8 = _components(mine, EIGHT)
    _, n4 = _components(mine, FOUR)
    in_window = sorted({int(v) for v in np.unique(piece[mine]) if v != NONE})
    pieces = []
    for k in range(1, n8 + 1):
        m = lab8 == k
        ys, xs = np.nonzero(m)
        pieces.append({
            "pixels": int(m.sum()),
            "area_ha": round(float(m.sum()) * pixel_ha, 4),
            "columns": [int(xs.min()) + i0, int(xs.max()) + i0],
            "rows": [int(ys.min()) + j0, int(ys.max()) + j0],
            "a6_piece_labels": sorted({int(v) for v in np.unique(piece[m]) if v != NONE}),
            "_mask": m,
        })
    pieces.sort(key=lambda p: -p["pixels"])

    split_by_the_count = []
    for p in pieces:
        labs = p["a6_piece_labels"]
        for v in labs[1:]:
            a, b = (piece == labs[0]) & p["_mask"], (piece == v) & p["_mask"]
            side, corner = _touch(a, b)
            lines = _tile_lines_between(a, b, i0, j0, tile_px)
            kinds = (["diagonal touch only"] if corner and not side else []) + (
                ["tile edge"] if lines else [])
            split_by_the_count.append({
                "separated_by": kinds or ["other"],
                "touch_along_a_side": side,
                "touch_at_a_corner": corner,
                "tile_lines_between": lines,
            })

    between_pieces = []
    big = pieces[0]["_mask"] if pieces else np.zeros_like(mine)
    raw_lab, _ = _components(raw == label, EIGHT)
    not_kept = (roi == 1) & (kept != 1)
    outside = roi != 1
    other = (roi == 1) & (kept == 1) & (final != NONE) & ~mine
    for p in pieces[1:]:
        m = p["_mask"]
        raw_ids = {int(v) for v in np.unique(raw_lab[big]) if v} & {
            int(v) for v in np.unique(raw_lab[m]) if v}
        via = np.isin(raw_lab, sorted(raw_ids)) & ~mine
        via_outside = int((via & outside).sum())
        via_not_kept = int((via & not_kept).sum())
        gap = _shortest_gap(big, m)
        crossing = {"outside_roi": 0, "not_kept": 0, "other_superpixels": 0, "unlabelled_kept": 0}
        for y, x in gap:
            if outside[y, x]:
                crossing["outside_roi"] += 1
            elif not_kept[y, x]:
                crossing["not_kept"] += 1
            elif other[y, x]:
                crossing["other_superpixels"] += 1
            else:
                crossing["unlabelled_kept"] += 1
        only_not_kept = _reach(big, m, not_kept)
        only_outside = _reach(big, m, outside | not_kept)
        lines = _tile_lines_between(big, m, i0, j0, tile_px)
        kinds = []
        if via_not_kept or only_not_kept is not None:
            kinds.append("masked pixels")
        if via_outside or (only_outside is not None and crossing["outside_roi"]):
            kinds.append("ROI edge")
        if lines:
            kinds.append("tile edge")
        if crossing["other_superpixels"] and only_not_kept is None and only_outside is None:
            kinds.append("other superpixels")
        between_pieces.append({
            "between": f"the largest piece ({pieces[0]['pixels']} px) and one of {p['pixels']} px",
            "separated_by": kinds or ["other"],
            "snics_own_label_joins_them": bool(raw_ids),
            "joined_through_pixels_outside_roi": via_outside,
            "joined_through_pixels_not_kept": via_not_kept,
            "gap_pixels_on_a_shortest_path": len(gap),
            "gap_crosses": crossing,
            "fewest_pixels_between_through_not_kept_land_only": only_not_kept,
            "fewest_pixels_between_through_not_kept_or_outside_roi_only": only_outside,
            "tile_lines_between": lines,
        })
    for p in pieces:
        del p["_mask"]
    return {
        "label": int(label),
        "kept_pixels_outside_roi_in_window": int(((kept == 1) & outside).sum()),
        "snic_label_pixels_outside_roi": int(((raw == label) & outside).sum()),
        "pieces_in_window_as_a6_counts_them": len(in_window),
        "pieces_8_connected": n8,
        "pieces_4_connected": n4,
        "pieces": pieces,
        "split_by_the_count": split_by_the_count,
        "between_pieces": between_pieces,
    }


def verdicts(result: dict[str, Any]) -> list[str]:
    """Plain lines for a result. Pure Python, so it is testable offline."""
    lines = []
    t = result.get("totals", {})
    if t:
        lines.append(f"over the ROI: {t.get('superpixels')} superpixels in {t.get('pieces')} pieces "
                     f"(counted as A6 counted them until 15 Oct 2026: "
                     f"{t.get('superpixels_as_a6_counts_them')} and "
                     f"{t.get('pieces_as_a6_counts_them')}, a key 'null' included where there is "
                     f"one); {len(result.get('split', []))} superpixels in more than one piece")
        missing = t.get("superpixels_without_a_piece_label") or {}
        if missing:
            lines.append(f"superpixels with no piece label (not in the grouped count): "
                         f"{', '.join(f'{k} ({v} px)' for k, v in missing.items())}")
    for s in result.get("split", []):
        if "error" in s:
            lines.append(f"superpixel {s['label']}: {s['error']}")
            continue
        areas = ", ".join(f"{p['area_ha']:g} ha" for p in s.get("pieces", []))
        why = [", ".join(x["separated_by"]) for x in s.get("between_pieces", [])]
        why += [f"(A6's count only) {', '.join(x['separated_by'])}" for x in s.get("split_by_the_count", [])]
        lines.append(f"superpixel {s['label']}: {s.get('pieces_over_the_roi_as_a6_counts_them')} pieces "
                     f"as A6 counts them over the ROI, {s['pieces_8_connected']} 8-connected and "
                     f"{s['pieces_4_connected']} 4-connected in its window, of {areas}; "
                     f"separated by: {'; '.join(why) or 'nothing found between them in the window'}")
    lines.append(f"export tasks submitted: {result.get('export_tasks_submitted')}")
    return lines


# ------------------------------------------------------------------- Earth Engine part


def find_split(ee: Any, get_info: Callable[..., Any], *, final: Any, pieces: Any, roi: Any,
               grid: Any) -> tuple[dict[str, Any], dict[int, dict[int, int]]]:
    """Totals, and {label: {piece label: pixels}} for every superpixel in more than one piece.

    One request holds both A6's counts (distinct labels of each image, as
    check_snic_on_kept_land.measure_masked takes them) and the grouped histogram, so the two
    describe one evaluation of the segmentation. A superpixel with no unmasked piece label
    (connectedComponents masks an object wider than its maxSize) is in the first and not in the
    second; any such label is listed."""
    hist = ee.Reducer.frequencyHistogram().unweighted()
    kw = {"geometry": roi, "crs": grid, "maxPixels": int(1e10), "tileScale": 4}
    got = get_info(
        ee.Dictionary({
            "superpixels": final.rename("v").reduceRegion(reducer=hist, **kw).get("v"),
            "pieces": pieces.rename("v").reduceRegion(reducer=hist, **kw).get("v"),
            "grouped": pieces.rename("piece").addBands(final.rename("sp")).reduceRegion(
                reducer=hist.group(groupField=1, groupName="sp"), **kw).get("groups"),
        }),
        context="pieces of each superpixel",
    )
    groups = got.get("grouped") or []
    split = {int(g["sp"]): {int(float(k)): int(v) for k, v in g["histogram"].items()}
             for g in groups if len(g["histogram"]) > 1}
    grouped = {int(g["sp"]) for g in groups}
    # A6's count is the number of keys of each histogram. A histogram can also hold a key "null"
    # (pixels the reducer saw with no value), which that count takes for one more label: it is
    # kept apart here, with its number of pixels.
    sp_hist, piece_hist = got.get("superpixels") or {}, got.get("pieces") or {}
    labels = {int(float(k)): int(v) for k, v in sp_hist.items() if k != "null"}
    totals = {
        "superpixels_as_a6_counts_them": len(sp_hist),
        "pieces_as_a6_counts_them": len(piece_hist),
        "null_key_pixels": {"superpixels": sp_hist.get("null"), "pieces": piece_hist.get("null")},
        "superpixels": len(labels),
        "pieces": len([k for k in piece_hist if k != "null"]),
        "superpixels_with_a_piece_label": len(groups),
        "pieces_of_those": sum(len(g["histogram"]) for g in groups),
        "superpixels_without_a_piece_label": {str(k): labels[k] for k in sorted(set(labels) - grouped)},
    }
    return totals, split


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, required=True,
                    help="a config that ran with mask_before_snic off, its upstream cached")
    ap.add_argument("--keep-small-patches", action="store_true",
                    help="do not leave out kept patches below merge.min_area_ha")
    ap.add_argument("--as-config", type=Path, default=None,
                    help="the kept-land config whose segmentation this checks")
    ap.add_argument("--out", type=Path, default=None, help="write the result here as JSON")
    ap.add_argument("--save-windows", type=Path, default=None,
                    help="also save each window's arrays here, as <label>.npz (for inspection)")
    args = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from check_snic_on_kept_land import as_config_problems, check_fmu_is_this_checkouts

    check_fmu_is_this_checkouts()

    import ee
    from pyproj import Transformer
    from shapely.geometry import Point, shape

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
    from fmu.utils.kept_land import kept_land_in_roi
    from fmu.utils.provenance import git_state

    cfg = load_config(args.config)
    if cfg.segmentation.mask_before_snic:
        raise SystemExit(f"{cfg.name} already has mask_before_snic on; name the config it was copied from")
    raw_cfg = cfg.model_dump(mode="json")
    raw_cfg["segmentation"]["mask_before_snic"] = True
    raw_cfg["segmentation"]["drop_kept_patches_below_min_area"] = not args.keep_small_patches
    on = Config.model_validate(raw_cfg)
    if args.as_config:
        problems = as_config_problems(on, load_config(args.as_config))
        if problems:
            raise SystemExit(f"{args.as_config} is not what {cfg.name} segments with the setting "
                             "on: " + "; ".join(problems))

    init_gee()
    import ee_read_only  # scripts/: every task or asset write raises before it is sent

    ee_read_only.forbid_writes()
    ee.data.setDeadline(REQUEST_DEADLINE_MS)
    roi = load_roi_geometry(cfg.roi.roi_file)
    scale = cfg.export.analysis_scale_m
    ctx = PipelineContext()
    ctx.set("roi", roi)
    run = Pipeline(segmentation_stage_names(cfg)[:-1], use_cache=True, submit_exports=False,
                   summaries=False).run(
        config=cfg, run_dir=Path(tempfile.mkdtemp(prefix="check_split_superpixels_")),
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

    snic = ee.Algorithms.Image.Segmentation.SNIC
    captured: dict[str, Any] = {}

    def keep(**kwargs: Any) -> Any:
        captured.update(kwargs)
        captured["result"] = snic(**kwargs)
        return captured["result"]

    params = on.segmentation
    grid = segmentation_module._analysis_grid(roi, scale)
    try:
        ee.Algorithms.Image.Segmentation.SNIC = keep
        stage_result = segmentation_module.SegmentationStage().run(context, on)
    finally:
        ee.Algorithms.Image.Segmentation.SNIC = snic
    final = stage_result.outputs["snic_clusters"]
    raw = captured["result"].select("clusters").reproject(grid)  # no clip, no mask
    # Kept land as the stage makes it: on the analysis grid, clipped to the ROI.
    kept = kept_land_in_roi(context.get("habitat_mask"), roi, grid,
                            min_patch_pixels=on.kept_patch_min_pixels(),
                            connectivity=params.connectivity)
    kernel = ee.Kernel.square(1) if params.connectivity == 8 else ee.Kernel.plus(1)
    pieces = final.connectedComponents(kernel, PIECES_MAX_SIZE).select("labels")

    proj = get_info(grid, context="analysis grid")
    crs, (sx, _, tx, _, sy, ty) = proj["crs"], proj["transform"]
    totals, split = find_split(ee, get_info, final=final, pieces=pieces, roi=roi, grid=grid)
    result: dict[str, Any] = {
        "config": cfg.name,
        "checks_the_segmentation_of": load_config(args.as_config).name if args.as_config else None,
        "with_the_setting_on": {
            "mask_before_snic": True,
            "drop_kept_patches_below_min_area": not args.keep_small_patches,
            "size": params.size, "connectivity": params.connectivity,
            "neighborhood_size": params.neighborhood_size,
        },
        "upstream_cache_status": status,
        "analysis_grid": {"crs": crs, "transform": proj["transform"]},
        "tile_lattice_assumed": f"{TILE_PX} px, starting at the grid's pixel origin",
        "totals": totals,
        "split": [],
    }

    if split:
        labels = sorted(split)
        # Where each one is, in longitude and latitude (pixel centres), then as pixel columns
        # and rows of the analysis grid, so the window below sits exactly on that grid.
        boxes = get_info(
            ee.Image.pixelLonLat().addBands(final.rename("sp"))
            .updateMask(final.remap(labels, [1] * len(labels), 0))
            .reduceRegion(reducer=ee.Reducer.minMax().repeat(2).group(groupField=2, groupName="sp"),
                          geometry=roi, crs=grid, maxPixels=int(1e10)),
            context="where the split superpixels are",
        ).get("groups") or []
        geom = shape(json.loads(Path(cfg.roi.roi_file).read_text())["features"][0]["geometry"])
        parts = list(getattr(geom, "geoms", [geom]))
        to_lonlat = Transformer.from_crs(crs, 4326, always_xy=True).transform
        to_grid = Transformer.from_crs(4326, crs, always_xy=True).transform
        stack = ee.Image.cat([
            final.unmask(NONE).toInt64().rename("final"),
            raw.unmask(NONE).toInt64().rename("raw"),
            kept.unmask(NONE).toInt64().rename("kept"),
            ee.Image(1).clip(roi).unmask(0).toInt64().rename("roi"),
            pieces.unmask(NONE).toInt64().rename("piece"),
        ])
        for g in sorted(boxes, key=lambda g: int(g["sp"])):
            label = int(g["sp"])
            corners = [to_grid(lon, lat) for lon in (g["min"][0], g["max"][0])
                       for lat in (g["min"][1], g["max"][1])]
            cols = [int(np.floor((x - tx) / sx)) for x, _ in corners]
            rows = [int(np.floor((y - ty) / sy)) for _, y in corners]
            i_lo, i_hi = min(cols) - MARGIN_PX, max(cols) + MARGIN_PX
            j_lo, j_hi = min(rows) - MARGIN_PX, max(rows) + MARGIN_PX
            width, height = i_hi - i_lo + 1, j_hi - j_lo + 1
            print(f"  ... window of {width} x {height} px around superpixel {label}", file=sys.stderr,
                  flush=True)
            arr = ee.data.computePixels({
                "expression": stack,
                "fileFormat": "NUMPY_NDARRAY",
                "grid": {
                    "dimensions": {"width": width, "height": height},
                    "affineTransform": {"scaleX": sx, "shearX": 0, "translateX": tx + i_lo * sx,
                                        "shearY": 0, "scaleY": sy, "translateY": ty + j_lo * sy},
                    "crsCode": crs,
                },
            })
            if args.save_windows:
                args.save_windows.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(args.save_windows / f"{label}.npz", i0=i_lo, j0=j_lo,
                                    **{k: arr[k] for k in ("final", "raw", "kept", "roi", "piece")})
            if not (arr["final"] == label).any():
                result["split"].append({"label": label, "error": "not found in its window",
                                        "window": {"columns": [i_lo, i_hi], "rows": [j_lo, j_hi]}})
                continue
            row = classify(arr["final"], arr["raw"], arr["kept"], arr["roi"], arr["piece"], label,
                           i0=i_lo, j0=j_lo, pixel_ha=abs(sx * sy) / 10_000.0)
            row["pieces_over_the_roi_as_a6_counts_them"] = len(split[label])
            row["piece_pixels_over_the_roi"] = {str(k): v for k, v in sorted(split[label].items())}
            row["window"] = {"columns": [i_lo, i_hi], "rows": [j_lo, j_hi]}
            for p in row["pieces"]:
                ci = (p["columns"][0] + p["columns"][1] + 1) / 2.0
                cj = (p["rows"][0] + p["rows"][1] + 1) / 2.0
                lon, lat = to_lonlat(tx + ci * sx, ty + cj * sy)
                p["box_centre_lon_lat"] = [round(lon, 6), round(lat, 6)]
                p["roi_part"] = next((k for k, part in enumerate(parts)
                                      if part.buffer(1e-4).contains(Point(lon, lat))), None)
            result["split"].append(row)

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
