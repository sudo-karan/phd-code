"""scripts/compare_stand_runs.py on hand-built squares, where the answer is obvious.

Offline and fast: no Earth Engine, no files beyond a temporary folder.

The squares sit at latitude 20 and are 0.001 degrees on a side (about 105 m by 111 m). Stands
are shifted or split along longitude only, so the expected ratios (1/2, 1/3, 2/3) hold to
many decimal places in the equal-area projection the tool measures in.
"""

from __future__ import annotations

import importlib.util
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "compare_stand_runs.py"

LON0, LAT0, S = 85.0, 20.0, 0.001


def _load():
    spec = importlib.util.spec_from_file_location("compare_stand_runs", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # the dataclasses in the script look their module up by name
    spec.loader.exec_module(mod)
    return mod


csr = _load()


def ring(col: float, row: float, w: float = 1.0, h: float = 1.0) -> list[list[float]]:
    """A closed ring: a rectangle w by h squares with its lower-left corner at (col, row)."""
    x0, y0 = LON0 + col * S, LAT0 + row * S
    y1 = y0 + h * S
    # a vertex at every square corner along the long sides, as a raster-derived outline has.
    # Without them the long edge is one straight line where two squares have two, and the
    # "same" ground differs by a millionth: enough to move an IoU of exactly 0.5 off 0.5.
    xs = [LON0 + (col + k) * S for k in range(int(w))] + [x0 + w * S]
    xs[0] = x0
    return [[x, y0] for x in xs] + [[x, y1] for x in reversed(xs)] + [[x0, y0]]


def feat(sid, *rings_, cluster=None, id_field="stand_lbl") -> dict:
    """One feature: a Polygon for one ring, a MultiPolygon for several."""
    if len(rings_) == 1:
        geom = {"type": "Polygon", "coordinates": [rings_[0]]}
    else:
        geom = {"type": "MultiPolygon", "coordinates": [[r] for r in rings_]}
    props = {id_field: sid}
    if cluster is not None:
        props["cluster_id"] = cluster
    return {"type": "Feature", "properties": props, "geometry": geom}


def compare(old: list[dict], new: list[dict], type_field: str | None = None, **kw) -> dict:
    lo = csr.layer_from_features(old, type_field=type_field, name="old", **kw)
    ln = csr.layer_from_features(new, type_field=type_field, name="new", **kw)
    return csr.compare_layers(lo, ln)


def square_ha() -> float:
    """Area of one S by S square at LAT0 from the WGS84 ellipsoid's radii of curvature,
    worked out here without pyproj so that it checks the tool rather than repeats it."""
    a, f = 6378137.0, 1 / 298.257223563
    e2 = f * (2 - f)
    phi = math.radians(LAT0 + S / 2)
    w = math.sqrt(1 - e2 * math.sin(phi) ** 2)
    m_per_deg_lat = math.radians(1) * a * (1 - e2) / w**3
    m_per_deg_lon = math.radians(1) * a * math.cos(phi) / w
    return (S * m_per_deg_lat) * (S * m_per_deg_lon) / 10_000


GRID4 = [feat(1, ring(0, 0)), feat(2, ring(1, 0)), feat(3, ring(0, 1)), feat(4, ring(1, 1))]


# --------------------------------------------------------------------------- areas
def test_area_is_true_area_not_square_degrees():
    res = compare([feat(1, ring(0, 0))], [feat(1, ring(0, 0))])
    expected = square_ha()
    # about 105 m by 111 m: 1.158 ha. A square-degree "area" would be 1e-6.
    assert expected == pytest.approx(1.1585, abs=5e-4)
    assert res["old"]["stand_area_ha"] == pytest.approx(expected, rel=1e-6)
    assert res["new"]["footprint_ha"] == pytest.approx(expected, rel=1e-6)


def test_area_at_another_latitude_is_smaller_by_the_cosine():
    # the same square in degrees covers less ground further from the equator
    far = [{"type": "Feature", "properties": {"stand_lbl": 1}, "geometry": {
        "type": "Polygon",
        "coordinates": [[[10.0, 60.0], [10.001, 60.0], [10.001, 60.001], [10.0, 60.001], [10.0, 60.0]]]}}]
    res = compare(far, far)
    assert res["old"]["stand_area_ha"] == pytest.approx(0.6210, abs=2e-3)
    assert res["old"]["stand_area_ha"] < 0.6 * square_ha()


# --------------------------------------------------------------------------- identical
def test_identical_layers_give_one_and_every_outline_matched():
    res = compare(GRID4, GRID4)
    assert res["old"]["n_stands"] == res["new"]["n_stands"] == 4
    assert res["old"]["n_polygons"] == 4
    assert res["same_outline_stands"] == res["same_outline_stands_new"] == 4
    assert res["same_outline_same_id"] == 4
    assert res["same_outline_polygons"] == 4
    for d in ("old_to_new", "new_to_old"):
        assert res[d]["area_weighted_iou"] == pytest.approx(1.0, abs=1e-12)
        assert res[d]["min_iou"] == pytest.approx(1.0, abs=1e-12)
        assert res[d]["share_area_iou_ge"][0.99] == pytest.approx(1.0)
        assert res[d]["n_no_overlap"] == 0
    assert res["footprint_iou"] == pytest.approx(1.0, abs=1e-12)
    assert res["common_footprint_ha"] == pytest.approx(4 * square_ha(), rel=1e-4)
    assert csr.is_identical(res)


def test_feature_order_ring_start_and_renumbering_do_not_hide_a_match():
    # same four squares: features reversed, each ring started at another vertex, ids renumbered
    def rotated(r):
        body = r[:-1]
        body = body[2:] + body[:2]
        return body + [body[0]]

    new = [feat(10 + f["properties"]["stand_lbl"], rotated(f["geometry"]["coordinates"][0]))
           for f in reversed(GRID4)]
    res = compare(GRID4, new)
    assert res["same_outline_stands"] == 4
    assert res["same_outline_same_id"] == 0  # the outlines match although no id does
    assert res["ids_in_both"] == 0
    assert res["old_to_new"]["area_weighted_iou"] == pytest.approx(1.0, abs=1e-12)
    assert csr.is_identical(res)


def test_a_difference_below_the_grid_is_the_same_outline_and_one_above_is_not():
    moved = json.loads(json.dumps(GRID4))
    moved[0]["geometry"]["coordinates"][0][0][0] += 2e-9  # 0.2 mm
    moved[0]["geometry"]["coordinates"][0][4][0] += 2e-9
    assert compare(GRID4, moved)["same_outline_stands"] == 4
    moved[0]["geometry"]["coordinates"][0][0][0] -= 5e-6  # half a metre
    moved[0]["geometry"]["coordinates"][0][4][0] -= 5e-6
    res = compare(GRID4, moved)
    assert res["same_outline_stands"] == 3
    assert not csr.is_identical(res)
    assert res["old_to_new"]["min_iou"] > 0.99


# --------------------------------------------------------------------------- differences
def test_layer_shifted_by_half_a_stand():
    old = [feat(i + 1, ring(i, 0)) for i in range(4)]
    new = [feat(i + 1, ring(i + 0.5, 0)) for i in range(4)]
    res = compare(old, new)
    # every stand shares half its area with its best match: 0.5 / (1 + 1 - 0.5) = 1/3
    for d in ("old_to_new", "new_to_old"):
        assert res[d]["area_weighted_iou"] == pytest.approx(1 / 3, abs=1e-6)
        assert res[d]["min_iou"] == pytest.approx(1 / 3, abs=1e-6)
        assert res[d]["share_area_iou_ge"][0.5] == 0.0
        assert res[d]["n_no_overlap"] == 0
    assert res["same_outline_stands"] == 0
    assert res["common_footprint_ha"] == pytest.approx(3.5 * square_ha(), rel=1e-4)
    assert res["footprint_iou"] == pytest.approx(3.5 / 4.5, abs=1e-6)
    assert not csr.is_identical(res)


def test_one_stand_split_in_two():
    old = [feat(1, ring(0, 0, w=2)), feat(2, ring(2, 0))]
    new = [feat(1, ring(0, 0)), feat(2, ring(1, 0)), feat(3, ring(2, 0))]
    res = compare(old, new)
    f, b = res["old_to_new"], res["new_to_old"]
    assert (res["old"]["n_stands"], res["new"]["n_stands"]) == (2, 3)
    # old: the double stand scores 0.5 and has weight 2, the untouched one scores 1
    assert f["area_weighted_iou"] == pytest.approx((2 * 0.5 + 1) / 3, abs=1e-6)
    # new: the two halves score 0.5 each, the untouched one scores 1
    assert b["area_weighted_iou"] == pytest.approx((0.5 + 0.5 + 1) / 3, abs=1e-6)
    assert f["share_area_iou_ge"][0.5] == pytest.approx(1.0)
    assert f["share_area_iou_ge"][0.9] == pytest.approx(1 / 3, abs=1e-6)
    assert b["share_area_iou_ge"][0.9] == pytest.approx(1 / 3, abs=1e-6)
    assert res["same_outline_stands"] == 1
    assert b["n_shared_best_match"] == 1  # one old stand is the best match of two new stands
    assert f["n_shared_best_match"] == 0
    assert res["footprint_iou"] == pytest.approx(1.0, abs=1e-9)  # the same ground, cut differently


def test_two_stands_merged_into_one():
    old = [feat(1, ring(0, 0)), feat(2, ring(1, 0)), feat(3, ring(2, 0))]
    new = [feat(7, ring(0, 0, w=2)), feat(3, ring(2, 0))]
    res = compare(old, new)
    f, b = res["old_to_new"], res["new_to_old"]
    assert (res["old"]["n_stands"], res["new"]["n_stands"]) == (3, 2)
    assert f["area_weighted_iou"] == pytest.approx(2 / 3, abs=1e-6)
    assert b["area_weighted_iou"] == pytest.approx(2 / 3, abs=1e-6)
    assert f["n_shared_best_match"] == 1  # one new stand is the best match of two old stands
    assert b["n_shared_best_match"] == 0
    assert f["n_stands_iou_ge"][0.9] == 1


def test_a_stand_made_of_two_pieces_is_one_stand():
    # Earth Engine writes one polygon per connected piece, both carrying the stand's id
    old = [feat(5, ring(0, 0)), feat(5, ring(3, 0)), feat(6, ring(1, 0))]
    as_multi = [feat(5, ring(0, 0), ring(3, 0)), feat(6, ring(1, 0))]
    res = compare(old, as_multi)
    assert (res["old"]["n_polygons"], res["new"]["n_polygons"]) == (3, 2)
    assert res["old"]["n_stands"] == res["new"]["n_stands"] == 2
    assert res["old"]["n_multi_piece_stands"] == 1
    assert res["same_outline_stands"] == 2  # the dissolved stand matches the MultiPolygon
    assert res["old_to_new"]["area_weighted_iou"] == pytest.approx(1.0, abs=1e-12)
    assert res["old"]["stand_area_ha"] == pytest.approx(3 * square_ha(), rel=1e-4)
    # how a stand is packaged into features is not a difference between the stands
    assert csr.is_identical(res)

    # the same pieces under two ids in the new layer: the old stand is now half of itself
    apart = [feat(5, ring(0, 0)), feat(8, ring(3, 0)), feat(6, ring(1, 0))]
    res = compare(old, apart)
    assert res["new"]["n_stands"] == 3
    assert res["old_to_new"]["area_weighted_iou"] == pytest.approx((2 * 0.5 + 1) / 3, abs=1e-6)
    assert res["same_outline_polygons"] == 3  # every polygon is still there
    assert res["same_outline_stands"] == 1  # but only one stand is


def test_a_stand_missing_from_the_new_layer():
    old = [feat(1, ring(0, 0)), feat(2, ring(5, 0))]
    new = [feat(1, ring(0, 0))]
    res = compare(old, new)
    f, b = res["old_to_new"], res["new_to_old"]
    assert f["n_no_overlap"] == 1
    assert f["area_no_overlap_ha"] == pytest.approx(square_ha(), rel=1e-4)
    assert f["area_weighted_iou"] == pytest.approx(0.5, abs=1e-6)
    assert f["min_iou"] == 0.0
    assert b["area_weighted_iou"] == pytest.approx(1.0, abs=1e-12)
    assert b["n_no_overlap"] == 0
    assert res["ids_only_old"] == 1
    assert res["footprint_iou"] == pytest.approx(0.5, abs=1e-6)
    rows = {r["stand_id"]: r for r in res["per_stand"]["old"]}
    assert rows[2]["best_match_id"] is None and rows[2]["iou"] == 0.0
    assert rows[1]["best_match_id"] == 1 and rows[1]["iou"] == pytest.approx(1.0)


def test_layers_that_do_not_touch_at_all():
    res = compare([feat(1, ring(0, 0))], [feat(1, ring(50, 0))])
    assert res["old_to_new"]["area_weighted_iou"] == 0.0
    assert res["new_to_old"]["n_no_overlap"] == 1
    assert res["common_footprint_ha"] == 0.0
    assert "n/a" not in "\n".join(csr.format_report(res)).split("INTERSECTION")[1].split("stands with")[0]


def test_stands_that_only_share_an_edge_do_not_count_as_overlapping():
    res = compare([feat(1, ring(0, 0))], [feat(1, ring(1, 0))])
    assert res["old_to_new"]["n_no_overlap"] == 1
    assert res["old_to_new"]["area_weighted_iou"] == 0.0


# --------------------------------------------------------------------------- awkward input
def test_invalid_and_self_touching_polygons_are_repaired_not_fatal():
    x, y = LON0, LAT0
    bowtie = {"type": "Feature", "properties": {"stand_lbl": 1}, "geometry": {
        "type": "Polygon",
        "coordinates": [[[x, y], [x + S, y + S], [x + S, y], [x, y + S], [x, y]]]}}
    # a ring that touches itself at one vertex: two squares meeting corner to corner
    touching = {"type": "Feature", "properties": {"stand_lbl": 2}, "geometry": {
        "type": "Polygon",
        "coordinates": [[[x + 2 * S, y], [x + 3 * S, y], [x + 3 * S, y + S], [x + 4 * S, y + S],
                         [x + 4 * S, y + 2 * S], [x + 3 * S, y + 2 * S], [x + 3 * S, y + S],
                         [x + 2 * S, y + S], [x + 2 * S, y]]]}}
    res = compare([bowtie, touching], [bowtie, touching])
    assert res["old"]["n_repaired"] == 2
    assert res["old"]["n_stands"] == 2
    # the bow-tie is two triangles, half a square together; the other is two whole squares
    assert res["old"]["stand_area_ha"] == pytest.approx(2.5 * square_ha(), rel=1e-3)
    assert res["old_to_new"]["area_weighted_iou"] == pytest.approx(1.0, abs=1e-9)
    assert res["same_outline_stands"] == 2


def test_features_without_geometry_or_id_are_counted_and_left_out():
    old = GRID4 + [
        {"type": "Feature", "properties": {"stand_lbl": 9}, "geometry": None},
        {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring(7, 7)]}},
    ]
    res = compare(old, GRID4)
    assert res["old"]["n_features"] == 6
    assert res["old"]["n_skipped"] == 2
    assert res["old"]["n_stands"] == 4
    assert res["old_to_new"]["area_weighted_iou"] == pytest.approx(1.0, abs=1e-12)


