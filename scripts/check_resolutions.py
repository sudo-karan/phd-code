"""
Check the native resolution of every dataset and cached feature output
the pipeline uses. Prints a clean table for design decisions about which
features to feed SNIC.

No exports, no clustering — just metadata queries against GEE.

Run with either config; results are identical since both configs use the
same datasets and analysis scale.
"""

from __future__ import annotations

import argparse

import ee

from fmu.config import load_config
from fmu.settings import get_settings
from fmu.utils.caching import asset_exists, cached_asset_path
from fmu.utils.gee import init_gee, safe_get_info


def _scale_of_image(img: ee.Image, sample_band: str | None = None) -> float | None:
    """Return nominalScale() in meters for an image, optionally selecting a band."""
    try:
        target = img.select(sample_band) if sample_band is not None else img
        scale = safe_get_info(
            target.projection().nominalScale(),
            context=f"projection scale (band={sample_band})",
        )
        return float(scale) if scale is not None else None
    except Exception as e:  # noqa: BLE001 — best-effort metadata probe
        print(f"    [error] {e}")
        return None


def _scale_of_collection_first(asset_id: str, sample_band: str | None = None) -> float | None:
    """For an ImageCollection asset, get the scale of the first image."""
    try:
        coll = ee.ImageCollection(asset_id)
        first = ee.Image(coll.first())
        return _scale_of_image(first, sample_band)
    except Exception as e:  # noqa: BLE001
        print(f"    [error] {e}")
        return None


def _band_names_safe(img: ee.Image) -> list[str]:
    try:
        names = safe_get_info(img.bandNames(), context="band names")
        return names or []
    except Exception:  # noqa: BLE001
        return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/sanjay_van_baseline.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    init_gee()
    get_settings()

    print()
    print("=" * 78)
    print("NATIVE RESOLUTIONS — SOURCE DATASETS")
    print("=" * 78)
    print(f"{'Source dataset':50s} {'Type':12s} {'Scale (m)':>12s}")
    print("-" * 78)

    # Source datasets — these are what we read from
    sources: list[tuple[str, str, str, str]] = [
        # (label, asset_id, kind, sample_band_or_None)
        ("Sentinel-2 SR (phenology)", config.datasets.phenology_collection, "collection", "B8"),
        ("Sentinel-2 SR (composite)", config.datasets.optical_composite_collection, "collection", "B8"),
        ("Sentinel-1 GRD (radar)", config.datasets.radar_collection, "collection", "VV"),
        ("ETH Global Canopy Height", config.datasets.canopy_height, "image", None),
        ("NASADEM (elevation)", config.datasets.dem, "image", "elevation"),
        ("ESA WorldCover", config.datasets.worldcover, "collection", "Map"),
        ("JRC Global Surface Water", config.datasets.water, "image", "occurrence"),
        ("VIIRS Nightlights", config.datasets.nightlights, "collection", "avg_rad"),
        ("CHIRPS PENTAD (climate)", config.datasets.climate, "collection", None),
    ]

    for label, asset_id, kind, sample_band in sources:
        if kind == "image":
            scale = _scale_of_image(ee.Image(asset_id), sample_band)
        else:
            scale = _scale_of_collection_first(asset_id, sample_band)
        scale_str = f"{scale:>10.2f}" if scale is not None else "         ?"
        print(f"  {label:48s} {kind:12s} {scale_str}")

    # Note about Open Buildings (it's a FeatureCollection, no scale)
    print(f"  {'Google Open Buildings':48s} {'features':12s} {'(vector)':>12s}")

    # Cached feature outputs
    print()
    print("=" * 78)
    print(f"CACHED FEATURE OUTPUTS — {config.name}")
    print("=" * 78)

    feature_assets: list[tuple[str, str, str]] = [
        # (label, stage_name, output_key)
        ("S2 composite", "data_load", "s2_composite"),
        ("Masking — habitat", "masking", "habitat_mask"),
        ("Masking — water", "masking", "water_mask"),
        ("Optical features", "features_optical", "optical_features"),
        ("Radar features", "features_radar", "radar_features"),
        ("Structure features", "features_structure", "structure_features"),
        ("Static features", "features_static", "static_features"),
    ]

    for label, stage_name, key in feature_assets:
        path = cached_asset_path(config.name, stage_name, key)
        if not asset_exists(path):
            print(f"  {label:30s} [not cached]")
            continue

        img = ee.Image(path)
        bands = _band_names_safe(img)
        if not bands:
            print(f"  {label:30s} [no bands?]")
            continue

        # Sample first band for the per-image projection
        first_band_scale = _scale_of_image(img, bands[0])
        scale_str = f"{first_band_scale:>10.2f}" if first_band_scale is not None else "         ?"
        print(f"  {label:30s} {len(bands):>3d} bands  scale (1st band): {scale_str} m")

        # Per-band detail (only if scales might differ; show all for completeness)
        for b in bands:
            band_scale = _scale_of_image(img, b)
            band_scale_str = f"{band_scale:>10.2f}" if band_scale is not None else "         ?"
            print(f"      {b:38s} {band_scale_str} m")
        print()

    print("=" * 78)
    print("INTERPRETATION GUIDE")
    print("=" * 78)
    print("Scales close to 10m → safe for SNIC at 10m analysis scale")
    print("Scales close to 30m → 3× coarser; can include but degrades boundary precision")
    print("Scales > 1000m       → much coarser than ROI extent; will not contribute to SNIC")
    print()
    print("If a cached output reports a different scale than its source dataset, that's")
    print("because the export resampled to the analysis scale. The 'real' information")
    print("content is bounded by the SOURCE resolution, not the cache resolution.")
    print()


if __name__ == "__main__":
    main()
