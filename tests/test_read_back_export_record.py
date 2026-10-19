"""What odisha_script/odisha_read_back_export.py records, offline.

Its main() is run here with every Earth Engine step stood in for: the pipeline run that rebuilds the
export pass's context, the export stage's ROI parts and layer builders, and the read of each layer.
The stand-ins give a run of one ROI part whose three layers are made up below; what is checked is
what the tool writes beside them (review of 19 Oct 2026, C30).
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "odisha_script"))
sys.path.insert(0, str(REPO / "scripts"))

CONFIG = REPO / "configs" / "odisha_v120_3ha_squares_koraput_keptland_s1desc.yaml"
NAME = CONFIG.stem


def _polygon(lat: float, lon: float, **props) -> dict:
    ring = [[lon, lat], [lon + 0.001, lat], [lon + 0.001, lat + 0.001], [lon, lat + 0.001], [lon, lat]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"centroid_lat": lat, "centroid_lon": lon, **props}}


# The three layers as the stand-in builders give them: stand 7 in two pieces, superpixel 12 in two.
LAYERS = {
    "stands_merged": [_polygon(20.3, 85.1, stand_lbl=7, stand_id=1), _polygon(20.2, 85.1, stand_lbl=7, stand_id=2),
                      _polygon(20.1, 85.1, stand_lbl=8, stand_id=3)],
    "stands_snic": [_polygon(20.3, 85.1, snic_label=12, stand_id=1), _polygon(20.2, 85.1, snic_label=12, stand_id=2),
                    _polygon(20.1, 85.1, snic_label=13, stand_id=3), _polygon(20.0, 85.1, snic_label=14, stand_id=4)],
    "stands_dissolved": [_polygon(20.3, 85.1, unit_id=1), _polygon(20.1, 85.1, unit_id=2)],
}
# What the export stage itself recorded in its manifest: no stand counts for the superpixels.
STAGE_COUNTS = {
    "stands_merged": {"n_features": 3, "n_stands": 2, "n_stands_split_into_pieces": 1, "max_pieces_per_stand": 2},
    "stands_snic": {"n_features": 4},
    "stands_dissolved": {"n_features": 2},
}


class _Result:
    def __init__(self, context):
        self.context = context
        self.stages = [
            types.SimpleNamespace(name="segmentation", cache_status={"snic_clusters": "hit"},
                                  metadata={"source": "cache"}),
            types.SimpleNamespace(name="merge", cache_status={}, metadata={}),
        ]


@pytest.fixture
def tool(monkeypatch, tmp_path):
    """The tool's module, with Earth Engine stood in for; returns (module, vectors dir, runs dir)."""
    import ee
    import ee_read_only
    import odisha_phase2_2_run_pipeline as runner
    import odisha_read_back_export as tool_module

    import fmu.pipeline
    import fmu.stages.export as export_stage
    import fmu.utils.gee
    import fmu.utils.logging

    vectors, runs = tmp_path / "vectors", tmp_path / "runs"
    vectors.mkdir()
    runs.mkdir()

    class _Pipeline:
        def __init__(self, **kwargs):
            pass

        def run(self, config, run_dir, initial_context):
            ctx = initial_context
            ctx.set("merge_diagnostics", {"n_stands": 2})
            ctx.set("stand_attributes", {"7": {}, "8": {}})
            ctx.set("stand_provenance", {"7": {}, "8": {}})
            return _Result(ctx)

    monkeypatch.setattr(fmu.utils.gee, "init_gee", lambda *a, **k: None)
    monkeypatch.setattr(fmu.utils.gee, "load_roi_geometry", lambda *a, **k: "roi")
    monkeypatch.setattr(ee.data, "setDeadline", lambda ms: None)
    monkeypatch.setattr(ee_read_only, "forbid_writes", lambda: None)
    monkeypatch.setattr(runner, "missing_cache", lambda *a, **k: [])
    monkeypatch.setattr(runner, "to_wgs84", lambda fc: fc)
    monkeypatch.setattr(runner, "sample_rasters_at_plots", lambda cfg, ctx: None)
    monkeypatch.setattr(fmu.utils.logging, "init_logging", lambda **k: tmp_path / "tool_run")
    monkeypatch.setattr(fmu.pipeline, "Pipeline", _Pipeline)
    monkeypatch.setattr(export_stage, "_roi_parts", lambda roi, scale: ["part"])
    for layer in LAYERS:
        builder = f"_build_{layer.removeprefix('stands_')}_feature_collection"
        monkeypatch.setattr(export_stage, builder, lambda *, ctx, config, scale, region, _layer=layer: _layer)
    monkeypatch.setattr(tool_module, "read_layer", lambda fc, context: json.loads(json.dumps(LAYERS[fc])))
    return tool_module, vectors, runs


def _write_export_manifest(runs: Path) -> None:
    """The manifest of the run's export pass, whose export stage counted the layers."""
    d = runs / f"{NAME}_20261015_120000"
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps({"config_name": NAME, "stages": [
        {"name": "segmentation", "metadata": {"source": "cache"}},
        {"name": "export", "metadata": {"manifest": {"vector_layers": STAGE_COUNTS}}}]}))


