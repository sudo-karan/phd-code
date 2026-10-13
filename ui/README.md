# FMU Pipeline Explorer

A static web page that shows the pipeline one step at a time, for Sanjay Van and the four Odisha
districts, both arms (feature vector and AlphaEarth): the land-cover mask and why each pixel was
kept or removed, the Sentinel-2 composite, the features, the superpixels, the merged stands, the
stand types, and the FES field plots with the field check. Each step has an "i" button that opens
the decisions behind it, from `docs/decisions.yaml`, with their papers and how strongly each paper
supports the choice.

## Files

- `ui/explorer.html`: the page. One file, written as a page fragment so that it can also be
  published as a Claude artifact. Leaflet 1.9.4 loads from cdnjs; its stylesheet is inlined.
- `scripts/build_ui_site.py`: wraps the page into a full document and puts it, the exported data
  and `decisions.json` (from `docs/decisions.yaml`) into `_site/`. A file named in the index but
  missing stops the build.
- `ui_data/`: the data the page reads. `ui_data/index.json` is the contract; its format is in
  `docs/handoff/2026-10-13-round2.md`, task A3. The pipeline's export writes it.
- `scripts/build_ui_early_data.py`: built the first `ui_data/` from files the 13 October re-runs
  had already saved (stands before the merge fix; features as stand means). The A3 export
  replaces that folder.

## See it locally

```
python scripts/build_ui_site.py
python -m http.server -d _site 8000
```

Then open http://localhost:8000. Opening `_site/index.html` directly does not work, because
browsers block a page read from disk from reading its data files.

## Hosting

`.github/workflows/pages.yml` builds the site on every push and pull request to `main`, and
publishes it to GitHub Pages from `main` only. The repository is public, so the site is public,
FES plot locations included (they are already in the repository).
