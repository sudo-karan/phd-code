"""Non-live tests for `MergeParams` and the derived component-size cap.

The cap is the one that matters most here. `reduceConnectedComponents`'s
`maxSize` does not clamp -- it **masks any component larger than it**, deleting
those regions with no error. It used to be hand-set per config, the shipped
configs disagreed (1024 baseline vs 256 embedding), and the embedding arm
consequently lost 15 superpixels / 43.9 ha in a two-arm comparison. These tests
pin the derivation so that cannot come back.
"""

from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from fmu.config import Config, MergeParams, load_config

REPO_ROOT = Path(__file__).parent.parent
CONFIG_DIR = REPO_ROOT / "configs"
SHIPPED_CONFIGS = sorted(CONFIG_DIR.glob("sanjay_van_*.yaml"))


# ---------- MergeParams defaults ----------


def test_default_criteria_are_xiongs_three_axes():
    """Vertical structure, canopy completeness, composition -- the closest
    analogue FMU has to Xiong et al. 2024's height / closure / species."""
    assert MergeParams().criteria == {
        "canopy_height": 2.00,
        "canopy_height_std": 0.45,
        "ndvi_amplitude_annual": 0.030,
    }


def test_elevation_is_not_a_default_criterion():
    """Rank-3 separator (0.52), deliberately excluded: Sanjay Van has ~20 m of
    total relief and a within-cluster elevation IQR of 10-12 m, so including it
    means two structurally identical patches refuse to merge over 10 m of
    altitude. Terrain is a site variable, not a forest-condition variable."""
    assert "elevation" not in MergeParams().criteria


def test_radar_criterion_is_off_by_default():
    """No paper in the 20-paper survey uses radar for stand delineation, so it
    ships as a novelty claim to be ablated, not as a default."""
    assert "vv_minus_vh_median" not in MergeParams().criteria


def test_default_area_bounds_and_relaxation():
    p = MergeParams()
    assert (p.min_area_ha, p.max_area_ha) == (1.0, 10.0)
    # Xiong's SH2/SH1 = 5/3 = 1.67; 1.75 sits just above it.
    assert p.relax_factor == 1.75
    assert p.relax_factor > 1.0


def test_pass1_needs_at_least_two_defined_criteria():
    """One criterion is too weak a similarity test to justify a pass-1 merge;
    pairs that fall short drop to pass 2, which is the right destination."""
    assert MergeParams().min_defined_criteria == 2


def test_tie_break_is_shared_edge_length():
    assert MergeParams().tie_break == "shared_edge_length"


def test_merge_enabled_by_default():
    assert MergeParams().enabled is True


# ---------- MergeParams validators ----------


def test_rejects_min_area_above_max_area():
    with pytest.raises(ValidationError, match="must be <"):
        MergeParams(min_area_ha=20.0, max_area_ha=10.0)


def test_rejects_equal_area_bounds():
    with pytest.raises(ValidationError, match="must be <"):
        MergeParams(min_area_ha=10.0, max_area_ha=10.0)


def test_rejects_zero_tolerance():
    """0 rejects every pair including identical ones; removing the key is how
    you disable a criterion."""
    with pytest.raises(ValidationError, match="tolerance must be > 0"):
        MergeParams(criteria={"canopy_height": 0.0})


def test_rejects_negative_tolerance():
    with pytest.raises(ValidationError, match="tolerance must be > 0"):
        MergeParams(criteria={"canopy_height": -1.0})


def test_rejects_empty_criteria():
    with pytest.raises(ValidationError):
        MergeParams(criteria={})


def test_rejects_relax_factor_at_or_below_one():
    """A relax factor of 1 makes pass 2 identical to pass 1, so every fragment
    pass 1 could not place falls straight through to the shared-edge fallback."""
    for bad in (1.0, 0.5):
        with pytest.raises(ValidationError):
            MergeParams(relax_factor=bad)


def test_rejects_unknown_field():
    with pytest.raises(ValidationError):
        MergeParams(max_area_hectares=10)  # type: ignore[call-arg]


def test_accepts_optional_radar_criterion():
    p = MergeParams(
        criteria={
            "canopy_height": 2.0,
            "canopy_height_std": 0.45,
            "ndvi_amplitude_annual": 0.03,
            "vv_minus_vh_median": 0.65,
        }
    )
    assert "vv_minus_vh_median" in p.criteria


# ---------- Config.max_component_pixels() ----------


