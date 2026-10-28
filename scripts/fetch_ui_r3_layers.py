"""Fetch the display rasters of the R3 runs, read-only, for the explorer (round 15).

    python scripts/fetch_ui_r3_layers.py [--out outputs/ui_data_full] [--check]

READ-ONLY on Earth Engine. `ee_read_only.forbid_writes()` is called right after `init_gee()`,
before any other Earth Engine call, so no task can be submitted and no asset written, changed or
deleted. It opens R3's cached assets by the ids their export manifests give (each stage's cache
key under the per-step layout: `{asset root}/{config}/{stage}/{output}__{key}`) and makes small
interactive downloads.

R3's runs are the eighteen with an export manifest in docs/reproducibility/r14_runs/second_half/
(`r3_runs`). They lie on five areas, one ROI file each: Sanjay Van's rectangle and each Odisha
district's boxes. The four runs of a district (two arms, two stand sizes), and the two at Sanjay
Van, share their masking and data_load step keys, which `areas` checks from the manifests before
any call: the same key is the same computation, so one run's assets give the area's display
rasters for every R3 run on it.

What it writes, under --out (git-ignored):
  r14_areas/<area>/<part>_true_colour.tif  the S2 composite's red, green and blue on a 10 m
      EPSG:4326 display grid over each part of the ROI, as scripts/transparency_masking.py
      downloads it (the asset is on the ROI's UTM grid, so this resamples it, review C31; it is
      only drawn, smoothed);
  r14_areas/<area>/<part>_mask_provenance.tif  the masking stage's reason and source bands on the
      asset's own grid, not resampled, so that the land-cover shapes drawn from it line up with
      R3's stands, which lie on that grid;
  r14_areas/<area>/fetch_record.json  the assets opened, the runs they serve, the git state;
  <run>/features_part01.tif, <run>/embedding_part01.tif  for the two Sanjay Van runs, the
      per-pixel layers the explorer draws there (round 3's brief): canopy height, the NDVI
      amplitude and VV minus VH for the hand-crafted run, the 64 embedding bands for the
      AlphaEarth run, each from the run's own cached features, on the true colour's grid, as
      scripts/fetch_ui_layers.py fetches them.

A file already there is not fetched again. --check reads the manifests and prints what would be
opened, with no Earth Engine call. Run from the repo root (fmu reads .env from the working
directory).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

R3_RECORDS = REPO / "docs" / "reproducibility" / "r14_runs" / "second_half"
# The stages whose keys must agree across an area's runs for one run's display rasters to serve
# them all, and the outputs read from each.
SHARED_STAGES = ("masking", "data_load")
NODATA = 255
# The bands the explorer draws pixel by pixel for a hand-crafted run, and the cached image each is
# in (build_ui_early_data.DRAWN_FEATURES).
DRAWN_BANDS = (("features_structure", "structure_features", "canopy_height"),
               ("features_optical", "optical_features", "ndvi_amplitude_annual"),
               ("features_radar", "radar_features", "vv_minus_vh_median"))
EMBEDDING = ("features_embedding", "embedding_features")


def r3_runs(records: Path = R3_RECORDS) -> list[str]:
    """R3's runs: those with an export manifest in the second half's records, sorted."""
    return sorted(p.name.removesuffix("_manifest_export.json")
                  for p in records.glob("*_r14_manifest_export.json"))


def manifest(run: str, records: Path = R3_RECORDS) -> dict[str, Any]:
    return json.loads((records / f"{run}_manifest_export.json").read_text())


def stage_keys(m: dict[str, Any]) -> dict[str, str | None]:
    return {s["name"]: s["cache_key"] for s in m["stages"]}


def area_of(m: dict[str, Any]) -> str:
    """The area a run lies on: `sanjay_van`, or the district its boxes are in."""
    roi = Path(m["config"]["roi"]["roi_file"]).stem
    if roi == "sanjay_van":
        return "sanjay_van"
    if roi.startswith("odisha_squares_"):
        return roi.removeprefix("odisha_squares_")
    raise SystemExit(f"{m['config_name']}: an ROI file this script does not know ({roi})")


def areas(records: Path = R3_RECORDS) -> dict[str, dict[str, Any]]:
    """Each area's R3 runs, its ROI file and the run whose assets serve it. Stops unless every run
    of an area has the same masking and data_load keys and the same ROI file."""
    out: dict[str, dict[str, Any]] = {}
    for run in r3_runs(records):
        m = manifest(run, records)
        keys = stage_keys(m)
        a = out.setdefault(area_of(m), {"runs": [], "roi_file": m["config"]["roi"]["roi_file"],
                                        "keys": {s: keys[s] for s in SHARED_STAGES}})
        if m["config"]["roi"]["roi_file"] != a["roi_file"]:
            raise SystemExit(f"{run}: another ROI file than the area's ({a['roi_file']})")
        for s in SHARED_STAGES:
            if keys[s] != a["keys"][s]:
                raise SystemExit(f"{run}: its {s} key {keys[s]} is not its area's {a['keys'][s]}: "
                                 "the area's display rasters would not be its computation")
        a["runs"].append(run)
    for a in out.values():
        a["source"] = a["runs"][0]
    return out


def asset_id(root: str, run: str, stage: str, output: str, m: dict[str, Any]) -> str:
    """A cached output's asset id under the per-step layout, from the run's manifest. Where the
    export pass names the asset (`asset_paths` of its manifest), the id must be that one: a
    wrong asset root in .env stops the script before any call."""
    if m.get("cache_layout") != "per_step":
        raise SystemExit(f"{run}: not on the per-step cache layout")
    st = next(s for s in m["stages"] if s["name"] == stage)
    if output not in st["produced"] or st["cache_status"].get(output) != "hit":
        raise SystemExit(f"{run}: {stage}/{output} is not a cached output of its export pass")
    aid = f"{root}/{run}/{stage}/{output}__{st['cache_key']}"
    export = next((s for s in m["stages"] if s["name"] == "export"), {})
    named = ((export.get("metadata") or {}).get("manifest") or {}).get("asset_paths", {}).get(output)
    if named is not None and named != aid:
        raise SystemExit(f"{run}: {aid} is not the asset its export pass names, {named}")
    return aid


def native_window(bounds: tuple[float, float, float, float], transform: list[float],
                  pad: int = 2) -> tuple[list[float], int, int]:
    """A north-up window over `bounds` (in the grid's own CRS) whose pixel edges are the asset
    grid's, grown to whole pixels and by `pad` pixels: its affine transform, width and height.

    The asset grid may count its rows southward or northward: the cache exports on
    `ee.Projection(<UTM>).atScale(scale)`, whose transform Earth Engine gives as
    [10, 0, 0, 0, 10, 0], so a cached asset reports a positive y step. Either way its pixel edges
    lie at f + j * |e| and c + i * a, and so do the window's: nothing is resampled."""
    a, b, c, d, e, f = transform
    if b or d or a <= 0 or e == 0:
        raise ValueError(f"not a grid aligned with its axes: {transform}")
    step = abs(e)
    minx, miny, maxx, maxy = bounds
    col0 = math.floor((minx - c) / a) - pad
    col1 = math.ceil((maxx - c) / a) + pad
    top = math.ceil((maxy - f) / step) + pad
    bottom = math.floor((miny - f) / step) - pad
    return [a, 0.0, c + col0 * a, 0.0, -step, f + top * step], col1 - col0, top - bottom


def download_native(image: Any, part: Any, proj: dict[str, Any], path: Path,
                    band_names: list[str], attempts: int = 4) -> None:
    """`image` over one part of the ROI on its own grid (`proj`, the asset's projection), as
    uint8 with NODATA outside the part, written to `path`."""
    import time

    import ee
    import rasterio
    from pyproj import Transformer
    from rasterio.transform import Affine
    from shapely.ops import transform as reproject
    from transparency_masking import blank_untouched

    to_grid = Transformer.from_crs("EPSG:4326", proj["crs"], always_xy=True).transform
    part_on_grid = reproject(to_grid, part.geometry)
    window, width, height = native_window(part_on_grid.bounds, proj["transform"])
    west, north = window[2], window[5]
    east, south = west + width * window[0], north + height * window[4]
    eps = window[0] / 4
    params = {
        "region": ee.Geometry.Rectangle([west + eps, south + eps, east - eps, north - eps],
                                        proj["crs"], False),
        "crs": proj["crs"], "crs_transform": window, "format": "GEO_TIFF",
    }
    tmp = path.with_suffix(".download.tif")
    for attempt in range(1, attempts + 1):
        try:
            url = image.unmask(NODATA, False).toUint8().getDownloadURL(params)
            with urllib.request.urlopen(url, timeout=600) as response:  # noqa: S310 - EE url
                tmp.write_bytes(response.read())
            break
        except Exception as exc:  # noqa: BLE001 - retried, then raised
            print(f"  ... {path.name}: attempt {attempt} of {attempts} failed: {str(exc)[:160]}",
                  file=sys.stderr, flush=True)
            if attempt == attempts:
                raise RuntimeError(f"could not fetch {path.name}: {exc}") from exc
            time.sleep(20)
    with rasterio.open(tmp) as got:
        data = got.read()
        if got.shape != (height, width) or got.transform != Affine(*window):
            raise SystemExit(f"{path.name}: fetched on another grid than the asset's window "
                             f"({got.shape}, {got.transform}); not written")
        crs = got.crs
    data = blank_untouched(data, part_on_grid, Affine(*window), NODATA)
    profile = {"driver": "GTiff", "height": height, "width": width, "count": data.shape[0],
               "dtype": "uint8", "crs": crs, "transform": Affine(*window), "compress": "deflate",
               "nodata": NODATA}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)
        dst.descriptions = tuple(band_names)
    tmp.unlink()


