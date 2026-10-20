"""odisha_script/copy_upstream_cache.py, offline: it imports, and it copies nothing in the per-step layout.

Earth Engine is replaced by stand-ins; nothing here talks to it.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "odisha_script" / "copy_upstream_cache.py"
CONFIG = "configs/odisha_v120_3ha_squares_angul_keptland_s1desc_r9.yaml"


@pytest.fixture(autouse=True)
def _a_project(monkeypatch):
    """Asset paths name a project; this checkout has no .env, so one is set, and unset after."""
    from fmu.settings import get_settings

    monkeypatch.setenv("GEE_PROJECT_ID", "test-project")
    get_settings(force_reload=True)
    yield
    monkeypatch.delenv("GEE_PROJECT_ID")
    get_settings(force_reload=True)


def _load():
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("copy_upstream_cache", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_tool_imports():
    """Review C42: it failed at import since c64180a, which stopped the runner importing
    `cached_asset_path`, although the round 9 brief and PHASE3_STATUS.md present it as a working
    helper."""
    mod = _load()
    assert mod.differences({"clustering": {"k": 6, "seed": 1}}, {"clustering": {"k": 5, "seed": 1}}) == {
        ("clustering", "k")}
    assert mod.cached_asset_path("c", "masking", "habitat_mask", "0123456789").endswith(
        "/c/masking/habitat_mask__0123456789")


def test_a_config_of_the_per_step_layout_has_nothing_to_copy(monkeypatch, capsys):
    """In the per-step layout a change of clustering.k moves the clustering step key only, so the
    stages before clustering keep their assets: the tool says so and copies nothing."""
    mod = _load()
    text = (REPO / CONFIG).read_text()
    old_text = text.replace("  k: 5\n", "  k: 6\n", 1)
    assert old_text != text

    def git_show(argv, **kwargs):
        assert argv[:2] == ["git", "show"] and argv[2] == f"HEAD:{CONFIG}"
        return types.SimpleNamespace(returncode=0, stdout=old_text, stderr="")

    def no_earth_engine(*a, **k):
        raise AssertionError("an asset was looked up")

    monkeypatch.chdir(REPO)
    monkeypatch.setattr(mod, "subprocess", types.SimpleNamespace(run=git_show))
    monkeypatch.setattr(mod, "init_gee", lambda: None)
    monkeypatch.setattr(mod, "asset_exists", no_earth_engine)
    monkeypatch.setattr(mod, "cache_layout_for", lambda cfg: ("per_step", "no legacy asset"))
    monkeypatch.setattr(sys, "argv", ["copy_upstream_cache.py", "--config", CONFIG, "--from-ref", "HEAD"])
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "per-step cache layout" in out and "nothing to copy" in out


@pytest.mark.parametrize("execute", [False, True])
def test_a_legacy_config_gets_its_plan_from_the_old_fingerprint(monkeypatch, capsys, execute):
    """The legacy layout, as before round 9: every cacheable output before clustering, from the old
    fingerprint's name to the new one's."""
    import ee

    mod = _load()
    text = (REPO / CONFIG).read_text()
    old_text = text.replace("  k: 5\n", "  k: 6\n", 1)
    monkeypatch.chdir(REPO)
    monkeypatch.setattr(mod, "subprocess", types.SimpleNamespace(
        run=lambda argv, **k: types.SimpleNamespace(returncode=0, stdout=old_text, stderr="")))
    monkeypatch.setattr(mod, "init_gee", lambda: None)
    copied: list[tuple[str, str]] = []
    monkeypatch.setattr(ee.data, "copyAsset", lambda s, d: copied.append((s, d)))
    monkeypatch.setattr(mod, "cache_layout_for", lambda cfg: ("legacy", "its cache holds a legacy asset"))
    old = mod.load_config(REPO / CONFIG).model_copy(deep=True)
    old.clustering.k = 6
    fp_old = mod.config_fingerprint(old)
    monkeypatch.setattr(mod, "asset_exists", lambda path: path.endswith(f"__{fp_old}"))
    argv = ["copy_upstream_cache.py", "--config", CONFIG, "--from-ref", "HEAD"]
    monkeypatch.setattr(sys, "argv", argv + (["--execute"] if execute else []))
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert ("copied" if execute else "would copy") in out and "segmentation/snic_clusters" in out
    assert "clustering/" not in out.replace("clustering.k", "")
    assert len(copied) == (out.count("copied           ") if execute else 0)
    assert all(s.endswith(f"__{fp_old}") and not d.endswith(f"__{fp_old}") for s, d in copied)
