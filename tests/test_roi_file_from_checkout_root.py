"""The ROI file is read from the checkout root, wherever a run is started (round 14).

Round 13's question 41 (review C40), answer (a). Until round 14 the per-step cache keys read a
config's relative `roi_file` from the working directory, and hashed None, with no warning, for a
file they could not read: from a subfolder every per-step key changed while the legacy
fingerprint did not, and the pass runner reported every upstream asset as missing (exit 3), which
named the wrong cause. `load_roi_geometry` read the path from the working directory too.

Both now read the file through `fmu.utils.gee.read_roi_file`: an absolute path as it is, a
relative one against the root of the checkout the `fmu` package was imported from (in a batch,
the run tree, whose `src/` is on PYTHONPATH). A file that cannot be read raises an OSError that
names the path as given, the path it resolved to and the root. A ROI given as an asset still
hashes as None, and no key moves for a config run from the repo root.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import ee
import pytest
import yaml

import fmu
from fmu.config import Config, load_config
from fmu.utils import caching
from fmu.utils.caching import PER_STEP_LAYOUT, cache_key, config_fingerprint, step_key, step_keys
from fmu.utils.gee import load_roi_geometry

REPO = Path(__file__).resolve().parent.parent
# The 10 km tile config, whose keys round 13 measured from the repo root and from docs/.
TILE = REPO / "configs" / "odisha_v120_3ha_tile10km_angul_keptland_s1desc_r9.yaml"


def _root() -> Path:
    """The checkout the imported fmu package sits in (this one, under PYTHONPATH=<it>/src)."""
    return Path(fmu.__file__).resolve().parents[2]


def _raw() -> dict[str, Any]:
    return yaml.safe_load(TILE.read_text())


def _with_roi_file(roi_file: str) -> Config:
    raw = _raw()
    raw["roi"]["roi_file"] = roi_file
    return Config.model_validate(raw)


# ---------------------------------------------------------------------
# 1. The working directory plays no part
# ---------------------------------------------------------------------


@pytest.mark.parametrize("where", ["docs", "src/fmu", "outside the checkout"])
def test_the_keys_from_another_folder_are_the_keys_from_the_root(where, monkeypatch, tmp_path):
    cfg = load_config(TILE)
    assert not Path(cfg.roi.roi_file).is_absolute()
    monkeypatch.chdir(_root())
    at_root = step_keys(cfg)
    fingerprint = config_fingerprint(cfg)
    monkeypatch.chdir(tmp_path if where == "outside the checkout" else _root() / where)
    assert step_keys(cfg) == at_root
    assert {s: step_key(cfg, s) for s in at_root} == at_root
    assert config_fingerprint(cfg) == fingerprint


def test_the_geometry_is_read_from_the_root_as_well(monkeypatch):
    cfg = load_config(TILE)
    feats = json.loads((_root() / cfg.roi.roi_file).read_text())["features"]
    monkeypatch.chdir(_root() / "docs")
    with patch.object(ee, "Geometry") as geom:
        load_roi_geometry(cfg.roi.roi_file)
    geom.assert_called_once_with(feats[0]["geometry"])


def test_a_run_tree_reads_its_own_roi_file(monkeypatch, tmp_path):
    """In a batch the package is imported from the run tree (PYTHONPATH=<run tree>/src): its
    ROI file is the one hashed and loaded, whatever folder the process stands in."""
    cfg = load_config(TILE)
    tree = tmp_path / "run_tree"
    (tree / "src" / "fmu").mkdir(parents=True)
    own = tree / cfg.roi.roi_file
    own.parent.mkdir(parents=True)
    gj = json.loads((REPO / cfg.roi.roi_file).read_text())
    ring = gj["features"][0]["geometry"]["coordinates"][0]
    ring[0][0] += 1e-6  # another outline than the live checkout's, still a closed ring
    ring[-1][0] = ring[0][0]
    own.write_text(json.dumps(gj))
    monkeypatch.setattr(fmu, "__file__", str(tree / "src" / "fmu" / "__init__.py"))
    monkeypatch.chdir(REPO)
    assert caching._roi_file_sha256(cfg) == hashlib.sha256(own.read_bytes()).hexdigest()
    with patch.object(ee, "Geometry") as geom:
        load_roi_geometry(cfg.roi.roi_file)
    geom.assert_called_once_with(gj["features"][0]["geometry"])


# ---------------------------------------------------------------------
# 2. A file that cannot be read raises, and says which
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "error"),
    [
        ("aois/no_such_roi_q41.geojson", FileNotFoundError),
        ("aois", IsADirectoryError),
        ("<tmp>/no_such_roi_q41.geojson", FileNotFoundError),
    ],
    ids=["missing", "a folder", "missing, absolute"],
)
def test_a_roi_file_that_cannot_be_read_raises_and_names_it(given, error, tmp_path):
    given = given.replace("<tmp>", str(tmp_path))
    resolved = Path(given) if Path(given).is_absolute() else _root() / given
    cfg = _with_roi_file(given)
    for compute in (
        lambda: step_keys(cfg),
        lambda: step_key(cfg, "masking"),
        lambda: cache_key(cfg, "clustering", PER_STEP_LAYOUT),
        lambda: load_roi_geometry(cfg.roi.roi_file),
    ):
        with pytest.raises(error) as info:
            compute()
        message = str(info.value)
        assert repr(given) in message, message
        assert str(resolved) in message, message
        assert str(_root()) in message, message
    # The legacy fingerprint hashes the path only, as before.
    assert len(config_fingerprint(cfg)) == 10


# ---------------------------------------------------------------------
# 3. What did not change
# ---------------------------------------------------------------------


def test_an_absolute_roi_file_is_read_as_it_is(monkeypatch, tmp_path):
    roi = tmp_path / "copy.geojson"
    roi.write_bytes((REPO / _raw()["roi"]["roi_file"]).read_bytes())
    cfg = _with_roi_file(str(roi))
    monkeypatch.chdir(_root() / "docs")
    assert caching._roi_file_sha256(cfg) == hashlib.sha256(roi.read_bytes()).hexdigest()


def test_a_roi_given_as_an_asset_still_hashes_as_none():
    raw = _raw()
    raw["roi"] = {"name": "t", "roi_asset": "projects/p/assets/roi"}
    cfg = Config.model_validate(raw)
    assert caching._roi_file_sha256(cfg) is None
    keys = step_keys(cfg)
    assert len(set(keys.values())) == len(keys)


def test_the_root_is_the_checkout_the_package_was_imported_from(tmp_path):
    from fmu.utils.gee import checkout_root, resolve_roi_file
    from fmu.utils.provenance import _checkout_root

    assert checkout_root() == _root()
    assert (checkout_root() / "src" / "fmu" / "__init__.py").is_file()
    assert str(checkout_root()) == _checkout_root()
    assert resolve_roi_file("aois/x.geojson") == checkout_root() / "aois" / "x.geojson"
    assert resolve_roi_file(Path("aois/x.geojson")) == checkout_root() / "aois" / "x.geojson"
    assert resolve_roi_file(tmp_path / "x.geojson") == tmp_path / "x.geojson"
