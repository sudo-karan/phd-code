"""Re-merge the demo set's superpixels into stands, under the committed second-pass rule and the new one.

    python scripts/remerge_demo_set.py --run <run_id> [<run_id> ...]      # or --all
        [--out-dir outputs/demo] [--summary-dir docs/demo/remerge]
    python scripts/remerge_demo_set.py --table                           # offline: the table of all runs

READ-ONLY on Earth Engine. It opens saved assets, runs reductions and makes small interactive
downloads. It submits no task and writes, changes or deletes no asset: `ee_read_only.forbid_writes()`
makes any such call raise before it is sent. `--table` needs no Earth Engine at all.

What it is for (brief of 13 Oct 2026, task A2; register entry spec-merge-pass2-skip-at-minimum).
The demo set is the 14 Earth Engine runs of 13 Oct 2026 (docs/demo/demo_set.json). Their stands
were merged by the code as committed then, in which a region that had already reached the minimum
stand size could be merged once more in the second pass. This tool merges the same superpixels
again, from the same saved assets, twice: under that rule ("old", merge.pass2_skip_at_min_area
false), to check that a re-merge reproduces the stands the run exported, and under the rule that
skips such a region ("new", the setting on). Everything after the merge that the demo needs is
then computed live for each rule: the stand types (the clustering stage, never its cache), the
stand layer (the export stage's own builder, read back instead of sent to Drive) and the stand of
each field plot.

How, for one run:
  1. The saved assets are opened BY THE PATHS in docs/demo/demo_set.json. No fingerprint is
     recomputed: with the setting on a config has a new fingerprint by design. The clustering
     assets are deliberately not opened: they hold the types of the old stands.
  2. The merge stage runs on them, once per rule. Its Earth Engine requests do not depend on the
     rule, and the tool checks that the two runs were given identical inputs, so whatever differs
     between the two results is the rule.
  3. The clustering stage runs live on each rule's stands, and one row per stand is read back:
     its type and the scaled features k-means was fitted on. Then the export stage's builder of
     the stand layer runs on the same context and the layer is read back: the polygons, the type
     the export attaches to each stand, and the per-stand columns, exactly as a run would send
     them to Drive.
  4. The superpixel raster is downloaded once, one small GeoTIFF per part of the ROI, on the
     grid the superpixels are stored on. Stand rasters are made from it locally with the merge's
     own superpixel-to-stand table.
  5. Old rule against the run. (a) The merge totals and every stand's pixel count and means
     against the run's own record. (b) The stand raster against the polygons the run exported,
     rasterised on the same grid: every pixel in the same stand. (c) The stand layer read back in
     step 3 against the one the run exported: each stand's type, area and outline.
  6. New rule against old: stands before and after, the share of stand area whose stand
     changed, the plots whose stand changed.
  7. The elbow of k-means on the rows of step 3, for k = 2 to 12, beside the config's k (which is
     not changed).

What it writes. Under --out-dir (git-ignored), per run: remerge/<run_id>/ with the rasters, the
merge inputs and results, the clustering rows, the plots table and a run record; and
vectors_old/ and vectors_new/ with <run_id>_stands_merged.geojson, the stand layer as the export
stage builds it (stand_lbl, cluster_id, area_ha, the per-stand means, the six provenance columns),
which is the form the Phase 2 join reads. Under --summary-dir (committed): <run_id>.json, results
only, no dates.

How a stand gets its type. The export stage takes, for each stand polygon, the commonest type
among the typed pixels it touches, each pixel weighted by the share of it inside the polygon
(`reduceRegions` with `ee.Reducer.mode()`). The types are stored on the grid of the features and
the polygons are drawn on the UTM grid of the superpixels, so a polygon also touches slivers of
its neighbours' pixels. A stand with no habitat pixel of its own, which the fit never typed, can
take a neighbour's type that way. The demo keeps the export's types, because they are what a
run writes; each summary counts the stands this happens to (`stands_typed_by_the_export_only`).

Run from the repo root (fmu reads .env from the working directory).
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import shlex
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO / "odisha_script"))

import raster_vector_tools as tools  # noqa: E402

DEMO_SET = REPO / "docs" / "demo" / "demo_set.json"
RULES = {"old": False, "new": True}  # rule name -> merge.pass2_skip_at_min_area
SETTING = "pass2_skip_at_min_area"
NODATA = -1
UNTYPED = 255  # in a raster of stand types: this pixel has none
K_RANGE = range(2, 13)
# The merge totals compared with the run's record (those the record held when it was written).
PINNED_DIAGNOSTICS = (
    "n_superpixels", "n_stands", "reduction_factor", "pass1_rounds", "pass1_merges",
    "pass1_pairs_blocked_by_area_round1", "pass1_pairs_blocked_by_undefined_criteria_round1",
    "pass2_iterations", "pass2_merges", "pass2_fallback_merges", "stands_below_min_area",
    "area_in_undersized_stands_ha", "orphans_isolated", "orphans_area_blocked",
    "orphans_no_attribute_match", "stands_with_incomplete_criteria",
)
# Assets the clustering stage wrote for the OLD stands. Never put in the context.
CLUSTERING_KEYS = {"cluster_labels", "feature_stack"}


def progress(text: str) -> None:
    print(f"  ... {text}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Pure helpers (no Earth Engine): tested in tests/test_remerge_demo_set.py
# ---------------------------------------------------------------------------


def stand_raster(labels: np.ndarray, valid: np.ndarray, raw_labels: list[int],
                 assignment: list[int]) -> tuple[np.ndarray, int]:
    """Superpixel labels to stand ids with the merge's own table.

    `raw_labels[i]` is the label of superpixel i and `assignment[i]` its stand. Returns the stand
    raster (NODATA where not valid) and the number of valid pixels whose label the merge never saw
    (they are set to NODATA as well, and reported).
    """
    table = dict(zip(raw_labels, assignment, strict=True))
    out = np.full(labels.shape, NODATA, dtype=np.int32)
    values, inverse = np.unique(labels[valid], return_inverse=True)
    mapped = np.array([table.get(int(v), NODATA) for v in values], dtype=np.int32)
    out[valid] = mapped[inverse]
    unseen = int(np.count_nonzero(out[valid] == NODATA))
    return out, unseen


def compare_records(mine: dict[str, Any], theirs: dict[str, Any], *, tolerance: float = 1e-9) -> dict[str, Any]:
    """The merge of this tool against the run's own record: totals, then every stand.

    `mine` and `theirs` hold "merge_diagnostics" and "stand_attributes" (stand id -> values; ids
    are strings after JSON). Numbers are equal when they differ by at most `tolerance`.
    """
    def same(a: Any, b: Any) -> bool:
        if isinstance(a, int | float) and isinstance(b, int | float) and not isinstance(a, bool):
            return abs(float(a) - float(b)) <= tolerance
        return a == b

    totals = {k: [mine["merge_diagnostics"].get(k), theirs["merge_diagnostics"].get(k)] for k in PINNED_DIAGNOSTICS}
    totals_differ = {k: v for k, v in totals.items() if not same(*v)}
    a = {str(k): v for k, v in mine["stand_attributes"].items()}
    b = {str(k): v for k, v in theirs["stand_attributes"].items()}
    differing, worst = [], 0.0
    for sid in sorted(set(a) & set(b), key=int):
        for key in sorted(set(a[sid]) | set(b[sid])):
            x, y = a[sid].get(key), b[sid].get(key)
            if not same(x, y):
                differing.append([sid, key, x, y])
            if isinstance(x, int | float) and isinstance(y, int | float):
                worst = max(worst, abs(float(x) - float(y)))
    return {
        "totals_equal": not totals_differ,
        "totals_that_differ": totals_differ,
        "stands_mine": len(a),
        "stands_theirs": len(b),
        "same_stand_ids": set(a) == set(b),
        "stand_values_that_differ": len(differing),
        "largest_difference": worst,
        "examples": differing[:10],
        "equal": not totals_differ and set(a) == set(b) and not differing,
    }


def stands_on_grid(stands: np.ndarray, stands_transform: Any, stands_crs: Any,
                   shape_hw: tuple[int, int], transform: Any, crs: Any) -> np.ndarray:
    """The stand under the centre of every pixel of another grid (NODATA where there is none).

    Stand rasters are on the UTM grid; stand types are stored and fitted on the geographic grid
    of the features. This puts the stands on that grid, by looking up each pixel centre.
    """
    from pyproj import Transformer

    rows, cols = np.indices(shape_hw)
    xs = transform.c + (cols + 0.5) * transform.a + (rows + 0.5) * transform.b
    ys = transform.f + (cols + 0.5) * transform.d + (rows + 0.5) * transform.e
    to_stands = Transformer.from_crs(crs, stands_crs, always_xy=True)
    x, y = to_stands.transform(xs.ravel(), ys.ravel())
    inv = ~stands_transform
    c = np.floor(inv.a * np.asarray(x) + inv.b * np.asarray(y) + inv.c).astype(np.int64)
    r = np.floor(inv.d * np.asarray(x) + inv.e * np.asarray(y) + inv.f).astype(np.int64)
    inside = (r >= 0) & (r < stands.shape[0]) & (c >= 0) & (c < stands.shape[1])
    out = np.full(xs.size, NODATA, dtype=np.int32)
    out[inside] = stands[r[inside], c[inside]]
    return out.reshape(shape_hw)


def types_by_mode(stands: np.ndarray, type_raster: np.ndarray, untyped: int) -> dict[int, int | None]:
    """The type of each stand as the export stage takes it: the commonest type among its pixels.

    `stands` and `type_raster` are on the same grid (the one the types are stored on).
    `type_raster` holds `untyped` where a pixel has no type (outside habitat). A stand with no
    typed pixel has no type. On a tie the smaller type number wins.
    """
    out: dict[int, int | None] = {}
    ok = stands != NODATA
    for sid in np.unique(stands[ok]):
        values = type_raster[ok & (stands == sid)]
        values = values[values != untyped]
        if values.size == 0:
            out[int(sid)] = None
            continue
        found, counts = np.unique(values, return_counts=True)
        out[int(sid)] = int(found[np.argmax(counts)])
    return out


def typing_agreement(a: np.ndarray, b: np.ndarray, both: np.ndarray) -> dict[str, Any]:
    """How alike two type maps are, whatever the type numbers: adjusted Rand index over pixels.

    k-means numbers its types afresh on every fit, so type 3 of one fit need not be type 3 of
    another; the index compares the groupings, not the numbers. 1 means the same grouping.
    """
    from sklearn.metrics import adjusted_rand_score

    n = int(np.count_nonzero(both))
    return {"pixels_typed_in_both": n,
            "adjusted_rand_index": round(float(adjusted_rand_score(a[both], b[both])), 4) if n else None}


def knee(ks: list[int], inertia: list[float]) -> int:
    """The k at the elbow: the point farthest from the chord between the first and last.

    The definition of odisha_script/odisha_phase3_2_stand_k_elbow.py, kept identical.
    """
    x, y = np.array(ks, float), np.array(inertia, float)
    x = (x - x.min()) / (x.max() - x.min())
    y = (y - y.min()) / (y.max() - y.min())
    num = np.abs((y[-1] - y[0]) * x - (x[-1] - x[0]) * y + x[-1] * y[0] - y[-1] * x[0])
    return ks[int(np.argmax(num / np.hypot(y[-1] - y[0], x[-1] - x[0])))]


def elbow(rows: np.ndarray) -> dict[str, Any]:
    """k-means on one row per stand for k = 2 to 12 (seed 42, 25 starts), and the elbow.

    `rows` are the scaled features the pipeline's k-means was fitted on. That is not the input of
    the Phase 3 elbow file, which scaled raw stand means itself; the method is the same.
    """
    from sklearn.cluster import KMeans

    ks, inertia = [], []
    for k in K_RANGE:
        if k >= len(rows):
            break
        ks.append(k)
        inertia.append(float(KMeans(n_clusters=k, random_state=42, n_init=25).fit(rows).inertia_))
    if len(ks) < 3:
        return {"rows": len(rows), "ks": ks, "inertia": inertia, "elbow_k": None}
    return {"rows": len(rows), "ks": ks, "inertia": [round(v, 6) for v in inertia], "elbow_k": knee(ks, inertia)}


def exported_types(features: list[dict[str, Any]]) -> dict[int, int | None]:
    """stand_lbl -> type from an exported stands_merged layer.

    A stand is one or more features. `cluster_id` is a float with noise, or missing. Pieces of one
    stand that disagree give the type of the largest piece, as the join's area-summing does not
    care; the caller is told how many disagree.
    """
    best: dict[int, tuple[float, int | None]] = {}
    for f in features:
        p = f["properties"]
        sid = int(float(p["stand_lbl"]))
        cid = p.get("cluster_id")
        typ = None if cid is None else int(round(float(cid)))
        area = float(p.get("area_ha") or 0.0)
        if sid not in best or area > best[sid][0]:
            best[sid] = (area, typ)
    return {sid: typ for sid, (_area, typ) in best.items()}


def compare_layers(mine: list[dict[str, Any]], theirs: list[dict[str, Any]], *,
                   area_tolerance_ha: float = 1e-6, outline_tolerance: float = 1e-6) -> dict[str, Any]:
    """Two stands_merged layers, stand by stand: type, area and outline.

    A stand is every feature with its `stand_lbl`. Areas are summed over its pieces. Outlines are
    compared as the area of the two unions' symmetric difference over the area of their union,
    which is 0 for identical polygons; a stand passes at or below `outline_tolerance`.
    """
    from shapely.geometry import shape
    from shapely.ops import unary_union

    def by_stand(features: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        out: dict[int, dict[str, Any]] = {}
        for f in features:
            sid = int(float(f["properties"]["stand_lbl"]))
            d = out.setdefault(sid, {"pieces": 0, "area_ha": 0.0, "geoms": []})
            d["pieces"] += 1
            d["area_ha"] += float(f["properties"].get("area_ha") or 0.0)
            d["geoms"].append(shape(f["geometry"]))
        return out

    a, b = by_stand(mine), by_stand(theirs)
    types_a, types_b = exported_types(mine), exported_types(theirs)
    shared = sorted(set(a) & set(b))
    type_differs = [s for s in shared if types_a[s] != types_b[s]]
    area_differs = [s for s in shared if abs(a[s]["area_ha"] - b[s]["area_ha"]) > area_tolerance_ha]
    pieces_differ = [s for s in shared if a[s]["pieces"] != b[s]["pieces"]]
    outline_differs = []
    for s in shared:
        ga, gb = unary_union(a[s]["geoms"]), unary_union(b[s]["geoms"])
        union = ga.union(gb).area
        if union > 0 and ga.symmetric_difference(gb).area / union > outline_tolerance:
            outline_differs.append(s)
    only = {"only_in_mine": sorted(set(a) - set(b)), "only_in_theirs": sorted(set(b) - set(a))}
    return {
        "features": {"mine": len(mine), "theirs": len(theirs)},
        "stands": {"mine": len(a), "theirs": len(b), **{k: len(v) for k, v in only.items()}},
        "stands_whose_type_differs": len(type_differs),
        "stands_whose_area_differs": len(area_differs),
        "stands_whose_number_of_pieces_differs": len(pieces_differ),
        "stands_whose_outline_differs": len(outline_differs),
        "examples_of_a_different_type": [[s, types_a[s], types_b[s]] for s in type_differs[:10]],
        "equal": not (type_differs or area_differs or pieces_differ or outline_differs
                      or only["only_in_mine"] or only["only_in_theirs"]) and len(mine) == len(theirs),
    }


def summary_table(summaries: list[dict[str, Any]]) -> str:
    """The Markdown table of docs/demo/remerge.md from the per-run summaries."""
    head = ("| Run | Old rule reproduces the run | Stands, old to new | Stand area that changed stand | "
            "Plots that changed stand | k in the config | Elbow, old / new stands |\n|---|---|---|---|---|---|---|")
    lines = [head]
    for s in sorted(summaries, key=lambda s: s["run_id"]):
        check = s["old_rule_check"]
        ok = "yes" if check["reproduces"] else "**NO**"
        ch = s["change"]
        plots = s.get("plots")
        lines.append(
            f"| `{s['run_id']}` | {ok} | {s['stands']['old']} to {s['stands']['new']} | "
            f"{100.0 * ch['share_area_changed']:.1f}% ({ch['area_ha_changed']:.1f} of {ch['area_ha_total']:.1f} ha) | "
            + (f"{plots['changed_stand']} of {plots['in_a_stand']}" if plots else "no field plots")
            + f" | {s['k']} | {s['elbow']['old']['elbow_k']} / {s['elbow']['new']['elbow_k']} |"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Earth Engine side
# ---------------------------------------------------------------------------


def download(image: Any, bounds: tuple[float, float, float, float], crs: str, scale: float,
             path: Path, attempts: int = 4) -> None:
    """One interactive download of `image` over lon/lat `bounds`, on the `crs` grid at `scale`.

    The grid is anchored at the CRS origin, which is the lattice superpixels are stored on (their
    assets sit at multiples of the scale). Retries a failed request before giving up.
    """
    import ee

    params = {
        "region": ee.Geometry.Rectangle(list(bounds), "EPSG:4326", False),
        "crs": crs,
        "crs_transform": [scale, 0, 0, 0, -scale, 0],
        "format": "GEO_TIFF",
    }
    for attempt in range(1, attempts + 1):
        try:
            url = image.getDownloadURL(params)
            with urllib.request.urlopen(url, timeout=600) as response:  # noqa: S310 - Earth Engine url
                data = response.read()
            break
        except Exception as exc:  # noqa: BLE001 - retried, then raised
            progress(f"download of {path.name} failed (attempt {attempt} of {attempts}): {exc}")
            if attempt == attempts:
                raise RuntimeError(f"could not download {path.name}: {exc}") from exc
            time.sleep(20)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def centre_inside(geometry: Any, crs: str, transform: Any, shape_hw: tuple[int, int]) -> np.ndarray:
    """True for the pixels of a `crs` grid whose centre lies inside a lon/lat geometry.

    This is the rule the pipeline's own stand polygons follow, so a raster cut this way covers
    the pixels they cover. A pixel the ROI outline only crosses is left out.
    """
    from pyproj import Transformer
    from rasterio.features import geometry_mask
    from shapely.geometry import mapping
    from shapely.ops import transform as shp_transform

    fwd = Transformer.from_crs(4326, crs, always_xy=True).transform
    projected = shp_transform(fwd, geometry)
    return geometry_mask([mapping(projected)], out_shape=shape_hw, transform=transform, invert=True)


def rasterise_exported(features: list[dict[str, Any]], crs: str, transform: Any, shape_hw: tuple[int, int]) -> np.ndarray:
    """An exported stand layer (lon/lat polygons with stand_lbl) as a stand raster on a grid."""
    from pyproj import Transformer
    from rasterio.features import rasterize
    from shapely.geometry import mapping, shape
    from shapely.ops import transform as shp_transform

    fwd = Transformer.from_crs(4326, crs, always_xy=True).transform
    shapes = [
        (mapping(shp_transform(fwd, shape(f["geometry"]))), int(float(f["properties"]["stand_lbl"])))
        for f in features
    ]
    return rasterize(shapes, out_shape=shape_hw, transform=transform, fill=NODATA, dtype="int32", all_touched=False)


def remerge_run(run: dict[str, Any], out_dir: Path, summary_dir: Path, argv: list[str]) -> dict[str, Any]:
    import ee
    from transparency_masking import roi_parts

    import fmu.stages.clustering as clustering_module
    import fmu.stages.merge as merge_module
    from fmu.config import load_config
    from fmu.stages.base import PipelineContext
    from fmu.stages.clustering import ClusteringStage
    from fmu.stages.merge import MergeStage
    from fmu.utils.gee import load_roi_geometry, safe_get_info
    from fmu.utils.provenance import git_state

    run_id = run["run_id"]
    work = out_dir / "remerge" / run_id
    work.mkdir(parents=True, exist_ok=True)
    cfg = load_config(REPO / run["config"])
    scale = cfg.export.analysis_scale_m
    roi = load_roi_geometry(cfg.roi.roi_file)
    assets = {a["key"]: a["asset"] for a in run["assets"]}
    record: dict[str, Any] = {
        "run_id": run_id,
        "command_line": "python " + " ".join(shlex.quote(a) for a in argv),
        "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "git": {k: v for k, v in git_state().items() if k != "root"},
        "assets_opened": sorted(v for k, v in assets.items() if k not in CLUSTERING_KEYS),
        "export_tasks_submitted": 0,
    }

    def base_context() -> PipelineContext:
        ctx = PipelineContext()
        ctx.set("roi", roi)
        for key, path in assets.items():
            if key not in CLUSTERING_KEYS:
                ctx.set(key, ee.Image(path))
        return ctx

    # ---- 2. the merge, once per rule, with its inputs and its table captured
    captured: dict[str, dict[str, Any]] = {}
    real_merge = merge_module.merge_superpixels

    def run_merge(rule: str) -> tuple[PipelineContext, Any]:
        on = RULES[rule]
        cfg_rule = cfg.model_copy(update={"merge": cfg.merge.model_copy(update={SETTING: on})})

        def spy(graph: Any, means: Any, valid_counts: Any, **kwargs: Any) -> Any:
            result = real_merge(graph, means, valid_counts, **kwargs)
            captured[rule] = {"graph": graph, "means": means, "valid_counts": valid_counts,
                              "settings": kwargs, "result": result}
            return result

        merge_module.merge_superpixels = spy
        try:
            ctx = base_context()
            stage = MergeStage()
            stage.validate(ctx, cfg_rule)
            progress(f"{run_id}: merge, {rule} rule")
            res = stage.run(ctx, cfg_rule)
        finally:
            merge_module.merge_superpixels = real_merge
        assert captured[rule]["settings"][SETTING] is on
        for key, value in res.outputs.items():
            ctx.set(key, value)
        return ctx, cfg_rule

    contexts = {rule: run_merge(rule) for rule in RULES}
    old, new = captured["old"], captured["new"]
    same_inputs = (
        old["graph"].raw_labels == new["graph"].raw_labels
        and old["graph"].n_pixels == new["graph"].n_pixels
        and old["graph"].edges == new["graph"].edges
        and old["means"] == new["means"]
        and old["valid_counts"] == new["valid_counts"]
        and {k: v for k, v in old["settings"].items() if k != SETTING}
        == {k: v for k, v in new["settings"].items() if k != SETTING}
    )
    if not same_inputs:
        raise SystemExit(f"{run_id}: Earth Engine gave the two merges different inputs; the comparison would not be of the rule alone")
    graph = old["graph"]
    (work / "merge_inputs.json").write_text(json.dumps({
        "raw_labels": graph.raw_labels, "n_pixels": graph.n_pixels,
        "edges": [[i, j, c] for (i, j), c in sorted(graph.edges.items())], "scale_m": graph.scale_m,
        "means": {str(k): v for k, v in old["means"].items()},
        "valid_counts": {str(k): v for k, v in old["valid_counts"].items()},
        "settings": {k: v for k, v in old["settings"].items() if k not in ("centroids", SETTING)},
        "centroids": {str(k): list(v) for k, v in (old["settings"].get("centroids") or {}).items()},
    }) + "\n")
    merged: dict[str, dict[str, Any]] = {}
    for rule in RULES:
        ctx = contexts[rule][0]
        merged[rule] = {
            "merge_diagnostics": ctx.get("merge_diagnostics"),
            "stand_attributes": {str(k): v for k, v in ctx.get("stand_attributes").items()},
            "stand_provenance": {str(k): v for k, v in ctx.get("stand_provenance").items()},
            "assignment": captured[rule]["result"].assignment,
            SETTING: RULES[rule],
        }
        (work / f"merge_{rule}.json").write_text(json.dumps(merged[rule], indent=1) + "\n")

    # ---- 3. clustering, live, per rule; one row per stand
    from fmu.stages.export import _build_merged_feature_collection

    fit_types: dict[str, dict[int, int | None]] = {}
    layers: dict[str, list[dict[str, Any]]] = {}
    label_images: dict[str, Any] = {}
    clustering_files: dict[str, dict[str, Any]] = {}
    elbows: dict[str, Any] = {}
    cluster_meta: dict[str, Any] = {}
    for rule in RULES:
        ctx, cfg_rule = contexts[rule]
        stage = ClusteringStage()
        stage.validate(ctx, cfg_rule)
        progress(f"{run_id}: clustering live, {rule} rule")
        res = stage.run(ctx, cfg_rule)
        for key, value in res.outputs.items():
            ctx.set(key, value)
        labels, stack = res.outputs["cluster_labels"], res.outputs["feature_stack"]
        meta = json.loads(safe_get_info(labels.get("clustering_metadata"), context="clustering metadata"))
        bands = meta["active_bands"]
        progress(f"{run_id}: one row per stand, {rule} rule")
        # The scaled bands first, so the sample is taken on the grid the fit was made on.
        rows = safe_get_info(
            clustering_module._sample_one_point_per_unit(
                stack.select(bands).addBands(labels), ctx.get("stand_clusters"), roi, scale,
                seed=cfg.clustering.seed, context="one row per stand",
            ),
            context=f"{run_id}: rows of the {rule} stands",
        )["features"]
        label_band = clustering_module.LABEL_BAND
        typed = {int(f["properties"][label_band]): int(round(f["properties"]["cluster_id"])) for f in rows}
        stand_ids = [int(s) for s in merged[rule]["stand_attributes"]]
        fit_types[rule] = {s: typed.get(s) for s in stand_ids}
        label_images[rule] = labels
        matrix = np.array([[f["properties"][b] for b in bands] for f in rows], dtype=float)
        elbows[rule] = elbow(matrix)
        cluster_meta[rule] = {k: meta[k] for k in ("k", "seed", "n_training_units", "n_units_total",
                                                   "n_units_in_habitat", "n_units_outside_habitat",
                                                   "n_units_dropped_null_band") if k in meta}
        clustering_files[rule] = {
            "metadata": meta, "bands": bands,
            "rows": [[int(f["properties"][label_band]), *[f["properties"][b] for b in bands]] for f in rows],
        }
        # The stand layer as the export stage builds it, read back in place of the Drive export.
        progress(f"{run_id}: the stand layer of the export stage, {rule} rule")
        built = _build_merged_feature_collection(ctx=ctx, config=cfg_rule, scale=scale)
        layers[rule] = safe_get_info(
            built.map(lambda f: f.setGeometry(f.geometry().transform("EPSG:4326", 0.1))),
            context=f"{run_id}: stand layer, {rule} rule",
        )["features"]

    # ---- 4. the superpixel raster, per part, and the stand rasters from it
    snic = ee.Image(assets["snic_clusters"]).select(0)
    proj = safe_get_info(snic.projection(), context="superpixel grid")
    crs = proj["crs"]
    record["superpixel_grid"] = {"crs": crs, "transform": proj["transform"]}
    # Both bands are given a value everywhere (sameFootprint False): a download wants one footprint.
    image = (
        snic.unmask(0, False).rename("snic")
        .addBands(snic.mask().gt(0).unmask(0, False).rename("valid"))
        .toInt32()
    )
    saved_labels = ee.Image(assets["cluster_labels"]).select(0)
    type_proj = safe_get_info(saved_labels.projection(), context="grid of the saved stand types")
    type_crs, type_scale = type_proj["crs"], abs(type_proj["transform"][0])
    record["type_grid"] = {"crs": type_crs, "transform": type_proj["transform"]}
    roi_geojson = json.loads((REPO / cfg.roi.roi_file).read_text())
    parts = roi_parts(roi_geojson, name_key="habitations")
    part_data = []
    for part in parts:
        path = work / f"snic_part{part.index + 1:02d}.tif"
        progress(f"{run_id}: superpixel raster, part {part.index + 1} of {len(parts)} ({part.name})")
        w, s, e, n = part.geometry.bounds
        pad = 3 * scale / 111_320.0
        region = (w - pad, s - pad, e + pad, n + pad)
        download(image, region, crs, scale, path)
        raster = tools.read_raster(path)
        labels, valid_band = raster.array[0], raster.array[1]
        valid = (valid_band == 1) & centre_inside(part.geometry, crs, raster.transform, labels.shape)
        stands = {}
        for rule in RULES:
            stands[rule], unseen = stand_raster(labels, valid, graph.raw_labels, merged[rule]["assignment"])
            if unseen:
                record.setdefault("pixels_of_superpixels_the_merge_did_not_see", {})[f"{rule}/part{part.index + 1}"] = unseen
            valid_rule = stands[rule] != NODATA
            _write_raster(work / f"stands_{rule}_part{part.index + 1:02d}.tif", stands[rule], raster, valid_rule)
        # The type of every pixel, on the grid the types are stored on (that of the features):
        # live for each rule, and as the run saved it (the types of the old stands).
        type_rasters, type_grid = {}, None
        sources = {**label_images, "saved": saved_labels}
        for name, labels_image in sources.items():
            tpath = work / f"types_{name}_part{part.index + 1:02d}.tif"
            progress(f"{run_id}: stand types per pixel ({name}), part {part.index + 1} of {len(parts)}")
            download(labels_image.unmask(UNTYPED, False).toUint8(), region, type_crs, type_scale, tpath)
            got = tools.read_raster(tpath)
            if type_grid is not None and (got.array.shape != type_grid.array.shape or got.transform != type_grid.transform):
                raise SystemExit(f"{run_id}: {tpath.name} is not on the grid of the other type rasters")
            type_grid = got
            type_rasters[name] = got.array
        on_type_grid = {
            rule: stands_on_grid(stands[rule], raster.transform, crs, type_grid.array.shape, type_grid.transform, type_crs)
            for rule in RULES
        }
        part_data.append({"part": part, "raster": raster, "labels": labels, "valid": valid, "stands": stands,
                          "types": type_rasters, "stands_on_type_grid": on_type_grid})

    several = tools.labels_in_several_parts([p["stands"]["old"] for p in part_data],
                                            [p["stands"]["old"] != NODATA for p in part_data])
    if several:
        raise SystemExit(f"{run_id}: {len(several)} stand(s) lie in more than one ROI part; the per-part files would split them")
    pixels_raster = sum(int(np.count_nonzero(p["stands"]["old"] != NODATA)) for p in part_data)
    pixel_area_ha = scale * scale / 10_000.0

    # The type of a stand is the one the export stage attaches (see the module docstring). Beside
    # it are kept the fit's own row for the stand and the commonest type among the pixels whose
    # centre is in the stand, on the grid the types are stored on. The three agree except for
    # stands with few or no habitat pixels of their own.
    types: dict[str, dict[int, int | None]] = {}
    for rule in RULES:
        types[rule] = exported_types(layers[rule])
        by_pixels: dict[int, int | None] = {}
        for p in part_data:
            by_pixels.update(types_by_mode(p["stands_on_type_grid"][rule], p["types"][rule], UNTYPED))
        stand_ids = [int(sid) for sid in merged[rule]["stand_attributes"]]
        missing = sorted(set(stand_ids) - set(types[rule]))
        if missing:
            raise SystemExit(f"{run_id}: {len(missing)} stand(s) of the {rule} merge are not in the stand layer read back, e.g. {missing[:5]}")
        fit = fit_types[rule]
        clustering_files[rule]["stand_type"] = {str(k): v for k, v in sorted(types[rule].items())}
        clustering_files[rule]["stand_type_from_the_fit"] = {str(k): v for k, v in sorted(fit.items())}
        clustering_files[rule]["stand_type_by_pixel_centres"] = {str(k): by_pixels.get(k) for k in sorted(stand_ids)}
        cluster_meta[rule]["stands_typed_by_the_export_only"] = sum(
            types[rule][s] is not None and fit.get(s) is None for s in stand_ids)
        cluster_meta[rule]["stands_the_export_types_differently_from_the_fit"] = sum(
            fit.get(s) is not None and types[rule][s] != fit[s] for s in stand_ids)
        cluster_meta[rule]["stands_whose_pixel_centres_disagree_with_the_fit"] = sum(
            by_pixels.get(s) != fit.get(s) for s in stand_ids)
        (work / f"clustering_{rule}.json").write_text(json.dumps(clustering_files[rule]) + "\n")
    in_roi = [p["stands_on_type_grid"]["old"] != NODATA for p in part_data]
    live_old = np.concatenate([p["types"]["old"][m] for p, m in zip(part_data, in_roi, strict=True)])
    saved = np.concatenate([p["types"]["saved"][m] for p, m in zip(part_data, in_roi, strict=True)])
    live_new = np.concatenate([p["types"]["new"][m] for p, m in zip(part_data, in_roi, strict=True)])
    saved_pixels = {
        "pixels_compared": int(live_old.size),
        "pixels_whose_type_differs": int(np.count_nonzero(live_old != saved)),
    }
    both_typed = (live_old != UNTYPED) & (live_new != UNTYPED)
    types_old_new = typing_agreement(live_old, live_new, both_typed)

    # ---- 5. the old rule against what the run itself wrote
    local = run["local"]
    run_record_path = REPO / local["run_record"]
    exported_path = REPO / local["stands_merged"]
    theirs = json.loads(run_record_path.read_text())
    records = compare_records(merged["old"], theirs)
    exported = json.loads(exported_path.read_text())["features"]
    partition_parts, uncovered = [], 0
    for p in part_data:
        mine = p["stands"]["old"]
        had = mine != NODATA
        theirs_raster = rasterise_exported(exported, crs, p["raster"].transform, mine.shape)
        both = had & (theirs_raster != NODATA)
        uncovered += int(np.count_nonzero(had & (theirs_raster == NODATA)))
        partition_parts.append(tools.partition_report(mine, theirs_raster, both))
    partition = {
        "pixels_compared": sum(r["n_pixels"] for r in partition_parts),
        "pixels_in_another_stand": sum(r["pixels_not_in_matching_sets"] for r in partition_parts),
        "same_stand_ids_everywhere": all(r["identical_labels"] for r in partition_parts),
        "same_partition": all(r["same_partition"] for r in partition_parts),
        "pixels_with_no_exported_polygon": uncovered,
    }
    layer_check = compare_layers(layers["old"], exported)
    layer_check["type_pixels_against_the_saved_type_raster"] = saved_pixels
    reproduces = bool(records["equal"] and partition["same_partition"] and partition["pixels_in_another_stand"] == 0)
    old_rule_check = {"reproduces": reproduces, "types_reproduce": layer_check["stands_whose_type_differs"] == 0,
                      "layer_reproduces": layer_check["equal"],
                      "record": records, "pixels": partition, "layer": layer_check}

    # ---- 6. new against old
    change = tools.change_report_parts(
        [(p["stands"]["old"], p["stands"]["new"], p["stands"]["old"] != NODATA) for p in part_data], pixel_area_ha
    )
    plots_summary = None
    if run["site"] == "Odisha":
        from odisha_phase2_0_aois import load_plot_points

        pts = load_plot_points()
        pts = pts[pts.district.str.lower() == run["district"].lower()]
        rows_out = []
        for _, pt in pts.iterrows():
            row = {"plot_key": pt.plot_key, "stand_old": None, "stand_new": None, "changed": None}
            for p in part_data:
                got = tools.sample_at_lonlat(p["stands"]["old"], p["raster"].transform, crs, [pt.lon6], [pt.lat6],
                                             valid=p["stands"]["old"] != NODATA)[0]
                if got is None:
                    continue
                moved = tools.changed_mask(p["stands"]["old"], p["stands"]["new"], p["stands"]["old"] != NODATA)
                row["stand_old"] = int(got)
                row["stand_new"] = int(tools.sample_at_lonlat(p["stands"]["new"], p["raster"].transform, crs,
                                                              [pt.lon6], [pt.lat6])[0])
                row["changed"] = bool(tools.sample_at_lonlat(moved, p["raster"].transform, crs, [pt.lon6], [pt.lat6])[0])
            for rule in RULES:
                sid = row[f"stand_{rule}"]
                row[f"type_{rule}"] = None if sid is None else types[rule].get(sid)
            rows_out.append(row)
        with (work / "plots.csv").open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["plot_key", "stand_old", "stand_new", "changed", "type_old", "type_new"])
            writer.writeheader()
            writer.writerows(rows_out)
        inside = [r for r in rows_out if r["stand_old"] is not None]
        plots_summary = {
            "in_the_district": len(rows_out),
            "in_a_stand": len(inside),
            "changed_stand": sum(bool(r["changed"]) for r in inside),
            "changed_stand_keys": sorted(r["plot_key"] for r in inside if r["changed"]),
            "with_a_type": {rule: sum(r[f"type_{rule}"] is not None for r in inside) for rule in RULES},
        }

    # ---- the stand layers, in the form the Phase 2 join reads
    for rule in RULES:
        vec = out_dir / f"vectors_{rule}" / f"{run_id}_stands_merged.geojson"
        vec.parent.mkdir(parents=True, exist_ok=True)
        vec.write_text(json.dumps({"type": "FeatureCollection", "features": layers[rule]}))

    summary = {
        "run_id": run_id,
        "site": run["site"],
        "area": run["area"],
        "arm": run["arm"],
        "stand_ceiling_ha": run["stand_ceiling_ha"],
        "k": run["k"],
        "merge_rule": {"old": "merge.pass2_skip_at_min_area false, as the run was made",
                       "new": "merge.pass2_skip_at_min_area true (spec-merge-pass2-skip-at-minimum)"},
        "superpixels_in_merge": merged["old"]["merge_diagnostics"]["n_superpixels"],
        "pixels": {"in_the_merge": int(sum(graph.n_pixels)), "on_the_downloaded_grid": pixels_raster},
        "old_rule_check": old_rule_check,
        "stands": {rule: merged[rule]["merge_diagnostics"]["n_stands"] for rule in RULES},
        "merge_totals": {rule: {k: merged[rule]["merge_diagnostics"][k] for k in PINNED_DIAGNOSTICS} for rule in RULES},
        "stands_with_a_type": {rule: sum(v is not None for v in types[rule].values()) for rule in RULES},
        "clustering": cluster_meta,
        "change": change,
        "types_old_against_new": types_old_new,
        "plots": plots_summary,
        "elbow": elbows,
        "export_tasks_submitted": 0,
    }
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / f"{run_id}.json").write_text(json.dumps(summary, indent=1) + "\n")
    (work / "run_record.json").write_text(json.dumps(record, indent=1) + "\n")
    return summary


def _write_raster(path: Path, array: np.ndarray, like: Any, valid: np.ndarray) -> None:
    import rasterio

    out = np.where(valid, array, NODATA).astype("int32")
    profile = {"driver": "GTiff", "height": out.shape[0], "width": out.shape[1], "count": 1, "dtype": "int32",
               "crs": like.crs, "transform": like.transform, "compress": "deflate", "nodata": NODATA}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(out, 1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", nargs="+", default=[], help="run ids from docs/demo/demo_set.json")
    ap.add_argument("--all", action="store_true", help="every run of the demo set")
    ap.add_argument("--out-dir", type=Path, default=REPO / "outputs" / "demo")
    ap.add_argument("--summary-dir", type=Path, default=REPO / "docs" / "demo" / "remerge")
    ap.add_argument("--table", action="store_true",
                    help="offline: print the table of every summary in --summary-dir and write it to its README.md")
    args = ap.parse_args()

    if args.table:
        summaries = [json.loads(p.read_text()) for p in sorted(args.summary_dir.glob("*_repro.json"))]
        print(summary_table(summaries))
        return

    demo = json.loads(DEMO_SET.read_text())
    runs = {r["run_id"]: r for r in demo["runs"]}
    wanted = sorted(runs) if args.all else args.run
    unknown = [r for r in wanted if r not in runs]
    if unknown or not wanted:
        raise SystemExit(f"name runs of the demo set (--run ... or --all); unknown: {unknown}")

    import ee
    import ee_read_only

    import fmu.stages.clustering  # noqa: F401  (importing registers the stages)
    import fmu.stages.merge  # noqa: F401
    from fmu.utils.gee import init_gee

    init_gee()
    ee.data.setDeadline(7 * 60 * 1000)
    ee_read_only.forbid_writes()
    failed = []
    for run_id in wanted:
        started = time.time()
        try:
            s = remerge_run(runs[run_id], args.out_dir, args.summary_dir, sys.argv)
        except Exception as exc:  # noqa: BLE001 - one run failing must not stop the rest
            failed.append(run_id)
            print(f"{run_id}: FAILED: {' '.join(str(exc).split())[:400]}", flush=True)
            continue
        ch, check = s["change"], s["old_rule_check"]
        print(
            f"{run_id}: old rule reproduces the run: {check['reproduces']} "
            f"(record equal {check['record']['equal']}, pixels in another stand {check['pixels']['pixels_in_another_stand']} "
            f"of {check['pixels']['pixels_compared']}), its stand layer: {check['layer_reproduces']} "
            f"({check['layer']['stands_whose_type_differs']} stands differ in type, "
            f"{check['layer']['stands_whose_outline_differs']} in outline, from the exported layer); "
            f"stands {s['stands']['old']} -> {s['stands']['new']}; "
            f"{100.0 * ch['share_area_changed']:.1f}% of stand area changed stand; "
            f"elbow {s['elbow']['old']['elbow_k']} / {s['elbow']['new']['elbow_k']} (k {s['k']})",
            flush=True,
        )
        progress(f"{run_id}: {time.time() - started:.0f} s")
    print("export tasks submitted: 0")
    if failed:
        raise SystemExit(f"failed: {failed}")


if __name__ == "__main__":
    main()
