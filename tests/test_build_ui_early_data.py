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
    runs = [r for r in index["runs"] if r.get("kept_land") and r["roi"] == "boxes"
            and r["group"] == "earlier"]
    # Round 6's four, and round 7's four on the descending radar orbit (R3's own are below).
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
        # Round 11: the box_runs rows are the 13 Oct box stands, a comparison and not a declared score.
        assert r["stands"] == (builder.BOX_RUNS_STANDS if r["analysis"] == "box_runs"
                               else "15 Oct 2026 kept-land runs (descending radar)")
        assert r["declaration"] == "odisha_script/PHASE_KEPTLAND_PREDECLARED.md"
        assert r["run_ids"] == sorted(builder.KEPTLAND_S1DESC_RUNS)
    assert sum(r["analysis"] == "box_runs" for r in rows) == 5
    assert "13 Oct 2026 box runs" in builder.BOX_RUNS_STANDS
    assert "not a declared score" in builder.BOX_RUNS_STANDS


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


# ---------------------------------------------------------------- R3 on the site (round 15)


DATA = SCRIPTS.parent / "ui_data"
R3_RECORDS = SCRIPTS.parent / "docs" / "reproducibility" / "r14_runs" / "second_half"


def _index() -> dict:
    return json.loads((DATA / "index.json").read_text())


def test_the_site_holds_r3s_eighteen_runs_as_current_and_the_earlier_28_as_history():
    index = _index()
    current = [r for r in index["runs"] if r["group"] == "current"]
    earlier = [r for r in index["runs"] if r["group"] == "earlier"]
    assert sorted(r["run_id"] for r in current) == sorted(
        p.name.removesuffix("_manifest_export.json")
        for p in R3_RECORDS.glob("*_r14_manifest_export.json"))
    assert len(current) == 18 and len(earlier) == 28
    # By area, arm and stand size, each choice has one run.
    keys = [(r["area"], r["arm"], r["stand_ceiling_ha"]) for r in current]
    assert len(set(keys)) == 18
    assert {r["area"] for r in current} == {"Sanjay Van", "Angul", "Dhenkanal", "Kendujhar",
                                            "Koraput"}
    for r in earlier:
        # One line: what the run is, and that it is from before the corrections (question 23).
        assert r["history"].endswith(" Its results are from before the corrections of 19 to 28 "
                                     "Oct 2026.")
        assert r["history"].count(".") == 2 or "round 7's" in r["history"]
    assert [x["path"] for x in index["history_links"]] == [
        "docs/handoff/2026-10-20-round13.md", "docs/handoff/2026-10-26-round14.md"]
    for path in [x["path"] for x in index["history_links"]] + [index["what_changed"]["review"]]:
        assert (SCRIPTS.parent / path).is_file(), path
    for group in index["what_changed"]["groups"]:
        assert (SCRIPTS.parent / group["record"]).is_file()
        # One plain sentence each, naming the finding or the live check it comes from.
        assert all(item["ref"] and item["text"].count(". ") == 0 for item in group["items"])


def test_each_r3_run_gives_k_with_jaskarans_reason_from_the_register():
    import yaml

    register = {d["id"]: d for d in yaml.safe_load(
        (SCRIPTS.parent / "docs" / "decisions.yaml").read_text())["decisions"]}
    for r in [r for r in _index()["runs"] if r["group"] == "current"]:
        kr = r["k_reason"]
        assert kr["k"] == r["k"] == r["facts"]["k"] == 5
        entry = register[kr["register"]]
        assert kr["reason"] in " ".join(entry["rationale"].split())
        assert (SCRIPTS.parent / kr["report"]).is_file()
        if r["area"] == "Sanjay Van":
            assert kr["reason"] == "the knee is 5 in both arms."
        else:
            size = "10 ha" if r["stand_ceiling_ha"] == 10.0 else "3 ha"
            assert kr["register"].endswith("part-2-of-the-elbow-report" if size == "10 ha"
                                           else "part-1-of-the-elbow-report")


