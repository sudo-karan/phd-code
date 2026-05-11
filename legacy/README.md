# Legacy

This directory contains pre-package work from the exploratory phase of the project (notebooks 1–14 from the 7–8 months of Colab development). These files are **read-only historical reference** — they are not executable as part of the current pipeline and may contain bugs, broken asset paths, or dependencies that no longer work.

Do not import from `legacy/`. The active pipeline lives in `src/fmu/`.

## Why we keep them

- They encode the project's intellectual history — what was tried, what worked, what didn't
- They are referenced by the journey document in the companion `phd-notebook` repo
- They contain methods and code patterns that will be ported (selectively) into the package
- Some of them contain plots and outputs that may end up in early thesis chapters or papers

## What's here

`colab_notebooks/` — the 14 Colab notebooks renamed by phase. See the journey document for context on each. A short summary:

| File | Phase | Brief description |
|------|-------|-------------------|
| `01_initial_scaffold.ipynb` | 1 | First multi-sensor scaffold; tried Terasaki-Hart phenology asset (failed). |
| `02_progress_report.ipynb` | 1 | Word-doc progress report generator. |
| `03_diagnostic_pass.ipynb` | 2 | Careful per-sensor verification with diagnostics. |
| `04_first_pipeline.ipynb` | 3 | First full clustering experiment: 4 scenarios (coeffs vs metrics). |
| `05_snic_micro_segmentation.ipynb` | 2 | Tight focus: SNIC + per-segment stats. |
| `06_e2e_clustering.ipynb` | 3 | End-to-end with client-side sklearn. |
| `07_vocab_validation.ipynb` | 4 | "Camera/Heartbeat/Skeleton" framing; first drone overlay. |
| `08_phase_structure.ipynb` | 4 | Pipeline broken into Phase 1/2/3. |
| `09_self_tuning.ipynb` | 5 | Dynamic skew log + auto-K elbow + PALSAR. |
| `10_forest_dna.ipynb` | 5 | "Forest DNA" rewrite; Tasseled Cap; Prosopis labeling. |
| `11_validation_overlay.ipynb` | 6 | Robust scaling; better drone overlay; asset baking. |
| `12_thesis_chapter_draft.ipynb` | 6 | Most complete narrative; feature importance ablation. |
| `13_ecotone_gradients.ipynb` | 6 | Ecotone RGB decomposition; "6 management units". |
| `14_repo_verification.ipynb` | 7 | Verification scratch for the GitHub package. |
