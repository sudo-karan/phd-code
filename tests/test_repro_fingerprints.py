"""The 14 `_repro` configs must keep the cache fingerprint of their saved assets.

The 14 re-runs of 13 October 2026 (PR #42) are the demo data, and the evidence
for that PR. Their Earth Engine assets live at
`{asset_root}/{config_name}/{stage}/{key}__{fingerprint}`, and the fingerprint
is a hash over the config's cache-relevant blocks, defaults included. So adding
any field with a default to one of those blocks changes all 14 fingerprints at
once, and the saved assets can no longer be found by name.

If a test here fails, do not update the pinned values. Change the code so that
the new setting stays out of the fingerprint while it is at its default (a
config that switches it on then gets a new fingerprint, which is correct).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from fmu.config import load_config
from fmu.utils.caching import config_fingerprint

REPO_ROOT = Path(__file__).parent.parent
CONFIG_DIR = REPO_ROOT / "configs"

# config name -> the fingerprint in the names of the assets its run saved.
PINNED = {
    "odisha_alphaearth_angul_repro": "34bffb7611",
    "odisha_alphaearth_dhenkanal_repro": "6e7046a5ce",
    "odisha_alphaearth_kendujhar_repro": "4c14ee1bce",
    "odisha_alphaearth_koraput_repro": "f1a8cc9cfa",
    "odisha_v120_3ha_angul_repro": "8c472d39f9",
    "odisha_v120_3ha_dhenkanal_repro": "a516a24b2d",
    "odisha_v120_3ha_kendujhar_repro": "9908a3bb6b",
    "odisha_v120_3ha_koraput_repro": "030aafaa2c",
    "odisha_v120_handcrafted_angul_repro": "d6096dce2e",
    "odisha_v120_handcrafted_dhenkanal_repro": "57b7c569b3",
    "odisha_v120_handcrafted_kendujhar_repro": "5bf920bc83",
    "odisha_v120_handcrafted_koraput_repro": "4bdfadbe7c",
    "sanjay_van_alphaearth_repro": "105fc40547",
    "sanjay_van_baseline_repro": "7f642cf2ca",
}


def test_the_fourteen_repro_configs_are_the_pinned_ones():
    on_disk = {p.stem for p in CONFIG_DIR.glob("*_repro.yaml")}
    assert on_disk == set(PINNED), {
        "not pinned": sorted(on_disk - set(PINNED)),
        "pinned but gone": sorted(set(PINNED) - on_disk),
    }


@pytest.mark.parametrize("name", sorted(PINNED))
def test_a_repro_config_still_hashes_to_the_fingerprint_of_its_saved_assets(name: str):
    cfg = load_config(CONFIG_DIR / f"{name}.yaml")
    assert cfg.name == name
    assert config_fingerprint(cfg) == PINNED[name], (
        f"{name}: the fingerprint changed, so its saved assets can no longer be found. "
        "A new config field must stay out of the fingerprint while it is at its default."
    )


@pytest.mark.parametrize("name", sorted(PINNED))
def test_the_pinned_value_is_the_one_in_the_saved_asset_path(name: str):
    """The pinned values are not taken from the configs: each is the fingerprint in the name of
    an asset the run saved, as recorded when that asset was read (PR #42)."""
    record = REPO_ROOT / "docs" / "reproducibility" / f"snic_cached_vs_live_{name[: -len('_repro')]}.json"
    own = [c["asset"] for c in json.loads(record.read_text())["comparisons"] if c["against"] == name]
    assert own, f"{record.name} holds no comparison against {name}"
    found = re.search(rf"/{name}/segmentation/snic_clusters__([0-9a-f]+)$", own[0])
    assert found and found.group(1) == PINNED[name], own[0]