def test_a_wrong_id_field_is_an_error_that_names_the_fields_present():
    with pytest.raises(ValueError, match="stand_lbl"):
        csr.layer_from_features(GRID4, id_field="snic_label")


def test_ids_written_as_inexact_floats_are_the_same_stand():
    old = [feat(17, ring(0, 0)), feat(17, ring(3, 0))]
    new = [feat(17.0, ring(0, 0)), feat(16.999999999999996, ring(3, 0))]
    res = compare(old, new)
    assert res["new"]["n_stands"] == 1
    assert res["ids_in_both"] == 1
    assert res["same_outline_same_id"] == 1


def test_another_id_field():
    old = [feat(1, ring(0, 0), id_field="snic_label"), feat(2, ring(1, 0), id_field="snic_label")]
    res = compare(old, old, id_field="snic_label")
    assert res["old"]["n_stands"] == 2
    assert csr.is_identical(res)


# --------------------------------------------------------------------------- types
def test_types_renumbered_between_runs_are_recognised_as_the_same_grouping():
    old = [feat(1, ring(0, 0), cluster=0), feat(2, ring(1, 0), cluster=1),
           feat(3, ring(2, 0), cluster=2.9999999999999973)]
    new = [feat(1, ring(0, 0), cluster=1), feat(2, ring(1, 0), cluster=3), feat(3, ring(2, 0), cluster=0)]
    t = compare(old, new, type_field="cluster_id")["types"]
    assert t["types_old"] == [0, 1, 3]  # 2.9999999999999973 is type 3
    assert t["share_same_number"] == pytest.approx(0.0, abs=1e-9)
    assert t["share_after_best_renumbering"] == pytest.approx(1.0)
    assert t["best_renumbering"] == {0: 1, 1: 3, 3: 0}