def test_r3_score_rows_are_their_sets_files_with_the_chance_test_and_c1():
    rows = [r for r in json.loads((DATA / "fes_comparison.json").read_text())["rows"]
            if r.get("set")]
    ids = {r["run_id"]: r for r in _index()["runs"]}
    stat = {"drawing_all_plots": "delin_all", "drawing_multi_plot": "delin_multi",
            "pair_precision": "prec", "labelling_district": "lab_wmean", "far_apart": "far_gap"}
    sets = sorted({r["set"] for r in rows})
    assert sets == ["keptland_alphaearth_10ha_r14", "keptland_alphaearth_r14",
                    "keptland_s1desc_10ha_r14", "keptland_s1desc_r14"]
    scores_dir = SCRIPTS.parent / "odisha_script" / "keptland_scores"
    for stem in sets:
        scores = {a["analysis"]: a for a in json.loads(
            (scores_dir / f"{stem}_scores.json").read_text())["analyses"]}
        chance = json.loads((scores_dir / f"{stem}_chance.json").read_text())
        mine = [r for r in rows if r["set"] == stem]
        assert len(mine) == 5 * len(scores) + 1
        for r in mine:
            assert r["run_ids"] == sorted(chance["runs"])
            assert all(ids[x]["group"] == "current" for x in r["run_ids"])
            if r["analysis"] == "C1":
                c1 = chance["checks"]["C1"]
                assert (r["score"], r["chance_percentile"], r["p"], r["p_holm"]) == (
                    c1["observed"], c1["pctile"], c1["p"], None)
                continue
            assert r["score"] == scores[r["analysis"]][stat[r["test"]]]
            tested = chance["analyses"].get(r["analysis"])
            if tested is None:
                assert (r["chance_percentile"], r["p"], r["p_holm"]) == (None, None, None)
            else:
                c = tested["scores"][stat[r["test"]]]
                assert (r["chance_percentile"], r["p"], r["p_holm"]) == (c["pctile"], c["p"],
                                                                          c["holm_p"])


def test_r3_plots_take_their_sets_declared_join():
    for r in [r for r in _index()["runs"] if r["group"] == "current" and r["site"] == "Odisha"]:
        stem = ("keptland_" + ("alphaearth" if r["arm"] == "alphaearth" else "s1desc")
                + ("_10ha" if r["stand_ceiling_ha"] == 10.0 else "") + "_r14")
        joined = {row["plot_key"]: row for row in builder_csv(
            SCRIPTS.parent / "odisha_script" / "keptland_scores" / f"{stem}_joined.csv")}
        plots = json.loads((DATA / "by_run" / r["run_id"] / "plots.geojson").read_text())
        stands = {f["properties"]["stand_id"]: f["properties"]["stand_type"] for f in json.loads(
            (DATA / "by_run" / r["run_id"] / "stands.json").read_text())["features"]}
        on_stand = 0
        for f in plots["features"]:
            p = f["properties"]
            row = joined.get(p["plot_key"])
            if row is None or row["how"] == "none":
                assert p["stand_id"] is None
                continue
            on_stand += 1
            assert p["stand_id"] == int(float(row["sid"]))
            assert p["stand_type"] == stands[p["stand_id"]]
            assert p["join_m"] == (round(float(row["dist_m"]), 1) if row["how"] == "within" else 0.0)
        assert on_stand == r["facts"]["plots_with_stand"]


def builder_csv(path: Path) -> list[dict]:
    import csv

    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def test_r3_stands_give_angles_by_sine_and_cosine_and_earlier_runs_by_plain_means():
    for r in _index()["runs"]:
        stands = json.loads((DATA / "by_run" / r["run_id"] / "stands.json").read_text())
        props = stands["features"][0]["properties"]
        if r["group"] == "current" and r["arm"] == "feature_vector":
            assert r["angles"] == "sin_cos"
            assert {"aspect_sin", "aspect_cos", "ndvi_phase_annual_sin",
                    "ndvi_phase_annual_cos"} <= props.keys()
            # The four are not measurements of their own: 22, as the earlier runs count.
            assert r["facts"]["n_feature_bands"] == 22
            assert r["ndvi_mean"] == {"what": "window_mean", "from": "2017-01-01",
                                      "to": "2022-12-31"}
        elif r["group"] == "earlier":
            assert r.get("angles") in (None, "plain")
            assert not any(k.endswith(("_sin", "_cos")) for k in props)
            assert r["ndvi_mean"] == {"what": "trend_value", "on": "2017-01-01"}


