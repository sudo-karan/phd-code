"""scripts/backup_off_git_to_drive.py, offline, against a fake Drive: the files off-git records name are
copied to the folder (made if missing) and checked by SHA-256, the records gain each copy's Drive path,
a copy already there is not sent again, a file named twice is sent once, another file of the same name
is never written over, and a file outside the repo, in a run tree, below a .env, not the record's, or
given two SHA-256s is refused, exit 2, before Drive is reached."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "backup_off_git_to_drive.py"


def _load():
    spec = importlib.util.spec_from_file_location("backup_off_git_to_drive", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load()


class _Exec:
    def __init__(self, fn):
        self.fn = fn

    def execute(self, num_retries: int = 0) -> Any:
        return self.fn()


class FakeDrive:
    """Files and folders by id, each with its name, parent and content; Drive's sha256Checksum given."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.created: list[str] = []
        self.calls = 0

    def files(self) -> FakeDrive:
        self.calls += 1
        return self

    def list(self, q: str, fields: str, spaces: str, pageToken: str | None = None) -> _Exec:  # noqa: N803
        name = re.search(r"name = '((?:[^'\\]|\\.)*)'", q).group(1).replace("\\'", "'").replace("\\\\", "\\")
        parent = re.search(r"'([\w-]+)' in parents", q).group(1)
        folder = "mimeType" in q

        def found() -> dict[str, Any]:
            return {"files": [{"id": i, "name": it["name"], "mimeType": it.get("mime", "application/octet-stream"),
                               "size": str(len(it.get("content", b""))), "sha256Checksum": it.get("sha")}
                              for i, it in self.items.items()
                              if it["name"] == name and it["parent"] == parent and it["folder"] == folder]}
        return _Exec(found)

    def create(self, body: dict[str, Any], fields: str, media_body: Any = None) -> _Exec:
        def make() -> dict[str, Any]:
            i = f"id{len(self.items)}"
            content = media_body.getbytes(0, media_body.size()) if media_body is not None else b""
            self.items[i] = {"name": body["name"], "parent": body["parents"][0], "folder": media_body is None,
                             "content": content, "sha": hashlib.sha256(content).hexdigest() if media_body else None}
            self.created.append(body["name"])
            return {"id": i, "sha256Checksum": self.items[i]["sha"]}
        return _Exec(make)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(B, "REPO", tmp_path)
    return tmp_path


def _record(root: Path, run: str, content: bytes, *, where: Path | None = None, folder: str = "records",
            name: str | None = None) -> Path:
    off = where or (root / "outputs" / "results" / (name or f"{run}_stands_snic.geojson"))
    off.parent.mkdir(parents=True, exist_ok=True)
    off.write_bytes(content)
    rec = root / folder / f"{run}_files_off_git.json"
    rec.parent.mkdir(parents=True, exist_ok=True)
    rec.write_text(json.dumps({"what": "x", "files": [{
        "file": off.name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
        "where": str(off)}]}))
    return rec


def _main(repo: Path, out: str, *records: Path, drive: FakeDrive, folder: str = "fmu_results_backup/round14") -> int:
    return B.main(["--folder", folder, "--out", str(repo / out), *map(str, records)], service=drive)


def _refused(repo: Path, out: str, *records: Path, drive: FakeDrive, match: str, capsys) -> None:
    with pytest.raises(SystemExit) as e:
        _main(repo, out, *records, drive=drive)
    assert e.value.code == 2
    assert re.search(match, capsys.readouterr().out)


