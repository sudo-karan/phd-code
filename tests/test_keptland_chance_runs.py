"""odisha_script/odisha_keptland_chance.py's --runs and --arm (round 10, 18 Oct 2026), offline.

The runs scored can be named by a pattern with {district}, as the scorer's --runs names them, so
that the AlphaEarth arm's runs can be tested; the arm's name in the seed strings is, by default,
the runs' name without "odisha_", the district and a round 9 run suffix. The default runs keep
their seeds (Q6 of the script). Short runs on the committed inputs, skipped where an off-git
stand layer is not on this machine.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "odisha_script"))
sys.path.insert(0, str(REPO / "scripts"))

pytest.importorskip("shapely")
import odisha_keptland_chance as C  # noqa: E402, N812
import odisha_keptland_score as K  # noqa: E402, N812

R9_DIR = REPO / "docs" / "reproducibility" / "r9_runs"
AE_RUNS = "odisha_alphaearth_3ha_squares_{district}_keptland_r9"


def _layers_here(pattern: str) -> bool:
    try:
        for d in K.DISTRICTS:
            K.stand_layer(pattern.format(district=d), R9_DIR)
    except SystemExit:
        return False
    return True


@pytest.mark.parametrize(("pattern", "arm"), [
    (K.RUNS, C.ARM),
    (K.RUNS + "_r9", C.ARM),
    (K.RUNS + "_r9_check", C.ARM),
    (AE_RUNS, "alphaearth_3ha_squares_keptland"),
])
def test_the_arms_seed_name_is_the_runs_name_without_the_district_and_the_run_suffix(pattern, arm):
    assert C.arm_from_runs(pattern) == arm


def test_the_runs_are_given_one_way_and_hold_the_district(tmp_path):
    with pytest.raises(SystemExit, match="not both"):
        C.run(12, tmp_path, stands_from="geojson", run_suffix="_r9", runs_pattern=AE_RUNS)
    with pytest.raises(SystemExit, match="district"):
        C.run(12, tmp_path, stands_from="geojson", runs_pattern="odisha_alphaearth_keptland_r9")
    with pytest.raises(SystemExit, match="geojson"):
        C.run(12, tmp_path, stands_from="ui_data", runs_pattern=AE_RUNS)


def test_the_runs_pattern_gives_what_the_run_suffix_gives(tmp_path):
    if not _layers_here(K.RUNS + "_r9"):
        pytest.skip("an off-git stand layer is not here")
    common = {"stands_from": "geojson", "stands_dir": R9_DIR, "scored_stem": "keptland_s1desc_r9", "declared": True}
    by_suffix = C.run(12, tmp_path / "a", run_suffix="_r9", **common)
    by_pattern = C.run(12, tmp_path / "b", runs_pattern=K.RUNS + "_r9", **common)
    assert by_pattern == by_suffix
    stem = "keptland_s1desc_r9_chance_rot12"
    for ext in (".json", ".txt"):
        assert (tmp_path / "a" / f"{stem}{ext}").read_bytes() == (tmp_path / "b" / f"{stem}{ext}").read_bytes()


def test_a_short_run_of_the_alphaearth_arm_passes_its_identity_checks_with_its_own_seeds(tmp_path):
    if not _layers_here(AE_RUNS):
        pytest.skip("an off-git stand layer is not here")
    res = C.run(12, tmp_path, stands_from="geojson", stands_dir=R9_DIR, runs_pattern=AE_RUNS,
                scored_stem="keptland_alphaearth_r9", declared=True)
    assert res["identity_checks"]["join_at_real_positions"] == "PASS" and res["null_built"]
    assert res["runs"] == [AE_RUNS.format(district=d) for d in K.DISTRICTS]
    assert res["arm_seed_name"] == "alphaearth_3ha_squares_keptland"
    assert res["seeds"]["unconditional"].startswith("alphaearth_3ha_squares_keptland/")
    assert res["seeds"]["unconditional"] != C.SEED_UNCOND and res["seeds"]["conditional"] != C.SEED_LABELLED
    assert not res["rehearsal"]
    saved = json.loads((tmp_path / "keptland_alphaearth_r9_chance_rot12.json").read_text())
    assert saved["runs"] == res["runs"]