def test_r3_stands_without_a_type_are_the_ones_its_clustering_had_no_row_for():
    for r in [r for r in _index()["runs"] if r["group"] == "current"]:
        stands = json.loads((DATA / "by_run" / r["run_id"] / "stands.json").read_text())
        untyped = [f["properties"] for f in stands["features"]
                   if f["properties"]["stand_type"] is None]
        assert len(untyped) == r["facts"]["n_untyped_stands"] == r["facts"]["untyped_no_data"]
        assert all(p["below_min"] for p in untyped)
        assert all(p.get("below_why") in ("isolated", "area_blocked") for p in untyped)
    sv = next(r for r in _index()["runs"] if r["run_id"] == "sanjay_van_baseline_keptland_r14")
    assert sv["facts"]["n_untyped_stands"] == 86


def test_no_file_of_the_site_data_is_over_5_mb():
    big = [p for p in DATA.rglob("*") if p.is_file() and p.stat().st_size > 5 * 1024 * 1024]
    assert big == []


def test_k_reason_takes_the_item_that_names_the_run_and_checks_its_k(builder):
    got = builder.k_reason(3.0, 5)
    assert got["reason"].startswith("the pooled knee is 5 in both arms")
    assert "Sanjay Van" not in got["reason"] and not got["reason"].endswith('"')
    assert builder.k_reason("sanjay_van", 5)["reason"] == "the knee is 5 in both arms."
    with pytest.raises(SystemExit, match="does not give k = 6"):
        builder.k_reason(10.0, 6)


def test_a_mask_on_a_projected_grid_is_drawn_in_longitude_and_latitude(builder):
    """An R3 area's mask is on its asset's UTM grid; its shapes come out in degrees, on that grid's
    pixel edges."""
    from rasterio.crs import CRS

    band = np.array([[1, 1], [2, 1]], dtype="uint8")
    utm = CRS.from_epsg(32645)
    got = builder.class_shapes(band, band > 0, from_origin(300000, 2300000, 10, 10),
                               {1: "a", 2: "b"}, utm)
    ring = _decode(got["classes"][1]["polygons"][0][0])
    from pyproj import Transformer

    fwd = Transformer.from_crs("EPSG:4326", utm, always_xy=True).transform
    # Class 2's one pixel, back on the grid to the metre (six decimals of a degree are ~0.1 m).
    corners = {tuple(float(round(v)) for v in fwd(lon, lat)) for lat, lon in ring}
    assert corners == {(300000.0, 2299990.0), (300010.0, 2299990.0), (300010.0, 2299980.0),
                       (300000.0, 2299980.0)}
    assert all(20 < lat < 21 and 85 < lon < 86 for lat, lon in ring)  # UTM 45N, 200 km west of 87 E


def _decode(s: str) -> list[tuple[float, float]]:
    out, i, lat, lng = [], 0, 0, 0
    while i < len(s):
        vals = []
        for _ in range(2):
            shift = result = 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            vals.append(~(result >> 1) if result & 1 else result >> 1)
        lat, lng = lat + vals[0], lng + vals[1]
        out.append((lat / 1e6, lng / 1e6))
    return out


def test_an_earlier_runs_line_says_what_it_is(builder):
    builder.AREAS.update({"sv": {"site": "Sanjay Van"}, "od": {"site": "Odisha"}})
    assert "whole rectangle" in builder.history_line("sanjay_van_baseline_repro", "sv")
    assert "village outlines" in builder.history_line("odisha_v120_3ha_angul_repro", "od")
    assert "13 Oct 2026 on the boxes" in builder.history_line("odisha_v120_3ha_squares_angul", "od")
    assert "ascending" in builder.history_line("odisha_v120_3ha_squares_angul_keptland", "od")
    assert "descending" in builder.history_line("odisha_v120_3ha_squares_angul_keptland_s1desc",
                                                "od")
    assert "Sanjay Van's rectangle" in builder.history_line("sanjay_van_baseline_keptland", "sv")


