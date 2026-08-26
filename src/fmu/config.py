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
    # CoRE Stack LULC_v4: annual 30 m land-cover, a folder of per-year images
    # (lulc_v4_YYYY_YYYY, band 'predicted_label'). Primary habitat source
    # (class 6 = Trees, 12 = Shrubs/Scrubs). Same product/legend as the private
    # projects/ee-indiasat asset, but publicly readable to CoRE Stack accounts.
    indiasat: str = "projects/corestack-trees/assets/LULC_v4"
    # ESA WorldCover v200: habitat fallback where IndiaSAT has no data.
    worldcover: str = "ESA/WorldCover/v200"
    water: str = "JRC/GSW1_4/GlobalSurfaceWater"
    # CHIRPS pentad rainfall (5-day totals, ~5 km). Long climatology source.
    climate: str = "UCSB-CHG/CHIRPS/PENTAD"
    # AlphaEarth Satellite Embedding: a 64-band annual per-pixel embedding
    # (bands A00..A63), one image per year from 2017. Read ONLY when
    # clustering.feature_source == "embedding". Point this at an uploaded
    # Tessera asset (a single Image) to run the Tessera arm instead — the
    # features_embedding stage handles both an ImageCollection (annual
    # AlphaEarth, collapsed over the feature window) and a single Image
    # (Tessera) source.
    embedding: str = "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"


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
    # single: annual cycle only; matches notebook baseline.
    # dual:   annual + semi-annual; catches double-peaked phenology.
    harmonic_mode: Literal["single", "dual"] = "single"
    # Whether to include a linear-trend term in the regression. Captures
    # multi-year greening or browning beyond seasonality.
    include_trend: bool = True
    # Reference date for the harmonic regression's time variable t.
    # t = years since `time_reference`. Affects the numerical value of
    # `phase_annual` (which is measured relative to this epoch) but NOT
    # amplitude, trend, or clustering outcomes. Default 2017-01-01
    # matches Sentinel-2's S2A+S2B full-constellation start, so cross-
    # config phase values are comparable by default.
    #
    # Important: do NOT auto-derive this from `dates.phenology.start`.
    # If two configs have different phenology windows, keeping a shared
    # anchor preserves cross-config phase comparability (which the
    # metrics stage relies on). Override only when you have a specific
    # reason and accept that phase values become non-comparable to
    # configs using the default anchor.
    time_reference: date = Field(default_factory=lambda: date(2017, 1, 1))


class FeaturesRadarParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Percentiles to compute over the S1 time series. Default [10, 50, 90]
    # covers the typical "low / median / high" backscatter summary.
    # Each percentile becomes a band (vv_p10, vv_p50, vv_p90, vh_p10, ...).
    percentiles: list[int] = Field(default=[10, 50, 90], min_length=1)
    # Add temporal spread (p90 - p10) as a variability metric (deck v3.0,
    # Stage 4). Adds vv_iqr and vh_iqr bands. p10 and p90 are computed
    # internally and also exposed as bands when listed in `percentiles`.
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
    # means a 3×3 window (radius=1); small enough to preserve boundaries.
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
    # Sanjay Van it'll be nearly constant; kept for cross-AOI generality.
    include_climate: bool = True
    # Max distance (in pixels at the analysis scale) for the distance-to-water
    # transform. Pixels farther than this are capped at this value.
    # 1000 pixels at 10m = 10 km cap. Tradeoff: larger = more compute, but
    # captures wider-ranging "near water" gradients.
    max_water_distance_pixels: int = Field(default=1000, ge=100, le=10000)


