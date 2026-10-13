"""scripts/snic_cached_vs_live.py must stay read-only: it is run while batch jobs are queued.

The comparison itself needs Earth Engine and is not run here.
"""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "snic_cached_vs_live.py"


def test_the_script_cannot_submit_a_task_or_write_an_asset():
    src = SCRIPT.read_text()
    for forbidden in ("ee.batch", "Export.", "start_export", "copyAsset", "deleteAsset",
                      "createFolder", "createAsset"):
        assert forbidden not in src, forbidden


def test_every_pipeline_it_builds_is_read_only():
    code = SCRIPT.read_text().split('"""', 2)[2]  # the code after the module docstring
    calls = [line for line in code.splitlines() if "Pipeline(" in line]
    assert calls, "expected the script to build a Pipeline"
    assert all("submit_exports=False" in line for line in calls), calls
