"""Build the static explorer site (GitHub Pages) from the page, the exported data and the register.

    python scripts/build_ui_site.py [--out _site] [--data ui_data] [--decisions docs/decisions.yaml]

`ui/explorer.html` is written as a page fragment, because the same file is also published as a
Claude artifact, which adds the document skeleton itself. This script wraps it in a full HTML
document, copies the exported data (`ui_data/`, written by the pipeline's export, brief A3), turns
the decision register into `decisions.json` for the page's "i" buttons, and checks that every file
the index names exists. A missing file stops the build. With no `ui_data/` at all the site still
builds, and the page says that the data has not been exported yet.

Serve the result locally with `python -m http.server -d _site 8000` and open
http://localhost:8000 (opening the file directly does not work: browsers block the data reads).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "ui" / "explorer.html"
BODY_START = '<div class="app"'
SIZE_LIMIT = 5 * 1024 * 1024

BASE_STYLE = (
    "<style>:root{color-scheme:light}body{margin:0}"
    "[hidden]{display:none!important}</style>"
)


def wrap(fragment: str) -> str:
    """Put the fragment's title, links and style in <head> and the rest in <body>."""
    cut = fragment.find(BODY_START)
    if cut < 0:
        raise ValueError(f"{PAGE} has no {BODY_START!r}: cannot split head from body")
    head, body = fragment[:cut], fragment[cut:]
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, '
        'viewport-fit=cover">\n'
        f"{BASE_STYLE}\n{head.strip()}\n</head>\n<body>\n{body.strip()}\n</body>\n</html>\n"
    )


def files_named_by(index: dict) -> list[str]:
    """Every data file the index points to, relative to the data folder."""
    names: list[str] = []
    if index.get("fes_comparison"):
        names.append(index["fes_comparison"])
    for run in index.get("runs", []):
        for step in run.get("steps", []):
            for layer in step.get("layers", []):
                if layer.get("file"):
                    names.append(layer["file"])
                names.extend(p["file"] for p in layer.get("parts") or [])
    return names


def check_data(data: Path) -> list[str]:
    """Problems with the exported data; an empty list means it is usable."""
    problems: list[str] = []
    index_path = data / "index.json"
    if not index_path.is_file():
        return [f"{index_path} is missing"]
    index = json.loads(index_path.read_text())
    if not index.get("runs"):
        problems.append("index.json lists no runs")
    for name in sorted(set(files_named_by(index))):
        if not (data / name).is_file():
            problems.append(f"index.json names {name}, which is not in {data}")
    return problems


def build(out: Path, data: Path, decisions: Path) -> dict:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / "index.html").write_text(wrap(PAGE.read_text()))
    (out / ".nojekyll").write_text("")
    register = yaml.safe_load(decisions.read_text())
    (out / "decisions.json").write_text(json.dumps(register, default=str, ensure_ascii=False))
    report: dict = {"data": "missing", "files": 0, "bytes": 0, "large_files": []}
    if data.is_dir():
        problems = check_data(data)
        if problems:
            raise SystemExit("ui_data is not usable:\n  " + "\n  ".join(problems))
        shutil.copytree(data, out / "ui_data")
        files = [p for p in (out / "ui_data").rglob("*") if p.is_file()]
        report.update(data="copied", files=len(files), bytes=sum(p.stat().st_size for p in files))
        report["large_files"] = [
            str(p.relative_to(out)) for p in files if p.stat().st_size > SIZE_LIMIT
        ]
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "_site")
    ap.add_argument("--data", type=Path, default=ROOT / "ui_data")
    ap.add_argument("--decisions", type=Path, default=ROOT / "docs" / "decisions.yaml")
    args = ap.parse_args(argv)
    report = build(args.out, args.data, args.decisions)
    if report["data"] == "missing":
        print(f"built {args.out} without data: {args.data} does not exist yet")
    else:
        mb = report["bytes"] / 1e6
        print(f"built {args.out}: {report['files']} data files, {mb:.1f} MB")
    for name in report["large_files"]:
        print(f"  note: {name} is over 5 MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