def test_types_partly_changed():
    old = [feat(1, ring(0, 0), cluster=0), feat(2, ring(1, 0), cluster=0), feat(3, ring(2, 0), cluster=1),
           feat(4, ring(3, 0))]
    new = [feat(1, ring(0, 0), cluster=0), feat(2, ring(1, 0), cluster=1), feat(3, ring(2, 0), cluster=1),
           feat(4, ring(3, 0), cluster=1)]
    res = compare(old, new, type_field="cluster_id")
    t = res["types"]
    assert t["untyped_stands_old"] == 1
    # three squares carry a type in both layers; two of them keep their number
    assert t["typed_common_area_ha"] == pytest.approx(3 * square_ha(), rel=1e-4)
    assert t["share_same_number"] == pytest.approx(2 / 3, abs=1e-6)
    assert res["same_outline_same_type"] == 2
    assert "STAND TYPES" in "\n".join(csr.format_report(res))


def test_types_are_not_reported_unless_asked_for():
    res = compare(GRID4, GRID4)
    assert res["types"] is None
    assert "STAND TYPES" not in "\n".join(csr.format_report(res))


# --------------------------------------------------------------------------- size
def test_several_hundred_stands():
    n = 20  # 400 stands per layer, matched through the spatial index
    old = [feat(r * n + c, ring(c, r)) for r in range(n) for c in range(n)]
    new = [feat(r * n + c, ring(c + 0.25, r)) for r in range(n) for c in range(n)]
    res = compare(old, new)
    assert res["old"]["n_stands"] == n * n
    # every stand shares three quarters with its best match: 0.75 / 1.25. Rows well away from
    # the latitude the projection is centred on are very slightly distorted in shape (never in
    # area), hence the looser tolerance than for the small layers above.
    assert res["old_to_new"]["area_weighted_iou"] == pytest.approx(0.6, abs=1e-4)
    assert res["old_to_new"]["share_area_iou_ge"][0.5] == pytest.approx(1.0)
    assert res["old_to_new"]["share_area_iou_ge"][0.9] == 0.0


