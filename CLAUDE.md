# Working rules for agents in this repo

Two agents work here and hand work to each other through one open PR:

- **Claude Code on Jaskaran's Mac** has Earth Engine and Google Drive access. It runs everything
  that touches Earth Engine.
- **Claude (chat)** works in the cloud with no Earth Engine access. It designs, reviews, does
  offline analysis and writes code that does not need Earth Engine.

Jaskaran reviews and merges. The current task brief is in `docs/handoff/` and is linked from the
open work PR. The PR description is the running handoff note.

## Git

- Work only on the work branch named in the open work PR. Never commit to `main`.
- One task per commit (a task may take several commits). Every commit leaves CI green:
  `pytest`, `ruff check src/ tests/ scripts/`, `mypy src/fmu/ --ignore-missing-imports`.
- Commit message: what changed, why, and how to check it.
- `git pull --rebase` before every push. Never force-push, never rewrite pushed history, never
  merge a PR, never delete a branch.
- After each task, update the checklist in the PR description (task, commit, status) and push.
- Never commit secrets (`.env`, credentials, keys) or large binaries (decks, zips, rasters over
  about 5 MB). Keep those in ignored folders and say in the PR where they are.

## Results

- Existing figures and result files are claims to check, not facts. Regenerate, compare, and
  replace only in a separate commit that states what the comparison showed. Never overwrite a
  committed result silently.
- Result files hold results only, no run times or dates, so that `git diff` after a re-run shows
  whether it reproduced. Timings go to logs.
- Every run manifest records the git commit it ran from and whether the tree had uncommitted
  changes.
- Do not choose settings (k, thresholds, which test, which field typology) by what scores best on
  any one site. Analyses are declared before they are run; the pattern is
  `odisha_script/PHASE3_PREDECLARED.md`.
- Established methods first (Rand index and the like). The rotation null is only the significance
  test behind an established statistic, never a metric of its own.
- ETH canopy height stays in the pipeline. This is the supervisor's decision; do not remove it.
- Keep the pipeline general: no site-specific code in `src/fmu/`.

## Sources

- Every paper cited gets a DOI checked against Crossref
  (`https://api.crossref.org/works/<doi>`): the returned title and first author must match the
  claim. Anything not verified is marked `UNVERIFIED`. Never invent a DOI, a quotation or a
  finding.
- Say what a paper supports: (a) others use the method, (b) a review recommends it, or (c) a
  comparison shows it beats the alternatives. These are different strengths of support.

## Earth Engine

- Run from the repo root: the pipeline reads `.env` from the working directory. See
  `docs/running.md`.
- `odisha_script/run_config_passes.sh` re-submits only missing results. Never start it again while
  tasks from an earlier start are still queued, or it submits a second copy of each. A first pass
  on an empty cache often hits Earth Engine's memory limit; the next pass completes from cache.
- Cached assets live at `{asset_root}/{config_name}/{stage}/{key}__{fingerprint}`. A re-run of
  the same config reads the old assets back, so it is not a reproducibility test. To recompute
  from scratch, copy the config under a new name (for example with a `_repro` suffix), changing
  nothing else.

## When unsure

- If a decision could reasonably go either way, do not guess. Write it under "Questions for
  Jaskaran" in the PR description and move on to the next task.
- If blocked (authentication, quota, an Earth Engine error that persists after the documented
  passes), write it under "Blocked" in the PR description and move on.