def fetch_area(name: str, area: dict[str, Any], root: str, out: Path) -> dict[str, Any]:
    """The true colour and the mask provenance of every part of one area."""
    import ee
    from shapely.geometry import mapping
    from transparency_masking import download_geotiff, roi_parts, snapped_bounds, true_colour_bands

    from fmu.utils.gee import safe_get_info

    run = area["source"]
    m = manifest(run)
    s2 = asset_id(root, run, "data_load", "s2_composite", m)
    prov = asset_id(root, run, "masking", "mask_provenance", m)
    scale = float(m["config"]["export"]["analysis_scale_m"])
    parts = roi_parts(json.loads((REPO / area["roi_file"]).read_text()))
    work = out / "r14_areas" / name
    work.mkdir(parents=True, exist_ok=True)
    rgb_bands = true_colour_bands(safe_get_info(ee.Image(s2).bandNames(), context=f"{run}: bands"))
    proj = safe_get_info(ee.Image(prov).select(["reason"]).projection(), context=f"{run}: grid")
    files = []
    for part in parts:
        geometry = ee.Geometry(mapping(part.geometry))
        tc = work / f"{part.slug}_true_colour.tif"
        if not tc.exists():
            print(f"  ... {name}: {tc.name}", file=sys.stderr, flush=True)
            rgb = ee.Image(s2).select(rgb_bands).clip(geometry)
            download_geotiff(rgb.unmask(0, False).clamp(0, 65535).toUint16(),
                             snapped_bounds(part.geometry.bounds, scale), scale, tc, rgb_bands,
                             "uint16", 0, keep=part.geometry)
        mp = work / f"{part.slug}_mask_provenance.tif"
        if not mp.exists():
            print(f"  ... {name}: {mp.name}", file=sys.stderr, flush=True)
            download_native(ee.Image(prov).select(["reason", "source"]), part, proj, mp,
                            ["reason", "source"])
        files += [tc.name, mp.name]
    return {"area": name, "runs_served": area["runs"], "keys": area["keys"],
            "assets_opened": sorted({s2, prov}), "files": files, "mask_grid": proj}


