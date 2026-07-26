"""Download the exported stand vectors from a Google Drive folder into
`fmu_exports_clean/` — so `report.py` has the GeoJSONs without a manual download.

The export stage writes `stands_dissolved` / `stands_snic` (GeoJSON + SHP) to a
Drive folder (default `fmu_exports`). Repeated runs make Drive append `(1)`,
`(2)` etc. to the names, so the folder fills with duplicates. This script lists
the folder, keeps the **newest** copy of each `<config>_stands_<layer>.geojson`
(normalizing away the `(n)` suffixes), and downloads it under the clean name
`report.py` expects. SHP/DBF and older duplicates are ignored.

Auth uses Application Default Credentials with a Drive read scope — no OAuth
client / client_secret.json needed. Grant the scope once (you likely already
have gcloud from the GCS/Tessera steps):

    gcloud auth application-default login \
        --scopes=openid,https://www.googleapis.com/auth/drive.readonly,https://www.googleapis.com/auth/cloud-platform

Install the Drive client if needed:  pip install -e '.[drive]'

Usage:
    python scripts/fetch_drive_vectors.py
    python scripts/fetch_drive_vectors.py --configs sanjay_van_baseline sanjay_van_alphaearth
    python scripts/fetch_drive_vectors.py --folder fmu_exports --dest fmu_exports_clean
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
_FOLDER_MIME = "application/vnd.google-apps.folder"


def canonical_name(name: str) -> str:
    """Strip Google Drive's duplicate `(n)` markers from a filename.

    Drive appends `(1)`, `(2)`, ... on repeated uploads, and does so either
    before or after the extension, e.g.
    `x_stands_dissolved(1).geojson`, `x_stands_dissolved.geojson(2)`.
    Removing every `(<digits>)` yields the clean name in both cases (config
    names never contain that pattern).
    """
    return re.sub(r"\(\d+\)", "", name)


def select_targets(
    files: list[dict],
    layers: tuple[str, ...] = ("dissolved", "snic"),
    configs: list[str] | None = None,
) -> dict[str, dict]:
    """Pick the newest GeoJSON per `<config>_stands_<layer>` from a file listing.

    `files` are Drive file dicts with at least `name` and `modifiedTime`.
    Returns {clean_name: file_dict}. `modifiedTime` is RFC3339, so string
    comparison orders it correctly.
    """
    suffixes = tuple(f"_stands_{layer}.geojson" for layer in layers)
    best: dict[str, dict] = {}
    for f in files:
        canon = canonical_name(f["name"])
        if not canon.endswith(suffixes):
            continue
        if configs and not any(canon.startswith(f"{c}_stands_") for c in configs):
            continue
        cur = best.get(canon)
        if cur is None or f.get("modifiedTime", "") > cur.get("modifiedTime", ""):
            best[canon] = f
    return best


def _drive_service():
    try:
        import google.auth
        from googleapiclient.discovery import build
    except ImportError as e:  # pragma: no cover - optional dep
        raise SystemExit(
            "Google Drive client not installed. Run: pip install -e '.[drive]'"
        ) from e
    try:
        creds, _ = google.auth.default(scopes=[_DRIVE_SCOPE])
    except Exception as e:  # noqa: BLE001 - surface a clear, actionable message
        raise SystemExit(
            "No Google credentials with a Drive scope. Grant it once with:\n"
            "  gcloud auth application-default login --scopes=openid,"
            "https://www.googleapis.com/auth/drive.readonly,"
            "https://www.googleapis.com/auth/cloud-platform\n"
            f"(underlying error: {e})"
        ) from e
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _find_folder_id(service, name: str) -> str:
    resp = (
        service.files()
        .list(
            q=f"mimeType='{_FOLDER_MIME}' and name='{name}' and trashed=false",
            fields="files(id,name)",
            pageSize=20,
        )
        .execute()
    )
    folders = resp.get("files", [])
    if not folders:
        raise SystemExit(f"No Drive folder named {name!r} found for this account.")
    if len(folders) > 1:
        print(f"  note: {len(folders)} folders named {name!r}; using the first.")
    return folders[0]["id"]


def _list_folder_files(service, folder_id: str) -> list[dict]:
    files: list[dict] = []
    token = None
    while True:
        resp = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="nextPageToken, files(id,name,modifiedTime,size)",
                pageSize=1000,
                pageToken=token,
            )
            .execute()
        )
        files.extend(resp.get("files", []))
        token = resp.get("nextPageToken")
        if not token:
            break
    return files


def _download(service, file_id: str, dest: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload

    request = service.files().get_media(fileId=file_id)
    with dest.open("wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--folder", default="fmu_exports",
                    help="Drive folder the export stage writes to (default fmu_exports)")
    ap.add_argument("--dest", type=Path, default=Path("fmu_exports_clean"),
                    help="local destination (default fmu_exports_clean)")
    ap.add_argument("--configs", nargs="*", default=None,
                    help="only fetch these config names (default: all found)")
    ap.add_argument("--layers", nargs="+", default=["dissolved", "snic"],
                    help="which vector layers to fetch (default: dissolved snic)")
    args = ap.parse_args()

    service = _drive_service()
    print(f"Finding Drive folder {args.folder!r} ...")
    folder_id = _find_folder_id(service, args.folder)
    files = _list_folder_files(service, folder_id)
    print(f"  {len(files)} file(s) in the folder.")

    targets = select_targets(files, layers=tuple(args.layers), configs=args.configs)
    if not targets:
        raise SystemExit(
            "No matching *_stands_<layer>.geojson files found. Check that the "
            "export tasks finished (earthengine task list | grep stands) and "
            "that --configs / --layers match."
        )

    args.dest.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {len(targets)} file(s) -> {args.dest}/")
    for clean_name, f in sorted(targets.items()):
        dest = args.dest / clean_name
        _download(service, f["id"], dest)
        print(f"  {clean_name}  (Drive name: {f['name']}, modified {f.get('modifiedTime', '?')})")

    print("Done. Now build the report, e.g.:")
    print("  python scripts/report.py --multi --reference sanjay_van_baseline "
          "--configs sanjay_van_alphaearth")


if __name__ == "__main__":
    main()
