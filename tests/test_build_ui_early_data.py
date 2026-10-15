"""Offline checks of scripts/build_ui_early_data.py: the stand means it keeps, and the layers it
draws pixel by pixel for Sanjay Van (round 3's step 3, done in round 4)."""

from __future__ import annotations

import importlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("rasterio")
pytest.importorskip("PIL")

import rasterio  # noqa: E402
from PIL import Image  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def builder(monkeypatch, tmp_path):
    """The script as a module, with its output and per-pixel folders under tmp_path. It reads
    its folders from sys.argv when imported, so the import sees no arguments."""
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.setattr(sys, "argv", ["build_ui_early_data.py"])
    module = importlib.import_module("build_ui_early_data")
    monkeypatch.setattr(module, "OUT", tmp_path / "ui_data")
    monkeypatch.setattr(module, "PIXELS", tmp_path / "ui_data_full")
    return module


def _geotiff(path: Path, bands: dict[str, np.ndarray]) -> None:
    """A small EPSG:4326 GeoTIFF with named float32 bands, as scripts/fetch_ui_layers.py writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    first = next(iter(bands.values()))
    with rasterio.open(path, "w", driver="GTiff", width=first.shape[1], height=first.shape[0],
                       count=len(bands), dtype="float32", crs="EPSG:4326", nodata=float("nan"),
                       transform=from_origin(77.0, 28.6, 0.0001, 0.0001)) as dst:
        for i, (name, data) in enumerate(bands.items(), 1):
            dst.write(data.astype("float32"), i)
            dst.set_band_description(i, name)


def _js_ramp(palette: list[str], t: float) -> list[int]:
    """`ramp` of ui/explorer.html, line for line."""
    x = min(1.0, max(0.0, t)) * (len(palette) - 1)
    i = min(len(palette) - 2, math.floor(x))
    f = x - i
    a = [int(palette[i][k:k + 2], 16) for k in (1, 3, 5)]
    b = [int(palette[i + 1][k:k + 2], 16) for k in (1, 3, 5)]
    return [math.floor(v + (w - v) * f + 0.5) for v, w in zip(a, b, strict=True)]


def test_every_feature_mean_is_kept_and_ids_and_provenance_are_not(builder):
    props = {"stand_id": 3, "stand_lbl": 3, "area_ha": 1.2, "cluster_id": 2, "n_pixels": 120,
             "centroid_lat": 28.5, "centroid_lon": 77.2, "perim_m": 500.0,
             "n_superpx": 2, "n_pass1": 1, "n_relaxed": 0, "n_fallback": 0, "below_min": 0,
             "below_why": "", "canopy_height": 7.25, "ndvi_trend": 0.000123456,
             "vh_p50": -19.87654}
    assert builder.feature_names(props) == ["canopy_height", "ndvi_trend", "vh_p50"]


def test_the_seven_first_kept_keep_their_decimals_and_the_rest_four_figures(builder):
    assert builder.feature_value("canopy_height", 7.25) == round(7.25, 1)
    assert builder.feature_value("elevation", 215.6) == 216.0
    assert builder.feature_value("ndvi_trend", 0.000123456) == 0.0001235
    assert builder.feature_value("vh_p50", -19.87654) == -19.88
    assert builder.feature_value("A07", 0.0412345) == 0.04123
    assert builder.feature_value("slope", None) is None
    assert builder.feature_value("vh_p50", float("nan")) is None


def test_the_colour_ramp_is_the_explorers(builder):
    palette = ["#f7fcf5", "#c7e9c0", "#74c476", "#238b45", "#00441b"]
    ts = np.array([-1.0, 0.0, 0.1, 0.25, 0.5, 0.6, 0.999, 1.0, 2.0])
    got = builder.ramp_rgb(palette, ts)
    assert got.tolist() == [_js_ramp(palette, float(t)) for t in ts]


def test_a_hand_crafted_run_gets_three_layers_pixel_by_pixel(builder, tmp_path):
    rng = np.random.default_rng(0)
    shape = (6, 5)
    bands = {name: rng.normal(size=shape) for name in
             ("B4_median", "B8_median", "canopy_height", "ndvi_amplitude_annual",
              "vv_minus_vh_median")}
    bands["canopy_height"][0, 0] = np.nan
    _geotiff(tmp_path / "ui_data_full" / "run_a" / "features_part01.tif", bands)

    layers = builder.pixel_feature_layers("run_a", "feature_vector")

    assert [layer["layer_id"] for layer in layers] == [
        "feature_canopy_height", "feature_ndvi_amplitude_annual", "feature_vv_minus_vh_median"]
    first = layers[0]
    assert first["kind"] == "raster" and first["smooth"] is False
    # No description: the explorer marks a colour-ramp layer with one as a stand average.
    assert "description" not in first
    valid = bands["canopy_height"][np.isfinite(bands["canopy_height"])]
    lo, hi = np.percentile(valid, [2, 98])
    assert first["colormap"]["min"] == round(float(lo), 3)
    assert first["colormap"]["max"] == round(float(hi), 3)
    (part,) = first["parts"]
    assert part["file"] == "by_run/run_a/feature_canopy_height_part01.png"
    assert part["bounds"] == [77.0, 28.5994, 77.0005, 28.6]
    rgba = np.asarray(Image.open(tmp_path / "ui_data" / part["file"]))
    assert rgba.shape == (*shape, 4)
    assert rgba[0, 0, 3] == 0 and (rgba[..., 3].ravel()[1:] == 255).all()


def test_an_alphaearth_run_gets_its_embedding_as_colour_pixel_by_pixel(builder, tmp_path):
    rng = np.random.default_rng(1)
    shape = (8, 7)
    bands = {f"A{i:02d}": rng.normal(size=shape) for i in range(64)}
    bands["A05"][3, 4] = np.nan
    _geotiff(tmp_path / "ui_data_full" / "run_b" / "embedding_part01.tif", bands)

    (layer,) = builder.pixel_feature_layers("run_b", "alphaearth")

    assert layer["layer_id"] == "embedding_rgb" and layer["kind"] == "raster"
    assert layer["color_is_value"] is True and "pixel" in layer["description"]
    path = tmp_path / "ui_data" / layer["parts"][0]["file"]
    first = path.read_bytes()
    rgba = np.asarray(Image.open(path))
    assert rgba.shape == (*shape, 4)
    assert rgba[3, 4, 3] == 0 and int((rgba[..., 3] == 255).sum()) == shape[0] * shape[1] - 1
    # The same data gives the same picture.
    builder.pixel_feature_layers("run_b", "alphaearth")
    assert path.read_bytes() == first


def test_a_run_without_geotiffs_gets_none(builder):
    assert builder.pixel_feature_layers("run_c", "feature_vector") is None


def test_the_committed_ui_data_draws_sanjay_van_pixel_by_pixel():
    index = json.loads((SCRIPTS.parent / "ui_data" / "index.json").read_text())
    by_id = {r["run_id"]: r for r in index["runs"]}
    for run_id in ("sanjay_van_baseline_repro", "sanjay_van_alphaearth_repro"):
        (step,) = [s for s in by_id[run_id]["steps"] if s["step"] == "features"]
        assert step["layers"] and all(layer["kind"] == "raster" for layer in step["layers"])
        for layer in step["layers"]:
            for part in layer["parts"]:
                assert (SCRIPTS.parent / "ui_data" / part["file"]).is_file()


# ---------------------------------------------------------------- the kept-land runs (round 5)

FILL = math.sqrt(2**31 - 1) * 10  # distance_to_water where the transform finds no water


def test_far_water_is_over_10_km_where_it_is_marked(builder):
    assert builder.feature_value("distance_to_water", FILL, far_water=True) == "over 10 km"
    # A capped band (features_static.cap_distance_to_water) holds the cap itself there.
    assert builder.feature_value("distance_to_water", 10_000.0, far_water=True) == "over 10 km"
    assert builder.feature_value("distance_to_water", 9_999.0, far_water=True) == 9999.0
    # The cap as Earth Engine reads it back, just under 10 km: "over 10 km", never 10000.0.
    assert builder.feature_value("distance_to_water", 9_999.98, far_water=True) == "over 10 km"
    assert builder.profile_value("distance_to_water", 9_999.5646) == "over 10 km"
    assert builder.feature_value("distance_to_water", 9_994.9, far_water=True) == 9995.0
    assert builder.feature_value("distance_to_water", FILL) == float(f"{FILL:.4g}")
    assert builder.feature_value("elevation", FILL, far_water=True) == round(FILL, 0)
    assert builder.profile_value("distance_to_water", FILL) == "over 10 km"
    assert builder.profile_value("canopy_height", 7.123456) == 7.123


def _stands(tmp_path, run_id: str) -> Path:
    square = [[[77.0, 28.0], [77.001, 28.0], [77.001, 28.001], [77.0, 28.001], [77.0, 28.0]]]
    feats = []
    for sid, (below, dist) in enumerate([(0, 1234.5), (1, FILL)]):
        props = {"stand_id": sid, "stand_lbl": sid, "area_ha": 1.5 + sid, "cluster_id": sid,
                 "n_pixels": 150, "centroid_lat": 28.0, "centroid_lon": 77.0, "perim_m": 400.0,
                 "n_superpx": 2, "n_pass1": 1, "n_relaxed": 0, "n_fallback": 0,
                 "below_min": below, "below_why": "isolated" if below else "",
                 "canopy_height": 6.0, "distance_to_water": dist}
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "Polygon", "coordinates": square}})
    path = tmp_path / f"{run_id}_stands_merged.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return tmp_path


def test_a_kept_land_runs_stands_carry_the_below_min_flag_and_far_water(builder, tmp_path):
    vec = _stands(tmp_path, "k_run")
    fc, st = builder.run_stands("k_run", "feature_vector", vec, keptland=True)
    first, second = (f["properties"] for f in fc["features"])
    assert (first["below_min"], second["below_min"]) == (False, True)
    assert (first["distance_to_water"], second["distance_to_water"]) == (1234.0, "over 10 km")
    assert "n_superpx" not in first and "below_why" not in first
    assert st["n_bands"] == 2
    # Another run's stands: no flag, and far water marked too (every run, round 7).
    fc, _ = builder.run_stands("k_run", "feature_vector", vec)
    other = fc["features"][1]["properties"]
    assert "below_min" not in other and other["distance_to_water"] == "over 10 km"


def test_a_kept_land_runs_profiles_diagnostics_and_metadata_are_written(builder, tmp_path):
    manifest = {"stages": [
        {"name": "profiling", "metadata": {"k": 2, "feature_bands": ["canopy_height",
                                                                     "distance_to_water"],
         "profiles": [{"cluster_id": 0, "pixel_count": 10, "area_ha": 0.1,
                       "canopy_height_mean": 6.123456, "canopy_height_p25": 5.0,
                       "canopy_height_p50": 6.0, "canopy_height_p75": 7.0,
                       "distance_to_water_mean": FILL, "distance_to_water_p25": 800.0,
                       "distance_to_water_p50": FILL, "distance_to_water_p75": FILL}]}},
        {"name": "export", "metadata": {"manifest": {"clustering": {
            "k": 2, "n_stands_left_out_of_fit": 3, "area_ha_in_stands_left_out_of_fit": 0.9}}}}]}
    (tmp_path / "k_run_manifest_export.json").write_text(json.dumps(manifest))
    # The one type's 0.1 ha against 0.0877 ha of kept land: 14% more.
    run = {"merge_diagnostics": {"n_stands": 5, "kept_land": {"kept_land_ha": 0.0877}}}
    names, clustering = builder.keptland_files("k_run", tmp_path, run, "at Sanjay Van", 28.53)
    assert clustering["n_stands_left_out_of_fit"] == 3
    out = tmp_path / "ui_data"
    prof = json.loads((out / names["profiles"]).read_text())
    assert prof["area_note"] == builder.area_note("at Sanjay Van", 14)
    (t0,) = prof["types"]
    assert t0["bands"]["canopy_height"] == {"mean": 6.123, "p25": 5.0, "p50": 6.0, "p75": 7.0}
    assert t0["bands"]["distance_to_water"] == {"mean": "over 10 km", "p25": 800.0,
                                                "p50": "over 10 km", "p75": "over 10 km"}
    assert json.loads((out / names["merge_diagnostics"]).read_text()) == run["merge_diagnostics"]
    assert json.loads((out / names["clustering_metadata"]).read_text())["k"] == 2


def test_the_kept_land_layer_holds_kept_land_only(builder, tmp_path, monkeypatch):
    mask_dir = tmp_path / "mask"
    band = np.array([[1, 1, 0, 0], [1, 1, 0, 0], [0, 0, 0, 1], [0, 0, 0, 1]], dtype="float64")
    _geotiff(mask_dir / "part01_x_habitat_mask.tif", {"habitat_mask": band})
    monkeypatch.setitem(builder.AREAS, "test_area", {"mask_dir": mask_dir})
    name = builder.kept_land_layer("test_area")
    data = json.loads((tmp_path / "ui_data" / name).read_text())
    assert [c["value"] for c in data["classes"]] == [1]
    assert len(data["classes"][0]["polygons"]) == 2  # the two patches


# ------------------------------------------------------- the box kept-land runs (round 6)

def test_the_area_note_gives_how_much_larger_the_type_areas_come_to(builder):
    # Sanjay Van's note as round 5 wrote it, word for word: its six types came to 967.3 ha on
    # 847.47 ha of kept land.
    assert builder.type_area_excess(967.3, 847.47, 28.53) == 14
    assert builder.area_note("at Sanjay Van", 14) == (
        "pixel_count and area_ha are the profiling stage's: pixels counted on the clustering "
        "image's own grid, a geographic one, each taken as 0.01 ha. Away from the equator its "
        "pixels are narrower than 10 m, so area_ha is too large by about 1/cos(latitude), some "
        "14% at Sanjay Van. The stands' areas (stands.json) are on the analysis grid.")
    # Measured where the kept land's area is known: a little more than the grid's share alone
    # (Angul's boxes, 20.8 N: 437.2 ha of types on 405.6 ha, against 1/cos 1.0696).
    assert builder.type_area_excess(437.2, 405.6, 20.79) == 8
    # Without it, the grid's share at the area's latitude.
    assert builder.type_area_excess(437.2, None, 20.79) == 7
    assert builder.type_area_excess(1.0, None, 18.8) == 6


def test_without_stands_the_plots_carry_no_stand(builder):
    """A box kept-land run's plots: shown, but joined to no stand (its field check is not run)."""
    from shapely.geometry import box

    everywhere = box(-180, -90, 180, 90)
    fc, n = builder.plots_for("k_run", "kendujhar", everywhere, with_stands=False)
    assert fc["features"] and n["in_district"] == len(fc["features"]) == n["inside"]
    assert "with_stand" not in n
    for f in fc["features"]:
        p = f["properties"]
        assert "stand_id" not in p and "stand_type" not in p
        assert p["district"] == "Kendujhar" and p["mask"] in ("kept", "dropped")
    # With stands (a box run), each plot carries the stand that covers it, or none.
    stands = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"stand_id": 7, "stand_type": 2},
         "geometry": {"type": "Polygon", "coordinates": [[[-180, -90], [180, -90], [180, 90],
                                                          [-180, 90], [-180, -90]]]}}]}
    fc, n = builder.plots_for("k_run", "kendujhar", everywhere, stands)
    assert n["with_stand"] == len(fc["features"])
    assert {(f["properties"]["stand_id"], f["properties"]["stand_type"])
            for f in fc["features"]} == {(7, 2)}


