"""odisha_script/r14_sanjay_van_description.py, offline: Sanjay Van's stand counts, sizes, k and the
types' shares.

A small run record, export manifest and merged layer are written to a temporary folder; the
description must give k, the counts, the sizes and each type's shares from them, read a layer off git
only when its SHA-256 is the record's, and refuse to write over a file that exists. No real run is
read.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "odisha_script"))

import r14_sanjay_van_description as S  # noqa: E402, N812


def _write_run(records: Path, run: str, *, off_git: Path | None = None) -> None:
    areas = {"1": 0.0, "2": 0.5, "3": 2.0, "4": 4.0, "5": 9.5}
    run_record = {"merge_diagnostics": {"n_stands": 5, "n_superpixels": 12, "stands_below_min_area": 2,
                                        "orphans_isolated": 2, "orphans_area_blocked": 0, "stands_over_max_area": 0},
                  "stand_attributes": {s: {"area_ha": a, "n_pixels": int(a * 100)} for s, a in areas.items()}}
    manifest = {"config": {"merge": {"min_area_ha": 1.0, "max_area_ha": 10.0}},
                "stages": [{"name": "export", "metadata": {"manifest": {"clustering": {
                    "k": 3, "feature_source": "embedding", "n_stands_left_out_of_fit": 2,
                    "area_ha_in_stands_left_out_of_fit": 0.5,
                    "cluster_distribution": [{"cluster_id": 0, "area_ha": 2.0, "percent_of_habitat": 12.5},
                                             {"cluster_id": 1, "area_ha": 13.5, "percent_of_habitat": 84.4},
                                             {"cluster_id": 2, "area_ha": 0.5, "percent_of_habitat": 3.1}]}}}}]}
    layer = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": None, "properties": {"stand_id": s, "cluster_id": t}}
        for s, t in ((2, 2), (3, 0), (4, 1), (5, 1))]}
    (records / f"{run}_run.json").write_text(json.dumps(run_record))
    (records / f"{run}_manifest_export.json").write_text(json.dumps(manifest))
    if off_git is None:
        (records / f"{run}_stands_merged.geojson").write_text(json.dumps(layer))
    else:
        off_git.write_text(json.dumps(layer))
        digest = hashlib.sha256(off_git.read_bytes()).hexdigest()
        (records / f"{run}_files_off_git.json").write_text(json.dumps({"files": [
            {"file": f"{run}_stands_merged.geojson", "where": str(off_git), "sha256": digest}]}))


def test_the_numbers_of_a_run(tmp_path: Path):
    _write_run(tmp_path, "sv_r14")
    out = tmp_path / "out"
    assert S.main(["--records", str(tmp_path), "--runs", "sv_r14", "--beside-runs",
                   "--out-dir", str(out), "--stem", "d"]) == 0
    r = json.loads((out / "d.json").read_text())["runs"]["sv_r14"]
    assert r["arm"] == "AlphaEarth" and r["k"] == 3
    assert r["counts"]["stands"] == 5 and r["counts"]["superpixels"] == 12
    assert r["counts"]["stand_polygons_in_merged_layer"] == 4 and r["counts"]["stands_with_no_pixel"] == 1
    assert r["sizes_all_stands"]["stands"] == 5 and r["sizes_all_stands"]["p50_ha"] == 2.0
    assert r["sizes_all_stands"]["total_ha"] == 16.0
    assert r["sizes_at_or_above_min_area"]["stands"] == 3
    assert r["sizes_at_or_above_min_area"]["smallest_ha"] == 2.0
    assert [(t["type"], t["stands"], t["share_of_stands"]) for t in r["types"]] == [
        (0, 1, 0.25), (1, 2, 0.5), (2, 1, 0.25)]
    assert [t["share_of_habitat_percent"] for t in r["types"]] == [12.5, 84.4, 3.1]
    md = (out / "d.md").read_text()
    assert "| k | 3 |" in md and "AlphaEarth (R3)" in md
    run = json.loads((out / "d_run.json").read_text())
    assert set(run["inputs_sha256"]) == {"sv_r14_run.json", "sv_r14_manifest_export.json",
                                         "sv_r14_stands_merged.geojson"}
    with pytest.raises(SystemExit, match="refusing to write over"):
        S.main(["--records", str(tmp_path), "--runs", "sv_r14", "--beside-runs",
                "--out-dir", str(out), "--stem", "d"])


def test_a_layer_off_git_is_read_only_when_its_sha256_is_the_records(tmp_path: Path):
    off = tmp_path / "off.geojson"
    _write_run(tmp_path, "sv_r14", off_git=off)
    assert S.stand_layer("sv_r14", tmp_path) == off
    off.write_text(off.read_text() + " ")
    with pytest.raises(SystemExit, match="SHA-256 differs"):
        S.stand_layer("sv_r14", tmp_path)


def test_a_type_outside_k_stops_it():
    manifest = {"config": {"merge": {"min_area_ha": 1.0}}, "stages": [{"name": "export", "metadata": {
        "manifest": {"clustering": {"k": 2, "cluster_distribution": []}}}}]}
    layer = {"features": [{"properties": {"cluster_id": 2}}]}
    with pytest.raises(SystemExit, match="types outside"):
        S.describe_run({"stand_attributes": {}}, manifest, layer, lambda run, manifest: {})
