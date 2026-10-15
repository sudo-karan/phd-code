"""Offline checks of the four descending-orbit kept-land configs of round 7.

configs/odisha_v120_3ha_squares_<district>_keptland_s1desc.yaml copies the round-6 config
configs/odisha_v120_3ha_squares_<district>_keptland.yaml and differs from it only in
data_load.s1_orbit, DESCENDING, and in its name, description and Drive folder (Jaskaran, 15 Oct
2026, round 7, his answer (b) to question 4 of docs/handoff/2026-10-15-round6.md;
docs/decisions.yaml, spec-odisha-keptland-s1-orbit-descending). The fingerprints are pinned,
because the reuse of upstream assets and the batch run name assets by them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from fmu.config import load_config
from fmu.utils.caching import config_fingerprint

REPO = Path(__file__).resolve().parent.parent
DISTRICTS = ("angul", "dhenkanal", "kendujhar", "koraput")

# new config -> the config it copies
SOURCES = {f"odisha_v120_3ha_squares_{d}_keptland_s1desc": f"odisha_v120_3ha_squares_{d}_keptland"
           for d in DISTRICTS}
CHANGED = {("name",), ("description",), ("export", "drive_folder"), ("data_load", "s1_orbit")}
# new config -> its cache fingerprint (pinned when the configs were written, round 7)
PINNED: dict[str, str] = {
    "odisha_v120_3ha_squares_angul_keptland_s1desc": "19038a24f3",
    "odisha_v120_3ha_squares_dhenkanal_keptland_s1desc": "b1769e9bdf",
    "odisha_v120_3ha_squares_kendujhar_keptland_s1desc": "e677e4866c",
    "odisha_v120_3ha_squares_koraput_keptland_s1desc": "e69861d62a",
}


def _flat(d: dict, prefix: tuple = ()) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flat(v, prefix + (k,)))
        else:
            out[prefix + (k,)] = v
    return out


def _yaml(name: str) -> dict:
    return yaml.safe_load((REPO / "configs" / f"{name}.yaml").read_text())


def test_the_four_configs_are_the_ones_on_disk():
    assert {p.stem for p in (REPO / "configs").glob("*_s1desc.yaml")} == set(SOURCES)


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_an_s1desc_config_changes_only_the_orbit_and_its_names(name: str):
    a, b = _flat(_yaml(SOURCES[name])), _flat(_yaml(name))
    changed = {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}
    assert changed == CHANGED, sorted(changed ^ CHANGED)
    assert a[("data_load", "s1_orbit")] == "ASCENDING"
    assert b[("data_load", "s1_orbit")] == "DESCENDING"
    assert b[("name",)] == name
    assert b[("export", "drive_folder")] == "fmu_exports_kept_land_s1desc"


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_an_s1desc_config_loads_with_the_round_6_settings(name: str):
    new = load_config(REPO / "configs" / f"{name}.yaml")
    old = load_config(REPO / "configs" / f"{SOURCES[name]}.yaml")
    assert new.data_load.s1_orbit == "DESCENDING" and old.data_load.s1_orbit == "ASCENDING"
    # Everything the round-6 run had: kept land only, the soft ceiling, the fit without the
    # small stands, the distance cap, the box ROI and k.
    assert new.segmentation.mask_before_snic is True
    assert new.merge.pass2_soft_ceiling is True and new.merge.pass2_skip_at_min_area is True
    assert new.clustering.fit_excludes_stands_below_min_area is True
    assert new.features_static.cap_distance_to_water is True
    assert new.roi == old.roi and new.clustering.k == old.clustering.k == 5
    assert new.merge.max_area_ha == old.merge.max_area_ha == 3.0


def test_each_has_a_fingerprint_of_its_own():
    fps = {name: config_fingerprint(load_config(REPO / "configs" / f"{name}.yaml"))
           for name in SOURCES}
    assert len(set(fps.values())) == len(fps)
    for name, fp in fps.items():
        assert fp != config_fingerprint(load_config(REPO / "configs" / f"{SOURCES[name]}.yaml"))


@pytest.mark.parametrize("name", sorted(PINNED))
def test_the_fingerprint_is_the_pinned_one(name: str):
    """The reuse plan and the batch name assets by these. If one moves, rerun the reuse tool's
    dry run before anything else."""
    assert config_fingerprint(load_config(REPO / "configs" / f"{name}.yaml")) == PINNED[name]
