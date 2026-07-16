"""
Module 2 tests: config schema validation and YAML loading.

These tests verify:
  1. The baseline YAML loads cleanly into a Config object
  2. Schema rejects bad inputs with clear errors
  3. Both ROI source options behave correctly
  4. Date ranges are validated
  5. Defaults work when fields are omitted
  6. v1.1.0 fields (masking toggles, time_reference, vector export knobs)
     have the right defaults and validators
"""

from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from fmu.config import (
    Config,
    DateRange,
    DatesConfig,
    ExportParams,
    FeaturesOpticalParams,
    MaskingParams,
    ROIConfig,
    load_config,
)

# ---------- Path to baseline YAML ----------

REPO_ROOT = Path(__file__).parent.parent
BASELINE_YAML = REPO_ROOT / "configs" / "sanjay_van_baseline.yaml"


# ---------- Loading the baseline ----------


def test_baseline_yaml_exists():
    assert BASELINE_YAML.exists(), f"Baseline config not found at {BASELINE_YAML}"


def test_baseline_yaml_loads():
    cfg = load_config(BASELINE_YAML)
    assert isinstance(cfg, Config)
    assert cfg.name == "sanjay_van_baseline"


def test_baseline_fields_have_expected_values():
    """Spot-check that the baseline values match what we locked."""
    cfg = load_config(BASELINE_YAML)
    assert cfg.roi.name == "sanjay_van"
    assert cfg.clustering.k == 6
    assert cfg.normalization.method == "robust"  # per DEC-003
    assert cfg.segmentation.size == 10
    assert cfg.cloud_mask.max_cloud_pct == 20.0


def test_baseline_dates_parse():
    cfg = load_config(BASELINE_YAML)
    # Single shared 2017-2022 window across all time-series features (deck v3.0).
    assert cfg.dates.phenology.start.year == 2017
    assert cfg.dates.phenology.end.year == 2022
    assert cfg.dates.radar.end.year == 2022


# ---------- ROI validation ----------


def test_roi_requires_exactly_one_source():
    # Both set
    with pytest.raises(ValidationError, match="exactly one"):
        ROIConfig(name="x", roi_file=Path("a.geojson"), roi_asset="projects/x/y")
    # Neither set
    with pytest.raises(ValidationError, match="exactly one"):
        ROIConfig(name="x")


def test_roi_file_only():
    roi = ROIConfig(name="x", roi_file=Path("aois/x.geojson"))
    assert roi.roi_file == Path("aois/x.geojson")
    assert roi.roi_asset is None


def test_roi_asset_only():
    roi = ROIConfig(name="x", roi_asset="projects/test/assets/x")
    assert roi.roi_asset == "projects/test/assets/x"
    assert roi.roi_file is None


# ---------- Date validation ----------


def test_date_range_rejects_inverted():
    with pytest.raises(ValidationError, match="before start"):
        DateRange(start="2024-01-01", end="2020-01-01")


def test_date_range_accepts_equal():
    """A single-day range is valid (rare but legal)."""
    dr = DateRange(start="2024-01-01", end="2024-01-01")
    assert dr.start == dr.end


def test_dates_config_requires_all_three():
    with pytest.raises(ValidationError):
        DatesConfig(phenology={"start": "2020-01-01", "end": "2024-12-31"})  # type: ignore[arg-type]


# ---------- Strict schema: no unknown fields ----------


def test_unknown_field_raises(tmp_path):
    """A typo in the config should fail loud, not be silently ignored."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(
        textwrap.dedent("""\
        name: test
        typo_field: 123          # not in schema
        roi:
          name: t
          roi_file: aois/t.geojson
        dates:
          phenology: {start: 2020-01-01, end: 2024-12-31}
          radar:     {start: 2020-01-01, end: 2024-12-31}
          optical_composite: {start: 2023-01-01, end: 2023-12-31}
        """)
    )
    with pytest.raises(ValidationError, match="typo_field"):
        load_config(bad_yaml)


def test_name_rejects_unsafe_characters():
    """Config names go into file paths, so they shouldn't contain slashes etc."""
    with pytest.raises(ValidationError, match="path-safe"):
        Config(
            name="bad/name",
            roi=ROIConfig(name="t", roi_file=Path("aois/t.geojson")),
            dates=DatesConfig(
                phenology=DateRange(start="2020-01-01", end="2024-12-31"),
                radar=DateRange(start="2020-01-01", end="2024-12-31"),
                optical_composite=DateRange(start="2023-01-01", end="2023-12-31"),
            ),
        )