def test_the_build_record_names_the_code_and_the_r3_rasters_off_git(builder, tmp_path):
    """Round 13's question 28 (spec-ui-data-build-record-in-docs-in-a-later-round): the record of a
    build of ui_data/, written outside it, with the files off git that the build read for R3."""
    import hashlib

    area = tmp_path / "ui_data_full" / "r14_areas" / "angul"
    area.mkdir(parents=True)
    (area / "part01_x_true_colour.tif").write_bytes(b"tif")
    (area / "fetch_record.json").write_text(json.dumps(
        {"runs_served": ["a_r14"], "keys": {"masking": "s1"}, "assets_opened": ["x"], "git": {}}))
    runs = [{"run_id": "a_r14", "group": "current"}, {"run_id": "b", "group": "earlier"}]
    rec = builder.build_record({"commit": "c0ffee", "dirty": False}, runs)
    assert rec["git"] == {"commit": "c0ffee", "dirty": False}
    assert rec["runs"] == {"current": ["a_r14"], "earlier": ["b"]}
    assert rec["r3_display_rasters"]["areas"]["angul"]["runs_served"] == ["a_r14"]
    assert rec["r3_display_rasters"]["files_off_git"] == [
        {"file": "r14_areas/angul/part01_x_true_colour.tif", "bytes": 3,
         "sha256": hashlib.sha256(b"tif").hexdigest()}]
    assert {"command", "date", "environment"} <= rec.keys()
    assert builder.BUILD_RECORD.parent.name == "reproducibility"


def test_r3_steps_name_the_register_entries_behind_what_r3_computes():
    """Review of round 15, L3: every decision a step names is in the register; R3's clustering
    step names the round 14 method changes and the run's own k entry."""
    import yaml

    register = {d["id"] for d in yaml.safe_load(
        (SCRIPTS.parent / "docs" / "decisions.yaml").read_text())["decisions"]}
    for r in _index()["runs"]:
        for step in r["steps"]:
            assert set(step["decisions"]) <= register, (r["run_id"], step["step"])
        if r["group"] == "current":
            (clustering,) = [s for s in r["steps"] if s["step"] == "clustering"]
            assert {"spec-clustering-kmeans-outside-earth-engine",
                    "spec-clustering-log-rule-right-skewed-bands", "spec-k-elbow-in-the-fits-space",
                    r["k_reason"]["register"]} <= set(clustering["decisions"])


def test_r3_superpixel_layers_lack_only_the_untyped_stands_superpixels():
    """Review of round 15, L4: the map draws the superpixels of the run's layer; those it has no
    polygon for are the superpixels of the stands with no type."""
    for r in [r for r in _index()["runs"] if r["group"] == "current"]:
        f = r["facts"]
        missing = f["n_superpixels"] - f["superpixels_in_layer"]
        assert missing == f["n_untyped_stands"]
        assert f["superpixels_missing_are_untyped"] is (missing > 0)
    sv = next(r for r in _index()["runs"] if r["run_id"] == "sanjay_van_baseline_keptland_r14")
    assert (sv["facts"]["n_superpixels"], sv["facts"]["superpixels_in_layer"]) == (1200, 1114)


def test_what_changed_says_k_was_chosen_before_r3s_field_scores():
    """Review of round 15, H2: the _r9 scores existed when k was chosen; R3's did not."""
    texts = [i["text"] for g in _index()["what_changed"]["groups"] for i in g["items"]]
    assert any("before any of R3's field scores" in t for t in texts)
    assert not any("before any field score" in t for t in texts)
    page = (SCRIPTS.parent / "ui" / "explorer.html").read_text()
    assert "before any field score" not in page


# ---------------------------------------------------------------- round 16


def test_round_7s_line_points_to_r3s_run_of_the_same_boxes(builder, monkeypatch):
    """Round 15's question 1 (b), site-round-7-runs-point-to-r3s-scores: a round-7 run's line says
    its scores are round 7's, kept as history; that the record is R3's scores, on R3's run of the
    same boxes, features and stand size, by name; that the _r9 scores are not on the site; and that
    the chance test was not run on these stands. The build stops if that R3 run is not R3's."""
    run = "odisha_v120_3ha_squares_angul_keptland_s1desc"
    monkeypatch.setattr(builder, "RUNS", [{"run_id": f"{run}_r14", "r3": True}])
    note = builder.s1desc_note(run)
    assert "Its field-check scores here are round 7's, kept as history." in note
    assert (f"The record is R3's scores, on R3's run of the same boxes, features and stand size, "
            f"{run}_r14.") in note
    assert "The _r9 scores, the record from before the corrections, are not on this site." in note
    assert "The chance test was not run on these stands, so their scores are numbers only." in note
    assert "does not show" not in note
    monkeypatch.setattr(builder, "RUNS", [{"run_id": f"{run}_r14"}])
    with pytest.raises(SystemExit, match="not among R3's runs"):
        builder.s1desc_note(run)


