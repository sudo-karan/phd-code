"""Fetch the pixel-level feature layers the UI shows, from a run's saved assets.

    python scripts/fetch_ui_layers.py --run <run_id> [<run_id> ...]      # or --all
        [--demo-set docs/demo/demo_set.json] [--grids outputs/transparency_repro/_mask_data]
        [--out outputs/ui_data_full]

READ-ONLY on Earth Engine. It opens saved assets by the paths in the demo set and makes small
interactive downloads. It submits no task and writes, changes or deletes no asset:
`ee_read_only.forbid_writes()` makes any such call raise before it is sent.

What it fetches, per part of the run's ROI, as one GeoTIFF with named bands:
  - hand-crafted runs: `features_partNN.tif`, the bands segmentation uses
    (`segmentation.input_bands` of the run's config) and ETH canopy height;
  - AlphaEarth runs: `embedding_partNN.tif`, the 64 bands of the embedding.
Pixels where any of the bands has no data are written as NaN.

The grid. Each part is fetched on the grid of the part's true-colour GeoTIFF that the masking
transparency tool saved (`--grids/<run_id>/partNN_*_true_colour.tif`), so every display raster of
a part lines up pixel for pixel. That grid is a 10 m geographic grid over the part. It is a
display grid: the saved assets are sampled onto it by nearest neighbour.

`scripts/export_ui_data.py` turns these files into the PNGs the explorer shows; the GeoTIFFs stay
in the git-ignored `--out` folder. A part whose file is already there is skipped.

Run from the repo root (fmu reads .env from the working directory).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ETH canopy height: (the context key of the image that holds it, its band).
CANOPY_HEIGHT = ("structure_features", "canopy_height")
NODATA = -9999.0


def bands_to_fetch(input_bands: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The (source, band) pairs segmentation uses, then ETH canopy height if it is not one of them.

    A band computed inside the segmentation stage (`composite_nirv`) is on no saved image and is
    left out; the caller is told which.
    """
    wanted = [pair for pair in input_bands if pair[1] != "composite_nirv"]
    return list(dict.fromkeys([*wanted, CANOPY_HEIGHT]))


def grid_files(grids: Path, run_id: str) -> list[Path]:
    """The true-colour GeoTIFF of each part, in part order."""
    found = sorted((grids / run_id).glob("part[0-9][0-9]_*_true_colour.tif"))
    if not found:
        raise SystemExit(f"{run_id}: no part*_true_colour.tif under {grids / run_id}; "
                         "run the masking transparency tool for this run first")
    return found


