"""
Pipeline configuration — the schema for per-experiment YAML files.

A `Config` object describes one full pipeline run: which ROI, which dates,
which datasets, which parameters. It is the single source of truth that
every stage reads from.

Configs are loaded with `load_config(path_to_yaml)`. The loader:
  1. Reads the YAML
  2. Validates against this schema
  3. Returns a typed `Config` object
  4. Raises a clear error if anything is wrong, pointing at the offending field

Separation of concerns:
  - This file (`config.py`) holds per-experiment values that GO IN GIT
    and change with every experiment (ROI, dates, dataset IDs, parameters).
  - `settings.py` holds per-machine values that DO NOT go in git
    (GEE project ID, output paths).

The schema is intentionally strict: misspelled keys, wrong types, or
out-of-range values all raise errors at load time, not at runtime in some
deep stage. This is one of the main mechanisms for stopping "going in
circles" — if a parameter has a bad value, you find out immediately.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------- ROI ----------


class ROIConfig(BaseModel):
    """
    Region of interest specification.

    Exactly one of `roi_file` or `roi_asset` must be set. We support both
    so the framework can handle small ROIs (GeoJSON, ~kB) and large ROIs
    (uploaded GEE asset, no inline-geometry size limit).

    For v0.2 only `roi_file` is implemented; `roi_asset` is reserved.
    See DEC-005.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        description="Short identifier for the ROI, used in output paths and reports.",
        min_length=1,
        max_length=64,
    )
    roi_file: Path | None = Field(
        default=None,
        description="Path to a local GeoJSON or Shapefile, relative to the repo root.",
    )
    roi_asset: str | None = Field(
        default=None,
        description=(
            "GEE FeatureCollection asset path, e.g. "
            "'projects/replicating-paper/assets/sanjay_van'. "
            "Reserved for v0.3+; not yet implemented."
        ),
    )

    @model_validator(mode="after")
    def exactly_one_source(self) -> ROIConfig:
        if (self.roi_file is None) == (self.roi_asset is None):
            raise ValueError(
                "ROIConfig: exactly one of `roi_file` or `roi_asset` must be set."
            )
        return self


# ---------- Dates ----------


class DateRange(BaseModel):
    """A start/end date range (inclusive), with validation."""

    model_config = ConfigDict(extra="forbid")

    start: date
    end: date

    @model_validator(mode="after")
    def end_after_start(self) -> DateRange:
        if self.end < self.start:
            raise ValueError(
                f"DateRange: end ({self.end}) must be >= start ({self.start})."
            )
        return self


class DatesConfig(BaseModel):
    """
    Per-stream date windows.

    Different sensors need different windows: phenology wants a long record
    (10+ years), radar wants a density-consistent window, the optical
    composite for SNIC wants a recent cloud-free year. All three are explicit.
    """

    model_config = ConfigDict(extra="forbid")

    phenology: DateRange = Field(
        ...,
        description="Date window for harmonic regression on the optical time series.",
    )
    radar: DateRange = Field(
        ...,
        description="Date window for Sentinel-1 statistics.",
    )
    optical_composite: DateRange = Field(
        ...,
        description="Date window for the cloud-free static composite used by SNIC.",
    )


# ---------- Datasets ----------


class DatasetIDs(BaseModel):
    """
    GEE asset IDs for every dataset the pipeline reads.

    Pinning IDs explicitly (instead of hard-coding them in stage code) means
    swapping a dataset is a one-line config change. E.g. to test HLS phenology
    instead of S2: change `phenology_collection` and re-run.
    """

    model_config = ConfigDict(extra="forbid")

    # Optical
    phenology_collection: str = Field(
        default="COPERNICUS/S2_SR_HARMONIZED",
        description="Optical time series for harmonic phenology fitting.",
    )
    optical_composite_collection: str = Field(
        default="COPERNICUS/S2_SR_HARMONIZED",
        description="Optical collection for the cloud-free static composite.",
    )
    # Radar
    radar_collection: str = Field(
        default="COPERNICUS/S1_GRD",
        description="Sentinel-1 GRD collection.",
    )
    # Structure
    canopy_height: str = Field(
        default="users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1",
        description="Lang 2023 ETH Global Canopy Height image.",
    )
    # Topography
    dem: str = Field(
        default="NASA/NASADEM_HGT/001",
        description="Digital elevation model.",
    )
    # Masks
    worldcover: str = Field(
        default="ESA/WorldCover/v200",
        description="ESA WorldCover for vegetation pre-mask.",
    )
    water: str = Field(
        default="JRC/GSW1_4/GlobalSurfaceWater",
        description="JRC global surface water for water mask.",
    )
    nightlights: str = Field(
        default="NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG",
        description="VIIRS night lights for urban pre-mask.",
    )


# ---------- Pipeline parameters ----------


class CloudMaskParams(BaseModel):
    """Sentinel-2 cloud filtering parameters."""

    model_config = ConfigDict(extra="forbid")

    max_cloud_pct: float = Field(
        default=20.0,
        ge=0.0,
        le=100.0,
        description="Max CLOUDY_PIXEL_PERCENTAGE per S2 scene.",
    )


class MaskingParams(BaseModel):
    """Pre-masking parameters (water, urban, vegetation)."""

    model_config = ConfigDict(extra="forbid")

    ndvi_min: float = Field(
        default=0.2,
        ge=-1.0,
        le=1.0,
        description="Pixels with NDVI below this are dropped as non-vegetation.",
    )
    nightlights_threshold: float = Field(
        default=30.0,
        ge=0.0,
        description=(
            "VIIRS radiance above this is masked as urban. "
            "This is the Sanjay-Van-calibrated value; revisit when generalizing. "
            "Units: nW/cm²/sr."
        ),
    )
    keep_worldcover_classes: list[int] = Field(
        default=[10, 20, 30],
        description="ESA WorldCover class codes to keep: 10=trees, 20=shrubs, 30=grass.",
    )