class FeaturesEmbeddingParams(BaseModel):
    """Pretrained-embedding feature source (the embedding-vs-hand-crafted arm).

    When `clustering.feature_source == "embedding"`, the four hand-crafted
    feature images (optical / radar / structure / static) are replaced by a
    single pretrained per-pixel embedding image — AlphaEarth's 64-band
    Satellite Embedding (an annual ImageCollection) or an uploaded Tessera
    asset (a single Image). Only read in embedding mode; ignored otherwise.
    """

    model_config = ConfigDict(extra="forbid")

    # How to collapse an annual embedding ImageCollection (AlphaEarth ships one
    # image per year) to a single image over the feature window. "mean" matches
    # the 2017-2022 averaging the hand-crafted arm rests on; "median" is a
    # robust alternative. Ignored when the source is a single uploaded image
    # (Tessera), which is loaded as-is.
    collapse_reducer: Literal["mean", "median"] = "mean"
    # Optional explicit band selection. None keeps every band the source
    # provides (AlphaEarth: 64 bands A00..A63; Tessera: 128). Set a list only to
    # restrict to a subset — the embedding dimensions are jointly meaningful, so
    # this is rarely needed.
    band_names: list[str] | None = None


class MaskingParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # IndiaSAT LULC classes kept as habitat: 6 = Trees, 12 = Shrubs/Scrubs.
    # Everything else (water 2-4, crops 5/8-11, built-up 1, barren 7, ...) is
    # excluded simply by not being in this set — the deck's single-phase mask.
    indiasat_habitat_classes: list[int] = Field(default=[6, 12], min_length=1)
    # Band holding the IndiaSAT class label. None -> use the first band of each
    # annual image (the class band; the collection also carries a confidence
    # band). Set explicitly if the asset names its class band differently
    # (the CoRE Stack LULC_v4 product names it 'predicted_label').
    indiasat_class_band: str | None = None
    # Hydrological-year window for the annual LULC images, matched on the start
    # year in each per-year asset id (e.g. lulc_v4_2017_2018 -> 2017). Both
    # bounds inclusive; None = use every year available under the asset. The
    # deck's "2017-2022 hydrological years" = start years 2017..2021.
    indiasat_year_min: int | None = None
    indiasat_year_max: int | None = None
    # WorldCover fallback classes, used only where IndiaSAT has no data:
    # 10 = tree cover, 20 = shrubland, 30 = grassland.
    keep_worldcover_classes: list[int] = Field(
        default=[10, 20, 30], min_length=1
    )
    # JRC GSW occurrence is 0-100 (% of months observed as water). >= this =
    # "permanent" water. Used ONLY to build water_mask for the downstream
    # distance-to-water feature, NOT for habitat masking.
    jrc_water_occurrence_threshold: float = Field(default=50.0, ge=0.0, le=100.0)


class SnicInputBand(BaseModel):
    """One band fed to SNIC, addressed as (context key, band name).

    `source` names a PipelineContext key holding an ee.Image; `band` names a
    band on it. Two special values:

      band: "*"              every band of that image, in its own order. This
                             exists for the embedding arm -- listing all 64
                             AlphaEarth dimensions by hand would be
                             unreadable and would silently rot if the
                             dimensionality changed. Resolving it costs one
                             extra getInfo (bandNames) at segmentation time.
      band: composite_nirv   does not exist on any upstream image -- it is
                             computed inside the segmentation stage from the
                             S2 composite's B4/B8, so it must be declared as
                             {source: s2_composite, band: composite_nirv}.
    """

    model_config = ConfigDict(extra="forbid")

    source: Literal[
        "s2_composite",
        "optical_features",
        "radar_features",
        "structure_features",
        "static_features",
        "embedding_features",
    ]
    band: str = Field(min_length=1)