def test_round_7s_field_check_points_to_r3s_run_and_says_the_r9_scores_are_not_on_the_site():
    """Round 15's question 1 (b): the score card of round 7's four runs."""
    page = (SCRIPTS.parent / "ui" / "explorer.html").read_text()
    assert "which this site does not show" not in page
    assert "the record is the scores on their re-runs" not in page
    card = page[page.index("These are round 7's scores"):]
    card = card[:card.index("</p>")]
    assert "kept as history" in card
    assert ('The record is R3\'s scores, on R3\'s run of the same boxes, features and stand size, '
            '${runLink(run().run_id + "_r14")}.') in card
    assert "The _r9 scores, the record from before the corrections, are not on this site." in card
    assert "The chance test was not run on these stands, so these scores are numbers only" in card


def _small_stands(tmp_path, run_id: str, whys: list[str]) -> Path:
    """A stand layer as the merge writes it: one stand per entry of `whys`, below the minimum where
    the entry says why ("isolated" or "area_blocked"), at or over it where it is ""."""
    square = [[[77.0, 28.0], [77.001, 28.0], [77.001, 28.001], [77.0, 28.001], [77.0, 28.0]]]
    feats = [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": square},
              "properties": {"stand_id": sid, "stand_lbl": sid, "area_ha": 0.5 if why else 2.0,
                             "cluster_id": 0, "n_superpx": 1, "n_pass1": 0, "n_relaxed": 0,
                             "n_fallback": 0, "below_min": int(bool(why)), "below_why": why,
                             "canopy_height": 6.0}}
             for sid, why in enumerate(whys)]
    (tmp_path / f"{run_id}_stands_merged.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}))
    return tmp_path


def test_an_earlier_kept_land_run_says_which_small_stands_were_too_big_to_take(builder, tmp_path):
    """Round 15's question 5 (b), site-earlier-keptland-small-stands-counted-apart: an earlier
    kept-land run whose merge left stands every neighbour was too big to take says of each small
    stand why it stayed small, as R3's runs do; one whose merge left none keeps the flag alone, so
    its popups keep their one sentence. The build stops if the layer and the merge disagree."""
    vec = _small_stands(tmp_path, "k_run", ["", "isolated", "area_blocked"])
    fc, _ = builder.run_stands("k_run", "feature_vector", vec, keptland=True, blocked=1)
    assert [f["properties"].get("below_why") for f in fc["features"]] == [None, "isolated",
                                                                          "area_blocked"]
    assert "below_why" not in fc["features"][0]["properties"]
    fc, _ = builder.run_stands("k_run", "feature_vector", vec, keptland=True)
    assert all("below_why" not in f["properties"] for f in fc["features"])
    assert [f["properties"]["below_min"] for f in fc["features"]] == [False, True, True]
    with pytest.raises(SystemExit, match="its merge counted 2"):
        builder.run_stands("k_run", "feature_vector", vec, keptland=True, blocked=2)
    # R3's runs say why in every run, as before, and are checked the same way.
    fc, _ = builder.run_stands("k_run", "feature_vector", vec, keptland=True, r3=True, blocked=1)
    assert [f["properties"].get("below_why") for f in fc["features"]][1:] == ["isolated",
                                                                              "area_blocked"]
    with pytest.raises(SystemExit, match="its merge counted 0"):
        builder.run_stands("k_run", "feature_vector", vec, keptland=True, r3=True)
    # A run that is not kept-land carries no flag, whatever its merge counted.
    fc, _ = builder.run_stands("k_run", "feature_vector", vec, blocked=1)
    assert all("below_min" not in f["properties"] and "below_why" not in f["properties"]
               for f in fc["features"])


def test_the_page_counts_every_kept_land_runs_small_stands_in_two_kinds():
    """Round 15's question 5 (b): the Stands step and the size chart count the two kinds apart on
    the earlier kept-land runs too, not on R3's alone (as 406e2e6, the review's M1, had made it)."""
    page = (SCRIPTS.parent / "ui" / "explorer.html").read_text()
    assert "const blocked = has(f.below_min_blocked) ? f.below_min_blocked : 0;" in page
    assert 'r.group === "current" && has(f.below_min_blocked)' not in page
    assert 'which stayed small ${f.below_min_blocked ? `because they share no edge' in page
    assert 'r.group === "current" && f.below_min_blocked' not in page
