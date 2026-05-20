"""Mocked tests for caching utility; path construction and signatures.

The actual asset existence check and export submission are GEE-only and
tested live in test_caching_live.py.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fmu.utils.caching import cached_asset_path


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
