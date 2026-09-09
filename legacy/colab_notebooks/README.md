# Legacy Colab notebooks

The pre-package method. These are the notebooks the `src/fmu` pipeline was
reconstructed from, and for several decisions they are the only record of what was
actually run before the package existed.

That makes `Untitled4.ipynb` a provenance problem, not just untidy: it is the largest
and most complete of them, it contains the first full SNIC + k-means chain, and its
filename says nothing. A thesis cannot cite "Untitled4".

## Outputs stripped, 2026-09

Cell outputs were cleared from eight of the twelve, taking the directory from
**17.69 MB to 7.17 MB** (59.5% smaller). Two files were almost entirely output:
`Untitled4.ipynb` was 5.26 MB of which 98.9% was output, `Untitled5.ipynb` 4.24 MB of
which 94.4%.

Four were left untouched — `Untitled0`, `Untitled9`, `Untitled10`, `Untitled11`.
Their outputs are 1–2% of their bytes, so re-serialising them would have grown the
files rather than shrunk them. They are large because they contain a lot of *source*,
which is the part worth keeping.

**The outputs are not gone.** No history was rewritten, so every original notebook,
outputs included, is retrievable from git at the commit before this one:

```bash
git log --oneline -- legacy/colab_notebooks/Untitled4.ipynb
git show <commit-before-strip>:legacy/colab_notebooks/Untitled4.ipynb > /tmp/Untitled4_with_outputs.ipynb
```

Note that stripping does **not** shrink `.git` — the old blobs are still in history.
Reclaiming that would mean a history rewrite, which has not been done and should not
be without asking.

## Proposed names

Not renamed. Renaming breaks any external reference to these paths, and the mapping
is a judgement call about what each notebook *was for* — which is the author's to
make. Proposed from reading the cells:

| current | proposed | what it contains |
|---|---|---|
| `Untitled0.ipynb` | `00_empty.ipynb` | one empty cell, no content at all — a candidate for deletion rather than renaming |
| `Untitled1.ipynb` | `01_feature_stack_prototype.ipynb` | first feature stack: harmonic fit, ETH canopy height, S1 GRD, CHIRPS. No segmentation, no clustering |
| `Untitled2.ipynb` | `02_kmeans_on_pixels_with_gedi.ipynb` | k-means directly on pixels, plus a GEDI look and an LULC mask. Pre-SNIC |
| `Untitled3.ipynb` | `03_snic_scratch.ipynb` | single cell, first SNIC call. Scratch |
| `Untitled4.ipynb` | `04_full_chain_snic_kmeans.ipynb` | **the reference notebook.** 24 cells, 45k chars: the complete SNIC → per-superpixel means → wekaKMeans chain with the full feature stack and geemap display |
| `Untitled5.ipynb` | `05_full_chain_condensed.ipynb` | the same chain in 12 cells; looks like a tidy-up of 04 |
| `Untitled6.ipynb` | `06_worldcover_mask_variant.ipynb` | same chain with a WorldCover-based mask |
| `Untitled7.ipynb` | `07_full_chain_variant.ipynb` | another pass at the same chain, 9 cells |
| `Untitled8.ipynb` | `08_terrain_features.ipynb` | adds NASADEM terrain; no harmonic fit and no canopy height |
| `Untitled9.ipynb` | `09_vector_export_and_folium.ipynb` | `reduceToVectors` + `Export.*` + folium display — the first vector export |
| `Untitled10.ipynb` | `10_lulc_and_worldcover_full.ipynb` | largest by source (60k chars): full chain with both LULC and WorldCover masking |
| `Untitled11.ipynb` | `11_full_chain_with_export.ipynb` | full chain plus export; the closest ancestor of the packaged pipeline |

If these are renamed, `git mv` keeps the history attached, and the table above should
move with them so the old names stay findable.

## Caveat on reading them

Nothing here is under test and none of it is the current method. Where a notebook and
`src/fmu` disagree, `src/fmu` is what runs — and `phd-notebook/decisions.md` is the
record of why. Several numbers in these notebooks predate the merge stage entirely,
so any stand count or cluster area in an output cell describes a pipeline that no
longer exists.
