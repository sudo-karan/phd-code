"""Offline tests of scripts/build_ui_site.py: the site builds, and bad data stops it."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build_ui_site as site  # noqa: E402

PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def _register(tmp_path: Path) -> Path:
    path = tmp_path / "decisions.yaml"
    path.write_text(
        "schema_version: 1\n"
        "decisions:\n"
        "- id: dn-example\n"
        "  title: An example decision\n"
        "  decision: Do the example thing.\n"
        "  status: adopted\n"
        "  papers: []\n"
    )
    return path


def _data(tmp_path: Path) -> Path:
    data = tmp_path / "ui_data"
    (data / "runs" / "r1").mkdir(parents=True)
    (data / "runs" / "r1" / "mask.png").write_bytes(PNG_1X1)
    (data / "runs" / "r1" / "stands.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": []})
    )
    (data / "fes.json").write_text(json.dumps({"rows": []}))
    index = {
        "label": "test",
        "fes_comparison": "fes.json",
        "runs": [
            {
                "run_id": "r1",
                "site": "Odisha",
                "area": "Angul",
                "arm": "feature_vector",
                "stand_ceiling_ha": 3,
                "k": 5,
                "bounds": [84.6, 20.7, 84.7, 20.8],
                "steps": [
                    {
                        "step": "masking",
                        "title": "Mask",
                        "decisions": ["dn-example"],
                        "layers": [
                            {"layer_id": "m", "kind": "raster", "parts": [
                                {"file": "runs/r1/mask.png", "bounds": [84.6, 20.7, 84.7, 20.8]}
                            ]},
                            {"layer_id": "s", "kind": "vector", "file": "runs/r1/stands.geojson"},
                        ],
                    }
                ],
            }
        ],
    }
    (data / "index.json").write_text(json.dumps(index))
    return data


def test_builds_a_full_document_with_data(tmp_path: Path) -> None:
    out = tmp_path / "_site"
    report = site.build(out, _data(tmp_path), _register(tmp_path))
    html = (out / "index.html").read_text()
    assert html.startswith("<!doctype html>")
    head, body = html.split("</head>", 1)
    assert "<title>Forest Stand Explorer</title>" in head
    assert '<div class="app"' in body
    assert json.loads((out / "decisions.json").read_text())["decisions"][0]["id"] == "dn-example"
    assert (out / "ui_data" / "runs" / "r1" / "mask.png").is_file()
    assert report["data"] == "copied"
    assert report["files"] == 4


def test_builds_without_data(tmp_path: Path) -> None:
    out = tmp_path / "_site"
    report = site.build(out, tmp_path / "no_such_folder", _register(tmp_path))
    assert report["data"] == "missing"
    assert (out / "index.html").is_file()
    assert not (out / "ui_data").exists()


def test_missing_file_stops_the_build(tmp_path: Path) -> None:
    data = _data(tmp_path)
    (data / "runs" / "r1" / "mask.png").unlink()
    with pytest.raises(SystemExit, match="runs/r1/mask.png"):
        site.build(tmp_path / "_site", data, _register(tmp_path))


def test_every_file_the_index_names_is_listed(tmp_path: Path) -> None:
    index = json.loads((_data(tmp_path) / "index.json").read_text())
    assert sorted(site.files_named_by(index)) == [
        "fes.json",
        "runs/r1/mask.png",
        "runs/r1/stands.geojson",
    ]