class SegmentationParams(BaseModel):
    """SNIC superpixel segmentation parameters."""

    model_config = ConfigDict(extra="forbid")

    size: int = Field(
        default=10,
        ge=1,
        description=(
            "SNIC seed spacing in pixels. Larger = fewer, larger stands. "
            "For Sanjay Van (~4 km², 10m grid), size=10 gives ~100m spacing."
        ),
    )
    compactness: float = Field(
        default=0.5,
        ge=0.0,
        description=(
            "Spatial-vs-spectral tradeoff. Higher = more regular shapes. "
            "Low values (0.1–0.5) follow spectral edges; high values produce tessellation."
        ),
    )
    connectivity: Literal[4, 8] = Field(
        default=8,
        description="SNIC pixel connectivity (4 or 8).",
    )
    neighborhood_size: int = Field(
        default=128,
        ge=8,
        description="SNIC neighborhood size in pixels.",
    )


class ClusteringParams(BaseModel):
    """K-means clustering parameters."""

    model_config = ConfigDict(extra="forbid")

    k: int = Field(
        default=6,
        ge=2,
        le=50,
        description="Number of clusters. Fixed in baseline; auto-K added in later module.",
    )
    n_training_samples: int = Field(
        default=5000,
        ge=100,
        description="Number of pixels (or stands) sampled to train the clusterer.",
    )
    seed: int = Field(
        default=42,
        description="Random seed for reproducibility.",
    )


class NormalizationParams(BaseModel):
    """Feature normalization strategy."""

    model_config = ConfigDict(extra="forbid")

    method: Literal["zscore", "robust"] = Field(
        default="zscore",
        description=(
            "zscore: (x - mean) / std. Sensitive to outliers but matches earlier notebooks.\n"
            "robust: (x - median) / IQR. More outlier-resistant."
        ),
    )


class FeatureToggles(BaseModel):
    """Which feature groups are included in the pipeline. Used by config swaps."""

    model_config = ConfigDict(extra="forbid")

    optical_harmonic: bool = True
    radar: bool = True
    canopy_height: bool = True
    terrain: bool = True
    custom_csv: bool = False


class CustomCSVFeature(BaseModel):
    """User-supplied per-pixel feature from a CSV. Reserved for a future module."""

    model_config = ConfigDict(extra="forbid")

    name: str
    path: Path
    lon_col: str = "lon"
    lat_col: str = "lat"
    value_col: str = "value"


class ExportParams(BaseModel):
    """How and where to export outputs."""

    model_config = ConfigDict(extra="forbid")

    export_geotiff: bool = Field(
        default=True,
        description="Export cluster map as GeoTIFF to OUTPUT_DIR (from .env).",
    )
    export_gee_asset: bool = Field(
        default=False,
        description=(
            "Export cluster map as a GEE asset under the configured asset root. "
            "Defaulting to False because asset exports queue and don't block the run."
        ),
    )
    analysis_scale_m: int = Field(
        default=10,
        ge=1,
        description="Pixel size in meters for raster exports.",
    )


# ---------- Top-level config ----------


class Config(BaseModel):
    """
    Top-level pipeline configuration.

    One of these objects is constructed per pipeline run, by loading the
    corresponding YAML file. Every stage reads from this object.
    """

    model_config = ConfigDict(extra="forbid")

    # Identity
    name: str = Field(
        ...,
        description=(
            "Experiment name. Goes into output paths and reports. "
            "Convention: '{roi}_{variant}', e.g. 'sanjay_van_baseline'."
        ),
        min_length=1,
        max_length=128,
    )
    description: str = Field(
        default="",
        description="Free-text description of what this experiment is testing.",
    )

    # What we're running on
    roi: ROIConfig
    dates: DatesConfig
    datasets: DatasetIDs = Field(default_factory=DatasetIDs)

    # How we're running it
    cloud_mask: CloudMaskParams = Field(default_factory=CloudMaskParams)
    masking: MaskingParams = Field(default_factory=MaskingParams)
    segmentation: SegmentationParams = Field(default_factory=SegmentationParams)
    clustering: ClusteringParams = Field(default_factory=ClusteringParams)
    normalization: NormalizationParams = Field(default_factory=NormalizationParams)
    features: FeatureToggles = Field(default_factory=FeatureToggles)
    custom_csv_features: list[CustomCSVFeature] = Field(default_factory=list)
    export: ExportParams = Field(default_factory=ExportParams)

    @field_validator("name")
    @classmethod
    def name_safe_for_paths(cls, v: str) -> str:
        # Output paths use the config name. Forbid characters that would break paths.
        bad = set(' \t\n\r/\\:*?"<>|')
        if any(c in bad for c in v):
            raise ValueError(
                f"Config.name must be path-safe (no whitespace, slashes, or special "
                f"characters). Got: {v!r}"
            )
        return v


# ---------- Loader ----------


def load_config(path: str | Path) -> Config:
    """
    Load a YAML config file from disk and validate against the schema.

    Args:
        path: Path to the YAML file.

    Returns:
        A validated Config object.

    Raises:
        FileNotFoundError: If the YAML file doesn't exist.
        ValueError: If the YAML is malformed.
        pydantic.ValidationError: If any field fails validation.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open() as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(
            f"Config file must contain a YAML mapping at the top level. "
            f"Got {type(raw).__name__} from {path}."
        )

    return Config.model_validate(raw)
