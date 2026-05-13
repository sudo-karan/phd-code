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


class CloudMaskParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_cloud_pct: float = Field(default=20.0, ge=0.0, le=100.0)


class MaskingParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ndvi_min: float = Field(default=0.2, ge=-1.0, le=1.0)
    # Sanjay-Van-calibrated; won't generalize, revisit for other ROIs
    nightlights_threshold: float = Field(default=30.0, ge=0.0)
    keep_worldcover_classes: list[int] = Field(
        default=[10, 20, 30], min_length=1
    )  # trees/shrub/grass
    # JRC GSW occurrence is 0-100 (% of months observed as water).
    # >= 50 means water at least half the time = "permanent" water.
    jrc_water_occurrence_threshold: float = Field(default=50.0, ge=0.0, le=100.0)


class SegmentationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    size: int = Field(default=10, ge=1)  # seed spacing in pixels, ~100m on 10m grid
    compactness: float = Field(default=0.5, ge=0.0)  # low = spectral, high = spatial
    connectivity: Literal[4, 8] = 8
    neighborhood_size: int = Field(default=128, ge=8)


class ClusteringParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    k: int = Field(default=6, ge=2, le=50)
    n_training_samples: int = Field(default=5000, ge=100)
    seed: int = 42


class NormalizationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # zscore: matches earlier notebooks. robust: median/IQR, outlier-resistant.
    method: Literal["zscore", "robust"] = "zscore"


class FeatureToggles(BaseModel):
    model_config = ConfigDict(extra="forbid")

    optical_harmonic: bool = True
    radar: bool = True
    canopy_height: bool = True
    terrain: bool = True
    custom_csv: bool = False


class CustomCSVFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    path: Path
    lon_col: str = "lon"
    lat_col: str = "lat"
    value_col: str = "value"


class ExportParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export_geotiff: bool = True
    export_gee_asset: bool = False
    analysis_scale_m: int = Field(default=10, ge=1)


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str = ""

    roi: ROIConfig
    dates: DatesConfig
    datasets: DatasetIDs = Field(default_factory=DatasetIDs)

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
