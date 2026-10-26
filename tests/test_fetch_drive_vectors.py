"""Non-live tests for scripts/fetch_drive_vectors.py pure logic.

The filename normalization + newest-per-layer selection, and main() against a
stubbed Drive service (the folder query, and the check of each layer against its
run manifest). The real Drive API calls need auth and are exercised manually.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

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


# ---------- B28 (review 2026-10-19): the folder, and the file against the run ----------
#
# main() is run against a stubbed Drive service: no network call, no credentials.

_FOLDER_MIME = "application/vnd.google-apps.folder"


class _Request:
    def __init__(self, resp: dict):
        self.resp = resp

    def execute(self) -> dict:
        return self.resp


class _Files:
    """`files().list(...)`: the folder query and the folder listing, each in pages."""

    def __init__(self, folder_pages: list[list[dict]], file_pages: list[list[dict]]):
        self.folder_pages, self.file_pages = folder_pages, file_pages

    def list(self, q: str, **kw):  # fields, pageSize, pageToken: Drive's own spelling
        pages = self.folder_pages if _FOLDER_MIME in q else self.file_pages
        i = int(kw.get("pageToken") or 0)
        resp: dict = {"files": pages[i]}
        if i + 1 < len(pages):
            resp["nextPageToken"] = str(i + 1)
        return _Request(resp)


class _Service:
    def __init__(self, files: _Files):
        self._files = files

    def files(self) -> _Files:
        return self._files


def _geojson(n: int) -> bytes:
    feats = [{"type": "Feature", "properties": {"stand_id": i + 1}, "geometry": None} for i in range(n)]
    return json.dumps({"type": "FeatureCollection", "features": feats}).encode()


def _write_run(runs: Path, config: str, n_by_layer: dict[str, int]) -> None:
    """A run folder as the pipeline writes it: manifest.json with the export stage's manifest."""
    run_dir = runs / f"{config}_20261001_120000"
    run_dir.mkdir(parents=True)
    layers = {f"stands_{layer}": {"n_features": n} for layer, n in n_by_layer.items()}
    manifest = {"stages": [{"name": "export", "metadata": {"manifest": {"vector_layers": layers}}}]}
    (run_dir / "manifest.json").write_text(json.dumps(manifest))


def _run_main(monkeypatch, tmp_path, service, contents: dict[str, bytes], *extra: str):
    import fetch_drive_vectors as mod

    def download(_service, file_id: str, dest: Path) -> None:
        dest.write_bytes(contents[file_id])

    monkeypatch.setattr(mod, "_drive_service", lambda: service)
    monkeypatch.setattr(mod, "_download", download)
    # Run folders are found where the pipeline writes them, outputs/runs/ in the working directory.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["fetch_drive_vectors.py", "--dest", str(tmp_path / "clean"), *extra])
    mod.main()


def test_several_folders_of_the_name_stop_the_fetch(monkeypatch, tmp_path):
    """Drive gives no order, so "the first" of two same-named folders is either. The
    second sits on the query's second page, which the fetcher used not to read."""
    files = [{"id": "a", "name": "c_stands_merged.geojson", "modifiedTime": "2026-10-01T12:00:00Z"}]
    service = _Service(_Files(folder_pages=[[{"id": "f1", "name": "fmu_exports"}],
                                            [{"id": "f2", "name": "fmu_exports"}]],
                              file_pages=[files]))
    _write_run(tmp_path / "outputs" / "runs", "c", {"merged": 2})
    with pytest.raises(SystemExit) as exc:
        _run_main(monkeypatch, tmp_path, service, {"a": _geojson(2)}, "--layers", "merged")
    assert exc.value.code not in (0, None)
    assert "2 Drive folders named 'fmu_exports'" in str(exc.value.code)


def test_the_folder_query_is_read_to_its_last_page(monkeypatch, tmp_path):
    files = [{"id": "a", "name": "c_stands_merged.geojson", "modifiedTime": "2026-10-01T12:00:00Z"}]
    service = _Service(_Files(folder_pages=[[], [{"id": "f1", "name": "fmu_exports"}]],
                              file_pages=[files]))
    _write_run(tmp_path / "outputs" / "runs", "c", {"merged": 2})
    _run_main(monkeypatch, tmp_path, service, {"a": _geojson(2)}, "--layers", "merged")
    assert (tmp_path / "clean" / "c_stands_merged.geojson").read_bytes() == _geojson(2)


def test_a_file_whose_polygon_count_differs_from_the_run_stops_the_fetch(monkeypatch, tmp_path):
    """The newest copy on Drive can be an older run's layer. Its polygon count is checked
    against the run manifest's n_features, and on a mismatch nothing is saved under the
    clean name."""
    files = [{"id": "a", "name": "c_stands_merged.geojson", "modifiedTime": "2026-10-01T12:00:00Z"}]
    service = _Service(_Files(folder_pages=[[{"id": "f1", "name": "fmu_exports"}]],
                              file_pages=[files]))
    _write_run(tmp_path / "outputs" / "runs", "c", {"merged": 3})
    with pytest.raises(SystemExit) as exc:
        _run_main(monkeypatch, tmp_path, service, {"a": _geojson(2)}, "--layers", "merged")
    assert exc.value.code not in (0, None)
    assert "2 polygons" in str(exc.value.code) and "n_features 3" in str(exc.value.code)
    assert not (tmp_path / "clean" / "c_stands_merged.geojson").exists()