def test_a_file_is_copied_checked_and_recorded(repo: Path, capsys):
    rec = _record(repo, "run_a", b"layer a")
    drive = FakeDrive()
    assert _main(repo, "backup.json", rec, drive=drive, folder="/fmu_results_backup//round14/") == 0
    folders = {it["name"]: it for it in drive.items.values() if it["folder"]}
    assert set(folders) == {"fmu_results_backup", "round14"} and folders["fmu_results_backup"]["parent"] == "root"
    entry = json.loads(rec.read_text())["files"][0]
    assert entry["drive"] == "fmu_results_backup/round14/run_a_stands_snic.geojson"
    out = json.loads((repo / "backup.json").read_text())
    assert out["failed"] == [] and out["folder"] == "fmu_results_backup/round14"
    assert "sent_now" not in out["files"][0]
    run = json.loads((repo / "backup_run.json").read_text())
    assert run["sent_by_this_run"] == ["run_a_stands_snic.geojson"] and "git_at_end" in run
    _refused(repo, "backup.json", rec, drive=drive, match="there already", capsys=capsys)
    # A second run finds the copy and does not send it again.
    assert _main(repo, "again.json", rec, drive=drive) == 0
    assert drive.created.count("run_a_stands_snic.geojson") == 1
    assert json.loads((repo / "again_run.json").read_text())["found_there"] == ["run_a_stands_snic.geojson"]


def test_a_file_named_by_two_records_is_sent_once_and_both_are_marked(repo: Path):
    a = _record(repo, "run_k", b"kendujhar", folder="r9_runs")
    b = _record(repo, "run_k", b"kendujhar", folder="round9_cache_test")
    drive = FakeDrive()
    assert _main(repo, "backup.json", a, b, drive=drive) == 0
    assert drive.created.count("run_k_stands_snic.geojson") == 1
    assert all(json.loads(r.read_text())["files"][0]["drive"].endswith("run_k_stands_snic.geojson") for r in (a, b))


def test_one_name_with_two_sha256s_is_refused_before_drive(repo: Path, capsys):
    a = _record(repo, "run_x", b"version a", folder="A")
    b = _record(repo, "run_x", b"version b", folder="B", where=repo / "outputs" / "other" / "run_x_stands_snic.geojson")
    drive = FakeDrive()
    _refused(repo, "backup.json", a, b, drive=drive, match="two SHA-256s", capsys=capsys)
    assert drive.calls == 0
    assert all("drive" not in json.loads(r.read_text())["files"][0] for r in (a, b))


def test_another_file_of_the_name_on_drive_is_not_written_over(repo: Path):
    rec = _record(repo, "run_a", b"layer a")
    drive = FakeDrive()
    fid = B.folder_id(drive, "fmu_results_backup/round14")
    drive.items["other"] = {"name": "run_a_stands_snic.geojson", "parent": fid, "folder": False,
                            "content": b"old", "sha": hashlib.sha256(b"old").hexdigest()}
    assert _main(repo, "backup.json", rec, drive=drive) == 1
    assert drive.items["other"]["content"] == b"old"
    assert "drive" not in json.loads(rec.read_text())["files"][0]
    assert "not the record's" in json.loads((repo / "backup.json").read_text())["failed"][0]


def test_refusals_come_before_drive(repo: Path, tmp_path_factory, capsys):
    drive = FakeDrive()
    outside = tmp_path_factory.mktemp("elsewhere") / "run_o_stands_snic.geojson"
    _refused(repo, "o1.json", _record(repo, "run_o", b"o", where=outside), drive=drive,
             match="not inside the repo", capsys=capsys)
    tree = _record(repo, "run_t", b"t", where=repo / "outputs" / "run_tree_5" / "x" / "run_t_stands_snic.geojson")
    _refused(repo, "o2.json", tree, drive=drive, match="run tree", capsys=capsys)
    (repo / "outputs" / "envd").mkdir(parents=True)
    (repo / "outputs" / "envd" / ".env").write_text("SECRET=1")
    env = _record(repo, "run_e", b"e", where=repo / "outputs" / "envd" / "deep" / "run_e_stands_snic.geojson")
    _refused(repo, "o3.json", env, drive=drive, match=r"\.env", capsys=capsys)
    changed = _record(repo, "run_c", b"c")
    (repo / "outputs" / "results" / "run_c_stands_snic.geojson").write_bytes(b"changed")
    _refused(repo, "o4.json", changed, drive=drive, match="not the file", capsys=capsys)
    assert drive.calls == 0
