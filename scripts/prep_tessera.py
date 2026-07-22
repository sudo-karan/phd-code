"""One-shot: ingest a Tessera embedding for an ROI into an Earth Engine asset.

Tessera (https://github.com/ucam-eo/geotessera) is a 128-channel, 10 m
pretrained embedding, distributed CC0 through the `geotessera` library — but it
lives OFF Earth Engine. To cluster it with the same pipeline that clusters
AlphaEarth (which is GEE-native), it has to be pulled down and uploaded to EE
once. This script does that:

  1. read the ROI bounding box from the config's roi_file (no EE needed),
  2. fetch the Tessera tiles covering that box for each requested year,
  3. export to GeoTIFF, mosaic/crop each year to the box, and (if several years
     are requested) average them into one image, matching AlphaEarth's mean
     over the 2017-2022 window,
  4. help you upload it to an EE asset (Code Editor UI, or gsutil + CLI).

Then paste the resulting asset id into configs/sanjay_van_tessera.yaml
(datasets.embedding) and run the pipeline exactly like the AlphaEarth arm.

This is a documented, interactive one-shot — NOT part of the tested pipeline.
`geotessera` is an optional dependency (requires Python 3.12+, so it will NOT
install in this project's 3.11 venv): run this in a separate 3.12+ environment
that has both this package and geotessera, e.g.
`uv venv --python 3.12 && pip install -e . geotessera`. The geotessera API is
young; if a call below does not match your installed version, check its
README / readthedocs. The upload step needs no geotessera at all.

Comparability note: the AlphaEarth arm averages six annual embeddings
(2017-2022). For a temporally matched Tessera arm, pass the same years:
`--years 2017 2018 2019 2020 2021 2022` (whichever Tessera actually publishes).
A single --years value is fine too, but is then one year vs a six-year mean —
say so in any writeup.

Uploading to Earth Engine (two paths — the CLI can NOT read a local file):
  A) Code Editor UI (simplest, no cloud bucket): Assets tab -> New ->
     "Image upload (GeoTIFF)" -> select the printed mosaic -> set the asset id.
  B) Command line (scriptable, needs a GCS bucket): pass --gcs gs://bucket and
     --upload; the script does `gsutil cp` then `earthengine upload image` from
     Cloud Storage.

Usage:
    # single year, upload via the Code Editor UI yourself:
    python scripts/prep_tessera.py --config configs/sanjay_van_tessera.yaml \
        --years 2022 --asset projects/<proj>/assets/tessera_sanjay_van_2022

    # six-year mean, upload via gsutil + CLI:
    python scripts/prep_tessera.py --config configs/sanjay_van_tessera.yaml \
        --years 2017 2018 2019 2020 2021 2022 \
        --asset projects/<proj>/assets/tessera_sanjay_van_2017_2022 \
        --gcs gs://<your-bucket>/tessera --upload
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
            "geotessera is not installed. Run this in a Python 3.12+ environment "
            "with `pip install -e . geotessera`. See "
            "https://github.com/ucam-eo/geotessera."
        ) from e

    out_dir.mkdir(parents=True, exist_ok=True)
    gt = GeoTessera()
    tiles = gt.registry.load_blocks_for_region(bounds=bounds, year=year)
    if not tiles:
        raise SystemExit(
            f"No Tessera tiles found for bounds={bounds} year={year}. "
            "Check ROI coverage and that Tessera publishes data for that year."
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


def average_mosaics(mosaics: list[Path], out_path: Path) -> Path:
    """Band-wise average of several per-year mosaics into one image.

    Matches the AlphaEarth arm's mean over the 2017-2022 window. The mosaics
    must share the same grid (same ROI/resolution/shape); Tessera is a fixed
    10 m grid, so per-year crops to the same bbox align. Masked (nodata) pixels
    are excluded from the mean.
    """
    import numpy as np
    import rasterio

    arrays: list[np.ma.MaskedArray] = []
    ref_profile = None
    ref_shape: tuple[int, int, int] | None = None
    for m in mosaics:
        with rasterio.open(m) as src:
            arr = src.read(masked=True).astype("float32")  # (bands, h, w)
            if ref_shape is None:
                ref_shape = arr.shape
                ref_profile = src.profile
            elif arr.shape != ref_shape:
                raise SystemExit(
                    f"Year mosaics have mismatched shapes ({arr.shape} vs "
                    f"{ref_shape}); cannot average. Re-run with a single --years "
                    "value, or ensure the same ROI/grid across years."
                )
            arrays.append(arr)

    assert ref_profile is not None and ref_shape is not None
    stacked = np.ma.stack(arrays, axis=0)          # (years, bands, h, w)
    mean = stacked.mean(axis=0)                     # masked mean over years
    ref_profile.update(dtype="float32", count=ref_shape[0])
    with rasterio.open(out_path, "w", **ref_profile) as dst:
        dst.write(mean.filled(np.nan).astype("float32"))
    return out_path


def _run(cmd: list[str]) -> None:
    print("  $ " + " ".join(cmd))
    result = subprocess.run(cmd, check=False)  # noqa: S603
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--config", default="configs/sanjay_van_tessera.yaml",
                    help="config whose roi_file defines the ROI bbox")
    ap.add_argument("--years", type=int, nargs="+", default=[2022],
                    help="Tessera year(s) to fetch; several are averaged (match "
                         "AlphaEarth's 2017-2022 mean for a controlled comparison)")
    ap.add_argument("--out-dir", type=Path, default=Path("outputs/tessera"),
                    help="working dir for the fetched/mosaicked GeoTIFFs")
    ap.add_argument("--asset", required=True,
                    help="target EE asset id, e.g. projects/<proj>/assets/tessera_sanjay_van_2017_2022")
    ap.add_argument("--gcs", default=None,
                    help="GCS prefix (gs://bucket/path) to stage the mosaic for the CLI upload; "
                         "required with --upload (the earthengine CLI reads from Cloud Storage)")
    ap.add_argument("--upload", action="store_true",
                    help="run gsutil cp + `earthengine upload image` for you (needs --gcs, the "
                         "CLIs, and auth). Omit to upload via the Code Editor UI yourself.")
    args = ap.parse_args()

    print(f"ROI bbox from {args.config} ...")
    bounds = roi_bounds_from_config(args.config)
    print(f"  bounds (minx,miny,maxx,maxy) = {bounds}")

    years = sorted(set(args.years))
    year_mosaics: list[Path] = []
    for y in years:
        print(f"Fetching Tessera tiles for {y} ...")
        tifs = fetch_tessera_geotiffs(bounds, y, args.out_dir / f"year_{y}")
        ymos = args.out_dir / f"tessera_{y}_mosaic.tif"
        print(f"  mosaicking {len(tifs)} tile(s) -> {ymos}")
        mosaic_to_one(tifs, bounds, ymos)
        year_mosaics.append(ymos)

    if len(year_mosaics) == 1:
        final = year_mosaics[0]
    else:
        tag = f"{years[0]}_{years[-1]}"
        final = args.out_dir / f"tessera_{tag}_mean.tif"
        print(f"Averaging {len(year_mosaics)} years -> {final}")
        average_mosaics(year_mosaics, final)

    # ----- Upload guidance (the CLI can NOT read a local file) -----
    print()
    print("=" * 72)
    print(f"Mosaic ready: {final}")
    print()
    print("Upload it to Earth Engine by EITHER:")
    print("  A) Code Editor UI (no bucket): https://code.earthengine.google.com")
    print("     Assets -> New -> 'Image upload (GeoTIFF)' -> select the file above")
    print(f"     -> asset id: {args.asset}")
    print("  B) Command line (needs a GCS bucket):")
    print(f"     gsutil cp {final} gs://<your-bucket>/")
    print(f"     earthengine upload image --asset_id={args.asset} "
          f"gs://<your-bucket>/{final.name}")
    print("     earthengine task list   # wait for COMPLETED")
    print("=" * 72)

    if args.upload:
        if not args.gcs:
            raise SystemExit(
                "--upload needs --gcs gs://bucket/prefix: the earthengine CLI uploads from "
                "Cloud Storage, not a local file. Either pass --gcs, or use the Code Editor "
                "UI (path A above)."
            )
        gcs_uri = args.gcs.rstrip("/") + "/" + final.name
        print(f"Staging to {gcs_uri} and uploading ...")
        _run(["gsutil", "cp", str(final), gcs_uri])
        _run(["earthengine", "upload", "image", f"--asset_id={args.asset}", gcs_uri])
        print("Upload task submitted; watch `earthengine task list` for COMPLETED.")

    print()
    print("When the asset is ready, set in configs/sanjay_van_tessera.yaml:")
    print(f"  datasets.embedding: {args.asset}")
    print("then: python scripts/inspect_metrics.py --config configs/sanjay_van_tessera.yaml")


if __name__ == "__main__":
    main()