# --------------------------------------------------------------------------- command line
def _write(path: Path, feats: list[dict]) -> Path:
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return path


def test_command_line_prints_the_table_and_writes_results_only(tmp_path, capsys):
    old = _write(tmp_path / "old.geojson", GRID4)
    new = _write(tmp_path / "new.geojson", GRID4[:3])
    out = tmp_path / "results" / "cmp.txt"
    per = tmp_path / "results" / "stands.csv"
    assert csr.main([str(old), str(new), "--out", str(out), "--per-stand-csv", str(per)]) == 0
    printed = capsys.readouterr().out
    text = out.read_text()
    assert text.strip() == printed.strip()
    assert "old.geojson" in text and "new.geojson" in text
    assert str(tmp_path) not in text  # file names, not this machine's folders
    assert "area-weighted mean IoU" in text
    lines = per.read_text().splitlines()
    assert lines[0].startswith("layer,stand_id,")
    assert len(lines) == 1 + 4 + 3

    # the same inputs give the same file, byte for byte: nothing in it depends on when it ran
    out2 = tmp_path / "results2" / "cmp.txt"
    assert csr.main([str(old), str(new), "--out", str(out2)]) == 0
    assert out2.read_text() == text


def test_command_line_reports_a_file_it_cannot_read(tmp_path, capsys):
    old = _write(tmp_path / "old.geojson", GRID4)
    assert csr.main([str(old), str(tmp_path / "absent.geojson")]) == 2
    (tmp_path / "bad.geojson").write_text(json.dumps({"type": "Feature"}))
    assert csr.main([str(old), str(tmp_path / "bad.geojson")]) == 2
    assert "could not compare" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_refuses_to_write_into_a_folder_holding_committed_files(tmp_path):
    repo = tmp_path / "repo"
    (repo / "results").mkdir(parents=True)
    (repo / "results" / "committed.txt").write_text("a committed result\n")

    def git(*args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    git("init", "-q")
    git("add", "results/committed.txt")
    git("-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-q", "-m", "result")

    old = _write(tmp_path / "old.geojson", GRID4)
    assert [Path(f).name for f in csr.tracked_files_in(repo / "results")] == ["committed.txt"]
    with pytest.raises(SystemExit, match="REFUSING"):
        csr.main([str(old), str(old), "--out", str(repo / "results" / "new.txt")])
    assert not (repo / "results" / "new.txt").exists()
    assert (repo / "results" / "committed.txt").read_text() == "a committed result\n"

    # a new folder in the same checkout holds nothing committed, so it is accepted
    assert csr.tracked_files_in(repo / "fresh") == []
    assert csr.main([str(old), str(old), "--out", str(repo / "fresh" / "new.txt")]) == 0
    assert (repo / "fresh" / "new.txt").exists()

    # a folder that does not exist yet, below the one with the committed file, is still inside it
    assert csr.tracked_files_in(repo) != []
    assert csr.tracked_files_in(repo / "results" / "sub") == []


def _ignores_case(folder: Path) -> bool:
    (folder / "CaseProbe").mkdir()
    return (folder / "caseprobe").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_refusal_is_not_bypassed_by_another_spelling_of_the_folder(tmp_path):
    # On a file system that ignores case (macOS by default) RESULTS/ is results/. The refusal
    # must hold for every spelling, or a committed result could be overwritten through one.
    repo = tmp_path / "repo"
    (repo / "results" / "deep").mkdir(parents=True)
    (repo / "results" / "committed.txt").write_text("a committed result\n")
    (repo / "results" / "deep" / "x.txt").write_text("another\n")
    for args in (["init", "-q"], ["add", "."],
                 ["-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-q", "-m", "result"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    old = _write(tmp_path / "old.geojson", GRID4)

    # the lookup itself ignores case on every file system (on one that tells the spellings
    # apart this refuses a folder it could have accepted, which is the safe side)
    assert sorted(csr.tracked_files_in(repo / "RESULTS")) == ["results/committed.txt", "results/deep/x.txt"]
    assert csr.tracked_files_in(repo / "Results" / "DEEP") == ["results/deep/x.txt"]
    with pytest.raises(SystemExit, match="REFUSING"):
        csr.main([str(old), str(old), "--out", str(repo / "RESULTS" / "committed.txt")])
    with pytest.raises(SystemExit, match="REFUSING"):
        csr.main([str(old), str(old), "--per-stand-csv", str(repo / "Results" / "Deep" / "x.txt")])
    assert (repo / "results" / "committed.txt").read_text() == "a committed result\n"
    assert (repo / "results" / "deep" / "x.txt").read_text() == "another\n"

    if not _ignores_case(tmp_path):
        pytest.skip("this file system tells RESULTS/ from results/: the rest needs one that does not")
    # called from inside the folder under its other spelling
    assert csr.tracked_files_in(Path(str(repo).replace("repo", "REPO")) / "results") != []


# --------------------------------------------------------------------------- the Odisha wrapper
# odisha_script/odisha_repro_compare.py runs the Phase 2 join and the Phase 3 scoring on a
# re-run's files; that needs the stand files and is checked by running it (see its docstring).
# Here: the parts that need no data.
WRAPPER = Path(__file__).parent.parent / "odisha_script" / "odisha_repro_compare.py"


def _load_wrapper():
    spec = importlib.util.spec_from_file_location("odisha_repro_compare", WRAPPER)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SCORE_TEXT = """\
  plots with a stand: 267
  stands holding them: 198   multi-plot stands: 44 holding 113 plots   (stand key = district:id)
----
A. DELINEATION -- do alike plots end up in the same stand?
----
  all pairs
      pairs 35,511   field-alike 28.7%   grouped-together 0.3%
                      same group   different
      field alike             63      10,116
      field differs           50      25,282
      accuracy 0.714   precision 0.558   recall 0.006   F1 0.012
      >>> ARI +0.0060   (0 = no better than chance, 1 = perfect)

----
B. LABELLING -- do alike plots get the same stand TYPE, even far apart?
----
    ANGUL       n=  39   ARI +0.1461
    KORAPUT     n= 145   ARI -0.0014

  same-district pairs  (ARI = plot-weighted mean of the per-district values above)
      pairs 13,984   field-alike 36.7%   grouped-together 22.6%
                      same group   different
      field alike          1,267       3,865
      field differs        1,891       6,961
      accuracy 0.588   precision 0.401   recall 0.247   F1 0.306
      >>> ARI +0.0793   (0 = no better than chance, 1 = perfect)

  same-district pairs more than 2 km apart  (ARI is a whole-partition score)
      pairs 10,651   field-alike 35.1%   grouped-together 17.3%
                      same group   different
      field alike            679       3,055
      field differs        1,159       5,758
      accuracy 0.604   precision 0.369   recall 0.182   F1 0.244
      >>> ARI n/a (see note)
"""


def test_wrapper_reads_every_number_of_a_score_file():
    w = _load_wrapper()
    got = dict(w.parse_score_file(SCORE_TEXT))
    assert got["plots with a stand"] == "267"
    assert got["multi-plot stands"] == "44"
    assert got["A delineation, all pairs: ARI"] == "+0.0060"
    assert got["A delineation, all pairs: alike, different"] == "10,116"
    assert got["B labelling, KORAPUT: ARI"] == "-0.0014"
    assert got["B labelling, same-district pairs: ARI"] == "+0.0793"
    assert got["B labelling, same-district pairs more than 2 km apart: recall"] == "0.182"
    # the far-apart block has no ARI, and none is invented for it
    assert "B labelling, same-district pairs more than 2 km apart: ARI" not in got
    assert len(got) == 4 + 12 + 4 + 12 + 11


def test_wrapper_score_comparison_marks_what_differs(capsys):
    w = _load_wrapper()
    same, n_diff = w.report_scores(SCORE_TEXT, SCORE_TEXT)
    assert same and n_diff == 0
    changed = SCORE_TEXT.replace("ARI +0.0793", "ARI +0.0811").replace("multi-plot stands: 44", "multi-plot stands: 45")
    same, n_diff = w.report_scores(SCORE_TEXT, changed)
    assert not same and n_diff == 2
    printed = capsys.readouterr().out
    assert "+0.0018 *" in printed and "+1 *" in printed


def test_wrapper_run_record_comparison_lists_what_differs():
    w = _load_wrapper()
    old = {"config": "a", "fingerprint": "f1", "run_dir": "runs/a_1", "drive_exports": {"t": 1},
           "pulled_polygon_counts": {"stands_merged": 203},
           "merge_diagnostics": {"n_stands": 200, "pass2_merges": 257, "adjacency": {"n_edges": 10}},
           "stand_attributes": {"0": {"n_pixels": 10, "area_ha": 0.1}, "1": {"n_pixels": 20, "area_ha": 0.2}}}
    new = json.loads(json.dumps(old))
    new.update(config="a_repro", run_dir="runs/a_repro_2", drive_exports={"t": 2},
               git={"commit": "abc", "dirty": False})
    res = w.compare_run_records(old, new)
    assert res["differences"] == []  # name, run folder, export tasks and git differ by construction
    assert res["git_new"] == {"commit": "abc", "dirty": False}
    assert w.report_run_records(res)

    new["merge_diagnostics"]["n_stands"] = 198
    new["merge_diagnostics"]["adjacency"]["n_edges"] = 11
    new["fingerprint"] = "f2"
    new["stand_attributes"]["1"]["n_pixels"] = 21
    res = w.compare_run_records(old, new)
    assert [d[0] for d in res["differences"]] == [
        "fingerprint", "merge_diagnostics.n_stands", "merge_diagnostics.adjacency.n_edges"]
    assert res["stand_attributes"]["ids_in_both_identical"] == 1
    assert not w.report_run_records(res)


def test_wrapper_refuses_to_write_where_committed_results_are(tmp_path):
    w = _load_wrapper()
    if not (w.REPO / ".git").exists():
        pytest.skip("needs the git checkout: the refusal asks git which folders hold committed files")
    rerun = tmp_path / "rerun"
    rerun.mkdir()
    for bad in (w.HERE, w.HERE / "phase2_vectors", w.HERE / "phase3_3ha" / "sub", w.REPO, rerun):
        with pytest.raises(SystemExit, match="REFUSING"):
            w.check_out_dir(bad, rerun, "odisha_v120_3ha")
    w.check_out_dir(tmp_path / "new", rerun, "odisha_v120_3ha")  # a new folder is accepted
    # the folders that hold committed results, reached through a link, are refused as well
    (tmp_path / "link").symlink_to(w.HERE, target_is_directory=True)
    for bad in (tmp_path / "link", tmp_path / "link" / "phase2_vectors" / "new"):
        with pytest.raises(SystemExit, match="REFUSING"):
            w.check_out_dir(bad, rerun, "odisha_v120_3ha")
    other = tmp_path / "other"
    other.mkdir()
    (other / "odisha_repro_compare_odisha_alphaearth.txt").write_text("x")
    with pytest.raises(SystemExit, match="another arm"):
        w.check_out_dir(other, rerun, "odisha_v120_3ha")


def test_wrapper_uses_the_phase3_options_of_each_arm():
    w = _load_wrapper()
    assert w.ARMS["odisha_v120_handcrafted"]["score_args"] == ["--arm", "v120"]
    assert w.ARMS["odisha_v120_3ha"]["score_args"] == ["--arm", "v120_3ha", "--tag", "_3ha"]
    assert w.ARMS["odisha_alphaearth"]["score_args"] is None  # Phase 3 did not score this arm
    assert [a[2] for a in w.ANALYSES] == ["", "_excl0", "_ft-k4", "_ft-allrows"]


def test_wrapper_refusal_holds_for_another_spelling_of_the_folder(tmp_path):
    # the blocker of the review: on macOS ODISHA_SCRIPT is odisha_script, and a check that
    # compared spellings let the committed plot table and score files be overwritten
    w = _load_wrapper()
    if not (w.REPO / ".git").exists():
        pytest.skip("needs the git checkout: the refusal asks git which folders hold committed files")
    if not Path(str(w.HERE).upper()).exists():
        pytest.skip("this file system tells ODISHA_SCRIPT/ from odisha_script/")
    rerun = tmp_path / "rerun"
    rerun.mkdir()
    for bad in (w.REPO / "ODISHA_SCRIPT", w.REPO / "odisha_script" / "Phase3_3HA",
                w.REPO / "odisha_script" / "PHASE2_VECTORS" / "x", w.REPO / "Odisha_Script" / "phase3_3HA" / "a" / "b",
                w.REPO / "DOCS", Path(str(rerun).replace("rerun", "RERUN"))):
        with pytest.raises(SystemExit, match="REFUSING"):
            w.check_out_dir(bad, rerun, "odisha_v120_3ha")


# ---- the wrapper's risky path: which files the join is given
def _stand_file(path: Path, id_field: str, n: int, shift: float = 0.0) -> None:
    feats = [feat(k + 1, ring(k + shift, 0), cluster=k % 2, id_field=id_field) for k in range(n)]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))


def _fake_run(folder: Path, arm: str, w, suffix: str, n: int, shift: float = 0.0) -> None:
    """The five files of every district, as odisha_phase2_2_run_pipeline.py names them."""
    folder.mkdir()
    for d in w.DISTRICTS:
        stem = f"{arm}_{d}{suffix}"
        _stand_file(folder / f"{stem}_stands_merged.geojson", "stand_lbl", n, shift)
        _stand_file(folder / f"{stem}_stands_snic.geojson", "snic_label", n + 1, shift)
        _stand_file(folder / f"{stem}_stands_dissolved.geojson", "stand_lbl", n, shift)
        (folder / f"{stem}_raster_at_plots.csv").write_text(f"plot_key,value\n{d},{n}\n")
        (folder / f"{stem}_run.json").write_text(json.dumps(
            {"config": stem, "fingerprint": "f1", "merge_diagnostics": {"n_stands": n}}))


def test_wrapper_presents_the_reruns_files_under_the_committed_names(tmp_path):
    w = _load_wrapper()
    arm = "odisha_v120_3ha"
    rerun, staged = tmp_path / "rerun", tmp_path / "staged"
    _fake_run(rerun, arm, w, "_repro", 2)
    (rerun / f"{arm}_koraput_repro_run.json").unlink()  # optional for the join: left out, not invented
    (rerun / f"{arm}_angul_stands_merged.geojson").write_text("not a re-run file: no _repro in its name")
    staged.mkdir()
    w.stage_rerun(rerun, arm, "_repro", w.DISTRICTS, staged)
    names = sorted(p.name for p in staged.iterdir())
    expected = sorted(f"{arm}_{d}_{tail}" for d in w.DISTRICTS for tail in w.FILE_SUFFIXES)
    expected.remove(f"{arm}_koraput_run.json")
    assert names == expected  # the names odisha_phase2_3_join.py looks for, and nothing else
    for p in staged.iterdir():
        d, tail = p.name[len(arm) + 1:].split("_", 1)
        assert p.resolve() == (rerun / f"{arm}_{d}_repro_{tail}").resolve()  # the re-run's file
        assert p.read_bytes() == (rerun / f"{arm}_{d}_repro_{tail}").read_bytes()
        assert w.COMMITTED_VECTORS.resolve() not in p.resolve().parents  # never the committed one


def test_wrapper_gives_the_join_the_reruns_files_and_clears_stale_outputs(tmp_path, monkeypatch, capsys):
    # main() from end to end on tiny stand files, with the Phase 2 join replaced by a stand-in
    # that records what it was pointed at. If the join were ever pointed at the committed
    # stands, every re-run would look perfectly reproduced; this is the test that would fail.
    w = _load_wrapper()
    arm = "odisha_v120_3ha"
    committed, rerun, out = tmp_path / "committed", tmp_path / "rerun", tmp_path / "out"
    _fake_run(committed, arm, w, "", 3)
    _fake_run(rerun, arm, w, "_repro", 2, shift=0.5)  # fewer stands, half a stand to the side
    monkeypatch.setattr(w, "COMMITTED_VECTORS", committed)

    # what an earlier, complete run with --checks left in the same output folder
    stale = [w.JOINED_NAME, w.JOIN_RESULTS_NAME, "odisha_phase3_1_score_v120_3ha_merged_districts_3ha.txt",
             "odisha_phase3_1_score_v120_3ha_merged_districts_3ha_excl0.txt",
             "odisha_phase3_1_score_v120_3ha_merged_districts_3ha_ft-k4.txt",
             f"odisha_repro_compare_{arm}_manifest.json", f"per_stand/{arm}_gone_stands_merged.csv"]
    (out / "per_stand").mkdir(parents=True)
    for name in stale:
        (out / name).write_text("from an earlier run\n")
    (out / "notes.txt").write_text("not written by the script\n")

    calls = []

    def fake_run_script(script, args):
        seen = {}
        if "--vectors-dir" in args:
            vdir = Path(args[args.index("--vectors-dir") + 1])
            seen = {p.name: (p.resolve(), p.read_bytes()) for p in vdir.iterdir()}
        calls.append((Path(script), list(args), seen))
        return subprocess.CompletedProcess(args, 1, "", "stand-in for the join: stops here")

    monkeypatch.setattr(w, "run_script", fake_run_script)
    assert w.main(["--arm", arm, "--rerun-dir", str(rerun), "--out-dir", str(out)]) == 0
    capsys.readouterr()

    assert len(calls) == 1  # the join failed, so nothing was scored
    script, args, seen = calls[0]
    assert script == w.JOIN_SCRIPT
    assert args[:4] == ["--set", "districts", "--arms", "v120_3ha"]
    assert Path(args[args.index("--out-dir") + 1]) == out.resolve()
    vdir = Path(args[args.index("--vectors-dir") + 1])
    assert vdir.resolve() != committed.resolve() and committed.resolve() not in vdir.resolve().parents
    assert not vdir.exists()  # the temporary folder is removed afterwards
    assert sorted(seen) == sorted(f"{arm}_{d}_{tail}" for d in w.DISTRICTS for tail in w.FILE_SUFFIXES)
    for name, (target, content) in seen.items():
        d, tail = name[len(arm) + 1:].split("_", 1)
        assert target == (rerun / f"{arm}_{d}_repro_{tail}").resolve()
        assert content == (rerun / f"{arm}_{d}_repro_{tail}").read_bytes()
        assert content != (committed / name).read_bytes()

    text = (out / f"odisha_repro_compare_{arm}.txt").read_text()
    assert "THE JOIN FAILED" in text and "NOT DONE: there is no new plot table" in text
    assert "3 -> 2" in text  # the stand comparison read the re-run's stands too
    assert "DIFFERS" in text and "Everything measured is identical" not in text
    assert str(tmp_path) not in text  # results only: no machine folders
    # nothing of the earlier run is left beside the new results file
    for name in stale[:5] + stale[6:]:
        assert not (out / name).exists(), name
    assert "from an earlier run" not in (out / f"odisha_repro_compare_{arm}_manifest.json").read_text()
    assert (out / "notes.txt").read_text() == "not written by the script\n"
    assert sorted(p.name for p in (out / "per_stand").iterdir()) == sorted(
        f"{arm}_{d}_{layer}.csv" for d in w.DISTRICTS for layer in w.COMPARED_LAYERS)
    # the committed stand-ins were only read
    assert sorted(p.name for p in committed.iterdir()) == sorted(
        f"{arm}_{d}_{tail}" for d in w.DISTRICTS for tail in w.FILE_SUFFIXES)


def _plot_table(w, merged_ids, clusters, bdist, ba=(10.0, 11.0, 12.0, 13.0, 14.0, 15.0)):
    import pandas as pd

    return pd.DataFrame({
        "plot_key": [f"p{k}" for k in range(6)],
        "district": ["a", "a", "a", "b", "b", "b"],
        "ba_m2_ha": list(ba),  # a field-data column: no re-run may change it
        "v120_3ha_merged_id": merged_ids,
        "v120_3ha_merged_cluster": clusters,
        "v120_3ha_merged_bdist_m": bdist,
    })


def test_wrapper_plot_table_comparison_on_hand_made_tables(capsys):
    w = _load_wrapper()
    inf = float("inf")
    # stand 1 of district a and stand 1 of district b are different stands (the key is district:id)
    old = _plot_table(w, [1, 1, 2, 1, 1, 2], [0, 0, 1, 0, 0, 1], [5.0, 6.0, 7.0, 8.0, 9.0, inf])
    same = w.compare_plot_tables(old, old.copy(), "v120_3ha")
    assert same["identical_on_shared_columns"] and same["differing"] == {}
    assert same["merged_partition"]["pairs_together_old"] == 2  # p0-p1 and p3-p4, not p0-p3
    assert same["merged_partition"]["stands_old"] == 4
    assert same["merged_partition"]["ari"] == pytest.approx(1.0)

    # every stand and every type renumbered, nothing else: the same grouping of plots
    renumbered = _plot_table(w, [5, 5, 6, 8, 8, 3], [1, 1, 0, 0, 0, 1], [5.0, 6.0, 7.0, 8.0, 9.0, inf])
    res = w.compare_plot_tables(old, renumbered, "v120_3ha")
    assert not res["identical_on_shared_columns"]
    assert res["differing"]["v120_3ha_merged_id"]["plots"] == 6
    assert "v120_3ha_merged_bdist_m" not in res["differing"]  # infinite in both is no difference
    assert res["field_columns_differing"] == []
    p = res["merged_partition"]
    assert (p["pairs_together_old"], p["pairs_together_new"], p["pairs_together_both"]) == (2, 2, 2)
    assert p["ari"] == pytest.approx(1.0)
    assert res["type_agreement"]["per_district"] == [("a", 3, pytest.approx(1.0), 0), ("b", 3, pytest.approx(1.0), 3)]

    # one plot (p1) moved to the stand of p2; one plot lost its stand; one distance became infinite;
    # one field value changed
    moved = _plot_table(w, [5, 6, 6, 8, 8, None], [1, 1, 0, 0, 0, 1], [5.0, inf, 7.0, 8.0, 9.5, inf],
                        ba=(10.0, 11.0, 12.0, 13.0, 14.0, 99.0))
    res = w.compare_plot_tables(old, moved, "v120_3ha")
    p = res["merged_partition"]
    assert (p["with_stand_old"], p["with_stand_new"], p["with_stand_both"], p["only_old"]) == (6, 5, 5, 1)
    # old pairs among the five plots still placed: p0-p1, p3-p4; new: p1-p2, p3-p4; both: p3-p4
    assert (p["pairs_together_old"], p["pairs_together_new"], p["pairs_together_both"]) == (2, 2, 1)
    assert p["ari"] < 1.0
    assert res["field_columns_differing"] == ["ba_m2_ha"]
    e = res["differing"]["v120_3ha_merged_bdist_m"]
    assert e["plots"] == 2 and e["one_side_infinite"] == 1
    assert e["max_abs_diff"] == inf  # not 0.5: a finite value that became infinite is not hidden
    w.report_plot_tables(res, "v120_3ha")
    printed = capsys.readouterr().out
    line = next(ln for ln in printed.splitlines() if ln.strip().startswith("v120_3ha_merged_bdist_m"))
    assert line.split()[-1] == "inf"
    assert "infinite in one table and finite in the other, for 1 plot" in printed


def test_wrapper_says_what_an_equal_fingerprint_does_not_show(capsys):
    w = _load_wrapper()
    rec = {"fingerprint": "f1", "merge_diagnostics": {"n_stands": 3}}
    assert w.report_run_records(w.compare_run_records(rec, dict(rec)))
    printed = capsys.readouterr().out
    assert "same cache-relevant settings" in printed and "not the version of the code" in printed
