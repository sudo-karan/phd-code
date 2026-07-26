"""Mocked tests for caching utility; path construction and signatures.

The actual asset existence check and export submission are GEE-only and
tested live in test_caching_live.py.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fmu.utils.caching import cached_asset_path, ensure_parent_folders


class TestCachedAssetPath:
    def test_path_format(self):
        with patch("fmu.utils.caching.asset_path") as mock_ap:
            mock_ap.return_value = "projects/x/assets/fmu/baseline/masking/habitat_mask"
            result = cached_asset_path("baseline", "masking", "habitat_mask")
            mock_ap.assert_called_once_with("habitat_mask", subdir="baseline/masking")
            assert result == "projects/x/assets/fmu/baseline/masking/habitat_mask"

    def test_key_must_be_alphanumeric_underscore(self):
        with pytest.raises(ValueError, match="alphanumeric/underscore"):
            cached_asset_path("baseline", "masking", "bad-key")
        with pytest.raises(ValueError, match="alphanumeric/underscore"):
            cached_asset_path("baseline", "masking", "bad key")
        with pytest.raises(ValueError, match="alphanumeric/underscore"):
            cached_asset_path("baseline", "masking", "bad/key")

    def test_key_with_underscores_ok(self):
        with patch("fmu.utils.caching.asset_path") as mock_ap:
            mock_ap.return_value = "ok"
            # No exception
            cached_asset_path("baseline", "masking", "habitat_mask_v2")


class TestEnsureParentFolders:
    ASSET = "projects/p/assets/fmu/sanjay_van_alphaearth/segmentation/snic_clusters"

    def test_creates_missing_config_and_stage_folders(self):
        """Creates every ancestor below the assets root that doesn't exist —
        the config folder and the stage folder — but NOT the leaf asset, and
        skips ancestors that already exist (e.g. the shared fmu root)."""
        existing = {"projects/p/assets/fmu"}

        def fake_exists(path: str) -> bool:
            return path in existing

        with patch("fmu.utils.caching.asset_exists", side_effect=fake_exists), \
             patch("fmu.utils.caching.ee.data.createFolder") as mk:
            ensure_parent_folders(self.ASSET)

        created = [c.args[0] for c in mk.call_args_list]
        assert created == [
            "projects/p/assets/fmu/sanjay_van_alphaearth",
            "projects/p/assets/fmu/sanjay_van_alphaearth/segmentation",
        ]
        # never tries to create the leaf asset itself
        assert self.ASSET not in created

    def test_noop_when_all_ancestors_exist(self):
        with patch("fmu.utils.caching.asset_exists", return_value=True), \
             patch("fmu.utils.caching.ee.data.createFolder") as mk:
            ensure_parent_folders(self.ASSET)
        mk.assert_not_called()

    def test_unrecognized_path_is_ignored(self):
        with patch("fmu.utils.caching.ee.data.createFolder") as mk:
            ensure_parent_folders("some/relative/path")
        mk.assert_not_called()
