"""Mocked tests for the export stage's asset inventory.

The inventory used to be a hand-maintained list (_CACHEABLE_OUTPUTS) that
drifted from reality. It missed landcover_summary (caught 2026-05-20) and
included a phantom built_up_mask entry (caught earlier). The fix replaced
the list with auto-discovery via the stage registry.

These tests assert the auto-discovery covers every stage that registers
cacheable image outputs, without re-checking the same hand-maintained
list this is supposed to replace.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

from fmu.stages.base import get_stage_class, list_registered_stages
from fmu.stages.export import _inventory_cached_assets


# Pre-import every stage module so the registry is populated when the
# tests run. (Pytest discovery would otherwise miss late-bound stages.)
def _import_all_stages():
    import fmu.stages.clustering  # noqa: F401
    import fmu.stages.data_load  # noqa: F401
    import fmu.stages.export  # noqa: F401
    import fmu.stages.features_optical  # noqa: F401
    import fmu.stages.features_radar  # noqa: F401
    import fmu.stages.features_static  # noqa: F401
    import fmu.stages.features_structure  # noqa: F401
    import fmu.stages.masking  # noqa: F401
    import fmu.stages.metrics  # noqa: F401
    import fmu.stages.profiling  # noqa: F401
    import fmu.stages.segmentation  # noqa: F401


_import_all_stages()


@contextmanager
def _mocked_cache(*, exists: bool):
    """Mock the GEE-touching helpers used by _inventory_cached_assets.

    asset_exists controls whether the inventory finds the asset. The
    cached_asset_path mock returns a deterministic fake path so we don't
    need GEE_PROJECT_ID set during the test.
    """
    with patch("fmu.stages.export.asset_exists", return_value=exists), patch(
        "fmu.stages.export.cached_asset_path",
        side_effect=lambda config, stage, key: f"fake_root/{config}/{stage}/{key}",
    ):
        yield


def test_inventory_discovers_landcover_summary():
    """Regression test for the bug found 2026-05-20: landcover_summary is
    a cacheable image output of the masking stage, but the hand-maintained
    inventory list omitted it. The auto-discovery via registry must include it.
    """
    with _mocked_cache(exists=True):
        paths = _inventory_cached_assets("test_config")
    assert "landcover_summary" in paths, (
        "auto-discovery missed landcover_summary — registry walk broken"
    )


def test_inventory_discovers_all_masking_outputs():
    """All three of masking's produces should be in the inventory when assets exist."""
    with _mocked_cache(exists=True):
        paths = _inventory_cached_assets("test_config")
    for output in ("habitat_mask", "water_mask", "landcover_summary"):
        assert output in paths, f"masking output {output!r} missing from inventory"


def test_inventory_excludes_optout_stages():
    """Stages with cacheable_outputs=set() (profiling, export, metrics) must
    not appear in the inventory — they don't produce cacheable images."""
    with _mocked_cache(exists=True):
        paths = _inventory_cached_assets("test_config")
    for output in ("cluster_profiles", "export_manifest", "comparison_metrics", "agreement_map"):
        assert output not in paths, (
            f"opt-out stage output {output!r} unexpectedly in inventory"
        )


def test_inventory_returns_empty_when_no_assets_exist():
    """When no assets exist on the server, inventory should be empty
    (not error)."""
    with _mocked_cache(exists=False):
        paths = _inventory_cached_assets("nonexistent_config")
    assert paths == {}


def test_inventory_excludes_imagecollection_outputs():
    """data_load produces s2_collection and s1_collection (ImageCollections),
    which aren't cacheable as assets. Only s2_composite should appear."""
    with _mocked_cache(exists=True):
        paths = _inventory_cached_assets("test_config")
    assert "s2_composite" in paths
    # The collections are not in cacheable_outputs, so they shouldn't appear
    assert "s2_collection" not in paths
    assert "s1_collection" not in paths


def test_inventory_covers_every_produces_of_image_only_stages():
    """For every registered stage whose entire `produces` set is cacheable,
    every output key should be discoverable. This is the broad coverage check.
    """
    from fmu.pipeline import Pipeline

    with _mocked_cache(exists=True):
        paths = _inventory_cached_assets("test_config")

    for stage_name in list_registered_stages():
        stage = get_stage_class(stage_name)()
        cacheable = Pipeline._resolve_cacheable_outputs(stage)
        for output in cacheable:
            assert output in paths, (
                f"stage {stage_name!r} declares {output!r} as cacheable, "
                "but auto-discovery didn't pick it up"
            )