def fetch_pixels(run: str, area_dir: Path, root: str, out: Path) -> dict[str, Any]:
    """A Sanjay Van run's per-pixel layers, on the true colour's grid of each part."""
    import ee
    from fetch_ui_layers import fetch_part

    from fmu.utils.gee import safe_get_info

    m = manifest(run)
    if any(s["name"] == "features_embedding" and s["cache_key"] for s in m["stages"]):
        image = ee.Image(asset_id(root, run, *EMBEDDING, m))
        names = safe_get_info(image.bandNames(), context=f"{run}: embedding bands")
        stem, opened = "embedding", [asset_id(root, run, *EMBEDDING, m)]
    else:
        opened = [asset_id(root, run, stage, output, m) for stage, output, _ in DRAWN_BANDS]
        names = [band for _, _, band in DRAWN_BANDS]
        image = ee.Image.cat([ee.Image(a).select([b]) for a, b in zip(opened, names, strict=True)])
        stem = "features"
    work = out / run
    work.mkdir(parents=True, exist_ok=True)
    files = []
    for grid in sorted(area_dir.glob("part[0-9][0-9]_*_true_colour.tif")):
        target = work / f"{stem}_{grid.name[:6]}.tif"
        if not target.exists():
            print(f"  ... {run}: {target.name}", file=sys.stderr, flush=True)
            fetch_part(image, names, grid, target)
        files.append(target.name)
    return {"run_id": run, "bands": names, "files": files, "assets_opened": sorted(opened)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=REPO / "outputs" / "ui_data_full")
    ap.add_argument("--check", action="store_true", help="print what would be opened; no call")
    args = ap.parse_args()

    found = areas()
    runs = [r for a in found.values() for r in a["runs"]]
    if len(runs) != 18:
        raise SystemExit(f"R3 is eighteen runs; the records hold {len(runs)}")
    from fmu.settings import get_settings

    root = get_settings().resolved_asset_root()
    for name, a in found.items():
        m = manifest(a["source"])
        print(f"{name}: {len(a['runs'])} runs, keys {a['keys']}; from {a['source']}: "
              f"{asset_id(root, a['source'], 'data_load', 's2_composite', m)}, "
              f"{asset_id(root, a['source'], 'masking', 'mask_provenance', m)}")
    if args.check:
        print("--check: no Earth Engine call made")
        return

    import ee
    import ee_read_only

    from fmu.utils.gee import init_gee
    from fmu.utils.provenance import git_state

    init_gee()
    refused = ee_read_only.forbid_writes()
    ee.data.setDeadline(7 * 60 * 1000)
    git = {k: v for k, v in git_state().items() if k != "root"}
    for name, a in found.items():
        record = fetch_area(name, a, root, args.out)
        if name == "sanjay_van":
            record["pixel_layers"] = [fetch_pixels(run, args.out / "r14_areas" / name, root,
                                                   args.out) for run in a["runs"]]
        record.update({"git": git, "writes_refused": len(refused), "export_tasks_submitted": 0})
        (args.out / "r14_areas" / name / "fetch_record.json").write_text(
            json.dumps(record, indent=1) + "\n")
        print(f"{name}: {len(record['files'])} file(s)", flush=True)
    print("export tasks submitted: 0")


if __name__ == "__main__":
    main()
