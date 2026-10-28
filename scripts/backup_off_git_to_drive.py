"""Back up the files that runs' off-git records name to a Google Drive folder, each copy checked by SHA-256.

    python scripts/backup_off_git_to_drive.py --folder fmu_results_backup/round14 \
        --out docs/reproducibility/r14_runs/off_git_backup.json <run>_files_off_git.json [...]

The round 14 brief, "Keep every run's data", 4: "Back up the off-git files. Copy the files the off-git
records name (never a run tree, never a folder holding .env) to a Drive folder
fmu_results_backup/round14, and check each copy's SHA-256."

Before Drive is reached, for each off-git record (<run>_files_off_git.json, written by
scripts/copy_run_results.py) and each file it names: the file, where the record says it is, must exist
and have the record's size and SHA-256; its real path (symbolic links followed) must lie inside the
repo, in no run tree (a path part beginning "run_tree") and below no folder, under the repo's root,
that holds a .env or a .git; and no two entries may give one file name two SHA-256s (the folder is
flat). An entry with a "drive" key other than the one this would give is refused too. A file named by
several records is sent once. Any of these refusals stops the script with exit 2, and nothing is sent.

Then, on Drive (the folder's path found under My Drive, each part made if it is not there; two folders
of one name at one level stop the script, as scripts/fetch_drive_vectors.py does; every listing read
to its last page): a file of the same name already in the folder with the record's SHA-256 is its copy,
not sent again; one with another SHA-256, a Google document or shortcut of the name, or several files
of the name, is recorded as a failure and that file is not sent: nothing on Drive is written over or
deleted. Otherwise the bytes that were checked are uploaded, and the copy's SHA-256 as Drive gives it
(sha256Checksum; if Drive gives none, the copy is downloaded and hashed) must be the record's, else the
failure is recorded with the copy's file id (the copy is left on Drive). The other files go on.

Then --out is written (results only: each checked file, its records, bytes, SHA-256, Drive path and
file id; the failures), and <out stem>_run.json beside it (the command, the date, the git state at the
start and at the end, and which files were sent by this run and which were found there); neither is
written over. Last, each record's entry whose copy was checked gains "drive": "<folder>/<file>", which
scripts/copy_run_results.py keeps while the file is the same (round 8's form). Auth: the Earth Engine
client's persistent credentials (ee.data.get_persistent_credentials()), whose scopes hold Drive's;
calls are billed to their project, whose Drive API must be enabled.

Exit 0: every file copied and checked; 1: a failure (named); 2: refused before Drive was reached.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shlex
import sys
from pathlib import Path
from typing import Any

HERE_REPO = Path(__file__).resolve().parent.parent  # this script's checkout: its git state
REPO = HERE_REPO  # the repo whose files may be backed up
FOLDER_TYPE = "application/vnd.google-apps.folder"


def refuse(why: str) -> None:
    print(f"REFUSED: {why}")
    raise SystemExit(2)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def norm_folder(folder: str) -> str:
    return "/".join(p for p in folder.split("/") if p)


def entries(records: list[Path], folder: str) -> list[dict[str, Any]]:
    """The files the records name, checked on the Mac, each once with the records that name it."""
    by_name: dict[str, dict[str, Any]] = {}
    for record in records:
        for f in json.loads(record.read_text())["files"]:
            where = Path(f["where"]).resolve()
            try:
                inside = where.relative_to(REPO)
            except ValueError:
                refuse(f"{where} is not inside the repo")
            if any(part.startswith("run_tree") for part in inside.parts):
                refuse(f"{where} is in a run tree")
            for parent in [p for p in where.parents if p != REPO and REPO in p.parents]:
                if (parent / ".env").exists() or (parent / ".git").exists():
                    refuse(f"{where} lies below {parent}, which holds a .env or a .git")
            if not where.is_file():
                refuse(f"{where} is not here")
            data = where.read_bytes()
            if len(data) != f["bytes"] or sha256(data) != f["sha256"]:
                refuse(f"{where} is not the file {record} names (size or SHA-256)")
            drive = f"{folder}/{f['file']}"
            if f.get("drive") not in (None, drive):
                refuse(f"{record} gives {f['file']} the Drive copy {f['drive']!r}, not {drive!r}")
            e = by_name.setdefault(f["file"], {"file": f["file"], "bytes": f["bytes"], "sha256": f["sha256"],
                                               "data": data, "records": []})
            if e["sha256"] != f["sha256"]:
                refuse(f"two entries give {f['file']} two SHA-256s")
            e["records"].append(str(record))
    return list(by_name.values())


def _quoted(name: str) -> str:
    return name.replace("\\", "\\\\").replace("'", "\\'")


def listed(service: Any, q: str, fields: str) -> list[dict[str, Any]]:
    """Every file the query finds, page by page."""
    out, token = [], None
    while True:
        page = service.files().list(q=q, fields=f"nextPageToken, files({fields})", spaces="drive",
                                    pageToken=token).execute(num_retries=3)
        out += page.get("files", [])
        token = page.get("nextPageToken")
        if not token:
            return out


def folder_id(service: Any, path: str) -> str:
    """The id of the folder at `path` under My Drive, each part made if it is not there."""
    parent = "root"
    for part in path.split("/"):
        found = listed(service, f"name = '{_quoted(part)}' and mimeType = '{FOLDER_TYPE}' and '{parent}' in "
                                "parents and trashed = false", "id, name")
        if len(found) > 1:
            refuse(f"{len(found)} Drive folders are named {part!r} in one place")
        parent = found[0]["id"] if found else service.files().create(
            body={"name": part, "mimeType": FOLDER_TYPE, "parents": [parent]}, fields="id").execute()["id"]
    return parent


def drive_sha256(service: Any, file_id: str, given: str | None) -> str:
    """The copy's SHA-256: Drive's, or else the copy downloaded and hashed."""
    if given:
        return given
    from googleapiclient.http import MediaIoBaseDownload

    buf = io.BytesIO()
    down = MediaIoBaseDownload(buf, service.files().get_media(fileId=file_id))
    done = False
    while not done:
        _, done = down.next_chunk(num_retries=3)
    return sha256(buf.getvalue())


def back_up(service: Any, folder: str, files: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Each file copied to the folder (or found there), checked; the rows, and the failures."""
    fid = folder_id(service, folder)
    rows, failed = [], []
    for e in files:
        there = listed(service, f"name = '{_quoted(e['file'])}' and '{fid}' in parents and trashed = false",
                       "id, name, mimeType, size, sha256Checksum")
        if len(there) > 1:
            failed.append(f"{e['file']}: {len(there)} files of the name in {folder}")
            continue
        if there and str(there[0].get("mimeType", "")).startswith("application/vnd.google-apps."):
            failed.append(f"{e['file']}: {folder} holds a Google item of the name ({there[0]['mimeType']})")
            continue
        if there:
            drive_file, sent = there[0], False
        else:
            from googleapiclient.http import MediaIoBaseUpload

            drive_file = service.files().create(
                body={"name": e["file"], "parents": [fid]},
                media_body=MediaIoBaseUpload(io.BytesIO(e["data"]), mimetype="application/octet-stream",
                                             resumable=True),
                fields="id, size, sha256Checksum").execute()
            sent = True
        got = drive_sha256(service, drive_file["id"], drive_file.get("sha256Checksum"))
        if got != e["sha256"]:
            failed.append(f"{e['file']}: the copy in {folder} (file id {drive_file['id']}"
                          f"{', sent by this run' if sent else ''}) has SHA-256 {got[:12]}..., not the record's")
            continue
        rows.append({"file": e["file"], "records": e["records"], "bytes": e["bytes"], "sha256": e["sha256"],
                     "drive": f"{folder}/{e['file']}", "drive_file_id": drive_file["id"], "sent_now": sent})
    return rows, failed


