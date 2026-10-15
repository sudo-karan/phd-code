# Forest Stand Explorer

A static web page that walks through the pipeline one step at a time, for Sanjay Van and the four
Odisha districts, both arms (our features and AlphaEarth):

1. **Area**: the land we work on, over a Sentinel-2 image.
2. **Land cover**: which pixels IndiaSAT (or WorldCover) calls trees or scrub.
3. **Measures**: what the satellite tells us per pixel (our 22 measurements, or AlphaEarth's 64).
4. **Superpixels**: SNIC's small patches of similar pixels.
5. **Stands**: superpixels joined into stands, with how many joins each rule made.
6. **Types**: k-means stand types, with the land that isn't trees or scrub shaded.
7. **Field check** (Odisha): lines between plots that share a stand (green when they are the same
   field type, red dashed when not), a stand type against field type table, and the chance test in
   plain words (how many of 100 random placements the real one beats, against the 95 set in
   advance).

Each step's text is written from the run's own numbers (`facts` in `ui_data/index.json`), and sets
the map for that step; every layer can still be switched on and off. "Why we did it this way" opens
the decisions behind the step, from `docs/decisions.yaml`, with their papers and how strongly each
supports the choice. Superpixels and land cover are drawn as encoded lines and shapes, so they stay
sharp at any zoom; the satellite image is smoothed rather than shown as 10 m blocks.

## Files

- `ui/explorer.html`: the page. One file, written as a page fragment so that it can also be
  published as a Claude artifact. Leaflet 1.9.4 loads from cdnjs; its stylesheet is inlined.
- `scripts/build_ui_site.py`: wraps the page into a full document and puts it, the exported data
  and `decisions.json` (from `docs/decisions.yaml`) into `_site/`. A file named in the index but
  missing stops the build.
- `ui_data/`: the data the page reads. `ui_data/index.json` is the contract; its format is in
  `docs/handoff/2026-10-13-round2.md`, task A3, with "Version 2 of the index". The pipeline's
  export writes it.
- `scripts/build_ui_early_data.py`: built the current `ui_data/` from files the 13 October re-runs
  had already saved (stands before the merge fix; features as stand means; only the superpixels
  that hold some trees or scrub). It adds the box runs of brief A0 by itself once their stand
  files and the output of `scripts/transparency_masking.py` for each box config exist (the
  folders it searches are `BOX_VEC_DIRS` and `BOX_MASK_DIRS` at its top); the page then offers
  "Village outlines" and "Boxes" for the 3 ha runs. Stands are written as encoded polylines
  (`stands.json`), which the page turns back into GeoJSON. The A3 export replaces that folder.

## See it locally

```
python scripts/build_ui_site.py
python -m http.server -d _site 8000
```

Then open http://localhost:8000. Opening `_site/index.html` directly does not work, because
browsers block a page read from disk from reading its data files. A link can point at a run and a
step: `#odisha_v120_3ha_koraput_repro/field`.

## Hosting

`.github/workflows/pages.yml` builds the site on every push and pull request to `main`, and
publishes it to GitHub Pages from `main` only. The repository is public, so the site is public,
FES plot locations included (they are already in the repository). The street map underneath only
loads on the published site; the Claude preview blocks outside map tiles.
