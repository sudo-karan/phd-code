"""The round 9 copies of configs, offline.

Round 9 (17 Oct 2026) re-runs configs from scratch as copies named `<name>_r9`, and its cache
test (task D) a second copy `<name>_r9_check`, each changing nothing but the name. A copy has
its source's fingerprint and per-step keys, under a new name, so its cache starts empty, and
having no legacy asset it runs in the per-step layout. Copies that change more than the name
(task H's AlphaEarth configs) are listed with what they change.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from fmu.config import load_config
from fmu.utils.caching import config_fingerprint, step_keys

REPO = Path(__file__).resolve().parent.parent
CONFIGS = REPO / "configs"
R9 = sorted(p for p in CONFIGS.glob("*_r9*.yaml"))
SUFFIXES = ("_r9_check", "_r9")
# A copy that changes more than its name: copy -> (source, the keys it changes besides the name).
DISTRICTS = ("angul", "dhenkanal", "kendujhar", "koraput")
# Task H: the AlphaEarth arm on the boxes. The feature description changes as Sanjay Van's
# AlphaEarth arm changes it; datasets.embedding and features_embedding are written out at the
# code's defaults (features_embedding.band_names: null equals its absence, so it is not listed).
ALPHAEARTH: dict[str, tuple[str, set[tuple[str, ...]]]] = {
    f"odisha_alphaearth_3ha_squares_{d}_keptland_r9": (
        f"odisha_v120_3ha_squares_{d}_keptland_s1desc_r9",
        {("description",), ("datasets", "embedding"), ("features_embedding", "collapse_reducer"),
         ("segmentation", "input_bands"), ("clustering", "feature_source")},
    )
    for d in DISTRICTS
}
NOT_NAME_ONLY: dict[str, tuple[str, set[tuple[str, ...]]]] = {**ALPHAEARTH}


def _source(stem: str) -> str:
    for suffix in SUFFIXES:
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    raise AssertionError(f"{stem} is not a round 9 copy")


def _flat(d: dict, prefix: tuple = ()) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flat(v, prefix + (k,)))
        else:
            out[prefix + (k,)] = v
    return out


def test_there_are_round_9_copies():
    assert {p.stem for p in R9} >= {
        "odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9",
        "odisha_v120_3ha_squares_kendujhar_keptland_s1desc_r9_check",
    }


@pytest.mark.parametrize("path", R9, ids=lambda p: p.stem)
def test_a_copy_changes_only_its_name(path: Path):
    source, extra = NOT_NAME_ONLY.get(path.stem, (_source(path.stem), set()))
    a = _flat(yaml.safe_load((CONFIGS / f"{source}.yaml").read_text()))
    b = _flat(yaml.safe_load(path.read_text()))
    changed = {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}
    assert changed == {("name",)} | extra, sorted(changed)
    assert b[("name",)] == path.stem


@pytest.mark.parametrize("path", R9, ids=lambda p: p.stem)
def test_a_name_only_copy_has_its_sources_keys(path: Path):
    if path.stem in NOT_NAME_ONLY:
        pytest.skip("changes more than the name")
    copy, source = load_config(path), load_config(CONFIGS / f"{_source(path.stem)}.yaml")
    assert config_fingerprint(copy) == config_fingerprint(source)
    assert step_keys(copy) == step_keys(source)


def _loaded(path: Path) -> dict:
    return _flat(load_config(path).model_dump(mode="json"))


def _loaded_difference(a: Path, b: Path) -> set:
    fa, fb = _loaded(a), _loaded(b)
    return {k for k in fa.keys() | fb.keys() if fa.get(k) != fb.get(k)}


def test_the_alphaearth_copies_exist():
    assert set(ALPHAEARTH) <= {p.stem for p in R9}


@pytest.mark.parametrize("stem", sorted(ALPHAEARTH))
def test_an_alphaearth_copy_changes_the_features_as_sanjay_van_does(stem: str):
    source, _ = ALPHAEARTH[stem]
    mine = _loaded_difference(CONFIGS / f"{source}.yaml", CONFIGS / f"{stem}.yaml")
    sanjay = _loaded_difference(CONFIGS / "sanjay_van_baseline_keptland.yaml",
                                CONFIGS / "sanjay_van_alphaearth_keptland.yaml")
    # Sanjay Van's arm also points its metrics at the hand-crafted arm; that is not the feature
    # description, and the copies keep the copied config's (none).
    assert mine == sanjay - {("metrics", "reference_config_name")}
    assert mine == {("name",), ("description",), ("clustering", "feature_source"), ("segmentation", "input_bands")}
    copy = load_config(CONFIGS / f"{stem}.yaml")
    assert copy.clustering.k == 5 and copy.clustering.seed == 42


@pytest.mark.parametrize("stem", sorted(ALPHAEARTH))
def test_an_alphaearth_copy_shares_the_steps_the_features_do_not_touch(stem: str):
    source, _ = ALPHAEARTH[stem]
    mine, theirs = step_keys(load_config(CONFIGS / f"{stem}.yaml")), step_keys(load_config(CONFIGS / f"{source}.yaml"))
    for step in ("masking", "data_load", "features_optical", "features_structure"):
        assert mine[step] == theirs[step], step
    assert mine["segmentation"] != theirs["segmentation"]
