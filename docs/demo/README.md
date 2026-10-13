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

## The 14 runs

- **Sanjay Van** (the 1,300 ha working rectangle around the park, not the park boundary): the
  feature vector and AlphaEarth, both with stands up to 10 ha.
- **Odisha**, for each of Angul, Dhenkanal, Kendujhar and Koraput: the feature vector with stands up
  to 3 ha (k = 5) and up to 10 ha (k = 6), and AlphaEarth with stands up to 10 ha (k = 6).

## Two things to know before using it

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

## How to rebuild and check it

```bash
python scripts/build_demo_set.py                    # lists the asset folders on Earth Engine, read-only
python scripts/build_demo_set.py --from-listing outputs/demo/assets_listing.json    # offline
pytest tests/test_demo_set.py
```

The first form submits nothing and changes nothing on Earth Engine. Both write the same file.