def test_a_box_kept_land_run_is_added_on_its_box_runs_area(builder, tmp_path, monkeypatch):
    kept = tmp_path / "keptland_runs"
    kept.mkdir()
    run_id = "odisha_v120_3ha_squares_kendujhar_keptland"
    for name in ("stands_merged.geojson", "stands_snic.geojson", "run.json",
                 "manifest_export.json"):
        (kept / f"{run_id}_{name}").write_text("{}")
    monkeypatch.setattr(builder, "KEPTLAND", kept)
    monkeypatch.setattr(builder, "RUNS", [])
    areas = {k: v for k, v in builder.AREAS.items() if not k.endswith("_boxes")}
    monkeypatch.setattr(builder, "AREAS", areas)
    notes = builder.add_keptland_runs()
    assert not builder.RUNS
    assert f"{run_id}: skipped (no area kendujhar_boxes: its box run was skipped)" in notes
    areas["kendujhar_boxes"] = {"title": "Kendujhar", "site": "Odisha", "roi": "boxes"}
    notes = builder.add_keptland_runs()
    (added,) = builder.RUNS
    assert added == {"run_id": run_id, "area": "kendujhar_boxes", "arm": "feature_vector",
                     "vec": kept, "keptland": True, "pixels_from": None}
    # The other three districts, the two Sanjay Van runs and the four descending-orbit runs of
    # round 7 have no files here.
    assert len(notes) == 9 and all("no committed files" in n for n in notes)


