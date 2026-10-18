"""scripts/eecu_by_stage.py, offline: the stage each task is given to, the pass spans, the sums.

No Earth Engine call: the task list and the wrapper log are made up here.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("eecu_by_stage", REPO / "scripts" / "eecu_by_stage.py")
assert _spec and _spec.loader
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)

CFG = "odisha_v120_3ha_tile10km_angul_keptland_s1desc_r9"


@pytest.mark.parametrize(("output", "stage"), [
    ("masking_habitat_mask", "masking"),
    ("data_load_s2_composite", "data_load"),
    ("features_optical_optical_features", "features_optical"),
    ("features_static_static_features", "features_static"),
    ("features_embedding_embedding_features", "features_embedding"),
    ("segmentation_snic_means", "segmentation"),
    ("clustering_feature_stack", "clustering"),
    ("features_raw", "export"),
    ("features_scaled", "export"),
    ("cluster_labels", "export"),
    ("stands_merged_geojson", "export"),
    ("something_else", "other: something_else"),
])
def test_each_task_goes_to_the_stage_its_description_names(output, stage):
    assert E.stage_of(output) == stage


def test_the_pass_spans_run_from_one_start_to_the_next_and_the_last_to_the_end():
    log = "\n".join([
        "[run_passes_safely 2026-10-18 16:29:54] batch i_tile started from commit be36f74",
        f"##### PASS1 {CFG} :: features :: 16:29:57 #####",
        f"##### PASS1 {CFG} :: segmentation :: 16:54:45 #####",
        "##### PASS1 another_config :: features :: 16:55:00 #####",
        f"##### PASS1 {CFG} :: export :: 17:10:00 #####",
        "[run_passes_safely 2026-10-18 17:20:30] batch i_tile ended: ALL CONFIGS COMPLETE",
    ])
    spans = E.pass_spans(log, CFG)
    assert [s[0] for s in spans] == ["features", "segmentation", "export"]
    assert spans[0][1] == datetime(2026, 10, 18, 10, 59, 57, tzinfo=UTC)  # 16:29:57 IST
    assert spans[0][2] == spans[1][1] and spans[1][2] == spans[2][1]
    assert spans[2][2] == datetime(2026, 10, 18, 11, 50, 30, tzinfo=UTC)


def test_a_log_without_the_config_is_refused():
    with pytest.raises(ValueError):
        E.pass_spans("[run_passes_safely 2026-10-18 16:29:54] batch x ended", CFG)


def test_batch_hours_are_summed_by_stage_failed_tasks_included_others_left_out():
    def op(desc, seconds, state="SUCCEEDED"):
        return {"metadata": {"description": desc, "batchEecuUsageSeconds": seconds, "state": state}}

    ops = [op(f"{CFG}_data_load_s2_composite", 7200), op(f"{CFG}_data_load_s2_composite", 3600, "FAILED"),
           op(f"{CFG}_stands_merged_shp", 36), op(f"{CFG}_features_raw", 360),
           op("odisha_v120_3ha_squares_angul_keptland_s1desc_r9_data_load_s2_composite", 9999)]
    hours, tasks = E.batch_by_stage(ops, CFG)
    assert hours == {"data_load": 3.0, "export": 0.11}
    assert [t["state"] for t in tasks["data_load"]] == ["SUCCEEDED", "FAILED"]
    result = E.summary(CFG, 10_000.0, hours, [("features", 0.5), ("export", 0.1)], tasks)
    assert result["batch_total"] == 3.11 and result["online_total"] == 0.6 and result["total"] == 3.71
    assert result["batch_eecu_h_per_1000_ha"]["data_load"] == 0.3
    assert result["total_per_1000_ha"] == 0.371
    assert "read_at" not in result and "from" not in str(result["online_eecu_h_by_pass"])
