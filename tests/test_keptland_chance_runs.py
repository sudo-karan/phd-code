"""odisha_script/odisha_keptland_chance.py's --runs and --arm (round 10, 18 Oct 2026), offline.

The runs scored can be named by a pattern with {district}, as the scorer's --runs names them, so
that the AlphaEarth arm's runs can be tested; the arm's name in the seed strings is, by default,
the runs' name without "odisha_", the district and its run suffixes. The default runs keep
their seeds (Q6 of the script). Short runs on the committed inputs, skipped where an off-git
stand layer is not on this machine.
"""

from __future__ import annotations

import json
import shlex
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "odisha_script"))
sys.path.insert(0, str(REPO / "scripts"))

pytest.importorskip("shapely")
import odisha_keptland_chance as C  # noqa: E402, N812
import odisha_keptland_score as K  # noqa: E402, N812
import odisha_phase3_3_significance as G  # noqa: E402, N812

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
    # Review of 19 Oct 2026, B22: a _repro copy (CLAUDE.md's from-scratch recipe) is seeded as its source.
    (K.RUNS + "_repro", C.ARM),
    (K.RUNS + "_r9_repro", C.ARM),
    (AE_RUNS + "_repro", "alphaearth_3ha_squares_keptland"),
    ("odisha_v120_10ha_squares_{district}_keptland_s1desc_r9_repro", "v120_10ha_squares_keptland_s1desc"),
    ("odisha_alphaearth_10ha_squares_{district}_keptland_r9_repro", "alphaearth_10ha_squares_keptland"),
    # A check of the B22 fix (round 13): a later round's suffix, and a numbered _repro copy, too.
    (K.RUNS + "_r13", C.ARM),
    (K.RUNS + "_r13_check", C.ARM),
    (K.RUNS + "_r9_repro2", C.ARM),
    (K.RUNS + "_repro2", C.ARM),
    (AE_RUNS.replace("_r9", "_r14"), "alphaearth_3ha_squares_keptland"),
    ("odisha_v120_10ha_squares_{district}_keptland_s1desc_r13", "v120_10ha_squares_keptland_s1desc"),
])
def test_the_arms_seed_name_is_the_runs_name_without_the_district_and_the_run_suffix(pattern, arm):
    assert C.arm_from_runs(pattern) == arm


def _recorded_arm_options(command_line: str) -> dict[str, str]:
    words = shlex.split(command_line)
    return {w: words[i + 1] for i, w in enumerate(words) if w in ("--runs", "--run-suffix", "--arm")}


@pytest.mark.parametrize("record", sorted((REPO / "odisha_script" / "keptland_scores").glob("*_chance*_run.json")),
                         ids=lambda p: p.name)
def test_every_committed_chance_result_keeps_its_seed_name_from_its_recorded_command(record):
    """B22's fix must leave every committed chance result as its recorded command draws it: the
    seed name the command gives today is the one its result file records."""
    rec = json.loads(record.read_text())
    opts = _recorded_arm_options(rec["command_line"])
    pattern = opts.get("--runs", K.RUNS + opts.get("--run-suffix", ""))
    arm = opts.get("--arm", C.arm_from_runs(pattern))
    result = json.loads((record.parent / rec["result_files"][1]).read_text())
    assert arm == result["arm_seed_name"]
    assert result["seeds"]["unconditional"] == G.SEED_UNCOND.format(arm=arm)


def test_a_repro_copy_of_a_scored_run_draws_the_same_placements_as_its_source(tmp_path):
    """B22: the _r9 stands copied under _r9_repro names (byte-identical layers) give the same
    result file, the run names aside, so a from-scratch re-run's p moves only if its stands do."""
    if not _layers_here(K.RUNS + "_r9"):
        pytest.skip("an off-git stand layer is not here")
    copies = tmp_path / "stands"
    copies.mkdir()
    for d in K.DISTRICTS:
        src = K.stand_layer(K.run_id(d, K.RUNS + "_r9"), R9_DIR)
        shutil.copyfile(src, copies / f"{K.run_id(d, K.RUNS + '_r9_repro')}_stands_merged.geojson")
    common = {"stands_from": "geojson", "scored_stem": "keptland_s1desc_r9", "declared": True}
    source = C.run(12, tmp_path / "a", runs_pattern=K.RUNS + "_r9", stands_dir=R9_DIR, **common)
    repro = C.run(12, tmp_path / "b", runs_pattern=K.RUNS + "_r9_repro", stands_dir=copies, **common)
    assert repro["seeds"] == source["seeds"]
    stem = "keptland_s1desc_r9_chance_rot12"
    for ext in (".json", ".txt"):
        a = (tmp_path / "a" / f"{stem}{ext}").read_text()
        b = (tmp_path / "b" / f"{stem}{ext}").read_text()
        assert b.replace("_r9_repro", "_r9") == a


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
