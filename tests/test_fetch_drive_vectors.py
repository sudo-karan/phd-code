"""Non-live tests for scripts/fetch_drive_vectors.py pure logic.

Only the filename normalization + newest-per-layer selection are tested here;
the Drive API calls need auth and are exercised manually.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from fetch_drive_vectors import canonical_name, select_targets  # noqa: E402


def test_canonical_strips_dup_markers_before_and_after_extension():
    assert canonical_name("x_stands_dissolved.geojson") == "x_stands_dissolved.geojson"
    assert canonical_name("x_stands_dissolved(1).geojson") == "x_stands_dissolved.geojson"
    assert canonical_name("x_stands_dissolved.geojson(2)") == "x_stands_dissolved.geojson"


def test_select_targets_keeps_newest_and_geojson_only():
    files = [
        {"name": "sanjay_van_baseline_stands_dissolved.geojson", "modifiedTime": "2026-07-22T16:18:00Z"},
        {"name": "sanjay_van_baseline_stands_dissolved.geojson(2)", "modifiedTime": "2026-07-22T19:06:00Z"},  # newer dup
        {"name": "sanjay_van_baseline_stands_dissolved.shp", "modifiedTime": "2026-07-22T19:06:00Z"},  # not geojson
        {"name": "sanjay_van_baseline_stands_snic(1).geojson", "modifiedTime": "2026-07-22T15:30:00Z"},
    ]
    got = select_targets(files)
    assert set(got) == {
        "sanjay_van_baseline_stands_dissolved.geojson",
        "sanjay_van_baseline_stands_snic.geojson",
    }
    # newest copy wins
    assert got["sanjay_van_baseline_stands_dissolved.geojson"]["modifiedTime"] == "2026-07-22T19:06:00Z"


def test_select_targets_config_filter():
    files = [
        {"name": "sanjay_van_baseline_stands_dissolved.geojson", "modifiedTime": "a"},
        {"name": "sanjay_van_alphaearth_stands_dissolved.geojson", "modifiedTime": "a"},
    ]
    got = select_targets(files, configs=["sanjay_van_alphaearth"])
    assert set(got) == {"sanjay_van_alphaearth_stands_dissolved.geojson"}


def test_select_targets_layers_filter():
    files = [
        {"name": "c_stands_dissolved.geojson", "modifiedTime": "a"},
        {"name": "c_stands_snic.geojson", "modifiedTime": "a"},
    ]
    got = select_targets(files, layers=("dissolved",))
    assert set(got) == {"c_stands_dissolved.geojson"}


def test_select_targets_ignores_non_stand_files():
    files = [
        {"name": "export_manifest_sanjay_van_baseline.json", "modifiedTime": "a"},
        {"name": "random.geojson", "modifiedTime": "a"},
    ]
    assert select_targets(files) == {}


def test_the_merged_layer_is_fetched_by_default():
    """`stands_merged` is the pipeline's deliverable, and the fetcher used to
    default to `("dissolved", "snic")`. It would have downloaded two layers,
    reported no error, and left the comparison running on the pre-merge ones."""
    files = [
        {"name": "sanjay_van_baseline_stands_merged.geojson", "modifiedTime": "2026-08-27T05:59:00Z"},
        {"name": "sanjay_van_baseline_stands_snic.geojson", "modifiedTime": "2026-08-27T05:59:00Z"},
        {"name": "sanjay_van_baseline_stands_dissolved.geojson", "modifiedTime": "2026-08-27T05:59:00Z"},
    ]
    assert set(select_targets(files)) == {
        "sanjay_van_baseline_stands_merged.geojson",
        "sanjay_van_baseline_stands_snic.geojson",
        "sanjay_van_baseline_stands_dissolved.geojson",
    }


def test_merged_is_not_confused_with_the_other_layers():
    """`_stands_<layer>.geojson` is matched by suffix, so a layer name that is a
    substring of another would collide. These three do not, and the test says so
    rather than leaving it to luck."""
    files = [
        {"name": "cfg_stands_merged.geojson", "modifiedTime": "2026-08-27T05:59:00Z"},
    ]
    assert set(select_targets(files, layers=("merged",))) == {"cfg_stands_merged.geojson"}
    assert select_targets(files, layers=("snic", "dissolved")) == {}


def test_the_cli_default_matches_the_function_default():
    """Two defaults for one decision: the signature's and argparse's. They
    disagreed for as long as it took to notice."""
    import inspect

    import fetch_drive_vectors as mod

    sig_default = inspect.signature(mod.select_targets).parameters["layers"].default
    src = inspect.getsource(mod.main)
    for layer in sig_default:
        assert f'"{layer}"' in src, f"--layers default is missing {layer!r}"
