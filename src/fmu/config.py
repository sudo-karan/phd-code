"""Per-experiment YAML schema. See docs/design_notes.md."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ROIConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    roi_file: Path | None = None
    roi_asset: str | None = None  # reserved; only roi_file is implemented

    @model_validator(mode="after")
    def exactly_one_source(self) -> ROIConfig:
        if (self.roi_file is None) == (self.roi_asset is None):
            raise ValueError("ROIConfig: set exactly one of roi_file / roi_asset.")
        return self


class DateRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: date
    end: date

    @model_validator(mode="after")
    def end_after_start(self) -> DateRange:
        if self.end < self.start:
            raise ValueError(f"end ({self.end}) before start ({self.start})")
        return self


class DatesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phenology: DateRange
    radar: DateRange
    optical_composite: DateRange
    # Climatology window for rainfall. Default to a 30-year standard
    # normal (1991-2020) when not specified.
    climate: DateRange = Field(
        default_factory=lambda: DateRange(start="1991-01-01", end="2020-12-31")
    )


class DatasetIDs(BaseModel):
    """GEE asset IDs. Swap any to test alternate sources."""

    model_config = ConfigDict(extra="forbid")

    phenology_collection: str = "COPERNICUS/S2_SR_HARMONIZED"
    optical_composite_collection: str = "COPERNICUS/S2_SR_HARMONIZED"
    radar_collection: str = "COPERNICUS/S1_GRD"
    canopy_height: str = "users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1"
    dem: str = "NASA/NASADEM_HGT/001"
    worldcover: str = "ESA/WorldCover/v200"
    water: str = "JRC/GSW1_4/GlobalSurfaceWater"
    nightlights: str = "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG"
    open_buildings: str = "GOOGLE/Research/open-buildings/v3/polygons"
    # CHIRPS pentad rainfall (5-day totals, ~5 km). Long climatology source.
    climate: str = "UCSB-CHG/CHIRPS/PENTAD"


class CloudMaskParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_cloud_pct: float = Field(default=20.0, ge=0.0, le=100.0)
    # SCL classes to drop. Defaults: 3=cloud_shadow, 8=cloud_medium_prob,
    # 9=cloud_high_prob, 10=thin_cirrus.
    drop_scl_classes: list[int] = Field(default=[3, 8, 9, 10], min_length=1)


class DataLoadParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # S1: VV+VH, IW mode by default. Single orbit direction (configurable).
    s1_orbit: Literal["ASCENDING", "DESCENDING"] = "ASCENDING"
    s1_polarizations: list[Literal["VV", "VH"]] = Field(
        default=["VV", "VH"], min_length=1
    )
    s1_instrument_mode: Literal["IW", "EW", "SM"] = "IW"
    # Composite reducer for the static S2 image SNIC will see.
    s2_composite_reducer: Literal["median", "p25", "p50", "p75"] = "median"


class FeaturesOpticalParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Vegetation index for phenology features.
    # ndvi: (NIR-RED)/(NIR+RED). Notebook baseline.
    # nirv: NIR * NDVI. Tracks productivity more linearly in dense canopy.
    index: Literal["ndvi", "nirv"] = "ndvi"
    # Harmonic mode.
    # single: annual cycle only — matches notebook baseline.
    # dual:   annual + semi-annual — catches double-peaked phenology.
    harmonic_mode: Literal["single", "dual"] = "single"
    # Whether to include a linear-trend term in the regression. Captures
    # multi-year greening or browning beyond seasonality.
    include_trend: bool = True


class FeaturesRadarParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Percentiles to compute over the S1 time series. Default [10, 50, 90]
    # covers the typical "low / median / high" backscatter summary.
    # Each percentile becomes a band (vv_p10, vv_p50, vv_p90, vh_p10, ...).
    percentiles: list[int] = Field(default=[10, 50, 90], min_length=1)
    # Add interquartile range (p75 - p25) as a variability metric. Adds
    # vv_iqr and vh_iqr bands. p25 and p75 are computed internally but
    # not exposed as bands unless they're also in `percentiles`.
    include_iqr: bool = True
    # Cross-pol contrast: VV_median - VH_median in dB. Equivalent to
    # 10*log10(VV_linear / VH_linear). Standard SAR vegetation metric;
    # the notebook's VV/VH (literal division of dB values) wasn't
    # mathematically well-defined.
    include_cross_pol_contrast: bool = True


class FeaturesStructureParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Add neighborhood statistics (std-dev and max) over a window around
    # each pixel. Captures local structural heterogeneity beyond the
    # point canopy height. Adds canopy_height_std and canopy_height_max
    # bands. When False, only canopy_height is emitted (notebook approach).
    include_neighborhood_stats: bool = True
    # Window size in pixels for the neighborhood. Must be odd. Default 3
    # means a 3×3 window (radius=1) — small enough to preserve boundaries.
    neighborhood_kernel_size: int = Field(default=3, ge=3, le=11)

    @field_validator("neighborhood_kernel_size")
    @classmethod
    def _odd_kernel(cls, v: int) -> int:
        if v % 2 == 0:
            raise ValueError(f"neighborhood_kernel_size must be odd, got {v}")
        return v


class FeaturesStaticParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Include CHIRPS-derived mean annual rainfall as a band. Useful if
    # the AOI spans different climate regimes. For a small AOI like
    # Sanjay Van it'll be nearly constant — kept for cross-AOI generality.
    include_climate: bool = True
    # Max distance (in pixels at the analysis scale) for the distance-to-water
    # transform. Pixels farther than this are capped at this value.
    # 1000 pixels at 10m = 10 km cap. Tradeoff: larger = more compute, but
    # captures wider-ranging "near water" gradients.
    max_water_distance_pixels: int = Field(default=1000, ge=100, le=10000)


class MaskingParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ndvi_min: float = Field(default=0.2, ge=-1.0, le=1.0)  # reserved, applied later (needs S2)
    # VIIRS radiance threshold (nW/cm²/sr). Delhi-calibrated; won't generalize.
    nightlights_threshold: float = Field(default=30.0, ge=0.0)
    keep_worldcover_classes: list[int] = Field(
        default=[10, 20, 30], min_length=1
    )  # trees/shrub/grass
    # JRC GSW occurrence is 0-100 (% of months observed as water).
    # >= 50 means water at least half the time = "permanent" water.
    jrc_water_occurrence_threshold: float = Field(default=50.0, ge=0.0, le=100.0)
    # Open Buildings polygons have a per-feature confidence in [0,1].
    # Drop polygons below this threshold to avoid noisy / low-confidence buildings.
    open_buildings_confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class SegmentationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    size: int = Field(default=10, ge=1)  # seed spacing in pixels, ~100m on 10m grid
    compactness: float = Field(default=0.5, ge=0.0)  # low = spectral, high = spatial
    connectivity: Literal[4, 8] = 8
    neighborhood_size: int = Field(default=128, ge=8)
    # Whether to z-score the 5 SNIC input bands per-band over the ROI before
    # running SNIC. Necessary when input bands have wildly different scales
    # (S2 reflectance 0-3000, NIRv 0-1, canopy_height 0-30, dB values).
    # Without this, the largest-magnitude band dominates SNIC's distance metric.
    normalize_inputs: bool = True


class ClusteringParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    k: int = Field(default=6, ge=2, le=50)
    n_training_samples: int = Field(default=5000, ge=100)
    seed: int = 42
    # Skewness threshold above which a feature gets log-transformed before scaling.
    # Per DEC-004: a feature with |skew| > 1.0 is log-transformed via log(x - min + 1e-3).
    skewness_threshold: float = Field(default=1.0, ge=0.0)
    # Pixels per superpixel cap for reduceConnectedComponents. Must exceed our
    # largest SNIC superpixel; 1024 is generous at size=10.
    superpixel_max_size: int = Field(default=1024, ge=64, le=8192)


class NormalizationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Default is "robust" (median/IQR scaling) per DEC-003 — outlier-resistant,
    # and what every shipped config uses. "zscore" remains available for ad-hoc
    # comparisons against earlier notebook behavior, but isn't the recommended
    # path forward.
    method: Literal["zscore", "robust"] = "robust"


class FeatureToggles(BaseModel):
    model_config = ConfigDict(extra="forbid")

    optical_harmonic: bool = True
    radar: bool = True
    canopy_height: bool = True
    terrain: bool = True


class ExportParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export_geotiff: bool = True
    export_gee_asset: bool = False
    analysis_scale_m: int = Field(default=10, ge=1)


class MetricsParams(BaseModel):
    """Parameters for the metrics stage (Module 18).

    `reference_config_name`: if set, the metrics stage will load the named
    config's `cluster_labels` asset and compute ARI/NMI/correspondence
    against the current config's cluster_labels. If null, only intrinsic
    metrics (silhouette score) are computed for the current config.
    """

    model_config = ConfigDict(extra="forbid")

    reference_config_name: str | None = None
    n_comparison_samples: int = Field(default=10000, ge=100)
    n_silhouette_samples_per_cluster: int = Field(default=833, ge=50)


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str = ""

    roi: ROIConfig
    dates: DatesConfig
    datasets: DatasetIDs = Field(default_factory=DatasetIDs)

    cloud_mask: CloudMaskParams = Field(default_factory=CloudMaskParams)
    data_load: DataLoadParams = Field(default_factory=DataLoadParams)
    masking: MaskingParams = Field(default_factory=MaskingParams)
    features_optical: FeaturesOpticalParams = Field(default_factory=FeaturesOpticalParams)
    features_radar: FeaturesRadarParams = Field(default_factory=FeaturesRadarParams)
    features_structure: FeaturesStructureParams = Field(default_factory=FeaturesStructureParams)
    features_static: FeaturesStaticParams = Field(default_factory=FeaturesStaticParams)
    segmentation: SegmentationParams = Field(default_factory=SegmentationParams)
    clustering: ClusteringParams = Field(default_factory=ClusteringParams)
    normalization: NormalizationParams = Field(default_factory=NormalizationParams)
    features: FeatureToggles = Field(default_factory=FeatureToggles)
    export: ExportParams = Field(default_factory=ExportParams)
    metrics: MetricsParams = Field(default_factory=MetricsParams)

    @field_validator("name")
    @classmethod
    def name_safe_for_paths(cls, v: str) -> str:
        bad = set(' \t\n\r/\\:*?"<>|')
        if any(c in bad for c in v):
            raise ValueError(f"name not path-safe: {v!r}")
        return v


def load_config(path: str | Path) -> Config:
    """Load YAML, validate, return Config."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open() as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top-level YAML must be a mapping, got {type(raw).__name__}")

    return Config.model_validate(raw)