# ---------- Defaults ----------


def test_defaults_fill_in_when_omitted(tmp_path):
    """Minimal YAML should fill in defaults for everything optional."""
    minimal_yaml = tmp_path / "minimal.yaml"
    minimal_yaml.write_text(
        textwrap.dedent("""\
        name: minimal_test
        roi:
          name: t
          roi_file: aois/t.geojson
        dates:
          phenology: {start: 2020-01-01, end: 2024-12-31}
          radar:     {start: 2020-01-01, end: 2024-12-31}
          optical_composite: {start: 2023-01-01, end: 2023-12-31}
        """)
    )
    cfg = load_config(minimal_yaml)
    # All defaults should be filled
    assert cfg.clustering.k == 6
    # Default is "robust" per DEC-003; was "zscore" pre-2026-05-20
    assert cfg.normalization.method == "robust"
    assert cfg.export.export_geotiff is True
    assert cfg.features.optical_harmonic is True


# ---------- Loader robustness ----------


def test_load_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_config("does_not_exist.yaml")


def test_load_non_mapping_raises(tmp_path):
    bad = tmp_path / "list.yaml"
    bad.write_text("- just\n- a\n- list\n")
    with pytest.raises(ValueError, match="mapping"):
        load_config(bad)


# ---------- masking: IndiaSAT-primary habitat ----------


def test_masking_habitat_classes_default():
    """Default habitat = IndiaSAT Trees (6) + Shrubs/Scrubs (12)."""
    mp = MaskingParams()
    assert mp.indiasat_habitat_classes == [6, 12]
    assert mp.indiasat_class_band is None
    assert mp.keep_worldcover_classes == [10, 20, 30]  # WorldCover fallback


def test_masking_habitat_classes_settable():
    mp = MaskingParams(indiasat_habitat_classes=[6], indiasat_class_band="label")
    assert mp.indiasat_habitat_classes == [6]
    assert mp.indiasat_class_band == "label"


def test_masking_rejects_removed_builtup_fields():
    """The VIIRS / Open Buildings toggles are gone (single-phase mask)."""
    with pytest.raises(ValidationError):
        MaskingParams(use_viirs=True)  # type: ignore[call-arg]


def test_baseline_masking_uses_indiasat():
    """Both baseline and variant YAMLs define IndiaSAT-primary masking."""
    cfg = load_config(BASELINE_YAML)
    assert cfg.masking.indiasat_habitat_classes == [6, 12]
    assert "ee-indiasat" in cfg.datasets.indiasat


# ---------- v1.1.0: features_optical.time_reference ----------


def test_time_reference_defaults_to_2017_01_01():
    """Default anchor preserves cross-config phase comparability."""
    fop = FeaturesOpticalParams()
    assert fop.time_reference == date(2017, 1, 1)


def test_time_reference_accepts_custom_date():
    fop = FeaturesOpticalParams(time_reference=date(2020, 6, 15))
    assert fop.time_reference == date(2020, 6, 15)


def test_time_reference_parses_iso_string(tmp_path):
    """YAML stores dates as 'YYYY-MM-DD' strings; pydantic should coerce."""
    cfg_yaml = tmp_path / "with_anchor.yaml"
    cfg_yaml.write_text(
        textwrap.dedent("""\
        name: anchor_test
        roi:
          name: t
          roi_file: aois/t.geojson
        dates:
          phenology: {start: 2020-01-01, end: 2024-12-31}
          radar:     {start: 2020-01-01, end: 2024-12-31}
          optical_composite: {start: 2023-01-01, end: 2023-12-31}
        features_optical:
          index: ndvi
          harmonic_mode: single
          include_trend: true
          time_reference: 2019-03-15
        """)
    )
    cfg = load_config(cfg_yaml)
    assert cfg.features_optical.time_reference == date(2019, 3, 15)


