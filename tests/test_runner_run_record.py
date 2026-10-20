"""The run record the export pass of odisha_script/odisha_phase2_2_run_pipeline.py writes, offline.

Its main() is run with every Earth Engine step stood in for (the pipeline run, the cache layout, the
read-back of the layers, the plots); what is checked is the record it writes (review of 19 Oct 2026,
C36).
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "odisha_script"))

CONFIG = REPO / "configs" / "odisha_v120_3ha_squares_angul_keptland_s1desc_r9.yaml"
NAME = CONFIG.stem
KEY = "s0123456789"  # the step key the export pass read the superpixels under


def _segmentation_pass(runs: Path, folder: str, key: str, scale: float) -> None:
    """The manifest of a segmentation pass that computed the superpixels and exported them."""
    d = runs / f"{NAME}_{folder}"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"config_name": NAME, "stages": [
        {"name": "segmentation", "metadata": {"distance_scale": scale},
         "cache_status": {"snic_clusters": "miss-exported", "snic_means": "miss-exported"},
         "export_tasks": [{"asset_path": f"projects/p/assets/fmu/{NAME}/segmentation/snic_clusters__{key}"},
                          {"asset_path": f"projects/p/assets/fmu/{NAME}/segmentation/snic_means__{key}"}]}]}))


@pytest.fixture
def runner(monkeypatch, tmp_path):
    """The runner's module with Earth Engine stood in for; returns (module, runs dir, vectors dir)."""
    import odisha_phase2_2_run_pipeline as module

    from fmu.stages.base import PipelineContext

    runs, vectors = tmp_path / "runs", tmp_path / "vectors"
    runs.mkdir()
    vectors.mkdir()
    this_pass = runs / f"{NAME}_20261018_120000"

    class _Pipeline:
        def __init__(self, **kwargs):
            pass

        def run(self, config, run_dir, initial_context):
            ctx = initial_context if initial_context is not None else PipelineContext()
            for key in ("merge_diagnostics", "stand_attributes", "stand_provenance"):
                ctx.set(key, {})
            stages = [
                types.SimpleNamespace(name="segmentation", cache_status={"snic_clusters": "hit"},
                                      metadata={"source": "cache"}, cache_key=KEY, export_tasks=[]),
                types.SimpleNamespace(name="export", cache_status={}, cache_key=None, export_tasks=[],
                                      metadata={"manifest": {"vector_layers": {}, "drive_exports": {}}}),
            ]
            return types.SimpleNamespace(stages=stages, context=ctx)

    def init_logging(**kwargs):
        this_pass.mkdir()
        return this_pass

    monkeypatch.setattr(module, "init_gee", lambda *a, **k: None)
    monkeypatch.setattr(module, "cache_layout_for", lambda cfg: ("per_step", "no legacy asset"))
    monkeypatch.setattr(module, "missing_cache", lambda *a, **k: [])
    monkeypatch.setattr(module, "load_roi_geometry", lambda *a, **k: "roi")
    monkeypatch.setattr(module, "init_logging", init_logging)
    monkeypatch.setattr(module, "Pipeline", _Pipeline)
    monkeypatch.setattr(module, "pull_vectors", lambda cfg, ctx: {"stands_merged": 0})
    monkeypatch.setattr(module, "sample_rasters_at_plots", lambda cfg, ctx: None)
    monkeypatch.setattr(module, "environment_state", lambda: {"python": "stood in for"})
    monkeypatch.setattr(module, "VECTOR_DIR", vectors)
    monkeypatch.chdir(REPO)
    monkeypatch.setattr(sys, "argv", ["odisha_phase2_2_run_pipeline.py", "--config", str(CONFIG),
                                      "--through", "export"])
    return module, runs, vectors


def test_the_export_pass_records_the_scale_its_superpixels_were_drawn_with(runner):
    """Review C36: snic_distance_scale was null in every run record. The record is written by the
    export pass, which reads segmentation from the cache, so the stage's metadata there is
    {'source': 'cache'}; the scale is in the manifest of the pass that made the superpixels."""
    module, runs, vectors = runner
    _segmentation_pass(runs, "20261018_100000", "s9999999999", 9.9)  # under an earlier key
    _segmentation_pass(runs, "20261018_110000", KEY, 1.3937265399261327)
    assert module.main() == 0
    record = json.loads((vectors / f"{NAME}_run.json").read_text())
    assert record["snic_distance_scale"] == 1.3937265399261327
    assert record["snic_distance_scale_from"] == (
        f"the manifest of the segmentation pass that exported segmentation/snic_clusters__{KEY}")


def test_without_that_manifest_the_scale_is_null_and_the_record_says_why(runner):
    module, runs, vectors = runner
    _segmentation_pass(runs, "20261018_100000", "s9999999999", 9.9)
    assert module.main() == 0
    record = json.loads((vectors / f"{NAME}_run.json").read_text())
    assert record["snic_distance_scale"] is None
    assert record["snic_distance_scale_from"].startswith("not found")
