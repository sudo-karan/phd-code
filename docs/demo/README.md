# The demo set

The demo set is the 14 Earth Engine runs of 13 October 2026 (PR #42): every `configs/*_repro.yaml`,
run from scratch at commit `df45350`. It is the data the explorer UI shows and the stands the FES
comparison is made on.

Every output made from it carries this label:

> Demo set: Earth Engine runs of 13 Oct 2026 (commit df45350), stands re-merged under
> `spec-merge-pass2-skip-at-minimum`. Upstream of the merge it carries the open cache-grid issue
> (PR #42, question 1). The final re-run replaces it.

## What is here

| File | What it holds |
|---|---|
| `demo_set.json` | One entry per run: site, district, arm, stand ceiling, k, config, the commit the run came from, every saved Earth Engine asset with the fingerprint in its name, the files sent to Drive, the folders on the Mac, and whether the superpixels were drawn on cached or on live features |
| `demo_set_boxes.json` | The same record for the four box runs of 14 October (below), with how each run's export pass ended and which local files were read back. |
| `remerge/` | The demo set re-merged under the second-pass rule: one summary per run and `README.md`, with what the re-merge showed. Also one summary per box run (`odisha_v120_3ha_squares_<district>.json`). |

## The 14 runs

- **Sanjay Van** (the 1,300 ha working rectangle around the park, not the park boundary): the
  feature vector and AlphaEarth, both with stands up to 10 ha.
- **Odisha**, for each of Angul, Dhenkanal, Kendujhar and Koraput: the feature vector with stands up
  to 3 ha (k = 5) and up to 10 ha (k = 6), and AlphaEarth with stands up to 10 ha (k = 6).

## The four box runs

The hand-crafted arm at 3 ha, run again on a box around each village's plots in place of the hull
of the plots (`configs/odisha_v120_3ha_squares_<district>.yaml`, 8,248 ha in 20 boxes; Jaskaran's
decision of 13 Oct, brief task A0). One batch, started once on 13 Oct from commit `4795358`, with
the second-pass rule on, so these stands are not re-merged. Kendujhar and Angul finished.
For Koraput and Dhenkanal the export pass ended early; their cached assets are complete, and the
local files the pass did not write were read back from those assets with
`odisha_script/odisha_read_back_export.py`, which sends nothing to Earth Engine's task queue.
`demo_set_boxes.json` says which files, run by run.

## Three things to know before using it

1. **The saved assets are read by the paths in `demo_set.json`, never by recomputing a fingerprint
   from a config.** A config that switches a new setting on gets a new fingerprint and would look
   for assets that do not exist. The 14 asset folders are read-only: nothing is added to them,
   changed or deleted. `tests/test_repro_fingerprints.py` pins the 14 fingerprints.
2. **Upstream of the merge the demo set carries the open cache-grid issue.** Cached features sit
   on a geographic grid and segmentation works on the UTM grid, so a run's superpixels depend on
   whether its features were cached when it segmented (`docs/reproducibility.md`, "Superpixels
   depend on whether the features were cached when SNIC ran"). `segmentation_route` in each entry
   says which it was. The final round fixes the cache grid and re-runs everything; that run
   replaces this set.
3. **The stand types a run saved are not, in most runs, the types a second fit gives.** The pass
   that fitted them had computed a feature stage live that later passes read from the cache
   (`remerge/README.md`, section 3). The demo's stand types for the 14 runs are from a fit made
   on the re-merged stands with every input read from the cache. The box runs show the types
   they saved, and carry this.

## How to rebuild and check it

```bash
python scripts/build_demo_set.py                    # lists the asset folders on Earth Engine, read-only
python scripts/build_demo_set.py --from-listing outputs/demo/assets_listing.json    # offline
python scripts/build_demo_set.py --set boxes        # the four box runs, to demo_set_boxes.json
pytest tests/test_demo_set.py
```

The first form submits nothing and changes nothing on Earth Engine. Both write the same file.
