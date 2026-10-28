"""odisha_script/r14_sanjay_van_description.py, offline: Sanjay Van's stand counts, sizes, k and the
types' shares.

A small run record, export manifest and merged layer are written to a temporary folder; the
description must give k, the counts, the sizes and each type's shares from them, count a stand split
into pieces once, give a type with no pixel 0 ha, keep to the declared numbers, read a layer off git
only when its record names it with its SHA-256, and refuse to write over a file that exists. No real
run is read.
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

# (polygon id, stand label, type): stand 5 is split into two pieces; type 3 has no stand and no pixel.
POLYGONS = ((1, 2, 2), (2, 3, 0), (3, 4, 1), (4, 5, 1), (5, 5, 1))


def _write_run(records: Path, run: str, *, off_git: Path | None = None, polygons=POLYGONS) -> None:
    areas = {"1": 0.0, "2": 0.5, "3": 2.0, "4": 4.0, "5": 9.5}
    run_record = {"merge_diagnostics": {"n_stands": 5, "n_superpixels": 12, "stands_below_min_area": 2,
                                        "orphans_isolated": 2, "orphans_area_blocked": 0, "stands_over_max_area": 0},
                  "stand_attributes": {s: {"area_ha": a, "n_pixels": int(a * 100)} for s, a in areas.items()}}
    manifest = {"config": {"merge": {"min_area_ha": 1.0, "max_area_ha": 10.0}},
                "stages": [{"name": "export", "metadata": {"manifest": {"clustering": {
                    "k": 4, "feature_source": "embedding", "n_stands_left_out_of_fit": 2,
                    "area_ha_in_stands_left_out_of_fit": 0.5,
                    "cluster_distribution": [{"cluster_id": 0, "area_ha": 2.0, "percent_of_habitat": 12.5},
                                             {"cluster_id": 1, "area_ha": 13.5, "percent_of_habitat": 84.4},
                                             {"cluster_id": 2, "area_ha": 0.5, "percent_of_habitat": 3.1}]}}}}]}
    layer = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": None, "properties": {"stand_id": i, "stand_lbl": s, "cluster_id": t}}
        for i, s, t in polygons]}
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
    assert r["arm"] == "AlphaEarth" and r["k"] == 4
    c = r["counts"]
    assert c["stands"] == 5 and c["stands_with_no_pixel"] == 1
    # The split stand 5 is one stand of two polygons; stand 1 has no polygon.
    assert (c["stands_in_merged_layer"], c["stand_polygons_in_merged_layer"]) == (4, 5)
    assert c["stands_split_into_pieces"] == 1 and c["stands_of_the_merge_with_no_polygon"] == 1
    assert r["sizes_all_stands"]["stands"] == 5 and r["sizes_all_stands"]["p50_ha"] == 2.0
    assert r["sizes_all_stands"]["total_ha"] == 16.0
    assert r["sizes_at_or_above_min_area"]["stands"] == 3
    assert r["sizes_at_or_above_min_area"]["smallest_ha"] == 2.0
    assert [(t["type"], t["stands"], t["share_of_stands_percent"]) for t in r["types"]] == [
        (0, 1, 25.0), (1, 2, 50.0), (2, 1, 25.0), (3, 0, 0.0)]
    # Type 3 is not in the distribution: no pixel, 0 ha and 0 %.
    assert [(t["area_ha"], t["share_of_habitat_percent"]) for t in r["types"]] == [
        (2.0, 12.5), (13.5, 84.4), (0.5, 3.1), (0.0, 0.0)]
    md = (out / "d.md").read_text()
    assert "| k | 4 |" in md and "AlphaEarth (R3)" in md and "n/a" not in md
    run = json.loads((out / "d_run.json").read_text())
    assert set(run["inputs_sha256"]) == {"sv_r14_run.json", "sv_r14_manifest_export.json",
                                         "sv_r14_stands_merged.geojson"}
    with pytest.raises(SystemExit, match="refusing to write over"):
        S.main(["--records", str(tmp_path), "--runs", "sv_r14", "--beside-runs",
                "--out-dir", str(out), "--stem", "d"])


def test_only_the_declared_counts(tmp_path: Path):
    """Stand counts, sizes, k and the types' shares only: describe()'s superpixels, kept land and
    each stand's excess are left out."""
    _write_run(tmp_path, "sv_r14")
    out = tmp_path / "out"
    S.main(["--records", str(tmp_path), "--runs", "sv_r14", "--beside-runs", "--out-dir", str(out), "--stem", "d"])
    r = json.loads((out / "d.json").read_text())["runs"]["sv_r14"]
    assert set(r) == {"arm", "k", "counts", "sizes_all_stands", "sizes_at_or_above_min_area", "types"}
    assert set(r["counts"]) == set(S.DESCRIBE_COUNTS) | {
        "stands_in_merged_layer", "stand_polygons_in_merged_layer", "stands_split_into_pieces",
        "stands_of_the_merge_with_no_polygon", "stands_in_merged_layer_without_a_type"}
    assert not any("superpixel" in key or "kept_land" in key or "excess" in key for key in r["counts"])


def test_a_stand_whose_pieces_carry_two_types_stops_it(tmp_path: Path):
    _write_run(tmp_path, "sv_r14", polygons=((1, 2, 2), (2, 5, 0), (3, 5, 1)))
    with pytest.raises(SystemExit, match="two types"):
        S.main(["--records", str(tmp_path), "--runs", "sv_r14", "--beside-runs",
                "--out-dir", str(tmp_path / "out"), "--stem", "d"])


def test_a_layer_off_git_is_read_only_when_its_record_names_it_with_its_sha256(tmp_path: Path):
    off = tmp_path / "off.geojson"
    _write_run(tmp_path, "sv_r14", off_git=off)
    assert S.stand_layer("sv_r14", tmp_path) == off
    off.write_text(off.read_text() + " ")
    with pytest.raises(SystemExit, match="SHA-256 differs"):
        S.stand_layer("sv_r14", tmp_path)
    (tmp_path / "sv_r14_files_off_git.json").write_text(json.dumps({"files": [
        {"file": "sv_r14_stands_snic.geojson", "where": str(off), "sha256": "0"}]}))
    with pytest.raises(SystemExit, match="does not name"):
        S.stand_layer("sv_r14", tmp_path)


def test_a_type_outside_k_stops_it():
    manifest = {"config": {"merge": {"min_area_ha": 1.0}}, "stages": [{"name": "export", "metadata": {
        "manifest": {"clustering": {"k": 2, "cluster_distribution": [{"cluster_id": 0}]}}}}]}
    layer = {"features": [{"properties": {"stand_lbl": 1, "cluster_id": 2}}]}
    with pytest.raises(SystemExit, match="types outside"):
        S.describe_run({"stand_attributes": {}}, manifest, layer, lambda run, manifest: {})