def mask_nodata(data: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Float32 bands with NaN wherever `valid` is 0. `data` is (bands, rows, cols)."""
    out = data.astype("float32")
    out[:, valid == 0] = np.nan
    return out


def fetch_part(image: Any, band_names: list[str], grid: Path, out: Path, attempts: int = 4) -> None:
    """One part: `image` sampled on the grid of `grid`, written to `out` with named bands."""
    import ee
    import rasterio

    with rasterio.open(grid) as ref:
        transform, shape, crs = ref.transform, ref.shape, ref.crs
        west, south, east, north = ref.bounds
    # A hair inside the outer edge, so the request covers exactly the reference pixels.
    eps = abs(transform.a) / 4
    params = {
        "region": ee.Geometry.Rectangle([west + eps, south + eps, east - eps, north - eps], "EPSG:4326", False),
        "crs": crs.to_string(),
        "crs_transform": [transform.a, transform.b, transform.c, transform.d, transform.e, transform.f],
        "format": "GEO_TIFF",
    }
    valid = image.mask().reduce(ee.Reducer.min()).gt(0).rename("valid")
    request = image.unmask(NODATA, False).toFloat().addBands(valid.unmask(0, False).toFloat())
    tmp = out.with_suffix(".download.tif")
    for attempt in range(1, attempts + 1):
        try:
            url = request.getDownloadURL(params)
            with urllib.request.urlopen(url, timeout=900) as response:  # noqa: S310 - Earth Engine url
                tmp.write_bytes(response.read())
            break
        except Exception as exc:  # noqa: BLE001 - retried, then raised
            print(f"  ... {out.name}: attempt {attempt} of {attempts} failed: {str(exc)[:160]}", file=sys.stderr, flush=True)
            if attempt == attempts:
                raise RuntimeError(f"could not fetch {out.name}: {exc}") from exc
            time.sleep(20)
    with rasterio.open(tmp) as got:
        data = got.read()
        if got.shape != shape or got.transform != transform:
            raise SystemExit(f"{out.name}: fetched on another grid than {grid.name} "
                             f"({got.shape} against {shape}); not written")
    bands = mask_nodata(data[:-1], data[-1])
    profile = {"driver": "GTiff", "height": shape[0], "width": shape[1], "count": bands.shape[0],
               "dtype": "float32", "crs": crs, "transform": transform, "compress": "deflate",
               "nodata": float("nan")}
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(bands)
        dst.descriptions = tuple(band_names)
    tmp.unlink()


def fetch_run(run: dict[str, Any], grids: Path, out_dir: Path) -> dict[str, Any]:
    import ee

    from fmu.config import load_config
    from fmu.utils.gee import safe_get_info
    from fmu.utils.provenance import git_state

    run_id = run["run_id"]
    cfg = load_config(REPO / run["config"])
    assets = {a["key"]: a["asset"] for a in run["assets"]}
    if run["arm"] == "alphaearth":
        image = ee.Image(assets["embedding_features"])
        names = safe_get_info(image.bandNames(), context=f"{run_id}: embedding bands")
        stem, opened = "embedding", [assets["embedding_features"]]
    else:
        pairs = bands_to_fetch([(b.source, b.band) for b in cfg.segmentation.input_bands])
        names = [band for _source, band in pairs]
        opened = sorted({assets[source] for source, _band in pairs})
        image = ee.Image.cat([ee.Image(assets[source]).select([band]) for source, band in pairs])
        stem = "features"
    work = out_dir / run_id
    work.mkdir(parents=True, exist_ok=True)
    files = []
    for grid in grid_files(grids, run_id):
        part = grid.name[:6]
        out = work / f"{stem}_{part}.tif"
        if not out.exists():
            print(f"  ... {run_id}: {out.name}", file=sys.stderr, flush=True)
            fetch_part(image, names, grid, out)
        files.append(out.name)
    record = {
        "run_id": run_id, "bands": names, "files": files, "grid_from": str(grids / run_id),
        "assets_opened": sorted(opened), "git": {k: v for k, v in git_state().items() if k != "root"},
        "export_tasks_submitted": 0,
    }
    (work / f"{stem}_fetch_record.json").write_text(json.dumps(record, indent=1) + "\n")
    return record


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", nargs="+", default=[], help="run ids from the demo set")
    ap.add_argument("--all", action="store_true", help="every run of the demo set")
    ap.add_argument("--demo-set", type=Path, default=REPO / "docs" / "demo" / "demo_set.json")
    ap.add_argument("--grids", type=Path, default=REPO / "outputs" / "transparency_repro" / "_mask_data")
    ap.add_argument("--out", type=Path, default=REPO / "outputs" / "ui_data_full")
    args = ap.parse_args()

    runs = {r["run_id"]: r for r in json.loads(args.demo_set.read_text())["runs"]}
    wanted = sorted(runs) if args.all else args.run
    unknown = [r for r in wanted if r not in runs]
    if unknown or not wanted:
        raise SystemExit(f"name runs of the demo set (--run ... or --all); unknown: {unknown}")

    import ee
    import ee_read_only

    from fmu.utils.gee import init_gee

    init_gee()
    ee.data.setDeadline(7 * 60 * 1000)
    ee_read_only.forbid_writes()
    failed = []
    for run_id in wanted:
        try:
            record = fetch_run(runs[run_id], args.grids, args.out)
        except Exception as exc:  # noqa: BLE001 - one run failing must not stop the rest
            failed.append(run_id)
            print(f"{run_id}: FAILED: {' '.join(str(exc).split())[:300]}", flush=True)
            continue
        print(f"{run_id}: {len(record['files'])} part(s), {len(record['bands'])} band(s)", flush=True)
    print("export tasks submitted: 0")
    if failed:
        raise SystemExit(f"failed: {failed}")


if __name__ == "__main__":
    main()
