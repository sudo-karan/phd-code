# Forest Stand Explorer

A static web page that walks through the pipeline one step at a time, for Sanjay Van and the four
Odisha districts, both arms (our features and AlphaEarth).

It opens on the current results, R3: the eighteen runs of 28 Oct 2026 (Sanjay Van, both arms; the
four districts' boxes at 3 ha and at 10 ha, both arms; all on kept land only), made after the
corrections of 19 to 28 Oct. The pickers choose among them by place, features and stand size. The
28 runs of 13 to 15 Oct stay as "Earlier versions" (the Results picker), each with one line saying
what it is and that its results are from before those corrections. The banner opens two panels:
"What changed" (the corrections that change what the pipeline computes, one sentence each, with
links to the review of 19 Oct and the round records) and "Earlier versions" (the 28, by place).
The steps:

1. **Area**: the land we work on, over a Sentinel-2 image.
2. **Land cover**: which pixels IndiaSAT (or WorldCover) calls trees or scrub.
3. **Measures**: what the satellite tells us per pixel (our 22 measurements, or AlphaEarth's 64).
4. **Superpixels**: SNIC's small patches of similar pixels.
5. **Stands**: superpixels joined into stands, with how many joins each rule made.
6. **Types**: k-means stand types, with the land that isn't trees or scrub shaded.
7. **Field check** (Odisha): lines between plots that share a stand (green when they are the same
   field type, red dashed when not), a stand type against field type table, and the chance test in
   plain words (how many of 100 random placements the real one beats, against the 95 set in
   advance). For R3, each set's declared field check and chance test
   (`odisha_script/keptland_scores/keptland_<set>_r14_*`), the plots joined by the set's declared
   join (the 30 m rule included), and the declared checks beside the main result: S1, S2, the
   plots a stand covers, the 13 Oct box stands (a comparison), and C1.

For R3 the Types step gives k with Jaskaran's reason, from the register; a stand's "Faces" and
"Peak month" come from the stand means of each angle's sine and cosine (a stand of flat cells
faces nowhere), where the earlier runs' are plain means of angles, with a note saying so; and the
stands without a type (86 small stands of the hand-crafted Sanjay Van run) say why. Distance to
water at or past 10 km reads "over 10 km" in every run.

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
- `scripts/fetch_ui_r3_layers.py` (round 15): R3's satellite image and land cover, read-only from
  R3's own cached assets (`ee_read_only.forbid_writes()`), into the git-ignored
  `outputs/ui_data_full/r14_areas/`, and the two Sanjay Van runs' per-pixel layers. The four runs
  of an area share their masking and data_load keys, so one download serves them all.
- `scripts/screenshot_explorer.py` (round 15): every step of chosen runs in screenshots, with the
  two panels, into a git-ignored folder (Playwright with Chromium).
- `docs/reproducibility/ui_data_build_run.json`: the record of the last build of `ui_data/` (which
  code, which inputs; the rasters off git with their size and SHA-256).
- `ui_data/`: the data the page reads. `ui_data/index.json` is the contract; its format is in
  `docs/handoff/2026-10-13-round2.md`, task A3, with "Version 2 of the index". The pipeline's
  export writes it.
- `scripts/build_ui_early_data.py`: builds `ui_data/`. R3's runs come from their records
  (`docs/reproducibility/r14_runs/second_half/`, the files off git by their records) and their
  sets' scores; the earlier runs as before. It first built the `ui_data/` from files the 13
  October re-runs had already saved (stands before the merge fix; features as stand means; only the superpixels
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
step: `#odisha_v120_10ha_squares_koraput_keptland_s1desc_r14/field` (R3), or an earlier version's,
`#odisha_v120_3ha_koraput_repro/field`.

To rebuild `ui_data/` (on the Mac, where the files off git are):
`python scripts/fetch_ui_r3_layers.py` (read-only; files already there are not fetched again),
then `python scripts/build_ui_early_data.py`.

## Hosting

`.github/workflows/pages.yml` builds the site on every push and pull request to `main`, and
publishes it to GitHub Pages from `main` only. The repository is public, so the site is public,
FES plot locations included (they are already in the repository). The street map underneath only
loads on the published site; the Claude preview blocks outside map tiles.
