"""A `features` toggle set to false is refused when the config loads (round 13 question 37, round 14).

Nothing reads the four toggles of the `features` block (review C20): which feature stages run, and
which bands a run uses, are set by clustering.feature_source, segmentation.input_bands and
merge.criteria. Until round 14 a false loaded without a word and changed nothing but the legacy
fingerprint, so a reader could think it had switched a feature family off. Jaskaran's answer to
question 37 (a), round 14: "Make a config with any toggle false fail to load, with a message that
names the settings which do choose the features."

The block stays, all true, because the legacy fingerprint hashes it (removing it would move every
legacy fingerprint). Offline: the configs are built in memory or written to tmp_path.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from fmu.config import Config, FeatureToggles, load_config
from fmu.utils.caching import config_fingerprint, step_keys

REPO = Path(__file__).resolve().parent.parent
TOGGLES = ("optical_harmonic", "radar", "canopy_height", "terrain")
# The settings that do choose the features, which the refusal must name.
CHOOSERS = ("clustering.feature_source", "segmentation.input_bands", "merge.criteria")

MINIMAL = textwrap.dedent("""\
    name: toggles_test
    roi:
      name: t
      roi_file: aois/sanjay_van.geojson
    dates:
      phenology: {start: 2020-01-01, end: 2024-12-31}
      radar:     {start: 2020-01-01, end: 2024-12-31}
      optical_composite: {start: 2023-01-01, end: 2023-12-31}
    """)


def _write(tmp_path: Path, features: str | None) -> Path:
    path = tmp_path / "toggles_test.yaml"
    path.write_text(MINIMAL + ("" if features is None else f"features: {features}\n"))
    return path


@pytest.mark.parametrize("toggle", TOGGLES)
def test_a_config_with_one_toggle_false_fails_to_load(tmp_path: Path, toggle: str):
    with pytest.raises(ValidationError) as refused:
        load_config(_write(tmp_path, f"{{{toggle}: false}}"))
    message = str(refused.value)
    assert f"features.{toggle}" in message
    for setting in CHOOSERS:
        assert setting in message, setting


def test_every_toggle_set_false_is_named(tmp_path: Path):
    with pytest.raises(ValidationError) as refused:
        load_config(_write(tmp_path, "{" + ", ".join(f"{t}: false" for t in TOGGLES) + "}"))
    message = str(refused.value)
    for toggle in TOGGLES:
        assert f"features.{toggle}" in message, toggle


@pytest.mark.parametrize("written", ["false", "no", "0"])
def test_a_false_is_refused_however_yaml_spells_it(tmp_path: Path, written: str):
    with pytest.raises(ValidationError, match="features.radar"):
        load_config(_write(tmp_path, f"{{radar: {written}}}"))


def test_the_model_refuses_a_false_however_the_config_is_built():
    with pytest.raises(ValidationError, match="features.terrain"):
        FeatureToggles(terrain=False)
    raw = {
        "name": "toggles_test",
        "roi": {"name": "t", "roi_file": "aois/sanjay_van.geojson"},
        "dates": {
            "phenology": {"start": "2020-01-01", "end": "2024-12-31"},
            "radar": {"start": "2020-01-01", "end": "2024-12-31"},
            "optical_composite": {"start": "2023-01-01", "end": "2023-12-31"},
        },
        "features": {"canopy_height": False},
    }
    with pytest.raises(ValidationError, match="features.canopy_height"):
        Config.model_validate(raw)


@pytest.mark.parametrize(
    "features",
    [None, "{}", "{optical_harmonic: true, radar: true, canopy_height: true, terrain: true}"],
    ids=["left out", "empty", "all four true"],
)
def test_a_config_with_the_toggles_true_or_left_out_loads_as_before(tmp_path: Path, features):
    """Passes before and after: what loads today still loads, to the same fingerprint and keys."""
    cfg = load_config(_write(tmp_path, features))
    assert cfg.features.model_dump() == dict.fromkeys(TOGGLES, True)
    left_out = load_config(_write(tmp_path, None))
    assert config_fingerprint(cfg) == config_fingerprint(left_out)
    assert step_keys(cfg) == step_keys(left_out)


def test_every_config_under_configs_loads_and_sets_no_toggle_false():
    """Passes before and after: no config sets a toggle false, so the refusal moves nothing."""
    paths = sorted((REPO / "configs").rglob("*.yaml"))
    assert len(paths) >= 74
    for path in paths:
        assert all(load_config(path).features.model_dump().values()), path
