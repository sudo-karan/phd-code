"""Every config under configs/ keeps the cache fingerprint it had before round 3.

tests/test_repro_fingerprints.py pins the 14 `_repro` configs to the fingerprints in the names
of their saved assets. This file does the same for every other config in the repo, so that a
setting added later (round 3: merge.pass2_soft_ceiling and
clustering.fit_excludes_stands_below_min_area) is shown to leave every existing config's
cached assets where they are, not only the 14.

The values were computed from the configs at commit 12d2a05, before either setting existed:

    git show 12d2a05:<config> > /tmp/c.yaml   # for each config listed below
    python -c "from fmu.config import load_config; from fmu.utils.caching import config_fingerprint; print(config_fingerprint(load_config('/tmp/c.yaml')))"

A config added after that commit is not listed and is not checked here. If a value here stops
matching, do not update it: keep the new setting out of the fingerprint while it is at its
default (`fmu.utils.caching._OMITTED_AT_DEFAULT`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fmu.config import load_config
from fmu.utils.caching import config_fingerprint

REPO = Path(__file__).resolve().parent.parent

# config path -> fingerprint at commit 12d2a05.
PINNED = {
    "configs/odisha_alphaearth.yaml": "1116d1285e",
    "configs/odisha_alphaearth_angul.yaml": "34bffb7611",
    "configs/odisha_alphaearth_angul_repro.yaml": "34bffb7611",
    "configs/odisha_alphaearth_dhenkanal.yaml": "6e7046a5ce",
    "configs/odisha_alphaearth_dhenkanal_repro.yaml": "6e7046a5ce",
    "configs/odisha_alphaearth_kendujhar.yaml": "4c14ee1bce",
    "configs/odisha_alphaearth_kendujhar_repro.yaml": "4c14ee1bce",
    "configs/odisha_alphaearth_koraput.yaml": "f1a8cc9cfa",
    "configs/odisha_alphaearth_koraput_repro.yaml": "f1a8cc9cfa",
    "configs/odisha_current_handcrafted.yaml": "135f0c93c4",
    "configs/odisha_current_handcrafted_angul.yaml": "a365c1b068",
    "configs/odisha_current_handcrafted_dhenkanal.yaml": "d63ca3bd15",
    "configs/odisha_current_handcrafted_kendujhar.yaml": "ac534a918a",
    "configs/odisha_current_handcrafted_koraput.yaml": "78580aea3f",
    "configs/odisha_v120_3ha_angul.yaml": "8c472d39f9",
    "configs/odisha_v120_3ha_angul_repro.yaml": "8c472d39f9",
    "configs/odisha_v120_3ha_dhenkanal.yaml": "a516a24b2d",
    "configs/odisha_v120_3ha_dhenkanal_repro.yaml": "a516a24b2d",
    "configs/odisha_v120_3ha_kendujhar.yaml": "9908a3bb6b",
    "configs/odisha_v120_3ha_kendujhar_repro.yaml": "9908a3bb6b",
    "configs/odisha_v120_3ha_koraput.yaml": "030aafaa2c",
    "configs/odisha_v120_3ha_koraput_repro.yaml": "030aafaa2c",
    "configs/odisha_v120_3ha_squares_angul.yaml": "d56b757ed6",
    "configs/odisha_v120_3ha_squares_dhenkanal.yaml": "3c7332fe61",
    "configs/odisha_v120_3ha_squares_kendujhar.yaml": "2a2e6e38e3",
    "configs/odisha_v120_3ha_squares_koraput.yaml": "39026bfa4e",
    "configs/odisha_v120_handcrafted.yaml": "0b6c3a50c5",
    "configs/odisha_v120_handcrafted_angul.yaml": "d6096dce2e",
    "configs/odisha_v120_handcrafted_angul_repro.yaml": "d6096dce2e",
    "configs/odisha_v120_handcrafted_dhenkanal.yaml": "57b7c569b3",
    "configs/odisha_v120_handcrafted_dhenkanal_repro.yaml": "57b7c569b3",
    "configs/odisha_v120_handcrafted_kendujhar.yaml": "5bf920bc83",
    "configs/odisha_v120_handcrafted_kendujhar_repro.yaml": "5bf920bc83",
    "configs/odisha_v120_handcrafted_koraput.yaml": "4bdfadbe7c",
    "configs/odisha_v120_handcrafted_koraput_repro.yaml": "4bdfadbe7c",
    "configs/sanjay_van_alphaearth.yaml": "105fc40547",
    "configs/sanjay_van_alphaearth_repro.yaml": "105fc40547",
    "configs/sanjay_van_baseline.yaml": "7f642cf2ca",
    "configs/sanjay_van_baseline_repro.yaml": "7f642cf2ca",
    "configs/sanjay_van_nirv_dual.yaml": "d8f55a1bf4",
    "configs/sanjay_van_tessera.yaml": "46cf4b793f",
    "configs/experiments/gate_effect_arm_a.yaml": "bbc3e3d624",
    "configs/experiments/gate_effect_arm_b.yaml": "d73692c66f",
    "configs/experiments/gate_effect_arm_c.yaml": "7f642cf2ca",
}


def test_every_config_of_that_commit_is_pinned():
    """A config of 12d2a05 missing here would go unchecked, so the list is checked too."""
    on_disk = {
        str(p.relative_to(REPO))
        for p in [*REPO.glob("configs/*.yaml"), *REPO.glob("configs/experiments/*.yaml")]
    }
    assert set(PINNED) <= on_disk, sorted(set(PINNED) - on_disk)


@pytest.mark.parametrize("path", sorted(PINNED))
def test_a_config_keeps_its_fingerprint(path: str):
    got = config_fingerprint(load_config(REPO / path))
    assert got == PINNED[path], (
        f"{path}: fingerprint {got}, was {PINNED[path]} at 12d2a05, so its cached assets can "
        "no longer be found by name. A new setting must stay out of the fingerprint while it "
        "is at its default."
    )


@pytest.mark.parametrize(
    ("record", "kind"),
    [("docs/demo/demo_set.json", "_repro runs"), ("docs/demo/demo_set_boxes.json", "box runs")],
)
def test_the_pinned_value_of_a_recorded_run_is_its_assets_fingerprint(record: str, kind: str):
    """For the runs the demo records list, the pinned value is also the fingerprint in the names
    of the assets the run saved (read with ee.data.listAssets when the record was made)."""
    runs = json.loads((REPO / record).read_text())["runs"]
    assert runs, f"{record} lists no {kind}"
    for run in runs:
        assert PINNED[run["config"]] == run["fingerprint"], run["run_id"]
        for asset in run["assets"]:
            assert asset["asset"].endswith(f"__{run['fingerprint']}"), asset["asset"]
