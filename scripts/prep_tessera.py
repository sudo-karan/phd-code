"""One-shot: ingest a Tessera embedding for an ROI into an Earth Engine asset.

Tessera (https://github.com/ucam-eo/geotessera) is a 128-channel, 10 m
pretrained embedding, distributed CC0 through the `geotessera` library — but it
lives OFF Earth Engine. To cluster it with the same pipeline that clusters
AlphaEarth (which is GEE-native), it has to be pulled down and uploaded to EE
once. This script does that:

  1. read the ROI bounding box from the config's roi_file (no EE needed),
  2. fetch the Tessera tiles covering that box for a year (geotessera),
  3. export them to GeoTIFF and mosaic to one file clipped to the box,
  4. print the `earthengine upload image` command (and run it with --upload).

Then paste the resulting asset id into configs/sanjay_van_tessera.yaml
(datasets.embedding) and run the pipeline exactly like the AlphaEarth arm.

This is a documented, interactive one-shot — NOT part of the tested pipeline.
`geotessera` is an optional dependency (requires Python 3.12+): install with
`pip install -e '.[tessera]'`. The geotessera API is young; if a call below
does not match your installed version, check its README / readthedocs.

Usage:
    python scripts/prep_tessera.py --config configs/sanjay_van_tessera.yaml \
        --year 2022 --asset projects/<your-ee-project>/assets/tessera_sanjay_van_2022
    # add --upload to run the earthengine upload for you (needs the CLI + auth)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from fmu.config import load_config


def roi_bounds_from_config(config_path: str) -> tuple[float, float, float, float]:
    """(minx, miny, maxx, maxy) lon/lat bbox of the config's ROI geojson.

    Read directly with shapely so no Earth Engine session is needed — this
    script runs entirely off-GEE up to the upload step.
    """
    from shapely.geometry import shape
    from shapely.ops import unary_union

    config = load_config(config_path)
    if config.roi.roi_file is None:
        raise SystemExit(
            f"{config_path}: roi.roi_file is not set; prep_tessera needs a geojson ROI."
        )
    roi_path = Path(config.roi.roi_file)
    if not roi_path.exists():
        raise SystemExit(f"ROI geojson not found: {roi_path}")

    data = json.loads(roi_path.read_text())
    feats = data["features"] if data.get("type") == "FeatureCollection" else [data]
    geom = unary_union([shape(f["geometry"]) for f in feats])
    return tuple(float(v) for v in geom.bounds)  # type: ignore[return-value]


def fetch_tessera_geotiffs(bounds: tuple[float, float, float, float], year: int,
                           out_dir: Path) -> list[Path]:
    """Fetch the Tessera tiles covering `bounds` for `year` and export GeoTIFFs.

    Uses the geotessera region API:
        gt.registry.load_blocks_for_region(bounds=..., year=...)
        gt.export_embedding_geotiffs(tiles, output_dir=...)
    Returns the exported .tif paths. See the geotessera docs if the API differs
    in your installed version.
    """
    try:
        from geotessera import GeoTessera
    except ImportError as e:  # pragma: no cover - optional dep, Python 3.12+
        raise SystemExit(
            "geotessera is not installed. Install with `pip install -e '.[tessera]'` "
            "(requires Python 3.12+). See https://github.com/ucam-eo/geotessera."
        ) from e

    out_dir.mkdir(parents=True, exist_ok=True)
    gt = GeoTessera()
    tiles = gt.registry.load_blocks_for_region(bounds=bounds, year=year)
    if not tiles:
        raise SystemExit(
            f"No Tessera tiles found for bounds={bounds} year={year}. "
            "Check ROI coverage and that Tessera has data for that year."
        )
    print(f"  {len(tiles)} Tessera tile(s) cover the ROI for {year}.")
    gt.export_embedding_geotiffs(tiles, output_dir=str(out_dir))
    return sorted(out_dir.glob("*.tif"))


def mosaic_to_one(tifs: list[Path], bounds: tuple[float, float, float, float],
                  out_path: Path) -> Path:
    """Mosaic per-tile GeoTIFFs into one file, cropped to the ROI bbox."""
    import rasterio
    from rasterio.merge import merge
    from rasterio.windows import from_bounds

    if len(tifs) == 1:
        # Single tile: still crop to the bbox so the asset isn't a full 12 km tile.
        with rasterio.open(tifs[0]) as src:
            window = from_bounds(*bounds, transform=src.transform)
            data = src.read(window=window)
            profile = src.profile
            profile.update(
                height=data.shape[1],
                width=data.shape[2],
                transform=src.window_transform(window),
            )
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(data)
        return out_path

    srcs = [rasterio.open(t) for t in tifs]
    try:
        mosaic, transform = merge(srcs, bounds=bounds)
        profile = srcs[0].profile
        profile.update(
            height=mosaic.shape[1], width=mosaic.shape[2], transform=transform
        )
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(mosaic)
    finally:
        for s in srcs:
            s.close()
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--config", default="configs/sanjay_van_tessera.yaml",
                    help="config whose roi_file defines the ROI bbox")
    ap.add_argument("--year", type=int, default=2022,
                    help="Tessera embedding year to fetch (single year)")
    ap.add_argument("--out-dir", type=Path, default=Path("outputs/tessera"),
                    help="working dir for the fetched/mosaicked GeoTIFFs")
    ap.add_argument("--asset", required=True,
                    help="target EE asset id, e.g. projects/<proj>/assets/tessera_sanjay_van_2022")
    ap.add_argument("--upload", action="store_true",
                    help="run `earthengine upload image` for you (needs the CLI + auth)")
    args = ap.parse_args()

    print(f"ROI bbox from {args.config} ...")
    bounds = roi_bounds_from_config(args.config)
    print(f"  bounds (minx,miny,maxx,maxy) = {bounds}")

    print(f"Fetching Tessera tiles for {args.year} ...")
    tifs = fetch_tessera_geotiffs(bounds, args.year, args.out_dir)

    mosaic_path = args.out_dir / f"tessera_{args.year}_mosaic.tif"
    print(f"Mosaicking {len(tifs)} tile(s) -> {mosaic_path}")
    mosaic_to_one(tifs, bounds, mosaic_path)

    # Upload to EE. Programmatic upload needs a GCS bucket; the CLI is simplest.
    upload_cmd = [
        "earthengine", "upload", "image",
        f"--asset_id={args.asset}",
        str(mosaic_path),
    ]
    print()
    print("=" * 72)
    print("Upload the mosaic to Earth Engine with:")
    print("  " + " ".join(upload_cmd))
    print("(then wait for the task to finish; check `earthengine task list`)")
    print("=" * 72)

    if args.upload:
        print("Running upload ...")
        result = subprocess.run(upload_cmd, check=False)  # noqa: S603
        if result.returncode != 0:
            sys.exit(result.returncode)

    print()
    print("When the asset is ready, set in configs/sanjay_van_tessera.yaml:")
    print(f"  datasets.embedding: {args.asset}")
    print("then: python scripts/inspect_metrics.py --config configs/sanjay_van_tessera.yaml")


if __name__ == "__main__":
    main()