def _main(tool_module, vectors: Path, runs: Path, monkeypatch) -> int:
    monkeypatch.chdir(REPO)
    monkeypatch.setattr(sys, "argv", ["odisha_read_back_export.py", "--config", str(CONFIG),
                                      "--vectors-dir", str(vectors), "--runs-dir", str(runs)])
    return tool_module.main()


def test_the_record_keeps_the_export_stages_counts_apart_from_the_tools_own(tool, monkeypatch):
    """Review C30: the record put the tool's own counts of what it read back under
    export_vector_layers, the key under which the runner records the export stage's counts; for
    the superpixels that gave n_stands and a split count the export stage never makes (8,723 in
    the committed Koraput records)."""
    tool_module, vectors, runs = tool
    (vectors / f"{NAME}_stands_merged.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": LAYERS["stands_merged"]}))  # the run wrote this one
    _write_export_manifest(runs)
    assert _main(tool_module, vectors, runs, monkeypatch) == 0
    record = json.loads((vectors / f"{NAME}_run.json").read_text())
    assert record["export_vector_layers"]["stands_snic"] == {
        "n_features": 4, "n_stands": None, "n_stands_split_into_pieces": None}
    assert record["export_vector_layers"]["stands_merged"] == {
        "n_features": 3, "n_stands": 2, "n_stands_split_into_pieces": 1}
    counts = record["read_back"]["layer_counts"]
    assert counts["stands_snic"] == {"n_features": 4, "n_stands": 3, "n_stands_split_into_pieces": 1}
    assert counts["stands_dissolved"] == {"n_features": 2, "n_stands": None, "n_stands_split_into_pieces": None}
    assert record["pulled_polygon_counts"] == {"stands_merged": 3, "stands_snic": 4, "stands_dissolved": 2}
    assert record["read_back"]["layers_the_run_wrote"] == ["stands_merged"]
    assert record["read_back"]["read_back_against_the_layers_the_run_wrote"]["stands_merged"]["equal"] is True


def test_the_export_stages_counts_come_from_the_newest_manifest_whose_export_stage_ran(tmp_path):
    import odisha_read_back_export as tool_module

    runs = tmp_path / "runs"
    runs.mkdir()
    _write_export_manifest(runs)
    later = runs / f"{NAME}_20261015_130000"  # a later pass that stopped before the export stage
    later.mkdir()
    (later / "manifest.json").write_text(json.dumps({"stages": [{"name": "segmentation"}]}))
    (runs / f"{NAME}_repro_20261016_000000").mkdir()  # another config's folder
    (runs / f"{NAME}_repro_20261016_000000" / "manifest.json").write_text(json.dumps({"stages": [
        {"name": "export", "metadata": {"manifest": {"vector_layers": {"stands_snic": {"n_features": 9}}}}}]}))
    manifests = tool_module.run_manifests(runs, NAME)
    assert [name for name, _ in manifests] == [f"{NAME}_20261015_120000", f"{NAME}_20261015_130000"]
    assert tool_module.export_stage_counts(manifests)["stands_snic"] == {
        "n_features": 4, "n_stands": None, "n_stands_split_into_pieces": None}
    assert tool_module.export_stage_counts(manifests[1:]) is None


def test_without_an_export_manifest_the_export_stages_counts_are_not_made_up(tool, monkeypatch):
    tool_module, vectors, runs = tool
    assert _main(tool_module, vectors, runs, monkeypatch) == 0
    record = json.loads((vectors / f"{NAME}_run.json").read_text())
    assert record["export_vector_layers"] is None
    assert "no run folder" in record["read_back"]["export_vector_layers_from"]


def test_a_run_record_the_run_wrote_is_kept_and_the_comparison_goes_beside_it(tool, monkeypatch):
    """Review C30: when the run had written its own record, the tool kept it, rightly, but the
    comparison of what it read back with the run's layers went to the terminal only."""
    tool_module, vectors, runs = tool
    for layer, features in LAYERS.items():
        (vectors / f"{NAME}_{layer}.geojson").write_text(json.dumps(
            {"type": "FeatureCollection", "features": features}))
    run_record = vectors / f"{NAME}_run.json"
    run_record.write_text('{"written by": "the run"}\n')
    assert _main(tool_module, vectors, runs, monkeypatch) == 0
    assert run_record.read_text() == '{"written by": "the run"}\n'
    read_back = json.loads((vectors / f"{NAME}_read_back.json").read_text())
    assert read_back["config"] == NAME and "commit" in read_back["git"]
    assert read_back["read_back"]["layers_read_back"] == []
    assert sorted(read_back["read_back"]["read_back_against_the_layers_the_run_wrote"]) == sorted(LAYERS)
    assert all(r["equal"] for r in read_back["read_back"]["read_back_against_the_layers_the_run_wrote"].values())
    assert read_back["read_back"]["layer_counts"]["stands_snic"]["n_stands"] == 3
