"""Offline checks of the six kept-land configs of round 3 (docs/handoff/2026-10-14-round3.md).

Each copies an existing config and differs from it only in the keys Jaskaran named on 14 Oct 2026:
the name and description, the Drive folder, and the three settings of D1 to D3
(segmentation.mask_before_snic, merge.pass2_soft_ceiling,
clustering.fit_excludes_stands_below_min_area). Sanjay Van keeps its 10 ha settings and Odisha its
four 3 ha box configs (D4). The fingerprints are pinned, because the reuse of upstream assets and
the batch run both name assets by them.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from fmu.config import load_config
from fmu.utils.caching import config_fingerprint

REPO = Path(__file__).resolve().parent.parent

# new config -> the config it copies
SOURCES = {
    "sanjay_van_baseline_keptland": "sanjay_van_baseline",
    "sanjay_van_alphaearth_keptland": "sanjay_van_alphaearth",
    **{
        f"odisha_v120_3ha_squares_{d}_keptland": f"odisha_v120_3ha_squares_{d}"
        for d in ("angul", "dhenkanal", "kendujhar", "koraput")
    },
}
ALLOWED = {
    ("name",),
    ("description",),
    ("segmentation", "mask_before_snic"),
    ("merge", "pass2_soft_ceiling"),
    ("clustering", "fit_excludes_stands_below_min_area"),
    ("export", "drive_folder"),
}
# new config -> its cache fingerprint (pinned after D2 and D3 were committed)
PINNED: dict[str, str] = {
    "odisha_v120_3ha_squares_angul_keptland": "9ae5f6a1ac",
    "odisha_v120_3ha_squares_dhenkanal_keptland": "ed02415c51",
    "odisha_v120_3ha_squares_kendujhar_keptland": "05257abfb4",
    "odisha_v120_3ha_squares_koraput_keptland": "0341971814",
    "sanjay_van_alphaearth_keptland": "10f7f6ab55",
    "sanjay_van_baseline_keptland": "c953e7073a",
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


def test_the_six_configs_are_the_ones_on_disk():
    on_disk = {p.stem for p in (REPO / "configs").glob("*_keptland.yaml")}
    assert on_disk == set(SOURCES)


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_a_keptland_config_changes_only_the_named_keys(name: str):
    a, b = _flat(_yaml(SOURCES[name])), _flat(_yaml(name))
    changed = {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}
    assert changed <= ALLOWED, sorted(changed - ALLOWED)
    assert b[("name",)] == name
    assert b[("segmentation", "mask_before_snic")] is True
    assert b[("merge", "pass2_soft_ceiling")] is True
    assert b[("clustering", "fit_excludes_stands_below_min_area")] is True
    assert b[("export", "drive_folder")] == "fmu_exports_kept_land"


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_a_keptland_config_loads_with_the_settings_of_d1_to_d4(name: str):
    new = load_config(REPO / "configs" / f"{name}.yaml")
    old = load_config(REPO / "configs" / f"{SOURCES[name]}.yaml")
    assert new.name == name
    # D1: mask before SNIC; small kept patches are not dropped.
    assert new.segmentation.mask_before_snic is True
    assert new.segmentation.drop_kept_patches_below_min_area is False
    assert new.kept_patch_min_pixels() == 0
    # D2 and D3.
    assert new.merge.pass2_soft_ceiling is True
    assert new.clustering.fit_excludes_stands_below_min_area is True
    # D4: Sanjay Van at 10 ha with its existing settings, Odisha on the 3 ha boxes.
    ceiling = 10.0 if name.startswith("sanjay_van") else 3.0
    assert new.merge.max_area_ha == old.merge.max_area_ha == ceiling
    assert new.merge.min_area_ha == old.merge.min_area_ha == 1.0
    assert new.clustering.k == old.clustering.k
    assert new.merge.pass2_skip_at_min_area == old.merge.pass2_skip_at_min_area
    assert new.merge.pass2_skip_at_min_area is (not name.startswith("sanjay_van"))
    assert new.roi == old.roi
    # The soft ceiling widens the component cap to max + min (plus 20%), as D2 says.
    assert new.max_component_pixels() == math.ceil(math.ceil((ceiling + 1.0) * 10_000 / 100) * 1.2)
    assert new.max_component_pixels() > old.max_component_pixels()


def test_each_has_a_fingerprint_of_its_own():
    fps = {name: config_fingerprint(load_config(REPO / "configs" / f"{name}.yaml"))
           for name in SOURCES}
    assert len(set(fps.values())) == len(fps)
    for name, fp in fps.items():
        assert fp != config_fingerprint(load_config(REPO / "configs" / f"{SOURCES[name]}.yaml"))


@pytest.mark.parametrize("name", sorted(PINNED))
def test_the_fingerprint_is_the_pinned_one(name: str):
    """The reuse plan and the batch name assets by these. If one moves, the plan in
    docs/handoff/2026-10-14-round3.md is out of date: rerun its dry run before anything else."""
    assert config_fingerprint(load_config(REPO / "configs" / f"{name}.yaml")) == PINNED[name]


@pytest.mark.parametrize("name", ["sanjay_van_baseline", "sanjay_van_alphaearth"])
def test_the_sanjay_van_asset_source_has_the_same_content(name: str):
    """The Sanjay Van configs copy configs/<name>.yaml; the assets they reuse are those of
    <name>_repro, which differs from it in its name only, so it has the same fingerprint."""
    a, b = _flat(_yaml(name)), _flat(_yaml(f"{name}_repro"))
    assert {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)} == {("name",)}