def test_time_reference_rejects_non_date():
    with pytest.raises(ValidationError):
        FeaturesOpticalParams(time_reference="not-a-date")  # type: ignore[arg-type]


# ---------- v1.1.0: export.drive_folder ----------


def test_drive_folder_defaults_to_fmu_exports():
    """Default preserves the pre-v1.1.0 ExportStage.DRIVE_FOLDER class constant."""
    assert ExportParams().drive_folder == "fmu_exports"


def test_drive_folder_accepts_custom():
    ep = ExportParams(drive_folder="my_research_outputs")
    assert ep.drive_folder == "my_research_outputs"


# ---------- v1.1.0: vector export toggles ----------


def test_vector_export_toggles_default_true():
    ep = ExportParams()
    assert ep.export_vector_snic is True
    assert ep.export_vector_dissolved is True


def test_vector_export_toggles_independent():
    """All four combos of the two toggles should validate."""
    for snic in (True, False):
        for dissolved in (True, False):
            ep = ExportParams(
                export_vector_snic=snic, export_vector_dissolved=dissolved
            )
            assert ep.export_vector_snic is snic
            assert ep.export_vector_dissolved is dissolved


# ---------- v1.1.0: vector_formats ----------


def test_vector_formats_default():
    assert ExportParams().vector_formats == ["shp", "geojson"]


def test_vector_formats_accepts_single():
    ep = ExportParams(vector_formats=["geojson"])
    assert ep.vector_formats == ["geojson"]


def test_vector_formats_rejects_empty():
    with pytest.raises(ValidationError):
        ExportParams(vector_formats=[])


def test_vector_formats_rejects_invalid_value():
    with pytest.raises(ValidationError):
        ExportParams(vector_formats=["kml"])  # type: ignore[list-item]
    with pytest.raises(ValidationError):
        ExportParams(vector_formats=["shp", "csv"])  # type: ignore[list-item]


def test_vector_formats_rejects_duplicates():
    """Duplicate formats would submit redundant Drive tasks; reject."""
    with pytest.raises(ValidationError, match="duplicates"):
        ExportParams(vector_formats=["shp", "shp"])
    with pytest.raises(ValidationError, match="duplicates"):
        ExportParams(vector_formats=["geojson", "geojson"])


# ---------- v1.1.0: vector_min_stand_pixels ----------


def test_vector_min_stand_pixels_default():
    assert ExportParams().vector_min_stand_pixels == 4


def test_vector_min_stand_pixels_accepts_in_range():
    assert ExportParams(vector_min_stand_pixels=1).vector_min_stand_pixels == 1
    assert ExportParams(vector_min_stand_pixels=1000).vector_min_stand_pixels == 1000


def test_vector_min_stand_pixels_rejects_zero():
    with pytest.raises(ValidationError):
        ExportParams(vector_min_stand_pixels=0)


def test_vector_min_stand_pixels_rejects_negative():
    with pytest.raises(ValidationError):
        ExportParams(vector_min_stand_pixels=-1)


def test_vector_min_stand_pixels_rejects_over_max():
    with pytest.raises(ValidationError):
        ExportParams(vector_min_stand_pixels=1001)


# ---------- v1.1.0: baseline YAML still validates ----------


def test_baseline_yaml_has_v1_1_0_defaults():
    """The shipped baseline relies on v1.1.0 fields defaulting correctly."""
    cfg = load_config(BASELINE_YAML)
    # masking
    assert cfg.masking.indiasat_habitat_classes == [6, 12]
    assert cfg.masking.keep_worldcover_classes == [10, 20, 30]
    # features_optical
    assert cfg.features_optical.time_reference == date(2017, 1, 1)
    # export
    assert cfg.export.drive_folder == "fmu_exports"
    assert cfg.export.export_vector_snic is True
    assert cfg.export.export_vector_dissolved is True
    assert cfg.export.vector_formats == ["shp", "geojson"]
    assert cfg.export.vector_min_stand_pixels == 4
