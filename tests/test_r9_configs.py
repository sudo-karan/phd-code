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
# Task I: the district cost pilot, the Angul _r9 config on one 10 km tile; only the ROI changes.
TILE = "odisha_v120_3ha_tile10km_angul_keptland_s1desc_r9"
TILE_SOURCE = "odisha_v120_3ha_squares_angul_keptland_s1desc_r9"
NOT_NAME_ONLY: dict[str, tuple[str, set[tuple[str, ...]]]] = {
    **ALPHAEARTH,
    TILE: (TILE_SOURCE, {("description",), ("roi", "name"), ("roi", "roi_file")}),
}


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


def test_the_tile_copy_changes_only_the_roi():
    mine = _loaded_difference(CONFIGS / f"{TILE_SOURCE}.yaml", CONFIGS / f"{TILE}.yaml")
    assert mine == {("name",), ("description",), ("roi", "name"), ("roi", "roi_file")}


def test_the_tile_is_the_declared_square():
    """10 km by 10 km, north-up in EPSG:32645, centred on the centroid of the union of the Angul boxes."""
    import json

    pytest.importorskip("shapely")
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform, unary_union

    to_utm = Transformer.from_crs(4326, 32645, always_xy=True).transform
    boxes = json.loads((REPO / "aois" / "odisha_squares_angul.geojson").read_text())
    centre = transform(to_utm, unary_union([shape(f["geometry"]) for f in boxes["features"]])).centroid
    tile_fc = json.loads((REPO / load_config(CONFIGS / f"{TILE}.yaml").roi.roi_file).read_text())
    assert len(tile_fc["features"]) == 1
    tile = transform(to_utm, shape(tile_fc["features"][0]["geometry"]))
    x0, y0, x1, y1 = tile.bounds
    assert abs(x1 - x0 - 10_000) < 0.01 and abs(y1 - y0 - 10_000) < 0.01
    assert abs(tile.area - 1e8) < 1e2  # a square, not a rotated or bent one
    assert abs((x0 + x1) / 2 - centre.x) < 0.01 and abs((y0 + y1) / 2 - centre.y) < 0.01
