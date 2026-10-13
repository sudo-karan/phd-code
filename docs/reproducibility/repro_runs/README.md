# Re-run configs: mask summary and merge provenance

One folder per `<config>_repro` re-run that has finished (see `docs/reproducibility.md`,
"Earth Engine re-runs"). Each holds what the two transparency scripts report for that re-run,
read from its own cached assets without submitting anything to Earth Engine:

- `mask_summary.md`: the numbers `scripts/transparency_masking.py` reports for the land-cover
  mask (area, share kept, share removed for each reason, which map decided). No date in it.
- `mask_run_record.json`: the config, cache fingerprint, the assets read, the git commit and the
  command of that run.
- `merge_provenance.csv`: one row per stand, from `scripts/inspect_merge.py`: how many
  superpixels it is made of, how many of its merges were first-pass, relaxed second-pass and
  shared-edge fallback merges, and whether and why it ended below the minimum size.

The map images are not committed here. The masks of the re-runs are the same, pixel for pixel,
as the masks of the original configs (`docs/reproducibility.md`), whose maps are in
`docs/transparency/`. The images and rasters of the re-runs are on the Mac under
`outputs/transparency_repro/` (git-ignored); each `mask_summary.md` names its image file.

To make these again for a config (both commands are read-only on Earth Engine):

```bash
python scripts/transparency_masking.py --config configs/<config>_repro.yaml
python scripts/inspect_merge.py --config configs/<config>_repro.yaml
```