# The default SNIC stack. Six bands spanning ~four independent axes:
# optical colour (B4/B8), vertical structure (canopy_height), canopy
# completeness (canopy_height_std), phenology (ndvi_amplitude_annual) and
# radar structure (vv_minus_vh_median).
#
# composite_nirv is deliberately NOT here: it is (B8/10000) x NDVI, i.e. an
# algebraic function of B4 and B8, so including it spent three columns on two
# degrees of freedom and inflated optical weight in SNIC's distance metric.
#
# Note this default references `optical_features`, so an embedding-arm config
# must override input_bands (e.g. with source: embedding_features) -- the
# embedding arm does not run features_optical.
_DEFAULT_SNIC_INPUT_BANDS: list[dict[str, str]] = [
    {"source": "s2_composite", "band": "B4_median"},
    {"source": "s2_composite", "band": "B8_median"},
    {"source": "structure_features", "band": "canopy_height"},
    {"source": "structure_features", "band": "canopy_height_std"},
    {"source": "optical_features", "band": "ndvi_amplitude_annual"},
    {"source": "radar_features", "band": "vv_minus_vh_median"},
]


class SegmentationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    size: int = Field(default=10, ge=1)  # seed spacing in pixels, ~100m on 10m grid
    compactness: float = Field(default=0.5, ge=0.0)  # low = spectral, high = spatial
    connectivity: Literal[4, 8] = 8
    neighborhood_size: int = Field(default=128, ge=8)
    # Whether to z-score the SNIC input bands per-band over the ROI before
    # running SNIC. Necessary when input bands have wildly different scales
    # (S2 reflectance 0-3000, NIRv 0-1, canopy_height 0-30, dB values).
    # Without this, the largest-magnitude band dominates SNIC's distance metric.
    normalize_inputs: bool = True
    # Whether to divide the z-scored stack by the empirical RMS feature distance
    # between 4-adjacent pixels, so the summed squared colour distance is
    # invariant to band count AND to correlation between bands. Without it,
    # `compactness` means something different in a 6-band arm than in a 64-band
    # one (colour distance grows with the number of effective axes, weakening
    # the spatial term). Makes compactness COMPARABLE across arms; it does not
    # make any particular value correct -- that still needs a sweep.
    normalize_distance_scale: bool = True
    # The bands SNIC segments on. Config-driven so that swapping the
    # segmentation feature space (e.g. to an embedding) is a YAML edit rather
    # than a code change.
    input_bands: list[SnicInputBand] = Field(
        default_factory=lambda: [SnicInputBand(**b) for b in _DEFAULT_SNIC_INPUT_BANDS],
        min_length=1,
    )

    def input_sources(self) -> set[str]:
        """PipelineContext keys the configured SNIC stack reads.

        One definition, used by three callers that must agree: the
        orchestrator (to decide which feature stages a run needs), the
        segmentation stage's validate(), and the tests.
        """
        return {b.source for b in self.input_bands}

    @field_validator("input_bands")
    @classmethod
    def _unique_band_names(cls, v: list[SnicInputBand]) -> list[SnicInputBand]:
        # A "*" entry claims every band of its source, so mixing it with named
        # bands from the same source would duplicate them after expansion. The
        # post-expansion uniqueness check lives in the segmentation stage
        # (it needs the server to say what the band names are); this catches
        # the statically-detectable half at config load.
        wildcarded = {b.source for b in v if b.band == "*"}
        for src in sorted(wildcarded):
            if sum(1 for b in v if b.source == src) > 1:
                raise ValueError(
                    f"segmentation.input_bands: source {src!r} uses band '*' "
                    "(all bands) together with other entries. Use either '*' "
                    "or an explicit band list for a given source, not both."
                )
        names = [b.band for b in v if b.band != "*"]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(
                f"segmentation.input_bands: duplicate band name(s) {dupes}. "
                "Band names must be unique -- they become the SNIC input band names."
            )
        return v


class ClusteringParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    k: int = Field(default=6, ge=2, le=50)
    n_training_samples: int = Field(default=10000, ge=100)
    seed: int = 42
    # Which feature vector k-means clusters.
    #   "handcrafted" (default): the multi-sensor hand-engineered stack
    #     (optical + radar + structure + static), the pipeline's original arm.
    #   "embedding": a single pretrained per-pixel embedding image from the
    #     features_embedding stage (AlphaEarth or Tessera).
    # Everything downstream of the raw stack (superpixel means, log/robust
    # scaling, k-means) is band-name-agnostic and runs identically for both, so
    # the two arms are directly comparable through the metrics stage.
    feature_source: Literal["handcrafted", "embedding"] = "handcrafted"
    # Skewness threshold above which a feature gets log-transformed before scaling.
    # Per DEC-004: a feature with |skew| > 1.0 is log-transformed via log(x - min + 1e-3).
    skewness_threshold: float = Field(default=1.0, ge=0.0)
    # Pixels per superpixel cap for reduceConnectedComponents. Must exceed our
    # largest SNIC superpixel; 1024 is generous at size=10.
    superpixel_max_size: int = Field(default=1024, ge=64, le=8192)


class NormalizationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Default is "robust" (median/IQR scaling) per DEC-003; outlier-resistant,
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

    # ----- Raster (existing) -----
    export_geotiff: bool = True
    export_gee_asset: bool = False
    analysis_scale_m: int = Field(default=10, ge=1)

    # ----- Drive folder (new) -----
    # Folder under My Drive where all exports land. Was previously hardcoded
    # to "fmu_exports" in ExportStage.DRIVE_FOLDER.
    drive_folder: str = "fmu_exports"

    # ----- Vector outputs (new) -----
    # Two vector layers, each with rich attributes (see docs/outputs.md):
    #   stands_snic     - one polygon per SNIC superpixel (debugging /
    #                     methodology layer). ~1,529 features for Sanjay Van.
    #   stands_dissolved - one polygon per connected same-cluster region
    #                     (forester-facing management units).
    export_vector_snic: bool = True
    export_vector_dissolved: bool = True
    # Output formats per vector layer. Each format gets its own Drive task.
    # SHP has a 10-char field-name limit so it carries only the minimal
    # attribute set; GeoJSON gets the full attribute schema.
    vector_formats: list[Literal["shp", "geojson"]] = Field(
        default=["shp", "geojson"], min_length=1
    )
    # Minimum pixel count for a dissolved stand to survive filtering.
    # Speckle (1-3 px misclassifications) gets dropped. Applies to the
    # dissolved layer ONLY; SNIC superpixels are unfiltered because SNIC
    # already enforces its own minimum-size via the `size` parameter.
    vector_min_stand_pixels: int = Field(default=4, ge=1, le=1000)

    @field_validator("vector_formats")
    @classmethod
    def _formats_unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError(f"vector_formats must not contain duplicates: {v}")
        return v


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
    features_embedding: FeaturesEmbeddingParams = Field(default_factory=FeaturesEmbeddingParams)
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

    @model_validator(mode="after")
    def _snic_optical_prefix_matches_index(self) -> Config:
        """Catch the one SNIC band name that silently depends on another block.

        features_optical prefixes its harmonic bands with `features_optical.index`
        ("ndvi" or "nirv"), so the default stack's `ndvi_amplitude_annual` does
        not exist in an `index: nirv` arm. Left unchecked that surfaces as a GEE
        band-not-found error partway through a run, after the expensive feature
        stages have already been billed. Cheap to catch here instead.

        Only the ndvi_/nirv_ prefix is checked -- other optical bands
        (composite_*, obs_count, ...) are index-independent.
        """
        index = self.features_optical.index
        wrong = {"ndvi", "nirv"} - {index}
        offenders = [
            b.band
            for b in self.segmentation.input_bands
            if b.source == "optical_features"
            and any(b.band.startswith(f"{p}_") for p in wrong)
        ]
        if offenders:
            raise ValueError(
                f"segmentation.input_bands names optical band(s) {sorted(offenders)}, "
                f"but features_optical.index is {index!r}, so features_optical "
                f"produces {index}_* bands. Rename the band(s) to the {index}_ "
                f"prefix, or change features_optical.index."
            )
        return self


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
