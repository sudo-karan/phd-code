# Forest Management Units (`fmu`)

A modular pipeline for delineating ecologically coherent forest stands from open multi-sensor satellite data, using Google Earth Engine.

**Status:** Pre-alpha. The package skeleton is in place; real stage implementations are being added module by module.

---

## What this is

A Python package (`fmu`) that fuses Sentinel-2 phenology, Sentinel-1 radar, canopy height, and topographic data into per-stand feature vectors, segments the landscape with SNIC, and clusters stands into ecologically meaningful groups — all running server-side on Google Earth Engine.

The pipeline is designed to be:

- **Modular.** Each stage (data loading, masking, feature extraction, segmentation, clustering, profiling, export) is swappable.
- **Configuration-driven.** ROI, dates, parameters, and dataset choices live in YAML files. No hardcoded magic numbers.
- **ROI-agnostic.** The same pipeline runs on any geometry from a 4 km² park to a 10,000 km² forest, with parameters that scale automatically.
- **Reproducible.** Every run produces a manifest pinning config, code version, and outputs.
- **Validation-first.** Every run automatically logs cluster stability, stand statistics, and weak-baseline agreement (WorldCover, Dynamic World).

## What it isn't (yet)

- Not a working end-to-end pipeline — see "Status" above.
- Not a published method — there is no paper yet, and the research question that the pipeline supports is still being developed.
- Not a replacement for ground-truth validation. The pipeline produces unsupervised stand maps; external validation against reference data is a separate, ongoing effort.

## Quick start

```bash
# 1. Clone and enter the repo
git clone <your-fork-url> phd-code
cd phd-code

# 2. Create a Python 3.13 virtual environment
python3.13 -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

# 3. Install in editable mode with dev tools
pip install -e ".[dev]"

# 4. Authenticate with Google Earth Engine (one-time, browser-based)
earthengine authenticate

# 5. Set up environment variables
cp .env.example .env
# Edit .env and set GEE_PROJECT_ID to your project

# 6. Run the smoke test
pytest tests/test_pipeline_smoke.py -v
```

## Repository layout

```
phd-code/
├── src/fmu/              # the package
│   ├── config.py         # Pydantic config + YAML loader
│   ├── pipeline.py       # the orchestrator
│   ├── stages/           # pipeline stages (one module per stage)
│   ├── metrics/          # automatic validation metrics
│   └── utils/            # GEE helpers, logging, etc.
├── configs/              # YAML config files (one per ROI/experiment)
├── tests/                # pytest tests
├── scripts/              # CLI entry points
├── notebooks/exploration/  # scratch notebooks (not part of the package)
├── legacy/               # archive of pre-package work; read-only history
├── .env.example          # template for environment variables
└── pyproject.toml        # package definition + dependencies
```

## How development works

This repo is being built **module by module**, with each module reviewed before the next is started. See `MODULES.md` for the status of each module and what's been locked vs what's in progress.

Design decisions are tracked in the companion `phd-notebook` repo under `decisions.md`. Each significant choice (e.g. Pydantic v2 over dataclasses; SNIC over watershed) has a written justification with a "revisit if..." clause. This is deliberate — the goal is to stop re-litigating settled questions every meeting.

## License

MIT — see `LICENSE`.

## Acknowledgements

Built as part of a PhD project supervised by Prof. Aaditeshwar Seth. The pipeline draws on methods from the multi-sensor remote sensing and land surface phenology literature; specific references are listed in the design document (in the companion `phd-notebook` repo).