def mark_records(rows: list[dict[str, Any]]) -> None:
    """Each record's entry of a checked copy gains its Drive path, matched by file name and SHA-256."""
    for record in sorted({r for row in rows for r in row["records"]}):
        path = Path(record)
        data = json.loads(path.read_text())
        for f in data["files"]:
            for row in rows:
                if record in row["records"] and (f["file"], f["sha256"]) == (row["file"], row["sha256"]):
                    f["drive"] = row["drive"]
        path.write_text(json.dumps(data, indent=1) + "\n")


def drive_service() -> Any:  # pragma: no cover - the network
    import ee
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=ee.data.get_persistent_credentials(), cache_discovery=False)


def main(argv: list[str] | None = None, service: Any = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--folder", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("records", type=Path, nargs="+")
    args = ap.parse_args(argv)
    folder = norm_folder(args.folder)
    run_out = args.out.with_name(args.out.stem + "_run.json")
    if args.out.exists() or run_out.exists():
        refuse(f"{args.out} or {run_out.name} is there already")
    if not args.out.parent.is_dir():
        refuse(f"no folder {args.out.parent}")
    sys.path.insert(0, str(HERE_REPO / "src"))
    from fmu.utils.provenance import git_state, git_state_now

    git = {k: v for k, v in git_state(HERE_REPO).items() if k != "root"}
    files = entries(args.records, folder)
    rows, failed = back_up(service if service is not None else drive_service(), folder, files)
    for r in rows:
        print(f"{r['drive']}: {'sent and' if r['sent_now'] else 'there already,'} checked ({r['sha256'][:12]}...)")
    for f in failed:
        print(f"FAILED: {f}")
    results = [{k: v for k, v in r.items() if k != "sent_now"} for r in rows]
    args.out.write_text(json.dumps({"folder": folder, "files": results, "failed": failed}, indent=1) + "\n")
    import datetime

    run_out.write_text(json.dumps({
        "result_files": [args.out.name],
        "command_line": "python " + " ".join(shlex.quote(a) for a in
                                             ["scripts/backup_off_git_to_drive.py",
                                              *(argv if argv is not None else sys.argv[1:])]),
        "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "sent_by_this_run": [r["file"] for r in rows if r["sent_now"]],
        "found_there": [r["file"] for r in rows if not r["sent_now"]],
        "git": git}, indent=1) + "\n")
    mark_records(rows)
    record = json.loads(run_out.read_text())
    record["git_at_end"] = {k: v for k, v in git_state_now(HERE_REPO).items() if k != "root"}
    run_out.write_text(json.dumps(record, indent=1) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
