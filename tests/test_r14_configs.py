"""The R3 configs of round 14 (Task 3): the nineteen _r9 configs copied under _r14, and two
copies of the Angul hand-crafted 3 ha one for the live check.

Round 14 brief, Task 3: "Copy each of the 19 _r9 configs under the suffix _r14, changing only the
name and the four new settings. Leave k as it is for now; Task 7 sets it. ... Pin their
fingerprints in the tests. For the live check, add two more copies of the Angul hand-crafted 3 ha
config, ..._r14_check_a and ..._r14_check_b, identical except for their names."
odisha_script/PHASE_KEPTLAND_PREDECLARED.md, the change of 26 Oct 2026, declares the runs.

The legacy fingerprints are pinned here and every step key in tests/data/r14_config_keys.json,
both as computed when the configs were written, but the merge, clustering and k_elbow keys,
pinned again on 27 Oct 2026, when the merge's revision 4 moved them (round 14's questions 11 and
2: every count of the merge on the label image's own projection, and every tie of the merge by
centroid); no other key and no fingerprint moved. Task 7 sets k, which moves the fingerprint and
the clustering key, and not the k elbow's: it updates the pins in the same commit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fmu.config import load_config
from fmu.stages.base import get_stage_class, list_registered_stages
from fmu.utils.caching import STEP_SETTINGS, config_fingerprint, step_keys

REPO = Path(__file__).resolve().parent.parent
CONFIGS = REPO / "configs"
SOURCES = sorted(CONFIGS.glob("*_r9.yaml"))
R3 = sorted(CONFIGS.glob("*_r14.yaml"))
CHECKS = [CONFIGS / f"odisha_v120_3ha_squares_angul_keptland_s1desc_r14_{s}.yaml" for s in ("check_a", "check_b")]
# Pinned again on 27 Oct 2026 (round 14): the merge's revision 4 moved the merge, clustering and
# k_elbow keys of every config here (every count of the merge on the label image's own
# projection, round 14's question 11, and pass 1's tie by centroid, question 2); the masking,
# data_load, feature and segmentation keys and the legacy fingerprints did not move.
KEYS = json.loads((REPO / "tests" / "data" / "r14_config_keys.json").read_text())
FOUR = {
    ("clustering", "fit_outside_earth_engine"): True,
    ("clustering", "log_rule"): "right_skew",
    ("features_optical", "mean_over_window"): True,
    ("k_elbow", "in_fit_space"): True,
}
# The legacy fingerprints, as the configs were written (26 Oct 2026, round 14).
FINGERPRINTS = {
    "odisha_alphaearth_10ha_squares_angul_keptland_r14": "4e3761771e",
    "odisha_alphaearth_10ha_squares_dhenkanal_keptland_r14": "29478f80c0",
    "odisha_alphaearth_10ha_squares_kendujhar_keptland_r14": "290a812030",
    "odisha_alphaearth_10ha_squares_koraput_keptland_r14": "ff0d75baa6",
    "odisha_alphaearth_3ha_squares_angul_keptland_r14": "6e61c02b27",
    "odisha_alphaearth_3ha_squares_dhenkanal_keptland_r14": "0f42ac8e09",
    "odisha_alphaearth_3ha_squares_kendujhar_keptland_r14": "c80e39c639",
    "odisha_alphaearth_3ha_squares_koraput_keptland_r14": "7bfc7bfa24",
    "odisha_v120_10ha_squares_angul_keptland_s1desc_r14": "3ac3adb10f",
    "odisha_v120_10ha_squares_dhenkanal_keptland_s1desc_r14": "f8deacddd6",
    "odisha_v120_10ha_squares_kendujhar_keptland_s1desc_r14": "174de165d7",
    "odisha_v120_10ha_squares_koraput_keptland_s1desc_r14": "43897c2077",
    "odisha_v120_3ha_squares_angul_keptland_s1desc_r14": "25ecc2af59",
    "odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_a": "25ecc2af59",
    "odisha_v120_3ha_squares_angul_keptland_s1desc_r14_check_b": "25ecc2af59",
    "odisha_v120_3ha_squares_dhenkanal_keptland_s1desc_r14": "9d0f42152a",
    "odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r14": "5e5d8f17ab",
    "odisha_v120_3ha_squares_koraput_keptland_s1desc_r14": "71e14a573f",
    "odisha_v120_3ha_tile10km_angul_keptland_s1desc_r14": "17e7dc5128",
    "sanjay_van_alphaearth_keptland_r14": "4bc321f551",
    "sanjay_van_baseline_keptland_r14": "0c67ee1fbd",
}


def _source(path: Path) -> Path:
    return CONFIGS / (path.stem.split("_r14")[0] + "_r9.yaml")


def _without_the_four(dump: dict) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in dump.items()}
    out.pop("name")
    for block, field in FOUR:
        out[block].pop(field)
    return out


def test_there_is_one_r3_copy_of_each_r9_config():
    assert len(SOURCES) == 19
    assert [p.name.replace("_r9.yaml", "_r14.yaml") for p in SOURCES] == [p.name for p in R3]
    assert set(FINGERPRINTS) == {p.stem for p in [*R3, *CHECKS]}


@pytest.mark.parametrize("path", [*R3, *CHECKS], ids=lambda p: p.stem)
def test_each_is_its_r9_config_but_the_name_and_the_four_settings(monkeypatch, path: Path):
    monkeypatch.chdir(REPO)
    cfg, src = load_config(path), load_config(_source(path))
    assert cfg.name == path.stem
    dump = cfg.model_dump(mode="json")
    for (block, field), value in FOUR.items():
        assert dump[block][field] == value, (block, field)
    assert _without_the_four(dump) == _without_the_four(src.model_dump(mode="json"))
    assert cfg.clustering.k == src.clustering.k  # Task 7 sets k


@pytest.mark.parametrize("path", [*R3, *CHECKS], ids=lambda p: p.stem)
def test_the_fingerprints_and_step_keys_are_pinned(monkeypatch, path: Path):
    monkeypatch.chdir(REPO)
    cfg = load_config(path)
    assert config_fingerprint(cfg) == FINGERPRINTS[path.stem]
    assert step_keys(cfg) == KEYS[path.stem]["step_keys"]


@pytest.mark.parametrize("path", R3, ids=lambda p: p.stem)
def test_they_share_their_r9_configs_steps_before_the_optical_features(monkeypatch, path: Path):
    """The settings reach features_optical and what follows it; the masks, the S2 composite and
    the other feature images have the _r9 keys (they are cached afresh all the same, as the
    asset path holds the config's name)."""
    monkeypatch.chdir(REPO)
    keys, src = step_keys(load_config(path)), step_keys(load_config(_source(path)))
    for step in ("masking", "data_load", "features_radar", "features_structure",
                 "features_static", "features_embedding"):
        assert keys[step] == src[step], step
    assert keys["features_optical"] != src["features_optical"]


def test_the_check_copies_are_the_angul_config_but_their_names(monkeypatch):
    monkeypatch.chdir(REPO)
    base = load_config(CONFIGS / "odisha_v120_3ha_squares_angul_keptland_s1desc_r14.yaml")
    for path in CHECKS:
        cfg = load_config(path)
        assert cfg.name == path.stem
        a, b = cfg.model_dump(mode="json"), base.model_dump(mode="json")
        a.pop("name"), b.pop("name")
        assert a == b
        assert step_keys(cfg) == step_keys(base)


def test_choosing_k_moves_the_clustering_key_and_not_the_elbows(monkeypatch):
    """So the elbow of the first half is read back from the cache in the second (Task 7)."""
    monkeypatch.chdir(REPO)
    cfg = load_config(R3[0])
    other = cfg.model_copy(update={"clustering": cfg.clustering.model_copy(update={"k": cfg.clustering.k + 1})})
    keys, moved = step_keys(cfg), step_keys(other)
    assert {s for s in keys if keys[s] != moved[s]} == {"clustering"}


@pytest.mark.parametrize("path", [*R3, *CHECKS], ids=lambda p: p.stem)
def test_every_task_description_fits_earth_engines_100_characters(path: Path):
    """The pipeline names a cache export <config>_<stage>_<output>, and the export stage its Drive
    files <config>_<file>; Earth Engine takes at most 100 characters."""
    import fmu.stages.clustering  # noqa: F401  (registers the stages)
    import fmu.stages.data_load  # noqa: F401
    import fmu.stages.export  # noqa: F401
    import fmu.stages.features_embedding  # noqa: F401
    import fmu.stages.features_optical  # noqa: F401
    import fmu.stages.features_radar  # noqa: F401
    import fmu.stages.features_static  # noqa: F401
    import fmu.stages.features_structure  # noqa: F401
    import fmu.stages.k_elbow  # noqa: F401
    import fmu.stages.masking  # noqa: F401
    import fmu.stages.segmentation  # noqa: F401
    from fmu.pipeline import Pipeline

    name = path.stem
    longest = 0
    for stage_name in list_registered_stages():
        if stage_name not in STEP_SETTINGS:
            continue
        stage = get_stage_class(stage_name)()
        for key in Pipeline._resolve_cacheable_outputs(stage):
            longest = max(longest, len(f"{name}_{stage_name}_{key}"))
    drive = ("cluster_labels", "features_raw", "features_scaled", "stands_dissolved_geojson")
    longest = max(longest, *(len(f"{name}_{f}") for f in drive))
    assert longest <= 100, (name, longest)