def test_the_committed_ui_data_shows_the_box_kept_land_runs_plots_without_a_stand():
    data = SCRIPTS.parent / "ui_data"
    index = json.loads((data / "index.json").read_text())
    runs = [r for r in index["runs"] if r.get("kept_land") and r["roi"] == "boxes"]
    # Round 6's four, and round 7's four on the descending radar orbit.
    assert sorted(r["run_id"] for r in runs) == sorted(
        f"odisha_v120_3ha_squares_{d}_keptland{s}" for d in ("angul", "dhenkanal", "kendujhar", "koraput")
        for s in ("", "_s1desc"))
    for r in runs:
        # Round 8: the descending-orbit runs' field check is run (numbers only), so they are
        # declared; their plot files still name no stand (the page joins them itself).
        assert r["fes_declared"] is r["run_id"].endswith("_s1desc")
        assert "plots_with_stand" not in r["facts"]
        (step,) = [s for s in r["steps"] if s["step"] == "fes_plots"]
        assert not {"stand_id", "stand_type"} & set(step["layers"][0]["popup_fields"])
        plots = json.loads((data / "by_run" / r["run_id"] / "plots.geojson").read_text())["features"]
        assert plots and not any({"stand_id", "stand_type"} & f["properties"].keys() for f in plots)
        stands = json.loads((data / "by_run" / r["run_id"] / "stands.json").read_text())["features"]
        assert all(isinstance(f["properties"]["below_min"], bool) for f in stands)
        # Capped at 10 km: 10 km reads "over 10 km", the cap read back just under it too.
        far = [f["properties"]["distance_to_water"] for f in stands]
        assert all(v == "over 10 km" or v < 10_000 for v in far)
        profiles = json.loads((data / "by_run" / r["run_id"] / "profiles.json").read_text())
        stats = [v for t in profiles["types"] for v in t["bands"]["distance_to_water"].values()]
        assert all(v == "over 10 km" or v < 10_000 for v in stats)


