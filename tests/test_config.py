"""
Module 2 tests: config schema validation and YAML loading.

These tests verify:
  1. The baseline YAML loads cleanly into a Config object
  2. Schema rejects bad inputs with clear errors
  3. Both ROI source options behave correctly
  4. Date ranges are validated
  5. Defaults work when fields are omitted
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from fmu.config import (
    Config,
    DateRange,
    DatesConfig,
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
    assert cfg.normalization.method == "zscore"
    assert cfg.segmentation.size == 10
    assert cfg.cloud_mask.max_cloud_pct == 20.0


def test_baseline_dates_parse():
    cfg = load_config(BASELINE_YAML)
    assert cfg.dates.phenology.start.year == 2017
    assert cfg.dates.phenology.end.year == 2024
    assert cfg.dates.radar.end.year == 2021


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


def test_empty_worldcover_classes_rejected(tmp_path):
    """An empty keep list = mask everything = no data. Catch it here, not in the stage."""
    bad_yaml = tmp_path / "empty_wc.yaml"
    bad_yaml.write_text(
        textwrap.dedent("""\
        name: empty_wc_test
        roi:
          name: t
          roi_file: aois/t.geojson
        dates:
          phenology: {start: 2020-01-01, end: 2024-12-31}
          radar:     {start: 2020-01-01, end: 2024-12-31}
          optical_composite: {start: 2023-01-01, end: 2023-12-31}
        masking:
          keep_worldcover_classes: []
        """)
    )
    with pytest.raises(ValidationError):
        load_config(bad_yaml)


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
    assert cfg.normalization.method == "zscore"
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