def test_derived_cap_at_defaults():
    """10 ha at 10 m = 1000 px of stand, x1.2 headroom = 1200.

    Against the retired hand-set values: 1024 was razor thin (2.4% under the
    stand it had to hold) and 256 was simply wrong."""
    cfg = load_config(CONFIG_DIR / "sanjay_van_baseline.yaml")
    assert cfg.max_component_pixels() == 1200


def test_derived_cap_matches_the_formula():
    cfg = load_config(CONFIG_DIR / "sanjay_van_baseline.yaml")
    scale = cfg.export.analysis_scale_m
    expected = math.ceil(
        math.ceil(cfg.merge.max_area_ha * 10_000 / (scale * scale)) * 1.2
    )
    assert cfg.max_component_pixels() == expected


def test_derived_cap_always_exceeds_the_max_stand_it_must_hold():
    """The property that actually matters: whatever the config, the cap must be
    strictly larger than a max_area_ha stand in pixels, or the largest stands
    get silently masked out of every reduceConnectedComponents result."""
    raw = yaml.safe_load((CONFIG_DIR / "sanjay_van_baseline.yaml").read_text())
    for min_area_ha, max_area_ha, scale in [
        (1.0, 10.0, 10),
        (1.0, 20.0, 10),
        (0.5, 50.0, 10),  # Xiong's natural-forest bound
        (0.1, 0.5, 10),  # Xiong's logging-stand minimum
        (1.0, 10.0, 20),
        (1.0, 10.0, 30),
        (0.5, 3.0, 5),
    ]:
        cfg_raw = copy.deepcopy(raw)
        cfg_raw["merge"] = {"min_area_ha": min_area_ha, "max_area_ha": max_area_ha}
        cfg_raw["export"]["analysis_scale_m"] = scale
        cfg = Config.model_validate(cfg_raw)
        stand_px = max_area_ha * 10_000 / (scale * scale)
        assert cfg.max_component_pixels() > stand_px, (max_area_ha, scale)


def test_derived_cap_scales_with_area_and_resolution():
    raw = yaml.safe_load((CONFIG_DIR / "sanjay_van_baseline.yaml").read_text())

    def cap(max_area_ha: float, scale: int) -> int:
        r = copy.deepcopy(raw)
        r["merge"] = {"max_area_ha": max_area_ha}
        r["export"]["analysis_scale_m"] = scale
        return Config.model_validate(r).max_component_pixels()

    assert cap(20.0, 10) == 2 * cap(10.0, 10)  # twice the area, twice the pixels
    assert cap(10.0, 20) < cap(10.0, 10)  # coarser pixels, fewer of them


def test_derived_cap_is_a_positive_int():
    cfg = load_config(CONFIG_DIR / "sanjay_van_baseline.yaml")
    v = cfg.max_component_pixels()
    assert isinstance(v, int) and v > 0


# ---------- shipped configs ----------


@pytest.mark.parametrize("path", SHIPPED_CONFIGS, ids=lambda p: p.stem)
def test_shipped_configs_agree_on_the_cap(path: Path):
    """The regression this whole change exists for: the cap must not differ
    between two arms of the same comparison."""
    assert load_config(path).max_component_pixels() == 1200


@pytest.mark.parametrize("path", SHIPPED_CONFIGS, ids=lambda p: p.stem)
def test_shipped_configs_no_longer_carry_the_retired_knob(path: Path):
    """`superpixel_max_size` is derived now. `extra="forbid"` means a leftover
    key fails the load, so this is really a guard against reintroducing it."""
    raw = yaml.safe_load(path.read_text())
    assert "superpixel_max_size" not in raw.get("clustering", {})


@pytest.mark.parametrize("path", SHIPPED_CONFIGS, ids=lambda p: p.stem)
def test_shipped_configs_share_the_merge_rules(path: Path):
    """Merge rules are part of what is held constant across arms — only the
    feature representation is supposed to differ."""
    base = load_config(CONFIG_DIR / "sanjay_van_baseline.yaml").merge
    assert load_config(path).merge.model_dump() == base.model_dump()


def test_retired_knob_is_rejected_if_reintroduced():
    raw = yaml.safe_load((CONFIG_DIR / "sanjay_van_baseline.yaml").read_text())
    raw["clustering"]["superpixel_max_size"] = 1024
    with pytest.raises(ValidationError):
        Config.model_validate(raw)