def test_the_committed_ui_data_holds_no_distance_to_water_of_10_km_as_a_number():
    """Every run, from round 7 (spec-ui-distance-to-water-over-10-km): 10 km or more reads
    "over 10 km"."""
    for f in sorted((SCRIPTS.parent / "ui_data" / "by_run").glob("*/stands.json")):
        values = [x["properties"].get("distance_to_water")
                  for x in json.loads(f.read_text())["features"]]
        assert all(v is None or v == "over 10 km" or v < 10_000 for v in values), f.parent.name


def test_an_alphaearth_runs_stands_carry_the_named_means_of_its_reduction(builder, tmp_path):
    """Round 7 (spec-ui-alphaearth-stands-named-means-by-reduction): beside the embedding, the
    means of <run>_stand_means.json, by polygon."""
    square = [[[77.0, 28.0], [77.001, 28.0], [77.001, 28.001], [77.0, 28.001], [77.0, 28.0]]]
    feats = [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": square},
              "properties": {"stand_id": sid, "stand_lbl": sid, "area_ha": 1.0, "cluster_id": 0,
                             "n_pixels": 100,
                             **{f"A{i:02d}": 0.01 * i + 0.1 * ((sid * (i + 1)) % 7) for i in range(64)}}}
             for sid in (1, 2, 3, 4)]
    (tmp_path / "ae_run_stands_merged.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}))
    fc, _ = builder.run_stands("ae_run", "alphaearth", tmp_path)
    assert fc["features"][0]["properties"]["canopy_height"] is None  # no reduction: null, as before
    means = {"bands": {"canopy_height": {}, "distance_to_water": {}},
             "stands": [{"stand_id": 1, "stand_lbl": 1, "canopy_height": 7.25,
                         "distance_to_water": FILL},
                        {"stand_id": 2, "stand_lbl": 2, "canopy_height": None,
                         "distance_to_water": 800.0},
                        *({"stand_id": s, "stand_lbl": s, "canopy_height": 5.0,
                           "distance_to_water": 50.0} for s in (3, 4))]}
    (tmp_path / "ae_run_stand_means.json").write_text(json.dumps(means))
    fc, st = builder.run_stands("ae_run", "alphaearth", tmp_path)
    first, second = (f["properties"] for f in fc["features"][:2])
    assert (first["canopy_height"], first["distance_to_water"]) == (7.2, "over 10 km")
    assert (second["canopy_height"], second["distance_to_water"]) == (None, 800.0)
    assert first["A05"] == builder.feature_value("A05", feats[0]["properties"]["A05"])
    assert "emb_rgb" in first


def test_a_file_kept_off_git_is_found_by_its_record_and_checked(builder, tmp_path):
    """spec-files-over-5-mb-off-git: the repo holds a run's <run>_files_off_git.json, the file is
    on the Mac; the builder reads it there once its SHA-256 matches the record."""
    import hashlib

    vec, off = tmp_path / "vec", tmp_path / "off"
    vec.mkdir()
    off.mkdir()
    (vec / "r_run.json").write_text("{}")
    big = off / "r_stands_snic.geojson"
    big.write_text('{"type": "FeatureCollection", "features": []}')
    record = {"files": [{"file": big.name, "bytes": big.stat().st_size,
                         "sha256": hashlib.sha256(big.read_bytes()).hexdigest(), "where": str(big)}]}
    (vec / "r_files_off_git.json").write_text(json.dumps(record))
    assert builder.vec_file(vec, "r_run.json") == vec / "r_run.json"
    assert builder.vec_file(vec, big.name) == big
    assert builder.vec_file(vec, "r_stands_merged.geojson") is None
    big.write_text("changed")
    with pytest.raises(SystemExit, match="SHA-256"):
        builder.vec_file(vec, big.name)
    # Named by the record but not on this machine: the build stops, it does not skip the run.
    big.unlink()
    with pytest.raises(SystemExit, match="not on this machine"):
        builder.vec_file(vec, big.name)


def test_the_kept_land_score_rows_follow_the_scores_file(builder):
    """Round 8: every analysis of odisha_script/keptland_scores/keptland_s1desc_scores.json, five
    rows each, numbers only, naming the four descending-orbit runs."""
    tests = [("drawing_all_plots", "a"), ("drawing_multi_plot", "b"), ("pair_precision", "c"),
             ("labelling_district", "d"), ("far_apart", "e")]
    rows = builder.keptland_rows(tests)
    scores = json.loads((SCRIPTS.parent / "odisha_script" / "keptland_scores"
                         / "keptland_s1desc_scores.json").read_text())["analyses"]
    assert len(rows) == 5 * len(scores) == 25
    stat = {"drawing_all_plots": "delin_all", "drawing_multi_plot": "delin_multi",
            "pair_precision": "prec", "labelling_district": "lab_wmean", "far_apart": "far_gap"}
    by = {a["analysis"]: a for a in scores}
    for r in rows:
        a = by[r["analysis"]]
        assert r["score"] == a[stat[r["test"]]] and r["n_plots"] == a["counts"]["plots"]
        assert (r["chance_percentile"], r["p"], r["p_holm"]) == (None, None, None)
        assert (r["arm"], r["stand_ceiling_ha"], r["roi"]) == ("feature_vector", 3.0, "boxes")
        assert r["stands"] == "15 Oct 2026 kept-land runs (descending radar)"
        assert r["declaration"] == "odisha_script/PHASE_KEPTLAND_PREDECLARED.md"
        assert r["run_ids"] == sorted(builder.KEPTLAND_S1DESC_RUNS)


def test_every_score_row_names_runs_in_the_index_and_no_run_has_a_row_twice():
    """Round 8: the page matches score rows to runs by run_ids. Each id is a run of the index,
    and no run gets two rows of the same analysis and test."""
    data = SCRIPTS.parent / "ui_data"
    ids = {r["run_id"] for r in json.loads((data / "index.json").read_text())["runs"]}
    rows = json.loads((data / "fes_comparison.json").read_text())["rows"]
    seen: set[tuple[str, str, str]] = set()
    for r in rows:
        assert isinstance(r["run_ids"], list), r
        for run in r["run_ids"]:
            assert run in ids, run
            key = (run, r.get("analysis") or "primary", r["test"])
            assert key not in seen, key
            seen.add(key)
    # The four descending-orbit runs are declared and scored; round 6's ascending ones are not.
    index = {r["run_id"]: r for r in json.loads((data / "index.json").read_text())["runs"]}
    for d in ("angul", "dhenkanal", "kendujhar", "koraput"):
        assert index[f"odisha_v120_3ha_squares_{d}_keptland_s1desc"]["fes_declared"] is True
        assert index[f"odisha_v120_3ha_squares_{d}_keptland"]["fes_declared"] is False
